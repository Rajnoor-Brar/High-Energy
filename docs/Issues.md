# Issues - Active Investigation

Updated: 2026-05-21.

This file tracks active issues and mismatches in the current `modules/` and
`utils/` code. Longer-term improvements live in [REVIEW.md](REVIEW.md).
Architecture and runtime ownership are summarized in [MAP.md](MAP.md) and
[Architecture.md](Architecture.md). TOML flow is in [DataFlow.md](DataFlow.md).

The active pipeline is now a three-stage threaded system:

1. Probe reads ROOT input with `probe_threads`.
2. Probe collectors or worker callbacks invoke Lambda analysis with
   `analysis_threads` or direct worker threads.
3. Writer drains fill requests with `writer_threads`, using worker-local ROOT
   clones where possible and a watchdog for lifecycle writes.

## P0 - Stage-Level Throughput Measurement Required

The bottleneck varies by stage ratios; no single `nThreads` knob governs total
throughput. The question is which stage is limiting under the current per-stage
config:

- `[probe].probe_threads`
- `[probe].analysis_threads`
- `[record].writer_threads`
- `[pythia].pythia_threads` for Pythia drivers

### Active Suspect Ranking

| Rank | Suspect | Current evidence | What would confirm it |
| ---- | ------- | ---------------- | --------------------- |
| 0 | ROOT input path | `ProbeParallel` uses per-thread `EventStream` and ROOT branch reads under ROOT thread safety. `ROOTMT.md` records prior CPU floors for this path. | `EventStream::next` wall time grows with more reader threads while CPU does not. |
| 1 | Writer tree mutexes | Histogram-like objects use worker-local clones, but particle and explicit TTrees are shared behind mutexes. | Tree-enabled runs scale worse than tree-disabled runs; tree mutex timing is high. |

Items removed from suspect ranking because they are resolved or by design:

- Lambda vector copies → resolved (`const auto&` references in `rootAnalysis`).
- Lambda pair loop O(nP×nPi) → by design; that is the algorithm.
- Writer particle request copies → resolved (move-aware `fillParticleEvent`).
- Writer queue back-pressure → by design; bounded queue is intentional producer
  throttling.
- Monitor publish locks → by design; single-mutex publish is an accepted cost.
- Pythia thread forwarding → resolved (`configurePythia` now sets
  `Parallelism:numThreads`).

### Measurement Sequence

1. ~~Add the timer registry~~ — done; `Monitor::TimerRegistry` / `ScopeTimer`
   in `utils/Monitor/Timer.hh`. Dump called from `_Lambda_Reconstruction.cc`.
2. Print `probe.stats()` and `writer.stats()` at the end of reconstruction
   runs in addition to the timer dump.
3. ~~Run a small matrix~~ — done; `_ThreadBench.cc` sweeps thread permutations.
4. Compare with `Probe::ProbeIMT` for the same input and event count if memory
   permits.
5. Only after timing data, choose between Lambda-loop work, Probe read-path
   work, Writer queue/tree work, or monitor contention work.

### Remaining Timer Labels

Most labels are already instrumented via `MONITOR_SCOPE_TIMER`. Still missing:

- `Record.Writer.treeMutex`
- `Monitor.AsyncLogger.publishThreadStats`

Decision question: are producers blocked before enqueue, during enqueue, while
Writer workers drain, or during lifecycle writes?

## P1 - Writer Lifecycle/Concurrency Risks To Test

The current Writer design is much stronger than the old single-scribe queue,
but the watchdog and worker-pool paths need targeted stress tests.

Required tests:

- checkpoint while fill producers are blocked on a full queue;
- checkpoint after one worker records an exception;
- finalize after a worker exception with pending watch requests;
- fatal write while workers are filling shared trees;
- tree-enabled run vs tree-disabled run at multiple `writer_threads`;
- `save_checkpoints=true` through logger-driven WatchRequests.

Current tests cover concurrent producer drain, explicit checkpoint, declaration
validation, and exception propagation to `finish`, but not the full watchdog
matrix above.

## P2 - Test Infrastructure

All current test targets (`test_record_writer`, `test_probe_parallel`,
`test_reconstructCandidates`) were written against a prior codebase. They
compile but do not cover:

- the ProbeParallel CollectorThread multi-collector vs WorkerThread split;
- the new Writer worker pool, clone management, and watchdog paths;
- `Config::configure` end-to-end with the live TOML keys;
- `[probe.index]` parsing applied to `ParticleSpec` fields.

Required new or rebuilt tests:

- `test_probe_parallel`: CollectorThread multi-collector; WorkerThread dispatch;
  queue back-pressure with small capacity; index error paths.
- `test_writer`: watchdog stress matrix from P1 Writer section above.
- `test_config`: configure round-trip for Probe, Record, and Monitor keys.
- `test_rootAnalysis_smoke`: already covers the full pipeline; extend to
  compare unvalidated/validated counts against analytic bounds.
