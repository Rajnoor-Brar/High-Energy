# P7-S08 — External Delphes stage

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md) |
| Blocks | [P9-S02](P9-S02_proc-rdf-delphes.md) |
| Effort | 0.75 d |
| Findings / decisions | R9; 05 §5 (Delphes) |
| Updated | 2026-09-17 |

## Goal

A HepMC tee feeds a supervised `DelphesHepMC3` stage that writes `delphes.root` with a provenance sidecar.

## Context

- In-process Delphes deferred (global `Event`, ROOT state).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `$HEP_INSTALL/delphes/bin/DelphesHepMC3` | CLI | drive |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `[delphes]` card; `Sink::Store` tee to FIFO; stage wiring; sidecar

**Out (non-goals)**

- In-process mode

## Design notes

- Delphes failures map to exit 4 (input) or 5 (output).

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- `hekit/adapters/delphes.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Output | 1k events | `delphes.root` readable by uproot |
| Failure | bad card | exit 4/5 attributed |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
