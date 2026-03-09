#include "Pythia8/Pythia.h"
#include "Pythia8/HeavyIons.h"

#include <TH1.h>
#include <TMath.h>
#include <TFile.h>
#include <TTree.h>
#include <TClonesArray.h>
#include <TParticle.h>
#include <TTimeStamp.h>
using namespace std;

int main() {

    const int nEvents = 10;
    const float ymax = 10.0;  
    string beamEnergy = "7000";
    string serial = "01";
    bool hardQCD = true ;
    bool softQCD = true;

    Pythia8::Pythia pythia;

    // Define Neon-20
    pythia.readString("1000100200 :all     = Ne20 Ne 10 20 0 0.0 0.0 0 0 0");

    // Beam settings
    pythia.readString("Beams      :idA     = 1000100200  ");                   // default = 2212 (proton)
    pythia.readString("Beams      :idB     = 1000100200  ");                   // default = 2212 (proton)
    pythia.readString("Beams      :eCM     = "+beamEnergy );                   // default = 14000.0
    pythia.readString("Random     :setSeed = on          ");                   // default = off (random seed)
    pythia.readString("Random     :seed    = 270403      ");                  

    // Heavy-ion specific settings
    pythia.readString("HeavyIon   :mode    = 1   ");                         // default = 0 (no heavy-ion model)
    pythia.readString("HeavyIon   :bMin    = 0.0 ");                         // default = 0.0 (minimum impact parameter in fm)
    pythia.readString("HeavyIon   :bMax    = 15.0");                         // default = 0.0 (maximum impact parameter in fm, 0 means auto)

    // Multiparton interactions
    pythia.readString("MultiPartonInteractions  :pT0Ref           = 2.15");   // default = 2.28 (for pp at 7 TeV)
    pythia.readString("HadronLevel              :BoseEinstein     = on");
    pythia.readString("HadronLevel              :all              = on");

    // Beam remnants
    pythia.readString("BeamRemnants             :remnantMode      = 1");     // default = 0
    pythia.readString("BeamRemnants             :saturation       = 5");     // Not a standard parameter, no default

    // Colour reconnection settings
    pythia.readString("ColourReconnection       :mode              = 1   ");  // default = 0
    pythia.readString("ColourReconnection       :allowDoubleJunRem = off ");  // default = on
    pythia.readString("ColourReconnection       :m0                = 0.3 ");  // default = 0.3
    pythia.readString("ColourReconnection       :timeDilationMode  = 2   ");  // default = 0
    pythia.readString("ColourReconnection       :timeDilationPar   = 0.18");  // default = 0.0

    // Parton vertex settings
    pythia.readString("PartonVertex :setVertex                   = on ");    // default = off
    pythia.readString("PartonVertex :protonRadius                = 0.7");    // default = 0.7
    pythia.readString("PartonVertex :emissionWidth               = 0.1");    // default = 0.1

    // Ropewalk (rope hadronization) settings
    pythia.readString("Ropewalk :RopeHadronization               = on  ");    // default = off
    pythia.readString("Ropewalk :doFlavour                       = on  ");    // default = off
    pythia.readString("Ropewalk :doShoving                       = on  ");    // default = off
    pythia.readString("Ropewalk :tInit                           = 1.5 ");    // default = 1.5
    pythia.readString("Ropewalk :deltat                          = 0.05");    // default = 0.1
    pythia.readString("Ropewalk :tShove                          = 0.1 ");    // default = 0.1
    pythia.readString("Ropewalk :gAmplitude                      = 0   ");    // default = 0.0
    pythia.readString("Ropewalk :r0                              = 0.5 ");    // default = 0.5
    pythia.readString("Ropewalk :m0                              = 0.2 ");    // default = 0.2
    pythia.readString("Ropewalk :beta                            = 0.1 ");    // default = 0.1

    // Conditional settings based on hard and soft QCD flags
    pythia.readString(hardQCD ? "HardQCD:all             = on"    : "HardQCD:all             = off");  // default = off
    pythia.readString(softQCD ? "SoftQCD:nonDiffractive  = on"    : "SoftQCD:nonDiffractive  = off");  // default = off
    pythia.readString(hardQCD ? "PhaseSpace:pTHatMin     = 15.0"  : "PhaseSpace:pTHatMin     = 0  ");  // default = 0.0

    TFile* rootFile = new TFile("NeNe_"+ beamEnergy+"TeV_"+
                                 "Hard"+(hardQCD ? "On" : "Off")+"_"+
                                 "Soft"+(softQCD ? "On" : "Off")+"_"+
                                 to_string(nEvents)+serial+".root", "RECREATE");

    TH1F* hdNdeta = new TH1F("hdNdeta", "dN_{ch}/d#eta; #eta; 1/N dN_{ch}/d#eta", 60, -ymax, ymax);

    TH1F* hMult =   new TH1F("hMult", "Total charged particle multiplicity; Mult; Counts", 100, 0, 100);

    TTree* tree = new TTree("Neon-Neon Collisions", "PYTHIA Track Tree");
    TClonesArray* trackArray = new TClonesArray("TParticle", 100);
    tree->Branch("tracks", "TClonesArray", &trackArray);




    pythia.init();


}
        // for (int a=0; a<4; ++a)
        //     HP_Inc[a]=HP_Inter[a]=HP_Out[a]=HP_Kick[a] = -999;

        // Int_t nProcIn=0, nProcInter=0, nProcOut=0, nProcKick=0;


//Event loop

            // int st = TMath::Abs( pythia .event[i] .status() );
            // int id =             pythia .event[i] .id();

            // // hardest process tagging
            // if (st==21 && nProcIn<4)    HP_Inc[nProcIn++]     = id;
            // if (st==22 && nProcInter<4) HP_Inter[nProcInter++]= id;
            // if (st==23 && nProcOut<4)   HP_Out[nProcOut++]    = id;
            // if (st==24 && nProcKick<4)  HP_Kick[nProcKick++]  = id;

            // final-state hadrons filter
            // if (!kPartons) {
            //     Bool_t kRes = (id==333 || id==313);
            //     if (!kRes && !pythia.event[i].isFinal()  ) continue;
            //     if          (!pythia.event[i].isHadron() ) continue;
            // }

            // // make TParticle
            // TParticle* track = new((*trackArray)[nCharged]) TParticle();
            // track->SetPdgCode    (id);
            // track->SetMother     (0, pythia.event[              i            ].mother1() );
            // // track->SetMother     (1, pythia.event[ i ].mother2()      );

            // track->SetMomentum   (pythia.event[i].px(),
            //                     pythia.event[i].py(),
            //                     pythia.event[i].pz(),
            //                     pythia.event[i].e () );

            // track->SetStatusCode (pythia.event[i].status());

            // // climb mother chain to find hard ancestor
            // Bool_t found=false;
            // Int_t idx = i, depth=0;

            // while (!found && depth<10) {
            //         idx = pythia.event[idx].mother1();
            //     int mst = pythia.event[idx].status ();

            //     if (TMath::Abs(mst)<=40) {
            //         found = true;
            //         track->SetDaughter(0, idx);
            //     } else depth++;
                
            // }
