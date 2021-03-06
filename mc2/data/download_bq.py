# TODO: modify release for linux build_ids
import datetime as dt
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from functools import partial

import buildhub_bid as bh_bid
import pandas as pd
from pandas import DataFrame
from pandas.testing import assert_frame_equal

# import src.buildhub_bid as bh_bid


SQL_FNAME = "data/download_template.sql"
dbg = lambda: None

os_dtype = pd.CategoricalDtype(
    categories=["Linux", "Darwin", "Windows_NT"], ordered=True
)


def read_product_details():
    pd_url = "https://product-details.mozilla.org/1.0/firefox.json"
    js = pd.read_json(pd_url)
    df = (
        pd.DataFrame(js.releases.tolist())
        .assign(release_label=js.index.tolist())
        .assign(date=lambda x: pd.to_datetime(x.date))
    )
    return df


def next_release_date(
    d: "pd.Series[dt.datetime]", max_days_future=365, use_today_as_max=False
):
    """
    d: Series of dates of releases, ordered by time
    return: date of next release. For most recent release,
        return that date + `max_days_future`
    """
    max_date = pd.to_datetime(dt.date.today()) if use_today_as_max else d.max()

    way_later = max_date + pd.Timedelta(days=max_days_future)
    return d.shift(-1).fillna(way_later)


def add_version_elements(df, element_parser, colname, to=int):
    """
    @element_parser: str -> {element_name: element_val}
    e.g., 65.0b10 -> {'major': '65', 'minor': '10'}
    """
    version_elems = df[colname].map(element_parser).tolist()
    elems_df = DataFrame(version_elems, index=df.index)
    for c in elems_df:
        df[c] = elems_df[c].astype(to)
    return df


def rls_version_parse(disp_vers: str):
    pat = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<dot>\d+))?$")
    m = pat.match(disp_vers)
    if not m:
        raise ValueError("unable to parse version string: {}".format(disp_vers))
    res = m.groupdict()
    if not res["dot"]:
        res["dot"] = "0"
    return res


def beta_version_parse(disp_vers: str):
    pat = re.compile(r"(?P<major>\d+)\.0b(?P<minor>\d+)$")
    m = pat.match(disp_vers)
    if not m:
        raise ValueError("unable to parse version string: {}".format(disp_vers))
    return m.groupdict()


def get_peak_date(vers_df, vers_col="dvers", date_col="date"):
    """
    Get nvc peak date
    """

    def max_nvc_date(ss):
        i = ss.nvc.values.argmax()
        return ss[date_col].iloc[i]

    if not len(vers_df):
        print("Empty dataframe passed. Recent release date?")
        return vers_df.assign(peak_date=[])

    agg_v_o_max_date = (
        vers_df.groupby([vers_col, "os"])
        .apply(max_nvc_date)
        .rename("peak_date")
    )
    vers_df2 = vers_df.merge(
        agg_v_o_max_date, left_on=[vers_col, "os"], right_index=True
    ).sort_index()
    assert_frame_equal(vers_df2.drop("peak_date", axis=1), vers_df)

    return vers_df2


########################
# Product Detail Pulls #
########################
# TODO: choose better min day than "2019-01-01"
def prod_det_process_release(df_all):
    """
    Process and categorize data from
    https://product-details.mozilla.org/1.0/firefox.json
    """
    # Release
    max_days_future = 365
    today = dt.datetime.today().strftime("%Y-%m-%d")  # noqa

    df = df_all.query(
        'category in ["major", "stability"] & date >= "2019-01-01" & date < @today'
    ).copy()

    df = add_version_elements(
        df, rls_version_parse, colname="version", to=int
    ).sort_values(
        # df = add_major_minor_dot(df, version_col="version").sort_values(
        ["major", "minor", "dot"],
        ascending=True,
    )

    # Subset for building model
    cur_major = df.major.iloc[-1]
    recent_majs = [cur_major, cur_major - 1, cur_major - 2]  # noqa
    df_model_release = df.query("major in @recent_majs")

    # Still need for data pull
    df_release_data = (
        df.query("major == @cur_major")[["version", "date"]]
        .assign(
            till=lambda x: next_release_date(
                x["date"], max_days_future=max_days_future
            ),
            channel="release",
            ndays=72,
            app_version_field="app_version",
            crash_build_version_field="environment.build.version",
        )
        .assign(date=lambda x: x.date.dt.date, till=lambda x: x.till.dt.date)
    )  # better string repr

    return df, df_model_release, df_release_data


def prod_det_process_beta(df_all, vers2bids_beta):
    """
    For most recent beta release, pull 7 days into the future.

    """
    days_future = 7
    app_version_field = "app_display_version"
    crash_build_version_field = "environment.build.build_id"
    category = "dev"  # noqa
    channel = "beta"
    ndays = 14
    build_id_mapping = vers2bids_beta

    df = df_all.query('category == @category & date >= "2019-01-01"').copy()
    df = add_version_elements(df, beta_version_parse, "version").sort_values(
        ["major", "minor"], ascending=True
    )

    # Subset for building model
    cur_major = df.major.iloc[-1]
    recent_majs = [cur_major, cur_major - 1, cur_major - 2]  # noqa
    df_model = df.query("major in @recent_majs").reset_index(drop=1)

    # Still need for data pull
    df_download_data = (
        df.query("major == @cur_major")[["version", "date"]]
        .assign(
            till=lambda x: next_release_date(x["date"], days_future),
            channel=channel,
            ndays=ndays,
            app_version_field=app_version_field,
            crash_build_version_field=crash_build_version_field,
        )
        # better string repr
        .assign(date=lambda x: x.date.dt.date, till=lambda x: x.till.dt.date)
        .reset_index(drop=1)
    )
    if build_id_mapping:
        df_download_data = df_download_data.assign(
            buildid=lambda x: x.version.map(build_id_mapping)
        )

    return df, df_model, df_download_data


def prod_det_process_nightly(pd_beta):
    """
    Ok, this is some weird logic.
    beta=70.0b3 is base release of beta cycle. This will correspond
    to vers. 71 on nightly channel. The display version is designated
    as 71.0a1

    """
    df = (
        pd_beta.query("minor == 3")[["major", "date"]]
        .assign(
            till=lambda x: next_release_date(x.date, 0, use_today_as_max=True),
            version=lambda x: x.major.add(1).map("{:.1f}a1".format),
        )
        .reset_index(drop=1)
    )
    beta_last_row = df.iloc[-1]

    df_nightly_data = DataFrame(
        dict(
            date_pd=pd.date_range(beta_last_row.date, beta_last_row.till),
            version=beta_last_row.version,
            channel="nightly",
            app_version_field="substr(app_build_id,1,8)",
            crash_build_version_field="substr(environment.build.build_id, 1, 8)",
            ndays=7,
        )
    ).assign(
        buildid=lambda x: x.date_pd.dt.strftime("%Y%m%d"),
        date=lambda x: x.date_pd.dt.strftime("%Y-%m-%d"),
        till=lambda x: (x.date_pd + pd.Timedelta(days=7)).dt.date,
    )
    recent_majs = [beta_last_row.major, beta_last_row.major + 1]

    df = df[["version", "date", "till"]].assign(
        date=lambda x: x.date.dt.date, till=lambda x: x.till.dt.date
    )
    return df, recent_majs, df_nightly_data


#################
# Build Queries #
#################
def sql_arg_dict(row):
    return dict(
        current_version=row.version,
        # current_version_crash="'{}'".format(row.version),
        current_version_release=row.date,
        norm_channel=row.channel,
        app_version_field=row.app_version_field,
        crash_build_version_field=row.crash_build_version_field,
        nday=row.ndays,
    )


def to_sql_str_list(xs):
    return ", ".join("'{}'".format(s) for s in xs)


def query_from_row_release(row, sql_template):
    """
    Given a sql template string, and a row from product details
    https://product-details.mozilla.org/1.0/firefox.json
    that's been processed, fill in the sql template with
    dates and details for a particular release.
    """
    kwargs = sql_arg_dict(row)
    kwargs_release = dict(current_version_crash="'{}'".format(row.version))
    return sql_template.format(**kwargs, **kwargs_release)


def query_from_row_beta(row, sql_template):
    kwargs = sql_arg_dict(row)
    kwargs_release = dict(current_version_crash="{}".format(row.buildid))
    return sql_template.format(**kwargs, **kwargs_release)


def query_from_row_nightly(row, sql_template):
    kwargs = sql_arg_dict(row)
    kwargs["current_version"] = row.buildid
    kwargs_release = dict(current_version_crash="'{}'".format(row.buildid))
    return sql_template.format(**kwargs, **kwargs_release)


########################
# Actual Data Download #
########################
def add_fields(df, current_version, date0, till):
    date0, till = map(pd.to_datetime, [date0, till])
    round_down = lambda x: 0 if x < 60 / 3600 else x

    df = df.assign(
        # date=date0,
        c_version=current_version,
        c_version_rel=date0,
        isLatest=lambda x: x.date <= till,
        t=lambda x: (x.date - date0).astype("timedelta64[D]").astype(int),
    ).assign(
        cmi=lambda x: (1 + x.dau_cm_crasher_cversion) / x.dau_cversion,
        cmr=lambda x: (1 + x.cmain)
        / x.usage_cm_crasher_cversion.map(round_down),
        # cmr=lambda x: (1 + x.cmain)
        # .div(x.usage_cm_crasher_cversion).map(round_down),
        cci=lambda x: (1 + x.dau_cc_crasher_cversion) / x.dau_cversion,
        ccr=lambda x: (1 + x.ccontent)
        / x.usage_cc_crasher_cversion.map(round_down),
        nvc=lambda x: x.usage_cversion / x.usage_all,
        os=lambda x: x.os.astype(os_dtype),
    )

    # TODO: this might not be necessary
    date_cols = "date c_version_rel".split()  # c_version
    for date_col in date_cols:
        df[date_col] = df[date_col].dt.date
    return df


#############
# Data pull #
#############
def verbose_query(q):
    def pipe_func(df):
        bm = df.eval(q)
        df_drop = df[~bm]
        print("Dropping {} rows that don't match `{}`:".format(len(df_drop), q))
        print(df_drop[["date", "os", "c_version"]])
        return df[bm].copy()

    return pipe_func


def pull_data_base(
    sql_template, download_meta_data, row2query, bq_read, version_col="version"
):
    dfs = []
    for _ix, row in download_meta_data.iterrows():
        query = row2query(row, sql_template)
        dbg.query = query
        df = bq_read(query)
        df2 = add_fields(df, row[version_col], row.date, row.till)
        dfs.append(df2)

    res = pd.concat(dfs, ignore_index=True)
    return res


def pull_data_release(download_meta_data, sql_template, bq_read, process=True):
    """
    isLatest comes from product_details.json, looking for next release
    date within a channel.
    """
    data = pull_data_base(
        sql_template,
        download_meta_data,
        query_from_row_release,
        bq_read=bq_read,
    )
    data = add_version_elements(data, rls_version_parse, "c_version", to=int)
    if process:
        data = (
            get_peak_date(data, "c_version")
            .pipe(verbose_query("(date <= peak_date) or isLatest"))
            .drop(["minor", "peak_date"], axis=1)
            .rename(columns={"dot": "minor"})
            .reset_index(drop=1)
        )
    return data


def pull_data_beta(download_meta_data, sql_template, bq_read, process=True):
    data = pull_data_base(
        sql_template, download_meta_data, query_from_row_beta, bq_read=bq_read
    )
    data = add_version_elements(data, beta_version_parse, "c_version", to=int)
    # TODO: have this optional for debugging for now
    if process:
        data = (
            get_peak_date(data, "c_version")
            .pipe(verbose_query("date <= peak_date"))
            .drop(["peak_date"], axis=1)
            .reset_index(drop=1)
        )
    return data


def pull_data_nightly(download_meta_data, sql_template, bq_read, process=True):
    data = pull_data_base(
        sql_template,
        download_meta_data,
        query_from_row_nightly,
        bq_read=bq_read,
        version_col="buildid",
    )
    # Unless we convert the nightly query to use buildhub
    assert (
        download_meta_data["version"].nunique() == 1
    ), "assuming single version for nightly metadata"
    display_version = download_meta_data["version"].iloc[0]
    # TODO: have this optional for debugging for now
    if process:
        data = (
            get_peak_date(data, "c_version")
            .pipe(verbose_query("date <= peak_date"))
            .drop(["peak_date"], axis=1)
            .assign(
                major=lambda _: int(display_version.split(".0a")[0]),
                minor=lambda x: x.c_version,
            )
            .reset_index(drop=1)
        )
    return data


###########
# Combine #
###########
@contextmanager
def pull_done(msg):
    try:
        print("{}...".format(msg), end="")
        sys.stdout.flush()
        yield
    finally:
        print(" Done.")


def read(fname):
    if not os.path.exists(fname):
        raise Exception(
            "{} not found. Make sure pwd is set to project dir.".format(fname)
        )
    with open(fname, "r") as fp:
        txt = fp.read()
    return txt


def write(fname, txt):
    with open(fname, "w") as fp:
        fp.write(txt)


def pull_all_model_data(bq_read, sql_fname=SQL_FNAME):
    pd_all = read_product_details()
    pd_release, pd_release_model, pd_release_download = prod_det_process_release(
        pd_all
    )

    sql_template = read(sql_fname)
    dbg.meta = pd_release_download
    dbg.sql = sql_template
    dbg.bq_read = bq_read

    with pull_done("\nPulling release data"):
        df_release = pull_data_release(
            pd_release_download, sql_template, bq_read
        )

    # docs_rls = bh_bid.pull_build_id_docs(channel="release")
    # vers2bids_rls = bh_bid.version2build_ids(docs_rls, keep_release=True)

    docs_beta = bh_bid.pull_build_id_docs()
    vers2bids_beta = bh_bid.version2build_id_str(docs_beta)
    pd_beta, _pd_beta_model, pd_beta_download = prod_det_process_beta(
        pd_all, vers2bids_beta
    )

    # TODO: debug
    dbg.pd_beta_download = pd_beta_download
    # raise ValueError

    with pull_done("\nPulling beta data"):
        df_beta = pull_data_beta(
            # todo: debug process=False
            pd_beta_download,
            sql_template,
            bq_read,
            process=True,
        )

    pd_nightly, pd_nightly_model, pd_nightly_download = prod_det_process_nightly(
        pd_beta
    )

    with pull_done("\nPulling nightly data"):
        df_nightly = pull_data_nightly(
            pd_nightly_download, sql_template, bq_read, process=True
        )

    df_all = pd.concat(
        [
            df_release.assign(channel="release"),
            df_beta.assign(channel="beta"),
            df_nightly.assign(channel="nightly"),
        ],
        ignore_index=True,
        sort=False,
    ).assign(
        minor=lambda x: x.minor.astype(int), major=lambda x: x.major.astype(int)
    )

    return df_all


############################################
# Pull model data after it's been uploaded #
############################################
def pull_model_data_pre_query(
    bq_read_fn, channel, n_majors, analysis_table="wbeard_crash_rate_raw"
):
    pre_query = """
    select distinct major from `moz-fx-data-derived-datasets`.analysis.{table}
    where channel = '{channel}'
    ORDER BY major desc
    LIMIT {n}
    """.format(
        table=analysis_table, n=n_majors, channel=channel
    )
    pre_data = bq_read_fn(pre_query)
    prev_majors = pre_data.major.astype(int).tolist()
    prev_major_strs = ", ".join(map(str, prev_majors))
    print(
        "Previous majors for `{}` were: {}. Pulling now...".format(
            channel, prev_majors
        )
    )

    return prev_major_strs


def pull_model_data_(bq_read_fn, channel, n_majors, analysis_table):
    prev_major_strs = pull_model_data_pre_query(
        bq_read_fn, channel, n_majors, analysis_table
    )

    pull_all_recent_query = """
    select * from `moz-fx-data-derived-datasets`.analysis.{table}
    where channel = '{channel}'
          and major in ({major_strs})
    """.format(
        table=analysis_table, channel=channel, major_strs=prev_major_strs
    )
    print("Running query:\n", pull_all_recent_query)
    df = bq_read_fn(pull_all_recent_query)
    return df


def download_raw_data(
    bq_read_fn, channel, n_majors: int, analysis_table, outname=None
):
    """
    Given a channel and a number of recent major version, return all of the
    uploaded raw mission control v2 data that matches the `n_majors` most
    recent major version of that channel.

    First do this by querying the MC v2 table for what those major versions
    are.

    This will write the file to a temporary feather file and return the filename.
    """
    df = pull_model_data_(bq_read_fn, channel, n_majors, analysis_table)
    if outname is None:
        outname = tempfile.NamedTemporaryFile(delete=False, mode="w+").name
    df.to_feather(outname)

    print("feather file saved to {}".format(outname))
    return outname
