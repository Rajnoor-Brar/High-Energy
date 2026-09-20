# 00 — Audit: what exists, what it costs, what survives

Date: 2026-09-17 · Machine: Lab_PC · Branch: `sidequest`

**Scope:**
- `utils/` (C++ framework), `modules/Lambda/`, `sources/`, `configs/`, `Makefile`;
- the `~/HEP` commands (`setup.sh`, `rivpyth`, `ydplt`, `ydmrg`, `rivpyth_common.py`);
- what each installed tool actually exposes on this machine.

Earlier audits:
- `docs/UtilsAudit.md` (2026-06, now `legacy/docs/`) is **partly stale**. Four of its open items are already fixed: the `traitsOf` bounds check, `writeTextFile` stream checking, the scoped `fs` alias, and the `Time.hh` → Config include. `docs/UtilsDependencyMap.md` is stale too.
- `legacy/docs/plans/01_CurrentState.md` (2026-09) still describes the two workflows correctly.

This file answers a different question: **judged from scratch, what is each piece worth?**

- **Revision 2026-09-17 (b):** a full read-only re-audit of `utils/`, Lambda and PhotoProduction + `~/HEP`.
  - It revised the verdicts in §3 and added §4 (current defects, with IDs `00/Bn`) and §5 (what gets carried over).
  - The function-level porting table is in [00b_PortingMap.md](00b_PortingMap.md).
- **ID scheme.** Findings here are cited as `00/Bn`, because `legacy/docs/plans` already uses B1, B2, … for different findings, cited as `plans/Bn`.

---

## 1. Inventory

### 1.1 `utils/` — 58 headers, ~10,600 lines, C++17 header-only

| Namespace | Lines | What it does | Coupled to |
|---|---|---|---|
| `Probe` | ~2,700 | Parallel reading of the project's *own* ROOT TTrees; Event/Feed row-join streams; an IMT variant | ROOT, Config |
| `Record` | ~2,600 | ROOT TTree/histogram writer; worker pool; clone-per-worker merge; checkpoints; `About/` provenance | ROOT, Config, Monitor |
| `Paint` | ~1,600 | TOML-driven ROOT canvas rendering (Book → Resolve → Render → Save) | ROOT, toml++ |
| `Monitor` | ~1,200 | Async logger; ANSI progress bar/status; stall detection; run/thread logs | Config, **Record::Writer** |
| `Config` | ~810 | TOML parse/merge, limits files, thread resolution, `configure<Pipeline>()` facade | Probe, Record, Monitor (facade) |
| `Utility` | ~730 | Time/number formatting, signals, SHA-256, paths, TOML merge, ROOT aids | ROOT (partly), Config (inversion) |
| `Physics` | ~290 | Property enums and trait tables, kinematics helpers, a small PDG table | ROOT `TLorentzVector`-style types |

Plus `modules/Lambda` (~470 lines), the Λ reconstruction module.

### 1.2 PhotoProduction toolchain

| Piece | Size | Where | Versioned |
|---|---|---|---|
| `rivpyth_common.py` | 1,147 lines | `~/HEP` | **no** |
| `rivpyth` / `ydplt` / `ydmrg` | 267 / 80 / 96 lines | `~/HEP` | **no** |
| `generator.cc` | 88 lines | `sources/PhotoProduction` | yes |
| `photo_eic.{cc,info,plot}` | 191 lines + metadata | `sources/PhotoProduction` | yes |
| `eic.toml`, `zeus_validation.toml`, `photo_ep.cmnd` | — | `configs/PhotoProduction` | yes (untracked) |
| `setup.sh` | ~150 lines | `~/HEP` | **no** |

### 1.3 What each tool exposes on this machine

Checked directly; items marked ✗ are defects or gaps in the install.

| Tool | C++ API | Python | CLI | Event I/O | Notes |
|---|---|---|---|---|---|
| Pythia 8.317 | ✓ `PythiaParallel`, `Pythia8Plugins/{HepMC3,RivetHooks,LHAPDF6,FastJet3}.h` | ✗ `pythia8.so` is in `pythia8/lib`, **not on `PYTHONPATH`** | examples only | HepMC3 out; LHE in | Callbacks serial unless `Parallelism:processAsync = on` |
| Rivet 4.1.3 | ✓ `AnalysisHandler` (`setCrossSection`, `merge`, `setFinalizePeriod`) | ✓ | `rivet`, `rivet-build`, `rivet-mkhtml`, `rivet-merge` | reads HepMC (file or FIFO) | `RivetONNXrt.hh` exists, but Rivet is **not linked to ONNX**; plugins would have to link it themselves |
| YODA 2.1.3 | ✓ | ✓ | `yodamerge`, `yoda2root`, … | — | |
| LHAPDF 6.5.6 | ✓ | ✓ | `lhapdf` (list/install) | — | |
| HepMC3 3.03.01 | ✓ | ✓ `pyHepMC3` (venv) | — | ASCII, HepMC2, LHEF; `search` library | No `HepMC3rootIO` seen, so no ROOT-format HepMC. Compression: header-only `WriterGZ`/`ReaderGZ` **verified** with `-DHEPMC3_USE_COMPRESSION -DHEPMC3_Z_SUPPORT -lz` (zstd/lzma headers present) |
| FastJet 3.5.0 | ✓ (+ contrib, SISCone) | ✗ not built | — | — | Linked through Rivet |
| ROOT 6.40.04 | ✓ `RDataFrame`, **`RNTupleParallelWriter`** | ✗ lives in `root/lib`, **not on `PYTHONPATH`** (works when added) | `root` | — | uproot 5.7 reads RNTuple |
| Herwig 7.3.0 / ThePEG 2.3.0 | ThePEG | — | `Herwig read/run` | **✗ ThePEG built without HepMC and Rivet** (no `HepMCFile`, no `RivetAnalysis` module) | Events cannot leave Herwig in a standard format until it is rebuilt |
| Sherpa 3.0.5 | — | — | `Sherpa` (YAML) | ✓ `libSherpaHepMC3Output`, ✓ `libSherpaRivetAnalysis` | Best-equipped external generator |
| Whizard 3.1.8 | — | — | `whizard` (SINDARIN) | ✓ HepMC3 sample output (symbols present) | Parton-level unless showered |
| MadGraph5_aMC | — | Python-2/3 internal | `mg5_aMC` | LHE out | Showering through Pythia (LHE → `Beams:frameType = 4`) |
| Delphes | ✓ `libDelphes` | via ROOT | `DelphesHepMC3`, `DelphesPythia8`, `DelphesLHEF`, … | HepMC3 in, ROOT out | Single-threaded |
| ONNX Runtime 1.29 | ✓ C/C++ | ✓ | — | — | |
| Python venv 3.12 | — | numpy, matplotlib, **mplhep**, **hist**, uproot, awkward, click | — | — | **No `rich`**; no `tomli_w`; `tomllib` is in the standard library |

---

## 2. Findings that shape the redesign

| # | Finding | Consequence for the design |
|---|---|---|
| F1 | **Two stacks with no shared core.** Lambda is C++ with its own config, monitor and output. PhotoProduction is Python orchestration plus a bare C++ generator. Neither reuses the other's code. | Rework the stack around one config model, one run-control layer and one output contract. |
| F2 | **Config logic exists twice and diverged.** C++ `Config::Reader` is lenient (unknown keys ignored). Python `rivpyth_common` is strict and far richer: sweeps, settle, studies. `Config` is also re-parsed by five subsystems. | Validate and expand **once**, in Python. C++ reads a fully *resolved* spec. |
| F3 | **The valuable config ideas live in the unversioned file** (typed quantities, `across` groups, `settle`, studies, base + point cmnd). | Carry these over as-is; they are the most mature design in the codebase. Move the code into the repo. |
| F4 | **Monitor is ANSI rendering + stall detection bolted onto Record.** It cannot run without a `Record::Writer`, and it renders only one process's progress. | Renderer moves to the orchestrator (sees all stages). C++ only *emits* status. |
| F5 | **Record (~2.6k lines) is a ROOT histogram/tree writer** with clone-and-merge and provenance (`About/`). Its histograms may be written unscaled, and its checkpoints are empty (§4.5). | Results become **YODA only** (D14): `Results` books YODA per worker and merges, reusing the clone/merge idea. Provenance → `provenance.json` + YODA annotations. *(The earlier idea of an RNTuple sink is withdrawn.)* |
| F6 | **Probe (~2.7k lines) buffers MC events in the project's own ROOT trees** and re-implements parallel reading. User priority: re-reading events is low. | Retire Probe. **HepMC3 is the event store** (D13, [11](11_EventStore.md)): sharded files, parallel replay, and the same reader serves external generators. ROOT reading is only needed for Delphes output (RDataFrame/uproot, [12](12_Processing.md)). |
| F7 | **Paint (~1.6k lines) is a ROOT styling DSL.** The new outputs are YODA, and `rivet-mkhtml` + mplhep cover plotting. | Retire Paint. One Python plotting layer for YODA. ROOT is a **processing** layer (fits, stats, RDataFrame; D15). |
| F8 | **FIFO pipeline:** the early-failure hang is fixed. Cross-section still comes from the last thread's running estimate, output is serialised ASCII, and generation and analysis are separate processes. | For Pythia, run Rivet **in-process** with a merged σ. Keep FIFO/HepMC only where the generator is another program. |
| F9 | **External generators have heterogeneous, text-only interfaces:** `.in` (Herwig), YAML (Sherpa), SINDARIN (Whizard), cards (MadGraph). | Adapter per generator that *renders* a native card from base file + overrides. Do not translate physics into TOML. |
| F10 | **Environment gaps:** `pythia8` and `ROOT` Python modules not importable; `RIVET_ANALYSIS_PATH` hard-codes one project and starts with `:`; ThePEG without HepMC/Rivet; no `rich`. | `setup.sh` fixes; a `hep doctor` check; a Herwig rebuild listed as a prerequisite. |
| F11 | **Build:** `make` evaluates every `*-config` for every target and links everything into everything. Header dependency tracking was lost. Tests are disconnected from the build output. | CMake with optional components (see 09). |
| F12 | **Terminal output today:** Pythia is silenced (`Print:quiet`). Rivet's INFO lines interleave with nothing. Lambda has a nice ANSI bar, but only for itself. | One dashboard for all stages; tool chatter goes to per-stage logs, with highlights (see 06). |

---

## 3. Verdicts (revised)

A **Keep** verdict means the *idea* moves into the new layout, rewritten to fit it. Namespaces follow the house style ([13_Namespaces.md](13_Namespaces.md)). **Archived** means `git mv` to a tracked `legacy/` directory with a tag and a README (P0-S06).

| Current piece | Verdict | Reason / target |
|---|---|---|
| `Config` (C++) | **Replace** with `Core` Spec reader (~200 lines) | Validation moves to Python (F2); migration tables → `hekit.config.migrate` |
| `Monitor` (C++) | **Replace** with `Status` (facts) | Rendering → `hekit.term`, stall detection → `hekit.run` (F4). `Timer.hh` is ported as-is. |
| `Record` | **Replace** with `Results` (YODA per-worker booking and merge) + `Core` Provenance | F5, D14. Kept ideas: clone/merge, declare-time validation, tmp + rename, Meta field list. |
| `Probe` | **Replace** with `Store` (HepMC3 shards) + `Source::StoreReplay` | F6, D13. Kept ideas: access patterns and the bounded queue. |
| `Paint` | **Remove** | F7. The house style becomes an mplhep style file. |
| `Physics` | **Port** → `Phys` | Trait tables, PDG table, kinematics |
| `Utility::{Sha256, Signals, Time, Paths}` | **Port** → `Core` | Small, correct, needed (move Signals to `sigaction`) |
| `Utility::{RootAid, RootTypes, Toml, numberString}` | **Remove** | No ROOT I/O in C++; TOML handling is in Python |
| `modules/Lambda`, `sources/Lambda`, `configs/lambda` | **Archive frozen** (D17) | Does not run (§4.5). The physics is documented for a possible revival. |
| `generator.cc` | **Hotfix now** (P0-S05), **replace** with `hep-run` (P2), **archive** at P4-S06 | F8, §4.3 |
| `photo_eic` plugin | **Keep**; make it re-entrant (P4-S05) | Good Rivet practice |
| `photo_5x41/10x100/18x275` | **Archive** | Superseded by `photo_eic`; only legacy YODAs reference them |
| `rivpyth_common.py`, `rivpyth`, `ydplt`, `ydmrg` | **Move into the repo** (P0-S03), **hotfix** (P0-S05), **port** into `hekit` (P1–P4), **archive** (P4-S06) | F3; D18, D19 |
| `setup.sh` | **Versioned** as `env/hep_env.sh` + a `~/HEP` stub; **fixed** (P0-S02) | §4.6 |
| `configs/defaults`, `configs/templates`, `configs/all.toml`, `configs/Paint.toml` | **Archive** | Replaced by the generated reference (03 §6); house style kept (00b §4) |
| `tests/` (C++ unit tests of the old code) | **Archive** | The new tests live with the new code (09) |
| `_Paint.cc`, `_ThreadBench.cc`, `root_macros/` | **Archive** | — |
| `docs/{MAP,Architecture,DataContract,UtilsAudit,UtilsDependencyMap,Audit}.md`, `docs/plans/` | **Archive** (P0-S06), then rewrite `docs/MAP.md` (P10-S02) | Stale (§4.7) |

**Net effect (estimate):**
- C++ framework: ~10.6k → ~3.2k lines (store and YODA results included; 05 §8).
- Python: ~1.6k → ~4k lines.
- Together these cover more tools than both old stacks.

---

## 4. Current workflow defects (2026-09-17)

### 4.1 PhotoProduction orchestration (`rivpyth`, `ydplt`, `ydmrg`, `rivpyth_common.py`)

**Fix columns:**
- **Old tools:** fixed in the old tools now (P0-S05).
- **hekit:** fixed by design in the new stack, with a regression test.
- **Test bed:** PhotoProduction is a test bed (D20). Physics, maths and logic must be right; specific physics choices are not blockers.

| ID | Defect | Evidence | Fix |
|---|---|---|---|
| 00/B1 | Seeds follow a point's position, not its identity: the same file name gets different seeds in different studies | `rivpyth_common.py:679-686` | hekit (P1-S04) |
| 00/B2 | Thread RNG streams overlap. Pythia seeds instance *i* with `seed+i` (`Parallelism:seeds` empty); points step the seed by 1 with 20 threads, so neighbouring points share 19 of 20 streams. | `Parallelism.xml:155`, `PythiaParallel.cc:93-101` | Old tools: guard `seed_step ≥ threads`. hekit: disjoint `Parallelism:seeds` blocks (P1-S04). |
| 00/B3 | A killed or failed run leaves a partial YODA at the final path (rivet finalizes on SIGTERM/EOF); `skip_existing` then skips it | `rivet:490-500,733,754-756`; `rivpyth:244` | Old tools: `.part` + rename. hekit: `analysis.partial.yoda` (P2-S05). |
| 00/B4 | The 27x920 label says √s = 95.6 GeV; 27.5×920 gives 318.1 GeV | `eic.toml:61` | Old tools |
| 00/B5 | ZEUS data is overlaid by histogram name onto different observables (e.g. `d08`) | `remap_data_yoda`; `ZEUS_2012_I1116258.cc:53-57` | Old tools: `use_data = false`. hekit: explicit data map (P4-S01). |
| 00/B6 | `--overlay`/`--style` without `--across` re-flattens coupled groups | `rivpyth_common.py:609-611` | hekit (P1-S03) |
| 00/B7 | Validation runs before the study is applied | `rivpyth_common.py:153` | hekit (P1-S03) |
| 00/B9 | `:g` formatting rounds Pythia and Rivet values to 6 significant digits | `rivpyth_common.py:194-195` | hekit (P1-S03) |
| 00/B10 | Stale comments in `eic.toml` (default scan, study descriptions, void/min_entries notes) | `eic.toml:7-11,21-22,47,136,140,169` | Old tools |
| 00/B11 | Every study runs e⁺ because of `[settle.use]` | `eic.toml:43-45` | No action (test bed) |
| 00/B12 | `NNLO`/`NNNLO` tags name LO/NLO sets | `eic.toml:83` | Renamed only in the v2 migration (P1-S06) |
| 00/B13 | Contradictory ProcessType notes between the two configs | `eic.toml:115-117`, `zeus_validation.toml:75` | Old tools (verify, then fix the comment) |
| 00/B14 | `zeus_validation.toml` declares R/ETMIN options the ZEUS analysis lacks | `zeus_validation.toml` | hekit: validation against `.info` (P1-S05/S06) |
| 00/B15 | Physics-identical points get different names (`pth6`, `allproc`, `r10` = base) | naming | hekit: hash on effective settings (P1-S04) |
| 00/B17 | `ydmrg` merged YODAs share the point namespace | `ydmrg:62-73` | hekit (P4-S01) |
| 00/B18 | All paths are CWD-relative | `rivpyth_common.py:755-800` | hekit (P1-S01, P3-S03) |
| 00/B19 | Fixed shared `/tmp` paths | `rivpyth:236-238`, `ydplt:21` | hekit (P3-S02, P4-S01) |
| 00/B20 | `supervise` can report the generator's SIGPIPE instead of rivet's real error | `rivpyth:156-166` | Old tools + hekit (P3-S02) |
| 00/B21 | `generator.cc` exits 0 when HepMC writes fail | `generator.cc:73,87` | Old tools + hekit (P2-S05) |
| 00/B22 | Numeric values cannot be pinned from the CLI (all-digit selector = index) | `rivpyth_common.py:566` | hekit (P1-S03) |
| 00/B23 | Stale `photo_ep.cmnd` comments (who appends, where N/threads come from) | `photo_ep.cmnd:3,10` | Old tools |
| 00/B24 | Debris: stale FIFOs in `output/PhotoProduction/`, misnamed pycache in `~/HEP` | `ls -la` | P0-S03 |
| 00/B25 | SISCone plugin leak (`delete_plugin_when_unused` not called) | `photo_eic.cc:76-80` | P4-S05 |
| 00/B26 | η acceptance inverted if `orientation = −1` | `photo_eic.cc:126` | **verified not a defect** (P4-S05): Rivet 4.1.3 normalises an inverted range, and both versions give identical output. The cut is now written symmetrically so it cannot depend on that. |
| 00/B27 | Base `pTHatMin = 6` > jet `ETMIN = 5` biases the first E_T bin | `photo_ep.cmnd`, `photo_eic.cc` | Record only (the pthatmin study measures it) |
| 00/B28 | `configs/photo_zeus/README_ZEUS.txt` describes deleted files and an old workflow | file | Archive (P0-S06) |
| 00/B29 | `yoda.read()` resets `LC_ALL` to `C` and never restores it, so the locale default encoding becomes ASCII and later locale-dependent text I/O fails on non-ASCII content (the point-cmnd header holds an em dash) | measured in P0-S05 | Old tools: restore the locale and name every encoding. hekit: never rely on the locale default (P1-S01) |
| 00/B30 | `Photon:ProcessType` 0 and 1 give identical events with this base cmnd, 2 fails `init()`, 3 only changes MPI handling, so the direct contribution is unreachable and the `process` study is a null comparison | measured in P0-S05 (400 events, 27x920) | Comments corrected (P0-S05); a direct-photon card is future physics work |
| 00/B31 | **Jet clustering cannot be done from two threads at once**, so no analysis that clusters can be sharded. `SISConePlugin::{stored_plugin, stored_particles, stored_siscone}` are process-wide statics mutated inside `run_clustering`, and `siscone::local_ranlux_state` is a global RNG its split-merge draws from; this FastJet is additionally built with `FASTJET_HAVE_LIMITED_THREAD_SAFETY` undefined. A race changes the jets rather than crashing | `fastjet-3.5.0/plugins/SISCone/SISConePlugin.cc:80-82,139-168`, `siscone/ranlux.cpp:57`, `fastjet/config_auto.h:112` | Found in P6-S01. `[run].mode = "auto"` refuses to shard a Rivet sink in a build without thread-safe FastJet and says why; an explicit `"sharded"` stops the run when an analysis turns out to declare a `FastJets`. `photo_eic` therefore always runs serially |
| 00/B32 | A sink exception thrown from `hep-run`'s event callback would have called `std::terminate`: `PythiaParallel` runs the callback on its worker threads in **both** modes (`processAsync = off` only adds a mutex), so the throw unwound through `std::thread` | `PythiaParallel.cc:170-210` | Fixed in P6-S01: both sources catch at the thread boundary and rethrow on the main thread, so a sink error keeps its exit code and message |
| 00/B33 | **`hep-run --check` on a stream source hung forever.** `Source::Replay::initialise()` started its readers, and opening a FIFO for reading blocks until a writer appears — which a preflight never starts. Every external-generator run would have hung before generating anything | found in P7-S01 | Fixed: `initialise()` validates the inputs without opening them (a FIFO only has to exist; a shard is checked as a regular file) and the readers start in `run()`, where there really is a writer at the other end |

B8 and B16 are unused: B8 is covered by §4.4, B16 by §4.5 / the P0-S04 inventory.

**Golden fixture** (the current expansion of `eic.toml`, captured in P0-S04):
| Study | Points | Pages |
|---|---|---|
| single | 1 | — |
| pdf | 4 | 1 |
| energies | 4 | 1 |
| energy_pdf | 16 | 4 |
| mpi | 3 | — |
| mpi_onoff | 2 | — |
| mpi_grid | 6 | 2 |
| pthatmin | 4 | — |
| process | 2 | — |
| radius | 3 (analysis `photo_eic:R=0.4/0.7/1`) | — |

`zeus_validation.toml` expands to 4 points and has never been run.

### 4.2 `photo_eic`
- `finalize()` only uses booked objects plus σ and ΣW, so it is already safe to re-run. The `.info` still says `Reentrant: false`.
  - With that flag, Rivet 4.1.3 skips `finalize` in periodic dumps (`AnalysisHandler.cc:700-705`).
  - `rivet-merge` warns about or drops the analysis.
  - Flip the flag after a `rivet-merge -e` check (P4-S05).
- The old per-energy plugins differ only in the W window. They are still referenced by legacy YODAs, and re-plotting those needs `plot_analysis = "photo_eic"`.

### 4.3 `generator.cc`
**Behaviours `hep-run` must preserve:**
1. Cards read in order, later values win; a failure exits 1.
2. `Print:quiet` by default; a card can re-enable output.
3. `processAsync` is forced off (the runner owns it).
4. Output is opened only after `init()`.
5. Output goes through `Pythia8ToHepMC`.
6. Exit codes: 2 = usage, 1 = card/init failure.

**Gaps:** σ is a per-thread running estimate; HepMC write failures exit 0 (00/B21); no signal handling; `GIT_SHA` is unused.

**Event counts (measured, P0-S04):** `Main:numberOfEvents` counts `next()` *attempts*. `PythiaParallel::run()` increments its per-thread counter before the success check and invokes the callback only for successful events (`PythiaParallel.cc:186-208`), so written events are fewer than attempts: about 2 % fewer at 5x41, 0.23 % at 10x100, 0.04 % at 18x275, 0.01 % at 27x920. Any completeness check must compare the analysis count with the *written* count.

### 4.4 Build and tests
- **Makefile:**
  - `:=` evaluates every `*-config` on every call.
  - Every target links ROOT, Pythia, HepMC3, FastJet, YODA, LHAPDF, ONNX, Delphes and toml++.
  - No header dependency tracking (`-MF` without `-MMD` was already inert before `0a10209`).
  - The `.so` rule hides copy failures (`; true`).
  - `clean` removes the plugins that `RIVET_ANALYSIS_PATH` points at.
  - `GIT_SHA` changes don't trigger a rebuild.
- **Tests:**
  - `tests/run_all.sh` globs `tests/test_*.exe`, but binaries are built in `output/tests/`, so it reports "0 passed" and exits 0.
  - `test_utils_hardening` expects `configs/Lambda_Limits.toml`, which has moved.
  - Untested: Signals, Time, Number, the Monitor loop, stall detection, `Meta::writeAbout`.

### 4.5 `utils/` and Lambda (recorded in `legacy/README.md`; not fixed)
**`utils/`:**
- Record checkpoints contain empty histograms: fills go to worker clones, and checkpoints write the unmerged masters.
- Final histograms are probably written unscaled: `outFile->Write(kOverwrite)` rewrites the masters after the scaled snapshot (unverified).
- The Monitor bar interval is computed from the default `nEvents = 100` in the Pythia pipeline.
- Negative section thread counts wrap around.
- `readFile`/`init()` results are unchecked.
- `sum_weights` is a placeholder.
- Include cycles: Config ↔ Probe and Record ↔ Monitor.
- Probe:
  - array readers are float-only;
  - reader-dependent column types;
  - two array specs on one tree can read stale data (unverified);
  - IMT re-reads earlier windows (quadratic I/O).

**Lambda:**
- Every driver aborts at configure: `hist_limits` resolves to the missing `configs/Lambda_Limits.toml`, and the `cmnd_file` and driver defaults point at old paths.
- The `.cmnd` redefines ²⁰Ne with m0 = 0 and chargeType 20.
- The angle cut is dead (cos θ ≡ −1 in the pair rest frame).
- `reserved_protons` doesn't match Angantyr's `NucRem`.
- `HeavyIon:SigFitNGen` is set twice.
- The writer can emit rows out of `event_index` order.
- Histograms are scaled ×100 when `hist_scaling` is unset.
- `Momentum_Z` limits start at 0.
- A syntax-only compile passes.

### 4.6 Environment (`~/HEP/setup.sh`)
- `PYTHONPATH` lacks `root/lib` and `pythia8/lib`, so `import ROOT` and `import pythia8` fail.
- `RIVET_ANALYSIS_PATH` hard-codes one project, uses `~`, and has empty elements (an empty element means the CWD).
- `_hep_prepend` is not idempotent, so `hep_refresh` duplicates every path variable.
- `hep_status` runs on every source (slow `--version` probes).
- `quit` unsets itself.
- The file is unversioned.

### 4.7 Stale documentation

All of the files listed here were archived to `legacy/docs/` in P0-S06; the paths below are their pre-move locations.
- `docs/MAP.md` (lines 19, 150-161), `docs/Architecture.md:5-6`, `docs/DataContract.md:61-64`, `docs/UtilsAudit.md`, `docs/UtilsDependencyMap.md`.
- `bots/CLAUDE.md` refers to missing docs (`docs/ROADMAP.md`, `REVIEW.md`, `DataFlow.md`, `Gemini/`) and to a May build status.
- `docs/rework/05` §3 said worker event assignment is timing-dependent. Wrong: `Parallelism:balanceLoad` is on by default (fixed in this revision).

## 5. What gets carried over

The function-level and snippet-level table is in [00b_PortingMap.md](00b_PortingMap.md). In summary:
- **Ported as code:** Sha256 (+ FIPS vectors), Signals, clocks, Paths, `Monitor/Timer`, the Physics tables and kinematics.
- **Ported as ideas:**
  - the deadline and coalescing heartbeat;
  - the stall predicates;
  - the Meta provenance fields;
  - tmp + rename writes;
  - per-worker clone and merge;
  - the bounded queue;
  - the migration tables;
  - the house plot style.
- **Python:** all of `rivpyth_common.py` moves function by function into `hekit`.
