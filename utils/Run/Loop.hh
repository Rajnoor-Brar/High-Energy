#pragma once

// ── Run/Loop.hh ──────────────────────────────────────────────────────────────
// Source → sinks, in chunks, with a stop that works (05 §3).
//
// The shape of the loop follows what P2-S02 measured: `PythiaParallel::run` cannot be interrupted from
// its callback, so the only place to stop, checkpoint or dump is a chunk boundary, and a chunk that is
// a multiple of the thread count keeps the event set identical to an unchunked run (D-Q2).
//
// The loop owns the order of events in a run's life, and nothing else:
//   configure → prepare sinks → pick mode → init → start sinks →
//   [chunk: events → checkpoint → stop?] → finish sinks → summary.
//
// The sinks are prepared *before* the generator initialises, because the mode depends on what they
// say about themselves and because an analysis that does not exist should cost a second rather than
// a Pythia init (05 §5).
//
// **Picking the mode** (05 §3). `serial` calls every sink on the event's own thread, one at a time.
// `sharded` lets k events be in flight at once: a `Sharded` sink holds one instance per slot and is
// called without a lock, and anything else goes through one mutex. `auto` — the default — chooses
// sharded only when there is more than one thread, at least one sink is shardable, and no sink
// objects; otherwise serial, and it says which sink asked for it.
//
// Every failure becomes a `Core::Error` with its own exit code, so `main` stays five lines.

#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "Core.hh"
#include "Events.hh"
#include "Results.hh"
#include "Run/Types.hh"
#include "Sink.hh"
#include "Source.hh"
#include "Status.hh"

namespace Run {

    class Loop {
      public:
        Loop(const Core::Spec& spec, Status::Writer& status, Status::Heartbeat& heartbeat)
            : spec_(spec), status_(status), heartbeat_(heartbeat) {}

        void add(std::unique_ptr<Sink::Sink> sink) { sinks_.push_back(std::move(sink)); }

        /// The source to run. Set before `prepare()`; a generator or a replay, the loop cannot tell
        /// (05 §1, 11 §4).
        void source(std::unique_ptr<Source::Base> source) { source_ = std::move(source); }

        // Everything up to (but not including) the first event. `--check` stops here (06 §3.3), so
        // everything that can be checked without generating belongs in this function: a card Pythia
        // refuses, a physics point that cannot initialise, an analysis that does not exist.
        void prepare() {
            if (source_ == nullptr) source_ = std::make_unique<Source::Pythia>(spec_, status_);
            status_.phase("configure", source_->kind() == "pythia"
                                           ? std::to_string(spec_.cards.size()) + " cards"
                                           : source_->kind());
            source_->configure();
            // Before the generator, not after: a sink loads its analyses and libraries here, so a
            // typo costs a second instead of a Pythia init (05 §5) — and the mode below is decided
            // from what the sinks then say about themselves.
            for (const auto& sink : sinks_) sink->prepare();
            mode_ = decideMode();
            source_->async(mode_ == "sharded");

            status_.phase("init");
            source_->initialise();
            slots_ = std::max(1, source_->slots());
            if (mode_ == "sharded" && slots_ == 1) mode_ = "serial";   // nothing to share out
            for (const auto& sink : sinks_) sink->shards(mode_ == "sharded" ? slots_ : 1);
#if defined(HEKIT_WITH_HEPMC)
            converters_ = std::vector<Events::Converter>(static_cast<std::size_t>(slots_));
#endif
            const Core::Beams& beams = source_->beams();
            std::vector<std::string> names;
            for (const auto& sink : sinks_) names.push_back(sink->name());
            status_.init(beams.ids, beams.energies, beams.sqrtS, source_->threads(), mode_, names);
            prepared_ = true;
        }

        /// The mode this run settled on, for the tests and the summary.
        const std::string& mode() const { return mode_; }

        Result run() {
            if (!prepared_) prepare();
            const Core::Steady::time_point started = Core::tick();
            started_at_ = Core::timestamp();
            const Core::Beams& beams = source_->beams();
            for (const auto& sink : sinks_) sink->start(beams, spec_.events);

            needs_hepmc_ = false;
            bool all_sharded = true;
            for (const auto& sink : sinks_) {
                needs_hepmc_ = needs_hepmc_ || sink->needs().hepmc;
                all_sharded = all_sharded && sink->concurrency() == Sink::Concurrency::Sharded;
            }
            // The lock is only taken when it can matter: several slots, and something to protect.
            shared_ = mode_ == "sharded" && slots_ > 1 && (!all_sharded || hook_ != nullptr);

            status_.phase("generate", std::to_string(spec_.events) + " events");
            heartbeat_.start();

            Result result;
            result.threads = source_->threads();
            result.chunk = source_->chunkSize(chunkTarget());
            const Core::Counts counts = source_->run(
                spec_.events, result.chunk,
                [&](Events::View& view) { consume(view); },
                [&] { return Core::Signals::stopRequested(); },
                [&](std::int64_t done) { atChunkEnd(done); });

            heartbeat_.stop();
            // A run shorter than one heartbeat interval would otherwise report no progress at all,
            // leaving a reader at 0 %. The final count is always sent.
            Status::Progress progress;
            progress.done = counts.accepted;
            progress.total = spec_.events;
            progress.rate = Core::since(started) > 0.0
                                ? static_cast<double>(counts.accepted) / Core::since(started)
                                : 0.0;
            progress.workers = source_->workers();
            status_.progress(progress, /*force=*/true);
            result.counts = counts;
            result.stopped = Core::Signals::stopRequested();
            result.wall_seconds = Core::since(started);
            result.seeds = source_->instanceSeeds();

            const Source::Xsec xsec = source_->xsec();
            result.xsec_pb = xsec.value_pb;
            result.xsec_error_pb = xsec.error_pb;
            result.xsec_known = xsec.known;
            if (xsec.known) status_.xsec(xsec.value_pb, xsec.error_pb, /*final=*/true);
            source_->reportWarnings(status_);

            status_.phase("finish", result.stopped ? "stopped: writing partial outputs" : "");
            const Core::RunRecord record = recordOf(result, started);
            for (const auto& sink : sinks_) {
                sink->finish(record);
                for (const Sink::Output& output : sink->outputs()) result.outputs.push_back(output);
            }
            // Written last, because it names what the sinks produced. `hekit.prov` folds it into
            // provenance.json (07 §2); it is not provenance itself.
            result.summary_path =
                Results::Writer(spec_.output_dir)
                    .writeText(spec_.summary_name,
                               Results::summaryJson(record, result.outputs, Core::timestamp()));

            result.exit = result.stopped ? Core::Exit::Stopped : Core::Exit::Ok;
            return result;
        }

        // The events the run actually saw, for `--list N`.
        void onEvent(std::function<void(Events::View&)> hook) { hook_ = std::move(hook); }

      private:
        Core::RunRecord recordOf(const Result& result, Core::Steady::time_point started) const {
            (void)started;
            Core::RunRecord record;
            record.point = spec_.point;
            record.hash = spec_.hash;
            record.origin = spec_.origin;
            record.started = started_at_;
            record.events_requested = spec_.events;
            record.attempted = result.counts.attempted;
            record.accepted = result.counts.accepted;
            record.xsec_pb = result.xsec_pb;
            record.xsec_error_pb = result.xsec_error_pb;
            record.stopped = result.stopped;
            record.threads = result.threads;
            record.chunk = result.chunk;
            record.wall_seconds = result.wall_seconds;
            record.mode = mode_;
            record.source = source_->kind();
            record.seed = spec_.seed;
            record.seeds.assign(result.seeds.begin(), result.seeds.end());
            record.warnings = source_->warningCounts();
            return record;
        }

        std::int64_t chunkTarget() const {
            // Small enough that Ctrl-C feels immediate, large enough that the chunk overhead is
            // invisible: about a second of generation, floored at the thread count.
            const std::int64_t wanted = spec_.events > 0 ? std::min<std::int64_t>(spec_.events, 20000)
                                                         : 20000;
            return std::max<std::int64_t>(wanted / 10, 1);
        }

        // Called once per event, on whatever thread produced it. In `serial` that is one thread at a
        // time; in `sharded` it is k at once, and the only things shared are the sinks that said they
        // could not be (one mutex for all of them, because a run has a handful of sinks and two locks
        // would only invite a deadlock).
        void consume(Events::View& view) {
            const std::size_t slot =
                slots_ <= 1 ? 0 : static_cast<std::size_t>(view.slot()) % static_cast<std::size_t>(slots_);
#if defined(HEKIT_WITH_HEPMC)
            // One converter per slot: `Pythia8ToHepMC` holds the event it just built, so two threads
            // sharing one would interleave two events into the same `GenEvent`.
            if (needs_hepmc_) Events::hepmc(view, converters_[slot]);
#endif
            for (const auto& sink : sinks_) {
                if (!shared_ || sink->concurrency() == Sink::Concurrency::Sharded) {
                    sink->event(view);
                } else {
                    const std::lock_guard<std::mutex> guard(shared_mutex_);
                    sink->event(view);
                }
            }
            if (hook_) {
                if (!shared_) {
                    hook_(view);
                } else {
                    const std::lock_guard<std::mutex> guard(shared_mutex_);
                    hook_(view);
                }
            }
            heartbeat_.update(view.index() + 1, spec_.events);
        }

        // 05 §3's rule, with the reasons kept so the notice can name them.
        std::string decideMode() {
            if (spec_.mode == "serial") return "serial";
            bool shardable = false;
            std::vector<std::string> objections;
            for (const auto& sink : sinks_) {
                if (sink->concurrency() == Sink::Concurrency::Sharded) shardable = true;
                const std::string why = sink->serialReason();
                if (!why.empty()) objections.push_back(sink->name() + ": " + why);
            }
            if (spec_.mode == "sharded") {
                // Asked for explicitly: honour it, but say what is about to be serialised anyway.
                for (const std::string& why : objections)
                    status_.log(Status::Level::Warn, "run", why + "; it will run under one lock");
                return "sharded";
            }
            if (spec_.threads == 1) return "serial";     // nothing to gain, and one less variable
            // The specific reason first: a sink that objects also reports itself as not shardable,
            // and "no sink can be sharded" would hide the sentence that says why.
            if (!objections.empty()) {
                for (const std::string& why : objections)
                    status_.log(Status::Level::Info, "run", "serial because " + why);
                return "serial";
            }
            if (!shardable) {
                status_.log(Status::Level::Info, "run", "serial: no sink can be sharded");
                return "serial";
            }
            return "sharded";
        }

        void atChunkEnd(std::int64_t done) {
            heartbeat_.update(done, spec_.events);
            heartbeat_.workers(source_->workers());
            const Source::Xsec xsec = source_->xsec();
            if (xsec.known) status_.xsec(xsec.value_pb, xsec.error_pb, /*final=*/false);
            source_->reportWarnings(status_);
            std::vector<std::string> written;
            for (const auto& sink : sinks_) {
                sink->checkpoint(done);
                for (const Sink::Output& output : sink->outputs())
                    if (output.partial) written.push_back(output.path);
            }
            if (!written.empty()) status_.checkpoint(done, written);
        }

        const Core::Spec& spec_;
        Status::Writer& status_;
        Status::Heartbeat& heartbeat_;
        std::unique_ptr<Source::Base> source_;
        std::vector<std::unique_ptr<Sink::Sink>> sinks_;
        std::function<void(Events::View&)> hook_;
        bool prepared_ = false;
        bool needs_hepmc_ = false;
        bool shared_ = false;                 // is the mutex below worth taking?
        std::mutex shared_mutex_;
        std::string mode_ = "serial";
        int slots_ = 1;
        std::string started_at_;
#if defined(HEKIT_WITH_HEPMC)
        std::vector<Events::Converter> converters_ = std::vector<Events::Converter>(1);
#endif
    };

}  // namespace Run
