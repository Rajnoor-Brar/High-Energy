#pragma once

// ── Physics ───────────────────────────────────────────────────────────────────
// Lorentz four-vector type alias, particle/event property enumerations, and the
// observable-evaluation helpers used throughout Lambda reconstruction.
//
// Submodules:
//   Types.hh      — Lorentz typedef (TLorentzVector), ParticleProperty and
//                   EventProperty enums, ParticleTraits metadata table
//   TypeAid.hh    — property ↔ name/string converters, tryStringToProperty
//                   parsers used by Config limits loading
//   Kinematics.hh — four-momentum computation helpers (invariant mass, boost,
//                   cos(theta*))
//   Properties.hh — valueOf(Lorentz, ParticleProperty) and
//                   valueOf(vector<Lorentz>, EventProperty) dispatch functions
// ─────────────────────────────────────────────────────────────────────────────

#include "Physics/Types.hh"
#include "Physics/TypeAid.hh"
#include "Physics/Kinematics.hh"
#include "Physics/Properties.hh"
