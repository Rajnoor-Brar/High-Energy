# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P4-S03 (mplhep backend and house style) — done

`hep plot --backend mpl` renders publication figures from the **same** `.plot` keys the mkhtml backend
reads, so an analysis's labels live in one place. The house style is the legacy ROOT preset translated
(`Paint.toml`'s 900×600 canvas, margins and tick settings), not invented.

Visual check recorded in the step's Log: the real 4-point PDF study renders with LaTeX axis labels from
`photo_eic.plot`, `LogY`, the pipeline's auto-range, four colour-blind-safe curves with their sweep
legends, error bars and a ratio panel.

Caught by looking at it: `LegendTitle` (where the analysis states its cuts) was being ignored, and a
`#` in a colour inside an `.mplstyle` file starts a comment — the first figures were silently on the
default palette.

## Next — P4-S04 (`hep compare` and shared statistics)

Read `docs/rework/steps/P4-S04_compare.md` and mirror it here before starting: χ²/ndf, pulls and the
comparison table, shared with the plotting pipeline.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · P4 3/6 · P5–P10 todo — 29 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
