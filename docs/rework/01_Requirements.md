# 01 — Requirements, constraints, assumptions

## 1. Users and usage

- **One physicist-developer.** Works in the terminal, sometimes from another device (phone or remote session). Runs are minutes to hours long.
- **Typical cycle:**
  1. Write or adjust a TOML study.
  2. Generate fresh events with one or more generators.
  3. Analyse them with Rivet and/or custom C++.
  4. Compare the curves with each other and with data.
  5. Iterate.
- **Re-analysing stored events** is occasional (guideline 4). It must be *possible* but must not shape the design.

## 2. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| R1 | Generate events with **Pythia 8** in-process, multi-threaded, from a native `.cmnd` base plus TOML overrides. | Must |
| R2 | Run **Rivet** analyses (project plugins with options, and standard analyses) on generated events. Write YODA normalised to the **merged** cross-section. | Must |
| R3 | **Sweeps and studies:** typed quantities, coupled/grid groups, `settle`, named studies, pins, overlay. This is the current `eic.toml` model. | Must |
| R4 | **Plot:** per-point pages, overlays, seed merges, data/reference overlays, empty-bin voiding, auto x-range. | Must |
| R5 | **Terminal presentation:** a live, readable view of every running stage (progress, rate, ETA, σ, warnings), with full tool output kept in logs. | Must |
| R6 | **Provenance:** every output can be traced to its resolved config, native cards (sha256), tool versions, git state, seed and event count. | Must |
| R7 | **External generators:** Sherpa, Whizard and Herwig through their native cards. Their events are analysed by the same Rivet/sink chain. | Should |
| R8 | **MadGraph:** matrix-element LHE → shower/hadronise in the Pythia runner → same sinks. | Should |
| R9 | **Delphes** detector simulation on generated events. Its ROOT output is analysed with RDataFrame/uproot, and derived histograms are written as YODA (12). | Should |
| R10 | **Custom C++ analysis modules** that book **YODA** histograms, merged across workers and written into the same `analysis.yoda` as Rivet (D14). Derived per-candidate tables are **deferred** (P8-S04). | Should |
| R11 | **ONNX inference** inside C++ modules and Rivet plugins. Python ONNX for offline evaluation. | Could |
| R12 | **HepMC3 event store and replay:** sharded HepMC3 files with an index; replay into any sinks (D13, [11](11_EventStore.md)). This replaces the old ROOT-tree buffering (Probe). | Should (the design must not be shaped by it; guideline 4) |
| R13 | **LHAPDF helpers:** list and verify the PDF sets a config needs, and install missing ones. | Could |
| R14 | **Environment checks:** tool versions, Python importability, missing modules (e.g. ThePEG-HepMC). | Should |
| R15 | **Processing layer:** post-run fits (Minuit2/RooFit, scipy fallback), statistics, and RDataFrame on Delphes output. Results go to `fits.json` and YODA (D15, [12](12_Processing.md)). | Should |
| R16 | **Keep the current workflow correct while porting:** version the `~/HEP` tools, fix their physics-relevant bugs (00/B1–B5), and compare them against golden fixtures (D18, D19). | Must |

## 3. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| N1 | **Throughput:** the event loop is not limited by text serialisation when both ends are ours. | Pythia→Rivet in-process; FIFO only across programs. |
| N2 | **Failure semantics:** no hangs; a failing stage stops the point with a clear message. Ctrl-C finalises partial outputs. | Every stage supervised; one exit-code table. |
| N3 | **Reproducibility:** same resolved spec + seed + thread count → same event set. With `Parallelism:balanceLoad = on` (the default) only the processing order differs. Seeds come from a point's identity, with disjoint per-thread blocks. Re-running an identical point is a no-op. | Content hash of the resolved physics; identity seeds (00/B1, 00/B2). |
| N4 | **Strict configuration:** unknown keys, type errors and conflicts are rejected *before* any process starts, with the file location and a fix hint. | 100% of the schema validated in `hep plan`. |
| N5 | **Optional dependencies:** a machine without Delphes, ONNX or Sherpa still builds and runs everything else. | CMake components; runtime capability probe. |
| N6 | **Portability:** Linux Lab_PC now, a Mac later (different stack paths). | No absolute paths in the repo; everything comes from the environment. |
| N7 | **Versioned tooling:** everything a run depends on is in the repo, except the toolchain install. | `~/HEP/setup.sh` is a stub that sources the versioned `env/hep_env.sh`. |
| N8 | **Readable output:** works in a TTY, degrades to plain lines in pipes/CI/remote logs, and never corrupts the terminal on crash. | TTY detection; `--plain`; a reset on exit. |
| N9 | **Small surface:** a single developer must keep all of it in their head. | ≲ 3.2k lines C++, ≲ 4k lines Python, one CLI. |
| N10 | **Test safety:** tests and dry runs never write into `results/` or `configs/`. | Scratch root `output/scratch/`, `HEKIT_RESULTS`, a pytest guard (09 §3). |

## 4. Constraints (from the environment)

- Pythia `PythiaParallel`:
  - callbacks are serial unless `processAsync = on`;
  - there is no abort API;
  - merged `sigmaGen()` and `weightSum()` are available, but there is no merged σ error.
- `Rivet::AnalysisHandler` is not thread-safe. Use one per worker and `merge()`. `RivetHooks::onStat` in 8.317 may double-merge (unverified), so use our own hook.
- ThePEG has no HepMC or Rivet modules here. **Herwig integration requires rebuilding ThePEG `--with-hepmc --with-rivet`**, or piping through Herwig's LHE/other output (not viable for full events).
- Delphes is single-threaded and ROOT-bound.
- Rivet is not linked to ONNX Runtime. A plugin that uses `RivetONNXrt` must add the ONNX flags itself.
- Python 3.12 venv. `tomllib` is available (read-only TOML). `click`, `mplhep`, `hist`, `uproot`, `awkward`, `onnxruntime`, `scipy` and `pyHepMC3` are installed. `rich`, `tomli_w` and `pytest` are not; they are added in P0-S02 (Q5 = yes).
- HepMC3 compression is header-only and must be enabled at compile time: `-DHEPMC3_USE_COMPRESSION -DHEPMC3_Z_SUPPORT` (+ `HEPMC3_ZSTD_SUPPORT`) with `-lz`/`-lzstd`. gzip is verified.
- `PythiaParallel`:
  - `Parallelism:seeds` sets per-instance seeds (default `Random:seed + i`);
  - `Parallelism:index` identifies the instance;
  - `balanceLoad` (default on) splits events evenly, so a fixed seed and thread count give the same event set.
- **Name clashes:** Delphes declares a global `class Event`, and X11 defines a `Status` macro (13 §3).
- `pythia8` and `ROOT` Python modules need `PYTHONPATH` fixes (00 F10). The design must **not** depend on them in the orchestrator anyway: generation stays in C++, and the orchestrator reads ROOT with uproot.

## 5. Assumptions

| # | Assumption | If wrong |
|---|---|---|
| A1 | Runs are sequential on one machine. Parallelism is *within* a run (threads), not across runs. | Add a batch backend later (10 §4). The point spec is already self-contained. |
| A2 | Physics settings stay in each generator's native language. TOML carries only run control, overrides and sweeps. | A physics-in-TOML layer would be a large, fragile translation effort. It is rejected. |
| A3 | Rivet stays the primary analysis framework for comparisons. Custom C++ is for things Rivet does poorly: candidate reconstruction, ML features, detector-level. | — |
| A4 | Rivet's CPU cost per event is comparable to or larger than Pythia's (three jet algorithms incl. SISCone). | If Rivet is cheap, single-handler serial mode is enough. Keep the threaded mode behind a switch either way (05 §3). |
| A5 | Weight variations (Pythia `UncertaintyBands`, Sherpa on-the-fly) may later replace some re-generation sweeps. | The design supports multi-weight YODA from day one, since Rivet handles it natively. |
| A6 | **PhotoProduction is a test bed** for the new stack (D20). Physics, maths and logic must be correct; specific physics choices (lepton charge, tag names, cut values) are not blockers. | — |

## 6. Out of scope

- Batch/grid submission (the design leaves the hook, 10 §4).
- Training ML models. Only inference is in scope. Feature export waits on the derived-tables decision (P8-S04).
- Porting the Lambda project: it is archived frozen (D17), with port notes kept in `legacy/README.md`.
- A physics-in-TOML abstraction across generators.
- A GUI or web dashboard. A terminal dashboard plus artifacts is enough.
