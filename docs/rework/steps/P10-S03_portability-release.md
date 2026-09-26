# P10-S03 — Portability check and release tag

| Field | Value |
|---|---|
| Status | done |
| Kind | test |
| Phase | P10 — Cleanup, docs, release |
| Depends on | [P10-S02](P10-S02_docs-final.md) |
| Blocks | — |
| Effort | 0.25 d |
| Findings / decisions | N5, N6; 00/B38 |
| Updated | 2026-09-20 |

## Goal

A build with all optional components off works; `hep doctor` degrades cleanly; size report against budgets; tag `rework/v1`.

## Context

- Mac stack later.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 05 §8, 09 §2 budgets | numbers | compare |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- all-off build
- doctor degradation
- size report
- tag (approval)

**Out (non-goals)**

- Mac installation

## Design notes

- —

## Tasks

- [x] Build
- [x] Report
- [x] Tag

## Outputs

- tag `rework/v1`

## Verification

| Check | Command | Expected | Measured |
|---|---|---|---|
| All-off | `cmake -DHEKIT_WITH_RIVET=OFF -DHEKIT_WITH_HEPMC=OFF -DHEKIT_WITH_ONNX=OFF` | builds | **builds**, and `hep-run` plus 8 test binaries link. `ctest -L cxx`: **11/11 pass**. `hep-run --capabilities` reports `"components": []` and `spec_schema: 2` — it degrades to a working Pythia-and-YODA binary rather than a broken one |
| Doctor | `hep doctor` without optional tools | clear messages, exit 0 | **exit 0** with the toolchain hidden: names each missing module and what to check (`yoda: part of the YODA install; check PYTHONPATH`), and marks each generator `—` rather than failing |
| Sizes | line counts against 05 §8 and 09 §2 | near budgets | **C++ 1.48x** (4 659 non-comment lines against 3 150) — and 4 659 against the **10 404** it replaced. **Python 3.32x** (13 261 against ~4 000): *missed*, in every area by 2-5x. See the Log |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Delete tag.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — **done.** All three rows measured; `rework/v1` tagged with user approval. **The rework
  is complete: 54 of 55 steps, with P7-S07 blocked by D-Q6 (the Herwig rebuild, deferred by the
  user).**

  **N5 holds: a build with everything off is a working build.** With `RIVET`, `HEPMC` and `ONNX` all
  `OFF`, CMake configures, `hep-run` and eight test binaries link, and `ctest -L cxx` passes 11/11.
  `hep-run --capabilities` answers `"components": []` — it has degraded to a Pythia-and-YODA binary
  that still speaks the same spec schema, rather than to a binary that cannot start. That is the
  difference between optional and load-bearing, and it is now checked rather than assumed.

  **N6 holds: `hep doctor` degrades cleanly.** Run with the toolchain hidden it still exits **0**,
  names each missing module *and what to check* (`yoda: part of the YODA install; check
  PYTHONPATH`), and marks each generator `—` instead of erroring. A diagnostic that fails when
  things are broken is the one tool that must not.

  **The size report, honestly.**

  | | Budget | Measured (non-comment) | |
  |---|---|---|---|
  | C++ (`utils/`, excluding python) | 3 150 | **4 659** | 1.48x |
  | Python (`hekit`) | ~4 000 | **13 261** | **3.32x — missed** |

  The C++ number is defensible and the comparison that matters is the other one: **4 659 lines
  replaced 10 404**, covering more tools, with the store, the results layer and the module API that
  the old code did not have. Per group the overshoot is concentrated where the work turned out to
  be: `ML` + `Phys` at 2.9x (DIS invariants, jet parsing and selectors that the one-line budget row
  did not anticipate) and `Analyzer` at 1.8x (four analyzers, not two).

  **The Python budget was missed outright, in every area, by 2 to 5x**, and the reason is visible in
  how it was set: ~4 000 lines was scoped as "port `rivpyth_common`" (1 147 lines) plus some glue.
  What was actually built is a different size of thing — four external-generator adapters with a
  prepare cache (1 525), a phased supervisor with transport and signals (1 684), three fit backends
  and two histogram engines (1 432), a results layer with comparison statistics and housekeeping
  (1 653), a live terminal (1 274), two plot backends (1 370). None of those is padding; the
  estimate was made before any of them existed as a design. Recording it as a miss rather than
  quietly revising the budget, so the next estimate starts from a known error rather than a clean
  sheet.

  **And the degradation check found a defect of its own (00/B38).** Running `hep doctor --refresh`
  in the stripped environment wrote its findings to `~/.cache/hekit/doctor.json`, whose key was the
  install root alone — so the *next* `hep doctor` in a perfectly good shell was handed "herwig: not
  installed" for the following day. It surfaced as an unrelated test failing. Every check the probe
  makes resolves through `PATH` and `PYTHONPATH`, so those are now part of the key, and a report is
  reused only in the environment that produced it. Verified by probing rich → stripped → rich and
  watching the third answer come back complete.

  **Deviation.** The all-off build's `ctest` was run with `-L cxx` rather than in full. Its Python
  and `slow` tests resolve the canonical `build/` directory by design — that is how they find the
  binaries under test — so running them from a second build tree re-tests the first one and says
  nothing about portability. The meaningful check is that the all-off tree configures, compiles and
  passes its own C++ tests, which it does.
