#pragma once

// ── Paint ─────────────────────────────────────────────────────────────────────
// ROOT presentation layer: colour/style presets and canvas-save helpers used
// for offline histogram rendering (not required during data-taking runs).
//
// Submodules:
//   Types.hh  — colour and marker/line style descriptor types
//   Style.hh  — histogram and canvas style presets (palettes, font sizes)
//   Apply.hh  — apply a style preset to a ROOT TH1/TH2/TGraph object
//   Save.hh   — save a TCanvas to file (PNG, PDF, ROOT) with one call
// ─────────────────────────────────────────────────────────────────────────────

#include "Paint/Types.hh"
#include "Paint/Style.hh"
#include "Paint/Apply.hh"
#include "Paint/Save.hh"
