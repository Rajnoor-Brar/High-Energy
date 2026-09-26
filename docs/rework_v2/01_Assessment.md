# 01 — Assessment: how lean, how bloated, and what must not be forgotten

v1 (`rework/v1` plus the two commits after it, `65feb97`), measured against the target in
[00_Brief.md](00_Brief.md) on 2026-09-26. Every number came from a command over the tree; the
commands are in the [appendix](#appendix-reproducing-the-numbers).

**The conclusion drives the whole plan.** v1's code is not worth keeping. Its **knowledge** is:
the quirks of Pythia, Rivet, FastJet, Delphes, Sherpa, Whizard and MadGraph that it found by running
them. So v2 deletes the code (decision V5) and keeps a ledger of the knowledge (§7).

---

## 1. The verdict

| | Lean or bloated? | Fate in v2 |
|---|---|---|
| **C++ physics libraries** (`Phys`, `ML`, `Results` booking) | lean and tested, but **unnecessary**: in a process model a module links HepMC3, FastJet and ROOT directly | deleted (V7); copied back from git only if a module needs them |
| **C++ process basics** (`Core`, `Status`) | lean | deleted; replaced by one ~120-line `Status.hh` |
| **C++ event loop** (`Source`, `Analyzer`, `Run`, `Spec`, `Module` loader, `hep-run.cc`) | correct, and ~3.2k lines of machinery for hosting three things in one process | deleted (V2) |
| **Python orchestrator** (`hekit`) | **bloated**: 11.1k code lines for what the user describes as one command | deleted; a fresh ~2k-line runner |
| **Build** (CMake 377 + `cmake/` 214 + Makefile 100) | bloated and split in two | replaced by one Makefile (V6) |
| **Tests** (33k lines) | 17k of it is golden data; most of the rest tests code that goes | deleted, except the reference data v2 is gated on |
| **Docs** (12.9k lines) | heavy: 15 design documents and 55 step files for a two-project toolkit | `docs/rework/`, `post_rework/`, GUIDE and MAP deleted (V20); `rework_v1/` kept for its lessons |

**Why it is convoluted.** The problem is not any one file: the largest is 701 lines, and the C++
layering holds. It comes from two kinds of indirection:

1. **Orchestration is derived rather than declared.**
   - The stage chain is computed from roles (`plan/build.py:71`).
   - Phases are inferred (`adapters/base.py:104`).
   - A quantity's effect is a nine-way type dispatch (`sweep/expand.py:95`).

   The brief's `tools = [A, [B, C], D]` and per-tool quantity maps say the same things out loud.
   Every inference was code that needed tests.
2. **There are two ways to do most things:**
   - events in process *or* through a FIFO;
   - modules (loaded with `dlopen`) *or* Rivet plugins, with different normalisation conventions in
     one file (`00/B42`);
   - CMake *or* `make X.exe`;
   - YODA as the record *and* ROOT as a derived view.

Behind both is **vocabulary**. v1's glossary has 17 pipeline terms (point, group, generation, study,
page, curve, variant, alias, analyzer, source, module, stage, phase, spec, identity, replica, replay,
store, shard, chunk). v2 has seven: run, configuration, point, quantity, tool, group, page.

---

## 2. Sizes

| Part | Files | Lines | of which code |
|---|---|---|---|
| Python `utils/python/` | 100 files | **17,172** | 11,130 |
| C++ `utils/` (11 namespaces + `hep-run.cc`) | 59 | **6,837** | ~4,660 |
| CMake + `cmake/` + Makefile | 12 | 691 | |
| `env/hep_env.sh` | 1 | 213 | |
| Rivet plugins `analyses/` | 6 | 641 | |
| Modules `modules/` | 4 | 694 | |
| Configs `configs/` | 7 | 877 | |
| Tests `tests/` | 123 | 33,178 | (17,350 of it is golden fixtures) |
| Docs `docs/` | 87 | 12,907 | |
| `legacy/` (v0, frozen) | 150 | 27,971 | |
| `aux/` (VS Code theme, icons) | 1,311 | — | not framework, untouched |

**Commands: 19** (`analyses bench build clean compare config doctor events new pdf plan plot proc
run runs show store studies watch`). v2 has **three**, `run`, `watch` and `build`, plus
`make`.

---

## 3. Python, package by package

Measured, with what each package *taught*. None of the code is kept.

| Package | Lines / code | What it knew that v2 needs (the ledger row) |
|---|---|---|
| `sweep` | 629 / 416 | coupled groups zip, and groups form a grid (~45 lines of core); selector precedence: tag → value → `#N` |
| `plan` | 1,150 / 688 | identity seeds, disjoint per-thread blocks in 1…9·10⁸ (`seeds.py`); an override equal to the base card must not change identity (`effective_settings`) |
| `run` | 2,137 / 1,398 | the process-group supervisor, stall detection, and attributing a failure to its cause (`signals.py:91`); the regex progress table (`parsers.py`) |
| `adapters` | 2,062 / 1,140 | the per-tool card dialects (§7, L12–L15) |
| `config` | 1,985 / 1,440 | strict validation with `where`/`hint`, and did-you-mean for unknown keys |
| `plot` | 1,719 / 1,080 | void across the whole page, *then* overlay the data, *then* auto-range (`transform.py`, `data.py`); the order is load-bearing |
| `proc` | 2,128 / 1,321 | YODA → ROOT conventions (`export.py`); nothing else is wanted (V4) |
| `term` | 1,561 / 1,114 | a view model fed by messages, not by the supervisor, which keeps the watch view decoupled |
| `results` | 1,618 / 1,069 | atomic writes (`.tmp` → rename); partial outputs named differently |
| `prov` | 461 / 293 | what provenance must hold: resolved config, card sha256s, tool versions, host, git revision and dirty flag |
| `store` | 435 / 304 | zstd over gz for kept event files, measured (D-STORE-COMP) |
| `env` | 1,093 / 743 | LHAPDF set checks; the repo root must be found by markers, never the working directory (`00/B18`) |

**Where the Python went, in code lines:**

| Bucket | Code lines | Share |
|---|---|---|
| Implemented something v2 still needs, done differently | ~2,300 | 21% |
| The `hep-run` contract | ~3,000 | 27% |
| Over-engineering, or dropped by V4 | ~3,500 | 31% |
| Plumbing (schema tables, CLI glue, dispatch) | ~2,300 | 21% |

Even the 21% is better rewritten than moved. It is written against v1's `Point`, `Plan` and
`Layout` types, which v2 does not have, and porting it would import their shape.

---

## 4. C++, namespace by namespace

| Namespace | Lines | What it knew that v2 needs |
|---|---|---|
| `Core` | 966 | exit codes as a contract (0/1/2/3/4/5/6/7/70); a second signal restores the default handler; sha256 must refuse FIFOs |
| `Status` | 489 | JSON lines on a separate fd, drop-on-full so a slow reader never blocks the generator, a heartbeat for stall detection; `#define Status int` in X11 (guard it) |
| `Events` | 154 | one `Pythia8ToHepMC` converter per worker |
| `Store` | 671 | `.part` → rename → sha256; zstd/gz writers through HepMC3's `CompressedIO` |
| `Results` | 616 | fill with raw weights, scale **once** at the end with σ and ΣW (the scaling contract, now a rule in `Module.hh`'s docs rather than a type) |
| `ML` | 460 | one ONNX session shared across threads, scratch per caller |
| `Phys` | 916 | `deltaPhi` must wrap, not loop (`00/B35`); `charge3` keeps the sign of the code given (the `-211` bug) |
| `Source` | 748 | σ combination; seed-list checks; chunked runs; catch at the thread boundary (§7) |
| `Module` | 217 | — (the `dlopen` model is gone) |
| `Analyzer` | 975 | Rivet's σ, `/RAW` and reentrancy behaviour (§7) |
| `Run` | 334 | — |
| `apps/hep-run.cc` | 291 | — |

Totals, by class:

| Class | Lines |
|---|---|
| Generic process basics | ~1,650 |
| Module library | ~1,970 |
| `hep-run` only | ~3,210 |

**All of it is deleted (V7).** The reason is not that it is bad: `post_rework` found the C++ half
healthy. It is that a process model needs about 320 lines of C++ support (`Status.hh` + `Module.hh`),
and a module that wants jets calls FastJet itself.

---

## 5. Build, environment, tests, docs, repository

| Item | Lines | Fate |
|---|---|---|
| `CMakeLists.txt` + `cmake/` | 591 | deleted; the `rivet-build` flags go to the ledger (L20) |
| `Makefile` | 100 | rewritten (V6). The `%.exe` rule is the interface the user wants, but it links every library, has no header dependencies and probes on every run (F4). |
| `env/hep_env.sh` | 213 | moved to `utils/Env/` and trimmed. It is the one v1 file kept as code, because it is the user's shell environment. |
| `tests/golden/legacy_run/` + the frozen `photo_ep.cmnd` from `tests/golden/inputs/` | ~2,000 | **kept** as `tests/reference/legacy_run/`: the cards, base card and YODAs of the legacy Pythia → FIFO → `rivet` pipeline at **one thread, seed 12345**, which is v2's architecture exactly |
| `tests/golden/test_legacy_counts.py` `EXPECTED_COUNTS` | 25 | **kept** as data: `tests/reference/point_counts.toml` |
| everything else in `tests/` | ~31,000 | deleted |
| `docs/rework/`, `docs/post_rework/`, `GUIDE.md`, `MAP.md` | 11,600 | deleted (V20) |
| `docs/rework_v1/` | 1,300 | kept: the retrospective v2 cites |
| `legacy/` | 27,971 | deleted (V20). `legacy/utils/Paint/` is consulted from git for Paint. |
| `analyses/` | 641 | moved to `modules/<P>/Rivet/` |
| `modules/Lambda/` | 385 | `Reconstruction.hh` rewritten without `Phys`; `Lambda.cc` rewritten as a plain program (P4) |
| `modules/Examples/ToyJets.cc` | 177 | deleted (a demo of the v1 module API) |
| `generator_comparison.{cc,root}` | 504 | the user's scratch file; **left untouched** at the repo root (user, 2026-09-26) |
| `aux/`, `literature/`, `_vs/`, `_text/`, `cross_machine/`, `archive/` | — | not framework; untouched |

---

## 6. Where the brief is already in v1

It is worth knowing, because it means the brief's design is **proven**, not speculative. Every
mechanism it names has worked once, somewhere in v1. v2 writes each one again, explicitly and
smaller.

| Brief item | Existed in v1 as |
|---|---|
| `sweeps = [q1, [q2, q3], q4]` | `[study].across` with coupled groups |
| `tools = [A, [B, C], D]` | supervisor phases, inferred from roles |
| `[prelim] fifo/files` | `make_fifo`, `Stage.writes` |
| stdout filter rules | `run/parsers.py`, as a Python literal |
| `[master]` compatible quantities | `key = {tool = …}` on a quantity |
| `[static]` | `[static]` |
| standard status reporting | `Status/` + `run/status.py` |
| `App_Pythia` | `legacy/generator.cc` (107 lines) + `Source/Pythia.hh` |
| `App_yd2rt` | `proc/export.py` (uproot) |
| Paint | `legacy/utils/Paint/` (1,675 lines; single histograms per canvas) |

**Genuinely new:**

- ROOT overlays with ratio panels and reference data;
- modules as plain HepMC-reading programs;
- quantity → tool maps as data;
- the make-native build.

---

## 7. The knowledge ledger

**What v1 learned by running things, which the deleted code carried implicitly.** Each entry says
where to read more (`git show rework/v1-final:<path>`) and which v2 phase must honour it. This is
the part of v1 that is kept.

| # | Knowledge | v1 evidence | v2 phase |
|---|---|---|---|
| **L1** | **σ over `PythiaParallel` instances:** a ΣW-weighted mean, errors in quadrature. `PythiaParallel` exposes σ but no error. | `utils/Source/Types.hh:38-50` (D-Q1) | P1 |
| **L2** | **A CLI Rivet normalises to the σ in the last event it reads**, and `Pythia8ToHepMC` stamps each event with its own thread's running σ. So threads > 1 means a wrong normalisation unless it is handled (F6). | `utils/Analyzer/Rivet.hh:18-20`; `legacy/generator.cc` | P1 |
| **L3** | `PythiaParallel` runs the callback on **worker threads in both modes**. An exception must be caught at the thread boundary, or it reaches `std::terminate` (`00/B32`). | `utils/Source/Pythia.hh` | P1 |
| **L4** | `Parallelism:seeds` is applied once in `init()`. Its length must equal the thread count, and each seed must be in 1…9·10⁸. **Pythia does not check.** | `plan/seeds.py`; D-SEEDS | P1 |
| **L5** | `Main:numberOfEvents` counts `next()` *attempts*. Failed events never reach the callback: ~2% at 5x41 GeV, 1e-4 at 27x920. So "written" ≠ "requested". | `configs/PhotoProduction/photo_ep.cmnd` header; `legacy/tools/rivpyth:102` | P1 |
| **L6** | Repeated `run()` after one `init()` is σ-consistent. A chunk size that is a multiple of the thread count reproduces the unchunked event set. | D-Q2 | P1 |
| **L7** | Rivet's `/RAW/_EVTCOUNT` is the analysed-event count, so it is the count check against the generator. | `legacy/tools/rivpyth:142` | P1 |
| **L8** | Opening a FIFO blocks until both ends are open. A dead writer leaves the reader blocked for ever, and there is no SIGPIPE. | `legacy/tools/rivpyth:195-213`; v1 supervisor | P1 |
| **L9** | Rivet initialises from the **first event** (beams from the event); `setCheckBeams` decides whether a beam change is fatal. | `utils/Analyzer/Rivet.hh` | P1 |
| **L10** | Rivet 4.1.3 skips `finalize` in a periodic dump for a non-reentrant analysis, so a dump is **unscaled**. Do not rely on dumps. | `utils/Analyzer/Rivet.hh:21-23` | P1 |
| **L11** | **Delphes cannot read a FIFO** (it skips zero-length input), and it creates its ROOT file before reading the card: write to `.part`, then rename. | `adapters/delphes.py:12-18` | P4 |
| **L12** | **Sherpa** prepends `./` to the output name, so use a relative FIFO name. Prepare with `RESULT_DIRECTORY` and `EVENT_OUTPUT: None`. The YAML is deep-merged and written whole. `mirror_mpi_pdf`. | `adapters/sherpa.py` | P4 |
| **L13** | **Whizard** SINDARIN is a *script*: the point card goes first, then include the base. `--execute` runs before the card. The integration card strips `n_events`, `$sample` and `sample_format`. There is no photon structure function, so direct photoproduction only. | `adapters/whizard.py`; D-Q7 | P4 |
| **L14** | **MadGraph**: a launch script, `lpp_for`, and four steps. The shower runs as Pythia with `Beams:frameType = 4` and `Beams:LHEF`. It **opens a browser** from a batch stage (`00/B39`, one line). | `adapters/madgraph.py` | P4 |
| **L15** | **Herwig/ThePEG**: build with `--with-hepmc --with-hepmcversion=3` (the default version is 2, and it fails); ThePEG's `RivetAnalysis` does not build against Rivet 4, and is not needed; `HepMCFile` writes HepMC3. Rebuilt 2026-09-26. | `docs/rework/steps/P7-S06_decide-herwig-rebuild.md` | P4 |
| **L16** | **FastJet SISCone keeps process-wide statics**: threads change the jets rather than crashing. Any threaded module that clusters must not share them (`00/B31`). | `docs/rework/00_Audit.md` B31 | P4 |
| **L17** | Reading a YODA **resets `LC_ALL` to `C`**: name `encoding="utf-8"` on every text read and write (`00/B29`). | `plot/io.py:28` | P1 onward |
| **L18** | **Reference data is matched by an explicit map, never by name**: ZEUS `d08` is not the same observable as `photo_eic`'s `d08` (`00/B5`). The eic map's physics justification is in the v1 `eic.toml` comments. | `configs/PhotoProduction/eic.toml` (v1) | P3 |
| **L19** | **A Rivet option not declared in the `.info` is silently ignored**, giving identical curves (`00/B14`). Check options against the `.info`. | `adapters/rivet.py` | P2 |
| **L20** | `rivet-build` needs `-I utils -I modules/<P>` for shared headers, `-DHEKIT_WITH_HEPMC=1` where the code checks it, and the ONNX include path when the `.info` says `Requires: ONNX` (`00/B37`). `.info`/`.plot` copies must be real make targets (`00/B44`). | `CMakeLists.txt:176-242` | P0 |
| **L21** | Rivet writes **densities** (dσ/dx). A module that writes per-bin integrals differs by the bin width (`00/B42`). A module plotted beside Rivet must divide by the width. | `modules/Lambda/Lambda.cc` | P4 |
| **L22** | **A cache must be keyed on everything it reads**, such as `PATH` and install roots (`00/B38`). This applies to `build/flags.mk`. | `env/doctor.py` | P0 |
| **L23** | Photoproduction card facts: with this card, `Photon:ProcessType` 0 and 1 give identical events, and direct needs its own card (`00/B13`); `pTHatMin` 6 sits above jet `ETMIN` 5 and biases the lowest bins (`00/B27`). | `configs/PhotoProduction/photo_ep.cmnd`, v1 `eic.toml` | P2 |
| **L24** | Cross-generator photoproduction: match EPA Q²max, the photon PDF (CJKL vs CJKLLO), the proton PDF and the order. Measured at 18×275 LO MPI-off: 11,950 ± 34 pb (Pythia) vs 9,636 ± 782 pb (Sherpa). | D-Q7 | P4 |
| **L25** | Kept event files: **zstd** beats gz on every axis measured (2.1× faster to write, 1.26× to read, smaller). | D-STORE-COMP | P1 |
| **L26** | **A test whose fakes have a different type from the real thing hides bugs.** Sherpa/Whizard/MadGraph setting sweeps crashed while their tests passed (F1). | §8 | all |

---

## 8. Findings

Numbered `v2/Fn`, recorded while measuring. In a clean slate most are resolved by deletion, but each
is kept because its *lesson* applies to the rewrite.

| # | Finding | Evidence | Resolved by |
|---|---|---|---|
| **F1** | Sherpa, Whizard and MadGraph unpack each `Point.settings` entry as a 3-tuple, but the entries are frozen `Assignment` dataclasses. **Any setting sweep on those tools raises `TypeError`**, while their tests pass on tuple fakes. Confirmed by running it. | `adapters/sherpa.py:127,189`; `whizard.py:155,215`; `madgraph.py:93,151` | deletion (P0); lesson L26 |
| **F2** | `Core/Paths.hh` has no callers, and its markers need `sources/`, which no longer exists. | `utils/Core/Paths.hh:16` | deletion |
| **F3** | Python root detection requires `analyses/`, plus four other hard-codes. | `env/paths.py:25` | deletion; v2 markers are `configs/` + `modules/` + `utils/Env/` |
| **F4** | The `%.exe` rule links every library, has no header dependencies, and probes seven `*-config` tools on every `make`. | `Makefile:61-100` | the P0 Makefile |
| **F5** | Five Pythia runners exist. | `Source::Pythia`, `legacy/generator.cc`, `generator_comparison.cc`, 2 spikes | one `App_Pythia` (P1) |
| **F6** | A CLI Rivet at threads > 1 is normalised to one thread's σ. | L2 | P1 S1 gate |
| **F7** | The module build is guarded on `HEKIT_WITH_RIVET`, which is always true. | `CMakeLists.txt:243-275` | deletion |
| **F8** | `Transport` is instantiated and never used in production. | `run/supervisor.py:154` | deletion |
| **F9** | `HEKIT_WITH_DELPHES` is read by nothing, and there is no `FindROOT`, although ROOT is the target's primary graphics. | `CMakeLists.txt` | deletion; `requires: root` |

---

## 9. What carries forward: principles, not code

From [rework_v1/01_Philosophy.md](../rework_v1/01_Philosophy.md), the principles that held:

| Principle | In v2 |
|---|---|
| Physics lives in the native card, never in TOML | `baseconfig`; quantities only render overrides |
| Resolved means resolved | each tool gets a finished card and argv; no tool interprets a default |
| stdout is not the status channel | `$HEP_STATUS_FD` |
| Identity-derived seeds | per point, simplified (02 §7) |
| A partial result has a different name | `*.partial.*`, and `.complete` written last |
| Require the explicit statement; refuse the convenient inference | the unconsumed-quantity check, explicit connections, the explicit data map |
| Tests never write into `results/` or `configs/` | `output/tests/` |
| One error type with `where` and `hint` | `HepError`, rewritten (~40 lines) |
| Say the number, including when it is bad | the budget in 06 §3 is measured at the end |

**Principles deliberately dropped**, with the reason:

| Dropped | Why |
|---|---|
| "Replacement before removal" | V5. The reference data plus L1–L26 replace a side-by-side v1. Its cost, a gap with no working system, is accepted (R3). |
| "Make the invalid state unrepresentable" through types (`Worker` without `scale()`) | V8. With ~200 lines of module kit, a documented rule and one test are enough. |
| Enforced layering of many packages | the runner is one flat package of ~10 modules; one import-order test is kept, because it is cheap |

---

## Appendix: reproducing the numbers

Run from the repo root, at `rework/v1-final` (or `65feb97`).

```bash
git ls-files utils/python | grep '\.py$' | xargs wc -l | tail -1                 # 17172
for d in utils/python/hekit/*/; do echo "$(find $d -name '*.py' | xargs cat | wc -l) $d"; done
for ns in Core Status Events Store Results ML Phys Source Module Analyzer Run; do
  echo "$ns $(cat utils/$ns.hh utils/$ns/*.hh 2>/dev/null | wc -l)"; done        # sums to 6546 (+291 hep-run.cc)
wc -l CMakeLists.txt cmake/*.cmake Makefile env/hep_env.sh
for d in tests/*/; do echo "$(git ls-files $d | xargs cat 2>/dev/null | wc -l) $d"; done
git ls-files docs | xargs wc -l | tail -1; git ls-files legacy | xargs wc -l | tail -1
git ls-files aux | wc -l
python3 -c "import sys; sys.path.insert(0,'utils/python'); from hekit.cli import COMMANDS; print(len(COMMANDS))"
```

The code/docstring split and the reuse buckets come from two read-only surveys run on
2026-09-26. The buckets are judgements, labelled `~`; the line counts are measurements.
