#pragma once

// ── Analyzer.hh ──────────────────────────────────────────────────────────────────
// Everything that consumes events (05 §2, 13 §2).

#include "Analyzer/Types.hh"
#include "Analyzer/Count.hh"
#if defined(HEKIT_WITH_RIVET)
#include "Analyzer/Modules.hh"
#include "Analyzer/Rivet.hh"
#endif
#if defined(HEKIT_WITH_HEPMC)
#include "Analyzer/Delphes.hh"
#include "Analyzer/Store.hh"
#endif
