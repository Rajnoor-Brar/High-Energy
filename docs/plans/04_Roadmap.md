# 04 — Integration Roadmap

Date: 2026-09-16 · Status: **Plan only — do not implement until explicitly requested.**

Implements the decision in `03_IntegrationOptions.md` (0 → A → B → C;
D deferred; E optional). Every phase ends in a working state and has its
own verification. Finding IDs (A1, B1, M1, R1 …) refer to
`01_CurrentState.md`.

---

## Phase overview

| Phase | Theme | Outcome | Effort | Depends on |
|---|---|---|---|---|
| 0 | Hygiene & defects | Current workflows correct, versioned, rebuildable | ½–1 d | — |
| 1 | Config foundations | One strict, parsed config document; beam-energy fix; sweep model | 1–2 d | 0 |
| 2 | Monitor/Output decoupling | Monitor and naming usable without `Record::Writer` | 1–2 d | 1 |
| 3 | In-process Rivet (`Observe::`) | `_Generate.exe` runs Pythia+Rivet with Monitor, signals, σ, provenance | 3–4 d | 2 |
| 4 | Event sinks (`Generate::`) | One loop → Rivet + Record + HepMC sinks; Lambda drivers ported | 2–3 d | 3 |
| 5 | Python layer on unified schema | `tools/` launch/plot from the same TOML; old schema migrated | 1 d | 1 (can run parallel to 3–4) |
| 6 | Optional | YODA source in Paint (E); HepMC ingest (D); multiweight PDFs | later | 3–4 |

---

## Phase 0 — Hygiene & defects

| Task | Fixes | Files |
|---|---|---|
| 0.1 Move `rivpyth`, `ydplt`, `ydmrg`, `rivpyth_common.py`, `rivpyth.example.toml` into repo `tools/`; `setup.sh` adds `$HIGH_ENERGY_ROOT/tools` to PATH | B2 | new `tools/`, `~/HEP/setup.sh` |
| 0.2 FIFO hang: start Rivet only after the generator has opened the pipe, or poll both processes (`wait` on whichever exits first; if generator exits non-zero, kill Rivet). Generator: open the HepMC output **before** `init()` or exit with a distinct code | B1 | `tools/rivpyth`, `generator.cc` |
| 0.3 Makefile: restore `-MMD -MP` + `-include`; per-target library sets (e.g. `PhotoProduction/%.exe: LIBS += rivet hepmc3`, Lambda gets ROOT+Pythia+toml only); lazy `*-config` evaluation (`=` not `:=`); `tests/%.exe` rule emitting where `run_all.sh` looks | M1–M3 | `Makefile`, `tests/run_all.sh` |
| 0.4 Lambda configs/paths: `cmnd_file`, `hist_limits`, driver defaults, test path → `configs/lambda/…`; `LimitAid` accepts sub-directory names | A1 | `configs/lambda/*.toml`, `LimitAid.hh`, `sources/Lambda/*.cc`, `tests/test_utils_hardening.cc` |
| 0.5 Migrate `eic140.toml`/`eic63.toml` to current schema; fix `eic140` cmnd/plugin/hepmc names | B2 | `configs/PhotoProduction/` |
| 0.6 `generator.cc`: validate args, honour cmnd `Main:numberOfEvents` when N ≤ 0, fix header, drop redundant mutex (or keep with comment re `processAsync`) | B7, B12 | `generator.cc` |
| 0.7 `setup.sh`: drop leading `:` in `RIVET_ANALYSIS_PATH` | B11 | `~/HEP/setup.sh` |

**Verify:** `rivpyth` with a missing cmnd exits non-zero in < 5 s; a
single-PDF 10k run reproduces the current YODA (same seed ⇒ identical
histograms); touching a `utils/*.hh` rebuilds a Lambda driver;
`tests/run_all.sh` finds and runs the suite; `_Lambda_Parallel.exe
configs/lambda/Lambda_Generation.toml` (event_count=1000) completes.

---

## Phase 1 — Config foundations

### 1.1 One parsed document

```cpp
// utils/Config/Document.hh (new)
namespace Config {
    struct Document {
        std::string  path;      // file or directory as given
        toml::table  table;     // merged (Utility::Toml::parseConfigTable)
        std::string  snapshot;  // serialized merged table for provenance
    };
    Document load(const std::string& path);   // parse once, rejectSectionAliases, key audit
}
```

- Every `configure*` gains a `const Config::Document&` overload; the
  existing `const std::string& configPath` overloads become one-line
  wrappers (no call-site churn for Lambda).
- `Record::Meta::fillDerived` stores `doc.snapshot` (the *merged* config,
  which a directory config currently loses — it reads the path as a file).

### 1.2 Strictness parity with `rivpyth_common`

`Utility::Toml` additions:

```cpp
template<class T> T require(const toml::table&, std::string_view key, std::string_view section);
template<class T> T optional(const toml::table&, std::string_view key, T fallback, std::string_view section); // type mismatch → throw, not fallback
void auditKeys(const toml::table&, std::initializer_list<std::string_view> known, std::string_view section); // unknown → warning
```

Each subsystem declares its known keys next to its reader (keeps section
ownership).

### 1.3 Beam energy (A2)

- `[pythia].beam_energy` → **rejected** when the cmnd sets
  `Beams:frameType != 1` (message points to the cmnd file).
- `Config::configurePythia` no longer derives the title energy before
  `init()`. Instead `OutputPlan` (Phase 2) accepts a late-bound
  `energyGeV` filled from `pythia.info.eCM()` after `init()`; directories
  are created at that point.

### 1.4 Sweep model

```toml
[sweep]
over      = "pdf"                       # first dimension; later: "cmnd", "option"
values    = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]
labels    = ["MSTW 2008 LO", "NNPDF 2.3 QCD+QED LO"]   # legend text
tags      = ["MSTW", "NNLO"]           # filename-safe
select    = 0                           # 0 = all, i = one-based point
tag_style = "index"                     # index | value | tag
seed_step = 1                           # seed_i = seed + (i-1)*seed_step
```

```cpp
namespace Config {
    struct SweepPoint { std::size_t index; std::string value, label, tag; long seed; };
    std::vector<SweepPoint> expandSweep(const Document&, std::optional<std::size_t> cliSelect);
}
```

- Same semantics as today's `use_pdf`/`pdf_suffix`/`alias_suffix`/`effective_seed`.
- Python (`tools/`) calls the C++ expander via `_Generate.exe --list-points`
  (JSON) so naming lives in **one** place.

**Verify:** new unit tests in `tests/test_config.cc`: type mismatch
throws; unknown key warns; `frameType=2` + `beam_energy` throws; sweep
expansion matches the current Python naming for `eic28.toml` (golden list).

---

## Phase 2 — Monitor & output decoupling

### 2.1 `Monitor::RunPaths`

```cpp
namespace Monitor {
    struct RunPaths {
        std::string runStat, threadStatDir, log, output, title;
        int serial = 0;
    };
    struct ReportHooks {                       // replaces Writer-derived report text
        std::function<std::string()> header;   // e.g. output file, hist config, analyses
        std::function<std::string()> programLog;
        std::function<void()>        printStats, listChangedSettings;
    };
    void AsyncLogger::initialise(const RunPaths&, ReportHooks = {});
}
// Record keeps: void AsyncLogger::initialise(const Record::Writer&)  → forwards writer.runPaths()
```

- `Monitor/Report.hh` stops including `Record/Writer.hh`; the Writer
  supplies a `header` hook. This removes the include cycle noted in
  `docs/UtilsAudit.md` §11 Phase 3 and the ordering hack in `Monitor.hh`.
- Fatal-stall handler stays generic (`setFatalStallHandler`); non-Writer
  runs install their own (finalize partial YODA).

### 2.2 `Config::OutputPlan` (finishes W9 for naming)

```cpp
namespace Config {
    struct OutputPlan {
        std::string directory, logDirectory, checkpointDirectory;
        std::string prefix; bool withSerial, withEnergy, withEvents;
        int serial; std::size_t padding;
        std::string title(const std::string& energy, std::size_t nEvents,
                          const std::string& variantTag) const;
        std::string file(std::string_view ext, …) const;   // ".root" | ".yoda" | ".hepmc"
        void createDirectories() const;
    };
    OutputPlan readOutputPlan(const Document&, const std::string& project);  // from [record.paths]/[record.file]
}
```

- `readPathsAndFile` becomes a thin adapter filling `Register` from the plan (Lambda unchanged).
- Sweep points append `_<tag>` (matching today's YODA names).
- Consider renaming the sections to `[output.paths]`/`[output.file]` with
  `[record.*]` accepted + migration warning (they are no longer
  Record-specific) — **decision needed (Q1)**.

**Verify:** all existing tests green; Lambda e2e output path/filename
byte-identical to before; a Monitor-only test (`tests/test_monitor.cc`)
runs `initialise(RunPaths)` → publish → finish without Record.

---

## Phase 3 — In-process Rivet stage (`Observe::`)

### 3.1 Layout (house style)

```
utils/Observe.hh              umbrella; compiled only when HE_WITH_RIVET is defined
utils/Observe/Types.hh        RivetSpec {analyses, preloads, checkBeams, dumpPeriod, mode}, ObserveResult
utils/Observe/Configure.hh    [rivet] reader (+ key audit, migration from [analysis].riv_plugin)
utils/Observe/Sink.hh         RivetSink: per-worker {Pythia8ToHepMC, AnalysisHandler}
utils/Observe/Lifecycle.hh    init (locked), analyze, merge, setCrossSection, finalize, write
utils/Observe/Provenance.hh   Record::Meta::Record → YODA annotations (+ .meta.toml sidecar)
sources/PhotoProduction/_Generate.cc   driver (~70 lines, mirrors _Lambda_Parallel)
```

### 3.2 `[rivet]` section

```toml
[rivet]
analyses    = ["photo_5x41"]          # "NAME" or "NAME:OPT=VAL"
plugin_dir  = "output/PhotoProduction"
preloads    = []
check_beams = true
mode        = "inprocess"             # inprocess | external (FIFO, today's path) | off
concurrency = "serial"                # serial (processAsync=off, 1 handler) | parallel (per-worker handlers)
dump_period = 0                       # events; 0 = off (maps to setFinalizePeriod)
```

### 3.3 Driver sketch

```cpp
int main(int argc, char* argv[]) {
    Utility::Signals::installGracefulStop();
    const auto doc    = Config::load(argc > 1 ? argv[1] : "configs/PhotoProduction/eic28.toml");
    for (const auto& point : Config::expandSweep(doc, cliPoint(argc, argv))) {
        Pythia8::PythiaParallel pythia;
        Monitor::AsyncLogger    logger;
        Config::configurePythia(doc, point, pythia, logger);     // cmnd, seed, pdf, threads, quiet
        Observe::RivetSink      rivet(Observe::configure(doc));
        pythia.init();                                           // → info.eCM() known
        auto plan = Config::readOutputPlan(doc, "PhotoProduction");
        logger.initialise(plan.runPaths(pythia.info.eCM(), point), rivet.reportHooks());
        pythia.run(nEvents(doc), [&](Pythia8::Pythia* w) {
            if (Utility::Signals::stopRequested()) return;
            const auto i = logger.countEvent();
            rivet.analyze(*w);                                   // per-worker handler
            logger.watch().recordEvent(std::chrono::system_clock::now());
            logger.publish(Monitor::RunPhase::Analysis);
        });
        pythia.stat();
        rivet.finish(pythia.sigmaGen() * 1e9 /*mb→pb*/, sigmaErrPb(pythia),
                     provenance(doc, point, plan), plan.file(".yoda", point));
        logger.finish(logger.watch(), logger.watch().iEvent);
        if (Utility::Signals::stopRequested()) break;
    }
}
```

### 3.4 Build

- `Makefile`: `PhotoProduction/_Generate.exe` gets
  `$(ROOT) $(PYTHIA) $(HEPMC3) $(RIVET) $(TOML) -DHE_WITH_RIVET`
  (`rivet-config --cxxflags --ldflags --ldlibs` already yields FastJet +
  HepMC3 + YODA).
- Lambda drivers never include `Observe.hh` → still build on a Mac
  without Rivet.

**Verify (equivalence gate — must pass before Phase 4):**
1. Same cmnd, seed, 100k events: in-process YODA vs FIFO YODA — histogram
   shapes agree within statistics (`yodadiff`, χ²/ndf per histogram), σ
   annotation equals `pythia.stat()` merged value.
2. `concurrency = parallel` vs `serial`: identical `sumW` totals
   (guards against R1-style double merges).
3. Wall-time benchmark vs FIFO at 1, 8, 20 threads (answers B6 with numbers).
4. SIGINT mid-run → partial YODA written with `n_events_processed` < N.
5. Missing plugin / bad analysis name → non-zero exit **before** generation starts.

---

## Phase 4 — Event sinks (`Generate::`)

```cpp
namespace Generate {
    struct Sink {                                   // minimal, virtual is fine here
        virtual ~Sink() = default;
        virtual void configure(const Config::Document&) = 0;
        virtual void onInit(Pythia8::PythiaParallel&) {}
        virtual void onEvent(Pythia8::Pythia& worker, std::size_t eventIndex) = 0;
        virtual void onFinish(const RunSummary&) = 0; // σ, weights, interrupted, n processed
        virtual Monitor::ReportHooks report() { return {}; }
    };
    int run(const Config::Document&, std::vector<std::unique_ptr<Sink>>);
}
```

| Sink | Wraps | Enabled by |
|---|---|---|
| `Observe::RivetSink` | Phase 3 | `[rivet].mode = "inprocess"` |
| `Generate::RecordSink<Module>` | `Record::Writer` + module callback (`Lambda::pythiaAnalysis`, `Lambda::dataGenerator`) | `[record]` present and a module selected |
| `Generate::HepMCSink` | `Pythia8ToHepMC` (merged, locked) or `HepMC3Hooks`-style per-thread | `[hepmc].write = true` |

- `Generate::run` owns: signals, sweep loop, Monitor lifecycle, `init()`,
  σ collection, ordered finish (sinks in reverse order), and the fatal-stall
  handler fan-out.
- `_Lambda_Data` / `_Lambda_Parallel` become ~20-line drivers selecting a
  `RecordSink`.
- `[rivet].mode = "external"` is implemented as `HepMCSink` to a FIFO +
  a supervised `rivet` child — the FIFO path survives without a second
  code path in Python.

**Verify:** Lambda e2e output identical to Phase 2 baseline; a combined
run (`rivet` + `record` + `hepmc`) produces all three outputs with one
`About/`/annotation provenance set; `hepmc` output re-analysed by the
`rivet` CLI reproduces the in-process YODA.

---

## Phase 5 — Python layer on the unified schema

- `tools/rivpyth` → thin launcher: `load TOML → _Generate.exe [--point i]`
  (or `--list-points`), optional batch submission later.
- `tools/ydplt`, `tools/ydmrg` read `[plot]` (below); naming from
  `_Generate.exe --list-points` JSON.
- Migration: old `[analysis]/[yoda]/[rivpyth]` keys produce a clear error
  naming the new key (same style as `rejectSectionAliases`).

### Unified schema (PhotoProduction example)

```toml
[events]
event_count = 1_000_000

[threads]
pythia = 20

[pythia]
cmnd_file = "configs/PhotoProduction/eic_5x41.cmnd"
seed      = 270403
quiet     = true

[sweep]
over   = "pdf"
values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed",
          "LHAPDF6:NNPDF23_nlo_as_0119_qed", "LHAPDF6:PDF4LHC21_40"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 QCD+QED LO", "NNPDF 2.3 QCD+QED NLO", "PDF4 LHC21.40"]
tags   = ["MSTW", "NNLO", "NNNLO", "LHC21"]
select = 0
tag_style = "index"

[rivet]
analyses   = ["photo_5x41"]
plugin_dir = "output/PhotoProduction"
mode       = "inprocess"

[hepmc]
write = false

[record]                 # naming only (or [output], see Q1)
serial = 1
[record.paths]
directory       = "results/PhotoProduction/"
serialDirectory = false
[record.file]
prefix = "eic28"
serial = true
energy = false
events = false
[record.metadata]
dataset_name = "EIC_photoproduction_5x41"
generator    = "Pythia8"

[monitor.intervals]
print_interval          = 1000
program_stall_threshold = 10

[plot]
plot_file = "sources/PhotoProduction/photo_5x41.plot"
merge     = "overlay"     # overlay | sum
legend    = "label"       # label | tag | point
[plot.data]
file      = "datasets/zeus_eic.yoda"
legend    = "Data"
reference = true
draw      = true          # today's data_hist
```

### Key migration map

| Old (`rivpyth`) | New |
|---|---|
| `[analysis].riv_plugin` | `[rivet].analyses = [...]` |
| `[analysis].cmnd_file` | `[pythia].cmnd_file` (full repo-relative path) |
| `[analysis].event_count` | `[events].event_count` |
| `[analysis].seed` | `[pythia].seed` |
| `[analysis].pdf_sets / pdf_alias / alias_suffix` | `[sweep].values / labels / tags` |
| `[analysis].use_pdf` | `[sweep].select` |
| `[analysis].pdf_suffix` (0/1/2) | `[sweep].tag_style` (index/value/tag) |
| `[yoda].pdf_legend` (1/2/3) | `[plot].legend` (label/tag/point) |
| `[yoda].plot_merge_type` (1/2) | `[plot].merge` (overlay/sum) |
| `[yoda].use_data / data_file / data_legend / data_reference / data_hist` | `[plot.data]` present / `file` / `legend` / `reference` / `draw` |
| `[rivpyth].project` | driver project name / `[record.paths].directory` |
| `[rivpyth].generator` | implicit (`_Generate.exe`) |
| `[rivpyth].serial` | `[record].serial` |
| `[rivpyth].hepmc_file` | `[hepmc].file` |
| `[rivpyth].yoda_file` | `[record.file].prefix` |
| `[rivpyth].plugin_dir` | `[rivet].plugin_dir` |
| `[rivpyth].threads` | `[threads].pythia` |
| `[rivpyth].path_literal` | dropped (all paths repo-relative, anchored by `Utility::Paths`) |

**Verify:** `eic28.toml` migrated; `ydmrg` output identical to today's
(same YODA inputs); `--list-points` names equal the Phase 1 golden list.

---

## Phase 6 — Optional / later

- **E**: `Paint` YODA source (`source_type = "YODA"`) via YODA C++ reader,
  or `yoda2root` conversion step.
- **D**: `Ingest::HepMC` source → same sinks (needed once Herwig/Sherpa
  samples are used).
- **Multiweight PDFs**: evaluate Pythia weight variations + Rivet
  multiweight handling as a replacement for sequential proton-PDF runs.
- **Plugin consolidation** (B8): one `photo_eic` analysis with
  `getOption("BEAMS")` (W window, labels) and binning aligned to ZEUS
  edges (B9). Physics review required before changing binning.
- **Batch**: `[sweep]` point → HTCondor/SLURM job array.

---

## Risks

| Risk | Phase | Mitigation |
|---|---|---|
| `AnalysisHandler::merge` semantics differ from expectations (R1) | 3 | Serial mode default until equivalence test (3.4-2) passes |
| Merged σ error not exposed by `PythiaParallel` | 3 | Q3; interim: record σ error as unavailable, never fabricate |
| Rivet + ROOT symbol/ABI clashes in one binary | 3 | Early link-only spike (`_Generate.exe` hello-world) before writing sinks |
| FastJet/SISCone dominates wall time in serial mode | 3 | Benchmark (3.4-3); switch default to `parallel` only with data |
| Output naming change breaks existing results/plots | 2, 5 | Golden-name tests; keep today's pattern as default |
| Mac stack lacks Rivet | 3–4 | `HE_WITH_RIVET` guard + per-target Makefile libs |
| Scope creep into a framework (Option F) | all | Sink interface stays ≤ 5 methods; no scheduler |

## Open questions (need your decision)

- **Q1** Rename `[record.paths]/[record.file]` → `[output.*]` (with migration), or keep `record` as the naming owner?
- **Q2** Should sweeps run in one process sequentially (simple) or one process per point (batch-friendly, isolates crashes)? Recommendation: both via `--point`, default sequential.
- **Q3** σ uncertainty: accept `pythia.stat()`-parsed value, add a small per-instance hook to collect `info.sigmaErr()`, or report none?
- **Q4** Default `[rivet].concurrency`: `serial` (safe) or `parallel` (faster, needs merge validation)?
- **Q5** Replace sequential proton-PDF runs with multiweight variations where physics allows?
- **Q6** Keep `rivet-mkhtml` as the only YODA plotter (recommended), or invest in Paint YODA support (E)?
- **Q7** Where should reference-data remapping live long-term — `tools/` (today) or a YODA-writing C++ step so plots never need a temp file?
