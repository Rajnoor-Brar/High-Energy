#pragma once

// ── Phys/Types.hh ────────────────────────────────────────────────────────────
// The four-vector everything else here speaks, and the property table that names what can be taken
// from one (13 §2; ported from `legacy/utils/Physics/{Types,TypeAid,Properties}.hh`).
//
// **The vector is HepMC3's.** The legacy `Physics::Lorentz` was `ROOT::Math::PxPyPzEVector`, so a
// module that wanted a particle's pT had to link ROOT and convert every particle out of the event it
// was already holding. `HepMC3::FourVector` is what a `GenEvent` stores, so there is no conversion at
// all, and it carries everything ROOT's did that is used here — components, pT, η, y, φ, m, and
// arithmetic — with a handful of exceptions (`transverseMass` below, `Phys::dot`) that are added
// rather than wrapped. Nothing in this namespace defines its own vector type, so a module can pass
// the momentum it already has straight in.
//
// **The property table is self-keyed**, the way the legacy one was: each row carries its own enum id
// and `traitsOf` checks it, so a row inserted in the wrong place is a startup error rather than a
// column of numbers that quietly means something else. `EventIndex` is deliberately *not* in the
// table — it is a branch label, not a thing a four-vector knows — and asking for its extractor
// throws rather than reading off the end, which is the bounds check the legacy hardening test was
// written for.
//
// The string spellings are the legacy ones (`Momentum_Transverse`, not `pt`) because they are the
// names already written in the old configs, and a name that has to be looked up twice is worth less
// than one that is the same in both places.

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <optional>
#include <string>
#include <vector>

#include "HepMC3/FourVector.h"

#include "Core/Errors.hh"

namespace Phys {

    /// What a particle's momentum is, everywhere in this namespace. Units are GeV (00 §2).
    using FourVector = HepMC3::FourVector;

    // ── property enums ───────────────────────────────────────────────────────

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
        EventIndex,   // a branch label, not a property of a four-vector: no extractor, on purpose
    };

    enum class EventProperty : std::size_t {
        Multiplicity,
    };

    template <typename Enum>
    constexpr std::size_t toIndex(Enum value) {
        return static_cast<std::size_t>(value);
    }

    // ── traits ───────────────────────────────────────────────────────────────

    struct ParticleTraits {
        ParticleProperty id;
        const char* name;
        double (*extract)(const FourVector&);
    };

    struct EventTraits {
        EventProperty id;
        const char* name;
        double (*extract)(const std::vector<FourVector>&);
    };

    /// mT = √(m² + pT²) — the transverse mass, which HepMC3's vector does not have.
    inline double transverseMass(const FourVector& p) {
        const double m2 = p.m2();
        return std::sqrt(std::max(0.0, m2) + p.perp2());
    }

    inline constexpr std::array<ParticleTraits, 12> kParticleTraits = {{
        {ParticleProperty::Mass_Invariant,      "Mass_Invariant",
         [](const FourVector& p) { return p.m(); }},
        {ParticleProperty::Mass_Transverse,     "Mass_Transverse",
         [](const FourVector& p) { return transverseMass(p); }},
        {ParticleProperty::Energy_Net,          "Energy_Net",
         [](const FourVector& p) { return p.e(); }},
        // The calorimeter-style ET = √(pT² + m²), which for an on-shell particle is its mT. The
        // other convention (E·sinθ) differs for massive particles: if it is ever wanted, it changes
        // *here* and in the docs of anything already stored.
        {ParticleProperty::Energy_Transverse,   "Energy_Transverse",
         [](const FourVector& p) { return transverseMass(p); }},
        {ParticleProperty::Momentum_Net,        "Momentum_Net",
         [](const FourVector& p) { return p.p3mod(); }},
        {ParticleProperty::Momentum_Transverse, "Momentum_Transverse",
         [](const FourVector& p) { return p.perp(); }},
        {ParticleProperty::Momentum_X,          "Momentum_X",
         [](const FourVector& p) { return p.px(); }},
        {ParticleProperty::Momentum_Y,          "Momentum_Y",
         [](const FourVector& p) { return p.py(); }},
        {ParticleProperty::Momentum_Z,          "Momentum_Z",
         [](const FourVector& p) { return p.pz(); }},
        {ParticleProperty::Rapidity,            "Rapidity",
         [](const FourVector& p) { return p.rap(); }},
        {ParticleProperty::Pseudorapidity,      "Pseudorapidity",
         [](const FourVector& p) { return p.eta(); }},
        {ParticleProperty::Azimuthal_Angle,     "Azimuthal_Angle",
         [](const FourVector& p) { return p.phi(); }},
    }};

    static_assert(kParticleTraits.size() ==
                      static_cast<std::size_t>(ParticleProperty::Azimuthal_Angle) + 1,
                  "kParticleTraits is out of step with ParticleProperty");

    inline constexpr std::array<EventTraits, 1> kEventTraits = {{
        {EventProperty::Multiplicity, "Multiplicity",
         [](const std::vector<FourVector>& particles) {
             return static_cast<double>(particles.size());
         }},
    }};

    static_assert(kEventTraits.size() ==
                      static_cast<std::size_t>(EventProperty::Multiplicity) + 1,
                  "kEventTraits is out of step with EventProperty");

    /// The row for a property. Throws for one that has no extractor — `EventIndex` — rather than
    /// indexing past the end of the table.
    inline const ParticleTraits& traitsOf(ParticleProperty property) {
        if (toIndex(property) >= kParticleTraits.size())
            throw Core::Error{Core::Exit::Internal,
                              "Phys::traitsOf: this ParticleProperty has no extractor",
                              "EventIndex is a branch label, not something a four-vector knows"};
        const ParticleTraits& row = kParticleTraits[toIndex(property)];
        if (row.id != property)
            throw Core::Error{Core::Exit::Internal,
                              "Phys::kParticleTraits is out of order",
                              "a row was inserted without moving the enum with it"};
        return row;
    }

    inline const EventTraits& traitsOf(EventProperty property) {
        if (toIndex(property) >= kEventTraits.size())
            throw Core::Error{Core::Exit::Internal,
                              "Phys::traitsOf: this EventProperty has no extractor"};
        const EventTraits& row = kEventTraits[toIndex(property)];
        if (row.id != property)
            throw Core::Error{Core::Exit::Internal, "Phys::kEventTraits is out of order"};
        return row;
    }

    // ── reading one ──────────────────────────────────────────────────────────

    inline double valueOf(const FourVector& particle, ParticleProperty property) {
        return traitsOf(property).extract(particle);
    }

    inline double valueOf(const std::vector<FourVector>& particles, EventProperty property) {
        return traitsOf(property).extract(particles);
    }

    inline const char* nameOf(ParticleProperty property) { return traitsOf(property).name; }
    inline const char* nameOf(EventProperty property) { return traitsOf(property).name; }

    // ── names ────────────────────────────────────────────────────────────────

    /// The property with this name, or nothing. `Mass` and `Energy` are the historical short
    /// spellings of the two that had them.
    inline std::optional<ParticleProperty> particleProperty(const std::string& name) {
        if (name == "Mass") return ParticleProperty::Mass_Invariant;
        if (name == "Energy") return ParticleProperty::Energy_Net;
        for (const ParticleTraits& row : kParticleTraits)
            if (name == row.name) return row.id;
        return std::nullopt;
    }

    inline std::optional<EventProperty> eventProperty(const std::string& name) {
        for (const EventTraits& row : kEventTraits)
            if (name == row.name) return row.id;
        return std::nullopt;
    }

    /// The same lookup, for a caller that has nothing useful to do with "not a property".
    inline ParticleProperty requireParticleProperty(const std::string& name) {
        if (const std::optional<ParticleProperty> found = particleProperty(name)) return *found;
        throw Core::Error{Core::Exit::Config, "no particle property called '" + name + "'",
                          "see Phys::kParticleTraits for the spellings"};
    }

    inline EventProperty requireEventProperty(const std::string& name) {
        if (const std::optional<EventProperty> found = eventProperty(name)) return *found;
        throw Core::Error{Core::Exit::Config, "no event property called '" + name + "'",
                          "see Phys::kEventTraits for the spellings"};
    }

}  // namespace Phys
