# P6-S02 — Shared generation for analysis-only variants

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P6 — Throughput |
| Depends on | [P4-S01](P4-S01_plot-pipeline.md), [P1-S05](P1-S05_plan-render.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | 03 §4 |
| Updated | 2026-09-19 |

## Goal

Points differing only in analysis-side quantities run as one generation with all variants in one Rivet analyzer; plotting selects variants.

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

- [x] Implement
- [x] Tests

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — the planning half was already done; the **plotting half was not**, and testing it end
  to end is what found that. New ctest test `event_groups` (label `slow`, 6 cases). Suite: **19/19
  ctest, 581 Python**.

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Plan | `hep plan --study radius --json` on the real `eic.toml`: **1 group**, `analyses = ["photo_eic:R=0.4", "photo_eic:R=0.7", "photo_eic:R=1.0"]`, three points naming it as their group and listed as its aliases. A control case checks that the `pdf` study is **not** grouped — 4 points, 4 groups — so "one group" cannot just mean the planner groups everything |
  | Output | one point directory for the whole study; its `analysis.yoda` carries `/photo_eic:R=0.4/...` and `/photo_eic:R=1.0/...`, both with filled histograms, and one `/_EVTCOUNT` equal to the run's event count — one generation, not one per variant |
  | Plot | `hep plot --study radius` draws **2 curves** on the two-member page. It drew **4** before this step |

  **The defect this step found: a two-member page got four curves.** `select.curves_for` expanded
  *every* variant it found in a point's file, which is right when one point holds several radii (a
  single point, several curves) and wrong the moment several points **share** one generation — then
  the shared file holds every variant and each point claimed all of them. The planner had grouped the
  points correctly since P1-S05 and the analyzer had booked both variants since P2-S05; nothing had ever
  asked what came out of the far end.

  The fix is small and is the step's "plot variant selection" scope item: `PointFile` now carries the
  point's own `analyses`, and a point that declares one takes only that one. A point that declares
  nothing still gets every variant in its file, so the single-point-several-radii case is unchanged
  (its unit test passes untouched). The legend stopped repeating itself as a side effect — a point
  whose label already reads "R = 0.4" no longer gets "R = 0.4 (R=0.4)" — because the option is only
  appended when a point is actually being split.

  **Deviations**

  1. `tests/e2e/mini.toml` gained a `[quantity.radius]` and a `[study.radius]` (two radii, pinned to
     one PDF) so the chain could be tested on a config small enough for the suite. The existing e2e
     tests are unaffected — `radius` is not in `[sweep].across`, so no other study changes.
  2. The design note "a replay can join a group instead of a live generation" needed no work: P5-S02
     already folds a group's whole analysis set into a replay's hash, and
     `test_two_option_variants_of_one_store_are_one_generation` covers it.
  3. No planner change was needed at all. The step is recorded as `code` and turned out to be mostly
     verification — which is the honest outcome, and the plot defect is why it was worth doing.
