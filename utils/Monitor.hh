#pragma once

// ── Monitor ───────────────────────────────────────────────────────────────────
// Runtime observability: progress reporting, heartbeat logging, and fatal-stall
// detection. The central class is AsyncLogger, which runs a background thread
// that periodically writes a run-stat file and renders a progress bar.
//
// Submodules:
//   Types.hh      — RunPhase/ThreadPhase enums, PacingInfo, RunSnapshot,
//                   ThreadSnapshot value types
//   Snapshot.hh   — snapshot builders (makeSnapshot), ETA calculation,
//                   runStatString/threadStatString formatters
//   Render.hh     — terminal rendering (renderProgressBar, terminalReport),
//                   log-text builders (buildLogText, outputLog, writeEmergencyLog)
//   Logger.hh     — AsyncLogger class: background heartbeat thread,
//                   publish/finish interface, fatal-stall detection
//   ConfigAid.hh  — configureMonitor: loads pacing intervals from TOML into
//                   AsyncLogger
// ─────────────────────────────────────────────────────────────────────────────

#include "Monitor/Types.hh"
#include "Monitor/Snapshot.hh"
#include "Monitor/Render.hh"
#include "Monitor/Logger.hh"
#include "Monitor/ConfigAid.hh"
#include "Monitor/Timer.hh"
