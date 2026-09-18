#pragma once

// ── Sink/Store.hh ────────────────────────────────────────────────────────────
// Writing the events a run generates, so they can be analysed again without regenerating them
// (11 §3, decision D13).
//
// This is the sink that makes "generate once, analyse many" possible, and it is also how external
// Delphes is fed (a store pointed at a FIFO, with no index). Two things it is careful about:
//
//   * **it needs the HepMC record, and says so** through `needs()`. A run whose only sink is Rivet
//     already pays for that conversion; a run with no HepMC-consuming sink never does (05 §1).
//   * **the shard is chosen by the worker that generated the event**, not by the thread that happens
//     to be running the callback. With `processAsync = off` callbacks move between threads, so keying
//     on anything else would interleave two workers' events in one shard and make the layout depend
//     on the concurrency mode (11 §1).
//
// The index is written in `finish()` from the `RunRecord`, after every shard is closed and hashed.

#include <memory>
#include <string>
#include <vector>

#include "Core.hh"
#include "Events.hh"
#include "Sink/Types.hh"
#include "Status.hh"
// The submodules directly, not the `Store.hh` facade: this file *is* `Sink/Store.hh`, and a quoted
// include looks in its own directory first — so `#include "Store.hh"` here finds itself.
#include "Store/Compression.hh"
#include "Store/Types.hh"
#include "Store/Writer.hh"

namespace Sink {

#if defined(HEKIT_WITH_HEPMC)

    class Store : public Sink {
      public:
        Store(const Core::SinkSpec& spec, std::string directory, Status::Writer& status)
            : spec_(spec), directory_(std::move(directory)), status_(status) {}

        std::string name() const override { return "store"; }

        Needs needs() const override { return Needs{/*pythia=*/false, /*hepmc=*/true}; }

        // One shard per worker means no lock is needed, which is the point of the layout (11 §1).
        Concurrency concurrency() const override { return Concurrency::Sharded; }

        void prepare() override {
            const std::string codec = spec_.compression.empty() ? "zst" : spec_.compression;
            ::Store::requireCodec(codec);            // fail here, not at the first event
            writer_ = std::make_unique<::Store::Writer>(directory_, codec);
        }

        void start(const Core::Beams& beams, long long expected_events) override {
            (void)expected_events;
            beams_ = beams;
            if (writer_ == nullptr) prepare();
            status_.log(Status::Level::Info, "store",
                        "writing " + writer_->codec() + " shards into " + directory_);
        }

        void event(Events::View& view) override {
            HepMC3::GenEvent* genEvent = view.hepmcOrNull();
            if (genEvent == nullptr)
                throw Core::Error{Core::Exit::Internal,
                                  "the store sink was given an event with no HepMC record"};
            writer_->write(view.worker(), *genEvent);
        }

        void finish(const Core::RunRecord& record) override {
            if (writer_ == nullptr) return;
            ::Store::Index index;
            index.point = record.point;
            index.hash = record.hash;
            index.tool = "pythia";
            index.beams = beams_;
            index.threads = record.threads;
            index.seeds.assign(record.seeds.begin(), record.seeds.end());
            index.xsec_pb = record.xsec_pb;
            index.xsec_err_pb = record.xsec_error_pb;
            index.events = writer_->events();
            index.stopped = record.stopped;
            const ::Store::Index written = writer_->finish(std::move(index));

            outputs_.push_back(Output{"store", directory_, record.stopped});
            status_.log(Status::Level::Info, "store",
                        std::to_string(written.events) + " events in " +
                            std::to_string(written.shards.size()) + " shards" +
                            (record.stopped ? " (partial)" : ""));
        }

        std::vector<Output> outputs() const override { return outputs_; }

        std::int64_t events() const { return writer_ != nullptr ? writer_->events() : 0; }

      private:
        Core::SinkSpec spec_;
        std::string directory_;
        Status::Writer& status_;
        Core::Beams beams_;
        std::unique_ptr<::Store::Writer> writer_;
        std::vector<Output> outputs_;
    };

#endif  // HEKIT_WITH_HEPMC

}  // namespace Sink
