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


#define DEFINE_VARS(name, title) \
    TDirectory* name##ValidatedDirectory = outFile->mkdir(title "Validated"); \
    Int_t name##ValidatedCount=0;\
    TH1D* name##ValidatedMassHist          = new TH1D(#name "Validated_Mass_Hist"               , "Mass Distribution of Reconstructed Lambda-particles", \
                                                                                                        binCount, binLimiter(#name,0,0), binLimiter(#name,0,1)); \
    TH1D* name##ValidatedEnergyHist        = new TH1D(#name "Validated_Energy_Hist"             , "Energy Distribution of Reconstructed Lambda-particles",  \
                                                                                                        binCount, binLimiter(#name,1,0), binLimiter(#name,1,1)); \
    TH1D* name##ValidatedNetMomentumHist   = new TH1D(#name "Validated_Total_Momentum_Hist"     , "Momentum Distribution of Reconstructed Lambda-particles", \
                                                                                                        binCount, binLimiter(#name,2,0), binLimiter(#name,2,1)); \
    TH1D* name##ValidatedTransMomentumHist = new TH1D(#name "Validated_Transverse_Momentum_Hist", "Transverse Momentum Distribution of Reconstructed Lambda-particles", \
                                                                                                        binCount, binLimiter(#name,3,0), binLimiter(#name,3,1)); \
    TH1D* name##ValidatedEtaHist           = new TH1D(#name "Validated_Eta_Hist"                , "Eta Distribution of Reconstructed Lambda-particles", \
                                                                                                        binCount, binLimiter(#name,4,0), binLimiter(#name,4,1)); \
    TH1I* name##ValidatedCountHist         = new TH1I(#name "CountHist"                         , "Count of Reconstructed Lambda-particles", \
                                                                                                        41, -0.5, 40.5);   

#define FILL_TO(name)\
    name##ValidatedCount++;\
    name##ValidatedTransMomentumHist ->Fill( lambda.Pt()  );\
    name##ValidatedNetMomentumHist   ->Fill( lambda.P()   );\
    name##ValidatedMassHist          ->Fill( lambda.M()   );\
    name##ValidatedEnergyHist        ->Fill( lambda.E()   );\
    name##ValidatedEtaHist           ->Fill( lambda.Eta() );

#define COUNT_FILL(name) \
    name##ValidatedCountHist->Fill(name##ValidatedCount);

#define COUNT_RESET(name) \
    name##ValidatedCount = 0;

#define SCALE_AND_WRITE(hist) \
    { Double_t _n = nEvents; \
      if (_n > 0) (hist)->Scale(histScale/_n, "width"); \
            (hist)->Write(); }
// (hist)->GetEntries()
#define WRITE_TO(name) \
    name##ValidatedDirectory->cd();\
    name##ValidatedCountHist           ->Scale(histScale/nEvents);\
    name##ValidatedCountHist           ->Write();\
    SCALE_AND_WRITE(name##ValidatedMassHist) \
    SCALE_AND_WRITE(name##ValidatedNetMomentumHist) \
    SCALE_AND_WRITE(name##ValidatedTransMomentumHist) \
    SCALE_AND_WRITE(name##ValidatedEnergyHist) \
    SCALE_AND_WRITE(name##ValidatedEtaHist)

#define DEFINE_THEM_ALL \
    DEFINE_VARS(un,          "un")          \
    DEFINE_VARS(Mass,        "Mass")        \
    DEFINE_VARS(Energy,      "Energy")      \
    DEFINE_VARS(Theta,       "Theta")       \
    DEFINE_VARS(EnergyMass,  "Energy-Mass") \
    DEFINE_VARS(EnergyTheta, "Energy-Theta")\
    DEFINE_VARS(MassTheta,   "Mass-Theta")  \
    DEFINE_VARS(All,         "All")

#define COUNT_FILLER \
    COUNT_FILL(un)          \
    COUNT_FILL(Mass)        \
    COUNT_FILL(Energy)      \
    COUNT_FILL(Theta)       \
    COUNT_FILL(EnergyMass)  \
    COUNT_FILL(EnergyTheta) \
    COUNT_FILL(MassTheta)   \
    COUNT_FILL(All)

#define COUNT_RESETTER \
    COUNT_RESET(un)          \
    COUNT_RESET(Mass)        \
    COUNT_RESET(Energy)      \
    COUNT_RESET(Theta)       \
    COUNT_RESET(EnergyMass)  \
    COUNT_RESET(EnergyTheta) \
    COUNT_RESET(MassTheta)   \
    COUNT_RESET(All)

#define WRITE_THEM_ALL \
    WRITE_TO(un)          \
    WRITE_TO(Mass)        \
    WRITE_TO(Energy)      \
    WRITE_TO(Theta)       \
    WRITE_TO(EnergyMass)  \
    WRITE_TO(EnergyTheta) \
    WRITE_TO(MassTheta)   \
    WRITE_TO(All)

using Lorentz  = ROOT::Math::PxPyPzEVector;
using SysClock = std::chrono::system_clock;
using uSeconds = std::chrono::microseconds;
using Seconds  = std::chrono::seconds;
using Minutes  = std::chrono::minutes;
using Hours    = std::chrono::hours;
using String   = std::string;
using std::to_string;
namespace Filesystem = std::filesystem;
namespace Chrono = std::chrono;

struct winsize w;

void printProgressStat(int iEvent, int nEvents, int nDigits, String ETA){

    std::cout<<std::setfill(' ')<<"\033[2A\r"<<"\t Events processed : "
                                  <<std::setw(nDigits)<<std::setfill(' ')<<iEvent<<" out of "<< nEvents<<"  |  "
                                  <<std::setw(2)<<100*iEvent/nEvents
                                    <<"% \033[B\r"<<ETA<<"\033[B\r"<<std::flush;
}

String durationString(uSeconds duration, bool showSeconds=true){
    std::ostringstream durString;
    int totalSeconds = Chrono::duration_cast<Seconds>(duration).count(),
        expectedSeconds = totalSeconds%60,
        expectedMinutes = (totalSeconds/60)%60,
        expectedHours   = (totalSeconds/3600)%24, 
        expectedDays    = totalSeconds/86400;

    durString<<(expectedDays ? to_string(expectedDays)+" days " : "")
            <<(expectedHours ? to_string(expectedHours)+" hours " : "")
            <<(expectedMinutes ? to_string(expectedMinutes)+" minutes " : ((!showSeconds && !(expectedDays || expectedHours)) ? " a min " : ""))
            <<((showSeconds && expectedSeconds) ? to_string(expectedSeconds)+" seconds " : "");
    return durString.str();
}
    
String updatedETA(int iEvent, int nEvents,Chrono::microseconds duration){
    uSeconds waitTime = ((nEvents-iEvent)/iEvent)*duration;

    std::ostringstream ETA;

    time_t expectedTime = SysClock::to_time_t(SysClock::now() + waitTime);
    ETA<<"\033[2K\tETA : "<<std::put_time(std::localtime(&expectedTime), "%F %T ")
                    <<" in " <<durationString(waitTime, true);         
    return ETA.str();
}

void printProgressBar(double progress){
    ioctl(STDOUT_FILENO, TIOCGWINSZ, &w);
    int nCols = (int)w.ws_col ? ((int)w.ws_col)-6 : 100;
    int filledCols = (int)(progress*nCols);
    std::cout<<"\r\033[2K"<<"\033[32;1m|"<<String(filledCols,'-')<<"\033[0m"<<">"<<"\033[31m"<<String(nCols-filledCols,'.')<<"|\033[0m"<<std::flush;
}

double binLimiter(String Validation, int quantity, int bound=1){
    static double m = 1.115, e = 1.115, p = 1.115, pT = 1 , eta = 5;
    static int lowLimit = 0, mediumLimit = 1, highLimit = 2;
    int limit=-1, validationIndex = -1;

    if      (Validation == "un")          validationIndex = 0;
    else if (Validation == "Mass")        validationIndex = 1;
    else if (Validation == "Energy")      validationIndex = 2;
    else if (Validation == "Theta")       validationIndex = 3;
    else if (Validation == "EnergyMass")  validationIndex = 4;
    else if (Validation == "EnergyTheta") validationIndex = 5;
    else if (Validation == "MassTheta")   validationIndex = 6;
    else if (Validation == "All")         validationIndex = 7;
    // 1 - mass, 2 - energy, 3 - P, 4 - Pt, 5 - Eta ; quantities ; indices are -1'ed
    // 1 - un , 2 - Mass , 3 - Energy , 4 - Theta , 5 - EnergyMass , 6 - EnergyTheta ,  7- MassTheta ,  8 - All
    static int limitMap[8][5]={
                            {highLimit ,   highLimit ,    highLimit ,   highLimit ,   highLimit},
                            { lowLimit ,   highLimit ,    highLimit ,   highLimit , mediumLimit},
                            { lowLimit ,    lowLimit ,     lowLimit ,    lowLimit ,    lowLimit},
                            {highLimit ,   highLimit ,    highLimit ,   highLimit ,   highLimit},
                            { lowLimit ,    lowLimit ,     lowLimit ,    lowLimit ,    lowLimit},
                            { lowLimit ,    lowLimit ,     lowLimit ,    lowLimit ,    lowLimit},
                            { lowLimit , mediumLimit ,  mediumLimit , mediumLimit ,    lowLimit},
                            { lowLimit ,    lowLimit ,     lowLimit ,    lowLimit ,    lowLimit}
                    };
    static double quantityLimits[5][3][2] = {
        {
            { m * 0.89 ,  m * 1.1 },
            { m * 0.8   ,  m * 1.25   },
            { m * 0.25,  m * 10  }
        },
        {
            { e * 0.89 ,  e * 1.2 },
            { e * 0.89 ,  e * 1.8   },
            { e * 0.89 ,  e * 10  }
        },
        {
            { 0      ,  p * 0.8 },
            { 0      ,  p * 1.5 },
            { 0      ,  p * 10  }
        },
        {
            { 0      ,  pT * 0.6 },
            { 0      ,  pT * 1.3 },
            { 0      ,  pT * 3 }
        },
        {
            { eta * -1 ,  eta * 1 },
            { eta * -2 ,  eta * 2 },
            { eta * -4 ,  eta * 4 }
        }
    };
    if (validationIndex<0){std::cout<<"\n\n Validation Failed \n"; validationIndex=0;}
    limit = limitMap[validationIndex][quantity];
    return quantityLimits[quantity][limit][bound];
}
// ------------------------------------------------------------------------------------------------------------------------------------

int main() {


    const Chrono::time_point<SysClock> start = SysClock::now();
    Chrono::time_point<SysClock> now;
    uSeconds elapsed = Chrono::duration_cast<uSeconds>(now - start);
    const time_t localStart = SysClock::to_time_t(start);
    
            Pythia8::Pythia pythia;
            
    pythia.readFile("configs/Lambda_Reconstruction.cmnd");
    Double_t lambdaMass = 1.115, lambdaEnergy = 1.115, protonMass = 0.938, pionMass = 0.140,\
             massDiff = lambdaMass - (protonMass + pionMass);

        Double_t EnergyTolerance=0.1, MassTolerance=0.05, ThetaTolerance=0.1;
        Int_t serial=0, nEvents=100, printInterval=10, binCount=100; Double_t histScale=100;

            std::ifstream configFile("configs/Lambda_Reconstruction.in");

            TString rootDirectory = "output/Lambda_Reconstruction/", logDirectory = "output/Lambda_Reconstruction/params/";
            TString beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";

            configFile >> serial >> nEvents >> printInterval >> binCount >> histScale;
            configFile >> EnergyTolerance >> MassTolerance >> ThetaTolerance ;
            configFile >> rootDirectory >> logDirectory;
            configFile.close();

            TString outName = Form("%sLR_NeNe_%02d_%sGeV_%d.root" , rootDirectory.Data(), serial, beamEnergy.Data(), nEvents);
            TString logName = Form("%sLR_NeNe_%02d_%sGeV_%d.log"  ,  logDirectory.Data(), serial, beamEnergy.Data(), nEvents);

    Filesystem::create_directories(rootDirectory.Data());
    Filesystem::create_directories( logDirectory.Data());
    TFile* outFile = new TFile(outName, "RECREATE");

    // TTree* protonTree = new TTree("ProtonTree" , "Lambda Reconstruction Tree");
    // TTree* pionTree   = new TTree("PionTree"   , "Lambda Reconstruction Tree");
    // TTree* lambdaTree = new TTree("LambdaTree" , "Lambda Reconstruction Tree");

    Lorentz lambda, proton, pion;
        // protonTree -> Branch("proton" , &proton) ;
        // pionTree   -> Branch("pion"   , &pion)   ;
        // lambdaTree -> Branch("lambda" , &lambda) ;
    
    std::vector<Lorentz> protonList, pionList;
    
            DEFINE_THEM_ALL
            // Defines count variables, Histograms and Directory

    Bool_t energyCheck, massCheck, thetaCheck ; Double_t theta;
    Int_t nRealEvents = 0, iEvent, particle, nProtons, iProton, nPions, iPion;
    ioctl(STDOUT_FILENO, TIOCGWINSZ, &w); int progGap=nEvents/(w.ws_col-6);

    int nDigits=0,temp=nEvents; while(temp>0){nDigits++; temp/=10;}

    pythia.init();

    std::cout<<std::endl;

    for(iEvent = 1; iEvent <=nEvents; ++iEvent){
        if(!pythia.next()) continue;

        if (iEvent==1) {pythia.info.list(); std::cout<<std::flush;} 
        if( iEvent==2) {
            std::cout<<"\n\n\n";
            elapsed = Chrono::duration_cast<uSeconds>(SysClock::now() - start);
            printProgressStat(2, nEvents, nDigits, updatedETA(2, nEvents, elapsed)); 
            printProgressBar(0.01);
        }
        nRealEvents++;

        for (particle=0; particle<pythia.event.size(); ++particle) {
            if (pythia.event[particle].id() == 2212) { // Proton
                proton.SetPxPyPzE(\
                                    pythia.event[particle].px(), \
                                    pythia.event[particle].py(), \
                                    pythia.event[particle].pz(), \
                                    pythia.event[particle].e()   \
                                );
                protonList.push_back(proton);
                // protonTree->Fill();
            }
            else if (pythia.event[particle].id() == -211) { // Pion
                pion.SetPxPyPzE(\
                                    pythia.event[particle].px(), \
                                    pythia.event[particle].py(), \
                                    pythia.event[particle].pz(), \
                                    pythia.event[particle].e()   \
                                );
                pionList.push_back(pion);
                // pionTree->Fill();
            }
        }

        if(iEvent%printInterval==0||iEvent==nEvents){
            now = SysClock::now();
            elapsed = Chrono::duration_cast<uSeconds>(now - start);
            printProgressStat(iEvent, nEvents, nDigits, updatedETA(iEvent, nEvents, elapsed));
        }
        
        if(iEvent%progGap==0||iEvent==nEvents) {printProgressBar((double)((double)iEvent/nEvents));}

        nProtons = protonList.size();
        nPions = pionList.size();
        
            COUNT_RESETTER

        for(iProton = 0; iProton < nProtons; ++iProton){
            for(iPion = 0; iPion < nPions; ++iPion){
                proton = protonList [iProton];
                pion   = pionList   [iPion]  ;

                lambda = proton + pion;
                // lambdaTree->Fill();
                FILL_TO(un)

                proton.BoostToCM(lambda);
                pion.BoostToCM(lambda);

                theta = ((proton.Px()*pion.Px() + proton.Py()*pion.Py() + proton.Pz()*pion.Pz()) / (proton.P() * pion.P()));

                energyCheck = (lambda.E() > (lambdaMass - EnergyTolerance) && lambda.E() < (lambdaMass + EnergyTolerance));
                massCheck   = (lambda.M() > (lambdaMass - MassTolerance  ) && lambda.M() < (lambdaMass + MassTolerance  ));
                thetaCheck  = (theta      > (   -1 - cos(ThetaTolerance)  ) &&  theta     < (   -1 + cos(ThetaTolerance)  )); 
                // Check if the angle between proton and pion is small enough and opposite

                if (massCheck  )                            {  FILL_TO(Mass)        }
                if (energyCheck)                            {  FILL_TO(Energy)      }
                if (thetaCheck )                            {  FILL_TO(Theta)       }
                if (massCheck   && energyCheck)             {  FILL_TO(EnergyMass)  }
                if (massCheck   && thetaCheck )             {  FILL_TO(MassTheta)   }
                if (energyCheck && thetaCheck )             {  FILL_TO(EnergyTheta) }
                if (energyCheck && massCheck && thetaCheck) {  FILL_TO(All)         }
            }
        }
        COUNT_FILLER
        protonList.clear();
        pionList.clear();
    }
    std::cout<<std::setfill(' ')<<"\n\n";
    pythia.stat();

    // protonTree->Write();
    // pionTree->Write();
    // lambdaTree->Write();

        WRITE_THEM_ALL

    outFile->Close();

    now = SysClock::now();
    elapsed = Chrono::duration_cast<uSeconds>( now - start);
    const time_t localNow = SysClock::to_time_t(now);
    std::cout << std::put_time(std::localtime(&localNow), "%F %T \n");
    
    elapsed = now - start;
    std::cout << durationString(elapsed, true) << std::endl;

    std::ofstream logStream(logName.Data(), std::ios::trunc);

    logStream<< "Serial                        : " << std::setw(2) << std::setfill('0') << serial            << std::endl;
    logStream<< "Beam Energy                   : " << beamEnergy.Data()                                      << std::endl;
    logStream<< "Event Count                   : " << nEvents                                                << std::endl;
    logStream<< "Real Event Count              : " << nRealEvents                                            << std::endl;
    logStream<< "Last Run                      : " << std::put_time(std::localtime(&localStart), "%F %T")    << std::endl;
    logStream<< "Time Taken                    : " << durationString(elapsed)                                << std::endl;
    logStream<< "Time Taken / 100 Events       : " << durationString((100*elapsed)/nEvents)                  << std::endl;
    logStream<< "Energy Tolerance              : " << EnergyTolerance                                        << std::endl;
    logStream<< "Mass Tolerance                : " << MassTolerance                                          << std::endl;
    logStream<< "Theta Tolerance               : " << ThetaTolerance                                         << std::endl;
    logStream<< "Progress Bar Update Interval  : " << progGap                                                << std::endl;

    std::streambuf* oldStream = std::cout.rdbuf();
    std::cout.rdbuf(logStream.rdbuf());
    std::cout<<"\n\n\n";

    pythia.info.list();
    std::cout<<"\n\n\n";
    pythia.stat();

    std::cout.rdbuf(oldStream);
    logStream.close();

    return 0;
}
