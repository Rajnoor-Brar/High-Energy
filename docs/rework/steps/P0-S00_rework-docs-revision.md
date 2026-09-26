# P0-S00 — Revise the rework docs and write the step files

| Field | Value |
|---|---|
| Status | done |
| Kind | docs |
| Phase | P0 — Baseline, hygiene, legacy freeze |
| Depends on | — |
| Blocks | [P0-S01](P0-S01_baseline-tag.md) |
| Effort | 0.5 d |
| Findings / decisions | all (this revision) |
| Updated | 2026-09-17 |

## Goal

`docs/rework/` reflects every decision taken so far (D13–D23), the re-audit findings (`00/Bn`) and the step-based roadmap; `steps/` holds the index and one file per step; `docs/plans/` is marked superseded.

## Context

- Approved meta-plan mirrored in `bots/current_plan.md`.
- Decisions: HepMC store (D13), YODA-only results (D14), ROOT as processing (D15), house namespaces (D16), Lambda archived (D17), tools-into-repo first (D18), hotfix-then-port (D19), test bed (D20).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `docs/rework/*.md` (first revision) | structure and content | revise |
| Audit reports of `utils/`, Lambda, PhotoProduction (this session) | findings, porting map | summarise into 00 / 00b |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Docs under `docs/rework/`, banner in `docs/plans/README.md`, `bots/current_plan.md`, memory note.

**Out (non-goals)**

- Any code, config, `~/HEP` or `results/` change.

## Design notes

- New docs: 00b_PortingMap, 11_EventStore, 12_Processing, 13_Namespaces.
- Corrected 05 §3: `balanceLoad` makes the event set deterministic for fixed seed + threads.

## Tasks

- [x] Write new docs 00b, 11, 12, 13
- [x] Revise README and 00–10
- [x] Write steps/README.md and 55 step files
- [x] Supersession banner in docs/plans/README.md
- [x] Run consistency checks
- [x] Update memory

## Outputs

- `docs/rework/**`
- `docs/plans/README.md` (banner only)
- `bots/current_plan.md`

## Verification

| Check | Command | Expected |
|---|---|---|
| No stale design terms | `grep -rnE 'NtupleAnalyzer\|ntuple\.root\|hekit::\|analyzer::\|timing-dependent' docs/rework` | hits only in removed/withdrawn context |
| Links resolve | scratch link-check script over `docs/rework/**/*.md` | 0 broken |
| Index ↔ files | scratch script: index IDs = step files; deps exist; graph acyclic | OK |
| Scope | `git status --porcelain` | only `docs/`, `bots/current_plan.md` |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

`git checkout -- docs/ bots/current_plan.md` (docs only).

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00). Completed in the same run.
