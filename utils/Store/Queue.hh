#pragma once

// ── Store/Queue.hh ───────────────────────────────────────────────────────────
// A bounded queue between reader threads and the event loop (11 §4).
//
// Ported from `legacy/utils/Probe/Lifecycle.hh:229-267`, which had the shape right: a capacity, a
// condition variable each way, a stop flag, and a count of finished producers. Reading a hundred
// gigabytes of HepMC is only useful if the readers run ahead of the analysis, and only safe if they
// cannot run *arbitrarily* far ahead — hence the bound. Three properties the loop depends on:
//
//   * **backpressure.** A full queue blocks the readers rather than growing; the queue's capacity is
//     the memory the replay is allowed to use for events in flight.
//   * **stopping is immediate.** `stop()` wakes everyone: readers stop pushing, consumers stop
//     waiting, and neither has to finish a shard first. That is what makes Ctrl-C during a replay
//     bounded (06 §4).
//   * **"finished" is not "empty".** A consumer must keep draining after the last reader has gone,
//     and must only stop when the queue is empty *and* every producer has finished — getting that
//     wrong drops the tail of the last shard, which is exactly the kind of loss nothing notices.

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <mutex>
#include <utility>

namespace Store {

    template <typename T>
    class Queue {
      public:
        explicit Queue(std::size_t capacity, int producers = 1)
            : capacity_(capacity == 0 ? 1 : capacity), producers_(producers) {}

        /// Block until there is room, then push. False when the queue was stopped.
        bool push(T item) {
            std::unique_lock<std::mutex> lock(mutex_);
            not_full_.wait(lock, [&] { return stopped_ || queue_.size() < capacity_; });
            if (stopped_) return false;
            queue_.push_back(std::move(item));
            pushed_ += 1;
            lock.unlock();
            not_empty_.notify_one();
            return true;
        }

        /// Block until there is an item, the queue stops, or every producer has finished.
        bool pop(T& item) {
            std::unique_lock<std::mutex> lock(mutex_);
            not_empty_.wait(lock, [&] {
                return stopped_ || !queue_.empty() || finished_ >= producers_;
            });
            // Drain before giving up: "every producer finished" does not mean "nothing left".
            if (queue_.empty()) return false;
            item = std::move(queue_.front());
            queue_.pop_front();
            popped_ += 1;
            lock.unlock();
            not_full_.notify_one();
            return true;
        }

        /// One producer has no more items. When the last one says so, waiting consumers wake up.
        void finish() {
            {
                const std::lock_guard<std::mutex> lock(mutex_);
                finished_ += 1;
            }
            not_empty_.notify_all();
        }

        /// Stop everything, at once. Safe from any thread, and idempotent.
        void stop() {
            {
                const std::lock_guard<std::mutex> lock(mutex_);
                stopped_ = true;
            }
            not_empty_.notify_all();
            not_full_.notify_all();
        }

        bool stopped() const {
            const std::lock_guard<std::mutex> lock(mutex_);
            return stopped_;
        }

        std::size_t size() const {
            const std::lock_guard<std::mutex> lock(mutex_);
            return queue_.size();
        }

        std::size_t capacity() const { return capacity_; }
        long long pushed() const { return pushed_.load(std::memory_order_relaxed); }
        long long popped() const { return popped_.load(std::memory_order_relaxed); }

        int finishedProducers() const {
            const std::lock_guard<std::mutex> lock(mutex_);
            return finished_;
        }

      private:
        mutable std::mutex mutex_;
        std::condition_variable not_empty_;
        std::condition_variable not_full_;
        std::deque<T> queue_;
        std::size_t capacity_;
        int producers_;
        int finished_ = 0;
        bool stopped_ = false;
        std::atomic<long long> pushed_{0};
        std::atomic<long long> popped_{0};
    };

}  // namespace Store
