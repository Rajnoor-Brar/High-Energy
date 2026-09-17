#pragma once

// ── Physics ───────────────────────────────────────────────────────────────────
// Lorentz four-vector type alias, particle/event property enumerations, and the
// observable-evaluation helpers used throughout Lambda reconstruction.
//
// UNIT CONVENTION: energies, momenta, and masses are in GeV throughout the
// project (natural units, c = 1); angles in radians. Config keys spell it out
// where it matters (delta_mass_gev). Anything ingested from external data in
// MeV must be converted at the boundary, never stored.
//
// Submodules:
//   Types.hh      — Lorentz typedef (PxPyPzEVector), ParticleProperty and
//                   EventProperty enums, ParticleTraits metadata table
//   TypeAid.hh    — property ↔ name/string converters, tryStringToProperty
//                   parsers used by Config limits loading
//   Kinematics.hh — four-momentum computation helpers (invariant mass, ΔR,
//                   Δφ, cos-opening, column-wise observables)
//   Properties.hh — valueOf(Lorentz, ParticleProperty) and
//                   valueOf(vector<Lorentz>, EventProperty) dispatch functions
//   Particles.hh  — PDG ID / name / mass / charge table with checked lookup
// ─────────────────────────────────────────────────────────────────────────────

#include "Physics/Types.hh"
#include "Physics/TypeAid.hh"
#include "Physics/Kinematics.hh"
#include "Physics/Properties.hh"
#include "Physics/Particles.hh"
