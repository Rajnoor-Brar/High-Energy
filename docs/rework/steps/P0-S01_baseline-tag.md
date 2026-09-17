# P0-S01 — Commit the in-flight work and tag the baseline

| Field | Value |
|---|---|
| Status | todo |
| Kind | git |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S00](P0-S00_rework-docs-revision.md) |
| Blocks | [P0-S02](P0-S02_env-setup-fixes.md), [P0-S06](P0-S06_legacy-archive.md) |
| Effort | 0.1 d |
| Findings / decisions | 00 §4.7; plans/B2 |
| Updated | 2026-09-17 |

## Goal

Everything the current PhotoProduction workflow depends on is committed in logical commits; annotated tags `rework/baseline` and `legacy/lambda-final` exist; the unversioned `~/HEP` tools are snapshotted with checksums.

## Context

- Uncommitted today: `configs/PhotoProduction/{eic.toml,photo_ep.cmnd,zeus_validation.toml}` (untracked), `sources/PhotoProduction/photo_eic.*` (untracked), `generator.cc` edits, deletions of old per-variant cmnds and eic*.toml, `Makefile`, `docs/plans`, `docs/rework`, `bots/current_plan.md`.
- **Needs user approval** for every commit and tag (BOT.md, roadmap rule 5).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `git status` (P0-S00 end) | file list | group into commits |
| `~/HEP/{rivpyth,ydplt,ydmrg,rivpyth_common.py,rivpyth.example.toml,setup.sh}` | snapshot | tar + sha256 |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Commits, two annotated tags, a scratch tarball.

**Out (non-goals)**

- Pushing to a remote (ask separately)
- any file content change

## Design notes

- Suggested commits: (1) PhotoProduction configs consolidation (+ deletions), (2) `photo_eic` plugin + Makefile metadata copy, (3) `generator.cc` base+point CLI, (4) docs (plans + rework + bots/current_plan.md).
- `legacy/lambda-final` points at the same commit as `rework/baseline` (Lambda code is unchanged there).

## Tasks

- [ ] Show the proposed commit grouping to the user and get approval
- [ ] Create the commits (with the session's attribution trailer)
- [ ] `git tag -a rework/baseline -m …`; `git tag -a legacy/lambda-final -m …`
- [ ] `tar czf output/scratch/p0/hep-tools.tar.gz -C ~/HEP rivpyth ydplt ydmrg rivpyth_common.py rivpyth.example.toml setup.sh` + `sha256sum > SHA256SUMS`

## Outputs

- commits
- tags `rework/baseline`, `legacy/lambda-final`
- `output/scratch/p0/hep-tools.tar.gz`, `SHA256SUMS` (gitignored)

## Verification

| Check | Command | Expected |
|---|---|---|
| Tree clean | `git status --porcelain` | empty |
| Tags exist | `git tag -l 'rework/*' 'legacy/*'` | both listed |
| Baseline has configs | `git show rework/baseline:configs/PhotoProduction/eic.toml \| head -3` | prints the file |
| Snapshot intact | `cd output/scratch/p0 && sha256sum -c SHA256SUMS` | all OK |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Tags: `git tag -d`; commits: `git reset --soft HEAD~N` (before any push).

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
