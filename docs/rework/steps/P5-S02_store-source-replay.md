# P5-S02 — Store and stream sources with parallel readers

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P5 — HepMC3 event store and replay |
| Depends on | [P5-S01](P5-S01_store-writer.md), [P3-S03](P3-S03_results-provenance.md) |
| Blocks | [P5-S03](P5-S03_replay-equivalence-events.md), [P6-S01](P6-S01_sharded-rivet.md), [P7-S01](P7-S01_adapter-framework.md) |
| Effort | 1 d |
| Findings / decisions | D8, D13; 11 §4–5 |
| Updated | 2026-09-19 |

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

- [x] Implement
- [x] Tests

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — implemented `Store/{Queue,Reader}.hh`, `Source/{Base,Replay}.hh` and
  `hekit/adapters/store.py`; the run loop now holds a `Source::Base` and cannot tell a generator from
  a replay. Suite: **17/17 ctest, 598 Python**.

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Replay | events consumed = the index's total, `source: store`, one reader per shard, **no seeds** (a replay chose none). Better than the row asks: the replayed YODA is **identical** to the generation's — 39 objects, 1004 numbers, χ² = 0 |
  | Planner | a store plus a generation-side quantity is refused for every such type (`setting`, `beams`, `energies`, `seed`, `card`, `generator`, `events`), naming the quantity and hinting `tool = "pythia"`; analysis-side ones are allowed |
  | Stop | SIGINT during a replay → exit 6 with `analysis.partial.yoda` and `stopped: true`, or 0 if it finished first — the same contract as a generating run (06 §3.3) |

  **Design notes**

  1. **`hep` reads the index, `hep-run` reads the spec.** `[source.store]` carries the index's facts
     (shards, workers, σ ± err, beams, weights, counts), so the C++ side needs no JSON parser and the
     index stays the source of truth (11 §4). That is the same split as everywhere else: judgement
     and JSON in Python, the event loop in C++ (02 §2).
  2. **One reader implementation for stores and streams.** A FIFO is a store with one shard and no
     index; σ then comes from the last event, which is the only value there is (04 §8).
  3. **The queue is the memory bound.** Readers run ahead of the analysis but not arbitrarily far;
     `stop()` wakes a blocked reader *and* a waiting consumer, which is what makes Ctrl-C during a
     FIFO read bounded at all.
  4. **"Every producer finished" is not "stop".** The consumer drains what is left first — getting
     that wrong silently loses the tail of the last shard, so it has its own test.
  5. `Source::Base` is new: the loop needed one interface for two sources that share almost nothing
     inside. `Source::Pythia` now implements it, unchanged otherwise.

  **The defect this step found**

  **Two option variants of one store became two generations sharing one directory**, and the second
  overwrote the first. `identity_inputs` folded each *point's* analyses into a replay's hash, so
  `photo_eic:R=0.4` and `photo_eic:R=1.0` hashed differently — but they replay the same events, and
  03 §4 says an option variant is not a separate generation. The analyses are now folded in after
  grouping, from the **group's** whole set: two variants stay one read, a different analysis set is a
  different point (11 §4), and replaying the same store the same way is the same point, so the skip
  rule recognises it. Found by replaying a real store, not by a unit test; there are four tests for
  it now.

  **Deviations**

  1. The step names `Source::StoreReplay` and `Source::Stream`; both are `Source::Replay`, because
     they differ only in whether an index exists — two classes would have been one class and a flag.
     `kind()` reports `store` or `stream`, and the summary records which.
  2. A store is resolved by path, point name or `sha256:…`, searching this project first and then the
     whole results tree — a replay config rarely lives in the project directory whose events it reads.
  3. `run.summary.json` gained `source`, so a result says whether its events were generated or
     replayed.
