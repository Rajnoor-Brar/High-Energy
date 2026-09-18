# Current plan

Executing `docs/rework` step by step. Read order: `bots/BOT.md` → this file → `docs/rework/steps/README.md`
→ the step being executed. Design context: `docs/rework/README.md`; decisions in `10_Roadmap.md` §2 are final.

## Just finished — P2-S06 (equivalence gate) — done. **Phase P2 is complete.**

The gate passes **identically**. Both legacy point cards of the golden mini run went through `hep-run`
at one thread with the card's own seed, and every number agrees with the YODA the legacy
`generator.exe` → FIFO → `rivet` pipeline wrote:

| Point | Seed | Attempts | Events | σ (pb) new | σ (pb) legacy | Result |
|---|---|---|---|---|---|---|
| MSTW | 12345 | 5000 | 5000 | 71422.15821 | 71422.16 | 39 objects, 1004 numbers, χ² = 0 |
| NNLO | 12346 | 5000 | 4999 | 72994.84068 | 72994.84 | 39 objects, 1004 numbers, χ² = 0 |

The NNLO row reproduces the legacy run's 4999-written-of-5000-attempted exactly, which is what makes it
a real test of 00/B21. It also confirms D-Q2 (ten chunks of 500 = one run of 5000) and D4 (in-process
HepMC = what the FIFO carried) on real physics.

Defect the gate caught: the Rivet sink wrote no `/RAW/` objects, so `rivet-merge -e` refused our files
outright — the seed-replica merge path of 07 §3 was broken. Fixed; the merge chain is now verified end
to end (error falls by exactly 1/√2), pending `Reentrant: true` in P4-S05.

New: `tests/tools/yodacmp.py`, `tests/integration/test_hep_run_vs_legacy.py` (ctest `equivalence`,
label `slow`, 14.2 s), `pytest.ini`. Full `ctest`: 11/11.

## Next — P3-S01 (results layout and legacy move)

P2 is finished, so the next phase is **P3 — supervision, provenance and the run command**. Read
`docs/rework/steps/README.md` for P3's order and then `P3-S01`, mirror it here, and note that moving
`results/` needs the user's approval (roadmap rule 5) — ask before touching it.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6 — phase complete** · P3–P10 todo — 21 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
