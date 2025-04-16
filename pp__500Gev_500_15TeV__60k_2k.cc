#include <iostream>
#include <string>
#include <vector>
#include "Pythia8/Pythia.h"
#include "TFile.h"
#include "TTree.h"

using namespace Pythia8;

int main() {
    // Initialize Pythia
    Pythia pythia;
    int k;

    TFile *rootFile = TFile::Open("pp_500GeV-15TeV_2000.root", "recreate");
    TTree *eventTree = new TTree("p-p collisions", "Simulating Proton-Proton collisions at various energies");
    Event *event = &pythia.event;

    int totalEvents = 2000, eventNum=0, collisionEnergy,i,j;
    vector <double> px, py, pz, energy, mass;

    eventTree->Branch("collisionEnergy", &collisionEnergy);
    eventTree->Branch("eventNum", &eventNum);
    eventTree->Branch("px", &px);
    eventTree->Branch("py", &py);
    eventTree->Branch("pz", &pz);
    eventTree->Branch("energy", &energy);
    eventTree->Branch("mass", &mass);

    pythia.readString("Beams:idA = 2212");
    pythia.readString("Beams:idB = 2212");
    pythia.readString("HardQCD:all = on");
    pythia.readString("PhaseSpace:pTHatMin = 20.");

    pythia.init();
    for (k =0; k<30;k++){
        collisionEnergy = 500 + 500*k;
        string eCM= "Beams:eCM = " + to_string(collisionEnergy) + ".";
        pythia.readString(eCM);

        for (i = 0; i<totalEvents;i++){
            
            if (!pythia.next()) continue;
            eventNum = i;
            for (j = 0; j<event->size(); j++){
                px.push_back(event->at(j).px());
                py.push_back(event->at(j).py());
                pz.push_back(event->at(j).pz());
                energy.push_back(event->at(j).e());
                mass.push_back(event->at(j).m());
            }
            eventTree->Fill();
            px.clear();
            py.clear();
            pz.clear();
            energy.clear();
            mass.clear();
        }
    }
    rootFile->cd();
    eventTree->Write();
    rootFile->Close();

    return 0;
}
