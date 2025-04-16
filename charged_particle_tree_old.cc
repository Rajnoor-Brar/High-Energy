// charged_particle_tree.cc is based on main01.cc from the 
// PYTHIA event generator, but has been modified by
// Peter Christiansen (peter.christiansen@hep.lu.se at Lund University)
//

#include "Pythia8/Pythia.h"

// ROOT includes
#include <TH1.h>
#include <TMath.h>
#include <TFile.h>
#include <TTree.h>
#include <TClonesArray.h>
#include <TParticle.h>
using namespace std;

int main() {

  // setup parametes
  const int   nEvents = 50000;
  const float ymax = 10.0;   

  // Initialize PYTHIA minbias Generator.
  Pythia8::Pythia pythia;
  pythia.readString("Beams:idA = 2212");
  pythia.readString("Beams:idB = 2212 ");
  pythia.readString("Beams:eCM = 13000."); // 7 TeV pp
  Bool_t kQCDCR = kFALSE;
  Bool_t kRopes = kFALSE;
  Bool_t kPartons= kFALSE;

  /*
    SoftQCD:all = on                   ! Allow total sigma = elastic/SD/DD/ND
    Optionally only study one or a few processes at a time.
    SoftQCD:elastic = on               ! Elastic
    SoftQCD:singleDiffractive = on     ! Single diffractive
    SoftQCD:doubleDiffractive = on     ! Double diffractive
    SoftQCD:centralDiffractive = on    ! Central diffractive
    SoftQCD:nonDiffractive = on        ! Nondiffractive (inelastic)
    SoftQCD:inelastic = on             ! All inelastic
   */
  pythia.readString("SoftQCD:inelastic = on"); 

  if(kQCDCR){

   pythia.readString("MultiPartonInteractions:pT0Ref = 2.15");
    pythia.readString("BeamRemnants:remnantMode = 1");
    pythia.readString("BeamRemnants:saturation = 5");
    pythia.readString("ColourReconnection:mode = 1");
    pythia.readString("ColourReconnection:allowDoubleJunRem = off");
    pythia.readString("ColourReconnection:m0 = 0.3");
    pythia.readString("ColourReconnection:allowJunctions = on");
    pythia.readString("ColourReconnection:junctionCorrection = 1.2");
    pythia.readString("ColourReconnection:timeDilationMode = 2");
    pythia.readString("ColourReconnection:timeDilationPar = 0.18");
    if(!kRopes)
      pythia.readString("Ropewalk:RopeHadronization = off");
  }
  if(kQCDCR && kRopes){
    pythia.readString("Ropewalk:doShoving = on");
    pythia.readString("Ropewalk:tInit = 1.5");
    pythia.readString("Ropewalk:deltat = 0.05");
    pythia.readString("Ropewalk:tShove = 0.1");
    pythia.readString("Ropewalk:gAmplitude = 0.");// # Set shoving strength to 0 explicitly

    pythia.readString("Ropewalk:doFlavour = on");
    pythia.readString("Ropewalk:r0 = 0.5");
    pythia.readString("Ropewalk:m0 = 0.2");
    pythia.readString("Ropewalk:beta = 0.1");
  }
  if(!kQCDCR && kRopes){
    cout<<"You are trying to turn on ropes without the neccesary junctions! Flip kQCDCR=kTRUE"<<endl;
    return -1;
  }
  pythia.readString("Random:setSeed = on");
  pythia.readString("Random:seed = 0");

  pythia.init();



  //
  // Create ROOT objects
  //

  // Write histograms to file
  TFile* outFile = new TFile("testtree.root", "RECREATE");

  TH1F* hdNdeta = 
    new TH1F("hdNdeta", "dN_{ch}/d#eta; #eta; 1/N_{events} dN_{ch}/d#eta",
	     60, -ymax, ymax);

  TH1F* hMult = 
    new TH1F("hMult", "Total charged particle multiplicity; Mult; Counts",
	     100, 0, 100);

  TTree* tree = new TTree("TT", "PYTHIA Track Tree");
  TClonesArray* trackArray = new TClonesArray("TParticle", 100);
  tree->Branch("tracks", "TClonesArray", &trackArray);
  

  Int_t HP_Inc[4] = {0};
  Int_t HP_Out[4] = {0};
  Int_t HP_Kick[4] = {0};
  Int_t HP_Inter[4] = {0};

  tree->Branch("HP_Inc1",&HP_Inc[0],"HP_Inc1/I");
  tree->Branch("HP_Inc2",&HP_Inc[1],"HP_Inc2/I");
  tree->Branch("HP_Inc3",&HP_Inc[2],"HP_Inc3/I");
  tree->Branch("HP_Inc4",&HP_Inc[3],"HP_Inc4/I");
  tree->Branch("HP_Out1",&HP_Out[0],"HP_Out1/I");
  tree->Branch("HP_Out2",&HP_Out[1],"HP_Out2/I");
  tree->Branch("HP_Out3",&HP_Out[2],"HP_Out3/I");
  tree->Branch("HP_Out4",&HP_Out[3],"HP_Out4/I");
  tree->Branch("HP_Inter1",&HP_Inter[0],"HP_Inter1/I");
  tree->Branch("HP_Inter2",&HP_Inter[1],"HP_Inter2/I");
  tree->Branch("HP_Inter3",&HP_Inter[2],"HP_Inter3/I");
  tree->Branch("HP_Inter4",&HP_Inter[3],"HP_Inter4/I");
  tree->Branch("HP_Kick1",&HP_Kick[0],"HP_Kick1/I");
  tree->Branch("HP_Kick2",&HP_Kick[1],"HP_Kick2/I");
  tree->Branch("HP_Kick3",&HP_Kick[2],"HP_Kick3/I");
  tree->Branch("HP_Kick4",&HP_Kick[3],"HP_Kick4/I");
  int   nRealEvents = 0;
  for (int iEvent = 0; iEvent < nEvents; ++iEvent) {
    for(Int_t a = 0; a<4;a++){
      HP_Inc[a]=-999;
      HP_Out[a]=-999;
      HP_Kick[a]=-999;
      HP_Inter[a]=-999;
    }

    Int_t nProcIn = 0;
    Int_t nProcInter = 0;
    Int_t nProcKick = 0;
    Int_t nProcOut =0;
    int nCharged  = 0;
    
    if (!pythia.next()) continue;
    
    nRealEvents++;
    
    if (iEvent < 1) {pythia.info.list(); pythia.event.list();} 
    
    for (int i = 0; i < pythia.event.size(); ++i) {
      //Checks PDG for incomming particles in hardest process
      if(TMath::Abs(pythia.event[i].status())==21){
	HP_Inc[nProcIn] = pythia.event[i].id();
	nProcIn++;
      }
      //Checks if there's an intermediary stage
      if(TMath::Abs(pythia.event[i].status())==22){
	HP_Inter[nProcInter] = pythia.event[i].id();
	nProcInter++;
      }
      //Checks PDG for outgoing particles in hardest process
      if(TMath::Abs(pythia.event[i].status())==23){
	HP_Out[nProcOut] = pythia.event[i].id();
	nProcOut++;
      }
      //Checks if a parton was kicked out in the diffraction.
      if(TMath::Abs(pythia.event[i].status())==24){
	HP_Kick[nProcKick] = pythia.event[i].id();
	nProcKick++;
      }

      if(!kPartons){
	//       Final
	if (!pythia.event[i].isFinal())
	  continue;
      
	//        Hadron
	if(!pythia.event[i].isHadron())
	  continue;
      }
      //        Charged
      //  if(pythia.event[i].isNeutral())
      // 	  continue;
	
      TParticle* track =
	new((*trackArray)[nCharged]) TParticle();
      track->SetPdgCode(pythia.event[i].id());
      track->SetMother(0, pythia.event[i].mother1());
      track->SetMother(1, pythia.event[pythia.event[i].mother1()].id());
      track->SetMomentum(pythia.event[i].px(), pythia.event[i].py(), 
			 pythia.event[i].pz(), pythia.event[i].e());

      track->SetStatusCode(pythia.event[i].status());
      Bool_t kFLAG = kFALSE;
      Int_t MLab [10] = {0};
      Int_t Code [10] = {0};
      Int_t iter = 0; 
      MLab[0] = i;
      while(!kFLAG){
	MLab[iter] = pythia.event[MLab[iter]].mother1();
	Code[iter] = pythia.event[MLab[iter]].status();
	if(TMath::Abs(Code[iter]) > 40){
	  iter++;
	}
	else{
	  kFLAG = kTRUE;
	  track->SetDaughter(0,Code[iter]);
	  if(iter>0)
	    track->SetDaughter(1,Code[iter-1]);
	}
      }
      // if(!pythia.event[i].isFinal())
      //  	track->SetDaughter(0,0);
      // else
      //  	track->SetDaughter(0,1);

      // if(!pythia.event[i].isHadron())
      //  	track->SetDaughter(1,0);
      // else
      //  	track->SetDaughter(1,1);



      nCharged++;

      const float eta = pythia.event[i].eta();
      hdNdeta->Fill(eta);
    }
    // Fill charged multiplicity histogram
    hMult->Fill(nCharged);
    // Update tree for this event
    tree->Fill();
    trackArray->Delete();
  } // End of event loop.
  
  // write PYTHIA summary to screen
  pythia.stat();
  
  // Here you could add the code to normalize hdNdeta
  hdNdeta->Scale(1.0/nEvents/hdNdeta->GetXaxis()->GetBinWidth(1));
  
  // Write and close output file
  outFile->Write();
  outFile->Close();
  
  // Check to see that we got most of the events we wanted
  cout << "Real events/simulated: " << nRealEvents 
       << "/ " << nEvents << endl;
  
  return 0;
}
