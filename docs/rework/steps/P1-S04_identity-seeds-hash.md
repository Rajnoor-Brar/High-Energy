# P1-S04 — Identity hashing and disjoint seed blocks

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P1 — Python core (hekit: config, sweep, plan) |
| Depends on | [P1-S03](P1-S03_sweep-engine.md) |
| Blocks | [P1-S05](P1-S05_plan-render.md), [P3-S03](P3-S03_results-provenance.md) |
| Effort | 0.5 d |
| Findings / decisions | 00/B1, B2, B15; D21 |
| Updated | 2026-09-18 |

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

- [x] Write `hekit/plan/{hashing,seeds}.py`
- [x] Property tests (hypothesis-free: enumerate all eic points)

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.**
  - **The seed function** (as the design note asks, stated exactly):

        stride    = smallest power of two ≥ max(threads, 1) and ≥ 1024
        blocks    = (900_000_000 − 1) // stride
        index     = int.from_bytes(sha256(b"hekit-seed/v1|" + run_seed + b"|" + hash)[:8], "big") % blocks
        base_seed = 1 + index · stride
        instances = [base_seed + i for i in range(threads)]        → `Parallelism:seeds`

    Blocks are aligned and `stride` wide, so two points share either their whole block or no seed at
    all. `stride ≥ 1024` means raising the thread count extends a block instead of moving it, so seeds
    are stable when a user re-runs with more threads. The domain prefix keeps these seeds from ever
    coinciding with another use of the same hash.
  - **Collisions.** 9·10⁸ seeds cannot hold 2²⁵⁶ hashes, so `assign()` checks the plan: the smaller hash
    keeps the block and the other probes upwards, deterministically by hash order rather than by point
    order. This is the only case where a seed depends on the rest of the plan; it is recorded as
    `SeedBlock.displaced` for provenance. For a 16-point plan the chance is about 1 in 7000.
  - **The hash** covers the base card's bytes, each extra card fragment, the **effective** overrides,
    the tool and its version, beams, energies, events, the replica, and (for a replay point) the store
    hash plus the analyses. `RECIPE_VERSION = 1` is part of it, so a future change to the input set can
    never compare equal to an old hash. Numbers hash by value (6 and 6.0 are one sample) and booleans
    match however the card spells them (`on`/`true`/`1`).
  - **Effective overrides (00/B15):** a setting equal to what the base card already says is dropped
    before hashing, so `pth6` hashes like the base point — verified on the real catalogue. The Pythia
    card parser lives in `hashing.card_defaults` for now; P1-S05 moves it into the adapter, and an
    unknown tool simply recognises nothing as redundant (a conservative hash, never a wrong one).
  - **Aliases:** `group_by_identity` returns one entry per generation with every name that maps to it.
  - **Skip rule:** `skip_decision(identity, name, existing)` → run / skip / conflict; a partial output is
    never complete, and a name with a different hash is a conflict with a message naming both hashes and
    pointing at `--rerun` (used by P3-S03).
  - **New config keys:** `[run].seed_policy = "identity" | "legacy"` and `[run].legacy_seed_step`
    (default 20). The legacy policy reproduces `seed + (position − 1)·step` and Pythia's own `seed + i`
    instance seeds, so P2-S06 can reproduce old results; it is documented as test-only.
  - **Verification** (on the frozen eic catalogue, translated to schema 2):
    | Check | Result |
    |---|---|
    | Stable across studies | `eic_18x275_ep_NNLO_pt32_mpi` and every other shared point hash identically in all 10 studies; the same point gets the same block from `single` and from `energies` |
    | Disjoint blocks | all points of all 10 studies (25 distinct generations) at 20 threads: no shared instance seed, all within 1…900000000 |
    | Order independence | shuffling the quantity tables leaves every hash unchanged (the *names* follow the catalogue, as intended) |
    | Aliases | `pth6` and the base point are one generation with two names: 4 generations for 5 points |
    | Whole suite | `pytest tests/python tests/golden -q` → **233 passed in 2.7 s** (24 new) |
