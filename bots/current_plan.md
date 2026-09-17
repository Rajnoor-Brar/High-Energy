# Current plan — P0-S00 rework docs revision

> Mirror of the approved plan (per bots/BOT.md). Source: `~/.claude/plans/eventual-mapping-nest.md`, approved 2026-09-17.
> Executing step: **P0-S00 `rework-docs-revision`** (docs only) — **done 2026-09-17**. Step index: `docs/rework/steps/README.md`.
> Next ready step: **P0-S01 `baseline-tag`** (needs user approval for commits/tags). Mirror each step here when it starts.


## Context

`docs/rework/` (README + 00–10, 2026-09-17) is the from-scratch design for `utils/` and the `~/HEP` tools. Since it was written, several things have changed.

**Decisions taken in discussion:**
- HepMC3 is the event store and replay layer. It replaces Probe.
- YODA is the only numerical-results format, including histograms booked by modules.
- ROOT is a processing layer only: fits, statistics, RDataFrame on Delphes output. Delphes' own ROOT output is the one exception.
- Tools are grouped into roles: core, capability, external, post-processing.
- The namespace map.

**Answered this session:**
- **Namespaces:** house style from `bots/BOT.md`. PascalCase top-level namespaces, a `Foo.hh` facade plus `Foo/` submodules, no nesting.
- **Derived tables:** deferred.
- **Lambda:** archived frozen, not ported.
- **Step files:** one per step.
- **Old tools:** hotfix now, port later.
- **PhotoProduction:** treated as a test bed. Physics, maths and logic must be right; don't be pedantic about specifics.

**Facts verified this session:**
| Fact | Where |
|---|---|
| HepMC3 gz read/write works with `-DHEPMC3_USE_COMPRESSION -DHEPMC3_Z_SUPPORT -lz`; zstd/lzma headers present | tested |
| `PythiaParallel::foreach` exists; `run()` returns per-thread counts | Pythia headers |
| `Parallelism:seeds` exists | `Parallelism.xml:155` |
| `balanceLoad` is on by default, so seed + thread count fixes the event set. 05 §3's claim of "timing-dependent" is **wrong** | `Parallelism.xml:203` |
| Delphes declares a global `class Event` | `DelphesClasses.h:46` |
| X11 defines `#define Status int` | `Xlib.h:83` |
| `archive/` and `results/` are gitignored; `legacy/` would be tracked | `.gitignore` |

**Already applied:** the split into `beams` (PDG ids) and `energies`, in docs 03/04/06/09.

**`docs/plans/` (2026-09-16):** mostly superseded. Its Phase 0 items 0.1, 0.3, 0.4 and 0.7 are still open and move into P0.

**Scope of the implement run: docs only.**
- Revise `docs/rework/` and write `docs/rework/steps/`.
- Add a supersession banner to `docs/plans/README.md`.
- Mirror the plan to `bots/current_plan.md` (per `BOT.md`).
- Update memory.
- No code, config or `~/HEP` edits.
- This run is itself step **P0-S00**.

---

## Audit summary (feeds the 00_Audit refresh and 00b_PortingMap)

### `utils/` (58 headers)

**Stale audit claims.** `docs/UtilsAudit.md` lists as open items that are already fixed: the `traitsOf` bounds check, the `writeTextFile` stream check, the scoped `fs` alias, and the `Time.hh` → Config include. `UtilsDependencyMap.md` is also stale.

**New defects (recorded in the legacy README):**
- Record checkpoints hold empty histograms: only the masters are written, and they are merged only at finalize.
- Final histograms are probably unscaled: `Write(kOverwrite)` runs after the scaled snapshot (unverified).
- The Monitor bar interval is computed before nEvents is known.
- Section thread counts wrap on negative values.
- `readFile`/`init` return values are unchecked.
- `sum_weights` is a placeholder.
- Probe:
  - float-only arrays;
  - column types that depend on the reader;
  - two array specs on one tree can read stale data (unverified);
  - quadratic I/O in IMT.
- Paint overlay legends may be destroyed before saving (unverified).

**Tests:**
- `tests/run_all.sh` finds 0 tests and exits 0.
- `test_utils_hardening` is broken (`Lambda_Limits.toml` moved).
- No header dependency tracking.

**Include cycles:** Config ↔ Probe and Record ↔ Monitor.

**What to carry over** (cite in step files, as `legacy/…` paths after P0-S06):
- `Utility/Sha256.hh` plus its FIPS test vectors (`tests/test_utils_hardening.cc:~129-153`)
- `Utility/Signals.hh:22-57` (move to `sigaction`), plus the cooperative-skip pattern in `sources/Lambda/_Lambda_Data.cc:43-50`
- `Utility/Time.hh:15-21`, `Utility/Paths.hh:25-54`, `Utility/Toml.hh:75-92` (ideas only)
- `Physics/Particles.hh:24-58`, `Physics/Types.hh:51-113`, `Physics/Kinematics.hh:24-41`
- `Monitor/Timer.hh`; the deadline and coalescing logic in `Monitor/Threading.hh:121-136,212-213,256-265`; the stall predicates at `:97-116`
- `Record/Meta.hh:25-110,243-299` (provenance fields), `Record/Recording.hh:204-231` (write to tmp, then rename), `Record/Cloning.hh:31-47,82-86` (clone and merge), `Record/Type_Methods.hh:11-27`
- `Probe/Lifecycle.hh:229-267` (bounded queue)
- The migration tables in `Config/Reader.hh:79-102` and `Monitor/Configure.hh:20-60`
- The house plot style: `configs/defaults/Paint.toml` and `root_macros/saveHist.C`

**Probe access patterns the HepMC module API should keep:**
- labelled collections;
- aligned typed per-particle columns;
- per-event scalars (weights, attributes);
- coordinate conversions;
- `(event, worker)` callbacks;
- callback on the reader thread or on a collector pool;
- the event-count resolution order;
- first error stops everything, joins, then rethrows.

**Verdicts:**
| Namespace | Verdict |
|---|---|
| Utility | port Sha256/Signals/Time; take ideas from Paths/Toml |
| Physics | port → `Phys` |
| Config | ideas only → Python |
| Monitor | ideas → `Status` and the supervisor; port `Timer` |
| Probe | drop, keep the access ideas |
| Record | ideas → `Results` (YODA shards) and `Run`; port the Meta fields |
| Paint | drop; the style becomes an mplhep style file |

### Lambda (archived)

**Physics:** Ne–Ne Angantyr at 7 TeV/nucleon, Λ→pπ⁻ only. It pairs particles, applies a mass window, then does a greedy unique selection capped at `Np − reserved_protons`. There are 21 histograms in 3 sets. The physics is about 100 lines and needs only isFinal/pid/momentum, so it would work on GenEvent.

**Health:** every driver aborts at configure: `hist_limits` resolves to the missing `configs/Lambda_Limits.toml`, and the card and driver paths are stale. A syntax-only compile passes.

**Physics bugs, for the archive README:**
- The `.cmnd` redefines ²⁰Ne with m0 = 0 and the wrong charge.
- The angle cut is dead (cos θ ≡ −1).
- `reserved_protons` doesn't match Angantyr's `NucRem`.
- `SigFitNGen` is set twice.
- The writer can emit rows out of `event_index` order.
- Histograms are scaled ×100 by default.
- `Momentum_Z` limits start at 0.

**Port notes, for a future revival:** module mapping, histogram list, fit caveats (at generator level the peak is a spike, so smearing or truth matching is needed), about 1.5–4 d.

**Stale docs:** `docs/MAP.md`, `docs/Architecture.md`, `docs/DataContract.md`, `bots/CLAUDE.md`.

### PhotoProduction + `~/HEP`

**`rivpyth_common.py`** (1147 lines, no dead code):
- The function-level porting table from the audit goes into `00b_PortingMap.md` verbatim, mapping every name to its `hekit` package.
- **Leftovers:** PDF shims, `path_literal`/`hepmc_file`/`serial`/`run_filename`, and the flat `style` key.
- **Duplicated three times:** env prepend, argparse block, `EXAMPLE`.

**Bugs** (in `00_Audit` they get new IDs `00/Bn`, because `docs/plans` already uses B1/B2):
| ID | Problem |
|---|---|
| B1 | Seeds follow a point's position, not its identity (`rivpyth_common.py:679-686`) |
| B2 | Thread RNG streams overlap: thread seeds are `seed+i` and points step by 1, so neighbours share 19 of 20 streams |
| B3 | A killed or failed run leaves a partial YODA at the final path, and it gets skipped later |
| B4 | The 27x920 label says √s = 95.6; the correct value is 318.1 |
| B5 | ZEUS data is overlaid on observables that only share the histogram name |
| B6 | `--overlay` without `--across` breaks coupling |
| B7 | Validation runs before the study is applied |
| B9 | `:g` formatting loses precision |
| B10 | Stale comments in `eic.toml` |
| B11 | Everything runs e⁺ — **no action** (test bed) |
| B12 | Misleading PDF tags — renamed only in the v2 migration |
| B13 | Contradictory ProcessType notes |
| B14 | ZEUS config declares options the analysis doesn't have |
| B15 | Physics-identical points get distinct names |
| B17 | Merged YODAs share the point namespace |
| B18 | Paths are relative to the CWD |
| B19 | Fixed `/tmp` paths |
| B20 | `supervise` masks rivet's error |
| B21 | The generator exits 0 on HepMC write failure |
| B22 | Numeric pins are impossible |
| B23 | Stale `photo_ep.cmnd` comments |
| B24 | Debris: stale FIFOs, pycache |
| B25 | SISCone leak |
| B26 | η range inverted when `orientation = −1` |
| B27 | pTHatMin bias — **record only** |
| B28 | `README_ZEUS` obsolete |

**Other findings:**
- **`photo_eic`:** its `finalize` is already re-entrant-safe, so the analysis can flip to `Reentrant: true` after a `rivet-merge -e` check. This is also needed so periodic dumps get finalized (`AnalysisHandler.cc:700-705`).
- **`generator.cc` behaviours `hep-run` must keep:**
  1. Cards are read in order; later values win; a card error exits 1.
  2. Quiet by default, but a card can re-enable output.
  3. The runner owns `processAsync`.
  4. The spec's run control beats the cards.
  5. No output is opened before `init`.
  6. HepMC3 output goes through `Pythia8ToHepMC`.
  7. Exit codes: 2 = usage, 1 = card or init failure.
- **Golden fixture: `eic` study expansion.** Assert point sets and pages, not names or seeds.
  | Study | Points | Pages |
  |---|---|---|
  | single | 1 | — |
  | pdf | 4 | — |
  | energies | 4 | — |
  | energy_pdf | 16 | 4 |
  | mpi | 3 | — |
  | mpi_onoff | 2 | — |
  | mpi_grid | 6 | 2 |
  | pthatmin | 4 | — |
  | process | 2 | — |
  | radius | 3 (`R=1`) | — |

  `zeus_validation` has never been run.
- **`results/PhotoProduction`:** legacy series 01–04 with serial drift, hand-reconstructed 01 cmnds, `/tmp` paths in `index.html`, old `/photo_5x41` YODAs. `output/` holds stale FIFOs and old `.so` files.
- **`setup.sh`:**
  - `PYTHONPATH` lacks `root/lib` and `pythia8/lib`;
  - `RIVET_ANALYSIS_PATH` is hard-coded and has empty entries;
  - `hep_refresh` duplicates paths;
  - `hep_status` runs on every source;
  - `quit` unsets itself;
  - empty path elements mean the CWD.
- **Makefile:**
  - `:=` evaluates `*-config` eagerly;
  - every target links every library;
  - no header dependencies (`-MF` without `-MMD` was already inert);
  - `run_all.sh` passes vacuously;
  - the `.so` rule hides errors;
  - `clean` deletes the plugins.

---

## Deliverables of the implement run

### A. New rework docs
| File | Content |
|---|---|
| `00b_PortingMap.md` | The function-level map: `rivpyth_common` / `rivpyth` / `ydplt` / `ydmrg` / `generator.cc` → `hekit` packages and the C++ namespaces; the legacy `utils` snippets → target steps |
| `11_EventStore.md` | Sharded layout `events/events.<k>.hepmc.{gz,zst}`, JSON schema for `events.index.json` (version, shards with events/bytes/sha256, totals, merged σ±err, weight names, beams, seeds, threads, provenance hash, stopped), write and replay flow (one reader per shard → bounded queue → consumers), performance notes, `tool = "store"`, CLI |
| `12_Processing.md` | ROOT's role; `hep proc`; `[[proc.fit]]` and `[[proc.hist]]`; outputs (`fits.json`, curves as YODA under `/PROC/…`, optional `.root`); backends (Minuit2/RooFit via PyROOT, scipy fallback); Delphes RDataFrame recipe |
| `13_Namespaces.md` | The C++ facade namespaces `Core, Status, Events, Source, Store, Results, Sink, Module, ML, Phys, Run`; clash notes (`Events` rename, the X11 `Status` guard, no namespace-scope `using namespace Pythia8/Rivet/HepMC3/fastjet`); dependency layers; the Python package list (+ `store`, `results`, `proc`); old → new mapping |

### B. Revisions to the existing rework docs
| File | Changes |
|---|---|
| `README.md` | New TL;DR (store / YODA-only / ROOT processing / house namespaces / Lambda archived / hotfix-then-port); parts table (+00b, 11–13, `steps/`); findings (+B2, B3; compression verified) |
| `00_Audit.md` | §4 "current workflow defects" with `00/Bn` IDs (above) plus the setup/Makefile/utils/Lambda findings; revised verdicts; reuse list; stale-doc list |
| `01_Requirements.md` | R10: modules book YODA, derived tables deferred. R12: store + replay = Should. New R15: ROOT processing. Constraints: HepMC compression flags, `balanceLoad`, `Parallelism:seeds`. New principle: the test-bed rule. |
| `02_Architecture.md` | Diagram (`Store`/`Results`/`Module`, no NtupleSink, `hep proc`); a `store` chain; contracts (`events/` + index, combined `analysis.yoda`, `fits.json`); layout (`utils/<NS>.hh` + `utils/<NS>/`, `utils/apps/`, `utils/python/hekit/`, `analyses/`, `modules/`, tracked `legacy/`, `env/hep_env.sh`); §6 → pointer to 13; new §8 tool roles (ROOT = processing; `hep-run` doesn't link ROOT by default) |
| `03_Configuration.md` | Remove `[sinks.ntuple]`. Replace `[sinks.hepmc]` with `[store]`. Add `tool = "store"` + `input`, `[[sinks.module]]`, `[[proc.*]]`, `[plot.data].map`. Identity seed policy (replaces `seed_step`; `Parallelism:seeds` blocks). Hash contents. Update the resolved-spec example. Note for the `.v2` transition. |
| `04_Generators.md` | A "store" pseudo-adapter row; Herwig gate → P7-S06; Q7 decision pointer; "ntuple" → modules |
| `05_EventPipeline.md` | Rename namespaces; fix the reproducibility note (`balanceLoad`) and use `Parallelism:index`/`seeds`; replace NtupleSink with Module + Results (YODA) and describe the combined write and the rivet-merge caveat (hekit merges module objects); Store section pointer; ML training data deferred; partial naming `analysis.partial.yoda`; size table |
| `06_Terminal.md` | `Status::` naming; store outputs in `summary`; `hep events --from` a store |
| `07_Outputs.md` | Layout (`events/`, `analysis.partial.yoda`, `fits.json`, `proc.yoda`, no `ntuple.root`); store hash in provenance; module-object merge rule; replace "Ntuple histograms" with a `hep proc` section; retention; placeholders for the Q3/Q4 outcomes |
| `08_CLI.md` | Add `hep proc`, `hep store ls/verify`, `hep events --from`, `hep new module`; tools move-then-retire path; `setup.sh` becomes a stub plus the versioned `env/hep_env.sh` |
| `09_Build_Test.md` | Components (no NTUPLE; HepMC compression; ROOT only via Delphes); Python map; tests (legacy golden fixtures, store round trip, module merge, proc fits, pytest guard, scratch rules) |
| `10_Roadmap.md` | Rewritten: §0 guiding rules, phases, step index link, decision log, risks, open questions. Decision log: D7 and D8 revised; new D13 house namespaces, D14 Lambda archived, D15 derived tables deferred, D16 identity seeds, D17 partial-output naming, D18 tools moved before the port, D19 hotfix-then-port, D20 test-bed rule. New risks: rivet-merge with module objects; Delphes `Event` clash; gz throughput; PyROOT availability; seeds vs chunked run. Q5/Q8/Q9(gz) answered; zstd pending. |

### C. Other docs
- `docs/plans/README.md`: supersession banner plus an item → step map.
- `bots/current_plan.md`: mirror of this plan.
- Memory: rework status.

### D. `docs/rework/steps/`
- `README.md`, structured as described below.
- 55 step files.

---

## Guiding rules (→ `10_Roadmap.md` §0 and `steps/README.md`)
- **Replacement before removal.** Nothing is removed before its replacement passes. The old tools stay in use, versioned and hotfixed, until the golden comparisons pass.
- **Working state.** Every phase ends working.
- **Test bed.** Physics, maths and logic must be correct; details are not blockers.
- **Scratch only.**
  - Tests never write to `results/` or `configs/`. Use the scratch root `output/scratch/` and `HEKIT_RESULTS`; a pytest guard enforces this from P1.
  - Legacy tools run from `output/scratch/legacy/`, with symlinks to `configs`, `output` and `datasets` and a real `results/`.
- **Approval.** Commits, tags and moves of `results/` only with user approval.
- **Citations.** Finding IDs are cited as `00/Bn` or `plans/Bn`.

---

## Phases and steps

**Kinds:** code · test · env · git · docs · decision.

**Effort:** about 37 d in total. The critical path P0→P4 (replacing today's workflow) is about 19 d. P5–P9 follow need.

```
P0 ─► P1 ─► P2 ─► P3 ─┬─► P4 ─┬──────────────► P10
                      │       ├─► P9 ◄┄ P7-S08
                      ├─► P5 ─┴─► P6 ─► P8
                      └─► P7 (needs P5-S02)
```

### P0 · Baseline, hygiene, legacy freeze (2.5 d)
**Exit:** clean tree plus tags; `setup.sh` idempotent and imports OK; `rivpyth` runs from the repo; hotfix tests pass in scratch; golden fixtures stored; PhotoProduction make targets build.

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S00 | `rework-docs-revision` | docs | This implement run | Stale-term grep; link check; index ↔ files |
| S01 | `baseline-tag` | git | Commit the in-flight work (configs rewrite, `generator.cc`, `photo_eic`, docs) in logical commits; tags `rework/baseline`, `legacy/lambda-final`; tarball of the `~/HEP` tools with sha256. **Needs user approval.** | `git status` clean; tags listed |
| S02 | `env-setup-fixes` | env | Versioned `env/hep_env.sh` + `~/HEP/setup.sh` stub; `PYTHONPATH` gets `root/lib` and `pythia8/lib`; drop the hard-coded `RIVET_ANALYSIS_PATH`; idempotent prepend; on-demand status; fixed `quit`; `pip install rich tomli_w pytest` (plans 0.7) | Source twice + refresh twice → 0 duplicate entries; `import ROOT, pythia8, yoda, rivet, lhapdf, rich, tomli_w, pytest` |
| S03 | `tools-into-repo` | code | Copy the tools verbatim into `tools/` (commit 1); `EXAMPLE` reads the example file, pycache and stale FIFOs removed, `PATH` updated, `~/HEP` copies renamed `*.moved` (commit 2) (plans 0.1, B24) | `which rivpyth` → `tools/`; `rivpyth -p` output equals the snapshot for every study |
| S04 | `golden-fixtures` | test | `tests/golden/capture_legacy.py` → plan JSONs for every study of both configs; a mini legacy run in scratch (2 points × 5k, 1 thread) → YODAs + plot intermediates; read-only inventory of `results/PhotoProduction` (sha, `_EVTCOUNT`, partial flags); `test_legacy_counts.py` | Stamp file: `find results configs -newer` = 0; `pytest tests/golden` |
| S05 | `legacy-hotfixes` | code | **B3**: `.part` + `_EVTCOUNT` check + rename. **B20**: first real error. **B21**: generator non-zero exit. **B2**: `seed_step ≥ threads` guard (configs `seed_step = 20`). **B4, B5** (`use_data = false`), **B10, B13, B23**. Record B27/B12; B11 no action. Re-capture fixtures + `EXPECTED_DELTAS.md`. | Kill test → no final YODA, rerun regenerates; bad analysis → rivet's message; unwritable output → non-zero; guard raises; `pytest tests/golden` |
| S06 | `legacy-archive` | git+docs | `git mv` to tracked `legacy/`: Lambda (modules, sources, configs), all `tests/`, old `utils/*`, `_Paint.cc`, `_ThreadBench.cc`, `root_macros/`, `configs/{defaults,templates,all.toml,Paint.toml}`, old `photo_*` plugins, `README_ZEUS.txt`, stale docs (MAP, Architecture, DataContract, UtilsAudit, UtilsDependencyMap, Audit, `plans/`). Write `legacy/README.md` (tags, Lambda and utils bugs, port notes) and `legacy/PORTING.md`. Propose `bots/` edits (applied only after approval). | `git grep` for old includes outside `legacy/` is empty; PhotoProduction targets build; `git log --follow` keeps history; mini run still passes |
| S07 | `makefile-hygiene` | code | Recursive `=`; per-target libraries (generator: Pythia + HepMC3; plugins: `rivet-build`); drop ONNX/Delphes/ROOT/toml++; `.so` rule errors visible; `make test` → pointer (plans 0.3, reduced) | `make -n … \| grep -c onnx` = 0; builds without `ONNXRUNTIME_DIR` |

### P1 · Python core (4.5 d)
**Exit:** `hep plan --json` matches the legacy fixtures, except for the changes listed in `EXPECTED_DELTAS.md`; pytest runs in under 5 s; `hep doctor` works.

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `package-skeleton` | code | `utils/python/pyproject.toml` (`hep` entry point, deps, extras `plot`/`ml`/`proc`); `cli`, `errors`, `env/paths` (`HEKIT_ROOT`, `HEKIT_RESULTS`); `tests/python/conftest.py` guard (B18) | `cd / && hep --version`; a planted write is caught |
| S02 | `config-schema` | code | Schema-2 dataclasses with doc metadata; unknown keys are errors with did-you-mean; layering, machine file, origin tracking; `[beams] ids/energies`; `[generator] tool = "store"`; `[rivet]`, `[store]`, `[[sinks.module]]`, `[output]`, `[plot]`, `[plot.data].map`, `[terminal]`, `[[proc.*]]` | pytest: did-you-mean, ranges (no wrap), `extends` cycle, allow-list, origin |
| S03 | `sweep-engine` | code | Port quantities, `across`, settle, studies, pins, overlay, naming. Fixes: B6, B7, B9 (lossless values), B22 (precedence decided in the step). | One test per bug (reproduces first); golden sweep test |
| S04 | `identity-seeds-hash` | code | Canonical hash of the effective settings; identity seeds with per-thread disjoint `Parallelism:seeds` blocks; replica index; collision check; equal-hash aliases → one group; skip = name + hash + complete output; test-only `seed_policy = "legacy"` (B1, B2, B15) | Property tests: same seed across studies; disjoint blocks; order-independent |
| S05 | `plan-render` | code | `hep plan` / `hep studies`: points → groups → stage chains → spec-v2 `run.toml` + `point.cmnd` (in tmp); Pythia adapter (header, ids/energies, rejects `Beams:*` / `processAsync` in cards, √s warning); Rivet options validated against `.info` (B14); `plan/spec_v2.json` shared contract | `energy_pdf` → 16 points, 4 pages; golden `point.cmnd` equal apart from seeds |
| S06 | `config-migrate` | code+config | `hep config migrate/reference/init/validate`; v1 → v2 map; commit `eic.v2.toml` and `zeus_validation.v2.toml` next to the originals (B12 renames + alias map, B14 cleanup, explicit data map); generated reference at `docs/rework/reference/config.md` | migrate \| validate; migrated plan equals the in-memory plan; deterministic reference |
| S07 | `doctor-pdf` | code | `hep doctor [--json/--brief]` (versions cached, imports, ThePEG modules, HepMC compression, `hep-run --capabilities`, env sanity); `hep pdf check/list/install`; `hep_status` becomes an alias | herwig = `run-only`; `pdf check` → 4 sets installed |

### P2 · C++ core, CMake, `hep-run` v1 (4.5 d)
**Exit:** full and minimal builds pass; the `slow` equivalence test against the legacy FIFO passes; Q1 and Q2 are decided.

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `cmake-skeleton` | code | CMake + `cmake/Find*.cmake` (via `*-config`); AUTO `HEKIT_WITH_{RIVET,HEPMC,ONNX,DELPHES}`; HepMC compression defines; one interface library per facade; `git mv` `photo_eic` → `analyses/PhotoProduction/` + `rivet_<project>` targets (legacy make also searches `analyses/`); ctest + pytest registration; compile DB | Full and minimal builds; plugin + `.info` in `build/`; `make …photo_eic.so` still works |
| S02 | `pythia-parallel-spike` | decision | Q2: k × `run(chunk)` vs `run(N)`. Q1: σ-error combination via `foreach` vs `stat()`. Check `Parallelism:seeds` readback. Records D-Q1, D-Q2, D-SEEDS; fallbacks documented. | Result table in the step file |
| S03 | `core-status` | code | `Core/{Types,Spec,Errors,Signals,Clock,Sha256,Paths}`; `Status/{Types,Writer,Heartbeat,Plain}` (fd 3, rate limiting, deadline loop, stderr fallback, `#ifdef Status` guard); Python status reader | ctest: `core_spec`, `core_sha256` (FIPS), `core_signals`, `status_roundtrip` |
| S04 | `source-run-loop` | code | `Source::Pythia` (checked `readFile` → exit 1; `init` → exit 3; chunked or single run per D-Q2; `Parallelism:index`; logger counts); `Events::View` (lazy HepMC); `Sink` interface; `Run::loop`; `hep-run SPEC [--check/--plain/--capabilities/--list N]` | `--check` good → 0; ProcessType 2 → 3; bad key → 1; SIGINT → 6 |
| S05 | `rivet-sink-results-writer` | code | Serial `Sink::Rivet` (options, check_beams, weights, merged σ, finalize, `getYodaAOs`); `Results/Writer` (tmp + rename; `analysis.partial.yoda`; `analysis.dump.yoda` only for re-entrant analyses; summary) (B3, B21) | Missing analysis → 1 before generation; `/_XSEC` = σ×1e9 pb; SIGINT → partial file only |
| S06 | `equivalence-gate` | test | `tests/integration/test_hep_run_vs_legacy.py` (`slow`): same card, 1 thread, fixed seed, 20k events; in-process vs `generator.exe` → FIFO → `rivet`; `tests/tools/yodacmp.py` | `ctest -L slow`; table in the step file |

### P3 · Supervision, results, terminal (3.4 d)
**Exit:** e2e mini run in scratch; Ctrl-C → partial result + exit 6; fake-stage tests pass; `hep watch` works.

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `decide-serial-and-legacy-results` | decision | Q3: drop the serial prefix; use study directories and manifests plus an optional `run.label`. Q4: no import; move `results/PhotoProduction/*` → `results/PhotoProduction/legacy/` (with approval); `[plot].extra` for overlays. | Sign-off; file count matches the inventory |
| S02 | `supervisor` | code | `hekit.run`: stages as data; `pass_fds`; per-stage logs; per-run FIFO directory; poll all stages; SIGINT → SIGTERM → SIGKILL; first-failure attribution; stall detection (B19, B20) | Fake stages: early exit, hang → 7, stderr flood, SIGINT ignored, reader dies → 4, cleanup |
| S03 | `results-provenance` | code | `hekit.results` (group directories, manifests, skip rule, partial outputs, orphans); `hekit.prov` (git, versions, card hashes, resources, run summary, YODA annotations) (B3, B18) | Same name + different hash → error; partial → rerun; annotations read back; runs from `/` |
| S04 | `terminal` | code | `hekit.term`: rich Live dashboard, plain mode, curated log pane; `hep watch/runs/show`; progress interval computed after totals are known | `Console(record=True)` snapshots; pipe → plain; pty test restores the terminal |
| S05 | `hep-run-command` | code+test | `hep run` (`--check`, `--rerun`, `--detach`, `--events`, `--threads`, `--set`) | e2e mini; 4-point PDF study; Ctrl-C behaviour; rerun skips done points; `--check` stops ProcessType 2 |

### P4 · Plotting, compare, retirement (4.25 d)
**Exit:** golden page comparisons pass; a real-study cross-check passes; tools moved to `legacy/`; v2 configs are canonical; Makefile wraps CMake.

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `plot-pipeline` | code | `hekit.plot.{io,select,transform,data,plotfile}`; unique curve namespaces (B17); data only via an explicit map or identical path (B5); per-run `MPLCONFIGDIR` (B19); variant selection by option path | Fixture tests; equal to the legacy functions |
| S02 | `plot-mkhtml` | code | `hep plot` (pages / `--points`) with the mkhtml backend | Page set, legends, overrides and remapped data equal ydmrg/ydplt (mini run + 2 legacy studies in scratch) |
| S03 | `plot-mpl-style` | code | `.plot` parser → mplhep; house style `hekit.mplstyle` | Parser tests; image smoke test; visual check |
| S04 | `compare` | code | `hep compare`: χ²/ndf, bins used, max pull; rich table + `compare.md`; absorbs `yodacmp` | Synthetic known-χ² fixtures |
| S05 | `photo-eic-reentrant` | code | SISCone ownership (B25); orientation-safe η (B26); `Reentrant: true`; `Beams:` in `.info` | `rivet-merge` 2×20k ≈ 40k; ASan clean; proton-as-beam-B works |
| S06 | `retire-legacy-tools` | git+code | Gate: `pdf` study at 100k compatible between old and new. Then `tools/` → `legacy/tools/`; `eic.v2` → `eic.toml`; `generator.cc` → `legacy/`; Makefile becomes a thin CMake wrapper; env drops `tools/`; `~/HEP/*.moved` removed | `which rivpyth` fails; `git grep rivpyth` outside legacy/docs empty; `make && make test`; `hep plan/run/plot` e2e |

### P5 · Event store and replay (2.5 d)
**Exit:** write → replay reproduces the in-process YODA; σ comes from the index; one reader per shard.

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `store-writer` | code | Spike first: gz vs zstd → D-STORE-COMP. Then the `Store` namespace (per-worker shards, atomic index), `Sink::Store`, `[store]`, `hekit.store`, `hep store ls/verify` | Counts sum up; `verify` catches truncation; build without zstd |
| S02 | `store-source-replay` | code | `Source::Store` and `Source::HepMC` (file/FIFO/list) share one reader: thread per shard → bounded queue → consumer; σ/beams/weights from the index; planner `tool = "store"` (`input` = name/hash/path; replay hash = store hash + analysis) | `ctest store_replay`; beam-changing quantities rejected; SIGINT → 6 |
| S03 | `replay-equivalence-events` | test+code | In-process + store → replay gives an identical YODA and σ; `hep events CONFIG/POINT/STORE -n N [--tree/--final/--hard]` | `ctest -L slow -R replay` |

### P6 · Throughput (2 d)

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `sharded-rivet` | code | Per-worker handlers (locked until first event), `processAsync = on`, merge → σ → finalize; `auto` only when all analyses are re-entrant and threads > 1; sharded replay consumers | 50k serial ≈ sharded; sumW and σ equal; non-re-entrant → serial with notice |
| S02 | `event-groups` | code | Analysis-only variants share one generation; replay can join a group | `radius` → 1 group with 3 variants; `R=0.4` objects present; 3 curves |
| S03 | `bench` | code | `hep bench`: generation only, with sinks, replay with k readers → recommendation | < 2 min; logic unit-tested |

### P7 · External generators and Delphes (7 d)

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `adapter-framework` | code | Adapter protocol and stages; prepare cache; FIFO wiring; parser registry; `generator` quantity; event-count check; beam-key clash rules | A fake external generator replaying a store runs through `hep run`; the cache is hit |
| S02 | `decide-photoproduction-equivalence` | decision | Q7: what counts as the same physics per generator (EPA/WW, Q²max, photon PDF, pTHatMin analogue, MPI) → `photo_ep.sherpa.yaml`, `photo_ep.sin` | Low-statistics 18x275 comparison, documented |
| S03 | `sherpa` | code | YAML merge; integration prepare stage; HepMC3 to the FIFO; native mode; progress parser; golden cards | 10k point with dashboard; 2-seed study prepares once; native ≈ in-process |
| S04 | `whizard` | code | Insertion rule; PDG → model names; `beams_momentum`/`sqrts`; `<stem>.hepmc` FIFO; parton-level flag | e⁺e⁻ → jj toy |
| S05 | `madgraph` | code | Process-directory cache; launch script; `lpp`/`ebeam`; LHE → Pythia shower | 1k toy LHE; cache reuse |
| S06 | `decide-herwig-rebuild` | decision+env | Q6: rebuild ThePEG `--with-hepmc --with-rivet` + Herwig now, later or never; record the commands | Doctor detects the modules |
| S07 | `herwig` | code | `read` and `run` stages; `-j N` → N FIFOs → multi-input source; particle names; golden cards (gated on S06) | Toy run |
| S08 | `delphes-external` | code | HepMC tee → supervised `DelphesHepMC3`; `[delphes]` card, external mode only; provenance sidecar | uproot reads `delphes.root`; failures → exit 4/5 |

### P8 · Modules, YODA results, Phys, ML (3 d)

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `module-sink-yoda` | code | `Module` (`configure` / `book` / `process` / `finalize`); `HEKIT_MODULE` + dlopen from `[[sinks.module]]`; `Results` per-worker clone and merge; combined write into `analysis.yoda` under `/<module>[:opts]/`; scaling contract; hekit merges module objects for replicas; `hep new module` | Exact totals at 1/4/20 threads; scaled integral correct; dumps not empty; plots show module histograms |
| S02 | `phys` | code | `Phys`: PDG traits, kinematics, `jetDefinition("antikt:0.4")` (port from `legacy/utils/Physics`) | Matches Pythia `ParticleData` / FastJet |
| S03 | `onnx` | code | `ML::OnnxModel` (shared session, per-worker scratch, shape checks, sha256); `HEKIT_WITH_ONNX`; `Requires: ONNX` → `rivet-build` flags | 20 workers give the same output as Python onnxruntime; build with ONNX off passes |
| S04 | `decide-derived-tables` | decision | Deferred. Options: Parquet via Python replay / C++ Arrow / RNTuple / YODA only. Trigger: first ML training dataset. | Recorded |

### P9 · ROOT processing layer (2.5 d)

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `proc-fits` | code | `hekit.proc`, `hep proc`, `[[proc.fit]]` (target, model, range, init, backend `auto/minuit2/roofit/scipy`); outputs `fits.json`, `/PROC/` YODA curves, optional `.root` | Parameter recovery; backends agree to 1e-3; scipy fallback without PyROOT; overlay plots |
| S02 | `proc-rdf-delphes` | code | `[[proc.hist]]` via RDataFrame, with uproot + hist fallback → `proc.yoda` | RDF = uproot bins on `delphes.root` |

### P10 · Cleanup, docs, release (1.25 d)

| ID | Slug | Kind | Goal | Key checks |
|---|---|---|---|---|
| S01 | `cleanup-housekeeping` | code | Remove shims (the v1 reader survives only inside `migrate`); drop `.v2` names; `hep clean`; `hep new analysis/project` | `git grep` for `rivpyth/ydmrg/NtupleSink/RNTuple` outside legacy is empty |
| S02 | `docs-final` | docs | User guide, config reference, new `docs/MAP.md`; rework docs marked "Implemented"; `bots/` updates (after approval); close the index | Link check; documented commands exist in `hep --help` |
| S03 | `portability-release` | test | All-off build; `hep doctor` degrades cleanly; Mac notes; size report; tag `rework/v1` | — |

**Count:** 55 steps. Decision-only: P2-S02, P3-S01, P7-S02, P7-S06, P8-S04. Docs-only: P0-S00, P10-S02.

---

## Step file template (`docs/rework/steps/P<p>-S<nn>_<slug>.md`)

**Header table:**
| Field | Value |
|---|---|
| Status | todo · in-progress · blocked · done · dropped |
| Kind | |
| Phase | |
| Depends on | |
| Blocks | |
| Effort | |
| Findings / decisions | |
| Updated | |

**Sections:**
1. **Goal**
2. **Context:** links to rework doc sections and audit IDs.
3. **Inputs to reuse:** a table of path:lines or `tag:path`, what to take, and how (copy or adapt; never include from `legacy/`).
4. **Scope:** in / out.
5. **Design notes.** Decision steps use a **Decision record** instead: question, options, criteria, evidence, decision, consequences, docs to update.
6. **Tasks** (checkboxes)
7. **Outputs**
8. **Verification:** check / command / expected, plus a test-safety line.
9. **Rollback**
10. **Done when**
11. **Log**

## `steps/README.md` structure
1. Conventions: IDs, status and kind values, readiness rule, working-state rule, approval rule, citation scheme.
2. How to execute a step: read it → mirror to `bots/current_plan.md` → do it → run the checks → set status → update the index.
3. Test-safety rules.
4. Phase table (goal, exit, steps, status).
5. Step index (ID, linked title, kind, depends on, effort, status).
6. Mermaid dependency graph, one subgraph per phase, built from the "Depends on" fields, plus the ASCII phase line.
7. **Decision register:** D-Q1, D-Q2, D-SEEDS, D-Q3, D-Q4, D-Q5 (answered yes in P0-S02), D-Q6, D-Q7, D-STORE-COMP, D-DERIVED (deferred), D-B11 (no action), D-B12 (v2 rename), D-B27 (record).
8. **Traceability matrix:**
   | Finding | Step(s) |
   |---|---|
   | B1, B15 | P1-S04 |
   | B2 | P0-S05, P1-S04, P2-S02 |
   | B3 | P0-S05, P2-S05, P3-S03 |
   | B4, B10, B13, B23 | P0-S05 |
   | B5 | P0-S05, P4-S01 |
   | B6, B7, B9, B22 | P1-S03 |
   | B11, B27 | P0-S05 (record) |
   | B12, B14 | P1-S05/S06 |
   | B17 | P4-S01 |
   | B18 | P1-S01, P3-S03 |
   | B19 | P3-S02, P4-S01 |
   | B20 | P0-S05, P3-S02 |
   | B21 | P0-S05, P2-S05 |
   | B24 | P0-S03 |
   | B25, B26 | P4-S05 |
   | B28 | P0-S06 |
   | setup.sh issues | P0-S02 |
   | Makefile issues | P0-S07, P2-S01, P4-S06 |
   | utils defects | P0-S06 (record), P8-S01, P3-S04, P1-S02, P2-S04 |
   | Lambda bugs | P0-S06 |
   | Stale docs | P0-S06, P10-S02 |
   | plans 0.1 / 0.3 / 0.4 / 0.7 | P0-S03 / P0-S07 / P0-S06 (archived instead) / P0-S02 |
9. Reuse map (legacy source → step), as in `legacy/PORTING.md`.
10. Change log.

---

## Implement-run procedure (docs only)
1. Write `bots/current_plan.md` (a copy of this plan).
2. Write the new docs: `00b_PortingMap.md` (the audit's porting table + utils snippet map), `11_EventStore.md`, `12_Processing.md`, `13_Namespaces.md`.
3. Revise `README` and 00–10 per table B, fixing the wrong 05 §3 reproducibility note.
4. Write `steps/README.md`, then the 55 step files in phase order. Content comes from the tables above plus the audit details in this conversation. P0-S00 is marked done at the end.
5. Add the supersession banner and item → step map to `docs/plans/README.md`.
6. Run the verification below and fix what it reports.
7. Update memory: rework status, decisions and step-file location.

## Verification (of the implement run)
- **Stale terms:** `grep -rnE 'NtupleSink|RNTuple|ntuple\.root|hekit::|sink::|timing-dependent' docs/rework` → hits only in "removed / was" context.
- **Links:** a scratchpad Python script resolves every relative markdown link under `docs/rework/`.
- **Step files:** a scratchpad script checks that all 55 files exist and match the index; every file has all template sections; every "Depends on" ID exists; the graph is acyclic; the mermaid edges equal the "Depends on" fields.
- **Traceability:** every `00/Bn` and every audit finding named in `00_Audit` appears in the matrix, as a step or as a record/no-action entry.
- **Scope:** `git status --porcelain` shows changes only under `docs/` and `bots/current_plan.md` (plus the memory directory outside the repo).
