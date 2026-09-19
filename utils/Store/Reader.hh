#pragma once

// ── Store/Reader.hh ──────────────────────────────────────────────────────────
// Reading HepMC3 back: one thread per shard, into a bounded queue (11 §4).
//
// The same code reads a store's shards and a FIFO, because they differ in exactly two ways that do
// not belong in the reader: a store has an index (so σ, beams and counts are known in advance) and a
// FIFO does not; and a store's shards can be read in parallel while a FIFO is one stream. Both are
// "a path that yields GenEvents until it stops", so both are a `Shard` here.
//
// What the reader itself has to get right:
//
//   * **it never blocks the loop.** Events go into a bounded queue; a slow analysis slows the readers
//     down instead of filling memory (`Store/Queue.hh`).
//   * **it stops where it is told.** `limit` bounds a partial replay, and the queue's stop flag ends
//     a read mid-shard — a FIFO read cannot be interrupted any other way.
//   * **a failed read is reported, not skipped.** A truncated shard ends that reader and is recorded;
//     the run then has fewer events than the index promised, and says so.

#include <atomic>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include "Core/Errors.hh"
#include "Store/Compression.hh"
#include "Store/Queue.hh"
#include "Store/Types.hh"

#if defined(HEKIT_WITH_HEPMC)
#include "HepMC3/GenEvent.h"
#include "HepMC3/Reader.h"
#endif

namespace Store {

#if defined(HEKIT_WITH_HEPMC)

    /// One event on its way from a reader to the loop, with the shard it came from.
    struct Frame {
        std::shared_ptr<HepMC3::GenEvent> event;
        int worker = 0;
        std::int64_t index = 0;
    };

    using EventQueue = Queue<Frame>;

    /// What one shard's reader did.
    struct ReadResult {
        int worker = 0;
        std::string file;
        std::int64_t events = 0;
        bool truncated = false;
        std::string error;
    };

    /// Read one shard into the queue. Runs on its own thread; returns when the shard ends, the limit
    /// is reached, or the queue is stopped.
    inline ReadResult readShard(const std::string& path, const std::string& codec, int worker,
                                EventQueue& queue, std::int64_t limit = 0) {
        ReadResult result;
        result.worker = worker;
        result.file = path;
        try {
            std::unique_ptr<HepMC3::Reader> reader = makeReader(path, codec);
            if (reader->failed()) {
                result.error = "cannot open " + path;
                queue.finish();
                return result;
            }
            while (limit <= 0 || result.events < limit) {
                auto event = std::make_shared<HepMC3::GenEvent>();
                reader->read_event(*event);
                if (reader->failed()) break;          // the end of the shard, or a broken record
                Frame frame;
                frame.event = std::move(event);
                frame.worker = worker;
                frame.index = result.events;
                if (!queue.push(std::move(frame))) break;   // stopped
                result.events += 1;
            }
            reader->close();
        } catch (const std::exception& error) {
            result.error = error.what();
        }
        queue.finish();
        return result;
    }

    /// Several shards at once: one thread each, all feeding one queue.
    class ParallelReader {
      public:
        ParallelReader(std::vector<Shard> shards, std::string codec, std::size_t capacity)
            : shards_(std::move(shards)), codec_(std::move(codec)),
              queue_(capacity, static_cast<int>(shards_.size())) {}

        ~ParallelReader() { stop(); join(); }

        /// Start one reader per shard. `limit` bounds each shard, not the total.
        void start(const std::string& directory, std::int64_t limit = 0) {
            for (std::size_t position = 0; position < shards_.size(); ++position) {
                const Shard& shard = shards_[position];
                const std::string path = shard.file.find('/') == std::string::npos
                                             ? directory + "/" + shard.file
                                             : shard.file;
                threads_.emplace_back([this, path, worker = shard.worker, limit] {
                    ReadResult found = readShard(path, codec_, worker, queue_, limit);
                    const std::lock_guard<std::mutex> lock(results_mutex_);
                    results_.push_back(std::move(found));
                });
            }
        }

        EventQueue& queue() { return queue_; }

        void stop() { queue_.stop(); }

        void join() {
            for (std::thread& thread : threads_)
                if (thread.joinable()) thread.join();
            threads_.clear();
        }

        std::vector<ReadResult> results() {
            const std::lock_guard<std::mutex> lock(results_mutex_);
            return results_;
        }

        std::int64_t eventsRead() {
            std::int64_t total = 0;
            for (const ReadResult& result : results()) total += result.events;
            return total;
        }

        std::vector<std::string> problems() {
            std::vector<std::string> found;
            for (const ReadResult& result : results())
                if (!result.error.empty()) found.push_back(result.file + ": " + result.error);
            return found;
        }

      private:
        std::vector<Shard> shards_;
        std::string codec_;
        EventQueue queue_;
        std::vector<std::thread> threads_;
        std::mutex results_mutex_;
        std::vector<ReadResult> results_;
    };

#endif  // HEKIT_WITH_HEPMC

}  // namespace Store
