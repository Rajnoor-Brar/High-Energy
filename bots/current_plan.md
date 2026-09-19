# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P5-S03 (replay equivalence, `hep events`) — done. **Phase P5 is complete.**

Both rows measured. The equivalence is **exact**, not "to rounding": a replayed store gives a YODA
identical to the generation's (1004 numbers, χ² = 0), because the same events go through the same
sinks in the same order.

`hep events` shows a store, any HepMC3 file, or a config (which generates a few events into a scratch
store first — one renderer, one data path). Tables with particle names, `--tree`, `--final`, `--hard`,
role colours, and a compressed shard is streamed through `zstd -dc` and cut off one event past the
last one asked for, so looking at three events never costs more.

## Next — P6-S01 (sharded Rivet and the concurrency modes)

**Phase P6 — concurrency and benchmarking.** Read `docs/rework/steps/README.md` for P6's order, then
`P6-S01_sharded-rivet.md`, and mirror it here before starting.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · **P4 6/6** · **P5 3/3 — phases P0–P5 all complete** · P6–P10 todo — 35 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
