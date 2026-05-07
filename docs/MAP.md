# Codebase Map

> Pythia8 / ROOT Lambda baryon (Λ → p + π⁻) reconstruction simulation.
> Layered C++17 header-only design under `-I./utils -I./modules`.
>
> **Build status (post-Batch07):** ✓ green. All four drivers
> (`_Lambda_Reconstruction.exe`, `_Lambda_Parallel.exe`, `_Lambda_Data.exe`,
> `_Lambda_Test.exe`) and `tests/*.exe` build clean. `make test` passes
> T1–T5 and S1–S5.
>
> Open backlog: [REVIEW.md](REVIEW.md). Status + deferred observations:
> [ROADMAP.md](ROADMAP.md). Strategic plan-of-plans:
> [Architecture.md](Architecture.md). TOML key inventory:
> [DataFlow.md](DataFlow.md). Per-batch summary:
> [plans/COMPLETED.md](plans/COMPLETED.md). Migration designs and
> observations from the parallel Gemini agent live under [Gemini/](Gemini/).

---

## Size summary (utils + modules + drivers + tests, .hh/.cc only)

| Umbrella           | Lines | Notes                                                                          |
| ------------------ | ----: | ------------------------------------------------------------------------------ |
| Record             | 1 203 | Seven headers; `Writer.hh` central; `Finalizer.hh` is now the inline-bodies file for Writer methods |
| Probe              | 1 123 | Nine headers; new `ProbeParallel.hh` + `ConfigAid.hh` (parses `[probe]` directly into `CollectionSpec`) |
| Monitor            |   804 | Five headers; new `ConfigAid.hh` (`configureMonitor`); pacing fields private to `AsyncLogger` |
| Lambda  (modules/) |   692 | Eight sub-headers + umbrella; `Lambda::configure` wraps `extractPhysics`+`declareObjects` |
| Config             |   630 | Six headers; `Configure.hh` separated from umbrella to break circular include  |
| Paint              |   426 | Four headers (no project deps)                                                 |
| Physics            |   300 | Four headers + umbrella                                                        |
| Drivers (root)     |   205 | Four `_Lambda_*.cc`                                                            |
| Utility            |   133 | Two headers + umbrella                                                         |
| tests/             |   396 | Asserts + 2 tests + 1 fixture generator                                        |

Direct `wc -l` of header/source under each umbrella; comments and blanks
counted.

---

## Layering

```
Physics ── ROOT only
Utility ── consumes Config::TimePoint via include
Paint   ── pure ROOT + toml++ (no project deps)
Config  ── Physics
Probe   ── Physics, Config (via Probe/ConfigAid.hh — parses [probe] TOML directly)
Monitor ── Config, Utility (no Pythia8 in transitive set)
Record  ── Physics, Config, Probe, Monitor
Lambda  ── Physics, Config, Probe, Record, Monitor, Pythia8

Config/Configure.hh ── Config + Probe + Record + Monitor
                       (driver-only header; not pulled in by Config.hh
                       because it would form a Probe ↔ Config cycle)
```

Pythia8 enters the include graph only through
`modules/Lambda/Reconstruction.hh` (where `harvestParticles` directly takes
`const Pythia8::Pythia&`). `_Lambda_Data.cc` and `_Lambda_Parallel.cc`
also include Pythia8 directly because they construct
`Pythia8::PythiaParallel`. Anything that does not include `Lambda.hh` does
not pull Pythia8.

**Dependency-direction rule** (documented at top of `utils/Config.hh`):
`Config → Probe / Record / Monitor` is allowed; the reverse direction is
also permitted (those umbrellas read Config types). `utils → Lambda`
module is **not** permitted.

---

## Drivers (`/`)

| File                        | Lines | Status  | Role                                                                                        |
| --------------------------- | ----: | ------- | ------------------------------------------------------------------------------------------- |
| `_Lambda_Reconstruction.cc` |    49 | ✓ green | Probe pipeline: `Probe::ProbeParallel.run` → `Lambda::rootAnalysis` over a stored ROOT file |
| `_Lambda_Parallel.cc`       |    48 | ✓ green | Pythia pipeline: `PythiaParallel::run` → `Lambda::pythiaAnalysis`; generation + analysis    |
| `_Lambda_Test.cc`           |    50 | ✓ green | Single-thread Pythia smoke driver; 5 ms sleep per event                                     |
| `_Lambda_Data.cc`           |    58 | ✓ green | Pythia pipeline: `PythiaParallel::run` → `Lambda::dataGenerator`; writes raw proton/pion trees |

All four drivers share the same lifecycle:

```cpp
<Runner>             runner;     // Probe::ProbeParallel or Pythia[Parallel]
Record::Writer       writer;
Monitor::AsyncLogger logger;

Config::configure(configPath, project, runner, writer, logger);
Lambda::Parameters phys; Lambda::RootArray sets;
Lambda::configure(phys, sets, writer, configPath);   // (analysis drivers only)

writer.bind(logger, logger.watch(), [&]{ return Lambda::logString(phys); });
writer.installFatalStallHandler(sets);

logger.watch().start = std::chrono::system_clock::now();
logger.start(writer);
runner.run([&](...){ Lambda::<handler>(...); });

writer.shutdown(sets);
```

`_Lambda_Data.cc` substitutes `Lambda::declareDataObjects(dataObjects, writer)`
for the histogram-set declaration and uses `Lambda::GenerationContext`.

---

## `tests/`

| File                                        | Lines | Role                                                                                        |
| ------------------------------------------- | ----: | ------------------------------------------------------------------------------------------- |
| `tests/test_assert.hh`                      |    66 | `TEST_EQ`, `TEST_NE`, `TEST_TRUE`, `TEST_FALSE`, `TEST_NEAR`, `TEST_LT`, `TEST_PASS` macros |
| `tests/test_reconstructCandidates.cc`       |    90 | Unit test, 5 cases (T1–T5). Pure physics; no ROOT file, no Pythia event                    |
| `tests/test_rootAnalysis_smoke.cc`          |   119 | Integration test, 5 cases (S1–S5). Uses the same `Config::configure` facade as drivers     |
| `tests/fixtures/make_lambda_fixture.cc`     |   121 | Generator for `lambda_fixture.root` (50 events, 4p + 5pi each, one signal pair per event)  |
| `tests/fixtures/lambda_fixture.toml`        |     — | Self-contained config; uses the `[probe].event_particles` form                              |
| `tests/fixtures/lambda_fixture_limits.toml` |     — | Limits TOML pointed at by `lambda_fixture.toml`'s `[lambda].hist_limits`                    |
| `tests/fixtures/lambda_fixture.root`        |     — | Committed binary fixture; rebuild with `make_lambda_fixture.exe` if regen needed            |
| `tests/run_all.sh`                          |    36 | Drives every `test_*.exe`; exit 77 = skip (fixture missing), nonzero = fail                 |

`make test` builds the fixture generator and both test binaries, then
invokes `run_all.sh`. Last green run: T1–T5 and S1–S5 all pass.

---

## `utils/`

### `Config.hh` — TOML → in-memory config

Top of file documents the dependency-direction rule (`Config → Probe /
Record / Monitor` allowed; reverse direction also OK). Public entry
points:

- `configuration(path, project, events, watch, reg)` — base 5-arg.
- `configuration(path, project, watch, reg)` — drops `Events`.
- `extractConfiguration(path, project, watch, reg)` — back-compat alias.
- `configurePythia<PythiaT>(path, project, watch, reg, pythia)` — loads
  `[pythia]` and applies `cmnd_file` / `seed` / `Beams:eCM` directly.
- `configureProbe(path, project, watch, reg, probe)` — loads `[probe]`
  into a `Config::ProbeConfig` (whose `collections` field is now
  `vector<Probe::CollectionSpec>` directly — no `ProbeParticle`
  intermediate).

The driver-facing facade lives in `utils/Config/Configure.hh` (separate
from the umbrella):

- `Config::configure(path, project, Probe::ProbeParallel&, Writer&, AsyncLogger&)`
- `Config::configure(path, project, PythiaT&, Writer&, AsyncLogger&)`

Three-tier resolution still applies inside `configuration()`:
`loadMonitorDefaults` (`configs/defaults/Monitor.toml`) → `limitExtractor`
(`configs/defaults/Limits.toml` **optional** — silently skipped if absent
since Batch07; project limits TOML still required) → user TOML
(`readEventsSection`, `readRecordSection`, `readLogSection`,
`readPathsAndFile`).

| Subfile                | Lines | Contents                                                                                                                 |
| ---------------------- | ----: | ------------------------------------------------------------------------------------------------------------------------ |
| `Config/Types.hh`      |   126 | `Bounds`, `RangeSize`, `LevelBounds`, `ParticleLimits`/`EventLimits`. `Events` (with `userEvents` sentinel), `PythiaConfig`, **`ProbeConfig` (`vector<Probe::CollectionSpec> collections;`)**. `Watch` (lock-free atomic `iEvent`/`n_real_events`/`elapsed`). `Register` (now without serial; serial moved onto `Writer::paths()`). |
| `Config/TypeAid.hh`    |    54 | `levelToString`, `stringToLevel`. Lock-free `Watch::recordEvent(TimePoint)` (`fetch_add` + relaxed `store`); `Watch::freeze()` for atomic-safe snapshots. |
| `Config/LimitAid.hh`   |    15 | `resolveLimitsPath` — accepts bare name, `name.toml`, or full path with `/`. |
| `Config/Defaults.hh`   |   103 | `parseBoundsArray`, `loadLimitsFile`, `limitExtractor` (defaults pass now optional), `loadMonitorDefaults`. |
| `Config/Reader.hh`     |   160 | TOML section parsers: `readEventsSection` (sets `userEvents` from key presence), `readRecordSection`, `readLogSection`, `readPathsAndFile`, `readPythiaSection`. The `[probe]` parser was moved into `Probe/ConfigAid.hh::parseCollectionsFromToml` (Batch05). Plus `resolveThreadCount`, `sanitiseLoggingConfig`. |
| `Config/Configure.hh`  |    73 | **The driver-facing facade.** Two `Config::configure` overloads (Probe / PythiaT). Probe overload calls `probe.resolveEvents()` before `configureWriter` so the output filename embeds the resolved count. Pythia overload reads `Beams:eCM` from already-loaded settings as fallback. |

### `Physics.hh` — pure physics

Property enum is the canonical source for `Config::ParticleLimits` /
`Config::EventLimits` keys. **Deps:** none.

| Subfile                 | Lines | Contents                                                                                                                                          |
| ----------------------- | ----: | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Physics/Types.hh`      |   103 | `Lorentz` (= `ROOT::Math::PxPyPzEVector`), `Column`. `ParticleProperty` (12 values), `EventProperty` (1: `Multiplicity`). `kParticleTraits[12]`/`kEventTraits[1]` arrays, `traitsOf` overloads. |
| `Physics/TypeAid.hh`    |    47 | `particlePropertyToString`, `eventPropertyToString`, `stringToParticleProperty`, `stringToEventProperty`, `try*` variants.                       |
| `Physics/Properties.hh` |    29 | `particlePropertyName`, `eventPropertyName`, `valueOf` (×2), `multiplicityOf`.                                                                    |
| `Physics/Kinematics.hh` |   100 | `fromComponents`, `invariantMass` (×2), `deltaPhi`, `deltaR`, `cosOpening`. Column-vectorised variants.                                          |

### `Utility.hh` — domain-agnostic formatters

**Deps:** Config (`Time.hh` consumes `Config::TimePoint`).

| Subfile             | Lines | Contents                                                                              |
| ------------------- | ----: | ------------------------------------------------------------------------------------- |
| `Utility/Number.hh` |    54 | `numberFormat` (comma-grouped, padded), `numberString` (k / M / B / T / P / E suffix). |
| `Utility/Time.hh`   |    66 | `localTime`, `timeString` (×2), `durationString`.                                     |

### `Probe.hh` — ROOT file reader

**Deps:** Physics, Config.

| Subfile                  | Lines | Contents                                                                                                                                                                                     |
| ------------------------ | ----: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Probe/Types.hh`         |    92 | `Lorentz` re-export. `BranchType`, `MissingBranchPolicy`, `BranchSpec` (name + type + policy). Coord specs uniform — `CartesianSpec` / `PtEtaPhiESpec` / `PtEtaPhiMSpec` each hold one `vector<BranchSpec>`. `ParticleSpec` / `using CollectionSpec = ParticleSpec`. `AuxColumn`, `ScalarValue`, `EventKey`, `Event`. |
| `Probe/BranchControl.hh` |   218 | `namespace Probe::BranchControl`. Helpers: `Partition`, `enableRootThreadSafety`, `branchTypeStr`, `detectType` (×3), `requireBranch`/`requireType`, `KinBuf`, `coordNames`, `makeLorentz`, `partitionEvents`, `probeFirstKey`, `scanIndexBranch`. |
| `Probe/ConfigAid.hh`     |   101 | **`Probe::parseCollectionsFromToml(const toml::table&)`** (Batch05) — builds `vector<CollectionSpec>` directly from the `[probe]` table. Replaces the old `Config::ProbeParticle` → `Probe::CollectionSpec` conversion glue. |
| `Probe/ProbeParallel.hh` |    38 | **`class Probe::ProbeParallel`** (Batch03) — fields `inputFile`, `collections`, `nThreads`, `nEvents`; methods `resolveEvents()` (two-tier fallback) and `template<class Cb> void run(Cb&&)` wrapping `runParallel`. |
| `Probe/FlatReader.hh`    |   231 | `class FlatReader` — per-particle row tree + index branch.                                                                                                                                   |
| `Probe/VecReader.hh`     |   103 | `class VecReader` — per-event vector branches via `TTreeReaderArray<float>`.                                                                                                                  |
| `Probe/Event.hh`         |   144 | `class EventStream` — unified Flat/Vec iterator with dense key range or full scan; `nEventsHint` short-circuits the index-key scan. (`scalars` parameter dropped in Batch03.)                |
| `Probe/Parallel.hh`      |   127 | `runParallel<Callback>` — wrapped by `ProbeParallel::run`. `scalars` parameter removed in Batch03.                                                                                            |
| `Probe/EventCount.hh`    |    36 | `resolveEventCount(filepath)` — opens a ROOT file and reads `About/events/n_events_total`. Returns 0 on any failure.                                                                          |

### `Record.hh` — ROOT object writer (histograms + trees + metadata)

**Deps:** Physics, Config, Probe, Monitor.

| Subfile               | Lines | Contents                                                                                                                                                                                                                              |
| --------------------- | ----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Record/Types.hh`     |    67 | `NoBasis`, `TH1Record`, `TH2Record`, `TreeRecord` (now populated when `[lambda.analysis].writeTree` lists the set), `EventTH1Record`, `ExtractHist1D`, `ExtractHist2D`, `RootObjects<Basis>`, `RootArray<Basis>`.                       |
| `Record/Configs.hh`   |    47 | `HistConfig` (binCount, histScale, particle/event limits maps, `histLimitsFile`). `Paths` (output / log / checkpoint path templates, serial). |
| `Record/Extract.hh`   |   172 | `namespace Record::Extract`. `Event`/`Lorentz`/`Scalars`/`Fn` aliases. Primitives + combinators for event-level extractors.                                                                                                            |
| `Record/Meta.hh`      |   406 | `namespace Record::Meta`. `Dataset`/`Processing`/`EventSummary`/`Physics`/`Objects`/**`Integrity` (with `git_sha`, `git_dirty`, `host_uname`, `file_shas`)** /`Notes`/`Record` structs. `nowISO8601`, `processedBy`, `osArch`, `readFile`, **`sha256File`**, **`integrityAddFileSha`**, `mergeFromToml`, `mergeFromProbe`, `fillDerived`, `capture()`, `writeAbout()`. |
| `Record/Histogram.hh` |   167 | `declareTree<N>`, `count`/`countAll`/`resetCount`/`resetAllCounts`. `fill` overloads. `scaleAndWrite`/`scaleAndWriteToDir`, `write`/`writeToDir`/`writeAll`.                                                                          |
| `Record/Writer.hh`    |   184 | **`class Record::Writer`** — owns `TFile*`, `Paths`, `HistConfig`, `Meta::Record`, private `histMutex_`, and the bound `AsyncLogger` + callbacks. Exposes `bind`, `installFatalStallHandler`, `shutdown(sets)`, `checkpoint(sets, idx)`, `recordingScope()`, `meta()`, `paths()`, `histConfig()`, `file()`. `Record::configureWriter(...)` factory. |
| `Record/Finalizer.hh` |   131 | Inline bodies for `Writer::bind`, `installFatalStallHandler`, `shutdown`, `checkpoint`, private `fatalShutdown`. Split out of `Writer.hh` to break the `Monitor::Logger` ↔ `Writer` include cycle. **`FinalizerController` no longer exists as a class** (Batch02). |

### `Monitor.hh` — async terminal I/O

**Deps:** Config, Utility. **No Pythia8 in transitive set.**

| Subfile               | Lines | Contents                                                                                                                                                                                                                                                                                                                            |
| --------------------- | ----: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Monitor/Types.hh`    |    71 | `FatalStallMultiplier`. `RenderStatus`/`RenderBar`/`WriteRunStat` constexpr flags + `Dont*` negatives. `NoEvents`, `CallbackCompleted`/`NoCallbackCompleted`. `RunPhase`, `ThreadPhase` enums. `RunSnapshot`, `PendingActions`, `ThreadSnapshot`, `PacingInfo`.                                                                       |
| `Monitor/Snapshot.hh` |   106 | `phaseString`, `threadPhaseString`, `statusString`, `makeSnapshot`, `runStatString`, `threadStatString`, `updatedETA`.                                                                                                                                                                                                              |
| `Monitor/Render.hh`   |   176 | Terminal control — `disable_input_echo`, `restore_terminal`, `terminalMutex`, `writeTextFile`, `renderProgressBar`. `buildLogText`, `outputLog`, `terminalReport`. `buildEmergencyLogText`, `writeEmergencyLog`.                                                                                                                    |
| `Monitor/Logger.hh`   |   361 | `class AsyncLogger` — background heartbeat thread. **Owns a private `Config::Watch watch_`** (Batch03) plus pacing-interval fields populated by `configureMonitor`. `start(writer)`, `publish`, `publishThreadStats`, `finish`, `setFatalStallHandler`, `stop`, `watch()`, `checkInterval()`, `printInterval()`, `pacingInfo()`.   |
| `Monitor/ConfigAid.hh`|    65 | **`Monitor::configureMonitor(AsyncLogger&, configPath, project)`** (Batch03) — loads pacing/interval values from `[monitor]` / `[log]` TOML directly into the logger's private fields.                                                                                                                                              |

### `Paint.hh` — ROOT histogram styling and export

**Deps:** none (pure ROOT + toml++).

| Subfile          | Lines | Contents                                                                                                                                                                                            |
| ---------------- | ----: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Paint/Types.hh` |    69 | `LineSpec`, `FillSpec`, `MarkerSpec`, `AxisSpec`, `CanvasSpec`, `StatsSpec`, `LegendSpec`, `Style`, `PadLayout`.                                                                                    |
| `Paint/Style.hh` |    38 | `parseColor` (named-color + offset parser, e.g. `kRed+2`).                                                                                                                                          |
| `Paint/Apply.hh` |   205 | `loadStyle`, `applyGlobalStyle`, `applyStyle` (TH1 / TGraph), `makeCanvas`, `applyStats`.                                                                                                            |
| `Paint/Save.hh`  |    97 | `saveToFile`, `savePdf`, `savePng`, `saveSvg`, `saveComposite`.                                                                                                                                     |

---

## `modules/`

### `Lambda.hh` — orchestrator

**Deps:** Probe, Record, Monitor, Config, Physics, Pythia8.

| Subfile                    | Lines | Contents                                                                                                                                                                                                                                                                                                                                              |
| -------------------------- | ----: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Lambda.hh` (umbrella)     |   135 | `dataLogString`, **`configure(parameters, sets, writer, configPath)`** (Batch07 — wraps `extractPhysics + declareObjects`), `logString(Parameters&)`, three handlers: `pythiaAnalysis(pythia, ctx)`, `rootAnalysis(ev, threadId, ctx)` (no histMutex param — Writer owns it), `dataGenerator(pythia, ctx)`.                                            |
| `Lambda/Types.hh`          |    59 | Constants `kLambdaMass`/`kProtonMass`/`kPionMass`/`kMassDiff`. `ProtonPid`/`PionPid`. `HistogramSet` enum + `kHistogramSetCount = 3`. Aliases `Lorentz` (= `Physics::Lorentz`), `RootObjects`, `RootArray`. `Candidates`, `Parameters` (with `writeTree: vector<HistogramSet>`), `HistogramSetAttributes`, `DataObjects`. (`SpecsArray` deleted in Batch07.) |
| `Lambda/TypeAid.hh`        |    23 | `kHistogramSetMap`, `propertyAlias`.                                                                                                                                                                                                                                                                                                                  |
| `Lambda/Parameters.hh`     |    96 | Bounds resolution helpers: `Recorded_ParticleProperties`, `explicitBounds`, `levelBounds` (×2), `boundsFromNode<P>`, `resolveBounds<P>`. (`kTreeEnabledSets` deleted in Batch07.)                                                                                                                                                                       |
| `Lambda/Loaders.hh`        |    81 | `extractPhysics` — reads `[lambda]` keys plus `[lambda.analysis].writeTree`, then loads the per-set/per-property bounds.                                                                                                                                                                                                                              |
| `Lambda/Declare.hh`        |   117 | `declareDataObjects` (Protons/Pions trees for the Pipeline-A data driver). `declareObjects` — count + per-property histograms per set; calls `Record::declareTree(...)` for each set listed in `parameters.writeTree`.                                                                                                                                  |
| `Lambda/Reconstruction.hh` |    96 | `Particle` candidate struct, `cosTheta`, `harvestParticles`, `reconstructCandidates`. **Includes `Pythia8/Pythia.h` directly** — only file in the project that does.                                                                                                                                                                                  |
| `Lambda/Recording.hh`      |    45 | `findObjects`, `fill` (×2; tree fill is now real when `writeTree` opts the set in), `fillCandidates`.                                                                                                                                                                                                                                                |
| `Lambda/Context.hh`        |    40 | `AnalysisContext { RootArray&, const Parameters&, Config::Watch&, Monitor::AsyncLogger&, Record::Writer& }`. `GenerationContext { DataObjects&, std::mutex&, Config::Watch&, Monitor::AsyncLogger&, Record::Writer& }`.                                                                                                                                  |

---

## `configs/`

### Run configs

| File                         | Driver                                       | Sections                                                                                                                                  |
| ---------------------------- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `Lambda_Generation.toml`     | `_Lambda_Parallel.exe` / `_Lambda_Data.exe`  | `[events]` · `[pythia]` · `[record]` · `[record.paths]` · `[record.file]` · `[record.metadata]` · `[lambda]` · `[monitor]`                |
| `Lambda_Reconstruction.toml` | `_Lambda_Reconstruction.exe` / `_Lambda_Test.exe` | `[events]` · `[probe]` · **`[pythia]` (Batch07)** · `[record]` · `[record.paths]` · `[record.file]` · `[record.metadata]` · `[lambda]` |

The `[probe].event_particles` form:

```toml
event_particles = [
    ["protons", 0, "Protons", [["pX","D"],["pY","D"],["pZ","D"],["Energy","D"]], [["Index","I"]]],
    ["pions",   0, "Pions",   [["pX","D"],["pY","D"],["pZ","D"],["Energy","D"]], [["Index","I"]]]
]
```

Position 0 = label, 1 = `spec` (0 Cartesian / 1 PtEtaPhiE / 2 PtEtaPhiM), 2 =
ROOT tree name, 3 = momenta `[name, type-letter]` pairs (must be exactly 4),
4 = index `[name, type-letter]` pairs. Type letters follow ROOT TBranch
leaf-list convention (`F`/`D`/`I`/`i`/`L`/`l`/`O`).

### Limits

| File                            | Scope                                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `configs/Lambda_Limits.toml`    | Lambda-specific bounds; loaded via `[lambda].hist_limits` resolution. Required if referenced.          |
| `configs/defaults/Limits.toml`  | Universal fallback. **Optional since Batch07** — silently skipped if absent.                           |
| `configs/defaults/Monitor.toml` | Read by `loadMonitorDefaults`; silently skipped if missing.                                            |
| `configs/defaults/Paint.toml`   | Consumed by `Paint::loadStyle` callers (downstream tooling, not the drivers).                          |

### Pythia

| File                         | Purpose                                                                                                  |
| ---------------------------- | -------------------------------------------------------------------------------------------------------- |
| `Lambda_Reconstruction.cmnd` | Pythia8 settings for the pp → Λ generation pass. Loaded via `[pythia].cmnd_file` — no driver hardcodes.  |
| `NeNe.cmnd`                  | Pythia8 settings for NeNe collisions.                                                                    |

---

## Key dependency notes

- **Pythia8 enters only through `Lambda/Reconstruction.hh`.** Anything
  that stops short of `#include "Lambda.hh"` does not need to link
  Pythia8.
- **Threads.** `Monitor::AsyncLogger` spawns the heartbeat thread.
  `Pythia8::PythiaParallel::run` and `Probe::ProbeParallel::run` (which
  delegates to `Probe::runParallel`) spawn their own worker threads.
- **`Config::Watch` is the central per-run mutable state** — but slim
  since Batch06: `iEvent` and `n_real_events` atomic, `start`,
  `elapsed` atomic, `nEvents`/`n_threads` plain. `recordEvent(now)` is
  lock-free (`fetch_add` + relaxed `store`). Owned by
  `Monitor::AsyncLogger` (Batch03); accessed by handlers via
  `ctx.logging` (which is `asyncLogger.watch()`).
- **`Record::Writer` is the central per-run writer object.** Owns the
  open `TFile*`, all output-path templates, `HistConfig`, the
  `Meta::Record` provenance block, the histogram-fill mutex, and the
  bound `AsyncLogger` + callbacks. Drivers no longer construct
  `FinalizerController` — `writer.bind(...)` + `writer.shutdown(sets)`
  cover the lifecycle.
- **Pipeline A is the only read path.** `[probe].event_particles` →
  `Probe::parseCollectionsFromToml` → `Probe::ProbeParallel` →
  `Lambda::rootAnalysis` (which asks `Probe::Event` for collections by
  string label).
