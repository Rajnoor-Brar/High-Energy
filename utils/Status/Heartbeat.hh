#pragma once

// ── Status/Heartbeat.hh ──────────────────────────────────────────────────────
// One thread that turns atomic counters into messages on a deadline (06 §3.1).
//
// Ported from the deadline loop of `legacy/utils/Monitor/Threading.hh:121-136,212-213`, which got two
// things right that are easy to get wrong:
//
//   * **Deadlines are advanced past `now` in a loop**, so a slow iteration does not produce a burst of
//     catch-up messages;
//   * **the wait is a `wait_until` with a predicate**, so a stop is immediate rather than "after the
//     next tick" — the difference between Ctrl-C feeling instant and feeling broken.
//
// The event loop only ever calls `update()`, which stores counters. Nothing in the hot path locks,
// formats or writes.

#include <atomic>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>

#include "Core/Clock.hh"
#include "Status/Types.hh"
#include "Status/Writer.hh"

namespace Status {

    class Heartbeat {
      public:
        Heartbeat(Writer& writer, double interval = 0.5) : writer_(writer), interval_(interval) {}

        ~Heartbeat() { stop(); }

        Heartbeat(const Heartbeat&) = delete;
        Heartbeat& operator=(const Heartbeat&) = delete;

        // Called from the event loop: cheap and lock-free.
        void update(long long done, long long total) {
            done_.store(done, std::memory_order_relaxed);
            total_.store(total, std::memory_order_relaxed);
        }

        void workers(std::vector<long long> counts) {
            const std::lock_guard<std::mutex> lock(mutex_);
            workers_ = std::move(counts);
        }

        void start() {
            if (thread_.joinable()) return;
            running_.store(true, std::memory_order_relaxed);
            started_ = Core::tick();
            thread_ = std::thread([this] { loop(); });
        }

        void stop() {
            if (!thread_.joinable()) return;
            {
                const std::lock_guard<std::mutex> lock(mutex_);
                running_.store(false, std::memory_order_relaxed);
            }
            wake_.notify_all();
            thread_.join();
        }

      private:
        void loop() {
            std::unique_lock<std::mutex> lock(mutex_);
            auto next = Core::Steady::now();
            const auto step = std::chrono::duration_cast<Core::Steady::duration>(
                std::chrono::duration<double>(interval_));
            long long last_done = -1;
            while (running_.load(std::memory_order_relaxed)) {
                next += step;
                // advance past now, so a stall does not queue up a burst of messages
                const auto now = Core::Steady::now();
                while (next <= now) next += step;
                wake_.wait_until(lock, next,
                                 [this] { return !running_.load(std::memory_order_relaxed); });
                if (!running_.load(std::memory_order_relaxed)) break;

                const long long done = done_.load(std::memory_order_relaxed);
                const long long total = total_.load(std::memory_order_relaxed);
                Progress progress;
                progress.done = done;
                progress.total = total;
                progress.rate = elapsed() > 0.0 ? static_cast<double>(done) / elapsed() : 0.0;
                progress.workers = workers_;
                lock.unlock();
                if (done != last_done) {
                    writer_.progress(progress, /*force=*/true);
                    last_done = done;
                } else if (writer_.sinceLastMessage() >= interval_) {
                    // nothing moved: say so, rather than letting the supervisor guess (06 §4)
                    writer_.heartbeat();
                }
                lock.lock();
            }
        }

        double elapsed() const { return Core::since(started_); }

        Writer& writer_;
        double interval_;
        std::atomic<long long> done_{0};
        std::atomic<long long> total_{0};
        std::atomic<bool> running_{false};
        std::vector<long long> workers_;
        std::mutex mutex_;
        std::condition_variable wake_;
        std::thread thread_;
        Core::Steady::time_point started_{};
    };

}  // namespace Status
