# Issues - Active Investigation

Updated: 2026-05-15.

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

Stage-level timing does not yet exist. Without it, per-stage thread changes are
uninformed guesses.

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

`BlockTimer` is no longer an active hot-path suspect because the Lambda call
sites are commented out. The old class still exists and should be replaced
before anyone re-enables it.

### Measurement Sequence

1. Add the timer registry proposed in [REVIEW.md](REVIEW.md), or a smaller
   temporary equivalent.
2. Print `probe.stats()` and `writer.stats()` at the end of reconstruction
   runs.
3. Run a small matrix with fixed event count:

```text
probe_threads:    1, 2, 4
analysis_threads: 1, 2, 4
writer_threads:   1, 2, 4, 8
```

4. Compare with `Probe::ProbeIMT` for the same input and event count if memory
   permits.
5. Only after timing data, choose between Lambda-loop work, Probe read-path
   work, Writer queue/tree work, or monitor contention work.

### Minimum Timer Labels

- `ProbeParallel.EventStream.next`
- `ProbeParallel.queue.push_wait`
- `ProbeParallel.queue.pop_wait`
- `ProbeParallel.collector.callback`
- `ProbeIMT.allocate`
- `ProbeIMT.read`
- `ProbeIMT.flush`
- `Lambda.rootAnalysis`
- `Lambda.reconstructCandidates`
- `Record.Writer.pushFill`
- `Record.Writer.applyParticleRequest`
- `Record.Writer.treeMutex`
- `Record.Writer.mergeAllClones`
- `Record.Writer.writeCheckpointFile`
- `Record.Writer.writeAllToCurrentFile`
- `Monitor.AsyncLogger.publish`
- `Monitor.AsyncLogger.publishThreadStats`

Decision question: are producers blocked before enqueue, during enqueue, while
Writer workers drain, or during lifecycle writes?

## P1 - Config/Data-Flow Mismatches

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

Risk to check first: `quiesceWorkers()` waits for all configured Writer workers
to arrive. A worker that exited early after storing `writerException_` will not
arrive, so a later checkpoint may block unless the watchdog detects the stored
exception before quiescing.

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

## Done Since The Prior Issues Snapshot

Closed or changed from the previous open-issue list:

- `[events].nThreads` removed in favor of per-stage thread keys.
- Writer single-scribe design replaced by fill workers, per-worker clones, and
  watchdog lifecycle requests.
- Monitor save flags are wired.
- `rootAnalysis` no longer constructs an active `BlockTimer`; the line is
  commented out.
- Probe CollectorThread mode is no longer necessarily serial; it can use
  multiple analysis collectors.
- ProbeIMT is implemented and covered by focused tests.
- `utils/Record.hh` updated: no longer describes Writer as owning "the scribe
  thread"; header comment now reflects fill workers plus watchdog.
- `utils/Probe.hh` cleaned up: includes `Probe/Parallel.hh` directly; stale
  `ProbeParallel.hh` subfile reference is gone.
- `runParallel` compatibility shim removed from `Probe`; callers now use
  `ProbeParallel::run` directly.
- `[probe.index]` TOML section parsed and applied to `ParticleSpec` fields
  (`indexSorted`, `indexAscending`, `indexMonotonic`).
- `Monitor::configureMonitor` repositioned after event count resolution so bar
  interval uses the correct event count.
- `heartbeat_interval` is milliseconds in TOML and microseconds internally;
  this is intentional — user-facing ms, internal µs.
- `[events].pythia` removed from fixture TOML; `Config::Register::checkpointInterval`
  removed (Monitor reads checkpoint interval directly).
- `Config::configurePythia` now covers all Pythia initialization: `beam_energy`,
  `seed`, and `cmnd_file` are read from `[pythia]` TOML and applied inside the
  facade; no ad-hoc driver setup required.
- Branch name drift (`Index` vs `event_index`) documented in
  `configs/Lambda_Reconstruction.toml` with an inline comment; the correct
  branch name is whatever the source file uses — no rename required.
- `[probe].callback_mode` and `[probe].queue_capacity` parsed and applied.
- `[record].writer_queue_capacity` parsed and applied.
- `Probe::progress_` counters made atomic; increment moved outside queue mutex.
- `prepareEntryBounds` error now includes row index, tree name, branch name,
  previous value, and current value.
- `fillParticleEvent` move-aware overload added; `Lambda::fillCandidates` now
  moves candidate vectors.
- `rootAnalysis` proton/pion vectors accessed via `const auto&` (no copy).
- `Meta::fillDerived` moved into `Writer::finish()` for accurate final event
  counts.
- `test_record_writer.cc` worker/watchdog labels corrected.
- `Lambda.hh` stale `WriterMT.md Phase` comments removed; `runParallel`
  references updated to `ProbeParallel::run`.
- `test_rootAnalysis_smoke.cc` header comment updated to reference
  `ProbeParallel::run`.
