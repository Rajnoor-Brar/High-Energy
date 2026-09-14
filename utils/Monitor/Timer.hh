#pragma once
// Thread-safe scoped timer. Records wall-time per labelled scope; dump at
// shutdown.
//
// Hot path is lock-free: each thread accumulates into a thread_local bucket
// keyed by the label's address (MONITOR_SCOPE_TIMER only ever passes string
// literals). Buckets merge into the global registry — keyed by string, so
// identical labels from different translation units aggregate — when a
// thread exits or dump() runs. The previous design took one global mutex and
// built a std::string per record(), serializing all workers on the hottest
// paths (pushFill / applyParticleRequest).
//
// Usage:
//   MONITOR_SCOPE_TIMER("Record.Writer.pushFill");
//   Monitor::TimerRegistry::instance().dump(std::cout);
//
// Compile with -DMONITOR_TIMERS=0 to eliminate all overhead.

#ifndef MONITOR_TIMERS
#  define MONITOR_TIMERS 1
#endif

#include <chrono>
#include <cstdint>
#include <map>
#include <mutex>
#include <ostream>
#include <string>
#include <unordered_map>

namespace Monitor {

class TimerRegistry {
  public:
    struct Entry { int64_t wallNs = 0; int64_t count = 0; };

    static TimerRegistry& instance() {
        static TimerRegistry inst;
        return inst;
    }

    // Hot path: thread-local, no lock, no string construction. `label` must
    // be a string literal (stable address for the lifetime of the process).
    void record(const char* label, int64_t wallNs) {
        auto& e  = threadBucket().map[label];
        e.wallNs += wallNs;
        e.count  += 1;
    }

    // Writes CSV: label,wall_ns,count — one row per label. Flushes the calling
    // thread's bucket first; other threads' buckets flush when they exit (all
    // worker threads are joined before the drivers dump).
    void dump(std::ostream& out) {
        flushThisThread();
        std::lock_guard<std::mutex> lock(mutex_);
        out << "label,wall_ns,count\n";
        for (const auto& [label, e] : entries_)
            out << label << ',' << e.wallNs << ',' << e.count << '\n';
    }

    void reset() {
        threadBucket().map.clear();
        std::lock_guard<std::mutex> lock(mutex_);
        entries_.clear();
    }

    void flushThisThread() { mergeBucket(threadBucket().map); }

  private:
    struct ThreadBucket {
        std::unordered_map<const char*, Entry> map;
        // Touch the registry in the constructor so it is constructed before
        // (and therefore destroyed after) any thread bucket — the destructor
        // below must merge into a live registry.
        ThreadBucket() { (void)TimerRegistry::instance(); }
        ~ThreadBucket() { TimerRegistry::instance().mergeBucket(map); }
    };

    static ThreadBucket& threadBucket() {
        thread_local ThreadBucket bucket;
        return bucket;
    }

    void mergeBucket(std::unordered_map<const char*, Entry>& bucket) {
        if (bucket.empty()) return;
        std::lock_guard<std::mutex> lock(mutex_);
        for (const auto& [label, e] : bucket) {
            Entry& g  = entries_[label];   // string key: merges across TUs
            g.wallNs += e.wallNs;
            g.count  += e.count;
        }
        bucket.clear();
    }

    mutable std::mutex           mutex_;
    std::map<std::string, Entry> entries_;
};

#if MONITOR_TIMERS

class ScopeTimer {
  public:
    explicit ScopeTimer(const char* label)
        : label_(label), start_(std::chrono::steady_clock::now()) {}

    ~ScopeTimer() {
        const auto end = std::chrono::steady_clock::now();
        TimerRegistry::instance().record(
            label_,
            std::chrono::duration_cast<std::chrono::nanoseconds>(end - start_).count());
    }

    ScopeTimer(const ScopeTimer&)            = delete;
    ScopeTimer& operator=(const ScopeTimer&) = delete;

  private:
    const char* label_;
    std::chrono::steady_clock::time_point start_;
};

// Helper macros for unique variable names per line.
#  define _MT_CAT(a, b)       a##b
#  define _MT_VAR(n)          _MT_CAT(_mt_, n)
#  define MONITOR_SCOPE_TIMER(label) \
       ::Monitor::ScopeTimer _MT_VAR(__LINE__)(label)

#else // MONITOR_TIMERS == 0

#  define MONITOR_SCOPE_TIMER(label) ((void)0)

#endif // MONITOR_TIMERS

} // namespace Monitor
