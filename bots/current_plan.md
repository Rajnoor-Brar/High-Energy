# Current plan — P2-S02 pythia-parallel-spike (done) → next P2-S03

> Source: `docs/rework/steps/P2-S02_pythia-parallel-spike.md`. Index: `docs/rework/steps/README.md`.
> Status: **done** (2026-09-18). 17 of 55 steps.

## Decisions recorded

- **D-Q2 = chunk.** `k × run(chunk)` after one `init()` is safe; with a chunk size that is a multiple of
  the thread count the event set is bit-identical to one `run(N)`. Rule:
  `chunk = threads · ceil(target / threads)`, remainder last, chunk size in provenance.
- **D-Q1 = combine from the instances.** σ = Σwᵢσᵢ/Σwᵢ, err = √(Σ(wᵢerrᵢ)²)/Σwᵢ via `foreach`;
  `PythiaParallel` exposes no error at all.
- **D-SEEDS = explicit blocks, length checked by us.** Seeds are applied once in `init()`, never
  re-seeded; a short list is undefined behaviour in Pythia, so `hep-run` checks it.

## Next: P2-S03 core-status

`Core/{Types,Spec,Errors,Signals,Clock,Sha256,Paths}` and `Status/{Types,Writer,Heartbeat,Plain}`
(fd 3, rate limiting, deadline loop, stderr fallback, the `#ifdef Status` guard for X11), plus the
Python status reader. ctest: `core_spec`, `core_sha256` (FIPS vectors), `core_signals`,
`status_roundtrip`.
