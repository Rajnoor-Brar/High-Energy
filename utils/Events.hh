#pragma once

// ── Events.hh ────────────────────────────────────────────────────────────────
// The per-event view every analyzer is handed (05 §1, 13 §2). Includes the HepMC conversion only when the
// build has HepMC3.

#include "Events/Types.hh"

#if defined(HEKIT_WITH_HEPMC)
#include "Events/Convert.hh"
#endif
