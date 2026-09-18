#pragma once

// ── Run/Loop.hh ──────────────────────────────────────────────────────────────
// Source → sinks, in chunks, with a stop that works (05 §3).
//
// The shape of the loop follows what P2-S02 measured: `PythiaParallel::run` cannot be interrupted from
// its callback, so the only place to stop, checkpoint or dump is a chunk boundary, and a chunk that is
// a multiple of the thread count keeps the event set identical to an unchunked run (D-Q2).
//
// The loop owns the order of events in a run's life, and nothing else:
//   configure → init → start sinks → [chunk: events → checkpoint → stop?] → finish sinks → summary.
//
// Every failure becomes a `Core::Error` with its own exit code, so `main` stays five lines.

#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include "Core.hh"
#include "Events.hh"
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

        // Everything up to (but not including) the first event. `--check` stops here (06 §3.3).
        void prepare() {
            status_.phase("configure", std::to_string(spec_.cards.size()) + " cards");
            source_ = std::make_unique<Source::Pythia>(spec_, status_);
            source_->configure();
            status_.phase("init");
            source_->initialise();
            const Core::Beams& beams = source_->beams();
            std::vector<std::string> names;
            for (const auto& sink : sinks_) names.push_back(sink->name());
            status_.init(beams.ids, beams.energies, beams.sqrtS, source_->threads(), "serial", names);
            prepared_ = true;
        }

        Result run() {
            if (!prepared_) prepare();
            const Core::Steady::time_point started = Core::tick();
            const Core::Beams& beams = source_->beams();
            for (const auto& sink : sinks_) sink->start(beams, spec_.events);

            needs_hepmc_ = false;
            for (const auto& sink : sinks_) needs_hepmc_ = needs_hepmc_ || sink->needs().hepmc;

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
            Core::RunRecord record;
            record.point = spec_.point;
            record.hash = spec_.hash;
            record.origin = spec_.origin;
            record.attempted = counts.attempted;
            record.accepted = counts.accepted;
            record.xsec_pb = result.xsec_pb;
            record.xsec_error_pb = result.xsec_error_pb;
            record.stopped = result.stopped;
            record.threads = result.threads;
            record.chunk = result.chunk;
            record.wall_seconds = result.wall_seconds;
            for (const auto& sink : sinks_) {
                sink->finish(record);
                for (const Sink::Output& output : sink->outputs()) result.outputs.push_back(output);
            }

            result.exit = result.stopped ? Core::Exit::Stopped : Core::Exit::Ok;
            return result;
        }

        // The events the run actually saw, for `--list N`.
        void onEvent(std::function<void(Events::View&)> hook) { hook_ = std::move(hook); }

      private:
        std::int64_t chunkTarget() const {
            // Small enough that Ctrl-C feels immediate, large enough that the chunk overhead is
            // invisible: about a second of generation, floored at the thread count.
            const std::int64_t wanted = spec_.events > 0 ? std::min<std::int64_t>(spec_.events, 20000)
                                                         : 20000;
            return std::max<std::int64_t>(wanted / 10, 1);
        }

        void consume(Events::View& view) {
#if defined(HEKIT_WITH_HEPMC)
            if (needs_hepmc_) Events::hepmc(view, converter_);
#endif
            for (const auto& sink : sinks_) sink->event(view);
            if (hook_) hook_(view);
            heartbeat_.update(view.index() + 1, spec_.events);
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
        std::unique_ptr<Source::Pythia> source_;
        std::vector<std::unique_ptr<Sink::Sink>> sinks_;
        std::function<void(Events::View&)> hook_;
        bool prepared_ = false;
        bool needs_hepmc_ = false;
#if defined(HEKIT_WITH_HEPMC)
        Events::Converter converter_;
#endif
    };

}  // namespace Run
