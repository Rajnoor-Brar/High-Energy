# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P2-S04 (source, event view, sink interface, run loop) — done

`hep-run SPEC` now runs Pythia end to end: `utils/{Events,Sink,Source,Run}` + a rewritten
`utils/apps/hep-run.cc` (942 lines). Every Verification row measured: `--check` → 0, `ProcessType = 2`
→ 3, bad key → 1, short seed list → 1 before Pythia starts (D-SEEDS), SIGINT → 6 at a chunk boundary,
`--capabilities` lists rivet + hepmc. Reference run: 200 events / 2 threads, σ = 70 819 ± 2212 pb,
chunk 20, seeds read back as planned.

Four defects found and fixed on the way (full detail in the step's Log): cumulative `workers` counts,
1-second status timestamps (`%.10g` on a Unix epoch), a relative path left in a written spec, and two
headers that named `Core::RunRecord` without including it.

Tests: ctest `run_rules` (chunk rule as a property, σ combination, `Sink::Count`) plus
`tests/python/run/test_hep_run.py` (25 cases against the real binary). Suite: 9/9 ctest, 359 Python.

## Next — P2-S05 (serial Rivet sink and atomic results writer)

Depends on P2-S04. Read `docs/rework/steps/P2-S05_rivet-sink-results-writer.md` and mirror it here
before starting, then implement `Sink::Rivet` and `Results::` writing, and record numbers in its Log.

## Progress

- P0 8/8 · P1 7/7 · P2 4/6 (S01–S04 done) · P3–P10 todo — 19 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
