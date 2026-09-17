# P9-S01 — hep proc: fits

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P9 — ROOT processing layer |
| Depends on | [P4-S04](P4-S04_compare.md) |
| Blocks | [P9-S02](P9-S02_proc-rdf-delphes.md) |
| Effort | 1.5 d |
| Findings / decisions | D15; R15; 12 §2.1 |
| Updated | 2026-09-17 |

## Goal

`hep proc` fits YODA histograms with Minuit2/RooFit (PyROOT) or scipy and writes `fits.json`, fitted curves as YODA and optional `.root`.

## Context

- PyROOT importable after P0-S02; lazy import.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `hekit/results/stats.py` | shared statistics | reuse |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/proc/{models,backends/{minuit2,roofit,scipy}}`
- `[[proc.fit]]`
- outputs + provenance
- `[plot].show_fits`

**Out (non-goals)**

- Unfolding, TMVA

## Design notes

- One model registry → ROOT TF1 formula + NumPy callable.

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- `utils/python/hekit/proc/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Recovery | synthetic Gaussian + background | parameters within 1σ |
| Backends agree | minuit2 vs scipy | ≤ 1e-3 relative |
| Fallback | monkeypatch ROOT import failure | scipy used and reported |
| Overlay | `hep plot` with show_fits | curve drawn |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
