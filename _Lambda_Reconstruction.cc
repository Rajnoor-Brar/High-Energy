#include <chrono>

#include "Pythia8/Pythia.h"

#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"

int main(int argc, char* argv[]) {
    Pythia8::Pythia pythia;
    const std::string project    = "Lambda_Reconstruction";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Root        rootParams;
    Config::Log         logParams;

    rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";

    Config::extractConfiguration(configPath, project, logParams, rootParams);

    Lambda::Parameters  analysisParams;
    Lambda::extractPhysics(configPath, analysisParams);
    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, analysisParams, rootParams);

    Monitor::AsyncLogger asyncLogger;
    Record::FinalizerController finalizer(
        pythia,
        histogramSets,
        rootParams,
        logParams,
        asyncLogger,
        [&analysisParams]() { return Lambda::logString(analysisParams); }
    );
    finalizer.installFatalStallHandler();

    logParams.start = std::chrono::system_clock::now();
    asyncLogger.start(rootParams, logParams);
    asyncLogger.publish(
        logParams,
        Monitor::RunPhase::Starting,
        0,
        Monitor::RenderStatus,
        Monitor::DontRenderBar,
        Monitor::WriteRunStat
    );

    pythia.init();
    
    for (std::size_t iEvent = 0; iEvent < logParams.nEvents; ++iEvent) {
        if (!pythia.next()) {
            continue;
        }

        Lambda::pythiaAnalysis(pythia, histogramSets, analysisParams, rootParams, logParams, asyncLogger);
    }

    finalizer.normalShutdown();

    return 0;
}
