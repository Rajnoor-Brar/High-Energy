#pragma once

// ── Phys.hh ──────────────────────────────────────────────────────────────────
// The physics a module writes with: what a PDG code means, what can be taken from a four-vector,
// which particles of an event you wanted, and a jet definition from a string (13 §2).
//
// It sits beside `Store`, `Results` and `ML` in the layering — above `Events`, below `Module` — so
// it may know about HepMC3 and FastJet and knows nothing of analyzers, sources or the run. That is what
// makes it usable from a Rivet analysis and a module alike.
//
// The submodules gate themselves on what the build has, so this facade is safe to include anywhere:
// `Pdg` is plain arithmetic and always present, the four-vector ones need HepMC3, and `Jets` needs
// FastJet.
//
// Replaces `legacy/utils/Physics/`, which was the same ideas on `ROOT::Math::PxPyPzEVector` and so
// cost every user of it a ROOT dependency and a conversion per particle.

#include "Phys/Pdg.hh"

#if defined(HEKIT_WITH_HEPMC)
#include "Phys/Types.hh"
#include "Phys/Kinematics.hh"
#include "Phys/Select.hh"
#endif

// Jets need both: FastJet to cluster, and the four-vector to convert to and from.
#if defined(HEKIT_WITH_FASTJET) && defined(HEKIT_WITH_HEPMC)
#include "Phys/Jets.hh"
#endif
