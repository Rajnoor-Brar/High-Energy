# P5-S02 — Store and stream sources with parallel readers

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P5 — HepMC3 event store and replay |
| Depends on | [P5-S01](P5-S01_store-writer.md), [P3-S03](P3-S03_results-provenance.md) |
| Blocks | [P5-S03](P5-S03_replay-equivalence-events.md), [P6-S01](P6-S01_sharded-rivet.md), [P7-S01](P7-S01_adapter-framework.md) |
| Effort | 1 d |
| Findings / decisions | D8, D13; 11 §4–5 |
| Updated | 2026-09-17 |

## Goal

`Source::StoreReplay` and `Source::Stream` read HepMC3 through one reader implementation (one thread per shard/FIFO → bounded queue → consumers); the planner supports `tool = "store"`.

## Context

- σ, beams and weights from the index (store) or last event (stream).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Probe/Lifecycle.hh:229-267` | bounded queue with backpressure | port |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Store/{Reader,Queue}`, `Source/{StoreReplay,Stream}`
- planner + adapter `store` (`input` = name/hash/path; replay hash)
- beam check against analyses

**Out (non-goals)**

- External generator adapters (P7)

## Design notes

- Only analysis-side quantities allowed on a store generator.

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- C++ sources
- `hekit/adapters/store.py` update

## Verification

| Check | Command | Expected |
|---|---|---|
| Replay | ctest store_replay | events consumed = index total |
| Planner | pytest: store + energies quantity | error with hint |
| Stop | SIGINT during replay | exit 6, partial output |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
