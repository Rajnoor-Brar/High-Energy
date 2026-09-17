# P4-S02 — hep plot with the rivet-mkhtml backend

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P4-S01](P4-S01_plot-pipeline.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md) |
| Effort | 0.75 d |
| Findings / decisions | R4 |
| Updated | 2026-09-17 |

## Goal

`hep plot` (pages and `--points`) produces the same pages as `ydmrg`/`ydplt`.

## Context

- 07 §4 backends.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:1116` `plot_arguments` | argv construction | port |
| `tools/ydplt:44-76`, `tools/ydmrg:43-92` | flow | replace |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/plot/backends/mkhtml.py`
- CLI

**Out (non-goals)**

- mpl backend (S03)

## Design notes

- Compare intermediate files (page set, legends, `.plot` overrides, remapped data YODAs), not HTML.

## Tasks

- [ ] Implement
- [ ] Golden comparisons

## Outputs

- backend + CLI
- `tests/integration/test_plot_vs_legacy.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Golden | P0-S04 mini run + 2 legacy studies copied to scratch | intermediates equal |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
