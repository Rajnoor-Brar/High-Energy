#pragma once

// ── Sink.hh ──────────────────────────────────────────────────────────────────
// Everything that consumes events (05 §2, 13 §2).

#include "Sink/Types.hh"
#include "Sink/Count.hh"
#if defined(HEKIT_WITH_RIVET)
#include "Sink/Modules.hh"
#include "Sink/Rivet.hh"
#endif
#if defined(HEKIT_WITH_HEPMC)
#include "Sink/Delphes.hh"
#include "Sink/Store.hh"
#endif
