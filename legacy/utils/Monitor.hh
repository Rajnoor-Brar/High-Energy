#pragma once

// ── Monitor ───────────────────────────────────────────────────────────────────
// Runtime observability: progress reporting, heartbeat logging, and fatal-stall
// detection. The central class is AsyncLogger; Logger.hh declares the class,
// and the implementation is split into small inline fragments below.
//
// Submodules:
//   Types.hh      — RunPhase/ThreadPhase enums, PacingInfo, RunSnapshot,
//                   ThreadSnapshot value types
//   Logger.hh     — AsyncLogger declaration only
//   Methods.hh    — snapshot builders, ETA/phase helpers, stat string helpers
//   Render.hh     — terminal rendering and status-line rendering
//   Report.hh     — log/report string builders and file writes
//   Lifecycle.hh  — AsyncLogger construction, start/stop, config state
//   Threading.hh  — publish/countEvent, run loop, periodic actions
//   Configure.hh  — configureMonitor: loads TOML pacing into AsyncLogger
// ─────────────────────────────────────────────────────────────────────────────

// Record/Writer.hh must enter the include graph before Monitor/Report.hh:
// Report's inline bodies use the Writer class, while Record/Lifecycle.hh (a
// Writer fragment) uses Report's functions. Including Writer.hh here first
// makes Monitor.hh safe to include in any order; without it, a TU that
// includes Monitor.hh before Record.hh fails mid-cycle.
#include "Record/Writer.hh"

#include "Monitor/Types.hh"
#include "Monitor/Logger.hh"
#include "Monitor/Methods.hh"
#include "Monitor/Render.hh"
#include "Monitor/Report.hh"
#include "Monitor/Lifecycle.hh"
#include "Monitor/Threading.hh"
#include "Monitor/Configure.hh"
#include "Monitor/Timer.hh"
