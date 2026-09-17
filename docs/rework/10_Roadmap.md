# 10 — Roadmap, decisions, risks, open questions

Date: 2026-09-17 (revision b) · Status: **Proposed**. Execution is step-based: see **[steps/README.md](steps/README.md)** for the index, the step files, the decision register and the traceability matrix.

**What this revision changed:**
- It supersedes the first roadmap (P0–P8, ≈ 20–23 d) of this directory.
- It supersedes `docs/plans/04_Roadmap.md`. That file's open items 0.1, 0.3, 0.4 and 0.7 are absorbed into P0 (0.4 by archiving Lambda instead of repairing it).
- It adds the decisions taken after the first revision (D13–D20) and the re-audit findings (`00/Bn`, [00_Audit §4](00_Audit.md#4-current-workflow-defects-2026-09-17)).

## 0. Guiding rules

1. **Replacement before removal.** Nothing is removed before its replacement passes. The old tools (`rivpyth`, `ydplt`, `ydmrg`, `generator.cc`) are versioned in the repo, hotfixed, and stay in use until the golden and real-study comparisons pass (P4-S06).
2. **Working state.** Every phase ends in a working state with its own exit criteria.
3. **Test bed** (D20). PhotoProduction is a test bed. Physics, maths and logic must be correct; specific physics choices are not blockers.
4. **Scratch only.** Tests and dry runs never write into `results/` or `configs/`. They use `output/scratch/`, `HEKIT_RESULTS`, and a pytest guard from P1. The old tools are run from `output/scratch/legacy/`.
5. **Approval.** Commits, tags, moves of `results/`, and edits to `bots/` happen only with user approval.
6. **One file per step.** Execution: read the step → mirror it to `bots/current_plan.md` → do it → run its checks → mark it done → update the index.
7. **Citations.** Findings are cited as `00/Bn` (this rework) or `plans/Bn` (`docs/plans`).

## 1. Phases

| Phase | Goal | Exit criteria | Depends on | Effort |
|---|---|---|---|---|
| **P0** Baseline, hygiene, legacy freeze | Current workflow versioned, physics-correct and reproducible from a tag; golden fixtures; Lambda and old utils frozen | Clean tree + tags; env idempotent, `import ROOT/pythia8/rich` OK; `rivpyth` runs from `tools/`; hotfix tests pass in scratch; `tests/golden` green; PhotoProduction make targets build | — | 2.5 d |
| **P1** Python core | `hep plan` on schema 2 with identity seeds and hashes | `hep plan --json` matches the legacy fixtures except `EXPECTED_DELTAS.md`; pytest < 5 s; `hep doctor` | P0 | 4.5 d |
| **P2** C++ core + CMake + `hep-run` v1 | Pythia + serial in-process Rivet, merged σ, status fd, atomic outputs | Full and minimal builds; ctest green incl. the `slow` equivalence gate against the legacy FIFO; D-Q1/D-Q2 recorded | P1 | 4.5 d |
| **P3** Supervision, results, terminal | `hep run` end-to-end with a live view and provenance | e2e mini run in scratch; Ctrl-C → partial + exit 6; fake-stage suite; `hep watch` | P2 | 3.4 d |
| **P4** Plotting, compare, retirement | `hep plot`/`hep compare` replace `ydplt`/`ydmrg`; `photo_eic` re-entrant; old tools retired | Golden page comparisons; real-study cross-check; tools in `legacy/`; v2 configs canonical; Makefile wraps CMake | P3 | 4.25 d |
| **P5** Event store and replay | Sharded HepMC3 store; `tool = "store"` | Write → replay reproduces the in-process YODA; σ from the index | P3 (can run alongside P4) | 2.5 d |
| **P6** Throughput | Sharded Rivet, event groups, bench | Serial ≡ sharded; radius study = 1 generation | P4-S05, P5 | 2 d |
| **P7** External generators + Delphes | Sherpa, Whizard, MadGraph, Herwig (gated), Delphes (external) | Sherpa and MG+Pythia points via `hep run`; prepare cache hit; `delphes.root`; Herwig runs or is explicitly gated | P3, P5-S02 | 7 d |
| **P8** Modules, YODA results, Phys, ML | User modules book YODA into `analysis.yoda`; ONNX | Toy module exact at 1/4/20 threads; ONNX toy; D-DERIVED recorded | P2, P6-S01, P5-S01 | 3 d |
| **P9** ROOT processing | `hep proc` fits and RDF → `fits.json` + YODA | Minuit2 ≡ scipy; RDF ≡ uproot on `delphes.root` | P4 (+ P7-S08 for S02) | 2.5 d |
| **P10** Cleanup + docs | No transitional code; docs match reality | Clean greps; minimal build; tag `rework/v1` | P4 (+ the optional phases done) | 1.25 d |

- **Total:** ≈ 37 d.
- **Critical path:** P0 → P4, about 19 d, replaces today's PhotoProduction workflow.
- **After that:** P5–P9 follow need.

```
P0 ─► P1 ─► P2 ─► P3 ─┬─► P4 ─┬──────────────► P10
                      │       ├─► P9 ◄┄ P7-S08
                      ├─► P5 ─┴─► P6 ─► P8
                      └─► P7 (needs P5-S02)
```

**Step count:** 55 (P0 8 · P1 7 · P2 6 · P3 5 · P4 6 · P5 3 · P6 3 · P7 8 · P8 4 · P9 2 · P10 3).
- **Decision-only steps:** P2-S02, P3-S01, P7-S02, P7-S06, P8-S04.
- **Docs-only steps:** P0-S00 (this revision), P10-S02.

## 2. Decision log

| # | Decision | Chosen | Given up |
|---|---|---|---|
| D1 | Language split | Python orchestration, C++ event loop | A single-language codebase |
| D2 | Config validation | Once, in Python; C++ reads a resolved spec | User-facing config ergonomics in `hep-run` (it gets `--plain` only) |
| D3 | Physics in TOML | No. Native cards + overrides only. | Cross-generator "same physics" guarantees (Q7 is a documented decision instead) |
| D4 | Pythia → Rivet | In-process sink | The HepMC text round trip (still available as the store / FIFO tee) |
| D5 | External generators → Rivet | FIFO into `hep-run` (uniform); native Rivet as an option | Some speed for Sherpa Rivet-only runs |
| D6 | Rendering | Python `rich`, one renderer across stages | The C++ progress bar when running `hep-run` by hand |
| D7 *(revised)* | Numerical results | **YODA only**, including C++ module histograms; ROOT is not a results format | Record's ROOT histograms/trees; the earlier RNTuple sink idea (withdrawn) |
| D8 *(revised)* | Reading events | **HepMC3 store + replay** (D13); `Source::Stream` for external generators; RDataFrame/uproot only for Delphes output | Probe's ROOT Event/Feed join model |
| D9 | Plotting | `rivet-mkhtml` + mplhep; `.plot` files as the label source | Paint's ROOT canvases |
| D10 | Build | CMake with optional components (+ thin Makefile) | Make simplicity |
| D11 | Results layout | Point directories + studies, keyed by name and hash | The `serial` prefix convention |
| D12 | CLI | One `hep` (click); shell only for env/cd | Standalone scripts per task |
| D13 | Event storage | Sharded HepMC3 files + JSON index; parallel replay ([11](11_EventStore.md)) | Fast columnar ROOT event buffers |
| D14 | Results format | YODA for Rivet **and** modules; one `analysis.yoda` per group | Per-module ROOT files |
| D15 | ROOT's role | Processing only: fits, statistics, RDataFrame ([12](12_Processing.md)); `hep-run` doesn't link ROOT | ROOT-native storage and canvases |
| D16 | C++ style | House style: PascalCase top-level facade namespaces, no nesting; `Events` (not `Event`), X11 `Status` guard, no namespace-scope `using namespace` ([13](13_Namespaces.md)) | Nested `hekit::…` namespaces |
| D17 | Lambda | Archived frozen in a tracked `legacy/` with tag, README (physics notes, bugs) and port notes | A Lambda module in this rework |
| D18 | Old tools | Moved into the repo **before** the port (P0-S03) | Porting directly from unversioned `~/HEP` files |
| D19 | Old-tool bugs | Hotfix the physics-relevant ones now (00/B2–B5, B20, B21), then port | A frozen legacy tool with known wrong results |
| D20 | PhotoProduction | A test bed: correctness required, specifics (lepton charge, tags, cut values) not blockers | Pedantic physics review as a gate |
| D21 | Seeds | Identity-derived, disjoint per-instance `Parallelism:seeds` blocks (03 §5) | Position-based `seed + (i−1)·step` |
| D22 | Partial outputs | Written only as `analysis.partial.yoda` / `.part`; atomic renames everywhere | Rivet's default "write whatever you have" at the final path |
| D23 | Derived tables | **Deferred** (P8-S04; trigger: first ML training dataset) | ML feature export in the first phases |

## 3. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Sharded Rivet merge ≠ serial (merge semantics, re-entrancy) | M | H | Equivalence gate in P6-S01; `auto` uses serial unless every analysis is re-entrant |
| Repeated `PythiaParallel::run()` misbehaves (σ accumulation), or `Parallelism:seeds` interacts badly with chunked runs | M | M | Spike P2-S02 before any C++ run loop; fallback: single `run()` + cooperative stop |
| σ error combination is wrong | M | M | Compare with `stat(true)`; record "unavailable" rather than a wrong number |
| `rivet-merge` ignores module objects in `analysis.yoda` | H | M | hekit merges module objects itself (07 §3); test in P8-S01 |
| External generators' HepMC lacks `GenCrossSection`, or writes it only at the end | M | M | Adapter preflight on 10 events; allow `rivet.xsec` = number |
| gz replay throughput too low for large stores | M | L | D-STORE-COMP spike (zstd); shards give parallelism; measure with `hep bench` |
| PyROOT unavailable or fragile on a machine | M | L | scipy/uproot fallbacks in `hep proc`; `hep doctor` check |
| Delphes global `Event` / ROOT state clashes | M | M | External Delphes only; namespace `Events`; in-process deferred |
| Herwig rebuild fails or is delayed | M | L | Decision step P7-S06; Herwig is the last adapter |
| `rich` rendering in remote or odd terminals | L | L | Plain mode; `hep watch` from files |
| Legacy hotfixes change today's outputs unexpectedly | M | M | Golden fixtures captured **before** the hotfixes (P0-S04); `EXPECTED_DELTAS.md` |
| Scope creep (a DAG engine, physics-in-TOML) | M | H | Rejected explicitly (02 §3, 03 intro); stage chains are a closed list |
| Losing working behaviour during the port | M | H | Rule 1; golden comparisons at P1, P2 and P4 |

## 4. What to revisit as the system grows

- **Batch backend:** `run.toml` is already self-contained. Add `hep run --backend slurm|condor`, one job per event group, and make `hep watch` read the job states.
- **Run index:** SQLite over the `provenance.json` files once there are hundreds of points (`hep runs --where pdf=NNLO`).
- **Weight variations instead of re-generation:** Pythia `UncertaintyBands` / Sherpa on-the-fly; Rivet multi-weight YODA is supported from P2.
- **Faster event I/O:** HepMC3-ROOT or Protobuf, if replay becomes central. Neither is built, and ROOT storage conflicts with D13, so this would need a new decision.
- **Derived tables** (D23), when ML training starts.
- **In-process Delphes and ROOT canvases**, only if needed.
- **Mac stack:** confirm that the components degrade cleanly (P10-S03).
- **Lambda revival:** a module on `GenEvent` plus `hep proc` fits (00b §5).
- **Shareable plot gallery:** a study's `plots/` as a single HTML page.

## 5. Open questions

The authoritative status lives in the decision register in [steps/README.md](steps/README.md#7-decision-register).

| # | Question | Status | Step |
|---|---|---|---|
| Q1 | Combine per-instance σ errors from `PythiaParallel` (check against `stat(true)`)? | open → spike | P2-S02 |
| Q2 | Repeated `PythiaParallel::run()` after one `init()` σ-consistent in 8.317? | open → spike | P2-S02 |
| Q3 | Numeric serial label for studies? | proposed: no (free-text `run.label` only) | P3-S01 |
| Q4 | Import legacy `results/PhotoProduction`? | proposed: no; move to `results/PhotoProduction/legacy/` | P3-S01 |
| Q5 | Add `rich`, `tomli_w` (and `pytest`) to the venv? | **answered: yes** | P0-S02 |
| Q6 | Rebuild ThePEG/Herwig with HepMC + Rivet now or later? | open | P7-S06 |
| Q7 | "Same physics" photoproduction set-up across generators? | open | P7-S02 |
| Q8 | Port or archive Lambda? | **answered: archive frozen** (D17) | P0-S06 |
| Q9 | HepMC3 gzip support here? | **answered: yes** (compile-time flags); zstd pending (D-STORE-COMP) | P5-S01 |
| Q10 | Derived per-candidate tables format? | **deferred** (D23) | P8-S04 |
