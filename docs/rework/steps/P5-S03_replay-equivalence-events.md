# P5-S03 — Replay equivalence and hep events

| Field | Value |
|---|---|
| Status | done |
| Kind | test |
| Phase | P5 — HepMC3 event store and replay |
| Depends on | [P5-S02](P5-S02_store-source-replay.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | R12; 06 §5 |
| Updated | 2026-09-19 |

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

- [x] Test
- [x] Implement `hep events` renderer (tables, `--tree`, `--final`, `--hard`)

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — implemented `hekit/term/events.py` and `hep events`; the equivalence test landed with
  P5-S02 and is registered as the ctest test `store_replay` (label `slow`). Suite: **17/17 ctest,
  615 Python**. **Phase P5 is complete.**

  **Verification, both rows measured**

  | Row | Result |
  |---|---|
  | Equivalence | `ctest -L slow -R store_replay`: a replayed store gives a YODA **identical** to the generation's — 39 objects, 1004 numbers, χ² = 0 — and σ equal to the index's to the precision YODA writes. The design note allowed "equality to rounding"; it is exact, because the same events go through the same analyzers in the same order |
  | Events | `hep events <store> -n 2 --final` prints the table of 06 §5; `--tree`, `--hard` and `--from FILE` all render; a config is inspected too |

  **Where events come from is uniform.** A store, any HepMC3 file, or a **config** — and a config is
  turned into the other two by generating a few events into a scratch store and rendering that. One
  renderer, one data path, and no second definition of "what an event is". 06 §5 describes this as
  `hep-run --list`; a temporary store is the same thing with a renderer that can show particles, and
  it reuses the pipeline instead of widening the status protocol to carry particle records.

  **Reading a compressed shard without decompressing it.** `pyHepMC3` has no compressed reader and
  `zstandard` is not in the venv, so a shard is streamed through `zstd -dc` / `gzip -dc` and cut off
  one event past the last one asked for, then handed to HepMC3's own ASCII reader. Looking at three
  events never costs more than three events, which on a 100 GB shard is the whole point.

  **What the table shows** (06 §5): index, particle **name** (from the `particle` package, falling
  back to the PDG number), status, mothers → daughters, pT, η, φ, m — with the role colour-coded
  (beam, hard, final, shower). η is reported as infinite for a particle exactly along the beam rather
  than as a huge number, and the table prints an em dash for it.

  **A per-event σ is labelled `sigma(so far)`.** It is the generator's running estimate at that
  event, not the run's merged value — that is in the store's index (11 §4), and confusing the two is
  how a plot gets normalised wrongly.

  **Deviations**

  1. The equivalence test lives in `tests/integration/test_store_replay.py`, written in P5-S02 when
     the replay landed; this step verified it rather than writing it twice.
  2. `hep-run --list` is unchanged: it still emits one `event` status message per event (index,
     particles, process), which is what a supervisor shows. The particle table is `hep events`.
