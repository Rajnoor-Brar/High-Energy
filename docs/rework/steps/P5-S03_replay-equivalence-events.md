# P5-S03 — Replay equivalence and hep events

| Field | Value |
|---|---|
| Status | todo |
| Kind | test |
| Phase | P5 — HepMC3 event store and replay |
| Depends on | [P5-S02](P5-S02_store-source-replay.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | R12; 06 §5 |
| Updated | 2026-09-17 |

## Goal

A stored run replays into the same YODA and σ; `hep events` shows events from configs, points or stores.

## Context

- `pyHepMC3` in the venv.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| P2-S06 comparison helper / `hep compare` | comparison | reuse |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `tests/integration/test_store_replay.py` (slow)
- `hekit/term/events.py`, `hep events`, `hep-run --list`

**Out (non-goals)**

- —

## Design notes

- Equality expected to rounding (same events, different processing order).

## Tasks

- [ ] Test
- [ ] Implement `hep events` renderer (tables, `--tree`, `--final`, `--hard`)

## Outputs

- test + renderer

## Verification

| Check | Command | Expected |
|---|---|---|
| Equivalence | `ctest -L slow -R replay` | identical YODA (to rounding) and σ |
| Events | `hep events <store> -n 2 --final` | table printed |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
