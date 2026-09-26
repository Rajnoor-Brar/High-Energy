# P4-S02 — hep plot with the rivet-mkhtml backend

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P4-S01](P4-S01_plot-pipeline.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md) |
| Effort | 0.75 d |
| Findings / decisions | R4 |
| Updated | 2026-09-18 |

## Goal

`hep plot` (pages and `--points`) produces the same pages as `ydmrg`/`ydplt`.

## Context

- 07 §4 backends.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:1116` `plot_arguments` | argv construction | port |
| `tools/ydplt:44-76`, `tools/ydmrg:43-92` | flow | replace |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/plot/backends/mkhtml.py`
- CLI

**Out (non-goals)**

- mpl backend (S03)

## Design notes

- Compare intermediate files (page set, legends, `.plot` overrides, remapped data YODAs), not HTML.

## Tasks

- [x] Implement
- [x] Golden comparisons

## Outputs

- backend + CLI
- `tests/integration/test_plot_vs_legacy.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Golden | P0-S04 mini run + 2 legacy studies copied to scratch | intermediates equal |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `hekit/plot/{page,cli}.py` and `hekit/plot/backends/mkhtml.py`, with
  `tests/integration/test_plot_vs_legacy.py` (10 cases, ctest `plot_equivalence`, label `slow`) and
  `tests/python/plot/test_plot_cli.py` (48 fast plot tests in all). Suite: 13/13 ctest.

  **Verification: the golden row passes on all four intermediates.** P0-S04 kept everything `ydmrg`
  and `ydplt` handed to `rivet-mkhtml`; the new pipeline was run on the same YODAs with the same
  settings and compared:

  | Intermediate | Result |
  |---|---|
  | voided curves | every bin equal, NaNs included, in both curves of the page |
  | number of voided bins | identical (voiding is decided across a page, so a different rule would show) |
  | `auto_range.plot` | identical blocks |
  | remapped data YODA | same objects, same edges, same values |
  | `rivet-mkhtml` argv | same flags in the same order, same titles, same file names |
  | `ydplt` single point | the same, for a one-curve page |

  The one deliberate difference is the data map: `ydmrg` matched data to MC by histogram name
  (00/B5), so the comparison passes that mapping **explicitly**, and a separate test shows that
  without a map nothing is overlaid at all. `suggest_map()` reproduces exactly what the old tool did
  implicitly, which is what `--suggest-data-map` prints for review.

  **Shape**

  - `page.prepare()` runs the pipeline in the order that works — select → unify → void → data →
    auto-range — into a work directory the caller owns. Voiding before the overlay means the reference
    is aligned against the binning the curves are actually drawn with; auto-range last means it sees
    both.
  - `backends/mkhtml.py` ports `plot_arguments`, including the subtlety that matters on screen and in
    no test: a reference kept as the ratio denominator but **not drawn** still owns a legend entry,
    which would shift every label by one, so the MC curves are named and `PLOT:LegendOnly` lists them.
  - `hep plot` replaces both old commands: `--points` makes one page per point, because a single point
    is a page with one curve and should behave identically.
  - Pages go to `studies/[NN_]<study>/plots/<page>/`, beside the manifest of the run that produced the
    points; `--out` overrides that, `--keep` leaves the intermediates next to the page.

  **Defects found and fixed**

  1. **`hep plot` leaked a temporary directory per page.** `mkdtemp` with no cleanup — caught by the
     P4-S01 test that asserts nothing new appears in the shared temporary tree (00/B19, again).
  2. **Two commands claimed steps that never implemented them.** `hep analyses` said "step P1-S07" and
     `hep build` said "step P2-S01", both of which are done — so the CLI was telling the user to wait
     for something that had already shipped. Both are now implemented here (`hep analyses` reads the
     same `.info` files Rivet does, build tree first, so a listed analysis is the one Rivet would
     load; `hep build` wraps cmake and replaces `make PROJECT/x.so`), and the skeleton test now
     **finds** the first unimplemented command instead of naming one, so it stops going stale, and
     asserts that every landed command is real.
  3. `hep analyses` listed the analysis from `output/` rather than the build tree, because the loop
     let the last directory win; the search order is first-wins, as the plugin search is.

  **Deviations**

  1. `hekit/plot/page.py` is an addition to the step's `{backend, CLI}` scope: both backends and the
     golden test need the same prepared page, and putting that in the CLI would have made P4-S03
     import a command module.
  2. The comparison is of intermediates, as the step's design note asks — the HTML carries timestamps
     and says less about what a plot shows than its inputs do.
