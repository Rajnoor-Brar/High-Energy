# Proposal — current phased plan

Source-truth phased plan derived from the active tree on 2026-04-28. Archive
files were reviewed for context only and do not drive the ordering below.

## Summary

- Scope: phased source changes only; this document records the current
  implementation plan from the live tree, not from older backlog wording.
- Ordering: lowest-risk naming and dead-code cleanup first, then file and
  namespace reshapes, then structural and behavioural additions, then
  cross-thread robustness.
- Normalized source truth: `Config::Log` / `Config::Root` currently appear 46
  times across 14 active files, `levelName` has 2 live call sites,
  `ThetaTolerance` is still read by `Lambda::logString`, `Monitor/Format.hh`
  still has 4 include touchpoints, the real default limits fallback is
  `configs/defaults/Limits.toml`, and the late-stage three-pass note belongs to
  `Lambda::fillCandidates`, not `Record::fillCandidates`.

## Phase 1 — Naming, aliases, dead code

### 1. Retire `Log` / `Root` aliases

- Files and lines: `utils/Config/Types.hh:134-138`; `_Lambda_Parallel.cc:20-22`; `_Lambda_Reconstruction.cc:20-21`; `_Lambda_Data.cc:21-23`; `_Lambda_Test.cc:19-20`; `tests/test_rootAnalysis_smoke.cc:56-57`; `modules/Lambda.hh:33`; `modules/Lambda/Context.hh:6,25,33`; `modules/Lambda/Parameters.hh:55,68,82,89,159,195,266`; `utils/Monitor/Render.hh:59-60,100-101,111-112,144-145,153`; `utils/Monitor/Snapshot.hh:41`; `utils/Monitor/Logger.hh:27,57,103`; `utils/Record/Finalizer.hh:44,81,108-109`; `utils/Record/Meta.hh:115-116`
- Dependencies: None. Land before the `HistConfig` / `Register` split to avoid alias churn on top of structural churn.
- Effort: one-day
- READY TO IMPLEMENT: Replace every active `Config::Log` / `Config::Root` use with `Watch` / `Register`, delete `using Log = Watch;` and `using Root = Register;` from `utils/Config/Types.hh`, and update the stale alias comment in `modules/Lambda/Context.hh`. Validate with `rg -n 'Config::Log|Config::Root' modules utils tests _Lambda_*.cc` returning no active hits.

### 2. Drop `Lambda::propertyName` passthrough wrappers

- Files and lines: `modules/Lambda/TypeAid.hh:13-15,21,25`; `modules/Lambda/Parameters.hh:58,71,91`
- Dependencies: Independent. If item 1 is already open in the same branch, do this sweep in the same pass.
- Effort: half-day
- READY TO IMPLEMENT: Delete both `Lambda::propertyName` wrappers. Replace the three `Parameters.hh` call sites with `Physics::particlePropertyName` / `Physics::eventPropertyName`, replace the `propertyAlias` fallthroughs in `TypeAid.hh` with the same direct calls, and keep all emitted strings unchanged.

### 3. Delete `Lambda::levelName`

- Files and lines: `modules/Lambda/TypeAid.hh:27-36`; `modules/Lambda/Parameters.hh:63,76`; canonical helper `utils/Config/TypeAid.hh:10-19`
- Dependencies: After item 2 only if `TypeAid.hh` is already being edited; otherwise independent.
- Effort: half-day
- READY TO IMPLEMENT: Replace both error-message call sites in `modules/Lambda/Parameters.hh` with `Config::levelToString`, delete `Lambda::levelName`, and keep the thrown messages otherwise unchanged.

### 4. Move `dataLogString` beside `logString`

- Files and lines: `modules/Lambda/Reconstruction.hh:7-12`; destination `modules/Lambda.hh:16-25`; consumer `_Lambda_Data.cc:58`
- Dependencies: Independent.
- Effort: half-day
- READY TO IMPLEMENT: Move `dataLogString()` out of `modules/Lambda/Reconstruction.hh` and place it beside `logString()` in `modules/Lambda.hh`. Keep the signature and text identical, delete the old definition, and leave `_Lambda_Data.cc` calling `Lambda::dataLogString()`.

### 5. Delete the redundant `Lorentz` aliases and keep the canonical one in `Physics`

- Files and lines: canonical `utils/Physics/Types.hh:14`; redundant aliases `utils/Probe/Types.hh:15`; `utils/Record/Types.hh:19`; `utils/Record/Extract.hh:23`; `modules/Lambda/Types.hh:18`; downstream Lambda users resolve through `modules/Lambda/Reconstruction.hh:15-22,34-100` and `modules/Lambda/Recording.hh:25-42`
- Dependencies: Independent. Do this before Phase 2 namespace moves so the type path is already simplified.
- Effort: half-day
- READY TO IMPLEMENT: Execute approved Option B. Delete the four redundant alias definitions, keep `Physics::Lorentz` as the canonical type, and update files that still want a short local name to use `using Physics::Lorentz` locally rather than re-exporting through other module types. Validate with `rg -n 'using Lorentz =' modules utils` leaving only `utils/Physics/Types.hh:14`.

### 6. Rename `ThetaTolerance` to `thetaTolerance`

- Files and lines: `modules/Lambda/Types.hh:47-59`; `modules/Lambda/Parameters.hh:269-271`; `modules/Lambda.hh:22-24`; downstream cosine use `modules/Lambda/Reconstruction.hh:76-78`
- Dependencies: Independent. Land before any later `Parameters` file split so the rename does not span multiple new headers.
- Effort: half-day
- READY TO IMPLEMENT: Rename `Parameters::ThetaTolerance` to `thetaTolerance`, update TOML extraction and the `Lambda::logString` readout, and keep `cosThetaTolerance` as the only value used by reconstruction logic after extraction. Add a short comment only if the raw angle remains solely for config/log visibility.

### 7. Rename `Watch` snake_case interval fields to camelCase

- Files and lines: `utils/Config/Types.hh:76-109`; `utils/Config/Reader.hh:96-106`; `utils/Config/Defaults.hh:91-96`; `utils/Config/TypeAid.hh:55-57`; `utils/Monitor/Logger.hh:41-46,336-338`; `utils/Monitor/Render.hh:76`
- Dependencies: After item 1. Land before Phase 4 so the later atomic pass is not mixed with field renames.
- Effort: one-day
- READY TO IMPLEMENT: Rename `heartbeat_interval` -> `heartbeatInterval`, `terminal_refresh_interval` -> `terminalRefreshInterval`, and `program_stall_threshold` -> `programStallThreshold` everywhere they are declared, loaded, copied, or rendered. Leave `iEvent` and `nEvents` unchanged. Validate with `rg -n 'heartbeat_interval|terminal_refresh_interval|program_stall_threshold' modules utils tests _Lambda_*.cc` returning no active hits.

## Phase 2 — File and namespace restructure

### 1. Rename `Probe/Schema.hh` to `Probe/BranchControl.hh` and rename `detail` to `BranchControl`

- Files and lines: `utils/Probe/Schema.hh:1-215`; `utils/Probe/VecReader.hh:9,40-47,75`; `utils/Probe/FlatReader.hh:8,29-30,40,45-46,104,220`; `utils/Probe/Event.hh:9`; `utils/Probe/Parallel.hh:24,46,68,73,87,92,129`; `utils/Probe.hh:4`
- Dependencies: After Phase 1 item 5 if the Lorentz alias cleanup is in flight; otherwise independent.
- Effort: one-day
- READY TO IMPLEMENT: Rename `utils/Probe/Schema.hh` to `utils/Probe/BranchControl.hh`, rename `namespace Probe::detail` to `namespace Probe::BranchControl`, and update all includes and qualified helper calls accordingly. Keep the helper bodies unchanged in this phase. Validate that no active `Schema.hh` include or `detail::` Probe helper reference remains.

### 2. Nest `Extract` and `Meta` under `Record`

- Files and lines: `utils/Record/Extract.hh:21-183`; `utils/Record/Meta.hh:21-250`; `utils/Record/Types.hh:41-48`; `utils/Record/Histogram.hh:85-94`; `utils/Record/Finalizer.hh:61,66,115`; `_Lambda_Reconstruction.cc:84-86`
- Dependencies: After Phase 1 item 5 if the Lorentz alias cleanup changes `Record/Extract.hh`; otherwise independent.
- Effort: one-day
- READY TO IMPLEMENT: Move both top-level namespaces under `namespace Record`, update all alias types and call sites to `Record::Extract::*` / `Record::Meta::*`, and keep header filenames stable. Validate with `rg -n '\\bMeta::|\\bExtract::' modules utils tests _Lambda_*.cc` showing only the nested `Record::` forms in active source.

### 3. Fold `Monitor/Format.hh` into `Monitor/Snapshot.hh`

- Files and lines: `utils/Monitor/Format.hh:1-23`; `utils/Monitor/Snapshot.hh:11,47`; `utils/Monitor/Logger.hh:14`; `utils/Monitor/Render.hh:17`; `utils/Monitor.hh:4`
- Dependencies: Independent.
- Effort: half-day
- READY TO IMPLEMENT: Move `updatedETA` into `utils/Monitor/Snapshot.hh`, update the include graph so `Logger.hh`, `Render.hh`, and `Monitor.hh` no longer include `Monitor/Format.hh`, and delete the file. Validate that `rg -n 'Monitor/Format.hh' modules utils tests _Lambda_*.cc` returns no active hits.

### 4. Split `modules/Lambda/Parameters.hh` into `Parameters.hh`, `Loaders.hh`, and `Declare.hh`

- Files and lines: `modules/Lambda/Parameters.hh:27-38,40-103,105-121,123-157,159-262,264-309`; `modules/Lambda.hh:9-12`; `_Lambda_Parallel.cc:27-29`; `_Lambda_Reconstruction.cc:32-35,68,77`; `_Lambda_Data.cc:33`; `_Lambda_Test.cc:28-30`; `tests/test_rootAnalysis_smoke.cc:64-67,83`
- Dependencies: After Phase 1 items 2, 3, and 6 so the split does not carry forward dead wrappers or the old `ThetaTolerance` name.
- Effort: one-day
- READY TO IMPLEMENT: Split the file mechanically using the current line ranges. Keep `modules/Lambda/Parameters.hh` for `Recorded_ParticleProperties`, `kTreeEnabledSets`, `explicitBounds`, `levelBounds`, `boundsFromNode`, and `resolveBounds`; move `loadInputSection`, `loadCandidatesSection`, and `extractPhysics` into new `modules/Lambda/Loaders.hh`; move `inputSchema`, `declareDataObjects`, `shouldWriteTree`, and `declareObjects` into new `modules/Lambda/Declare.hh`. Update `modules/Lambda.hh` to include the new headers and keep all signatures unchanged in this phase.

### 5. Move `_Lambda_Data.cc` shutdown to `FinalizerController` with a `preCloseHook`

- Files and lines: `_Lambda_Data.cc:48-60`; `utils/Record/Finalizer.hh:40-116`; `modules/Lambda.hh:16-25`
- Dependencies: After Phase 2 item 4 only if `Lambda::dataLogString` moved into `modules/Lambda.hh` is part of the same branch; otherwise independent.
- Effort: half-day
- READY TO IMPLEMENT: Add an optional `std::function<void()> preCloseHook = {}` to `Record::FinalizerController`, invoke it after `writeAll` / metadata writes and before `outFile->Write()` / `Close()`, and convert `_Lambda_Data.cc` to use the controller instead of the inline tail. `_Lambda_Data.cc` should pass a hook that runs both `BuildIndex("event_index")` calls and should reuse `Lambda::dataLogString()` through the controller’s program-log callback path.

## Phase 3 — Structural additions and behavioural changes

### 1. Add `userEvents` to `Config::Events` and remove the reconstruction driver's TOML re-parse

- Files and lines: `utils/Config/Types.hh:45-49`; `utils/Config/Reader.hh:41-53`; `utils/Config.hh:17-46,96-102`; `_Lambda_Reconstruction.cc:22,48-68`
- Dependencies: After Phase 2 item 4 if `extractPhysics` / declaration helpers have already moved out of `Parameters.hh`; otherwise independent.
- Effort: half-day
- READY TO IMPLEMENT: Add `bool userEvents = false;` to `Config::Events`, set it in `readEventsSection` by checking whether `[events].event_count` or legacy `[run].event_count` is present, and expose an `extractConfiguration(configPath, project, Events&, Watch&, Register&)` overload so the reconstruction driver can read it directly. Replace the inline TOML re-parse in `_Lambda_Reconstruction.cc` with the existing `logParams.nEvents` when `events.userEvents` is true, otherwise fall back to `Probe::resolveEventCount(inputPath)` and then the existing full-scan fallback.

### 2. Add TeX axis labels through `Physics::particlePropertyTeX`

- Files and lines: `utils/Physics/Types.hh:51-75`; `utils/Physics/Properties.hh:10-16`; `modules/Lambda/Parameters.hh:225-245`
- Dependencies: After Phase 2 item 4 if histogram declaration has moved into `Declare.hh`; otherwise independent.
- Effort: half-day
- READY TO IMPLEMENT: Extend `Physics::ParticleTraits` with a `tex` field, add `Physics::particlePropertyTeX(ParticleProperty)` alongside the existing name helpers, and use the TeX string only for histogram titles and axis labels inside Lambda object declaration. Keep ROOT object names and branch names on `Physics::particlePropertyName`.

### 3. Replace the dead compile-time tree gate with runtime tree configuration

- Files and lines: `modules/Lambda/Types.hh:15-23,40-59`; `modules/Lambda/Parameters.hh:36-38,141-156,178-191,200-257`; `modules/Lambda/Recording.hh:25-43`; `utils/Record/Types.hh:32-36,51-65`; `utils/Record/Histogram.hh:25-47,78-83,141-157`
- Dependencies: After Phase 2 item 4 so the declaration and loader code is already split cleanly.
- Effort: one-day
- READY TO IMPLEMENT: Add `[lambda.analysis]` with `writeTree = ["Selected"]` parsed into a runtime `std::vector<HistogramSet>` on the Lambda-side configuration object. Delete `kTreeEnabledSets` and `shouldWriteTree`, and drive tree declaration and filling from the parsed runtime set instead of the current empty compile-time gate. Keep the existing `TreeRecord`, `RootObjects::trees`, `Record::declareTree`, `Record::fill`, and `Record::write` path alive so the configured trees actually appear in the ROOT output. If `kHistogramSetCount` is removed, replace its size uses with `kHistogramSetMap.size()` or equivalent enum-safe size logic.

### 4. Split `HistConfig` out of `Register` and remove path-only intermediates that never escape config loading

- Files and lines: `utils/Config/Types.hh:112-131`; `utils/Config/Reader.hh:70-80,84-109,112-181`; `utils/Config/Defaults.hh:70-99`; `utils/Config.hh:17-37,85-101`; `utils/Monitor/Logger.hh:27-53`; `utils/Monitor/Render.hh:59-165`; `utils/Record/Finalizer.hh:44-115`; `_Lambda_Reconstruction.cc:25`; `modules/Lambda/Parameters.hh:55-103,159-199,264-306`
- Dependencies: After Phase 1 item 1 and Phase 2 item 4. This is the first large structural consumer rewrite and should not compete with alias churn or the old monolithic `Parameters.hh`.
- Effort: two-day
- READY TO IMPLEMENT: Create `Config::HistConfig { binCount, histScale, histLimitsFile, particleLimits, eventLimits }` and move those five fields out of `Register`. Audit the remaining path fields one by one: remove `rootDirectory`, `logDirectory`, and `checkpointDirectory` if they are only transient construction locals inside `Config::Reader.hh`; keep the externally consumed survivors `beamEnergy`, `outName`, `logName`, `runStatName`, `threadStatDirectory`, `checkpointOutName`, `checkpointLogName`, and `fileTitle`; move `inputPath` out of `Register` alongside event/input configuration. Update consumers to take the narrowest surviving config object they need.

### 5. Wire `cmnd_file` through the normal configuration extraction path

- Files and lines: `utils/Config/Types.hh:52-56`; `utils/Config/Reader.hh:184-189`; `utils/Config.hh:48-70`; `_Lambda_Parallel.cc:18-24`; `_Lambda_Data.cc:19-25`; `_Lambda_Test.cc:17-25`
- Dependencies: Independent, but cleaner after Phase 3 item 4 if configuration structs are already narrower.
- Effort: half-day
- READY TO IMPLEMENT: Thread `Config::PythiaConfig::cmndFile` through the standard extraction path used by the drivers so `_Lambda_Parallel.cc`, `_Lambda_Data.cc`, and `_Lambda_Test.cc` stop hardcoding `"configs/Lambda_Reconstruction.cmnd"`. Keep the existing beam-energy and seed handling consistent with the existing `readPythiaSection` / `configurePythia` behaviour.

### 6. Replace the hardcoded default limits path with the real optional fallback

- Files and lines: `utils/Config/Defaults.hh:37-80`; `modules/Lambda/Parameters.hh:281-286`; actual fallback file `configs/defaults/Limits.toml:1-90`
- Dependencies: After Phase 3 item 4 if `HistConfig` owns the limits state; otherwise independent.
- Effort: half-day
- READY TO IMPLEMENT: Replace the nonexistent hardcoded `configs/General_Limits.toml` fallback with the actual `configs/defaults/Limits.toml` path. Load struct-init defaults first, attempt to merge the default limits file if it exists, warn and continue with zero/default limits if it does not, then overlay the resolved user limits file during extraction. Stop treating the default fallback as a hard requirement and keep the path spelling case-correct.

## Phase 4 — Robustness

### 1. Remove `eventMutex_` and unify worker-updated `Watch` state under atomics

- Files and lines: `utils/Config/Types.hh:77-108`; `utils/Config/TypeAid.hh:34-62`; `modules/Lambda.hh:36,50,72,85,96,121`; `utils/Monitor/Snapshot.hh:41-53`; `utils/Monitor/Render.hh:68-78`; `utils/Record/Meta.hh:161-164`; `tests/test_rootAnalysis_smoke.cc:94-98`
- Dependencies: After Phase 1 item 7 so the interval-field rename does not mix with the thread-safety rewrite.
- Effort: one-day
- READY TO IMPLEMENT: Convert the remaining worker-written `Watch` fields to atomic-backed state, remove `eventMutex_`, and update `recordEvent`, `freeze`, snapshot creation, and metadata capture accordingly. `iEvent` is already atomic; the active audit says the only other worker-written fields today are `nRealEvents` and `elapsed`. Keep all other `Watch` fields plain because they are configured before worker threads start.

## Late Stage

- Precompiled header for ROOT / Pythia8 / toml++.
- TThreadedObject-backed input-file pool for `Probe::runParallel`.
- `event_particles` TOML schema after Investigation E in [REVIEW.md](REVIEW.md).
- `Probe::runParallel` worker-loop dedup after Phase 4 lands (`utils/Probe/Parallel.hh:53-61,98-106`).
- `Lambda::fillCandidates` three-pass traversal (`modules/Lambda/Recording.hh:35-43`): either document why the three passes stay or combine them into one pass.
- `Record::write` / `writeToDir` deduplication (`utils/Record/Histogram.hh:128-159`).
