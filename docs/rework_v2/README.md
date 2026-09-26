# rework_v2 — the second rework

The plan for rebuilding the framework around the user's own design: tools chained as processes,
one run TOML, and conventions for where everything lives. Written 2026-09-26 against `65feb97`
(branch `rework`). Revised the same day, on the user's instruction *"do not be afraid to overhaul
everything and scrapping entire utils. Do not be too risk averse"*.

**Status: executed**, 2026-09-26 to 2026-09-27, on the user's order, as commits on the branch
`rework` (P0–P4, local). Each phase file's Log records what was measured and every deviation;
[06_Roadmap.md §3](06_Roadmap.md#3-budgets) the measured budget. The user guide is
[../GUIDE.md](../GUIDE.md).

---

## The one-paragraph version

- **`utils/` is scrapped and rebuilt small.** Everything else v1 built goes too: CMake, 33k lines
  of tests, `legacy/`, and the v1 design docs. Git tags keep all of it.
- **The new `utils/` holds:**
  - three apps: `App_Pythia`, `App_yd2rt`, `Paint`;
  - two small headers: `Status.hh`, and `Module.hh` for project programs;
  - `utils/Env/`, which contains the shell environment, a small Python runner, and one folder per
    standard tool.
- **A run is a TOML** under `configs/<project>/` naming a **configuration**. Its `sweeps` expand
  into **points**: independent quantities form a grid, and entangled ones move together.
- **For each point, the runner:**
  1. makes the agreed interface files (`[prelim]`);
  2. writes each tool's native point card;
  3. runs `tools` in order, where an inner list runs together;
  4. watches the processes.
- **After all points,** Paint draws ROOT pages, one per `plot_points` cell.
- **Where files go.** Technical files go to `output/`, products to `results/`, and compiled things
  to `build/`.

**What survives from v1 is knowledge, not code.** The Rivet analyses, the configs and cards, the
reference data, and a *knowledge ledger* of every quirk v1 learned the hard way
([01_Assessment.md §7](01_Assessment.md#7-the-knowledge-ledger)).

## Measured starting point

v1 is **~24,700 lines of code** plus 33k of tests and 13k of docs, for two projects. v2's budget is
**~5,000**. Its physics libraries are lean but unnecessary once every tool is a process. The
orchestration is bloated by inference (a pipeline derived rather than declared) and by duplication
(two ways of doing most things). The details are in [01_Assessment.md](01_Assessment.md).

---

## The documents

| | |
|---|---|
| **[00_Brief.md](00_Brief.md)** | The user's design, verbatim, plus every answer given during planning. The source of truth. |
| **[01_Assessment.md](01_Assessment.md)** | v1 measured; why it is convoluted; what is deleted; **the knowledge ledger** (what must not be forgotten when the code goes). |
| **[02_Architecture.md](02_Architecture.md)** | The v2 model: the process chain, components, categories → runner roles, connections, scopes, identity, status, failure handling. |
| **[03_Layout_Build.md](03_Layout_Build.md)** | The tree, path resolution, output vs results, make rules and `hep build`, commands, tests, and the P0 delete/keep/move list. |
| **[04_Config.md](04_Config.md)** | The run TOML formalised, the master TOML, quantity semantics, validation, and the v1 configs translated. |
| **[05_Tools.md](05_Tools.md)** | The tool-folder contract, the standard tools, the status protocol and filters, App_Pythia, the module kit, App_yd2rt, Paint. |
| **[06_Roadmap.md](06_Roadmap.md)** | Five phases, budgets, risks. |
| **[phases/](phases/)** | One file per phase, 2–3 steps each. |

**Reading order:** the brief, this README, 02, 04. Then 06 and `phases/` to execute.

---

## Decisions

All taken during planning. Nothing is left pending that blocks P0. Each row names what it gives up.
Decisions made during execution are appended as V22, V23, … in the same form.

| # | Decision | Gives up | Source |
|---|---|---|---|
| **V1** | The runner is **Python**, small and fresh: `utils/Env/run` plus `utils/Env/<tool>/`. Standard library only (`tomllib`, `argparse`, `subprocess`), with `rich` optional for the watch view. | click; v1's package structure | user |
| **V2** | **No in-process event loop.** Every tool is a process: `App_Pythia` → HepMC (FIFO or file) → `rivet`. A module is its own program. | in-process speed; sharded Rivet (1.67× on 4 threads) | user |
| **V3** | Keep: `--plan` (dry run), identity seeds, skip-unchanged, provenance, a live watch, and YODA plotting when asked | — | user |
| **V4** | Drop: fits and derived histograms, bench, config migrate/reference, store, compare, clean, new, doctor, and every other v1 command | built-in fitting (a fit is a custom tool now) | user |
| **V5** | **Clean slate.** `utils/`, CMake, `cmake/`, `env/`, `legacy/`, v1's tests and v1's design docs are deleted in P0. Nothing is ported as code; v1 is **consulted** through git (`git show rework/v1-final:<path>`). | a working system between P0 and P1 (R3); v1's tested code | user (revised instruction) |
| **V6** | **Make-native build**: pattern rules, `requires:` lines, a flag cache, `-MMD` header dependencies. No CMake. | CMake's `AUTO` components; ctest | brief (`make *.exe`, `hep build`) |
| **V7** | **No C++ libraries carried**: `Core`, `Status`, `Events`, `Store`, `Results`, `ML`, `Phys`, `Source`, `Module`, `Analyzer` and `Run` all go. The new C++ is two headers (`Status.hh` ~120 lines, `Module.hh` ~200) and three apps. A later need for `Phys`- or `ML`-like helpers is met by copying from git deliberately, when it arises. | ~3.6k lines of tested library code (`Phys` 916, `ML` 460, `Results` 616, …) | this revision |
| **V8** | **Modules are plain programs.** `modules/<P>/<X>.cc` has a `main()`, reads HepMC through `Module.hh`, and writes ROOT (or YODA) itself. No `Module::Base`, no registration macro, no scaling-contract types. | v1's type-enforced "scale exactly once" contract | this revision |
| **V9** | **Identity is per point**, not per step. There is **no shared generation and no Rivet multiplexing**: every point runs its own chain. It is deferred with a trigger ([02 §7](02_Architecture.md#7-identity-seeds-and-skip)). | cheap analysis-option sweeps (a Rivet-option sweep regenerates events) | this revision |
| **V10** | **YODA plotting is `rivet-mkhtml`**, called with the point YODAs as curves. No matplotlib backend. | v1's mpl publication style | this revision |
| **V11** | **Labels are TLatex** (`#sqrt{s}`, `e^{-}`), since ROOT is primary. The YODA backend translates a documented subset to LaTeX. | writing `$…$` natively | this revision (was risk R6) |
| **V12** | `serial` is a **directory prefix only**; identity decides skip | — | was Q1 |
| **V13** | A leading `./` means **the repo root**; `../` is an error | relative-to-CWD paths | was Q2 |
| **V14** | `provenance.json` sits **next to the products** in `results/` | — | was Q3 |
| **V15** | After-all-points tools go in `post = [...]`, handed a points manifest | — | was Q4 |
| **V16** | Fan-out is a **list-valued `output_file`** on a producer (App_Pythia writes all of them) | a general tee | was Q7 |
| **V17** | The master TOML is `utils/Env/master.toml`, optionally overlaid by `configs/<P>/master.toml` | — | was Q8 |
| **V18** | Rivet sources: **both** `modules/<P>/Rivet/<x>.cc` and `modules/<P>/Rivet_<x>.cc`, as the brief allows | — | was Q10 |
| **V19** | A tool may be chosen by a quantity (`"@generator"` in `tools`) | — | was Q14 |
| **V20** | `legacy/`, `docs/rework/`, `docs/post_rework/`, `GUIDE.md` and `MAP.md` are **deleted**. `docs/rework_v1/` (the retrospective) is kept, because v2 cites its lessons. | readable history in the tree (git keeps it) | was Q6 |
| **V21** | **Standard configurations for custom tools.** A `custom` or `module` table may set `<tool>_<export> = true` (`pythia_cmnd`, `rivet_analyses`, `herwig_run`, …; default false). The runner renders that standard tool's card for the point as usual, even when the tool is not in the chain, and writes its absolute path(s) under `[standard.<tool>_<export>]` in the custom tool's config. **Every tool with a card exports `<tool>_card` automatically**; named keys are aliases or declared extras. This enables **integrated process runs**: e.g. Pythia and Rivet in one user program, with the runner's sweeps and identity seeds. | the program takes on the chain's duties itself (σ over threads, counts): L1–L3 | user |

**v1 decisions this overturns:**

| v1 | Overturned by |
|---|---|
| D1, D4 (Python over an in-process C++ loop) | V2 |
| D7, D14 (YODA only) | the brief's "ROOT primary" |
| D8, D13 (event store) | V2 |
| D10 (CMake) | V6 |
| D16 (the namespace house style) | V7 (with only two headers, it no longer applies) |
| D17 (legacy archived in the tree) | V20 |
| D21 (identity seeds) | kept, simplified |

---

## Traceability: every item of the brief, and where it is answered

| Brief item ([00_Brief.md](00_Brief.md)) | Answered in |
|---|---|
| §Tools: the ten categories | [02 §4](02_Architecture.md#4-tool-categories-what-the-runner-does), [05 §2](05_Tools.md#2-the-standard-tools) |
| §Directory Structure 1–8 | [03 §1](03_Layout_Build.md#1-the-tree), [03 §3](03_Layout_Build.md#3-output-and-results) |
| §Directory Structure 9: no `./env`; `utils/Env/` | [03 §1](03_Layout_Build.md#1-the-tree), [03 §8](03_Layout_Build.md#8-p0-delete-keep-move) |
| §Directory Structure 10: no `./analyses`; `Rivet_` prefix or `Rivet/` | [03 §5.1](03_Layout_Build.md#51-make-pathexe-and-make-pathso), V18 |
| Automatic path prefixing unless `./` | [03 §2](03_Layout_Build.md#2-how-a-name-becomes-a-path) |
| Configuration through native config files | [04 §1](04_Config.md#1-three-kinds-of-file), [05 §1](05_Tools.md#1-the-tool-folder-contract) |
| `[master]` / compatible quantities | [04 §2](04_Config.md#2-master) |
| `[run]` | [04 §3](04_Config.md#3-run) |
| `[run.<configuration>]`: `sweeps`, `plot_points`, `tools` | [04 §4](04_Config.md#4-runconfiguration) |
| `[prelim]` | [04 §5](04_Config.md#5-prelim), [02 §5](02_Architecture.md#5-connections-how-data-moves-between-tools) |
| `[static]` | [04 §6.2](04_Config.md#62-static) |
| `[tools.<tag>]`, custom tools, `[tools.<custom>.config]` | [04 §7](04_Config.md#7-toolstag) |
| Status: standard, or stdout filter rules | [05 §3](05_Tools.md#3-status-the-standard-protocol-and-the-filter-rules) |
| `[quantities.<q>]` | [04 §6.1](04_Config.md#61-quantitiesq) |
| `[plot]`: ROOT primary, YODA → ROOT, a Paint-like app, pdf/png/svg, gutters | [04 §9](04_Config.md#9-plot), [05 §6](05_Tools.md#6-appyd2rt-utilsappyd2rtcc), [05 §7](05_Tools.md#7-paint) |
| `make *.exe`, `make *.so` | [03 §5.1](03_Layout_Build.md#51-make-pathexe-and-make-pathso) |
| `hep build` | [03 §5.4](03_Layout_Build.md#54-hep-build) |
| `hep run {config}` | [03 §6](03_Layout_Build.md#6-commands) |
| `utils/App_Pythia`, `utils/App_yd2rt` | [05 §4](05_Tools.md#4-apppythia-utilsapppythiacc), [05 §6](05_Tools.md#6-appyd2rt-utilsappyd2rtcc) |
| `utils/Env/run`, the dict of standard tools, `Env/{tool}/` | [05 §1](05_Tools.md#1-the-tool-folder-contract), [02 §3](02_Architecture.md#3-components) |
| "determine how much lean or bloated" | [01_Assessment.md](01_Assessment.md) |
| "do not overfactorise into too many steps in a phase" | [06 §1](06_Roadmap.md#1-the-phases): 5 phases, 13 steps |
| "do not be afraid to overhaul everything … not too risk averse" | V5, V7–V10, V20; [06 §2](06_Roadmap.md#2-how-a-phase-is-run) |
| Custom tools get standard tools' configuration (`pythia_cmnd = true` → `[standard.pythia_cmnd]`) | V21; [04 §7.3](04_Config.md#73-standard-configurations-for-custom-tools), [05 §2](05_Tools.md#2-the-standard-tools), [05 §5](05_Tools.md#5-the-module-kit-utilsmodulehh) |
