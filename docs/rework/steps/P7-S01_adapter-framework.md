# P7-S01 — External adapter framework and prepare cache

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P3-S05](P3-S05_hep-run-command.md), [P5-S02](P5-S02_store-source-replay.md) |
| Blocks | [P7-S02](P7-S02_decide-photoproduction-equivalence.md), [P7-S03](P7-S03_sherpa.md), [P7-S04](P7-S04_whizard.md), [P7-S05](P7-S05_madgraph.md), [P7-S07](P7-S07_herwig.md), [P7-S08](P7-S08_delphes-external.md) |
| Effort | 1 d |
| Findings / decisions | F9; 04 §1, §8 |
| Updated | 2026-09-19 |

## Goal

External generators plug in as adapters producing stages; prepare steps are cached; FIFO wiring, progress parsers, event-count checks and beam-key clash rules are shared.

## Context

- 04 §1–2, §8; 06 §4 parser table.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `hekit/adapters/{base,pythia,store}.py` | interfaces | extend |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Adapter protocol, `Stage` data, parser registry
- prepare cache `results/<project>/.cache/<tool>/<prep-hash>/`
- `generator` quantity with per-tool keys

**Out (non-goals)**

- Specific generators (S03–S07)

## Design notes

- A fake external generator (replays a store to a FIFO) exercises the framework.

## Tasks

- [x] Implement
- [x] Fake generator test

## Outputs

- `hekit/adapters/*`
- `tests/python/adapters/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Fake generator | `hep run` with the fake tool | completes via `Source::Stream` |
| Cache | 2-seed study | prepare runs once |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — implemented `hekit/adapters/{registry,base,cache}.py`, the phased supervisor and the
  external stage chain. New ctest test `external_adapter` (label `slow`, 7 cases) and 30 unit tests
  for the shared rules. Suite: **21/21 ctest, 626 Python**.

  **Verification, both rows measured**

  | Row | Result |
  |---|---|
  | Fake generator | `hep run` with the stand-in tool completes through `Source::Stream`: 300 events, `source: stream`, no seeds of its own — and the YODA is **identical** to the Pythia run whose store the events came from (39 objects, 1004 numbers). The events are not merely delivered, they arrive unchanged |
  | Cache | a two-seed study runs the prepare step **once**: one log, one cache entry, one `prepared.json`. A second `hep run --rerun` of the same point reuses it |

  **The stand-in is the point.** There is no Sherpa here, and waiting for one would have left the
  framework untested until P7-S03. `tests/tools/fake_generator.py` behaves like an external generator
  in the two ways that matter — a cacheable prepare step, and generating by writing HepMC3 into a
  FIFO — and its events come from a real event store, so the histograms that come out of the FIFO can
  be compared with the ones that went in. A framework test that invented its own events could only
  check that processes started.

  **Two defects, both found by running it.**

  1. **00/B33 — `hep-run --check` on a stream hung forever.** `Source::Replay::initialise()` started
     its readers, and opening a FIFO for reading blocks until a writer appears, which a preflight
     never starts. Every external-generator run would have hung before generating anything. Fixed:
     `initialise()` validates the inputs *without opening them* (a FIFO only has to exist; a shard is
     still checked as a regular file) and the readers start in `run()`. The FIFO is also created
     before the preflight rather than before the run, because `--check` opens the source.
  2. **A seed study prepared once per point.** The stage chain is built when the plan is built, and
     at that moment the cache is empty for every point. Whether a prepare step is still needed is a
     question about *now*, so the run re-asks it per point — which is the entire reason the cache
     exists. Nothing marked the cache ready either; the marker is now written after a successful
     prepare, and only when the outputs the stage promised exist.

  **What 04 §8's "since there is one producer" is worth.** Streaming a **one**-worker store
  reproduces the generation's YODA exactly. Streaming a **two**-worker store scales every histogram
  by 1.8 %, because the last event carries one worker's running σ rather than the merged value — the
  same `sigma(so far)` trap as P5-S03 and P6-S01, from a third direction. Every external generator
  here is a single process so the rule holds, and 04 §8 now says so explicitly.

  **Design notes**

  1. **The tool list lives in one place.** `[generator].tool`'s `choices` and the `ADAPTERS` dict
     were two copies that could disagree; the schema now reads the registry. That needed `Field
     .choices` to accept a callable, resolved when it is used rather than when the field is declared
     — otherwise a tool registered after import would be valid to the registry and invalid to the
     schema.
  2. **`StageSpec` gained a phase.** Stages of one phase run together; a phase runs only after the
     one before it. A generator and the `hep-run` reading its FIFO must be concurrent or they
     deadlock; a prepare step must finish before either starts. Two numbers express both, and the
     chain stays a closed list (02 §3).
  3. **Attribution looks across phases**, so a failed prepare is the reason reported rather than
     whatever the next phase did (00/B20).
  4. **An adapter never spawns anything.** It returns `Stage` data — argv, env, cwd, log, parser,
     timeout, produces — and the supervisor runs all of them the same way.

  **Deviations**

  1. The fake adapter lives in `tests/tools/`, not in `hekit`: it is a test fixture, and shipping a
     generic "run any command" tool would be a design decision the roadmap did not make.
  2. `render`/`validate`/`probe` are on the protocol and on the fake, but the planner still calls the
     older `check_card`/`check_overrides`/`render_card` that Pythia has. Unifying those is churn with
     no behaviour change; S03 will show whether the protocol's shape or the existing one is the right
     one, and the two are reconciled then rather than guessed at now.
