# P7-S05 — MadGraph adapter (LHE → Pythia shower)

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md), [P2-S04](P2-S04_source-run-loop.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | R8; 04 §7 |
| Updated | 2026-09-17 |

## Goal

MadGraph matrix elements are generated, cached, and showered by `Source::Pythia` into the same sinks.

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

- [ ] Implement
- [ ] Tests

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

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
