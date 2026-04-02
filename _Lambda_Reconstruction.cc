#include <chrono>

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
    Lambda::Parameters  analysisParams;

    rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";

    Config::extractParameters(configPath, project, logParams, rootParams);
    Lambda::extractPhysics(configPath, analysisParams);

    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, analysisParams, rootParams);

    std::size_t temp = logParams.nEvents;
    std::size_t nDigits = 0;
    while (temp > 0) {
        ++nDigits;
        temp /= 10;
    }
    logParams.nDigits = nDigits;

    pythia.init();

    logParams.start = std::chrono::system_clock::now();

    std::cout << std::endl;

    for (std::size_t iEvent = 0; iEvent < logParams.nEvents; ++iEvent) {
        if (!pythia.next()) {
            continue;
        }

        Lambda::pythiaAnalysis(pythia, histogramSets, analysisParams, rootParams, logParams);
    }

    Analysis::wrapUp(histogramSets, rootParams.outFile, rootParams.histScale, logParams.nEvents);

    Record::terminalReport(pythia, rootParams, logParams);
    Record::outputLog(pythia, rootParams, logParams, Lambda::logString(analysisParams));

    return 0;
}
