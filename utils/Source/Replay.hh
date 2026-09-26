#pragma once

// ── Source/Replay.hh ─────────────────────────────────────────────────────────
// Replaying stored events, and reading a stream (11 §4, decision D13).
//
// "Generate once, analyse many": a store's events go through the same analyzers as fresh ones, so a
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
//     what they meant when the events were written. Under `[run].mode = "sharded"` that is no longer
//     the same number as the *slot* it is analysed on: k consumers pop from one queue fed by n
//     shards, so an event carries both (05 §3, `Events::View`).
//
// **Sharded replay keeps the chunk boundary.** The consumers run a chunk's worth of events and are
// joined; only then does the main thread checkpoint and look at the stop flag. That is the same
// shape as the generator (D-Q2) and it is what makes "stop" and "write a partial result" mean the
// same thing for both sources — a checkpoint never runs while an analyzer is being called.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <filesystem>
#include <cstdint>
#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
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

        /// Check the inputs and build the reader. **Nothing is opened here.**
        ///
        /// Opening a FIFO for reading blocks until a writer appears, and `--check` runs exactly this
        /// far (06 §3.3) — so opening here would make a preflight of an external generator hang
        /// forever, waiting for a generator that a preflight never starts. The readers are started
        /// in `run()` instead, where there really is one at the other end.
        void initialise() override {
            const std::size_t capacity = spec_.store.queue > 0
                                             ? static_cast<std::size_t>(spec_.store.queue)
                                             : kDefaultQueue;
            requireInputs();
            reader_ = std::make_unique<Store::ParallelReader>(shards_, codec_, capacity);
            counted_ = std::vector<std::atomic<long long>>(shards_.size());
            for (std::atomic<long long>& counter : counted_) counter.store(0);
            workers_.assign(shards_.size(), 0);
            status_.log(Status::Level::Info, kind(),
                        "replaying " + std::to_string(shards_.size()) + " " + codec_ +
                            " shard(s) through a queue of " + std::to_string(capacity));
        }

        const Core::Beams& beams() const override { return beams_; }

        /// One reader per shard, so the shard count is what a replay parallelises over.
        int threads() const override { return static_cast<int>(shards_.size()); }

        void async(bool on) override { async_ = on; }

        /// One consumer per shard: more would contend on the queue for no gain, fewer would leave a
        /// reader blocked on a full queue.
        int slots() const override {
            return async_ ? std::max<int>(1, static_cast<int>(shards_.size())) : 1;
        }

        /// A replay chose no seeds; saying so is better than inventing them (07 §2).
        std::vector<std::int64_t> instanceSeeds() override { return {}; }

        std::int64_t chunkSize(std::int64_t wanted) const override {
            return chunkFor(wanted, threads());
        }

        Core::Counts run(std::int64_t target, std::int64_t chunk,
                         const std::function<void(Events::View&)>& consume,
                         const std::function<bool()>& stop,
                         const std::function<void(std::int64_t)>& checkpoint = {}) override {
            // Here, not in `initialise()`: this is the first moment a writer can be at the other
            // end of a FIFO (see `initialise`).
            reader_->start(spec_.store.directory.empty() ? spec_.input : spec_.store.directory);

            Core::Counts counts;
            const int consumers = async_ ? std::max(1, slots()) : 1;
            const std::int64_t step = std::max<std::int64_t>(1, chunkSize(chunk));
            std::atomic<std::int64_t> accepted{0};
            std::atomic<std::int64_t> attempted{0};
            std::atomic<bool> drained{false};
            std::exception_ptr failure;
            std::mutex failure_mutex;

            // One chunk's worth of events on `consumers` threads, then join. The index is claimed
            // *before* the pop so the chunk never overshoots and no event is claimed and dropped.
            const auto body = [&](int slot, std::int64_t ceiling) {
                Store::Frame frame;
                try {
                    while (true) {
                        std::int64_t index = accepted.load(std::memory_order_relaxed);
                        do {
                            if (index >= ceiling) return;
                        } while (!accepted.compare_exchange_weak(index, index + 1));
                        if (!reader_->queue().pop(frame)) {
                            accepted.fetch_sub(1);
                            drained.store(true);
                            return;
                        }
                        attempted.fetch_add(1, std::memory_order_relaxed);
                        Events::View view(nullptr, index, frame.worker, slot);
                        view.adoptHepMC(frame.event.get());
                        view.weights().values.assign(1, weightOf(*frame.event));
                        bump(frame.worker);
                        remember(frame.event);            // keeps the event alive for the analyzers
                        consume(view);
                    }
                } catch (...) {
                    // An analyzer threw on a thread we started; carry it to the main thread rather than
                    // letting it unwind through `std::thread` into `std::terminate`.
                    const std::lock_guard<std::mutex> guard(failure_mutex);
                    if (!failure) failure = std::current_exception();
                    drained.store(true);
                }
            };

            while (!drained.load() && (target <= 0 || accepted.load() < target)) {
                std::int64_t ceiling = accepted.load() + step;
                if (target > 0) ceiling = std::min(ceiling, target);
                if (consumers == 1) {
                    body(0, ceiling);
                } else {
                    std::vector<std::thread> threads;
                    threads.reserve(static_cast<std::size_t>(consumers));
                    for (int slot = 0; slot < consumers; ++slot)
                        threads.emplace_back(body, slot, ceiling);
                    for (std::thread& thread : threads) thread.join();
                }
                counts.accepted = accepted.load();
                counts.attempted = attempted.load();
                if (failure) {
                    reader_->stop();
                    reader_->join();
                    std::rethrow_exception(failure);
                }
                // Nothing is running now, so a checkpoint sees a static set of analyzers.
                if (checkpoint) checkpoint(counts.accepted);
                if (stop && stop()) {
                    reader_->stop();                      // a blocked FIFO read ends here
                    break;
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
            const std::lock_guard<std::mutex> guard(last_lock_);
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

        // Materialised from the atomic counters, because two consumers can be holding events from
        // the same source shard at the same time.
        const std::vector<long long>& workers() const override {
            workers_.resize(counted_.size());
            for (std::size_t index = 0; index < counted_.size(); ++index)
                workers_[index] = counted_[index].load(std::memory_order_relaxed);
            return workers_;
        }

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

        /// What can be checked about the inputs without blocking on them.
        ///
        /// A FIFO only has to *exist* — opening it is what blocks, and whether a generator will
        /// write to it is not knowable until one does. A shard is a regular file, so it can be
        /// checked properly, which keeps `--check` on a store as useful as it was.
        void requireInputs() const {
            const std::string root =
                spec_.store.directory.empty() ? spec_.input : spec_.store.directory;
            for (const Store::Shard& shard : shards_) {
                const std::filesystem::path path =
                    shard.file.find('/') == std::string::npos
                        ? std::filesystem::path(root) / shard.file
                        : std::filesystem::path(shard.file);
                std::error_code code;
                const std::filesystem::file_status state = std::filesystem::status(path, code);
                if (code || !std::filesystem::exists(state))
                    throw Core::Error{Core::Exit::Source, "no such input: " + path.string(),
                                      kind() == "stream"
                                          ? "the generator writes into this FIFO; `hep run` creates "
                                            "it before starting either process"
                                          : "the store's index names it, so the store is incomplete"};
                if (std::filesystem::is_fifo(state)) continue;      // cannot be checked further
                if (!std::filesystem::is_regular_file(state))
                    throw Core::Error{Core::Exit::Source,
                                      "not a file or a FIFO: " + path.string()};
            }
        }

        void bump(int worker) {
            if (worker >= 0 && static_cast<std::size_t>(worker) < counted_.size())
                counted_[static_cast<std::size_t>(worker)].fetch_add(1, std::memory_order_relaxed);
        }

        // The analyzers only borrow the event, so one reference has to outlive the call; a stream also
        // reads σ off the last one it saw (there being no index to read it from).
        void remember(const std::shared_ptr<HepMC3::GenEvent>& event) {
            const std::lock_guard<std::mutex> guard(last_lock_);
            last_ = event;
        }

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
        bool async_ = false;
        std::vector<std::atomic<long long>> counted_;
        mutable std::vector<long long> workers_;
        std::shared_ptr<HepMC3::GenEvent> last_;
        mutable std::mutex last_lock_;
        std::vector<std::pair<std::string, long long>> warnings_;
        std::set<std::string> reported_;
    };

#endif  // HEKIT_WITH_HEPMC

}  // namespace Source
