# ROADMAP: High-Energy Project Evolution

## Active Plan
See `PROPOSAL.md` for the current phased plan.

## Late Stage

- **Precompiled Headers (ROADMAP 5)**: Implement PCH for ROOT, Pythia8, and toml++ to reduce build times.
- **TThreadedObject Integration**: Evaluate and integrate `TThreadedObject` for safer multi-threaded histogram filling.
- **event_particles Schema Update**: Implement the expanded TOML schema for particle probing.
- **runParallel Deduplication**: Refactor `Parallel.hh` to deduplicate worker loop logic.
- **Record Traversal Optimization**: Combine `Record::fillCandidates` three-pass traversal into a single pass.
- **Record IO Deduplication**: Deduplicate `Record::write` and `Record::writeToDir`.

## Unconcerns

- **WorkerStats RAII**: Per-event overhead is negligible.
- **EventScope RAII**: Same as WorkerStats.
- **Reproducibility Metadata**: Standard `Meta::capture` is sufficient.
- **Register 4-way Split**: Superseded by the cleaner `HistConfig` approach.
