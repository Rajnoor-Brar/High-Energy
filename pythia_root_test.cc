#include <iostream>
#include <string>
#include <vector>
#include "Pythia8/Pythia.h"
#include "TFile.h"
#include "TTree.h"

using namespace Pythia8;

int main() {
    int k,collisionEnergy;
    Pythia pythia;
    TFile *rootFile = TFile::Open("pp_500GeV-15TeV_30x2k.root", "recreate");
    TTree *eventTree = new TTree("p-p collisions", "Simulating Proton-Proton collisions at various energies");
    Event *event = &pythia.event;

    for (k =0; k<30;k++){
        eventTree->Reset();
        collisionEnergy = 500 + 500*k;
        eventTree->SetTitle(("p-p collisions at " + to_string(collisionEnergy) + " GeV").c_str());
        eventTree->SetName(("p-p_" + to_string(collisionEnergy) + "GeV").c_str());

        int totalEvents = 2000, eventNum=0,i,j;
        vector <double> id, status, mass, px, py, pz, pT, energy;

        eventTree->Branch("collisionEnergy", &collisionEnergy);
        eventTree->Branch("eventNum", &eventNum);
        eventTree->Branch("id", &id);
        eventTree->Branch("status", &status);
        eventTree->Branch("mass", &mass);
        eventTree->Branch("px", &px);
        eventTree->Branch("py", &py);
        eventTree->Branch("pz", &pz);
        eventTree->Branch("pT", &pT);
        eventTree->Branch("energy", &energy);

        pythia.readString("Beams:idA = 2212");
        pythia.readString("Beams:idB = 2212");
        pythia.readString("HardQCD:all = on");
        pythia.readString("PhaseSpace:pTHatMin = 20.");

        string eCM= "Beams:eCM = " + to_string(collisionEnergy) + ".";
        pythia.readString(eCM);

        pythia.init();

        for (i = 0; i<totalEvents;i++){
            if (!pythia.next()) continue;
            eventNum = i;
            for (j = 0; j<event->size(); j++){
                id.push_back(event->at(j).id());
                status.push_back(event->at(j).status());
                mass.push_back(event->at(j).m());
                px.push_back(event->at(j).px());
                py.push_back(event->at(j).py());
                pz.push_back(event->at(j).pz());
                pT.push_back(event->at(j).pT());
                energy.push_back(event->at(j).e());
            }
            eventTree->Fill();
            id.clear();
            status.clear();
            mass.clear();
            px.clear();
            py.clear();
            pz.clear();
            pT.clear();
            energy.clear();
        }
        rootFile->cd();
        eventTree->Write();
    }
    rootFile->Close();

    return 0;
}
