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
//   Administration.hh — AsyncLogger construction, start/stop, config state
//   Directive.hh  — publish/countEvent, run loop, periodic actions
//   Configure.hh  — configureMonitor: loads TOML pacing into AsyncLogger
// ─────────────────────────────────────────────────────────────────────────────

#include "Monitor/Types.hh"
#include "Monitor/Logger.hh"
#include "Monitor/Methods.hh"
#include "Monitor/Render.hh"
#include "Monitor/Report.hh"
#include "Monitor/Administration.hh"
#include "Monitor/Directive.hh"
#include "Monitor/Configure.hh"
#include "Monitor/Timer.hh"
