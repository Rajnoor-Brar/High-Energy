# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P4-S06 (retire the legacy tools) — done. **Phase P4 is complete.**

The gate first: the `pdf` study at **100 k events per point** through both toolchains gives χ²/ndf of
1.085, 1.227, 1.129 and 1.043 over ~410 bins each, with σ agreeing to 0.2–0.4 %. Independent samples,
so ≈1 is the right answer.

Then, with your approval: `tools/*` and `generator.cc` → `legacy/`, `sources/` gone, the v2 configs
promoted to `eic.toml`/`zeus_validation.toml` (originals archived), `tools/` off PATH, the Makefile
reduced to a CMake wrapper, and the five `~/HEP/*.moved` files deleted — two of which were pre-hotfix
originals, located in git (`73658d0`) before deleting.

**Worth knowing:** `which rivpyth` still finds `~/.local/bin/rivpyth` — an *older standalone bash*
script with a different interface that predates the Python tool. It is outside the repo and outside
what was approved, so it was left alone.

14/14 ctest; `hep plan/run/plot` verified end to end on the promoted config.

## Next — P5-S01 (Store namespace, store sink and store CLI)

**Phase P5 — the HepMC3 event store and event inspection.** Read `docs/rework/steps/README.md` for
P5's order, then `P5-S01_store-writer.md`, and mirror it here before starting.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6** · **P3 5/5** · **P4 6/6 — phases P0–P4 all complete** · P5–P10 todo — 32 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
