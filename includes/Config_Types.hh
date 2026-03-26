#pragma once

#include <chrono>
#include "TDirectory.h"
#include "TFile.h"
#include "TH1.h"
#include "TH1D.h"
#include "TTree.h"

namespace Config{
    using TimePoint = std::chrono::system_clock::time_point;
    using uSeconds  = std::chrono::microseconds; 

    struct Analysis {
        Double_t    lambdaMass           = 1.115;
        Double_t    lambdaEnergy         = 1.115; 
        Double_t    protonMass           = 0.938; 
        Double_t    pionMass             = 0.140;
        Double_t    massDiff             = 0.037;     //lambdaMass - (protonMass + pionMass)
        Double_t    EnergyTolerance      = 0.1 ;
        Double_t    MassTolerance        = 0.05; 
        Double_t    ThetaTolerance       = 0.1 ;
        Double_t    histScale            = 100 ;
        Double_t    lambdaMomentum       = 1.115;
        Double_t    lambdaTransMomentum  = 1.0;
        Double_t    etaExtent            = 5.0;
    };

    struct Log {
    std::atomic<Int_t> iEvent = 0;  // atomic just in case
                Int_t  serial          = 0   ;
                Int_t  nEvents         = 100 ;
                Int_t  nRealEvents     = 0   ;
                Int_t  nDigits         = 0   ;
                Int_t  printInterval   = 10  ;
                Int_t  barInterval     = 50  ;
            TimePoint  start           = TimePoint{};
            uSeconds   elapsed         = uSeconds(0) ;
    };

    struct Root{
        TFile*  outFile       = nullptr;
        TString rootDirectory = "output/Lambda_Reconstruction/";
        TString logDirectory  = "output/Lambda_Reconstruction/params/";
        TString beamEnergy    = "";
        TString outName       = "";
        TString logName       = "";
        TString fileTitle     = "";
        Int_t   binCount        = 100;
    };

}