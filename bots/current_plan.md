# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P5-S02 (store and stream sources) — done

`Store/{Queue,Reader}.hh` + `Source/{Base,Replay}.hh` + the store adapter. The run loop now holds a
`Source::Base` and cannot tell a generator from a replay.

All three rows measured, and the replay row beat its own bar: a replayed store gives a YODA
**identical** to the generation's (1004 numbers, χ² = 0), not merely compatible. A generation-side
quantity on a store is refused with a hint; SIGINT gives exit 6 and a partial YODA.

**Defect found by replaying a real store:** two option variants became two generations sharing one
directory, and the second overwrote the first — a replay's hash folded in each *point's* analyses
instead of the group's. Now: two variants are one read, a different analysis set is a different point.

## Next — P5-S03 (replay equivalence and `hep events`)

Read `docs/rework/steps/P5-S03_replay-equivalence-events.md` and mirror it here before starting. It
formalises the replay equivalence (already true) and adds `hep events` for inspecting events — the
last step of P5.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · **P4 6/6** · P5 2/3 · P6–P10 todo — 34 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
