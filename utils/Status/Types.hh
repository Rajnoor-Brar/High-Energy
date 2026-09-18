#pragma once

// ── Status/Types.hh ──────────────────────────────────────────────────────────
// The message kinds of the status protocol (06 §3.2). The set is closed: `hep` logs and ignores a kind
// it does not know, so the protocol can grow without breaking an older reader.

#include <string>
#include <vector>

namespace Status {

    enum class Kind {
        Phase,        // which stage of the run we are in
        Init,         // what the run turned out to be: beams, threads, mode, sinks
        Progress,     // done/total and a rate, rate-limited
        Xsec,         // a cross-section estimate, final or not
        Log,          // a message from a tool, with a level
        Checkpoint,   // outputs written while still running
        Event,        // one event, only with --list
        Summary,      // the run's result
        Heartbeat,    // "still alive", when nothing else has been sent
    };

    inline const char* name(Kind kind) {
        switch (kind) {
            case Kind::Phase: return "phase";
            case Kind::Init: return "init";
            case Kind::Progress: return "progress";
            case Kind::Xsec: return "xsec";
            case Kind::Log: return "log";
            case Kind::Checkpoint: return "checkpoint";
            case Kind::Event: return "event";
            case Kind::Summary: return "summary";
            case Kind::Heartbeat: return "heartbeat";
        }
        return "unknown";
    }

    enum class Level { Debug, Info, Warn, Error };

    inline const char* name(Level level) {
        switch (level) {
            case Level::Debug: return "debug";
            case Level::Info: return "info";
            case Level::Warn: return "warn";
            case Level::Error: return "error";
        }
        return "info";
    }

    // What the event loop updates and the heartbeat thread reads (06 §3.1): counters, never strings.
    struct Progress {
        long long done = 0;
        long long total = 0;
        double rate = 0.0;
        std::vector<long long> workers;
    };

}  // namespace Status
