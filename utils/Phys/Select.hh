#pragma once

// ── Phys/Select.hh ───────────────────────────────────────────────────────────
// Getting the particles you want out of a `GenEvent` (13 §2).
//
// A module is handed a whole event — beams, the hard process, every shower and hadronisation
// product, and the decayed copies of things that are also present as their daughters. Nearly every
// module starts by throwing most of that away. `modules/Examples/ToyJets.cc` was written before this
// header and carried that loop itself: a status comparison, a pT and an |η| cut, and a hand-rolled
// pseudorapidity wrapped in a guard against the particle travelling straight down the beam. This is
// that loop, once, and the module is four lines shorter for it.
//
// **Status 1 is the only reliable "final".** HepMC3 status codes above 3 are generator-specific, and
// a particle that has decayed is still in the event with its daughters — so summing everything, or
// keeping everything with no `end_vertex`, double-counts. `finalState` means status 1 and nothing
// else.
//
// **`Acceptance` is data, not code.** A cut written as a struct can be logged, compared between two
// runs, and put in a config later; the same cut written as an `if` inside a module can only be read.
// It deliberately has no charge cut: HepMC3 does not carry a charge and thirteen rows of PDG table
// cannot supply one for an arbitrary code, so a module that wants charged particles composes its own
// predicate with `selectIf` rather than being handed an answer that is right for pions and wrong for
// everything else.

#include <algorithm>
#include <limits>
#include <optional>
#include <vector>

#include "HepMC3/GenEvent.h"
#include "HepMC3/GenParticle.h"

#include "Phys/Kinematics.hh"
#include "Phys/Pdg.hh"
#include "Phys/Types.hh"

namespace Phys {

    using Particle = HepMC3::ConstGenParticlePtr;
    using Particles = std::vector<Particle>;

    /// HepMC3 status codes that mean the same thing in every generator (HepMC3 §3.2).
    enum Status : int {
        Final = 1,            ///< a particle that really is final
        Decayed = 2,          ///< decayed, and present again as its daughters
        Documentation = 3,    ///< a hard-process record entry
        Beam = 4,             ///< an incoming beam particle
    };

    // ── a cut, as data ───────────────────────────────────────────────────────

    struct Acceptance {
        double pt_min = 0.0;
        double pt_max = std::numeric_limits<double>::infinity();
        double eta_max = std::numeric_limits<double>::infinity();   ///< on |η|
        double e_min = 0.0;
        bool visible = false;   ///< drop neutrinos

        /// Whether this momentum passes. A particle along the beam has infinite η and fails any
        /// finite `eta_max`; with no `eta_max` set it passes, which is what "no η cut" should mean.
        bool accepts(const FourVector& momentum) const {
            const double pt = momentum.perp();
            if (pt < pt_min || pt > pt_max) return false;
            if (momentum.e() < e_min) return false;
            if (std::isfinite(eta_max) && !(std::abs(momentum.eta()) <= eta_max)) return false;
            return true;
        }

        bool accepts(const Particle& particle) const {
            if (!particle) return false;
            if (visible && Pdg::isNeutrino(particle->pid())) return false;
            return accepts(particle->momentum());
        }
    };

    // ── selectors ────────────────────────────────────────────────────────────

    /// Every particle the predicate keeps, in the event's own order.
    template <typename Predicate>
    Particles selectIf(const HepMC3::GenEvent& event, Predicate keep) {
        Particles kept;
        for (const Particle& particle : event.particles())
            if (particle && keep(particle)) kept.push_back(particle);
        return kept;
    }

    inline Particles withStatus(const HepMC3::GenEvent& event, int status) {
        return selectIf(event, [status](const Particle& p) { return p->status() == status; });
    }

    /// Status 1, and nothing else — see the header note on why.
    inline Particles finalState(const HepMC3::GenEvent& event) {
        return withStatus(event, Status::Final);
    }

    inline Particles finalState(const HepMC3::GenEvent& event, const Acceptance& acceptance) {
        return selectIf(event, [&acceptance](const Particle& p) {
            return p->status() == Status::Final && acceptance.accepts(p);
        });
    }

    /// `either_sign` takes the antiparticle too, which is usually what "the pions" means.
    inline Particles withPid(const HepMC3::GenEvent& event, int pid, bool either_sign = false) {
        return selectIf(event, [pid, either_sign](const Particle& p) {
            return either_sign ? std::abs(p->pid()) == std::abs(pid) : p->pid() == pid;
        });
    }

    /// The incoming beams. HepMC3 keeps them itself, so this is its answer rather than a status cut.
    inline Particles beams(const HepMC3::GenEvent& event) { return event.beams(); }

    /// The beam particle whose PDG code matches, or a null pointer. The lepton beam of an ep run is
    /// `beam(event, 11)` — `either_sign`, because a beam of positrons is still the lepton beam.
    inline Particle beam(const HepMC3::GenEvent& event, int pid, bool either_sign = true) {
        for (const Particle& particle : event.beams()) {
            if (!particle) continue;
            const bool matches = either_sign ? std::abs(particle->pid()) == std::abs(pid)
                                             : particle->pid() == pid;
            if (matches) return particle;
        }
        return {};
    }

    /// The most energetic particle of a set, or null for an empty one.
    inline Particle mostEnergetic(const Particles& particles) {
        Particle best;
        for (const Particle& particle : particles) {
            if (!particle) continue;
            if (!best || particle->momentum().e() > best->momentum().e()) best = particle;
        }
        return best;
    }

    /// The scattered lepton: the most energetic **final-state** lepton of the beam's flavour.
    ///
    /// A heuristic, and named as one. It is what an experiment does and it is right for the DIS and
    /// photoproduction events this project generates, but a lepton radiated from the hadronic side
    /// could in principle outrank the real one. A null return is a real answer — P7-S04 found that
    /// Whizard's EPA events have no scattered lepton at all, because the photon flux replaces it —
    /// so callers must check rather than dereference.
    inline Particle scatteredLepton(const HepMC3::GenEvent& event, int beam_pid = 11) {
        const Particle incoming = beam(event, beam_pid);
        const int flavour = incoming ? incoming->pid() : beam_pid;
        return mostEnergetic(selectIf(event, [flavour](const Particle& p) {
            return p->status() == Status::Final && p->pid() == flavour;
        }));
    }

    // ── momenta ──────────────────────────────────────────────────────────────

    inline std::vector<FourVector> momenta(const Particles& particles) {
        std::vector<FourVector> found;
        found.reserve(particles.size());
        for (const Particle& particle : particles)
            if (particle) found.push_back(particle->momentum());
        return found;
    }

    /// The DIS invariants of an event, from its own beams and its scattered lepton. Returns nothing
    /// when the event has no scattered lepton to find.
    inline std::optional<Dis> disKinematics(const HepMC3::GenEvent& event, int lepton_pid = 11,
                                            int hadron_pid = 2212) {
        const Particle incoming = beam(event, lepton_pid);
        const Particle hadron = beam(event, hadron_pid);
        const Particle scattered = scatteredLepton(event, lepton_pid);
        if (!incoming || !hadron || !scattered) return std::nullopt;
        return disKinematics(incoming->momentum(), scattered->momentum(), hadron->momentum());
    }

}  // namespace Phys
