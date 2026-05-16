#pragma once

// ── Record ────────────────────────────────────────────────────────────────────
// ROOT output management: Writer-owned histogram/tree containers, queued fill
// requests, provenance metadata, and final ROOT file writing.
//
// Submodules:
//   Types.hh      — RecordKey, branch buffers, and Writer-owned records
//   Type_Methods.hh — inline helper definitions for Types.hh
//   Requests.hh   — queue payloads, barrier states, and ParticleFillView
//   Configs.hh    — HistConfig (binCount, histScale, limits maps, file paths)
//   Meta.hh       — Record::Meta: capture/merge provenance and write
//                   About/ directory to TFile
//   Writer.hh     — Record::Writer declarations and implementation includes
//   Administration.hh — lifecycle, state, configuration, and configureWriter
//   Declaration.hh — Writer data-object declaration methods
//   Recording.hh  — fill request methods and ROOT writing
//   Directives.hh — worker/watchdog loops and queue management
//   Cloning.hh    — worker-local clone allocation and merge-back
// ─────────────────────────────────────────────────────────────────────────────

#include "Record/Types.hh"
#include "Record/Requests.hh"
#include "Record/Configs.hh"
#include "Record/Meta.hh"
#include "Record/Writer.hh"
