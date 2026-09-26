#pragma once

// ── Sink/Modules.hh ──────────────────────────────────────────────────────────
// User C++ analysis, booking YODA into the same file as Rivet's (05 §5).
//
// This is the sink that can actually be sharded here. `Sink::Rivet` cannot, because its analyses
// cluster jets and SISCone keeps its cache in process-wide statics (00/B31); a module holds nothing
// but its own YODA objects, one set per worker, so k workers fill k clones and the clones are added
// at the end. The equality that makes that sound is the one P6-S01 arrived at: **fills add**, and a
// `Results::Worker` can do nothing but fill.
//
// The objects go into the **same `analysis.yoda`** as Rivet's, under `/<module>/<name>`, so
// `rivet-mkhtml` and `hep plot` treat them alike and nothing downstream has to learn a second format
// (07 §1). `Results::Writer` does the writing; this sink only hands over the objects.

#include <atomic>
#include <memory>
#include <string>
#include <vector>

#include "YODA/AnalysisObject.h"

#include "Core.hh"
#include "Events.hh"
#include "Module/Loader.hh"
#include "Module/Types.hh"
#include "Results.hh"
#include "Results/Booker.hh"
#include "Results/Merge.hh"
#include "Results/Worker.hh"
#include "Sink/Types.hh"
#include "Status.hh"

namespace Sink {

    class Modules : public Sink {
      public:
        Modules(std::vector<Core::SinkSpec> specs, std::vector<std::string> paths,
                Status::Writer& status)
            : specs_(std::move(specs)), paths_(std::move(paths)), status_(status) {}

        std::string name() const override { return "modules"; }

        Needs needs() const override {
            Needs wanted;
            for (const auto& loaded : loaded_) {
                const Needs module_needs = loaded.module->needs();
                wanted.hepmc = wanted.hepmc || module_needs.hepmc;
                wanted.pythia = wanted.pythia || module_needs.pythia;
            }
            return loaded_.empty() ? Needs{false, true} : wanted;
        }

        // Nothing here is shared between workers, so there is nothing to lock (05 §3) — unless a
        // module says otherwise. `Phys::cluster` is the case that matters: FastJet keeps clustering
        // state in process-wide statics, so a module that makes jets races in exactly the way that
        // stopped the Rivet sink from sharding (00/B31). One mutex around this sink is enough;
        // making the whole run serial would give up parallel generation for one sink's sake.
        Concurrency concurrency() const override {
            return threadSafe() ? Concurrency::Sharded : Concurrency::Locked;
        }

        bool threadSafe() const {
            for (const Loaded& loaded : loaded_)
                if (!loaded.module->threadSafe()) return false;
            return true;
        }

        // Load, configure and book — all of it before the first event, so a missing library or a
        // duplicate object name costs a second rather than a run (06 §3.3).
        void prepare() override {
            if (!loaded_.empty()) return;
            for (const Core::SinkSpec& spec : specs_) {
                Loaded loaded;
                loaded.name = spec.name;
                loaded.module = Module::load(spec.name, paths_);
                loaded.module->configure(spec.options);
                loaded.booker = std::make_unique<Results::Booker>("/" + spec.name);
                loaded.module->book(*loaded.booker);
                if (loaded.booker->declarations().empty())
                    status_.log(Status::Level::Warn, "modules",
                                spec.name + " booked no objects, so it will produce nothing");
                loaded_.push_back(std::move(loaded));
            }
            status_.log(Status::Level::Info, "modules", "loaded " + joined());
            std::string unsafe;
            for (const Loaded& loaded : loaded_)
                if (!loaded.module->threadSafe())
                    unsafe += (unsafe.empty() ? "" : ", ") + loaded.name;
            if (!unsafe.empty())
                status_.log(Status::Level::Info, "modules",
                            unsafe + " is not thread-safe, so modules run under one lock");
        }

        /// One set of objects per worker; built here, on the main thread, before any event.
        void shards(int count) override {
            if (loaded_.empty()) prepare();
            const std::size_t wanted = static_cast<std::size_t>(std::max(1, count));
            for (Loaded& loaded : loaded_) {
                loaded.workers.clear();
                for (std::size_t slot = 0; slot < wanted; ++slot)
                    loaded.workers.push_back(Results::clonesOf(*loaded.booker));
            }
            slots_ = wanted;
        }

        void start(const Core::Beams& beams, long long expected_events) override {
            (void)beams;
            (void)expected_events;
            if (loaded_.empty()) prepare();
            if (slots_ == 0) shards(1);
        }

        void event(Events::View& view) override {
            const std::size_t slot =
                slots_ <= 1 ? 0 : static_cast<std::size_t>(view.slot()) % slots_;
            // Σw is the denominator of every normalisation, and only this sink is in a position to
            // count it per event; atomic because k workers are here at once.
            const double weight = view.weights().nominal();
            double seen = sum_of_weights_.load(std::memory_order_relaxed);
            while (!sum_of_weights_.compare_exchange_weak(seen, seen + weight)) {}
            for (Loaded& loaded : loaded_) {
                Results::Worker worker(loaded.workers[slot], static_cast<int>(slot));
                loaded.module->process(view, worker);
            }
        }

        // Merge, then finalize, then hand the objects over. In that order, and only once: σ and ΣW
        // are not known before it, and `finalize` is the only place scaling is allowed (05 §5).
        void finish(const Core::RunRecord& record) override {
            for (Loaded& loaded : loaded_) {
                if (loaded.workers.empty()) continue;
                for (std::size_t slot = 1; slot < loaded.workers.size(); ++slot)
                    Results::merge(loaded.workers[0], loaded.workers[slot]);
                Results::Final results(loaded.workers[0], record.xsec_pb,
                                       sum_of_weights_.load(), record.accepted);
                loaded.module->finalize(results);
            }
            const std::vector<std::shared_ptr<YODA::AnalysisObject>> found = objects();
            status_.log(Status::Level::Info, "modules",
                        joined() + ": " + std::to_string(found.size()) + " objects");

            // Normally the Rivet sink writes them, so they land in the *same* `analysis.yoda`
            // (07 §1). With no Rivet sink in the run there is nobody to hand them to, so this
            // writes the file itself rather than dropping them.
            if (writes_own_ && !found.empty()) {
                Results::Writer writer(output_dir_);
                const std::string written =
                    writer.writeYoda(yoda_name_, found, record.stopped);
                outputs_.push_back(Output{"yoda", written, record.stopped});
                status_.log(Status::Level::Info, "modules", "wrote " + written);
            }
        }

        std::vector<Output> outputs() const override { return outputs_; }

        /// Each module's inputs, keyed by module so two modules cannot collide.
        std::vector<std::pair<std::string, std::string>> provenance() const override {
            std::vector<std::pair<std::string, std::string>> found;
            for (const Loaded& loaded : loaded_)
                for (const auto& entry : loaded.module->provenance())
                    found.emplace_back(loaded.name + "." + entry.first, entry.second);
            return found;
        }

        /// Where to write when there is no Rivet sink to hand the objects to.
        void writesOwnFile(std::string output_dir, std::string yoda_name) {
            writes_own_ = true;
            output_dir_ = std::move(output_dir);
            yoda_name_ = std::move(yoda_name);
        }

        /// The Rivet sink is taking them, so do not write a second file.
        void handsOver() { writes_own_ = false; }

        /// The merged, finalized objects, for `Results::Writer` to put beside Rivet's (07 §1).
        ///
        /// Shared pointers with **no deleter**: the writer wants the same type Rivet's handler
        /// gives it, and this sink owns the objects. Handing over an owning pointer would mean two
        /// owners and a double free the moment the writer's vector went out of scope.
        std::vector<std::shared_ptr<YODA::AnalysisObject>> objects() const {
            std::vector<std::shared_ptr<YODA::AnalysisObject>> found;
            for (const Loaded& loaded : loaded_) {
                if (loaded.workers.empty()) continue;
                for (const Results::Slot& slot : loaded.workers[0])
                    if (YODA::AnalysisObject* object = slot.object())
                        found.emplace_back(object, [](YODA::AnalysisObject*) {});
            }
            return found;
        }

        bool empty() const { return loaded_.empty(); }

      private:
        struct Loaded {
            std::string name;
            std::unique_ptr<Module::Base> module;
            std::unique_ptr<Results::Booker> booker;
            std::vector<std::vector<Results::Slot>> workers;   // one per slot
        };

        std::string joined() const {
            std::string out;
            for (const Loaded& loaded : loaded_) out += (out.empty() ? "" : ", ") + loaded.name;
            return out;
        }

        std::vector<Core::SinkSpec> specs_;
        std::vector<std::string> paths_;
        Status::Writer& status_;
        std::vector<Loaded> loaded_;
        std::size_t slots_ = 0;
        std::atomic<double> sum_of_weights_{0.0};
        bool writes_own_ = false;
        std::string output_dir_;
        std::string yoda_name_;
        std::vector<Output> outputs_;
    };

}  // namespace Sink
