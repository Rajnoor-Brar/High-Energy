#pragma once

// ── Utility ───────────────────────────────────────────────────────────────────
// Formatting helpers used by Monitor and Record for human-readable output.
//
// Submodules:
//   Number.hh — numberFormat: integer formatting with thousands separators
//   Time.hh   — timeString (wall-clock), durationString (μs → human-readable
//               "Xh Ym Zs") used in progress logs and terminal reports
// ─────────────────────────────────────────────────────────────────────────────

#include "Utility/Number.hh"
#include "Utility/Time.hh"
