#pragma once

// ── Record ────────────────────────────────────────────────────────────────────
// ROOT output management: Writer-owned histogram/tree containers, queued fill
// requests, provenance metadata, and final ROOT file writing.
//
// Submodules:
//   Extract.hh    — event-level extractor function types (Extract::Fn, Event)
//                   used by ExtractHist1D/2D records
//   Types.hh      — RecordKey, branch buffers, Writer-owned records, and
//                   temporary RootObjects/RootArray compatibility types
//   Requests.hh   — queue payloads, barrier states, and ParticleFillView
//   Configs.hh    — HistConfig (binCount, histScale, limits maps, file paths)
//   Meta.hh       — Record::Meta: capture/merge provenance and write
//                   About/ directory to TFile
//   Writer.hh     — Record::Writer class: owns TFile, records, queues, and the
//                   scribe thread
//   Histogram.hh  — legacy fill/write helpers retained during migration
//   Finalizer.hh  — inline bodies for Writer::bind, finish, fatalShutdown
// ─────────────────────────────────────────────────────────────────────────────

#include "Record/Extract.hh"
#include "Record/Types.hh"
#include "Record/Requests.hh"
#include "Record/Configs.hh"
#include "Record/Meta.hh"
#include "Record/Writer.hh"
#include "Record/Histogram.hh"
#include "Record/Finalizer.hh"
