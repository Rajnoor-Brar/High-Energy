# P10-S02 — Final documentation pass

| Field | Value |
|---|---|
| Status | todo |
| Kind | docs |
| Phase | P10 — Cleanup, docs, release |
| Depends on | [P10-S01](P10-S01_cleanup-housekeeping.md) |
| Blocks | [P10-S03](P10-S03_portability-release.md) |
| Effort | 0.5 d |
| Findings / decisions | 00 §4.7 |
| Updated | 2026-09-17 |

## Goal

Docs describe the implemented system: user guide, generated config reference, new `docs/MAP.md`, rework docs marked implemented with deviations, `bots/` updated (with approval), step index closed.

## Context

- Legacy docs stay in `legacy/docs/`.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `docs/rework/*` | design | update status |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- docs only

**Out (non-goals)**

- Code

## Design notes

- Every documented command must appear in `hep --help` (test).

## Tasks

- [ ] Write guide
- [ ] Regenerate reference
- [ ] New MAP
- [ ] Mark rework docs
- [ ] Propose bots/ edits
- [ ] Close index

## Outputs

- `docs/**`
- `bots/**` (approved)

## Verification

| Check | Command | Expected |
|---|---|---|
| Links | link-check script | 0 broken |
| Commands | pytest docs-commands test | all present |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
