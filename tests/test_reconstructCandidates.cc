// Unit test: Lambda::reconstructCandidates
//
// Tests the pure-physics reconstruction function in isolation — no Pythia, no
// ROOT files, no threads.  The four test cases cover:
//
//  T1  All 3×3 proton-pion combinations appear in the unvalidated output.
//  T2  Only the one pair with invariant mass near kLambdaMass passes the
//      mass window and lands in validated.
//  T3  That one candidate is promoted to selected when reservedProtons = 0.
//  T4  The selected lambda's mass is within 1 MeV of kLambdaMass.
//  T5  When reservedProtons == nProtons (candidateTarget == 0) no candidate
//      is selected even though one is validated.

#include <cmath>
#include <iostream>

#include "test_assert.hh"
#include "Lambda/Reconstruction.hh"   // pulls in Lambda/Types.hh → Record.hh
                                       // → Monitor/Render.hh → Pythia8/Pythia.h
                                       // (only the DECLARATION of harvestParticles
                                       //  needs Pythia8; we never CALL it here)

int main() {
    std::cout << "── test_reconstructCandidates ──────────────────────────────\n";

    // ── Physics-accurate kinematics for Lambda → p + π⁻ at rest ─────────────
    //
    // With CM momentum p_cm ≈ 0.1 GeV/c:
    //   E_proton = sqrt(0.1² + 0.938²) ≈ 0.94334 GeV
    //   E_pion   = sqrt(0.1² + 0.140²) ≈ 0.17205 GeV
    //   Lambda 4-momentum: (px=0, py=0, pz=0, E=1.11539) → M ≈ 1.11539 GeV
    //
    // Lambda::Lorentz = ROOT::Math::PxPyPzEVector constructor: (px, py, pz, E)

    const Lambda::Lorentz goodProton(  0.1,  0.0, 0.0, 0.94334);  // signal proton
    const Lambda::Lorentz goodPion(   -0.1,  0.0, 0.0, 0.17205);  // signal pion (back-to-back)

    // "Beam" protons — combined with any pion give lambda mass ≫ kLambdaMass+0.1
    const Lambda::Lorentz beamProton1( 4.99, 0.0, 0.0, 5.0);
    const Lambda::Lorentz beamProton2( 9.99, 0.0, 0.0, 10.0);

    // Energetic pions — combined with any proton give lambda mass ≫ kLambdaMass+0.1
    const Lambda::Lorentz fastPion1(   1.99, 0.0, 0.0, 2.0);
    const Lambda::Lorentz fastPion2(   4.99, 0.0, 0.0, 5.0);

    const std::vector<Lambda::Lorentz> protons = {goodProton, beamProton1, beamProton2};
    const std::vector<Lambda::Lorentz> pions   = {goodPion,   fastPion1,   fastPion2};

    // Parameters: wide mass window (±100 MeV), cosThetaTolerance = cos(0.1 rad)
    // so the theta window is (-1.995, -0.005) — all back-to-back pairs pass.
    Lambda::Parameters params;
    params.massTolerance     = 0.1;    // ±100 MeV window around kLambdaMass
    params.cosThetaTolerance = 0.995;  // cos(0.1 rad) — wide; theta is always −1
    params.reservedProtons   = 0;      // candidateTarget = nProtons − 0 = 3

    const Lambda::Candidates result = Lambda::reconstructCandidates(protons, pions, params);

    // ── T1: all 3×3 combinations enter unvalidated ───────────────────────────
    TEST_EQ(result.unvalidated.size(), std::size_t{9});
    TEST_PASS("T1  unvalidated.size() == 9");

    // ── T2: only goodProton+goodPion survives the mass cut ───────────────────
    // Verify the OTHER 8 combinations are well outside the mass window:
    //   beamProton1 + goodPion : M ≈ 1.685  (|M-1.115| ≈ 0.57 > 0.1)
    //   goodProton  + fastPion1 : M ≈ 2.07  (|M-1.115| ≈ 0.96 > 0.1)
    //   rest: even larger masses
    TEST_EQ(result.validated.size(), std::size_t{1});
    TEST_PASS("T2  validated.size() == 1  (only signal pair passes mass cut)");

    // ── T3: candidateTarget = 3 → the one validated candidate is selected ────
    TEST_EQ(result.selected.size(), std::size_t{1});
    TEST_PASS("T3  selected.size() == 1");

    // ── T4: selected mass is within 1 MeV of kLambdaMass ────────────────────
    TEST_NEAR(result.selected[0].M(), Lambda::kLambdaMass, 1e-3);
    TEST_PASS("T4  selected[0].M() ≈ kLambdaMass (within 1 MeV)");

    // ── T5: reservedProtons == nProtons → candidateTarget = 0 → no selection ─
    Lambda::Parameters params5 = params;
    params5.reservedProtons = protons.size();  // 3 reserved, 3 protons → target = 0
    const Lambda::Candidates result5 =
        Lambda::reconstructCandidates(protons, pions, params5);
    TEST_EQ(result5.unvalidated.size(), std::size_t{9});
    TEST_EQ(result5.validated.size(),   std::size_t{1});
    TEST_EQ(result5.selected.size(),    std::size_t{0});
    TEST_PASS("T5  reservedProtons==nProtons → selected.size() == 0");

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
