# Current plan — P1-S03 sweep-engine (done) → next P1-S04

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P1-S03_sweep-engine.md`.
> Step index: `docs/rework/steps/README.md`. Status: **done** (2026-09-18).

## What P1-S03 delivered

`hekit.sweep` = quantity behaviour, selection (across/overlay/settle/study/pins), expansion into points,
pages and event groups. The four legacy sweep bugs are fixed with tests that first reproduce the old
behaviour through `tools/rivpyth_common`: 00/B6 (overlay no longer uncouples a group), 00/B7 (sweep rules
are judged on the scan that runs), 00/B9 (lossless values), 00/B22 (tag → value → `#N`, decided as D-B22).
The golden comparison reproduces all 17 legacy cases on points, pages and legends.

## Next: P1-S04 identity-seeds-hash

Canonical hash of the effective generation settings; identity seeds with disjoint per-thread
`Parallelism:seeds` blocks; replica index; collision check; equal-hash aliases; skip rule inputs;
test-only `seed_policy = "legacy"` (00/B1, B2, B15; 03 §5).
