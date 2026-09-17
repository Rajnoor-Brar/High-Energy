# P8-S04 — Decide the derived-tables format (deferred)

| Field | Value |
|---|---|
| Status | todo |
| Kind | decision |
| Phase | P8 — Modules, YODA results, Phys, ML |
| Depends on | [P8-S01](P8-S01_module-sink-yoda.md) |
| Blocks | — |
| Effort | 0.1 d |
| Findings / decisions | D23; Q10 |
| Updated | 2026-09-17 |

## Goal

The derived per-candidate table question is recorded with options, criteria and a revisit trigger.

## Context

- Deferred by user decision.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 12 §5, 05 §5 | context | read |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- decision record only

**Out (non-goals)**

- Implementation

## Decision record

- **Question:** How should per-candidate / ML-feature tables be produced and stored?
- **Options:**
  - Python replay of the store to Parquet
  - C++ module writing Parquet/Arrow
  - RNTuple (derived tables only)
  - YODA only (no tables)
- **Criteria:**
  - ML tooling fit
  - dependencies
  - consistency with D13–D15
- **Evidence:** (deferred)
- **Decision:** Deferred; trigger: first ML training dataset
- **Consequences:** none now
- **Docs to update:** 10_Roadmap.md D23, steps/README.md decision register

## Tasks

- [ ] Record

## Outputs

- decision record D-DERIVED

## Verification

| Check | Command | Expected |
|---|---|---|
| Recorded | Decision record | status deferred with trigger |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

n/a.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
