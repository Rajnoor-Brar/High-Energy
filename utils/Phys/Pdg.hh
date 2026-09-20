#pragma once

// ── Phys/Pdg.hh ──────────────────────────────────────────────────────────────
// What a PDG code means: a small table of the particles this project actually writes down, and the
// predicates that come from the *numbering scheme* rather than from a table (ported from
// `legacy/utils/Physics/Particles.hh`).
//
// **Two different things, deliberately separated.**
//
//   * a **table** answers "how heavy is a Λ" — there is no formula, so it is thirteen rows of data,
//     checked against Pythia's `ParticleData` by `tests/cxx/test_phys.cc`. It is short on purpose:
//     a module that needs the whole PDG already has Pythia's copy of it, and a second full table
//     that drifts out of date is worse than no table;
//   * a **predicate** answers "is 14 a neutrino" — that *is* a formula, laid down by the PDG
//     numbering scheme, so `isNeutrino` reads the digits rather than looking anything up and works
//     for every code including ones nobody has tabulated.
//
// **One legacy defect fixed here.** `Physics::particle(-211).charge3` returned +3: the lookup
// resolved the antiparticle to its particle entry and then handed back that entry's charge, so a π⁻
// was positive. The table still keys on |id| — that is the only way thirteen rows can cover
// twenty-six particles — but `charge3(id)` and `charge(id)` flip the sign for a negative code, and
// `info(id).charge3` is documented as the charge of the *positive* state.
//
// Masses are GeV (00 §2), PDG 2024, and agree with Pythia's table to the five decimals Pythia keeps.

#include <array>
#include <cmath>
#include <cstdlib>
#include <string>

#include "Core/Errors.hh"

namespace Phys::Pdg {

    struct Info {
        int pdgId;            ///< the positive (particle) code
        const char* name;     ///< Pythia's spelling, so the two agree when they are printed together
        double mass;          ///< GeV
        int charge3;          ///< charge of the **positive-code** state, in units of e/3
    };

    inline constexpr std::array<Info, 13> kParticles = {{
        {11,   "e-",       0.000511, -3},
        {13,   "mu-",      0.105658, -3},
        {22,   "gamma",    0.0,       0},
        {111,  "pi0",      0.134977,  0},
        {211,  "pi+",      0.139570, +3},
        {130,  "K_L0",     0.497611,  0},
        {310,  "K_S0",     0.497611,  0},
        {321,  "K+",       0.493677, +3},
        {2112, "n0",       0.939565,  0},
        {2212, "p+",       0.938272, +3},
        {3122, "Lambda0",  1.115683,  0},
        {3312, "Xi-",      1.321710, -3},
        {3334, "Omega-",   1.672450, -3},
    }};

    /// The entry for this code, or `nullptr`. Antiparticles resolve to their particle's entry, so
    /// the `charge3` in it is the **positive** state's — use `charge3(id)` for the signed one.
    inline const Info* find(int pdgId) {
        const int code = std::abs(pdgId);
        for (const Info& entry : kParticles)
            if (entry.pdgId == code) return &entry;
        return nullptr;
    }

    inline bool known(int pdgId) { return find(pdgId) != nullptr; }

    /// The entry, or a `Core::Error`. For anything outside these thirteen, ask Pythia.
    inline const Info& info(int pdgId) {
        if (const Info* entry = find(pdgId)) return *entry;
        throw Core::Error{Core::Exit::Config,
                          "PDG code " + std::to_string(pdgId) + " is not in Phys::Pdg::kParticles",
                          "the table holds the particles this project writes down; Pythia's "
                          "ParticleData has the rest"};
    }

    inline double mass(int pdgId) { return info(pdgId).mass; }
    inline const char* name(int pdgId) { return info(pdgId).name; }

    /// Charge × 3, **signed for the code given**: `charge3(-211)` is −3.
    inline int charge3(int pdgId) {
        const int magnitude = info(pdgId).charge3;
        return pdgId < 0 ? -magnitude : magnitude;
    }

    /// Charge in units of e.
    inline double charge(int pdgId) { return charge3(pdgId) / 3.0; }

    // ── the numbering scheme ─────────────────────────────────────────────────
    // No table: these read the code the way the PDG defines it, so they answer for particles that
    // are not in `kParticles` at all.

    inline bool isQuark(int pdgId) {
        const int code = std::abs(pdgId);
        return code >= 1 && code <= 8;
    }

    inline bool isGluon(int pdgId) { return pdgId == 21; }
    inline bool isPhoton(int pdgId) { return pdgId == 22; }

    inline bool isLepton(int pdgId) {
        const int code = std::abs(pdgId);
        return code >= 11 && code <= 18;
    }

    /// e, μ, τ (and a fourth generation, were there one): the odd codes.
    inline bool isChargedLepton(int pdgId) {
        const int code = std::abs(pdgId);
        return code >= 11 && code <= 18 && (code % 2) == 1;
    }

    /// νe, νμ, ντ: the even codes. What a "visible final state" leaves out.
    inline bool isNeutrino(int pdgId) {
        const int code = std::abs(pdgId);
        return code >= 12 && code <= 18 && (code % 2) == 0;
    }

    /// W, Z, H, g, γ and the rest of 21–37.
    inline bool isBoson(int pdgId) {
        const int code = std::abs(pdgId);
        return code >= 21 && code <= 37;
    }

    /// A nucleus: the ten-digit `±10LZZZAAAI` form. Checked first, because its digits would
    /// otherwise read as a meson or a baryon.
    inline bool isNucleus(int pdgId) {
        const int code = std::abs(pdgId);
        return code > 1000000000;
    }

    /// Three quark digits: 1000 ≤ |id| < 1000000, with none of the first three zero.
    inline bool isBaryon(int pdgId) {
        const int code = std::abs(pdgId);
        if (isNucleus(pdgId) || code < 1000 || code >= 1000000) return false;
        const int nq1 = (code / 1000) % 10;
        const int nq2 = (code / 100) % 10;
        const int nq3 = (code / 10) % 10;
        return nq1 != 0 && nq2 != 0 && nq3 != 0;
    }

    /// Two quark digits: 100 ≤ |id| < 1000000 with the 1000s digit zero. K⁰_L (130) and K⁰_S (310)
    /// are mesons by this rule, which is what they are.
    inline bool isMeson(int pdgId) {
        const int code = std::abs(pdgId);
        if (isNucleus(pdgId) || code < 100 || code >= 1000000) return false;
        if ((code / 1000) % 10 != 0) return false;
        const int nq2 = (code / 100) % 10;
        const int nq3 = (code / 10) % 10;
        return nq2 != 0 && nq3 != 0;
    }

    inline bool isHadron(int pdgId) { return isMeson(pdgId) || isBaryon(pdgId); }

}  // namespace Phys::Pdg
