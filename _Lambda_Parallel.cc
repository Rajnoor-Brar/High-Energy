#include <chrono>

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

#include "Analysis.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Record.hh"

int main(int argc, char* argv[]) {
    Pythia8::PythiaParallel pythia;
    const std::string project    = "Lambda_Reconstruction";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Root     rootParams;
    Config::Log      logParams;
    Lambda::Parameters analysisParams;

        rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";

    Config::extractParameters(configPath, project, logParams, rootParams);
    Lambda::extractPhysics(configPath, analysisParams);

    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, analysisParams, rootParams);

    pythia.init();

        logParams.start = std::chrono::system_clock::now();

    pythia.run(static_cast<long>(logParams.nEvents), [&](Pythia8::Pythia* worker) {
        Lambda::pythiaAnalysis(*worker, histogramSets, analysisParams, rootParams, logParams);
    });

    Analysis::wrapUp(histogramSets, rootParams.outFile, rootParams.histScale, logParams.nEvents);

    Record::terminalReport(pythia, rootParams, logParams);

    Record::outputLog(pythia, rootParams, logParams, Lambda::logString(analysisParams));

    return 0;
}
