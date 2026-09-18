# P4-S04 — hep compare and shared statistics

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P4-S01](P4-S01_plot-pipeline.md) |
| Blocks | [P4-S05](P4-S05_photo-eic-reentrant.md), [P9-S01](P9-S01_proc-fits.md) |
| Effort | 0.5 d |
| Findings / decisions | 07 §5 |
| Updated | 2026-09-18 |

## Goal

`hep compare` prints χ²/ndf, bins used and max pull per histogram and writes `compare.md`; the statistics module is shared with `hep proc`.

## Context

- Absorbs `tests/tools/yodacmp.py` from P2-S06.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tests/tools/yodacmp.py` | comparison | promote |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/results/{stats,compare}.py`
- CLI

**Out (non-goals)**

- Fits (P9)

## Design notes

- Aligned-bin rule from `align_to_edges`; voided bins excluded.

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- modules + CLI

## Verification

| Check | Command | Expected |
|---|---|---|
| Known χ² | pytest synthetic fixtures | expected values |
| Alignment | pytest mismatched binning | only aligned bins used |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `hekit/results/{stats,compare}.py` (≈340 lines) and `hep compare`, with
  22 tests. Suite: 13/13 ctest.

  **Verification**

  | Row | Result |
  |---|---|
  | Known χ² | fixtures whose answer is known by hand: identical curves → 0; one combined error apart in every bin → χ²/ndf = 1; two apart → 4; errors combine in quadrature (3 and 4 make 5) |
  | Alignment | two binnings with no shared edges → **0 bins used**, "no bins align", χ²/ndf NaN rather than a number; a partly aligned reference uses exactly the bins that line up |

  **What must not enter a χ², and is counted instead**

  1. **unaligned bins** — the pipeline's `align_to_edges` rule decides what lines up (07 §4);
  2. **voided bins** — a void is "no information", and treating a blanked bin as a measurement of zero
     would invent a large χ² out of nothing;
  3. **bins with no error** — dividing by zero is how a χ² becomes infinite and a study becomes
     nonsense.

  Each is reported separately in the row's note (`10 voided`, `2 unaligned`), so a number that looks
  small because half the bins were dropped says so.

  **On real results.** `hep compare configs/PhotoProduction/eic.v2.toml --study pdf --ref
  eic_27x920_ep_MSTW08lo_pt32_mpi` on the 4-point 20 k-event study gives χ²/ndf ≈ 1.1–1.4 for
  NNPDF2.3 LO against MSTW08 LO and ≈ 3.2–5.7 for NNPDF2.3 NLO and PDF4LHC21 — the LO sets agree with
  each other and the NLO one does not, which is what a PDF study is for.

  **Notes**

  1. `tests/tools/yodacmp.py` is **promoted** rather than moved: the arithmetic is now in
     `hekit.results.stats`, and the tool stays as the file-to-file diff the equivalence gates use.
     "Is every number identical?" (a gate) and "are these compatible?" (a comparison) are different
     questions, and conflating them would weaken the gate.
  2. `--ref data` compares against the overlaid reference the plot pipeline builds; `--ref POINT`
     compares every other curve against one of them, which is what a tune or PDF study asks.
  3. `compare.md` is written into the study directory beside the manifest, atomically like everything
     else, so a scan survives the session.
  4. The terminal table colours χ²/ndf green/yellow/red (< 2, < 5, above), because the point of the
     table is to find the one row worth opening a plot for.
