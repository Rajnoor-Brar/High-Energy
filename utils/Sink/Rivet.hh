#pragma once

// ── Sink/Rivet.hh ────────────────────────────────────────────────────────────
// Rivet in process (05 §5). This is the change the whole rework is for: the legacy pipeline wrote
// HepMC3 into a FIFO and ran the `rivet` command on the other end, which cost a full serialisation of
// every event and made the two halves fail independently (00 §4.1, D4). The analysis now sees the same
// `GenEvent` the FIFO carried, without the FIFO.
//
// What this class is careful about, in the order it matters:
//
//   1. **A missing analysis fails before the first event.** Rivet's `addAnalysis` only *warns* when a
//      name is unknown, so a typo would otherwise cost a whole generation and then write an empty
//      YODA. The names are resolved in `prepare()`, which runs under `--check` too.
//   2. **Rivet initialises from the first event**, not from a beam declaration, so `init()` is called
//      once, on the first `GenEvent` (`setCheckBeams` then decides whether a beam change is fatal).
//   3. **σ is set once, at the end, from the merged value** (D-Q1) with `isUserSupplied = true`, so
//      Rivet normalises to the number the run actually measured rather than to whatever the last
//      event's `GenCrossSection` happened to hold.
//   4. **Periodic dumps only for re-entrant analyses.** Rivet 4.1.3 skips `finalize` in a dump for a
//      non-re-entrant analysis (`AnalysisHandler.cc:700-705`), so the dump would be unscaled and
//      quietly wrong; `dump_every` is refused with a warning in that case.
//   5. **`Pythia8Plugins/RivetHooks.h` is not used**: its `onStat` hook can merge twice (05 §5).
//   6. **The `/RAW/` objects are written**, because `rivet-merge -e` re-runs `finalize` from them
//      (07 §3) and refuses a file without them.

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "Rivet/Analysis.hh"          // AnalysisHandler only forward-declares it; reentrant() needs it
#include "Rivet/AnalysisHandler.hh"
#include "Rivet/AnalysisLoader.hh"

#include "Core.hh"
#include "Events.hh"
#include "Results.hh"
#include "Sink/Types.hh"
#include "Status.hh"

namespace Sink {

    // The class is `Sink::Rivet`, as 05 §5 names it, so every mention of the framework inside is
    // spelled `::Rivet::` — the class name shadows the namespace in here (13 §3 has the same problem
    // with Delphes' global `Event`, solved the same way).
    class Rivet : public Sink {
      public:
        Rivet(const Core::SinkSpec& spec, std::string output_dir, std::string yoda_name,
                  Status::Writer& status)
            : spec_(spec), output_dir_(std::move(output_dir)), yoda_name_(std::move(yoda_name)),
              status_(status) {}

        std::string name() const override { return "rivet"; }

        // Rivet analyses take a HepMC event and nothing else; a run whose only sink is this one
        // therefore pays for exactly one conversion per event (05 §1).
        Needs needs() const override { return Needs{/*pythia=*/false, /*hepmc=*/true}; }

        // Serial for now. P6-S01 adds the sharded mode, which needs one handler per worker and a
        // merge at the end — the reason `AnalysisHandler::merge` exists.
        Concurrency concurrency() const override { return Concurrency::Serial; }

        // Before any event: load the analyses and refuse the ones that do not exist.
        void prepare() override {
            addSearchPaths();
            handler_ = std::make_unique<::Rivet::AnalysisHandler>();
            handler_->setCheckBeams(spec_.check_beams);
            if (spec_.weights == "nominal") handler_->skipMultiWeights(true);

            if (spec_.analyses.empty())
                throw Core::Error{Core::Exit::Config, "the rivet sink has no analyses"};
            for (const std::string& requested : spec_.analyses) {
                const std::string base = requested.substr(0, requested.find(':'));
                if (::Rivet::AnalysisLoader::getAnalysis(base) == nullptr)
                    throw Core::Error{Core::Exit::Config, "unknown Rivet analysis: " + base,
                                      "it is not in RIVET_ANALYSIS_PATH" +
                                          (spec_.paths.empty()
                                               ? ""
                                               : " or in " + joined(spec_.paths)) +
                                          "; `hep doctor` lists what is visible"};
                handler_->addAnalysis(requested);
            }
            // Defensive: `addAnalysis` can still drop a name it does not like (a bad option value),
            // and an empty handler would write an empty YODA after a full generation.
            if (handler_->analysisNames().size() != spec_.analyses.size())
                throw Core::Error{Core::Exit::Config,
                                  "Rivet loaded " + std::to_string(handler_->analysisNames().size()) +
                                      " of " + std::to_string(spec_.analyses.size()) + " analyses",
                                  "the log above names the one it refused; an option value is the "
                                  "usual cause"};
            configureDumps();
            status_.log(Status::Level::Info, "rivet",
                        "loaded " + joined(handler_->analysisNames()));
        }

        void start(const Core::Beams& beams, long long expected_events) override {
            (void)beams;             // Rivet takes the beams from the first event, not from us
            (void)expected_events;
            if (handler_ == nullptr) prepare();
        }

        void event(Events::View& view) override {
            HepMC3::GenEvent* genEvent = view.hepmcOrNull();
            if (genEvent == nullptr)
                throw Core::Error{Core::Exit::Internal,
                                  "the Rivet sink was given an event with no HepMC record"};
            if (!initialised_) {
                // Rivet reads the beams, the weight names and the generator from the first event.
                handler_->init(*genEvent);
                initialised_ = true;
            }
            handler_->analyze(*genEvent);
            analysed_ += 1;
        }

        void checkpoint(long long done) override { (void)done; }

        void finish(const Core::RunRecord& record) override {
            if (!initialised_ || analysed_ == 0) {
                // Nothing was analysed, so there is nothing to finalize — and calling finalize on an
                // uninitialised handler is undefined. An empty YODA would be worse than no file:
                // `hep` treats a missing output as "not run", which is the truth here.
                status_.log(Status::Level::Warn, "rivet",
                            "no events reached the analyses, so no YODA was written");
                return;
            }
            const std::pair<double, double> xsec = crossSection(record);
            handler_->setCrossSection(xsec.first, xsec.second, /*isUserSupplied=*/true);
            handler_->finalize();

            Results::Writer writer(output_dir_);
            // `includeraw = true` keeps Rivet's own `/RAW/` copies in the file. They are not
            // decoration: `rivet-merge -e` re-runs `finalize` from them, and without them it refuses
            // the file outright ("Missing cross-section for /RAW/_XSEC"), which would break the seed
            // replica merge of 07 §3. The legacy `rivet` command wrote them too, so this also keeps
            // the two pipelines' files comparable (P2-S06).
            const std::string written = writer.writeYoda(
                yoda_name_, handler_->getYodaAOs(/*includeraw=*/true), record.stopped);
            outputs_.push_back(Output{"yoda", written, record.stopped});
            status_.log(Status::Level::Info, "rivet",
                        std::to_string(analysed_) + " events analysed, wrote " + written);
        }

        std::vector<Output> outputs() const override { return outputs_; }

        long long analysed() const { return analysed_; }

      private:
        // `[[sink]].paths` are prepended to RIVET_ANALYSIS_PATH, which is how the legacy pipeline
        // found `photo_eic` (`tools/rivpyth:252`) and what `rivet-build` produces plugins for.
        void addSearchPaths() const {
            if (spec_.paths.empty()) return;
            std::string value;
            for (const std::string& entry : spec_.paths) value += entry + ":";
            if (const char* inherited = std::getenv("RIVET_ANALYSIS_PATH"))
                value += inherited;
            else if (!value.empty())
                value.pop_back();
            ::setenv("RIVET_ANALYSIS_PATH", value.c_str(), /*overwrite=*/1);
        }

        // A dump is only meaningful for a re-entrant analysis; for the others Rivet writes the
        // unfinalized objects, which look like a result and are not one.
        void configureDumps() {
            if (spec_.dump_every <= 0) return;
            std::vector<std::string> blocking;
            for (const auto& analysis : handler_->analyses())
                if (!analysis->reentrant()) blocking.push_back(analysis->name());
            if (!blocking.empty()) {
                status_.log(Status::Level::Warn, "rivet",
                            "dump_every ignored: " + joined(blocking) +
                                " is not re-entrant, so a periodic dump would be unfinalized "
                                "(Rivet 4.1.3 skips finalize in that case)");
                return;
            }
            handler_->setFinalizePeriod(
                (std::filesystem::path(output_dir_) / Results::marked(yoda_name_, "dump")).string(),
                static_cast<int>(spec_.dump_every));
        }

        // "generator" means the σ the run measured (the default); a number in the spec overrides it,
        // which is what a fixed-σ normalisation needs.
        std::pair<double, double> crossSection(const Core::RunRecord& record) const {
            if (spec_.xsec.empty() || spec_.xsec == "generator")
                return {record.xsec_pb, record.xsec_error_pb};
            try {
                return {std::stod(spec_.xsec), 0.0};
            } catch (const std::exception&) {
                throw Core::Error{Core::Exit::Config,
                                  "[[sink]].xsec is neither 'generator' nor a number: " + spec_.xsec};
            }
        }

        static std::string joined(const std::vector<std::string>& values) {
            std::string out;
            for (const std::string& value : values) out += (out.empty() ? "" : ", ") + value;
            return out;
        }

        Core::SinkSpec spec_;
        std::string output_dir_;
        std::string yoda_name_;
        Status::Writer& status_;
        std::unique_ptr<::Rivet::AnalysisHandler> handler_;
        bool initialised_ = false;
        long long analysed_ = 0;
        std::vector<Output> outputs_;
    };

}  // namespace Sink
