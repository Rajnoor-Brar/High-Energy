# P2-S02 — Decide chunked runs, σ error and seed blocks (spike)

| Field | Value |
|---|---|
| Status | done |
| Kind | decision |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S01](P2-S01_cmake-skeleton.md) |
| Blocks | [P2-S04](P2-S04_source-run-loop.md) |
| Effort | 0.5 d |
| Findings / decisions | Q1, Q2; 00/B2; D21 |
| Updated | 2026-09-18 |

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
- **Evidence** (`tests/cxx/spikes/pythia_parallel_spike.cc`, Pythia 8.317, jets at √s = 200 GeV,
  pTHatMin 20, MPI and hadronisation off, identity seed block from 700001):

  | threads | events | chunks | chunk sizes | events | σ | event set |
  |---|---|---|---|---|---|---|
  | 1 | 400 | 4 | 100 each | same | same | **identical** |
  | 4 | 4000 | 4 | 1000 = 250×4 | same | same | **identical** |
  | 20 | 4000 | 2 | 2000 = 100×20 | same | same | **identical** |
  | 20 | 4000 | 3 | 1333, 1333, 1334 | same | **differs** | **differs** (statistically consistent) |
  | 4 | 4003 | 4 | 1000×3, 1003 | same | same | **identical** |
  | 20 | 4000 | 20 | 200 = 10×20 | same | same | **identical** |

  - **σ from the instances** (`foreach`, weighted by `info.weightSum()`) equals `PythiaParallel::sigmaGen()`
    **exactly** in every configuration. Its combined error behaves as 1/√N:
    ±1.24e-06 (1000 events) → ±9.2e-07 (2000) → ±7.49e-07 (3000) → ±6.45e-07 (4000).
  - **σ is cumulative across chunks**, not per chunk: `PythiaParallel` zeroes its accumulators at the
    start of each `run()` and recomputes them from the instances' own cumulative `info`, so after the
    last chunk it equals the value a single run would report.
  - **Against a serial reference** over the same number of events: 0.00σ (1 thread, same seed, so the
    events are identical), 0.85σ, −1.05σ, 0.90σ. The relative errors match (0.80 % parallel vs 0.79 %
    serial at 4000 events), so nothing is lost by combining rather than using `stat()`.
  - **`PythiaParallel` exposes no σ error at all** — only `sigmaGen()` and `weightSum()`
    (`PythiaParallel.h:65,68`), which is why the error has to come from the instances.
  - **Seeds:** `Parallelism:seeds` reaches the instances (read back exactly, before and after chunks) and
    `run()` never re-seeds — seeding happens once in `init()` (`PythiaParallel.cc:91-103`), so chunks
    continue the streams instead of repeating them.
  - **A seed list shorter than the thread count does not fail**, contrary to the documentation: 3 seeds
    with 4 threads initialised successfully, because `seeds[iPythia]` is an unchecked `std::vector`
    index (`PythiaParallel.cc:118`). That is undefined behaviour, so **hekit must guarantee the length
    itself**.
  - **`threads = 0`** resolves to `hardware_concurrency` (24 here) and derives seeds `Random:seed + i`,
    which is exactly the identity block, so leaving the list out is safe while the core count stays
    below the block stride (1024).
- **Decision:**
  - **D-Q2 = yes, chunk** (option A). `k × run(chunk)` after one `init()` is safe: counts and σ are
    correct, and with a **chunk size that is a multiple of the thread count** the event set is
    bit-identical to one `run(N)`. `Run::loop` therefore chunks, which is the only way to stop between
    chunks, since `PythiaParallel::run` cannot be interrupted from its callback.
    - **Rule for P2-S04:** `chunk = threads · ceil(target / threads)`, the remainder folded into the
      last chunk; the effective chunk size goes into provenance.
  - **D-Q1 = combine from the instances.** σ = Σwᵢσᵢ / Σwᵢ and error = √(Σ(wᵢ·errᵢ)²) / Σwᵢ over the
    instances, collected with `foreach`. No parsing of `stat()` output, and the number is never
    "unavailable".
  - **D-SEEDS = explicit blocks, validated by us.** `hep-run` checks
    `len(run.seeds.instances) == run.threads` before `init()` and exits 1 otherwise; the planner already
    writes exactly that many. With `threads = 0` the list is omitted deliberately.
- **Consequences:** 05 §4 text; P2-S04 implementation; risk table in 10 §3
- **Docs to update:** 05_EventPipeline.md §4, 10_Roadmap.md §5, steps/README.md decision register

## Tasks

- [x] Write spike
- [x] Run 3 configurations (threads 1/4/20) — six, including a chunk count that does not divide the total
- [x] Fill decision record
- [x] Update docs

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

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.** Decisions D-Q1, D-Q2 and D-SEEDS recorded above with the measured table.
  - **Deviation:** the spike lives in `tests/cxx/spikes/pythia_parallel_spike.cc` (not `tests/spikes/`),
    beside the other C++ tests but deliberately not registered in ctest — it is a measurement, not a test.
    It takes `threads events chunks` on the command line so the table can be reproduced.
  - **Two findings beyond the questions asked:**
    - a short `Parallelism:seeds` list is undefined behaviour rather than the documented failure, so the
      length check moves into `hep-run` (added to P2-S04's scope);
    - chunking only reproduces the unchunked event set when each chunk's per-thread split matches, hence
      the multiple-of-threads rule.
  - My first spike lost events to integer division (4000/3 → 3×1333), which briefly looked like a Pythia
    inconsistency; the remainder now goes into the last chunk.
