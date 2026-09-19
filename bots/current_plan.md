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

## Just finished — P6-S01 (sharded Rivet and the concurrency modes) — done

Serial and sharded analyse the **same 50 000 events** and write YODAs that are **identical to the
precision YODA writes** — 53 of 55 objects, `rtol = 0`. σ and sumW are exactly equal. Sharded is
**1.67x faster on four threads**.

**Two findings, both recorded in the audit.**

- **00/B31 — jet clustering cannot be sharded.** SISCone keeps its clustering cache
  (`stored_siscone`, `stored_plugin`, `stored_particles`) and its RNG (`local_ranlux_state`) in
  process-wide statics in *every* FastJet build, and this FastJet is built without
  `FASTJET_HAVE_LIMITED_THREAD_SAFETY` besides. A race changes the jets rather than crashing.
  `photo_eic` runs kT, anti-kT and SISCone, so it always runs serially; `auto` refuses before the
  first event and says why, and an explicit `sharded` stops right after `init()` if a `FastJets`
  turns up. The equivalence had to be measured with a jet-free analysis instead.
- **00/B32 — a sink exception would have called `std::terminate`.** `PythiaParallel` runs the
  callback on its worker threads in *both* modes (`processAsync = off` only adds a mutex), so a
  Rivet error mid-run was unwinding through `std::thread`. Both sources now catch at that boundary.

Also settled: **`fill` merges, `set` does not** — `MC_XS` is re-entrant and still has one object it
`set()`s from the per-event running σ, which no merge can reconstruct. That is the rule P8-S01 has
to follow for module results.

## Next — P6-S02 (shared generation for analysis-only variants)

Read `docs/rework/steps/P6-S02_event-groups.md` and mirror it here before starting.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · **P4 6/6** · **P5 3/3 — P0–P5 all complete** · P6 1/3 · P7–P10 todo — 36 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
