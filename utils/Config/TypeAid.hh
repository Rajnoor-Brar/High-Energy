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
    // Increments nRealEvents and updates elapsed under the per-Watch mutex.
    // Replaces the three function-static `stateMutex` blocks that previously
    // lived in Lambda::pythiaAnalysis / rootAnalysis / dataGenerator.
    inline void Watch::recordEvent(TimePoint now) {
        std::lock_guard<std::mutex> lock(eventMutex_);
        ++nRealEvents;
        elapsed = std::chrono::duration_cast<uSeconds>(now - start);
    }

    // ── Watch::freeze (out-of-line) ───────────────────────────────────────────
    // Returns a heap-allocated point-in-time snapshot. The atomic counter is
    // loaded once under the eventMutex_; the result is completely independent
    // of *this and safe to read off-thread or pass to a shared_ptr.
    inline std::unique_ptr<Watch> Watch::freeze() const {
        auto out = std::make_unique<Watch>();
        std::lock_guard<std::mutex> lock(eventMutex_);
        out->iEvent.store(iEvent.load());
        out->serial                    = serial;
        out->srPadding                 = srPadding;
        out->nEvents                   = nEvents;
        out->nRealEvents               = nRealEvents;
        out->nDigits                   = nDigits;
        out->nThreads                  = nThreads;
        out->printInterval             = printInterval;
        out->heartbeat_interval        = heartbeat_interval;
        out->terminal_refresh_interval = terminal_refresh_interval;
        out->program_stall_threshold   = program_stall_threshold;
        out->barInterval               = barInterval;
        out->checkInterval             = checkInterval;
        out->start                     = start;
        out->elapsed                   = elapsed;
        return out;
    }
}