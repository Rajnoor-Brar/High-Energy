#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"
#include "Pythia8/HeavyIons.h"
#include "Math/Vector4D.h"

#include <iostream>
#include <cstdlib>
#include <fstream>
#include <filesystem>
#include <vector>
#include <string>
#include <chrono>
#include "TTimeStamp.h"
#include "TFile.h"
#include "TTree.h"
#include "TH1D.h"
#include <sys/ioctl.h>
#include <unistd.h>

#include "Config_Types.hh"

#include "Analysis_Namespace.hh"

#include "Lambda_Functions.hh"

#include "progress.hh"

int main() {
    
            Pythia8::PythiaParallel pythia;
            
    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Config::Root     rootParams;
    Config::Log      logParams;
    Config::Analysis analysisParams;

    rootParams.beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";;

    extract_Parameters("Lambda_Reconstruction", analysisParams, logParams, rootParams);

    RootAnalysis::SkipList  skipList;
                            skipList.validationSkips.push_back(RootAnalysis::ValidationBasis::Mass);
                            skipList.validationSkips.push_back(RootAnalysis::ValidationBasis::MassTheta);
                            skipList.  quantitySkips.push_back(RootAnalysis::Quantity::Mass);

    RootAnalysis::ValidatedArray validatedObjects;
    RootAnalysis::declareObjects(validatedObjects, analysisParams, rootParams, skipList);

    int temp=logParams.nEvents;
    int nDigits=0; while(temp>0){nDigits++; temp/=10;}
    logParams.nDigits = nDigits;

    pythia.init();

    logParams.start =  std::chrono::system_clock::now();

    std::cout<<std::endl;

                            pythia.run(logParams.nEvents, [&](Pythia8::Pythia* p) {
                                pythiaAnalysis(*p, validatedObjects, analysisParams, logParams);
                            });

    RootAnalysis::writeAll(validatedObjects, analysisParams, logParams);
    rootParams.outFile->Close();

        terminalReport(pythia, rootParams, analysisParams, logParams);

        outputLog(pythia, rootParams, analysisParams, logParams);

    return 0;
}
