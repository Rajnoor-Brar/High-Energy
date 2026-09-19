#pragma once

// ── Store.hh ─────────────────────────────────────────────────────────────────
// The HepMC3 event store (11, decision D13): a directory of per-worker shards plus an index that is
// the source of truth for replaying them. `Source::Store` (P5-S02) reads what this writes.

#include "Store/Types.hh"
#include "Store/Compression.hh"
#include "Store/Writer.hh"
