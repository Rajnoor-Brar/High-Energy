# 06 — Internals

How the framework works inside, and how to extend it without breaking its shape. Part one is the
design: components, data model, a run from command to pages, connections, identity, the caches,
status, failures and where files go (§1–14). Part two is the craft: the build, the tool-folder
contract, adding a tool, a backend or a figure class, the C++ kits and protocols, the tests and the
conventions (§15–27). The principles behind both are [01](01_Overview.md#4-principles).

---

## 1. Repository layout

| Path | Holds | In git |
|---|---|---|
| `configs/<Project>/` | run TOMLs and native base cards; optionally a project `master.toml` and style files | yes |
| `modules/<Project>/` | programs (`<Name>.cc`), shared headers, Rivet plugins (`Rivet/<x>.{cc,info,plot,yoda}` or `Rivet_<x>.cc`); `_`-prefixed folders are parked | yes |
| `utils/*.hh` | the C++ kits: `Status.hh`, `Kit.hh`, `Module.hh`, `PythiaRun.hh` (§2.2) | yes |
| `utils/App_*.cc` | single-file apps: App_Pythia, App_PythiaCheck, App_yd2rt | yes |
| `utils/Apps/Paint/` | the multi-file Paint app, and `base.toml` (the style) | yes |
| `utils/hepkit.py` | the kit for a custom tool in Python (§22) | yes |
| `utils/Env/` | `hep`, `run`, `hep_env.sh`, `flags.sh`, `stack.toml` and `stack.py` (the software stack), `quantities.toml` (the vocabulary), `latex.toml`, `schema/`, `runner/`, the tool folders, the plot backends (`yoda/`, `mpl/`), `figures/` (the figures' plugins), `patches/` | yes |
| `utils/Env/patches/` | patches this repository needs in the `~/HEP` stack, applied by hand; each file says to which source (`fastjet-3.5.0-siscone-thread-local-ranlux.patch`: `cd ~/HEP/src/fastjet-3.5.0 && patch -p0 < …`, rebuild, `make install`) | yes |
| `tests/` | `runner/` (unit), `integration/` (real processes), `cxx/`, `fixtures/` (the configs tests load), `reference/` (data the gates compare against) | yes |
| `docs/` | this manual; `stack/` (building the software stack from source, on a machine or in Docker); `audit_2/01_Health.md` (the open health check; finished audits are in git) | yes |
| `bots/` | agent rules (`BOT.md`), `intent.md` (ideas not built) | yes |
| `build/` | everything compiled: apps, `<Project>/`, `Rivet/`, `tests/`, `deps/`, `flags.mk`, `Herwig/` | no |
| `output/` | technical files per project, `output/tests/` | no |
| `results/` | products per project | no |
| `datasets/` | your own reference data | no |

The repository root is found by its markers (`configs/`, `modules/`, `utils/Env/`) or by
`$HEKIT_ROOT`, never by the working directory. `aux/`, `literature/` and the other non-framework
folders are not the framework's business.

---

## 2. Components

```
configs/<Project>/            run TOMLs and native base cards (the physics)
modules/<Project>/            your C++: programs (<Name>.cc) and Rivet plugins (Rivet/<x>.cc, Rivet_<x>.cc)
utils/
├── Env/                      ─── shell and Python ───
│   ├── hep                   the `hep` command: build → make; everything else → the runner
│   ├── run                   the runner's entry script
│   ├── hep_env.sh            the shell environment (load_hep, quit, hep_cd, hep_status, …)
│   ├── flags.sh, stack.toml  the stack: each library's flags and version, probed once → build/flags.mk
│   ├── quantities.toml       the vocabulary: what each quantity name means (shape, unit)
│   ├── schema/run.toml       every key a run TOML may hold, its type, default and meaning (V55, V90)
│   ├── runner/               the runner: one flat Python package (§2.1)
│   ├── <tool>/               one folder per standard tool: tool.toml (+ quantities.toml, render.py, filters.toml)
│   ├── yoda/, mpl/           the plot backends besides Paint: backend.py
│   └── figures/              the figures' plugins: derive.py (YODA's Python), sheet.py (pdflatex, PIL)
├── Status.hh, Kit.hh         ─── C++ ─── the status protocol; exit codes, arguments, JSON
├── Module.hh, PythiaRun.hh   the kit for module programs; App_Pythia's Pythia rules, shared
├── App_Pythia.cc             the standard Pythia tool (+ App_PythiaCheck.cc: its card check)
├── App_yd2rt.cc              YODA → ROOT, and a sweep into one file
├── Apps/Paint/               the ROOT plotting app (+ base.toml, the style)
└── hepkit.py                 the kit for a custom tool in Python
build/                        everything compiled; output/ technical files; results/ products
```

### 2.1 The runner

The runner is **one flat package**, `utils/Env/runner/`, with a declared rank for each module. A
module imports only from its own rank or a lower one, and the import graph has no cycles.
- The ranks are one table, `RANKS` in `runner/__init__.py`.
- `tests/runner/test_imports.py` enforces it, and `test_docs.py` holds the table below to it.

(v1's lesson: the half of v1 whose layering was written down and checked held; the half whose
layering was not had nine cycles.)

| Rank | Module | Owns |
|---|---|---|
| 0 | `errors.py` | `HepError(message, where, hint)`, `did_you_mean` |
| 0 | `paths.py` | the repository root (by markers, or `$HEKIT_ROOT`), the `configs/`, `output/` and `results/` roots, the path rules (04 §2) |
| 0 | `schema.py` | the run TOML's schema, `utils/Env/schema/run.toml`: every key's type, choices, bounds, default, inheritance, doc and notes; checking a table against it; the editor schema (V55, V90) |
| 0 | `hepfiles.py` | reading YODA text (1D and 2D objects, `/RAW` twins, counters; `.gz` too) and Rivet's data directories, once (V60) |
| 0 | `plugins.py` | loading a folder's Python by path, once: `render.py`, `backend.py`, `provider.py`, the figures' plugins (V61) |
| 1 | `config.py` | load the TOML, `[config].import`, `--set`, the strict schema check and the figure rules; the typed model (`RunConfig`, `Configuration`, `Tool`, `Quantity`) |
| 1 | `quantities.py` | the master TOML, static values and selectors, who consumes what (C7), provider checks (C10) |
| 1 | `sweep.py` | points from `sweeps` (grid and zip), point names, pages, `--points` |
| 1 | `labels.py` | Rivet `.plot` keys, YODA's text macros, line breaks, LaTeX → TLatex for Paint, TLatex → LaTeX for `hep migrate` |
| 1 | `events.py` | the event stream (V72): the bus, the watch socket (`Hub`), the `--journal` file |
| 2 | `tools.py` | the tool folders; per point: interfaces, connections (C6), cards, configs, exports, prepare keys, argv; seeds last; the combine command (`combiner`, `merge_files`) |
| 3 | `execute.py` | `[prelim]`, prepare steps, groups as supervised process groups, the count checks, settling products |
| 3 | `status.py` | the status and output pipes, read on a thread per tool; the filter rules; a failed tool's tail |
| 3 | `record.py` | identity, seeds, skip, provenance, `points.json` |
| 3 | `results.py` | a run's results from Python, read from `points.json` (V77) |
| 4 | `watch.py` | the reducer of events (`State`), the live and plain views, `hep watch` |
| 4 | `plot.py` | the plot stage: figures, the merged sweep, page configs, the style layers, Paint and the other backends; `hep overlay` on files |
| 4 | `post.py` | the pre, combined and post stages |
| 5 | `cli.py` | `argparse`: `run`, `plot`, `overlay`, `watch`, `check`, …; the order of events |
| 5 | `house.py` | `ls`, `explain`, `status`, `clean` (V74) |
| 5 | `migrate.py` | `hep migrate`: run TOMLs and cards rewritten in today's forms (V79) |
| 5 | `docs.py` | `make docs`: the manual's generated blocks (keys, style, commands) from the schema, base.toml and the CLI (V91) |

**Plugins:**
- A tool plugin (`utils/Env/<tool>/render.py`, `provider.py`) and a plot backend's `backend.py` may
  import only `PLUGINS_MAY_IMPORT` (`errors`, `paths`, `quantities`, `labels` and `hepfiles`), and
  never another plugin.
- The figures' plugins import nothing of the runner.

**Dependencies:**
- The runner is standard library only, plus `tomli_w` for writing TOML.
- Lazily, it loads `yaml` (Sherpa's plugin), `uproot` (the Delphes count and `hep overlay` on ROOT
  files), YODA's Python (the figures' and the backends' plugins) and PIL (sheets).
- `rich`, for the live view, is optional.

### 2.2 The C++

There are no libraries and no namespace hierarchy (V7): a few headers, and apps that each link only
what their `// requires:` line names.

| File | Is | Links |
|---|---|---|
| `Status.hh` | `Status::Reporter`: JSON lines to `$HEP_STATUS_FD`, or plain stderr; heartbeat; drop-on-full (§22) | nothing |
| `Kit.hh` | `Kit::Exit` (the one exit-code table, §11), `Kit::Args`, `Kit::Json::Object` and `Flat` (the sidecars' and reports' writer and reader) (V73) | nothing |
| `Module.hh` | the kit for module programs: argv, the config, HepMC input (file or FIFO, gz, zst), ΣW, σ, `RootOut`, the report (§21) | HepMC3, toml++, (ROOT) |
| `PythiaRun.hh` | App_Pythia's Pythia rules, which the integrated programs share: σ combination, stamping, the seed check, chunking (V63) | Pythia 8, HepMC3 |
| `App_Pythia.cc` | Pythia → HepMC3, threaded, σ combined, sidecar | Pythia 8, HepMC3, zstd, zlib |
| `App_PythiaCheck.cc` | the pythia folder's card check: Pythia's own reader on every line, one JSON line per rejected one (V59) | Pythia 8 |
| `App_yd2rt.cc` | YODA → ROOT; `--merge` | YODA, ROOT |
| `Apps/Paint/` | pages from page TOMLs and the style, many per process (§20) | ROOT, toml++ |

---

## 3. The data model

| Type | Module | Holds |
|---|---|---|
| `RunConfig` | `config` | the parsed run TOML: `path`, `project`, `name`, `serial`, `default_configuration` (None under `sweep_runs`), `configurations`, `prelim`, `static`, `tools`, `quantities`, `plot`, `master_toml`, `raw`, `sweep_runs`, `sweep_list` (`sweep_runs = ["a", "b"]`), `sets` (the `--set`s it was loaded with), `included` (what came from `[config].import`) |
| `Configuration` | `config` | one `[run.cfgs.<cfg>]`: `key`, `label` (its folder: `[run.cfgs.<cfg>].label`, else the key), `run_folder` (`[run.cfgs.<cfg>].name`, else `[run].name`), `serial`, `title`, `description`, `event_count`, `threads` (resolved), `parallelism` (and `parallelism_auto`), `sweeps`, `plot_points`, `combine`, `tools`/`pre`/`post` (lists of groups), `static` (merged), `prelim`, `swept`, `seed_type`, `manual_seed`, `origins` (where each value came from, for `--show-config`) |
| `Tool`, `Quantity` | `config` | one table each; a tool's folder-specific keys and export requests are in `Tool.extra`; a quantity's `values`, `tags`, `labels`, `styles` (a look per value), `shape`, `exclude` |
| `Point` | `sweep` | `index` (1-based; −1 pre, 0 post), `name`, `choice` (quantity → value index), `page`, `stage` (`"combined"`) |
| `Mapping` | `quantities` | how one quantity reaches one tool: `tag`, `form` (`key`, `keys`, `flag`, `option`, `config`, `seed`), `key`, `format`, `analysis`, `check` |
| `Override` | `quantities` | `(key, value, origin)`, a `NamedTuple`: what a `render.py` receives |
| `Folder` | `tools` | a tool folder: `name`, `dir`, `spec` (its `tool.toml`), `plugin` (`render.py`), `filters` |
| `Interface` | `tools` | `name`, `path`, `kind` (`fifo`, `file`, `product`, `pre`, `points`), `producer`, `readers`, `group`, for `points` the `paths` and `names` of every point, and `shard` (a shard's product: technical, not the point's) |
| `Step` | `tools` | one tool of one point: its folder, group, executable, argv, env, cwd, log, status mode, filters, inputs, outputs, products (final, partial), sidecar, count check, card lines and paths, config, prepare entry and argv, `identity_parts`, `texts` (what page texts may cite: `{opt:…}`) |
| `PointPlan` | `tools` | one point (or stage): `point`, `values`, `out`, `res`, `groups` of steps, `rendered` (every step, export-only ones included), `interfaces`, `consumers`, `identity`, `seed`, `writes` (files to write), `context`, `upstream`, `deal` (a dealt interface → its group) |
| `ToolState`, `Reader` | `status` | what the views show per tool; one process's status and output pipes, on a thread (V72) |
| `Bus`, `RunBus`, `Hub`, `Journal` | `events` | the event stream; a run's view of it under a sweep of runs; the watch socket; `status.jsonl` with `--journal` (V72, V75) |
| `State`, `PlainView`, `LiveView` | `watch` | the reducer of events, and the views that render it |
| `ToolResult`, `PointResult`, `Stopper`, `Budget` | `execute` | exits, causes and messages; the stop flag; the cores runs share (V75) |
| `Figure` | `plot` | one `[plot.figures.<key>]`: `kind` (its class), `type`, `name`, `objects`, `labels`, `table` (the page keys it sets), and each class's own: `over`, `configurations`, `op`, `x`, `y`, `table_pages`, `columns` |
| `Compared` | `plot` | one configuration of a compare figure: `ref` (`"cfg"` or `"<Project>/<config>:<cfg>"`), its `run` and `configuration` (V83, V88) |
| `Page` | `plot` | one page: its config path, output, cell, object, document, sources, variants, data, overrides, ranges, merged style, `plots` (the backend root), `overlay`, `bands` |

---

## 4. Tool categories and what the runner does with each

The brief's ten categories are informal. They matter to the runner only through **when a tool runs
and what it reads and writes**, which its tool folder declares.

| # | Category | Examples | Runner role |
|---|---|---|---|
| 1 | Providers | LHAPDF, FeynRules, SARAH | **plan-time checks**: a PDF set a quantity names must be installed (C10). No process. |
| 2 | Bridges | HepMC3, LHE | the **formats at tool boundaries**: `[prelim]` FIFOs and files; libraries the apps link |
| 3 | Process generators | MadGraph, Whizard | per-point tools writing a file, with a **prepare cache** keyed by the card |
| 4 | Event generators | App_Pythia, Herwig, Sherpa | per-point tools → HepMC; the usual head of a chain; `produces_events` (their identity is the seed basis) |
| 5 | Detector simulators | Delphes, Geant4 | Delphes: a tool reading a **file** (not streamable). Geant4 has no command line: a simulation is a module program with `// requires: geant4` |
| 6 | Analysis algorithms | FastJet, ROOT libraries | build flags only (`// requires: fastjet`) |
| 7 | Analysis applications | Rivet; module programs | per-point tools → YODA/ROOT, **count-checked** against the producer |
| 8 | Visualisation | YODA, ROOT | `yd2rt`, `plotmerge`, and the plot stage (Paint, mkhtml, matplotlib) |
| 9 | Statistics | RooFit, pyhf, uproot, ML | custom tools, per point or in `post`; no built-in fitter (V4) |
| 10 | Database | xrootd, rucio | none yet; a fetch would be a `[prelim]` command or a `pre` tool |

---

## 5. A run, from command to pages

**Planning** (`cli.build_plans`, returned as one `cli.Planned`) writes nothing:

1. **Load** (`config.load`): the run TOML and its `[config].import`s, `--set` applied to the raw table, then
   the file checked (C1–C5, C12, C14): every section, key and type against the schema, the figure
   rules, the sweeps, `plot_points` and tool lists. `threads = 0` becomes a number.
2. **Expand** (`sweep.points`): the grid of the axes, names from the tags, unique names (C11); then
   `--points` picks which to run.
3. **Plan the pre stage** (`post.plan_pre`), then **every point** (`tools.plan_point`):
   - the active quantities and their consumers (C7, C8, C10);
   - the interfaces from `[prelim]`, outputs and inputs, and the connection rules (C6);
   - each tool's card lines, config file, exports (C13), prepare key and argv.

   Nothing is spawned yet.
4. **Identity** (`record.identity`, §8), then **seeds** (`record.assign_seeds`), disjoint across the
   plan. Then `tools.finalise` writes the seed lines into the cards and lists the files to write.
5. **The plot checks** (`plot.validate`, `plot.check_texts`, `plot.check_figures`), then the
   combined and post stages' plans (`post.plan_combined`, `post.plan`).

With `--plan`, everything is printed here and nothing runs. **Running** (`cli.run_one`) goes
`post.run_pre` → `execute.run_points` → `points.json` → `post.run_combined` → `post.run` →
`plot.draw`:
- the pre stage is skipped when complete, and its failure stops everything;
- every point that is not complete runs (§5.1), `parallelism` at a time;
- each combined group runs once its own points are complete (V35);
- the post stage runs only when every point is complete;
- the plot stage (§13) draws the combined groups when there are any.

`execute.prepare` is the first write of a point.

### 5.1 One point

`execute.run_point`:

1. **Prepare the directories**:
   - write the cards and configs;
   - delete an old `.complete` (an attempt is under way) and any product left by an earlier attempt;
   - make the FIFOs fresh and touch the agreed files;
   - run the `[prelim]` commands.
2. **Prepare steps** (§9): each tool's cached slow step, if it has one and it is not cached.
3. **The groups, in order.**
   - Each tool of a group starts at once, each in its own process group, its stdout and stderr read
     from pipes and, for a standard-status tool, its status pipe too.
   - The supervisor polls them (§11).
   - After a group succeeds, it **settles**. The runner writes the sidecars of generators that
     always make what they are asked for, then runs the count checks. Then it renames the group's
     products from `*.partial.*` to their final names, so the next group can read them.
4. **Record**: the FIFOs are removed, `provenance.json` is written, and `.complete` holding the
   identity is written **last**.

A failure anywhere stops the point: its products keep their partial names, no `.complete` is
written, and the run goes on to the next point.

### 5.2 Several runs, points at once, combine

**Points at once** (`execute.run_points`, V36):
- The points not yet complete run `parallelism` at a time, each through `run_point` on a worker
  thread, with `view.for_point(plan)` as its sink.
- The main thread waits in half-second steps so that Ctrl-C gets in, and starts nothing more once it
  is set.
- `"auto"` (V75, `execute.auto_parallelism`) is `os.cpu_count() //` the costliest point's cores, set
  after planning; `execute.cores(plan)` is `--plan`'s estimate.
- Shared across points:
  - the event bus;
  - the views (a part per point, under one lock);
  - the prepare cache entries (`execute._prepare_lock`: a lock per entry and `flock` on
    `<entry>.lock`, and the `.prepared` stamp is checked again inside).

**Several runs** (`[run].sweep_runs`, V38, V75):
- `cmd_run` asks `RunConfig.runs(name)` which configurations to run, in this order of precedence:
  the named one; else `sweep_runs`'s list, or every `swept` configuration in file order; else
  `[run].configuration`.
- It plans every one first. A `HepError` names the configuration, and nothing runs.
- They then run **pipelined** (`cli._pipelined`): each run on a thread of its own, started once the
  run before has started all its points. Their points take cores from one `execute.Budget`.
- Signals stay on the main thread. There is one `Stopper`, one bus and one watch socket for them
  all, so `hep watch` follows the sweep as one stream.
- Each run emits through an `events.RunBus`, which adds `run` to its events. A run's journal takes
  only its own events. A run whose planning fails at its turn gets a `not run` pair of events
  (`cli.not_run`), so `watch.follow_file` never waits on it.

**Combine** (`post.plan_combined`, V35) plans one stage for each group of points that differ only in
`combine`'s quantities. It works as `post.plan` plans the post stage:
- a `Tool` of the `merge` folder, whose input is the group's products;
- `upstream` set to the members' identities;
- `Point.stage = "combined"`, with the group's `choice`.

The plot stage draws the groups as it draws points.

**Seeds** (`record`, V39):
- `seed_rule(plan)` is what the identity says: `"generator"`, `["manual", seed]` or `"random"`.
- `manual_seed_of` reads a seed quantity's value (the step's `replica` identity part), or else
  `manual_seed`.
- `assign_seeds(plans, rerun)` fills `plan.seed` by mode:
  - manual, with the overlap refusal over `seed_basis(plan, replica=False)`;
  - random: a complete point's provenance seed, else `secrets`, unless the point is named in
    `rerun`;
  - identity.

Stages keep the identity rule.

**Where a check lives**:

| Check | Module |
|---|---|
| C1–C5, C12, C14, the figure rules | `config` / `paths` |
| C7, C8, C10 | `quantities` and `tools._render` |
| C6, C9, C13 | `tools` |
| C11 | `sweep` |
| the style, backends, data, bands, figures and texts | `plot` |

Everything raises `HepError(message, where=…, hint=…)`; nothing else prints error text.

---

## 6. Connections

**Connections are explicit.** A tool table names what it reads (`input`) and writes
(`output_file`), by `[prelim]` names or by paths; the runner never guesses that "the HepMC of the
previous tool" is meant.

| Interface | Made by | Lives in | Connects |
|---|---|---|---|
| FIFO (`[prelim] fifo`) | the runner, fresh per attempt; removed when the point ends | the point's output dir | a writer and **one** reader **in the same group** |
| file (`[prelim] files`) | the runner (empty), then its writer; kept | the point's output dir | a writer and readers **in later groups** |
| product (any other `output_file`) | its tool, as `*.partial.*`, renamed after the checks | the point's results dir | readers in later groups; the plot stage; post tools |
| pre product | a pre tool | `…/<cfg>/pre/` | every point |
| every point's product | the points | their results dirs | a post tool (`input` naming the product) |

**The rules** (C6), checked at plan time:

| Rule | Why |
|---|---|
| A FIFO connects tools in the same group only | a FIFO needs both ends open at once: a reader in a later group leaves the writer blocked for ever (L8) |
| Between groups, the interface is a regular file | the earlier group has finished, so the file is complete |
| A FIFO has exactly one reader; fan-out is a list-valued `output_file` on the producer (V16) | two readers would split the stream, each getting some events |
| A **sharded** tool (`shards = K`) reads from a producer that can **deal** | the runner replaces its FIFO by K, the producer sends each event to one of them, and a merge step joins the K products (V31, §6.1) |
| No FIFO into a tool that is not `streamable` | Delphes skips zero-length input, which a FIFO always is (L11) |
| Every input is produced earlier or in the same group, is a `[prelim]` file, or already exists | the brief's "inexistence error" cannot happen |
| Every output has exactly one writer | two writers race |

**Standard configurations** move *configuration*, where connections move *data*. A custom or module
tool may ask for a standard tool's rendered card or values (`pythia_cmnd = true`), and that tool is
then configured without being run (04 §9.4). That is how an **integrated program**, one process
running Pythia and Rivet, gets the chain's card and seeds.

### 6.1 Sharding: one tool as K processes

A Rivet process uses one core, and in a Pythia → Rivet chain it sets the pace whatever Pythia's
threads (measured at ~1,500 events/s for ZEUS_2012). `shards = K` on the table (V31) is rewritten,
for each point, before anything else is planned:

```
[["pythia", "rivet"], "yd2rt"]         with [tools.rivet] shards = 3
  → [["pythia", "rivet.1", "rivet.2", "rivet.3"], ["rivet.merge"], ["yd2rt"]]
     pythia writes  events.s1.hepmc+events.s2.hepmc+events.s3.hepmc   (a deal group: one each)
     rivet.<i>      reads events.s<i>.hepmc, writes output/…/shards/photo.s<i>.yoda
     rivet.merge    rivet-merge -e the three → results/…/photo.yoda
```

`tools._shard` makes the rewrite:
- `<tag>.1` … `<tag>.K` are copies of the table's `Tool`;
- the producer's `output_file` gets the K members, rendered as a `+` group by `_outputs_argument`;
- a `<tag>.merge` step of the folder's `[shard] merge` tool is inserted as the next group;
- `_retarget` points quantities aimed at the table (`target`, a tag-keyed `key`) at every copy.

Every rule of §6 then applies to the rewritten chain as to any other:
- each shard is count-checked against its own share of the producer's sidecar (`written_per_output`);
- the generator's seeds follow its cards, not its argv, so the events are the same as unsharded
  (§8);
- the shards' products are technical: not the point's products, not in `points.json`, not drawn.

---

## 7. Scopes

| Scope | What runs there | Configured by |
|---|---|---|
| per run, once | load, expand, plan, checks | `[config]`, `[run]` |
| **pre**, once before every point | a download, a shared build: products every point may name; its identity is in theirs | `[run.cfgs.<cfg>].pre` |
| **per point** | `[prelim]`, the prepare steps, then the `tools` groups | `[run.cfgs.<cfg>].tools`, `[prelim]` |
| **combined**, once per group | the merge of points that differ only in `combine`'s quantities | `[run.cfgs.<cfg>].combine` |
| **post**, once after every point | seed-replica merges, the sweep in one file, fits, any statistics; handed `points.json` and every point's product | `[run.cfgs.<cfg>].post` |
| **plot**, once, last | the figures' pages | `[plot]` |

Points run **`parallelism` at a time** (V36; one after another by default), each with the
configuration's `threads`. A post stage runs only when every point is complete, because a merge or a
fit over a subset would look like the whole.

---

## 8. Identity, seeds and skip

**The identity of a point** is the sha256 of everything that decides its result:

```
identity = sha256( threads, events, the groups, [prelim],
                   for every rendered tool: its tag, tool, binary path and sha256, card lines (without
                     lines that repeat the base card's own value), base cards' sha256, flags, analysis
                     options, config values, analyses (and each plugin's sha256), the extracted config,
                     exported tools' identities, argv (with the point's directories as {out}/{res}),
                     the prepare key, replica values;
                   the seed rule; for pre, combined and post, the identities upstream )
```

It is computed from the cards **before** seeds are written into them. The seeds are then derived
and appended, so there is no circularity. What it hashes is written beside `.complete` as
`identity.json` (V57), which is what `--why` compares.

**Seeds follow the generator** (V22). The *seed basis* is the identity of the event-producing steps
alone (their cards without comments, base cards, binaries, replica values), with threads and
events. A detector simulation or an analysis downstream does not move it.

```
base  = lo + int(basis[:12], 16) mod (hi − lo + 1 − threads)    threads use base … base + threads − 1
```

`[lo, hi]` is the point's seed range: the intersection of its seeded tools' `[card] seed_range`
(V54). By default it is Pythia's 1 … 9·10⁸, which every seed came from before.

**What that guarantees:**
- Blocks are checked for overlap across the whole plan, and a clash moves up by `threads` (L4), so
  two points of one plan never share events.
- Across configurations, **the same generator set-up gives the same events**: eic's `single` point
  and its integrated `inproc` point can be compared bin for bin.
- The same point gets the same events in every run, and the thread count changes the partition, not
  the statistics (v1's D21, kept).

**How the seed reaches the tool:**
- For Pythia, the card always gets `Random:setSeed = on` and `Random:seed = base`, and at threads > 1
  `Parallelism:seeds = {base, …}`.
- Other tools get their own seed line or flag.
- The runner's seed lines come after the base card, so a seed set in the card (`Random:seed = 0`)
  never counts; `seed_type` is how to choose.

**`seed_type`** (V39; `[run]` or `[run.cfgs.<cfg>]`) chooses the base; the threads always use base … base
+ threads − 1.

| `seed_type` | base | in the identity |
|---|---|---|
| `"identity"` (default) | from the seed basis, as above | `"generator"` |
| `"manual"` | exactly the value of a quantity targeting `<tool>/seed`, else `manual_seed`: every point shares it | `["manual", base]` |
| `"random"` | drawn from the OS when the point runs (`--rerun` draws again); a complete point keeps the seed its `provenance.json` records | `"random"` |

Under `"manual"`, points whose physics differs may share a seed. Two points with one generator
set-up (the seed basis without the seed value) whose blocks overlap without being equal are
refused: they would repeat some of each other's events. The pre, post and combined stages keep the
identity rule. Every mode records the seed in `provenance.json` and `points.json`, so any point can
be repeated with `seed_type = "manual"` and its seed, or by `hep reproduce`.

**Skip-unchanged.** A point is complete when `output/…/<point>/.complete` holds its identity; it is
then skipped (`--rerun` runs it anyway). `.complete` is written last, after the count checks, so a
half-written point is never skipped. Change anything the identity covers and the points it affects
run again; change a serial and the location is new.

**No sharing between points** (V9). Every point runs its whole chain, so a sweep of a Rivet analysis
option regenerates the events for each value. The way around it today is to keep the events as a
`[prelim]` file in one configuration and analyse them in another. The designs that would share are
T1 and T2 in `bots/intent.md`.

---

## 9. The prepare cache

A tool folder may declare a **prepare step**: slow work that depends on the card but not on the seed
or the event count. Examples are Sherpa's and Whizard's integrations, `Herwig read` and MadGraph's
process directory.

- **Where it runs:** before the point's groups, as its own supervised step (with at least an hour
  before it counts as stalled), in a cache entry `output/<P>/.cache/<tool>/<key>/`.
- **The key:** the tool, its binary's sha256, the base cards' sha256 and the card lines, without the
  lines the folder says to ignore (the event count, the seed). With `key = "base"`, it is the base
  cards alone (MadGraph builds from the proc card only). So every point, replica, rerun and event
  count with the same physics shares one entry.
- **A hit:** an entry is a hit when it holds a **`.prepared` stamp**, written only after the step
  exited 0 and left its `marker` file. An interrupted integration is redone, never used.
- **In use:** `{prepared}` names the entry in argv and cards, and `--plan` shows each prepare step
  and whether it is cached. An export that needs a prepared product (`herwig_run`) runs the step on
  demand.

---

## 10. Status, events and watch

| Source | Channel | Read by |
|---|---|---|
| our apps, module programs, `hepkit` tools (`status = "standard"`) | JSON lines on the fd in `$HEP_STATUS_FD` (§22) | `status.Reader`, from a pipe per process |
| every other tool (`status = "filters"`) | its stdout and stderr, through a pipe | the same reader, matched line by line against `filters.toml` rules (§23) |
| a tool with `status = "none"` | its stdout and stderr | the last line only |

- **stdout is never the status channel**: it may carry HepMC, and it always carries chatter.
- **One reader thread per tool** (V72) reads both pipes, so a tool that prints fast never waits on a
  full pipe.
- **Runtime state stays off disk** (the user's decision). A tool's output is kept in memory (its
  last 200 lines) and written to `output/…/<point>/logs/<tag>.log` only when it fails; `--logs`
  writes every tool's whole output there as it comes.
- **A filter rule never fails a run.** The exit code does that.
- **The event stream** (`events.py`, V72). The executor, the stages and the CLI emit versioned
  events onto one bus:
  - `run`;
  - `point` (started, done/failed/stopped, skipped);
  - `tool`, `exit`;
  - a tool's own `phase`, `progress`, `xsec` and `log`, and its latest `line`;
  - `note`, `say`.

  It has three listeners:
  - **the view;**
  - **the process's watch socket**, an abstract Unix socket `@hep-watch-<pid>` that `hep watch`
    finds in `/proc/net/unix`. It sends a greeting, the current run's events so far, then every
    event live for the life of the process: a sweep of runs is one stream.
  - **the journal** `output/…/<cfg>/status.jsonl`, only with `--journal`: one file per run, for
    `hep watch --file` and replay.
- **The views.** A view is one reducer of events (`watch.State`) and a renderer on its own thread,
  the same in the run, in `hep watch` and over a journal.
  - **The live view** (with `rich`, on a terminal) shows each running point below the finished
    blocks: its heading and its time so far, then a line per running tool with progress, rate, ETA,
    σ and the last warning.
  - **The plain view** (`--plain`, or not a terminal) prints progress every few seconds.

  **A view never blocks the run** (V32). Everything it prints goes through one background thread,
  so a terminal that stops reading (a paused tab, Ctrl-S) stops the display, not the supervision.
  Both views print **one block per finished point**:

  ```
  ── point 2/4: NNPDF23lo ── ok after 1min 12s
     done → results/PhotoProduction/zeus/default/NNPDF23lo
  ```

  A failed point's block names the tool to blame, its exit and the message. A cached prepare step is
  one line in the block.

---

## 11. Failures and exit codes

A FIFO chain fails in two ways a single process does not; both are handled by construction.

**Deadlock at open (L8).** Opening a FIFO blocks until both ends are open, and a dead writer leaves
its reader blocked for ever, with no SIGPIPE. So:

- each tool runs in **its own process group**. The first nonzero exit is a failure, and after 2 s
  the rest of the group get SIGTERM, then after 5 s more SIGKILL;
- a tool **silent** for `stall_after` seconds (no log line, status message or heartbeat; default
  300) fails as stalled, and one past its `timeout` fails as timed out;
- FIFOs are made fresh per point, per attempt.

**A partial result that looks complete.** If the generator dies mid-stream, Rivet sees end of file,
finalises, and exits 0 with a plausible YODA. So:
- every event producer writes a **sidecar** (written, σ, seeds);
- every event consumer's count is **checked** against it (Rivet: `/RAW/_EVTCOUNT`, L7; a module: its
  report; Delphes: its tree);
- a mismatch fails the point with the product still `*.partial.*` and no `.complete`.

**Attribution.** When several processes die together, the report names the cause: the first process
to exit nonzero before the runner sent any signal. **A SIGPIPE death is never the cause** (its
reader went away first), even when both exits are seen in one poll.

**Ctrl-C** sends SIGINT to the running tools (SIGTERM 2 s later, SIGKILL 5 s after that) and stops
the run with exit 6. The point is left partial, and rerunning the same command resumes, since
finished points are skipped. A second Ctrl-C gets the default behaviour.

**Exit codes of our apps** (App_Pythia, App_yd2rt, Paint, module programs, `hepkit` tools). They are
one table, `Kit::Exit` in `utils/Kit.hh` (V73), and `hepkit.Exit` in Python:

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | config or card |
| 2 | usage |
| 3 | init |
| 4 | input |
| 5 | output |
| 6 | stopped, with partials written |
| 7 | stalled |
| 70 | internal |

**Exit codes of `hep run`:**

| Code | Meaning |
|---|---|
| 0 | every point done or skipped |
| 1 | a point, a stage or a page failed |
| 2 | a config error before anything ran |
| 6 | stopped by the user |

`hep check` exits 2 when any config is not well.

---

## 12. Provenance and manifests

- **`output/…/<point>/provenance.json`** (V23):
  - the point's values;
  - its identity, seed, threads and events;
  - per tool: the binary's path, sha256 and version, the argv, the card and its sha256, the config,
    and the result (exit, seconds, note);
  - the `--set`s it ran with (V77);
  - the host, platform, user, git revision and dirty flag;
  - start and end times.

  `hep reproduce` runs a point again from it.
- **`output/…/<cfg>/points.json`**: every point's values (tag, label, value), page, products,
  directories, identity, seed and whether it is complete. Post tools, the plot stage and
  `runner.results` read it, so none of them has to know the layout. It is also stored inside the
  merged sweep file.
- **`identity.json`** beside `.complete` (V57): what the identity hashed, for `--why`.
- **Sidecars and reports** travel with their products (04 §14).

---

## 13. The plot stage inside

`plot.draw(run, configuration, plans, say, others)` runs after the stages, on `--only plot`, and in
`hep plot`. Its input is the complete points only (`record.is_complete` and a YODA product).

1. **Figures.** `plot.figures(run)` reads `[plot.figures.<key>]` into `Figure`s, in file order. The
   implicit figure, `[plot].objects` as defined pages, is `_pages`' own. A figure carries every
   [plot] key marked `page = true` in the schema that it sets; `override_of` and `chosen` resolve a
   key, most specific table first, with `"default"` keeping the value below (V55).
2. **Members.** A page builder works on *members*: plans keyed by `point.name`, each with a YODA.
   Points are the usual members. Several classes build **stand-in plans** instead
   (`dataclasses.replace` of a real plan, renamed by the tags it stands for), each with a YODA of its
   own made once per change of its inputs:
   - **derived** (`point_yodas`, `derive.py`): a copy of each point's YODA with `/FIGURES/<name>`
     appended, in `output/…/plots/derived/`;
   - **merged** (`_merged`): per value of the kept axes, the members' YODAs merged by the combine
     folder's command (`tools.merge_files`), in `plots/merged/<name>/`;
   - **scan** (`_scanned`, `derive.scan_value`): per value of the other curve axes, a Scatter2D, a
     point per value of `x`, in `plots/scan/<name>/`;
   - **compare** (`compare_pages`): every compared configuration's members, renamed `<ref>_<point>`,
     their choice gaining a `@configuration` curve axis. Another run TOML's members carry their own
     run in `context["run"]`, so their labels and looks are their own.

   Each set is stamped by the sha256 of its inputs, and the figure's spec where it matters, so a
   rerun rebuilds nothing unchanged.
3. **The sweep in one file** (`merge`): every member's YODA merged by `App_yd2rt --merge` into one
   ROOT file, with a directory per member, raw entries and `points.json`. The configuration's file
   is `results/…/plots/root/<cfg>.root`; a figure with members of its own has its own file. The
   file is rebuilt only when a member's YODA changed. Reference data are converted once, into
   `output/<P>/.cache/datasets/`.
4. **Page documents** (`_pages`):
   - **Objects:** the objects of the members' YODAs (`hepfiles.objects`, `objects_2d`: not `/RAW`,
     `/TMP`, the counters or weight variations). They are keyed by the option-free path, so a swept
     analysis option's variants are curves on one page.
   - **Claims:** a declared defined figure claims its objects' pages, and two that claim one object
     are refused.
   - **The page:** a page per `plot_points` cell and object (a 2D object: per member, `_heatmap`),
     or per cell for an overlay.
   - **Its `[page]` table:** `page_settings` takes the labels from the `.plot` file under the
     figure's and `[plot]`'s values, with placeholders filled by `filler` (one value per page, or a
     curve's own).
   - **Its curves:** each with its label and look, and with a band folded by `_banded`.
   - **Written:** the style layers' changes and the mapped data. Each document goes to
     `output/…/plots/[<cell>/][<folder>/]<object>.toml` (labels through `for_root`: LaTeX → TLatex)
     and is kept in memory as a `Page`.
5. **Draw** (`_draw`):
   - **Paint:** one `Paint.exe` per `PAINT_BATCH` (200) pages, each page's outcome a JSON line;
     `--ranges` writes each page's ranges and voids beside its config for the other backends.
   - **The other backends:** they get the same `Page`s by folder (a cell's, or a figure's folder in
     it), with `output` moved to `plots/<backend>/` (`for_backend`). Heat maps are Paint's alone
     (V87).
   - **Indexes:** an `index.html` per backend tree (`write_index`, V70), where the backend writes
     none of its own.
   - **Then:** the sheet figures tile what was drawn (`sheet`, `sheet.py`). A compare figure is
     drawn by each of its own configurations' plot stages, once every configuration it names has
     complete points; `others(ref)` gives another configuration's plans (`cli.others_of`).

   A failed page is counted, and the run exits 1, but the others are drawn.

The style is a stack of TOML layers over `utils/Apps/Paint/base.toml` (V27), checked against it at
plan time (`check_style`). Keys a backend cannot honour are errors, never silently dropped (v1's
`LegendXPos` was parsed and ignored).

---

## 14. Where files go

**Technical files go in `output/`, products in `results/`, compiled things in `build/`.** A run
writes nothing else.

```
output/<P>/<run>/<cfg>/
  points.json   [status.jsonl: --journal]
  <point>/      cards/  config/  logs/  FIFOs, [prelim] files  provenance.json  identity.json  .complete
  pre/, post/, <combined group>/      the same, for the stages
  plots/        [<cell>/]<object>.toml (page configs, + .ranges.json), merged.sha256
                derived/<point>.yoda   merged/<figure>/   scan/<figure>/   yoda/ (mkhtml's work files)
output/<P>/<run>/compare/<figure>/    a compare figure's page configs
output/<P>/.cache/<tool>/<key>/       prepare caches
output/<P>/.cache/datasets/           reference data converted for Paint
output/tests/                         everything tests write

results/<P>/<run>/<cfg>/
  <point>/                            the products only
  pre/, post/, <combined group>/      the stages' products
  plots/root/<cfg>.root               the sweep in one file (a figure's own: plots/root/<figure>/, scan/)
  plots/<backend>/[<cell>/][<figure>/]<object>.<fmt>   the pages: root (Paint), yoda (mkhtml), mpl
  plots/<backend>/index.html          every page, by cell
  plots/<backend>/sheets/<figure>.{pdf,png}   sheets
results/<P>/<run>/compare/<figure>/<backend>/  a compare figure's pages
```

`<run>` and `<cfg>` are `NN_<name>` when they have a serial. `<point>` is the swept tags joined by
`_`, or `point`. `datasets/` (your reference data) is not in git; Rivet's own are `rivet:<Analysis>`.

---

## 15. The build

`Makefile`, `utils/Env/flags.sh`, and `hep build` = `make all`. No CMake (V6).

### 15.1 The rules

The target is written the way the source is, and the output lands where the convention says:

| Source | Target | Output | Include path |
|---|---|---|---|
| `utils/App_<X>.cc` | `utils/App_<X>.exe` | `build/App_<X>.exe` | `-I utils` |
| `utils/Apps/<X>/main.cc` | `utils/Apps/<X>.exe` | `build/<X>.exe` | `-I utils -I utils/Apps/<X>/` |
| `modules/<P>/<X>.cc` | `modules/<P>/<X>.exe` | `build/<P>/<X>.exe` | `-I utils -I modules/<P>` |
| `modules/<P>/Rivet/<x>.cc`, `modules/<P>/Rivet_<x>.cc` | `….so`, or `rivet_<x>` | `build/Rivet/Rivet_<x>.so` + `<x>.info`, `.plot`, `.yoda` | `rivet-build … -I utils -I modules/<P>` |
| `tests/cxx/<X>.cc` | `tests/cxx/<X>.exe` | `build/tests/<X>.exe` | `-I utils` |
| any other `<dir>/<X>.cc`, named | `<dir>/<X>.exe` or `.so` | `build/<dir>/<X>.exe` or `build/<dir>/lib<X>.so` | `-I utils` |

- **Aliases:** the typed target is a phony alias of the real file in `build/`, so make's up-to-date
  check works on the real file.
- **Header dependencies:** `-MMD -MP` writes them to `build/deps/`. Editing `Reconstruction.hh`
  rebuilds `Lambda.exe` and `Rivet_Lamriv.so`.
- **Rivet plugins:**
  - a plugin's `.info`, `.plot` and `.yoda` copies are real targets: editing one re-copies it
    (00/B44);
  - a `.info` saying `Requires: ONNX` adds the ONNX flags (00/B37, L20).
- **`make all`** builds:
  - every non-parked `modules/<P>/*.cc` program and `modules/<P>/Rivet/` plugin (a subfolder of a
    project holds headers);
  - every app;
  - `build/Herwig/HerwigDefaults.rpo` (`Herwig init --repo=…`, when Herwig is on `PATH`; a failure
    warns and leaves no file, L15).
- **Other targets:**
  - `tests` (the C++ tests);
  - `test` (build and run them, then pytest without the slow tests);
  - `test-slow`;
  - `configure`;
  - `list` (everything `all` builds);
  - `schema` (the editor schema, V55);
  - `docs` (the manual's generated blocks, V91);
  - `clean`.
- **Compiler:** `CXX` (default `g++`), `CXXFLAGS` (default `-O2`), always `-std=c++17`.

### 15.2 `// requires:`

A source names its libraries in a comment near the top; a trailing `(…)` is a note:

```cpp
// requires: pythia8 hepmc3 fastjet   (the kit adds hepmc3 toml)
```

| Name | Flags from |
|---|---|
| `pythia8` | `pythia8-config --cxxflags --ldflags` |
| `hepmc3` | `HepMC3-config --cflags --libs` |
| `yoda` | `yoda-config --cppflags --libs` |
| `root` | `root-config --cflags --libs` |
| `fastjet` | `fastjet-config --cxxflags --libs --plugins=yes` |
| `lhapdf` | `lhapdf-config --cppflags --ldflags` |
| `rivet` | `rivet-config --cppflags --ldflags --libs` |
| `geant4` | `geant4-config --cflags --libs` |
| `toml`, `zstd`, `zlib` | `pkg-config tomlplusplus`, `libzstd`, `zlib` |
| `onnx`, `delphes` | `$ONNXRUNTIME_DIR`, `$HEP_INSTALL/delphes` |

- `none` links nothing.
- **No line** links every library that was found: a quick manual compile keeps working, just slower
  to link.
- `#include "Module.hh"` adds `hepmc3 toml`.
- An unknown name, or a name whose `*-config` was not found, is a make error saying which.

### 15.3 The flag cache

**The stack is one file**, `utils/Env/stack.toml` (V78). For each library and program it gives:
- the command that prints its flags (or, for a library with no `*-config`, its install directory and
  library);
- the command that prints its version (or a `{ file = … }` to read it from).

A new library is one entry there. `utils/Env/stack.py` reads it:
- for `flags.sh` (its probes);
- for the tool folders (`[identity] version = "stack:<name>"`, the version in a point's provenance);
- for `hep status --stack`.

`hep_env.sh` keeps its own list: it runs at login and stays bash-only.

`build/flags.mk` holds every library's flags, `FOUND` and `KNOWN` (the stack's libraries: what a
`// requires:` line may name).
- It is written by `utils/Env/flags.sh`, which runs each `*-config` once.
- It records a key: the resolved path of every `*-config` it used, the two install directories, and
  the stack file's checksum.
- Make recomputes the key on every call and rewrites the cache when it differs (L22: a cache keyed on
  less than it reads is a correctness bug). `hep build --configure` forces it.
- `build/flags.log` records each probe.

**Run make with the environment loaded** (`load_hep`): without it, the probes find nothing, and the
cache is rewritten with every library missing.

---

## 16. The tool-folder contract

Everything the runner knows about a kind of tool is in `utils/Env/<tool>/`. The core never names a
tool, so adding one is adding a folder.

```
utils/Env/<tool>/
  tool.toml        required   what the tool is and how to run it
  quantities.toml  optional   how it consumes the vocabulary's quantity names (V58)
  render.py        optional   the whole point card, for dialects [card] cannot write
  filters.toml     optional   stdout rules, for a tool without the status protocol (§23)
```

### 16.1 `tool.toml`

Every section and key is checked when the folders load: an unknown one is an error.

| Section | Key | Means |
|---|---|---|
| `[tool]` | `category` | one of the ten (§4), for reading |
| | `executable` | a command on `PATH`, or `{repo}/build/…` for our apps (must exist: "not built, run hep build") |
| | `streamable` | may read its input from a FIFO (default false) |
| | `status` | `standard`, `filters`, `none` (default none) |
| | `consumes_events` | its product's event count is checked against its input's producer sidecar |
| | `produces_events` | an event generator: its identity is the seed basis, and its `[outputs] sidecar` is its sidecar |
| | `config_file`, `config_always` | its table's `config`, consumed quantities and standard-configuration requests go to `config/<tag>.toml`, its first argument, and it may ask for exports (custom, module); `config_always`: even when empty (module) (V60) |
| `[card]` | `style` | `append` (base cards then the point card: last wins), `render` (`render.py` writes the whole card), `none` (no card; values become flags or options) |
| | `ext`, `comment` | the card's extension and comment marker (`cmnd`, `!`) |
| | `bools` | how true and false are written (default `["true", "false"]`; Pythia `["on", "off"]`) |
| | `line` | one value's line (default `"{key} = {value}"`; `"set {key} {value}"` for ThePEG and Tcl) |
| | `footer` | lines after the values (placeholders `{output_name}`, `{tag}`, `{input}`); a line whose placeholders are all empty is left out |
| | `seed`, `seed_parallel` | seed lines, after everything (`{seed}`; `{seeds}`, the block, only at threads > 1) |
| | `seed_range` | `[lo, hi]`: the seeds the tool accepts (default `[1, 900_000_000]`, Pythia's); a point's seeds come from the intersection over its seeded steps (V54) |
| | `merge`, `repeatable`, `owned` | `merge = true`: the combined card holds each key once, parsed with the folder's `line` (V59); `repeatable`: commands kept every time (Pythia's particle-data `onIfMatch`, …); `owned`: keys the runner sets: a base card's value of one is reported by `--plan` (append), or refused by `render.py`, which gets the list as `context["owned"]` (V61) |
| | `drop`, `trailing`, `drop_inside_braces` | how the combined card leaves out a base card's comments (V54): `drop` a full-line comment (a regex; default: a line starting with `comment`), `trailing` a comment after a value, `drop_inside_braces = false` keeps comment-looking lines inside `{ … }` (Tcl) |
| `[command]` | `argv` | the argv template (04 §10); default `["{exe}"]` |
| | `env` | extra environment (`RIVET_ANALYSIS_PATH = "{repo}/build/Rivet"`) |
| | `cwd` | where it runs (default the point's output directory; Whizard: `{prepared}`) |
| `[options]` | `<key> = { kind, required, flag, default }` | the tool-specific keys a table may carry; `kind` is `list`, `table`, `str`, `int`, `float`, `bool` or `flag` (`flag = "-e"`, `default`); every option is also a placeholder |
| `[outputs]` | `products` | the kinds it writes (for reading) |
| | `event_count` | how a count is read back: `yoda:<path>` (a counter's entries), `json:<key>` (the product's report), `root:<tree>` (a tree's entries) |
| | `sidecar` | where a producer's sidecar is (`"{output}.json"`) |
| | `written` | `"requested"`: it always makes what it is asked for or fails, so the runner writes the sidecar after exit 0 |
| | `combines` | product suffixes this folder merges for `combine` (V35): `["yoda"]` in `merge` (V60) |
| | `deal` | `true`: its `{outputs}` may hold a deal group (`A+B+C`: each event to one member), so it can feed a sharded tool; its sidecar must then carry `written_per_output` |
| `[prepare]` | `argv` | the prepare step (`{repo}`, `{exe}`, `{card}`, `{prepare_card}`, `{prepared}`, `{out}`), run in the cache entry |
| | `marker` | a file the step must leave; the `.prepared` stamp is written only then |
| | `ignore` | card keys left out of the cache key (`EVENTS`, `n_events`, `seed`) |
| | `key` | `"card"` (default) or `"base"`: key on the base cards only |
| `[exports.<name>]` | `alias = "card"` | `<tool>_<name>` is `<tool>_card` |
| | `values` | values handed over: a template (`plugin_path = "{repo}/build/Rivet"`), or `"identity:<part>"` for a part of the tool's identity (`analyses = "identity:analyses"`) (V60) |
| | `path` | a path handed over (`{prepared}`, `{card}`) |
| | `needs_prepare` | asking for it runs the prepare step on demand |
| `[identity]` | `files` | files whose sha256 enters the identity (`{repo}`, `{exe}`, `{analysis}`) |
| | `version` | a command whose first line is the version, or `"stack:<name>"` (the stack's, V78), for provenance |
| `[shard]` | `merge` | the tool folder that joins K shards' products into the table's `output_file`; without it, `shards` is refused (rivet: `merge`, i.e. `rivet-merge -e`) |
| `[beams]` | `slots` | the card's fixed beam slots, `["lepton", "hadron"]` (Herwig): the run's per-beam values are reordered into them (V62); without it a tool takes `[beam A, beam B]` as given |
| `[render]` | (free) | data for the folder's `render.py`, handed over as `context["render"]` (MadGraph's `[render.lpp]`, PDG → lpp) (V61) |
| `[checks]` | `files` | files that must exist at plan time (C10) |
| | `card` | argv that reads a card (`{card}`) and prints one JSON line `{"line": N, "text": …}` per line it rejects; run at plan time, cached by the card's text (V59) |
| | `info_dirs`, `info_dirs_command` | where analyses' `.info` files are, for C9 |

`<tool>_card` is exported automatically by every folder whose card style is not `none`.

### 16.2 `render.py`

For a card that is a tree, a script, or a launch file. It is plain functions:

```python
from runner.errors import HepError        # PLUGINS_MAY_IMPORT only (runner/__init__.py, test_imports.py)

def card(bases: list[str], overrides: list, context: dict) -> str:
    """The whole point card, before seeds. `bases` are the base cards' texts in order; each override
    is the runner's Override(key, value, origin), in order; context has point, tag, output_name,
    output, base_paths, owned ([card] owned) and render (the folder's [render] table). The runner adds
    a header comment, the [card] footer and the seed lines."""

def prepare_card(lines: list[str], bases: list[str], context: dict) -> str:   # optional
    """The card the prepare step reads ({prepare_card}), from the final point card's lines
    (seeds included); context has prepared, base_paths and tag."""

def options(extra: dict, targeted: dict, context: dict) -> dict:             # optional (V60)
    """A tool's own handling of its table's keys (rivet: its analyses and their options). `targeted`:
    analysis → {option: value} from quantities; context has tag, bools, native, info_dirs. Returns
    identity (parts), config_data, placeholders (for argv), identity_values (the names
    [identity] files expands, e.g. {"analysis": [...]}) and texts (what page texts may cite)."""
```

**Providers:** a provider (`utils/Env/<name>/provider.py`, V60) is a folder with no `tool.toml` and
one function, `check(form, value, where)`, which a mapping names as `check = "<name>:<form>"`
(`lhapdf:pythia`). `tests/runner/test_imports.py` fails if a core module names a tool or a provider.

**What a plugin receives:**
- A value reaches a `render.py` through a plain `key` mapping (the master's or a quantity's). The
  key means what the plugin says: a YAML path for Sherpa, a SINDARIN variable for Whizard.
- Refuse a base card that sets what the plan owns (seeds, events, outputs, beams): it would silently
  win or lose.
- Test it with the runner's own `Override` (L26).

### 16.3 How the runner uses a folder, per point

1. **Options**: the table's extra keys are checked against `[options]` (C1), and the `required` ones
   must be present.
2. **Card**: the built-in and quantity values that reach this tool (04 §8.1), each through its
   `Mapping`:
   - `key`/`keys` become card lines (`[card] line`);
   - `flag` becomes argv;
   - `option` an analysis option;
   - `config` a config key;
   - `seed` a replica.

   Then come the header, the lines and the footer; for `render`, `card()`. The seed lines are added
   at `finalise`, after the identity.
3. **Prepare key and argv**, if `[prepare]`.
4. **argv**, `env` and `cwd` from `[command]`, with every placeholder (04 §10); a module or custom
   tool's config file.
5. **Count check**, if the tool consumes events and reads a count, and its input's producer has a
   sidecar.

---

## 17. Adding a standard tool

A worked outline, for a generator `gen` that reads a card and writes HepMC to a named file:

1. **Read the ledger** ([07 §3](07_Record.md#3-the-knowledge-ledger)) and v1's adapter if there was
   one (`git show rework/v1-final:utils/python/hekit/adapters/<tool>.py`).
2. **`utils/Env/gen/tool.toml`**:

   ```toml
   [tool]
   category        = "event-generator"
   executable      = "gen"
   status          = "filters"
   produces_events = true

   [card]
   style   = "append"
   ext     = "gen"
   comment = "#"
   seed    = ["seed = {seed}"]

   [command]
   argv = ["{exe}", "--card", "{card}", "--events", "{events}", "--out", "{output}"]

   [outputs]
   sidecar = "{output}.json"
   written = "requested"            # only if it truly always makes what it is asked for

   [identity]
   version = ["gen", "--version"]
   ```

3. **`filters.toml`**: a progress rule from a real log and an error rule; nothing that fails a run.
4. **Its quantities**: `utils/Env/gen/quantities.toml`, how it consumes the vocabulary's names
   (`energies = { keys = [...] }`, `pdf`, `events`). A name the vocabulary lacks goes into
   `utils/Env/quantities.toml` first, with its shape (V58).
5. **Its version**: an entry in `utils/Env/stack.toml`, and `[identity] version = "stack:gen"`.
6. **Tests**:
   - a **plan-time test** in `tests/runner/` (the card, the argv, a refusal), using `helpers.raw()`,
     `parse()` and `plan()`;
   - a **slow gate** in `tests/integration/` that runs a point and checks a number (σ against the
     tool's own, the count check).
7. **The docs**: its section in [05](05_Commands_and_Tools.md#3-the-standard-tools-at-a-glance), its
   row in 05 §3, and in the master table of 04 §3. `tests/runner/test_docs.py` fails if a folder has
   no section or an option is undocumented.

These questions decide the design of a folder:
- Can it read a FIFO (`streamable`)?
- Does it write σ into its events? (Whizard does not.)
- Does it write exactly what it is asked for (`written = "requested"`)?
- Is part of its work card-dependent but seed-independent (`[prepare]`)?
- Does its output path need to be relative? (Sherpa prepends `./`.)

---

## 18. Adding a plot backend

A backend is `utils/Env/<name>/backend.py`, with no `tool.toml`, loaded by `plot.backend(name)`:

```python
def validate(settings: dict, beside_root: bool = False, curve_styles: list[dict] = ()) -> None:
    """Refuse, at plan time, every [plot] key this backend cannot honour (raise HepError).
    beside_root: the root backend draws too, so Paint honours the style; curve_styles: the
    quantities' per-value looks (V67)."""

def draw(cells: dict[str, list], settings: dict, say) -> int:
    """cells: a page set, one folder of pages (a plot_points cell's, or a figure's folder in it, V82)
    → its Pages (plot.Page: config, output under plots/<name>/, object, document, sources, variants,
    data, overrides, style, overlay, bands, and ranges from Paint). Heat maps are Paint's and never
    reach a backend (V87). Draw them, report with say(), return the number of pages that failed."""

INDEX = True      # optional: the runner writes plots/<name>/index.html (the backend writes none)
```

- Add the name to the schema's `[plot.backend]` choices (`plot.BACKENDS` reads them).
- **A key the backend cannot honour is an error**, never ignored (v1's `LegendXPos`).
- The mpl backend is the example (`utils/Env/mpl/backend.py`). The yoda backend is frozen (V71).

---

## 19. Adding a figure class

A figure class is a way to build pages: which members and which objects. Drawing stays one path, a
page document, then the backends, so a new class gets ratios, bands, data, styles, placeholders,
overrides and every backend for free.

1. **Schema**: add the class to `[figure.class]`'s choices in `utils/Env/schema/run.toml`, and any
   key of its own as a `[figure.<key>]` entry. List that key in `schema.FIGURE_OWN`, so it is not
   taken for a page key, and run `make schema`.
2. **Rules**: in `config.check_plot`, add the keys it needs and the ones it refuses, refused when the
   file is read. In `plot.check_figures`, add what needs the configuration (its axes, its
   quantities), refused at plan time.
3. **`Figure`**: a field for each key of its own, read in `plot.figures`.
4. **Members**: a function that returns `(members, yodas)`: stand-in plans named by what they stand
   for, and each one's YODA, made once per change of its inputs (a sha256 stamp beside it). Arithmetic
   on YODA objects belongs in a plugin in `utils/Env/figures/` (loaded with `plugins.load`), which
   keeps the runner standard library.
5. **Pages**: in `plot.pages` (or `plot.draw`, for figures that need other configurations' plans or
   drawn pages), merge the members into their own ROOT file (`merge`) and call `_pages` with the
   figure as a `defined` one, its curve axes and its folder.
6. **Tests**:
   - a `tests/runner/test_plot.py` case per refusal;
   - an integration test in `tests/integration/test_plot_stage.py` that draws its pages from the
     fixtures.
7. **Docs**: its section in [03 §7](03_Plots.md#7-figures), and its keys' `doc` and `notes` in the
   schema, which `make docs` puts in 04 §11.2.

---

## 20. Paint inside

`utils/Apps/Paint/`:
- `main.cc`: the batch and the modes;
- `Page.hh`: the page TOML;
- `Style.hh`: base.toml and the layers;
- `Transform.hh`: void, align, normalise and the ranges;
- `Draw.hh`: the canvases.

It is built to `build/Paint.exe`, with `// requires: root toml`. Its command line is
[05 §18](05_Commands_and_Tools.md#18-paints-command-line).

**A page, in this order** (inherited from v1, and load-bearing):

1. **Load** the curves (and the `/RAW` entries when `raw` is given).
2. **Void** bins across the whole page: `void_empty` (zero in every curve) and `min_entries` (fewer
   raw entries in any curve). This applies only when the curves share one binning; otherwise there
   is a warning.
3. **Align** the reference data to the first curve's bins: its longest run of bins whose edges are
   all MC edges. Otherwise it is dropped with a warning.
4. **Normalise** (V68): with `normalise = "area"`, every curve and the data are scaled to unit area,
   Σ value × width over the bins drawn.
5. **x range**: auto-range (bins with content, plus `range_pad`) or the full range, then `x_gutter`.
6. **y range**: `(1 + y_gutter) ×` the largest drawn value within x. On a log axis, the gutter is
   that fraction of the decades shown. With no gutter it is ROOT's own choice for one histogram
   holding every drawn value (`THistPainter`): 5% of the span above, below as well unless that
   crosses 0; on a log axis ×0.5 below and ×2·0.9/0.95 above.
7. **Draw**:
   - **The MC:** steps per run of non-void bins (a voided bin is a gap), with error bars at the bin
     centres (or a band, or none). With `markers` (a Scatter2D figure, V86) each curve is instead a
     marker per bin with its error bar. A band (V69) is the members' envelope, shaded in the curve's
     colour.
   - **The data:** points with x bars, under the MC.
   - **The legend:** a "+" per entry, the header first, data first. A curve with every bin voided is
     listed as "(no entries)".
   - **The ratio pad:** each curve over the data, or over the first curve, on the reference's bins.
     Its range is at least `ratio.range`, widened to the ratios drawn within `ratio.limits`. Labels
     at the joint of the two pads are dropped.
8. **Save** each format (`pdf`, `png`, `svg`, `eps`). The PDF page is `page.size`, and the PNG is
   size × dpi.

**A heat map page** (`heatmap = true`, V87) draws one 2D object instead: a `TH2D` from App_yd2rt,
coloured by value (`COLZ`, ROOT's `kBird` palette), with its z scale on the right (`z_label`,
`logz`). It has the 1D pages' frame, titles and text sizes, and no ratio, data, voiding or ranges.

**`--dump-ranges`** prints the result of steps 1–6 as JSON and draws nothing. Its fields:
- `x`, `y`, `largest`;
- `voided` (1-based bins);
- `data_bins`, `data_x` (the aligned data span);
- `x_tool`, `y_tool` (the range is the tool's own choice: no gutter).

This is how the arithmetic is tested; `--ranges` writes the same beside each page for the other
backends. **`--dump-style`** prints the merged style as TOML (base.toml's alone, without a page).

The style is `utils/Apps/Paint/base.toml`, found beside `build/` (else under `$HEKIT_ROOT`), with
the page's `[style]` merged over it. An unknown key, or a value of another kind, is an error.

---

## 21. `Module.hh`

A module is a plain program in `modules/<P>/<Name>.cc` with its own `main()`, built to
`build/<P>/<Name>.exe`. `#include "Module.hh"` adds `hepmc3 toml` to its libraries; add `root` for
`RootOut`.

```cpp
// modules/Lambda/Lambda.cc          requires: root   (Module.hh adds hepmc3 toml)
#include "Module.hh"
#include "TH1D.h"

int main(int argc, char** argv) {
    Module::Job job(argc, argv);                        // CONFIG.toml --input= --output= --events= --sidecar=
    const double massTol = job.config().get("mass_tolerance", 0.15);
    Module::RootOut out(job.output());                  // written when the job finishes
    auto* mass = out.book<TH1D>("mass", ";m_{p#pi} [GeV];dN", 100, 1.08, 1.16);

    for (const Module::Event& event : job.events())     // file or FIFO, plain/gz/zst
        for (const auto& candidate : reconstruct(event.hepmc(), massTol))
            mass->Fill(candidate.mass, event.weight());

    out.scale(job.crossSectionPb() / job.sumW(), "width");   // once; "width" for a density (L21)
    return job.finish();
}
```

| Call | Does |
|---|---|
| `Module::Job job(argc, argv)` | parses `CONFIG.toml [--input=F] [--output=F] [--events=N] [--sidecar=F]` (`--x v` also works); reads the config; installs SIGINT/SIGTERM handlers |
| `job.config()` | a `Values` view of the config: `get(key, fallback)`, `has(key)`, `list(key)`, `table(key)`, `raw()` |
| `job.quantities()` | the config's `[quantities]` table |
| `job.events()` | iterates `Module::Event`s from the input (`HepMC3::deduce_reader`: file or FIFO, plain, gz or zst); counts events and ΣW, reports progress, stops on a signal |
| `event.hepmc()`, `event.weight()` | the `HepMC3::GenEvent`; its first weight (1 if none) |
| `job.count()`, `job.sumW()` | events read and ΣW so far |
| `job.crossSectionPb()`, `job.crossSectionErrPb()` | from `--sidecar` when given (a file chain), else the last event's `GenCrossSection` (Rivet's rule, L2) |
| `job.standard(key)`, `job.standardParts(key)`, `job.standardValues(key)` | a requested standard configuration (04 §9.4): its `path`, its `parts`, or its table; a request the table did not make is an error naming the key |
| `job.hasInput()` | false for an integrated program (empty `--input=`); `events()` is then unavailable |
| `job.countEvent(w)`, `job.setCrossSection(pb, err)` | an integrated program's own count, ΣW and σ |
| `job.progress(done, total)`, `job.status()` | status reporting (§22) |
| `job.fail(code)`, `job.stopping()` | an early exit with a `Kit::Exit` code; whether a stop was requested |
| `job.finish()` | writes every output, then the report `<output>.json` (`events`, `sum_w`, `sigma_pb`, the σ source); returns the exit code: 6 when interrupted |
| `Module::RootOut out(path)` | ROOT histograms written to one file at `finish()`; `book<H>("Dir/name", args…)` books into a directory |
| `out.scale(factor, option)` | once, after the loop (a second call is an error: fill raw, scale once); `"width"` also divides by the bin width |

- `RootOut` exists when ROOT's headers are on the include path (the source requires `root`).
- A module runs single-threaded. One that uses threads and clusters jets must not share FastJet's
  SISCone statics (L16).
- The exit codes are §11's.

**An integrated program** (`modules/PhotoProduction/InprocJets.cc`, V33) asks for `pythia_cmnd` and
`rivet_analyses` (`job.standard`, `job.standardValues`). It gets the same card and seeds as the
chain's App_Pythia would, and the rivet table's analyses with their options. It runs Pythia through
`PythiaRun.hh` as App_Pythia does, and `rivet_threads` `Rivet::AnalysisHandler`s on threads of their
own (V34). Its parts are headers in `modules/PhotoProduction/Inproc/`:

| Header | Holds |
|---|---|
| `Stamp.hh` | what every event gets before Rivet sees it: one numbering, one run info, the combined σ (L1, L2), and the last σ stamped (L28) |
| `Feed.hh` | a bounded queue from the Pythia threads to the Rivets: whichever Rivet is free takes the next event; a full feed holds generation back |
| `Analysis.hh` | the Rivets: every handler initialised on the first event before any analyses; each `analyze`s on its own thread; at the end `merge` into the first (raw fills and event counters added, before any `finalize`, so re-entrancy is not needed), the L28 σ as a user σ (`setCrossSection(σ, true)`), one `finalize`, `writeData`. Above one Rivet it checks that SISCone's state is per thread (L29) and refuses otherwise |
| `Engines.hh` | `serial` (one `Pythia8::Pythia`) and `parallel` (`PythiaParallel`, `processAsync = on`, a converter per instance, chunks of 100 × threads); after Rivet's thread starts, a failure is returned, never exited on (L3, L5, L6) |

**Its config** (`[tools.<tag>.config]`) has `engine` (`"parallel"`, `"serial"`) and **`rivet_threads`**
(default 1).

**Several Rivets in one process** need FastJet's SISCone to keep its state per thread. Stock SISCone
has one random generator and one η range for the process, so threads clustering at once get other
jets, or a FastJet internal error (L16, L29). The patch is
`utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch`, applied to `~/HEP` on
2026-09-29; a single-threaded Rivet gives byte-identical YODAs with it.

| 200k events of `single`, with the ~5 s start-up | photo_eic (`InProcEIC`) | ZEUS (`InProcZeus`) |
|---|---|---|
| chain, 12 threads + 10 `shards` | 29.0 s | 27.1 s |
| in one process, 12 threads + 1 Rivet | 112 s | — |
| in one process, 12 + 12 Rivets | 20.7 s | — |
| in one process, 10 + 14 Rivets | 19.3 s | 17.3 s |

One Rivet in one process was already 1.26× faster than the old callback design (31.3 s → 24.9 s for
40k events, the same YODA to the last digit). Several Rivets make the integrated program about 1.5×
faster than the sharded chain, because nothing formats or parses HepMC text.

---

## 22. `Status.hh` and the status protocol

A tool with `status = "standard"` writes **JSON lines** to the file descriptor named in
`$HEP_STATUS_FD`. The runner opens a pipe per process and reads it. Unknown kinds go onto the event
stream (and the journal, with `--journal`) and are otherwise ignored, so the set can grow. stdout is
never the status channel (§10).

| Kind | Fields | Shown as |
|---|---|---|
| `phase` | `phase`, `detail` | the tool's phase |
| `progress` | `done`, `total`, `rate` | the progress bar, rate and ETA |
| `xsec` | `value_pb`, `err_pb`, `final` | σ |
| `log` | `level` (`warn`, `error`), `msg` | the last warning or error |
| `summary` | tool-defined (counts, outputs) | the event stream only |
| `heartbeat` | — | keeps the tool from counting as stalled |

Every line has the envelope `{"t": <unix time>, "k": <kind>, …}`.

**C++**: `#include "Status.hh"` (before any X11 header: X11 `#define`s `Status`), then
`Status::Reporter status;`, which reads the variable itself.

| Call | |
|---|---|
| `Reporter(int beatMs = 500)` | a heartbeat every `beatMs` when structured |
| `structured()` | the descriptor is set |
| `phase(name, detail)`, `progress(done, total, rate, force)`, `xsec(pb, err, final)`, `log(level, msg)`, `summary(jsonFields)` | one message each; `progress` sends at most every 0.25 s unless `force` |
| `dropped()` | lines dropped because the pipe was full |

Writes are **non-blocking and drop on a full pipe**, so a slow reader never slows a generator. With
the variable unset, the same calls print plain lines to stderr, so a tool run by hand is readable.

**Python**: `utils/hepkit.py` (V74) is the same kit for a custom tool. It provides:
- `hepkit.Status()`: `phase`, `progress`, `xsec`, `log`, `summary`, and a heartbeat every half
  second;
- `hepkit.report(output, **fields)`: the report, written whole;
- `hepkit.Exit`: §11's table;
- `stopping()` and `usage()`.

It lives in `utils/`, not `utils/Env`, whose `yoda/` and `rivet/` folders would shadow those packages
on a tool's path.

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "utils"))   # from modules/<P>/
import hepkit

status = hepkit.Status()
status.progress(500, 10_000, 120.0)
hepkit.report(output, events=500)
sys.exit(hepkit.Exit.OK)
```

Any other language writes the same lines itself. A tool that stays silent (no log line, status
message or heartbeat) for `stall_after` seconds (default 300) fails as stalled.

---

## 23. `filters.toml`

This is for a tool that only prints. Its output is read line by line, each line matched against the
rules in order, and **the first match wins**.

```toml
# utils/Env/<tool>/filters.toml, or your own via filters = "<file>" (V61)
[[rule]]
match = '^Event (?P<done>\d+) \('     # a Python regex
emit  = "progress"                    # progress | phase | warn | error | ignore

[[rule]]
match = '^Reading events from'
emit  = "phase"
phase = "analysing"                   # a fixed name; else the (?P<phase>…) group, else the match

[[rule]]
match = 'ERROR|Exception'
emit  = "error"
```

| `emit` | Needs | Makes |
|---|---|---|
| `progress` | a `(?P<done>…)` group (commas and spaces allowed), optionally `(?P<total>…)` | a `progress` message |
| `phase` | `phase = "…"`, or a `(?P<phase>…)` group | a `phase` message |
| `warn`, `error` | — | a `log` message with the line |
| `ignore` | — | nothing, and stops the lines below from matching |

**A rule never fails a run**: the exit code does that. A rule that stops matching costs a progress
bar, not a result. Lines are split on `\n` and `\r` (a counter rewritten in place, like Herwig's
`event>`). The last line is always shown for a tool with no progress.

---

## 24. Writing C++

- **A few headers only.** A helper a second program needs goes into `utils/` as one more header;
  until then it lives in `modules/<P>/`. The headers today:
  - `Status.hh`, `Kit.hh` and `Module.hh`;
  - `PythiaRun.hh`, App_Pythia's and the integrated programs'.

  v1's libraries (`Phys`, `ML`, …) come back from git only when a program needs them, as a
  deliberate copy (V7).
- **A header holds one PascalCase namespace**, checked against the installed toolchain first: X11
  `#define`s `Status` (so `Status.hh` guards it), and Delphes declares a global `class Event`.
  Functions are `camelCase`; no `using namespace` of an external library at namespace scope.
- **Every program and app has a `// requires:` line.** A Rivet plugin links through `rivet-build`,
  plus ONNX when its `.info` says `Requires: ONNX`.
- **An app speaks the status protocol** (§22) and uses `Kit::Exit` (§11).
- **Outputs are written atomically**: to a partial name, renamed on success. A stopped program
  writes what it has, marked partial, and exits 6.
- **Threads**: catch exceptions at the thread boundary (L3). FastJet's SISCone is not thread-safe
  unpatched (L16, L29).
- **A module program** follows §21: fill raw, scale once; a density beside Rivet (L21).
- **A rebuilt binary changes identities.** Every point whose chain runs it reruns, so rebuild App_*,
  modules and Rivet plugins deliberately (§27).

---

## 25. Tests

```bash
make test           # the C++ tests, then pytest -m "not slow" (about 90 s)
make test-slow      # real generators and plots: the gates (several minutes)
```

| Suite | Holds |
|---|---|
| `tests/runner/` | the runner, fast:<br>• one bad config per rule (`test_config.py`)<br>• plans and connections (`test_plan.py`)<br>• paths, sweeps and the point-count gate (`test_sweeps.py`)<br>• the import ranks (`test_imports.py`)<br>• status (`test_status.py`)<br>• plot checks, figures and the style layers (`test_plot.py`)<br>• each tool folder's cards (`test_module.py`, `test_generators.py`, `test_process_generators.py`)<br>• seeds (`test_seeds.py`)<br>• shards, `combine`, `parallelism` and `sweep_runs` (`test_shards.py`, `test_combine.py`, `test_parallel.py`, `test_run_sweep.py`)<br>• layers and `include` (`test_layers.py`)<br>• `--why` and `hep check` (`test_why.py`)<br>• housekeeping and `hep migrate` (`test_house.py`, `test_migrate.py`)<br>• the path rules (`test_paths.py`)<br>• `hepkit` and the stack (`test_hepkit.py`, `test_stack.py`)<br>• the manual (`test_docs.py`) |
| `tests/integration/` | real processes: App_Pythia, App_yd2rt, Paint, the plot stage and every figure class (`test_plot_stage.py`), `hep overlay` (`test_hep_plot.py`), post and pre (`test_post.py`), failure injection (`test_failures.py`); `@pytest.mark.slow` for the physics gates (`test_gates_*.py`, `test_*_p4.py`) |
| `tests/cxx/` | `Status.hh`, `Kit.hh` and the module kit |
| `tests/fixtures/configs/` | the run TOMLs and cards the tests load by name (`PhotoProduction/eic`, …), frozen from `configs/` (V52). Change one only with the test that needs it |
| `tests/support.py`, `tests/runner/helpers.py` | the shared helpers: `support.hep` / `hep_ok` run `hep` with outputs under a scratch folder; `helpers.raw`, `parse`, `plan`, `plans_of`, `plans` build and plan configs |
| `tests/reference/` | **data only**: `legacy_run/` (the legacy Pythia → FIFO → `rivet` pipeline's cards, frozen base card and YODAs, at one thread, seed 12345) and `point_counts.toml` (the legacy point and page counts). **Never regenerate them.** |

**Rules** (also in `bots/BOT.md`):

- **Tests never read or write the user's `configs/` and `results/`** (V52).
  - `tests/conftest.py` sets `HEKIT_RESULTS` and `HEKIT_OUTPUT` to `output/tests/` and
    `HEKIT_CONFIGS` to `tests/fixtures/configs/`, unconditionally, and the basetemp to
    `output/tests/pytest/` wherever pytest starts.
  - The session guard fails the run if `tests/fixtures/` or `tests/reference/` changed (content
    hashes). A change under `results/`, `configs/` or `modules/`, which the user may be editing
    meanwhile, is listed at the end instead.
  - Use the `scratch` fixture for files, and `support.hep` to run `hep`.
- **One pytest session at a time**: the basetemp is shared and wiped per session.
- **Name `encoding="utf-8"`** on every text read and write, and on subprocess output: reading a YODA
  resets `LC_ALL` to `C` (L17), and `make` runs in an ASCII locale.
- **A fake has the real type** (L26). Build configs with `helpers.raw(**changes)` (dotted keys as
  `__`), `helpers.parse(data, scratch)` and `helpers.plan(data, scratch)`; a `render.py` gets the
  runner's `Override`.
- **Keep the tests that prove a refusal still refuses** (a FIFO into Delphes, an undeclared option).
- **A test that needs a tool skips cleanly** when the tool is not on `PATH` (`load_hep`) or not
  built.

**The manual is tested.** `tests/runner/test_docs.py` checks that:
- every relative link in `docs/` resolves, anchors included;
- every TOML block parses, and every complete run TOML example loads through the runner's own
  parser (one that imports, through its imports: the fixtures');
- every key the schema accepts, every `base.toml` key and every tool folder's option appears in the
  reference, and every tool folder has its section in 05;
- the generated blocks are current (`make docs`, V91);
- every section and id the code cites exists.

Change a key, and the test says which page to update.

---

## 26. Conventions

- **Errors**: one type, `HepError(message, where=…, hint=…)`. `where` is a file and key, a point or
  a path; `hint` says what to do, with `did_you_mean` for names. A message that only restates the
  failure is not enough.
- **Refuse the convenient inference.** Anywhere a correspondence could be guessed (names, paths,
  which tool a quantity is for, a data map), require it to be stated, and make a wrong one loud
  ([01 §4.5](01_Overview.md#45-require-the-explicit-statement-refuse-the-convenient-inference)).
- **Keys a consumer cannot honour are errors**, in configs, styles and backends.
- **Say it once.**
  - A key's type, default and meaning are written in `schema/run.toml`, never again by hand: the
    reference's tables are generated from it.
  - A style key's are in `base.toml`, and a command's help in `cli.parser()`.
- **Citations**:
  - Code cites this manual by section (`04 §9.4`) and the record by id (`L18`, `V22`, `C7`,
    `00/B5`).
  - A new lesson learned by running something becomes a ledger row, and a new decision a V-row.
    Ids are never reused.
  - Audit ids (audit 1's C, F, L, B, K and audit 2's H, which overlap the record's own C, F and L) are
    cited only in the audits and in `bots/`, written "audit C6". Code and this manual cite the
    V-row an audit item lands as.
- **Docstrings carry the reasoning**: a module opens with what it owns and why its shape is what it
  is.
- **Python**:
  - `from __future__ import annotations`, type hints, and dataclasses for anything with more than
    two values;
  - standard library in the runner (V1);
  - plugins import only `PLUGINS_MAY_IMPORT`.
- **Names**:
  - projects are PascalCase (`PhotoProduction`);
  - configs, quantities and tool tags are lowercase (`eic.toml`, `pt0ref`, `pythia`);
  - tags are short and filename-safe (`27x920`, `MSTW08lo`);
  - a Rivet analysis's file, class and `.info` name are one string (`photo_eic`).
- **Commits**: local, one per step of work, with the co-author line; never pushed without the user.

---

## 27. Changing things safely

- **What reruns.** Anything in a point's identity (§8) reruns the points it touches the next time
  they are run: a tool folder's argv or card lines, a binary (rebuilt apps, plugins), the seed rule.
  That is correct, but it costs generations: say so in the commit when a change reruns every point.
- **What does not rerun.** Plot settings, figures, styles and base.toml: `--only plot` or `hep plot`
  redraws.
- **Seeds**: changing the seed basis moves every point's seeds. `test_sweeps.py` pins that `single`,
  `pdf`'s NNPDF23lo point and `inproc` share theirs.
- **The reference gates** compare against `tests/reference/`. A change that moves them is a physics
  change and needs the user.
- **Breaking a config form**: refuse the old form with a hint, and teach `hep migrate` to rewrite it
  (V79, V81). The user's `configs/` are migrated only on the user's word.
- **Size**: the budget and where it stands are in [07 §9](07_Record.md#9-budget). Growth over 1.5× a
  part's budget is recorded with its cause.
