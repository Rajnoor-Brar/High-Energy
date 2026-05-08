# Probe Inspection

This document merges the earlier `Probe_Inspection.md` and
`Probe_Inspection2.md` notes against the current code state.

Outdated sections were removed:

- `Probe::ProbeParallel` is no longer just a public-field wrapper.
- `Probe::runParallel` is no longer the main implementation path; it is now a
  compatibility shim.
- default Probe callback dispatch is no longer worker-thread callback dispatch;
  it is `Probe::CallbackMode::CollectorThread`.
- pre-run event planning and per-worker entry bounds now exist.
- `Probe::readAllParallel` is no longer present.
- `Probe::CallbackMode::MainThreadOrdered` never landed under that name; the
  implemented mode is `Probe::CallbackMode::CollectorThread`.

The remaining analysis focuses on what is true now, what problems remain, and
what should be measured next.

## Current State

### `Probe::ProbeParallel`

`Probe::ProbeParallel` now owns the main Probe execution model. The class lives
in `utils/Probe/Parallel.hh` and is included through `utils/Probe.hh`.

Public configuration and query API:

```cpp
void configureProbe(std::string inputFile,
                    std::vector<ParticleSpec> particleSpecs,
                    std::size_t threadCount,
                    std::size_t requestedEvents,
                    bool userRequestedEvents);

void setCallbackMode(CallbackMode mode);
void setQueueCapacity(std::size_t capacity);

const std::string& inputFile() const;
std::size_t threadCount() const;
std::size_t eventCount() const;
StreamType streamType() const;
std::string stats() const;
```

Private state is now internal:

- `inputFile_`
- `particleSpecs_`
- `indexSpecs_`
- `streamType_`
- `callbackMode_`
- `threadCount_`
- `eventCount_`
- `eventRange_`
- `eventPartitions_`
- `entryBoundsByWorker_`
- collector queue state and progress counters

This means callers no longer mutate `inputFile`, `collections`, `nThreads`, or
`nEvents` directly. `Config::configure(...)` calls
`Probe::ProbeParallel::configureProbe(...)` once, then reads
`probe.eventCount()` and `probe.threadCount()` to configure logging and output
paths.

### Event-count resolution

`Probe::ProbeParallel::configureProbe(...)` resolves event count in this order:

1. explicit TOML/requested event count;
2. ROOT metadata through `Probe::resolveEventCount(inputFile_)`;
3. fallback scan:
   - indexed event streams: scan index branches through
     `Probe::BranchControl::scanIndexBranch(...)`;
   - vector streams: use the first vector tree's `TTree::GetEntries()`.

If event count is zero after resolution, the object is configured but `run()`
returns without starting workers.

### Stream type

`Probe::ProbeParallel::determineStreamType()` chooses:

- `Probe::StreamType::Events` when all particle specs have index branches;
- `Probe::StreamType::Vectors` when no particle specs have index branches;
- throw if indexed and vector specs are mixed.

Vector stream support is currently only compatible with
`Probe::CallbackMode::WorkerThread`. `CollectorThread` vector streams throw
clearly.

### Index assumptions

`Probe::ProbeParallel::buildIndexSpecs()` currently hard-codes indexed flat
input as:

```cpp
IndexOrdering::Ascending
dense = true
grouped = true
```

There is no TOML-level index metadata yet. The implementation assumes the
current Lambda indexed files are ascending, dense, and grouped. If a file is not
ascending, `prepareEntryBounds()` throws while scanning index branches.

Important detail: nondecreasing index values imply grouped event IDs for a
single sorted branch. The code catches decreasing values. It does not yet model
descending, unordered, sparse-but-sorted, or grouped-but-not-globally-sorted
inputs.

### Event partitions

For vector streams, event partitions are dense row ranges:

```text
0 .. eventCount - 1
```

For indexed event streams:

- if fallback scanning produced actual keys, partitions are based on those keys;
- otherwise the code probes the first key and assumes a dense range:

```text
firstKey .. firstKey + eventCount - 1
```

`Probe::BranchControl::partitionEvents(...)` partitions key vectors by count, not
by estimated event cost.

### Entry bounds

`Probe::ProbeParallel::prepareEntryBounds()` is the major change from the older
docs. It scans each indexed particle tree's index branch once before workers are
started and records physical ROOT entry bounds per worker and per particle:

```cpp
std::vector<std::vector<Bounds>> entryBoundsByWorker_;
```

Workers pass those bounds into `Probe::EventStream`, which passes each particle's
bound into `Probe::FlatReader`.

This fixes the old worst case where every worker opened a flat tree and walked
from entry zero to its first event range. Workers can now start near the physical
entry range that belongs to their event partition.

Limitations:

- bounds are found through a linear scan of index branches;
- the scan is done for each indexed particle tree during configuration;
- if event count fallback also needs `scanFlatEventKeys()`, index branches may
  be scanned once to collect keys and again to prepare entry bounds;
- bounds planning assumes ascending grouped data;
- bounds are event-range based, not work-cost based.

### `Probe::EventStream`

Each worker still owns its own `Probe::EventStream`.

One worker means:

- one `Probe::EventStream`;
- one worker-local `TFile`;
- one set of `Probe::FlatReader` or `Probe::VecReader` objects;
- one reusable current `Probe::Event`.

`Probe::EventStream` now supports:

```cpp
const Event& event() const;
Event takeEvent();
```

`event()` supports worker-thread callback mode. `takeEvent()` supports collector
mode by moving the current event into the bounded queue.

### Callback modes

Default mode:

```cpp
Probe::CallbackMode::CollectorThread
```

Collector mode flow:

```text
worker threads
  -> EventStream::next()
  -> EventStream::takeEvent()
  -> push QueuedEvent into bounded queue

collector thread
  -> pop QueuedEvent
  -> callback(event, workerIndex)
```

This means `_Lambda_Reconstruction.cc` no longer calls `Lambda::rootAnalysis`
concurrently by default. Workers load events in parallel; analysis and output
run serially through the collector callback.

Compatibility mode:

```cpp
Probe::CallbackMode::WorkerThread
```

Worker-thread mode keeps the old behavior:

```cpp
while (stream.next())
    callback(stream.event(), static_cast<int>(t));
```

The free function `Probe::runParallel(...)` now constructs a `ProbeParallel`,
sets `CallbackMode::WorkerThread`, configures it, and calls `run(...)`. It is a
compatibility shim for older call sites and tests.

### Collector queue

Collector mode uses:

- `std::deque<Probe::QueuedEvent> queue_`
- `std::mutex queueMutex_`
- `std::condition_variable queueNotEmpty_`
- `std::condition_variable queueNotFull_`
- `std::atomic<bool> stopRequested_`
- `workersFinished_`
- `produced_`
- `consumed_`
- `progress_`

Default queue capacity is `10 * threadCount`, with a minimum of `threadCount`.
`setQueueCapacity(...)` can override it.

`stats()` reports stream type, callback mode, thread count, active worker count,
event count, queue capacity, produced/consumed event counts, and per-worker
progress.

## Current Lambda Interaction

`_Lambda_Reconstruction.cc` still constructs one shared `Lambda::RootArray`:

```cpp
Lambda::RootArray histogramSets;
Lambda::configure(physParams, histogramSets, writer, configPath);
Lambda::AnalysisContext ctx{histogramSets, physParams, watch, logger, writer};
probe.run([&](const Probe::Event& ev, int threadId) {
    Lambda::rootAnalysis(ev, threadId, ctx);
});
```

`Lambda::rootAnalysis(...)` still:

1. increments `Config::Watch::iEvent`;
2. publishes thread stats;
3. copies protons and pions out of `Probe::Event`;
4. locks `Record::Writer::recordingScope()`;
5. calls `Lambda::reconstructCandidates(...)`;
6. calls `Lambda::fillCandidates(...)`;
7. records/publishes progress.

Because the default Probe mode is now `CollectorThread`, the shared
`Lambda::RootArray` is normally touched by only the collector callback thread in
reconstruction. The `recordingScope()` lock remains active, but it no longer
protects against multiple Probe workers in the default path.

In `WorkerThread` mode, the current `recordingScope()` covers both candidate
reconstruction and filling. That serializes analysis work and output fills. It is
correcter than unlocked shared ROOT mutation, but it prevents worker-thread
analysis scaling.

## Problems

### 1. Probe workers no longer parallelize `Lambda::rootAnalysis`

Collector mode intentionally moved callback execution to one collector thread.
That fixed the old bug where multiple workers could call shared analysis/output
state concurrently, and tests now confirm the callback count equals logical event
count.

The cost is that worker count only parallelizes event loading. If
`Lambda::rootAnalysis`, candidate reconstruction, histogram filling, logger
publication, or Writer locking dominate wall-clock, increasing Probe worker
count cannot speed up the run much.

This is now the most important explanation for "CPU scales with thread count but
work done does not": workers can spend CPU loading events while the collector is
the throughput gate.

### 2. `Lambda::rootAnalysis` still locks too much for `WorkerThread`

In current `Lambda::rootAnalysis`, the lock scope is:

```cpp
auto lock = ctx.writer.recordingScope();
fillCandidates(ctx.histograms,
               reconstructCandidates(protonList, pionList, ctx.parameters));
```

This means `WorkerThread` mode serializes both pure candidate reconstruction and
ROOT output mutation under one mutex.

If `WorkerThread` is used as a benchmark, it is not a benchmark of parallel
analysis. It is a benchmark of parallel reading plus serialized analysis/output.

The better long-term fix is the Writer overhaul in `docs/Chat/WriterPlan.md`:
callbacks enqueue Writer requests and no callback thread directly mutates ROOT
output objects.

### 3. Shared ROOT output still exists

The default collector mode hides concurrent mutation by making callbacks serial,
but the output model itself is still shared external state:

- `Lambda::RootArray`
- `Record::RootObjects::candidateCount`
- `TH1D*` histograms
- optional `TTree*` candidate trees

That means `WorkerThread` mode still requires serialization, and any future code
that bypasses collector mode can reintroduce ROOT output races.

The ownership issue belongs to `Record::Writer`, not Probe. The planned Writer
scribe architecture is the right place to solve it.

### 4. Candidate materialization can dominate

`Lambda::reconstructCandidates(...)` constructs vectors of candidates:

- `unvalidated`
- `validated`
- `selected`

For high-multiplicity events, unvalidated candidates scale roughly as:

```text
nProtons(event) * nPions(event)
```

The production input discussed earlier had event shapes far heavier than the
small smoke fixtures. A simple 100k loop or a small fixed fixture does not
represent the same workload.

If candidate reconstruction/fill dominates, CollectorThread makes the run
serial at exactly the expensive stage.

### 5. Static partitions are not work-balanced

Probe partitions by event key range, not expected work.

Even after entry bounds, a worker's load is not proportional to event count if
event multiplicity varies. In Lambda reconstruction, the real per-event cost is
closer to:

```text
nProtons(event) * nPions(event)
```

Static partitions can leave some workers with much more event loading or queue
production than others. Collector mode softens the effect by decoupling workers
from callback execution, but it does not make partitioning work-aware.

### 6. Dense-key assumptions are still baked in

When event count comes from TOML or ROOT metadata, event partitions assume:

```text
firstKey .. firstKey + eventCount - 1
```

`Probe::EventStream::nextFlat()` also iterates dense keys from `denseLo_` to
`denseHi_`. If an indexed file has missing event IDs, Probe can produce empty
events for gaps.

The current `IndexSpec` has `dense` and `grouped` fields, but there is not yet a
config path for the user to describe sparse, descending, unordered, or
grouped-but-not-sorted index branches.

### 7. Entry-bound preparation is linear and index-only, but not free

The old duplicated worker positioning was removed. The replacement is one
configuration-time linear scan per index branch to compute entry bounds.

That is usually better than each worker walking from entry zero, but it still
means:

- very large files pay pre-run scanning cost;
- multiple particle trees each need a scan;
- missing metadata can cause an additional full key scan;
- no `TTreeIndex` is built or persisted for reuse.

### 8. ROOT internal locking and I/O contention may still cap read scaling

`Probe::BranchControl::enableRootThreadSafety()` calls `ROOT::EnableThreadSafety()`.
Independent worker-local `TFile` objects are the right broad shape, but ROOT can
still take global or shared locks around dictionaries, metadata, directories,
class loading, cache internals, and some branch/file operations.

Removing `ROOT::EnableThreadSafety()` is not a valid test; the crash observed
through Cling/TClass/TBranch paths is exactly the kind of unsafe behavior it is
there to prevent.

The correct test is profiling time in:

- `pthread_mutex_lock`;
- ROOT internals;
- `TTree::GetEntry`;
- `TBranch::GetEntry`;
- decompression/read calls;
- callback execution.

### 9. Monitor publication remains hot-path work

`Lambda::rootAnalysis` still calls:

- `Monitor::AsyncLogger::publishThreadStats(...)` before analysis;
- `Config::Watch::recordEvent(...)`;
- `Monitor::AsyncLogger::publish(...)`;
- `Monitor::AsyncLogger::publishThreadStats(...)` after analysis.

Collector mode makes this serial in the default Probe path, but it is still
per-event overhead. In `WorkerThread` mode, Monitor mutexes and thread-stat file
updates can become shared hot spots.

The monitor path should be sampled or batched if it shows up in measurement.

### 10. `Probe::Event` allocation churn remains

Every `EventStream::next()` clears maps and vectors inside `Probe::Event`.
Collector mode then moves the event into `QueuedEvent`.

For high-multiplicity events, repeated allocation in:

- `Event::particles`;
- `std::vector<Lorentz>`;
- aux-column vectors;
- `QueuedEvent`;

can matter. This is secondary to callback/output bottlenecks, but it is still a
possible optimization target.

## Bottleneck Ranking For Current Code

### Highest suspicion: serial collector callback

Default `CollectorThread` mode means only one callback runs at a time. If
`Lambda::rootAnalysis` is the major cost, Probe worker count cannot improve
end-to-end wall-clock beyond hiding input-read latency.

### High suspicion: candidate reconstruction/fill volume

Large production events can create huge numbers of proton-pion candidate pairs.
This can dominate even if Probe event loading is parallel.

### High suspicion: old shared-output model

The current Writer/RootArray model still forces serialization if callbacks are
run on workers. It is correct to serialize ROOT output for now, but it prevents
parallel analysis in `WorkerThread` mode.

### Medium suspicion: ROOT read contention

Worker-local files are correct, but ROOT internals and disk/decompression can
still limit scaling. This needs profiler evidence.

### Medium suspicion: static partition imbalance

Entry bounds reduce startup waste, but event-key partitions can still be
unbalanced by row count or candidate-pair count.

### Lower suspicion: atomic event counters

`Config::Watch::iEvent` and related atomics can bounce cache lines, but this is
unlikely to dominate compared with serial callback execution, candidate work,
ROOT I/O, and output mutation.

## Measurement Plan

### 1. Compare callback modes

Run the same fixed event subset with:

- `Probe::CallbackMode::CollectorThread`
- `Probe::CallbackMode::WorkerThread`

For WorkerThread, also test a no-output or no-analysis callback, because current
`Lambda::rootAnalysis` holds `recordingScope()` across reconstruction and fill.

Record:

- wall-clock;
- callback count;
- `probe.stats()`;
- output correctness if real Lambda output is enabled.

### 2. Split read time from callback time

Instrument in `Probe::ProbeParallel`:

- worker `EventStream::next()` time;
- worker queue wait time;
- collector queue wait time;
- collector callback time;
- produced/consumed counts;
- max queue depth.

If worker read time shrinks with threads but callback time dominates, Probe is
not the bottleneck anymore; Lambda/Writer is.

### 3. Profile ROOT read scaling

Use a system profiler on `nThreads = 1, 2, 4, 8`.

Look for time in:

- `pthread_mutex_lock`;
- `ROOT::*`;
- `TTree::GetEntry`;
- `TBranch::GetEntry`;
- decompression;
- disk I/O.

This is the safe way to evaluate ROOT global locking. Do not disable
`ROOT::EnableThreadSafety()` for this test.

### 4. Validate entry-bound planning cost

Time:

- `configureProbe(...)`;
- `prepareEntryBounds()`;
- worker startup to first produced event.

Do this on:

- fixture files with `TTreeIndex`;
- production files without `TTreeIndex`;
- files with metadata event counts;
- files requiring fallback key scanning.

### 5. Check output correctness across modes

For a small deterministic input:

- run CollectorThread;
- run WorkerThread if output locking is active;
- compare histogram entries/integrals;
- verify candidate count histograms;
- verify callback count equals logical event count.

## Solutions And Routes

### Route A: keep CollectorThread as the correctness default

Keep:

```cpp
CallbackMode::CollectorThread
```

as the default for reconstruction while `Record::Writer` still exposes shared
ROOT output objects. This avoids concurrent ROOT output mutation and keeps
callback count correct.

Do not expect this mode to speed up CPU-heavy analysis. It parallelizes event
loading, not callback execution.

### Route B: implement the Writer overhaul

The main remaining blocker for parallel analysis is not Probe. It is shared
output ownership.

Implement `docs/Chat/WriterPlan.md`:

- Writer owns ROOT output objects;
- callbacks submit fill requests;
- a Writer scribe thread mutates ROOT;
- callback threads do not directly call `TH1::Fill` or `TTree::Fill`.

After that, `WorkerThread` mode can be revisited because callbacks can run
analysis in parallel without mutating shared ROOT output directly.

### Route C: narrow `Lambda::rootAnalysis` lock as an interim benchmark

If `WorkerThread` mode is used before the Writer overhaul, move candidate
reconstruction outside `recordingScope()`:

```cpp
const Candidates candidates =
    reconstructCandidates(protonList, pionList, ctx.parameters);

{
    auto lock = ctx.writer.recordingScope();
    fillCandidates(ctx.histograms, candidates);
}
```

This is not the final architecture, but it separates CPU candidate generation
from ROOT output serialization for measurement.

Risk: `Candidates` can be very large, so this may increase peak memory pressure
when many worker callbacks reconstruct simultaneously.

### Route D: stream candidate output instead of materializing everything

`Lambda::reconstructCandidates(...)` currently materializes candidate vectors and
then `fillCandidates(...)` walks them.

For high-multiplicity production events, consider a streaming candidate visitor:

```cpp
forEachCandidate(protons, pions, parameters, visitor);
```

The visitor can count, fill, or enqueue output without storing every
unvalidated candidate. This could reduce memory traffic and allocation churn.

This route belongs mostly to Lambda and Writer, not Probe.

### Route E: make index metadata configurable

Add config support for:

- sorted/ordering: ascending, descending, unordered;
- dense versus sparse;
- grouped/contiguous event IDs;
- optional physical entry bounds or index metadata if known.

Use that to decide whether Probe can:

- use dense range planning;
- compute bounds by linear scan;
- use binary/jump search;
- throw for unsupported unordered/interspersed data.

Current v1 behavior should continue to throw on descending or unordered event
collector input rather than silently doing inefficient or incorrect work.

### Route F: dynamic scheduling

Static event partitions can be replaced or augmented with dynamic chunks:

```text
shared queue of event-id chunks
workers claim next chunk
workers produce QueuedEvent
collector consumes callbacks
```

This helps when event loading or event sizes are uneven. It does not fix serial
collector callback cost.

For Lambda, dynamic scheduling is most useful after Writer allows parallel
callback execution or after Probe read time is proven to dominate.

### Route G: optimize `Probe::Event` reuse

If allocation shows up in profiles:

- reserve particle vectors from recent event sizes;
- reuse aux-column vectors;
- avoid repeated unordered-map growth;
- consider label-indexed vectors instead of string-keyed maps on the hot path.

This is a secondary optimization after callback/output bottlenecks are resolved.

## Non-Solutions

### Disabling ROOT thread safety

This is unsafe. The observed crash through Cling/TClass/TBranch paths is enough
evidence that disabling thread safety is not a valid diagnostic for the normal
multi-threaded path.

Use profiling instead.

### Increasing thread count alone

More workers can increase CPU usage while not increasing completed callbacks.
With collector mode, the collector callback can be the gate. With WorkerThread
mode, `recordingScope()` can serialize analysis/output.

### Treating the smoke fixture as representative

The fixture is useful for correctness and regression tests. It does not represent
large production row counts, missing `TTreeIndex`, high event multiplicity, or
large candidate-pair volumes.

### Moving callbacks to workers before fixing output ownership

Worker callbacks can only scale safely after shared ROOT output mutation is
removed or sharded. Otherwise the code either races on ROOT output or serializes
through a large lock.

## Current Bottom Line

The old Probe architecture problem has mostly been addressed:

- `ProbeParallel` owns configuration and execution;
- event count and partitions are resolved during configuration;
- per-worker entry bounds are precomputed;
- default dispatch is CollectorThread;
- `runParallel` is only compatibility;
- callback count is tested to be exactly logical event count.

The remaining speed problem is probably no longer "Probe workers all call the
callback `nEvents` times" or "every worker starts at row zero." Those were
addressed.

The likely current limits are:

1. default collector-mode serial callback execution;
2. Lambda candidate reconstruction/fill volume;
3. old shared ROOT output ownership forcing serialization in WorkerThread mode;
4. ROOT read/decompression contention;
5. static event-key partitioning;
6. Monitor hot-path overhead.

The next structural fix should be the Writer overhaul, then re-evaluate
`WorkerThread` mode with callbacks that do CPU analysis in parallel and enqueue
output requests instead of mutating ROOT objects directly.
