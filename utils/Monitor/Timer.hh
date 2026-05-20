#pragma once
// Thread-safe scoped timer. Records wall-time per labelled scope in an
// in-memory registry; no file I/O on the hot path. Dump at shutdown.
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
#include <mutex>
#include <ostream>
#include <string>
#include <unordered_map>

namespace Monitor {

class TimerRegistry {
  public:
    static TimerRegistry& instance() {
        static TimerRegistry inst;
        return inst;
    }

    void record(const std::string& label, int64_t wallNs) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto& e  = entries_[label];
        e.wallNs += wallNs;
        e.count  += 1;
    }

    // Writes CSV: label,wall_ns,count — one row per label.
    void dump(std::ostream& out) const {
        std::lock_guard<std::mutex> lock(mutex_);
        out << "label,wall_ns,count\n";
        for (const auto& [label, e] : entries_)
            out << label << ',' << e.wallNs << ',' << e.count << '\n';
    }

    void reset() {
        std::lock_guard<std::mutex> lock(mutex_);
        entries_.clear();
    }

  private:
    struct Entry { int64_t wallNs = 0; int64_t count = 0; };
    mutable std::mutex mutex_;
    std::unordered_map<std::string, Entry> entries_;
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
