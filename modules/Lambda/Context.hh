#pragma once

#include <mutex>

#include "Types.hh"
#include "Config.hh"    // Config::Watch / Config::Register
#include "Monitor.hh"   // Monitor::AsyncLogger

// ── Lambda handler context bundles ───────────────────────────────────────────
// Each analysis handler receives a *context* struct instead of six individual
// arguments. The bundle groups the persistent collaborators that are the same
// across every call into a given run; per-call arguments (Pythia worker, event
// data, thread id) remain as explicit parameters.
//
// Two structs, not one: the output target differs between the histogram handlers
// (AnalysisContext → RootArray) and the data-generation handler
// (GenerationContext → DataObjects + treeMutex).

namespace Lambda {

    // Used by: pythiaAnalysis, rootAnalysis
    struct AnalysisContext {
        RootArray&            histograms;   // histogram sets (shared across threads)
        const Parameters&     parameters;  // physics cuts (read-only)
        Config::Watch&        logging;     // live event counters
        Monitor::AsyncLogger& asyncLogger; // progress publisher
    };

    // Used by: dataGenerator
    struct GenerationContext {
        DataObjects&          data;        // TTree branches (shared across threads)
        std::mutex&           treeMutex;   // serialises TTree::Fill calls
        Config::Watch&        logging;     // live event counters
        Monitor::AsyncLogger& asyncLogger; // progress publisher
    };

} // namespace Lambda
