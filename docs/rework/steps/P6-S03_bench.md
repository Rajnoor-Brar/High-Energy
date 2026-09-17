# P6-S03 — hep bench

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P6 — Throughput |
| Depends on | [P6-S01](P6-S01_sharded-rivet.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | A4; 05 §3 |
| Updated | 2026-09-17 |

## Goal

`hep bench CONFIG` measures generation only, generation with sinks, and replay with k readers, and recommends a concurrency mode.

## Context

- Decision rule 05 §3.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Monitor/Timer.hh` (ported in P2-S03) | timers | reuse |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- CLI + recommendation logic

**Out (non-goals)**

- Automatic tuning

## Design notes

- Small event counts; results cached per machine.

## Tasks

- [ ] Implement
- [ ] Unit-test the recommendation logic

## Outputs

- `hekit` bench command

## Verification

| Check | Command | Expected |
|---|---|---|
| Runtime | `hep bench tests/e2e/mini.toml` | < 2 min |
| Logic | pytest | recommendations match table |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
