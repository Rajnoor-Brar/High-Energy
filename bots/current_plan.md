# Current plan — P0-S03 tools-into-repo

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P0-S03_tools-into-repo.md`.
> Step index: `docs/rework/steps/README.md`. Status: **in-progress** (2026-09-17).
> Approved by the user for P0: tags, `~/HEP` edits, local per-step commits (no push), `bots/` layout edits.

## Goal

`rivpyth`, `ydplt`, `ydmrg`, `rivpyth_common.py`, `rivpyth.example.toml` are versioned under `tools/` and are the
ones on PATH; debris is gone (plans 0.1, 00/B24, D18).

## Plan

1. Scratch CWD `output/scratch/legacy/` (symlinks `configs`, `output`, `datasets`, `sources` → repo; own `results/`),
   also reused by P0-S04.
2. "Before" snapshot: run the P0-S01 tarball copy of the tools (`output/scratch/p0/snapshot/`) with
   `rivpyth -p` for eic.toml (default + 10 studies) and zeus_validation.toml; keep stdout and the dry point cmnds.
3. Commit 1: verbatim copy into `tools/` (+x).
4. Commit 2:
   - `rivpyth` `EXAMPLE` reads `rivpyth.example.toml` next to the script (removes the duplicate text);
   - `env/hep_env.sh`: `$HEKIT_ROOT/tools` replaces `$HEP` on PATH;
   - `.gitignore`: `__pycache__/`;
   - remove `~/HEP/__pycache__` and the stale FIFOs in `output/PhotoProduction` (after `test -p`);
   - rename the `~/HEP` copies to `*.moved`.
5. "After" run with `tools/` on PATH; diff against the snapshot (stdout + point cmnds), and `--help` epilog equal.

## Verification

| Check | Expected |
|---|---|
| `which rivpyth ydplt ydmrg` | all under `$HEKIT_ROOT/tools/` |
| `rivpyth -p` for every study vs snapshot | identical (the dry-dir line is the same path) |
| FIFOs in `output/PhotoProduction`; `~/HEP/__pycache__` | none; absent |

## Out of scope

Behaviour changes (P0-S05).

## Next

P0-S04 `golden-fixtures`.
