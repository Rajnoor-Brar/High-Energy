#include "Pythia8/Pythia.h"
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

#include "Lambda_Defines.hh"

#include "progress.hh"
// ------------------------------------------------------------------------------------------------------------------------------------

DECLARE_THEM_ALL

#include "Lambda_Analysis.hh"

int main() {
    
            Pythia8::Pythia pythia;
            
    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";
        EXTRACT_CONFIRGURATION
    
            DEFINE_THEM_ALL
            // Defines count variables, Histograms and Directory

    int temp=nEvents;
    nDigits=0; while(temp>0){nDigits++; temp/=10;}

    pythia.init();
    start = SysClock::now();
    std::cout<<std::endl;

    for(iEvent = 1; iEvent <=nEvents; ++iEvent){
        if(!pythia.next()) continue;
        pythiaAnalysis(pythia);
    }

    std::cout<<std::setfill(' ')<<"\n\n";
    pythia.stat();

        WRITE_THEM_ALL

    outFile->Close();

    now = SysClock::now();
    elapsed = Chrono::duration_cast<uSeconds>( now - start);
        time_t localNow = SysClock::to_time_t(now);
    std::cout << std::put_time(std::localtime(&localNow), "%F %T \n");
    std::cout << durationString(elapsed) << std::endl;

           outputLog(pythia);

    return 0;
}
