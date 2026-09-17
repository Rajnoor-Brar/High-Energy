# P7-S01 — External adapter framework and prepare cache

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P3-S05](P3-S05_hep-run-command.md), [P5-S02](P5-S02_store-source-replay.md) |
| Blocks | [P7-S02](P7-S02_decide-photoproduction-equivalence.md), [P7-S03](P7-S03_sherpa.md), [P7-S04](P7-S04_whizard.md), [P7-S05](P7-S05_madgraph.md), [P7-S07](P7-S07_herwig.md), [P7-S08](P7-S08_delphes-external.md) |
| Effort | 1 d |
| Findings / decisions | F9; 04 §1, §8 |
| Updated | 2026-09-17 |

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

- [ ] Implement
- [ ] Fake generator test

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

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
