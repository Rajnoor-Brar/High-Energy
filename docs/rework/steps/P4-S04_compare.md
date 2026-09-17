# P4-S04 — hep compare and shared statistics

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P4-S01](P4-S01_plot-pipeline.md) |
| Blocks | [P4-S05](P4-S05_photo-eic-reentrant.md), [P9-S01](P9-S01_proc-fits.md) |
| Effort | 0.5 d |
| Findings / decisions | 07 §5 |
| Updated | 2026-09-17 |

## Goal

`hep compare` prints χ²/ndf, bins used and max pull per histogram and writes `compare.md`; the statistics module is shared with `hep proc`.

## Context

- Absorbs `tests/tools/yodacmp.py` from P2-S06.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tests/tools/yodacmp.py` | comparison | promote |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/results/{stats,compare}.py`
- CLI

**Out (non-goals)**

- Fits (P9)

## Design notes

- Aligned-bin rule from `align_to_edges`; voided bins excluded.

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- modules + CLI

## Verification

| Check | Command | Expected |
|---|---|---|
| Known χ² | pytest synthetic fixtures | expected values |
| Alignment | pytest mismatched binning | only aligned bins used |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
