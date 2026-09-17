# P1-S04 — Identity hashing and disjoint seed blocks

| Field | Value |
|---|---|
| Status | todo |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S03](P1-S03_sweep-engine.md) |
| Blocks | [P1-S05](P1-S05_plan-render.md), [P3-S03](P3-S03_results-provenance.md) |
| Effort | 0.5 d |
| Findings / decisions | 00/B1, B2, B15; D21 |
| Updated | 2026-09-17 |

## Goal

Every point has a canonical hash of its effective generation settings; its seeds derive from that hash and are disjoint across all instances of all points in a plan; physics-identical points collapse into one generation with aliases.

## Context

- 03 §5; `Parallelism:seeds` (Pythia `Parallelism.xml:155`); runtime behaviour confirmed in P2-S02.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth_common.py:660-716` `build_point` | claim/clash logic | adapt |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- Canonical JSON: base card sha256, effective overrides (value equal to base card = unset), tool+version, events, beam ids/energies, replica index
- `seed_point = f(run.seed, hash)` stable; instance block `[s_i]` of size threads; plan-level collision check
- Aliases: same hash, different names → one group
- Skip rule predicate: name + hash + complete output (used in P3-S03)
- Test-only `seed_policy = "legacy"`

**Out (non-goals)**

- Writing seeds into cards (S05)

## Design notes

- Choose `f` so blocks never overlap for any 2 points in a plan (e.g. derive a 31-bit base from the hash and space by a large stride; resolve collisions deterministically). Document the exact function in the step log.

## Tasks

- [ ] Write `hekit/plan/{hashing,seeds}.py`
- [ ] Property tests (hypothesis-free: enumerate all eic points)

## Outputs

- `utils/python/hekit/plan/{hashing,seeds}.py`
- `tests/python/plan/test_identity.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Stable across studies | pytest: point `18x275_ep_NNLO_pt32_mpi` in studies energies/mpi/mpi_grid | same seed |
| Disjoint blocks | pytest: all eic points × 20 threads | no shared instance seed |
| Order independence | pytest: shuffle catalogue | same seeds/hashes |
| Aliases | pytest: `pth6` vs base | one group, two names |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
