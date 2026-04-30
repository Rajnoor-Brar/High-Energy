#include <chrono>
#include <mutex>
#include <string>

#include <toml++/toml.hpp>

#include "Probe.hh"
#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Reconstruction";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    Config::Register rootParams;
    Config::Watch    logParams;
    Config::ProbeConfig probeConfig;

    Config::configureProbe(configPath, project, logParams, rootParams, probeConfig);
    Config::openOutputFile(rootParams);

    Lambda::Parameters physParams;
    Lambda::extractPhysics(configPath, physParams, rootParams);

    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, physParams, rootParams);

    Monitor::AsyncLogger asyncLogger;

    Record::FinalizerController finalizer(
        histogramSets,
        rootParams,
        logParams,
        asyncLogger,
        [&physParams]() { return Lambda::logString(physParams); }
    );
    finalizer.installFatalStallHandler();

    if(probeConfig.eventConfig.eventCount == 0){
        probeConfig.eventConfig.eventCount = logParams.nEvents = Probe::resolveEventCount(probeConfig.inputFile);
    }
    if(probeConfig.eventConfig.eventCount == 0){
        probeConfig.eventConfig.eventCount = logParams.nEvents = Probe::EventStream(probeConfig.inputFile, Lambda::inputSchema(physParams)).nEvents();
    }

    logParams.start = std::chrono::system_clock::now();
    asyncLogger.start(rootParams, logParams);

    Lambda::AnalysisContext ctx{histogramSets, physParams, logParams, asyncLogger};
    std::mutex histMutex;
    Probe::runParallel(probeConfig.inputFile,
        Lambda::inputSchema(physParams),
        [&](const Probe::Event& ev, int threadId) {
            Lambda::rootAnalysis(ev, threadId, histMutex, ctx);
        },
        Config::resolveThreadCount(logParams.n_threads), probeConfig.eventConfig.eventCount);

    {
        Record::Meta::Record metaRec = Record::Meta::capture("Lambda_Reconstruction", configPath, logParams, rootParams);
        metaRec.dataset.parent_files = {probeConfig.inputFile};
        finalizer.setMeta(std::move(metaRec));
    }
    finalizer.normalShutdown();
 
    return 0;
}
