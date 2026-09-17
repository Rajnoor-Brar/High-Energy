# P2-S02 — Decide chunked runs, σ error and seed blocks (spike)

| Field | Value |
|---|---|
| Status | todo |
| Kind | decision |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S01](P2-S01_cmake-skeleton.md) |
| Blocks | [P2-S04](P2-S04_source-run-loop.md) |
| Effort | 0.5 d |
| Findings / decisions | Q1, Q2; 00/B2; D21 |
| Updated | 2026-09-17 |

## Goal

Evidence-based answers to Q1 (σ error combination), Q2 (repeated `run()` after one `init()`) and D-SEEDS (`Parallelism:seeds` behaviour), recorded as decisions that P2-S04 implements.

## Context

- `PythiaParallel` has `foreach`, `run(n, cb)` returning per-thread counts, `sigmaGen()`, `weightSum()`; `balanceLoad` on by default.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `~/HEP/install/pythia8/include/Pythia8/PythiaParallel.h` | API | read |
| `configs/PhotoProduction/photo_ep.cmnd` | test card | use at low statistics |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `tests/spikes/pythia_parallel/` small C++ program + table output

**Out (non-goals)**

- Production code

## Decision record

- **Question:** Can `hep-run` call `run(chunk)` repeatedly after one `init()` without corrupting σ/weights? How is the merged σ error obtained? Does `Parallelism:seeds` set instance seeds as documented, also with chunked runs?
- **Options:**
  - A: chunked run + foreach σ-error combination + explicit seeds
  - B: single `run()` + cooperative stop; σ error 'unavailable' if not reproducible
  - C: mix (chunked if Q2 OK; error from `stat()` parsing)
- **Criteria:**
  - sigmaGen/weightSum/accepted counts equal between k×run(chunk) and run(N) (incl. N not divisible by threads)
  - error combination matches `stat(true)` to printed precision
  - instance seeds read back equal the requested block
- **Evidence:** (fill in: result table)
- **Decision:** (fill in)
- **Consequences:** 05 §4 text; P2-S04 implementation; risk table in 10 §3
- **Docs to update:** 05_EventPipeline.md §4, 10_Roadmap.md §5, steps/README.md decision register

## Tasks

- [ ] Write spike
- [ ] Run 3 configurations (threads 1/4/20)
- [ ] Fill decision record
- [ ] Update docs

## Outputs

- `tests/spikes/pythia_parallel/*`
- decision records D-Q1, D-Q2, D-SEEDS

## Verification

| Check | Command | Expected |
|---|---|---|
| Evidence attached | this file's Decision record | table present |
| Docs updated | `grep -n 'D-Q1\\|D-Q2' docs/rework/05_EventPipeline.md docs/rework/steps/README.md` | outcome recorded |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

n/a (decision).

## Done when

- [ ] every Verification row passes
- [ ] docs named in this step are updated
- [ ] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
