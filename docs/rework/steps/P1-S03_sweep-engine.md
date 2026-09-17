# P1-S03 — Port quantities, across, settle, studies and pins (with fixes)

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S02](P1-S02_config-schema.md) |
| Blocks | [P1-S04](P1-S04_identity-seeds-hash.md) |
| Effort | 1 d |
| Findings / decisions | 00/B6, B7, B9, B22; golden counts |
| Updated | 2026-09-17 |

## Goal

The sweep semantics of `eic.toml` work on schema 2 — coupled/grid groups, overlay, settle, studies, pins — and the four legacy bugs are fixed with regression tests.

## Context

- 03 §3–4; legacy semantics in `docs/plans/04_Roadmap.md` §1.4 (now in `legacy/docs/`).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:235-760` | Quantity, Sweep, Settle, read_*, flat_groups, set_groups, parse_across, apply_*, expand_points, naming helpers | port per 00b §1 |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Types: setting (key), beams (ids; `side`), energies, seed, card, generator, events, analysis, option
- B6: overlay/style never re-flatten coupled groups
- B7: validation after study and pins
- B9: lossless value rendering (`repr` for floats; exact ints/bools)
- B22: pin selector precedence (decide here: tag → exact value → `#N` index; record the rule)

**Out (non-goals)**

- Seeds and hashing (S04)
- card rendering (S05)

## Design notes

- Each legacy bug gets a test that first reproduces the old behaviour via `tools/rivpyth_common` (while it exists).

## Tasks

- [ ] Write `hekit/sweep/{quantity,select,expand,pages}.py`
- [ ] Regression tests
- [ ] Golden sweep test against `tests/golden/legacy_plan` (points/pages/legends, via in-memory v1→v2 read)

## Outputs

- `utils/python/hekit/sweep/*`
- `tests/python/sweep/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Bugs fixed | `pytest tests/python/sweep -q` | B6/B7/B9/B22 tests pass |
| Golden sets | `pytest tests/python/sweep/test_golden.py` | point sets and page groupings equal legacy for all studies |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
