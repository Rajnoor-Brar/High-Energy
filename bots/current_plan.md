# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P4-S01 (plot pipeline) — done

`hekit/plot/{io,select,transform,data,plotfile}.py` (726 lines), 38 tests. The three verification rows:
the transforms are compared bin for bin against the legacy functions imported from `tools/` and match;
a data file with no `[plot.data].map` produces no overlay and a warning naming 00/B5; merged curves
each own their namespace so none can be lost to a collision (00/B17).

The pipeline is the validated legacy one, reorganised, with the findings fixed: explicit data map,
curve namespaces, no fixed temp paths (plus a per-run `MPLCONFIGDIR`), and option variants treated as
curves on a shared plot rather than separate pages.

## Next — P4-S02 (`hep plot` with the rivet-mkhtml backend)

Read `docs/rework/steps/P4-S02_plot-mkhtml.md` and mirror it here before starting. It puts the
pipeline behind the `hep plot` command with the default mkhtml backend.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · P4 1/6 · P5–P10 todo — 27 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
