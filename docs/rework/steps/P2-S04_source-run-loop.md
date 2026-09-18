# P2-S04 — Pythia source, event view, sink interface and run loop

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S02](P2-S02_pythia-parallel-spike.md), [P2-S03](P2-S03_core-status.md), [P1-S05](P1-S05_plan-render.md) |
| Blocks | [P2-S05](P2-S05_rivet-sink-results-writer.md), [P7-S05](P7-S05_madgraph.md) |
| Effort | 1 d |
| Findings / decisions | 00 §4.3 (generator behaviours); utils defect: unchecked readFile/init |
| Updated | 2026-09-17 |

## Goal

`hep-run SPEC` runs Pythia from cards with checked errors and forced run control, fans events to (empty) sinks, stops cleanly, and supports `--check`, `--plain`, `--capabilities`, `--list N`.

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

- `Source::Pythia`, `Events::View` (lazy per-worker HepMC), `Sink::Base`/`Sharded`, `Run::{Context,Result,Loop}`, `utils/apps/hep-run.cc`
- Warnings from the Pythia Logger → `log` status messages

**Out (non-goals)**

- Rivet sink (S05)
- sharded mode (P6-S01)

## Added by P2-S02

- Chunk with `chunk = threads · ceil(target / threads)`, the remainder in the last chunk, so the event set
  matches an unchunked run (D-Q2); record the effective chunk size in provenance.
- Combine σ from the instances with `foreach` (D-Q1); `PythiaParallel` has no σ error of its own.
- **Check `len(run.seeds.instances) == run.threads` before `init()` and exit 1 otherwise** (D-SEEDS):
  Pythia indexes the seed list without bounds checking, so a short list is undefined behaviour.

## Design notes

- Run control from the spec overrides cards (events, threads, `Parallelism:seeds`, `Next:numberCount = 0`).
- `--list N`: generate N events, emit `event` messages (06 §5), no sinks.

## Tasks

- [ ] Implement
- [ ] ctest cases below

## Outputs

- `utils/{Events,Source,Sink,Run}*`
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

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
