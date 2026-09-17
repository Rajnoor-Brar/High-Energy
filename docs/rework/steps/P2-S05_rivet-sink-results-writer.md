# P2-S05 — Serial Rivet sink and atomic results writer

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S04](P2-S04_source-run-loop.md) |
| Blocks | [P2-S06](P2-S06_equivalence-gate.md), [P3-S05](P3-S05_hep-run-command.md), [P4-S05](P4-S05_photo-eic-reentrant.md), [P5-S01](P5-S01_store-writer.md) |
| Effort | 0.75 d |
| Findings / decisions | 00/B3, B21; F8; D22 |
| Updated | 2026-09-17 |

## Goal

`hep-run` writes `analysis.yoda` normalised to the merged σ; stopped runs write only `analysis.partial.yoda`; periodic dumps only for re-entrant analyses; a run summary feeds provenance.

## Context

- 05 §5 (Rivet), 07 §1–2.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Record/Recording.hh:204-231` | tmp + atomic rename | adapt |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Sink::Rivet` (serial): analyses + options, check_beams, weights policy, `setCrossSection(σ, err, true)`, finalize, `getYodaAOs()`
- `Results::Writer`: `.tmp` → rename; partial naming; `analysis.dump.yoda` via `setFinalizePeriod` for re-entrant analyses only; `run.summary.json`

**Out (non-goals)**

- Module objects (P8-S01)
- sharded Rivet (P6-S01)

## Design notes

- Missing analysis is detected before generation (load analyses right after `init()`).

## Tasks

- [ ] Implement
- [ ] Tests

## Outputs

- `utils/Sink/Rivet.hh`, `utils/Results*`
- `tests/cpp/rivet_*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Missing analysis | spec with `NOPE_2099_I1` | exit 1 before any event |
| σ | python `yoda.read` of `/_XSEC` | = merged sigmaGen × 1e9 pb |
| Partial | SIGINT mid-run | only `analysis.partial.yoda` exists |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
