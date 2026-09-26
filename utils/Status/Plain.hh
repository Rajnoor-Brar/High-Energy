#pragma once

// ── Status/Plain.hh ──────────────────────────────────────────────────────────
// The fallback for a `hep-run` nobody is watching: no fd 3, so progress goes to stderr as plain lines
// (06 §3.1). Running the binary by hand has to stay pleasant, because that is what people do when
// something is wrong.

#include <cstdio>
#include <string>

#include "Core/Clock.hh"
#include "Status/Types.hh"

namespace Status {

    // "[ 45%] 450000/1000000  1180 ev/s  eta 7 m 46 s"
    inline std::string progressLine(const Progress& progress) {
        char buffer[160];
        if (progress.total > 0) {
            const double fraction = static_cast<double>(progress.done) / static_cast<double>(progress.total);
            const double remaining = progress.rate > 0.0
                                         ? (progress.total - progress.done) / progress.rate
                                         : 0.0;
            std::snprintf(buffer, sizeof buffer, "[%3.0f%%] %lld/%lld  %.0f ev/s  eta %s",
                          100.0 * fraction, progress.done, progress.total, progress.rate,
                          remaining > 0.0 ? Core::durationText(remaining).c_str() : "?");
        } else {
            std::snprintf(buffer, sizeof buffer, "%lld events  %.0f ev/s", progress.done, progress.rate);
        }
        return buffer;
    }

}  // namespace Status
