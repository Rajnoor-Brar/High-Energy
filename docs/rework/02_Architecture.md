# 02 — Architecture

## 1. The core decision: who does what

### Options considered

| Option | Shape | Verdict |
|---|---|---|
| **a. All C++** | C++ CLI, C++ sweep expansion, C++ plotting (ROOT/Paint) | ✗ Re-implements what Python does in a tenth of the code: TOML strictness, subprocess supervision, YODA plotting. It also has to link every optional tool. This is the current Lambda direction, and it is why `utils/` is 10k lines. |
| **b. Python orchestrator + C++ runner** | Python validates, expands, supervises, renders and plots. One C++ executable runs the event loop and its analyzers. | ✓ **Chosen** |
| **c. All Python** | `pythia8` + `rivet` bindings in one Python process | ✗ Per-event Python overhead and the GIL. Loses `PythiaParallel`. Bindings are not even importable here yet. Custom modules and ONNX-in-the-loop become awkward. |
| **d. Shell + C++** | Bash wrappers around the executables | ✗ No real validation, weak error handling. Sweeps in bash are unmaintainable. |

**Scores** (1–5, weights in brackets):

| Criterion | a | **b** | c | d |
|---|---|---|---|---|
| Throughput (3) | 5 | 5 | 2 | 5 |
| Config strictness and ergonomics (3) | 3 | 5 | 5 | 1 |
| Multi-tool supervision (3) | 2 | 5 | 4 | 2 |
| Terminal UX (2) | 3 | 5 | 5 | 2 |
| Plotting (2) | 2 | 5 | 5 | 2 |
| Code size / maintainability (3) | 1 | 4 | 4 | 3 |
| Custom analysis / ONNX in loop (2) | 5 | 5 | 2 | 5 |
| **Total (/90)** | 55 | **87** | 67 | 49 |

### Rule of thumb that follows

**Rule:**
- **C++** is used where an *event* is touched: generation, analyzers, Rivet plugins, custom modules, inference.
- **Python** is used where a *file, process or person* is touched: configs, native cards, subprocesses, terminal, plots, provenance.
- **Shell** is used only where the *calling shell* must change: environment and `cd` helpers.

This answers guideline 3 ("in code, or custom terminal command"):
- Commands are Python (`hep …`).
- Heavy lifting is C++ behind a single executable (`hep-run`).
- `~/HEP/setup.sh` stays the shell bootstrap (08).

## 2. Component diagram

```
┌──────────────────────────── hep (Python package "hekit", CLI "hep") ───────────────────────────┐
│                                                                                                │
│  cli ──► config ──► sweep ──► plan ──────────────► run.supervisor ──────► term.dashboard       │
│          (schema,   (points,  (groups, stage       (spawn, pipes,         (live view / plain)  │
│           layering,  pages,    chains, resolved     status fd, logs,                           │
│           migration) names)    specs, identity      signals, stalls)                           │
│                                seeds, hashes)             │                                    │
│  adapters: pythia · rivet · store · sherpa · whizard · madgraph · herwig · delphes             │
│  results: layout · manifests · skip rule · YODA model · stats      store: index · ls · verify  │
│  plot: transforms · data map · backends (rivet-mkhtml | mplhep)    proc: fits · RDF (ROOT)     │
│  prov: git, versions, sha256, annotations  ·  env: paths, doctor, lhapdf                       │
└───────────────────────────────────────────┬────────────────────────────────────────────────────┘
                     resolved spec (TOML)   │  argv + env        ▲ status (JSON lines, fd 3)
                                            ▼                    │
┌──────────────────────── hep-run (C++, house-style namespaces, 13) ─────────────────────────────┐
│  Core: Spec · Errors · Signals · Clock · Sha256 · Paths · Provenance      Status: fd-3 writer  │
│  Source: Pythia (cards, LHE) │ StoreReplay (HepMC3 shards) │ Stream (FIFO/file HepMC3)         │
│        │ Events::View (live Pythia event + lazily converted HepMC3::GenEvent)                  │
│        ▼                                                                                       │
│  Analyzer:  Rivet │ Store (HepMC3 shards / FIFO tee) │ Modules (user C++ → YODA) │ Delphes*        │
│  Results: YODA per-worker booking, merge, atomic write      Run: loop · concurrency · σ merge  │
│  ML: OnnxModel (modules)      Phys: PDG · kinematics · selectors · jets      * optional        │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
      external programs (driven by adapters):  Sherpa · Whizard · Herwig · mg5_aMC · DelphesHepMC3
      post-processing tools:                   rivet-mkhtml · rivet-merge · lhapdf · ROOT (PyROOT)
```

**Formats (D13–D15):**
- **Events** are stored as HepMC3 ([11](11_EventStore.md)).
- **Numerical results** are stored as YODA ([07](07_Outputs.md)).
- **ROOT** is a processing layer ([12](12_Processing.md)). `hep-run` does not link ROOT unless in-process Delphes is built, which is deferred.

## 3. Process model per point

A **point** is one physics configuration (03 §4). Points that differ only in analysis-side quantities form one **event group** and share one generation.

The planner turns each group into a short, linear **stage chain**. Only these chains are allowed; there is no general DAG (rejected in `docs/plans/03` Option F).

| Generator | Chain | Transport |
|---|---|---|
| Pythia | `hep-run` (`Source::Pythia`) → analyzers | in-process |
| MadGraph | `mg5_aMC` (LHE file) → `hep-run` (`Source::Pythia`, LHE shower) → analyzers | file |
| Sherpa | `Sherpa` → FIFO → `hep-run` (`Source::Stream`) → analyzers | HepMC3 ASCII FIFO |
| Whizard | `whizard` → FIFO → `hep-run` (`Source::Stream`) → analyzers | HepMC3 ASCII FIFO |
| Herwig | `Herwig run` → FIFO(s) → `hep-run` (`Source::Stream`) → analyzers | requires ThePEG with HepMC (P7-S06) |
| store (`tool = "store"`) | `hep-run` (`Source::StoreReplay`, one reader per shard) → analyzers | files ([11](11_EventStore.md)) |
| any + Delphes | `hep-run` (`Analyzer::Store` as FIFO tee) → `DelphesHepMC3` | FIFO; in-process Delphes deferred |

**Why the external chains still end in `hep-run`, instead of each tool's native Rivet interface:**
- **One Rivet driver:** one σ policy, one provenance writer, one status protocol.
- **The same analyzers everywhere:** store, modules, Delphes tee.
- **Escape hatch:** Sherpa's native `ANALYSIS: Rivet` stays available as `rivet.mode = "native"` (04 §4).

## 4. Data flow and contracts

| Boundary | Contract | Owner |
|---|---|---|
| user → hep | Run TOML (+ native base cards) | 03 |
| hep → hep-run | **Resolved spec v2**: fully explicit TOML with no defaults, sweeps or `use` indices; plus point card(s). A JSON Schema, `plan/spec_v2.json`, is shared by Python and C++ tests. | 03 §7 |
| hep → external generator | Rendered native card + argv | 04 |
| external generator → hep-run | HepMC3 ASCII on a FIFO created by hep | 05 §4 |
| hep-run → hep | **Status stream**: JSON lines on fd 3; exit-code table | 06 §3 |
| hep-run → disk | `analysis.yoda` (Rivet + module objects), `analysis.partial.yoda` if stopped, `events/` store + `events.index.json`, `delphes.root` (external stage), run summary for `provenance.json` | 07, 11 |
| disk → hep plot / proc | YODA via `yoda`; Delphes ROOT via RDataFrame/uproot; fit outputs `fits.json` + `proc.yoda` | 07 §4, 12 |

The resolved spec is the **only** configuration hep-run understands.
- Consequence: hep-run is simple (no defaults logic) and testable in isolation.
- Consequence: it can run on another machine from the spec alone (batch-ready, 10 §4).

## 5. Repository layout (target)

```
utils/                       C++ facades + submodules (house style, 13)
  Core.hh     Core/          Types Spec Errors Signals Clock Sha256 Paths Provenance
  Status.hh   Status/        Types Writer Heartbeat Plain Timer
  Events.hh   Events/        Types(View) Convert Weights
  Store.hh    Store/         Types(Index, Shard) Writer Reader Compression Queue
  Results.hh  Results/       Types Booker Worker Merge Writer
  ML.hh       ML/            Types OnnxModel Features
  Phys.hh     Phys/          Types Pdg Kinematics Select Jets
  Source.hh   Source/        Types Pythia StoreReplay Stream
  Module.hh   Module/        Types Registry Loader
  Analyzer.hh     Analyzer/          Types Rivet Store Modules Delphes
  Run.hh      Run/           Types Loop Concurrency Checkpoint
  apps/hep-run.cc            the one executable
  python/                    pyproject.toml + hekit/ (CLI "hep"; packages listed in 13 §4)
analyses/<project>/          Rivet plugins: *.cc *.info *.plot *.yoda  (photo_eic moves here in P2-S01)
modules/<project>/           user C++ modules (dlopen'd, libhekit_<name>.so)
configs/<project>/           run TOMLs + native base cards (*.cmnd, *.yaml, *.in, *.sin, proc cards)
env/hep_env.sh               versioned shell layer (~/HEP/setup.sh is a stub that sources it)
tools/                       legacy rivpyth/ydplt/ydmrg while they are still in use (P0-S03 → P4-S06)
legacy/                      tracked archive: lambda/, utils/, tests/, misc/, configs/, analyses/, docs/, tools/
tests/                       golden/ (legacy fixtures), python/, integration/, spikes/, tools/
datasets/                    reference data
results/<project>/…          see 07 (gitignored)
output/                      build products + output/scratch/ (gitignored; all test/dry-run writes)
CMakeLists.txt, cmake/       (+ thin Makefile wrapper)
```

**Moved to `legacy/` (P0-S06):**
- `utils/{Config,Monitor,Probe,Record,Paint,Physics,Utility}`;
- `modules/Lambda`, `sources/Lambda`, `configs/lambda`;
- `tests/*`;
- `_Paint.cc`, `_ThreadBench.cc`, `root_macros/`;
- `configs/{defaults,templates,all.toml,Paint.toml}`;
- the old `photo_*` plugins;
- the stale docs.

`sources/` disappears once `photo_eic` and `generator.cc` have moved (P2-S01, P4-S06).

## 6. Namespaces and names

See [13_Namespaces.md](13_Namespaces.md). In short:
- **C++ namespaces:** PascalCase top-level namespaces with facades (`Core`, `Status`, `Events`, `Store`, `Results`, `ML`, `Phys`, `Source`, `Module`, `Analyzer`, `Run`).
- **No namespace-scope `using namespace`** of the toolchain namespaces.
- **Python:** package `hekit`, console script `hep`.
- **Executable:** `hep-run`.
- **Plugins:** Rivet libraries stay `Rivet_<name>.so`; modules are `libhekit_<name>.so`.

## 7. Cross-cutting policies

| Policy | Rule |
|---|---|
| **Errors** | Python: one `HepError(msg, where, hint)` type, printed as `file:key — msg (hint)`. C++: exceptions inside, a mapped exit code at `main` (06 §3.3). |
| **Units** | GeV, mm (HepMC3 / Pythia), pb for YODA σ. All conversions happen in one place (`Run` → `Analyzer::Rivet` / `Results`). |
| **Seeds** | Derived from the point's identity (hash), never from its position in a sweep. Always explicit in the resolved spec. Pythia gets disjoint per-instance blocks via `Parallelism:seeds`; external generators get the seed through their card (00/B1, 00/B2). |
| **Threads** | Resolved to integers by hep. `0` means hardware concurrency, resolved in Python and never passed on. |
| **Paths** | The repo root comes from the location of `hekit` (Python) or `HEKIT_ROOT` (set by hep for children). The CWD never matters. |
| **Logging** | Every child's stdout/stderr → `logs/<stage>.log`. The terminal shows curated lines only (06). |
| **Signals** | hep owns SIGINT/SIGTERM. Children get SIGINT, then SIGTERM, then SIGKILL on a timer. `hep-run` finalises partial outputs on SIGINT, always under a `.partial` name (00/B3). |
| **Outputs** | Every output is written to a temporary name and renamed when complete. Readers and the skip rule never see half-written files. |
| **Test safety** | Tests and dry runs write only under `output/scratch/` or `HEKIT_RESULTS`, never `results/` or `configs/`. |

## 8. Tool roles

| Role | Meaning | Tools |
|---|---|---|
| **Core** | Always present; the pipeline doesn't work without it | Pythia, HepMC3, Rivet, YODA, LHAPDF (FastJet via Rivet) |
| **Capability** | Optional; switches on extra outputs or processing | ROOT (processing only: fits, stats, RDataFrame), Delphes, ONNX Runtime |
| **External generator** | Separate program driven by its native card | Sherpa, Whizard, Herwig, MadGraph |
| **Post-processing** | Works on files after the run | `rivet-mkhtml`, `rivet-merge`, `yodamerge`, the Python plotting stack, PyROOT (`hep proc`) |

**Rules:**
- **File formats are the contracts between tools**, not shared C++ types. HepMC3 carries events, YODA carries results, and Delphes ROOT carries detector-level events.
- **Tools are not wrapped.** Their native cards and interfaces stay visible.

**Per tool:**
| Tool | Role | Boundary |
|---|---|---|
| Pythia | main generator in `hep-run` | physics in `.cmnd`; hep adds overrides and run control |
| Rivet | main analysis framework | plugins with options; YODA out |
| YODA | the only results format | module histograms too; read by `hekit.plot` |
| HepMC3 | event transport between programs; event store | FIFO or sharded store; not an analysis format |
| LHAPDF | PDF provider inside the generators | `hep pdf` checks and installs sets |
| FastJet | jet finding | inside Rivet plugins and modules (`Phys` jets) |
| ROOT | processing | fits, statistics, RDataFrame on Delphes output; never event or result storage |
| Delphes | detector simulation | external stage fed by HepMC; its ROOT output is analysed, not stored as our format |
| ONNX Runtime | inference | inside modules (`ML`) and Rivet plugins (`RivetONNXrt`) |
