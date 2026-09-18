# P4-S03 — mplhep backend and house style

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P4-S01](P4-S01_plot-pipeline.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | F7 (Paint retired) |
| Updated | 2026-09-18 |

## Goal

`hep plot --backend mpl` renders publication figures using the same `.plot` keys and a house mplhep style.

## Context

- 07 §4.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/configs/defaults/Paint.toml`, `legacy/misc/root_macros/saveHist.C:20-177` | fonts, margins, sizes, palette | translate to `hekit.mplstyle` |
| `legacy/utils/Paint/Resolve.hh:124-140,269-280` | preset chain, glob | optional idea |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/plot/plotfile.py` parser → kwargs
- `hekit/plot/backends/mpl.py`
- `hekit/plot/styles/hekit.mplstyle`

**Out (non-goals)**

- ROOT canvases

## Design notes

- Ratio panel and reference handling mirror mkhtml semantics.

## Tasks

- [x] Implement
- [x] Tests
- [x] Visual check (record in Log)

## Outputs

- backend, parser, style

## Verification

| Check | Command | Expected |
|---|---|---|
| Parser | pytest | Title/XLabel/YLabel/LogY/XMin/XMax/RatioPlot* mapped |
| Smoke | pytest image render | files produced |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `hekit/plot/backends/mpl.py` (310 lines),
  `hekit/plot/styles/hekit.mplstyle` (58) and the `[plot.style]` config section, with 17 tests.
  Suite: 560 Python, 13/13 ctest.

  **Verification**

  | Row | Result |
  |---|---|
  | Parser | `Title`, `XLabel`, `YLabel`, `LogX/LogY`, `XMin/XMax`, `YMin/YMax`, `RatioPlot`, `RatioPlotY{Min,Max,Label}`, `LegendOnly`, `LegendTitle` and `MainPanel` all mapped, with the types the keys imply; an unparseable number is dropped rather than guessed, and an unknown key is kept under its own name |
  | Smoke | a page renders to `.png` and `.pdf`, both non-trivial; a reference is drawn and becomes the ratio denominator; voided bins stay gaps; `matplotlib` is on `Agg` before anything is drawn |

  **Visual check** (asked for by this step). Drawn from the real 4-point PDF study of
  `configs/PhotoProduction/eic.v2.toml` at 20 k events:
  `hep plot … --backend mpl` produced `photo_eic_d01-x01-y01.png` with

  - the analysis's own labels rendered as LaTeX — `$E_T$ [GeV]` and
    `$\mathrm{d}\sigma/\mathrm{d}E_T$ [pb/GeV]` — straight from `photo_eic.plot`;
  - `LogY=1` honoured, and the x range 5–41 GeV taken from the auto-range override the pipeline
    generated;
  - four curves in the colour-blind-safe cycle with their sweep legends (MSTW 2008 LO, NNPDF 2.3
    QCD+QED LO/NLO, PDF4 LHC21.40), error bars, and a ratio panel against the first curve;
  - the house look: 9×6 in, ticks inward on all four sides, no grid, no legend frame.

  The figure is the one a paper would take, which is what this backend is for (F7: it replaces
  Paint — a TOML-configured ROOT canvas becomes a `.plot` file plus a style sheet).

  **Notes**

  1. **The style is the legacy one translated, not invented.** `hekit.mplstyle` carries the numbers
     from `legacy/configs/defaults/Paint.toml` — the 900×600 canvas becomes 9×6 in at 100 dpi, the
     0.12/0.05/0.12/0.08 margins become the subplot margins, `ticks_x`/`ticks_y` become ticks inward
     on all sides — and `saveHist.C`'s font sizes become point sizes.
  2. **One label source.** Both backends read the analysis's `.plot` file, so a relabelled histogram is
     relabelled in both. The auto-range file is read after it, overriding only `XMin`/`XMax`.
  3. `LegendTitle` was being ignored until the visual check: `photo_eic.plot` states the cuts there
     (`$-3.5 < \eta < 3.5, k_T$ alg`) and mkhtml draws it as a legend header, so this does too.
  4. A `#` in a colour in an `.mplstyle` file starts a comment, so the palette is written as bare hex.
     matplotlib reported it and drew anyway — the figures of the first run were silently on the
     default cycle.
  5. `[plot.style]` (name, figure, font_size, dpi, formats, ratio) is new in the schema, and the
     committed `docs/rework/reference/config.md` is regenerated.
  6. One bad plot is skipped with its reason rather than failing the page: a study is fifteen
     histograms, and losing fourteen to one is not a trade worth making.
