# P7-S07 — Herwig adapter

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S06](P7-S06_decide-herwig-rebuild.md), [P7-S01](P7-S01_adapter-framework.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | R7; 04 §6 |
| Updated | 2026-09-17 |

## Goal

Herwig points run through `hep run` with cached `read`, parallel `-j N` jobs feeding a multi-input stream source.

## Context

- Only if P7-S06 decided to rebuild.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 04 §6 | rendering, stages | implement |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- read/run stages
- `-j N` → N FIFOs
- ThePEG particle names
- golden cards checked against Herwig 7.3
- per-job seeds recorded

**Out (non-goals)**

- —

## Design notes

- Step status becomes `dropped` if P7-S06 decides 'never'.

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- `hekit/adapters/herwig.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Toy | `hep run` Herwig toy | YODA produced |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
