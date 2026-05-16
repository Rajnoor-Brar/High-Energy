# Architecture

Updated: 2026-05-15.

Focus: `utils/` layer. Domain logic lives in `modules/Lambda/`; driver entry
points live in the top-level `_*.cc` files.

---

## Overview

The runtime is a three-stage pipeline:

```
[ROOT TTree] ──► Probe ──► user callback ──► Record::Writer ──► [ROOT output]
                                 │
                          Monitor::AsyncLogger (heartbeat, progress, stall)
```

Configuration is parsed once from TOML at startup and distributed to each
stage via `Config::configure<ProbePipeline>()`.

---

## Config

### Responsibilities

- Parse a TOML file and an optional limits file into `Watch`, `Register`, and
  `Events` structs.
- Resolve thread counts (hardware concurrency minus two, clamped to ≥ 1).
- Parse `event_particles` sections into `CollectionSpec` vectors (both
  inline-array and named-table formats).
- Provide `Config::configure<ProbePipeline>()` — a single-call facade that
  configures Probe, Writer, and Monitor without the caller managing order.

### Key types (`Config/Types.hh`)

| Type | Purpose |
|---|---|
| `Watch` | Runtime logging flags and event counter |
| `Register` | Output paths, histogram bin counts, limits maps |
| `Events` | Event-count cap, thread counts, particle specs |
| `Bounds` | `{low, high}` pair for histogram / cut limits |
| `ParticleLimits` / `EventLimits` | `ParticleProperty`/`EventProperty` → `Bounds` maps |

### Include topology

`Config.hh` wraps `Config/{Types,TypeAid,LimitAid,Defaults,Reader}`.
`Config/Configure.hh` is excluded from the wrapper because it depends on
`Probe.hh`, `Record.hh`, and `Monitor.hh`, which all depend on `Config.hh`
(would be circular). Drivers include `Config/Configure.hh` explicitly after
their other umbrella includes.

---

## Probe

### Responsibilities

Read ROOT TTrees in parallel and invoke a user-supplied callback for each
event, delivering a `std::vector<std::vector<Lorentz>>` — one inner vector
per particle collection declared in config.

### `ProbeParallel` (the primary path)

`ProbeParallel` splits the event space across *N* reader threads. Two callback
modes are selectable at runtime:

| Mode | Behaviour |
|---|---|
| `CollectorThread` | Reader workers push events onto a bounded queue; a single collector thread drains the queue and invokes the callback serially |
| `WorkerThread` | Each reader worker invokes the callback directly (callback must be thread-safe) |

Stream types detected automatically:

| `StreamType` | Source layout |
|---|---|
| `Events` | TTree with event-key index (flat per-event branches) |
| `Vectors` | TTree with vector-valued branches (one entry = one event) |

Entry bounds are precomputed in `configureProbe` by scanning the TTreeIndex or
vector entry count, then partitioned uniformly across threads.

### `ProbeIMT`

Alternative reader using ROOT's `TTreeProcessorMT`. Loads all events into a
3-D buffer (`vector<vector<vector<Lorentz>>>`) then flushes in parallel.
Suitable only for event-keyed (flat) streams; not used in the reconstruction
pipeline by default.

### Internal structure

```
Probe/Types          CollectionSpec, Bounds, EventStream, StreamType
Probe/BranchControl  ROOT branch introspection, KinBuf (branch binding), key scanning
Probe/ConfigAid      TOML → CollectionSpec parsing; validates branch names
Probe/Readers        FlatReader, VecReader — per-thread TTreeReader wrappers
Probe/Parallel       ProbeParallel class declaration
Probe/ParallelIMT    ProbeIMT class declaration
Probe/Administration Constructors, getters, partition helpers (determineStreamType,
                     prepareEventPartitions, prepareEntryBounds)
Probe/Configuration  configureProbe() implementations for both classes
Probe/Methods        run() body — spawns reader threads, handles IMT flush
Probe/Directives     Worker and collector thread loop bodies
```

---

## Record

### Responsibilities

Accept fill requests from analysis callbacks, buffer them through a worker
pool, accumulate per-worker ROOT-object clones, and write merged masters to a
ROOT output file.

### Threading model

```
caller thread  ──pushFill()──► bounded deque ──► N fill-worker threads
                                                       │
                                              per-worker TH1/TH2/TGraph/TProfile clones
                                                       │
                                              watchdog thread
                                                  │            │
                                           finalize()    checkpoint() (every K events)
                                                  │
                                          mergeAllClones() → TFile::Write()
```

- **Fill workers**: pull `FillRequest` variants from the deque and dispatch via
  `if constexpr` to `applyParticleRequest`, `applyHist1DRequest`, etc.
- **Clones**: each fill-worker has its own ROOT object clones, allocated in
  `allocateAllClones()`. Clones are detached from any `TDirectory` so they
  don't appear in the output file.
- **Merge**: `mergeAllClones()` resets the master then `Add()`s each clone
  into it. For `TGraph`, points are copied sequentially.
- **Watchdog**: a dedicated thread monitors `consumed_` and emits
  `WatchRequest`s to `Monitor::AsyncLogger`, which triggers checkpoint
  or finalize depending on the abort flag.

### Fill request lifecycle

```
fillParticleEvent(basis, particles)
    → pushFill(ParticleRequest{...})     ← move-only, no copy
    → fill-worker dequeues
    → applyParticleRequest(req, workerIdx)
    → clone[workerIdx]->Fill(...)
```

### Internal structure

```
Record/Types          Master and clone record structs; RecordKey
Record/Type_Methods   RecordKey hash, equality, string
Record/Requests       FillRequest variant + all request types
Record/Configs        Paths, HistConfig (output paths + limits)
Record/Meta           Run provenance metadata; writeMeta()
Record/Writer         Class declaration; aggregates all impl fragments
Record/Declaration    declareXxx() — register histograms/graphs/trees
Record/Recording      fillXxx() — create fill requests; scaleAndWrite
Record/Directives     pushFill(), worker loop, applyXxxRequest bodies
Record/Cloning        allocateAllClones(), mergeAllClones(), *Impl helpers
Record/Administration open/start/finalize/checkpoint lifecycle;
                      binds Monitor::AsyncLogger as the watchdog
```

---

## Monitor

### Responsibilities

Run a background heartbeat thread that: renders terminal progress (status line
+ bar), detects fatal stalls, writes run-stat files, and issues checkpoint /
finalize signals to `Record::Writer`.

### `AsyncLogger` lifecycle

```
AsyncLogger::start()
    ↓
heartbeat thread ──loop──► sleep(heartbeatMs)
                        ├── render progress (every printInterval events)
                        ├── render bar (every barInterval events)
                        ├── check stall (every checkInterval events)
                        │       └── stallThreshold exceeded? → abort + finalize
                        └── flush log slots → file / stdout

AsyncLogger::stop()
    ↓
join heartbeat thread
```

`WatchRequest` variants are emitted by the watchdog in `Record::Administration`
and queued in Logger's slot vector. The heartbeat loop drains them.

### Pacing (`PacingInfo`)

| Field | Default | Effect |
|---|---|---|
| `printInterval` | 10 | render status line every N events |
| `barInterval` | 50 | render progress bar every N events |
| `checkInterval` | 10 000 | check stall / emit WatchRequest every N events |
| `heartbeatMs` | 1 000 ms | heartbeat sleep duration |
| `terminalRefresh` | 300 s | full terminal re-draw period |
| `stallThreshold` | 300 s | no-progress duration before abort |

### Internal structure

```
Monitor/Types          PacingInfo, RunSnapshot, PendingActions
Monitor/Logger         AsyncLogger class declaration (no method bodies)
Monitor/Methods        String builders: updatedETA, formatProgress, statusLine
Monitor/Render         renderStatus, renderBar (ANSI terminal, ioctl width)
Monitor/Report         writeRunStat, flushLog
Monitor/Directive      Main loop body, heartbeat dispatch, mergePending
Monitor/Administration Constructor/destructor, start/stop, bindWriter
Monitor/Configure      configureMonitor() — TOML → AsyncLogger pacing/stall
Monitor/ConfigAid      Compatibility shim → Configure.hh
Monitor/Timer          BlockTimer RAII helper (independent of AsyncLogger)
```

---

## Physics

Thin domain layer. No `utils/` dependencies other than ROOT's `Math/Vector4D`.

- `Physics/Types.hh` — `Lorentz` alias (`ROOT::Math::PxPyPzEVector`);
  `ParticleProperty` / `EventProperty` enums with trait tables (name,
  extractor function).
- `Physics/Kinematics.hh` — invariant mass, rapidity, pT, η calculators.
- `Physics/Properties.hh` — `valueOf(lorentz, property)` dispatcher.
- `Physics/TypeAid.hh` — enum↔string converters.

---

## Utility

Three fully independent helpers with no mutual dependencies (except
`Utility/Time` which uses `Config::uSeconds`/`Seconds`).

- `Utility/RootTypes.hh` — `DataType` enum + `detectBranchType(TBranch*)`
  and `typeName()` used throughout Probe for branch introspection.
- `Utility/Number.hh` — comma-separated, padded integer formatter.
- `Utility/Time.hh` — elapsed-time and ETA string formatters.

---

## Paint

Fully isolated from the Probe/Record/Monitor runtime stack. Used only by the
`_Paint.cc` entry point and `tests/test_paint.cc`.

```
Paint/Types       Config types for plots (PlotType, PadConfig, CanvasConfig, …)
Paint/Style       ROOT style setters (color, marker, line)
Paint/Apply       applyPad/Canvas/drawEntries onto ROOT objects
Paint/Save        savePlot — renders and exports to file
Paint/Book        TOML → PaintConfig parser
Paint/Render      Low-level TH1/TH2/TGraph drawing primitives
Paint/Resolve     ROOT object retrieval from TFile/TDirectory by path
Paint/Illustrator High-level driver: book → resolve → render → save
```

---

## Threading Summary

| Thread | Owner | Role |
|---|---|---|
| Main | driver | configure, call `run()`, await completion |
| Reader × N | `ProbeParallel` | open TFile, read TTrees, push to queue or invoke callback |
| Collector (optional) | `ProbeParallel` | drain queue, invoke callback serially |
| Fill worker × M | `Record::Writer` | dequeue `FillRequest`, fill per-worker clones |
| Watchdog | `Record::Writer` | monitor `consumed_`, emit `WatchRequest`, merge+write on finalize |
| Heartbeat | `Monitor::AsyncLogger` | render progress, detect stall, flush log slots |

Reader thread count (`probe_threads`) and fill-worker count (`record_threads`)
are configured independently. Both default to `(hardware_concurrency − 2) / 2`.

---

## Data Flow

```
TOML file
    │
    ▼ Config::readConfig
Watch / Register / Events
    │
    ├──► Probe::configureProbe(Events)
    │         │
    │         ▼ ProbeParallel::run(callback)
    │         │   Reader thread 0: FlatReader/VecReader → Lorentz vectors
    │         │   Reader thread 1: …
    │         │   [Collector thread]: invoke callback(event_vectors)
    │         │
    │         └──► callback (Lambda::reconstructCandidates, …)
    │                   │
    │                   ▼ Record::Writer::fillParticleEvent(…)
    │                         │ pushFill(ParticleRequest)
    │                         ▼
    │                   Fill worker: clone[i]->Fill(…)
    │
    ├──► Monitor::AsyncLogger::start()
    │         heartbeat thread: progress render, stall check
    │         WatchRequest: checkpoint every K events
    │
    └──► end of run:
              mergeAllClones()
              TFile::Write()
              Monitor::AsyncLogger::stop()
```
