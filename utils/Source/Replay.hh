#pragma once

// ── Source/Replay.hh ─────────────────────────────────────────────────────────
// Replaying stored events, and reading a stream (11 §4, decision D13).
//
// "Generate once, analyse many": a store's events go through the same sinks as fresh ones, so a
// different analysis, a new histogram or a changed cut costs a read rather than a generation. The
// same class reads a FIFO, because a stream is a store with one shard and no index — which is how
// external generators deliver events (04 §8).
//
// Three things it does differently from a generator, all of them deliberate:
//
//   * **σ, beams and weight names come from the index**, not from the events. A per-event
//     `GenCrossSection` is the generator's running estimate at that event; the index carries the
//     final, merged value (11 §4). For a stream, where there is no index, the *last* event's value is
//     the best available and is used.
//   * **there are no seeds.** A replay did not choose any; `instanceSeeds()` is empty, and the
//     summary says so rather than inventing a number.
//   * **the worker of an event is the shard it came from**, so the per-worker counts keep meaning
//     what they meant when the events were written.

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "Core.hh"
#include "Events.hh"
#include "Source/Base.hh"
#include "Source/Types.hh"
#include "Status.hh"
#include "Store/Reader.hh"
#include "Store/Types.hh"

namespace Source {

#if defined(HEKIT_WITH_HEPMC)

    class Replay : public Base {
      public:
        Replay(const Core::Spec& spec, Status::Writer& status) : spec_(spec), status_(status) {}

        std::string kind() const override { return spec_.store.shards.empty() ? "stream" : "store"; }

        /// Work out which shards to read. Nothing is opened yet.
        void configure() override {
            const Core::StoreSpec& store = spec_.store;
            codec_ = store.compression.empty() ? "zst" : store.compression;
            Store::requireCodec(codec_);

            shards_.clear();
            if (!store.shards.empty()) {
                for (std::size_t position = 0; position < store.shards.size(); ++position) {
                    Store::Shard shard;
                    shard.file = store.shards[position];
                    shard.worker = position < store.workers.size()
                                       ? store.workers[position]
                                       : static_cast<int>(position);
                    shards_.push_back(shard);
                }
            } else if (!spec_.inputs.empty()) {
                // A stream: the paths are FIFOs or files, one reader each, no index (04 §8).
                for (std::size_t position = 0; position < spec_.inputs.size(); ++position) {
                    Store::Shard shard;
                    shard.file = spec_.inputs[position];
                    shard.worker = static_cast<int>(position);
                    shards_.push_back(shard);
                }
            }
            if (shards_.empty())
                throw Core::Error{Core::Exit::Config,
                                  "the spec asks for a replay but names no shards",
                                  "`hep run` fills [source.store] from the store's index; a "
                                  "hand-written spec must list shards or inputs"};

            beams_.ids = store.beam_ids;
            beams_.energies = store.beam_energies;
            if (beams_.energies.size() == 2)
                beams_.sqrtS = 2.0 * std::sqrt(beams_.energies[0] * beams_.energies[1]);
            else if (beams_.energies.size() == 1)
                beams_.sqrtS = beams_.energies[0];
        }

        /// Open the shards and start the readers. This is where a missing file is noticed.
        void initialise() override {
            const std::size_t capacity = spec_.store.queue > 0
                                             ? static_cast<std::size_t>(spec_.store.queue)
                                             : kDefaultQueue;
            reader_ = std::make_unique<Store::ParallelReader>(shards_, codec_, capacity);
            reader_->start(spec_.store.directory.empty() ? spec_.input : spec_.store.directory);
            workers_.assign(shards_.size(), 0);
            status_.log(Status::Level::Info, kind(),
                        "replaying " + std::to_string(shards_.size()) + " " + codec_ +
                            " shard(s) through a queue of " + std::to_string(capacity));
        }

        const Core::Beams& beams() const override { return beams_; }

        /// One reader per shard, so the shard count is what a replay parallelises over.
        int threads() const override { return static_cast<int>(shards_.size()); }

        /// A replay chose no seeds; saying so is better than inventing them (07 §2).
        std::vector<std::int64_t> instanceSeeds() override { return {}; }

        std::int64_t chunkSize(std::int64_t wanted) const override {
            return chunkFor(wanted, threads());
        }

        Core::Counts run(std::int64_t target, std::int64_t chunk,
                         const std::function<void(Events::View&)>& consume,
                         const std::function<bool()>& stop,
                         const std::function<void(std::int64_t)>& checkpoint = {}) override {
            Core::Counts counts;
            const std::int64_t step = std::max<std::int64_t>(1, chunkSize(chunk));
            Store::Frame frame;
            std::int64_t since_checkpoint = 0;

            while (target <= 0 || counts.accepted < target) {
                if (!reader_->queue().pop(frame)) break;          // drained, or stopped
                counts.attempted += 1;
                Events::View view(nullptr, counts.accepted, frame.worker);
                view.adoptHepMC(frame.event.get());
                view.weights().values.assign(1, weightOf(*frame.event));
                counts.accepted += 1;
                if (frame.worker >= 0 && static_cast<std::size_t>(frame.worker) < workers_.size())
                    workers_[static_cast<std::size_t>(frame.worker)] += 1;
                last_ = frame.event;                              // keeps the event alive for the sinks
                consume(view);

                if (++since_checkpoint >= step) {
                    since_checkpoint = 0;
                    if (checkpoint) checkpoint(counts.accepted);
                    if (stop && stop()) {
                        reader_->stop();                          // a blocked FIFO read ends here
                        break;
                    }
                }
            }
            reader_->stop();
            reader_->join();
            for (const std::string& problem : reader_->problems())
                warnings_.emplace_back(problem, 1);
            return counts;
        }

        /// From the index for a store; from the last event for a stream, which has no index.
        Xsec xsec() override {
            Xsec found;
            if (spec_.store.xsec_pb > 0.0) {
                found.value_pb = spec_.store.xsec_pb;
                found.error_pb = spec_.store.xsec_err_pb;
                found.known = true;
                return found;
            }
            if (last_ != nullptr) {
                const std::shared_ptr<HepMC3::GenCrossSection> cross = last_->cross_section();
                if (cross != nullptr && cross->xsec() > 0.0) {
                    found.value_pb = cross->xsec();               // HepMC3 carries pb
                    found.error_pb = cross->xsec_err();
                    found.known = true;
                }
            }
            return found;
        }

        const std::vector<long long>& workers() const override { return workers_; }

        void reportWarnings(Status::Writer& status) override {
            for (const auto& [message, count] : warnings_) {
                if (reported_.count(message) != 0) continue;
                reported_.insert(message);
                status.log(Status::Level::Warn, kind(), message);
            }
        }

        std::vector<std::pair<std::string, long long>> warningCounts() override { return warnings_; }

        std::int64_t eventsRead() const { return reader_ != nullptr ? reader_->eventsRead() : 0; }

      private:
        static constexpr std::size_t kDefaultQueue = 512;

        static double weightOf(const HepMC3::GenEvent& event) {
            const std::vector<double>& weights = event.weights();
            return weights.empty() ? 1.0 : weights.front();
        }

        const Core::Spec& spec_;
        Status::Writer& status_;
        std::string codec_;
        std::vector<Store::Shard> shards_;
        std::unique_ptr<Store::ParallelReader> reader_;
        Core::Beams beams_;
        std::vector<long long> workers_;
        std::shared_ptr<HepMC3::GenEvent> last_;
        std::vector<std::pair<std::string, long long>> warnings_;
        std::set<std::string> reported_;
    };

#endif  // HEKIT_WITH_HEPMC

}  // namespace Source
