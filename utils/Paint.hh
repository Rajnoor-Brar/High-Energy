#pragma once

// ── Paint ─────────────────────────────────────────────────────────────────────
// Offline ROOT plotting layer. Paint reads [paint] TOML figure recipes, resolves
// ROOT objects from an output file, and renders TH1/TH2/TGraph figures through
// the Paint::Illustrator facade.
//
// Submodules:
//   Types.hh       — style, source, result, book, and render-plan structs
//   Style.hh       — colour parsing and style/table merge helpers
//   Book.hh        — default/user TOML loading
//   Resolve.hh     — preset/source resolution and ROOT object lookup
//   Apply.hh       — apply styles to TH1/TH2/TGraph objects
//   Render.hh      — single/overlay/grid drawing
//   Save.hh        — PNG/PDF/SVG/ROOT export helpers
//   Illustrator.hh — high-level load/resolve/dry-run/render facade
// ─────────────────────────────────────────────────────────────────────────────

#include "Paint/Types.hh"
#include "Paint/Style.hh"
#include "Paint/Book.hh"
#include "Paint/Resolve.hh"
#include "Paint/Apply.hh"
#include "Paint/Save.hh"
#include "Paint/Render.hh"
#include "Paint/Illustrator.hh"
