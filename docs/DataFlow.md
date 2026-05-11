# DataFlow — post Probe/Writer overhaul

Updated: 2026-05-10.

This document tracks the current TOML and runtime data flow after the
Probe/Writer overhaul. It focuses on keys that affect event count, threading,
output ownership, and the current performance-scaling investigation.

Companion docs: [CGPTsummary.md](CGPTsummary.md) (overhaul context),
[MAP.md](MAP.md) (file map), [REVIEW.md](REVIEW.md) (expansions /
improvements backlog), [Issues.md](Issues.md) (active scaling
investigation).

## High-level runtime flow

```text
TOML config
  -> Config::configure(...)
      -> Monitor::configureMonitor(...)
      -> Config::configureProbe(...) or Config::configurePythia(...)
      -> Record::configureWriter(...)
  -> Lambda::configure(...) or Lambda::declareDataObjects(...)
  -> writer.start()
  -> Probe/Pythia event loop
      -> Lambda callback
      -> writer.fillParticleEvent(...) or writer.fillTree(...)
      -> Writer queue
      -> Writer scribe mutates ROOT objects
  -> metadata updates
  -> writer.finish(eventCount)
```

The important post-overhaul boundary is that Lambda never owns or mutates output
ROOT objects on the active path. Lambda owns analysis data and submits requests;
Writer owns ROOT output.

## Startup parse chain

The same main TOML is still parsed more than once. Current important passes:

| Step | Caller | Consumes | Notes |
| ---- | ------ | -------- | ----- |
| 1 | `Monitor::configureMonitor` | `[monitor]`, `[log]`, `[logging]` | Configures heartbeat/pacing. Currently called before `[events]` is parsed, so verify derived bar interval. |
| 2 | `Config::configuration` | `[events]`, `[record]`, `[record.paths]`, `[record.file]`, monitor hist overrides | Also loads monitor defaults and limits via `limitExtractor`. |
| 3 | `Config::configureProbe` or `configurePythia` | `[probe]` or `[pythia]` | Pipeline-specific parse. |
| 4 | Probe facade only | ROOT input metadata / index scan | If event count was not explicit, Probe resolves actual event count and `Config::Configure.hh` rereads paths/file so names include the resolved count. |
| 5 | `Record::configureWriter` | TOML metadata plus optional Probe input metadata | Opens output file and stores `Paths`, `HistConfig`, and `Meta::Record` in Writer. |
| 6 | `Lambda::extractPhysics` | `[lambda]`, `[lambda.analysis]`, limits TOML | Declares output into Writer after this. |

Side-loaded files:

- `configs/defaults/Monitor.toml`: optional; used for default `binCount` and
  `histScale`.
- `configs/defaults/Limits.toml`: optional; generic property bounds.
- resolved `[lambda].hist_limits`: required; read by Config for generic bounds
  and read again by Lambda for per-set bounds.
- Pythia `.cmnd` file: read by Pythia, not TOML-parsed by Config.

## `[events]`

### `events.event_count`

Current consumers:

- parsed into `Config::Events::eventCount`;
- mirrored into `Config::Watch::nEvents`;
- for Probe, explicit presence sets `userEvents = true` and prevents metadata
  fallback scan;
- used by Pythia drivers as the loop count;
- used by output file naming and metadata scaling;
- passed to `writer.finish(eventCount)` for histogram scaling.

Probe behavior:

- if explicit, use that count;
- if absent, resolve from input ROOT `About/events/n_events_total`;
- if metadata is absent, scan input event keys or vector entries.

### `events.nThreads`

Current state:

- parsed into `Config::Events::nThreads`;
- mirrored into `Config::Watch::n_threads`;
- Probe facade passes it to `Probe::ProbeParallel::configureProbe`;
- `_Lambda_Data.cc` manually applies it to Pythia parallelism;
- `_Lambda_Parallel.cc` currently does not explicitly apply it to Pythia
  parallelism;
- Writer does not consume it.

Target direction:

- keep as temporary compatibility fallback;
- move Probe threads to `[probe].nThreads`;
- move Probe callback mode to `[probe].callback_mode`;
- move Pythia threads to `[pythia].nThreads`;
- move Writer lanes to `[record].writer_threads`.

## `[probe]`

### `probe.input_file`

Consumed by:

- `Probe::ProbeParallel` as the ROOT input path;
- Probe event-count metadata read or fallback scan;
- per-worker `EventStream` construction;
- reconstruction metadata, where the input file becomes a parent file.

### `probe.event_particles`

Parsed by `Probe::parseCollectionsFromToml` into `Probe::CollectionSpec`.

Shape:

```toml
event_particles = [
  ["protons", 0, "Protons",
   [["pX","D"],["pY","D"],["pZ","D"],["Energy","D"]],
   [["event_index","I"]]]
]
```

Fields:

- label used by Lambda, for example `protons` or `pions`;
- coordinate spec id: `0 = Cartesian`, `1 = PtEtaPhiE`, `2 = PtEtaPhiM`;
- ROOT tree name;
- four momentum branch name/type pairs;
- zero or more index branch name/type pairs.

Branch type letters are bridged through `RootUtil::DataType`.

Branch-name caveat:

- Writer-owned data generation declares `event_index`.
- `tests/fixtures/lambda_fixture.toml` also reads `event_index`.
- `configs/Lambda_Reconstruction.toml` currently reads `Index`.
- Probe uses the branch name from the config literally, so this must match the
  actual input ROOT file.

### `probe.index`

Current config contains keys such as:

```toml
[probe.index]
sorted = [true, true]
ascending = [true, true]
monotonic = [true, true]
```

Current code does not parse this section. `Probe::ProbeParallel` currently
builds index specs as ascending, dense, and grouped. Treat `[probe.index]` as
reserved until it is wired or removed.

### Proposed `probe.callback_mode`

Not implemented yet. Current default is `CollectorThread`, where Probe workers
read events and one collector thread invokes the Lambda callback. That means
`nThreads` parallelizes input reading, not Lambda reconstruction. Now that
Writer output mutation is queued, `WorkerThread` mode should be benchmarked for
reconstruction.

## `[pythia]`

### `pythia.beam_energy`

If present, `Config::configurePythia` sends `Beams:eCM = ...` to Pythia and
stores the value for output naming/logging/metadata. If absent, the facade
falls back to `pythia.settings.parm("Beams:eCM")` after reading the `.cmnd`
file.

### `pythia.cmnd_file`

If present, `Config::configurePythia` calls `pythia.readFile(cmnd_file)`.

### `pythia.seed`

If nonzero, `Config::configurePythia` sends `Random:seed = ...` to Pythia.

### Proposed `pythia.nThreads`

Not implemented yet. Should become the Pythia-specific replacement for the
current shared `[events].nThreads` fallback.

## `[record]`

### Active keys

| Key | Current consumer |
| --- | ---------------- |
| `serial` | copied into `Record::Paths::serial`; used in file/log names and logs. |
| `sr_padding` | local padding width during path composition. |
| `bin_count` | copied into `Record::HistConfig::binCount`; Lambda declarations use it for histograms. |
| `hist_scaling` | copied into `Record::HistConfig::histScale`; Writer uses it during checkpoint/final histogram scaling. |

### Present but not wired

These keys appear in current configs but are not read by current code:

- `save_checkpoints`
- `save_log_threads`
- `save_heartbeat`
- `save_final_log`

Either implement them or mark them as reserved config.

### Proposed Writer keys

Not implemented yet:

```toml
[record]
writer_threads = 1
writer_queue_capacity = 1024
```

`writer_threads` should default to 1 until multi-lane Writer ownership is
designed. `writer_queue_capacity` can be useful even before parallel Writer
lanes, because it controls producer backpressure.

## `[record.paths]`

Parsed by `Config::readPathsAndFile` and copied through `Config::Register` into
`Record::Paths`.

| Key | Effect |
| --- | ------ |
| `directory` | base output directory. |
| `output_log_directory` | base log directory or subdirectory. |
| `checkpoint_directory` | checkpoint output directory or subdirectory. |
| `serialDirectory` | if true, serial subdirectory is appended to output base. |
| `logInSubDir` | if true, log directory is under output directory. |
| `checkpointsInSubDir` | if true, checkpoint directory is under output directory. |

These produce:

- `paths.outName`
- `paths.logName`
- `paths.runStatName`
- `paths.threadStatDirectory`
- `paths.checkpointOutName`
- `paths.checkpointLogName`

## `[record.file]`

Controls composed file/log title:

| Key | Effect |
| --- | ------ |
| `prefix` | base file title. |
| `serial` | append padded serial. |
| `energy` | append beam energy. |
| `events` | append event count string. |

The same `energy` and `events` toggles also influence the thread-stat directory
name. If that is surprising, split thread-stat naming into its own keys later.

## `[record.metadata]` and top-level `[metadata]`

Both are read by `Record::Meta::mergeFromToml`; nested `[record.metadata]` is
applied after top-level `[metadata]` and therefore wins on duplicate fields.

Recognized fields:

- `dataset_name`
- `data_type`
- `run_period`
- `campaign`
- `experiment`
- `notes`
- `known_issues`
- `contact`
- `generator`
- `tune`
- `pdf_set`

For reconstruction from a Probe input file, `Record::Meta::mergeFromProbe` can
then overwrite compatible dataset/physics fields from the input file's
`About/` directory.

## `[monitor]`, `[log]`, `[logging]`

All three section names are accepted; `[monitor]` wins if present.

Active keys:

- `true_time_at_config`
- `print_interval`
- `check_interval`
- `heartbeat_interval`
- `terminal_refresh_interval`
- `program_stall_threshold`
- compatibility histogram keys: `bin_count`, `hist_scaling`

`check_interval` controls when Lambda/Pythia analysis requests
`writer.checkpoint(eventIndex)`.

## `[lambda]`

### Active keys

| Key | Consumer |
| --- | -------- |
| `hist_limits` | resolved to limits TOML path and stored in `Record::HistConfig`. |
| `delta_mass_gev` | `Lambda::Parameters::massTolerance`. |
| `delta_theta_rad` | `thetaTolerance`; `cosThetaTolerance` is derived with `std::cos`. |
| `reserved_protons` | target selected-candidate count baseline. |
| `proton_label` | optional Probe event label override; default `protons`. |
| `pion_label` | optional Probe event label override; default `pions`. |

### `[lambda.analysis].writeTree`

Optional array of histogram-set names that get particle candidate TTrees:

```toml
[lambda.analysis]
writeTree = ["Selected"]
```

Recognized names are the `HistogramSet` tags in `Lambda/TypeAid.hh`.

## Runtime request flow

### Reconstruction (Probe pipeline)

1. Probe worker builds `Probe::Event` (per-thread `EventStream` opens its
   own `TFile`).
2. In `CallbackMode::CollectorThread` (default), the worker pushes a
   `QueuedEvent` into `Probe::ProbeParallel::queue_` (bounded; default
   capacity `10 × threadCount`); a single collector thread pops and
   invokes `Lambda::rootAnalysis`. In `CallbackMode::WorkerThread`, the
   worker invokes the callback directly.
3. Lambda fetches proton/pion vectors by label from `Probe::Event`
   (currently copies them — see Issues §1 for the `const auto&` fix).
4. Lambda runs `reconstructCandidates` (CPU-bound; mass + theta cuts).
5. Lambda calls `writer.fillParticleEvent<HistogramSet>({...})`.
6. Writer copies candidate vectors into a `ParticleRequest` payload,
   pushes the payload into the `Particle` lane, pushes a
   `QueueLane::Particle` ticket onto the grand queue, signals the
   scribe.
7. Writer's single scribe thread pops the next ticket, pops the matching
   payload off the lane, calls `applyParticleRequest` which fills
   declared particle hists / counts / graphs / profiles / trees on the
   scribe.
8. `_Lambda_Reconstruction.cc` does **not** currently call
   `writer.checkpoint(eventIndex)` on a periodic interval; the Pythia
   driver does. Either checkpoint policy should move into Writer
   (REVIEW §2.6) or the Probe driver should mirror the Pythia path.

The performance boundary is between steps 3–5 (Lambda reconstruction +
enqueue), step 6 (queue back-pressure), and step 7 (scribe throughput).
[Issues.md](Issues.md) §1 ranks suspects.

### Pythia analysis

1. Pythia worker generates an event.
2. Lambda harvests final-state protons and pions
   (`Lambda::harvestParticles`).
3. Lambda runs `reconstructCandidates`.
4. Lambda calls `writer.fillParticleEvent<HistogramSet>` (same as the
   Probe pipeline from step 5 onward).
5. On `eventIndex % asyncLogger.checkInterval() == 0`, the driver calls
   `writer.checkpoint(eventIndex)`. The scribe applies any earlier
   queued fills before writing the checkpoint file (barrier
   semantics).

### Data generation

1. Pythia worker generates an event.
2. Lambda harvests final-state protons and pions.
3. For each particle, Lambda calls
   `writer.fillTree<DataTree, DataBranch>(DataTree::Protons | Pions, {...})`
   with `event_index`, `Energy`, `pX`, `pY`, `pZ`. One ticket per
   particle (see REVIEW §2.3 for batching).
4. Writer scribe fills explicit trees on the scribe thread.
5. At `finish()`, Writer's `writeIndependentObjectsToDir` builds a
   `BuildIndex("event_index")` for any explicit tree that has that
   branch.

### Writer queue lane / scribe path

Producer side (any non-scribe thread):

```text
fill*Event(...)
  -> push payload into per-lane deque (Particle | Hist1D | Hist2D |
                                       Graph | Profile | Tree |
                                       Checkpoint | Finish | FatalWrite)
  -> push QueueTicket{lane} onto grandQueue_
  -> ++produced_
  -> notify scribe (queueNotEmpty_)
  -> if grandQueue_.size() == queueCapacity_, BLOCK on queueNotFull_
```

Scribe side (single thread):

```text
wait queueNotEmpty_ until grandQueue_ is non-empty
pop ticket from grandQueue_; pop payload from matching lane
release queueMutex_; notify queueNotFull_
apply{Particle,Hist1D,Hist2D,Graph,Profile,Tree}Request(...)
  | Checkpoint:  writeCheckpointFile + completeBarrier
  | Finish:      writeAllToCurrentFile + completeBarrier + exit loop
  | FatalWrite:  writeAllToCurrentFile (best-effort) + completeBarrier
```

Exception path: any exception inside an apply/write call is captured in
`scribeException_`; pending barriers are completed with the exception
attached; `accepting_` flips to false; future producer pushes throw the
captured exception.

### Timer / instrumentation flow (proposed)

The current `BlockTimer` in
[utils/Monitor/Timer.hh](../utils/Monitor/Timer.hh) opens a file on
construction. The proposed `Monitor::Timer` family ([REVIEW §3](REVIEW.md))
reroutes timing data through a thread-local registry with a CSV dump on
shutdown. No file I/O on the hot path. When that lands, the runtime
flow gains:

```text
ScopeTimer t{"label"}              // RAII; reads CLOCK_THREAD_CPUTIME_ID
... block ...
~ScopeTimer                        // adds ns to thread-local TimerStats
                                   // by label
TimerRegistry::dump(path)          // called from writer.preCloseHook
  -> merges thread-local maps
  -> emits CSV: label, hits, wallNs, cpuNs, minWallNs, maxWallNs
```

The registry has no compile-time dependency on Writer or Logger; the
choice of dump path is the only integration point.

## Threading data flow

Current:

- `[events].nThreads` -> `Config::Events::nThreads`
  -> `logger.watch().n_threads` (mirror)
  -> `Probe::ProbeParallel::threadCount_` (via
     `probe.configureProbe(..., requestedEvents, userRequestedEvents)`)
  -> `_Lambda_Data.cc`: also pushes `Parallelism:numThreads` to Pythia
  -> `_Lambda_Parallel.cc`: does **not** apply to Pythia (cleanup item).
- `tests/test_rootAnalysis_smoke.cc` reads it back via
  `probe.threadCount()` to assert the resolved thread count.
- Writer always uses one scribe thread (capacity-bounded grand queue
  serves multiple producer threads).
- Probe `CallbackMode` defaults to `CollectorThread` and is only
  changeable in code today (no TOML key wired).
- AsyncLogger has its own heartbeat thread (independent of the above).
- ROOT thread safety is enabled once globally; `TBranch::GetEntry` and
  related ROOT calls take a recursive global mutex underneath.

Target:

```toml
[probe]
nThreads      = 8
callback_mode = "WorkerThread"

[pythia]
nThreads = 8

[record]
writer_threads        = 1
writer_queue_capacity = 1024
```

Migration:

- `[events].nThreads` remains a fallback during transition.
- Probe prefers `[probe].nThreads`, then `[events].nThreads`, then auto.
- Probe callback mode comes from `[probe].callback_mode`; default
  `CollectorThread` for conservative behaviour, but reconstruction
  benchmarks should test `WorkerThread` (now safe — Writer queues output
  mutation).
- Pythia prefers `[pythia].nThreads`, then `[events].nThreads`, then
  Pythia default. `_Lambda_Parallel.cc` must apply the resolved count to
  `Pythia8::PythiaParallel`.
- Writer reads `[record].writer_threads` and
  `[record].writer_queue_capacity`. Writer threads default to 1 until
  multi-lane Writer (REVIEW §2.1) lands.
- Document that Probe / Pythia / Writer thread counts are independent
  and can sum beyond hardware cores; the user is responsible for
  oversubscription.
