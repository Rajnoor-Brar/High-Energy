#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <vector>

#include "Math/Vector4D.h"
#include "Rtypes.h"

namespace Physics {

    using Lorentz = ROOT::Math::PxPyPzEVector;
    using Column  = std::vector<Double_t>;

    // ── Property enums ────────────────────────────────────────────────────────
    // The single source of truth for what a "particle property" or
    // "event property" can be. Config::ParticleLimits / Config::EventLimits
    // key their maps on these enums; Record / Lambda / Probe consume them.

    enum class ParticleProperty : std::size_t {
        Mass_Invariant,
        Mass_Transverse,
        Energy_Net,
        Energy_Transverse,
        Momentum_Net,
        Momentum_Transverse,
        Momentum_X,
        Momentum_Y,
        Momentum_Z,
        Rapidity,
        Pseudorapidity,
        Azimuthal_Angle,
        EventIndex, // reserved for tree branches that capture the event index of a particle candidate
    };

    enum class EventProperty : std::size_t {
        Multiplicity,
    };

    template <typename Enum>
    constexpr std::size_t toIndex(Enum value) {
        return static_cast<std::size_t>(value);
    }

    // ── Traits ────────────────────────────────────────────────────────────────
    // Each trait carries its own enum id, so kParticleTraits is self-keyed.
    // Lookup by enum goes through traitsOf() which validates enum/index sync
    // at the call site.

    struct ParticleTraits {
        ParticleProperty id;
        const char*      name;
        Double_t (*extract)(const Lorentz&);
    };
    struct EventTraits {
        EventProperty id;
        const char*   name;
        Double_t (*extract)(const std::vector<Lorentz>&);
    };

    inline constexpr std::array<ParticleTraits, 12> kParticleTraits = {{
        {ParticleProperty::Mass_Invariant,      "Mass_Invariant",      [](const Lorentz& p) -> Double_t { return p.M();  }},
        {ParticleProperty::Mass_Transverse,     "Mass_Transverse",     [](const Lorentz& p) -> Double_t { return p.Mt(); }},
        {ParticleProperty::Energy_Net,          "Energy_Net",          [](const Lorentz& p) -> Double_t { return p.E();  }},
        {ParticleProperty::Energy_Transverse,   "Energy_Transverse",   [](const Lorentz& p) -> Double_t { return std::sqrt(p.Pt() * p.Pt() + p.M() * p.M()); }},
        {ParticleProperty::Momentum_Net,        "Momentum_Net",        [](const Lorentz& p) -> Double_t { return p.P();  }},
        {ParticleProperty::Momentum_Transverse, "Momentum_Transverse", [](const Lorentz& p) -> Double_t { return p.Pt(); }},
        {ParticleProperty::Momentum_X,          "Momentum_X",          [](const Lorentz& p) -> Double_t { return p.Px(); }},
        {ParticleProperty::Momentum_Y,          "Momentum_Y",          [](const Lorentz& p) -> Double_t { return p.Py(); }},
        {ParticleProperty::Momentum_Z,          "Momentum_Z",          [](const Lorentz& p) -> Double_t { return p.Pz(); }},
        {ParticleProperty::Rapidity,            "Rapidity",            [](const Lorentz& p) -> Double_t { return p.Rapidity(); }},
        {ParticleProperty::Pseudorapidity,      "Pseudorapidity",      [](const Lorentz& p) -> Double_t { return p.Eta(); }},
        {ParticleProperty::Azimuthal_Angle,     "Azimuthal_Angle",     [](const Lorentz& p) -> Double_t { return p.Phi(); }},
    }};

    static_assert(kParticleTraits.size() ==
                  static_cast<std::size_t>(ParticleProperty::Azimuthal_Angle) + 1,
                  "kParticleTraits size out of sync with ParticleProperty enum");

    inline constexpr std::array<EventTraits, 1> kEventTraits = {{
        {EventProperty::Multiplicity, "Multiplicity",
         [](const std::vector<Lorentz>& v) -> Double_t { return static_cast<Double_t>(v.size()); }},
    }};

    static_assert(kEventTraits.size() ==
                  static_cast<std::size_t>(EventProperty::Multiplicity) + 1,
                  "kEventTraits size out of sync with EventProperty enum");

    inline const ParticleTraits& traitsOf(ParticleProperty p) {
        const auto& trait = kParticleTraits[toIndex(p)];
        if (trait.id != p)
            throw std::logic_error("Physics::kParticleTraits ordering does not match ParticleProperty enum");
        return trait;
    }

    inline const EventTraits& traitsOf(EventProperty p) {
        const auto& trait = kEventTraits[toIndex(p)];
        if (trait.id != p)
            throw std::logic_error("Physics::kEventTraits ordering does not match EventProperty enum");
        return trait;
    }
}
