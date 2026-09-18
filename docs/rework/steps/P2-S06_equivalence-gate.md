# P2-S06 — Equivalence gate against the legacy FIFO pipeline

| Field | Value |
|---|---|
| Status | done |
| Kind | test |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S05](P2-S05_rivet-sink-results-writer.md), [P0-S04](P0-S04_golden-fixtures.md) |
| Blocks | [P4-S06](P4-S06_retire-legacy-tools.md) |
| Effort | 0.5 d |
| Findings / decisions | F8; rule 1 |
| Updated | 2026-09-18 |

## Goal

The in-process path is proven equivalent to `generator.exe` → FIFO → `rivet` for the same card, seed and 1 thread.

## Context

- Golden mini run from P0-S04; comparison helper later becomes `hep compare`.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tests/golden/legacy_mini.toml`, legacy run outputs | reference | reuse |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `tests/integration/test_hep_run_vs_legacy.py` (label `slow`)
- `tests/tools/yodacmp.py`

**Out (non-goals)**

- Multi-thread equivalence (P6-S01)

## Design notes

- 20k events; expect identical bins up to ASCII precision; otherwise χ²-compatible; σ equals the value in the log.

## Tasks

- [x] Write test + helper
- [x] Run; attach table to the Log

## Outputs

- `tests/integration/test_hep_run_vs_legacy.py`
- `tests/tools/yodacmp.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Gate | `ctest -L slow -R equivalence` | pass; table in Log |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

n/a.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **the gate passes identically.** The two legacy point cards of the golden mini run
  (P0-S04) went through `hep-run` at one thread with the seed written in the card, and the resulting
  YODA was compared against the YODA the legacy `generator.exe` → FIFO → `rivet` pipeline produced.

  | Point | Seed | Attempts | Events | σ (pb), new | σ (pb), legacy log | Objects | Numbers | Result |
  |---|---|---|---|---|---|---|---|---|
  | `mini_27x920_ep_MSTW` | 12345 | 5000 | 5000 | 71422.15821 ± 415.579759 | 71422.16 | 39 | 1004 | identical, χ² = 0 (0/320) |
  | `mini_27x920_ep_NNLO` | 12346 | 5000 | 4999 | 72994.84068 ± 433.984786 | 72994.84 | 39 | 1004 | identical, χ² = 0 (0/333) |

  "Identical" is literal: every value and every error agrees at `rtol = 1e-6`, and χ² over the bins is
  exactly zero — the two pipelines wrote the same numbers, `/RAW/` copies included. The comparison
  covers 17 finalized histograms, their 17 raw counterparts, `/_XSEC` and `/_EVTCOUNT`.

  The `NNLO` row is the one that earns its keep: the legacy run attempted 5000 events and wrote 4999,
  and the new run reproduces **both** numbers. A pipeline that treated attempts as successes (00/B21)
  would agree everywhere else and disagree here.

  This also settles two things by measurement rather than by argument: chunking does not change the
  event set (D-Q2 — the new run generated in ten chunks of 500, the legacy one in a single call to
  `PythiaParallel::run`), and in-process HepMC conversion produces the same events the FIFO carried
  (D4).

  **Defect found by the gate:** the Rivet sink wrote `getYodaAOs()` with its default
  `includeraw = false`, so our files had 20 objects where the legacy ones had 39 — and
  `rivet-merge -e` refused them outright (`Missing cross-section for /RAW/_XSEC`). Since 07 §3 merges
  seed replicas exactly that way, the whole merge path was broken and no test before this one would
  have noticed. Fixed in `Sink::Rivet::finish` (`includeraw = true`), which is also what the legacy
  `rivet` command did.

  With that fixed, the merge chain was verified end to end: `rivet-merge -e` on two copies of one run
  gives the identical value with the error scaled by exactly 1/√2 (0.70710687) — but only once
  `photo_eic` declares `Reentrant: true`. As it stands (`Reentrant: false`) the merge keeps the run
  scalars and silently drops the histograms, which is what P4-S05 is for. The test asserts what is
  true today and says where it tightens.

  **Outputs**

  - `tests/tools/yodacmp.py` — object/bin comparison with `--rtol`, `--atol`, `--raw` and `--chi2`,
    usable by hand and destined to become `hekit.compare` in P9-S02.
  - `tests/integration/test_hep_run_vs_legacy.py` — 9 cases, marked `slow`, registered as the ctest
    test `equivalence` (14.2 s). `ctest -L slow -R equivalence` passes; the full `ctest` is 11/11.
  - `pytest.ini` — declares the `slow` marker (the repository had no pytest configuration at all).

  **Deviations**

  1. **5000 events, not the 20k the design note guessed.** The golden reference captured in P0-S04 is
     5000 events per point, and comparing against a stored reference is worth more than a larger run
     compared against a freshly rerun legacy pipeline. Two points at 5000 give 1004 compared numbers
     and 320–333 bins with a defined error, which is ample to catch a changed event sequence.
  2. The gate writes a **hand-built minimal spec** rather than one from `hep plan`, deliberately:
     the comparison is against the *legacy card*, so nothing `hep plan` renders may come between the
     two pipelines. `hep plan`'s own agreement with the legacy card is already a golden test (P1-S05).
  3. C++ tests live in `tests/cxx/`, not `tests/cpp/` as this step file's Outputs say — a naming choice
     made in P2-S01 and used since; the step's `tests/cpp/rivet_*` became `tests/cxx/test_results_writer.cc`
     in P2-S05 and this gate in Python, where the YODA reader is.
