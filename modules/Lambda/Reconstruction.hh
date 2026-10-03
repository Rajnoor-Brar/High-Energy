#pragma once

// modules/Lambda/Reconstruction.hh — the Λ → p π⁻ reconstruction, as a pure function of
// four-vectors. Shared by the module program (Lambda.cc) and the Rivet analysis (Rivet/Lamriv.cc),
// so a disagreement between the two is in the frameworks, never in the physics.
//
// It takes and returns HepMC3::FourVector: no generator, no framework, no ROOT. From v1 (itself a
// port of the legacy module) with the physics unchanged:
//
//   * every (p, π⁻) pair is a candidate (unvalidated);
//   * the pairs inside the mass window, and optionally the cos θ* cut, are validated;
//   * the selected set is the greedy one-to-one matching: best mass agreement first, no track reused,
//     bounded by the protons that are not beam remnants (`reserved_protons`, 2 × Z per beam pair).

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <vector>

#include "HepMC3/FourVector.h"

namespace Lambda {

    using FourVector = HepMC3::FourVector;

    inline constexpr double kLambdaMass = 1.115683;   ///< PDG 2024, GeV
    inline constexpr int kProtonPid = 2212;
    inline constexpr int kPionPid = -211;

    /// The three sets a candidate can belong to. They nest: selected ⊆ validated ⊆ unvalidated.
    enum class Set : std::size_t { Unvalidated = 0, Validated = 1, Selected = 2 };
    inline constexpr std::size_t kSetCount = 3;
    inline constexpr const char* kSetNames[kSetCount] = {"unvalidated", "validated", "selected"};

    struct Cuts {
        double mass_tolerance = 0.15;       ///< |m(pπ) − m(Λ)| accepted, GeV
        double cos_theta_tolerance = 0.0;   ///< 0 = off; else |cosθ* + 1| must be within this
        std::size_t reserved_protons = 2;   ///< beam protons per event that cannot come from a Λ (pp's 2 × Z)
    };

    /// One reconstructed pair, kept with the indices so the greedy matching can refuse a reuse.
    struct Candidate {
        FourVector momentum;
        std::size_t proton_index = 0;
        std::size_t pion_index = 0;
        double mass_difference = 0.0;
    };

    struct Candidates {
        std::vector<FourVector> unvalidated;
        std::vector<FourVector> validated;
        std::vector<FourVector> selected;

        const std::vector<FourVector>& of(Set set) const {
            switch (set) {
                case Set::Validated: return validated;
                case Set::Selected: return selected;
                case Set::Unvalidated: break;
            }
            return unvalidated;
        }
    };

    /// cos θ* — the angle between the daughters in the Λ rest frame.
    ///
    /// A genuine two-body decay gives −1 exactly, because the daughters are back to back there; a
    /// combinatorial pair does not. The boost is written out: six lines, and no ROOT.
    inline double cosThetaStar(const FourVector& proton, const FourVector& pion,
                               const FourVector& lambda) {
        const double energy = lambda.e();
        if (!(energy > 0.0)) return std::numeric_limits<double>::quiet_NaN();

        // β of the Λ, and the Lorentz factor that goes with it.
        const double bx = lambda.px() / energy, by = lambda.py() / energy, bz = lambda.pz() / energy;
        const double b2 = bx * bx + by * by + bz * bz;
        if (!(b2 > 0.0) || b2 >= 1.0) return std::numeric_limits<double>::quiet_NaN();
        const double gamma = 1.0 / std::sqrt(1.0 - b2);

        const auto boost = [&](const FourVector& p) {
            const double bp = bx * p.px() + by * p.py() + bz * p.pz();
            const double factor = (gamma - 1.0) * bp / b2 - gamma * p.e();
            return FourVector(p.px() + factor * bx, p.py() + factor * by, p.pz() + factor * bz,
                              gamma * (p.e() - bp));
        };

        const FourVector p_cm = boost(proton);
        const FourVector pi_cm = boost(pion);
        const double norm = p_cm.p3mod() * pi_cm.p3mod();
        if (!(norm > 0.0)) return std::numeric_limits<double>::quiet_NaN();
        return (p_cm.px() * pi_cm.px() + p_cm.py() * pi_cm.py() + p_cm.pz() * pi_cm.pz()) / norm;
    }

    /// Every pair, the ones inside the window, and the greedy one-to-one matching.
    ///
    /// Cost is O(protons × pions) pairs plus one sort of the validated ones, which is the legacy
    /// behaviour and is fine at these multiplicities. `unvalidated` therefore grows as the product
    /// and is the reason its histograms need a wider mass range than the others.
    inline Candidates reconstruct(const std::vector<FourVector>& protons,
                                  const std::vector<FourVector>& pions, const Cuts& cuts) {
        Candidates result;
        std::vector<Candidate> accepted;

        for (std::size_t ip = 0; ip < protons.size(); ++ip) {
            for (std::size_t ipi = 0; ipi < pions.size(); ++ipi) {
                const FourVector lambda = protons[ip] + pions[ipi];
                result.unvalidated.push_back(lambda);

                const double mass = lambda.m();
                if (!std::isfinite(mass)) continue;
                const double difference = std::abs(mass - kLambdaMass);
                if (difference > cuts.mass_tolerance) continue;

                // Off by default, so the ported behaviour is exactly the legacy one until asked for.
                if (cuts.cos_theta_tolerance > 0.0) {
                    const double cos_theta = cosThetaStar(protons[ip], pions[ipi], lambda);
                    if (!std::isfinite(cos_theta) ||
                        std::abs(cos_theta + 1.0) > cuts.cos_theta_tolerance)
                        continue;
                }

                result.validated.push_back(lambda);
                accepted.push_back(Candidate{lambda, ip, ipi, difference});
            }
        }

        // Beam protons cannot have come from a Λ, so they bound how many candidates are physical.
        const std::size_t target = protons.size() > cuts.reserved_protons
                                       ? protons.size() - cuts.reserved_protons
                                       : 0;
        if (target == 0) return result;

        std::sort(accepted.begin(), accepted.end(), [](const Candidate& a, const Candidate& b) {
            return a.mass_difference < b.mass_difference;
        });

        std::vector<bool> proton_used(protons.size(), false);
        std::vector<bool> pion_used(pions.size(), false);
        for (const Candidate& candidate : accepted) {
            if (proton_used[candidate.proton_index] || pion_used[candidate.pion_index]) continue;
            proton_used[candidate.proton_index] = true;
            pion_used[candidate.pion_index] = true;
            result.selected.push_back(candidate.momentum);
            if (result.selected.size() >= target) break;
        }
        return result;
    }

}  // namespace Lambda
