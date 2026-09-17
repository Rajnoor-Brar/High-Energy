# Current plan — P1-S04 identity-seeds-hash (done) → next P1-S05

> Source: `docs/rework/steps/P1-S04_identity-seeds-hash.md`. Index: `docs/rework/steps/README.md`.
> Status: **done** (2026-09-18).

## What P1-S04 delivered

`hekit.plan.hashing` (identity hash of the effective generation settings, aliases, skip rule) and
`hekit.plan.seeds` (identity-derived, block-allocated seeds with a plan-level disjointness check, plus a
test-only legacy policy). 00/B1, 00/B2 and 00/B15 are fixed and verified on the real catalogue.

## Next: P1-S05 plan-render

`hep plan` / `hep studies`: points → groups → stage chains → spec-v2 `run.toml` + `point.cmnd` (in tmp);
the Pythia adapter (header, ids/energies, rejects `Beams:*` and `processAsync` in cards, √s warning);
Rivet options validated against the `.info` (00/B14); `plan/spec_v2.json` as the shared contract.
