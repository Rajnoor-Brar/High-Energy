#pragma once

// ── Results.hh ───────────────────────────────────────────────────────────────
// Everything a run leaves on disk (07 §1–2, 13 §2). YODA is the only result format (D14): Rivet
// objects, module objects and processing outputs all land in the same kind of file, so one merge, one
// plotter and one comparison serve them all.
//
// `Results::Booker`/`Worker`/`Final` — the declare-once, clone-per-worker booking that user modules
// use — arrive with `Module` in P8-S01.

#include "Results/Writer.hh"
#include "Results/Summary.hh"
