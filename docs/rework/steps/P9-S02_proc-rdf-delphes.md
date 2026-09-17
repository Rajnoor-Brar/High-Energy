# P9-S02 — hep proc: RDataFrame histograms on Delphes output

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P9 — ROOT processing layer |
| Depends on | [P9-S01](P9-S01_proc-fits.md), [P7-S08](P7-S08_delphes-external.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | D15; R9; 12 §2.2 |
| Updated | 2026-09-17 |

## Goal

`[[proc.hist]]` fills histograms from `delphes.root` via RDataFrame (or uproot+hist) into `proc.yoda`.

## Context

- Heavy RDF jobs run as a supervised stage.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `uproot`, `hist`, PyROOT | engines | use |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/proc/hist.py`
- stage wiring

**Out (non-goals)**

- In-process Delphes

## Design notes

- Same bins from both engines is a test requirement.

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- module + tests

## Verification

| Check | Command | Expected |
|---|---|---|
| Engines agree | RDF vs uproot on a small delphes.root | identical bins |
| Plots | `hep plot` | proc histograms shown |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
