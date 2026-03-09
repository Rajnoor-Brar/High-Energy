#include "Pythia8/Pythia.h"
#include "Pythia8/HeavyIons.h"
#include "Math/Vector4D.h"

#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <chrono>
#include "TTimeStamp.h"
#include "TFile.h"
#include "TTree.h"
#include "TH1D.h"

using Lorentz = ROOT::Math::PxPyPzEVector;

int main() {

    const std::chrono::time_point<std::chrono::system_clock> start = std::chrono::system_clock::now();
    const time_t localStart = std::chrono::system_clock::to_time_t(start);
    std::cout << std::put_time(std::localtime(&localStart), "%F %T \n");
    
    //=== Pythia initialization ===
    Pythia8::Pythia pythia;

    pythia.readFile("configs/Lambda_Reconstruction.cmnd");

            FILE* configFile = fopen("configs/Lambda_Reconstruction.log", "r");

            Int_t serial=0, nEvents=100;
            TString directory = "output/Lambda_Reconstruction/";
            
            TString beamEnergy = pythia.settings.parm("Beams:eCM") > 0 ? Form("%.0f", pythia.settings.parm("Beams:eCM")) : "UnknownEnergy";

            if (configFile) {
                fscanf(configFile, "%d", &serial);
                fscanf(configFile, "%d", &nEvents);
                fclose(configFile);
            } else {
                std::cerr << "Could not open config file. Using default values." << std::endl;
            }

            Lorentz lambda, proton, pion;
            Int_t pairCount =0;
            
            std::vector<Lorentz> protonList, pionList;
            TString outName = Form("%sLR_NeNe_%02d_%sGeV_%d.root", directory.Data(), serial, beamEnergy.Data(), nEvents);

    TFile* outFile = new TFile(outName, "RECREATE");

    TTree* protonTree = new TTree("ProtonTree", "Lambda Reconstruction Tree");
    TTree* pionTree = new TTree("PionTree", "Lambda Reconstruction Tree");
    TTree* pairTree = new TTree("PairTree", "Lambda Reconstruction Tree");
    
            protonTree->Branch("proton", &proton);
            pionTree->Branch("pion", &pion);
            pairTree->Branch("lambda", &pairCount); // Store the count of valid pairs for each event

        Double_t pr_Px, pr_Py, pr_Pz, pr_E;
        Double_t pi_Px, pi_Py, pi_Pz, pi_E;

    TH1D* pairHist = new TH1D("pairHist", "Valid Proton-Pion Pairs per Event;Number of Pairs;Counts", 41, -0.5, 40.5);

    Int_t nRealEvents = 0, iEvent, particle;

    std::vector<std::vector<Int_t>> validPrPiIndices; // Store valid proton-pion index pairs for Lambda reconstruction

    Int_t nProtons, iProton;
    Int_t nPions, iPion;
    //Below in units Gev/c^2
    Double_t lambdaMass = 1.115, protonMass = 0.938, pionMass = 0.140, massDiff = lambdaMass - (protonMass + pionMass);
    Double_t theta;
    Double_t energyVariance=0.1, massVariance=0.05;
    Double_t thetaVariance=0.1; //radians

    Bool_t energyCheck, massCheck, thetaCheck ;
    // Initialize Pythia
    pythia.init();

    for(iEvent = 0; iEvent <nEvents; ++iEvent){
        if(!pythia.next()) continue;

        if (iEvent==0) {pythia.info.list();  pythia.event.list(); }
        nRealEvents++;

        for (particle=0; particle<pythia.event.size(); ++particle) {
            if (pythia.event[particle].id() == 2212) { // Proton
                proton.SetPxPyPzE(pythia.event[particle].px(), pythia.event[particle].py(), pythia.event[particle].pz(), pythia.event[particle].e());
                protonList.push_back(proton);
                protonTree->Fill();
            }
            else if (pythia.event[particle].id() == -211) { // Pion
                pion.SetPxPyPzE(pythia.event[particle].px(), pythia.event[particle].py(), pythia.event[particle].pz(), pythia.event[particle].e());
                pionList.push_back(pion);
                pionTree->Fill();
            }
        }
         if(iEvent%50==0){std::cout<<"\n\n\t\tEvents processed : "<<iEvent<<" out of "<< nEvents<<"\n\n";}

        nProtons = protonList.size();
        nPions = pionList.size();
        pairCount = 0; // Reset pair count for each event
        

        for(iProton = 0; iProton < nProtons; ++iProton){
            for(iPion = 0; iPion < nPions; ++iPion){
                proton = protonList[iProton];
                pion = pionList[iPion];

                lambda = proton + pion;

                proton.BoostToCM(lambda);
                pion.BoostToCM(lambda);

                energyCheck = (lambda.E() > lambdaMass - energyVariance && lambda.E() < lambdaMass + energyVariance);
                massCheck = (lambda.M() > lambdaMass - massVariance && lambda.M() < lambdaMass + massVariance);

                theta = ((proton.Px()*pion.Px() + proton.Py()*pion.Py() + proton.Pz()*pion.Pz()) / (proton.P() * pion.P()));
                thetaCheck = ((theta > 1-cos(thetaVariance)) && (theta < 1+cos(thetaVariance))); // Check if the angle between proton and pion is small enough

                if (energyCheck && massCheck && thetaCheck) {
                    pairCount++;
                }
            }
        }
        pairHist->Fill(pairCount);
        pairTree->Fill();
        protonList.clear();
        pionList.clear();
    }

    pythia.stat();
    // pairHist->Scale(1/nEvents);

    pairHist->Write();
    protonTree->Write();
    pionTree->Write();
    pairTree->Write();
    outFile->Close();

    const std::chrono::time_point<std::chrono::system_clock> now = std::chrono::system_clock::now();
    const time_t localNow = std::chrono::system_clock::to_time_t(now);
    std::cout << std::put_time(std::localtime(&localNow), "%F %T \n");
    
    auto elapsed = now - start;
    std::cout << std::chrono::duration_cast<std::chrono::seconds>(elapsed).count() << " s\n";
    std::cout << std::chrono::duration_cast<std::chrono::minutes>(elapsed).count() << " min\n";

    return 0;
}
