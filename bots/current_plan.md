# Current plan — P0-S02 env-setup-fixes

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P0-S02_env-setup-fixes.md`.
> Step index: `docs/rework/steps/README.md`. Status: **in-progress** (2026-09-17).
> Approved by the user for P0: tags, `~/HEP` edits, local per-step commits (no push), `bots/` layout edits.

## Goal

The shell layer lives in the repo as `env/hep_env.sh`; `~/HEP/setup.sh` is a stub that sources it; path handling is
idempotent; `import ROOT` and `import pythia8` work; `rich`, `tomli_w`, `pytest` are installed.

## Changes (08 §3, 00 §4.6)

- `env/hep_env.sh` (tracked) from `~/HEP/setup.sh`, with:
  - idempotent `_hep_prepend` (only existing dirs, no duplicates, no empty elements); records what it added;
  - PYTHONPATH += `$HEP_INSTALL/root/lib`, `$HEP_INSTALL/pythia8/lib`; python version detected, not hard-coded;
  - no hard-coded `RIVET_ANALYSIS_PATH` (the legacy tools prepend `plugin_dir` per run — verified in
    `rivpyth:204-206`, `ydplt:17-20`, `ydmrg:17-20`);
  - `hep_status` on demand only; one-line hint when an interactive shell sources it;
  - `quit` removes what was added and restores the scalars, does not unset itself, and is a no-op when not loaded;
  - `hep_refresh` = quit + source the stub; `hep_cd PROJECT [dir]` added;
  - `$HEP` stays on PATH until P0-S03 moves the tools to `$HEKIT_ROOT/tools`.
- `~/HEP/setup.sh` → stub (`HEP`, `HEP_INSTALL`, `HEKIT_ROOT`, source the repo file); backup `setup.sh.pre-rework`.
- `pip install rich tomli_w pytest` into `~/HEP/.venv`.

## Out of scope

`tools/` on PATH (P0-S03); `hep` completion / `hep_bootstrap` / `hep doctor` alias (after P1).

## Verification

| Check | Expected |
|---|---|
| source twice + `hep_refresh` twice → duplicate count for PATH, LD_LIBRARY_PATH, PYTHONPATH | 0 0 0 |
| `[[ ":$PYTHONPATH:" != *"::"* ]]` | ok |
| `python -c 'import ROOT, pythia8, yoda, rivet, lhapdf, rich, tomli_w, pytest'` | no error |
| `RIVET_ANALYSIS_PATH=$HEKIT_ROOT/output/PhotoProduction rivet --list-analyses photo_eic` | listed |
| `quit; quit; hep_refresh` | no "command not found" |

## Next

P0-S03 `tools-into-repo`.
