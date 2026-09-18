# P5-S01 — Store namespace, store sink and store CLI

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P5 — HepMC3 event store and replay |
| Depends on | [P2-S05](P2-S05_rivet-sink-results-writer.md) |
| Blocks | [P5-S02](P5-S02_store-source-replay.md), [P8-S01](P8-S01_module-sink-yoda.md) |
| Effort | 1 d |
| Findings / decisions | D13; Q9; 11 §1–3 |
| Updated | 2026-09-19 |

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

- [x] Spike + decision
- [x] Implement writer and sink
- [x] Python index model + CLI
- [x] Tests

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `utils/Store/{Types,Compression,Writer}.hh`, `utils/Sink/Store.hh` and
  `hekit/store/{index,verify,cli}.py` with the committed JSON Schema (≈1 500 lines including tests).
  Suite: 15/15 ctest, 573 Python.

  **The spike, and decision D-STORE-COMP: `zst`.** `tests/cxx/spikes/store_compression.cc` generates
  real photoproduction events with the project's own card and writes *the same* events through each
  codec. At 10 000 events:

  | codec | bytes/event | ratio | write ev/s | read ev/s |
  |---|---:|---:|---:|---:|
  | none | 29 197 | 1.00 | 6 333 | 6 249 |
  | gz | 10 223 | 2.86 | 1 086 | 4 461 |
  | **zst** | **9 866** | **2.96** | **2 289** | **5 624** |

  zstd is smaller, **2.1× faster to write** and 1.26× faster to read: no axis favours gz, so `zst` is
  the default and `gz` the fallback for a build without it. The same numbers held at 2 000 events, so
  this is not a sample-size artefact.

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Counts | ctest `store_writer`: 30 events round-robin over 3 workers → 3 shards of 10, index `events` = Σ shards, every shard hashed, nothing left in `.part` |
  | Verify | a truncated shard is caught by **size alone** (`events.1.hepmc.zst is 1877341 bytes, the index says 1882341 (truncated)`, exit 1); a single changed byte needs `--deep`; a missing shard, an undeclared shard and a half-written store are each named |
  | No zstd | a build configured without zstd reports `"compression": "gz"`, passes the store test (55 checks), and refuses a `zst` spec with *"this build cannot write 'zst' event stores — it has: none, gz"* |

  End to end: `hep run … --set store.enabled=true` wrote two stores (400 events, 2 shards each,
  3.8–4.0 MB), and `hep store ls` / `hep store verify --deep` read and checked them.

  **Design notes**

  1. **The order is the design.** Shards stream into `.part` with no lock, are closed, hashed and
     renamed, and only then is `events.index.json` written atomically. So a directory *with* an index
     is a store whose shards are all closed and hashed, and one without is unfinished rather than
     silently short — the D22/00-B3 rule applied to a directory.
  2. **The shard is keyed by the worker that generated the event** (`Parallelism:index`), not by the
     thread running the callback: with `processAsync = off` callbacks move between threads, so
     anything else would interleave two workers in one shard and make the layout depend on the
     concurrency mode (11 §1).
  3. **An index whose shards do not add up is refused**, not written. That is a bug in the writer, and
     a store that lies about its own size is worse than a missing one.
  4. A partial store (`stopped: true`) **verifies**: it is a run that was stopped, its events are
     real, and it is reported as partial rather than failed.

  **Deviations and defects found**

  1. **The spike was wrong twice before it was right**, and both are worth recording: my first card
     was hand-written and ran at ~15 ev/s (the project's card does 2 750), and `Pythia8ToHepMC`
     **reuses one `GenEvent`**, so holding `getEventPtr()` 10 000 times would have measured one event
     written 10 000 times. The events are copied now.
  2. **`#include "Store.hh"` from `utils/Sink/Store.hh` included itself**: a quoted include looks in
     its own directory first, so the facade was never read and `Store::` did not exist. It includes
     the three submodules directly, with a comment saying why.
  3. **`hekit.store` re-exported `verify` over its own module** — the same trap as `prov.stamp` in
     P3-S03. The rule is now stated in the package docstring: a package must not re-export a function
     under one of its module names.
  4. `[store].compression` defaults to `zst` in the schema, and the committed
     `docs/rework/reference/config.md` is regenerated. 11 §1 carries the spike's table.
  5. `pkill -f` matched my own command line again and killed the shell mid-edit. Noted for the third
     time: never `pkill -f` a pattern that the running command contains.
