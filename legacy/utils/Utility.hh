#pragma once

// ── Utility ───────────────────────────────────────────────────────────────────
// Formatting helpers used by Monitor and Record for human-readable output.
//
// Submodules:
//   Number.hh    — numberFormat: integer formatting with thousands separators
//   Time.hh      — clock aliases (TimePoint/uSeconds/Seconds), timeString,
//               durationString (μs → human-readable "Xh Ym Zs")
//   RootTypes.hh — shared ROOT branch/value type helpers
//   RootAid.hh   — checked ROOT access (get/require/openRead), thread-safety
//               init, gROOT/gStyle RAII guards
//   Toml.hh      — shared TOML table merge, directory-config loader,
//               numeric validators
//   Paths.hh     — project-root anchored path resolution
//   Sha256.hh    — in-process SHA-256 (provenance/integrity hashing)
//   Signals.hh   — SIGINT/SIGTERM graceful-stop flag for event loops
// ─────────────────────────────────────────────────────────────────────────────

#include "Utility/Number.hh"
#include "Utility/Time.hh"
#include "Utility/RootTypes.hh"
#include "Utility/RootAid.hh"
#include "Utility/Toml.hh"
#include "Utility/Paths.hh"
#include "Utility/Sha256.hh"
#include "Utility/Signals.hh"
