#pragma once

// ── Core/Clock.hh ────────────────────────────────────────────────────────────
// Two clocks, deliberately separate (adapted from `legacy/utils/Utility/Time.hh:15-21`).
//
// `Wall` is what a person reads in a timestamp; it can jump when the system clock is adjusted.
// `Steady` is what durations, rates and deadlines must use, because it only ever moves forward.
// Mixing them is the classic way to get a negative "elapsed" time.

#include <chrono>
#include <cstdio>
#include <string>

namespace Core {

    using Wall = std::chrono::system_clock;      // timestamps in status messages and provenance
    using Steady = std::chrono::steady_clock;    // durations, rates, deadlines
    using Seconds = std::chrono::duration<double>;

    inline double now() {  // seconds since the epoch, as the status protocol writes it
        return std::chrono::duration<double>(Wall::now().time_since_epoch()).count();
    }

    inline Steady::time_point tick() { return Steady::now(); }

    inline double since(Steady::time_point start) {
        return Seconds(Steady::now() - start).count();
    }

    // "1.4 s", "3 m 07 s", "2 h 41 m" — short enough for one line of a dashboard.
    inline std::string durationText(double seconds) {
        char buffer[32];
        if (seconds < 60.0) {
            std::snprintf(buffer, sizeof buffer, "%.1f s", seconds);
        } else if (seconds < 3600.0) {
            const int minutes = static_cast<int>(seconds) / 60;
            std::snprintf(buffer, sizeof buffer, "%d m %02d s", minutes, static_cast<int>(seconds) % 60);
        } else {
            const int hours = static_cast<int>(seconds) / 3600;
            std::snprintf(buffer, sizeof buffer, "%d h %02d m", hours,
                          (static_cast<int>(seconds) % 3600) / 60);
        }
        return buffer;
    }

    // ISO-8601 in UTC, for provenance: sortable and unambiguous.
    inline std::string timestamp(Wall::time_point when = Wall::now()) {
        const std::time_t seconds = Wall::to_time_t(when);
        std::tm parts{};
        gmtime_r(&seconds, &parts);
        char buffer[32];
        std::strftime(buffer, sizeof buffer, "%Y-%m-%dT%H:%M:%SZ", &parts);
        return buffer;
    }

}  // namespace Core
