# P0-S06 — Archive Lambda, old utils and stale docs into legacy/

| Field | Value |
|---|---|
| Status | todo |
| Kind | git |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | [P0-S01](P0-S01_baseline-tag.md), [P0-S04](P0-S04_golden-fixtures.md) |
| Blocks | [P0-S07](P0-S07_makefile-hygiene.md) |
| Effort | 0.5 d |
| Findings / decisions | D17; 00 §4.4, §4.5, §4.7; 00/B28; plans 0.4 (archived instead) |
| Updated | 2026-09-17 |

## Goal

All code and docs that the new stack replaces live in a tracked `legacy/` with history, a README and a porting guide; nothing outside `legacy/` includes them; PhotoProduction still builds.

## Context

- `archive/` is gitignored, `legacy/` is not.
- Can run in parallel with P0-S02…S05 once S01 and S04 are done (S04 needs `tests/` untouched only for its own new files).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| Audit notes (00 §4.4–4.5, 00b §4–5) | bugs, reuse list | write README/PORTING |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `git mv` of: `modules/Lambda{,.hh}`, `sources/Lambda`, `configs/lambda` → `legacy/lambda/`; `tests/*` except `tests/golden` → `legacy/tests/`; `utils/{Config,Monitor,Paint,Physics,Probe,Record,Utility}{,.hh}` → `legacy/utils/`; `_Paint.cc`, `_ThreadBench.cc`, `root_macros/` → `legacy/misc/`; `configs/{defaults,templates,all.toml,Paint.toml}` → `legacy/configs/`; `sources/PhotoProduction/photo_{5x41,10x100,18x275}.*` → `legacy/analyses/`; `configs/photo_zeus/README_ZEUS.txt` → `legacy/configs/photo_zeus/`; `docs/{MAP,Architecture,DataContract,UtilsAudit,UtilsDependencyMap,Audit}.md`, `docs/archive/`, `docs/plans/` → `legacy/docs/`; `tests/golden/results_inventory.json` → `legacy/results/PhotoProduction.inventory.json`.
- `legacy/README.md`: what, why, tags to build from (`legacy/lambda-final`), Lambda physics summary and bugs (00 §4.5), utils defects, port notes (00b §5).
- `legacy/PORTING.md`: snippet → target step table (00b §4).
- Proposal (not applied) for `bots/CLAUDE.md` and `bots/BOT.md` layout/testing sections.

**Out (non-goals)**

- Deleting anything
- editing `bots/` without approval

## Design notes

- Keep `docs/rework/` in place; `docs/` then holds only `rework/` (+ README pointer).
- Legacy Makefile targets for Lambda stop working — expected; document how to build from the tag.

## Tasks

- [ ] `git mv` per table
- [ ] Write `legacy/README.md`, `legacy/PORTING.md`, `docs/README.md` pointer
- [ ] Fix any path in docs/rework that points to moved docs
- [ ] Propose bots/ edits to the user
- [ ] Commit (approval)

## Outputs

- `legacy/**`
- `docs/README.md`

## Verification

| Check | Command | Expected |
|---|---|---|
| No stray includes | `git grep -nE '#include "(Config\|Monitor\|Probe\|Record\|Paint\|Physics\|Utility\|Lambda)' -- ':!legacy'` | empty |
| PhotoProduction builds | `make PhotoProduction/generator.exe PhotoProduction/photo_eic.so` | OK |
| History kept | `git log --follow --oneline legacy/utils/Utility/Sha256.hh \| head -3` | shows old commits |
| Legacy workflow intact | P0-S05 mini run in scratch | passes |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`git revert` the move commit.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
