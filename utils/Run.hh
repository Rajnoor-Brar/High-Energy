#pragma once

// ── Run.hh ───────────────────────────────────────────────────────────────────
// The event loop: one source, several sinks, chunked so that stopping works (05 §3, 13 §2).

#include "Run/Types.hh"
#include "Run/Loop.hh"
