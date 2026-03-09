#include "Pythia8/Pythia.h"
#include "Pythia8/HeavyIons.h"

#include <TH1.h>
#include <TH2.h>
#include <TMath.h>
#include <TFile.h>
#include <TTree.h>
#include <TGraph.h>
#include <TClonesArray.h>
#include <TParticle.h>
#include <TTimeStamp.h>
#include <iostream>
using namespace std;

int main() {
    //=== Pythia initialization ===
    Pythia8::Pythia pythia;

    // Define Neon-20 nucleus
    pythia.readString("1000100200:all = Ne20 Ne 10 20 0 0.0 0.0 0 0 0");

    //=== User-configurable parameters ===
    const int    nEvents    = 100000    ;
    const int    nbins      = 500     ;     // number of bins in histograms
    const int    mbins      = 200     ;     // bins for multiplicity
    const float  mMax       = 5000   ;
    const float  ymax       = 60.0    ;     // pseudorapidity range
    const string beamEnergy = "7000"  ;     // sqrt(s_NN) in GeV
    const string serial     = "12"    ;     // output file serial
    const string seedVal    = "270403";     // seed value if not random


    const bool   seedRandom = true    ;     // random seed

    // Physics toggles
    const bool hardQCD   = true ;
    const bool softQCD   = true ;
    const bool kQCDCR    = true ;            // colour reconnection
    const bool kRopes    = true ;            // rope hadronization
    const bool kShoving  = true ;            // rope shoving
    const bool kPartons  = true ;            // store all parton data

    // Beam settings
    pythia.readFile("config/_config_NeNe.cmnd");

    // Initialize Pythia
    pythia.init();

    //=== ROOT output setup ===
    TString outName = Form("NeNe_E%s_%sTeV_%04d_%s%s%s%s.root",
                            serial.c_str(), beamEnergy.c_str(), nEvents,
                            hardQCD  ? "HardQCD_"     : "",
                            softQCD  ? "SoftQCD_"     : "",
                            kShoving ? "RopeShoving_" : "",
                            kRopes   ? "RopeFlavour"  : "");

    TFile* outFile = new TFile(outName, "RECREATE");

    TH1F*    nMult   = new TH1F   ("nMult"  , "Net Total Multiplicity;N_{t};Counts"             , mbins,   0  , mMax*4);
    TH1F*    hMult   = new TH1F   ("hMult"  , "Net Charged Multiplicity;N_{t,ch};Counts"        , mbins,   0  , mMax*1.25);
    TH1F*    kMult   = new TH1F   ("kMult"  , "Net Uncharged Multiplicity;N_{t,ch};Counts"        , mbins,   0  , mMax*3);
    
    TH1F*    fMult   = new TH1F   ("fMult"  , "Final Total Particle Multiplicity;N_{f};Counts"  , mbins,   0  , mMax);
    TH1F*    cMult   = new TH1F   ("cMult"  , "Final Charged Multiplicity;N_{f,ch};Counts"      , mbins,   0  , mMax);
    TH1F*    uMult   = new TH1F   ("uMult"  , "Final Uncharged Multiplicity;N_{f,un};Counts"    , mbins,   0  , mMax);

    TH1F*    nEtaDis = new TH1F   ("nEtaDis", "Net All particle #eta distribution;#eta; Counts"        , nbins, -ymax, ymax );
    TH1F*    hEtaDis = new TH1F   ("hEtaDis", "Net Charged particle #eta distribution;#eta; Counts"    , nbins, -ymax, ymax );
    TH1F*    kEtaDis = new TH1F   ("kEtaDis", "Net Uncharged particle #eta distribution;#eta;Counts"   , nbins, -ymax, ymax );

    TH1F*    fEtaDis = new TH1F   ("fEtaDis", "Final All particle #eta distribution;#eta; Counts"      , nbins, -ymax, ymax );
    TH1F*    cEtaDis = new TH1F   ("cEtaDis", "Final Charged particle #eta distribution;#eta; Counts"  , nbins, -ymax, ymax );
    TH1F*    uEtaDis = new TH1F   ("uEtaDis", "Final Uncharged particle #eta distribution;#eta;Counts" , nbins, -ymax, ymax );

    TGraph* fEnergyEta = new TGraph(0);
    fEnergyEta->SetName("fEnergyEta");
    fEnergyEta->SetTitle("Final particle energy vs #eta;#eta;E_{T} (GeV)");
    
    TGraph* fEnergyMmnt = new TGraph(0);
    fEnergyMmnt->SetName("fEnergyMmnt");
    fEnergyMmnt->SetTitle("Final particle pseudo-rapidity vs Transverse momentum;#eta;p_{T}");
    
    TGraph* nEnergyEta = new TGraph(0);
    nEnergyEta->SetName("nEnergyEta");
    nEnergyEta->SetTitle("Net particle energy vs #eta;#eta;E_{T} (GeV)");
    
    TGraph* nEnergyMmnt = new TGraph(0);
    nEnergyMmnt->SetName("nEnergyMmnt");
    nEnergyMmnt->SetTitle("Net particle pseudo-rapidity vs Transverse momentum;#eta;p_{T}");
    
    TGraph* cEnergyEta = new TGraph(0);
    cEnergyEta->SetName("cEnergyEta");
    cEnergyEta->SetTitle("Final charged particle energy vs #eta;#eta;E_{T} (GeV)");
    
    TGraph* cEnergyMmnt = new TGraph(0);
    cEnergyMmnt->SetName("cEnergyMmnt");
    cEnergyMmnt->SetTitle("Final charged pseudo-rapidity vs Transverse momentum;#eta;p_{T}");
    


    TH2D*   nEnerEta  = new TH2D   ("nEnerEta", "Net particle energy vs #eta;#eta;E_{T} (GeV)" , nbins, -ymax, ymax , (nbins*3), 0, 2000 );
    TH2D*   nMnmtEta  = new TH2D   ("nMnmtEta", "Net particle transverse momentum vs #eta;#eta;p_{T} (GeV)" , nbins, -ymax, ymax , (nbins*3), 0, 2000 );

    TH2D*   fEnerEta  = new TH2D   ("fEnerEta", "Final particle energy vs #eta;#eta;E_{T} (GeV)" , nbins, -ymax, ymax , (nbins*3), 0, 2000 );
    TH2D*   fMnmtEta  = new TH2D   ("fMnmtEta", "Final particle transverse momentum vs #eta;#eta;p_{T} (GeV)" , nbins, -ymax, ymax , (nbins*3), 0, 2000 );
    TH2D*   cEnerEta  = new TH2D   ("cEnerEta", "Final charged particle energy vs #eta;#eta;E_{T} (GeV)" , nbins, -ymax, ymax , (nbins*3), 0, 2000 );
    TH2D*   cMnmtEta  = new TH2D   ("cMnmtEta", "Final charged particle transverse momentum vs #eta;#eta;p_{T} (GeV)" , nbins, -ymax, ymax , (nbins*3), 0, 2000 );
    
    // TH1I*    fQuarks = new TH1I   ("fQuarks"   , "Final Quark Distribution; PDG Code; Counts"    , 31,   -0.5 , 30.5  );
    // TH1I*    fBaryon = new TH1I   ("fBaryon"   , "Final Baryon Distribution; PDG Code; Counts"   , 120,   2200 , 3400 );
    // TH1I*    fMeson  = new TH1I   ("fMesons"   , "Final Meson Distribution; PDG Code; Counts"    , 42,   110 , 530    );
    
    // TGraph*  PDG     = new TGraph ();

    TTree*        tree       = new TTree        ("Totality"        , "All Particle Data"  );
    TTree*        fnTree     = new TTree        ("Finality"        , "Final Particle Data");
    TTree*        eTree      = new TTree        ("Events"          , "Event Data"  );

    Double_t p_pT, p_pX, p_pY, p_pZ, p_y, p_eta, p_energy;
    Float_t    p_id, p_status, p_color;

    Int_t nTotal=0, nCharged=0, nUncharged=0, nChargedFinal=0, nFinal=0, nFinalUncharged=0, iEvent=0;

    fnTree->Branch("id"                 , &p_id    , "id"          );
    fnTree->Branch("Event_Number"       , &iEvent  , "Event Number" );
    fnTree->Branch("Color"              , &p_color , "Color Charge");
    fnTree->Branch("Transverse_Momentum", &p_pT    , "Transverse Momentum (p_{T})");
    fnTree->Branch("Forward_Momentum"   , &p_pZ    , "Forward Momentum (p_{Z})"   );
    fnTree->Branch("Pseudorapidity"     , &p_eta   , "Pseudorapidity (#eta)" );
    fnTree->Branch("Energy"             , &p_energy, "Energy (E)" );
    fnTree->Branch("Status_Code"        , &p_status, "Status Code" );
    fnTree->Branch("X_Momentum"         , &p_pX    , "X Momentum (p_{X})" );
    fnTree->Branch("Y_Momentum"         , &p_pY    , "Y Momentum (p_{Y})" );
    fnTree->Branch("Rapidity"           , &p_y     , "Rapidity (y)" );

    tree->Branch("id"                 , &p_id    , "id"          );
    tree->Branch("Event_Number"       , &iEvent  , "Event Number" );
    tree->Branch("Color"              , &p_color , "Color Charge");
    tree->Branch("Transverse_Momentum", &p_pT    , "Transverse Momentum (p_{T})");
    tree->Branch("Forward_Momentum"   , &p_pZ    , "Forward Momentum (p_{Z})"   );
    tree->Branch("Pseudorapidity"     , &p_eta   , "Pseudorapidity (#eta)" );
    tree->Branch("Energy"             , &p_energy, "Energy (E)" );
    tree->Branch("Status_Code"        , &p_status, "Status Code" );
    tree->Branch("X_Momentum"         , &p_pX    , "X Momentum (p_{X})" );
    tree->Branch("Y_Momentum"         , &p_pY    , "Y Momentum (p_{Y})" );
    tree->Branch("Rapidity"           , &p_y     , "Rapidity (y)" );

    eTree->Branch("Total_Multiplicity"                  , &nTotal            , "nTotal"          );
    eTree->Branch("Total_Charged_Multiplicity"          , &nCharged          , "nCharged"          );
    eTree->Branch("Total_Uncharged_Multiplicity"        , &nUncharged        , "nUncharged"        );
    eTree->Branch("Final_Multiplicity"                  , &nFinal            , "nFinal"            );
    eTree->Branch("Final_Charged_Multiplicity"          , &nChargedFinal     , "nChargedFinal"     );
    eTree->Branch("Final_Uncharged_Multiplicity"        , &nFinalUncharged   , "nFinalUncharged"   );

    Int_t nRealEvents = 0;

    //=== Event loop ===
    for (iEvent = 0; iEvent < nEvents; ++iEvent) {

        nTotal = nCharged = nChargedFinal = nFinal = nUncharged = nFinalUncharged = 0;

        if (!pythia.next()) continue;

        ++nRealEvents;

        if (iEvent==0) {pythia.info.list();  pythia.event.list(); }
//
        for (int i=0; i<pythia.event.size(); ++i) {
            p_id        = static_cast<float>(pythia.event[i].id()    );
            p_color     = static_cast<float>(pythia.event[i].col()   );
            p_status    = static_cast<float>(pythia.event[i].status());
            p_pT        = pythia.event[i].pT();
            p_pZ        = pythia.event[i].pz();
            p_eta       = pythia.event[i].eta();
            p_energy    = pythia.event[i].e();
            p_pX        = pythia.event[i].px();
            p_pY        = pythia.event[i].py();
            p_y         = pythia.event[i].y();

            nTotal++;
            nEtaDis->Fill(p_eta);
            nEnergyEta->SetPoint(nEnergyEta->GetN(), p_eta, p_energy);
            nEnergyMmnt->SetPoint(nEnergyMmnt->GetN(), p_eta, p_pT);
            nMnmtEta->Fill(p_eta, p_pT);
            nEnerEta->Fill(p_eta, p_energy);
            
            if (pythia.event[i].isCharged()) {
                hEtaDis->Fill(p_eta);
                nCharged++;
            }
            else{
                kEtaDis->Fill(p_eta);
                nUncharged++;
            }
            
            if (pythia.event[i].isFinal()) {
                nFinal++;
                fEtaDis->Fill(p_eta);
                fEnergyEta->SetPoint(fEnergyEta->GetN(), p_eta, p_energy);
                fEnergyMmnt->SetPoint(fEnergyMmnt->GetN(), p_eta, p_pT);
                fMnmtEta->Fill(p_eta, p_pT);
                fEnerEta->Fill(p_eta, p_energy);

                if (pythia.event[i].isCharged()) {
                    cEtaDis->Fill(p_eta);
                    nChargedFinal++;
                    cEnergyEta->SetPoint(cEnergyEta->GetN(), p_eta, p_energy);
                    cEnergyMmnt->SetPoint(cEnergyMmnt->GetN(), p_eta, p_pT);
                    cMnmtEta->Fill(p_eta, p_pT);
                    cEnerEta->Fill(p_eta, p_energy);
                }
                else{
                    uEtaDis->Fill(p_eta);
                    nFinalUncharged++;
                }

                fnTree->Fill();            
            }
            tree->Fill();
        }

        fMult->Fill(static_cast<float>(nFinal));
        hMult->Fill(static_cast<float>(nCharged));
        uMult->Fill(static_cast<float>(nFinalUncharged));
        nMult->Fill(static_cast<float>(nTotal));
        cMult->Fill(static_cast<float>(nChargedFinal));
        kMult->Fill(static_cast<float>(nUncharged));

        eTree->Fill();
    }

    hEtaDis->Scale(1.0 / nRealEvents / hEtaDis->GetXaxis()->GetBinWidth(1) );
    nEtaDis->Scale(1.0 / nRealEvents / nEtaDis->GetXaxis()->GetBinWidth(1) ); 
    cEtaDis->Scale(1.0 / nRealEvents / cEtaDis->GetXaxis()->GetBinWidth(1) ); 
    uEtaDis->Scale(1.0 / nRealEvents / uEtaDis->GetXaxis()->GetBinWidth(1) ); 
    fEtaDis->Scale(1.0 / nRealEvents / fEtaDis->GetXaxis()->GetBinWidth(1) ); 

    hMult->Scale(100.0 / nRealEvents / hMult->GetXaxis()->GetBinWidth(1) );  
    cMult->Scale(100.0 / nRealEvents / cMult->GetXaxis()->GetBinWidth(1) );  
    fMult->Scale(100.0 / nRealEvents / fMult->GetXaxis()->GetBinWidth(1) );  
    nMult->Scale(100.0 / nRealEvents / nMult->GetXaxis()->GetBinWidth(1) );  

    pythia.stat();
    
    tree->Write();    fnTree->Write();    eTree->Write();

    nMult->Write();    hMult->Write();    kMult->Write();    fMult->Write();    cMult->Write();    uMult->Write();

    nEtaDis->Write();    hEtaDis->Write();    kEtaDis->Write();     cEtaDis->Write();    uEtaDis->Write();    fEtaDis->Write();

    // nEnergyEta->Write();    nEnergyMmnt->Write();
    // fEnergyEta->Write();    fEnergyMmnt->Write();
    // cEnergyEta->Write();    cEnergyMmnt->Write();

    // nMnmtEta->Write();     nEnerEta->Write();
    // cMnmtEta->Write();    cEnerEta->Write();
    // fMnmtEta->Write();    fEnerEta->Write();
    

    outFile->Close();

    cout << "Real events: " << nRealEvents << "/" << nEvents << endl;
    return 0;
}
