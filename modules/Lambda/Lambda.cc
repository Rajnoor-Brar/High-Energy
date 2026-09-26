// ── modules/Lambda/Lambda.cc ─────────────────────────────────────────────────
// Λ → p π⁻ reconstruction from Pythia events, as a module sink (05 §5).
//
// This is the legacy `Lambda` module rebuilt on the current framework. The physics is in
// `Reconstruction.hh`; this file is the *framework* half, and it is short on purpose — which is the
// point of the exercise. The legacy version carried its own thread pool, its own ROOT writer, its
// own checkpointing and its own terminal output, in 839 lines across nine headers plus four
// `main()`s. None of that is a module's job any more:
//
//   | legacy Lambda did it              | now                                              |
//   |-----------------------------------|--------------------------------------------------|
//   | own worker pool, collectors       | `Sink::Modules` shards; one clone per worker     |
//   | own ROOT `Record::Writer`         | `Results::Booker` → YODA → `hep proc --export`   |
//   | own checkpoint/heartbeat/log      | the supervisor and the status stream (06)        |
//   | own serial/directory/file naming  | the results layout (07 §1)                       |
//   | four `main()` variants            | one `hep run`, four studies in one TOML          |
//   | hand-rolled TOML reading          | the schema, validated before anything starts     |
//
// **What it fills.** Three nested sets — every (p, π⁻) pair, the pairs inside the mass window, and
// the greedy one-to-one matching — each with the same six distributions plus a per-event count, so
// the three can be compared directly. `/Lambda/<set>_<property>`, which is where the export puts
// them into ROOT directories.
//
// **Thread safety.** This module clusters nothing and holds nothing shared: `process` reads the
// event and fills its own worker's clones, so `threadSafe()` stays true and the sink shards
// (00/B31 and 00/B36 are about the case where it cannot). On a 20-thread run that is the difference
// between the module being free and the module being the run.

#include <cmath>
#include <memory>
#include <string>
#include <vector>

#include "Module/Registry.hh"
#include "Module/Types.hh"
#include "Phys.hh"

#include "HepMC3/GenEvent.h"

#include "Reconstruction.hh"

namespace {

    /// The six distributions each set records. The names are the YODA object names.
    enum Property : std::size_t {
        kMass = 0, kEnergy, kMomentum, kTransverse, kLongitudinal, kPseudorapidity, kPropertyCount
    };

    struct Axis {
        const char* name;
        const char* title;
        std::size_t bins;
        double low;
        double high;
    };

    class LambdaModule : public Module::Base {
      public:
        void configure(const Core::Options& options) override {
            cuts_.mass_tolerance = options.number("mass_tolerance", 0.15);
            cuts_.cos_theta_tolerance = options.number("cos_theta_tolerance", 0.0);
            cuts_.reserved_protons =
                static_cast<std::size_t>(options.integer("reserved_protons", 20));

            // The acceptance the *tracks* must pass before any pairing. The legacy module had no
            // such cut — it took every final-state proton and π⁻ in the record, including ones no
            // detector would see — so the defaults here are wide open and it reproduces that.
            track_.pt_min = options.number("track_pt_min", 0.0);
            track_.eta_max = options.number("track_eta_max",
                                            std::numeric_limits<double>::infinity());

            bins_ = static_cast<std::size_t>(options.integer("bins", 100));
            if (bins_ == 0)
                throw Core::Error{Core::Exit::Config, "Lambda: bins must be at least 1"};

            // The unvalidated set is every pair, so its mass axis has to cover the combinatorics;
            // the other two are inside the window by construction. One knob, not three, because a
            // window wider than the axis is a silent empty histogram.
            mass_window_ = options.number("mass_axis", 0.4);
            max_energy_ = options.number("energy_axis", 200.0);
            max_momentum_ = options.number("momentum_axis", 200.0);
            max_transverse_ = options.number("pt_axis", 20.0);
            max_eta_ = options.number("eta_axis", 8.0);
            max_count_ = static_cast<std::size_t>(options.integer("count_axis", 50));
        }

        void book(Results::Booker& booker) override {
            for (std::size_t set = 0; set < Lambda::kSetCount; ++set) {
                const std::string tag = Lambda::kSetNames[set];

                for (const Axis& axis : axes()) {
                    const std::size_t which = index_of(axis);
                    handles_[set][which] = booker.histo1D(
                        tag + "_" + axis.name, axis.bins, axis.low, axis.high,
                        std::string(axis.title) + " (" + tag + ")");
                    // Kept for `finalize`: see the note there. Every axis here is uniform, so one
                    // width per histogram is the whole story.
                    widths_[which] = (axis.high - axis.low) / static_cast<double>(axis.bins);
                }
                counts_[set] = booker.histo1D(
                    tag + "_count", max_count_ + 1, -0.5, static_cast<double>(max_count_) + 0.5,
                    "candidates per event (" + tag + ")");
            }
            events_ = booker.counter("events", "events this module saw");
        }

        void process(Events::View& view, Results::Worker& worker) override {
            const HepMC3::GenEvent* event = view.hepmcOrNull();
            if (event == nullptr) return;
            const double weight = view.weights().nominal();

            const std::vector<Phys::FourVector> protons = tracks(*event, Lambda::kProtonPid);
            const std::vector<Phys::FourVector> pions = tracks(*event, Lambda::kPionPid);

            const Lambda::Candidates found = Lambda::reconstruct(protons, pions, cuts_);

            for (std::size_t set = 0; set < Lambda::kSetCount; ++set) {
                const auto& candidates = found.of(static_cast<Lambda::Set>(set));
                for (const Phys::FourVector& candidate : candidates) fill(worker, set, candidate,
                                                                          weight);
                worker.fill(counts_[set], static_cast<double>(candidates.size()), weight);
            }
            worker.count(events_, weight);
        }

        void finalize(Results::Final& results) override {
            // σ / Σw, once, here. There is no `scale` on a `Worker`, which is the contract of 05 §5
            // written as a type rather than as a rule to remember.
            //
            // **And divided by the bin width**, which `normalise()` alone does not do. Rivet's
            // `finalize` turns a scaled histogram into a *density* estimate — dσ/dx — so a module
            // that only calls `normalise()` writes per-bin integrals into the same `analysis.yoda`
            // as a Rivet analysis writing densities, and the two differ by exactly the bin width.
            // Measured against `Lamriv` on identical events: 125x on the mass axis, 0.25x on p_z,
            // 6.25x on eta — each one 1/width. The y-axis labels in the booking say dσ/dx, so this
            // is what makes them true. Recorded as 00/B42.
            //
            // `counts_` is a multiplicity, whose bins are one unit wide, so its width is 1 and this
            // is the same as `normalise()` — written out anyway so the convention is visible.
            const double per_event = results.perEventCrossSection();
            for (std::size_t set = 0; set < Lambda::kSetCount; ++set) {
                for (std::size_t property = 0; property < kPropertyCount; ++property)
                    results.scale(handles_[set][property],
                                  widths_[property] > 0.0 ? per_event / widths_[property]
                                                          : per_event);
                results.scale(counts_[set], per_event);
            }
        }

        /// The cuts that produced these numbers, next to them in `run.summary.json`.
        std::vector<std::pair<std::string, std::string>> provenance() const override {
            return {{"mass_tolerance", std::to_string(cuts_.mass_tolerance)},
                    {"cos_theta_tolerance", std::to_string(cuts_.cos_theta_tolerance)},
                    {"reserved_protons", std::to_string(cuts_.reserved_protons)}};
        }

        // No FastJet, no shared state: this one really can shard. See the header note.
        bool threadSafe() const override { return true; }

      private:
        std::vector<Axis> axes() const {
            return {
                {"mass", "$m(p\\pi^-)$ [GeV]", bins_, Lambda::kLambdaMass - mass_window_,
                 Lambda::kLambdaMass + mass_window_},
                {"energy", "$E$ [GeV]", bins_, 0.0, max_energy_},
                {"momentum", "$|p|$ [GeV]", bins_, 0.0, max_momentum_},
                {"pt", "$p_T$ [GeV]", bins_, 0.0, max_transverse_},
                {"pz", "$p_z$ [GeV]", bins_, -max_momentum_, max_momentum_},
                {"eta", "$\\eta$", bins_, -max_eta_, max_eta_},
            };
        }

        static std::size_t index_of(const Axis& axis) {
            const std::string name = axis.name;
            if (name == "mass") return kMass;
            if (name == "energy") return kEnergy;
            if (name == "momentum") return kMomentum;
            if (name == "pt") return kTransverse;
            if (name == "pz") return kLongitudinal;
            return kPseudorapidity;
        }

        std::vector<Phys::FourVector> tracks(const HepMC3::GenEvent& event, int pid) const {
            std::vector<Phys::FourVector> found;
            for (const Phys::Particle& particle : Phys::withPid(event, pid)) {
                if (particle->status() != 1) continue;            // final state only
                if (!track_.accepts(particle)) continue;
                found.push_back(particle->momentum());
            }
            return found;
        }

        void fill(Results::Worker& worker, std::size_t set, const Phys::FourVector& p,
                  double weight) {
            worker.fill(handles_[set][kMass], p.m(), weight);
            worker.fill(handles_[set][kEnergy], p.e(), weight);
            worker.fill(handles_[set][kMomentum], p.p3mod(), weight);
            worker.fill(handles_[set][kTransverse], p.perp(), weight);
            worker.fill(handles_[set][kLongitudinal], p.pz(), weight);
            // A candidate exactly along the beam has infinite η. Dropping it from *this* histogram
            // is honest — an overflow bin would claim a value it does not have — and it is why the
            // η plot can hold fewer entries than the others.
            const double eta = p.eta();
            if (std::isfinite(eta)) worker.fill(handles_[set][kPseudorapidity], eta, weight);
        }

        Lambda::Cuts cuts_;
        Phys::Acceptance track_;
        std::size_t bins_ = 100;
        double mass_window_ = 0.4;
        double max_energy_ = 200.0;
        double max_momentum_ = 200.0;
        double max_transverse_ = 20.0;
        double max_eta_ = 8.0;
        std::size_t max_count_ = 50;

        double widths_[kPropertyCount] = {};
        Results::Handle handles_[Lambda::kSetCount][kPropertyCount] = {};
        Results::Handle counts_[Lambda::kSetCount] = {};
        Results::Handle events_ = 0;
    };

}  // namespace

HEKIT_MODULE("Lambda", LambdaModule)
