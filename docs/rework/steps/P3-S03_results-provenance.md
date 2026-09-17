# P3-S03 — Results layout, skip rule and provenance

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P3-S01](P3-S01_decide-serial-and-legacy-results.md), [P1-S04](P1-S04_identity-seeds-hash.md) |
| Blocks | [P3-S05](P3-S05_hep-run-command.md), [P4-S01](P4-S01_plot-pipeline.md), [P5-S02](P5-S02_store-source-replay.md) |
| Effort | 0.75 d |
| Findings / decisions | 00/B3, B18; 07 §1–2 |
| Updated | 2026-09-17 |

## Goal

Point/group directories, study manifests, the name+hash+complete skip rule, partial handling and full provenance (JSON + YODA annotations) are implemented and redirectable via `HEKIT_RESULTS`.

## Context

- Decision Q3/Q4 from P3-S01.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Record/Meta.hh:25-110,243-299` | field list (git, host, compiler, file hashes) | port |
| `tools/rivpyth_common.py:755-800` | path resolution | replace (repo-root based) |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/results/{layout,manifest,skip}.py`, `hekit/prov/{provenance,stamp}.py`
- YODA annotations `HekitPoint/HekitHash/HekitGit` on `/_EVTCOUNT`
- orphan detection

**Out (non-goals)**

- Plotting

## Design notes

- All writes via tmp + rename.

## Tasks

- [ ] Implement
- [ ] Tests with tmp `HEKIT_RESULTS`

## Outputs

- `utils/python/hekit/{results,prov}/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Name collision | pytest: same name, different hash | error with `--rerun` hint |
| Partial | pytest: `analysis.partial.yoda` present | point reruns |
| Annotations | pytest: stamp then `yoda.read` | keys present |
| CWD independence | run from `/` | same layout |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
