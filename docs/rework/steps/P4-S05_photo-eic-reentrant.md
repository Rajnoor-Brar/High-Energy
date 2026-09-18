# P4-S05 — Make photo_eic re-entrant and fix plugin defects

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P2-S05](P2-S05_rivet-sink-results-writer.md), [P4-S04](P4-S04_compare.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md), [P6-S01](P6-S01_sharded-rivet.md) |
| Effort | 0.5 d |
| Findings / decisions | 00/B25, B26; 00 §4.2 |
| Updated | 2026-09-18 |

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

- [x] Edit plugin
- [x] Rebuild
- [x] Tests

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — three changes to the plugin, each measured. Tests:
  `tests/integration/test_photo_eic_plugin.py` (6 cases, ctest `photo_eic`, label `slow`).

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Merge | `rivet-merge -e` of 2 × 20 k against one 40 k run: **χ²/ndf = 0.602 over 378 bins** in 17 histograms (`hep compare`); merged 39 996 events and σ = 71 523.9 pb against 39 997 and 71 487.7 pb |
  | Leak | ASan, 1 000 events: **14 744 bytes in 74 allocations before, 14 664 in 73 after** — exactly one 80-byte allocation gone, the `SISConePlugin` object. The remaining 73 are one-time allocations inside Pythia/LHAPDF/Rivet |
  | Orientation | a card with the proton as beam B (`DISKinematics::orientation() = -1`, printed to confirm): **17 of 17 histograms filled** |
  | Dumps | a run with `dump_every` now writes `analysis.dump.yoda` with no "ignored" warning, and the file is **finalized** — `/_XSEC` present, `ScaledBy = 50.377`, `d01` bin 1 = 14 760 pb/GeV against a raw weight sum of 586 |

  **00/B26 is verified as *not* a defect.** The audit recorded it as "(unverified)", and it is worth
  saying which way it went: with the proton as beam B the old cut
  `Cuts::etaIn(-etamax*orientation, +etamax*orientation)` builds `etaIn(3.5, -3.5)`, but **Rivet 4.1.3
  normalises an inverted range**, so all 17 histograms filled either way. Built both versions and
  compared: **identical, 39 objects / 1004 numbers**. The acceptance is symmetric, so it is now
  written that way (`Cuts::abseta < _etamax`) and no longer depends on that behaviour — a neutral
  change, which is what "no physics changes to binning or cuts" requires.

  **00/B25 was real.** One `SISConePlugin` per run, and one per worker in a sharded run (P6-S01), so
  the cost would have scaled with the thread count.

  **`Reentrant: true` is now earned, not asserted.** P2-S06 had shown the merge chain works when the
  flag is set; this step sets it and backs it with the merge test above. The plugin's `finalize()`
  only scales and normalises booked objects, which is what re-entrancy requires.

  **`Beams: [p+, e-], [p+, e+]`** added to the `.info`. Both charges are run (00/B11: the EIC studies
  use e⁺ through `[settle.use]`), and `check_beams` is on by default, so both have to be declared.

  **Deviations**

  1. A test that P2-S05 wrote — "dump_every is refused for a non-re-entrant analysis" — had to change,
     as its own log predicted. It now asserts the new truth (the dump is written and finalized), and
     the refusal path is still covered by copying the plugin with `Reentrant: false` put back.
  2. The equivalence gates (P2-S06, P4-S02) were re-run after the plugin change and still pass bin for
     bin against the legacy results, which is the strongest available check that nothing moved.
