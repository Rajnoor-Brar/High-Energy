# DataFlow — every TOML key, end-to-end

Configuration data flow for the High-Energy reconstruction simulation.
Documents every key the codebase can read from a project TOML, the C++
struct/field that receives it, every downstream consumer, and the point at
which the value is no longer read.

> **Scope.** The "main" TOML the user passes on `argv[1]`
> (`Lambda_Generation.toml`, `Lambda_Reconstruction.toml`, or
> `tests/fixtures/lambda_fixture.toml`). Includes side-loaded TOMLs that
> Config opens from inside that flow (`configs/defaults/Limits.toml`,
> `configs/defaults/Monitor.toml`, `Lambda_Limits.toml`). Excludes
> `configs/defaults/Paint.toml` (no in-tree consumer) and `*.cmnd` files
> (read by Pythia, not by the Config namespace).

> **Companion docs.** [MAP.md](MAP.md) (file map), [REVIEW.md](REVIEW.md)
> (open backlog), [ROADMAP.md](ROADMAP.md) (active phase),
> [Architecture.md](Architecture.md) (strategic plan-of-plans). Parallel-agent
> reports under [Gemini/](Gemini/) — `ConfigReport.md` and
> `DataPath.toml`/`DataPath.md` cover overlapping ground but lag
> the live tree (e.g. they describe Pipeline B; this doc reflects
> Pipeline A as merged).

---

## Reading order — five distinct `toml::parse_file` calls per run

The same project TOML is parsed up to five times during driver startup; each
parse populates a different sink. Tracking which parse a key belongs to is
the only way to predict which fields are actually loaded into which struct.

| # | Caller                          | Site                                    | Key path consumed                                                |
| - | ------------------------------- | --------------------------------------- | ---------------------------------------------------------------- |
| 1 | `Config::limitExtractor`        | `utils/Config/Defaults.hh:75`           | `[lambda].hist_limits`                                           |
| 2 | `Config::configuration`         | `utils/Config.hh:26`                    | `[events]`, `[record]`, `[monitor]`/`[log]`, `[record.paths]`, `[record.file]` |
| 3 | `Config::configurePythia`       | `utils/Config.hh:59`  *(unused — see "Dead Config" below)* | `[pythia]`                                       |
| 3'| `Config::configureProbe`        | `utils/Config.hh:79`                    | `[probe]`                                                        |
| 4 | `Lambda::extractPhysics`        | `modules/Lambda/Loaders.hh:20`          | `[lambda]`                                                       |
| 5 | `Record::Meta::capture`         | `utils/Record/Meta.hh:121`              | `[metadata]` (top-level — **not** `[record.metadata]`), `[lambda]` (snapshot) |

Plus two side-loaded TOMLs:

| #  | Caller                       | Site                              | File                                                  |
| -- | ---------------------------- | --------------------------------- | ----------------------------------------------------- |
| S1 | `Config::loadMonitorDefaults`| `utils/Config/Defaults.hh:88`     | `configs/defaults/Monitor.toml` (silent if absent)    |
| S2 | `Config::loadLimitsFile` ×2  | `utils/Config/Defaults.hh:73, 79` | `configs/defaults/Limits.toml` then resolved `[lambda].hist_limits` |
| S3 | `toml::parse_file`           | `modules/Lambda/Loaders.hh:39`    | `root.histLimitsFile` (the resolved limits file, parsed a SECOND time inside `extractPhysics`) |

Counts of `toml::parse_file` per main-TOML run: **5** (project file) + **3**
(side loaders, with limits parsed twice). The limits file is parsed twice
because `loadLimitsFile` populates `Register::particleLimits`/`eventLimits`
(generic per-property-per-level table), then `extractPhysics` re-parses to
read the per-set tables (`[Unvalidated]`, `[Validated]`, `[Selected]`) that
reference the level keys.

---

## `[events]`

Source of run mode + loop sizing. Parser: `Config::readEventsSection`
(`utils/Config/Reader.hh:41-55`). Backwards-compat alias `[run]` is consulted
only when `[events]` is absent.

### `events.pythia` (bool, default: `true`)

| Aspect             | Detail                                                                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into        | `Config::Events::isPythia` (`utils/Config/Types.hh:46`)                                                                                           |
| Reader call sites  | `Reader.hh:43-45` (`config["events"]["pythia"]` first, falls back to `!config["events"]["probe"]`).                                               |
| Passed to          | Stored in `Events`. **Never read by any driver.** The drivers each pick `Pythia8::PythiaParallel` or `Probe::runParallel` based on their *file identity*, not on `events.isPythia`. |
| Active lifetime    | From `readEventsSection` until destruction of the local `Events` object inside `Config::configuration` (or `Config::configureProbe::eventConfig`). |
| Abandoned at       | `readEventsSection` is the only writer; **no reader.** Effectively dead.                                                                          |
| Use count          | 0 reads after parsing. Trace incomplete? — no, exhaustive grep for `isPythia` returns only the assignment.                                        |

### `events.probe` (bool, default: `false`/inverse of `pythia`)

| Aspect            | Detail                                                                          |
| ----------------- | ------------------------------------------------------------------------------- |
| Parsed into       | `Config::Events::isPythia` (negated; same field as above).                      |
| Use count         | 0 — folded into `isPythia` then never read.                                     |

### `events.event_count` (integer, default: `1000`)

Backwards-compat: `[run].event_count` if `[events]` absent.

| Aspect            | Detail                                                                                                                                                                                                                                                                                                                                       |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | **Two places** (cross-cutting): `Config::Events::eventCount` (`Types.hh:48`) and `Config::Watch::nEvents` (`Types.hh:83`). The Reader writes both at once (`Reader.hh:46-48, 53`).                                                                                                                                                            |
| Passed to         | (a) `Config::sanitiseLoggingConfig` (`Reader.hh:34`) computes `bar_interval = nEvents / progressDivisor`; (b) `Config::readPathsAndFile` (`Reader.hh:148`) appends `Utility::numberString(watch.nEvents)` to the file title if `[record.file].events = true`; (c) `Monitor::AsyncLogger::publish` reads `logging.nEvents` for edge detection (`Logger.hh:65`); (d) `Monitor::makeSnapshot` puts `nEvents` into `RunSnapshot::nEvents` (`Snapshot.hh:54`); (e) `Monitor::buildLogText` and `buildEmergencyLogText` print it (`Render.hh:69, 73, 126`); (f) `Record::FinalizerController::normalShutdown` calls `writeAll(_, _, logging_.nEvents)` to scale histograms (`Finalizer.hh:66, 95`); (g) `Record::Meta::capture` writes `r.events.n_events_total = log.nEvents` (`Meta.hh:161`); (h) Each driver reads `logParams.nEvents` to size its run loop (`_Lambda_Parallel.cc:49`, `_Lambda_Data.cc:44`, `_Lambda_Test.cc:51`). |
| Active lifetime   | Set during `configuration()`; live for the rest of the run.                                                                                                                                                                                                                                                                                  |
| Mutated mid-run   | Yes — `_Lambda_Reconstruction.cc:45, 51` overwrites `logParams.nEvents` with the resolved event count from `Probe::resolveEventCount` (ROOT metadata) or `EventStream::nEvents()` (full key scan) when the user did not set `event_count` and the parsed default of 1000 was clobbered to 0 via the `eventCount == 0` guard.                                                                                                                                                                                                                                          |
| Abandoned at      | Survives until `Watch` destructor at end of `main()`; `Events::eventCount` survives only inside `ProbeConfig::eventConfig` for the reconstruction driver (`probeConfig.eventConfig.eventCount` at `_Lambda_Reconstruction.cc:45, 51, 65`).                                                                                                    |
| Use count         | ~13 distinct reader sites (counted: bar_interval calc, file-title builder, AsyncLogger.publish edge check, makeSnapshot, buildLogText, buildEmergencyLogText, terminalReport via snapshot, FinalizerController::normalShutdown.writeAll, FinalizerController::fatalShutdown.wrapUp, Meta::capture, three driver run loops, two reconstruction-driver fallback writers). |

### `events.nThreads` (integer, default: `0` = auto)

Backwards-compat: `[run].nThreads`.

| Aspect            | Detail                                                                                                                                                                                                                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | **Two places** (cross-cutting): `Config::Events::nThreads` (`Types.hh:47`) and `Config::Watch::n_threads` (`Types.hh:86`). Both written by `Reader.hh:49-51, 54`.                                                                                                                                       |
| Passed to         | (a) `_Lambda_Data.cc:27-29` passes `Config::resolveThreadCount(logParams.n_threads)` into `pythia.readString("Parallelism:numThreads = ...")`; (b) `_Lambda_Reconstruction.cc:64` passes the resolved count to `Probe::runParallel`. **`Events::nThreads` itself is never read** — only the `Watch::n_threads` mirror is consumed. |
| Resolution        | `resolveThreadCount(0)` returns `hardware_concurrency() - 2` (min 1); any positive value passes through unchanged (`Reader.hh:21-25`).                                                                                                                                                                  |
| Active lifetime   | Set during `configuration()`; consumed inside the driver right before launching the worker pool.                                                                                                                                                                                                        |
| Abandoned at      | `_Lambda_Data.cc:29` after `pythia.readString`; `_Lambda_Reconstruction.cc:64` after `Probe::runParallel` returns. After the worker pool is sized, the field sits idle in `Watch`.                                                                                                                      |
| Use count         | 2 (one driver each). `Events::nThreads` use count: 0.                                                                                                                                                                                                                                                   |

---

## `[probe]`

Parsed by `Config::readProbeSection` (`utils/Config/Reader.hh:179-214`).
Loaded only via `Config::configureProbe` (`utils/Config.hh:71-81`), which is
called only by `_Lambda_Reconstruction.cc:24` and
`tests/test_rootAnalysis_smoke.cc:82`.

### `probe.input_file` (string, default: `""`)

| Aspect            | Detail                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::ProbeConfig::inputFile` (`Types.hh:70`).                                                                                                                                                                                                                                                                                                                                     |
| Passed to         | (a) `Probe::resolveEventCount(probeConfig.inputFile)` to read `About/events/n_events_total` from the ROOT metadata (`_Lambda_Reconstruction.cc:45`); (b) `Probe::EventStream(probeConfig.inputFile, collectionSpecs)` for the fallback full-key-scan event count (`_Lambda_Reconstruction.cc:51`); (c) `Probe::runParallel(probeConfig.inputFile, ...)` to open the source `TFile` per worker (`_Lambda_Reconstruction.cc:59`); (d) `Record::Meta::capture` does not read it directly — `_Lambda_Reconstruction.cc:70` copies it into `metaRec.dataset.parent_files` after `capture()` returns. |
| Active lifetime   | Set during `configureProbe`; held by reference until `runParallel` completes; the copy in `Meta::Record` survives until `Meta::writeAbout` writes it to the output ROOT file.                                                                                                                                                                                                          |
| Abandoned at      | `_Lambda_Reconstruction.cc:70` (last use as a string before being copied into Meta).                                                                                                                                                                                                                                                                                                  |
| Use count         | 4 (resolveEventCount, EventStream, runParallel, Meta parent_files).                                                                                                                                                                                                                                                                                                                   |

### `probe.event_particles` (array of [label, spec, treeName, momenta-pairs[], index-pairs[]] arrays)

The "spec" integer encodes the coord system: `0` = Cartesian, `1` =
PtEtaPhiE, `2` = PtEtaPhiM. Position 3 must be exactly 4 `[name, type-letter]`
pairs (px, py, pz, E or pt, eta, phi, E/M); position 4 is the index branch
specification (typically one pair). Type letter follows ROOT TBranch leaf
list convention: `F` Float, `D` Double, `I` Int32, `i` UInt32, `L` Int64,
`l` UInt64, `O` Bool.

| Aspect            | Detail                                                                                                                                                                                                                                                                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Parsed into       | `std::vector<Config::ProbeParticle>` inside `Config::ProbeConfig::particles` (`Types.hh:71`). Each `ProbeParticle` holds `label`, `spec`, `treeName`, `momentaBranches: vector<pair<string,string>>`, `indexBranches: vector<pair<string,string>>` (`Types.hh:61-67`).                                                                                  |
| Passed to         | `Probe::toCollectionSpecs(probeConfig)` → `Probe::toParticleSpecs` (`utils/Probe/ConfigAid.hh:13-50`) which converts each entry to a `Probe::ParticleSpec` (`Probe::CollectionSpec` is its alias). `momentaBranches` becomes `Probe::CartesianSpec{vector<BranchSpec>}` (or PtEtaPhiE/PtEtaPhiM depending on `spec`); `indexBranches` becomes `vector<BranchSpec>`. Throws `runtime_error` if `momentaBranches.size() != 4` or `spec` is not 0/1/2. |
| Downstream        | The `vector<CollectionSpec>` is passed to `Probe::EventStream` (`_Lambda_Reconstruction.cc:51`) and to both `runParallel` invocations (`:59`). Inside `runParallel` (`utils/Probe/Parallel.hh`), each `CollectionSpec` is read for `tree`, `coords`, `indexBranches[0]`, and `auxBranches`; passed into `FlatReader` ctor (`utils/Probe/FlatReader.hh:16-80`) which calls `tree_->SetBranchAddress(spec.indexBranches[0].name, ...)` etc. |
| Lifetime          | `ProbeConfig::particles` lives for the full driver run. The transformed `vector<CollectionSpec> collectionSpecs` lives in the driver as a stack local (`_Lambda_Reconstruction.cc:48`) until `runParallel` returns.                                                                                                                                     |
| Abandoned at      | `_Lambda_Reconstruction.cc:66` — last use of `collectionSpecs` is inside `runParallel`. The original `ProbeConfig::particles` is never read again after `toCollectionSpecs` returns.                                                                                                                                                                    |
| Use count         | 1 (only `toCollectionSpecs`); the converted result has many uses inside `Probe`.                                                                                                                                                                                                                                                                        |

---

## `[pythia]`

Parsed by `Config::readPythiaSection` (`utils/Config/Reader.hh:172-177`),
called only from `Config::configurePythia` (`utils/Config.hh:49-69`).

> **Pythia config is currently dead.** No driver calls `configurePythia`.
> Each Pythia driver (`_Lambda_Data.cc`, `_Lambda_Parallel.cc`,
> `_Lambda_Test.cc`) hardcodes `pythia.readFile("configs/Lambda_Reconstruction.cmnd")`
> and reads `pythia.settings.parm("Beams:eCM")` *from the cmnd file Pythia
> just loaded*, not from the project TOML. The `[pythia]` section in
> `Lambda_Generation.toml` is decorative; its values never reach Pythia.
> See REVIEW item 20.

### `pythia.beam_energy` (double, default: `0.0`)

| Aspect            | Detail                                                                                                                                                                                                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::PythiaConfig::beamEnergy` (`Types.hh:53`).                                                                                                                                                                                                                                   |
| If consumed       | (only inside the unused `configurePythia`) `pythia.readString("Beams:eCM = ...")` AND `reg.beamEnergy = Form("%.0f", py.beamEnergy)`, after which `beamEnergy` is read by `Render.hh:68, 120` (log text), `Meta::capture:168` (parsed back to `Double_t`), and `readPathsAndFile:147, 151` (file title). |
| Actual flow today | `Register::beamEnergy` is set directly by each driver from `pythia.settings.parm("Beams:eCM")` (`_Lambda_Parallel.cc:21`, `_Lambda_Data.cc:22`, `_Lambda_Test.cc:22`) — i.e. from the cmnd file, not from TOML.                                                                       |
| Use count         | 0 today. (Would be ~5 sites if `configurePythia` were wired up.)                                                                                                                                                                                                                      |

### `pythia.cmnd_file` (string, default: `""`)

| Aspect            | Detail                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::PythiaConfig::cmndFile`.                                                                                                                                                                                                                                   |
| If consumed       | (inside unused `configurePythia`) `pythia.readFile(py.cmndFile)`.                                                                                                                                                                                                   |
| Actual flow today | All drivers hardcode `pythia.readFile("configs/Lambda_Reconstruction.cmnd")` (`_Lambda_Parallel.cc:19`, `_Lambda_Data.cc:20`, `_Lambda_Test.cc:18`). The TOML key is dead.                                                                                          |
| Use count         | 0 today.                                                                                                                                                                                                                                                            |

### `pythia.seed` (integer, default: `0`)

Same status as `cmnd_file` — parsed into `PythiaConfig::seed`, consumed only
inside the unused `configurePythia`. Use count: 0.

---

## `[record]`

Parsed by `Config::readRecordSection` (`utils/Config/Reader.hh:58-70`).
Backwards-compat alias `[run]` for `serial`/`sr_padding`.

### `record.serial` (integer, default: `0`)

| Aspect            | Detail                                                                                                                                                                                                                                                  |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Watch::serial` (`Types.hh:81`, type `Int_t`).                                                                                                                                                                                                  |
| Passed to         | (a) `Config::readPathsAndFile:132-133` formats `serialStr = Form("_%0Nd", sr_padding, serial)` and prepends to `rootDirectory`/`fileTitle`; (b) `Monitor::buildLogText:67` and `Monitor::buildEmergencyLogText:119` print it as `Serial : NN` in the log file. |
| Active lifetime   | Set during `configuration()`; consumed by `readPathsAndFile` immediately, then re-read at log-write time.                                                                                                                                              |
| Abandoned at      | Last log write inside `FinalizerController::normalShutdown` → `Monitor::outputLog` (`Render.hh:67`).                                                                                                                                                   |
| Use count         | 3 (path format, log text, emergency log).                                                                                                                                                                                                              |

### `record.sr_padding` (integer, default: `2`)

Backwards-compat: `[run].sr_Padding` (capital P).

| Aspect            | Detail                                                                                                                                                |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Watch::sr_padding` (`Types.hh:82`).                                                                                                          |
| Passed to         | `readPathsAndFile:133` only (zero-pad width for `serial`).                                                                                            |
| Abandoned at      | `readPathsAndFile` returns; the value sits idle in `Watch` for the rest of the run.                                                                  |
| Use count         | 1.                                                                                                                                                    |

### `record.bin_count` (integer, default: `100`)

| Aspect            | Detail                                                                                                                                                                                                            |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Register::binCount` (`Types.hh:132`, type `Int_t`).                                                                                                                                                      |
| Override path     | `[monitor].bin_count` re-overrides at `Reader.hh:96`. Default seeded by `loadMonitorDefaults:97` from `configs/defaults/Monitor.toml`.                                                                            |
| Passed to         | `Lambda::declareObjects` (`modules/Lambda/Declare.hh:64`) — `new TH1D(name, title, root.binCount, low, high)` for every per-property histogram in every histogram set.                                            |
| Active lifetime   | Set during `configuration()`; read once during `declareObjects` (called per driver right after `extractPhysics`).                                                                                                  |
| Abandoned at      | After `Lambda::declareObjects` returns — every per-driver call site is the same.                                                                                                                                  |
| Use count         | 1 reader; effectively constant per run.                                                                                                                                                                           |

### `record.hist_scaling` (double, default: `100`)

| Aspect            | Detail                                                                                                                                                                                                                                                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Register::histScale` (`Types.hh:133`, type `Double_t`).                                                                                                                                                                                                                                                                        |
| Override path     | `[monitor].hist_scaling` at `Reader.hh:97`; default `1.0` from `configs/defaults/Monitor.toml` via `loadMonitorDefaults:98`.                                                                                                                                                                                                            |
| Passed to         | (a) `Lambda::pythiaAnalysis` checkpoint branch — `Record::checkpointWrite(ctx.histograms, root.checkpointOutName, root.histScale, eventIndex)` (`Lambda.hh:65`); (b) `Record::FinalizerController::normalShutdown` — `writeAll(histogramSets_, root_.histScale, logging_.nEvents)` (`Finalizer.hh:66`); (c) `Record::FinalizerController::fatalShutdown` → `wrapUp(...)` (`Finalizer.hh:95`); (d) `Render.hh:74` prints "Histogram Scale" in the log. |
| Math              | Inside `scaleAndWrite` (`Histogram.hh:107-122`): `scale = histScale / nEvents`, applied to every TH1/TH2 with `Scale(scale, "width")` for 1D non-2D, or `Scale(scale)` otherwise.                                                                                                                                                       |
| Active lifetime   | Set during `configuration()`; live until `outFile->Close()` inside `normalShutdown`.                                                                                                                                                                                                                                                    |
| Abandoned at      | `FinalizerController::normalShutdown` (or `fatalShutdown`).                                                                                                                                                                                                                                                                             |
| Use count         | 4 (checkpoint, normal write, fatal write, log text).                                                                                                                                                                                                                                                                                    |

---

## `[record.paths]`

Parsed inside `Config::readPathsAndFile` (`utils/Config/Reader.hh:100-170`).
Backwards-compat: `[paths]` if `[record.paths]` absent. All values consumed
locally to compose path templates; no field survives unmodified. Output is
written into `Register` TString fields, then `fs::create_directories` creates
the directories on disk.

### `record.paths.directory` (string, default: `"output/<project>/"`)

| Aspect       | Detail                                                                                                                                                                                                                                                          |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into  | Local `baseRootDir` in `readPathsAndFile`. Composed with `serialStr` (if `serialDirectory=true`) into local `rootDir`, copied into `Register::rootDirectory`.                                                                                                  |
| Used by      | (a) `Register::rootDirectory` is read by `readPathsAndFile` itself to build `Register::outName` (`Reader.hh:156`); (b) compose `Register::logDirectory` and `Register::checkpointDirectory` if `logInSubDir`/`checkpointsInSubDir` are true; (c) **never read directly outside `readPathsAndFile`**. The `outName`/`logName`/etc. paths are what the rest of the system uses. |
| Use count    | 1 reader (the immediate composition).                                                                                                                                                                                                                            |

### `record.paths.output_log_directory` (string, default: `"params/"`)

| Aspect       | Detail                                                                                                                                                                                                |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into  | Local `logBasePath`; composed (or not, depending on `logInSubDir`) into `Register::logDirectory`.                                                                                                     |
| Used by      | `Register::logDirectory` feeds `Register::logName` (`Reader.hh:157`), `runStatName` (`:158`), `threadStatDirectory` (`:159`).                                                                          |
| Use count    | 1 reader (local composition).                                                                                                                                                                         |

### `record.paths.checkpoint_directory` (string, default: `"checkpoints/"`)

| Aspect       | Detail                                                                                                                                  |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into  | Local `checkBasePath`; composed into `Register::checkpointDirectory`.                                                                   |
| Used by      | `Register::checkpointDirectory` feeds `Register::checkpointOutName` and `Register::checkpointLogName` (`Reader.hh:160-161`).            |
| Use count    | 1 reader.                                                                                                                                |

### `record.paths.serialDirectory` (bool, default: `true`)

| Aspect       | Detail                                                                                                                            |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into  | Local `serialSubDir` in `readPathsAndFile`. If true, `rootDir = baseRootDir + serialStr + "/"`.                                   |
| Use count    | 1 reader; discarded immediately when `readPathsAndFile` returns.                                                                  |

### `record.paths.logInSubDir` (bool, default: `true`)

Same pattern: local `logSubDir`. If true, `logDirectory = rootDir + logBasePath`; otherwise `logDirectory = logBasePath` (treated as an
absolute or independent path). Discarded after composition.

### `record.paths.checkpointsInSubDir` (bool, default: `true`)

Same pattern: local `checkSubDir`. If true, `checkpointDirectory = rootDir + checkBasePath`. Discarded after composition.

---

## `[record.file]`

Parsed inside `Config::readPathsAndFile` (same function as `[record.paths]`).
Backwards-compat: `[file]`. All values local to that function.

### `record.file.prefix` (string, default: `"Unspecified"`)

| Aspect       | Detail                                                                                                                                                                                              |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into  | Local `filePrefix` (`Reader.hh:140`). Becomes the base of `fileTitle`, then copied to `Register::fileTitle` (`:154`).                                                                              |
| Used by      | (a) `Register::fileTitle` propagates into `outName`, `logName`, `runStatName`, `threadStatDirectory`, `checkpointOutName`, `checkpointLogName` (`Reader.hh:156-161`); (b) `Monitor::AsyncLogger::start` reads `root.fileTitle.Data()` to seed the initial `RunSnapshot::eta` field shown during the "Initializing ..." display (`Logger.hh:47`); (c) `Render.hh:121` prints `File Title : ...` in the emergency log. |
| Use count    | ~9 (six derived `Register::*Name` fields, plus three direct readers).                                                                                                                              |

### `record.file.serial` (bool, default: `true`)

| Aspect       | Detail                                                                                                                                                |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into  | Local `fileSerial`. If true, append `_<padded serial>` to the file title.                                                                              |
| Use count    | 1; discarded after composition.                                                                                                                       |

### `record.file.energy` (bool, default: `true`)

Local `fileEnergy`. If true, append `_<beamEnergy>GeV` to file title AND to
the threads directory name. Discarded after composition. Use count: 1.

### `record.file.events` (bool, default: `true`)

Local `fileEvents`. If true, append `_<numberString(nEvents)>` (e.g. `_1k`,
`_10M`) to file title AND to threads directory name. Discarded after
composition. Use count: 1.

---

## `[record.metadata]` — **dead under current code**

The user TOML uses `[record.metadata]` (nested table), which produces
`cfg["record"]["metadata"]`. But `Record::Meta::capture`
(`utils/Record/Meta.hh:122`) reads `cfg["metadata"]` (top-level). The two
do not match, so **every key under `[record.metadata]` is silently ignored**.
The corresponding `About/dataset/...` fields written to the output ROOT file
are empty strings.

| Key          | Intended target                            | Actual fate                            |
| ------------ | ------------------------------------------ | -------------------------------------- |
| `dataset_name` | `Meta::Dataset::name`                    | Never read; `Meta::Record::dataset.name = ""` |
| `data_type`    | `Meta::Dataset::data_type`               | Never read; defaults to `""`           |
| `run_period`   | `Meta::Dataset::run_period`              | Never read; defaults to `""`           |
| `campaign`     | `Meta::Dataset::campaign`                | Never read; defaults to `""`           |
| `notes`        | `Meta::Notes::description`               | Never read; defaults to `""`           |
| `generator`    | `Meta::Physics::generator`               | Defaults to `"Pythia8"`                |
| `tune`         | `Meta::Physics::tune`                    | Never read; defaults to `""`           |
| `pdf_set`      | `Meta::Physics::pdf_set`                 | Never read; defaults to `""`           |

To activate: rename TOML section to `[metadata]` (top level), or update
`Meta::capture:122` to read `cfg["record"]["metadata"]`. **Both project
configs (`Lambda_Generation.toml`, `Lambda_Reconstruction.toml`) currently
populate `[record.metadata]`, so all five fields ship as empty strings.**
Trace incomplete? — no, exhaustive grep on `["metadata"]` and `meta->get` in
`Meta.hh` confirms only `cfg["metadata"]`.

---

## `[monitor]` (or `[log]` / `[logging]`)

Parsed by `Config::readLogSection` (`utils/Config/Reader.hh:72-98`). The
parser picks the first of `[monitor]`, `[log]`, `[logging]` that exists.
Defaults seeded by `Config::loadMonitorDefaults` (`Defaults.hh:84-100`) from
`configs/defaults/Monitor.toml` if present.

### `monitor.print_interval` (integer, default: `100`)

| Aspect            | Detail                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Watch::print_interval` (`Types.hh:87`).                                                                                                                                    |
| Sanitisation      | `Config::sanitiseLoggingConfig` (`Reader.hh:36`) clamps to `>= 1`.                                                                                                                  |
| Passed to         | `Monitor::AsyncLogger::publish` (`Logger.hh:66`) — render the status line every Nth event.                                                                                          |
| Active lifetime   | Set during `configuration()`; consumed once per `publish` call, i.e. once per analyzed event for every driver.                                                                      |
| Abandoned at      | After the run loop ends and `AsyncLogger::finish` is called.                                                                                                                        |
| Use count         | 1 reader; called once per event.                                                                                                                                                    |

### `monitor.check_interval` (integer, default: `10000`)

| Aspect            | Detail                                                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Watch::check_interval` (`Types.hh:92`).                                                                                                                  |
| Passed to         | (a) `Lambda::pythiaAnalysis` (`modules/Lambda.hh:64`) — `if (ctx.logging.check_interval > 0 && eventIndex % check_interval == 0) { checkpointWrite + outputLog }`. (b) `Render.hh:77` prints "Check Interval" in the run log. |
| Active lifetime   | Set during `configuration()`; consumed once per analyzed event in `pythiaAnalysis`.                                                                                |
| Abandoned at      | End of run loop.                                                                                                                                                  |
| Use count         | 2 (checkpoint trigger, log text).                                                                                                                                  |

### `monitor.heartbeat_interval` (integer, default: `1000`, units: microseconds)

| Aspect            | Detail                                                                                                                                                                                                                                                                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Watch::heartbeat_interval` (`Types.hh:88`, type `Config::uSeconds = std::chrono::microseconds`). Reader scales the int via `uSeconds(hb)` — interpreted as microseconds.                                                                                                                                                                       |
| Passed to         | `AsyncLogger::start` (`Logger.hh:40-41`) copies into the private member `heartbeat_interval_` (with a min-1000-µs guard). The runLoop uses it as the deadline for `flushRunStat` (`Logger.hh:196, 275`) — controls how often the runstat log file is updated.                                                                                          |
| Logged            | `Render.hh:75` — "Status Snapshot Interval (ms)".                                                                                                                                                                                                                                                                                                       |
| Lifetime          | Set during `configuration()`; lives in `Watch` and in `AsyncLogger` for the duration of the run.                                                                                                                                                                                                                                                       |
| Abandoned at      | `AsyncLogger::stop` (called from destructor).                                                                                                                                                                                                                                                                                                           |
| Use count         | 2 (AsyncLogger heartbeat deadline, log text).                                                                                                                                                                                                                                                                                                           |

### `monitor.terminal_refresh_interval` (double, default: `2.0` in Monitor.toml; units: minutes)

| Aspect            | Detail                                                                                                                                                                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Watch::terminal_refresh_interval` (`Types.hh:89`, type `Config::Seconds`). Reader converts via `Seconds(static_cast<int>(60 * tr))` — input minutes, stored as seconds.                                                                         |
| Passed to         | `AsyncLogger::start` (`Logger.hh:42-43`, with min-60-s guard) copies into private `terminalRefreshInterval_`. The runLoop uses it as the deadline for `heartbeatTerminal` (`Logger.hh:197, 276`) — controls how often the terminal status is redrawn. |
| Lifetime          | Same as `heartbeat_interval`.                                                                                                                                                                                                                            |
| Use count         | 1 (terminal refresh deadline).                                                                                                                                                                                                                            |

### `monitor.program_stall_threshold` (double, default: `5.0` in Monitor.toml; units: minutes)

| Aspect            | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Config::Watch::program_stall_threshold` (`Types.hh:90`, type `Config::Seconds`). Same min-conversion as terminal_refresh.                                                                                                                                                                                                                                                                                                                                            |
| Passed to         | `AsyncLogger::start` (`Logger.hh:44-45`, with min-300-s guard) copies into `programStallThreshold_`. (a) `AsyncLogger::isTerminalStalled` (`:133-138`) checks idle ≥ threshold to mark a stalled status; (b) `AsyncLogger::isFatalStalled` (`:140-145`) checks idle ≥ `threshold * FatalStallMultiplier` to fire the registered fatal-stall handler (which is set by `FinalizerController::installFatalStallHandler`); (c) the constant is also written into `RunSnapshot::stallThreshold` for emergency-log reporting. |
| `FatalStallMultiplier` | Defined in `utils/Monitor/Types.hh:7`.                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Lifetime          | Same as other monitor intervals.                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Use count         | 3 (terminal stall test, fatal stall test, snapshot field).                                                                                                                                                                                                                                                                                                                                                                                                            |

### `monitor.bin_count` / `monitor.hist_scaling` (override of `[record]` keys)

`Reader.hh:96-97` lets `[monitor]` re-override `Register::binCount` and
`Register::histScale` after `[record]` was already read. Same downstream
consumers as `[record].bin_count` and `[record].hist_scaling`.

---

## `[lambda]`

Parsed twice: by `Config::limitExtractor` (`Defaults.hh:75-76`, only the
`hist_limits` key) and by `Lambda::extractPhysics` (`Loaders.hh:20-29`, all
the rest plus a re-read of the resolved limits file).

### `lambda.hist_limits` (string, default: `"Lambda_Limits"`)

Resolution rules (`Config::resolveLimitsPath` at `utils/Config/LimitAid.hh:7-15`):
- If contains `/` → use as-is.
- Else if ends in `.toml` → prepend `"configs/"`.
- Else → wrap as `"configs/<name>.toml"`.

| Aspect            | Detail                                                                                                                                                                                                                                                                                                                       |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | Local `limitsFileName` in `limitExtractor`; resolved → `Register::histLimitsFile` (`Defaults.hh:78`).                                                                                                                                                                                                                        |
| Passed to         | (a) `Config::loadLimitsFile(limitsFile, root.particleLimits, root.eventLimits)` (`Defaults.hh:79`); (b) `Lambda::extractPhysics` reads `root.histLimitsFile` again (`Loaders.hh:34, 39`) and `toml::parse_file(...)` on it to load the `[Unvalidated]/[Validated]/[Selected]` per-set tables.                                |
| Active lifetime   | Set during `limitExtractor`; consumed twice (once by loadLimitsFile, once by extractPhysics). Lives in `Register` for the rest of the run but never read after `extractPhysics` returns.                                                                                                                                     |
| Abandoned at      | `Lambda::extractPhysics` returns.                                                                                                                                                                                                                                                                                            |
| Use count         | 2 (loadLimitsFile, extractPhysics).                                                                                                                                                                                                                                                                                          |

### `lambda.delta_mass_gev` (double, default: `0.1`)

| Aspect            | Detail                                                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Lambda::Parameters::massTolerance` (`modules/Lambda/Types.hh:32`).                                                                                               |
| Passed to         | (a) `Lambda::reconstructCandidates` (`modules/Lambda/Reconstruction.hh:66-67`) — accept candidate iff `\|M(p+π) - kLambdaMass\| < massTolerance`; (b) `Lambda::logString` (`modules/Lambda.hh:31`) prints "Mass Tolerance" in the program log. |
| Active lifetime   | Set in `extractPhysics`; consumed in every event.                                                                                                                  |
| Use count         | 2 (cut, log).                                                                                                                                                      |

### `lambda.delta_theta_rad` (double, default: `0.1`)

| Aspect            | Detail                                                                                                                                                                                                                                                                                                |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Lambda::Parameters::thetaTolerance` (`Types.hh:33`). Loader immediately computes `parameters.cosThetaTolerance = std::cos(thetaTolerance)` (`Loaders.hh:24`) into a sibling field.                                                                                                                   |
| Used by           | (a) `Lambda::logString` (`Lambda.hh:32`) prints "Theta Tolerance" in the program log; (b) `Lambda::reconstructCandidates` (`Reconstruction.hh:69-70`) reads `parameters.cosThetaTolerance` (NOT `thetaTolerance`). The angular cut is `theta > -1 - cosThetaTolerance && theta < -1 + cosThetaTolerance`. |
| Active lifetime   | `thetaTolerance` is **write-only after `extractPhysics`** (only `logString` reads it). `cosThetaTolerance` is the real cut input.                                                                                                                                                                      |
| Use count         | `thetaTolerance`: 1 (log only). `cosThetaTolerance`: 1 (cut). REVIEW item 13.                                                                                                                                                                                                                          |

### `lambda.reserved_protons` (integer, default: `20`)

| Aspect            | Detail                                                                                                                                                                                                                                                                  |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Lambda::Parameters::reservedProtons` (`Types.hh:35`).                                                                                                                                                                                                                  |
| Passed to         | (a) `Lambda::reconstructCandidates` (`Reconstruction.hh:48-49`) — `candidateTarget = max(0, protons.size() - reservedProtons)` — caps the number of selected lambda candidates per event; (b) `Lambda::logString` (`Lambda.hh:33`) prints "Reserved Protons" in the log. |
| Use count         | 2 (cut, log).                                                                                                                                                                                                                                                            |

### `lambda.proton_label` (string, default: `"protons"`)

| Aspect            | Detail                                                                                                                                                                                                                                                                                  |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Lambda::Parameters::protonLabel` (`Types.hh:38`). The struct's in-class default is `"Protons"`, but `extractPhysics` always overwrites it with `value_or("protons")` (`Loaders.hh:28`) — note the lowercase. **The in-class default is unreachable.**                                  |
| Passed to         | `Lambda::rootAnalysis` (`Lambda.hh:85`) — `ev[ctx.parameters.protonLabel]` queries `Probe::Event::particles` map. Throws if label is not registered. The label must match the LABEL field (column 0) of one of the `[probe].event_particles` entries (e.g. `"protons"` lowercase). |
| Active lifetime   | Set in `extractPhysics`; read once per analyzed event in `_Lambda_Reconstruction.exe`.                                                                                                                                                                                                  |
| Use count         | 1.                                                                                                                                                                                                                                                                                       |

### `lambda.pion_label` (string, default: `"pions"`)

Same as `proton_label`. Read at `Lambda.hh:86`. Use count: 1.

---

## Limits files (`configs/defaults/Limits.toml` + resolved `lambda.hist_limits`)

Both files share the same per-property-per-level schema, parsed by
`Config::loadLimitsFile` (`utils/Config/Defaults.hh:37-68`):

```toml
[<PropertyName>]                      # e.g. [Mass_Invariant], [Energy_Net]
<LevelName> = [low, high]             # e.g. Moderate = [1.08, 1.15]
```

Recognised property names come from `Physics::tryStringToParticleProperty`
and `Physics::tryStringToEventProperty` (`utils/Physics/TypeAid.hh`); unknown
top-level keys are silently skipped. Recognised level names: `Minute`,
`Small`, `Moderate`, `Large`, `Extreme` (`Config::stringToLevel` at
`utils/Config/TypeAid.hh:21-28`).

| Aspect            | Detail                                                                                                                                                                                                                                                                                                                            |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parsed into       | `Register::particleLimits: ParticleLimits = map<ParticleProperty, map<RangeSize, Bounds>>` and `Register::eventLimits: EventLimits = map<EventProperty, map<RangeSize, Bounds>>` (`Config/Types.hh:130-131`).                                                                                                                       |
| Layered          | `defaults/Limits.toml` is loaded first; user `lambda.hist_limits` is loaded second and overwrites duplicate keys (`Defaults.hh:73, 79`). Both files MUST exist (loadLimitsFile throws if missing).                                                                                                                                |
| Passed to         | `Lambda::extractPhysics` re-parses the user file (NOT the defaults) and reads its `[<HistogramSet>]` tables (`[Unvalidated]`, `[Validated]`, `[Selected]`); for each property in `Recorded_ParticleProperties` (6 of them) it calls `Lambda::resolveBounds<P>` which dispatches to `Lambda::levelBounds(root, prop, level)` to look up the actual numeric bounds in `root.particleLimits` (`Loaders.hh:51-59`, `Parameters.hh:44-97`). The result is stored in `Lambda::Parameters::setParticleLimits`/`setEventLimits` (per-set, per-property). |
| Then              | `Lambda::declareObjects` (`modules/Lambda/Declare.hh:33-67`) reads `parameters.setEventLimits` (for the Multiplicity count histogram bounds) and `parameters.setParticleLimits` (for each property's `TH1D` bounds).                                                                                                              |
| Active lifetime   | `Register::particleLimits`/`eventLimits` are only read by `Lambda::extractPhysics`. After that they sit unused in `Register`. The transformed `Parameters::setParticleLimits`/`setEventLimits` are read only by `declareObjects`. After histograms are declared, the limits maps are never read again.                            |
| Abandoned at      | `Register` limits maps: end of `Lambda::extractPhysics`. `Parameters` limits maps: end of `Lambda::declareObjects`.                                                                                                                                                                                                              |
| Use count         | `Register::particleLimits`: 1 reader (`Lambda::levelBounds` ×N inside `extractPhysics`). `Parameters::setParticleLimits`: 1 reader (`declareObjects`).                                                                                                                                                                            |

### Limits file `[<HistogramSet>]` tables

The user limits file additionally has per-set tables (`[Unvalidated]`,
`[Validated]`, `[Selected]`) that loadLimitsFile **does not parse** — those
are silently skipped because `tryStringToParticleProperty("Unvalidated")`
fails. Only `Lambda::extractPhysics`'s second parse of the user file reads
those (`Loaders.hh:39-61`).

The set tables can use:
- `default = "Moderate"` — picks a level from the per-property tables.
- `Mass_Invariant = "Large"` — overrides per-property level for that set.
- `Mass_Invariant = [1.08, 1.15]` — explicit bounds, bypassing the level
  system. Resolved by `Lambda::explicitBounds` (`Parameters.hh:29-42`).

This is the only place where the level-vs-explicit dispatch happens
(`Lambda::boundsFromNode` at `Parameters.hh:70-75`).

---

## Shared / cross-cutting values (coupling points)

These keys are read from one TOML key but populate **two or more** unrelated
sinks, creating implicit coupling between modules.

| TOML key                | Sinks                                                              | Coupling impact                                                                                                                                  |
| ----------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `events.event_count`    | `Events::eventCount` AND `Watch::nEvents`                          | Two long-lived state holders for one user input. AsyncLogger reads `Watch`; reconstruction event-count fallback writes to BOTH (`Lambda_Reconstruction.cc:45, 51`). Diverge if either is mutated. |
| `events.nThreads`       | `Events::nThreads` AND `Watch::n_threads`                          | `Events::nThreads` is dead post-parse; `Watch::n_threads` is what every driver actually reads.                                                   |
| `record.bin_count`      | `Register::binCount` (set by `[record]`, overridable by `[monitor]`) | Two TOML sections write the same field — order-dependent behaviour. Last reader wins.                                                            |
| `record.hist_scaling`   | `Register::histScale` (same dual-section override)                  | Same as `bin_count`.                                                                                                                              |
| `record.serial`         | `Watch::serial` then `Register::outName/logName/etc.` via `serialStr` | A single integer changes the actual output file paths. Renaming `serial` mid-run would not invalidate path templates — they are baked at startup. |
| `record.paths.directory`| Composes all of `rootDirectory`, `logDirectory`, `checkpointDirectory` (transitively → 6 path templates) | Tight coupling between path scheme and 6 derived strings, all set in one function pass.                                                          |
| `record.file.energy`/`events` | Both `fileTitle` AND `threadStatDirectory` (`Reader.hh:150-152`)  | The threads-log directory name and the output file name share boolean toggles — surprising if you only meant to change file names.                |
| `lambda.hist_limits`    | `Register::histLimitsFile` AND parsed twice (loadLimitsFile + Lambda::extractPhysics) | The same file is opened/parsed twice for different schemas (per-property vs. per-set tables).                                                     |

---

## Dead / unused config keys

Keys the codebase *can* parse but does not act on, given the current driver
call paths.

| Key                                  | Status                                                                                                       |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| `events.pythia` / `events.probe`     | Parsed into `Events::isPythia`. **No reader.** Drivers do not branch on this.                                |
| `pythia.beam_energy`                 | `configurePythia` is never called by any driver. Dead.                                                       |
| `pythia.cmnd_file`                   | Same — dead. Drivers hardcode `pythia.readFile("configs/Lambda_Reconstruction.cmnd")`.                        |
| `pythia.seed`                        | Same — dead.                                                                                                  |
| `record.metadata.dataset_name` (and siblings) | `Meta::capture` reads `cfg["metadata"]` (top-level), but project TOMLs put it under `[record.metadata]`. Silently ignored. |
| `Register::inputPath`                | Field exists (`Types.hh:117`), populated by `readInputSection` (referenced by `Reader.hh` only via `readPathsAndFile`), but `_Lambda_Reconstruction.cc` reads `probeConfig.inputFile` instead. Stale post-Pipeline-A migration. |
| `Lambda::SpecsArray` typedef         | Was used by deleted `Lambda::inputSchema`. No remaining callers.                                               |
| `Probe::ScalarSpec` (and `[probe]` scalar plumbing) | Parsed nowhere from TOML; struct exists in `Probe/Types.hh:42-47` and is threaded through `runParallel` signatures, but no driver supplies any. |
| `Lambda::Recording.hh:28` `for (auto& tree : object.trees)` | Iterates an always-empty vector; `RootObjects::trees` is never populated post-Pipeline-A. |

---

## Potential restructuring

### Shotgun coupling

1. **`record.event_count` and `record.nThreads` write to two structs each.**
   The `Events`/`Watch` mirror is a workaround for `Watch` being the only
   struct shared with `AsyncLogger`. Either drop the duplicate from
   `Events` (since it's never read) or make `Events` the single source of
   truth and change `AsyncLogger::start` to take both. Today the field-pair
   structure invites bugs where one side is updated and the other isn't —
   exactly what `_Lambda_Reconstruction.cc:45` does
   (`probeConfig.eventConfig.eventCount = logParams.nEvents = ...`,
   manually keeping them in sync).

2. **`record.file.energy/events` controls *two* unrelated output paths.**
   `Reader.hh:150-152` reuses `fileEnergy`/`fileEvents` for the threads log
   directory name (`threads_<energy>_<events>`). Toggling one toggles
   both. Decouple by giving the threads directory its own naming key.

3. **`record.bin_count` / `record.hist_scaling` are settable from two
   sections.** `[record]` then `[monitor]` overrides. Either pick a single
   home (architecturally `[record]` is the histogram-config home; `[monitor]`
   shouldn't touch it) or document the override semantics (it is
   undocumented today).

### Large structs that should be split

1. **`Config::Register` is a god-object** (`Types.hh:115-134`, 18 fields).
   Distinct concerns:
   - Output ROOT artifact: `outFile`.
   - Histogram config: `binCount`, `histScale`, `histLimitsFile`,
     `particleLimits`, `eventLimits`.
   - Path templates: `rootDirectory`, `logDirectory`, `checkpointDirectory`,
     `outName`, `logName`, `runStatName`, `threadStatDirectory`,
     `checkpointOutName`, `checkpointLogName`, `fileTitle`, `beamEnergy`.
   - Stale: `inputPath` (dead post-Pipeline-A).
   
   `AsyncLogger::start` (`Logger.hh:26`) takes the whole `Register&` to read
   `runStatName`, `threadStatDirectory`, `fileTitle` — three of 18 fields.
   `Lambda::extractPhysics` and `Lambda::declareObjects` take the whole
   `Register&` to read the limits/binCount fields. A `HistConfig` split
   (REVIEW item 11) would let consumers depend on what they actually need.

2. **`Config::Watch` mixes counters with pacing** (`Types.hh:79-112`).
   - Atomic-mutated counters: `iEvent` (atomic), `n_real_events` (under
     `eventMutex_`), `elapsed`.
   - Set-once and never mutated after `configuration()`: `serial`,
     `sr_padding`, `nEvents`, `n_digits`, `n_threads`, `print_interval`,
     `bar_interval`, `check_interval`, `heartbeat_interval`,
     `terminal_refresh_interval`, `program_stall_threshold`, `start`.
   
   The set-once group could be a `const RunPacing` initialised once and
   passed by `const&` everywhere. The mutation surface shrinks to 3 fields,
   which matches what `recordEvent`/`freeze` actually touch.

3. **`Lambda::Parameters` mixes physics cuts with collection labels.**
   `protonLabel`/`pionLabel` are I/O concerns; `massTolerance`,
   `thetaTolerance`, `cosThetaTolerance`, `reservedProtons` are physics
   concerns; `setParticleLimits`/`setEventLimits` are histogram-binning
   concerns. The label fields belong with `Probe`/`Config`, not with the
   physics struct.

### Values that could be constants instead

1. **`record.serial` and `record.sr_padding`** are read once in
   `readPathsAndFile` to format `serialStr`, then survive in `Watch` only
   for `serial` to be printed in two log lines. Could be a stack local in
   `readPathsAndFile`; promote `serialStr` itself to `Register::serialStr`
   if the log lines need it (today they re-derive it from `serial`).

2. **`record.paths.*` and `record.file.*` booleans** are entirely local to
   `readPathsAndFile`. They're already discarded — no struct field. Good.

3. **`record.bin_count`** is read once during `declareObjects`. After that
   it sits idle in `Register::binCount` for the rest of the run.
   `Register::binCount` could be moved out of long-lived state.

4. **All `monitor.*` interval values** are copied into `AsyncLogger`'s
   private fields at `start()` and never re-read from `Watch`. The Watch
   copies (`Watch::print_interval`, `bar_interval`, `check_interval`,
   `heartbeat_interval`, `terminal_refresh_interval`,
   `program_stall_threshold`) survive only so `Render.hh:75-77` can echo
   three of them in the log file. Move the values into `AsyncLogger`
   directly (or into a `RunPacing` struct shared by both) — no need to
   keep them in `Watch`.

### Wrong type for semantic meaning

1. **`events.pythia`/`events.probe` are bools** but encode a 2-way enum
   (run-mode = Pythia | Probe). The `pythia ? : (probe ? !: true)` logic
   in `Reader.hh:45` is awkward because two bools express one choice. An
   enum (`enum class RunMode { Pythia, Probe }`) parsed from a single
   `events.mode = "pythia"` would be clearer and impossible to set
   inconsistently.

2. **`probe.event_particles` `spec` integer** (0/1/2) encodes the coord
   system. `enum class CoordKind { Cartesian, PtEtaPhiE, PtEtaPhiM }` would
   make TOML `spec = "cartesian"` self-documenting. Currently the user has
   to remember `0=Cartesian` from comments.

3. **TOML branch type letters** (`"D"`, `"I"`, etc., second element of each
   momenta/index pair) reuse ROOT's TBranch leaf-list convention. They map
   to `Probe::BranchType` enum via `BranchControl::detectType(char)`
   (`utils/Probe/BranchControl.hh:51-62`). Could be `"double"`/`"int32"` for
   readability; the enum is the source of truth either way.

4. **`monitor.terminal_refresh_interval` and `monitor.program_stall_threshold`
   are doubles in minutes**, then converted to `Seconds` via
   `Seconds(int(60 * tr))` (`Reader.hh:90, 94`). The TOML unit (minutes) is
   not in the key name; users have to read code to know the magnitude.
   `monitor.program_stall_threshold_minutes = 5.0` is ugly but
   unambiguous; alternatively store as `string` `"5min"`/`"30s"` and parse.

5. **`monitor.heartbeat_interval` is an integer in microseconds**, while
   the other two are doubles in minutes. Inconsistent unit treatment.

### Suggested struct groupings

```cpp
// Values that DON'T change after configuration() — pass by const&
struct RunIdentity { int serial; std::size_t sr_padding; std::string serialStr; };
struct RunSize     { std::size_t nEvents; std::size_t nThreads; };

struct RunPacing {  // owned by AsyncLogger; not in Watch
    std::size_t print_interval;
    std::size_t bar_interval;
    std::size_t check_interval;
    Config::uSeconds heartbeat_interval;
    Config::Seconds  terminal_refresh_interval;
    Config::Seconds  program_stall_threshold;
};

struct RunCounters {  // the only thing that mutates after start()
    std::atomic<std::size_t> iEvent;
    std::size_t n_real_events;     // protected by eventMutex_
    Config::TimePoint start;
    Config::uSeconds elapsed;
    std::mutex eventMutex_;
};

// Replaces Register
struct OutputArtifact { TFile* outFile; TString outName; TString fileTitle; TString beamEnergy; };
struct OutputLogPaths { TString logName; TString runStatName; TString threadStatDirectory; TString checkpointOutName; TString checkpointLogName; };
struct HistConfig     { Int_t binCount; Double_t histScale; TString histLimitsFile; ParticleLimits particleLimits; EventLimits eventLimits; };

// Replaces Lambda::Parameters
struct LambdaCuts   { Double_t massTolerance; Double_t cosThetaTolerance; std::size_t reservedProtons; };
struct LambdaLabels { std::string protonLabel; std::string pionLabel; };
struct LambdaBins   { std::map<HistogramSet, std::map<Physics::ParticleProperty, Config::Bounds>> particle; std::map<HistogramSet, std::map<Physics::EventProperty, Config::Bounds>> event; };
```

The split makes mutation surfaces explicit (`RunCounters` is the only
non-const argument the orchestrators need) and lets each function depend on
the smallest sufficient struct.

### Unify run-mode dispatch

`Events::isPythia` is parsed but never read. The reason: each driver knows
its own run mode from its source file (its `main()` either constructs
`Pythia8::PythiaParallel` or doesn't). The mode-dispatch is **at link
time, not config time** — one binary per mode.

Either remove `events.pythia`/`events.probe` (0 readers today) or actually
use it: a single `_Lambda` driver that branches on `Events::isPythia` would
let the same binary serve both generation and reconstruction modes. Today
the duplicate driver TUs are the alternative.

---

## Summary table — quick lookup

| TOML path                                  | Field                                  | Use count | Status     |
| ------------------------------------------ | -------------------------------------- | --------: | ---------- |
| `events.pythia` / `events.probe`           | `Events::isPythia`                     | 0         | dead       |
| `events.event_count`                       | `Events::eventCount` + `Watch::nEvents`| ~13       | active     |
| `events.nThreads`                          | `Events::nThreads` + `Watch::n_threads`| 2         | active (Events side dead) |
| `probe.input_file`                         | `ProbeConfig::inputFile`               | 4         | active     |
| `probe.event_particles`                    | `ProbeConfig::particles`               | 1         | active     |
| `pythia.*`                                 | `PythiaConfig::*`                      | 0         | dead       |
| `record.serial`                            | `Watch::serial`                        | 3         | active     |
| `record.sr_padding`                        | `Watch::sr_padding`                    | 1         | active     |
| `record.bin_count`                         | `Register::binCount`                   | 1         | active     |
| `record.hist_scaling`                      | `Register::histScale`                  | 4         | active     |
| `record.paths.directory`                   | `Register::rootDirectory` (transitive) | 1         | active     |
| `record.paths.output_log_directory`        | `Register::logDirectory` (transitive)  | 1         | active     |
| `record.paths.checkpoint_directory`        | `Register::checkpointDirectory` (trans)| 1         | active     |
| `record.paths.serialDirectory`             | local bool                             | 1         | active     |
| `record.paths.logInSubDir`                 | local bool                             | 1         | active     |
| `record.paths.checkpointsInSubDir`         | local bool                             | 1         | active     |
| `record.file.prefix`                       | `Register::fileTitle` (transitive)     | ~9        | active     |
| `record.file.serial`                       | local bool                             | 1         | active     |
| `record.file.energy`                       | local bool                             | 1         | active     |
| `record.file.events`                       | local bool                             | 1         | active     |
| `record.metadata.*`                        | `Meta::Record::*`                      | 0         | **dead — wrong key path** |
| `monitor.print_interval`                   | `Watch::print_interval`                | 1         | active     |
| `monitor.check_interval`                   | `Watch::check_interval`                | 2         | active     |
| `monitor.heartbeat_interval`               | `Watch::heartbeat_interval`            | 2         | active     |
| `monitor.terminal_refresh_interval`        | `Watch::terminal_refresh_interval`     | 1         | active     |
| `monitor.program_stall_threshold`          | `Watch::program_stall_threshold`       | 3         | active     |
| `monitor.bin_count` / `monitor.hist_scaling` | `Register::binCount/histScale` (override) | 1+1   | active     |
| `lambda.hist_limits`                       | `Register::histLimitsFile`             | 2         | active     |
| `lambda.delta_mass_gev`                    | `Parameters::massTolerance`            | 2         | active     |
| `lambda.delta_theta_rad`                   | `Parameters::thetaTolerance` + `cosThetaTolerance` | 1+1 | active (theta is log-only) |
| `lambda.reserved_protons`                  | `Parameters::reservedProtons`          | 2         | active     |
| `lambda.proton_label`                      | `Parameters::protonLabel`              | 1         | active     |
| `lambda.pion_label`                        | `Parameters::pionLabel`                | 1         | active     |
| `[<HistogramSet>]` in limits file          | `Parameters::setParticleLimits` etc.   | 1         | active     |
| `[<Property>].<Level>` in limits file      | `Register::particleLimits` etc.        | 1         | active (read by levelBounds) |
