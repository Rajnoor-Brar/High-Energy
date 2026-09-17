# P4-S03 — mplhep backend and house style

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P4-S01](P4-S01_plot-pipeline.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | F7 (Paint retired) |
| Updated | 2026-09-17 |

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

- [ ] Implement
- [ ] Tests
- [ ] Visual check (record in Log)

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

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
