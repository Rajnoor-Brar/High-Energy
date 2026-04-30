#include <chrono>
#include <mutex>

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Data";
    const std::string configPath = argc > 1 ? argv[1] : "configs/Lambda_Generation.toml";

    Pythia8::PythiaParallel pythia;
    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Register rootParams;
                     rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";
    Config::Watch    logParams;
    Config::extractConfiguration(configPath, project, logParams, rootParams);
    Config::openOutputFile(rootParams);

    if (logParams.n_threads > 0) {
        const std::size_t nThreads = Config::resolveThreadCount(logParams.n_threads);
        pythia.readString("Parallelism:numThreads = " + std::to_string(nThreads));
    }

    Lambda::DataObjects dataObjects;
    Lambda::declareDataObjects(dataObjects, rootParams);
    std::mutex treeMutex;

    Monitor::AsyncLogger logger;

    logParams.start = std::chrono::system_clock::now();
    logger.start(rootParams, logParams);

    pythia.init();

    Lambda::GenerationContext ctx{dataObjects, treeMutex, logParams, logger};
    pythia.run(static_cast<long>(logParams.nEvents), [&](Pythia8::Pythia* worker) {
        Lambda::dataGenerator(*worker, ctx);
    });

    Lambda::RootArray emptyObjects;
    Record::FinalizerController finalizer(
        emptyObjects,
        rootParams,
        logParams,
        logger,
        []() { return Lambda::dataLogString(); },
        [&pythia]() { pythia.stat(); },
        [&pythia]() { pythia.settings.listChanged(); },
        [&dataObjects]() {
            if (dataObjects.protons) dataObjects.protons->BuildIndex("event_index");
            if (dataObjects.pions)   dataObjects.pions->BuildIndex("event_index");
        }
    );
    finalizer.normalShutdown();

    return 0;
}
