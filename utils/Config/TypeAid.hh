#pragma once

#include <optional>
#include <stdexcept>
#include <string>

#include "Types.hh"

namespace Config {
    inline const char* levelToString(RangeSize level) {
        switch (level) {
            case RangeSize::Minute:   return "Minute";
            case RangeSize::Small:    return "Small";
            case RangeSize::Moderate: return "Moderate";
            case RangeSize::Large:    return "Large";
            case RangeSize::Extreme:  return "Extreme";
        }
        throw std::runtime_error("Invalid RangeSize enum value");
    }

    inline RangeSize stringToLevel(const std::string& levelStr) {
        if (levelStr == "Minute")   return RangeSize::Minute;
        if (levelStr == "Small")    return RangeSize::Small;
        if (levelStr == "Moderate") return RangeSize::Moderate;
        if (levelStr == "Large")    return RangeSize::Large;
        if (levelStr == "Extreme")  return RangeSize::Extreme;
        throw std::runtime_error("Unknown limit level: " + levelStr);
    }

    // ── Watch::recordEvent (out-of-line) ─────────────────────────────────────
    // Lock-free: n_real_events and elapsed are both std::atomic.
    inline void Watch::recordEvent(TimePoint now) {
        n_real_events.fetch_add(1, std::memory_order_relaxed);
        elapsed.store(std::chrono::duration_cast<uSeconds>(now - start),
                      std::memory_order_relaxed);
    }

    // ── Watch::freeze (out-of-line) ───────────────────────────────────────────
    // Returns a heap-allocated point-in-time snapshot.  All atomic fields are
    // loaded with relaxed ordering (display-only use; no synchronisation needed).
    inline std::unique_ptr<Watch> Watch::freeze() const {
        auto out = std::make_unique<Watch>();
        out->iEvent.store(iEvent.load(std::memory_order_relaxed),
                          std::memory_order_relaxed);
        out->nEvents       = nEvents;
        out->n_real_events.store(n_real_events.load(std::memory_order_relaxed),
                                 std::memory_order_relaxed);
        out->n_threads     = n_threads;
        out->start         = start;
        out->elapsed.store(elapsed.load(std::memory_order_relaxed),
                           std::memory_order_relaxed);
        return out;
    }
}
