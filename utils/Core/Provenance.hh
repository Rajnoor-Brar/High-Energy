#pragma once

// ── Core/Provenance.hh ───────────────────────────────────────────────────────
// What produced a result (07 §2; field list adapted from `legacy/utils/Record/Meta.hh:25-110`).
//
// The C++ side records only what it alone knows: its own build, the host it ran on, the versions it
// linked against and what the run did. `hekit.prov` adds the git state, the configuration and the
// resources (P3-S03). Everything here is best-effort: provenance must never be the reason a run fails.

#include <array>
#include <string>
#include <utility>
#include <vector>
#include <unistd.h>

#include "Core/Clock.hh"

namespace Core {

    struct Build {
        std::string version = "unknown";
        std::string type = "unknown";
        std::string compiler;
        std::string date;
        std::string components;
    };

    inline std::string hostname() {
        std::array<char, 256> buffer{};
        if (::gethostname(buffer.data(), buffer.size() - 1) != 0) return "unknown";
        return buffer.data();
    }

    inline std::string compilerName() {
#if defined(__clang__)
        return "clang " __clang_version__;
#elif defined(__GNUC__)
        return "gcc " __VERSION__;
#else
        return "unknown";
#endif
    }

    // The build is described by compile definitions, so a binary can always say what it is.
    inline Build build() {
        Build found;
#if defined(HEKIT_VERSION)
        found.version = HEKIT_VERSION;
#endif
#if defined(HEKIT_BUILD_TYPE)
        found.type = HEKIT_BUILD_TYPE;
#endif
        found.compiler = compilerName();
        found.date = __DATE__;
        return found;
    }

    struct RunRecord {
        std::string point;
        std::string hash;
        std::string origin;
        std::string started;                 // ISO-8601 UTC
        double wall_seconds = 0.0;
        long long events_requested = 0;      // what the spec asked for
        long long attempted = 0;             // next() calls: Main:numberOfEvents (P0-S04)
        long long accepted = 0;              // events that reached the sinks
        double xsec_pb = 0.0;
        double xsec_error_pb = 0.0;
        bool stopped = false;                // a signal ended it, so the outputs are partial
        int threads = 0;
        long long chunk = 0;                 // the effective chunk size (P2-S02, D-Q2)
        std::string mode = "serial";         // serial | sharded (P6-S01)
        long long seed = 0;                  // the point seed, the base of its block (03 §5)
        std::vector<long long> seeds;        // read back from the instances, not assumed
        // Aggregated by source: message → how many times. A warning is not an error, but a run that
        // produced 10⁵ of them is not the same result as one that produced none.
        std::vector<std::pair<std::string, long long>> warnings;
    };

}  // namespace Core
