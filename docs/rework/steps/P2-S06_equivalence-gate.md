# P2-S06 — Equivalence gate against the legacy FIFO pipeline

| Field | Value |
|---|---|
| Status | todo |
| Kind | test |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S05](P2-S05_rivet-sink-results-writer.md), [P0-S04](P0-S04_golden-fixtures.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md) |
| Effort | 0.5 d |
| Findings / decisions | F8; rule 1 |
| Updated | 2026-09-17 |

## Goal

The in-process path is proven equivalent to `generator.exe` → FIFO → `rivet` for the same card, seed and 1 thread.

## Context

- Golden mini run from P0-S04; comparison helper later becomes `hep compare`.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tests/golden/legacy_mini.toml`, legacy run outputs | reference | reuse |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `tests/integration/test_hep_run_vs_legacy.py` (label `slow`)
- `tests/tools/yodacmp.py`

**Out (non-goals)**

- Multi-thread equivalence (P6-S01)

## Design notes

- 20k events; expect identical bins up to ASCII precision; otherwise χ²-compatible; σ equals the value in the log.

## Tasks

- [ ] Write test + helper
- [ ] Run; attach table to the Log

## Outputs

- `tests/integration/test_hep_run_vs_legacy.py`
- `tests/tools/yodacmp.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Gate | `ctest -L slow -R equivalence` | pass; table in Log |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

n/a.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
