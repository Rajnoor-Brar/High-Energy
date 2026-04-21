#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <string>
#include <vector>

#include "Config.hh"
#include "Math/Vector4D.h"
#include "Math/VectorUtil.h"

namespace Analysis {
    using Lorentz = ROOT::Math::PxPyPzEVector;
    using Column  = std::vector<Double_t>;

    template <typename Enum>
    constexpr std::size_t toIndex(Enum value) {
        return static_cast<std::size_t>(value);
    }

    struct QuantityTraits {
        const char* name;
        Double_t (*extract)(const Lorentz&);
    };

    static constexpr std::array<QuantityTraits, 13> kQuantityTraits = {{
        {"Mass_Invariant",      [](const Lorentz& p) -> Double_t { return p.M(); }},
        {"Mass_Transverse",     [](const Lorentz& p) -> Double_t { return p.Mt(); }},
        {"Energy_Net",          [](const Lorentz& p) -> Double_t { return p.E(); }},
        {"Energy_Transverse",   [](const Lorentz& p) -> Double_t { return std::sqrt(p.Pt() * p.Pt() + p.M() * p.M()); }},
        {"Momentum_Net",        [](const Lorentz& p) -> Double_t { return p.P(); }},
        {"Momentum_Transverse", [](const Lorentz& p) -> Double_t { return p.Pt(); }},
        {"Momentum_X",          [](const Lorentz& p) -> Double_t { return p.Px(); }},
        {"Momentum_Y",          [](const Lorentz& p) -> Double_t { return p.Py(); }},
        {"Momentum_Z",          [](const Lorentz& p) -> Double_t { return p.Pz(); }},
        {"Rapidity",            [](const Lorentz& p) -> Double_t { return p.Rapidity(); }},
        {"Pseudorapidity",      [](const Lorentz& p) -> Double_t { return p.Eta(); }},
        {"Azimuthal_Angle",     [](const Lorentz& p) -> Double_t { return p.Phi(); }},
        {"Multiplicity",        [](const Lorentz&  ) -> Double_t { return 1.0; }},
    }};

    static_assert(kQuantityTraits.size() == static_cast<std::size_t>(Config::Quantity::Multiplicity) + 1,
                  "kQuantityTraits size out of sync with Config::Quantity enum");

    inline std::string quantityName(Config::Quantity quantity) {
        return kQuantityTraits[toIndex(quantity)].name;
    }

    inline Double_t valueOf(const Lorentz& particle, Config::Quantity quantity) {
        return kQuantityTraits[toIndex(quantity)].extract(particle);
    }

    inline Lorentz fromComponents(Double_t E, Double_t px, Double_t py, Double_t pz) {
        return Lorentz(px, py, pz, E);
    }

    inline Double_t invariantMass(const Lorentz& a, const Lorentz& b) {
        return (a + b).M();
    }

    inline Double_t invariantMass(Double_t E, Double_t px, Double_t py, Double_t pz) {
        const Double_t m2 = E * E - px * px - py * py - pz * pz;
        return m2 > 0.0 ? std::sqrt(m2) : 0.0;
    }

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

    inline Double_t cosOpening(const Lorentz& a, const Lorentz& b) {
        const Double_t pa = a.P();
        const Double_t pb = b.P();
        if (pa <= 0.0 || pb <= 0.0) return 0.0;
        return (a.Px() * b.Px() + a.Py() * b.Py() + a.Pz() * b.Pz()) / (pa * pb);
    }

    inline Column invariantMassColumn(const Column& E, const Column& px,
                                      const Column& py, const Column& pz) {
        const std::size_t n = E.size();
        Column out(n, 0.0);
        for (std::size_t i = 0; i < n; ++i)
            out[i] = invariantMass(E[i], px[i], py[i], pz[i]);
        return out;
    }

    inline Column transverseMomentum(const Column& px, const Column& py) {
        const std::size_t n = px.size();
        Column out(n, 0.0);
        for (std::size_t i = 0; i < n; ++i)
            out[i] = std::sqrt(px[i] * px[i] + py[i] * py[i]);
        return out;
    }

    inline Column momentum(const Column& px, const Column& py, const Column& pz) {
        const std::size_t n = px.size();
        Column out(n, 0.0);
        for (std::size_t i = 0; i < n; ++i)
            out[i] = std::sqrt(px[i] * px[i] + py[i] * py[i] + pz[i] * pz[i]);
        return out;
    }

    inline Column pseudorapidity(const Column& px, const Column& py, const Column& pz) {
        const std::size_t n = px.size();
        Column out(n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            const Double_t pt    = std::sqrt(px[i] * px[i] + py[i] * py[i]);
            const Double_t theta = std::atan2(pt, pz[i]);
            out[i] = -std::log(std::tan(theta / 2.0));
        }
        return out;
    }

    inline Column rapidity(const Column& E, const Column& pz) {
        const std::size_t n = E.size();
        Column out(n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            const Double_t num = E[i] + pz[i];
            const Double_t den = E[i] - pz[i];
            out[i] = (den > 0.0 && num > 0.0) ? 0.5 * std::log(num / den) : 0.0;
        }
        return out;
    }

    inline Column azimuthalAngle(const Column& px, const Column& py) {
        const std::size_t n = px.size();
        Column out(n, 0.0);
        for (std::size_t i = 0; i < n; ++i)
            out[i] = std::atan2(py[i], px[i]);
        return out;
    }
}
