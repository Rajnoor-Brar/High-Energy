# P0-S03 — Move the ~/HEP tools into the repo

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S02](P0-S02_env-setup-fixes.md) |
| Blocks | [P0-S04](P0-S04_golden-fixtures.md) |
| Effort | 0.2 d |
| Findings / decisions | plans 0.1, plans/B2, F3, 00/B24 |
| Updated | 2026-09-17 |

## Goal

`rivpyth`, `ydplt`, `ydmrg`, `rivpyth_common.py`, `rivpyth.example.toml` are versioned under `tools/` and are the ones on PATH; debris is gone.

## Context

- The scripts import `rivpyth_common` from their own directory, so moving them changes only PATH.
- D18: move before porting so hotfixes and fixtures are reviewable diffs.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `~/HEP/{rivpyth,ydplt,ydmrg,rivpyth_common.py,rivpyth.example.toml}` | files | copy verbatim |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `tools/*`
- `env/hep_env.sh` PATH entry
- debris removal

**Out (non-goals)**

- Behaviour changes (P0-S05)

## Design notes

- Commit 1: verbatim copy (history starts from the baseline snapshot).
- Commit 2: `EXAMPLE` in `rivpyth` reads `rivpyth.example.toml` (removes the duplicate); PATH via `env/hep_env.sh`; remove `~/HEP/__pycache__`; remove stale FIFOs `output/PhotoProduction/*.hepmc` after `test -p`; rename `~/HEP` copies to `*.moved`.

## Tasks

- [ ] Copy files to `tools/`, `chmod +x`, commit (approval)
- [ ] Apply commit-2 changes, commit (approval)
- [ ] Capture `rivpyth -p` output for every study before and after (scratch) and diff

## Outputs

- `tools/rivpyth`, `tools/ydplt`, `tools/ydmrg`, `tools/rivpyth_common.py`, `tools/rivpyth.example.toml`

## Verification

| Check | Command | Expected |
|---|---|---|
| PATH | `which rivpyth ydplt ydmrg` | all under `$HEKIT_ROOT/tools/` |
| Same behaviour | for s in '' single pdf energies energy_pdf mpi mpi_onoff mpi_grid pthatmin process radius: `rivpyth -p configs/PhotoProduction/eic.toml ${s:+--study $s}` vs snapshot tools | identical except the tmp-dir line |
| Debris gone | `ls -la output/PhotoProduction \| grep '^p'`; `ls ~/HEP/__pycache__` | no FIFOs; no such dir |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Remove `tools/` from PATH and rename `~/HEP/*.moved` back.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
