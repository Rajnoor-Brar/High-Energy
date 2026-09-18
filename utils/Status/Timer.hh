#pragma once

// ── Status/Timer.hh ──────────────────────────────────────────────────────────
// Scope timers, for answering "where did the time go" without a profiler. Ported from
// `legacy/utils/Monitor/Timer.hh` (standard library only) and trimmed to what a run needs: named
// totals and call counts, reported once at the end.
//
//   {
//     Status::Scope scope(timers, "rivet.analyze");
//     ...
//   }                                   // adds the elapsed time to that name
//
// Off by default in the hot path: `hep bench` (P6-S03) turns it on.

#include <map>
#include <mutex>
#include <string>
#include <utility>

#include "Core/Clock.hh"

namespace Status {

    class Timers {
      public:
        void add(const std::string& name, double seconds) {
            const std::lock_guard<std::mutex> lock(mutex_);
            Entry& entry = entries_[name];
            entry.seconds += seconds;
            entry.calls += 1;
        }

        struct Entry {
            double seconds = 0.0;
            long long calls = 0;
        };

        std::map<std::string, Entry> snapshot() const {
            const std::lock_guard<std::mutex> lock(mutex_);
            return entries_;
        }

        bool empty() const {
            const std::lock_guard<std::mutex> lock(mutex_);
            return entries_.empty();
        }

      private:
        mutable std::mutex mutex_;
        std::map<std::string, Entry> entries_;
    };

    class Scope {
      public:
        Scope(Timers& timers, std::string name)
            : timers_(&timers), name_(std::move(name)), started_(Core::tick()) {}

        ~Scope() {
            if (timers_ != nullptr) timers_->add(name_, Core::since(started_));
        }

        Scope(const Scope&) = delete;
        Scope& operator=(const Scope&) = delete;

      private:
        Timers* timers_;
        std::string name_;
        Core::Steady::time_point started_;
    };

}  // namespace Status
