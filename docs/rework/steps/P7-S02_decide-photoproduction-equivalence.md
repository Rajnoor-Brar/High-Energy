# P7-S02 — Decide cross-generator photoproduction set-ups

| Field | Value |
|---|---|
| Status | todo |
| Kind | decision |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md) |
| Blocks | [P7-S03](P7-S03_sherpa.md), [P7-S04](P7-S04_whizard.md) |
| Effort | 0.5 d |
| Findings / decisions | Q7; D3; D20 |
| Updated | 2026-09-17 |

## Goal

A documented choice of Sherpa and Whizard settings that best match `photo_ep.cmnd` (EPA/WW, Q²max, photon PDF, pTHatMin analogue, MPI), with base cards committed.

## Context

- PhotoProduction is a test bed: document, don't gate.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `configs/PhotoProduction/photo_ep.cmnd` | reference physics | read |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `configs/PhotoProduction/photo_ep.sherpa.yaml`, `photo_ep.sin`
- low-statistics 18x275 comparison

**Out (non-goals)**

- Tuning

## Decision record

- **Question:** Which generator settings count as 'the same physics' as `photo_ep.cmnd`?
- **Options:**
  - per-generator defaults with matched cuts only
  - matched EPA/WW parameters + Q²max + photon PDF where available
  - defer (no external photoproduction)
- **Criteria:**
  - availability of equivalent knobs
  - comparison quality
  - effort
- **Evidence:** (fill in: comparison plots/table)
- **Decision:** (fill in)
- **Consequences:** base cards; 04 §2 note
- **Docs to update:** 04_Generators.md §2, steps/README.md decision register

## Tasks

- [ ] Research knobs
- [ ] Write base cards
- [ ] Run comparison
- [ ] Record

## Outputs

- base cards
- decision record D-Q7

## Verification

| Check | Command | Expected |
|---|---|---|
| Recorded | Decision record | filled |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

n/a.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
