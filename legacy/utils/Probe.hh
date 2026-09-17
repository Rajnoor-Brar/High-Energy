#pragma once

// ── Probe ─────────────────────────────────────────────────────────────────────
// ROOT input pipeline: reads TTree branches per event, dispatches callbacks
// across threads, and resolves event counts. The runtime entry points are
// ProbeParallel and ProbeIMT.
//
// Submodules:
//   Types.hh         — specs (EventParticleSpec, …), Event/Feed, BranchType
//   BranchControl.hh — checked branch access, coordinate specs, partitioning
//   ConfigAid.hh     — [probe] TOML section → ProbeConfig (parseProbeConfig)
//   Readers.hh       — reader class declarations, BranchHandle
//   Parallel.hh      — ProbeParallel declaration
//   ParallelIMT.hh   — ProbeIMT declaration (TTreeProcessorMT path)
//   Methods.hh       — reader implementations (FlatReader, Array/RowJoin/Feed)
//   Configuration.hh — ProbeParallel::configureProbe validation + setup
//   Lifecycle.hh     — entry bounds, queue push/pop, stop/reset state
//   Threading.hh     — streamEvents/streamFeed worker + collector loops
// ─────────────────────────────────────────────────────────────────────────────

#include "Probe/Types.hh"
#include "Probe/BranchControl.hh"
#include "Probe/ConfigAid.hh"
#include "Probe/Readers.hh"
#include "Probe/Parallel.hh"
#include "Probe/ParallelIMT.hh"

#include "Probe/Methods.hh"
#include "Probe/Configuration.hh"
#include "Probe/Lifecycle.hh"
#include "Probe/Threading.hh"
