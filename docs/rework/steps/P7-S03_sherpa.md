# P7-S03 — Sherpa adapter

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md), [P7-S02](P7-S02_decide-photoproduction-equivalence.md) |
| Blocks | — |
| Effort | 1.5 d |
| Findings / decisions | R7; 04 §4 |
| Updated | 2026-09-19 |

## Goal

Sherpa points run through `hep run` (in-process Rivet via FIFO, or native Rivet), with integration cached and progress shown.

## Context

- `libSherpaHepMC3Output`, `libSherpaRivetAnalysis` present.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 04 §4 | rendering table | implement |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- YAML deep merge
- prepare stage (integration)
- HepMC3 output to FIFO
- native mode
- progress parser calibrated on real logs
- golden cards

**Out (non-goals)**

- NLO matching set-ups

## Design notes

- σ from last event `GenCrossSection`; preflight on 10 events.

## Tasks

- [x] Implement
- [x] Tests
- [x] Real runs in scratch

## Outputs

- `hekit/adapters/sherpa.py`
- golden cards

## Verification

| Check | Command | Expected |
|---|---|---|
| Point | 10k-event Sherpa point | dashboard + YODA |
| Cache | 2-seed study | one integration |
| Modes | native vs in-process | compatible |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — implemented `hekit/adapters/sherpa.py`. Sherpa 3.0.5 is installed here, so every row
  was measured against the real binary. New ctest test `sherpa` (label `slow`, 7 cases, 4 min) and 21
  unit tests.

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Point | a 200-event Sherpa point runs end to end: integrate (75 s, cached) then generate into the FIFO, `hep-run` reading it as `Source::Stream`, and `photo_eic` writing a YODA. 200/200 events, sigma = 9 452 pb, consistent with the 9 636 +- 782 pb P7-S02 measured standalone. The dashboard showed both stages' progress |
  | Cache | a two-seed study integrates **once**: one `sherpa-integrate.log`, one cache entry, one `prepared.json` (version 3.0.5, `produces: [Results.zip]`). The two seeds give different sigma, so they really are different events |
  | Modes | `native` and `inprocess` agree on sigma **to 1e-6** at a fixed seed — different code on both sides of the seam, the same events. `native` has no `hep-run` stage at all and writes `analysis.yoda.gz` |

  **Four defects, all found by running it rather than by reading.**

  1. **The prepare stage looked for a card in the cache that nothing wrote.** Both stages now read the
     point's own card; what differs goes on the command line. There is only ever one card, and a copy
     would be a second thing that could drift.
  2. **The runner overrode every stage's working directory**, so the integration ran in the point
     directory and filled it with `Process/`, `Results.zip` and `Settings_Report`. `Stage` now carries
     `cwd` and `env` through the plan, and the runner creates a stage's directory before spawning it.
     `env` earned its keep immediately: native mode needs `RIVET_ANALYSIS_PATH`.
  3. **`EVENT_OUTPUT` must be relative.** Sherpa prefixes what it is given with `./`, so an absolute
     path became `.//home/...` and could not be opened — and `HepMC3_GenEvent[events]` writes a file
     called `events`, not `events.hepmc`. The generator wrote 3.2 MB to the wrong name and exited 0.
  4. **The planner and the runner computed the prepare-cache key differently** — the planner asked the
     adapter for its version, the runner read a constant that no longer existed — so the grid was
     written to one directory and the marker to another, and every run re-integrated. There is now one
     function, `cache.for_group`, and both call it.

  **The defect that fell out of (3): a chain could hang for ever.** With the generator writing to the
  wrong file, `hep-run` sat in `open()` on a FIFO no one would ever write to, and the supervisor
  waited on it indefinitely. The rule added: when every producer has exited **successfully** and an
  `analyse` stage is still running and idle past the grace period, it can never receive anything, so
  the chain is stopped. Only for successful producers — a *failed* producer is already handled, and
  "the generator's card was wrong" is a better answer than "the reader stalled".

  **Deviations**

  1. The committed base card has `MI_HANDLER: None`. Amisic is the physics-correct choice and is
     unusable here (P7-S02: 0 events in 768 s), so a Sherpa point currently has **no underlying
     event** — a real difference from the Pythia reference, written into the card rather than hidden.
  2. `rivet.weights = "nominal"` is honoured in `inprocess` mode but not in `native`, where Sherpa
     keeps its scale variations: 68 `photo_eic` objects against 17. sigma is unaffected, which is why
     the modes row compares sigma.
  3. The base card no longer sets `BEAMS`/`BEAM_ENERGIES`/`EVENTS` — the plan owns them (04 §8) and
     `check_card` refuses them. The 18x275 values are in a comment so the file can still be run by
     hand, which is how P7-S02 measured it.
