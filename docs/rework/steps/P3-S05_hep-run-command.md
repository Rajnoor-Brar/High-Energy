# P3-S05 — Wire the hep run command end to end

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P3-S02](P3-S02_supervisor.md), [P3-S03](P3-S03_results-provenance.md), [P3-S04](P3-S04_terminal.md), [P2-S05](P2-S05_rivet-sink-results-writer.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md), [P7-S01](P7-S01_adapter-framework.md) |
| Effort | 0.5 d |
| Findings / decisions | R1–R6; rule 1 |
| Updated | 2026-09-17 |

## Goal

`hep run CONFIG [selectors]` plans, supervises `hep-run`, renders, writes results and provenance, honours `--check`, `--rerun`, `--detach`, `--events`, `--threads`, `--set`.

## Context

- 08 §2.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth:225-263` `main` | flow | replace |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/cli` run command
- `tests/e2e/mini.toml`

**Out (non-goals)**

- External generators (P7)

## Design notes

- `--check` runs `hep-run --check` for every group before spawning any run.

## Tasks

- [ ] Implement
- [ ] e2e tests in scratch

## Outputs

- CLI wiring
- `tests/e2e/mini.toml`
- `tests/integration/test_hep_run_e2e.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| e2e | `HEKIT_RESULTS=output/scratch/r hep run tests/e2e/mini.toml` | 2 groups, YODA + provenance |
| Study | 4-point PDF study at 20k (scratch) | completes with dashboard |
| Ctrl-C | interrupt mid-run | partial + exit 6; later points not started |
| Rerun | `hep run` again | done points skipped, partial redone |
| Preflight | config with ProcessType 2 | stopped before any spawn |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
