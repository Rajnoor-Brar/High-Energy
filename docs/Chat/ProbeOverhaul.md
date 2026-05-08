# Probe Overhaul Plan

## Summary

`Probe::ProbeParallel` becomes the owner of Probe setup and execution:
input path, particle specs, thread count, event count, stream type,
partitions, worker startup, queue coordination, callback dispatch, and
runtime stats.

The default callback mode is `Probe::CallbackMode::CollectorThread`.
Workers read/build `Probe::Event` objects and push them into a bounded FIFO.
A collector thread pops those events and calls the analysis callback serially.
`Probe::CallbackMode::WorkerThread` remains available for the previous direct
worker-callback behavior.

## Implemented API Shape

New Probe-level types:

```cpp
enum class StreamType { Unset, Events, Vectors };
enum class CallbackMode { WorkerThread, CollectorThread };
enum class IndexOrdering { Unknown, Ascending, Descending, Unordered };

struct Bounds {
    Long64_t first = 0;
    Long64_t last = -1;
};

struct IndexSpec {
    BranchSpec branch;
    IndexOrdering ordering = IndexOrdering::Unknown;
    bool dense = false;
    bool grouped = false;
};

struct QueuedEvent {
    std::size_t workerIndex = 0;
    Long64_t eventIndex = 0;
    Event event;
};
```

`Probe::ProbeParallel` no longer exposes mutable configuration fields. It is
configured through:

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

`using CollectionSpec = ParticleSpec` remains for compatibility with existing
config parsing and older call sites.

## Execution Model

`Probe::ProbeParallel::configureProbe` resolves event count with this priority:

1. explicit TOML event count;
2. ROOT metadata via `Probe::resolveEventCount`;
3. brute-force fallback by scanning indexed event keys or vector tree entries.

For indexed event streams, `ProbeParallel` builds logical event partitions once
and scans each index branch once to produce per-worker, per-particle ROOT entry
bounds. Workers pass those bounds into `Probe::EventStream`, and
`Probe::FlatReader` can start directly at the worker’s relevant row range.

For collector mode, a bounded FIFO uses `std::deque<Probe::QueuedEvent>`,
`std::mutex`, `std::condition_variable`, worker progress counters, and a
shutdown flag. Producers wait when the queue is full; the collector waits when
the queue is empty. Normal movement uses `notify_one`; shutdown and errors use
`notify_all`.

For vector streams, the current direct vector reader path remains separate.
Collector mode for vectors throws until a deliberate vector queue path is
designed.

## Config And Call Sites

`Config::configure(..., Probe::ProbeParallel&, ...)` now calls
`Probe::ProbeParallel::configureProbe(...)` instead of assigning public fields.
After Probe resolves the event count, it mirrors the resolved values into
`Monitor::AsyncLogger::watch()`.

Drivers use Probe accessors such as `probe.inputFile()` and `probe.eventCount()`.
`Probe::runParallel` remains as a compatibility shim that configures a
temporary `ProbeParallel` in `WorkerThread` mode.

## Test Coverage

Existing Lambda smoke coverage still verifies end-to-end reconstruction through
`Probe::ProbeParallel`.

Focused Probe coverage verifies:

- collector mode calls the callback exactly once per logical event;
- worker mode preserves direct worker callbacks;
- small queue capacity still drains correctly;
- collector callback exceptions propagate to the caller;
- event ids from the fixture cover the expected range;
- `Probe::stats()` reports produced and consumed event counts.

## Current Assumptions

The v1 indexed event path assumes current Lambda files have ascending, dense,
grouped event-index branches. If an indexed branch is detected as non-ascending
during bounds preparation, Probe throws instead of silently using an unsafe
parallel path.

The future `[probe.index.<particle>]` TOML schema is still deferred. Current
`event_particles` parsing remains the source of particle and branch identity.
