#include "Pythia8/Pythia.h"
#include "TFile.h"
#include "TTree.h"

using namespace Pythia8;

int main() {
    // Initialize Pythia
    Pythia pythia;

    TFile *rootFile = TFile::Open("pp_14TeV_500.root", "recreate");
    TTree *eventTree = new TTree("p-p collisions", "Simulating Proton-Proton collisions");
    Event *event = &pythia.event;

    int totalEvents = 2000, eventNum=0;
    double px, py, pz, energy, mass;

    eventTree->Branch("eventNum", &eventNum);
    eventTree->Branch("px", &px);
    eventTree->Branch("py", &py);
    eventTree->Branch("pz", &pz);
    eventTree->Branch("energy", &energy);
    eventTree->Branch("mass", &mass);

    pythia.readString("Beams:idA = 2212");
    pythia.readString("Beams:idB = 2212");
    pythia.readString("Beams:eCM = 14000.");
    pythia.readString("HardQCD:all = on");
    pythia.readString("PhaseSpace:pTHatMin = 20.");

    pythia.init();

    for (int i = 0; i<totalEvents;i++){
        if (!pythia.next()) continue;
        eventNum = i;
        for (int j = 0; j<event->size(); j++){
            px = event->at(j).px();
            py = event->at(j).py();
            pz = event->at(j).pz();
            energy = event->at(j).e();
            mass = event->at(j).m();

            eventTree->Fill();
        }
    }
    rootFile->cd();
    eventTree->Write();
    rootFile->Close();

    return 0;
}
