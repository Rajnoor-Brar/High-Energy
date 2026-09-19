# P6-S01 — Sharded Rivet and concurrency modes

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P6 — Throughput |
| Depends on | [P4-S05](P4-S05_photo-eic-reentrant.md), [P5-S02](P5-S02_store-source-replay.md) |
| Blocks | [P6-S03](P6-S03_bench.md), [P8-S01](P8-S01_module-sink-yoda.md) |
| Effort | 1 d |
| Findings / decisions | A4; 05 §3; risk: merge semantics |
| Updated | 2026-09-19 |

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

- [x] Implement
- [x] Equivalence test

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — implemented the sharded mode end to end and measured it. Suite: **18/18 ctest, 579
  Python** (the new ctest test is `sharded_rivet`, label `slow`, 11 cases).

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Equivalence | 50 000 events, four threads, the same seeds: serial and sharded analysed the **same 49 994 events** and produced YODAs whose every object is **identical to the precision YODA writes** (`rtol = 0`) — 53 of 55, with the two exceptions explained below. Better than the row's "pulls within expectation" |
  | Totals | `sumW` equal exactly; σ and its error equal exactly (`/_XSEC` 71 319.86094 ± 131.5107189 in both, and equal to `run.summary.json`) |
  | Fallback | three of them: a non-re-entrant analysis (`MC_PRINTEVENT`) → serial, naming it; a build without thread-safe FastJet → serial, naming the macro; an explicit `sharded` on an analysis that turns out to cluster jets → the run **stops**, exit 5 |

  It is also faster, which is the point of the phase: **1.67x on four threads** at 50 k events
  (10.98 s → 6.57 s) with `MC_FSPARTICLES` + `MC_XS`, and 2.3x at 2 000 events.

  **The finding that shaped the step: jet clustering cannot be sharded** (00/B31). Before writing any
  code I went looking for what the analyses call underneath, and:

  - `SISConePlugin::{stored_plugin, stored_particles, stored_siscone}` are **process-wide statics**
    mutated inside `run_clustering` (the clustering cache), and `siscone::local_ranlux_state` is a
    global RNG its split-merge draws from. That is true of **every** FastJet build;
  - this FastJet is additionally built with `FASTJET_HAVE_LIMITED_THREAD_SAFETY` **undefined**.

  Two threads clustering at once do not crash — they change each other's jets. `photo_eic` runs kT,
  anti-kT *and* SISCone, so it can never be sharded, and the step's "50 k serial vs sharded" row had
  to be measured with a jet-free analysis instead.

  Whether an analysis clusters is only knowable after `Analysis::init()`, which Rivet calls on the
  first event, so the question is answered **twice**: `auto` refuses before any event (without a
  thread-safe FastJet, *no* analysis may be sharded, because any of them might cluster and there is
  no way to ask yet) and an explicit `sharded` stops right after `init()` if a `FastJets` turns up. A
  jet race produces a plausible histogram with the wrong numbers in it, which is worse than no
  histogram — so it is a refusal, not a warning.

  **A second defect, latent since P2-S04** (00/B32). `PythiaParallel` runs the callback on its
  **worker threads in both modes** — `processAsync = off` only wraps it in a mutex
  (`PythiaParallel.cc:201-208`). So any sink exception was unwinding through `std::thread` into
  `std::terminate`: a Rivet error mid-run would have killed the process instead of producing an exit
  code and a message. Both sources now catch at that boundary and rethrow on the main thread.

  **`fill` merges, `set` does not.** `MC_XS` is `Reentrant: true` and every *filled* object of it
  merges exactly, but one object — `XS` — is `set()` from the per-event running σ. Four snapshots
  cannot be reconstructed into one, `AnalysisHandler::merge` falls back to copying, and that object
  is the only difference between the two modes. Neither value is even reproducible run to run,
  because Pythia's callback mutex imposes no *order*, so "the last event" is whichever worker got
  there first — the test asserts that both stay estimates of the same σ rather than that they
  differ, which is what an earlier draft got wrong and flaked on once. The rule matters for P8-S01:
  a module's results must be filled, not set. The run's own σ is unaffected — it comes from the
  generator and is applied once to the merged total (D-Q1).

  **Design notes**

  1. **`Events::View` now carries a slot beside its worker.** `worker` is provenance (which instance
     or shard made the event), `slot` is which consumer is carrying it. They are the same for a
     generator and differ for a replay, where k consumers pop from one queue fed by n shards.
     Sharding the store on `slot` would silently re-shard a replayed store; sharding Rivet on
     `worker` would hand one handler to two threads. Hence two numbers, and a unit test for it.
  2. **Sinks are prepared before the generator initialises.** The mode is decided from what the sinks
     say about themselves, and a typo in an analysis name now costs a second rather than a Pythia
     `init()`.
  3. **`Sink::Sink` gained `shards(int)` and `serialReason()`.** Shards are built on the main thread
     because Rivet's analysis loader is a process-wide registry; the reason is a sentence, because
     "sharding is off" without "because X" sends the reader to the source.
  4. **A sharded replay keeps the chunk boundary**: consumers run a chunk's worth and are joined, and
     only then does the main thread checkpoint and read the stop flag. Same shape as the generator
     (D-Q2), and a checkpoint never runs while a sink is being called.
  5. **`Store::Writer` is now safe for concurrent writers** — the shard map is guarded while it
     grows, the total is atomic, and one lock per shard is held across the HepMC3 write. Uncontended
     for a generator (one worker per thread); it is what stops a replay's two consumers interleaving
     one shard.
  6. **A periodic dump is dropped in sharded mode**, with a notice: one handler is a fraction of the
     run, and a file that looks like a result and is a quarter of one is worse than no file.

  **Deviations**

  1. The step's equivalence row named the project's own analysis; it cannot be sharded (see above),
     so equivalence is measured with `MC_FSPARTICLES` + `MC_XS` and `photo_eic` gets its own two
     tests: that `auto` still runs it (serially, with a notice) and that an explicit `sharded`
     refuses it.
  2. `Concurrency::Locked` exists in the enum but no sink uses it yet; the loop already routes
     anything that is not `Sharded` through one mutex, so it costs nothing to leave.
  3. `[run].mode` is a machine key (like `threads`): it changes the wall clock, not the events, and
     is deliberately not part of a point's identity.
  4. Three new `hep-run` messages were written with em dashes and then made ASCII: the Python side
     has a locale fallback and the C++ side has none, and `hep-run`'s output had been all-ASCII until
     this step (00/B29 again, the fifth time).
