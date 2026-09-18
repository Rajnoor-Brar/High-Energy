# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P3-S05 (`hep run` end to end) — done. **Phase P3 is complete.**

`hep run` now plans, preflights, supervises, renders, writes results and explains them. All five
verification rows measured:

| Row | Result |
|---|---|
| e2e | 2 generations, each with YODA + summary + provenance + journal + logs |
| Study | 4-point PDF study at 20 k events, live dashboard under a pty: 4 done in 1m34s |
| Ctrl-C | exit 6, `analysis.partial.yoda` only, second point never started |
| Rerun | `0 done, 2 skipped`; `--rerun` redoes; a changed identity is refused |
| Preflight | `ProcessType = 2` → exit 3 before any spawn, nothing generated |

Eight defects found by wiring it up — the two that mattered: the skip rule never matched (bare digest
vs `sha256:`-prefixed, so every rerun looked like a collision), and Ctrl-C reached nothing, because
every stage has its own session and nobody forwarded the signal. Both fixed and covered.

## Next — P4-S01 (plot pipeline: load, select, transform, data map)

**Phase P4 — plotting, comparison, retiring the legacy tools.** Read
`docs/rework/steps/README.md` for P4's order, then `P4-S01_plot-pipeline.md`, and mirror it here
before starting. The pipeline reorganises the validated `rivpyth_common` plotting functions into
`hekit.plot.{io,select,transform,data,backends}`.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5 — phases P0–P3 all complete** · P4–P10 todo — 26 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
