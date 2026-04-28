#include <chrono>
#include <thread>
#include "Pythia8/Pythia.h"

#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Test";
    const std::string configPath = argc > 1 ? argv[1] : "configs/Lambda_Reconstruction.toml";

    Pythia8::Pythia pythia;
    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Root        rootParams;
    Config::Log         logParams;

    rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";

    Config::extractConfiguration(configPath, project, logParams, rootParams);
    Config::openOutputFile(rootParams);

    Lambda::Parameters  analysisParams;
    Lambda::extractPhysics(configPath, analysisParams, rootParams);
    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, analysisParams, rootParams);

    Monitor::AsyncLogger asyncLogger;
    Record::FinalizerController finalizer(
        histogramSets,
        rootParams,
        logParams,
        asyncLogger,
        [&analysisParams]() { return Lambda::logString(analysisParams); },
        [&pythia]() { pythia.stat(); },
        [&pythia]() { pythia.settings.listChanged(); }
    );
    finalizer.installFatalStallHandler();

    pythia.init();

    logParams.start = std::chrono::system_clock::now();
    asyncLogger.start(rootParams, logParams);
    pythia.next();

    Lambda::AnalysisContext ctx{histogramSets, analysisParams, logParams, asyncLogger};
    for (std::size_t iEvent = 0; iEvent < logParams.nEvents; ++iEvent) {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        Lambda::pythiaAnalysis(pythia, rootParams, ctx);
    }

    finalizer.normalShutdown();

    return 0;
}
