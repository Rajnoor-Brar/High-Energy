# utils/ rework — from-scratch design

Date: 2026-09-17 (revision b) · Status: **Proposed**; execution is step-based ([steps/README.md](steps/README.md)).

**Question:** if `utils/` and the `~/HEP` commands were designed from scratch, what would they be? The design covers the full installed stack: Pythia, Rivet, YODA, HepMC3, LHAPDF, FastJet, ROOT, Herwig/ThePEG, Sherpa, Whizard, MadGraph, Delphes and ONNX Runtime. It aims for TOML configuration, a presentable terminal, and a merit-based split between code and commands.

## TL;DR

- **Two halves, one contract.**
  - **`hep`** is a Python CLI (package `hekit`). It validates TOML, expands sweeps, renders native cards, supervises processes, draws the terminal dashboard, plots, processes results and records provenance.
  - **`hep-run`** is one C++ executable. It runs the event loop: a Pythia, store or stream source feeds sinks (Rivet, event store, user modules, Delphes tee).
  - They communicate through a **resolved spec** (TOML in) and a **status stream** (JSON lines out).
- **Formats have fixed roles:**
  - **Events:** HepMC3. Sharded stores with an index replace the old ROOT-tree buffering (Probe) and support parallel replay ([11](11_EventStore.md)).
  - **Numerical results:** YODA only, for Rivet and C++ modules alike, in one `analysis.yoda` per group.
  - **ROOT:** a processing layer only: fits, statistics, RDataFrame on Delphes output (`hep proc`, [12](12_Processing.md)).
- **Physics stays in native cards.** TOML carries run control, wiring, overrides and sweeps.
  - The proven `eic.toml` model (typed quantities, `across`, `settle`, studies) is generalised to every generator.
  - `beams` holds PDG ids and `energies` holds energies.
  - Seeds come from a point's identity, with disjoint per-thread blocks.
- **C++ follows the house style** ([13](13_Namespaces.md)): PascalCase facade namespaces `Core`, `Status`, `Events`, `Store`, `Results`, `ML`, `Phys`, `Source`, `Module`, `Sink`, `Run`.
- **One renderer** (`rich`) shows every stage. Tool chatter goes to logs, with curated warnings on screen. `hep watch` works from anywhere.
- **Getting there safely:**
  - The current tools move into the repo and get the physics-relevant hotfixes first.
  - Golden fixtures are captured before any change.
  - Lambda and the old `utils/` are archived frozen in a tracked `legacy/`.
  - PhotoProduction is treated as the test bed.
- **Size:** the C++ framework goes from ~10.6k to ~3.2k lines, plus ~4k lines of Python, covering more tools than both old stacks.
- **Roadmap:** 11 phases, 55 steps, ≈ 37 d. The critical path P0→P4 (≈ 19 d) replaces today's workflow ([10](10_Roadmap.md)).

## Parts (read in order)

| # | File | Covers |
|---|---|---|
| 00 | [00_Audit.md](00_Audit.md) | Inventory, per-tool capabilities, findings F1–F12, verdicts, **current defects `00/Bn`**, stale docs |
| 00b | [00b_PortingMap.md](00b_PortingMap.md) | Function-level map of `rivpyth_common` / scripts / `generator.cc` / legacy `utils` → new packages, namespaces and steps |
| 01 | [01_Requirements.md](01_Requirements.md) | Functional and non-functional requirements, constraints, assumptions, scope |
| 02 | [02_Architecture.md](02_Architecture.md) | Language split, component diagram, stage chains, contracts, repo layout, policies, tool roles |
| 03 | [03_Configuration.md](03_Configuration.md) | TOML anatomy, layering, quantities (`beams`/`energies`), sweeps/studies, identity and seeds, validation, migration, resolved spec |
| 04 | [04_Generators.md](04_Generators.md) | Adapter interface, capability matrix, Pythia / Sherpa / Whizard / Herwig / MadGraph / store |
| 05 | [05_EventPipeline.md](05_EventPipeline.md) | `hep-run`: `Events::View`, sink interface, concurrency and reproducibility, sources, Rivet/Store/Modules/Delphes sinks, ONNX |
| 06 | [06_Terminal.md](06_Terminal.md) | Dashboard, plain mode, status protocol, exit codes, supervision, event inspection, remote watching |
| 07 | [07_Outputs.md](07_Outputs.md) | Results layout, provenance, partial outputs, merging, plotting, comparison, retention |
| 08 | [08_CLI.md](08_CLI.md) | Code-vs-command criteria, `hep` command tree, transition path, shell layer (`env/hep_env.sh`), `hep doctor` |
| 09 | [09_Build_Test.md](09_Build_Test.md) | CMake components, Python packaging, test layout and safety rules |
| 10 | [10_Roadmap.md](10_Roadmap.md) | Guiding rules, phases, decision log D1–D23, risks, revisit list, open questions |
| 11 | [11_EventStore.md](11_EventStore.md) | HepMC3 store: layout, index schema, writing, replay, CLI |
| 12 | [12_Processing.md](12_Processing.md) | ROOT as a processing layer: `hep proc`, fits, RDataFrame |
| 13 | [13_Namespaces.md](13_Namespaces.md) | C++ facade namespaces, clash check, Python packages, old → new |
| — | [steps/README.md](steps/README.md) | **Execution:** step index, dependency graph, decision register, traceability |

## Findings worth acting on even without the rework

These are also the P0 steps.

1. **Seeds.** Point seeds follow sweep position, and neighbouring points share 19 of 20 thread RNG streams (00/B1, B2). Results of different points are correlated.
2. **Partial results.** A killed run leaves a partial YODA at the final path, and `skip_existing` then skips it (00/B3).
3. **Wrong label and data overlay.** The 27x920 label says √s = 95.6 GeV instead of 318.1 (00/B4). ZEUS data is overlaid on non-matching observables (00/B5).
4. **Python imports.** `import ROOT` and `import pythia8` fail: their paths are missing from `PYTHONPATH`.
5. **Herwig.** ThePEG is built without HepMC and Rivet, so Herwig events cannot reach Rivet or a file.
6. **`RIVET_ANALYSIS_PATH`** hard-codes one project and has empty entries, which add the CWD.
7. **Test runner.** `tests/run_all.sh` reports success with zero tests. `test_utils_hardening` is broken.
8. **`photo_eic` re-entrancy.** It is re-entrant in practice but flagged `Reentrant: false`. Seed merges and periodic dumps need the flag.
9. **Lambda doesn't run.** Its drivers abort at configure (stale paths), and its `.cmnd` redefines ²⁰Ne with mass 0.
10. **Verified toolchain facts:**
    - HepMC3 gzip works with compile-time flags.
    - `PythiaParallel` balances load by default, so the event set is deterministic for a fixed seed and thread count.

## Relation to `docs/plans/`

`docs/plans/` (2026-09-16) asked how to **integrate** the new tools into the *existing* module stack.
- This rework answers the from-scratch question and **supersedes** it. The mapping of its items to steps is in `docs/plans/README.md`.
- In-process Rivet (plans B) and sinks (plans C) are kept.
- Unified configuration (plans A) is realised by validating in Python.
- The old modules are archived, not adapted.
