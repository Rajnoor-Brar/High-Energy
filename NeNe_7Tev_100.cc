

#include "Pythia8/Pythia.h"
#include "TFile.h"
#include "TTree.h"
#include "TH1D.h"
#include <vector>

using namespace Pythia8;

int main() {
    Pythia pythia;

    Event *event = &pythia.event;
    TFile *rootFile = TFile::Open("NeNe_7TeV_100.root", "recreate");
    TTree *eventTree = new TTree("Ne-Ne collisions", "Simulating Neon-Neon collisions");
    TH1D *hist = new TH1D("dN/dpT","Transverse Momentum Distribution",300,0,300);
    hist->GetYaxis()->SetTitle("Number of Particles");
    hist->GetXaxis()->SetTitle("Transverse Momenta");


    int totalEvents = 100, eventNum=0;
    vector <double> px, py, pz, pT, energy, mass;

    eventTree->Branch("eventNum", &eventNum);
    eventTree->Branch("px", &px);
    eventTree->Branch("py", &py);
    eventTree->Branch("pz", &pz);
    eventTree->Branch("pT", &pT);
    eventTree->Branch("energy", &energy);
    eventTree->Branch("mass", &mass);

    pythia.readString("Beams:idA = 1000100200");
    pythia.readString("Beams:idB = 1000100200");
    pythia.readString("Beams:eCM = 7000");
    pythia.readString("HardQCD:all = on");
    pythia.readString("PhaseSpace:pTHatMin = 20.");

    pythia.init();

    for (int i = 0; i<totalEvents;i++){
        px.clear();
        py.clear();
        pz.clear();
        pT.clear();
        energy.clear();
        if (!pythia.next()) continue;
        eventNum = i;
        for (int j = 0; j<event->size(); j++){
            px.push_back(event->at(j).px());
            py.push_back(event->at(j).py());
            pz.push_back(event->at(j).pz());
            pT.push_back(event->at(j).pT());
            energy.push_back(event->at(j).e());

            hist->Fill(event->at(j).pT());
            eventTree->Fill();
        }
    }
    hist->Write();
    rootFile->cd();
    eventTree->Write();
    rootFile->Close();

    return 0;
}
