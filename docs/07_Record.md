# 07 — The record

What was decided, what was learned, and what has been measured. The code cites this document by
id: **V** a decision, **L** a row of the knowledge ledger, **C** a validation rule, **F** a
finding, **R** a risk, and `00/Bn` or **Dn** for v1's findings and decisions. An id is never
reused or renumbered; a decision that is overturned stays, with the row that overturned it.

The previous documents (v1's design set and retrospective, and the rework v2 plan with its phase
logs) were replaced by this manual on 2026-09-27 (V30). They are in git: v1's at the tag
`rework/v1-final` (`git show rework/v1-final:docs/rework/10_Roadmap.md`), and the v2 plan in the
history of `docs/rework_v2/` (`git log --all -- docs/rework_v2`).

---

## 1. The brief

The user's design for the second rework, given on 2026-09-26, **verbatim**: everything else in this
manual answers to it. Headings were added so the rest can cite *Brief §Tools* and so on; the text
under each is unchanged, spelling included.

## Preamble

> Goal of this session is second rework. Make files related to this in docs/rework_v2/
>
> This will be first round of plan for more high level planning with another round of planning to
> follow if required.
>
> As it stands, from my perspective whole framework is very convoluted and scattered, since it was
> rework by Claude as per its best judgement for the pipelines.
>
> So I will now give rough high level design for how I want whole thing to work and then you can
> plan after determining how much lean or bloated current framework is.

## Tools

> Tools will be categorised (informally, not necessarily physically into folders) into following
> categories. (whether a category actually has tools installed is different matter)
>
> 1. Providers (PDFs, PDF providers (LHAPDF) and tools such as FeynRules, Sarah; tools that extend
>    other tools with data/ standard configurations)
> 2. Bridges/Interfaces (HepMC3,LHE)
> 3. Process Generators (MadGraph, Whizard)
> 4. Event Generators
> 5. Detector Simulators (Geant, Delphes)
> 6. Analysis *Algorithms* (Fastjet, ROOT; fuction-like library based tools used inside analysis
>    applications or programs that provide function, classes and methods to process data)
> 7. Analysis *Applications*(Rivet, CMSS: pre-set pipelines; called as an independent process)
> 8. Analysis *Visualisation* (YODA, Root ; plot and store final data usually as graphs and
>    histograms)
> 9. Statistics (roofit, roostats, uproot, python; ML applications/libraries)
> 10. Database (xrootd,rucio etc)

## Directory Structure

> 1 ./configs/{project}/{file}.{ext}  for configuration files
> 2. ./modules/{project}/<{sources_to_be_compiled}.cc , {headers}.hh , {header}/{headers.hh}>  for
>    specific tasks that cant be achieved by typical tool chaining
> 3. ./output/{project}/ for tmp files, logs, configs and other technical files
> 4. ./output/{tests}/ for tests
> 5. ./results/{project}/ for yoda/root/plots and analysis and post analysis products
> 6. ./build/ for compiled stuff
> 7. ./build/Rivet/ for rivet analyses
> 8. ./docs/ for plans and documentations
> 9. no ./env folder, /utils/Env/ for bash script, terminal command codes
> 10. no ./analyses , recognise rivet sources from modules root by Rivet_ prefix or in
>     {module}/Rivet/
>
> generally automatically prefix path as expected by convention, fo example, where config is
> expected, automatically prefix by ./config/ and so, unless begun by ./

## Configurations

> Wherever possible, configuration will be provide to processes via config files (especially to
> generators; like cmnd to pythia; .run for herwig etc; or toml)

### Main toml config

> would have
>
> ```
> [master]
> master_toml =
> base option for additional infor for parsing the toml
> like [quanities.{standard_tool}.compatible_quantities]
>
> [run]
> serial
> name
> project
> configuration =
>
> [run.{configuation}]
> serial
> name
> event_count =
> threads =
> sweeps = [thisQuantity, [these two, together], and this] # independent and entangled sweeps
> plot_points = [energy, mass] # for example, plots will be separated by grid of point based on these quantities , (only first quantities of entangled groups, if two entangled quantities are put in here)
> tools = [firstThis, [these ones, together with &], thenthis] (sequence of tool call for each point)
> tools may called via tool configuration tag
>
> [prelim]
> fifo = ["this.hepmc","that.root"]
> files =
> #for preparations required before using tools, such as what files to be created beforehand, whether normal or fifo; typically for interface files between two or more tools, you cant entrust one process to make due to capability or timing constraints, that is, tools are given agree upon file that is already made for them so neither risks inexistence error.
> #other options that need to be evaluated, or executed BEFORE running tools.
>
> [static]
> quantity = value/preset used when not sweeped
>
> [tools.{tooltag}]
> tool = "pythia"
> baseconfig =
> output_file=
> OtherToolSpecificOption =
>
> [tools.{custom}]
> tool = "custom"
> executable = /folder/file.exe
> arguments = # given in tool call
>
> [tools.{custom}.config]
> #toml options extracted into separate toml file, given as first tool arg, so it can it however it wants.
>
> #either a tool can be compatible and report state in standard manner for terminal watch; or a json or some other thing can be supplied for tool with rules for run to parse/filter stdout lines
>
> [quantities.{quantity}]
>
>
> [plot.{options}]
> ```

### Plotting

> Primary Graphics shall be done via Root, unless explictly told to use yoda. Yoda files would be
> converted to non-temporary Root files. Perhaps a legacy Paint like utils, that can be compiled as
> standalone program, and called to output based on config file. have options to decide,
> pdf/png/svg as outputs.
>
> incluce options like
> y_gutter = 1.5 (y-axis goes to 1.5*MAXY_value in plot; to make space for labels/legends)
> x_gutter =

## Commands

> make *.exe ; for *.cc to .exe for manually compiling a particular source
> similarly make *.so ; expect full paths, then determine output path based on conventions
>
> hep build ; for all modules, utils/App_*.cc, utils/Apps/*
> hep run {config} (sourced directly from ./configs/{config}, unless {config} starts with ./)
>
> utils/App_Pythia for standard pythia tool that outputs hepmc, utils/App_yd2rt for yoda to root
> conversions and so on
>
> /utils/Env/run script, dict of standard tools, in Env/{tool}/ for standard operation scripts, such
> as config parser and whatever for that respective tool.
### Answers given while planning

As binding as the brief.

| Question | Answer |
|---|---|
| Language of the runner (`utils/Env/run`, `utils/Env/{tool}/`) | **Python, slimmed** |
| Fate of v1's in-process `hep-run` | **Drop it** — every tool is a process |
| v1 capabilities to keep beyond `run`/`build` | **Plan + seeds + provenance**, **live terminal watch**, **YODA-side plotting**. Not kept: fits/statistics (`hep proc`), and by default bench, config migrate/reference, store commands, compare, clean, new, doctor |
| How v1 is retired | **Refactor v1 in place / build from clean slate if required** |
| Granularity of the plan | "make proper detailed plan in docs/rework_v2/; do not overfactorise into too many steps in a phase" |
| When to implement | "do not start implementation until my explicit order, now keep planning" |
| Boldness (revision, same day) | "Go over plan once more. Do not be afraid to overhaul everything and scrapping entire utils. Do not be too risk averse" |
| Standard configurations for custom tools | "How about a way for custom tools to get configuration of standard tools. Let custom tool have in running toml to have {pythia_cmnd, etc} bool options (default false) during run temp confs wil be generated as usual but tool toml will have file path options [standard.pythia_cmnd] etc which tools can retrieve themselves and use for integrated process runs" |

The last answer superseded "refactor v1 in place": the first draft of the plan (refactor in place,
dual routing, 9 phases) was replaced by the clean slate of V5 and V7–V10.

---

## 2. Decisions

Each row names what it gives up. V1–V21 were taken while planning (2026-09-26); V22 onwards during
execution and after it, most on the user's instruction.

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
| **V9** | **Identity is per point**, not per step. There is **no shared generation and no Rivet multiplexing**: every point runs its own chain. It is deferred with a trigger (02 §8). | cheap analysis-option sweeps (a Rivet-option sweep regenerates events) | this revision |
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
| **V20** | `legacy/`, `docs/rework/`, `docs/post_rework/`, `GUIDE.md` and `MAP.md` are **deleted**. `docs/rework_v1/` (the retrospective) was kept at first, because v2 cites its lessons; the manual (01–07) replaced it, and it is in git (`git log --all -- docs/rework_v1`). | readable history in the tree (git keeps it) | was Q6 |
| **V21** | **Standard configurations for custom tools.** A `custom` or `module` table may set `<tool>_<export> = true` (`pythia_cmnd`, `rivet_analyses`, `herwig_run`, …; default false). The runner renders that standard tool's card for the point as usual, even when the tool is not in the chain, and writes its absolute path(s) under `[standard.<tool>_<export>]` in the custom tool's config. **Every tool with a card exports `<tool>_card` automatically**; named keys are aliases or declared extras. This enables **integrated process runs**: e.g. Pythia and Rivet in one user program, with the runner's sweeps and identity seeds. | the program takes on the chain's duties itself (σ over threads, counts): L1–L3 | user |
| **V22** | **Seeds follow the generator's identity**, not the whole point's: the `produces_events` steps' cards (comments dropped), base cards, binaries and replica values, with threads and events (02 §8). The same generator set-up gives the same events in any configuration, so a chain's point and an integrated program's can be compared bin for bin. The identity carries the rule (`"seeds": "generator"`). | every point reran once when it changed | P4 S1 |
| **V23** | **`.complete` and `provenance.json` live in `output/<point>/`**; `results/<point>/` holds the products only. Overturns V14. | provenance beside the numbers (P1 in `bots/intent.md` would bring an identification back into the products) | user, P5 |
| **V24** | **A `pre` stage**: tools run once before every point; their products are inputs every point may name, and their identity is part of every point's. A failed pre stage stops the run. | — | user, P5 |
| **V25** | **The sweep in one file**: after the points, `results/…/plots/root/<configuration>.root` holds every point's YODA (a directory per point, raw entries, `points.json` inside), built by `App_yd2rt --merge` and rebuilt only when a YODA changes; the pages are drawn from it. The same merge is a post tool, `plotmerge`. `hep plot` draws a configuration's pages, or overlays any YODA/ROOT files. Pages go to `plots/root/` (Paint) and `plots/yoda/` (mkhtml). | the per-point conversion cache | user, P5 |
| **V26** | **One block per finished point** in the views: `── point 2/4: NNPDF23lo ── ok after 71.8 s` and the results path; a failed point's block names the tool, its exit and the message. `hep watch` builds the same blocks from the (timestamped) journal. | per-tool lines for tools that did their job | user, P5 |
| **V27** | **Paint looks like rivet-mkhtml by default, and its style is TOML**: `utils/Apps/Paint/base.toml` holds every style key with mkhtml's values; `[plot].root_style` (a file), `[plot.style]` and `[plot.object."<glob>"].style` name only what they change, later layers winning, each checked against base.toml at plan time and by Paint. Math letters in labels are italic. `[plot].legend` moved to `legend.position`. | the 900 × 600 canvas and sans-serif pages | user, P5 S2–S3 |
| **V28** | **`backend = "both"`** (or a list): one run draws the Paint pages and the mkhtml pages from the same page configs, ranges and voids. Beside Paint the style keys are allowed; a legend placed at `[x, y]` is still refused. | — | user, P5 S4 |
| **V29** | **Gutters**: `y_gutter = g` puts the top of the y axis at (1 + g) × the largest drawn value (the brief's `y_gutter = 1.5` becomes `0.5`); `x_gutter = g` widens x by g of its span. `0` or `"default"` sets nothing: the drawing tool's own range (ROOT's `THistPainter` rule for Paint; mkhtml's for the yoda backend). Defaults: `y_gutter = 0.5`, `x_gutter = "default"`. | the brief's multiplier spelling | user, 2026-09-27 |
| **V30** | **The documents are this manual** (`docs/01`–`07`). `docs/rework_v1/`, `docs/rework_v2/`, `GUIDE.md` and the old README are deleted; ideas found while reading them are in `bots/intent.md`. Overturns V20's keeping of `rework_v1/`. | readable plans and phase logs in the tree (git keeps them) | user, 2026-09-27 |
| **V31** | **`shards = K`** on a Rivet table: the runner makes K Rivet processes in the table's group, each reading its own FIFO, and a `<tag>.merge` step (`rivet-merge -e`, the folder's `[shard] merge`) in the next group writes the table's `output_file`. The producer **deals** each event to one member of a group (`A+B+C` in App_Pythia's outputs). Each shard is count-checked against its share (`written_per_output`); the seeds do not move (cards, not argv). App_Pythia formats on the worker threads (`processAsync = on`), one writer and lock per output. Separate processes, so L16's statics are not shared. Every analysis must be `Reentrant: true`. | one Rivet process per point; its single `.yoda` as the only technical file | user, 2026-09-29 |
| **V32** | **A view never blocks the run**: every line and frame goes through one background thread (`watch._Screen`); a terminal that stops reading loses the display, never the supervision, and `end()` gives up after a few seconds. | a view that is exactly in step with the run | user, 2026-09-29 |
| **V33** | **The integrated program runs Pythia as App_Pythia does**: `InprocJets` is split into headers (`modules/PhotoProduction/Inproc/`: `Stamp.hh`, `Feed.hh`, `Analysis.hh`, `Engines.hh`); a converter per instance with `processAsync = on`; one Rivet on its own thread behind a bounded feed, given the L28 σ at the end as a user σ. Still one Rivet (L16). | one file; Rivet inside Pythia's callback | user, 2026-09-29 |
| **V34** | **Several Rivets in one process**: `rivet_threads = K` in InprocJets' config runs K `AnalysisHandler`s on threads of their own, fed first-free from one queue, initialised on the first event before any analyses, merged (`AnalysisHandler::merge`) before one `finalize`. It needs FastJet's SISCone patched (L29) and refuses K > 1 without it. `InProcZeus.toml` and `InProcEIC.toml` use 12 + 12. | a stock `~/HEP` FastJet; a Rivet that is one thread per process | user, 2026-09-29 |
| **V35** | **`combine = ["replica"]`**: the points that differ only in the combined quantities are merged per group (`rivet-merge -e`, planned as a stage like `post`, in `<cfg>/<group>/`), and the pages are drawn from the groups: seed replicas become one curve per PDF with their statistics added. C14 checks it. `zeus_seedSweep.toml` uses it (4 PDFs × 5 seeds, pT0Ref = 3.2); its `spread` configuration draws the same seeds one curve each. | a post merge of every point, or one long run per curve | user, 2026-09-29 |
| **V36** | **`parallelism = K`**: up to K points at once, each on a thread through the unchanged executor (`execute.run_points`). `threads` stays per point and parallelism is in no identity or seed, so every point's result is its one-at-a-time result. No renamed temp files: each point already has its own folder; the journal, the views (a part per point) and prepare cache entries (lock + `flock`) are made safe to share. Ctrl-C stops the running points and starts no more. | one point at a time (T3) | user, 2026-09-30 |
| **V37** | *(its meaning of "default" in a child is replaced by V55)* **`"default"` is a value of every drawing option**: `[plot]`, `[plot.object]` and style keys; it sets nothing and the drawing tool does what it does by itself (no voiding, its own range, the `.plot`'s log axes, labels and `RatioPlot`, base.toml's look), which is not always the runner's default for a key left out. `[plot.object]` values are now type-checked (a string for a bool was read as true). | — | user, 2026-09-30 |
| **V38** | **`[run].sweep_runs = true`: every configuration, one run after another.** `hep run <config>` runs each configuration not `swept = false`, in file order, **each a run of its own** (exactly `hep run <config> <cfg>`: title, blocks, verdict, journal, folder) after a `run NN - <title> -` line (`[run.<cfg>].title`). All are planned before the first starts (a config error anywhere: exit 2, nothing run); each is planned again at its turn, so TOML edits count. A failed run leaves the next to start; Ctrl-C starts no more. Each run's journal names the next, so `hep watch` follows on. Not a grand run: no sweep-level state or summary. | a shell loop, whose Ctrl-C only ended one run | user, 2026-09-30 |
| **V39** | **`seed_type` = "identity" \| "manual" \| "random"** in `[run]` or `[run.<cfg>]`. "identity" is V22 unchanged (its identity still says "generator": nothing reruns). "manual": exactly `manual_seed` for every point, or a seed quantity's value per point; overlapping blocks on one generator setup are refused (they would repeat events). "random": drawn from the OS by the runner when a point runs and recorded, not `Random:seed = 0`: PythiaParallel's time seed gives threads time+i, so points started within `threads` seconds of each other repeat events, and Herwig's and Sherpa's defaults are fixed. Every seed is in provenance.json, so any run can be repeated with "manual". | seeds only from the identity; a card's `Random:seed` silently ignored | user, 2026-09-30 |
| **V40** | **A Pythia `pdf` value is written as given: no `LHAPDF6:` is added.** Write `"LHAPDF6:<set>[/member]"` (checked installed), or one of Pythia's own set numbers (`13`), or a grid file. A bare installed LHAPDF set name is refused with the `LHAPDF6:` spelling (Pythia would read it as a file). Sherpa keeps the bare name (`check = "lhapdf"` now refuses a prefixed one), so one `pdf` quantity no longer feeds both. Identities of prefixed values are the old ones (the card line is the same): zeus_seedSweep's 24 complete points stayed complete. | the master's `format = "LHAPDF6:{}"`, which turned Pythia's own set numbers into `LHAPDF6:5` | user, 2026-09-30 |
| **V41** | **Labels follow TLatex's rules in both backends.** ROOT subscripts only `_{…}` (checked by drawing: `PDF4LHC21_40` and `E_T` are drawn as written), but the yoda backend put any word with `_` into mathtext, so `PDF4LHC21_40_pdfas` came out as subscripts. Now `latex()` makes only `_{…}`, `^{…}` and `#<name>` math and writes a literal `_` inside math as `\_`. The escapes `\_ \^ \#` give the character (for ROOT through `plot.root_text` when Paint's page TOML is written; before a brace as `#kern[0]{_}`). A TOML error about a backslash now hints at single quotes. | the user's `"PDF4LHC21\_40\_pdfas"`, a TOML error | user, 2026-09-30 |
| **V42** | **`[quantities.<q>].exclude = [i, …]`**: values a sweep leaves out, by their 1-based place (the user's choice, matching `static = "#2"` and `--points`). `sweep.kept` filters each axis; an entangled group loses a value any member excludes; `static` is unaffected. Remaining points keep their names and identities, so nothing reruns. | — | user, 2026-10-01 |
| **V43** | *(superseded by V45 and V46)* **One serial, before the run's name**: `<P>/NN_<run name>/<cfg name>/<point>`, NN the configuration's `serial` if it sets one, else `[run]`'s (`tools.run_dir`). Was `<P>/NN_<run>/NN_<cfg>/`. A location, never an identity: existing results stay where they are, and a configuration whose folder moved runs again in the new place. | two serials, `03_eic/01_pdf` | user, 2026-10-01 |
| **V44** | **`[plot].use_data = false`** turns the reference data off while `[plot.data]` stays in the file (still checked); with `ratio = true` each page's ratio is over its first curve, the first value of its curve axis (Paint's and mkhtml's own rule without data). | delete the table to drop the data | user, 2026-10-01 |
| **V45** | **`<P>/<run name>/NN_<cfg label>/<point>`** (supersedes V43's `NN_<run>/<cfg>`): the serial (the configuration's, else `[run]`'s) goes before the configuration's folder, named by its new `label` (the table key when empty or unset). A location, never an identity. | V43 | user, 2026-10-01 |
| **V46** | **`[run.<cfg>].name` overrides `[run].name`** for that configuration's run folder: `<P>/<name>/NN_<label>/`. | — | user, 2026-10-01 |
| **V47** | **`.plot` titles with line breaks and YODA's macros, in both backends.** `plot.lines_of` splits at `\newline` or `\\` and closes a `$…$` left open across the break; `tlatex` joins the lines with `#splitline{…}{…}` and expands YODA's own macros (`\GeV`, `\TeV`, `\MeV`, `\pT`, `\pt`, `\dfrac`); the yoda backend writes a title that needed closing into its pages.plot (mkhtml typesets each line apart, so `$a \newline b$` failed with "Extra }, or forgotten $"). Paint sizes the legend header by its lines. | the user's d15–d17 LegendTitle: 3 of 17 yoda pages not drawn, ROOT showing `#newline` | user, 2026-10-01 |
| **V48** | **The yoda backend's ratio window is Paint's**: `ratio_window` starts from `ratio.range`, widens to every ratio drawn on bins in the x range (0.9 × (r − err), 1.1 × (r + err)), stops at `ratio.limits`, and writes `RatioPlotYMin`/`RatioPlotYMax` (the top pulled in by 10⁻⁴ of the span, as mkhtml's 1.4999). YODA's macros (`\GeV`, …) are expanded by `plot.macros` (`\mathrm{GeV}` in math, `GeV` outside) before mkhtml sees a title: Rivet's own `\GeV` uses `\xspace`, undefined in matplotlib's LaTeX, so a `\GeV` title failed to draw. | yoda: only `ratio.divisions` | user, 2026-10-01 |
| **V49** | **`legend.position = "best"`**: Paint counts the drawn points (bin centres) under the legend at each corner and takes the fewest (`placed`, `legend`); the yoda backend rewrites mkhtml's anchored legend to matplotlib's `loc='best'` and reruns the page script (`best_legend`). With `y_gutter = "default"` mkhtml's axis has no headroom, and its log range runs lower than ROOT's, so there may be no free corner; a numeric `y_gutter` gives both backends the same range and the room. | a fixed corner overlapping the curves | user, 2026-10-01 |
| **V50** | **The yoda legend title follows `text.header`**: matplotlib sizes a legend title from `legend.title_fontsize`, else `font.size`, never from the entries' `legend.fontsize`; the backend sets it beside `LegendFontSize`. | the title stayed at 10 pt | user, 2026-10-01 |
| **V51** | **Titles, the legend header and overlays; parents and children.** `title` (centred above the frame), `title_left`, `title_right` (over its corners) and `legend_header` are valid in `[plot]` for every page and in `[plot.object."<glob>"]` / `[plot.overlay.<name>]` for theirs: a child inherits and may override, and a key means the same at both levels. The `.plot`'s `Title` is the title and its `LegendTitle` the header in both backends (Paint had drawn `Title` as the header, mkhtml above the frame). Paint grows its top margin only by the titles drawn; yoda blanks mkhtml's own `Title` and adds the three to each page's script (tight bounding box). `[plot.overlay.<name>]`: several objects of each point on one page; yoda renders it in an mkhtml run of its own (mkhtml rebuilds its whole output folder), each object copied under one path, `/overlay/<name>`. Also: `<` and `>` in yoda text are set as math (LaTeX's text font prints `>` as ¿). | the legend header was the only title | user, 2026-10-03 |
| **V52** | **Tests read frozen configs, never the user's** (audit 1, P0 S1). `$HEKIT_CONFIGS` (`paths.configs_root`) replaces `configs/` as the root of `config`, `master`, `baseconfig`, `filters` and `root_style`; `tests/conftest.py` sets it to `tests/fixtures/configs/` (copied from `configs/` at 59f71da), and sets `HEKIT_OUTPUT`/`HEKIT_RESULTS` unconditionally (`setdefault` let a shell's own values through) and an absolute basetemp. The guard fails on a change to `tests/fixtures/` or `tests/reference/` (content hashes) and lists, without failing, changes under `results/`, `configs/` and `modules/`, which the user edits while tests run. The integration tests' seven copies of the run helper are `tests/support.py`; the runner tests' `plans`/`plans_of` are in `helpers.py`. | about 25 tests loaded the user's live configs and failed whenever they were edited or stashed | user, 2026-10-03 |
| **V53** | **One rank table, and the label helpers in a module of their own** (audit 1, P0). `RANKS` and `PLUGINS_MAY_IMPORT` live in `runner/__init__.py` alone; `test_imports.py` reads them and `test_docs.py` holds 02 §3.1 to them (there were three tables, which disagreed: `status_client`, never written, closes F10). `runner/labels.py` (rank 1) holds what the plot stage and its backends share about text: `.plot` keys (`labels_of`), YODA's macros, `lines_of`, `tlatex`, `root_text`; `plot.py` re-exports them. The yoda backend imported `runner.plot` (rank 4), which a plugin may not; it imports `labels`. `test_plot_stage` reads the expected log axis from the built `.plot` instead of assuming the committed one. | `test_imports` failed on the backend's import; three rank tables | audit 1, 2026-10-03 |
| **V54** | **Quick correctness fixes** (audit 1, P0 S3). Rivet options follow parent → child: the table's `options`, then the analysis's own inline `NAME:OPT=V`, then quantities (the table's had beaten the inline value). A custom or module `executable` is built under `build/<project>/` or refused; `path:<command>` asks for a command on `PATH` by name (a missing build had silently run a same-named command). `[card] seed_range` per tool folder: a point's seeds come from the intersection over its seeded steps; the default is Pythia's 1 … 9·10⁸, so every seed is what it was; `manual_seed`'s upper bound is checked when the point is planned. `[plot]` is validated before any point is planned. `hep make`; options and positionals in any order. A file's sha256 is computed once per process; under `sweep_runs` each run starts from the plan made up front unless the TOML was edited since. The combined card of an `append` tool carries the base cards' settings without comments or blank lines (`[card] drop`, `trailing`, `drop_inside_braces`). Dead code removed: `[defaults]` in `filters.toml` (F13), card style `prepend` (F12). | audit 1 C4a, C8, C12, C11, C15, L10, L13, L14a | audit 1, 2026-10-03 |
| **V55** | **One schema, and "default" = keep it as it is** (audit 1, P1 S1; the user's rule, 2026-10-03). `utils/Env/schema/run.toml` holds every run-TOML key once: type, choices, bounds, the runner's default, inheritance and whether it takes `"default"`; `runner/schema.py` (rank 0) checks every table against it, and `config.py` and `plot.py` keep only the rules that span keys. `[plot]` and its children are checked when the file is read (C11). `make schema` writes `run.schema.json` for an editor (`test_docs` holds it current, and 04 to the schema). `"default"`: in a child (`[run.<cfg>]`, `[plot.object]`, an overlay, a style layer) it is the parent's value; at the top level nothing is set and the tool decides. This replaces V37's meaning, where an object's `"default"` overrode `[plot]` with the tool's value. Paint keeps no runner defaults: a page key left out is ROOT's own behaviour (no gutter, no auto range); the runner writes every key it sets. A gutter of `0` is no headroom, no longer a second spelling of `"default"`. The runner stays standard library (02 §3.1): the schema is checked by its own 100 lines, not `jsonschema`. | audit 1 C2, C5, C11; B1 | user, 2026-10-03 |

**v1 decisions these overturn:**

| v1 | Overturned by |
|---|---|
| D1, D4 (Python over an in-process C++ loop) | V2 |
| D7, D14 (YODA only) | the brief's "ROOT primary" |
| D8, D13 (event store) | V2 |
| D9 (mkhtml and mplhep; Paint retired) | the brief's Paint; V10 keeps mkhtml as the second backend |
| D10 (CMake) | V6 |
| D16 (the namespace house style) | V7 (with two headers, it no longer applies) |
| D17 (legacy archived in the tree) | V20 |
| D21 (identity seeds) | kept, simplified (V9, V22) |

---

## 3. The knowledge ledger

What v1 learned by running things, which its deleted code carried implicitly. The evidence column
names paths **at the tag `rework/v1-final`** (read them with `git show rework/v1-final:<path>`), and
the last column the v2 phase that had to honour the row. Every row is now honoured by code that
cites it.

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
| **L26** | **A test whose fakes have a different type from the real thing hides bugs.** Sherpa/Whizard/MadGraph setting sweeps crashed while their tests passed (F1). | §5 | all |
| **L27** | **What sets a Pythia → Rivet point's pace** (2026-09-29, ZEUS_2012 card, i7-13700K, 24 hardware threads): one Rivet process reads ~1,500 events/s (13.3 s per 20k; 4.3 s of it is reading HepMC). App_Pythia with `processAsync = off` wrote ~2,200 events/s whatever its threads (40k events: 4 threads 17.7 s at 217 % CPU, 20 threads 20.5 s at 622 %): the callback was serialised, so the machine sat at ~4 %. With V31's App_Pythia, one output still caps at ~3,600 events/s (formatting holds that output's lock), while dealing to 8 outputs at 12 threads gives ~14,600; the whole chain at 12 threads + 10 shards runs ~9,200 events/s steady (5.9× the 1,570 of the last unsharded run), and more of either does not help. Start-up is ~5 s. | measured by hand | V31 |
| **L28** | **Each output must end on the latest σ.** A shard's Rivet, like any CLI Rivet, normalises to the σ of the last event it reads (L2); with events dealt, each shard's last event carried the running σ of its own moment, and `rivet-merge -e` kept their mean: 2.2e-4 off the unsharded result at 4,000 events, 1 thread, 10 shards (`test_inproc_equals_the_chain_at_one_thread`). App_Pythia now writes each output one event late and stamps every output's held event with the σ of the last event stamped. One output at one instance is untouched: still byte-identical to the legacy pipeline. | `test_app_pythia.py`, `test_gates_shards.py` (slow) | V31 |
| **L29** | **SISCone keeps two pieces of process-wide state**, so two threads clustering at once is a data race (the mechanism behind L16): the `ranlux` random generator that draws each particle's 96-bit reference (`ranlux.cpp`: 0 of 4 concurrent threads drew a clean sequence), and `Ceta_phi_range::eta_min/eta_max`, which each clustering sets from its own particles (`split_merge.cpp`; with the generator alone per thread, four Rivets stopped with FastJet's *trying to recombine an object that has previously been recombined*). Both made `thread_local` (`utils/Env/patches/`); FastJet's `--enable-limited-thread-safety` covers neither, and it would change FastJet's ABI for Rivet, Herwig/ThePEG and Whizard. With the patch a single-threaded Rivet is byte-identical, and 4 Rivets on threads equal 1 exactly. | `test_modules_p4.py` (slow), by hand 2026-09-29 | V34 |

---

## 4. Validation rules

C1–C14 are the plan-time checks. Their full statement, and the message each gives, is the
reference's: [04_Config_Reference.md §13](04_Config_Reference.md#13-validation-rules).

---

## 5. Findings

Numbered while measuring (F1–F9, 2026-09-26) and while writing this manual (F10–F14). Most of F1–F9
were resolved by deleting v1; each is kept for its lesson.

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
| **F10** | `status_client.py` is in the runner's rank table (`runner/__init__.py`, `tests/runner/test_imports.py`) and was documented as the Python client of the status protocol, but it was never written. | `ls utils/Env/runner/` | **closed by V53**: removed from the rank table (`RANKS`, now in `runner/__init__.py` alone); [05 §19](05_Tools_Reference.md#19-statushh-and-the-status-protocol) shows the protocol inline |
| **F11** | The master mapping form `render = "fn"` is described in `master.toml`'s header, but the runner refuses it ("render mappings arrive with their tool"). Tools with a `render.py` take plain `key` mappings and apply them themselves. | `tools._render`, `apply` | open; the reference documents `key`, `keys` and `flag` only |
| **F12** | Card style `"prepend"` passes the folder check but raises when a folder uses it; Whizard's point-card-first dialect is a `render.py`. | `tools.CARD_STYLES`, `_render` | **closed by V54** (removed) |
| **F13** | `filters.toml`'s `[defaults] last_line = true` is never read: the last log line is always shown. | `status.Reader` | **closed by V54** (removed from the folders) |
| **F14** | The venv still holds v1's editable `hekit` install and its dead `hep` entry point, shadowed by `utils/Env` on `PATH`. | `utils/Env/hep_env.sh` comment | open: the venv is the user's |

---

## 6. v1's findings and decisions, as the code cites them

The full text is at `rework/v1-final:docs/rework/00_Audit.md` (findings) and
`…/10_Roadmap.md` §2 (decisions).

**Findings (`00/Bn`)**

| # | What | What it means now |
|---|---|---|
| 00/B5 | ZEUS data were overlaid **by histogram name** onto different observables (ZEUS `d08` is not `photo_eic`'s `d08`). Nothing complained. | reference data only through an explicit `[plot.data].map` (L18) |
| 00/B13 | Two configs disagreed about `Photon:ProcessType`: with `photo_ep.cmnd`, 0 and 1 give identical events. | L23; eic's `process` configuration is a null comparison |
| 00/B14 | A config declared Rivet options the analysis does not take: identical curves, silently. | C9 (L19): every option is checked against the `.info` |
| 00/B18 | Every path was relative to the working directory. | one convention root per key; `./` is the repo root (V13, 04 §2) |
| 00/B25 | SISCone plugin leak in `photo_eic` (`delete_plugin_when_unused` never called). | fixed in the plugin |
| 00/B26 | η acceptance "inverted" for `orientation = −1`: verified **not** a defect (Rivet normalises an inverted range); the cut is written symmetrically anyway. | — |
| 00/B27 | The base card's `pTHatMin = 6` GeV sits above the jet `ETMIN = 5`: the lowest E_T bins are biased. | L23; eic's `pthatmin` configuration measures it |
| 00/B29 | Reading a YODA resets `LC_ALL` to `C`. | L17: `encoding="utf-8"` on every text read and write |
| 00/B30 | With `photo_ep.cmnd`, ProcessType 0 and 1 give identical events, 2 fails `init()`, 3 only changes MPI: the direct contribution needs its own card. | L23 |
| 00/B31 | FastJet's SISCone keeps **process-wide statics** and a global RNG; a race changes the jets rather than crashing. | L16: a threaded module that clusters must not share them |
| 00/B32 | `PythiaParallel` runs the callback on worker threads in both modes; an exception would reach `std::terminate`. | L3: App_Pythia catches in the callback and rethrows on the main thread |
| 00/B33 | A preflight that opened a FIFO for reading hung for ever: nobody writes to it. | anything that checks inputs must not open a FIFO (`bots/intent.md` U8) |
| 00/B34 | The PDG lookup returned an antiparticle's charge with the particle's sign (`charge3(-211) = +3`). | a module that needs charges uses `Pythia8::ParticleData` or HepMC3 |
| 00/B35 | A Δφ wrapped with a `while` loop never ends for ±∞ (HepMC3's own `delta_phi` too). | wrap with `std::remainder`, or check finiteness |
| 00/B37 | The `Requires: ONNX` convention had never been run; its include path was wrong for a source build. | the `rivet-build` rule adds the ONNX flags when the `.info` says so (L20) |
| 00/B38 | A cache keyed only on the install root served a stripped shell's answer to a normal one. | L22: `build/flags.mk` records the paths of every `*-config` it used |
| 00/B39 | MadGraph opens a browser from a batch run (`automatic_html_opening`). | `set automatic_html_opening False` in both MadGraph cards |
| 00/B40 | A module's options could not be swept: the value changed a directory name and nothing else. | a quantity with `target = "<module tag>"` sets a key of its config (04 §8) |
| 00/B42 | Module and Rivet histograms landed in one file with different normalisation: Rivet writes densities. | L21: a module plotted beside Rivet scales with `"width"` |
| 00/B44 | Editing a `.info` or `.plot` did not re-copy it into the build tree. | the copies are real make targets (06 §2) |

**Decisions (`Dn`)**

| # | Decision (v1) | Now |
|---|---|---|
| D3 | Physics in native cards, not TOML | kept: 01 §2.2 |
| D9 | `rivet-mkhtml` + mplhep; the `.plot` file as the label source | the `.plot` file is still the one label source; mkhtml is the second backend (V10) |
| D13 | Sharded HepMC3 store + JSON index | overturned (V2); a kept event file is a `[prelim] files` entry |
| D14 | YODA for Rivet and modules, one `analysis.yoda` | overturned: a module writes its own ROOT file |
| D15 | ROOT for processing only | overturned: ROOT is the primary graphics (the brief) |
| D20 | PhotoProduction is a test bed: correctness required, physics choices not blockers | kept |
| D21 | Identity-derived seeds, disjoint blocks | kept, simplified (V22) |
| D22 | Partial outputs named differently; atomic renames | kept: `*.partial.*`, `.complete` last (02 §11) |
| D-Q7 | Cross-generator photoproduction: match EPA Q²max, the photon PDF, the proton PDF and the order | L24 |

---

## 7. Risks

The risks of the rework, with how each ended.

| # | Risk | Likelihood | Impact | Response | Where |
|---|---|---|---|---|---|
| **R1** | **σ normalisation**: a CLI Rivet takes σ from the last event, and each Pythia thread stamps its own (L2, F6) | certain unless handled | every absolute number is wrong at threads > 1 | App_Pythia's writer stamps the combined σ; a gate at threads = 4 against the sidecar to 1e-6; fallback `rivet -x` | P1 S1 |
| **R2** | **FIFO failure modes**: deadlock at open, and a partial result that looks complete (L8) | high | a hang, or a wrong result | process groups, stall timeout, the sidecar count check, `.complete` written last; a failure-injection suite | P1 S2–S3 |
| **R3** | **Nothing runs between P0 and P1 S2.** *Accepted.* | certain | the user cannot run studies for that span | v1 stays one command away: `git worktree add ../High-Energy-v1 rework/v1-final`, then build it there with its own CMake | P0 |
| **R4** | **Lost in-process speed** (v1's sharded Rivet was 1.67×; the chain adds HepMC serialisation). *Accepted.* | certain | low: `photo_eic` could never shard in-process (L16); separate processes can (V31) | one timing baseline from v1 before the delete (P0 S1), compared once in P1 | P0, P1 |
| **R5** | **No sharing between points**, so an analysis-option sweep regenerates. *Accepted* (V9). | certain | CPU time | the workaround of keeping events as a file plus an analysis-only configuration; trigger for per-step identity in 02 §8 | P2 |
| **R6** | **Knowledge lost with the code** | medium | a bug v1 already fixed comes back | the ledger L1–L26; each phase file names the rows it must honour, and P4's tool steps read their rows *before* writing the plugin | all |
| **R7** | **Size overrun** | medium | medium | the budget in 07 §9, measured; over 1.5× is a finding | P4 S3 |

**How they ended:** R1 retired (σ at threads = 4 equals the sidecar to 1.3e-8, §8). R2 mitigated:
failure injection never hangs, and a stream cut short is caught by the count check. R3 closed at
P1 S3. R4 measured: 0.90× v1's in-process rate. R5 accepted and still true (`radius` is three
generations; `bots/intent.md` T1–T2). R6: every ledger row is cited by the code that honours it.
R7 measured: §9.

---

## 8. What has been verified

The gates, as numbers. Each is a test that still runs (`make test`, or `make test-slow` for the
ones marked slow), so a regression shows up there.

| What | Result | Test |
|---|---|---|
| App_Pythia at 1 thread against the legacy Pythia → FIFO → `rivet` pipeline | **byte-identical** YODAs (0 of 1,530 lines differ), σ = 71,422.158 pb | `test_gates_p1.py` (slow) |
| σ at 4 threads, 100k events | Rivet `/_XSEC` 75,215.52 pb against the sidecar's 75,215.52097: 1.3e-8; `/RAW/_EVTCOUNT` 99,987 = written | `test_gates_p1.py` (slow) |
| The runner against App_Pythia → rivet by hand, 100k events | byte-identical `photo.yoda`; a rerun skips | `test_gates_p1.py` (slow) |
| Failure injection | a producer or consumer killed mid-stream, an init failure while the reader blocks, Ctrl-C: no hang, the right tool blamed, no `.complete` | `test_failures.py` (slow) |
| Point and page counts | equal the legacy table for all 12 cases (e.g. `energy_pdf` 16 points, 4 pages) | `test_sweeps.py` |
| Seeds | disjoint across every eic configuration; `single`, `pdf`'s NNPDF23lo point and `inproc` share their seeds | `test_sweeps.py` |
| A rerun | 0 processes | `test_plan.py` |
| App_yd2rt | 17 of 17 objects equal YODA's own reading to 1e-12 | `test_yd2rt.py` |
| Paint against the legacy plotting | auto-range 17/17 and voided bins 17/17 equal the legacy `ydmrg` output | `test_paint.py` |
| Lambda: the module program against the Rivet analysis, same events | 21 histograms, 3,906 values equal to YODA's written precision | `test_modules_p4.py` (slow) |
| An integrated program (InprocJets) against the chain | all 17 objects equal bin for bin at 1 thread (the chain sharded 10 ways); σ equals the sidecar exactly at 4 threads | `test_modules_p4.py` (slow) |
| A sharded point against the same point unsharded (4 shards, 4 threads, 4,000 events) | RAW sums equal to 1e-9, σ equal to 1e-9 | `test_gates_shards.py` (slow) |
| Four Rivets on threads in one process against one (InProcEIC and InProcZeus, 4,000 events) | every raw sum and final bin equal; σ equal | `test_modules_p4.py` (slow) |
| Two PDFs × two seeds, combined | each merged YODA's events = its seeds' sum; one curve per PDF, from the groups | `test_gates_combine.py` (slow) |
| Four points at once against one at a time (2 PDFs × 2 seeds, threads 2) | every point's σ and raw sums equal; a failing point leaves the others to finish; Ctrl-C stops the 3 running of 4 (exit 6, no `.complete`), the 4th never starts | `test_gates_parallel.py` (slow) |
| Every output of App_Pythia ends on the same σ | a deal group of three and a copy: one σ line | `test_app_pythia.py` |
| Replicas merged by `rivet-merge -e` | 14,996 entries = 4,998 + 4,999 + 4,999 | `test_post.py` |
| Delphes | the `Delphes` tree's entries = the sidecar's written (2,000) | `test_generators_p4.py` (slow) |
| Sherpa, 18×275 LO, MPI off | σ = 9,201 ± 306 pb against v1's 9,636 ± 782 pb (0.5σ); the integration cached on rerun | `test_generators_p4.py` (slow) |
| Herwig, ep NC DIS | Rivet's σ = 29,910.68 pb = Herwig's own 29.9(3) nb | `test_generators_p4.py` (slow) |
| MadGraph → Pythia → Rivet | Rivet's σ = MadGraph's; the process directory built once | `test_process_generators_p4.py` (slow) |
| Whizard, direct photoproduction | two subprocesses integrated (1,288 ± 13 and 1,195 ± 16 pb) | `test_process_generators_p4.py` (slow) |
| Three generators on one page per spectrum | 3 points, 4 pages, 3 curves each | `test_process_generators_p4.py` (slow) |
| Both plot backends | 34 Paint pages and 34 mkhtml pages from one four-point fixture | `test_plot_stage.py` (slow) |
| A fresh clone | `hep build` in 10 s, a 50k-event point in 42 s, 17 pages with the ZEUS data | by hand, P4 S3 |
| End-to-end speed, 50k events at 20 threads | 1,312 events/s, 0.90× v1's in-process 1,455 (Rivet sets the pace) | by hand, P1 S1 |

---

## 9. Budget

The size, measured the way the plan budgeted it (by surface area, after v1's 3.3× miss). Any part
over 1.5× its budget is a finding.

| Part | v1 | Budget | At P4 (2026-09-27) | Now (2026-09-27, after P5 and V29) |
|---|---|---|---|---|
| Runner, `utils/Env/runner/` | 17,172 | 2,000 | 3,344 (1.67×) | 3,746 (1.87×) |
| Tool folders, plugins, master | (adapters 2,062) | 1,000 | 858 | 896 |
| Shell (`hep`, `run`, `hep_env.sh`, `flags.sh`) | 213 | 250 | 325 | 343 (1.37×) |
| C++ headers (`Status.hh`, `Module.hh`) | 6,546 | 320 | 535 (1.67×) | 535 (1.67×) |
| C++ apps (App_Pythia, App_yd2rt, Paint) | 291 (`hep-run`) | 1,400 | 1,248 | 1,640 (Paint 946) |
| Makefile | 691 (CMake + make) | 200 | 160 | 160 |
| **Code** | **~24,700** | **~5,200** | **6,470 (1.24×)** | **7,320 (1.41×; 0.30× v1)** |
| Tests | 33,178 | ~1,500 | 2,496 | 2,842 |

**Over 1.5×, with the cause:** the runner grew with what a tool folder can say (placeholders,
exports, prepare steps, connection checks; `tools.py` is 961 lines) and with P5 (the pre stage, the
merged sweep, `hep plot`, the style layers, two backends: `plot.py` is 652). The headers: `Module.hh`
took on the report, the sidecar reader, the standard configurations and `RootOut`.

---

## 10. Glossary

| Term | Means |
|---|---|
| **run** | one TOML under `configs/<Project>/`, with `[run]` |
| **configuration** | a named recipe in a run, `[run.<name>]`: sweeps, tools, events, threads |
| **point** | one combination of swept values: one chain of processes, one output and one results directory |
| **quantity** | a named value that can be swept or held static, `[quantities.<q>]` |
| **swept / static / active / inactive** | varied across points / held at one value / either of those, so rendered into cards / neither, so the base card's value stands |
| **entangled** | quantities in an inner list of `sweeps`: they move together, value i with value i |
| **built-in quantity** | `events` and `threads`, provided by the runner and consumed through the master |
| **replica** | a quantity with `target = "<tag>/seed"`: it only changes the seed |
| **tag / label** | a value's short, filename-safe name (in point names and `--points`) / its legend text (TLatex) |
| **selector** | how a static value or `--points` names a value: a tag, then an exact value, then `#N` |
| **tool, tool tag** | one process in the chain / the key of its `[tools.<tag>]` table |
| **tool folder, standard tool** | `utils/Env/<tool>/`, which tells the runner everything about one kind of tool / a tool with a folder |
| **custom tool** | `tool = "custom"`: any executable, with `arguments` and an extracted config |
| **module, module program** | a C++ program in `modules/<P>/`, built with `utils/Module.hh`; `tool = "module"` |
| **integrated program** | a module that runs a generator (and perhaps Rivet) itself, fed the standard tools' configuration |
| **chain, group** | the configuration's `tools` / one entry of it: tools that run together (an inner list) |
| **interface** | what connects two tools: a FIFO or file from `[prelim]`, a product, a pre product, or every point's product (post) |
| **product, partial** | a file a tool writes that is not a `[prelim]` entry: it lives in `results/` / its name (`*.partial.*`) until the point's checks pass |
| **sidecar, report** | an event producer's JSON beside its first output (written, σ, seeds) / a module program's JSON beside its product (events, ΣW, σ) |
| **count check** | a consumer's event count read back from its product, compared with the producer's sidecar |
| **prelim** | the per-point preparations: FIFOs, agreed files, commands |
| **pre / post / plot stage** | tools run once before every point / once after them / the pages, drawn last |
| **page, cell, curve** | one plot of one histogram / one cell of the `plot_points` grid (a page folder) / one point on a page |
| **variant** | one analysis-option combination of an object (`/photo_eic:R=0.4/d01-x01-y01`), drawn as a curve |
| **identity** | the sha256 of everything that decides a point's result; `.complete` holds it |
| **seed basis, seed block** | what the seeds follow (the generators' identity, V22) / a point's seeds, base … base + threads − 1 |
| **prepare step, cache entry** | a tool's slow once-per-card step (integration, `Herwig read`) / where it lives, `output/<P>/.cache/<tool>/<key>/` |
| **export, standard configuration** | a standard tool's rendered card or values, requested by a custom or module tool (`pythia_cmnd = true`) |
| **provenance, points manifest, journal** | `provenance.json` per point / `points.json` per configuration / `status.jsonl`, every status message |
| **backend** | what draws the pages: `root` (Paint) or `yoda` (rivet-mkhtml) |
| **style layer** | base.toml, the `root_style` file, `[plot.style]`, an object's style: each over the one before |
| **gutter, void, auto-range, alignment** | headroom past the data (V29) / a bin blanked across the page / x trimmed to the filled bins / the reference data cut to bins whose edges are MC edges |
