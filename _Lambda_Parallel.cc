#include <chrono>

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

#include "Analysis.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Record.hh"

int main() {
    Pythia8::PythiaParallel pythia;

    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Root     rootParams;
    Config::Log      logParams;
    Lambda::Parameters analysisParams;

    rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";

    Config::extractParameters("Lambda_Reconstruction", logParams, rootParams);
    Lambda::extractPhysics("Lambda_Reconstruction", analysisParams);

    Lambda::SkipList skipList;
    skipList.validationSkips.push_back(Lambda::ValidationBasis::Mass);
    skipList.validationSkips.push_back(Lambda::ValidationBasis::MassTheta);
    // skipList.quantitySkips.push_back(Lambda::Quantity::Mass);

    Lambda::RootArray validatedObjects;
    Lambda::declareObjects(validatedObjects, analysisParams, rootParams, skipList);

    int temp = logParams.nEvents;
    int nDigits = 0;
    while (temp > 0) {  ++nDigits; temp /= 10;}
    logParams.nDigits = nDigits;

    pythia.init();

    logParams.start = std::chrono::system_clock::now();

    std::cout << std::endl;

    pythia.run(logParams.nEvents, [&](Pythia8::Pythia* worker) {
        Lambda::pythiaAnalysis(*worker, validatedObjects, analysisParams, logParams);
    });

    Analysis::writeAll(validatedObjects, rootParams.histScale, logParams.nEvents);
    rootParams.outFile->Close();

    Record::terminalReport(pythia, rootParams, logParams);

    Record::outputLog(pythia, rootParams, logParams, Lambda::logString(analysisParams));

    return 0;
}
