# P6-S01 — Sharded Rivet and concurrency modes

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P6 — Throughput |
| Depends on | [P4-S05](P4-S05_photo-eic-reentrant.md), [P5-S02](P5-S02_store-source-replay.md) |
| Blocks | [P6-S03](P6-S03_bench.md), [P8-S01](P8-S01_module-sink-yoda.md) |
| Effort | 1 d |
| Findings / decisions | A4; 05 §3; risk: merge semantics |
| Updated | 2026-09-17 |

## Goal

`processAsync = on` with one `AnalysisHandler` per worker, merged at the end; `auto` picks sharded only when safe; replay consumers are sharded too.

## Context

- `photo_eic` re-entrant (P4-S05).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Record/Threading.hh:116-236` | quiesce/barrier for checkpoints | idea |
| `legacy/utils/Record/Cloning.hh` | clone/merge shape | idea |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Sink::Rivet` shards (construction + first-event init under a global lock)
- merge → σ → finalize
- `Run` concurrency modes; checkpoint copies off by default

**Out (non-goals)**

- Module sharding (P8-S01 uses the same machinery)

## Design notes

- Non-re-entrant analysis → serial with a status notice.

## Tasks

- [ ] Implement
- [ ] Equivalence test

## Outputs

- C++ changes
- `tests/integration/test_sharded_rivet.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Equivalence | 50k serial vs sharded + `hep compare` | pulls within expectation |
| Totals | sumW, σ | equal |
| Fallback | non-re-entrant test analysis | serial + notice |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Force `serial` in `auto`.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
