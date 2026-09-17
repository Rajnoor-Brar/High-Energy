# 09 — Build, packaging, tests

## 1. Build system

### Options

| Option | + | − |
|---|---|---|
| **Keep Make** (fix per-target flags, `-MMD`) | Familiar; small | Optional components, feature detection, compile DB and Mac portability are all hand-written. The current file already lost dependency tracking once. |
| **CMake** (+ thin `Makefile` wrapper) | `find_package(ROOT)` is first-class. `option()`/auto-detect per tool. Header dependencies, `compile_commands.json`, `ctest` and a Mac toolchain come for free. | More verbose. Pythia, Rivet, YODA and LHAPDF ship `*-config` scripts, not CMake configs, so they need small `Find*.cmake` wrappers. |
| **Meson** | Clean syntax | ROOT support is weak. A new tool to learn. |

**Decision: CMake.**
- A 15-line top-level `Makefile` keeps muscle memory: `make`, `make analyses P=PhotoProduction`, `make test`.
- `hep build` wraps both.

### Components

```cmake
option(HEKIT_WITH_RIVET   "Sink::Rivet + analyses"            AUTO)   # AUTO = on if found
option(HEKIT_WITH_HEPMC   "Store, Source::StoreReplay/Stream"  AUTO)   # adds HEPMC3_USE_COMPRESSION + HEPMC3_Z_SUPPORT (+ZSTD if found)
option(HEKIT_WITH_ONNX    "ML::OnnxModel"                      AUTO)
option(HEKIT_WITH_DELPHES "in-process Delphes (links ROOT)"    OFF)    # deferred; external Delphes needs no build option
```

- **Always built:** `Results` (YODA) and `Module`, because YODA comes with Rivet and is always required.
- **ROOT:** not linked by `hep-run` unless `HEKIT_WITH_DELPHES` is on. ROOT processing happens in Python (`hep proc`, [12](12_Processing.md)).
- **HepMC3 compression** is header-only (`HepMC3/CompressedIO.h`) and enabled by compile definitions plus `ZLIB::ZLIB` (and `zstd` if found). Verified for gzip on this machine.
- **Libraries:** one INTERFACE library per facade namespace (`hekit_Core`, `hekit_Store`, …; see 13). Each component is linked into `hep-run` only when enabled.
- `hep-run --capabilities` prints the enabled set, which `hep doctor` and `hep plan` read.
- **A missing optional tool never breaks the build** (N5). Pythia is the one hard requirement.

### Targets

| Target | Output |
|---|---|
| `hep-run` | `build/bin/hep-run` (installed into the venv's `bin/` by `hep build`, so it is on `PATH`) |
| `hekit_<module>` | `build/modules/<project>/libhekit_<name>.so` (MODULE libraries) |
| `rivet_<project>` | `build/analyses/<project>/Rivet_<name>.so`, built with `rivet-build` flags; `.info`/`.plot`/`.yoda` are copied beside it. This keeps the current Makefile behaviour, which works. A plugin whose `.info` lists `Requires: ONNX` also gets the ONNX flags. |
| `tests` | unit and integration test executables |

**Per-project directories** are discovered with a glob over `analyses/*/` and `modules/*/`. Adding a project needs no CMake edits.

## 2. Python packaging

- `utils/python/pyproject.toml`:
  - package `hekit`;
  - entry point `hep = hekit.cli:main`;
  - dependencies: `click`, `rich`, `tomli_w`.
- **Optional extras:** `plot` (`matplotlib`, `mplhep`, `hist`, `uproot`), `ml` (`onnxruntime`), `proc` (`scipy`; PyROOT from the toolchain). All are already present in the venv; `rich`, `tomli_w` and `pytest` are added in P0-S02.
- **Not pip dependencies:** `yoda`, `rivet`, `lhapdf`, `pyHepMC3` and `ROOT` come from the toolchain (`PYTHONPATH`, fixed in P0-S02). `hep doctor` checks them.
- Installed **editable** into `~/HEP/.venv` (08 §3).

**Package map** (full description in [13 §4](13_Namespaces.md#4-python-packages-utilspythonhekit-cli-hep)):
```
hekit/
  cli.py  errors.py
  config/   schema load layer validate migrate reference
  sweep/    quantity select expand pages
  plan/     model build naming hashing seeds spec (+ spec_v2.json)
  adapters/ base pythia rivet store sherpa whizard madgraph herwig delphes
  run/      supervisor transport status parsers signals
  term/     dashboard plain events theme
  results/  layout manifest skip yoda stats compare
  store/    index ls verify info
  plot/     io select transform data plotfile backends/{mkhtml,mpl} styles/hekit.mplstyle
  proc/     models backends/{minuit2,roofit,scipy} hist
  prov/     git versions provenance stamp
  env/      paths doctor lhapdf tools
```

**Size budget** (≈ 4,000 lines):
| Area | Lines |
|---|---|
| config + sweep | 1,000 (mostly ported from `rivpyth_common`) |
| plan | 400 |
| adapters | 700 |
| run | 450 |
| term | 400 |
| results + store | 350 |
| plot | 600 |
| proc | 300 |
| prov + env | 300 |

## 3. Tests

**Layout:**
```
tests/
  golden/        legacy fixtures (P0-S04): plan JSONs per study, mini-run YODAs + plot intermediates, EXPECTED_DELTAS.md
  python/        pytest unit tests; conftest.py guard (fails if results/ or configs/ change)
  integration/   slow end-to-end and equivalence tests (pytest + ctest label "slow")
  spikes/        decision experiments (e.g. PythiaParallel chunked run, gz vs zstd); kept for provenance
  tools/         yodacmp.py (→ hekit.results.compare in P4-S04)
  cpp/           ctest sources (Core, Status, Store, Results, Sink)
```

The old C++ tests move to `legacy/tests/` (P0-S06), together with their fixtures and `run_all.sh`.

| Layer | Test | Tooling |
|---|---|---|
| legacy golden | `rivpyth` plan expansion per study (points, pages, settings with origin); mini-run YODAs and plot intermediates; study counts | `pytest tests/golden` |
| config / sweep | Schema errors (unknown key, did-you-mean, migration); precedence chain; `across` grammar; settle clashes; study pins; one test per legacy bug (00/B6, B7, B9, B22) | `pytest`, pure Python, <2 s |
| identity / seeds | Same seed for the same point across studies; disjoint `Parallelism:seeds` blocks; catalogue-order independence; equal-hash aliases | `pytest` (property tests) |
| adapters | Golden files: point → rendered card for each tool; Pythia ids + energies (pair / scalar √s / LHE); PDG → Whizard/Herwig/MadGraph mapping; the Whizard insertion rule; Rivet option validation against `.info` | `pytest` + `tests/golden/` |
| plan | `eic` studies → expected point, group and page counts; analysis-only variants share one group; migrated plan equals the in-memory migration | `pytest` |
| supervisor | Fake stages that exit early, hang, flood stderr, or ignore SIGINT → exit codes, sibling shutdown, FIFO cleanup, stall detection | `pytest`, with timeouts |
| status protocol | C++ `Status::Writer` ↔ Python reader round-trip; unknown `k` values ignored | `ctest` + `pytest` |
| hep-run core | Spec parsing errors; `--check` on good and bad cards (unknown key → 1, `ProcessType = 2` → 3); SIGINT → 6 with a `.partial` output | `ctest` |
| Pythia spike | Repeated `run()` vs single `run()`; σ-error combination vs `stat(true)`; `Parallelism:seeds` readback | `tests/spikes/` (decision evidence) |
| Rivet sink | **Legacy equivalence:** in-process vs `generator.exe` → FIFO → `rivet`, 1 thread, fixed seed. **Serial vs sharded:** 50k events. σ equals `sigmaGen()`. | `ctest -L slow` |
| store | Write → verify (counts, hashes, truncation detection) → replay → same YODA and σ; build without zstd | `ctest` + `ctest -L slow` |
| modules | Toy-module totals exact for 1/4/20 threads; scaled integral correct; non-empty dumps; module objects merged by hekit for replicas | `ctest` + `pytest` |
| plot | Voiding, auto-range, data map, `.plot` parser → mpl kwargs; outputs equal the legacy functions | `pytest` with small YODA fixtures |
| proc | Synthetic fits recover parameters; backends agree to 1e-3; scipy fallback without PyROOT; RDF = uproot bins | `pytest` (`proc` marker) |
| end-to-end | `hep run tests/e2e/mini.toml` (2 points × 2k events, Pythia + Rivet) → `hep plot` → files exist, provenance complete | `make e2e` (~1 min) |

**Test safety rules** (the lesson from this session; also in `steps/README.md`):
- **Guard:** tests and `hep plan` never write into `results/` or `configs/`. The pytest guard enforces this from P1-S01.
- **Scratch:** tests use `tmp_path` or `output/scratch/`, with `HEKIT_RESULTS` redirecting the results root.
- **Old tools:** they are exercised from `output/scratch/legacy/`, a directory with symlinks to `configs`, `output` and `datasets` and its own `results/`. This works because they resolve paths relative to the CWD.
- **Old tests:** per BOT.md, their output paths are redirected to test directories and restored only after the tests pass.
