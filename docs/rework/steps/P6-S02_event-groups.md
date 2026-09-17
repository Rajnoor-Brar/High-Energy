# P6-S02 — Shared generation for analysis-only variants

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P6 — Throughput |
| Depends on | [P4-S01](P4-S01_plot-pipeline.md), [P1-S05](P1-S05_plan-render.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | 03 §4 |
| Updated | 2026-09-17 |

## Goal

Points differing only in analysis-side quantities run as one generation with all variants in one Rivet sink; plotting selects variants.

## Context

- Canonical option paths (`/photo_eic:R=0.4/…`).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py` option handling (legacy) | analysis strings | reference |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- planner grouping
- spec with multiple analysis variants
- plot variant selection

**Out (non-goals)**

- —

## Design notes

- A replay can join a group instead of a live generation.

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- planner/plot changes

## Verification

| Check | Command | Expected |
|---|---|---|
| Plan | `hep plan --study radius --json` | 1 group, 3 variants |
| Output | YODA paths | `/photo_eic:R=0.4/…` present |
| Plot | `hep plot --study radius` | 3 curves |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert (one generation per point).

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
