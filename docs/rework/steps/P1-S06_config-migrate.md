# P1-S06 — Migration tool and schema-2 configs

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S05](P1-S05_plan-render.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md) |
| Effort | 0.5 d |
| Findings / decisions | 00/B12, B14; 03 §6 |
| Updated | 2026-09-17 |

## Goal

`hep config migrate|reference|init|validate` exist; `eic.v2.toml` and `zeus_validation.v2.toml` are committed next to the originals; the config reference is generated.

## Context

- Transition: v2 files replace v1 at P4-S06; `.v2` suffix dropped in P10-S01.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Config/Reader.hh:79-102`, `legacy/utils/Monitor/Configure.hh:20-60` | removed-key tables | idea |
| `tools/rivpyth_common.py:90-100` | `MOVED_*` dicts | port |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- v1 → v2 map per 03 §6 (lepton → beams side b; old beams → energies; sections)
- Hand-reviewed v2 configs: B12 tag renames with a legacy alias map; B14 invalid quantities removed; explicit `[plot.data].map` or no data
- `docs/rework/reference/config.md` generated from schema metadata

**Out (non-goals)**

- Deleting v1 configs

## Design notes

- `migrate --stdout` for review; never overwrites without `--write`.

## Tasks

- [ ] Implement commands
- [ ] Migrate + hand-review both configs (approval for commit)
- [ ] Generate reference

## Outputs

- `utils/python/hekit/config/{migrate,reference}.py`
- `configs/PhotoProduction/{eic,zeus_validation}.v2.toml`
- `docs/rework/reference/config.md`

## Verification

| Check | Command | Expected |
|---|---|---|
| Round trip | `hep config migrate eic.toml --stdout \| hep config validate -` | valid |
| Same plan | pytest: plan(migrated file) vs plan(in-memory migration) | equal except documented renames |
| Deterministic reference | generate twice; diff | identical |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Delete the `.v2` files; revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
