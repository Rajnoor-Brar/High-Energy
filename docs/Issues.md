# Plan — `Probe::ProbeParallel` + `Config::configure` facade + `AsyncLogger::watch()`

## Context

After two sessions, the primary architectural goal remains undelivered: drivers still
declare `Config::Register`, `Config::Watch`, and `Config::ProbeConfig` explicitly, and
no `Config::configure` facade exists. This plan delivers exactly what was requested:

```cpp
// Target driver shape — Probe pipeline
Probe::ProbeParallel  probe;
Record::Writer        writer;
Monitor::AsyncLogger  logger;

Config::configure(configPath, project, probe, writer, logger);

// ...declare histograms, build finalizer using logger.watch()...
logger.watch().start = std::chrono::system_clock::now();
logger.start(writer);  // UI initiation + startTime marking (kept on AsyncLogger)
probe.run([&](const Probe::Event& ev, int tid){ /* analysis */ });
// ...shutdown...
```

---

## What exists vs. what's missing

**Exists (post-W7):**
- `Config::configureProbe(configPath, project, Watch&, Register&, ProbeConfig&)` — legacy signature
- `Config::configurePythia<T>(configPath, project, Watch&, Register&, PythiaT&)` — legacy signature
- `Config::configuration(...)` — old facade (named wrong, exposes Register)
- `Record::configureWriter(Writer&, project, configPath, Watch&, Register&, inputFile)`
- `Record::FinalizerController` — fully implemented, takes `Writer&, Config::Watch&, AsyncLogger&`
- `AsyncLogger::start(const Record::Writer&, const Config::Watch&)` — exists

**Missing / broken:**
- `Probe::ProbeParallel` class — does not exist; `runParallel` is still a free function
- `Config::configure` facade — does not exist
- `AsyncLogger::watch()` accessor — Watch is not owned by AsyncLogger
- `Config::extractConfiguration` — called by 3 drivers (`_Lambda_Parallel`, `_Lambda_Test`,
  `_Lambda_Data`) but **never defined anywhere** (current build error)
- `fillDerived` last param is `Config::Register&` — blocks Register removal from drivers

---

## Step-by-step implementation

### Step 1 — Add `watch_` to `AsyncLogger` + `watch()` accessor
**File:** `utils/Monitor/Logger.hh`

Add private member:
```cpp
Config::Watch watch_;
```

Add public accessors:
```cpp
Config::Watch&       watch()       { return watch_; }
const Config::Watch& watch() const { return watch_; }
```

Add single-arg `start()` overload that delegates to the existing two-arg overload:
```cpp
void start(const Record::Writer& writer) {
    start(writer, watch_);
}
```

Keep existing `start(const Record::Writer&, const Config::Watch&)` unchanged — still
used by legacy call sites until they migrate in Steps 5–7. Do NOT change `publish()`
or any other method signatures.

---

### Step 2 — Create `Probe::ProbeParallel`
**File:** `utils/Probe/ProbeParallel.hh` (new file)

```cpp
#pragma once
#include "Probe/Types.hh"
#include "Probe/Parallel.hh"
#include "Probe/EventCount.hh"

namespace Probe {

class ProbeParallel {
  public:
    // Populated by Config::configure:
    std::string                 inputFile;
    std::vector<CollectionSpec> collections;
    std::size_t                 nThreads = 0;
    std::size_t                 nEvents  = 0;  // 0 = not yet resolved

    // Resolve nEvents from the input file if still 0 after configure.
    void resolveEvents() {
        if (nEvents == 0)
            nEvents = Probe::resolveEventCount(inputFile);
        if (nEvents == 0)
            nEvents = EventStream(inputFile, collections).nEvents();
    }

    // Run the parallel event loop (wraps Probe::runParallel).
    template<typename Callback>
    void run(Callback&& callback) const {
        runParallel(inputFile, collections,
                    std::forward<Callback>(callback), nThreads, nEvents);
    }
};

} // namespace Probe
```

**File:** `utils/Probe.hh` — append at end (before closing include guard / pragma):
```cpp
#include "Probe/ProbeParallel.hh"
```

---

### Step 3 — Change `fillDerived` last param: `Register&` → `Paths&`
**File:** `utils/Record/Meta.hh`

Add `#include "Record/Configs.hh"` near top (after `#include "Config.hh"`).

Change signature (~line 211):
```cpp
// Before:
inline void fillDerived(Record& r, const std::string& analysisName,
                        const std::string& configPath,
                        const Config::Watch& log, const Config::Register& root)

// After:
inline void fillDerived(Record& r, const std::string& analysisName,
                        const std::string& configPath,
                        const Config::Watch& log, const Record::Paths& paths)
```

Change the one use of `root` inside the body:
```cpp
// Before:
r.physics.center_of_mass_energy_gev = std::stod(std::string(root.beamEnergy.Data()));
// After:
r.physics.center_of_mass_energy_gev = std::stod(std::string(paths.beamEnergy.Data()));
```

Fix the backward-compat `capture()` wrapper (it calls `fillDerived` with a Register):
```cpp
inline Record capture(const std::string& analysisName, const std::string& configPath,
                      const Config::Watch& log, const Config::Register& root)
{
    Record r;
    mergeFromToml(r, configPath);
    Record::Paths tmp;
    tmp.beamEnergy = root.beamEnergy;        // only field fillDerived uses from Register
    fillDerived(r, analysisName, configPath, log, tmp);
    return r;
}
```

**File:** `utils/Record/Writer.hh` — `configureWriter` calls `fillDerived` at line 133.
Change:
```cpp
// Before:
Meta::fillDerived(meta, project, configPath, watch, reg);
// After (paths is in scope at this point, constructed at lines 108-120):
Meta::fillDerived(meta, project, configPath, watch, paths);
```

---

### Step 4 — Add `Config::configure` facade overloads + `extractConfiguration` alias
**File:** `utils/Config.hh`

Add forward declarations before the `namespace Config {` block (to avoid circular includes,
since `Probe.hh` and `Monitor.hh` both `#include "Config.hh"`):
```cpp
namespace Probe   { class ProbeParallel; }
namespace Monitor { class AsyncLogger;   }
// Record::Writer already forward-declared or included via Record/Writer.hh
```

Inside `namespace Config`:

**Alias that fixes 3 broken drivers immediately:**
```cpp
inline void extractConfiguration(const std::string& configPath,
                                 const std::string& project,
                                 Watch& watch, Register& reg) {
    configuration(configPath, project, watch, reg);
}
```

**Probe pipeline facade** (requires full types — place after the forward decls, relies on
drivers having included `Probe.hh`, `Record.hh`, `Monitor.hh` before `Config.hh`):
```cpp
inline void configure(const std::string&    configPath,
                      const std::string&    project,
                      Probe::ProbeParallel& probe,
                      Record::Writer&       writer,
                      Monitor::AsyncLogger& logger)
{
    Register    reg;
    ProbeConfig probeConfig;
    configureProbe(configPath, project, logger.watch(), reg, probeConfig);

    probe.inputFile   = probeConfig.inputFile;
    probe.collections = Probe::toCollectionSpecs(probeConfig);
    probe.nThreads    = resolveThreadCount(probeConfig.eventConfig.nThreads);
    probe.nEvents     = probeConfig.eventConfig.eventCount;

    Record::configureWriter(writer, project, configPath,
                            logger.watch(), reg, probeConfig.inputFile);
}
```

**Pythia pipeline facade** (extracts beamEnergy fallback from Pythia settings after
`configurePythia` runs, handles the case where beam energy is in the cmnd file not TOML):
```cpp
template<typename PythiaT>
inline void configure(const std::string&    configPath,
                      const std::string&    project,
                      PythiaT&              pythia,
                      Record::Writer&       writer,
                      Monitor::AsyncLogger& logger)
{
    Register reg;
    configurePythia(configPath, project, logger.watch(), reg, pythia);

    // Fallback: if TOML had no beam_energy, read it from Pythia's settings
    // (cmnd file may have set Beams:eCM before configure was called).
    if (reg.beamEnergy.IsNull() || reg.beamEnergy == TString("")) {
        const double ecm = pythia.settings.parm("Beams:eCM");
        if (ecm > 0) reg.beamEnergy = Form("%.0f", ecm);
    }

    Record::configureWriter(writer, project, configPath, logger.watch(), reg, "");
}
```

**Include ordering note:** The two `configure` overloads use `Probe::toCollectionSpecs`,
`Record::configureWriter`, and `Monitor::AsyncLogger::watch()` — these need full types.
Drivers include `Probe.hh`, `Record.hh`, `Monitor.hh` before `Config.hh`, so this is
satisfied at driver scope. Add a comment in Config.hh documenting this requirement.
If standalone Config.hh inclusion (e.g. in tests) breaks, add the three includes at
the bottom of Config.hh after the namespace closes.

---

### Step 5 — Migrate `_Lambda_Reconstruction.cc`

```cpp
Probe::ProbeParallel  probe;
Record::Writer        writer;
Monitor::AsyncLogger  asyncLogger;

Config::configure(configPath, project, probe, writer, asyncLogger);

Lambda::Parameters physParams;
Lambda::extractPhysics(configPath, physParams, writer.histConfig());
Lambda::RootArray histogramSets;
Lambda::declareObjects(histogramSets, physParams, writer);

Record::FinalizerController finalizer(
    histogramSets, writer, asyncLogger.watch(), asyncLogger,
    [&physParams]() { return Lambda::logString(physParams); }
);
finalizer.installFatalStallHandler();

probe.resolveEvents();
asyncLogger.watch().nEvents = probe.nEvents;          // sync after resolution
asyncLogger.watch().start   = std::chrono::system_clock::now();
asyncLogger.start(writer);                            // UI init + startTime marking

Lambda::AnalysisContext ctx{histogramSets, physParams, asyncLogger.watch(), asyncLogger};
std::mutex histMutex;
probe.run([&](const Probe::Event& ev, int tid) {
    Lambda::rootAnalysis(ev, tid, histMutex, ctx);
});

writer.meta().dataset.parent_files = {probe.inputFile};
Record::Meta::fillDerived(writer.meta(), project, configPath,
                           asyncLogger.watch(), writer.paths());
finalizer.setMeta(writer.meta());
finalizer.normalShutdown();
```

**Removed from driver:** `Config::Register rootParams`, `Config::Watch logParams`,
`Config::ProbeConfig probeConfig`, `Probe::toCollectionSpecs(...)` call,
`Probe::runParallel(...)` call, manual event-count resolution block.

---

### Step 6 — Migrate Pythia drivers

**`_Lambda_Parallel.cc` and `_Lambda_Test.cc`** — replace `Register` + `Watch` +
`extractConfiguration` with the Pythia `configure` overload:

```cpp
Pythia8::PythiaParallel pythia;           // (or Pythia8::Pythia for _Test)
pythia.readFile("configs/Lambda_Reconstruction.cmnd");  // sets Beams:eCM

Record::Writer       writer;
Monitor::AsyncLogger logger;

Config::configure(configPath, project, pythia, writer, logger);

// ...histogram setup...
Record::FinalizerController finalizer(
    histogramSets, writer, logger.watch(), logger, ...
);
finalizer.installFatalStallHandler();
pythia.init();
logger.watch().start = std::chrono::system_clock::now();
logger.start(writer);
// ...run loop using logger.watch()...
finalizer.normalShutdown();
```

**`_Lambda_Data.cc`** — same pattern. The `preCloseHook` for `BuildIndex` calls is
already wired through FinalizerController (from W7) — keep it. FinalizerController
is constructed AFTER the run loop in this driver (current structure) — that stays.

---

### Step 7 — Migrate `tests/test_rootAnalysis_smoke.cc`

Same migration as `_Lambda_Reconstruction.cc` (Step 5). Replace `logParams` +
`rootParams` + manual configureProbe/configureWriter with `configure` facade.

---

## Critical files

| File | Change |
|---|---|
| `utils/Monitor/Logger.hh` | Add `Config::Watch watch_`; `watch()` accessor; `start(writer)` overload |
| `utils/Probe/ProbeParallel.hh` | **New** — `Probe::ProbeParallel` class |
| `utils/Probe.hh` | Add `#include "Probe/ProbeParallel.hh"` |
| `utils/Record/Meta.hh` | `fillDerived`: `Register&` → `Paths&`; add Configs.hh include; fix `capture()` |
| `utils/Record/Writer.hh` | `configureWriter`: pass `paths` not `reg` to `fillDerived` |
| `utils/Config.hh` | Add `extractConfiguration` alias + two `configure` overloads |
| `_Lambda_Reconstruction.cc` | Full migration |
| `_Lambda_Parallel.cc` | Migrate to Pythia `configure` |
| `_Lambda_Test.cc` | Migrate to Pythia `configure` |
| `_Lambda_Data.cc` | Migrate to Pythia `configure` |
| `tests/test_rootAnalysis_smoke.cc` | Migrate to clean driver |

---

## Verification

After Steps 1–4 (non-driver changes):
```bash
make clean && make _Lambda_Reconstruction.exe _Lambda_Parallel.exe _Lambda_Test.exe _Lambda_Data.exe
```
Must build clean.

After Step 7:
```bash
make test   # T1–T5 + S1–S5 must all pass
```

Final sanity check — no legacy declarations remain in drivers:
```bash
grep -n "Config::Register\|Config::Watch\|Config::ProbeConfig\|extractConfiguration" \
    _Lambda_*.cc tests/test_rootAnalysis_smoke.cc
# Must return empty
```