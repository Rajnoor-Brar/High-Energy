# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P4-S04 (`hep compare` and shared statistics) — done

`hekit/results/{stats,compare}.py` + the `hep compare` command, 22 tests. Both verification rows
measured on fixtures whose answers are known by hand (one combined error apart → χ²/ndf = 1; two →
4), and two binnings with no shared edges give **no** χ² rather than a misleading number.

Three things never enter a χ² and are counted in the row's note instead: unaligned bins, voided bins
(a void is "no information", not a measurement of zero) and bins with no error.

On the real 4-point study: NNPDF2.3 LO sits at χ²/ndf ≈ 1.1–1.4 against MSTW08 LO, the NLO set and
PDF4LHC21 at ≈ 3.2–5.7 — which is what a PDF study is meant to show.

## Next — P4-S05 (make `photo_eic` re-entrant and fix plugin defects)

Read `docs/rework/steps/P4-S05_photo-eic-reentrant.md` and mirror it here before starting. P2-S06
already proved the merge chain works once the analysis declares `Reentrant: true`, so this closes that
loop; it also fixes the plugin defects the audit recorded.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · P4 4/6 · P5–P10 todo — 30 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
