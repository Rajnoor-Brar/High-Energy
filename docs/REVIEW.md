# Review - Current Backlog

Updated: 2026-05-21.

This review reflects the current `modules/` and `utils/` state after the
Probe/WriterMT work. Items here are backlog and design cleanup, not a claim
that the current code is unusable.

Major changes since the prior review snapshot:

- `[events].nThreads` is gone; per-stage thread keys are live.
- `Record::Writer` is no longer a single-scribe queue. It has a fill-worker
  pool, per-worker ROOT clones for histograms/graphs/profiles, mutexed shared
  trees, and a watchdog lifecycle queue.
- Monitor save flags are wired.
- `Monitor::TimerRegistry` / `ScopeTimer` in `utils/Monitor/Timer.hh` replace
  the old `BlockTimer`. Most hot-path labels are already instrumented.
- `Probe::ProbeIMT` is in tree as a drop-in runtime but not the default driver
  choice.
- `[monitor.intervals].check_interval` removed; stall detection is purely
  time-based via `program_stall_threshold`.

Companion docs:

- [MAP.md](MAP.md): current file map and runtime ownership.
- [DataFlow.md](DataFlow.md): current TOML/config/runtime flow.
- [Issues.md](Issues.md): active correctness and performance mismatches.
- [Architecture.md](Architecture.md): current component and concurrency model.
- [WriterMT.md](WriterMT.md), [ROOTMT.md](ROOTMT.md): detailed implementation
  history and measurement notes.

## Item Map

- 1. Probe backlog
- 2. Writer backlog
- 3. Monitor and timer backlog
- 4. Config/data-flow cleanup
- 5. Lower-priority retained work
- 6. Non-issues for now

## 1. Probe Backlog

### 1.1 Document `analysis_threads` contract

`analysis_threads` sets the number of collector threads in CollectorThread
mode. In WorkerThread mode, the field is ignored and callbacks run on reader
worker threads directly. The old mental model "CollectorThread means serial
Lambda callback" is stale. Document and test the current contract:

- reader workers build events and push into a shared queue;
- `analysis_threads` collectors pop opportunistically and can run concurrently;
- callbacks must be thread-safe regardless of mode;
- the callback receives the collector index, not the original reader index;
- in WorkerThread mode `analysis_threads` is silently ignored.

## 2. Writer Backlog

### 2.1 Per-worker and per-record stats

`writer.stats()` reports total produced/consumed/backlog. It should expose:

- configured worker count and active worker count;
- per-request-kind counts;
- current and max fill queue wait;
- tree mutex wait time;
- checkpoint/final merge/write timings.

This can be lightweight text first; structured stats can follow.

### 2.2 Watchdog barrier stress tests

Checkpoint/final/fatal lifecycles route through `WatchRequest` barriers. Add
stress tests for:

- checkpoint while producers are blocked on a full queue;
- worker exception followed by checkpoint/final;
- fatal write while worker threads are in tree mutex sections;
- multiple queued watch barriers after the first failure.

## 3. Monitor And Timer Backlog

### 3.1 Remaining timer labels

`Monitor::TimerRegistry` / `MONITOR_SCOPE_TIMER` are implemented and most
hot-path labels are instrumented. Two labels remain:

- `Record.Writer.treeMutex` — tree mutex wait in fill workers.
- `Monitor.AsyncLogger.publishThreadStats` — per-thread stats publish cost.

Wall/CPU ratios are needed before more architecture changes.

### 3.2 Reduce per-event monitor locking

`AsyncLogger::publish` still locks a single mutex when a publish happens.
`publishThreadStats` is gated by `save_log_threads`, but when enabled it also
locks the same mutex. Use per-thread buffers or atomic snapshots if this shows
up in timing.

## 4. Config And Data-Flow Cleanup

### 4.1 Remove inline docs from header files

Module-level doc blocks in `.hh` files duplicate or drift from the companion
`.md` docs. Only the `why` — hidden constraints, workarounds, non-obvious
invariants — belongs in the code. Remove multi-paragraph doc blocks from
headers and keep the authoritative descriptions in the companion docs.

Partially done: `Lambda.hh` and `Config/Reader.hh` cleaned. Remaining headers
to audit: `Probe/Parallel.hh`, `Probe/ConfigAid.hh`, `Record/Writer.hh`,
`Monitor/Logger.hh`, `Config/Configure.hh`.

### 4.2 Split parse side effects

The Probe facade still calls `configuration`, which creates directories before
Probe has resolved a metadata-derived event count. The facade then re-reads
paths and creates directories again. Split "read values" from "create output
directories" so the final event count is known before filesystem side effects.

## 5. Lower-Priority Retained Work

- `Config::LimitAid::resolveLimitsPath` silently expands bare names into
  `configs/<name>.toml`; log or expose the resolved path.
- `AsyncLogger::runLoop` carries several optional action snapshots across a
  lock boundary; a small action queue may be simpler to extend.
- Consider structured JSON/CSV stats for Probe/Writer/Monitor once the timing
  registry exists.
- Audit `Paint` against current ROOT style needs before expanding it.

## 6. Non-Issues For Now

- Replacing ROOT TFile output with RNTuple.
- Disabling ROOT thread safety.
- C++20/23 migration.
- Project-wide naming style sweep.
- Precompiled headers.
- Broad file reorganization without a specific bottleneck.
- `ProbeIMT` TOML-selectable runtime: ProbeIMT is documented as a measured
  alternate path (indexed streams only, high memory peak, event order not
  preserved). No TOML selection key planned.
- Batching explicit tree rows per event: trees are mutex-protected shared
  objects; per-particle requests are simpler and acceptable until tree writes
  appear in throughput profiling.
- Per-worker particle TTrees: histograms/graphs/profiles already use per-worker
  clones; shared mutexed trees are acceptable until timing shows otherwise.
- Reworking `reconstructCandidates` hot path: the O(nP×nPi) loop, pair
  materialization, and disabled theta cut are intentional design points; no
  changes planned until profiling shows them as a bottleneck.
