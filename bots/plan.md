# Phase 3 Plan — items 5, 9, 11

Companion to [docs/REVIEW.md](../docs/REVIEW.md) and [docs/refactor-direction.md](../docs/refactor-direction.md). Three items from the architecture audit, sequenced as recommended (5 first, then 9, then 11). Each section lists exact files, exact symbols, **explicit Phase 2 dependencies** flagged with ⚠️, and a compile-plus-test gate.

**Global pre-condition for all three sections:** Phase 2 (Sections 2, 4, 6, 7) is merged and `make test` is green. The `tests/test_reconstructCandidates.exe` and `tests/test_rootAnalysis_smoke.exe` binaries are the regression net for everything below.

---

## 5. Drop the `NoPythia` shim — redesign `FinalizerController` to take optional callbacks

### What this fixes

`Record::FinalizerController` is templated on `PythiaT` because two of its methods need `pythia.stat()` and `pythia.settings.listChanged()`. Two drivers (`_Lambda_Reconstruction.cc`, `tests/test_rootAnalysis_smoke.cc`) have no Pythia instance, so they fake one with a `NoPythia` struct that satisfies the duck-typed interface. This is the dependency arrow pointing the wrong way: a generic output finalizer should not require a Pythia-shaped object.

The fix replaces the templated `PythiaT&` with two `std::function<void()>` callbacks that drivers wire up explicitly. Drivers that have Pythia bind to `[&]{ pythia.stat(); }` / `[&]{ pythia.settings.listChanged(); }`; drivers that don't pass `nullptr` (or `{}`), and the controller skips them.

### Phase 2 dependencies

⚠️ **Section 6 (`AnalysisContext`/`GenerationContext`) must be merged.** The reconstruction driver's `NoPythia` callsite is exactly the `FinalizerController(dummy, ...)` instantiation; the smoke test's was added in Section 2 as part of Phase 2. If Section 6 is not in, the handler signatures still take `Config::Root&` directly, but that's orthogonal — the controller change is independent of the handler-bundle refactor.

⚠️ **Section 4 (`Watch::recordEvent` + `freeze() → unique_ptr`) must be merged.** `fatalShutdown()` already uses `logging_.freeze()` returning `std::unique_ptr<Config::Log>`; no further freeze churn in this section.

No dependency on Section 7. No dependency on Section 2 mechanically, but the smoke test is the regression check used to validate the change.

### Files to change

#### `utils/Record/Finalizer.hh` — the core redesign

Drop the `PythiaT` template parameter. Replace `pythia_` with two callback members.

| Symbol                                                                                                          | Current                                                                                                                                                                                      | After                                                                                                                                                                                                                                                |
| --------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Template params                                                                                                 | `template <typename PythiaT, typename RootArrayT, typename ProgramLogBuilder>` (line 39)                                                                                                     | `template <typename RootArrayT, typename ProgramLogBuilder>`                                                                                                                                                                                         |
| Ctor signature                                                                                                  | `FinalizerController(PythiaT& pythia, RootArrayT& histogramSets, Config::Root& root, Config::Log& logging, Monitor::AsyncLogger& logger, ProgramLogBuilder programLogBuilder)` (lines 42–45) | `FinalizerController(RootArrayT& histogramSets, Config::Root& root, Config::Log& logging, Monitor::AsyncLogger& logger, ProgramLogBuilder programLogBuilder, std::function<void()> printStats = {}, std::function<void()> listChangedSettings = {})` |
| Member: `PythiaT& pythia_;` (line 102)                                                                          | drop                                                                                                                                                                                         | replace with `std::function<void()> printStats_;` and `std::function<void()> listChangedSettings_;`                                                                                                                                                  |
| `normalShutdown()` lines 69–70 (`Monitor::terminalReport(pythia_, ...)` and `Monitor::outputLog(pythia_, ...)`) | calls Pythia-templated functions                                                                                                                                                             | call new versions that accept callbacks instead — see below                                                                                                                                                                                          |
| `fatalShutdown()` line 88 (`Monitor::outputLog(pythia_, ...)`)                                                  | same                                                                                                                                                                                         | same fix                                                                                                                                                                                                                                             |

**Why callbacks instead of inheritance / a strategy interface:** `std::function` has the right shape (zero or one optional behavior), drivers already pass lambdas everywhere else (e.g. `programLogBuilder`, the worker callback to `pythia.run`), and there's no shared state between the two methods. An interface would be over-engineered.

#### `utils/Monitor/Render.hh` — de-template the two consumers

Currently `terminalReport` (line 159) and `outputLog`/`buildLogText` (lines 60–113) are `template <typename PythiaT>` and call `pythia.stat()`, `pythia.settings.listChanged()`, `pythia.info.list()`. Two replacement strategies; pick **(a)**.

**(a) Replace template with two `std::function` parameters** — simpler, matches Finalizer's new shape:

```cpp
inline std::string buildLogText(const Config::Root& root,
                                 const Config::Log& logging,
                                 const std::string& programLog = {},
                                 const std::function<void()>& printStats = {},
                                 const std::function<void()>& listChangedSettings = {});
inline void outputLog(const Config::Root& root,
                       const Config::Log& logging,
                       const std::string& programLog = {},
                       const TString& logPath = "",
                       const std::function<void()>& printStats = {},
                       const std::function<void()>& listChangedSettings = {});
inline void terminalReport(const Config::Root& root,
                            Config::Log& logging,
                            const std::function<void()>& printStats = {});
```

Inside the bodies:
- Line 91 (`pythia.settings.listChanged();`) → `if (listChangedSettings) listChangedSettings();`
- Lines 93–96 (the `if constexpr (std::is_same_v<PythiaT, Pythia8::Pythia>) { pythia.info.list(); ... }`) → **drop entirely**. `info.list()` is only called for the non-parallel `Pythia8::Pythia` (not `PythiaParallel`); it's the per-event info dump for the first event. The drivers that want it (`_Lambda_Test.cc`, `_Lambda_Parallel.cc`) already call it themselves in `pythiaAnalysis` (`modules/Lambda.hh:39-41`). The duplicate call here is dead in PythiaParallel and redundant in serial. Removing it eliminates the `if constexpr` and the last `<type_traits>` dep here.
- Line 97 (`pythia.stat();`) → `if (printStats) printStats();`
- Line 162 (`if (stats) { pythia.stat(); ... }`) → `if (stats && printStats) { printStats(); ... }`

**(b) Alternative: keep templates, add an optional `void(PythiaT*)` callback** — more elaborate, doesn't actually remove the template, rejected.

Drop `#include "Pythia8/Pythia.h"` (line 14) and `#include <type_traits>` (line 8) from `Render.hh` — neither is needed after (a). Add `#include <functional>` instead.

This is a **load-bearing decoupling**: it removes Pythia8 from `Monitor.hh`'s transitive include set entirely. Currently every TU that includes `Lambda.hh` pulls in Pythia8 because of `Lambda/Types.hh → Record.hh → Record/Finalizer.hh → Monitor.hh → Monitor/Render.hh → Pythia8/Pythia.h`. After (a) the chain breaks at Render.hh, and the unit test (`tests/test_reconstructCandidates.cc`) no longer needs Pythia8 link flags. **This is the largest secondary benefit and worth pricing in.**

#### Driver instantiation sites — every one needs an update

Sweep `grep -n 'FinalizerController' --include='*.cc'`:

| File:line                                                        | Current                                                                                                                                                                                                                                                                                                                                                                               | After                                                                                                                                                               |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_Lambda_Parallel.cc:32-39`                                      | `Record::FinalizerController finalizer(pythia, histogramSets, rootParams, logParams, logger, [&]{...})`                                                                                                                                                                                                                                                                               | `Record::FinalizerController finalizer(histogramSets, rootParams, logParams, logger, [&]{...}, [&]{ pythia.stat(); }, [&]{ pythia.settings.listChanged(); });`      |
| `_Lambda_Reconstruction.cc:14-19` (the `NoPythia` struct)        | **delete the entire `namespace { struct NoPythia {...}; }` block**                                                                                                                                                                                                                                                                                                                    | gone                                                                                                                                                                |
| `_Lambda_Reconstruction.cc:48-55`                                | `NoPythia dummy; Record::FinalizerController finalizer(dummy, histogramSets, rootParams, logParams, asyncLogger, [&]{...});`                                                                                                                                                                                                                                                          | `Record::FinalizerController finalizer(histogramSets, rootParams, logParams, asyncLogger, [&]{...});` (no Pythia callbacks → defaults to `{}`)                      |
| `_Lambda_Data.cc`                                                | **does not instantiate `FinalizerController`** — it inlines `wrapUp` + `outputLog` + `terminalReport` manually at lines 47–57. Two choices:<br>(i) **Leave alone** — out of scope for this section.<br>(ii) **Migrate to `FinalizerController`** — drops the duplicated tail, but adds a fourth driver to update. **Recommend (i)** for this section; (ii) becomes its own follow-up. | unchanged in this section                                                                                                                                           |
| `_Lambda_Test.cc:33-40`                                          | `Record::FinalizerController finalizer(pythia, histogramSets, rootParams, logParams, asyncLogger, [&]{...})`                                                                                                                                                                                                                                                                          | `Record::FinalizerController finalizer(histogramSets, rootParams, logParams, asyncLogger, [&]{...}, [&]{ pythia.stat(); }, [&]{ pythia.settings.listChanged(); });` |
| `tests/test_rootAnalysis_smoke.cc:37-40` (the `NoPythia` struct) | **delete the entire local `NoPythia` struct**                                                                                                                                                                                                                                                                                                                                         | gone                                                                                                                                                                |
| `tests/test_rootAnalysis_smoke.cc:75-80`                         | `NoPythia dummy; Record::FinalizerController finalizer(dummy, ...)`                                                                                                                                                                                                                                                                                                                   | `Record::FinalizerController finalizer(histogramSets, rootParams, logParams, asyncLogger, [&]{...});`                                                               |
| `_Lambda_Data.cc:57`                                             | `Monitor::outputLog(pythia, rootParams, logParams, Lambda::dataLogString());` (still templated)                                                                                                                                                                                                                                                                                       | `Monitor::outputLog(rootParams, logParams, Lambda::dataLogString(), "", [&]{ pythia.stat(); }, [&]{ pythia.settings.listChanged(); });`                             |
| `_Lambda_Data.cc:56`                                             | `Monitor::terminalReport(pythia, rootParams, logParams);`                                                                                                                                                                                                                                                                                                                             | `Monitor::terminalReport(rootParams, logParams, [&]{ pythia.stat(); });`                                                                                            |

### Public API breakage

This **is a breaking change** to:
- `Record::FinalizerController` — template signature changes (one fewer parameter), ctor adds two new params.
- `Monitor::buildLogText`, `Monitor::outputLog`, `Monitor::terminalReport` — signatures change (no longer templates; new optional callback params).

Out-of-tree consumers do not exist (this is a single-repo project; the four drivers and the smoke test are the only users). But the changes are wider than internal — anyone who has a downstream branch with their own driver or test must update their `FinalizerController(...)` instantiation.

`_Monitor_FatalStall_Harness.cc` is **not** a consumer of either symbol — it talks to `AsyncLogger` directly. No change needed there in this section.

### Files NOT changed in this section

- `utils/Monitor/Logger.hh` — `AsyncLogger` is unrelated.
- `utils/Monitor/Snapshot.hh` — pure data formatting.
- `modules/Lambda.hh`, `modules/Lambda/Context.hh` — handlers don't call `FinalizerController`.
- All `Lambda/Parameters.hh`, `Lambda/Reconstruction.hh`, etc. — physics layer, no contact.

### Compile + test gate

```sh
make clean
make _Lambda_Parallel.exe _Lambda_Reconstruction.exe _Lambda_Data.exe _Lambda_Test.exe
make test
```

All four drivers must compile clean. `tests/test_reconstructCandidates.exe` should compile **without** Pythia8 link flags now (verify with `nm tests/test_reconstructCandidates.exe | grep -i pythia` — should be empty). `tests/test_rootAnalysis_smoke.exe` continues to need Pythia8 (Lambda.hh handler bodies use Pythia8::Pythia in `harvestParticles`). `make test` continues to pass `S1–S5` and `T1–T5`.

Manual smoke: `./_Lambda_Parallel.exe configs/Lambda_Generation.toml` should produce a `.log` file containing the same Pythia stats / settings dump as before (callbacks fire identically).

---

## 9. Rename `Watch`/`Register` to informative names; complete the alias migration

### What this fixes

REVIEW #4 catalogues the half-done alias migration: `Config::Log = Watch` and `Config::Root = Register` are pure backwards-compat aliases living in `Config/Types.hh:137-138`. Drivers and Lambda still use `Config::Log` / `Config::Root` everywhere; no caller has switched to `Watch` / `Register`. The audit (C2) goes further: **neither current pair is informative**. `Watch` doesn't say "runtime counters", `Register` doesn't say "output ROOT artifacts", `Log` is misleading (it's not a log file, it's runtime state), `Root` is a name-collision with the ROOT framework itself.

The fix is **two coordinated renames**, not just an alias retirement. Pick names that describe what the structs *hold*:

- `Config::Watch` (≡ `Config::Log`) → **`Config::RunStats`**
  - Holds: per-event counters (`iEvent`, `nRealEvents`, `elapsed`), pacing intervals (`heartbeat_interval`, `terminal_refresh_interval`, `program_stall_threshold`, `printInterval`, `barInterval`, `checkInterval`), schema metadata (`serial`, `srPadding`, `nEvents`, `nDigits`, `nThreads`), start time, and the per-event mutex.
  - Alternative considered: `RuntimeStats`. Picked `RunStats` because it matches the file/log artifact naming (`runStatName`, `runStatString`) already in the codebase.
- `Config::Register` (≡ `Config::Root`) → **`Config::OutputContext`**
  - Holds: output `TFile*`, beam-energy string, all output path templates (`outName`, `logName`, `runStatName`, `threadStatDirectory`, `checkpointOutName`, `checkpointLogName`, `rootDirectory`, `logDirectory`, `checkpointDirectory`, `fileTitle`, `histLimitsFile`), histogram config (`binCount`, `histScale`), particle/event limits maps, and `inputPath`.
  - Note: This is **the type that Section 11 will split**. We rename to `OutputContext` here as a stepping stone; Section 11 then splits it into `OutputFile` + `OutputPaths` + `LimitsConfig`. Alternative: skip this rename, go straight to Section 11's split. **Rejected**: Section 11 is gated on `Lambda/Parameters.hh` split (REVIEW #15) which is not yet planned. We need the rename to land independently so consumers stop typing `Config::Root` in code that won't be touched in #15.

After both renames, **delete the aliases** `Config::Log = Watch` and `Config::Root = Register` from `Config/Types.hh:137-138`. The compiler then enforces the migration.

### Phase 2 dependencies

⚠️ **Section 4 (`Watch::recordEvent` + `freeze() → unique_ptr`) is the load-bearing dependency.** `Watch` got a `std::mutex eventMutex_` member, the `recordEvent()` method, and a non-movable / non-copyable shape. The rename `Watch → RunStats` must preserve all of that *and* update the out-of-line `Watch::recordEvent` and `Watch::freeze()` definitions in `Config/TypeAid.hh:32-58` to `RunStats::recordEvent` / `RunStats::freeze`. Without Section 4 in place, the rename has fewer files to touch but also the `freeze()` and `recordEvent` symbols don't exist; if Section 4 has *not* landed, defer this section.

⚠️ **Section 6 (`AnalysisContext`/`GenerationContext`)** changes the field types inside the context structs (`modules/Lambda/Context.hh:25`, `:33` use `Config::Log&` and `Config::Root&` aliases). After this section, those become `Config::RunStats&` and `Config::OutputContext&`. If Section 6 has not landed, those fields don't exist and the renames are still doable but touch fewer files.

⚠️ **Section 7 (`readInputSection` + `inputPath` field) is a soft dependency.** Section 7 added `inputPath` to `Register`. The rename `Register → OutputContext` carries that field along. No fix needed beyond renaming.

No dependency on Section 2.

### Files to change

A purely mechanical sweep, but **wide**. Use `git grep -l` to enumerate every file:

```sh
git grep -l 'Config::Watch\|Config::Register\|Config::Log\|Config::Root' \
  -- '*.hh' '*.cc' '*.cpp'
```

Expected hit list (from current grep output above):

#### Definition site

| File                      | Lines                                                              | Change                                                                                                                  |
| ------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `utils/Config/Types.hh`   | `:74` `struct Watch`                                               | rename to `struct RunStats`                                                                                             |
| `utils/Config/Types.hh`   | `:99,101,105,108` (out-of-line method declarations)                | `Watch::recordEvent` → `RunStats::recordEvent`; `Watch::freeze` → `RunStats::freeze`; comment block at `:72-75` updated |
| `utils/Config/Types.hh`   | `:112` `struct Register`                                           | rename to `struct OutputContext`                                                                                        |
| `utils/Config/Types.hh`   | `:137-138` `using Log = Watch; using Root = Register;`             | **delete both lines**                                                                                                   |
| `utils/Config/TypeAid.hh` | `:30,32,49,52` (out-of-line `Watch::recordEvent`, `Watch::freeze`) | rename `Watch::` → `RunStats::` (`replace_all` is safe here — no other `Watch::` appears in this file)                  |

#### Direct consumers (use `replace_all` in each file with `Config::Log → Config::RunStats` and `Config::Root → Config::OutputContext`)

Every file from the grep output above:

| File                                                        | Symbols touched                                                                                                                                                                                                                                                                  |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `utils/Config.hh`                                           | `Watch&`/`Register&` parameter types in `configuration` (×2), `configurePythia`, `configureProbe`, `extractConfiguration`, `openOutputFile`. (None use the `Log`/`Root` aliases here — already on the new names; only the rename to `RunStats`/`OutputContext` needs to happen.) |
| `utils/Config/Reader.hh`                                    | `Watch&`, `Register&` — section reader signatures                                                                                                                                                                                                                                |
| `utils/Config/Defaults.hh`                                  | `Root&` — `limitExtractor`, `loadMonitorDefaults` (uses `Log&` + `Root&`)                                                                                                                                                                                                        |
| `utils/Monitor/Logger.hh:27,57,103`                         | `start(const Config::Root&, const Config::Log&)`, `publish(const Config::Log&, ...)`, `finish(const Config::Log&, ...)`                                                                                                                                                          |
| `utils/Monitor/Snapshot.hh:41`                              | `makeSnapshot(const Config::Log&, RunPhase)`                                                                                                                                                                                                                                     |
| `utils/Monitor/Render.hh:62-63,107-108,116-117,149-150,159` | `buildLogText`, `outputLog`, `buildEmergencyLogText`, `writeEmergencyLog`, `terminalReport` — all `Config::Root&` / `Config::Log&` parameters                                                                                                                                    |
| `utils/Record/Finalizer.hh:43,76,104-105`                   | ctor params, the `frozenLog` line, the two member references                                                                                                                                                                                                                     | **conflicts with Section 5**: order matters. If 5 lands first, Finalizer.hh has `Config::Log& logging_` and `Config::Root& root_` to rename; if 9 lands first, the ctor still takes `Config::Log&` and `Config::Root&` plus `PythiaT&`. **Recommended order: 5 then 9** so 9 doesn't have to dance around the dropped `pythia_` member. |
| `utils/Record/Meta.hh:115-116`                              | `capture(...)` signature                                                                                                                                                                                                                                                         |
| `modules/Lambda.hh:33`                                      | `pythiaAnalysis(Pythia8::Pythia&, Config::Root&, AnalysisContext&)` — the `Config::Root&` for checkpoint paths                                                                                                                                                                   |
| `modules/Lambda/Context.hh:25,33`                           | `Config::Log&` field in both `AnalysisContext` and `GenerationContext`                                                                                                                                                                                                           |
| `modules/Lambda/Parameters.hh:55,68,82,89,159,195,266`      | `levelBounds(const Config::Root&, ...)` (×2), `boundsFromNode<P>`, `resolveBounds<P>`, `declareDataObjects(DataObjects&, Config::Root&)`, `declareObjects(RootArray&, ..., Config::Root&)`, `extractPhysics(..., const Config::Root&)`                                           |
| `modules/Lambda/Parameters.hh:6`                            | `#include "Config.hh"` — no change, but verify it picks up the renamed types                                                                                                                                                                                                     |
| `_Lambda_Parallel.cc:20,22`                                 | `Config::Root rootParams; Config::Log logParams;`                                                                                                                                                                                                                                |
| `_Lambda_Reconstruction.cc:29-30`                           | same                                                                                                                                                                                                                                                                             |
| `_Lambda_Data.cc:21,23`                                     | same                                                                                                                                                                                                                                                                             |
| `_Lambda_Test.cc:19-20`                                     | same                                                                                                                                                                                                                                                                             |
| `_Monitor_FatalStall_Harness.cc:12,20`                      | `Config::Root root; Config::Log logging;`                                                                                                                                                                                                                                        |
| `tests/test_rootAnalysis_smoke.cc:62-63`                    | same                                                                                                                                                                                                                                                                             |

#### Comment-only sweep

| File                          | Lines                                                                                                |
| ----------------------------- | ---------------------------------------------------------------------------------------------------- |
| `modules/Lambda/Context.hh:6` | `// Config::Log / Config::Root aliases` → `// Config::RunStats / Config::OutputContext`              |
| `utils/Config/Types.hh:134`   | comment block describing the aliases — delete entirely along with the aliases                        |
| `docs/MAP.md:59-60`           | "Aliases: `Log = Watch`, `Root = Register`" → "Renamed to `RunStats` / `OutputContext` (Phase 3 #9)" |
| `docs/REVIEW.md:19-20` (#4)   | mark resolved with the chosen names                                                                  |

### Mechanical approach

```sh
# Step 1: rename the structs in their definition file
sed -i.bak \
  -e 's/struct Watch /struct RunStats /' \
  -e 's/struct Register /struct OutputContext /' \
  utils/Config/Types.hh

# Step 2: update out-of-line method definitions
sed -i.bak 's/Watch::/RunStats::/g' utils/Config/TypeAid.hh

# Step 3: tree-wide rename of the alias names (they were the de-facto canonical names).
git grep -l 'Config::Log\|Config::Root' -- '*.hh' '*.cc' | \
  xargs sed -i.bak \
    -e 's/Config::Log\b/Config::RunStats/g' \
    -e 's/Config::Root\b/Config::OutputContext/g'

# Step 4: delete the alias declarations
sed -i.bak '/using Log  *= *Watch/d; /using Root *= *Register/d' utils/Config/Types.hh

# Step 5: clean up the .bak files
find . -name '*.bak' -delete
```

**Caveats with the mechanical sweep:**
- `\b` is a GNU sed-ism; on macOS use `[[:>:]]` or just `'s/Config::Log /Config::RunStats /g'` style with explicit trailing chars, OR use `perl -i -pe 's/Config::Log\b/Config::RunStats/g'`.
- The `Config::Root` rename will catch every reference but **does not** affect the `ROOT::` namespace from CERN ROOT (those are `ROOT::Math::PxPyPzEVector` etc. — different prefix, no clash).
- The variable names `rootParams`, `logParams`, `root_`, `logging_` in driver/Finalizer code are **not renamed** by this section. Their *types* change (`Config::Root → Config::OutputContext`); the local-variable identifiers stay. A future cleanup could rename `rootParams → outputCtx` etc., but that's noise not signal here.
- Watch out for the field `root.outFile` etc. — `root` is a variable name, not the type. The mechanical sweep should not touch those, and `Config::Root` only matches the qualified type form.

### Public API breakage

This **is a breaking change** to the entire `Config::` API surface used by every other module. After this section, code referencing `Config::Log` or `Config::Root` will not compile. Consumers updated in lockstep within this commit; out-of-tree consumers must update.

The aliases are *removed*, not *deprecated* — there's no transition window. (Adding `using [[deprecated]] Log = RunStats;` is a possible compromise but adds noise for one cycle and contradicts the audit's "pick a side and grep-replace" guidance.)

### Files NOT touched in this section

- `utils/Probe/*` — no `Config::Log`/`Config::Root` use.
- `utils/Physics/*` — no Config dependency.
- `utils/Utility/*` — no Config dependency.
- `utils/Paint/*` — uses TOML directly, no Config types.
- `tests/test_reconstructCandidates.cc` — pure physics test, no Config.
- `tests/fixtures/make_lambda_fixture.cc` — direct ROOT API, no Config.

### Compile + test gate

```sh
make clean
make _Lambda_Parallel.exe _Lambda_Reconstruction.exe _Lambda_Data.exe _Lambda_Test.exe
make test
make _Monitor_FatalStall_Harness.exe && ./_Monitor_FatalStall_Harness.exe
```

The `_Monitor_FatalStall_Harness.cc` rebuild is the highest-risk check — it directly mutates fields on `Config::Log` and `Config::Root` without going through any helper, so a missed renamed field surfaces here.

`make test` continues to pass `S1–S5` + `T1–T5`. Run the smoke test 5× back-to-back to catch any subtle change in the `recordEvent`/`freeze()` machinery hidden by the rename.

Verify the final state:

```sh
git grep -n 'Config::Log\|Config::Root' && echo "FAIL: aliases still referenced" || echo "OK"
```

Expected: zero hits.

---

## 11. Split `Config::Root` (now `Config::OutputContext`) into `OutputFile` and `OutputPaths`

### What this fixes

Audit D1: `Config::Root` (≡ `Config::Register`, post-§9 = `Config::OutputContext`) is doing **four jobs** in one struct:
1. **Output `TFile*` handle** + histogram scale (`outFile`, `histScale`, `binCount`).
2. **Beam-energy string** for filename composition (`beamEnergy`).
3. **Output path templates** (`outName`, `logName`, `runStatName`, `threadStatDirectory`, `checkpointOutName`, `checkpointLogName`, `rootDirectory`, `logDirectory`, `checkpointDirectory`, `fileTitle`).
4. **Histogram limits** (`particleLimits`, `eventLimits`, `histLimitsFile`) — used only by `Lambda::extractPhysics`.

Splitting lets `Monitor::AsyncLogger::start` take only the path templates (it only needs `runStatName` and `threadStatDirectory`) instead of the whole bag. It lets `Lambda::Parameters.hh` take only the limits (the file path + the maps). The `TFile*` lifecycle stays in its own struct. **Three structs, not two**, because the limits are large maps that don't belong with either the file handle or the path templates.

Proposed split:

```cpp
namespace Config {
    // ── File handle + histogram knobs (lifecycle: open at startup, close at shutdown) ──
    struct OutputFile {
        TFile*   handle      = nullptr;
        TString  outName     = "";       // path passed to TFile::Open
        Int_t    binCount    = 100;
        Double_t histScale   = 100;
    };

    // ── All filename / directory templates (lifecycle: derived once at config-read) ──
    struct OutputPaths {
        TString rootDirectory       = "output/";
        TString logDirectory        = "output/params/";
        TString checkpointDirectory = "output/checkpoints/";
        TString beamEnergy          = "";
        TString fileTitle           = "";
        TString outName             = "";   // duplicated with OutputFile::outName — see migration note
        TString logName             = "";
        TString runStatName         = "";
        TString threadStatDirectory = "";
        TString checkpointOutName   = "";
        TString checkpointLogName   = "";
    };

    // ── Histogram limits + input file (lifecycle: read once from TOML) ──
    struct LimitsConfig {
        std::string    inputPath;        // [events].input_file (Phase 2 §7)
        TString        histLimitsFile;
        ParticleLimits particleLimits;
        EventLimits    eventLimits;
    };
}
```

**Why three not two:** the audit suggests `OutputFile` + `OutputPaths`. But the limits maps and `inputPath` don't belong with either — they're the *input* side of the run, not the output. A third struct keeps each focused. Alternative: fold limits into `Lambda::Parameters` (where they're consumed) — **rejected** because `extractPhysics` populates them from `OutputContext` today, and the limits are per-driver not per-Lambda; any future analysis (not just Lambda) would consume them.

**`outName` duplication:** Both `OutputFile` (where the TFile opens) and `OutputPaths` (where the path is composed) need access to `outName`. `Config::openOutputFile(OutputFile&, const OutputPaths&)` reads `paths.outName` and writes `file.outName = paths.outName; file.handle = new TFile(...)`. The duplication is intentional — the file owns its open path so post-shutdown access still works.

### Phase 2 dependencies

⚠️ **Phase 2 §7 (`Register::inputPath` field) must be merged.** The new `LimitsConfig::inputPath` field absorbs Phase 2 §7's addition. Without §7 in place, `inputPath` doesn't exist and the new struct just doesn't have that field.

⚠️ **Phase 3 §9 (rename to `OutputContext`) must be merged.** This section operates on `Config::OutputContext`, not on `Config::Root` / `Config::Register`. If §9 is not in, the type is still `Register` and the rename / split conflict at every callsite. **Order: §9 then §11**, non-negotiable.

⚠️ **REVIEW #15 (split `Lambda/Parameters.hh`) must be merged.** This is the audit's call-out: Phase 3 #11 cannot land safely until #15 lands first. Why: `Lambda/Parameters.hh::extractPhysics` reads `root.histLimitsFile`, `root.particleLimits`, `root.eventLimits`, and `root.binCount`. After the split, this code reads from two different structs (`LimitsConfig` for limits + `OutputFile::binCount` for the bin count). The current 308-line `Parameters.hh` mixes three concerns; touching the limits resolution in this monolithic file is risky. After #15:
- `Lambda/Parameters.hh` (slimmed) takes `const LimitsConfig&` for `levelBounds`, `boundsFromNode`, `resolveBounds`.
- `Lambda/Loaders.hh` (`extractPhysics`) takes `const LimitsConfig&` for the limits + `const OutputFile&` for `binCount` (or, better: pass `binCount` through `Parameters` directly — see follow-up).
- `Lambda/Declare.hh` (`declareObjects`, `declareDataObjects`) takes `OutputFile&` (for `handle->mkdir` and `binCount`).

If #15 is not in, this section's blast radius across `Parameters.hh` is much wider and harder to verify.

### Files to change

#### Definition

| File                    | Change                                                                                                                                                        |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `utils/Config/Types.hh` | Replace `struct OutputContext { ... }` with the three new structs above. Order: `OutputFile`, `OutputPaths`, `LimitsConfig`. Delete the comment "(was Root)". |

#### Reader

| File:line                                                                                       | Current                                                                             | After                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `utils/Config.hh:17-21` `configuration(...)` ctor and ×2 overloads                              | takes `OutputContext&`                                                              | takes `OutputFile& file, OutputPaths& paths, LimitsConfig& limits` (3 params instead of 1, OR a small umbrella struct `OutputBundle{file, paths, limits}` for back-compat — see "Public API breakage" below) |
| `utils/Config.hh:84-93` `openOutputFile(OutputContext&)`                                        | reads `reg.outFile`, `reg.outName`                                                  | becomes `openOutputFile(OutputFile& file, const OutputPaths& paths)` — reads `paths.outName`, sets `file.handle` and `file.outName`                                                                          |
| `utils/Config/Reader.hh:55-65` `readInputSection(config, OutputContext&)` (Phase 2 §7)          | populates `reg.inputPath`                                                           | becomes `readInputSection(config, LimitsConfig&)` — populates `limits.inputPath`                                                                                                                             |
| `utils/Config/Reader.hh:67-79` `readRecordSection(config, RunStats&, OutputContext&)`           | sets `reg.binCount`, `reg.histScale`                                                | becomes `readRecordSection(config, RunStats&, OutputFile&)` — sets `file.binCount`, `file.histScale`                                                                                                         |
| `utils/Config/Reader.hh:81-110` `readLogSection(config, RunStats&, OutputContext&)`             | sets `reg.binCount`, `reg.histScale`                                                | becomes `readLogSection(config, RunStats&, OutputFile&)`                                                                                                                                                     |
| `utils/Config/Reader.hh:112-181` `readPathsAndFile(config, project, RunStats&, OutputContext&)` | populates ten `reg.*` path fields                                                   | becomes `readPathsAndFile(config, project, RunStats&, OutputPaths&)` — populates the same fields on `paths`                                                                                                  |
| `utils/Config/Defaults.hh:70-80` `limitExtractor(configPath, OutputContext&)`                   | clears + populates `root.particleLimits`, `root.eventLimits`, `root.histLimitsFile` | becomes `limitExtractor(configPath, LimitsConfig&)`                                                                                                                                                          |
| `utils/Config/Defaults.hh:82-99` `loadMonitorDefaults(RunStats&, OutputContext&)`               | sets `root.binCount`, `root.histScale`                                              | becomes `loadMonitorDefaults(RunStats&, OutputFile&)`                                                                                                                                                        |

#### Driver consumers (each driver declares the three structs)

| File                                     | Change                                                                                                                                                                                                                                                                                                                                                                         |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `_Lambda_Parallel.cc:20-22`              | Replace `Config::OutputContext rootParams;` with `Config::OutputFile fileCtx; Config::OutputPaths pathCtx; Config::LimitsConfig limitsCtx;` (variable names: short, descriptive). Update `extractConfiguration`, `openOutputFile`, `Lambda::extractPhysics`, `Lambda::declareObjects`, `FinalizerController` ctor to pass the right struct(s).                                 |
| `_Lambda_Reconstruction.cc:29-44`        | Same pattern. `inputPath` now lives on `limitsCtx.inputPath`.                                                                                                                                                                                                                                                                                                                  |
| `_Lambda_Data.cc:21-23`                  | Same.                                                                                                                                                                                                                                                                                                                                                                          |
| `_Lambda_Test.cc:19-22`                  | Same.                                                                                                                                                                                                                                                                                                                                                                          |
| `_Monitor_FatalStall_Harness.cc:12-20`   | Currently writes to `root.rootDirectory`, `root.logDirectory`, `root.logName`, `root.runStatName`, `root.threadStatDirectory`, `root.fileTitle`. All of those are on `OutputPaths` after the split — replace `Config::OutputContext root;` with `Config::OutputPaths paths;` and update the field writes. **No `OutputFile` needed** because the harness doesn't open a TFile. |
| `tests/test_rootAnalysis_smoke.cc:62-65` | Same as drivers; three structs declared.                                                                                                                                                                                                                                                                                                                                       |

#### Monitor (the win this section delivers)

| File:line                                                                                                      | Current                                                                                       | After                                                                                                                                                                                                                                                                               |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `utils/Monitor/Logger.hh:27` `start(const OutputContext& root, const RunStats& logging)`                       | reads `root.runStatName`, `root.threadStatDirectory`                                          | becomes `start(const OutputPaths& paths, const RunStats& logging)` — reads `paths.runStatName`, `paths.threadStatDirectory`. Update `start()` body lines 31-32.                                                                                                                     |
| `utils/Monitor/Render.hh:60-103` `buildLogText(const OutputContext& root, ...)` and the post-§5 callbacks-form | reads `root.beamEnergy`, `root.histScale`, `root.fileTitle`, `root.logName`                   | becomes `buildLogText(const OutputPaths& paths, const OutputFile& file, ...)` — reads `paths.beamEnergy`, `file.histScale`, `paths.fileTitle`, `paths.logName`. Or pass a tiny aggregate `LogContext{paths, file}` if signature pressure becomes painful (likely not for two refs). |
| `utils/Monitor/Render.hh:106-114` `outputLog`                                                                  | same                                                                                          | same — takes `paths` + `file`                                                                                                                                                                                                                                                       |
| `utils/Monitor/Render.hh:116-156` `buildEmergencyLogText` / `writeEmergencyLog`                                | reads `root.logName`, `root.outName`, `root.runStatName`, `root.fileTitle`, `root.beamEnergy` | takes `OutputPaths` only (no `outFile` needed for emergency log — only paths)                                                                                                                                                                                                       |
| `utils/Monitor/Render.hh:159-169` `terminalReport`                                                             | reads `root.outName`                                                                          | takes `OutputPaths` only (or `OutputFile` if we standardize on it; pick one — `OutputPaths` is sufficient because `outName` is duplicated there)                                                                                                                                    |

#### Record

| File:line                                                                                     | Current                     | After                                                                                                                                                                                                                                                                                                                                                       |
| --------------------------------------------------------------------------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `utils/Record/Finalizer.hh:43,76,87,88,104`                                                   | takes `OutputContext& root` | takes three refs `OutputFile& file, OutputPaths& paths` (skip `LimitsConfig` — Finalizer doesn't read limits). Inside: `root_.outFile` → `file_.handle`; `root_.histScale` → `file_.histScale`; `root_.checkpointOutName` etc. → `paths_.checkpointOutName`. The `Monitor::outputLog`/`terminalReport` call sites pass `paths_` and (where needed) `file_`. |
| `utils/Record/Meta.hh:115-116` `capture(..., const RunStats& log, const OutputContext& root)` | reads `root.beamEnergy`     | takes `(..., const RunStats& log, const OutputPaths& paths)`. The `physics.center_of_mass_energy_gev` parse at line 167-169 reads `root.beamEnergy.Data()`; rewire to `paths.beamEnergy.Data()`.                                                                                                                                                            |

#### Lambda (gated on REVIEW #15)

After REVIEW #15 splits `Parameters.hh`:

| File                                                                                                         | Change                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Lambda/Parameters.hh::levelBounds(const OutputContext&, ...)` (×2), `boundsFromNode<P>`, `resolveBounds<P>` | takes `const LimitsConfig&` (uses `.particleLimits`, `.eventLimits`)                                                                                                                                                                                                                                                                                                                                                                 |
| `Lambda/Loaders.hh::extractPhysics(..., const OutputContext&)`                                               | takes `(..., const LimitsConfig& limits)` — `root.histLimitsFile` → `limits.histLimitsFile`, `root.particleLimits` → `limits.particleLimits`, `root.eventLimits` → `limits.eventLimits`                                                                                                                                                                                                                                              |
| `Lambda/Declare.hh::declareObjects(..., OutputContext&)`                                                     | takes `(OutputFile& file, ...)` — `root.outFile` → `file.handle`, `root.binCount` → `file.binCount`                                                                                                                                                                                                                                                                                                                                  |
| `Lambda/Declare.hh::declareDataObjects(DataObjects&, OutputContext&)`                                        | takes `(DataObjects&, OutputFile&)` — `root.outFile` → `file.handle`                                                                                                                                                                                                                                                                                                                                                                 |
| `modules/Lambda.hh:33` `pythiaAnalysis(Pythia&, OutputContext&, AnalysisContext&)`                           | takes `(Pythia&, OutputPaths&, OutputFile&, AnalysisContext&)` — `root.checkpointOutName` → `paths.checkpointOutName`, `root.histScale` → `file.histScale`, `root.checkpointLogName` → `paths.checkpointLogName`. **Or**: rebundle these into the `AnalysisContext` (Section 6) so the handler signature shrinks back to `(Pythia&, AnalysisContext&)`. **Recommended: rebundle**, since Section 6 already proved the pattern works. |
| `modules/Lambda/Context.hh:19-24` `AnalysisContext`                                                          | add `OutputFile& file; OutputPaths& paths;` fields (or one `OutputBundle` aggregate). After this, drop the explicit `Config::OutputContext& root` argument from `pythiaAnalysis`.                                                                                                                                                                                                                                                    |

### Public API breakage

**This is the biggest break of the three sections.** Every Config consumer updates. The `extractConfiguration` overloads grow from 1 trailing `OutputContext&` to three trailing refs (or one aggregate). Two compromise options for callers who can't update everything at once:

**Option A (clean break):** Three separate refs everywhere. No back-compat. Simple, principled, churn ≈ §9.

**Option B (aggregate struct):** Add `struct OutputBundle { OutputFile file; OutputPaths paths; LimitsConfig limits; };` and have `extractConfiguration(..., OutputBundle&)` populate all three. Drivers declare a single `OutputBundle ctx;` and pass `ctx.file`, `ctx.paths`, `ctx.limits` to consumers individually. Reduces churn at the driver level (one variable instead of three) without re-merging the structs.

**Recommend Option B** because it preserves the "one variable in the driver" pattern (matches `AnalysisContext` from §6 — drivers already think in terms of context bundles after Phase 2). The split is at the type-system level, not at the callsite level.

### Files NOT touched in this section

- `utils/Probe/*` — no Config types beyond `Bounds` and friends, which stay where they are.
- `utils/Physics/*` — no Config dependency.
- `utils/Utility/*`, `utils/Paint/*` — no Config dependency.
- `tests/test_reconstructCandidates.cc` — no Config types.
- `tests/fixtures/make_lambda_fixture.cc` — direct ROOT API, no Config.

### Compile + test gate

```sh
make clean
make _Lambda_Parallel.exe _Lambda_Reconstruction.exe _Lambda_Data.exe _Lambda_Test.exe
make test
make _Monitor_FatalStall_Harness.exe && ./_Monitor_FatalStall_Harness.exe
```

The harness rebuild is again the canary for missed field-rewires. `make test` continues to pass `S1–S5` + `T1–T5`. Run `_Lambda_Parallel.exe configs/Lambda_Generation.toml` with the project's standard `event_count = 1000, serial = 99` testing config (per `bots/BOT.md`) and confirm the produced `.root` and `.log` files have identical structure to a pre-split baseline:

```sh
# pre-split baseline
git stash
make _Lambda_Parallel.exe && ./_Lambda_Parallel.exe configs/Lambda_Generation.toml
mv output baseline_output
git stash pop
# post-split
make _Lambda_Parallel.exe && ./_Lambda_Parallel.exe configs/Lambda_Generation.toml
diff -r baseline_output output  # expect: only timestamp / UUID differences
```

Verify the final state:

```sh
git grep -n 'OutputContext' utils/Config/Types.hh && echo "FAIL: OutputContext still defined"
```

Expected: zero hits in the definition file. `OutputContext` should remain only in comments and (transiently) in REVIEW.md before that line is updated to mark this section resolved.

---

## Recommended sequencing

1. **§5** first. It's the cleanest, lowest-risk decoupling. It removes Pythia8 from the `Monitor.hh` transitive include set, which makes the unit test cheaper to compile and removes the one place where the codebase fakes a Pythia interface.
2. **§9** next. Pure renaming, mechanical, but blocked on §5 if Finalizer changes interfere. Doing §9 second means Finalizer.hh is already de-templated, so the rename touches only the field types, not the template parameter list.
3. **REVIEW #15** (Parameters split) before §11. **Out of Phase 3's direct scope but a hard prerequisite** — must be planned and merged separately before §11 starts.
4. **§11** last. Highest blast radius, depends on both §9 (so it operates on `OutputContext` not `Register`) and #15 (so the limits-resolution split is already in place). Each prior section landing reduces §11's surface area.

Total estimated effort:
- §5: ½ day (including test verification).
- §9: ½ day (mechanical sweep + rebuild + tests).
- §11: 2 days (after #15 lands), gated on a reliable diff against a pre-split baseline.
