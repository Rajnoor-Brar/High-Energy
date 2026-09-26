# P2-S04 — Pythia source, event view, analyzer interface and run loop

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S02](P2-S02_pythia-parallel-spike.md), [P2-S03](P2-S03_core-status.md), [P1-S05](P1-S05_plan-render.md) |
| Blocks | [P2-S05](P2-S05_rivet-analyzer-results-writer.md), [P7-S05](P7-S05_madgraph.md) |
| Effort | 1 d |
| Findings / decisions | 00 §4.3 (generator behaviours); utils defect: unchecked readFile/init |
| Updated | 2026-09-18 |

## Goal

`hep-run SPEC` runs Pythia from cards with checked errors and forced run control, fans events to (empty) analyzers, stops cleanly, and supports `--check`, `--plain`, `--capabilities`, `--list N`.

## Context

- 05 §1–4; exit codes 06 §3.3; decisions from P2-S02.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `sources/PhotoProduction/generator.cc` | card order, quiet default, processAsync forcing, output-after-init | preserve |
| `legacy/lambda/sources/_Lambda_Data.cc:43-50` | cooperative skip | fallback per D-Q2 |
| `legacy/utils/Probe/Types.hh:148-203` | access patterns | shape `Events::View` helpers |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Source::Pythia`, `Events::View` (lazy per-worker HepMC), `Analyzer::Base`/`Sharded`, `Run::{Context,Result,Loop}`, `utils/apps/hep-run.cc`
- Warnings from the Pythia Logger → `log` status messages

**Out (non-goals)**

- Rivet analyzer (S05)
- sharded mode (P6-S01)

## Added by P2-S02

- Chunk with `chunk = threads · ceil(target / threads)`, the remainder in the last chunk, so the event set
  matches an unchunked run (D-Q2); record the effective chunk size in provenance.
- Combine σ from the instances with `foreach` (D-Q1); `PythiaParallel` has no σ error of its own.
- **Check `len(run.seeds.instances) == run.threads` before `init()` and exit 1 otherwise** (D-SEEDS):
  Pythia indexes the seed list without bounds checking, so a short list is undefined behaviour.

## Design notes

- Run control from the spec overrides cards (events, threads, `Parallelism:seeds`, `Next:numberCount = 0`).
- `--list N`: generate N events, emit `event` messages (06 §5), no analyzers.

## Tasks

- [x] Implement
- [x] ctest cases below

## Outputs

- `utils/{Events,Source,Analyzer,Run}*`
- `utils/apps/hep-run.cc`
- `tests/cpp/run_*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Good card | `hep-run spec.toml --check` | exit 0 |
| Init failure | spec with `Photon:ProcessType = 2` | exit 3 |
| Bad key | spec with a misspelled setting | exit 1 |
| Capabilities | `hep-run --capabilities \| jq .components` | lists built components |
| Stop | SIGINT during a 1M run | exit 6 within one chunk |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented: `utils/{Events,Analyzer,Source,Run}` facades + submodules and a rewritten
  `utils/apps/hep-run.cc`, 942 lines. Loop order is fixed in one place: configure → init → start analyzers →
  [chunk: events → checkpoint → stop?] → final forced progress → finish analyzers → summary.

  **Verification, all rows measured** (specs written by `hekit.plan`, run from `output/scratch/`):

  | Row | Result |
  |---|---|
  | good card `--check` | exit 0, `phase=checked`, √s = 318.12 GeV, 2 threads |
  | init failure (`Photon:ProcessType = 2`) | exit 3, "Pythia failed to initialise" |
  | bad key (`ThisKey:doesNotExist`) | exit 1, "Pythia rejected the card", names the card |
  | `--capabilities` | exit 0, `spec_schema: 2`, components `["rivet", "hepmc"]` |
  | SIGINT during a 400 000-event run | exit 6 in 2.97 s total, stopped at a chunk boundary, `stopped: true` |

  Also checked because they are part of the same contract: no arguments → 2, unknown option → 2, a
  second spec → 2, `--list` without a number → 2, absent spec → 1, garbled TOML → 1, missing `[source]`
  → 1, missing card → 1, short seed list → 1 (`[run.seeds] instances has 1 entries for 2 threads`,
  refused **before** Pythia starts, D-SEEDS).

  Reference run, 200 events on 2 threads: σ = 70 819 ± 2212 pb, chunk 20, seeds read back as planned
  `[718623745, 718623746]`, 200/200 progress, wall 0.11 s (2.2 s of it LHAPDF init, which dominates any
  short run).

  **Tests:** `tests/cxx/test_run_rules.cc` (ctest `run_rules`) for the arithmetic — the D-Q2 chunk rule
  as a property over 3200 (threads, wanted) pairs, the D-Q1 σ combination including a zero-weight
  instance, `Analyzer::Count` and an empty `Events::View`; `tests/python/run/test_hep_run.py`, 25 cases
  driving the real binary against real planned specs (12 s, four Pythia initialisations shared through
  module-scoped fixtures). Suite: 9/9 ctest, 359 Python.

  **Deviations and defects found**

  1. **`workers` was wrong.** `PythiaParallel::run` returns attempts *per chunk*, and I was assigning
     them to the progress message, so a 200-event run reported `workers [10, 10]`. 06 §3 shows the
     counts adding up to `done` (`done: 642113`, 20 workers × ~32000), so they are now cumulative
     accepted events per worker, counted in the callback from `Parallelism:index`. Caught by the test,
     not by reading.
  2. **Status timestamps had 1-second resolution.** `Status::number` formats with `%.10g`, which on a
     Unix epoch (1.79e9) is exactly whole seconds — every rate and ETA computed from `t` would have been
     garbage. Added `Status::stamp` (`%.6f`) for the timestamp field only; guarded in both status tests.
  3. **A written spec held a relative path.** `hep plan --write out/dir` (a relative `--write`) left a
     relative card path in the spec, so the spec was only runnable from the directory it was written
     from. `spec.relocated()` now resolves the target: 03 §7 says a resolved spec has no relative paths.
  4. **`Analyzer/Types.hh` and `Run/Types.hh` named `Core::RunRecord` without including `Core/Provenance.hh`**
     and only compiled because `hep-run` includes `Core.hh` first. The new test, which includes
     `Analyzer.hh` alone, failed to compile — which is the point of a test that does not include the facade.
  5. `Source::chunkFor` and `Source::Combine` were split out of `Source/Pythia.hh` into
     `Source/Types.hh`, so D-Q1 and D-Q2 can be checked without linking a generator.
  6. The chunk target is `min(events, 20000) / 10` floored at 1, then rounded up to a whole number of
     workers — about a second of generation, which is what makes Ctrl-C feel immediate. Recorded in
     `Run::Result.chunk` and in the summary, as this step asked.
  7. `Pythia8::Logger` has no `getCounts()`; it is iterable over its message → count map, so
     `reportWarnings` iterates it directly. Each distinct message is reported once.
  8. Beams are `[2212, -11]` (proton × positron) in this card. Kept as measured, per the standing
     instruction not to be pedantic about e+ vs e-.
