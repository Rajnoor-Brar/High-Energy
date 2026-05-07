# Probe Inspection 2

This note revises the Probe parallelism investigation using the external
analysis as a starting point, then corrects it against the current code and the
observed symptom:

- `_Lambda_Reconstruction` does not speed up with higher
  `[events].nThreads`.
- The reported 100k-event run gets worse with more Probe threads:
  about 11 minutes at 2 threads and about 17 minutes at 8 threads.
- CPU usage scales with thread count, but useful event throughput does not.

The important correction to the external analysis is that the current
`Lambda::rootAnalysis` does not hold `Record::Writer::recordingScope()` around
`Lambda::reconstructCandidates` or `Lambda::fillCandidates`. The lock exists,
but the lock block is commented out. That means the current problem is not
"workers serialize through `Record::Writer::histMutex_`." The current problem is
more dangerous: workers concurrently fill shared ROOT output objects and shared
candidate counters without the intended serialization.

## Current Parallel Model

### `Probe::ProbeParallel`

`Probe::ProbeParallel` is not the executor. It is a wrapper/state holder:

- `Probe::ProbeParallel::inputFile`
- `Probe::ProbeParallel::collections`
- `Probe::ProbeParallel::nThreads`
- `Probe::ProbeParallel::nEvents`
- `Probe::ProbeParallel::resolveEvents()`
- `Probe::ProbeParallel::run()`

`Probe::ProbeParallel::run()` delegates directly to
`Probe::runParallel(...)`.

### `Probe::runParallel`

`Probe::runParallel` is the actual executor. It:

1. Calls `Probe::BranchControl::enableRootThreadSafety()`.
2. Detects flat versus vector collection mode.
3. Builds static partitions.
4. Starts worker `std::thread`s.
5. Constructs a worker-local `Probe::EventStream`.
6. Calls the shared callback from the worker thread.

The callback call is:

```cpp
while (stream.next()) callback(stream.event(), static_cast<int>(t));
```

So workers are not waiting for one main thread to call a single callback.
The callback is invoked concurrently by worker threads.

### `Probe::EventStream`

`Probe::EventStream` is per worker. Each worker opens its own `TFile`, creates
its own `Probe::FlatReader` or `Probe::VecReader`, and owns its current
`Probe::Event`.

This is the right broad shape for ROOT: do not share one `TFile` or one
`TTree` reader across worker threads.

## Corrected Reading Of The External Analysis

### ROOT global locking is plausible, but not proven from code alone

The external analysis ranks ROOT's global thread-safety mutex as the highest
suspicion. That is plausible. `Probe::BranchControl::enableRootThreadSafety()`
calls `ROOT::EnableThreadSafety()`, and ROOT can take global locks around
metadata, class dictionaries, directories, branch setup, cache state, and other
internals.

However, do not assume every `TTree::GetEntry` across independent `TFile`s is
fully serialized only because `ROOT::EnableThreadSafety()` was called. Treat
ROOT global locking as a measurement target:

- time in `pthread_mutex_lock`;
- time in ROOT internals;
- time in `TTree::GetEntry`;
- time in `TBranch::GetEntry`;
- time in callback and output.

The higher-thread slowdown strongly supports "contention somewhere", but it
does not by itself identify which mutex or subsystem is responsible.

### `Record::Writer::histMutex_` is not currently the bottleneck

`Record::Writer::recordingScope()` exists and returns a lock on
`Record::Writer::histMutex_`.

But current `Lambda::rootAnalysis` has the intended lock commented out:

```cpp
// {
//     auto lock = ctx.writer.recordingScope();
// }

fillCandidates(ctx.histograms, reconstructCandidates(...));
```

Therefore, the external Route A "move reconstruction outside the lock" does not
apply to the current tree as written. There is currently no lock to narrow.

The actual current issue is that `Lambda::fillCandidates` mutates shared
histograms and shared per-set counters from multiple worker threads. That is a
correctness problem and a likely performance problem.

### `Probe::runParallel` is not serializing callbacks

The callback is shared by reference, but it is called concurrently from worker
threads. If callback state is shared, the state must be thread-safe.

In `_Lambda_Reconstruction.cc`, the callback captures one shared
`Lambda::AnalysisContext`. That shared context contains:

- `Lambda::RootArray& histograms`
- `Lambda::Parameters& parameters`
- `Config::Watch& logging`
- `Monitor::AsyncLogger& asyncLogger`
- `Record::Writer& writer`

`Config::Watch::iEvent` and `Config::Watch::n_real_events` are atomic. The
ROOT output objects in `Lambda::RootArray` are not worker-local.

## Problems

### 1. Shared ROOT output is mutated concurrently

`Lambda::rootAnalysis` calls:

```cpp
fillCandidates(ctx.histograms,
               reconstructCandidates(protonList, pionList, ctx.parameters));
```

`Lambda::fillCandidates` then calls:

- `Record::resetAllCounts(...)`
- `Record::fill(TH1Record&, const Lorentz&)`
- `Record::fill(TreeRecord&, const Lorentz&)`
- `Record::countAll(...)`

The shared `Lambda::RootArray` contains ROOT objects and mutable counters:

- `TH1D* Record::RootObjects::count`
- `std::vector<Record::TH1Record> Record::RootObjects::hists1D`
- `std::vector<Record::TreeRecord> Record::RootObjects::trees`
- `Int_t Record::RootObjects::candidateCount`

This is unsafe in the current code. Multiple workers can reset and fill the
same counters and histograms at the same time.

This is likely enough to explain bad scaling, corrupted multiplicity counts, or
ROOT-internal contention.

### 2. `Lambda::fillCandidates` resets shared per-event counters

`Lambda::fillCandidates` starts by resetting all counts:

```cpp
Record::resetAllCounts(histogramSets);
```

That is a per-event operation, but the storage is shared across all workers.
If worker A resets counters while worker B is still filling or counting its
event, the multiplicity histograms can be wrong.

This is not just a speed issue.

### 3. Production events are far heavier than smoke events

The inspected 10M input has no `TTreeIndex` and has large row counts:

- `Protons`: 304,480,886 rows
- `Pions`: 2,746,275,925 rows

For 10M events, that is roughly:

- 30 proton rows per event;
- 275 pion rows per event.

The first 10k events inspected produced about 151.8 million unvalidated
proton-pion pairs. A 100k-event run can therefore create on the order of
billions of candidate-level operations.

A "100k loop" smoke test that does not reproduce this event shape does not
measure the same workload.

### 4. Candidate materialization is expensive

`Lambda::reconstructCandidates` stores all unvalidated candidates in
`Lambda::Candidates::unvalidated`.

For high-multiplicity events, this means:

1. construct every pair;
2. store every unvalidated `Lorentz`;
3. later walk that vector again in `Lambda::fillCandidates`;
4. fill several histograms per candidate.

This can dominate wall-clock even if the pure function looks cheap in a small
smoke loop.

### 5. `Monitor::AsyncLogger` is hot-path synchronized

`Lambda::rootAnalysis` calls:

- `Monitor::AsyncLogger::publishThreadStats(...)` before analysis;
- `Config::Watch::recordEvent(...)`;
- `Monitor::AsyncLogger::publish(...)`;
- `Monitor::AsyncLogger::publishThreadStats(...)` after analysis.

`Monitor::AsyncLogger::publishThreadStats` takes `Monitor::AsyncLogger::mutex_`
and queues a dirty thread snapshot. The logger worker then writes thread-stat
files through `Monitor::writeTextFile(...)`.

At 100k events, this is up to 200k thread-stat updates. At 8 threads, the
contention and notification rate are higher. This is a credible contributor to
"CPU scales, work does not."

### 6. Monitor heartbeat units are misleading

`Monitor::PacingInfo::heartbeatMs` is named like milliseconds, and
`Monitor::Render::buildLogText` prints:

```text
Status Snapshot Interval (ms)
```

But the type is `Config::uSeconds`, and `Monitor::configureMonitor` assigns:

```cpp
p.heartbeatMs = Config::uSeconds(hb);
```

So the value is interpreted as microseconds. This can make status/runstat
updates much more frequent than intended.

### 7. No-index flat stream positioning duplicates work

The production file has no `TTreeIndex` for `Protons` or `Pions`.

`Probe::FlatReader::FlatReader` has a fast path when `TTree::GetTreeIndex()`
exists:

```cpp
tree_->GetEntryNumberWithIndex(minKey_, 0);
```

Without an index, it falls back to walking forward until `idxValue() >= minKey`.
By that point, kinematic branches are already active, so this is not a cheap
index-only seek.

Every worker constructs its own `Probe::EventStream`; therefore every worker
can duplicate seek-to-start work for its partition.

### 8. Static partitions do not balance real work

`Probe::BranchControl::partitionEvents` partitions event keys by count. But
Lambda reconstruction cost is closer to:

```text
nProtons(event) * nPions(event)
```

Equal event counts are not equal work. Higher thread counts can make this more
visible: some workers finish early, while one or two workers remain on heavy
chunks.

The final `join()` then looks like "threads waiting for each other", but the
cause is static work imbalance.

### 9. `Probe::runParallel` owns too much setup policy

`Probe::runParallel` currently owns:

- ROOT thread-safety setup;
- mode detection;
- event-count hint handling;
- first-key probing through `Probe::BranchControl::probeFirstKey`;
- fallback key scanning through `Probe::BranchControl::scanIndexBranch`;
- partition construction;
- worker creation;
- worker exception collection.

This makes `Probe::ProbeParallel` a wrapper instead of an execution object.
It also means prestream planning cannot be inspected or logged before the run.

### 10. `Probe::ProbeParallel::resolveEvents` can construct a stream just to count

`Probe::ProbeParallel::resolveEvents` first calls `Probe::resolveEventCount`.
If that returns zero, it constructs a full `Probe::EventStream` just to read
`Probe::EventStream::nEvents()`.

That fallback opens a ROOT file, constructs readers, binds branches, and then
throws the stream away. It is acceptable as a last fallback, but it should not
be part of a hot or normal configuration path.

### 11. `nEventsHint` assumes dense event keys

When `nEventsHint > 0`, `Probe::runParallel` computes:

```cpp
firstKey = Probe::BranchControl::probeFirstKey(...)
lastKey  = firstKey + nEventsHint - 1
```

That assumes dense contiguous event keys. If event keys are sparse or if the
input file contains gaps, Probe can iterate keys that do not correspond to real
events.

### 12. Current branch naming has historical drift

Current data declaration code writes `event_index`, while the inspected large
input and current reconstruction config use `Index`.

This is not necessarily the cause of the slowdown, but it is a reproducibility
risk. Probe should not hard-code either name; configs must match the input
being read.

## Potential Problems

### ROOT global thread-safety lock may cap read scaling

Even with per-worker `TFile`s, ROOT may serialize parts of reading or metadata
access through internal locks. If profiling shows most wall time in
`pthread_mutex_lock`, `TTree::GetEntry`, `TBranch::GetEntry`, or ROOT cache
internals, Probe-side callback restructuring will not fix the read floor.

In that case, better routes are:

- pre-shard the input ROOT file by event ranges;
- use ROOT RDataFrame with implicit multithreading if it fits the data model;
- use process-level parallelism and merge outputs;
- build a sidecar index to reduce seek work.

### Main-thread callback dispatch can make analysis serial

The proposed alternate model is:

```text
workers load events -> workers signal ready -> main thread calls callback
```

This may remove concurrent mutation of shared histograms, but it also makes
`Lambda::reconstructCandidates` single-threaded unless reconstruction is moved
back into workers.

For this workload, reconstruction and output are not trivial. Main-thread
callback dispatch is likely slower than a correct worker-local-output design.

### Queued events can grow memory quickly

If workers push complete `Probe::Event` objects into a queue, memory can grow
fast. Production events contain many particle rows, and high-multiplicity
events produce many candidates downstream.

Any queue route needs:

- bounded queues;
- backpressure;
- explicit event ownership;
- clear cancellation behavior.

Do not use `std::vector<bool>` as the readiness mechanism. It is a packed
specialization with proxy references. Use `std::queue`, a condition variable,
or a real bounded queue type.

### Adding a single histogram lock would fix correctness but may worsen scaling

Re-enabling `Record::Writer::recordingScope()` around all
`Lambda::fillCandidates` calls would serialize ROOT output and fix some races.
But it would also make histogram filling a single-thread bottleneck.

It is acceptable as a temporary correctness patch. It is not the final
performance design.

### Per-thread histograms need a tree policy

Per-worker histograms are straightforward. Per-worker `TTree` output is not.

If `Lambda::Parameters::writeTree` is empty, per-worker histogram sharding is
simple. If candidate trees are enabled, choose one:

- per-worker trees and merge at shutdown;
- a small serialized tree-fill path;
- disable candidate trees for parallel reconstruction until implemented.

### More threads can amplify every shared hot spot

The reported 8-thread slowdown is consistent with a shared bottleneck. More
threads can increase:

- ROOT internal mutex contention;
- logger mutex contention;
- ROOT output contention;
- disk I/O contention;
- decompression contention;
- duplicated no-index seek work;
- cache-line bouncing on atomics.

The correct goal is not "use more threads"; it is "remove shared hot paths so
more threads do useful work."

## Bottleneck Ranking

### Highest suspicion: shared ROOT output from `Lambda::fillCandidates`

Current code mutates the same output histograms and counters from all workers.
This is both unsafe and likely expensive.

Why it matches symptoms:

- CPU can rise with thread count because workers are active.
- Useful throughput may not rise because ROOT output and shared cache lines are
  contested.
- Higher thread count can be slower because contention rises faster than useful
  parallel work.

### High suspicion: `Monitor::AsyncLogger` hot path

Two thread-stat updates per event across all workers is too much. Even if each
update is small, it is synchronized and can cause file churn.

Why it matches symptoms:

- More worker threads means more mutex contenders.
- It does not appear in a small "analysis only" smoke loop unless logger calls
  are included.
- It scales with event count.

### High suspicion: ROOT internal locking/read contention

`Probe::BranchControl::enableRootThreadSafety` is required for safety, but it
may reduce parallel read scaling. The only safe conclusion is that this must be
profiled.

Why it matches symptoms:

- More threads can spend more time in ROOT locks.
- CPU usage can rise from lock contention and decompression without improving
  event throughput.

Why it is not the only explanation:

- A no-op Probe read over 100k events was seconds-scale on the inspected
  machine, not minutes-scale.
- The full run includes reconstruction, output, and monitor costs.

### Medium suspicion: no-index flat reader positioning

The production input has no `TTreeIndex`. Each worker may duplicate positioning
work. This is structurally inefficient and should be fixed, but by itself it
did not explain minutes of runtime in a no-op 100k Probe timing.

### Medium suspicion: static partition imbalance

Equal event-count chunks are not equal candidate-work chunks. This can make
some worker threads wait at join while a heavy partition finishes.

### Lower suspicion: `Config::Watch::iEvent` atomic bouncing

`Config::Watch::iEvent` increments once per event across all workers. It can
cause cache-line bouncing, but it is probably smaller than ROOT output,
logging, reconstruction, and read contention.

## Measurement Plan

Do not restructure blindly. Run these measurements on the same 100k or 200k
event subset at `nThreads = 1, 2, 4, 8`.

### 1. Wall-clock sweep

Use the same input file and same event count for every run. Record:

- wall time;
- CPU utilization;
- output file size;
- real event count;
- thread count.

### 2. System profiler

Use an available profiler for the platform:

- macOS: Instruments, `sample`, or `dtrace`-style tooling if available.
- Linux: `perf record -g` and `perf report`.

Look for:

- `pthread_mutex_lock`;
- ROOT mutex symbols;
- `TTree::GetEntry`;
- `TBranch::GetEntry`;
- `TH1::Fill` / `TH1D::Fill`;
- file write calls from logger;
- `Lambda::reconstructCandidates`;
- `Lambda::fillCandidates`.

### 3. Inline phase timing

Add temporary timing around:

- `Probe::EventStream::next`;
- the callback body;
- `Lambda::reconstructCandidates`;
- `Lambda::fillCandidates`;
- `Monitor::AsyncLogger::publishThreadStats`;
- `Monitor::AsyncLogger::publish`.

Print per-worker totals after join. Remove this instrumentation after
measurement.

### 4. Probe-only timing

Run `Probe::runParallel` with:

- no-op callback;
- callback that only touches `Config::Watch`;
- callback that includes logger publish calls;
- callback that includes reconstruction but no output;
- callback that includes output.

This splits read cost from callback cost.

### 5. Output correctness check

Run the same small event subset with `nThreads = 1` and `nThreads = 8`.
Compare histogram entries and integrals. If they differ, shared output races
are already visible.

## Solutions

### Solution A: restore correctness immediately with a narrow output lock

As a temporary correctness patch, compute candidates outside the lock and lock
only the fill:

```cpp
const Lambda::Candidates candidates =
    Lambda::reconstructCandidates(protonList, pionList, ctx.parameters);

{
    auto lock = ctx.writer.recordingScope();
    Lambda::fillCandidates(ctx.histograms, candidates);
}
```

This differs from the external analysis. The current code has no active lock,
so this is not "lock narrowing"; it is "add a narrow lock."

Expected effect:

- fixes shared histogram/counter races;
- may make scaling worse if output dominates;
- gives a correct baseline for further measurement.

### Solution B: use per-worker histograms and merge

This is the recommended performance fix for output.

Design:

1. Before starting workers, clone the declared output histograms once per
   worker.
2. Each worker fills only its own `Lambda::RootArray`.
3. After `Probe::ProbeParallel::run` returns, merge worker histograms into the
   final output array.
4. `Record::Writer::shutdown` writes the merged result.

Relevant APIs/types:

- `Lambda::RootArray`
- `Record::RootObjects`
- `Record::TH1Record`
- `Record::EventTH1Record`
- `Record::TreeRecord`
- `Lambda::fillCandidates`
- `Record::Writer::shutdown`

Add helpers such as:

- `Lambda::cloneRootArray`
- `Lambda::mergeRootArray`

For v1, assert or reject parallel candidate trees if
`Lambda::RootObjects::trees` is non-empty.

### Solution C: stream candidate output

Refactor `Lambda::reconstructCandidates` so unvalidated candidates do not need
to be stored in a giant vector.

Target concept:

```cpp
namespace Lambda {
    class CandidateSink {
      public:
        void unvalidated(const Lorentz&);
        void validated(const Lorentz&);
        void selected(const Lorentz&);
    };
}
```

Then `Lambda::reconstructCandidates` can emit unvalidated candidates directly
to a worker-local output sink and retain only the smaller candidate set needed
for selection.

This attacks the biggest production-volume path.

### Solution D: sample monitor updates

Change hot-path monitor publication so it is not called twice per event.

Options:

- call `Monitor::AsyncLogger::publishThreadStats` every N events per worker;
- publish only phase changes plus final state;
- store worker-local counters and flush them on `Monitor::AsyncLogger`
  heartbeat;
- disable per-worker thread-stat file writes by default for high-event runs.

Also fix `Monitor::PacingInfo::heartbeatMs` naming/units.

### Solution E: move Probe planning into `Probe::ProbeParallel`

Unify execution ownership:

- `Probe::ProbeParallel::configure`
- `Probe::ProbeParallel::resolveEvents`
- `Probe::ProbeParallel::preparePlan`
- `Probe::ProbeParallel::run`

Move these out of the hot launch path:

- first-key probing;
- partition construction;
- no-index entry range planning;
- mode validation;
- branch validation where possible.

Keep per-worker `Probe::EventStream` construction. Do not share one stream.

### Solution F: add no-index entry-range planning

During `Probe::ProbeParallel::preparePlan`, scan only index branches and build
entry ranges for partitions. Then pass entry bounds to worker readers so they
do not seek from entry 0 with kinematic branches active.

This requires extending `Probe::FlatReader` or adding a reader plan type so a
worker can start at a known entry range.

### Solution G: dynamic chunk scheduling

Replace one static partition per worker with many chunks.

Basic implementation:

- precompute chunks;
- use an atomic next-chunk counter;
- each worker claims chunks until exhausted.

Better implementation:

- estimate chunk weight from index row counts or approximate
  `nProtons * nPions`;
- keep chunk weights roughly equal.

This reduces end-of-run worker imbalance.

### Solution H: optional main-thread callback mode

Do not make this the default performance route. It serializes callback work.

If implemented, make it explicit:

```cpp
enum class Probe::CallbackMode {
    WorkerThread,
    MainThreadOrdered
};
```

Use bounded queues and condition variables. Do not use `std::vector<bool>` as
the readiness structure.

This mode is useful for:

- deterministic debugging;
- proving whether callback/output is the bottleneck;
- serial ROOT output compatibility.

It is not the main speedup route.

## Foolery

### `Probe::ProbeParallel` is a facade without execution ownership

The name suggests a runner. The implementation is only a wrapper over
`Probe::runParallel`. This makes state ownership unclear.

### `Probe::runParallel` opens the input before workers and workers open it again

The pre-worker open is used for entry count or key scanning. Workers then open
their own `TFile`s. Per-worker opens are necessary; the extra pre-worker open
is not inherently wrong but belongs in a prepared execution plan.

### Full-key scan fallback uses `std::set`

When `nEventsHint == 0`, `Probe::runParallel` scans index branches into a
`std::set<Long64_t>`. For large files, that is a lot of node allocation and
poor locality.

This path is avoided when `nEventsHint > 0`, but it remains a bad fallback.

### `Probe::readAllParallel` exists despite being unsafe for large files

`Probe::readAllParallel` is marked with a memory warning and pushes all events
into a shared vector under a mutex. It should not be part of the production API
unless there is a small-file-only use case.

### The fixture proves the wrong thing

The fixture has a `TTreeIndex`, tiny event count, and tiny multiplicity. It
does not test the production path where the input has no `TTreeIndex` and high
multiplicity.

### Monitor config names lie about units

`heartbeatMs` and "Status Snapshot Interval (ms)" imply milliseconds, but the
stored type is microseconds.

## Routes

### Route 0: measure before and after every change

This is mandatory. The symptom is contention-like, but the exact bottleneck is
not proven by code inspection alone.

Keep a table for:

- `nThreads = 1, 2, 4, 8`;
- no-op Probe;
- Probe plus logger;
- Probe plus reconstruction;
- Probe plus reconstruction plus output;
- full `_Lambda_Reconstruction`.

### Route A: correctness baseline

Add a narrow `Record::Writer::recordingScope` around
`Lambda::fillCandidates` only.

Purpose:

- prove output races are real or not;
- get correct single-shared-output behavior;
- measure how much serialized output costs.

Expected risk:

- may further reduce speedup.

### Route B: per-worker output shards

Implement `Lambda::cloneRootArray` and `Lambda::mergeRootArray`, then fill
worker-local histograms.

This is the recommended speed route if output contention is significant.

Expected result:

- removes shared `TH1D::Fill` hot path;
- fixes `candidateCount` races;
- keeps reconstruction parallel.

### Route C: Probe unification

Move `Probe::runParallel` body into `Probe::ProbeParallel`.

Add:

- `Probe::ExecutionPlan`;
- `Probe::ProbeStats`;
- `Probe::WorkerContext`;
- `Probe::ProbeParallel::preparePlan`;
- cached partitions.

This cleans up ownership and lets config-time setup produce the run plan.

This is important engineering work, but it should not be expected to solve
shared output contention by itself.

### Route D: no-index and dynamic scheduling

Add no-index entry-range planning and dynamic chunks.

This addresses:

- duplicated flat-reader positioning;
- worker imbalance;
- high thread count slowdowns from static partitions.

### Route E: ROOT read scaling alternative

If profiling proves ROOT read locking dominates even after output and monitor
fixes:

- pre-shard input files and run process-level parallel jobs;
- use RDataFrame with implicit multithreading if the schema can fit;
- build a sidecar index;
- consider a vector/event-row data format for reconstruction inputs.

### Route F: main-thread callback mode

Implement only as optional:

- `Probe::CallbackMode::MainThreadOrdered`
- bounded queues;
- worker-loaded events;
- main-thread callback.

Use it to diagnose callback/output bottlenecks or guarantee ordered serial
output. Do not use it as the default performance path.

## Recommended Execution Order

1. Add temporary instrumentation.
2. Run a thread sweep on a fixed event count.
3. Add narrow output lock for correctness and rerun.
4. If output lock dominates, implement per-worker histograms and merge.
5. Reduce monitor update frequency and fix heartbeat units.
6. Move Probe execution planning into `Probe::ProbeParallel`.
7. Add no-index entry-range planning.
8. Add dynamic chunk scheduling.
9. Re-evaluate whether ROOT read locking is still the floor.
10. Only then consider optional main-thread callback mode.

## Bottom Line

The external analysis is directionally useful but stale in one crucial place:
current `Lambda::rootAnalysis` is not serializing on
`Record::Writer::histMutex_`; it is concurrently mutating shared ROOT output.

The most likely explanation for worse runtime at 8 threads is combined
contention:

- shared ROOT histogram/counter mutation in `Lambda::fillCandidates`;
- hot `Monitor::AsyncLogger` mutex and file output;
- ROOT internal locking or read contention;
- no-index flat-reader positioning;
- static partition imbalance;
- very high real candidate volume.

`Probe::runParallel` does call callbacks from worker threads. The fix is not to
make the main thread call every callback. The better route is to keep analysis
parallel, make output worker-local, reduce monitor hot-path synchronization,
and make `Probe::ProbeParallel` own an explicit precomputed execution plan.
