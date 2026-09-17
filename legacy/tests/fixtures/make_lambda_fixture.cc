// Generator for tests/fixtures/lambda_fixture.root
//
// Writes a deterministic ROOT file containing Protons and Pions TTrees that
// match the schema written by _Lambda_Data (identical branch names / types).
// Every event has:
//   - 3 "beam" protons   (high-energy, combinatorial background)
//   - 1 "signal" proton  (λ-decay kinematics, p_cm ≈ 0.1 GeV/c)
//   - 4 "soft" pions     (background)
//   - 1 "signal" pion    (back-to-back with signal proton)
//
// Signal pair invariant mass: M ≈ 1.11539 GeV (within ±100 MeV of kLambdaMass).
// All other combinations have M ≫ 1.215 GeV or M ≪ 1.015 GeV.
//
// Usage:  ./tests/fixtures/make_lambda_fixture.exe [output_path]
//         Default: tests/fixtures/lambda_fixture.root
//
// The file is written once and committed; run only when regeneration is needed.

#include <array>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

#include "TFile.h"
#include "TParameter.h"
#include "TTree.h"

// ── Kinematics constants ─────────────────────────────────────────────────────
namespace {
    constexpr int    kNEvents    = 50;
    constexpr double kSignalE_p  = 0.94334;   // proton E in Lambda rest frame
    constexpr double kSignalPx_p =  0.1;      // proton px
    constexpr double kSignalE_pi = 0.17205;   // pion E in Lambda rest frame
    constexpr double kSignalPx_pi = -0.1;     // pion px (back-to-back)

    // Beam proton kinematics (3 per event — combinatorial background)
    constexpr double kBeamE[3]  = {5.0,  10.0, 20.0};
    constexpr double kBeamPx[3] = {4.99,  9.99, 19.99};

    // Soft pion kinematics (4 per event — combinatorial background)
    constexpr double kSoftE[4]  = {0.5, 1.0, 2.0, 5.0};
    constexpr double kSoftPx[4] = {0.49, 0.99, 1.99, 4.99};
}

static void declareTree(TTree* tree, Int_t& eventIdx,
                        std::array<Double_t, 4>& branches)
{
    tree->Branch("event_index", &eventIdx,    "event_index/I");
    tree->Branch("Energy",      &branches[0], "Energy/D");
    tree->Branch("pX",          &branches[1], "pX/D");
    tree->Branch("pY",          &branches[2], "pY/D");
    tree->Branch("pZ",          &branches[3], "pZ/D");
}

int main(int argc, char* argv[]) {
    const std::string outPath =
        argc > 1 ? argv[1] : "tests/fixtures/lambda_fixture.root";

    TFile* f = TFile::Open(outPath.c_str(), "RECREATE");
    if (!f || f->IsZombie()) {
        std::cerr << "Cannot create " << outPath << '\n';
        return 1;
    }

    // ── Declare trees ─────────────────────────────────────────────────────────
    TTree* protonTree = new TTree("Protons", "Final state protons");
    TTree* pionTree   = new TTree("Pions",   "Final state pions");

    Int_t eventIdx = 0;
    std::array<Double_t, 4> protonBranch{}, pionBranch{};

    declareTree(protonTree, eventIdx, protonBranch);
    declareTree(pionTree,   eventIdx, pionBranch);

    // ── Fill ──────────────────────────────────────────────────────────────────
    auto fillParticle = [](TTree* tree, Int_t idx,
                           std::array<Double_t, 4>& b,
                           double E, double px, double py = 0.0, double pz = 0.0) {
        // b[0]=Energy, b[1]=pX, b[2]=pY, b[3]=pZ  (matches declareDataObjects layout)
        b[0] = E; b[1] = px; b[2] = py; b[3] = pz;
        (void)idx;  // eventIdx is the outer variable captured by reference
        tree->Fill();
    };

    for (int ev = 1; ev <= kNEvents; ++ev) {
        eventIdx = ev;

        // Signal proton (signal pair: M ≈ 1.11539)
        fillParticle(protonTree, ev, protonBranch, kSignalE_p, kSignalPx_p);

        // Beam protons (3 background protons with high px → large lambda mass)
        for (int b = 0; b < 3; ++b)
            fillParticle(protonTree, ev, protonBranch, kBeamE[b], kBeamPx[b]);

        // Signal pion (back-to-back with signal proton)
        fillParticle(pionTree, ev, pionBranch, kSignalE_pi, kSignalPx_pi);

        // Soft pions (4 background pions)
        for (int b = 0; b < 4; ++b)
            fillParticle(pionTree, ev, pionBranch, kSoftE[b], kSoftPx[b]);
    }

    // ── Index + metadata ──────────────────────────────────────────────────────
    protonTree->BuildIndex("event_index");
    pionTree  ->BuildIndex("event_index");

    // About/events/n_events_total is read by _Lambda_Reconstruction's
    // event-count resolver (and by the smoke test's Probe::resolveEventCount).
    TDirectory* aboutDir = f->mkdir("About");
    TDirectory* evDir    = aboutDir->mkdir("events");
    evDir->cd();
    TParameter<Long64_t> nTotal("n_events_total", static_cast<Long64_t>(kNEvents));
    nTotal.Write();

    f->Write("", TObject::kOverwrite);
    f->Close();

    std::cout << "Wrote " << kNEvents << " events → " << outPath << '\n';
    return 0;
}
