# REVIEW: Project Status and Architectural Investigations

## Surviving Open Items

1. **Driver/App skeleton (Former 13)**: Scope reduced after Phase 2 AnalysisContext work. Reassess after Phase 2 lands.
2. **Doc-comment headers on umbrellas (Former 21)**: Add standard Doxygen-style headers to `Lambda.hh`, `Config.hh`, etc.
3. **Cross-link docs (Former 22)**: Ensure `ROADMAP.md`, `REVIEW.md`, and `PROPOSAL.md` are cross-referenced.

## Investigations

### A. BranchControl/Probe namespacing
**Findings**: `utils/Probe/Schema.hh` (to be `BranchControl.hh`) contains low-level ROOT branch manipulation utilities in `Probe::detail`. Moving these to `Probe::BranchControl` improves semantic clarity. The core `Probe` functions in `Probe.hh` are the primary interface, while `BranchControl` handles the "plumbing". This separation is beneficial for maintainability.

### B. AsyncLogger queue shape
**Findings**: `AsyncLogger` currently uses a `std::vector<ThreadSnapshot> dirtyThreadSnapshots_` which is swapped and processed in the `runLoop`. This is an efficient batching strategy. Robustness could be improved by adding an exception aggregation mechanism to catch and report errors occurring within the logging thread or the worker threads.

### C. Abstraction pair 1 (Contexts)
**Findings**: `Lambda::AnalysisContext` and `Lambda::GenerationContext` share several fields (`logParams`, `logger`). Combining them into a base `Context` or a unified `DriverContext` would reduce duplication and clarify what is "common" vs "specific" to analysis or generation.

### D. Abstraction pair 2 (Watch/Snapshot)
**Findings**: `Config::Watch` is the "live" state with atomics/mutexes, while `Monitor::RunSnapshot` is a point-in-time POD copy. Unifying them is challenging because `Watch` must remain thread-safe for writing, while `RunSnapshot` must be cheap to pass around for rendering. The current `Watch::freeze()` approach is the correct pattern.

### E. event_particles TOML schema
**Findings**: The proposed schema `[[(string)name, (Int)Spec, (string)treeName, [(strings)specBranchNames], (string/char)branchType]]` is viable and would allow for more flexible data extraction in `Probe`. This requires updating `Config::ProbeParticle` and `Config::readProbeSection`.

## Unconcerns

- **Former REVIEW 11**: Per-event WorkerStats RAII — readable as-is.
- **Former REVIEW 12**: Register four-way split — superseded by HistConfig approach.
- **Former REVIEW 17**: Reproducibility metadata — implemented in `Meta.hh`.
- **Former REVIEW 19**: README.md — basic version exists.
- **ROADMAP 8**: EventScope RAII — same rationale as REVIEW 11.
- **ROADMAP Robustness**: Unifying event counters to atomics.
- **ROADMAP Performance**: Parallel loop efficiency.
- **ROADMAP Readability**: Snake_case to camelCase.
- **REVIEW 6 (ScalarSpec)**: User reported fixed; although `ScalarSpec` remains in source, it is no longer an active concern.
