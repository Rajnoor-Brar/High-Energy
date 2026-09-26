# P4-S01 — Plot pipeline: load, select, transform, data map

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P3-S03](P3-S03_results-provenance.md) |
| Blocks | [P4-S02](P4-S02_plot-mkhtml.md), [P4-S03](P4-S03_plot-mpl-style.md), [P4-S04](P4-S04_compare.md), [P6-S02](P6-S02_event-groups.md) |
| Effort | 1 d |
| Findings / decisions | 00/B5, B17, B19 |
| Updated | 2026-09-18 |

## Goal

`hekit.plot` reproduces the legacy transforms (unify, void, auto-range, align, remap) on the new layout, with variant selection by option path, unique curve namespaces and an explicit data map.

## Context

- 07 §4.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:831-1147` | `plot_file_for`, `common_analysis`, `unify_yodas`, `void_bins`, `auto_range_plot`, `read_yoda`, `split_object_path`, `align_to_edges`, `remap_data_yoda` | port per 00b §1 |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/plot/{io,select,transform,data,plotfile}.py`
- `hekit/env` per-run `MPLCONFIGDIR`

**Out (non-goals)**

- Backends (S02, S03)

## Design notes

- Tests compare against the legacy functions (imported from `tools/`) on small fixtures while they exist.

## Tasks

- [x] Implement
- [x] Fixture tests

## Outputs

- `utils/python/hekit/plot/*`
- `tests/python/plot/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Equal to legacy | `pytest tests/python/plot -q` | outputs identical on fixtures |
| Data map (B5) | pytest: data file without a map | no overlay; warning |
| Namespaces (B17) | pytest: merged page | no collision with point names |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `hekit/plot/{io,select,transform,data,plotfile}.py` (726 lines) plus
  `paths.mpl_config_dir()`, with 38 tests (0.35 s). Suite: 526 Python.

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Equal to legacy | `void_bins`, `auto_range_plot`, `align_to_edges` and `split_object_path` compared against the originals imported from `tools/rivpyth_common.py` on the same fixtures: identical bin values (NaNs included), identical `.plot` blocks, identical trims |
  | Data map (00/B5) | a data file with no `[plot.data].map` produces **no overlay**, no file, and a warning that names the finding |
  | Namespaces (00/B17) | merged curves each own their prefix; every object path has exactly one owner, and `denamespaced()` reverses it |

  **What changed from the legacy functions, and why**

  1. **The data overlay is explicit or absent** (00/B5). `remap_data_yoda` matched a data object to an
     MC histogram *by name*, which in this project drew ZEUS data over a different observable and said
     nothing. Now `[plot.data].map` decides; a mapped entry that does not exist is an **error**, and
     `suggest_map()` exists for `--suggest-data-map` so the convenience is a suggestion the user
     confirms rather than a silent default.
  2. **Curve namespaces** (00/B17): `with_namespaces()` moves each curve's objects under its own name
     before a merge, so a page cannot lose a curve to a collision the way `ydmrg` could.
  3. **No fixed temporary paths** (00/B19): every transform writes where it is told, and
     `paths.mpl_config_dir()` gives matplotlib a per-run cache under `output/scratch/` instead of
     racing on `$HOME/.config/matplotlib`.
  4. **Option variants are curves, not pages.** One generation holds `photo_eic:R=0.4` and
     `:R=0.7` (03 §4), so `variants_in()`/`curves_for()` select an object path, and `io.plot_key()`
     deliberately ignores options — two variants share a plot and must agree on voiding and range.
  5. The locale is saved and restored around every YODA read (00/B29), and every YODA write is atomic
     with the suffix kept on the temporary (P0-S03).

  **Deviations**

  1. The step lists `hekit/plot/{io,select,transform,data,plotfile}.py`; that is exactly what was
     written. `plotfile.py` also **parses** `.plot` files, which P4-S03 needs to render the same keys
     with mplhep — one label source for both backends.
  2. `.plot` files are searched build-tree-first, in the same order as the plugin, so a `.plot` never
     comes from a different build than the analysis it describes.
  3. Three test expectations were wrong before the code was: the void report counts voided *plot* bins
     rather than curve-bins, and an "empty" fixture still carried a second histogram. The legacy
     functions agree with the counts as implemented.
