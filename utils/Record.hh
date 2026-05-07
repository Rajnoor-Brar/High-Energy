#pragma once

// ── Record ────────────────────────────────────────────────────────────────────
// ROOT output management: histogram/tree containers, the output-file writer,
// provenance metadata, and the fill/write helpers used by analysis handlers.
//
// Submodules:
//   Extract.hh    — event-level extractor function types (Extract::Fn, Event)
//                   used by ExtractHist1D/2D records
//   Types.hh      — RootObjects<Basis>, RootArray, TH1Record, TreeRecord,
//                   EventTH1Record, ExtractHist1D/2D
//   Configs.hh    — HistConfig (binCount, histScale, limits maps, file paths)
//   Meta.hh       — Record::Meta: capture/merge provenance and write
//                   About/ directory to TFile
//   Writer.hh     — Record::Writer class: owns TFile, Paths, HistConfig, Meta,
//                   and the fill-mutex; exposes bind/shutdown/checkpoint
//   Histogram.hh  — fill(), write(), writeAll() free functions for RootObjects
//   Finalizer.hh  — inline bodies for Writer::bind, shutdown, checkpoint,
//                   fatalShutdown (split here to break circular include with
//                   Monitor.hh)
// ─────────────────────────────────────────────────────────────────────────────

#include "Record/Extract.hh"
#include "Record/Types.hh"
#include "Record/Configs.hh"
#include "Record/Meta.hh"
#include "Record/Writer.hh"
#include "Record/Histogram.hh"
#include "Record/Finalizer.hh"
