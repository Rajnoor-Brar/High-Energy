# P4-S01 — Plot pipeline: load, select, transform, data map

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P3-S03](P3-S03_results-provenance.md) |
| Blocks | [P4-S02](P4-S02_plot-mkhtml.md), [P4-S03](P4-S03_plot-mpl-style.md), [P4-S04](P4-S04_compare.md), [P6-S02](P6-S02_event-groups.md) |
| Effort | 1 d |
| Findings / decisions | 00/B5, B17, B19 |
| Updated | 2026-09-17 |

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

- [ ] Implement
- [ ] Fixture tests

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

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
