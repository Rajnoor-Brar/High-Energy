# P7-S03 — Sherpa adapter

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md), [P7-S02](P7-S02_decide-photoproduction-equivalence.md) |
| Blocks | — |
| Effort | 1.5 d |
| Findings / decisions | R7; 04 §4 |
| Updated | 2026-09-17 |

## Goal

Sherpa points run through `hep run` (in-process Rivet via FIFO, or native Rivet), with integration cached and progress shown.

## Context

- `libSherpaHepMC3Output`, `libSherpaRivetAnalysis` present.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 04 §4 | rendering table | implement |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- YAML deep merge
- prepare stage (integration)
- HepMC3 output to FIFO
- native mode
- progress parser calibrated on real logs
- golden cards

**Out (non-goals)**

- NLO matching set-ups

## Design notes

- σ from last event `GenCrossSection`; preflight on 10 events.

## Tasks

- [ ] Implement
- [ ] Tests
- [ ] Real runs in scratch

## Outputs

- `hekit/adapters/sherpa.py`
- golden cards

## Verification

| Check | Command | Expected |
|---|---|---|
| Point | 10k-event Sherpa point | dashboard + YODA |
| Cache | 2-seed study | one integration |
| Modes | native vs in-process | compatible |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
