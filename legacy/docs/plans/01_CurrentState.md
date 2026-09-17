# 01 — Current State Audit

Date: 2026-09-16 · Machine: Lab_PC (Linux, `~/HEP` source-built stack) ·
Branch: `sidequest` · Scope: the new Pythia→HepMC→Rivet→YODA workflow
(PhotoProduction) and the previous ROOT–Pythia module stack (Lambda /
`utils/`), as they exist **on this machine today**.

Evidence is cited as `file:line`. Items marked **[reproduced]** were
demonstrated in a scratch directory; **[reasoned]** items were read from
source but not run.

---

## 1. Workflow A — ROOT–Pythia module stack (Lambda)

### 1.1 Shape

```
                         one TOML (file or dir-of-*.toml, merged)
                                      │
            ┌─────────────────────────┼──────────────────────────────┐
            ▼                         ▼                              ▼
 Config::configure<PythiaT>   Monitor::configureMonitor   Record::configureWriter
 (Config/Configure.hh)        (Monitor/Configure.hh)      (+ Meta::mergeFromToml)
            │                         │                              │
            ▼                         ▼                              ▼
   Pythia8::PythiaParallel ──cb──► Lambda::pythiaAnalysis ──fill──► Record::Writer ──► .root (+About/)
   (N generator threads)          (modules/Lambda.hh)               (M fill workers,
                                     │  countEvent/publish           watchdog, checkpoints)
                                     ▼                                    ▲
                              Monitor::AsyncLogger ◄───bind(hooks)────────┘
                              (heartbeat, bar, stall → fatalShutdown)
```

- **One process, one binary per driver** (`sources/Lambda/_Lambda_*.cc`,
  ~60 lines each). The driver is pure composition: construct runtime objects,
  `Config::configure(...)`, bind hooks, run, `finish()`.
- **Lifecycle is owned by the library**: open → declare → start → fill →
  finish (Writer), initialise → publish → finish (Logger), with a
  barrier-synchronised watchdog, checkpoints, fatal-stall shutdown and
  SIGINT/SIGTERM graceful stop (`Utility/Signals.hh`).
- **Analysis is C++ in-process** (`modules/Lambda/`), talking to the Writer
  through typed fill requests.
- **Output contract** is one ROOT file with `About/` provenance (git SHA,
  config snapshot, file SHA-256s, event counts) — `docs/DataContract.md`.
- **Plotting** is `Paint` (TOML-driven ROOT rendering), a separate binary.

### 1.2 Configuration model

| Aspect | How it works |
|---|---|
| Grammar | One TOML tree, sectioned by subsystem: `[events] [threads] [pythia] [probe.*] [record] [record.paths] [record.file] [record.metadata] [record.limits.*] [monitor.intervals] [monitor.logs] [lambda]` |
| Composition | File **or directory** of `*.toml` merged alphabetically (`Utility/Toml.hh:41`) |
| Ownership | Each subsystem parses its own section: `Config::read*Section`, `Monitor::configureMonitor`, `Record::Meta::mergeFromToml`, `Lambda::extractPhysics` |
| Validation | Typed reads with `value_or`, `requirePositive/NonNegative`, and **explicit rejection of removed keys with migration messages** (`Config.hh`/`Reader.hh:rejectSectionAliases`, `Monitor/Configure.hh:validateMonitorSchema`). Unknown keys are silently ignored. |
| Precedence | `[threads].<key>` → `[<section>].<key>` → auto (`Reader.hh:resolveThreadKey`) |
| Physics vs run control | Physics in `.cmnd`; TOML may override `seed`, `Beams:eCM`, `Parallelism:numThreads` (`Config.hh:59-91`) |
| Naming | Deterministic: `<dir>/_<serial>/<prefix>[_serial][_<E>GeV][_<N>].root` + `logs/`, `checkpoints/`, `threads_*` (`Reader.hh:readPathsAndFile`) |
| Documentation | `configs/all.toml` (canonical reference) + `configs/templates/*.toml` (per-subsystem, annotated with the C++ field each key feeds) |

### 1.3 Current health on this machine

| # | Finding | Evidence | Severity |
|---|---|---|---|
| A1 | **Lambda configs point at pre-move paths.** `cmnd_file = "configs/Lambda_Reconstruction.cmnd"` but the file now lives in `configs/lambda/`; `hist_limits = "Lambda_Limits"` resolves to `configs/Lambda_Limits.toml` (`LimitAid.hh:17-20`); drivers default to `configs/Lambda_*.toml`. The Lambda drivers cannot run with their shipped configs. | `configs/lambda/Lambda_Generation.toml:15`, `Lambda_Reconstruction.toml:77`, `sources/Lambda/_Lambda_Data.cc:21`, `tests/test_utils_hardening.cc:114` | High (for Lambda) |
| A2 | **`beamEnergy` is wrong for asymmetric beams.** `configurePythia` reads `Beams:eCM` from settings; with `Beams:frameType = 2` (all EIC/ZEUS cmnds) that parameter is unused and stays at its default (14000), so file titles would say `14000GeV`. A TOML `beam_energy` is silently ignored by Pythia in that frame. | `utils/Config.hh:73-81`; Pythia `BeamParameters.xml:80-81` | High (blocks reuse for PhotoProduction) |
| A3 | **Monitor cannot run without a Record::Writer.** `AsyncLogger::initialise(const Record::Writer&)` takes paths from the Writer; `Monitor/Report.hh` builds logs from `Writer::paths()/histConfig()`; `Monitor.hh` must include `Record/Writer.hh` first to break an include cycle. | `Monitor/Lifecycle.hh:98-122`, `Monitor/Report.hh:16,34-149`, `Monitor.hh:21-27` | Medium (integration blocker) |
| A4 | **`Config::Register` still hard-codes Lambda defaults** (`output/Lambda/...`) and is the transitional W9 blob mirrored into `Record::Paths`. | `Config/Types.hh:120-146`, `Reader.hh:172` | Low/Medium |
| A5 | **Each subsystem re-parses the config file** (`parseConfig` called from Config, Monitor, Meta, Lambda, and again in `Configure.hh:49`). Harmless at this size, but means there is no single parsed, validated config object to hand to new subsystems. | `Config/Configure.hh:49`, `Monitor/Configure.hh:65`, `Record/Meta.hh:mergeFromToml`, `modules/Lambda/Loaders.hh:19` | Low |

---

## 2. Workflow B — Pythia → HepMC → Rivet → YODA (PhotoProduction)

### 2.1 Shape

```
 run TOML ([analysis] [yoda] [rivpyth])          ~/HEP (NOT a git repo)
        │
        ▼
 rivpyth ── for each PDF (sequential) ────────────────────────────────────────┐
   │  mkfifo output/<P>/<serial>_<hepmc>_<sfx>                                 │
   │  Popen(generator.exe cmnd fifo N threads seed [pdf])  ── HepMC3 ASCII ──┐ │
   │  Popen(rivet --analysis=<plugin> -o results/<P>/…yoda fifo)  ◄──────────┘ │
   │  wait(rivet) → terminate(generator) on failure → wait(generator)          │
   └───────────────────────────────────────────────────────────────────────────┘
        │
 ydplt  ─► rivet-mkhtml (one PDF)        ─► results/<P>/<stem>/
 ydmrg  ─► rivet-mkhtml overlay | yodamerge + rivet-mkhtml
          (+ remapped data yoda in a tempdir)
```

- **Multi-process pipeline** coordinated by Python (`~/HEP/rivpyth`,
  `ydplt`, `ydmrg`, `rivpyth_common.py`). Tools talk through a **named
  pipe** carrying HepMC3 ASCII, and through **CLI arguments**.
- **Generator** (`sources/PhotoProduction/generator.cc`) is a thin
  standalone: `PythiaParallel` + one `Pythia8ToHepMC` writer under a mutex,
  no project headers.
- **Analysis** is a Rivet plugin (`photo_<beams>.cc` + `.plot` + `.info`),
  built with `rivet-build` into `output/PhotoProduction/Rivet_*.so`.
- **Output** is YODA text; plots come from `rivet-mkhtml`.

### 2.2 Configuration model

| Aspect | How it works |
|---|---|
| Grammar | Run TOML with three sections: `[analysis]` (plugin, cmnd, events, seed, PDF sweep), `[yoda]` (plotting/data overlay), `[rivpyth]` (paths, serial, threads) |
| Composition | Single file; no merging |
| Ownership | Python only (`rivpyth_common.read_config`); C++ generator receives **positional args** |
| Validation | Strict typed getters with ranges; cross-field checks (list lengths, filename-safe suffixes, `data_hist`/`data_reference`) — stricter than the C++ side about types; unknown keys also ignored |
| Paths | Convention: `output/<project>/`, `configs/<project>/`, `results/<project>/`, `sources/<project>/<plugin>.plot`; `path_literal` escape hatch |
| Naming | `<serial>_<name>_<pdf suffix>.<ext>`; suffix = index / sanitized set / alias |
| Run matrix | Built-in PDF sweep (`use_pdf = 0` → all), seed offset per PDF |
| Physics vs run control | Physics in `.cmnd`; generator overrides `Random:seed`, `PDF:pSet`, threads, `Print:quiet` |
| Analysis parameters | Hard-coded in C++ plugin (W window, E_T cuts, binning) — **three copies** differing only by W range |

### 2.3 Findings

| # | Finding | Evidence | Severity |
|---|---|---|---|
| B1 | **Pipeline hangs forever if the generator fails before opening the FIFO** (bad cmnd path, init failure). `rivet` blocks in `open()` on the FIFO; `rivpyth` waits on rivet first. **[reproduced]** — killed only by a 25 s timeout. | `~/HEP/rivpyth:109-115`; `generator.cc:66-82` (FIFO opened only after `init()`) | **High** |
| B2 | **Orchestration code is unversioned.** `~/HEP` is not a git repo, yet repo configs depend on its schema; two repo configs already drifted (`eic140.toml`, `eic63.toml` use the old `[events]/[pythia]` schema and fail to load; `eic140` also points at 5×41 files). | `git status` in `~/HEP` fails; `configs/PhotoProduction/eic140.toml`, `eic63.toml` | High |
| B3 | **Cross-section normalisation comes from per-thread estimates.** Each worker's `Pythia8ToHepMC::writeNextEvent(*pythiaPtr)` writes that thread's own running σ; Rivet uses what arrives last. `pythia.stat()`'s merged σ is printed but never reaches Rivet. **[reasoned]** | `generator.cc:85-94` | Medium |
| B4 | **No run observability.** `Print:quiet = on`, no progress, no ETA, no stall detection, no log files; a 1M-event run is silent until it ends. | `generator.cc:73` | Medium |
| B5 | **No provenance in outputs.** YODA files carry no git SHA, config snapshot, cmnd SHA, seed or PDF annotation; the only link is the filename index `pNN`. | `rivpyth`, `generator.cc` | Medium |
| B6 | **Throughput is capped by serialisation.** N generator threads funnel into one mutex-guarded ASCII writer, then a single-threaded Rivet parses text. Not yet measured. **[reasoned]** | `generator.cc:83-90` | Medium (unmeasured) |
| B7 | **Generator CLI is unvalidated & mis-documented.** `atol` without checks; default `nEvents = 10000` always overrides `Main:numberOfEvents` although the header says "default: use the cmnd file"; `seed = 0` keeps cmnd `Random:seed = 0` = time-seeded → irreproducible by default; header still names `GenerateHepMC.cc` / `generate_hepmc`. | `generator.cc:1-35,60-74` | Low |
| B8 | **Three near-identical Rivet plugins** (`photo_5x41/10x100/18x275`) differ only by class name and the W window; `.plot` files differ only in legends. Rivet analysis options (`getOption`) would collapse them to one. `.info` files are unfilled templates. | `photo_*.cc:82-84`, `photo_*.info` | Low |
| B9 | **Plugin binning ≠ reference binning.** ZEUS E_T edges (…47, 55, 71, 95) are not plugin edges, so data overlays are trimmed (see the `ydmrg` fix of this session). | `photo_5x41.cc:48`; `datasets/zeus_eic.yoda` | Low (physics choice) |
| B10 | **Stale FIFOs** remain in `output/PhotoProduction/` after aborted runs (harmless: reused). | `ls -la output/PhotoProduction` | Info |
| B11 | `RIVET_ANALYSIS_PATH` starts with an empty entry (`=:~/…`). | `~/HEP/setup.sh:14` | Info |
| B12 | **`PythiaParallel` callbacks are already serial by default** (`Parallelism:processAsync = off`). The generator's `writeMutex` is redundant, and — relevant to A too — `Lambda::pythiaAnalysis` in `_Lambda_Parallel` also runs one event at a time; only generation is parallel. Nothing in the repo sets `processAsync`. | `~/HEP/install/pythia8/share/Pythia8/xmldoc/Parallelism.xml:161-168`; `generator.cc:83-88`; `grep processAsync` → no hits | Info (design input) |

---

## 3. Shared infrastructure

### 3.1 Makefile (rewritten for this machine)

| # | Finding | Evidence | Severity |
|---|---|---|---|
| M1 | **Header-dependency tracking was dropped.** Phase 1 of `docs/UtilsAudit.md` added `-MMD -MP` after stale binaries were found; the new rules rebuild only when the `.cc` or `Makefile` is newer, so editing any `utils/*.hh` does not rebuild drivers — the exact bug that was fixed before. | `Makefile:44-53` vs `docs/UtilsAudit.md` §11 Phase 1 item 2 | **High** |
| M2 | **Every `.exe` links every library** (ROOT, Pythia, HepMC3, FastJet, YODA, LHAPDF, ONNX, Delphes, toml++), and all `*-config` shells run on every `make` invocation (even `make` with no target). A missing optional tool breaks every build; link times and binary deps grow. | `Makefile:12-27` | Medium |
| M3 | **Test harness disconnected.** `make tests/test_x.exe` now emits `output/tests/test_x.exe`, but `tests/run_all.sh` looks for `tests/test_*.exe`. | `Makefile:44-53`, `tests/run_all.sh:12` | Medium |
| M4 | `FORCE` + manual mtime checks re-implement make; no `.PHONY` per target, no parallel-safe dependency graph. | `Makefile:41-53` | Low |

### 3.2 Environment

- `load_hep` = `source ~/HEP/setup.sh`: PATH/LD_LIBRARY_PATH/PYTHONPATH for
  15 packages, venv activation, `LHAPDF_DATA_PATH`, `RIVET_ANALYSIS_PATH`.
- Available C++ integration points (verified present):
  `Rivet/AnalysisHandler.hh` (`init/analyze/finalize/writeData/merge/
  setCrossSection/setFinalizePeriod`), `Pythia8Plugins/{HepMC3.h,
  HepMC3Hooks.h, RivetHooks.h, Pythia8Rivet.h, LHAPDF6.h, FastJet3.h}`,
  `libpythia8rivet.so`, `libpythia8hepmc3.so`, `libpythia8lhapdf6.so`,
  YODA C++ headers, and `yoda2root` / `root2yoda`.
- `rivet-config --cxxflags --ldflags --ldlibs` gives a complete link line
  (FastJet + contrib, HepMC3, YODA, Rivet).

### 3.3 Upstream caveat relevant to integration

**R1 — Pythia 8.317 `RivetHooks::onStat` merges each non-main handler
twice**: once inside the `try` and again unconditionally after it
(`~/HEP/install/pythia8/include/Pythia8Plugins/RivetHooks.h:181,187`). If
`AnalysisHandler::merge` is additive (as its use suggests), statistics
from threads 1..N−1 are double-counted relative to thread 0. **[reasoned —
must be verified empirically before relying on `libpythia8rivet.so`]**; a
project-owned hook avoids the question entirely (see 03 §B).

---

## 4. Inventory summary

| Concern | Workflow A (module stack) | Workflow B (toolchain) |
|---|---|---|
| Entry point | `output/Lambda/_Lambda_*.exe <toml>` | `rivpyth <toml> [pdf]`, `ydplt`, `ydmrg` |
| Languages | C++17 header-only | Python 3.12 + thin C++ + Rivet C++ plugins |
| Config files | TOML (+ `.cmnd`, limits TOML, Paint TOML) | TOML (+ `.cmnd`, `.plot`, `.info`, positional CLI) |
| Processes | 1 | 2 per PDF (+1 per plot) |
| Parallelism | Generator threads + writer pool + logger thread | Generator threads only; Rivet single thread |
| IPC | In-memory queues, barriers | FIFO (HepMC3 ASCII), exit codes |
| Output | ROOT (+`About/`), logs, checkpoints | YODA, HTML/PDF/PNG |
| Provenance | Strong | Filename only |
| Observability | Progress bar, ETA, run-stat, stall detection | None |
| Failure handling | Signals, fatal-stall shutdown, partial finalize | Signal forwarding; hang on early generator failure |
| Versioned | Yes (repo) | Partially (plugins/configs in repo, orchestration outside) |
