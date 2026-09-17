# P1-S05 — Plan groups, stage chains, resolved specs and point cards

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S04](P1-S04_identity-seeds-hash.md) |
| Blocks | [P1-S06](P1-S06_config-migrate.md), [P1-S07](P1-S07_doctor-pdf.md), [P2-S04](P2-S04_source-run-loop.md), [P6-S02](P6-S02_event-groups.md) |
| Effort | 1 d |
| Findings / decisions | 00/B14; F2 |
| Updated | 2026-09-17 |

## Goal

`hep plan` and `hep studies` show points → groups → stage chains and write resolved `run.toml` + `point.cmnd` to a temporary directory; the Pythia and Rivet adapters validate their parts.

## Context

- 02 §3–4, 03 §7, 04 §3; spec contract shared with C++ tests.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:786-840` | `execution_plan`, `write_point_cmnd`, `plot_file_for`, `common_analysis` | port |
| `tools/rivpyth:128-146` | `print_point` output shape | adapt for `hep plan` |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/plan/{model,build,naming,spec}.py` + `spec_v2.json` (JSON Schema)
- `hekit/adapters/{base,pythia,rivet,store}.py`: card header (base sha256, origin); ids/energies rendering; `Parallelism:seeds`; reject raw `Beams:*` and `processAsync` in cards/overrides; √s-with-different-ids warning; Rivet options checked against the plugin `.info` `Options:`
- `hep plan [--json] [--explain KEY]`, `hep studies`

**Out (non-goals)**

- `--check` preflight (needs `hep-run`, P2-S04)
- external adapters (P7)

## Design notes

- Rendered files go to a per-invocation temp dir; never into `results/`.

## Tasks

- [ ] Implement modules
- [ ] CLI wiring
- [ ] Golden tests against legacy point cmnds (settings modulo seeds)
- [ ] Test that zeus R/ETMIN option quantities are rejected

## Outputs

- `utils/python/hekit/{plan,adapters}/*`
- `tests/python/plan/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Counts | `hep plan configs/PhotoProduction/eic.v2.toml --study energy_pdf --json \| jq '.points\|length, .pages\|length'` (after S06; before: in-memory v1) | 16, 4 |
| Cards | pytest golden | settings equal legacy except seeds |
| Option validation (B14) | pytest: zeus config | error naming R/ETMIN |
| Guard | pytest session | no writes to results/configs |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
