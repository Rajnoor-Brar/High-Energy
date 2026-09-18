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

## Just finished — P3-S01 (serial label and the fate of legacy results) — done

Both questions decided with the user on 2026-09-18:

- **D-Q3 — the numeric serial stays, as an option, on the *study* directory**:
  `results/<project>/studies/[NN_]<study>[_<label>]/`, prefix form, `[run].serial` default on,
  `[run].label` optional. A point path stays name + hash, so points are still shared between studies and
  the skip rule still recognises them — a serial there is the drift the audit recorded. Implemented in
  P3-S03. (The roadmap had proposed no serial at all; this is the recorded compromise, and
  `[run].serial = false` gives the original behaviour.)
- **D-Q4 — moved and frozen.** 541 files → `results/PhotoProduction/legacy/`, file list compared before
  and after, **25 of 25 YODA checksums re-verified** against the P0-S06 inventory, and a README written
  beside them explaining why they cannot be rebuilt and what they may still be used for.

Docs updated: 07 §1, 10_Roadmap §2 (Q3, Q4 → answered), the decision register in `steps/README.md`.

## Next — P3-S02 (process supervisor, FIFO transport and stall detection)

Read `docs/rework/steps/P3-S02_supervisor.md` and mirror it here before starting. Note P3-S03 (results
layout) is where D-Q3's serial and D-Q4's `legacy/` line actually get implemented.

## Progress

- P0 8/8 · P1 7/7 · **P2 6/6 — phase complete** · P3 1/5 · P4–P10 todo — 22 of 55 steps done.

## Standing constraints

- Tests and dry runs never write into `results/` or `configs/`; use `output/scratch/` or `HEKIT_RESULTS`
  (legacy tools run from a scratch CWD). Enforced by `tests/conftest.py`.
- Approved by the user for this work: tags on 2364ccf, `~/HEP` edits, local per-step commits (never
  pushed), `bots/` layout edits. Anything else — pushes, moving `results/` — needs asking first.
- PhotoProduction is a test bed: physics, maths and logic must be right; specifics like e+ vs e- and tag
  names are not worth being pedantic about.
