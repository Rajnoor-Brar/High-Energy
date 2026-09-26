# P0-S03 — Move the ~/HEP tools into the repo

| Field | Value |
|---|---|
| Status | done |
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

- [x] Copy files to `tools/`, `chmod +x`, commit (approval)
- [x] Apply commit-2 changes, commit (approval)
- [x] Capture `rivpyth -p` output for every study before and after (scratch) and diff

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-17 — **done.**
  - **Commit 1** (`73658d0`): verbatim copy. The sha256 sums equal the P0-S01 snapshot.
  - **Commit 2:**
    - `rivpyth` reads its `--help` example from `rivpyth.example.toml` next to the resolved script path (the text was byte-identical before). A missing file gives a note, not a crash.
    - `env/hep_env.sh` puts `$HEKIT_ROOT/tools` on PATH instead of `$HEP`, so the `~/HEP` stub is no longer on PATH.
    - `.gitignore` gains `__pycache__/` and `*.pyc`. Running the tools from `tools/` creates `tools/__pycache__`, which is now ignored.
  - **Debris removed:**
    - FIFOs `output/PhotoProduction/{01_eic_28_p01,eic_28}.hepmc`, both checked with `test -p`;
    - `~/HEP/__pycache__` (4 `.pyc` files).
    - The five `~/HEP` copies were renamed to `*.moved`.
  - **Scratch CWD** `output/scratch/legacy/`: symlinks `configs`, `output`, `datasets` and `sources` (the last is also needed, because `plot_file_for` reads `sources/<project>/<analysis>.plot`), plus its own `results/`.
  - **Verification:**
    - `which rivpyth ydplt ydmrg` → `$HEKIT_ROOT/tools/…`.
    - `capture_p.sh` ran the snapshot (`output/scratch/p0/snapshot/`) and then `tools/`. It captured stdout, exit code and the dry point cmnds for `eic.toml` (default + 10 studies), `zeus_validation.toml` and the `--help` of all three tools. `diff -r output/scratch/p0/dry_before dry_after` is **identical**. The dry-dir line is the same `/tmp/rivpyth-dry-1002` for both.
    - Points per study: default 4, single 1, pdf 4, energies 4, energy_pdf 16, mpi 3, mpi_onoff 2, mpi_grid 6, pthatmin 4, process 2, radius 3; zeus 4. All exit 0.
    - No FIFOs left in `output/PhotoProduction`; `~/HEP/__pycache__` is absent.
