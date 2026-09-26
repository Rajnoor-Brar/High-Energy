#pragma once

// ── Run/Types.hh ─────────────────────────────────────────────────────────────
// What one run produced (05 §3, 07 §2).

#include <cstdint>
#include <string>
#include <vector>

#include "Core/Types.hh"
#include "Core/Provenance.hh"
#include "Analyzer/Types.hh"

namespace Run {

    struct Result {
        Core::Counts counts;
        double xsec_pb = 0.0;
        double xsec_error_pb = 0.0;
        bool xsec_known = false;
        bool stopped = false;                 // a signal ended it, so the outputs are partial
        double wall_seconds = 0.0;
        std::int64_t chunk = 0;               // the effective chunk size (D-Q2)
        int threads = 1;
        std::vector<std::int64_t> seeds;      // read back from the instances
        std::vector<Analyzer::Output> outputs;
        std::string summary_path;             // run.summary.json, written after the analyzers finish
        Core::Exit exit = Core::Exit::Ok;
    };

}  // namespace Run
