#pragma once

// ── Physics/Particles.hh ──────────────────────────────────────────────────────
// Central particle-data table: PDG IDs, names, masses, charges.
//
// Units: GeV (project-wide convention — see Physics.hh).
// Masses: PDG 2024 values, truncated to the precision the simulation uses.
//
// Same self-keyed pattern as kParticleTraits: each entry carries its own
// PDG ID, and lookups are checked. Antiparticles share the entry of their
// particle (lookup takes |pdgId|); charge3 is the charge of the listed
// (positive-ID) state in units of e/3.
// ─────────────────────────────────────────────────────────────────────────────

#include <array>
#include <cstdlib>
#include <stdexcept>
#include <string>

#include "Rtypes.h"

namespace Physics {

    struct ParticleInfo {
        int         pdgId;    // positive (particle) PDG code
        const char* name;
        Double_t    massGeV;
        int         charge3;  // electric charge × 3 (e.g. proton = +3, Λ = 0)
    };

    inline constexpr std::array<ParticleInfo, 13> kParticles = {{
        {11,   "e-",      0.000511,  -3},
        {13,   "mu-",     0.105658,  -3},
        {22,   "gamma",   0.0,        0},
        {111,  "pi0",     0.134977,   0},
        {211,  "pi+",     0.139570,  +3},
        {130,  "K0_L",    0.497611,   0},
        {310,  "K0_S",    0.497611,   0},
        {321,  "K+",      0.493677,  +3},
        {2112, "n",       0.939565,   0},
        {2212, "p",       0.938272,  +3},
        {3122, "Lambda",  1.115683,   0},
        {3312, "Xi-",     1.321710,  -3},
        {3334, "Omega-",  1.672450,  -3},
    }};

    // particle — checked lookup by PDG ID; antiparticles resolve to their
    // particle entry (|pdgId|). Throws for IDs not in the table.
    inline const ParticleInfo& particle(int pdgId) {
        const int absId = std::abs(pdgId);
        for (const ParticleInfo& info : kParticles)
            if (info.pdgId == absId) return info;
        throw std::runtime_error("Physics::particle: PDG ID " +
                                 std::to_string(pdgId) + " not in kParticles table");
    }

    // particleMass — convenience for the common case (GeV).
    inline Double_t particleMass(int pdgId) { return particle(pdgId).massGeV; }

} // namespace Physics
