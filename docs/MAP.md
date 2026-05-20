# Project Directory Map

Updated: 2026-05-15.

---

## Top Level

```
High-Energy/
├── _Lambda_Data.cc          entry: Pythia8 data generation (writes ROOT TTree)
├── _Lambda_Parallel.cc      entry: parallel Probe-based Lambda reconstruction
├── _Lambda_Reconstruction.cc entry: main reconstruction pipeline
├── _Lambda_Test.cc          entry: quick integration smoke test
├── _Paint.cc                entry: standalone ROOT histogram renderer
├── Time_Collect.cc          scratch: wall-time collection helper
├── Makefile
├── configs/                 TOML config files + defaults/
├── datasets/                input ROOT files (not tracked)
├── docs/                    design and reference documents
├── modules/                 domain logic (Lambda)
├── output/  outputs/  results/  dump/   generated output directories
├── tests/                   unit + integration tests
└── utils/                   reusable library (no domain logic)
```

---

## `utils/`

### Wrappers (include everything in their namespace)

| File | Aggregates |
|---|---|
| `Physics.hh` | Physics/{Types,TypeAid,Kinematics,Properties} |
| `Utility.hh` | Utility/{Number,RootTypes,Time} |
| `Config.hh` | Config/{Types,TypeAid,LimitAid,Defaults,Reader} |
| `Probe.hh` | Probe/{Types,BranchControl,ConfigAid,Readers,Parallel,ParallelIMT,Administration,Configuration,Methods,Directives} |
| `Record.hh` | Record/{Types,Requests,Configs,Meta,Writer} |
| `Monitor.hh` | Monitor/{Types,Logger,Methods,Render,Report,Administration,Directive,Configure,Timer} |
| `Paint.hh` | Paint/{Types,Style,Apply,Save} |

`Config/Configure.hh` is intentionally excluded from `Config.hh` (depends on Probe/Record/Monitor — circular). Drivers include it explicitly.

---

### `utils/Physics/`

| File | Summary |
|---|---|
| `Types.hh` | `Lorentz` 4-vector alias; `ParticleProperty`/`EventProperty` enums with trait tables (name, extractor) |
| `TypeAid.hh` | Enum↔string converters for `ParticleProperty`/`EventProperty` |
| `Kinematics.hh` | Kinematic calculators: invariant mass, rapidity, pT, η; thin wrappers over `ROOT::Math` |
| `Properties.hh` | `valueOf()` — dispatches a `Lorentz` vector to a `ParticleProperty` via trait table |

---

### `utils/Utility/`

| File | Summary |
|---|---|
| `RootTypes.hh` | `DataType` enum (Float/Double/Int32/…); `detectBranchType(TBranch*)` and `typeName()` introspectors |
| `Number.hh` | `numberFormat()` — comma-separated, right-padded integer formatter |
| `Time.hh` | Timestamp string, elapsed-time, ETA formatters; consumes `Config::uSeconds`/`Seconds` aliases |

---

### `utils/Config/`

| File | Summary |
|---|---|
| `Types.hh` | Core config types: `Bounds`, `RangeSize`, `Watch`, `Register`, `Events`, `ParticleLimits`, `EventLimits`; imports `Probe::CollectionSpec` |
| `TypeAid.hh` | `RangeSize`↔string; `Watch::recordEvent` inline |
| `LimitAid.hh` | `resolveLimitsPath()` — bare name → `configs/*.toml` path |
| `Defaults.hh` | `parseBoundsArray`, `limitExtractor` — TOML helpers for defaults |
| `Reader.hh` | `resolveThreadCount`, `readConfig` — full TOML parse into `Watch`/`Register`/`Events`; parses `event_particles` (both array and named-table formats) |
| `Configure.hh` | `configure<ProbePipeline>()`/`configure<PythiaPipeline>()` — single-call facade to configure Probe, Writer, and Monitor from a config path |

---

### `utils/Probe/`

| File | Summary |
|---|---|
| `Types.hh` | `CollectionSpec`, `Bounds`, `EventRange`, `EventStream`, `StreamType` (Events/Vectors) |
| `BranchControl.hh` | ROOT branch introspection; `KinBuf` (float/double branch binding); `probeFirstKey`, `scanFlatEventKeys`, `enableRootThreadSafety` |
| `ConfigAid.hh` | `parseBranchPair`, `parseCollectionSpec`, `readParticleSpecs` — TOML → `CollectionSpec` parsing |
| `Readers.hh` | `FlatReader` (event-keyed TTree reader) and `VecReader` (vector-branch reader) |
| `Parallel.hh` | `ProbeParallel` class — multi-threaded ROOT event reader (CollectorThread and WorkerThread modes) |
| `ParallelIMT.hh` | `ProbeIMT` class — ROOT IMT in-memory table reader |
| `Administration.hh` | `ProbeParallel`/`ProbeIMT` constructors, getters, `determineStreamType`, partition helpers |
| `Configuration.hh` | `ProbeParallel::configureProbe` and `ProbeIMT::configureProbe` implementations |
| `Methods.hh` | `ProbeParallel::run` and `ProbeIMT::run` — top-level reader loop bodies |
| `Directives.hh` | Worker-thread and collector-thread loop bodies for `ProbeParallel::run` |

---

### `utils/Record/`

| File | Summary |
|---|---|
| `Types.hh` | Record structs: `ParticleTH1`/`TH2`/`Graph`/`Profile`/`Tree` (master + clone vectors); `RecordKey` |
| `Type_Methods.hh` | `RecordKey` hash, equality, `keyString`; `keyOf`/`requireEnumBasis` helpers |
| `Requests.hh` | `ParticleRequest`, `Hist1DRequest`, `Hist2DRequest`, `GraphRequest`, `ProfileRequest`, `TreeRowRequest`; `FillRequest` variant |
| `Configs.hh` | `Paths` (output TStrings) and `HistConfig` (bin count, scale, limits maps) |
| `Meta.hh` | `Meta::Record` struct; `Writer::writeMeta` — saves run provenance to ROOT file |
| `Writer.hh` | `Record::Writer` class declaration; aggregates all implementation fragments below |
| `Declaration.hh` | `declareParticleGroup`, `declareTH1`/`TH2`/`Graph`/`Profile`/`Tree` method bodies |
| `Recording.hh` | `fillParticleEvent`, `fillTH1`/`TH2`/`Graph`/`Profile`/`Tree`, `scaleAndWrite` |
| `Directives.hh` | `pushFill`, worker loop, `applyParticleRequest` and per-type `applyXxxRequest` bodies |
| `Cloning.hh` | `allocateAllClones`, `mergeAllClones`, and per-type `cloneXxxImpl`/`mergeXxxImpl` helpers |
| `Administration.hh` | `open`, `start`, `finalize`, `checkpoint`, `cleanup` — Writer lifecycle; binds to `Monitor::AsyncLogger` |

---

### `utils/Monitor/`

| File | Summary |
|---|---|
| `Types.hh` | `PacingInfo` (print/bar/check intervals, heartbeat, stall threshold); `RunSnapshot`; `PendingActions` |
| `Logger.hh` | `AsyncLogger` class declaration — owns the heartbeat thread and log-message slot vector |
| `Methods.hh` | `updatedETA`, `formatProgress`, `statusLine` — pure string builders |
| `Render.hh` | `renderStatus`, `renderBar` — terminal progress rendering (ANSI, `ioctl` terminal width) |
| `Report.hh` | `writeRunStat` — writes run-stat JSON/text to file; `flushLog` |
| `Directive.hh` | `AsyncLogger` main-loop body, heartbeat dispatch, `mergePending` |
| `Administration.hh` | `AsyncLogger` constructor/destructor, `start`/`stop`, `bindWriter` |
| `Configure.hh` | `configureMonitor` — reads TOML pacing/stall keys into `AsyncLogger` |
| `ConfigAid.hh` | Compatibility shim → re-exports `Monitor/Configure.hh` |
| `Snapshot.hh` | Reserved (empty; `#pragma once` only) |
| `Timer.hh` | `BlockTimer` — RAII wall-clock scope timer; appends to `output/timer.log` |

---

### `utils/Paint/`

| File | Summary |
|---|---|
| `Types.hh` | `PlotType`, `PadConfig`, `CanvasConfig`, `HistogramEntry`, `PaintConfig` |
| `Style.hh` | `applyStyle` — ROOT style/color/marker/line setters |
| `Apply.hh` | `applyPad`, `applyCanvas`, `drawEntries` — applies config to ROOT canvas/pad |
| `Save.hh` | `savePlot` — renders and exports to PNG/PDF |
| `Book.hh` | TOML → `PaintConfig` parser; reads plot definitions |
| `Render.hh` | Low-level ROOT drawing helpers (TH1, TH2, TGraph overlays) |
| `Resolve.hh` | ROOT object retrieval from TFile/TDirectory by path and type |
| `Illustrator.hh` | `Illustrator` class — high-level driver: load book, resolve objects, render, save |

---

## `modules/`

### `modules/Lambda/`

| File | Summary |
|---|---|
| `Types.hh` | `Lorentz`, `Candidates` struct, `HistogramSet` enum, mass constants |
| `TypeAid.hh` | `kHistogramSetMap` attribute table (enum → label/display name) |
| `Parameters.hh` | `Parameters` struct — mass window, cut values; TOML loader |
| `Loaders.hh` | Pythia8 `.cmnd` script loader; Pythia event-loop helpers |
| `Context.hh` | `AnalysisContext` — bundles `Parameters`, `Watch`, `Writer` for callback use |
| `Declare.hh` | `declareHistograms()` — registers all Lambda histograms on `Record::Writer` |
| `Reconstruction.hh` | `reconstructCandidates()` — proton×pion combinatorics, mass-window cut |
| `Recording.hh` | `fillCandidates()` — fans out validated/unvalidated candidates into Writer fill requests |
