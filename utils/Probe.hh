#pragma once

// ── Probe ─────────────────────────────────────────────────────────────────────
// ROOT input pipeline: reads TTree branches per event, dispatches callbacks
// across threads, and resolves event counts. The runtime entry point is
// ProbeParallel, which owns input-file path, particle specs, thread count,
// event partitioning, queue coordination, and the run() method.
//
// Submodules:
//   Types.hh         — ParticleSpec/CollectionSpec, CartesianSpec, PtEtaPhiESpec,
//                      PtEtaPhiMSpec, BranchSpec — branch-layout descriptors
//   BranchControl.hh — BranchControl struct and detectType helper
//   FlatReader.hh    — reads flat (scalar) branches from a TBranch
//   VecReader.hh     — reads std::vector branches from a TBranch
//   Event.hh         — Probe::Event container (label → vector<Lorentz>)
//   Parallel.hh      — runParallel compatibility shim around ProbeParallel
//   EventCount.hh    — resolveEventCount: count TTree entries without
//                      opening multiple files
//   ConfigAid.hh     — parseCollectionsFromToml: build ParticleSpec vector
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
