# Codebase Map

> Pythia8 / ROOT Lambda baryon (Λ → p + π⁻) reconstruction simulation.
> Layered C++17 header-only design under `-I./utils -I./modules`.
>
> **Build status:** ✓ green. All four drivers and the test binaries compile clean.
> See `make _Lambda_Parallel.exe`, `make _Lambda_Reconstruction.exe`,
> `make _Lambda_Data.exe`, `make _Lambda_Test.exe`, `make test`.
>
> Open backlog: [REVIEW.md](REVIEW.md). Active phase: [ROADMAP.md](ROADMAP.md).

---

## Size summary (utils + modules + drivers + tests, .hh/.cc only)

| Umbrella           | Lines | Notes                                                  |
| ------------------ | ----: | ------------------------------------------------------ |
| Probe              |   983 | Seven headers; `EventCount.hh` added in Phase 2        |
| Record             |   791 | Five headers; `Finalizer.hh` is callback-based         |
| Lambda  (modules/) |   781 | Eight headers including new `Context.hh`               |
| Monitor            |   697 | Five headers; `Render.hh` no longer pulls Pythia8      |
| Config             |   633 | Five headers; `Watch::recordEvent` lives in `TypeAid`  |
| Paint              |   415 | Four headers (no project deps)                         |
| Physics            |   285 | Four headers; `Properties.hh` + `TypeAid.hh` re-split  |
| Utility            |   124 | Two headers (no project deps)                          |
| Drivers (root)     |   371 | Four `_Lambda_*.cc` + harness                          |
| tests/             |   413 | Asserts + 2 tests + 1 fixture generator                |

---

## Layering

```
Physics ── (no project deps; ROOT only)
Utility ── (no project deps; consumes Config::TimePoint via include)
Paint   ── (no project deps; pure ROOT + toml++)
Config  ── Physics
Probe   ── Physics, Config
Monitor ── Config, Utility               (* no Pythia8 in transitive set *)
Record  ── Physics, Config, Probe, Monitor
Lambda  ── Physics, Config, Probe, Record, Monitor, Pythia8
```

Notable: `Monitor/Render.hh` no longer includes `Pythia8/Pythia.h`. Pythia8 enters
the include graph only through `modules/Lambda/Reconstruction.hh` (where
`harvestParticles` directly uses `Pythia8::Pythia&`). Anything that does not
include `Lambda.hh` does not pull Pythia8.

---

## Drivers (`/`)

| File                             | Lines | Role                                                                                           |
| -------------------------------- | ----: | ---------------------------------------------------------------------------------------------- |
| `_Lambda_Parallel.cc`            |    56 | `PythiaParallel::run` + `Lambda::pythiaAnalysis` callback. Generation + analysis in one pass. |
| `_Lambda_Reconstruction.cc`      |    91 | `Probe::runParallel` over a stored ROOT file → `Lambda::rootAnalysis`. No Pythia instance.    |
| `_Lambda_Data.cc`                |    63 | `PythiaParallel::run` + `Lambda::dataGenerator` (writes flat per-particle trees).             |
| `_Lambda_Test.cc`                |    59 | Single-thread smoke driver; 5 ms sleep per event.                                              |
| `_Monitor_FatalStall_Harness.cc` |   102 | Standalone harness for `Monitor::AsyncLogger`'s fatal-stall watchdog. Not in `make` targets.   |

All four `_Lambda_*` drivers share the same lifecycle skeleton:
`disable_input_echo` → `extractConfiguration` → `openOutputFile` →
`extractPhysics` → `declareObjects` → `AsyncLogger.start` →
`FinalizerController + installFatalStallHandler` → driver-specific run loop →
`finalizer.normalShutdown`. `_Lambda_Data` deviates: it has no `FinalizerController`
and instead inlines `BuildIndex` + `outFile->Close` + `terminalReport` + `outputLog`
manually (`_Lambda_Data.cc:48–60`). See ROADMAP item 2.

---

## `tests/`

| File                                        | Lines | Role                                                                                                |
| ------------------------------------------- | ----: | --------------------------------------------------------------------------------------------------- |
| `tests/test_assert.hh`                      |    66 | `TEST_EQ`, `TEST_NE`, `TEST_TRUE`, `TEST_FALSE`, `TEST_NEAR`, `TEST_LT`, `TEST_PASS` macros.       |
| `tests/test_reconstructCandidates.cc`       |    90 | Unit test, 5 cases (T1–T5). Pure physics; no ROOT file, no Pythia event.                            |
| `tests/test_rootAnalysis_smoke.cc`          |   136 | Integration test, 5 cases (S1–S5). Runs `Probe::runParallel` over `lambda_fixture.root`.            |
| `tests/fixtures/make_lambda_fixture.cc`     |   121 | Generator for `lambda_fixture.root` (50 events, 4p + 5pi each, one signal pair per event).         |
| `tests/fixtures/lambda_fixture.toml`        |     — | Self-contained config for the smoke test (sections `[input]`, `[lambda]`, `[record]`, `[events]`). |
| `tests/fixtures/lambda_fixture_limits.toml` |     — | Limits TOML pointed at by `lambda_fixture.toml`'s `[lambda].hist_limits`.                           |
| `tests/fixtures/lambda_fixture.root`        |     — | Committed binary fixture; rebuild with `make_lambda_fixture.exe` if regen needed.                   |
| `tests/run_all.sh`                          |    36 | Drives every `test_*.exe`; exit 77 = skip (fixture missing), nonzero = fail.                        |

`make test` builds the fixture generator and both test binaries, then invokes `run_all.sh`.

---

## `utils/`

### `Config.hh` — TOML → in-memory config

Entry points: `configuration` (×2 overloads), `configurePythia<T>`,
`configureProbe`, `openOutputFile`, `extractConfiguration`. Three-tier resolution:
defaults (`configs/defaults/*.toml`) → limits (`*_Limits.toml`) → user TOML
overrides. **Deps:** Physics.

| Subfile              | Lines | Contents                                                                                                                                                                                                                                                                                                                                                       |
| -------------------- | ----: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Config/Types.hh`    |   139 | `Bounds`, `RangeSize`, `LevelBounds`, `ParticleLimits`/`EventLimits` (keyed on `Physics::*Property`); time aliases `TimePoint`/`uSeconds`/`Seconds`; configs `Events`, `PythiaConfig`, `ProbeParticle`, `ProbeConfig`. **`Watch`** (atomic `iEvent` + `mutable std::mutex eventMutex_`; copy/move all deleted). **`Register`** (TFile* + paths + `inputPath`). |
|                      |       | **Aliases retained:** `using Log = Watch;` and `using Root = Register;` (lines 137–138). All consumers still type `Config::Log` / `Config::Root` — the alias removal is open.                                                                                                                                                                                  |
| `Config/TypeAid.hh`  |    63 | `levelToString`, `stringToLevel`. Out-of-line `Watch::recordEvent(TimePoint)` (locks `eventMutex_`, increments `nRealEvents`, updates `elapsed`) and `Watch::freeze()` returning `std::unique_ptr<Watch>` for atomic-safe snapshots.                                                                                                                          |
| `Config/LimitAid.hh` |    15 | `resolveLimitsPath` — accepts bare name, `name.toml`, or full path with `/`.                                                                                                                                                                                                                                                                                  |
| `Config/Defaults.hh` |   101 | `parseBoundsArray`, `loadLimitsFile`, `limitExtractor` (loads `configs/General_Limits.toml` then the project limits file), `loadMonitorDefaults`. Includes `Physics/TypeAid.hh` directly.                                                                                                                                                                       |
| `Config/Reader.hh`   |   212 | TOML section parsers: `readEventsSection`, **`readInputSection`** (added Phase 2; populates `Register::inputPath`), `readRecordSection`, `readLogSection`, `readPathsAndFile`, `readPythiaSection`, `readProbeSection`. Plus `resolveThreadCount`, `sanitiseLoggingConfig`.                                                                                    |

---

### `Physics.hh` — pure physics

Property enum is the canonical source for `Config::ParticleLimits` /
`Config::EventLimits` keys. **Deps:** none.

| Subfile                 | Lines | Contents                                                                                                                                                                                                                              |
| ----------------------- | ----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Physics/Types.hh`      |   103 | `Lorentz` (= `ROOT::Math::PxPyPzEVector`), `Column`. `ParticleProperty` enum (12 values), `EventProperty` enum (1: `Multiplicity`). `toIndex<Enum>`, `ParticleTraits`/`EventTraits`, `kParticleTraits[12]`/`kEventTraits[1]` arrays, `static_assert`s, `traitsOf` overloads. |
| `Physics/TypeAid.hh`    |    47 | String converters: `particlePropertyToString`, `eventPropertyToString`, `stringToParticleProperty`, `stringToEventProperty`, `tryStringToParticleProperty`, `tryStringToEventProperty`.                                                |
| `Physics/Properties.hh` |    29 | High-level: `particlePropertyName`, `eventPropertyName`, `valueOf` (×2: per-particle and per-event), `multiplicityOf`.                                                                                                                  |
| `Physics/Kinematics.hh` |   100 | `fromComponents`, `invariantMass` (×2), `deltaPhi`, `deltaR`, `cosOpening`. Also column-vectorized variants: `invariantMassColumn`, `transverseMomentum`, `momentum`, `pseudorapidity`, `rapidity`, `azimuthalAngle`.                  |

---

### `Utility.hh` — domain-agnostic formatters

**Deps:** Config (Time.hh consumes `Config::TimePoint`).

| Subfile             | Lines | Contents                                                                              |
| ------------------- | ----: | ------------------------------------------------------------------------------------- |
| `Utility/Number.hh` |    54 | `numberFormat` (comma-grouped, padded), `numberString` (k / M / B / T / P / E suffix). |
| `Utility/Time.hh`   |    66 | `localTime`, `timeString` (×2: `time_t` and `Config::TimePoint`), `durationString`.    |

---

### `Probe.hh` — ROOT file reader

Pulls in seven sub-headers; consumers use only `#include "Probe.hh"`.
**Deps:** Physics, Config.

| Subfile               | Lines | Contents                                                                                                                                                                                                                                                                                                                |
| --------------------- | ----: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Probe/Types.hh`      |   109 | `Lorentz` re-export. Coord specs (`CartesianSpec`, `PtEtaPhiESpec`, `PtEtaPhiMSpec`) + `CoordSpec` variant. `BranchType`, `MissingBranchPolicy`, `BranchSpec`, `CollectionSpec`, **`ScalarSpec`** (declared but currently never consumed). `AuxColumn`, `ScalarValue`, `EventKey`, `Event` (with `[]`, `n`, `column<T>`, `scalar<T>`). |
| `Probe/Schema.hh`     |   215 | `namespace detail` only. Helpers: `Partition`, `enableRootThreadSafety`, `branchTypeStr`, `detectType`, `requireBranch`/`requireType`, `KinBuf`, `coordNames`, `makeLorentz`, `partitionEvents`, `probeFirstKey`, `scanIndexBranch`. (Filename should be `Detail.hh` — see REVIEW.)                                       |
| `Probe/FlatReader.hh` |   226 | `class FlatReader` — per-particle row tree + index branch. Branch caching, `TTreeIndex` support, `keyRange` scan.                                                                                                                                                                                                       |
| `Probe/VecReader.hh`  |   103 | `class VecReader` — per-event vector branches via `TTreeReaderArray<float>`. v1: only Float kinematics.                                                                                                                                                                                                                  |
| `Probe/Event.hh`      |   145 | `class EventStream` — unified Flat/Vec iterator with dense key range or full scan; `nEventsHint` short-circuits the index-key scan.                                                                                                                                                                                     |
| `Probe/Parallel.hh`   |   140 | `runParallel<Callback>` (×2 overloads — with/without scalars), `readAllParallel` (in-RAM, flagged unsafe for large files).                                                                                                                                                                                              |
| `Probe/EventCount.hh` |    36 | **(Added Phase 2)** `resolveEventCount(filepath)` — opens a ROOT file and reads `About/events/n_events_total` (written by `Meta::writeAbout`). Returns 0 on any failure. Used by `_Lambda_Reconstruction.cc:61` as middle tier of three.                                                                                |

---

### `Record.hh` — ROOT object writer (histograms + trees + metadata)

**Deps:** Physics, Config, Probe, Monitor.

| Subfile               | Lines | Contents                                                                                                                                                                                                                                                                                          |
| --------------------- | ----: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Record/Types.hh`     |    69 | `NoBasis`, `TH1Record`, `TH2Record`, `TreeRecord`, `EventTH1Record`, `ExtractHist1D`, `ExtractHist2D`, `RootObjects<Basis>`, `RootArray<Basis>`. `Lorentz` re-export.                                                                                                                              |
| `Record/Extract.hh`   |   183 | **Top-level `namespace Extract`** (not `Record::Extract`). `Event`/`Lorentz`/`Scalars`/`Fn` aliases. Primitives: `property`, `multiplicity`, `totalMultiplicity`, `pairInvariantMass`, `deltaR`, `column`, `scalar`, `constant`. Combinators: `leadingOf`, `trailingOf`, `filtered`, `sumOf`, `countIf`. |
| `Record/Meta.hh`      |   250 | **Top-level `namespace Meta`** (not `Record::Meta`). `Dataset`/`Processing`/`EventSummary`/`Physics`/`Objects`/`Integrity`/`Notes`/`Record` structs. `nowISO8601`, `processedBy`, `osArch`, `readFile`, `capture()`, `writeAbout()`. Writes ROOT directories under `About/`.                       |
| `Record/Histogram.hh` |   165 | `declareTree<N>`, `count`/`countAll`/`resetCount`/`resetAllCounts`. `fill` overloads (5 record types). `scaleAndWrite`/`scaleAndWriteToDir`, `write`/`writeToDir`/`writeAll`.                                                                                                                      |
| `Record/Finalizer.hh` |   117 | `FatalGracePeriod` constant. `checkpointWrite`, `wrapUp`. **`class FinalizerController<RootArrayT, ProgramLogBuilder>`** — no `PythiaT` template. Ctor takes optional `std::function<void()>` callbacks `printStats` and `listChangedSettings`. Methods: `installFatalStallHandler`, `setMeta`, `normalShutdown`, private `fatalShutdown`. |

---

### `Monitor.hh` — async terminal I/O

**Deps:** Config, Utility. **No Pythia8 in transitive set.**

| Subfile               | Lines | Contents                                                                                                                                                                                                                                                                                       |
| --------------------- | ----: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Monitor/Types.hh`    |    62 | `FatalStallMultiplier`. `RenderStatus`/`RenderBar`/`WriteRunStat` constexpr flags + `Dont*` negatives. `NoEvents`, `CallbackCompleted`/`NoCallbackCompleted`. `RunPhase`, `ThreadPhase` enums. `RunSnapshot`, `PendingActions`, `ThreadSnapshot`.                                              |
| `Monitor/Format.hh`   |    23 | `updatedETA` only — single-function file. (REVIEW: fold into `Snapshot.hh`.)                                                                                                                                                                                                                  |
| `Monitor/Snapshot.hh` |    95 | `phaseString`, `threadPhaseString`, `statusString`, `makeSnapshot`, `runStatString`, `threadStatString`.                                                                                                                                                                                       |
| `Monitor/Render.hh`   |   165 | Terminal control — `disable_input_echo`, `restore_terminal`, `terminalMutex`, `writeTextFile`, `renderProgressBar`. **Non-templated** (was templated on `PythiaT`): `buildLogText`, `outputLog`, `terminalReport`. All three accept optional `std::function<void()>` callbacks for `printStats` / `listChangedSettings`. Plus `buildEmergencyLogText`, `writeEmergencyLog`. |
| `Monitor/Logger.hh`   |   345 | `class AsyncLogger` — background heartbeat thread. `start`, `publish`, `publishThreadStats`, `finish`, `setFatalStallHandler`, `stop`. Internal: `runLoop`, `mergePending`, `processUpdate`, `flushRunStat`, `heartbeatTerminal`, `writeThreadStats`, `terminalIdleFor`/`isTerminalStalled`/`isFatalStalled`, `renderStatusLine`. |

---

### `Paint.hh` — ROOT histogram styling and export

**Deps:** none (pure ROOT + toml++).

| Subfile          | Lines | Contents                                                                                                                                                                                            |
| ---------------- | ----: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Paint/Types.hh` |    69 | `LineSpec`, `FillSpec`, `MarkerSpec`, `AxisSpec`, `CanvasSpec`, `StatsSpec`, `LegendSpec`, `Style`, `PadLayout`.                                                                                    |
| `Paint/Style.hh` |    38 | `parseColor` (named-color + offset parser, e.g. `kRed+2`).                                                                                                                                          |
| `Paint/Apply.hh` |   205 | `loadStyle` (TOML reader, default + section override); `applyGlobalStyle`, `applyStyle` (TH1 / TGraph), `makeCanvas`, `applyStats`. Private `detail::readColor`, `valueOr`, `stringOr`, `mergeSection`. |
| `Paint/Save.hh`  |    97 | `saveToFile`, `savePdf`, `savePng`, `saveSvg`, `saveComposite`. Private `detail::ensureDirFor`.                                                                                                     |

---

## `modules/`

### `Lambda.hh` — orchestrator

Owns the three analysis-callback orchestrators (`pythiaAnalysis`,
`rootAnalysis`, `dataGenerator`) and the `logString` helper.
**Deps:** Probe, Record, Monitor, Config, Physics, Pythia8.

| Subfile                    | Lines | Contents                                                                                                                                                                                                                                                                                                                                                                                                |
| -------------------------- | ----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Lambda.hh` (umbrella)     |   125 | Top-level `logString(Parameters&)`, plus the three orchestrators. `pythiaAnalysis(pythia, root, ctx)` uses `AnalysisContext`; the checkpoint branch calls `Monitor::outputLog(root, ctx.logging, ..., printStats, listChangedSettings)`. `rootAnalysis(ev, threadId, histMutex, ctx)` uses `AnalysisContext`. `dataGenerator(pythia, ctx)` uses `GenerationContext`.                                       |
| `Lambda/Types.hh`          |    77 | Constants `kLambdaMass`/`kProtonMass`/`kPionMass`/`kMassDiff`. `ProtonPid`/`PionPid`. `HistogramSet` enum (`Unvalidated`/`Validated`/`Selected`) and `kHistogramSetCount = 3`. Aliases `Lorentz` (= `Record::Lorentz`), `RootObjects`, `RootArray`, `SpecsArray`. Structs `Candidates`, `InputConfig`, `CandidateConfig`, `Parameters`, `HistogramSetAttributes`, `DataObjects`.                          |
| `Lambda/TypeAid.hh`        |    37 | `kHistogramSetMap`. `propertyName(Physics::ParticleProperty)` / `propertyName(Physics::EventProperty)` — thin wrappers over `Physics::*PropertyName`. `propertyAlias` (`Mass_Invariant`→`Mass`, `Energy_Net`→`Energy`). `levelName(Config::RangeSize)` — duplicates `Config::levelToString`.                                                                                                            |
| `Lambda/ParamAid.hh`       |    47 | `defaultTreeName`, `resolveTreeName`, `labelForPidAbs`, `resolveCandidateLabels`.                                                                                                                                                                                                                                                                                                                       |
| `Lambda/Parameters.hh`     |   310 | `Recorded_ParticleProperties` (6 props). `kTreeEnabledSets` (empty std::array). Bounds resolution: `explicitBounds`, `levelBounds` (×2), `boundsFromNode<P>`, `resolveBounds<P>`. Schema: `inputSchema`. TOML loaders: `loadInputSection`, `loadCandidatesSection`. ROOT object decl: `declareDataObjects`, `shouldWriteTree`, `declareObjects`. Top-level orchestrator: `extractPhysics`. **Largest file in the project.** |
| `Lambda/Reconstruction.hh` |   103 | `dataLogString` (a static log blurb — REVIEW says move out). `Particle` candidate struct (renamed from `Lambda` in Phase 1). `cosTheta`, `harvestParticles` (uses `Pythia8::Pythia`), `reconstructCandidates`. **Includes `Pythia8/Pythia.h` directly** — the only file in the project that does, breaking the previous transitive chain through `Render.hh`.                                            |
| `Lambda/Recording.hh`      |    45 | `findObjects`, `fill` (×2: per-particle + array), `fillCandidates`.                                                                                                                                                                                                                                                                                                                                     |
| `Lambda/Context.hh`        |    37 | **(Added Phase 2)** `AnalysisContext { RootArray&, const Parameters&, Config::Log&, Monitor::AsyncLogger& }` for `pythiaAnalysis` / `rootAnalysis`. `GenerationContext { DataObjects&, std::mutex& treeMutex, Config::Log&, Monitor::AsyncLogger& }` for `dataGenerator`.                                                                                                                                |

---

## `configs/`

### Run configs

| File                         | Driver                       | Sections                                                                                                                   |
| ---------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `Lambda_Generation.toml`     | `_Lambda_Parallel.exe`       | `[events]` · `[pythia]` · `[record]` · `[record.paths]` · `[record.file]` · `[record.metadata]` · `[lambda]` · `[monitor]` |
| `Lambda_Reconstruction.toml` | `_Lambda_Reconstruction.exe` | `[events]` (with `input_file`) · `[probe]` · `[record]` · `[record.paths]` · `[record.file]` · `[record.metadata]` · `[lambda]` |

### Limits

| File                            | Scope                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------ |
| `configs/General_Limits.toml`   | Universal fallback. Loaded first by `limitExtractor`; required to exist.       |
| `configs/Lambda_Limits.toml`    | Lambda-specific bounds; loaded second, overrides `General_Limits.toml` keys.   |
| `configs/defaults/Limits.toml`  | Older fallback (still present); not currently in the load path.                |
| `configs/defaults/Monitor.toml` | Read by `loadMonitorDefaults`; silently skipped if missing.                    |
| `configs/defaults/Paint.toml`   | Consumed by `Paint::loadStyle` callers (downstream tooling, not the drivers).  |

### Pythia

| File                         | Purpose                                         |
| ---------------------------- | ----------------------------------------------- |
| `Lambda_Reconstruction.cmnd` | Pythia8 settings for the pp → Λ generation pass |
| `NeNe.cmnd`                  | Pythia8 settings for NeNe collisions            |

---

## Key dependency notes

- **Pythia8 enters only through `Lambda/Reconstruction.hh`.** Anything that stops
  short of `#include "Lambda.hh"` does not need to link Pythia8. The unit test
  `tests/test_reconstructCandidates.exe` does include `Lambda/Reconstruction.hh`
  (which now pulls Pythia8 explicitly) but never *calls* `harvestParticles`, so
  link-time Pythia8 symbols can be elided when the inline body is not emitted.
- **`Monitor::AsyncLogger` is the only thread the codebase spawns explicitly.**
  Pythia parallelism is handled inside `PythiaParallel::run`. `Probe::runParallel`
  spawns its own `std::thread` per partition.
- **`Watch` (= `Config::Log`) is the central per-run mutable state.** It is
  shared by reference by every orchestrator and the `AsyncLogger`. Per-event
  accounting goes through `Watch::recordEvent(now)` under `Watch::eventMutex_`.
  A point-in-time copy is obtained via `Watch::freeze()` (returns
  `std::unique_ptr<Watch>`); the type is non-copyable and non-movable.
- **`Register` (= `Config::Root`) is a god-object.** It holds `TFile*`, all
  output-path templates, beam-energy string, histogram bin count + scale, the
  particle/event limits maps, and `inputPath`. ROADMAP-level split candidate.
