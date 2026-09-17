# P0-S02 — Version and fix the shell environment

| Field | Value |
|---|---|
| Status | done |
| Kind | env |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S01](P0-S01_baseline-tag.md) |
| Blocks | [P0-S03](P0-S03_tools-into-repo.md) |
| Effort | 0.25 d |
| Findings / decisions | 00 §4.6; F10; plans 0.7; Q5 |
| Updated | 2026-09-17 |

## Goal

The shell layer lives in the repo as `env/hep_env.sh`; `~/HEP/setup.sh` is a stub that sources it; path handling is idempotent; ROOT and pythia8 Python modules import; `rich`, `tomli_w`, `pytest` are installed.

## Context

- `~/HEP/setup.sh` today: PYTHONPATH lacks `root/lib` and `pythia8/lib`; `RIVET_ANALYSIS_PATH=:~/Github/High-Energy/output/PhotoProduction:…` (empty entries, `~`); `_hep_prepend` not idempotent (`hep_refresh` duplicates); `hep_status` runs on every source; `quit` unsets itself.
- 08 §3 describes the target.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `~/HEP/setup.sh` | all functions (hep_status, quit, hep_refresh, cd helpers) | copy into `env/hep_env.sh`, then fix |
| 08 §3 table | change list | apply |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `env/hep_env.sh` (new, tracked)
- `~/HEP/setup.sh` stub (+ `setup.sh.pre-rework` backup)
- venv packages

**Out (non-goals)**

- `tools/` on PATH (P0-S03)
- `hep` completion (after P1-S01)

## Design notes

- Stub: `export HEP=$HOME/HEP HEP_INSTALL=$HEP/install HEKIT_ROOT=${HEKIT_ROOT:-$HOME/Github/High-Energy}; source "$HEKIT_ROOT/env/hep_env.sh"`.
- Idempotent prepend: `case ":${!1}:" in *":$2:"*) ;; *) export $1="$2${!1:+:${!1}}";; esac` (no trailing `:` on empty vars).
- Add `$HEP_INSTALL/root/lib` and `$HEP_INSTALL/pythia8/lib` to PYTHONPATH.
- Drop the hard-coded `RIVET_ANALYSIS_PATH` (the legacy tools prepend their plugin dir per run).
- `hep_status` on demand only; one-line hint on source.
- `quit` restores the saved PATH-like variables and does not unset itself.

## Tasks

- [x] Create `env/hep_env.sh` from the current file
- [x] Apply the fixes above
- [x] Back up `~/HEP/setup.sh` → `setup.sh.pre-rework`; write the stub (ask user before editing `~/HEP`)
- [x] `pip install rich tomli_w pytest` in `~/HEP/.venv`
- [x] Update `load_hep` alias if needed (it already sources the stub)

## Outputs

- `env/hep_env.sh`
- `~/HEP/setup.sh` (stub)
- `~/HEP/setup.sh.pre-rework`

## Verification

| Check | Command | Expected |
|---|---|---|
| Idempotent | `bash -ic 'source ~/HEP/setup.sh; source ~/HEP/setup.sh; hep_refresh; hep_refresh; for v in PATH LD_LIBRARY_PATH PYTHONPATH; do tr : "\n" <<<"${!v}" \| sort \| uniq -d \| wc -l; done'` | 0 0 0 |
| No empty elements | same shell: `[[ ":$PYTHONPATH:" != *"::"* ]] && echo ok` | ok |
| Imports | `python -c 'import ROOT, pythia8, yoda, rivet, lhapdf, rich, tomli_w, pytest'` | no error |
| Rivet still finds the plugin | `RIVET_ANALYSIS_PATH=$HEKIT_ROOT/output/PhotoProduction rivet --list-analyses photo_eic` | photo_eic listed |
| quit/refresh | `quit; quit; hep_refresh` | no 'command not found' |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`mv ~/HEP/setup.sh.pre-rework ~/HEP/setup.sh`; `pip uninstall rich tomli_w pytest` if needed.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-17 — **done.**
  - `env/hep_env.sh` created from `~/HEP/setup.sh` (backup: `setup.sh.pre-rework`). `~/HEP/setup.sh` is now an 8-line stub. The `load_hep` alias is unchanged, since it already sources the stub.
  - Fixes applied:
    - idempotent `_hep_prepend` (existing dirs only, no duplicates, no empty elements);
    - `PYTHONPATH` gains `root/lib` and `pythia8/lib`; the site-packages python version is detected, not hard-coded;
    - `RIVET_ANALYSIS_PATH` is no longer set;
    - `hep_status` runs on demand only; interactive sourcing prints a one-line hint.
  - **Additions beyond the design notes:**
    - `_HEP_ADDED` records each element that was added, so `quit` removes exactly those and restores `LHAPDF_DATA_PATH`/`ONNXRUNTIME_DIR`. `quit` stays defined and is a no-op when the environment is not loaded.
    - `HEP_SETUP` records the file that sourced `hep_env.sh`, and `hep_refresh` re-sources it. A fixed `~/HEP/setup.sh` made scratch testing hit the real file.
    - A child shell (variables inherited, functions not) gets the functions without mutating paths. Its `quit` also strips the venv `bin/`.
    - `hep_cd PROJECT [configs|results|output|sources]` (08 §3).
  - `pip install rich tomli_w pytest` installed rich 15.0.0, tomli_w 1.2.0 and pytest 9.1.1.
  - Verification, in a clean `env -i` interactive shell with the real stub:

    | Check | Result |
    |---|---|
    | Duplicates in PATH / LD_LIBRARY_PATH / PYTHONPATH | 0 0 0 (also CMAKE_PREFIX_PATH, PKG_CONFIG_PATH) |
    | No empty elements | ok, for all three |
    | `import ROOT, pythia8, yoda, rivet, lhapdf, rich, tomli_w, pytest` | ok (ROOT 6.40.04) |
    | `photo_eic` listed with an explicit `RIVET_ANALYSIS_PATH` | yes |
    | `quit; quit; hep_refresh` | exit 0; the second quit prints "HEP env not loaded" |
    | After `quit` | PATH is byte-identical to the original; PYTHONPATH, LD_LIBRARY_PATH, LHAPDF_DATA_PATH and VIRTUAL_ENV are unset |
    | Source time | 15 ms (the old file ran `hep_status` on every source) |
  - **Note for open shells:** a shell that loaded the old file needs a new terminal. The old `quit` unsets itself, and the paths it added are not recorded in `_HEP_ADDED`.
