#pragma once

// ── Core.hh ──────────────────────────────────────────────────────────────────
// The bottom layer: no other namespace of the toolkit, no generator, no analysis framework. Everything
// here is about running a process well — reading its spec, hashing, clocks, signals, exit codes and
// provenance (13 §2).
//
// Cross-namespace code includes this facade, or `Core/Types.hh` alone when that is enough.

#include "Core/Types.hh"
#include "Core/Errors.hh"
#include "Core/Clock.hh"
#include "Core/Paths.hh"
#include "Core/Provenance.hh"
#include "Core/Sha256.hh"
#include "Core/Signals.hh"
#include "Core/Spec.hh"
