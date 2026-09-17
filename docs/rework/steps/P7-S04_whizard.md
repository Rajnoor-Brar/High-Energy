# P7-S04 — Whizard adapter

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md), [P7-S02](P7-S02_decide-photoproduction-equivalence.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | R7; 04 §5 |
| Updated | 2026-09-17 |

## Goal

Whizard points run through `hep run` with SINDARIN rendering, model particle names and HepMC3 FIFO output.

## Context

- Whizard appends `.hepmc` to the sample name.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 04 §5 | rules | implement |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- insertion-rule check
- PDG → model names
- `beams_momentum`/`sqrts`
- `<stem>.hepmc` FIFO
- parton-level flag
- prepare (grids)

**Out (non-goals)**

- —

## Design notes

- Reject cards that set seed/n_events after the insertion point.

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- `hekit/adapters/whizard.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Toy | e+e- → jj | runs |
| ep | card from S02 (if any) | runs |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
