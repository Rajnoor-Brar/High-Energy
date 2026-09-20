#pragma once

// ── Phys/Kinematics.hh ───────────────────────────────────────────────────────
// The derived quantities a four-vector does not carry: pairwise separations, invariant masses, and
// the DIS invariants this project is actually about (ported from
// `legacy/utils/Physics/Kinematics.hh`, on `HepMC3::FourVector` instead of ROOT's).
//
// Single-particle observables — pT, η, y, φ — belong to the vector itself and to the property table
// in `Phys/Types.hh`; nothing here repeats them.
//
// **Δφ no longer loops.** The legacy wrap was `while (d > π) d -= 2π`, which does not terminate for
// d = ±∞ and is the defect this step was told to guard against. HepMC3's own `FourVector::delta_phi`
// has the same loop and guards only NaN, so this is not a legacy-only problem and is the reason
// `deltaPhi` here is used in preference to the method on the vector. `std::remainder` does the wrap
// in one branch-free step, over the same range the loop produced ([−π, π], both ends reachable), and
// gives NaN for a non-finite input rather than hanging the run.
//
// An infinite φ only arises from a caller's mistake — φ is an `atan2` and always finite — so the
// answer is NaN rather than a number: a poisoned fill is visible, a hung run is not.

#include <cmath>
#include <limits>
#include <vector>

#include "Phys/Types.hh"

namespace Phys {

    /// The Minkowski product, (+,−,−,−). Every invariant below is built from it.
    inline double dot(const FourVector& a, const FourVector& b) {
        return a.e() * b.e() - a.px() * b.px() - a.py() * b.py() - a.pz() * b.pz();
    }

    // ── separations ──────────────────────────────────────────────────────────

    /// Signed azimuthal separation, wrapped into [−π, π]. NaN for a non-finite input.
    inline double deltaPhi(double phi1, double phi2) {
        const double difference = phi1 - phi2;
        if (!std::isfinite(difference)) return std::numeric_limits<double>::quiet_NaN();
        return std::remainder(difference, 2.0 * M_PI);
    }

    inline double deltaPhi(const FourVector& a, const FourVector& b) {
        return deltaPhi(a.phi(), b.phi());
    }

    inline double deltaEta(const FourVector& a, const FourVector& b) {
        return a.eta() - b.eta();
    }

    inline double deltaRapidity(const FourVector& a, const FourVector& b) {
        return a.rap() - b.rap();
    }

    /// ΔR in (η, φ). A particle exactly along the beam has infinite η, so this is infinite too —
    /// which is the truth, and `std::isfinite` on the result is how a caller says it does not want
    /// that particle. The alternative, silently clamping η, puts a spike in the outermost bin.
    inline double deltaR(const FourVector& a, const FourVector& b) {
        const double eta = deltaEta(a, b);
        const double phi = deltaPhi(a, b);
        return std::sqrt(eta * eta + phi * phi);
    }

    /// ΔR in (y, φ), which is the one a jet algorithm uses for massive inputs.
    inline double deltaRRapidity(const FourVector& a, const FourVector& b) {
        const double rapidity = deltaRapidity(a, b);
        const double phi = deltaPhi(a, b);
        return std::sqrt(rapidity * rapidity + phi * phi);
    }

    // ── masses ───────────────────────────────────────────────────────────────

    inline double invariantMass(const FourVector& a, const FourVector& b) {
        return (a + b).m();
    }

    /// From components, **clamped at zero**: a vector that rounding has made spacelike (m² < 0)
    /// gives 0 rather than NaN. `FourVector::m()` returns −√(−m²) for the same input, which is a
    /// different and also defensible answer — this one is the legacy behaviour, kept because the
    /// thing it protects is a histogram fill.
    inline double invariantMass(double e, double px, double py, double pz) {
        const double m2 = e * e - px * px - py * py - pz * pz;
        return m2 > 0.0 ? std::sqrt(m2) : 0.0;
    }

    /// The mass of a system: the sum of the four-vectors, then its mass.
    inline double invariantMass(const std::vector<FourVector>& particles) {
        FourVector total{0.0, 0.0, 0.0, 0.0};
        for (const FourVector& particle : particles) total = total + particle;
        return invariantMass(total.e(), total.px(), total.py(), total.pz());
    }

    inline FourVector sum(const std::vector<FourVector>& particles) {
        FourVector total{0.0, 0.0, 0.0, 0.0};
        for (const FourVector& particle : particles) total = total + particle;
        return total;
    }

    // ── DIS invariants ───────────────────────────────────────────────────────
    // The variables an ep run is described by. Rivet has `DISKinematics` for an analysis; a module
    // has this, and the two agree because they are the same four formulas.

    struct Dis {
        double q2 = 0.0;    ///< Q² = −q², the photon virtuality [GeV²]
        double x = 0.0;     ///< Bjorken x = Q² / (2 P·q)
        double y = 0.0;     ///< inelasticity y = (P·q) / (P·k)
        double w2 = 0.0;    ///< W² = (P + q)², the hadronic mass squared [GeV²]
        double nu = 0.0;    ///< ν = (P·q) / M, the energy transfer in the hadron's rest frame [GeV]

        /// Photoproduction is the Q² → 0 limit; the conventional line is 1 GeV².
        bool photoproduction(double q2_max = 1.0) const { return q2 < q2_max; }
    };

    /// The invariants from the three vectors that define them: the lepton before and after, and the
    /// hadron it scattered off. Degenerate cases (a hadron at rest, a zero denominator) give 0
    /// rather than an infinity, so one bad event cannot poison a histogram.
    inline Dis disKinematics(const FourVector& beam_lepton, const FourVector& scattered_lepton,
                             const FourVector& beam_hadron) {
        const FourVector q = beam_lepton - scattered_lepton;
        Dis found;
        found.q2 = -dot(q, q);

        const double hadron_dot_q = dot(beam_hadron, q);
        const double hadron_dot_lepton = dot(beam_hadron, beam_lepton);
        if (hadron_dot_lepton != 0.0) found.y = hadron_dot_q / hadron_dot_lepton;
        if (hadron_dot_q != 0.0) found.x = found.q2 / (2.0 * hadron_dot_q);

        const double hadron_mass = beam_hadron.m();
        if (hadron_mass > 0.0) found.nu = hadron_dot_q / hadron_mass;

        const FourVector hadronic = beam_hadron + q;
        found.w2 = dot(hadronic, hadronic);
        return found;
    }

}  // namespace Phys
