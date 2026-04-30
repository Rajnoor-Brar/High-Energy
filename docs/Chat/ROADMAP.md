# Roadmap

## Active Plan

See PROPOSAL.md for the current phased plan.

## Late Stage

- Precompiled header for ROOT / Pythia8 / toml++.
- TThreadedObject-backed input-file pool for `Probe::runParallel`.
- `event_particles` TOML schema after Investigation E in [REVIEW.md](REVIEW.md).
- `Probe::runParallel` worker-loop dedup after Phase 4 lands (`utils/Probe/Parallel.hh:53-61,98-106`).
- `Lambda::fillCandidates` three-pass traversal (`modules/Lambda/Recording.hh:35-43`): either document why the three passes stay or combine them into one pass.
- `Record::write` / `writeToDir` deduplication (`utils/Record/Histogram.hh:128-159`).

## Unconcerns

- Former REVIEW 11: Per-event `WorkerStats` RAII helper remains readable enough as-is.
- Former REVIEW 12: The old four-way `Register` split is superseded by the `HistConfig` route in [PROPOSAL.md](PROPOSAL.md).
- Former REVIEW 17: Reproducibility metadata can wait until the phased source reshapes settle.
- Former REVIEW 19: `README.md` is useful, but it is not on the critical refactor path.
- ROADMAP 8: `EventScope` RAII is the same class of local boilerplate cleanup as former REVIEW 11.
- ROADMAP robustness unconcern: `tests/run_all.sh:26-29` breaking on first failure is acceptable for now.
- ROADMAP performance unconcern: `Watch::freeze()`'s dual allocation on the fatal path is acceptable for now.
- ROADMAP readability unconcern: `modules/Lambda/ParamAid.hh:42-47` indirection via `resolveCandidateLabels` is acceptable for now.
