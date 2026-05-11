# Codebase Map

Updated: 2026-05-10.

High-Energy is a C++17, header-heavy ROOT/Pythia8 Lambda baryon
reconstruction project. The current architecture is post Probe/Writer
overhaul: Probe owns event input, Lambda owns physics analysis, and
`Record::Writer` owns ROOT output objects and queued output mutation.

Companion docs:

- [CGPTsummary.md](CGPTsummary.md): condensed historical context for the overhaul.
- [Issues.md](Issues.md): active performance and threading investigation
  (P0 = `nThreads` scaling).
- [REVIEW.md](REVIEW.md): expansions/improvements backlog for Probe,
  Writer, Monitor, Lambda. Includes the `Monitor::Timer` proposal that
  replaces the current `BlockTimer`.
- [DataFlow.md](DataFlow.md): current TOML/config/runtime data flow.

## Runtime ownership

```
Config/Configure.hh
  -> configures Probe or Pythia, Record::Writer, Monitor::AsyncLogger

Probe::ProbeParallel or Pythia8::Pythia[Parallel]
  -> produces one logical event at a time

Lambda::{rootAnalysis,pythiaAnalysis,dataGenerator}
  -> reconstructs candidates or raw rows
  -> enqueues Writer requests

Record::Writer
  -> owns output TFile and ROOT records
  -> scribe thread mutates ROOT objects
  -> checkpoint/finish/fatal write

Monitor::AsyncLogger
  -> heartbeat/progress/logging thread
```

Normal reconstruction driver shape:

```cpp
Probe::ProbeParallel probe;
Record::Writer writer;
Monitor::AsyncLogger logger;

Config::configure(configPath, project, probe, writer, logger);

Lambda::Parameters parameters;
Lambda::configure(parameters, writer, configPath);

writer.bind(logger, logger.watch(),
            [&] { return Lambda::logString(parameters); });

logger.initialise(writer);
writer.start();

Lambda::AnalysisContext ctx{parameters, logger.watch(), logger, writer};
probe.run([&](const Probe::Event& ev, int threadId) {
    Lambda::rootAnalysis(ev, threadId, ctx);
});

writer.finish(logger.watch().nEvents);
```

No active Lambda driver should construct `Lambda::RootArray` or call
`writer.shutdown(sets)`.

## Layering

```
Physics  -> ROOT math types only
Utility  -> generic number/time/root-type helpers
Config   -> TOML parsing and runtime object configuration
Probe    -> ROOT input reader and event dispatcher
Monitor  -> async terminal/log output
Record   -> ROOT output owner, request queues, metadata
Lambda   -> domain analysis and output declarations
Drivers  -> wire one pipeline together
Tests    -> unit/smoke coverage
```

Rule: `utils` must not depend on `modules/Lambda`. Lambda may depend on utils.

`Config/Configure.hh` is driver-facing and intentionally not included by
`Config.hh`; it depends on Probe, Record, and Monitor umbrellas.

## Drivers

| File | Role |
| ---- | ---- |
| `_Lambda_Reconstruction.cc` | Probe pipeline over an existing ROOT file. Configures Probe, Writer, Logger; declares Lambda output; runs `Lambda::rootAnalysis`; finishes Writer. |
| `_Lambda_Parallel.cc` | Pythia8 parallel generation plus Lambda analysis. Uses Writer-owned histograms. |
| `_Lambda_Test.cc` | Single-thread Pythia smoke-style driver with a small sleep per event. |
| `_Lambda_Data.cc` | Pythia8 data generation. Declares Writer-owned explicit `Protons` and `Pions` trees and fills rows through Writer. |

## Tests

| File | Role |
| ---- | ---- |
| `tests/test_reconstructCandidates.cc` | Pure Lambda reconstruction unit tests. |
| `tests/test_probe_parallel.cc` | Probe collector/worker modes, queue behavior, and stats. |
| `tests/test_record_writer.cc` | RootUtil, RecordKey, branch buffers, Writer declaration validation, queue drain, and scribe exception propagation. |
| `tests/test_rootAnalysis_smoke.cc` | Probe + Lambda + Writer smoke test that inspects the final ROOT output after `writer.finish`. |
| `tests/fixtures/make_lambda_fixture.cc` | Builds the committed Lambda fixture ROOT file. |
| `tests/run_all.sh` | Runs test executables. |

## `utils/Config`

Purpose: parse TOML, load defaults/limits, and configure runtime objects.

Important files:

- `Config/Types.hh`: `Events`, `PythiaConfig`, `ProbeConfig`, `Watch`, and
  transitional `Register`.
- `Config/Reader.hh`: parses `[events]`, `[record]`, `[record.paths]`,
  `[record.file]`, `[pythia]`, and `[probe]`.
- `Config/Defaults.hh`: loads optional monitor defaults and required
  Lambda limits.
- `Config/Configure.hh`: driver facade overloads:
  - `Config::configure(..., Probe::ProbeParallel&, Writer&, AsyncLogger&)`
  - `Config::configure(..., PythiaT&, Writer&, AsyncLogger&)`

Current thread caveat: `[events].nThreads` is still the only parsed thread key.
The intended next direction is per-section thread config.

## `utils/Probe`

Purpose: read ROOT input data into `Probe::Event` and invoke callbacks.

Important files:

- `Probe/Types.hh`: branch specs, collection specs, stream/callback modes,
  event key/event containers, `QueuedEvent`, and
  `BranchType = RootUtil::DataType`.
- `Probe/BranchControl.hh`: ROOT branch helpers, type checks, partitioning,
  index scanning, and `enableRootThreadSafety`.
- `Probe/ConfigAid.hh`: parses `[probe].event_particles` into
  `Probe::ParticleSpec` (alias `CollectionSpec`).
- `Probe/Event.hh`: `EventStream` wrapper for flat indexed trees and vector
  event trees. Per-thread; opens its own `TFile`.
- `Probe/FlatReader.hh`: per-collection reader for indexed flat trees.
- `Probe/VecReader.hh`: per-collection reader for vector-branch event
  trees. v1 supports float kinematics.
- `Probe/Parallel.hh`: `Probe::ProbeParallel` class and a compatibility
  `runParallel<Cb>(...)` free function that internally constructs a
  `ProbeParallel` in `WorkerThread` mode.
- `Probe/EventCount.hh`: reads `About/events/n_events_total` from ROOT input.

`Probe::ProbeParallel`:

- defaults to `CallbackMode::CollectorThread`;
- in CollectorThread mode, workers parallelize event reading but the Lambda
  callback is invoked serially by the collector;
- supports `WorkerThread` for compatibility/direct callbacks;
- owns input file, particle specs, stream type, event count/range, partitions,
  entry bounds, queue capacity, callback mode, and stats;
- assumes indexed branches are ascending, dense, and grouped;
- queues built events to the collector in CollectorThread mode.

Note: `utils/Probe.hh` still mentions a `ProbeParallel.hh` subfile, but the
class currently lives in `Probe/Parallel.hh`.

## `utils/Record`

Purpose: own output ROOT records, request queues, metadata, checkpoints, final
write, and fatal write.

Important files:

- `Record/Types.hh`: `RecordKey`, branch buffers, Writer-owned record structs,
  and temporary legacy `RootObjects` / `RootArray` compatibility types.
- `Record/Requests.hh`: queue payloads, barrier state, queue lanes, and
  `ParticleFillView`.
- `Record/Writer.hh`: main Writer class. Owns `TFile`, record registries,
  queues, scribe thread, lifecycle APIs, and request application.
- `Record/Finalizer.hh`: inline `Writer::bind`, `finish`, and fatal shutdown
  bodies.
- `Record/Meta.hh`: provenance metadata and `About/` ROOT writing.
- `Record/Configs.hh`: `Paths` and `HistConfig`.
- `Record/Histogram.hh`: legacy fill/write helpers retained during migration.

Writer public lifecycle:

```cpp
writer.open(paths, histConfig, meta);
// declarations only
writer.start();
// concurrent producers enqueue fills
writer.checkpoint(eventIndex);
writer.finish(eventCount);
writer.fatalWrite(eventCount, timeout);
```

Writer is single-scribe today. The grand queue (default capacity 1024) is
bounded; producers block on `queueNotFull_` when full. Per-lane payload
queues exist for Particle, Hist1D, Hist2D, Graph, Profile, Tree,
Checkpoint, Finish, FatalWrite, and Stop tickets. `writer.stats()` reports
queue capacity, current backlog, produced/consumed request counts, and
max observed backlog.

Declaration APIs (must run before `start()`):

- particle group: `declareParticleGroup`, `declareParticleCount`,
  `declareParticleHist1D`, `declareParticleHist2D`,
  `declareParticleGraph`, `declareParticleProfile`,
  `declareParticleTree`.
- independent: `declareHist1D`, `declareHist2D`, `declareGraph`,
  `declareProfile`, `declareTree<TreeBasis, BranchBasis>`.

Fill APIs (after `start()`):

- `fillParticleEvent<Basis>({ {basis, particles}, ... })` — one call
  per logical event; the scribe applies all groups in one ticket.
- `fillHist1D`, `fillHist2D`, `fillGraph`, `fillProfile`, `fillTree`
  for independent objects.

Lifecycle: `checkpoint(eventIndex)` is a barrier ticket; the scribe
applies every queued fill before the checkpoint write. `finish(eventCount)`
flips `accepting_` to false, drains the queue, writes metadata, closes
the file, joins. `fatalWrite(eventCount, timeout)` bypasses normal queue
capacity and wakes blocked producers.

## `utils/Monitor`

Purpose: asynchronous terminal and log reporting.

Important files:

- `Monitor/Logger.hh`: `AsyncLogger`, private `Config::Watch`, heartbeat
  thread, snapshots, fatal-stall callback, thread stats.
- `Monitor/ConfigAid.hh`: reads monitor pacing from `[monitor]`, `[log]`, or
  `[logging]`.
- `Monitor/Render.hh`: terminal and log rendering.
- `Monitor/Snapshot.hh`: snapshot formatting helpers.
- `Monitor/Timer.hh`: currently a single `BlockTimer` (global namespace,
  not `Monitor::`) that opens `output/timer.log` per construction and
  writes a duration on destruction. Used only in
  `modules/Lambda.hh::rootAnalysis`. The per-event file open is
  problematic under multi-threaded callbacks; see [REVIEW §3](REVIEW.md)
  for the proposed `Monitor::Timer` family that replaces it.

Fatal-stall handling currently routes through `Writer::bind`, which registers a
logger callback that calls `writer.fatalWrite`.

## `modules/Lambda`

Purpose: Lambda baryon domain logic, output declarations, and callbacks.

Important files:

- `Lambda/Types.hh`: `HistogramSet`, `DataTree`, `DataBranch`, `Candidates`,
  and `Parameters`.
- `Lambda/Loaders.hh`: reads `[lambda]` and `[lambda.analysis].writeTree`.
- `Lambda/Declare.hh`: declares Writer-owned particle groups/histograms/trees
  and raw data trees.
- `Lambda/Reconstruction.hh`: harvests Pythia particles and reconstructs
  Lambda candidates.
- `Lambda/Recording.hh`: adapts `Candidates` to `writer.fillParticleEvent`.
- `Lambda/Context.hh`: lightweight contexts containing parameters/watch/logger
  and Writer references only.
- `Lambda.hh`: orchestrator and callback implementations. Provides
  `Lambda::configure(parameters, writer, configPath)` (calls
  `extractPhysics` then `declareObjects` so drivers replace four
  setup lines with two). `rootAnalysis`, `pythiaAnalysis`, and
  `dataGenerator` are the three event callbacks.

Current performance attention is on `reconstructCandidates`, candidate vector
materialization, and the Writer enqueue/fill boundary; see
[Issues.md](Issues.md).

## Configs

Primary configs:

- `configs/Lambda_Reconstruction.toml`: Probe reconstruction from stored ROOT.
- `configs/Lambda_Generation.toml`: Pythia generation and data driver input.
- `configs/Lambda_Limits.toml`: Lambda histogram/selection bounds.
- `configs/defaults/Limits.toml`: optional global limits fallback if present.
- `configs/defaults/Monitor.toml`: optional histogram default fallback if
  present.

Known config caveats:

- `[events].nThreads` is still global-ish and should split into
  `[probe].nThreads`, `[probe].callback_mode`, `[pythia].nThreads`, and
  `[record].writer_threads`.
- `[probe.index]` is present in reconstruction TOML but not currently parsed.
- Writer-owned raw data trees use `event_index`; the current reconstruction
  config names `Index`. Keep the config aligned with the actual input ROOT file.
- several `[record].save_*` booleans are present but not wired.

## Threading at a glance

- Probe can spawn N worker threads and, in CollectorThread mode, one
  collector. The default callback mode is `CollectorThread`, which means
  Lambda analysis is invoked serially even when N>1. `WorkerThread`
  parallelises the Lambda callback and is now safe (Writer queues output
  mutation), but is not yet wired to TOML; see
  [REVIEW §1.1](REVIEW.md).
- Pythia8 parallel drivers spawn Pythia workers controlled by Pythia
  settings. `_Lambda_Data.cc` propagates `[events].nThreads` to Pythia;
  `_Lambda_Parallel.cc` currently does not.
- Writer always spawns exactly one scribe thread today. Multi-lane
  Writer is REVIEW §2.1.
- AsyncLogger spawns one monitor heartbeat thread.

Do not interpret low Probe CPU as a Probe failure by itself. It can mean
Probe is producing fine and Lambda analysis (Suspect rank 0–3 in
[Issues.md](Issues.md)) is the bottleneck, or that Writer queue space is
saturated.

Inter-thread synchronization points to be aware of:

- `AsyncLogger::publish` and `publishThreadStats` lock a single
  `mutex_`; both are called twice per event. Real contention candidate
  under WorkerThread mode (Issues §1 suspect 2).
- `Writer::pushNormal` blocks producers on `queueNotFull_` when the
  bounded grand queue is full. Default capacity 1024; back-pressure
  shows up as elevated wall time in `fillParticleEvent`.
- `Probe::ProbeParallel::queueMutex_` (CollectorThread mode only) is
  held briefly per push/pop. Each `QueuedEvent` carries a moved
  `Probe::Event`.
- ROOT's global thread-safety mutex (set once via
  `ROOT::EnableThreadSafety()`) wraps `TBranch::GetEntry` and other ROOT
  ops. Disabling it is not on the table.
