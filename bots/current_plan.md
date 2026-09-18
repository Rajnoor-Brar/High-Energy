# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P4-S02 (`hep plot`, mkhtml backend) — done

`hep plot` replaces `ydmrg` and `ydplt`. The golden row passes on every intermediate P0-S04 kept from
a real run of the old tools: voided curves bin for bin (NaNs included), the same number of voided
bins, identical `auto_range.plot`, the same remapped data YODA, and the same `rivet-mkhtml` argv —
for a page and for a single point.

The deliberate difference is 00/B5: the comparison passes the old tool's implicit name-matching map
**explicitly**, and without a map nothing is overlaid at all.

Also fixed: `hep plot` leaked a temp directory per page, and `hep analyses`/`hep build` claimed steps
(P1-S07, P2-S01) that are done but never implemented them — both are now real, and the skeleton test
finds the first unimplemented command rather than naming one, so it stops going stale.

## Next — P4-S03 (mplhep backend and house style)

Read `docs/rework/steps/P4-S03_plot-mpl-style.md` and mirror it here before starting. It renders
publication figures from the **same** `.plot` keys the mkhtml backend uses, so one label source serves
both backends.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · P4 2/6 · P5–P10 todo — 28 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
