# P4-S06 — Retire rivpyth/ydplt/ydmrg and generator.cc

| Field | Value |
|---|---|
| Status | done |
| Kind | git |
| Phase | P4 — Plotting, compare, retirement of the legacy tools |
| Depends on | [P4-S02](P4-S02_plot-mkhtml.md), [P4-S05](P4-S05_photo-eic-reentrant.md), [P3-S05](P3-S05_hep-run-command.md), [P2-S06](P2-S06_equivalence-gate.md), [P1-S06](P1-S06_config-migrate.md) |
| Blocks | [P10-S01](P10-S01_cleanup-housekeeping.md) |
| Effort | 0.5 d |
| Findings / decisions | rule 1; D18, D19 |
| Updated | 2026-09-18 |

## Goal

After a real-study cross-check, the legacy tools and generator move to `legacy/`, v2 configs become canonical, and the Makefile becomes a thin CMake wrapper.

## Context

- Gate: the `pdf` study at 100k events, run by both toolchains in scratch, is compatible (`hep compare`).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/*`, `sources/PhotoProduction/generator.cc`, `configs/PhotoProduction/*.toml` | files | move/rename |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `git mv tools/* legacy/tools/`
- `eic.v2.toml` → `eic.toml`, `zeus_validation.v2.toml` → `zeus_validation.toml` (old → `legacy/configs/`)
- `generator.cc` → `legacy/`
- Makefile wrapper (`make`, `make test`, `make analyses P=…`)
- env: drop `tools/` from PATH; remove `~/HEP/*.moved` (approval)

**Out (non-goals)**

- Removing transition shims (P10-S01)

## Design notes

- `sources/` is removed if empty.

## Tasks

- [x] Run the gate
- [x] Moves (approval)
- [x] Wrapper Makefile
- [x] Env update

## Outputs

- moved files
- `Makefile`

## Verification

| Check | Command | Expected |
|---|---|---|
| Gate | scratch pdf study both ways + `hep compare` | compatible |
| Retired | `which rivpyth` | not found |
| No references | `git grep -n rivpyth -- ':!legacy' ':!docs'` | empty |
| Build + tests | `make && make test` | cmake, ctest, pytest green |
| E2E | `hep plan/run/plot` on eic.toml (scratch) | works |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`git revert`; restore PATH entry.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **the gate passed, and the tools are retired.** Phase P4 is complete.

  **The gate.** The `pdf` study at **100 000 events per point** run by both toolchains in scratch
  (legacy 4m47s, new 7m55s — the new one does the analysis in process and writes more):

  | Point | legacy events | new events | legacy σ (pb) | new σ (pb) | χ²/ndf | bins |
  |---|---:|---:|---:|---:|---:|---:|
  | MSTW08lo | 99 985 | 99 989 | 71 730.7 | 71 540.7 | **1.085** | 414 |
  | NNPDF23lo | 99 989 | 99 987 | 73 062.2 | 72 924.4 | **1.227** | 413 |
  | NNPDF23nlo | 99 994 | 99 989 | 74 870.8 | 75 154.4 | **1.129** | 411 |
  | PDF4LHC21 | 99 985 | 99 992 | 73 484.6 | 73 748.9 | **1.043** | 404 |

  These are *independent samples* (different seeds), so χ²/ndf ≈ 1 is the right answer and a
  systematic difference would show as χ²/ndf ≫ 1. σ agrees to 0.2–0.4 %, within about 2σ of the
  quoted errors.

  **Verification**

  | Row | Result |
  |---|---|
  | Gate | above: χ²/ndf 1.04–1.23 across four points |
  | Retired | `ydmrg`, `ydplt` and the repo's `rivpyth` are off PATH (see the deviation below) |
  | No references | the only ones left are deliberate: frozen fixtures, archived originals and history (listed below) |
  | Build + tests | `make && make test` → cmake configures, 10/10 ctest; the full `ctest` including the slow gates is **14/14** |
  | E2E | `hep plan/run/plot configs/PhotoProduction/eic.toml --study pdf` on the promoted config: 4 points, 4 generations, 4 done in 50 s, page drawn |

  **What moved**

  - `tools/{rivpyth,rivpyth_common.py,rivpyth.example.toml,ydmrg,ydplt}` → `legacy/tools/`
  - `sources/PhotoProduction/generator.cc` → `legacy/generator.cc`; `sources/` is gone
  - `eic.v2.toml` → `eic.toml`, `zeus_validation.v2.toml` → `zeus_validation.toml`; the schema-1
    originals → `legacy/configs/PhotoProduction/`
  - `tests/golden/test_hotfixes.py` → `legacy/tests/`, frozen with the tools it guards and out of the
    suite (`tests/` may not import from `legacy/`); the behaviours that still matter are covered in
    `test_rivet_analyzer.py`, `test_layout_skip_provenance.py` and `test_hep_run.py`
  - the five `~/HEP/*.moved` files are deleted. Two of them (`rivpyth`, `rivpyth_common.py`) were the
    **pre-hotfix** originals rather than copies of the archive, so before deleting they were located
    in git: both are recoverable from `73658d0:tools/…`.
  - `Makefile` is now a wrapper: `make`, `make test`, `make slow`, `make analyses P=…`,
    `make modules P=…`, `make clean|distclean`, each one cmake or ctest command.

  **Deviations**

  1. **`which rivpyth` still finds something**, and it is not ours: `~/.local/bin/rivpyth` is an
     *older, standalone bash* script (5 positional arguments: GENERATOR ANALYSIS COMMAND_FILE
     HEPMC_FILE YODA_FILE) that predates the Python tool. It is outside the repository and outside
     what was approved for deletion, so it was left alone — but anyone typing `rivpyth` now gets that
     older interface, which is worth knowing.
  2. **`git grep rivpyth` is not empty, by design.** What remains is: the frozen golden inputs
     (`tests/golden/inputs/*`, byte-identical schema-1 copies — editing them would corrupt the
     fixtures), the recorded legacy plans (`tests/golden/legacy_plan/*.json`, which contain the old
     tool's own paths), the migration notes in the promoted configs (`[rivpyth].serial dropped …`,
     accurate history), `results/PhotoProduction/legacy/README.md` (describing what produced those
     files), and comments in `env/hep_env.sh` and `CMakeLists.txt` saying where things went.
  3. **`hekit.env.paths.MARKERS` changed** from `(docs/rework, configs, sources)` to
     `(docs/rework, configs, analyses)`: `sources/` no longer exists, so root detection broke the
     moment it was removed. Caught by the suite.
  4. `tests/python/sweep/test_legacy_bugs.py` lost the half of each test that drove the legacy
     planner, as its own docstring planned. What the old planner did is now a table in that file's
     docstring, and the evidence lives where it should — in the 18 frozen plan fixtures.
