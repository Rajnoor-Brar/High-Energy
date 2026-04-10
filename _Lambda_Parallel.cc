#include <chrono>

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

#include "Analysis.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Record.hh"

int main(int argc, char* argv[]) {
    Record::disable_input_echo();

    Pythia8::PythiaParallel pythia;
    const std::string project    = "Lambda_Reconstruction";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Root     rootParams;
                     rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";
    Config::Log      logParams;
    Config::extractConfiguration(configPath, project, logParams, rootParams);

    Lambda::Parameters analysisParams;
    Lambda::extractPhysics(configPath, analysisParams);
    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, analysisParams, rootParams);

    Record::AsyncLogger logger;

    logParams.start = std::chrono::system_clock::now();
    logger.start(rootParams, logParams);
    logger.publish(
        logParams,
        Record::RunPhase::Starting,
        Record::NoEvents,
        Record::RenderStatus,
        Record::DontRenderBar,
        Record::WriteRunStat,
        Record::NoParticleCounts,0,0,
        rootParams.fileTitle.Data()
    );

    pythia.init();

    pythia.run(static_cast<long>(logParams.nEvents), [&](Pythia8::Pythia* worker) {
        Lambda::pythiaAnalysis(*worker, histogramSets, analysisParams, rootParams, logParams, logger);
    });

    Analysis::wrapUp(histogramSets, rootParams.outFile, rootParams.histScale, logParams.nEvents);
    logParams.elapsed = std::chrono::duration_cast<Config::uSeconds>(std::chrono::system_clock::now() - logParams.start);
    logger.finish(logParams, logParams.iEvent.load());

    Record::terminalReport(pythia, rootParams, logParams);
    Record::outputLog(pythia, rootParams, logParams, Lambda::logString(analysisParams));

    return 0;
}
