# P10-S03 — Portability check and release tag

| Field | Value |
|---|---|
| Status | todo |
| Kind | test |
| Phase | P10 — Cleanup, docs, release |
| Depends on | [P10-S02](P10-S02_docs-final.md) |
| Blocks | — |
| Effort | 0.25 d |
| Findings / decisions | N5, N6 |
| Updated | 2026-09-17 |

## Goal

A build with all optional components off works; `hep doctor` degrades cleanly; size report against budgets; tag `rework/v1`.

## Context

- Mac stack later.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 05 §8, 09 §2 budgets | numbers | compare |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- all-off build
- doctor degradation
- size report
- tag (approval)

**Out (non-goals)**

- Mac installation

## Design notes

- —

## Tasks

- [ ] Build
- [ ] Report
- [ ] Tag

## Outputs

- tag `rework/v1`

## Verification

| Check | Command | Expected |
|---|---|---|
| All-off | `cmake -DHEKIT_WITH_RIVET=OFF -DHEKIT_WITH_HEPMC=OFF -DHEKIT_WITH_ONNX=OFF …` | builds |
| Doctor | `hep doctor` without optional tools | clear messages, exit 0 |
| Sizes | `cloc utils/ --exclude-dir=python`, `cloc utils/python` | near budgets |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Delete tag.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
