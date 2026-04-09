#include <chrono>
#include <thread>
#include "Pythia8/Pythia.h"

#include "Analysis.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Record.hh"

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

    Record::AsyncLogger asyncLogger;

    pythia.init();

    logParams.start = std::chrono::system_clock::now();
    asyncLogger.start(rootParams, logParams);
    asyncLogger.publish(
        logParams,
        Record::RunPhase::Starting,
        0,
        Record::RenderStatus,
        Record::DontRenderBar,
        Record::WriteRunStat
    );
    pythia.next();
    for (std::size_t iEvent = 0; iEvent < logParams.nEvents; ++iEvent) {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        Lambda::pythiaAnalysis(pythia, histogramSets, analysisParams, rootParams, logParams, asyncLogger);
    }

    Analysis::wrapUp(histogramSets, rootParams.outFile, rootParams.histScale, logParams.nEvents);
    logParams.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logParams.start);
    asyncLogger.finish(logParams, logParams.iEvent.load());

    Record::terminalReport(pythia, rootParams, logParams);
    Record::outputLog(pythia, rootParams, logParams, Lambda::logString(analysisParams));

    return 0;
}
