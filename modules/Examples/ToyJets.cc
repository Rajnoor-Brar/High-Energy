// ── modules/Examples/ToyJets.cc ──────────────────────────────────────────────
// The smallest useful module, and the one the tests measure (05 §5, P8-S01).
//
// It exists to show the four verbs and the scaling contract in something short enough to read
// whole. The physics is deliberately trivial — final-state multiplicity, pT and η — because the
// point being made is about *where* things happen, not about what is being measured:
//
//   * `book` declares, once, before any event. A duplicate name or an inverted range is caught here.
//   * `process` fills **this worker's** clones with the event's raw weight. There is no `scale()`
//     to call, which is the contract rather than a convention.
//   * `finalize` runs once, after every worker's clones have been added together, with σ and ΣW
//     known. It is the only place scaling exists.
//
// That last point is what the "exact totals at 1, 4 and 20 threads" test checks: fills add, so k
// workers give the same integral as one.

#include "Module/Registry.hh"
#include "Module/Types.hh"

#include "HepMC3/GenEvent.h"
#include "HepMC3/GenParticle.h"

#include <cmath>

namespace {

    /// HepMC3 status 1: a particle that is really final.
    constexpr int FINAL = 1;

    class ToyJets : public Module::Base {
      public:
        void configure(const Core::Options& options) override {
            // A module's options are its own invention; `Core::Options` only says what was expected
            // when a value is not a number.
            pt_min_ = options.number("pt_min", 0.5);
            eta_max_ = options.number("eta_max", 5.0);
        }

        void book(Results::Booker& booker) override {
            multiplicity_ = booker.histo1D("multiplicity", 50, 0.0, 200.0,
                                           "final-state particles per event");
            pt_ = booker.histo1D("pt", 40, 0.0, 20.0, "particle $p_T$ [GeV]");
            eta_ = booker.histo1D("eta", 40, -5.0, 5.0, "particle $\\eta$");
            pt_vs_eta_ = booker.profile1D("pt_vs_eta", 20, -5.0, 5.0,
                                          "mean $p_T$ against $\\eta$");
            counted_ = booker.counter("events", "events this module saw");
        }

        void process(Events::View& view, Results::Worker& worker) override {
            const HepMC3::GenEvent* event = view.hepmcOrNull();
            if (event == nullptr) return;
            const double weight = view.weights().nominal();

            long long kept = 0;
            for (const auto& particle : event->particles()) {
                if (particle->status() != FINAL) continue;
                const HepMC3::FourVector& momentum = particle->momentum();
                const double pt = std::hypot(momentum.px(), momentum.py());
                if (pt < pt_min_) continue;
                const double magnitude = std::sqrt(momentum.px() * momentum.px() +
                                                   momentum.py() * momentum.py() +
                                                   momentum.pz() * momentum.pz());
                // A particle exactly along the beam has no finite eta; skipping it is honest, and
                // an arbitrary large number would put a spike in the outermost bin.
                if (magnitude <= std::abs(momentum.pz())) continue;
                const double eta =
                    0.5 * std::log((magnitude + momentum.pz()) / (magnitude - momentum.pz()));
                if (std::abs(eta) > eta_max_) continue;

                worker.fill(pt_, pt, weight);
                worker.fill(eta_, eta, weight);
                worker.fill(pt_vs_eta_, eta, pt, weight);
                kept += 1;
            }
            worker.fill(multiplicity_, static_cast<double>(kept), weight);
            worker.count(counted_, weight);
        }

        void finalize(Results::Final& results) override {
            // σ / Σw turns a weight sum into a cross-section. The only scaling in the module, and
            // the only place it could be.
            results.normalise(multiplicity_);
            results.normalise(pt_);
            results.normalise(eta_);
            // A profile is a *mean*, so scaling it would be wrong: it is already per-entry.
        }

      private:
        double pt_min_ = 0.5;
        double eta_max_ = 5.0;
        Results::Handle multiplicity_ = 0;
        Results::Handle pt_ = 0;
        Results::Handle eta_ = 0;
        Results::Handle pt_vs_eta_ = 0;
        Results::Handle counted_ = 0;
    };

}  // namespace

HEKIT_MODULE("ToyJets", ToyJets)
