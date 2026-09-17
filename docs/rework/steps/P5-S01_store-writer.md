# P5-S01 — Store namespace, store sink and store CLI

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P5 — HepMC3 event store and replay |
| Depends on | [P2-S05](P2-S05_rivet-sink-results-writer.md) |
| Blocks | [P5-S02](P5-S02_store-source-replay.md), [P8-S01](P8-S01_module-sink-yoda.md) |
| Effort | 1 d |
| Findings / decisions | D13; Q9; 11 §1–3 |
| Updated | 2026-09-17 |

## Goal

Runs can write a sharded, indexed, compressed HepMC3 store atomically; `hep store ls|info|verify` inspect it.

## Context

- gz verified; zstd headers present; decide the default first (D-STORE-COMP).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `HepMC3/WriterGZ.h`, `ReaderGZ.h` | compressed I/O | use |
| `legacy/utils/Record/Recording.hh:204-231` | tmp + rename | adapt |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Spike: gz vs zstd on 10k events (size, write/read throughput) → D-STORE-COMP; also shard behaviour in serial mode
- `Store/{Types,Writer,Compression}` + `Sink::Store` (Sharded)
- `events.index.json` + JSON Schema
- `[store]` schema section
- `hekit/store/*` + CLI

**Out (non-goals)**

- Replay (S02)

## Design notes

- Shards keyed by `Parallelism:index`; `.part` → rename on close; index last.

## Tasks

- [ ] Spike + decision
- [ ] Implement writer and sink
- [ ] Python index model + CLI
- [ ] Tests

## Outputs

- `utils/Store*`, `utils/Sink/Store.hh`
- `utils/python/hekit/store/*`
- `tests/spikes/store_compression/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Counts | ctest store_write | Σ shard events = total |
| Verify | truncate one shard; `hep store verify` | reported |
| No zstd | build with zstd disabled | OK; gz only |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
