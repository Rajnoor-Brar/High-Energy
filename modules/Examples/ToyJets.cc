// ── modules/Examples/ToyJets.cc ──────────────────────────────────────────────
// The smallest useful module, and the one the tests measure (05 §5, P8-S01; `Phys`, P8-S02).
//
// It exists to show the four verbs and the scaling contract in something short enough to read
// whole. The physics is deliberately trivial — final-state multiplicity, pT, η, and jets — because
// the point being made is about *where* things happen, not about what is being measured:
//
//   * `book` declares, once, before any event. A duplicate name or an inverted range is caught here.
//   * `process` fills **this worker's** clones with the event's raw weight. There is no `scale()`
//     to call, which is the contract rather than a convention.
//   * `finalize` runs once, after every worker's clones have been added together, with σ and ΣW
//     known. It is the only place scaling exists.
//
// That last point is what the "exact totals at 1, 4 and 20 threads" test checks: fills add, so k
// workers give the same integral as one.
//
// **And it is where `Phys` earns its place.** This file used to carry its own final-state loop, its
// own pT, and a hand-written pseudorapidity with a divide-by-zero guard around a particle travelling
// along the beam. All three are one `Phys::Acceptance` now, and the jets — which the module was
// named after and never had — are two lines. The physics is unchanged, which is what
// `tests/integration/test_modules.py` re-measures.
//
// **It clusters jets, so it says `threadSafe() == false`.** FastJet keeps clustering state in
// process-wide statics (00/B31), which is the same reason the Rivet analyzer refuses to shard. Saying so
// costs one mutex around this analyzer; generation stays parallel, and the alternative is a race that
// changes the jets rather than crashing.

#include "ML.hh"
#include "Module/Registry.hh"
#include "Module/Types.hh"
#include "Phys.hh"

#include "HepMC3/GenEvent.h"

#include <memory>

namespace {

    class ToyJets : public Module::Base {
      public:
        void configure(const Core::Options& options) override {
            // A module's options are its own invention; `Core::Options` only says what was expected
            // when a value is not a number.
            acceptance_.pt_min = options.number("pt_min", 0.5);
            acceptance_.eta_max = options.number("eta_max", 5.0);
            jet_pt_min_ = options.number("jet_pt_min", 5.0);
            jets_ = Phys::jetDefinition(options.text("jets", "antikt:0.4"));

            // `model = "..."` turns on the ML half; with no model this is an ordinary module and
            // nothing below it runs. The schema is named next to the model it belongs to, and
            // `matches` checks the two agree now rather than after a generation (05 §6).
            const std::string model = options.text("model", "");
            if (!model.empty()) {
#if defined(HEKIT_WITH_ONNX)
                features_ = ML::Features({"pt", "eta", "phi", "mass"});
                // Rebuilt *after* the schema, not before: a `Row` is sized and named by the schema
                // it was made from, so one made against the default would quietly survive a schema
                // of the same width and be wrong for any other.
                row_ = features_.row();
                model_ = std::make_unique<ML::OnnxModel>(model);
                features_.matches(*model_);
#else
                throw Core::Error{Core::Exit::Config,
                                  "this build has no ONNX Runtime, so ToyJets cannot load " + model,
                                  "configure with -DHEKIT_WITH_ONNX=ON"};
#endif
            }
        }

        void book(Results::Booker& booker) override {
            multiplicity_ = booker.histo1D("multiplicity", 50, 0.0, 200.0,
                                           "final-state particles per event");
            pt_ = booker.histo1D("pt", 40, 0.0, 20.0, "particle $p_T$ [GeV]");
            eta_ = booker.histo1D("eta", 40, -5.0, 5.0, "particle $\\eta$");
            pt_vs_eta_ = booker.profile1D("pt_vs_eta", 20, -5.0, 5.0,
                                          "mean $p_T$ against $\\eta$");
            jet_count_ = booker.histo1D("jets", 10, -0.5, 9.5, "jets per event");
            jet_pt_ = booker.histo1D("jet_pt", 40, 0.0, 40.0, "jet $E_T$ [GeV]");
            counted_ = booker.counter("events", "events this module saw");
#if defined(HEKIT_WITH_ONNX)
            // Booked only when there is a model, so a run without one writes no empty histogram.
            if (model_) score_ = booker.histo1D("score", 20, 0.0, 1.0, "network score per jet");
#endif
        }

        void process(Events::View& view, Results::Worker& worker) override {
            const HepMC3::GenEvent* event = view.hepmcOrNull();
            if (event == nullptr) return;
            const double weight = view.weights().nominal();

            // Status 1, inside the acceptance. A particle exactly along the beam has infinite η and
            // fails the |η| cut, which is the honest answer — it is not in the detector either.
            const Phys::Particles kept = Phys::finalState(*event, acceptance_);
            for (const Phys::Particle& particle : kept) {
                const Phys::FourVector& momentum = particle->momentum();
                worker.fill(pt_, momentum.perp(), weight);
                worker.fill(eta_, momentum.eta(), weight);
                worker.fill(pt_vs_eta_, momentum.eta(), momentum.perp(), weight);
            }
            worker.fill(multiplicity_, static_cast<double>(kept.size()), weight);

            const std::vector<Phys::FourVector> jets =
                Phys::cluster(Phys::momenta(kept), jets_, jet_pt_min_);
            worker.fill(jet_count_, static_cast<double>(jets.size()), weight);
            for (const Phys::FourVector& jet : jets) worker.fill(jet_pt_, jet.perp(), weight);

#if defined(HEKIT_WITH_ONNX)
            if (model_) {
                // `scratch_` and `row_` are **one per module**, which is only safe because this
                // module already declares `threadSafe() == false` for the clustering above, so the
                // analyzer runs it under one lock. A module without that declaration would have to keep
                // a `Scratch` per worker — which is exactly what `ML::Scratch` is for, and what
                // `tests/cxx/test_ml.cc` runs 20 of.
                for (const Phys::FourVector& jet : jets) {
                    row_.clear();
                    row_.set("pt", jet.perp());
                    row_.set("eta", std::isfinite(jet.eta()) ? jet.eta() : 0.0);
                    row_.set("phi", jet.phi());
                    row_.set("mass", jet.m());
                    const ML::Floats out = model_->run(row_.values(), scratch_);
                    worker.fill(score_, out[0], weight);
                }
            }
#endif

            worker.count(counted_, weight);
        }

        void finalize(Results::Final& results) override {
            // σ / Σw turns a weight sum into a cross-section. The only scaling in the module, and
            // the only place it could be.
            results.normalise(multiplicity_);
            results.normalise(pt_);
            results.normalise(eta_);
            results.normalise(jet_count_);
            results.normalise(jet_pt_);
#if defined(HEKIT_WITH_ONNX)
            if (model_) results.normalise(score_);
#endif
            // A profile is a *mean*, so scaling it would be wrong: it is already per-entry.
        }

        /// Which weights answered. A hash nothing writes down is no better than no hash (05 §6).
        std::vector<std::pair<std::string, std::string>> provenance() const override {
#if defined(HEKIT_WITH_ONNX)
            if (model_)
                return {{"model", model_->path()}, {"model_sha256", model_->sha256()}};
#endif
            return {};
        }

        /// See the header note: clustering jets is not something two threads may do at once.
        bool threadSafe() const override { return false; }

      private:
        Phys::Acceptance acceptance_;
        double jet_pt_min_ = 5.0;
        fastjet::JetDefinition jets_{fastjet::antikt_algorithm, 0.4};
        Results::Handle multiplicity_ = 0;
        Results::Handle pt_ = 0;
        Results::Handle eta_ = 0;
        Results::Handle pt_vs_eta_ = 0;
        Results::Handle jet_count_ = 0;
        Results::Handle jet_pt_ = 0;
        Results::Handle counted_ = 0;
#if defined(HEKIT_WITH_ONNX)
        ML::Features features_{std::vector<std::string>{"pt", "eta", "phi", "mass"}};
        ML::Row row_{features_};
        std::unique_ptr<ML::OnnxModel> model_;
        mutable ML::Scratch scratch_;
        Results::Handle score_ = 0;
#endif
    };

}  // namespace

HEKIT_MODULE("ToyJets", ToyJets)
