#pragma once

// ── Sink.hh ──────────────────────────────────────────────────────────────────
// Everything that consumes events (05 §2, 13 §2). `Sink::Modules` in P8-S01 and `Sink::Delphes` in P7-S08.

#include "Sink/Types.hh"
#include "Sink/Count.hh"
#if defined(HEKIT_WITH_RIVET)
#include "Sink/Rivet.hh"
#endif
#if defined(HEKIT_WITH_HEPMC)
#include "Sink/Store.hh"
#endif
