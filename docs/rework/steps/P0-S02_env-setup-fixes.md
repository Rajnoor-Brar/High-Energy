# P0-S02 — Version and fix the shell environment

| Field | Value |
|---|---|
| Status | todo |
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

- [ ] Create `env/hep_env.sh` from the current file
- [ ] Apply the fixes above
- [ ] Back up `~/HEP/setup.sh` → `setup.sh.pre-rework`; write the stub (ask user before editing `~/HEP`)
- [ ] `pip install rich tomli_w pytest` in `~/HEP/.venv`
- [ ] Update `load_hep` alias if needed (it already sources the stub)

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

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
