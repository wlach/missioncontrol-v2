processDownloadsWorked <- FALSE
operating.systems <- c("Windows_NT","Darwin","Linux","overall")
message("Starting posteriors")

release.current.vs.previous <- lapply(operating.systems,function(os){
    compare.two.versions(versiona = getCurrentVersion(dall.rel2,os,'release'),
                         versionb = getPreviousVersion(dall.rel2,os,'release'),
                         oschoice = os,
                         dataset  = dall.rel2,
                         model    = list( mr=cr.cm.rel,cr=cr.cc.rel,mi=ci.cm.rel,ci=ci.cc.rel),
                         doLatest = FALSE)
})
  names(release.current.vs.previous) <- operating.systems

release.current.vs.previous.realNVC <- lapply(operating.systems,function(os){
    compare.two.versions(versiona = getCurrentVersion(dall.rel2,os,'release'),
                         versionb = getPreviousVersion(dall.rel2,os,'release'),
                         oschoice = os,
                         dataset  = dall.rel2,
                         model    = list( mr=cr.cm.rel,cr=cr.cc.rel,mi=ci.cm.rel,ci=ci.cc.rel),
                         doLatest = FALSE,
                         normalizeNVC = FALSE)
})
  names(release.current.vs.previous.realNVC) <- operating.systems

message("Release done")

  beta.current.vs.previous <- lapply(operating.systems,function(os){
    compare.two.versions(versiona = getCurrentVersion(dall.beta2,os,'beta'),
                         versionb = getPreviousVersion(dall.beta2,os,'beta'),
                         oschoice = os,
                         dataset  = dall.beta2,
                         model    = list( mr=cr.cm.beta,cr=cr.cc.beta,mi=ci.cm.beta,ci=ci.cc.beta),
                         doLatest = TRUE)
  })
  names(beta.current.vs.previous) <- operating.systems

message("Beta done")
## It doesn't make sense to set the previous version something that is yesterdays
## There is so little data. Might as well set it to some version with at least 

  nightly.current.vs.previous <- lapply(operating.systems,function(os){
    compare.two.versions(versiona = getPreviousVersion(dall.nightly2,os,'nightly'),
                         versionb = getMaxVersionBeforeX(dall.nightly2, os,'nightly',
                                                         c(getCurrentVersion(dall.nightly2,os,'beta'),getPreviousVersion(dall.nightly2,os,'nightly'))),
                         oschoice = os,
                         dataset  = dall.nightly2,
                         model    = list( mr=cr.cm.nightly,cr=cr.cc.nightly,mi=ci.cm.nightly,ci=ci.cc.nightly),
                         doLatest = TRUE)
  })
  names(nightly.current.vs.previous) <- operating.systems

message("Nightlys done")


message("Starting Summaries")


release.usage <- makeUsageSummary(release.current.vs.previous)
release.summary <- makeSummaryTable(release.current.vs.previous)


beta.usage <- makeUsageSummary(beta.current.vs.previous)
beta.summary <- makeSummaryTable(beta.current.vs.previous)



nightly.usage <- makeUsageSummary(nightly.current.vs.previous)
nightly.summary <- makeSummaryTable(nightly.current.vs.previous)


###############################################################################################
## Evolution Figures
## which indicates the estimate crash rates and incidences of different versions (major/minor)
## Doesn't compare two versions!
###############################################################################################
release.evolution <- get.evolution(model=list( mr=cr.cm.rel,cr=cr.cc.rel,mi=ci.cm.rel,ci=ci.cc.rel),
                                dataset = dall.rel2)
beta.evolution <- get.evolution(model=list( mr=cr.cm.beta,cr=cr.cc.beta,mi=ci.cm.beta,ci=ci.cc.beta),
                                dataset = dall.beta2)
nightly.evolution <- get.evolution(model=list( mr=cr.cm.nightly,cr=cr.cc.nightly,mi=ci.cm.nightly,ci=ci.cc.nightly),
                                dataset = dall.nightly2[c_version<=getCurrentVersion(dall.nightly2,"Linux",'nightly'),])


allversions <- list(
    release=list(v=dall.rel2[,unique(c_version)],c=(release.current.vs.previous)$Darwin$versiona,p=(release.current.vs.previous)$Darwin$versionb),
    beta=list(v=dall.beta2[,unique(c_version)],c=(beta.current.vs.previous)$Darwin$versiona,p=(beta.current.vs.previous)$Darwin$versionb),
    nightly=list(v=dall.nightly2[,unique(c_version)],c=(nightly.current.vs.previous)$Darwin$versiona,p=(nightly.current.vs.previous)$Darwin$versionb)
)

n <- as.character(Sys.Date())
n <- as.character(dall.rel2[,max(date)])
gen.time <- Sys.time()
data.file <- glue("/tmp/models-{n}.Rdata",n=n)
save.list <- list(
    "allversions","gen.time",
    "cr.cm.rel","cr.cc.rel","ci.cm.rel","ci.cc.rel",
    "cr.cm.beta","cr.cc.beta","ci.cm.beta","ci.cc.beta",
    "cr.cm.nightly","cr.cc.nightly","ci.cm.nightly","ci.cc.nightly",
    "dall.rel2","dall.beta2","dall.nightly2",
    "release.current.vs.previous","release.usage","release.summary","release.evolution",
    "beta.current.vs.previous","beta.usage","beta.summary","beta.evolution",
    "nightly.current.vs.previous","nightly.usage","nightly.summary","nightly.evolution"  
)
save(list=unlist(save.list),file=data.file)
system(glue("cp {data.file} ./all.the.data.Rdata"))

system(glue("gsutil cp {data.file}  gs://moz-fx-data-derived-datasets-analysis/sguha/missioncontrol/archive/"))
system(glue("gsutil cp all.the.data.Rdata  gs://moz-fx-data-derived-datasets-analysis/sguha/missioncontrol/archive/"))
slackr(glue("Data file saved at   gs://moz-fx-data-derived-datasets-analysis/sguha/missioncontrol/archive/{data.file}. Download using gsutil cp"))

processDownloadsWorked <- TRUE
