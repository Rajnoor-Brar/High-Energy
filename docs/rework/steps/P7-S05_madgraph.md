# P7-S05 — MadGraph adapter (LHE → Pythia shower)

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md), [P2-S04](P2-S04_source-run-loop.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | R8; 04 §7 |
| Updated | 2026-09-20 |

## Goal

MadGraph matrix elements are generated, cached, and showered by `Source::Pythia` into the same analyzers.

## Context

- Pythia LHE: `Beams:frameType = 4`, `Beams:LHEF`.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 04 §7 | stages | implement |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- process-dir cache
- launch script (`nevents`, `iseed`, `lpp`, `ebeam`, `run_card.*`)
- LHE decompression
- shower card

**Out (non-goals)**

- Merging validation (warn only)

## Design notes

- ids/energies unset for the shower stage (LHE defines them).

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- `hekit/adapters/madgraph.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Toy | 1k LHE events | showered + analysed |
| Cache | second run | process dir reused |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — implemented `hekit/adapters/madgraph.py`. MadGraph 3.7.3 is installed, so both rows
  were run. New ctest test `madgraph` (label `slow`, 7 cases) and 17 unit tests.

  **Verification, both rows measured**

  | Row | Result |
  |---|---|
  | Toy | `e+ e- -> mu+ mu-` at the Z runs end to end: build the process directory, launch to an LHE, unpack it, and Pythia showers it inside `hep-run`. 100 events, σ = 2 016 pb from the LHE header, `MC_FSPARTICLES` filled, and `/_XSEC` equal to the summary's σ |
  | Cache | a second run reuses the process directory: one `madgraph-build.log`, one cache entry with `produces: [process/bin/generate_events]`, and `generate_events` untouched (same mtime). The **planner** drops the build stage entirely once the entry is ready, which the test asserts from both sides |

  **This is the adapter that does not hand over events.** It hands over a matrix element, so there is
  no FIFO and no `Source::Stream`: the spec's `source.kind` is `pythia`, and the card this adapter
  renders is a five-line *Pythia* card. Everything else about it follows from that.

  **Four phases, because nothing may overlap.** A FIFO's two ends must be open at once; a file must
  be finished before anything reads it. `base.Stage` gained a `phase`, defaulting to 0 for a prepare
  step and 1 otherwise, and the planner gives `hep-run` the generator's phase when the tool streams
  and one *after* it when it does not (`STREAMS = False`).

  **Three defects, all found by running it.**

  1. **The prepare stage wrote the wrong card.** `group.card` is the rendered Pythia shower card, so
     MadGraph was handed a file with no `generate` line and said "No model found". The proc card is
     `group.base_card`, which the group now carries, and `cache.for_group` asks the adapter which
     text to key on — the same confusion twice, fixed once.
  2. **The spec said `source.kind = "madgraph"`**, which `hep-run` rightly did not recognise. Pythia
     is the source whatever produced the matrix element.
  3. **The preflight ran `hep-run --check` before the LHE existed**, so Pythia failed to initialise
     on every MadGraph point. It is skipped when a stage that *produces* events runs in an earlier
     phase — a streaming generator's FIFO exists from the start, so those are still preflighted.

  **Deviations**

  1. The toy is 100 events rather than the row's 1 000: the subject is the chain, and four processes
     in order are exercised the same either way.
  2. `merging_warning` warns when a proc card generates several jet multiplicities; validating the
     merging itself is out of scope, as the step says.
  3. The LHE is unpacked into the point directory rather than the cache — see the doc note; it also
     means `hep show` can find the events a point was showered from.
