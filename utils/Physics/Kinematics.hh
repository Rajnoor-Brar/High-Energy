#pragma once

#include <cmath>

#include "Math/Vector4D.h"
#include "Math/VectorUtil.h"

#include "Physics/Types.hh"

namespace Physics {

    // Per-particle observables live in the kParticleTraits table (Types.hh);
    // this header keeps only the pairwise/derived kinematics helpers.
    // (A Column-based batch API — invariantMassColumn, momentum, rapidity
    // et al. over vector<Double_t> — used to live here; it predated the
    // trait table, had no callers anywhere, and was removed in the round-2
    // dead-code pass. See docs/Audit.md §5.1.)

    inline Double_t invariantMass(const Lorentz& a, const Lorentz& b) {
        return (a + b).M();
    }

    // Spacelike inputs (m² < 0, e.g. from rounding) clamp to 0, never NaN.
    inline Double_t invariantMass(Double_t E, Double_t px, Double_t py, Double_t pz) {
        const Double_t m2 = E * E - px * px - py * py - pz * pz;
        return m2 > 0.0 ? std::sqrt(m2) : 0.0;
    }

    // Wraps into (-π, π].
    inline Double_t deltaPhi(Double_t phi1, Double_t phi2) {
        Double_t d = phi1 - phi2;
        while (d >  M_PI) d -= 2.0 * M_PI;
        while (d < -M_PI) d += 2.0 * M_PI;
        return d;
    }

    inline Double_t deltaR(const Lorentz& a, const Lorentz& b) {
        const Double_t dEta = a.Eta() - b.Eta();
        const Double_t dPhi = deltaPhi(a.Phi(), b.Phi());
        return std::sqrt(dEta * dEta + dPhi * dPhi);
    }
}
