#include <chrono>

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Generation";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    Pythia8::PythiaParallel pythia;
    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Root     rootParams;
                     rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";
    Config::Log      logParams;
    Config::extractConfiguration(configPath, project, logParams, rootParams);
    Config::openOutputFile(rootParams);

    Lambda::Parameters analysisParams;
    Lambda::extractPhysics(configPath, analysisParams, rootParams);
    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, analysisParams, rootParams);

    Monitor::AsyncLogger logger;
    Record::FinalizerController finalizer(
        histogramSets,
        rootParams,
        logParams,
        logger,
        [&analysisParams]() { return Lambda::logString(analysisParams); },
        [&pythia]() { pythia.stat(); },
        [&pythia]() { pythia.settings.listChanged(); }
    );
    finalizer.installFatalStallHandler();

    logParams.start = std::chrono::system_clock::now();
    logger.start(rootParams, logParams);

    pythia.init();

    Lambda::AnalysisContext ctx{histogramSets, analysisParams, logParams, logger};
    pythia.run(static_cast<long>(logParams.nEvents), [&](Pythia8::Pythia* worker) {
        Lambda::pythiaAnalysis(*worker, rootParams, ctx);
    });

    finalizer.normalShutdown();

    return 0;
}
