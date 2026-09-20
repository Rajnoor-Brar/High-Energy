#pragma once

// ── Sink/Delphes.hh ──────────────────────────────────────────────────────────
// The tee that feeds an external Delphes (05 §5, P7-S08).
//
// Delphes runs as its own process, reading HepMC3 from a FIFO this sink writes. It is *not* run in
// process, and the reason is worth stating because it is the same reason this namespace is `Events`
// and not `Event`: Delphes declares a global `class Event` (`DelphesClasses.h:46`), and it keeps ROOT
// global state that a generator thread has no business sharing (13 §3). One process each keeps both
// halves' globals to themselves.
//
// So this sink is deliberately the smallest thing that works:
//
//   * **one writer, one path, no index.** A store (11) is sharded and indexed because it is meant to
//     be replayed; this is a pipe to a program that is reading it *now*, so there is nothing to index
//     and nowhere to shard to. `Store::Writer`'s `.part`-then-rename would also be wrong on a FIFO,
//     which cannot be renamed.
//   * **uncompressed.** Two processes on one machine; compressing the pipe spends CPU to save
//     nothing, and `DelphesHepMC3` reads plain HepMC3.
//   * **serial.** The far end is a single-threaded reader of one stream, so there is no version of
//     this that shards.
//
// Opening the FIFO blocks until Delphes opens the other end, which is why that happens in `start()`
// (once the run is really going) rather than in `prepare()`, where `--check` would sit on it for ever
// waiting for a process a preflight never starts (00/B33 was the same trap from the reading side).

#include <memory>
#include <string>
#include <vector>

#include "Core.hh"
#include "Events.hh"
#include "Sink/Types.hh"
#include "Status.hh"
#include "Store/Compression.hh"
#include "Store/Types.hh"

namespace Sink {

#if defined(HEKIT_WITH_HEPMC)

    class Delphes : public Sink {
      public:
        Delphes(const Core::SinkSpec& spec, Status::Writer& status)
            : spec_(spec), status_(status) {}

        std::string name() const override { return "delphes"; }

        Needs needs() const override { return Needs{/*pythia=*/false, /*hepmc=*/true}; }

        // One stream to one reader: there is no sharded version of a pipe.
        Concurrency concurrency() const override { return Concurrency::Serial; }

        std::string serialReason() const override {
            return "the Delphes tee is one stream to one reader";
        }

        void prepare() override {
            if (spec_.dir.empty())
                throw Core::Error{Core::Exit::Config,
                                  "the delphes sink has no path to write to",
                                  "`hep run` points it at the FIFO the Delphes stage reads"};
        }

        // Opening the FIFO blocks until the reader arrives, so it happens here rather than in
        // `prepare()` — which is where `--check` stops (06 §3.3).
        void start(const Core::Beams& beams, long long expected_events) override {
            (void)beams;
            (void)expected_events;
            if (writer_ != nullptr) return;
            status_.log(Status::Level::Info, "delphes", "opening " + spec_.dir + " for Delphes");
            writer_ = ::Store::makeWriter(spec_.dir, "none");
            if (writer_->failed())
                throw Core::Error{Core::Exit::Sink, "cannot write to " + spec_.dir,
                                  "the Delphes stage should be reading it"};
        }

        void event(Events::View& view) override {
            HepMC3::GenEvent* genEvent = view.hepmcOrNull();
            if (genEvent == nullptr)
                throw Core::Error{Core::Exit::Internal,
                                  "the delphes sink was given an event with no HepMC record"};
            writer_->write_event(*genEvent);
            if (writer_->failed())
                throw Core::Error{Core::Exit::Sink,
                                  "writing to the Delphes pipe failed after " +
                                      std::to_string(written_) + " events",
                                  "Delphes exited early; its log says why"};
            written_ += 1;
        }

        // Closing is what tells Delphes there are no more events, so it must happen even on a
        // stopped run — otherwise the far end waits for ever on a pipe nobody will write to again.
        void finish(const Core::RunRecord& record) override {
            if (writer_ == nullptr) return;
            writer_->close();
            writer_.reset();
            outputs_.push_back(Output{"delphes-fifo", spec_.dir, record.stopped});
            status_.log(Status::Level::Info, "delphes",
                        std::to_string(written_) + " events written to Delphes" +
                            (record.stopped ? " (stopped)" : ""));
        }

        std::vector<Output> outputs() const override { return outputs_; }

        long long written() const { return written_; }

      private:
        Core::SinkSpec spec_;
        Status::Writer& status_;
        std::unique_ptr<HepMC3::Writer> writer_;
        long long written_ = 0;
        std::vector<Output> outputs_;
    };

#endif  // HEKIT_WITH_HEPMC

}  // namespace Sink
