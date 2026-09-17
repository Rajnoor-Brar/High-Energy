# Current plan — P0-S01 baseline-tag

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P0-S01_baseline-tag.md`.
> Step index: `docs/rework/steps/README.md`. Previous mirror (P0-S00 plan) is in git at `2364ccf:bots/current_plan.md`.
> Status: **in-progress** (started 2026-09-17).

## Goal

Everything the current PhotoProduction workflow depends on is committed; annotated tags `rework/baseline` and
`legacy/lambda-final` exist; the unversioned `~/HEP` tools are snapshotted with checksums.

## State found at start

- Tree clean on branch `rework`. The user already committed the in-flight work as one commit `2364ccf rework`
  (configs consolidation + deletions, `photo_eic.{cc,info,plot}`, `generator.cc`, Makefile, `docs/plans`,
  `docs/rework`, `bots/current_plan.md`) — instead of the 4 suggested logical commits. Not rewritten (history is
  the user's; splitting would need a rebase).
- No tags yet.

## Tasks

- [x] Commits — already done by the user (`2364ccf`); deviation recorded in the step Log
- [ ] `git tag -a rework/baseline 2364ccf`; `git tag -a legacy/lambda-final 2364ccf` — **needs user approval**
- [ ] `tar czf output/scratch/p0/hep-tools.tar.gz -C ~/HEP rivpyth ydplt ydmrg rivpyth_common.py rivpyth.example.toml setup.sh`
      + `sha256sum > SHA256SUMS` (scratch, gitignored)

## Verification

| Check | Command | Expected |
|---|---|---|
| Tree clean | `git status --porcelain` | empty (apart from this step's own doc/status edits) |
| Tags exist | `git tag -l 'rework/*' 'legacy/*'` | both listed |
| Baseline has configs | `git show rework/baseline:configs/PhotoProduction/eic.toml \| head -3` | prints the file |
| Snapshot intact | `cd output/scratch/p0 && sha256sum -c SHA256SUMS` | all OK |

## Out of scope

Pushing; any content change.

## Next

P0-S02 `env-setup-fixes` (`env/hep_env.sh`, `~/HEP/setup.sh` stub — `~/HEP` edit needs approval; venv packages).
