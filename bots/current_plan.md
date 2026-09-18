# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P2-S05 (serial Rivet sink and atomic results writer) — done

Rivet now runs in process. A 200-event run writes `analysis.yoda` (17 `photo_eic` histograms,
`/_XSEC = 7.081873e+04 ± 2.212236e+03` pb — exactly the run's merged σ) plus `run.summary.json` with
counts, seeds read back, σ ± err and Pythia warning counts. SIGINT leaves `analysis.partial.yoda` and
never `analysis.yoda`; an unknown analysis is exit 1 before any event, under `--check` too.

Found on the way: the plan was pointing Rivet at `analyses/<project>` but not at
`build/analyses/<project>`, where the plugin actually is — fixed with `paths.build_root()`.

Tests: ctest `results_writer` + `tests/python/run/test_rivet_sink.py` (13 cases). Suite: 10/10 ctest,
372 Python.

## Next — P2-S06 (equivalence gate against the legacy FIFO pipeline)

Depends on P2-S05 and P0-S04. Read `docs/rework/steps/P2-S06_equivalence-gate.md` and mirror it here
before starting: same seeds through the new in-process path and the legacy FIFO path, compare the
YODAs, and record the tolerance actually needed.

## Progress

- P0 8/8 · P1 7/7 · P2 5/6 (S01–S05 done) · P3–P10 todo — 20 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
