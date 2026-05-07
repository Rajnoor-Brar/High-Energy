#pragma once

// ── Probe ─────────────────────────────────────────────────────────────────────
// ROOT input pipeline: reads TTree branches per event, dispatches callbacks
// across threads, and resolves event counts. The runtime entry point is
// ProbeParallel, which owns input-file path, collection specs, thread count,
// and the run() method.
//
// Submodules:
//   Types.hh         — CollectionSpec, CartesianSpec, PtEtaPhiESpec,
//                      PtEtaPhiMSpec, BranchSpec — branch-layout descriptors
//   BranchControl.hh — BranchControl struct and detectType helper
//   FlatReader.hh    — reads flat (scalar) branches from a TBranch
//   VecReader.hh     — reads std::vector branches from a TBranch
//   Event.hh         — Probe::Event container (label → vector<Lorentz>)
//   Parallel.hh      — runParallel free function: multi-threaded TTree
//                      iteration with per-thread TFile copies
//   EventCount.hh    — resolveEventCount: count TTree entries without
//                      opening multiple files
//   ConfigAid.hh     — parseCollectionsFromToml: build CollectionSpec vector
//                      directly from a toml::table (no Config staging types)
//   ProbeParallel.hh — ProbeParallel class: configurable runtime probe object
// ─────────────────────────────────────────────────────────────────────────────

#include "Probe/Types.hh"
#include "Probe/BranchControl.hh"
#include "Probe/FlatReader.hh"
#include "Probe/VecReader.hh"
#include "Probe/Event.hh"
#include "Probe/Parallel.hh"
#include "Probe/EventCount.hh"
#include "Probe/ConfigAid.hh"
#include "Probe/ProbeParallel.hh"
