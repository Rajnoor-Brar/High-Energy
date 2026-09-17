# P4-S05 — Make photo_eic re-entrant and fix plugin defects

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P2-S05](P2-S05_rivet-sink-results-writer.md), [P4-S04](P4-S04_compare.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md), [P6-S01](P6-S01_sharded-rivet.md) |
| Effort | 0.5 d |
| Findings / decisions | 00/B25, B26; 00 §4.2 |
| Updated | 2026-09-17 |

## Goal

`photo_eic` has `Reentrant: true` backed by a merge test, no SISCone leak, orientation-safe η acceptance and a `Beams:` entry.

## Context

- Rivet 4.1.3 skips finalize in dumps for non-re-entrant analyses (`AnalysisHandler.cc:700-705`).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `analyses/PhotoProduction/photo_eic.{cc,info}` | plugin | edit |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- SISCone plugin ownership (`delete_plugin_when_unused` or member)
- η range built as `[min, max]` independent of orientation
- `Reentrant: true`; `Beams: [p+, e-]` (and e+ if needed)

**Out (non-goals)**

- Physics changes to binning or cuts

## Design notes

- Merge test: `rivet-merge -e` of 2×20k replicas vs one 40k run, compared with `hep compare`.

## Tasks

- [ ] Edit plugin
- [ ] Rebuild
- [ ] Tests

## Outputs

- plugin changes

## Verification

| Check | Command | Expected |
|---|---|---|
| Merge | `rivet-merge -e` 2×20k vs 40k | compatible |
| Leak | ASan 1k events | no leak |
| Orientation | card with proton as beam B | non-empty jet histograms |
| Dumps | serial run with dump_every | dump is finalized |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
