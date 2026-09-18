# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P4-S05 (photo_eic re-entrant, plugin defects) — done

Three plugin changes, each measured:

| Row | Result |
|---|---|
| Merge | `rivet-merge -e` of 2×20 k vs one 40 k run → **χ²/ndf = 0.602 over 378 bins** |
| Leak | ASan 1 k events: 74 allocations before, **73 after** — exactly the 80-byte `SISConePlugin` |
| Orientation | proton as beam B (orientation = −1 confirmed): 17 of 17 histograms filled |
| Dumps | `analysis.dump.yoda` written and **finalized** (`ScaledBy`, `/_XSEC`, cross-section values) |

**00/B26 turned out not to be a defect** — the audit had it as "unverified". Rivet 4.1.3 normalises an
inverted range, and both versions give byte-identical output; the cut is now written symmetrically so
it cannot depend on that. The audit row is updated to say so.

`Reentrant: true` is earned rather than asserted, and both equivalence gates still pass bin for bin
after the plugin change.

## Next — P4-S06 (retire rivpyth/ydplt/ydmrg and generator.cc). **P4 finishes with it.**

Read `docs/rework/steps/P4-S06_retire-legacy-tools.md` and mirror it here before starting. It moves
`tools/` into `legacy/tools/` and removes the `~/HEP/*.moved` files — note that `~/HEP` edits and the
move both need care, and the plot tests import `tools/rivpyth_common.py` today, so that comparison has
to be retired with it.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · P4 5/6 · P5–P10 todo — 31 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
