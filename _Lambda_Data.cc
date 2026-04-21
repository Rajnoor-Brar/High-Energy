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
    Config::Root rootParams;
                 rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";
    Config::Log  logParams;
    Config::extractConfiguration(configPath, project, logParams, rootParams);
    Config::openOutputFile(rootParams);

    if (logParams.nThreads > 0) {
        const std::size_t nThreads = Config::resolveThreadCount(logParams.nThreads);
        pythia.readString("Parallelism:numThreads = " + std::to_string(nThreads));
    }

    Lambda::DataObjects dataObjects;
    Lambda::declareDataObjects(dataObjects, rootParams);
    std::mutex treeMutex;

    Monitor::AsyncLogger logger;

    logParams.start = std::chrono::system_clock::now();
    logger.start(rootParams, logParams);

    pythia.init();

    pythia.run(static_cast<long>(logParams.nEvents), [&](Pythia8::Pythia* worker) {
        Lambda::pythiaGenerator(*worker, dataObjects, treeMutex, logParams, logger);
    });

    rootParams.outFile->Write("", TObject::kOverwrite);
    rootParams.outFile->Close();

    logParams.elapsed = std::chrono::duration_cast<Config::uSeconds>(
        std::chrono::system_clock::now() - logParams.start);
    logger.finish(logParams, logParams.iEvent.load());
    Monitor::terminalReport(pythia, rootParams, logParams);
    Monitor::outputLog(pythia, rootParams, logParams, Lambda::dataLogString());

    return 0;
}
