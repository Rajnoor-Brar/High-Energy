# Current plan — P2-S01 cmake-skeleton (done) → next P2-S02

> Source: `docs/rework/steps/P2-S01_cmake-skeleton.md`. Index: `docs/rework/steps/README.md`.
> Status: **done** (2026-09-18). 16 of 55 steps.

## What P2-S01 delivered

CMake with nine `*-config` Find modules, AUTO/ON/OFF components, one INTERFACE library per facade
namespace, a `hep-run` stub that reports its capabilities, `rivet_<project>` targets from `analyses/*/`,
ctest running both the C++ checks and the Python suite, and `photo_eic` moved to
`analyses/PhotoProduction/`.

## Next: P2-S02 pythia-parallel-spike (decision)

Q2: repeated `run(chunk)` after one `init()` vs a single `run(N)` — is σ consistent?
Q1: merged σ error from `PythiaParallel` vs `stat()`.
D-SEEDS: does `Parallelism:seeds` behave as documented, including with chunked runs?
Record D-Q1, D-Q2, D-SEEDS with the measured numbers and the fallbacks.
