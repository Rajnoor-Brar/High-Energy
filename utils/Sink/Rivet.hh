#pragma once

// ── Sink/Rivet.hh ────────────────────────────────────────────────────────────
// Rivet in process (05 §5), serial or one handler per slot (05 §3). This is the change the whole
// rework is for: the legacy pipeline wrote HepMC3 into a FIFO and ran the `rivet` command on the
// other end, which cost a full serialisation of every event and made the two halves fail
// independently (00 §4.1, D4). The analysis now sees the same `GenEvent` the FIFO carried, without
// the FIFO.
//
// What this class is careful about, in the order it matters:
//
//   1. **A missing analysis fails before the first event.** Rivet's `addAnalysis` only *warns* when a
//      name is unknown, so a typo would otherwise cost a whole generation and then write an empty
//      YODA. The names are resolved in `prepare()`, which runs under `--check` too.
//   2. **Rivet initialises from the first event**, not from a beam declaration, so `init()` is called
//      once per handler, on that handler's first `GenEvent` (`setCheckBeams` then decides whether a
//      beam change is fatal).
//   3. **σ is set once, at the end, from the merged value** (D-Q1) with `isUserSupplied = true`, so
//      Rivet normalises to the number the run actually measured rather than to whatever the last
//      event's `GenCrossSection` happened to hold.
//   4. **Periodic dumps only for re-entrant analyses.** Rivet 4.1.3 skips `finalize` in a dump for a
//      non-re-entrant analysis (`AnalysisHandler.cc:700-705`), so the dump would be unscaled and
//      quietly wrong; `dump_every` is refused with a warning in that case.
//   5. **`Pythia8Plugins/RivetHooks.h` is not used**: its `onStat` hook can merge twice (05 §5).
//   6. **The `/RAW/` objects are written**, because `rivet-merge -e` re-runs `finalize` from them
//      (07 §3) and refuses a file without them.
//
// **Sharding, and when it is refused.** `AnalysisHandler` owns its own `ProjectionHandler`
// (`AnalysisHandler.hh:788`) and Rivet's logging is `thread_local`, so k handlers analysing k events
// at once is sound *in Rivet*. It is not sound in what the analyses call:
//
//   * FastJet here is built with `FASTJET_HAVE_LIMITED_THREAD_SAFETY` undefined, so its warning
//     registry, error state and area-generator seeds are unguarded globals;
//   * and SISCone is unsafe in **every** build — `SISConePlugin::{stored_plugin, stored_particles,
//     stored_siscone}` are process-wide statics mutated inside `run_clustering`, and
//     `siscone::local_ranlux_state` is a global RNG that its split-merge draws from. Two threads
//     clustering at once do not crash reliably; they quietly produce different jets.
//
// Whether an analysis clusters jets cannot be known before it runs — projections are declared inside
// `Analysis::init()`, which Rivet calls on the first event — so the question is split in two:
//
//   * **before any event**, and this is what `auto` uses: an analysis must be `Reentrant: true`, and
//     FastJet must be built thread-safe. Without that flag *no* analysis can be sharded, because any
//     of them may cluster and there is no way to ask yet. That is the case in this installation, so
//     `auto` is serial here and says so once;
//   * **right after `init()`**, and this is what an explicit `[run].mode = "sharded"` runs into: if
//     an analysis did declare a `FastJets`, the run stops. SISCone is unsafe even in a thread-safe
//     FastJet, and stopping is the only honest option — a jet race produces a plausible histogram
//     with the wrong numbers in it, which is worse than no histogram.

#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

#include "Rivet/Analysis.hh"          // AnalysisHandler only forward-declares it; reentrant() needs it
#include "Rivet/AnalysisHandler.hh"
#include "Rivet/AnalysisLoader.hh"
#include "Rivet/Projections/FastJets.hh"

#include "fastjet/config.h"           // FASTJET_HAVE_LIMITED_THREAD_SAFETY

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

        // Decided in `prepare()`, from what can be known before an event exists (see the header).
        Concurrency concurrency() const override {
            return reason_.empty() ? Concurrency::Sharded : Concurrency::Serial;
        }

        std::string serialReason() const override { return reason_; }

        // Before any event: load the analyses and refuse the ones that do not exist.
        void prepare() override {
            addSearchPaths();
            if (spec_.analyses.empty())
                throw Core::Error{Core::Exit::Config, "the rivet sink has no analyses"};
            handlers_.clear();
            initialised_.clear();
            handlers_.push_back(makeHandler());
            configureDumps();

            std::vector<std::string> blocking;
            for (const auto& analysis : handlers_.front()->analyses())
                if (!analysis->reentrant()) blocking.push_back(analysis->name());
            if (!blocking.empty())
                reason_ = joined(blocking) + " is not marked `Reentrant: true`, so per-worker "
                                             "handlers could not be merged (Rivet 4.1.3 calls the "
                                             "result unpredictable)";
#if !defined(FASTJET_HAVE_LIMITED_THREAD_SAFETY)
            else
                reason_ = "FastJet is built without FASTJET_HAVE_LIMITED_THREAD_SAFETY, and whether "
                          "an analysis clusters jets is only known once it has initialised, so no "
                          "analysis can be shared out safely";
#endif
            status_.log(Status::Level::Info, "rivet",
                        "loaded " + joined(handlers_.front()->analysisNames()));
        }

        // One handler per slot, all built here on the main thread: `AnalysisLoader` is a process-wide
        // registry and the `.info` files are read from disk, neither of which wants k threads.
        void shards(int count) override {
            if (handlers_.empty()) prepare();
            const std::size_t wanted = static_cast<std::size_t>(std::max(1, count));
            while (handlers_.size() < wanted) handlers_.push_back(makeHandler());
            if (wanted == 1) return;
            // A periodic dump writes one handler's objects, and one handler is now a fraction of the
            // run. Rather than a file that looks like a result and is a quarter of one, the dump is
            // dropped and said so; the final YODA is the merge of all of them and is unaffected.
            if (spec_.dump_every > 0) {
                handlers_.front()->setNoFinalizePeriod();
                status_.log(Status::Level::Warn, "rivet",
                            "dump_every ignored in sharded mode: a dump would hold one worker's "
                            "events, not the run's");
            }
            status_.log(Status::Level::Info, "rivet",
                        std::to_string(wanted) + " analysis handlers, merged at the end");
        }

        void start(const Core::Beams& beams, long long expected_events) override {
            (void)beams;             // Rivet takes the beams from the first event, not from us
            (void)expected_events;
            if (handlers_.empty()) prepare();
        }

        void event(Events::View& view) override {
            HepMC3::GenEvent* genEvent = view.hepmcOrNull();
            if (genEvent == nullptr)
                throw Core::Error{Core::Exit::Internal,
                                  "the Rivet sink was given an event with no HepMC record"};
            const std::size_t slot =
                handlers_.size() == 1 ? 0 : static_cast<std::size_t>(view.slot()) % handlers_.size();
            ::Rivet::AnalysisHandler& handler = *handlers_[slot];

            if (!initialised_[slot]) {
                // Rivet reads the beams, the weight names and the generator from the first event.
                // `init()` touches the analysis loader, reads `.info` files and books objects, so it
                // goes under one lock however many slots there are — it happens once per slot.
                std::lock_guard<std::mutex> guard(init_mutex_);
                if (!initialised_[slot]) {
                    handler.init(*genEvent);
                    if (handlers_.size() > 1) requireThreadSafeProjections(handler);
                    initialised_[slot] = 1;
                }
            }
            handler.analyze(*genEvent);
            analysed_.fetch_add(1, std::memory_order_relaxed);
        }

        void checkpoint(long long done) override { (void)done; }

        void finish(const Core::RunRecord& record) override {
            const long long analysed = analysed_.load(std::memory_order_relaxed);
            ::Rivet::AnalysisHandler* merged = mergeShards();
            if (merged == nullptr || analysed == 0) {
                // Nothing was analysed, so there is nothing to finalize — and calling finalize on an
                // uninitialised handler is undefined. An empty YODA would be worse than no file:
                // `hep` treats a missing output as "not run", which is the truth here.
                status_.log(Status::Level::Warn, "rivet",
                            "no events reached the analyses, so no YODA was written");
                return;
            }
            const std::pair<double, double> xsec = crossSection(record);
            merged->setCrossSection(xsec.first, xsec.second, /*isUserSupplied=*/true);
            merged->finalize();

            Results::Writer writer(output_dir_);
            // `includeraw = true` keeps Rivet's own `/RAW/` copies in the file. They are not
            // decoration: `rivet-merge -e` re-runs `finalize` from them, and without them it refuses
            // the file outright ("Missing cross-section for /RAW/_XSEC"), which would break the seed
            // replica merge of 07 §3. The legacy `rivet` command wrote them too, so this also keeps
            // the two pipelines' files comparable (P2-S06).
            const std::string written = writer.writeYoda(
                yoda_name_, merged->getYodaAOs(/*includeraw=*/true), record.stopped);
            outputs_.push_back(Output{"yoda", written, record.stopped});
            status_.log(Status::Level::Info, "rivet",
                        std::to_string(analysed) + " events analysed, wrote " + written);
        }

        std::vector<Output> outputs() const override { return outputs_; }

        long long analysed() const { return analysed_.load(std::memory_order_relaxed); }

        /// How many handlers this sink is holding, for the tests and the summary.
        std::size_t handlerCount() const { return handlers_.size(); }

      private:
        // Every handler is built the same way; the only thing that differs between them is which
        // events they see.
        std::unique_ptr<::Rivet::AnalysisHandler> makeHandler() {
            auto handler = std::make_unique<::Rivet::AnalysisHandler>();
            handler->setCheckBeams(spec_.check_beams);
            if (spec_.weights == "nominal") handler->skipMultiWeights(true);
            for (const std::string& requested : spec_.analyses) {
                const std::string base = requested.substr(0, requested.find(':'));
                if (::Rivet::AnalysisLoader::getAnalysis(base) == nullptr)
                    throw Core::Error{Core::Exit::Config, "unknown Rivet analysis: " + base,
                                      "it is not in RIVET_ANALYSIS_PATH" +
                                          (spec_.paths.empty()
                                               ? ""
                                               : " or in " + joined(spec_.paths)) +
                                          "; `hep doctor` lists what is visible"};
                handler->addAnalysis(requested);
            }
            // Defensive: `addAnalysis` can still drop a name it does not like (a bad option value),
            // and an empty handler would write an empty YODA after a full generation.
            if (handler->analysisNames().size() != spec_.analyses.size())
                throw Core::Error{Core::Exit::Config,
                                  "Rivet loaded " + std::to_string(handler->analysisNames().size()) +
                                      " of " + std::to_string(spec_.analyses.size()) + " analyses",
                                  "the log above names the one it refused; an option value is the "
                                  "usual cause"};
            initialised_.push_back(0);
            return handler;
        }

        // Fold the other slots into the first initialised one. `AnalysisHandler::merge` adds the
        // event counters, the σ error accumulator and every analysis object path by path, and leaves
        // `finalize()` to the caller — which is exactly the order this sink wants (D-Q1: σ is applied
        // once, to the merged total).
        ::Rivet::AnalysisHandler* mergeShards() {
            ::Rivet::AnalysisHandler* first = nullptr;
            for (std::size_t slot = 0; slot < handlers_.size(); ++slot) {
                if (!initialised_[slot]) continue;       // a slot that never saw an event
                if (first == nullptr) {
                    first = handlers_[slot].get();
                    continue;
                }
                first->merge(*handlers_[slot]);
            }
            return first;
        }

        // Called once per handler, right after `init()`, and only when there is more than one: the
        // projections exist only from that moment, and a jet clustering race is silent (see the
        // header note).
        void requireThreadSafeProjections(const ::Rivet::AnalysisHandler& handler) const {
            std::vector<std::string> clustering;
            for (const auto& analysis : handler.analyses())
                for (const auto& projection : analysis->getProjections())
                    if (dynamic_cast<const ::Rivet::FastJets*>(projection) != nullptr) {
                        clustering.push_back(analysis->name());
                        break;
                    }
            if (clustering.empty()) return;
            throw Core::Error{
                Core::Exit::Sink,
                joined(clustering) + " clusters jets, which cannot be done from several threads",
#if defined(FASTJET_HAVE_LIMITED_THREAD_SAFETY)
                "SISCone keeps its clustering cache and its RNG in process-wide statics "
                "(SISConePlugin::stored_siscone, siscone::local_ranlux_state), so concurrent "
                "clustering silently changes the jets. Use [run].mode = \"serial\"."
#else
                "this FastJet is built without FASTJET_HAVE_LIMITED_THREAD_SAFETY, and SISCone keeps "
                "its clustering cache and RNG in process-wide statics whatever the build: "
                "concurrent clustering silently changes the jets. Use [run].mode = \"serial\", or "
                "\"auto\", which already does"
#endif
            };
        }

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
        // unfinalized objects, which look like a result and are not one. Only the first handler
        // dumps: a per-slot dump would be a fraction of the run under the same name.
        void configureDumps() {
            if (spec_.dump_every <= 0) return;
            std::vector<std::string> blocking;
            for (const auto& analysis : handlers_.front()->analyses())
                if (!analysis->reentrant()) blocking.push_back(analysis->name());
            if (!blocking.empty()) {
                status_.log(Status::Level::Warn, "rivet",
                            "dump_every ignored: " + joined(blocking) +
                                " is not re-entrant, so a periodic dump would be unfinalized "
                                "(Rivet 4.1.3 skips finalize in that case)");
                return;
            }
            handlers_.front()->setFinalizePeriod(
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
        std::vector<std::unique_ptr<::Rivet::AnalysisHandler>> handlers_;
        // `char` rather than `bool`: the vector is written from several threads (each at its own
        // index, under the lock) and `std::vector<bool>` packs bits, so neighbouring slots would
        // share a word.
        std::vector<char> initialised_;
        std::mutex init_mutex_;
        std::atomic<long long> analysed_{0};
        std::string reason_;
        std::vector<Output> outputs_;
    };

}  // namespace Sink
