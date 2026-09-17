# P1-S01 — Create the hekit package, CLI entry point and test guard

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P0-S07](P0-S07_makefile-hygiene.md) |
| Blocks | [P1-S02](P1-S02_config-schema.md), [P1-S07](P1-S07_doctor-pdf.md), [P2-S03](P2-S03_core-status.md) |
| Effort | 0.3 d |
| Findings / decisions | 00/B18; N10 |
| Updated | 2026-09-18 |

## Goal

`pip install -e utils/python` gives a working `hep` command from any directory; errors use one type; a pytest guard fails any test that writes into `results/` or `configs/`.

## Context

- 08 §2 (command tree), 09 §2 (packaging), 13 §4 (packages).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Utility/Paths.hh:25-54` | env var → walk up to an anchor | reimplement in `hekit.env.paths` |
| `tools/rivpyth_common.py:16` `ConfigError` | error shape | adapt to `HepError(msg, where, hint)` |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `utils/python/pyproject.toml` (entry `hep = hekit.cli:main`; deps click, rich, tomli_w; extras plot, ml, proc)
- `hekit/{__init__,cli,errors}.py`, `hekit/env/paths.py` (`HEKIT_ROOT`, `HEKIT_RESULTS`, repo root from package location)
- `tests/python/conftest.py`: autouse fixture sets `HEKIT_RESULTS=tmp_path`, snapshots mtimes of `results/` and `configs/`, fails the session on change

**Out (non-goals)**

- Any subcommand logic

## Design notes

- click groups registered lazily so `hep --help` stays fast (no yoda/ROOT import).
- `hep --version` prints hekit version + git sha (via `hekit.prov.git` stub).

## Tasks

- [x] Write pyproject + skeleton
- [x] Editable install into `~/HEP/.venv`
- [x] Add completion line to `env/hep_env.sh` (cached)
- [x] Write guard + a deliberately failing planted-write test (marked xfail-strict)

## Outputs

- `utils/python/**`
- `tests/python/conftest.py`
- `env/hep_env.sh` (completion)

## Verification

| Check | Command | Expected |
|---|---|---|
| Runs anywhere | `cd / && hep --version` | version string |
| Guard works | `pytest tests/python -q` | planted write detected (xfail passes) |
| Fast help | `time hep --help` | < 0.3 s |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`pip uninstall hekit`; remove `utils/python`.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - **Package** `utils/python/` (`pyproject.toml`: package `hekit`, entry point `hep = hekit.cli:main`, deps
    click/rich/tomli_w, extras `plot`/`ml`/`proc`/`dev`), installed editable into `~/HEP/.venv`
    (`pip install -e utils/python`).
  - **`hekit.errors`:** one `HepError(message, where=, hint=)` with `render()` and `exit_code = 2`; subclass
    `NotImplementedYet(command, step)` (exit 3); `did_you_mean()` for misspellings. Only `cli.main` prints.
  - **`hekit.env.paths`:** root from `HEKIT_ROOT` (validated against the markers `docs/rework`, `configs`,
    `sources`), else walking up from the package, else from the current directory; `HEKIT_RESULTS` redirects the
    results tree; `configs/sources/analyses/output/scratch/results` roots, `project_dir(kind, project)` and
    `describe()` (which reports where each root came from). Adapted from `legacy/utils/Utility/Paths.hh:25-54`.
  - **`hekit.prov.git`:** `git_state()` → sha, branch, dirty; every failure degrades to `unknown` rather than
    raising, so provenance never breaks a command.
  - **`hekit.cli`:** click group with a `LazyGroup` that imports a subcommand's module only when it runs. All 19
    commands of 08 §2 are registered with the step that implements them; an unimplemented one prints
    "arrives in step P1-S05" and exits 3, and `hep --help` lists them with their step. Global options
    `--project-root`, `-v/-q`, `--plain`, `--version`.
    - **Deviation:** `--version` is a custom eager flag rather than `click.version_option`, so it can print the
      git sha and the resolved root: `hep 0.1.0 (d75c7b8+dirty) root: /home/rajnoor/Github/High-Energy`.
  - **Test guard (00/B18):**
    - **Deviation:** the guard lives in `tests/guard.py` and is applied by `tests/conftest.py`, so it covers
      **every** test directory (including `tests/golden`, which drives the legacy tools), not only
      `tests/python`. `tests/python/conftest.py` keeps the `HEKIT_RESULTS` → `tmp_path` redirect.
    - **Deviation:** instead of an `xfail-strict` planted write, the guard's snapshot/diff functions are unit
      tested on a fake tree (planting a write in the real `configs/` is precisely what the guard forbids). A
      temporary planted-write test was run once to confirm the mechanism end to end, and it errored with
      `this test wrote into a protected tree … modified …/configs/`.
    - **Found while testing:** the first version only snapshotted files, so a test that created *and deleted* a
      file was not caught. Directories are now snapshotted too (their mtime changes), which the new test
      `test_guard_detects_a_write_that_cleans_up_after_itself` pins.
  - **`env/hep_env.sh`:** `_hep_load_completion` caches `_HEP_COMPLETE=bash_source hep` under
    `${XDG_CACHE_HOME:-~/.cache}/hekit/` and regenerates it only when the `hep` entry point is newer;
    interactive shells only. The loader is deliberately *not* called `_hep_completion` — that is the name click
    generates, and the two collided.
  - **Verification:**
    | Check | Result |
    |---|---|
    | `cd / && hep --version` | `hep 0.1.0 (d75c7b8+dirty) root: …/High-Energy` |
    | `pytest tests/python tests/golden -q` | **80 passed in 0.90 s** |
    | `time hep --help` | **0.039 s** (limit 0.3 s); no rich/yoda/ROOT/numpy/matplotlib in `sys.modules` after importing the CLI |
    | `hep plan x.toml` (not implemented) | exit 3, names P1-S05 |
    | `hep plna` | exit 2, "did you mean 'plan'?" |
    | completion | `complete -o nosort -F _hep_completion hep` after sourcing; cache written once; sourcing the env stays at ~20 ms |
