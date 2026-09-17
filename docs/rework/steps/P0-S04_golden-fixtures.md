# P0-S04 — Capture golden fixtures of the legacy workflow

| Field | Value |
|---|---|
| Status | todo |
| Kind | test |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S03](P0-S03_tools-into-repo.md) |
| Blocks | [P0-S05](P0-S05_legacy-hotfixes.md), [P0-S06](P0-S06_legacy-archive.md), [P2-S06](P2-S06_equivalence-gate.md), [P3-S01](P3-S01_decide-serial-and-legacy-results.md) |
| Effort | 0.5 d |
| Findings / decisions | 00 §4.1 golden fixture; 00/B16 inventory; plans/B1 |
| Updated | 2026-09-17 |

## Goal

Legacy behaviour is frozen as data before any fix: plan expansions for every study, a mini run with plot intermediates, and an inventory of existing results.

## Context

- Legacy tools resolve `results/`, `configs/`, `output/` relative to the CWD (00/B18), so they can run in a scratch CWD with symlinks — no code change needed.
- Scratch CWD: `output/scratch/legacy/` with symlinks `configs`, `output`, `datasets` → repo and a real `results/`.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py` | `read_config`, `apply_overrides`, `expand_points`, `execution_plan`, `group_pages`, `page_suffix`, `curve_legend` | import (pure functions) |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `tests/golden/**` (tracked)
- scratch runs
- read-only inventory

**Out (non-goals)**

- Any tool fix (P0-S05)

## Design notes

- (a) `tests/golden/capture_legacy.py`: for `eic.toml` (default + 10 studies) and `zeus_validation.toml` write `tests/golden/legacy_plan/<cfg>/<study>.json` (points: number, suffix, settings with origin, analysis, legend, page; pages: suffix, members, legends; plan paths relative; point-cmnd text).
- (b) `tests/golden/legacy_mini.toml`: 2 PDF points, 5k events, 1 thread, fixed seed; run `rivpyth`, `ydmrg`, `ydplt` in the scratch CWD; store YODAs, unified/voided intermediates and generated `.plot` overrides under `tests/golden/legacy_run/` (small files only).
- (c) Read-only inventory of `results/PhotoProduction` → `tests/golden/results_inventory.json` (path, bytes, sha256, `/_EVTCOUNT` numEntries/sumW, cmnd sha, serial); flags partial files and serial drift. (Moved to `legacy/results/` in P0-S06.)
- (d) `tests/golden/test_legacy_counts.py`: single 1; pdf 4 (1 page); energies 4 (1 page); energy_pdf 16 (4 pages); mpi 3; mpi_onoff 2; mpi_grid 6 (2 pages); pthatmin 4; process 2; radius 3 (analysis `photo_eic:R=1` for the last); zeus 4 (never run).

## Tasks

- [ ] Create scratch CWD with symlinks
- [ ] Write and run capture script
- [ ] Run mini legacy workflow in scratch
- [ ] Write inventory script and run it read-only
- [ ] Write count tests

## Outputs

- `tests/golden/{capture_legacy.py,legacy_mini.toml,test_legacy_counts.py,results_inventory.json}`
- `tests/golden/legacy_plan/**`
- `tests/golden/legacy_run/**`

## Verification

| Check | Command | Expected |
|---|---|---|
| No writes to real dirs | `touch output/scratch/stamp` before; after: `find results configs -newer output/scratch/stamp \| wc -l` | 0 |
| Counts | `pytest tests/golden -q` | all pass |
| Mini run complete | `ls tests/golden/legacy_run/*.yoda` | 2 files with `/_EVTCOUNT` = 5000 |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Delete `tests/golden/` and the scratch dir.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
