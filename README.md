# missioncontrol-v2
An alternate view of crash and stability

## Installation instructions

This code is designed to be 'easy' to install and repeatable. That is if the underlying data doesn't change the output should not either.

- Strongly recommend you use a 16 core (at least) compute intensive
  GCP instance. I don't believe this works on general purpose
  instances. I used a Ubuntu 18.04 LTS release with 30GB disk space
- Setup your instances and be sure to upload your BigQuery service account credentials (for querying BigQuery via python)

```
sudo apt -y update 
sudo apt -y install python3-pip
sudo pip3 install bq-utils


gcloud auth activate-service-account --key-file=/home/sguha/gcloud.json # your service account credential file
gcloud config set project moz-fx-data-derived-datasets
bq init # choose the number corresponding to the above project
```

- Install R on your instances

```
sudo apt install apt-transport-https software-properties-common

sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys E298A3A825C0D65DFD57CBB651716619E084DAB9

sudo add-apt-repository 'deb https://cloud.r-project.org/bin/linux/ubuntu bionic-cran35/'

sudo apt update
sudo apt install r-base
sudo apt install libssl-dev
sudo apt install libcurl4-openssl-dev
```


- Time to install Conda, download fromhere https://www.anaconda.com/distribution/#download-section (choose Linux, Python 3.7 x86-64 installer)
- Install it, log out, log back in and run `conda init bash` and log out and log back in

- Clone the repo `git clone  https://github.com/mozilla/missioncontrol-v2`
- switch to the `missionctrol-v2` directory

```
conda env create -f environment.yml
conda acvtivate mc2
```


- you've installed R, the following instructions will download all the required packages
- start R in the `missioncontrol-v2` directory, you'll get a message about `renv` being installed. Let it happen. Once it has,

```
options(Ncpus=14)
renv::restore()
```

- and say `Y` to install the packages.

By now eveything is installed. Lets run


## Instructions to run


### Download Data and Build Model

We'll call from R,

- change directory to `missioncontrol-v2`
- run the following (the environment variable prevents paths from getting mixed up)

```
export PYTHONNOUSERSITE=True
conda acvtivate mc2
```

- start R, the following file has a path  to a BigQuery credentials(`BQCREDS` in the above R file) . You need this(a service account json file)

```
source("download.data.and.build.model.R")
```


### Process Model Output

- then run the following. This command munges model output, and saves
  all the model information in an Rdata file and uploads to 
  `gs://moz-fx-data-derived-datasets-analysis/sguha/missioncontrol/archive/`

```
source("process.model.and.build.board.R")
```



- Once this is done, we generate the dashboards using rmarkdown which
  will produce static HTML files and uploads them to gs. There are two
  versions, one for public (sans DAU) and for us(with DAU).

And you're done. All of this ought to take roughtly 50 minutes. The models take about 40 minutes. 

(the above commands are present in the single bash file `complete.runner.sh`) e.g.

```
sh complete.runner.sh  2>&1 | tee logfile
```

It is a good idea to save the logfile to say
`gs://moz-fx-data-derived-datasets-analysis/sguha/missioncontrol/archive/`
so that when someone needs to debug they can read the logfile for informtation.

```
gsutil cp logfile gs://moz-fx-data-derived-datasets-analysis/sguha/missioncontrol/archive/
```


# Gotchas
- if you run the data pulling code shortly after a new release, and did not pull data in the
previous days, then those days' data could be missing for the previous major release versions.

## Using buildhub_bid.py

```
$ python buildhub_bid.py
{'67.0b19': [('67.0b19', '20190509185224', 1557440284038)], '67.0b18': [('67.0b18', '20190506235559', 1557198168463)], '67.0b17': [('67.0b17', '20190505015947', 1557029673054)], '67.0b16': [('67.0b16', '20190502232159', 1556853606531), ('67.0b16', '20190502224831', 1556845098897)], '67.0b15': [('67.0b15', '20190429125729', 1556568682185)], '67.0b14': [('67.0b14', '20190424140259', 1556129999744)], '67.0b13': [('67.0b13', '20190422163745', 1555961835650)], '67.0b12': [('67.0b12', '20190418160535', 1555623291044)], '67.0b11': [('67.0b11', '20190415085659', 1555336602366)], '67.0b10': [('67.0b10', '20190411084603', 1554986422095)], '67.0b9': [('67.0b9', '20190408123043', 1554735105625)], '67.0b8': [('67.0b8', '20190404130536', 1554387637419), ('67.0b8', '20190404040123', 1554356102631)], '67.0b7': [('67.0b7', '20190331141835', 1554108515909)], '67.0b6': [('67.0b6', '20190328152334', 1553800576367)], '67.0b5': [('67.0b5', '20190325125126', 1553534107445)], '67.0b4': [('67.0b4', '20190322012752', 1553242114648), ('67.0b4', '20190321164326', 1553202047019)], '67.0b3': [('67.0b3', '20190318154932', 1552936543292)]}


release
{'67.0.4': [('67.0.4', '20190619235627', 1560996835776)], '67.0.3': [('67.0.3', '20190618025334', 1560836951266)], '67.0.2': [('67.0.2', '20190607204818', 1560068562495), ('67.0.2', '20190605225443', 1559794985112)], '67.0.1': [('67.0.1', '20190529130856', 1559144445386)], '67.0': [('67.0', '20190516215225', 1558053461988), ('67.0', '20190513195729', 1557789027847)]}

```

## Testing
```
$ ipython
import sys
sys.path.insert(0, '/Users/wbeard/repos/missioncontrol-v2/src/')
import src.crud as crud
%load_ext autoreload
%autoreload 2
```
