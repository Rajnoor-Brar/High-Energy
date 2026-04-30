# PROPOSAL: Project Refactor and Enhancement

This document outlines a phased plan to refactor the High-Energy project, improve its structure, and enhance its configurability and robustness.

## Phase 1 — Naming, aliases, dead code
*Lowest risk, no logic changes.*

### 1.1 Retire Log/Root aliases (REVIEW 1 / ROADMAP 6)
- **Directives**: Delete `using Log = Watch` and `using Root = Register` from `utils/Config/Types.hh:137-138`.
- **Sweep**: Replace all `Config::Log` with `Config::Watch` and `Config::Root` with `Config::Register` across the codebase.
- **Files**: `utils/Config/Types.hh`, `_Lambda_Data.cc`, `_Lambda_Parallel.cc`, `_Lambda_Reconstruction.cc`, `_Lambda_Test.cc`, `modules/Lambda.hh`, `modules/Lambda/Context.hh`, `modules/Lambda/Parameters.hh`, `modules/Lambda/Reconstruction.hh`, `utils/Config/Reader.hh`, `utils/Config/Defaults.hh`, `utils/Monitor/Logger.hh`, `utils/Record/Meta.hh`, etc.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 1.1: Delete Log/Root aliases in `utils/Config/Types.hh` and replace all occurrences with Watch/Register."

### 1.2 Drop Lambda::propertyName passthrough wrappers (REVIEW 2)
- **Directives**: Delete `Lambda::propertyName` wrappers from `modules/Lambda/TypeAid.hh:13-15`.
- **Sweep**: Update 5 call sites in `modules/Lambda/Parameters.hh` to call `Physics::particlePropertyName` or `Physics::eventPropertyName` directly.
- **Files**: `modules/Lambda/TypeAid.hh`, `modules/Lambda/Parameters.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 1.2: Remove `Lambda::propertyName` passthroughs and update call sites to use `Physics::*PropertyName`."

### 1.3 Delete Lambda::levelName (REVIEW 3)
- **Directives**: Delete `Lambda::levelName` from `modules/Lambda/TypeAid.hh:27-36`.
- **Sweep**: Replace the single call site in `modules/Lambda/Parameters.hh:67` with `Config::levelToString`.
- **Files**: `modules/Lambda/TypeAid.hh`, `modules/Lambda/Parameters.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 1.3: Delete `Lambda::levelName` and update call site in `Parameters.hh`."

### 1.4 Move dataLogString (REVIEW 4)
- **Directives**: Move `dataLogString` from `modules/Lambda/Reconstruction.hh:6-12` to `modules/Lambda.hh` alongside `logString`.
- **Files**: `modules/Lambda/Reconstruction.hh`, `modules/Lambda.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 1.4: Move `dataLogString` to `modules/Lambda.hh`."

### 1.5 Delete redundant Lorentz aliases (REVIEW 5)
- **Directives**: Delete `using Lorentz = ...` aliases from `utils/Probe/Types.hh:15`, `utils/Record/Types.hh:19`, `utils/Record/Extract.hh:23`, and `modules/Lambda/Types.hh:18`.
- **Canonical**: Use `Physics::Lorentz` from `utils/Physics/Types.hh`.
- **Files**: `utils/Probe/Types.hh`, `utils/Record/Types.hh`, `utils/Record/Extract.hh`, `modules/Lambda/Types.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 1.5: Delete redundant Lorentz aliases and ensure `Physics::Lorentz` is used."

### 1.6 Rename ThetaTolerance (REVIEW 15)
- **Directives**: Rename `ThetaTolerance` to `thetaTolerance` in `modules/Lambda/Types.hh:49` and `modules/Lambda/Parameters.hh:270-271`.
- **Observation**: Check if `thetaTolerance` is write-only after `extractPhysics` and add a comment if so.
- **Files**: `modules/Lambda/Types.hh`, `modules/Lambda/Parameters.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 1.6: Rename `ThetaTolerance` to `thetaTolerance`."

### 1.7 Snake_case to camelCase in Config::Watch (ROADMAP Readability)
- **Directives**: Rename `heartbeat_interval`, `terminal_refresh_interval`, `program_stall_threshold` to `heartbeatInterval`, `terminalRefreshInterval`, `programStallThreshold` in `Config::Watch`. Keep `iEvent` and `nEvents`.
- **Files**: `utils/Config/Types.hh`, `utils/Config/Reader.hh`, `utils/Monitor/Logger.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 1.7: Rename snake_case fields in `Config::Watch` to camelCase."

---

## Phase 2 — File and namespace restructure

### 2.1 BranchControl (REVIEW 8)
- **Directives**: Rename `utils/Probe/Schema.hh` → `utils/Probe/BranchControl.hh`. Rename namespace `Probe::detail` → `Probe::BranchControl`.
- **Update**: Update 4 include sites: `Probe/FlatReader.hh:8`, `VecReader.hh:9`, `Event.hh:9`, `Probe.hh:4`.
- **Files**: `utils/Probe/Schema.hh`, `utils/Probe/FlatReader.hh`, `utils/Probe/VecReader.hh`, `utils/Probe/Event.hh`, `utils/Probe.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 2.1: Rename `Schema.hh` to `BranchControl.hh` and update namespace."

### 2.2 Nest Extract/Meta (REVIEW 9)
- **Directives**: Move `namespace Extract` and `namespace Meta` under `namespace Record`.
- **Update**: Update `_Lambda_Reconstruction.cc:84` and all consumers.
- **Files**: `utils/Record/Extract.hh`, `utils/Record/Meta.hh`, `_Lambda_Reconstruction.cc`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 2.2: Nest `Extract` and `Meta` namespaces under `Record`."

### 2.3 Merge Format (REVIEW 14)
- **Directives**: Fold `utils/Monitor/Format.hh` (one function `updatedETA`) into `utils/Monitor/Snapshot.hh`. Delete `Format.hh`.
- **Update**: Update include sites in `Snapshot.hh:11,47`.
- **Files**: `utils/Monitor/Format.hh`, `utils/Monitor/Snapshot.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 2.3: Merge `Format.hh` into `Snapshot.hh`."

### 2.4 Split Parameters.hh (ROADMAP 1)
- **Directives**: Split `modules/Lambda/Parameters.hh` into:
  - `Parameters.hh`: bounds helpers (approx. lines 35-103).
  - `Loaders.hh`: TOML loaders, `extractPhysics` (approx. lines 105-165, 267-313).
  - `Declare.hh`: ROOT object declaration (approx. lines 179-265).
- **Update**: Update `Lambda.hh` umbrella.
- **Files**: `modules/Lambda/Parameters.hh`, `modules/Lambda/Loaders.hh`, `modules/Lambda/Declare.hh`, `modules/Lambda.hh`.
- **Effort**: One-day.
- **READY TO IMPLEMENT**: "Phase 2.4: Split `Parameters.hh` into `Parameters.hh`, `Loaders.hh`, and `Declare.hh`."

### 2.5 FinalizerController (ROADMAP 2)
- **Directives**: Migrate `_Lambda_Data.cc:48-60` inline tail to `FinalizerController` with a `preCloseHook` callback (Option 1).
- **Files**: `_Lambda_Data.cc`, `utils/Record/Finalizer.hh`.
- **Effort**: One-day.
- **READY TO IMPLEMENT**: "Phase 2.5: Migrate `_Lambda_Data.cc` tail logic to `FinalizerController` with `preCloseHook`."

---

## Phase 3 — Structural additions and behavioral changes

### 3.1 userEvents bool (REVIEW 16 / ROADMAP 3)
- **Directives**: Add `bool userEvents` to `Config::Events`. Populate in `readEventsSection` by checking key presence. Collapse IIFE in `_Lambda_Reconstruction.cc:55-62`.
- **Files**: `utils/Config/Types.hh`, `utils/Config/Reader.hh`, `_Lambda_Reconstruction.cc`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 3.1: Add `userEvents` flag to `Config::Events` and simplify `_Lambda_Reconstruction.cc`."

### 3.2 TeX labels (REVIEW 18)
- **Directives**: Add `Physics::particlePropertyTeX` returning TeX strings. Add `tex` field to `ParticleTraits`. Wire into `declareObjects` `SetTitle`.
- **Files**: `utils/Physics/Types.hh`, `utils/Physics/Properties.hh`, `modules/Lambda/Parameters.hh`.
- **Effort**: One-day.
- **READY TO IMPLEMENT**: "Phase 3.2: Add TeX label support to particle properties and ROOT histograms."

### 3.3 kTreeEnabledSets (REVIEW 20)
- **Directives**: Delete `kTreeEnabledSets`, `shouldWriteTree`, `kHistogramSetCount`, and `trees` field on `RootObjects`.
- **Add**: `[lambda.analysis]` section to TOML with `writeTree` key (array of strings). Parse into `std::vector<HistogramSet>`.
- **Files**: `modules/Lambda/Types.hh`, `modules/Lambda/Parameters.hh`, `utils/Record/Types.hh`, `utils/Config/Reader.hh`.
- **Effort**: One-day.
- **READY TO IMPLEMENT**: "Phase 3.3: Implement runtime-sized tree selection via TOML."

### 3.4 Register split / HistConfig (ROADMAP 7)
- **Directives**: Create `Config::HistConfig` holding `binCount`, `histScale`, `histLimitsFile`, `particleLimits`, `eventLimits`. Move these out of `Register`.
- **Cleanup**: Identify internal-only fields in `Register` and remove.
- **Files**: `utils/Config/Types.hh`, `utils/Config/Reader.hh`, `utils/Config/Defaults.hh`.
- **Effort**: One-day.
- **READY TO IMPLEMENT**: "Phase 3.4: Split `Register` and introduce `HistConfig`."

### 3.5 Configurability (ROADMAP)
- **Directives**: 
  - Wire `cmnd_file` path through `Config::PythiaConfig::cmndFile`.
  - Replace `General_Limits.toml` hardcoded path with `configs/Defaults/Limits.toml`. Make optional.
- **Files**: `utils/Config/Types.hh`, `utils/Config/Reader.hh`, `utils/Config/Defaults.hh`, `_Lambda_Reconstruction.cc`.
- **Effort**: One-day.
- **READY TO IMPLEMENT**: "Phase 3.5: Enhance configurability for Pythia and Histogram Limits."

---

## Phase 4 — Robustness

### 4.1 Atomics (ROADMAP Robustness)
- **Directives**: Make `nRealEvents` atomic. Drop `eventMutex_` and unify to all-atomic. Audit other `Watch` fields.
- **Files**: `utils/Config/Types.hh`, `utils/Config/TypeAid.hh`.
- **Effort**: Half-day.
- **READY TO IMPLEMENT**: "Phase 4.1: Unify `Config::Watch` to use atomics for event counting."

---

## Late Stage

- **ROADMAP 5**: PCH for ROOT/Pythia8/toml++.
- **TThreadedObject**: Integrate after Investigation B report is accepted.
- **event_particles TOML schema**: Implement after Investigation E report is accepted.
- **runParallel deduplication**: Deduplicate worker loops in `Parallel.hh:53-61` and `98-106`.
