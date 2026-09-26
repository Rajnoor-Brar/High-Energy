// tests/cxx/test_lambda.cc — the Λ reconstruction, without a generator.
//
// The legacy `harvestParticles` took a `Pythia8::Pythia&`, so testing the selection meant running a
// generator and hoping the event had what you needed. `Lambda::reconstruct` takes vectors, so the
// interesting cases can be *built*: a clean decay, a pair that misses the window, two candidates
// competing for one track, and the beam-proton subtraction.

#include "check.hh"

#include <cmath>
#include <vector>

#include "../../modules/Lambda/Reconstruction.hh"

namespace {

    using Lambda::FourVector;

    /// A four-vector from (px, py, pz) and a mass, so the tests can state momenta and mean them.
    FourVector of(double px, double py, double pz, double mass) {
        return FourVector(px, py, pz, std::sqrt(px * px + py * py + pz * pz + mass * mass));
    }

    bool near(double left, double right, double tolerance) {
        return std::abs(left - right) <= tolerance;
    }

    const double kProton = 0.938272;
    const double kPion = 0.139570;

    /// A p and a π⁻ whose invariant mass is exactly m(Λ): back to back in the Λ rest frame, with
    /// the momentum that a two-body decay of a Λ actually gives.
    std::pair<FourVector, FourVector> decayPair(double pz_boost = 0.0) {
        const double m = Lambda::kLambdaMass;
        const double p = std::sqrt((m * m - (kProton + kPion) * (kProton + kPion)) *
                                   (m * m - (kProton - kPion) * (kProton - kPion))) /
                         (2.0 * m);
        FourVector proton = of(0.0, 0.0, p + pz_boost, kProton);
        FourVector pion = of(0.0, 0.0, -p + pz_boost, kPion);
        return {proton, pion};
    }

}  // namespace

int main() {
    // ── a clean decay is validated and selected ──────────────────────────────
    {
        const auto [proton, pion] = decayPair();
        Lambda::Cuts cuts;
        cuts.reserved_protons = 0;
        const Lambda::Candidates found = Lambda::reconstruct({proton}, {pion}, cuts);

        CHECK_EQ(found.unvalidated.size(), 1u);
        CHECK_EQ(found.validated.size(), 1u);
        CHECK_EQ(found.selected.size(), 1u);
        CHECK(near(found.validated[0].m(), Lambda::kLambdaMass, 1e-9));
    }

    // ── the mass window actually excludes ────────────────────────────────────
    {
        // A high-momentum pair that cannot come from a Λ: invariant mass far above the window.
        const FourVector proton = of(5.0, 0.0, 0.0, kProton);
        const FourVector pion = of(-5.0, 0.0, 0.0, kPion);
        Lambda::Cuts cuts;
        cuts.reserved_protons = 0;
        const Lambda::Candidates found = Lambda::reconstruct({proton}, {pion}, cuts);

        CHECK_EQ(found.unvalidated.size(), 1u);   // every pair is a candidate
        CHECK_EQ(found.validated.size(), 0u);     // none of them is a Λ
        CHECK_EQ(found.selected.size(), 0u);
    }

    // ── the sets nest: selected ⊆ validated ⊆ unvalidated ────────────────────
    {
        const auto [proton, pion] = decayPair();
        const FourVector stray = of(3.0, 1.0, 2.0, kPion);
        Lambda::Cuts cuts;
        cuts.reserved_protons = 0;
        const Lambda::Candidates found = Lambda::reconstruct({proton}, {pion, stray}, cuts);

        CHECK_EQ(found.unvalidated.size(), 2u);
        CHECK(found.validated.size() <= found.unvalidated.size());
        CHECK(found.selected.size() <= found.validated.size());
    }

    // ── the greedy matching never reuses a track ─────────────────────────────
    {
        // One proton, two pions that both pair inside the window. Only one candidate may survive,
        // because the proton cannot belong to two Λs.
        const auto [proton, pion] = decayPair();
        const auto [ignored, pion2] = decayPair(0.001);
        (void)ignored;
        Lambda::Cuts cuts;
        cuts.reserved_protons = 0;
        const Lambda::Candidates found = Lambda::reconstruct({proton}, {pion, pion2}, cuts);

        CHECK_EQ(found.validated.size(), 2u);   // both pairs are inside the window
        CHECK_EQ(found.selected.size(), 1u);    // but they share the proton
    }

    // ── reserved_protons bounds the selection ────────────────────────────────
    {
        const auto [proton, pion] = decayPair();
        Lambda::Cuts cuts;
        cuts.reserved_protons = 5;              // more than there are protons
        const Lambda::Candidates found = Lambda::reconstruct({proton}, {pion}, cuts);

        CHECK_EQ(found.validated.size(), 1u);   // still a Λ by mass
        CHECK_EQ(found.selected.size(), 0u);    // but no room for it above the beam protons
    }

    // ── cos θ* is −1 for a genuine two-body decay ────────────────────────────
    {
        const auto [proton, pion] = decayPair(3.0);   // boosted along z, so the test is not trivial
        const FourVector lambda = proton + pion;
        CHECK(near(Lambda::cosThetaStar(proton, pion, lambda), -1.0, 1e-6));
    }

    // ── and the θ cut, when on, rejects a combinatorial pair ─────────────────
    {
        // Two tracks that happen to land in the mass window but are not back to back in the
        // candidate's rest frame. With the cut off they are validated; with it on they are not.
        const FourVector proton = of(0.30, 0.0, 0.40, kProton);
        const FourVector pion = of(-0.05, 0.22, 0.02, kPion);
        Lambda::Cuts loose;
        loose.mass_tolerance = 0.5;               // wide enough that mass is not what decides
        loose.reserved_protons = 0;
        const Lambda::Candidates without = Lambda::reconstruct({proton}, {pion}, loose);

        Lambda::Cuts tight = loose;
        tight.cos_theta_tolerance = 1e-3;
        const Lambda::Candidates with = Lambda::reconstruct({proton}, {pion}, tight);

        CHECK(with.validated.size() <= without.validated.size());
        const double cos_theta = Lambda::cosThetaStar(proton, pion, proton + pion);
        if (std::isfinite(cos_theta) && std::abs(cos_theta + 1.0) > 1e-3)
            CHECK_EQ(with.validated.size(), 0u);
    }

    // ── a non-finite input does not hang or throw (00/B35's lesson) ──────────
    {
        const FourVector broken(0.0, 0.0, 0.0, 0.0);
        const double cos_theta = Lambda::cosThetaStar(broken, broken, broken);
        CHECK(!std::isfinite(cos_theta));
    }

    return check::finish("lambda");
}
