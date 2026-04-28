# Roadmap — Phase 4

> Companion to [REVIEW.md](REVIEW.md) (open backlog) and [MAP.md](MAP.md)
> (current state). This file holds the **active phase plan**: ordered work,
> with dependencies and an executable prompt per item.
>
> **Phases 1–3 are complete and removed from this file.** For their content,
> consult git history. Summary of what they shipped: Phase 1 fixed the P0
> build break and renamed `Lambda::Lambda` → `Lambda::Particle`. Phase 2 added
> `tests/`, `Watch::recordEvent`/`Watch::freeze`,
> `AnalysisContext`/`GenerationContext`, `Probe::resolveEventCount`, and
> `Config::readInputSection`. Phase 3 §5 dropped the `NoPythia` shim and
> de-templated `FinalizerController` + `Monitor::buildLogText` /
> `outputLog` / `terminalReport` to use callbacks. (Phase 3 §9 and §11 — the
> rename to `RunStats`/`OutputContext` and the `Register` split — were
> **planned but not implemented**; they re-enter the backlog as REVIEW items
> 1 and 12.)

---

## Phase 4

Each item below is sized (effort), has explicit dependencies, and includes a
self-contained execution prompt. Items are ordered by dependency: do them
top-to-bottom unless a dependency note says otherwise.

### Item ordering

| #   | Item                                                            | Effort   | Depends on           |
| --- | --------------------------------------------------------------- | -------- | -------------------- |
| 1   | Split `Lambda/Parameters.hh`                                    | one-day  | —                    |
| 2   | Migrate `_Lambda_Data.cc` to `FinalizerController`              | half-day | —                    |
| 3   | Add a "specified vs defaulted" sentinel for `event_count`       | half-day | —                    |
| 4   | Promote orphan harness into `tests/`                            | half-day | —                    |
| 5   | Add precompiled header for ROOT/Pythia8/toml++                  | one-day  | none (independent)   |
| 6   | Decide & retire the `Log`/`Root` aliases                        | one-day  | item 1 (parallel ok) |
| 7   | Split `Register` into `OutputFile`/`OutputPaths`/`LimitsConfig` | two-day  | items 1 + 6          |
| 8   | Per-event `EventScope` RAII helper                              | half-day | none                 |

Total estimated: ~6 working days if executed serially. Items 1, 2, 3, 4, 5,
8 have no inter-dependency and can be parallelized across agents.

---

### 1. Split `Lambda/Parameters.hh` into three files

**Effort:** one-day. **Depends on:** nothing. **Unblocks:** item 7.

`modules/Lambda/Parameters.hh:1-310` mixes three concerns. The split is the
hard prerequisite for any further `Register` refactor (item 7) because seven
functions in this file currently take `Config::Root&`.

#### Prompt (self-contained)

> Split `modules/Lambda/Parameters.hh` (310 lines) into three files. Read
> `modules/Lambda/Parameters.hh` end-to-end, then partition by concern:
>
> - **`modules/Lambda/Parameters.hh`** retains: `Recorded_ParticleProperties`
>   (lines 27–34), `kTreeEnabledSets` (36–38), `explicitBounds` (40–53),
>   `levelBounds` ×2 (55–79), `boundsFromNode<P>` (81–86), `resolveBounds<P>`
>   (88–103). All four `levelBounds`/`boundsFromNode`/`resolveBounds`
>   templates use `Config::Root&` for `particleLimits` / `eventLimits` —
>   keep them taking `Config::Root&` for now (item 7 will rewrite the type).
> - **(new) `modules/Lambda/Loaders.hh`** receives:
>   `loadInputSection` (123–139), `loadCandidatesSection` (141–157),
>   `extractPhysics` (264–309). Uses `toml++`, `Config::Root&` (read-only
>   for histLimits path), and the bounds helpers from `Parameters.hh`.
> - **(new) `modules/Lambda/Declare.hh`** receives:
>   `inputSchema` ×2 (105–121), `declareDataObjects` (159–176),
>   `shouldWriteTree` (178–191), `declareObjects` (193–262). All take
>   `Config::Root&` and write into ROOT objects.
>
> Update `modules/Lambda.hh` (the umbrella) to include the two new headers
> after `Parameters.hh`. Verify build: `make clean && make _Lambda_Parallel.exe
> _Lambda_Reconstruction.exe _Lambda_Data.exe _Lambda_Test.exe && make test`.
> Tests S1–S5 and T1–T5 must pass.
>
> Do **not** rename any function or change any signature in this item. The
> split is mechanical; rewrites belong to item 7.

---

### 2. Migrate `_Lambda_Data.cc` to use `FinalizerController`

**Effort:** half-day. **Depends on:** nothing.

`_Lambda_Data.cc:48-60` inlines `BuildIndex` + `outFile->Close` +
`logger.finish` + `Monitor::terminalReport` + `Monitor::outputLog` instead of
constructing a `FinalizerController`. This was deferred from Phase 3 §5
because the data driver is the only one whose tail differs (it does
`BuildIndex` before closing the file, which the controller doesn't currently
do).

#### Prompt (self-contained)

> Migrate `_Lambda_Data.cc` to use `Record::FinalizerController` like the
> other three drivers, eliminating the inline tail at `_Lambda_Data.cc:48-60`.
>
> The blocker: `FinalizerController::normalShutdown` at
> `utils/Record/Finalizer.hh:63-76` calls `writeAll(histogramSets_, ...)` and
> then `outFile->Write/Close`. `_Lambda_Data` does not declare histograms
> (it generates raw trees), and it calls `BuildIndex("event_index")` on
> the proton/pion trees (`_Lambda_Data.cc:48-49`) **before** closing the
> file. That step has no analog in the histogram drivers.
>
> Two choices:
>
> 1. **Add a `preCloseHook` callback to `FinalizerController`.** Construct
>    the controller with a third-style callback `std::function<void()>
>    preClose = {}` that fires inside `normalShutdown` after `writeAll` but
>    before `outFile->Write/Close`. `_Lambda_Data` passes
>    `[&]{ dataObjects.protons->BuildIndex("event_index");
>    dataObjects.pions->BuildIndex("event_index"); }`. Histogram drivers
>    pass nothing.
> 2. **Templatize `RootArrayT` to also accept `Lambda::DataObjects`.** Add
>    a free function `Record::writeAll(DataObjects&, ...)` that does the
>    `BuildIndex` calls. Heavier — `RootObjects<Basis>` is a structurally
>    different type from `DataObjects`.
>
> **Recommended:** option 1. It composes cleanly with the existing callback
> shape (`printStats`, `listChangedSettings` already trail the ctor). It
> also lets `Lambda::dataLogString()` flow through `programLogBuilder`
> instead of being constructed at the call site.
>
> After migration, `_Lambda_Data.cc` should compress to roughly:
> ```cpp
> Record::FinalizerController finalizer(
>     /* histogramSets unused; pass an empty RootArray<HistogramSet>{} */,
>     rootParams, logParams, logger,
>     []() { return Lambda::dataLogString(); },
>     [&pythia]() { pythia.stat(); },
>     [&pythia]() { pythia.settings.listChanged(); },
>     [&dataObjects]() {
>         if (dataObjects.protons) dataObjects.protons->BuildIndex("event_index");
>         if (dataObjects.pions)   dataObjects.pions->BuildIndex("event_index");
>     }
> );
> finalizer.installFatalStallHandler();
> // ... pythia.run() ...
> finalizer.normalShutdown();
> ```
>
> Verify: `make _Lambda_Data.exe` then run with `event_count = 1000`,
> `serial = 99`, output redirected to `outputs/test/`. The output ROOT file
> must still have `BuildIndex` applied (verify with `root -l outputs/test/...root
> -e 'auto t = (TTree*)_file0->Get("Protons"); std::cout << (t->GetTreeIndex() != nullptr) << std::endl'`).

---

### 3. Add a "specified vs defaulted" sentinel for `event_count`

**Effort:** half-day. **Depends on:** nothing.

REVIEW item 16. Removes the last `toml::parse_file` re-read from
`_Lambda_Reconstruction.cc:55-62`.

#### Prompt (self-contained)

> Eliminate the inline TOML re-parse in `_Lambda_Reconstruction.cc:55-62`.
>
> Current state: `Config::readEventsSection`
> (`utils/Config/Reader.hh:41-53`) writes `1000` as the default for
> `[events].event_count`, making it indistinguishable from a user-set
> value of 1000. The reconstruction driver works around this with an IIFE
> that re-parses the TOML to check key presence.
>
> Fix: add `bool eventCountExplicit = false;` to either `Config::Events`
> (`utils/Config/Types.hh:45-49`) or `Config::Watch`/`Register`. Recommend
> putting it on `Watch` because it's the struct the driver already reads
> from for `nEvents`. Populate it in `readEventsSection`:
>
> ```cpp
> const bool hasEventsKey = config["events"]["event_count"].is_value();
> const bool hasRunKey    = config["run"]["event_count"].is_value();
> watch.eventCountExplicit = hasEventsKey || hasRunKey;
> events.eventCount = static_cast<std::size_t>(
>     hasEventsKey ? config["events"]["event_count"].value_or(1000)
>                  : config["run"]["event_count"].value_or(1000));
> ```
>
> Then `_Lambda_Reconstruction.cc` becomes:
> ```cpp
> const std::size_t nEventsHint =
>     logParams.eventCountExplicit ? logParams.nEvents
>                                   : Probe::resolveEventCount(inputPath);
> ```
> The `<toml++/toml.hpp>` include at `_Lambda_Reconstruction.cc:5` and the
> entire IIFE at lines 55-62 disappear. Tier 3 (full key scan) stays in the
> driver as the final fallback.
>
> Verify both code paths: (a) run with `event_count = 1000` set in TOML —
> driver uses 1000, no warning; (b) comment out `event_count` in TOML —
> driver falls back to ROOT-file metadata, then key scan.

---

### 4. Promote `_Monitor_FatalStall_Harness.cc` into `tests/`

**Effort:** half-day. **Depends on:** nothing.

REVIEW item 7. The harness is real test code (verifies three paths in
`Monitor::AsyncLogger::runLoop`); it's just stranded outside the test
infrastructure.

#### Prompt (self-contained)

> Move `_Monitor_FatalStall_Harness.cc` into `tests/` and integrate it with
> `make test` / `tests/run_all.sh`.
>
> Steps:
>
> 1. `git mv _Monitor_FatalStall_Harness.cc tests/test_fatal_stall.cc`.
> 2. The Makefile rule `tests/%.exe: tests/%.cc` at `Makefile:21-23` already
>    builds the file with full ROOT + Pythia8 + toml++ link flags. The
>    harness only needs Config + Monitor (no Pythia, no ROOT histograms);
>    consider adding a stripped rule that drops `$(PYTHIA_FLAGS)` for
>    Monitor-only tests, but the cheap fix is just letting it use the full
>    flags.
> 3. Add `tests/test_fatal_stall.exe` to the `TEST_EXES` list at
>    `Makefile:18`.
> 4. Verify `make clean && make test` runs four test binaries (the existing
>    two plus this one) and they all pass.
>
> Do not rewrite the harness — it currently uses raw `assert`-style
> stderr+exit instead of the `tests/test_assert.hh` macros. Updating it to
> use `TEST_EQ`/`TEST_PASS` is a separate cleanup; out of scope here.

---

### 5. Precompiled header for ROOT / Pythia8 / toml++

**Effort:** one-day (mostly verification). **Depends on:** nothing.

Architecture audit E1. Header-only design + heavy external headers means
every TU re-parses the world. Cheap quality-of-life win.

#### Prompt (self-contained)

> Add a precompiled header to cut compile time. Read `Makefile` first.
>
> 1. Create `utils/PCH.hh` containing the heavy external headers shared by
>    every driver:
>    ```cpp
>    #pragma once
>    #include "TFile.h"
>    #include "TTree.h"
>    #include "TH1D.h"
>    #include "TH2.h"
>    #include "TString.h"
>    #include "TDirectory.h"
>    #include "TParameter.h"
>    #include "Math/Vector4D.h"
>    #include "Math/VectorUtil.h"
>    #include "Pythia8/Pythia.h"
>    #include "Pythia8/PythiaParallel.h"
>    #include <toml++/toml.hpp>
>    ```
> 2. Add to `Makefile`:
>    ```make
>    PCH := utils/PCH.hh.gch
>
>    $(PCH): utils/PCH.hh
>        @$(CXX) -x c++-header $< -o $@ $(ROOT_FLAGS) $(PYTHIA_FLAGS) $(TOML_FLAGS) $(BASE_CXXFLAGS)
>
>    %.exe: %.cc $(PCH)
>        @$(CXX) -include utils/PCH.hh $< -o $@ $(ROOT_FLAGS) $(PYTHIA_FLAGS) $(TOML_FLAGS) $(BASE_CXXFLAGS)
>    ```
> 3. Add `utils/PCH.hh.gch` to `.gitignore` and `make clean`.
> 4. Time three full clean rebuilds before and after on the slowest driver
>    (`_Lambda_Parallel.cc`). Record numbers in the commit message — if the
>    speedup is < 30%, revert; PCH carries its own complexity cost.
>
> Note: clang and gcc handle PCH differently. The Makefile uses
> `$(CXX) ?= g++`. If the project ships with clang on macOS in CI, the
> `-x c++-header` syntax still works but the `.gch` extension is
> compiler-specific (clang generates `.pch`). Check `$(CXX) --version` in
> the Makefile and switch the extension if needed.
>
> Do not include project headers in PCH (Config, Monitor, Lambda, …) —
> those change too often and would defeat the purpose.

---

### 6. Decide & retire the `Log`/`Root` aliases

**Effort:** one-day. **Depends on:** nothing mechanical, but executes more
cleanly after item 1 reduces the number of files that touch
`Config::Root`.

REVIEW item 1. Pick a destination first; do not migrate to `Watch`/`Register`
just to migrate again to `RunStats`/`OutputContext` later.

#### Prompt (self-contained)

> First decide: do `Watch`/`Register` stay as the canonical names, or rename
> to `RunStats`/`OutputContext` (audit-recommended)? Read both names'
> consumers in `utils/Monitor/Render.hh:59-153` (six function signatures),
> `utils/Record/Finalizer.hh:43-115` (one class), `modules/Lambda.hh:33`,
> `modules/Lambda/Context.hh:25, 33`, `modules/Lambda/Parameters.hh:55-266`
> (seven functions), and the four drivers. Pick the names that read best in
> those contexts — they're where the type names are actually written.
>
> Then execute as a single mechanical pass:
>
> 1. Rename the `struct Watch` (or `Register`) at
>    `utils/Config/Types.hh:76` (or `:112`) to the chosen name. The
>    out-of-line `Watch::recordEvent` and `Watch::freeze` definitions in
>    `utils/Config/TypeAid.hh:34, 44` move with the rename.
> 2. Delete the alias declarations at `utils/Config/Types.hh:137-138`.
> 3. Sweep every consumer listed in REVIEW item 1's table (~50 occurrences
>    across 14 files) and replace `Config::Log` → new name,
>    `Config::Root` → new name. Sweep with `sed -i`; verify with
>    `grep -rn 'Config::Log\|Config::Root'` returning empty.
> 4. The compiler enforces correctness — any remaining alias use becomes a
>    compile error.
>
> Verify: `make clean && make _Lambda_Parallel.exe _Lambda_Reconstruction.exe
> _Lambda_Data.exe _Lambda_Test.exe && make test`. Tests must pass.
>
> Do not split `Register` (= `Root`) in this item. That's item 7. The
> rename is name churn; the split is structural.

---

### 7. Split `Register` into `OutputFile`/`OutputPaths`/`LimitsConfig`

**Effort:** two-day. **Depends on:** items 1 (splits Lambda/Parameters.hh
which holds the largest block of `Config::Root&` consumers) **and** 6 (sets
the canonical name; without it this item churns through aliases).

REVIEW item 12. The largest item in Phase 4. After this lands, every
consumer asks for the smallest object that satisfies its needs.

#### Prompt (self-contained)

> Split `utils/Config/Types.hh:112-131` (`struct Register` /
> `struct OutputContext` after item 6) into three structs along the lines
> outlined in REVIEW item 12. Add a thin `OutputBundle` (or similar) struct
> that aggregates the three so existing single-argument signatures stay
> ergonomic during the transition.
>
> Steps:
>
> 1. Define in `utils/Config/Types.hh`:
>    ```cpp
>    struct OutputFile { TFile* outFile = nullptr;
>                        Int_t binCount = 100;
>                        Double_t histScale = 100;
>                        TString beamEnergy = ""; };
>    struct OutputPaths { TString rootDirectory, logDirectory, checkpointDirectory;
>                         TString outName, logName, runStatName, threadStatDirectory;
>                         TString checkpointOutName, checkpointLogName;
>                         TString fileTitle; };
>    struct LimitsConfig { TString histLimitsFile;
>                          ParticleLimits particleLimits;
>                          EventLimits    eventLimits; };
>    struct InputConfig { std::string inputPath; };  // promoted from Register::inputPath
>    struct OutputBundle { OutputFile& file; OutputPaths& paths; LimitsConfig& limits; InputConfig& input; };
>    ```
> 2. `utils/Config/Reader.hh::readPathsAndFile` (`:112-182`) is the largest
>    consumer; split its updates into the new structs. `readInputSection`
>    (`:58-68`) writes to the new `InputConfig`. `loadMonitorDefaults`
>    (`utils/Config/Defaults.hh:84-100`) writes to `OutputFile`.
> 3. Update `Config::extractConfiguration` (`utils/Config.hh:96-102`) to
>    take `OutputFile&, OutputPaths&, LimitsConfig&, InputConfig&` as four
>    args (or one `OutputBundle`).
> 4. Update consumers field-by-field. `Monitor::AsyncLogger::start`
>    (`utils/Monitor/Logger.hh:27`) only needs `OutputPaths`. `Monitor::outputLog`
>    only needs `OutputFile.beamEnergy + binCount + histScale` and
>    `OutputPaths.logName`. Tighten signatures wherever obvious.
> 5. `_Lambda_Reconstruction.cc:25` (`rootParams.inputPath`) becomes
>    `inputCfg.inputPath`.
> 6. Delete `struct Register` (or `struct OutputContext`) and any remaining
>    `Config::Root` reference.
>
> This is the single most invasive item in Phase 4. Land item 1 and item 6
> first to keep the diff focused on type splits, not concurrent renames or
> file moves.
>
> Verify: same compile + test gate as items 1 and 6.

---

### 8. Per-event `EventScope` RAII helper

**Effort:** half-day. **Depends on:** nothing.

REVIEW item 11. Phase 2 already extracted step 4 (`Watch::recordEvent`); this
finishes the pattern.

#### Prompt (self-contained)

> Collapse the per-event boilerplate in `modules/Lambda.hh` (three handlers,
> six steps each — see REVIEW item 11). Read the file first.
>
> Add to `modules/Lambda/Context.hh` (or a new `modules/Lambda/EventScope.hh`):
>
> ```cpp
> namespace Lambda {
>     struct EventScope {
>         Config::Log&          logging;
>         Monitor::AsyncLogger& logger;
>         int                    workerIndex;
>         std::size_t            eventIndex;
>
>         EventScope(Config::Log& log, Monitor::AsyncLogger& l, int worker)
>             : logging(log), logger(l), workerIndex(worker),
>               eventIndex(++logging.iEvent)
>         {
>             logger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Analysis,
>                                       eventIndex, Monitor::NoCallbackCompleted);
>         }
>         ~EventScope() {
>             logging.recordEvent(std::chrono::system_clock::now());
>             logger.publish(logging, Monitor::RunPhase::Analysis, Monitor::DontWriteRunStat);
>             logger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Simulation,
>                                       eventIndex, Monitor::CallbackCompleted);
>         }
>         EventScope(const EventScope&)            = delete;
>         EventScope& operator=(const EventScope&) = delete;
>     };
> }
> ```
>
> Each handler then becomes:
> ```cpp
> inline void rootAnalysis(const Probe::Event& ev, int threadId,
>                          std::mutex& histMutex, AnalysisContext& ctx)
> {
>     EventScope scope{ctx.logging, ctx.asyncLogger, threadId};
>     // ... user work using scope.eventIndex ...
> }
> ```
>
> Note: `pythiaAnalysis` has an additional pre-event branch
> (`if (eventIndex == 1) pythia.info.list();` at `modules/Lambda.hh:39-43`)
> and a post-event checkpoint branch (`Lambda.hh:55-58`). Both stay outside
> the scope's RAII region — handle them explicitly inside the function body.
>
> Verify: `make test` (S1–S5 confirms `nRealEvents==50` is still correct;
> if the destructor isn't running on every event, that assertion fires).
> Also run `_Lambda_Test.exe` and confirm the per-event sleep/print rhythm
> looks right.

---

## Other observations (deferred — not in Phase 4)

These were noted while reading the actual source. None block Phase 4; they
would form a Phase 5 candidate list.

### Configurability and inputs

- **Hardcoded `cmnd_file` paths.** `_Lambda_Parallel.cc:19`,
  `_Lambda_Test.cc:18`, `_Lambda_Data.cc:20` all hardcode
  `"configs/Lambda_Reconstruction.cmnd"` instead of reading the path
  through `Config::PythiaConfig::cmndFile` (which already exists at
  `utils/Config/Types.hh:54`). The `[pythia]` section is read by
  `readPythiaSection` (`utils/Config/Reader.hh:184-189`) but only inside
  `configurePythia<T>` (`utils/Config.hh:49-70`), which the drivers don't
  call — they call `extractConfiguration` instead. Wire `cmnd_file` into
  the standard configuration path so drivers stop hardcoding.
- **`General_Limits.toml` is a hard requirement that throws.**
  `utils/Config/Defaults.hh:73`'s `loadLimitsFile("configs/General_Limits.toml", ...)`
  throws if the file is absent (`Defaults.hh:40-42`). There's no fallback,
  no warning. A user with a self-contained limits file in
  `[lambda].hist_limits` still gets killed by this. Either make it optional
  with a one-line warning, or document the requirement loudly in BOT.md
  and CLAUDE.md.
- **`hist_limits` resolution is silent.** `Config::resolveLimitsPath`
  (`utils/Config/LimitAid.hh:7-15`) silently expands a bare name into
  `configs/<name>.toml`. If the user typoed or moved the file, the only
  signal is a downstream `Histogram limits file does not exist` exception
  (`Lambda/Parameters.hh:281-283`). Print the resolved path on first read.

### Robustness and fallbacks

- **`Watch::eventMutex_` lives next to `std::atomic<std::size_t> iEvent`.**
  `iEvent` is incremented atomically (no mutex); `nRealEvents` and `elapsed`
  are guarded by `eventMutex_` (`utils/Config/TypeAid.hh:34-38`). Two
  different sync disciplines on adjacent fields is the original A1 smell —
  Phase 2 fixed the silent corruption but didn't unify the discipline.
  Consider making `nRealEvents` atomic too and dropping the mutex (the
  `recordEvent` body becomes lock-free).
- **`AsyncLogger::runLoop` has five `std::optional<...>` locals shuttled
  across one lock boundary** (`utils/Monitor/Logger.hh:212-280`). Works,
  hard to extend. A small `std::queue<Action>` drained outside the lock
  would make adding a new heartbeat tick (e.g. memory-usage probe) a
  one-line change instead of editing six places.
- **`Probe::runParallel` swallows then rethrows the *first* worker
  exception** (`utils/Probe/Parallel.hh:62-63, 108-109`). If two workers
  fault, the second's diagnostic is lost. Aggregate or chain them.
- **`tests/run_all.sh:30` `break`s on first failure.** Means a regression
  in `test_reconstructCandidates` masks any later regression in
  `test_rootAnalysis_smoke`. Drop the `break`; report total pass/fail at
  the end.

### Performance and efficiency

- **Every `runParallel` worker re-opens the input file** via a fresh
  `EventStream` (`utils/Probe/Parallel.hh:99-105`). On NFS or with
  lazy-load TFile drivers this matters. A shared TFile pool isn't free to
  build (TFile is not thread-safe; `TThreadedObject<TFile>` is the ROOT
  pattern), but the cost is paid once at scale.
- **`Lambda::reconstructCandidates`** (`modules/Lambda/Reconstruction.hh:54-101`)
  is `O(P × π)` on every event with `P = nProtons` (default 24,
  `reservedProtons = 20` + ~4 signal) and `π = nPions` (variable). For
  every pair it boosts to the CM frame and computes `cosTheta`, even when
  the mass cut already rejected the pair. Reorder: mass cut first, then
  `cosTheta` only on survivors. Currently the code does compute `cosTheta`
  before the mass cut (line 71 vs line 72), which is wasted work.
- **`Watch::freeze()`** (`utils/Config/TypeAid.hh:44-63`) heap-allocates a
  fresh `Watch` on every fatal-stall snapshot. The fatal path is
  one-shot, so this is fine. Mention: `Finalizer.hh:81` wraps the result
  in `shared_ptr` immediately, paying for two allocations (the `Watch`
  itself plus the control block); use `make_shared<Watch>` directly inside
  `freeze()` if a future change wants both allocations fused.

### Readability and abstraction depth

- **Field naming inconsistency in `Config::Watch`.** Most fields are
  camelCase (`iEvent`, `nEvents`, `printInterval`); three are
  snake_case (`heartbeat_interval`, `terminal_refresh_interval`,
  `program_stall_threshold`). Pick one.
- **`Config::Register::*Name` vs `Config::Register::*Directory`.** Mixed:
  `outName`, `logName`, `runStatName`, `checkpointOutName`,
  `checkpointLogName` (file paths) live next to `rootDirectory`,
  `logDirectory`, `checkpointDirectory`, `threadStatDirectory` (directory
  paths). After the item-7 split, normalize to `*File` and `*Dir`.
- **`Lambda::ParamAid.hh::resolveCandidateLabels`**
  (`modules/Lambda/ParamAid.hh:42-47`) exists because PID lookup is
  threaded through two layers (`labelForPidAbs` then the pair). Inline.
- **`Probe/Parallel.hh::runParallel` has two near-identical worker loops**
  (lines 53-61 for vec, lines 98-106 for flat). Extract the common spawn
  pattern.

### Reduced nested abstractions

- **`Lambda/Recording.hh::fillCandidates`** (lines 35-44) calls
  `Record::resetAllCounts(histogramSets)`, then `Lambda::fill` per
  particle (which calls `Record::fill` per histogram), then
  `Record::countAll(histogramSets)`. Three traversal loops over the
  same array. Combine into one pass with a state machine, or accept the
  redundancy and document why three passes is the right choice.
- **`Record/Histogram.hh::write` and `writeToDir`** (lines 128-159) are
  identical except for the `dir->cd()` placement. Either parameterize, or
  drop one — at runtime they always pair up.
