# Probe Inspection

This note records the inspection of the Probe reconstruction path around
`Probe::ProbeParallel`, `Probe::runParallel`, and `Probe::EventStream`.
It is analysis only. It does not choose an implementation date.

## Direct Answers

### How parallel is `Probe::ProbeParallel`?

`Probe::ProbeParallel` is not itself a parallel executor. It is currently a
small state holder with:

- `Probe::ProbeParallel::inputFile`
- `Probe::ProbeParallel::collections`
- `Probe::ProbeParallel::nThreads`
- `Probe::ProbeParallel::nEvents`
- `Probe::ProbeParallel::resolveEvents()`
- `Probe::ProbeParallel::run()`

`Probe::ProbeParallel::run()` forwards directly to `Probe::runParallel(...)`.
All actual worker creation, partitioning, stream construction, and callback
dispatch happens in `Probe::runParallel`.

### How parallel is `Probe::runParallel`?

`Probe::runParallel` is genuinely multi-threaded. It:

1. Enables ROOT thread safety through
   `Probe::BranchControl::enableRootThreadSafety()`.
2. Detects flat versus vector collection mode.
3. Builds static partitions.
4. Spawns one `std::thread` per partition.
5. Constructs a separate `Probe::EventStream` inside each worker.
6. Calls the callback from that worker thread:

```cpp
while (stream.next()) callback(stream.event(), static_cast<int>(t));
```

So the worker threads are not waiting for a main thread to invoke one serial
callback. They call the callback concurrently.

The callback object itself is shared by reference into all worker lambdas. That
means a stateless callback is fine, but a callback that closes over shared state
must make that state thread-safe. In `_Lambda_Reconstruction.cc`, the callback
closes over one shared `Lambda::AnalysisContext`.

### How parallel is `Probe::EventStream`?

`Probe::EventStream` is not an internal parallel stream. Each worker owns one
independent `Probe::EventStream`, and each stream opens its own `TFile`.

That means the parallel model is:

- one worker thread;
- one worker-local `Probe::EventStream`;
- one worker-local `TFile`;
- one worker-local current `Probe::Event`;
- concurrent callback calls into shared callback state.

The event loading is disjoint by event-key partition after each stream has
positioned itself. The positioning step is where the current flat/no-index path
can waste work.

## Inspection Evidence

### Current reconstruction path

`_Lambda_Reconstruction.cc` does this:

- constructs `Probe::ProbeParallel`;
- passes it into `Config::configure(...)`;
- builds histograms through `Lambda::configure(...)`;
- starts `Monitor::AsyncLogger`;
- calls `Probe::ProbeParallel::run(...)`;
- each event callback calls `Lambda::rootAnalysis(...)`.

The runtime path is therefore:

```text
Config::configure(...)
  -> Probe::ProbeParallel::resolveEvents()
  -> Record::configureWriter(...)
  -> Monitor::configureMonitor(...)

Probe::ProbeParallel::run(...)
  -> Probe::runParallel(...)
  -> Probe::EventStream::EventStream(...)
  -> Probe::EventStream::next()
  -> Lambda::rootAnalysis(...)
```

### Production input differs from the smoke fixture

The large input inspected at
`output/Lambda_Data/_08/Lambda_Recons_7000GeV_10M.root` has:

- `Protons`: 304,480,886 rows, no `TTreeIndex`
- `Pions`: 2,746,275,925 rows, no `TTreeIndex`

The small fixture `tests/fixtures/lambda_fixture.root` has:

- `Protons`: indexed
- `Pions`: indexed

This matters because `Probe::FlatReader` has a fast path when
`TTree::GetTreeIndex()` exists and a linear positioning path when it does not.
The smoke fixture tests the better path; the production file uses the worse
path.

### Read-only timing observations

These timings were measured against the current workspace on this machine. They
are diagnostic numbers, not benchmark guarantees.

- `Probe::runParallel` with a no-op callback, 100k events:
  - ~3.94 seconds at 2 threads
  - ~3.71 seconds at 8 threads

- `Probe::runParallel` plus hot-path `Monitor::AsyncLogger` calls, but without
  logger worker/file output, 100k events:
  - ~13.37 seconds at 2 threads
  - ~14.69 seconds at 8 threads

- `Probe::runParallel` plus real logger worker/file output, 10k events:
  - ~4.07 seconds at 2 threads
  - ~4.08 seconds at 8 threads

- `Probe::runParallel` plus `Lambda::reconstructCandidates`, 10k events:
  - ~9.09 seconds at 2 threads
  - ~3.46 seconds at 8 threads
  - about 151,793,278 unvalidated proton-pion pairs in those 10k events

- `Probe::runParallel` plus `Lambda::reconstructCandidates` plus
  `Lambda::fillCandidates`, 1k events:
  - ~2.03 seconds at 2 threads
  - ~1.26 seconds at 8 threads
  - about 14,789,561 unvalidated proton-pion pairs in those 1k events

The pure Probe no-op timing does not explain an 11-17 minute 100k-event run.
The more likely explanation is combined cost: production event size, candidate
construction, histogram filling, monitor mutex/file activity, static work
imbalance, and duplicated no-index positioning.

## Problems

### `Probe::ProbeParallel` does not own the execution model

`Probe::ProbeParallel` sounds like the high-level Probe engine, but it only
stores configuration and forwards to `Probe::runParallel`.

This causes the same setup knowledge to be split across:

- `Config::configure(...)`
- `Probe::ProbeParallel::resolveEvents()`
- `Probe::runParallel(...)`
- `Probe::EventStream::EventStream(...)`
- `Probe::FlatReader::FlatReader(...)`

The result is that prestream setup is repeated or deferred until worker startup,
when it is harder to inspect and harder to optimize.

### `Probe::runParallel` mixes too many responsibilities

`Probe::runParallel` currently handles:

- ROOT thread-safety setup;
- flat/vector mode detection;
- event count interpretation;
- first-key probing through `Probe::BranchControl::probeFirstKey(...)`;
- fallback index-key scanning through
  `Probe::BranchControl::scanIndexBranch(...)`;
- static partition construction;
- worker creation;
- per-worker `Probe::EventStream` construction;
- callback dispatch;
- exception collection.

That is too much policy in one free function. It also means
`Probe::ProbeParallel` cannot inspect or cache the execution plan after
configuration.

### No-index flat trees can duplicate positioning work

`Probe::FlatReader::FlatReader(...)` binds index and kinematic branches, then:

```cpp
if (auto* idx = dynamic_cast<TTreeIndex*>(tree_->GetTreeIndex())) {
    Long64_t entry = tree_->GetEntryNumberWithIndex(minKey_, 0);
    ...
}

if (totalEntries_ > 0) tree_->GetEntry(cursor_);

while (cursor_ < totalEntries_ && idxValue() < minKey_) {
    ++cursor_;
    if (cursor_ < totalEntries_) tree_->GetEntry(cursor_);
}
```

When no `TTreeIndex` exists, each worker starts from entry 0 and walks forward
to its partition start. Because kinematic branches are already active, this can
read and decompress more data than an index-only seek requires.

For 8 static chunks, later workers can spend CPU and I/O just getting to their
first useful event. This is not workers waiting on a callback; it is duplicated
stream positioning.

### Static partitioning can imbalance real work

`Probe::runParallel` partitions by event-key range, not by expected amount of
work. Real event cost is closer to:

```text
cost(event) ~= nProtons(event) * nPions(event)
```

or even:

```text
cost(event) ~= candidates(event) * number_of_output_quantities
```

If event multiplicity varies, equal event-count partitions are not equal work
partitions. One worker can end up with heavier events while other workers finish
and wait at `std::thread::join()`.

### The callback is concurrent, but callback state is shared

`Lambda::rootAnalysis(...)` receives:

- one `Probe::Event`;
- one worker id;
- one shared `Lambda::AnalysisContext`.

The shared context contains:

- shared `Lambda::RootArray`;
- shared `Lambda::Parameters`;
- shared `Config::Watch`;
- shared `Monitor::AsyncLogger`;
- shared `Record::Writer`.

`Config::Watch::iEvent` and `Config::Watch::n_real_events` are atomic, but the
histogram objects and candidate counters in `Lambda::RootArray` are not
thread-local.

### Histogram filling is currently unsafe and probably distorts scaling

`Record::Writer::recordingScope()` exists specifically to serialize ROOT
histogram filling:

```cpp
std::lock_guard<std::mutex> recordingScope();
```

But in `Lambda::rootAnalysis(...)`, the intended lock is commented out:

```cpp
// {
//     auto lock = ctx.writer.recordingScope();
// }

fillCandidates(ctx.histograms, reconstructCandidates(...));
```

So worker threads call `Lambda::fillCandidates(...)` concurrently on shared
ROOT objects and shared `candidateCount` fields.

That is both a correctness issue and a performance suspect. ROOT histogram
operations may hit internal synchronization or undefined shared-state behavior,
and `Lambda::RootObjects::candidateCount` is a plain `Int_t`.

### `Lambda::fillCandidates` resets shared counters per event

`Lambda::fillCandidates(...)` starts with:

```cpp
Record::resetAllCounts(histogramSets);
```

Then it fills candidates for one event and records event multiplicity through
`Record::countAll(...)`.

With shared `histogramSets`, one worker can reset counts while another worker
is still filling its event. This can corrupt multiplicity histograms even if
the individual `TH1D::Fill(...)` calls appear to survive.

### Candidate materialization is expensive

`Lambda::reconstructCandidates(...)` pushes every proton-pion combination into
`Lambda::Candidates::unvalidated`.

For the inspected production input, the first 10k events produced about
151.8 million unvalidated candidates. Each candidate is a `Lorentz` object
that is later walked again for histogram filling.

That means the current path does at least two heavy passes:

1. build/store all candidate vectors;
2. fill output objects from those vectors.

For the unvalidated set, most of this could be streamed directly to an output
sink without retaining the full vector.

### Monitor hot-path work is too expensive

`Lambda::rootAnalysis(...)` calls:

- `Monitor::AsyncLogger::publishThreadStats(...)` before analysis;
- `Config::Watch::recordEvent(...)`;
- `Monitor::AsyncLogger::publish(...)`;
- `Monitor::AsyncLogger::publishThreadStats(...)` after analysis.

`Monitor::AsyncLogger::publishThreadStats(...)` takes a mutex, updates a map,
pushes a dirty snapshot, and notifies the logger thread. The logger thread then
writes thread-stat files through `Monitor::writeTextFile(...)`.

For 100k events, that is up to 200k thread-stat updates. At higher thread
counts, the mutex pressure rises and the logger can become a throughput tax.

### Monitor units are confusing

`Monitor::PacingInfo::heartbeatMs` is named like milliseconds, log output says
"Status Snapshot Interval (ms)", but the type is `Config::uSeconds` and
`Monitor::configureMonitor(...)` assigns:

```cpp
p.heartbeatMs = Config::uSeconds(hb);
```

So a config value that looks like milliseconds is interpreted as microseconds.
This can make logging much more aggressive than intended.

### Dense-key assumptions are fragile

When `nEventsHint > 0`, `Probe::runParallel` uses:

```cpp
firstKey = Probe::BranchControl::probeFirstKey(...)
lastKey  = firstKey + total - 1
```

`Probe::EventStream` also uses dense key assumptions when `nEventsHint > 0`.
This is fine only when event keys are contiguous and exactly one logical event
exists per key.

If keys are sparse or have gaps, the stream can generate empty events or wrong
partitions.

### Data/config branch names can drift

Current `Lambda::declareDataObjects(...)` writes `event_index`, while the
current reconstruction config for the large input references `Index`. The
large production file inspected has `Index`.

This is probably historical drift, but it is dangerous. A newly generated file
from current data code may not match the current reconstruction config unless
the config is also changed.

## Potential Problems

### `std::vector<bool>` should not be used for worker readiness

The proposed idea of workers pushing readiness into a `std::vector<bool>` is
risky. `std::vector<bool>` is a packed bitset specialization with proxy
references, not a normal vector of independent booleans.

If a main-thread callback mode is ever added, use one of:

- `std::queue<ReadyEvent>` plus `std::mutex` and `std::condition_variable`;
- a bounded MPSC queue;
- per-worker SPSC queues;
- `std::vector<std::atomic<bool>>` only for simple flags, not event ownership.

### Main-thread callback mode can serialize the actual bottleneck

A design where workers only load events and the main thread invokes the
callback may help isolate ROOT input from analysis, but it serializes
`Lambda::rootAnalysis(...)`.

That would not solve expensive candidate reconstruction or histogram filling.
It may be useful as a debug mode or as an ordered-output mode, but it should
not replace worker-thread callbacks as the default performance route.

### Event buffering can explode memory

If workers load full `Probe::Event` objects and queue them for a main thread,
memory pressure can rise quickly. Production events contain tens of protons and
hundreds of pions on average, and reconstructed candidate counts can be much
larger.

Any queued callback design needs bounded queues and backpressure.

### ROOT object ownership is too implicit

`Probe::EventStream` owns its `TFile`, `Probe::FlatReader` owns branch address
buffers, and `Lambda::RootArray` owns raw `TH1D*` and `TTree*` pointers through
ROOT directories.

This works when lifetimes are simple, but parallel execution makes ownership
mistakes harder to debug. Per-worker output shards will need explicit merge and
write ownership rules.

### Exceptions do not stop other workers early

`Probe::runParallel` stores worker exceptions and rethrows after join. If one
worker fails, the other workers keep running until their partitions finish.

For large runs, this can waste time after a deterministic schema or read error.
An atomic cancellation flag would allow other workers to stop sooner.

### More threads can increase I/O contention

Each worker opens the same ROOT file independently. On local SSD this can work
well up to a point, but higher thread counts can increase:

- decompression pressure;
- ROOT cache memory;
- disk read contention;
- branch basket contention;
- duplicated seek work without indexes.

Higher CPU usage does not prove higher useful event throughput.

## Bottlenecks

### Bottleneck 1: production event shape

The inspected production input is much heavier than the fixture. The average
row counts are roughly:

- 30 protons per event;
- 275 pions per event.

The first 10k inspected events produced about 15k unvalidated proton-pion
pairs per event. A 100k-event run can therefore produce on the order of
billions of candidate-level histogram fill opportunities.

This makes the "analysis smoke test" misleading if it only loops 100k times
without matching production multiplicity and output behavior.

### Bottleneck 2: shared histogram output

`Lambda::fillCandidates(...)` fills six particle properties for each
candidate set, plus event multiplicity counts. For unvalidated candidates, the
volume is huge.

Because all workers fill the same `Lambda::RootArray`, output is either:

- data-racy;
- internally serialized by ROOT somewhere;
- cache-contention-heavy;
- or all three.

This is a prime suspect for "CPU usage scales but useful work does not".

### Bottleneck 3: monitor mutex and file churn

The logger path is hot even when rendering is infrequent because
`Monitor::AsyncLogger::publishThreadStats(...)` is called twice per event.

At 100k events, this creates significant mutex traffic. If thread-stat file
writing is enabled, the logger thread also repeatedly truncates and rewrites
per-worker files.

### Bottleneck 4: no-index flat stream positioning

Without `TTreeIndex`, `Probe::FlatReader` walks from entry 0 to the partition
start in every worker. For 100k events this was not enough by itself to explain
minutes of runtime in the no-op measurement, but it is still structurally
wrong and becomes worse for larger event counts and higher thread counts.

It also makes startup cost grow with partition start position.

### Bottleneck 5: static work partitioning

Equal event ranges are not equal reconstruction work. A worker assigned a
high-multiplicity region can dominate wall time while other workers finish.

The current `std::thread::join()` phase then looks like workers waiting for
each other, even though the real cause is static imbalance.

### Bottleneck 6: allocation churn in `Probe::Event`

`Probe::EventStream::next()` clears `current_.particles` and `current_.aux`
every event. `Probe::FlatReader::ensureLabel(...)` then recreates map entries.

For millions of events, repeated unordered-map and vector allocation can become
noticeable. This is lower priority than output and partitioning, but worth
fixing during a Probe cleanup.

## Solutions

### Solution 1: make `Probe::ProbeParallel` the actual engine

Unify `Probe::ProbeParallel`, `Probe::runParallel`, and prestream setup under
one owner.

Target shape:

- `Probe::ProbeParallel::configure(...)`
- `Probe::ProbeParallel::resolveEvents()`
- `Probe::ProbeParallel::preparePlan()`
- `Probe::ProbeParallel::run(...)`
- `Probe::ProbeParallel::stats()`

Keep `Probe::runParallel(...)` temporarily as a compatibility wrapper:

```cpp
template <typename Callback>
void Probe::runParallel(..., Callback&& callback) {
    Probe::ProbeParallel probe;
    probe.configure(...);
    probe.run(std::forward<Callback>(callback));
}
```

After callers are migrated, either delete the free function or leave it as a
thin deprecated facade.

### Solution 2: introduce `Probe::ExecutionPlan`

Add an internal execution plan owned by `Probe::ProbeParallel`.

It should contain:

- input file path;
- collection mode: flat or vector;
- resolved event count;
- first key and last key when dense keys are valid;
- whether every flat tree has `TTreeIndex`;
- worker partitions;
- optional per-collection entry ranges;
- branch/type validation results;
- estimated work per partition when available.

This moves setup out of worker startup and gives one inspectable object for
debugging and logging.

### Solution 3: fix no-index flat partitioning

For flat trees without `TTreeIndex`, do not let every
`Probe::FlatReader::FlatReader(...)` walk from entry 0 with kinematic branches
active.

Instead, during `Probe::ProbeParallel::preparePlan()`:

1. Open the file once.
2. For each flat collection, activate only the index branch.
3. Scan index values once.
4. Build event-key to entry-range metadata.
5. Partition using event keys and/or estimated row counts.
6. Pass entry bounds directly to each worker's reader.

For dense keys, the metadata can be compact:

```text
event key -> [first entry, last entry]
```

For very large files, consider a sidecar cache keyed by:

- input path;
- file size;
- modification time;
- tree name;
- index branch name.

Do not require rewriting the 88G production file just to get a persistent
ROOT index.

### Solution 4: support dynamic chunk scheduling

Replace one static partition per worker with many smaller chunks.

Basic route:

- create chunks larger than one event but smaller than a full worker range;
- use `std::atomic<std::size_t> nextChunk`;
- each worker repeatedly claims the next chunk;
- each chunk creates or repositions a stream using precomputed entry bounds.

Better route:

- estimate chunk work from row counts per event;
- partition by approximate pair count or row count;
- keep chunks balanced by expected work, not just event count.

This addresses "workers waiting for each other" at `join()`.

### Solution 5: keep worker-thread callbacks as default

The default should remain:

```cpp
worker loads event -> worker invokes callback
```

This preserves analysis parallelism.

If a serial callback mode is useful, make it explicit:

```cpp
enum class Probe::CallbackMode {
    WorkerThread,
    MainThreadOrdered
};
```

`Probe::CallbackMode::MainThreadOrdered` must use bounded queues and
backpressure. It should be documented as a determinism/debug option, not the
performance path.

### Solution 6: add `Probe::WorkerContext`

Replace the raw `int threadId` interface with a stable context type:

```cpp
namespace Probe {
    struct WorkerContext {
        int workerIndex;
        Long64_t firstEvent;
        Long64_t lastEvent;
        std::size_t chunkIndex;
    };
}
```

Then support both callback forms during migration:

- `callback(const Probe::Event&, int)`
- `callback(const Probe::Event&, const Probe::WorkerContext&)`

This avoids exposing worker internals while still allowing logging and
per-worker output sharding.

### Solution 7: use per-worker Lambda output shards

Do not fill one shared `Lambda::RootArray` from all workers.

Preferred shape:

1. Create one `Lambda::RootArray` per Probe worker.
2. Each worker fills only its own histograms and counters.
3. After `Probe::ProbeParallel::run(...)` returns, merge worker histograms.
4. `Record::Writer::shutdown(...)` writes the merged output.

ROOT histograms support merging through `TH1::Add(...)` for compatible
histograms. Candidate trees, if enabled, need a separate policy:

- either disable candidate TTrees in parallel reconstruction;
- or write per-worker trees and merge at finalization;
- or serialize tree filling only.

As a short-term correctness patch, wrap `Lambda::fillCandidates(...)` in
`Record::Writer::recordingScope()`. That will likely reduce scaling, so it
should be treated as a fallback, not the final design.

### Solution 8: stream candidate output where possible

Refactor `Lambda::reconstructCandidates(...)` so unvalidated candidates do not
have to be fully materialized before output.

Possible target:

```cpp
namespace Lambda {
    struct CandidateSink {
        void unvalidated(const Lorentz&);
        void validated(const Lorentz&);
        void selected(const Lorentz&);
    };
}
```

Then reconstruction can:

- stream unvalidated candidates directly to the sink;
- retain only validated candidates needed for sorting/selection;
- retain selected candidates if output requires them.

This reduces memory traffic and removes a second pass over the largest
candidate set.

### Solution 9: make monitor publication sampled

Change `Monitor::AsyncLogger::publishThreadStats(...)` usage so it is not
called twice per event unconditionally.

Options:

- publish every `pacing.threadInterval` events;
- publish only phase changes and final worker state;
- batch worker snapshots and flush on the logger heartbeat;
- disable per-worker thread-stat files by default for high-event runs.

Also fix the heartbeat unit mismatch:

- either rename `Monitor::PacingInfo::heartbeatMs` to `heartbeatInterval`;
- or store it as `std::chrono::milliseconds`;
- or make config/log output say microseconds.

### Solution 10: add Probe-specific instrumentation

Add a lightweight `Probe::ProbeStats` object with per-worker counters:

- events loaded;
- particles loaded per collection;
- time in stream construction;
- time in `Probe::EventStream::next()`;
- time in callback;
- chunks processed;
- exceptions;
- empty events;
- max/min event multiplicity.

This should be optional or low-overhead. It will make future "is Probe the
bottleneck?" checks answerable without ad hoc ROOT macros.

### Solution 11: add representative tests and benchmarks

Existing smoke coverage is useful but not representative.

Add:

- a no-index flat ROOT fixture;
- an indexed flat ROOT fixture;
- a sparse-key fixture;
- a high-multiplicity fixture;
- a no-op Probe benchmark;
- a Probe plus logger benchmark;
- a Probe plus Lambda reconstruction benchmark;
- a single-thread versus multi-thread histogram equivalence test after output
  sharding is implemented.

The no-index fixture should intentionally avoid `TTree::BuildIndex(...)` so it
tests the production path.

## Suggested Implementation Route

The chosen route is "Unify Now", but implementation can happen whenever desired.

Order of work when implementation starts:

1. Add `Probe::ExecutionPlan` and make `Probe::ProbeParallel` own preparation.
2. Move `Probe::runParallel` logic behind `Probe::ProbeParallel::run(...)`.
3. Add no-index entry-range planning.
4. Add dynamic chunk scheduling.
5. Add `Probe::WorkerContext` while preserving old callback compatibility.
6. Add `Probe::ProbeStats`.
7. Fix Lambda output with per-worker histogram shards.
8. Reduce monitor hot-path publication.
9. Add representative fixtures and benchmarks.

## Non-Solutions

### Main-thread callback as the primary fix

This can make event loading parallel and callback execution serial, but the
callback contains expensive reconstruction and output. It is not the correct
default performance fix.

### More threads

Increasing `nThreads` can increase CPU usage while adding duplicated seek work,
logger mutex pressure, ROOT output contention, and I/O contention. More threads
will not reliably improve throughput until output sharding, monitor sampling,
and no-index planning are fixed.

### Relying on the fixture result

The fixture has a `TTreeIndex`, tiny event multiplicity, and only 50 events. It
does not reproduce production Probe behavior.

### Rewriting the production ROOT file as the only fix

Adding a persistent ROOT index may help, but the code should not require
rewriting an 88G input file. Probe should be able to build a temporary or
sidecar execution index.

## Bottom Line

`Probe::runParallel` is actually parallel, and worker threads call callbacks on
their own threads. The slowdown is more likely from the interaction of:

- no-index flat ROOT input;
- static chunking;
- heavy production event multiplicity;
- materializing huge candidate vectors;
- shared ROOT histogram filling;
- hot monitor mutex/file-output paths.

The clean fix is to make `Probe::ProbeParallel` the real execution owner,
prepare an explicit `Probe::ExecutionPlan` at configuration time, eliminate
duplicated no-index positioning, use dynamic chunks, keep worker-thread
callbacks, and move Lambda output to per-worker shards before merging.
