#pragma once

// ── Source.hh ────────────────────────────────────────────────────────────────
// Where events come from (05 §4, 11 §4, 13 §2). `Source::Pythia` generates them; `Source::Replay`
// reads them back from a store or a stream. The run loop holds a `Source::Base` and cannot tell which
// it has, which is what makes "generate once, analyse many" cost nothing in the loop.

#include "Source/Base.hh"
#include "Source/Pythia.hh"
#if defined(HEKIT_WITH_HEPMC)
#include "Source/Replay.hh"
#endif
