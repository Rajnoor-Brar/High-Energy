#pragma once

// ── Probe ─────────────────────────────────────────────────────────────────────
// ROOT input pipeline: reads TTree branches per event, dispatches callbacks
// across threads, and resolves event counts. The runtime entry points are
// ProbeParallel and ProbeIMT.
// ─────────────────────────────────────────────────────────────────────────────

#include "Probe/Types.hh"
#include "Probe/BranchControl.hh"
#include "Probe/ConfigAid.hh"
#include "Probe/Readers.hh"
#include "Probe/Parallel.hh"
#include "Probe/ParallelIMT.hh"

#include "Probe/Methods.hh"
#include "Probe/Configuration.hh"
#include "Probe/Administration.hh"
#include "Probe/Directives.hh"
