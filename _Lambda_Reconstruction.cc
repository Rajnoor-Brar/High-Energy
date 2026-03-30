#include <chrono>

#include "Pythia8/Pythia.h"

#include "Analysis.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Record.hh"

int main() {
    Pythia8::Pythia pythia;

    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Root        rootParams;
    Config::Log         logParams;
    Lambda::Parameters  analysisParams;

    rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";

    Config::extractParameters("Lambda_Reconstruction", logParams, rootParams);
    Lambda::extractPhysics("Lambda_Reconstruction", analysisParams);

    Lambda::RootArray histogramSets;
    Lambda::declareObjects(histogramSets, analysisParams, rootParams);

    int temp = logParams.nEvents;
    int nDigits = 0;
    while (temp > 0) {
        ++nDigits;
        temp /= 10;
    }
    logParams.nDigits = nDigits;

    pythia.init();

    logParams.start = std::chrono::system_clock::now();

    std::cout << std::endl;

    for (int iEvent = 0; iEvent < logParams.nEvents; ++iEvent) {
        if (!pythia.next()) {
            continue;
        }

        Lambda::pythiaAnalysis(pythia, histogramSets, analysisParams, logParams);
    }

    Analysis::writeAll(histogramSets, rootParams.histScale, logParams.nEvents);
    rootParams.outFile->Close();

    Record::terminalReport(pythia, rootParams, logParams);
    Record::outputLog(pythia, rootParams, logParams, Lambda::logString(analysisParams));

    return 0;
}
