# P10-S01 — Remove transition shims; housekeeping commands

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P10 — Cleanup, docs, release |
| Depends on | [P4-S06](P4-S06_retire-legacy-tools.md) |
| Blocks | [P10-S02](P10-S02_docs-final.md) |
| Effort | 0.5 d |
| Findings / decisions | rule 1 (end state) |
| Updated | 2026-09-17 |

## Goal

No transitional code remains outside `legacy/`: v1 reading only inside `migrate`, no `.v2` names, `sources/` gone; `hep clean` and `hep new analysis|project` exist.

## Context

- 07 §6.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| — | — | — |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- shim removal
- renames
- `hep clean`
- `hep new analysis|project`

**Out (non-goals)**

- —

## Design notes

- `hep clean --dry-run` reports sizes before deleting anything.

## Tasks

- [ ] Remove shims
- [ ] Rename
- [ ] Implement commands

## Outputs

- code + config renames

## Verification

| Check | Command | Expected |
|---|---|---|
| Clean greps | `git grep -nE 'rivpyth\|ydmrg\|NtupleSink\|RNTuple' -- ':!legacy' ':!docs/rework/10_Roadmap.md' ':!docs/rework/00_Audit.md'` | empty |
| Dry run | `hep clean --dry-run` | size report |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
