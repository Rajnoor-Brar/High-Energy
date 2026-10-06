# 05 — Commands and tools

Every `hep` command and its options, the build and the environment; then every standard tool: what
it runs, how its card is written, which quantities it consumes, what it writes, how its events are
counted, what it can export, and the quirks that shaped it (the ledger rows,
[07 §3](07_Record.md#3-the-knowledge-ledger)). Then the apps as you run them by hand.
- **Generated:** the commands' options come from `hep`'s own parser (`make docs`, V91).
- **Written by hand:** the tools' sections come from `utils/Env/<tool>/`.
- **Writing a new tool folder:** [06 §16](06_Internals.md#16-the-tool-folder-contract).

---

## 1. Commands

Every subcommand and its arguments (options and positionals may come in any order, V54):

<!-- generated: commands -->
**`hep run`**: plan and run a configuration

| Argument | Meaning |
|---|---|
| `config` | configs/<Project>/<name>[.toml], or ./path from the repo root |
| `[configuration]` | overrides [run].configuration; under [run].sweep_runs, runs only it |
| `--plan` | print the plan; run nothing |
| `--why` | for each point that would run, what changed since it last completed; run nothing |
| `--show-config` | print each configuration's resolved values and where each came from; run nothing |
| `--points SEL` | run a subset: tags, indices or quantity=tag |
| `--set KEY=VALUE` | override one value for this invocation (repeatable) |
| `--rerun` | ignore skip-unchanged |
| `--only pre\|post\|plot` | rerun only the pre tools, the post tools or the plots |
| `--plain` | plain lines instead of the live view |
| `--journal` | also write every status event to output/…/status.jsonl (for hep watch --file and replay) |
| `--logs` | keep every tool's whole output in logs/<tag>.log (default: only a failed tool's last lines) |

**`hep plot`**: draw a configuration's pages from its complete points

| Argument | Meaning |
|---|---|
| `config` | the run config |
| `[configuration]` | overrides [run].configuration; under sweep_runs, only it |
| `--set KEY=VALUE` | as for hep run |

**`hep overlay`**: overlay any YODA/ROOT files through Paint, with no run TOML

| Argument | Meaning |
|---|---|
| `FILE…` | YODA (.yoda, .yoda.gz) or ROOT files |
| `-o, --output OUTPUT` | where the pages go (default results/plots/<first file>) |
| `--labels LABELS` | legend labels, comma-separated, one per file |
| `--objects GLOB…` | only these YODA paths |
| `--formats FORMATS` | pdf, png, svg, eps (default pdf,png) |
| `--ratio` | a ratio panel against the first curve |
| `--style FILE` | a style file over utils/Apps/Paint/base.toml |

**`hep ls`**: every config and its configurations

| Argument | Meaning |
|---|---|
| `[project]` | only this project's configs |

**`hep explain`**: a run TOML key: its type, default and meaning (the schema's)

| Argument | Meaning |
|---|---|
| `key` | e.g. plot.y_gutter, run.event_count, quantities.<q>.styles |

**`hep status`**: each configuration's points: complete, stale, incomplete or to run

| Argument | Meaning |
|---|---|
| `[config]` | one config (default: every config) |
| `[configuration]` | one configuration of it |
| `--stack` | the software stack instead: each package's version (V78) |

**`hep migrate`**: rewrite run TOMLs and their cards in today's forms (a diff, or --apply)

| Argument | Meaning |
|---|---|
| `CONFIG…` | configs to migrate (default: every config) |
| `--apply` | write the changes (default: print the diff) |

**`hep reproduce`**: run a finished point again, from its provenance, beside it

| Argument | Meaning |
|---|---|
| `provenance` | output/…/<point>/provenance.json |
| `--anyway` | run it even though the setup changed since |
| `--plain` | plain lines instead of the live view |

**`hep clean`**: remove what the runner made and no plan uses (output/ only)

| Argument | Meaning |
|---|---|
| `[config]` | one config (default: every config, and the unused caches) |
| `--dry-run` | list only |
| `--yes` | delete without asking |

**`hep check`**: check run TOMLs: every configuration loaded, validated and planned

| Argument | Meaning |
|---|---|
| `CONFIG…` | configs to check (default: every configs/<Project>/*.toml with a [run]) |

**`hep watch`**: attach the live view to a running job

| Argument | Meaning |
|---|---|
| `[config]` | the run config whose job to watch (default: the latest job) |
| `[configuration]` | overrides [run].configuration (or the sweep's latest) |
| `--plain` | plain lines instead of the live view |
| `--file STATUS.JSONL` | follow a --journal run's status file instead |
<!-- /generated -->

### 1.1 `hep run`

The order is: the pre stage → every point not complete (in point order, `parallelism` at a time) →
`points.json` → the combined groups → the post stage → the plot stage. A failed point does not stop
the others.

- **`--plan`** prints everything and runs nothing:
  - per point: the values and their consumers, the groups and each tool's argv, what each reads and
    writes, the prepare steps and whether they are cached, the output and results directories, and
    whether the point is complete;
  - the pre, combined and post stages;
  - the page count;
  - each point's seed.
- **`--why`** gives, for each point and stage that would run, what changed since it last completed,
  from its `identity.json`: `events: 10 → 20`, `tools.pythia.card: + PDF:pSet = …` (V57).
- **`--show-config`** prints each configuration's resolved values and the layer each came from (its
  own, `extends`, `[run.defaults]`, `[run]`, default), and what `[config].import` gave (V56).
- **`--points SEL`** takes comma-separated point names, single tags, 1-based indices, or
  `quantity=tag`. The other points keep their state, and `points.json` lists them all. It is
  refused under a sweep of several runs: name the configuration.
- **`--set KEY=VALUE`** overrides one value of the TOML, by dotted key, before anything is checked.
  The value is read as TOML, else as a string: `--set run.event_count=50000`, `--set
  run.pdf.threads=8`, `--set static.energies=18x275`, `--set 'plot.formats=["png"]'`, `--set
  plot.min_entries=default`.
- **`--rerun`** runs complete points (and the stages) again.
- **`--only`:** `--only plot` draws the pages and runs nothing; `--only pre` and `--only post` run
  that stage whether or not it is complete.
- **`--journal`** also writes the run's events to `output/…/<cfg>/status.jsonl` (V72). Without it,
  nothing of the run's state is on disk.
- **`--logs`** keeps every tool's whole output; without it, only a failed tool's last 200 lines are
  kept.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | everything done or skipped |
| 1 | a point, a stage or a page failed |
| 2 | a config error, before anything ran |
| 6 | stopped by the user (Ctrl-C: SIGINT, then SIGTERM, then SIGKILL to the running tools; a second Ctrl-C is the default behaviour) |

Under `[run].sweep_runs` (04 §4.1), the command exits 6 if a run was stopped, else 1 if any failed,
else 0. With `[run] notify = "desktop"`, the end is also a desktop notification (V76).

### 1.2 `hep plot` and `hep overlay`

- **`hep plot CONFIG [CFG]`** draws a config's pages, as after a run (`--only plot`). Under
  `[run].sweep_runs` it draws every swept configuration's, each under its `run NN - <title> -`
  line, and the compare figures whose configurations are all complete.
- **`hep overlay FILE…`** (V74; `hep plot FILE…` is refused with the hint) takes files ending
  `.yoda`, `.yoda.gz` or `.root`:
  - one page per object any of them holds;
  - one curve per file, or one per point of a merged sweep file (labelled from the `points.json`
    inside it).

  `-o` defaults to `results/plots/<first file's stem>/`; `--labels` gives one label per file; and
  `--style` is a style file over base.toml.

### 1.3 `hep ls`, `hep explain`, `hep status`, `hep clean`

This is housekeeping (V74).

- **`ls`** lists every config and its configurations, with descriptions; a `*` marks what `hep run
  CONFIG` runs.
- **`explain`** gives a key's type, default, choices, bounds, inheritance, doc and notes, from the
  schema (`utils/Env/schema/run.toml`): `plot.y_gutter`, `run.event_count`,
  `quantities.<q>.styles`, `plot.figures.<f>.logy`, or a bare key looked up in every table.
- **`status`** gives every configuration's points and stages, each **complete**, **stale** (complete
  for an earlier identity: it reruns), **incomplete** (begun, not done: failed, stopped or running)
  or **to run**. Each comes with when it finished and its results' size, and `[running]` marks a
  configuration a job is running now. `status --stack` gives each package of
  `utils/Env/stack.toml`, its version and where it is (V78).
- **`clean`** removes what the runner made and no plan uses:
  - within each configuration's folder, the point folders no plan has (in `output/`) and the
    `.partial` leftovers (in `output/` and `results/`);
  - with no config named, every config is planned (all must plan), and the run folders no
    configuration has and the prepare cache entries no plan references go too.

  It never removes a result: an unused point's `results/` folder is listed as kept. It lists first,
  then asks on a terminal (`--yes` elsewhere); `--dry-run` only lists, and it refuses while a job is
  running.

### 1.4 `hep check`

`hep check` loads each config (with none given, every `configs/<Project>/*.toml` that has a
`[run]`), validates its `[plot]` and its figures, and plans every configuration's points. That
covers every C-rule, path, consumer, connection and card, with nothing run or written (V57). It
prints one line per config, and the error of each that fails. It exits 0, or 2 when any failed: for
a pre-commit hook, or before a long sweep.

### 1.5 `hep watch`

`hep watch` follows a running job from another terminal (V72), through the watch socket its `hep
run` serves while it lives.
- **Which job:** with no config, the latest job started on this machine; with one, the job running
  that config (and that configuration).
- **What it shows:** the run so far, then what follows, as the same blocks as the run. It leaves when
  the job's process ends. Under `[run].sweep_runs` the job is one process, so the watch follows it
  from run to run.
- **`--file`** follows a `--journal` run's status file instead (a finished run's too). It leaves when
  the run finishes, or follows on to the next run's journal in a sweep.

### 1.6 `hep migrate`

`hep migrate` rewrites run TOMLs, and the base cards they name, in the forms the runner takes today
(V79, V81). By default it prints a diff of each file; with `--apply` it writes the files (with no
config, every config). It works by line, so comments and layout stay. It rewrites:

- **figures:** `[plot.overlay.<name>]` and `[plot.object."<glob>"]` → `[plot.figures.…]`, and in a
  figure, a style key written bare (`ratio.range`) → `style.ratio.range`. This runs first, on the
  text, so that a file that was not TOML only because of it reads once migrated;
- **labels** (`labels`, `title`, `title_left`, `title_right`, `legend_header`, `x_label`, `y_label`,
  `legend`): from TLatex to LaTeX, as a physicist writes it. `E_{T} > 4 GeV` becomes `$E_{T}$ > 4
  GeV`, and `p_{T0}^{ref}` becomes `$p_{T0}^{\mathrm{ref}}$`;
- **`swept = false`** → `sweep_runs = ["a", "b", …]`, the configurations the sweep ran, in its
  order;
- **a custom tool's bare `executable`** that is not built but is a command on PATH → `"path:<name>"`
  (V54);
- **a base card's lines for keys the runner sets** (its folder's `[card] owned`). This changes the
  card, so the points' identities: they rerun.

It reads each config leniently (the old forms included) before writing anything, and strictly after.

### 1.7 `hep reproduce`

`hep reproduce` runs a finished point again (V77), exactly as it ran: its config, its configuration,
its `--set` overrides (the provenance records them) and its seed.
- **Where it runs:** into `output/<P>/.reproduce/<identity>/`, with its own `output/` and
  `results/`, never over the original.
- **The comparison:** each product against the original's, giving `identical`, `the same values` or
  `differs`, with exit 1 if any differs:
  - a YODA file object by object;
  - a ROOT file histogram by histogram;
  - anything else byte for byte.
- **A changed setup:** if the identity is not the one the provenance records, it prints what changed,
  as `--why` does, and stops. `--anyway` runs today's setup with the recorded seed.

---

## 2. The environment, `hep build` and `make`

`hep build [TARGET…] [--tests] [--clean] [--configure] [-j N]` is `make all` from the repository
root, on every core by default:
- `make all` builds every module program, Rivet plugin and app, and Herwig's repository;
- `--tests` adds the C++ tests;
- `--clean` empties `build/` first;
- `--configure` probes the toolchain again.

`hep make …` is `make …` from the repository root, wherever it is typed (V54). The targets:
- `<path>/<X>.exe`, `<path>/<x>.so`;
- `all`, `tests`, `test`, `test-slow`;
- `configure`, `list`;
- `schema`, `docs`;
- `clean`.

The make rules are in [06 §15](06_Internals.md#15-the-build). Run them with the environment loaded
(`load_hep`).

| Variable | Set by | Means |
|---|---|---|
| `HEKIT_ROOT` | `~/HEP/setup.sh` | the repository (else found from the runner's own location) |
| `HEKIT_OUTPUT`, `HEKIT_RESULTS` | you, tests | replace `output/` and `results/` (the tests point them into `output/tests/`) |
| `HEKIT_CONFIGS` | tests | replaces `configs/` as the root of run TOMLs and their cards (the tests point it at `tests/fixtures/configs/`) |
| `HEP_STATUS_FD` | the runner, per tool | the status pipe of a `status = "standard"` tool |
| `RIVET_ANALYSIS_PATH` | the rivet and merge folders, per run | `build/Rivet` (not set in the shell on purpose) |
| `LHAPDF_DATA_PATH`, `GEANT4_DATA_DIR`, `ONNXRUNTIME_DIR` | `utils/Env/hep_env.sh` | the toolchain's data |

---

## 3. The standard tools at a glance

A **standard tool** is a folder `utils/Env/<tool>/`, and its name is the value of `tool = …`. The
runner discovers the folders and names none of them.

| `tool =` | Category | Runs | Card | Streamable | Status | Count check | Prepare | Exports |
|---|---|---|---|---|---|---|---|---|
| `pythia` | event generator | `build/App_Pythia.exe` | `.cmnd`, append | — (writes) | standard | produces: sidecar | — | `card`, `cmnd` |
| `rivet` | analysis application | `rivet` (or K of them: `shards`) | none (flags) | yes | filters | `/RAW/_EVTCOUNT` | — | `analyses` |
| `yd2rt` | visualisation | `build/App_yd2rt.exe` | none | file | standard | — | — | — |
| `merge` | analysis application (post) | `rivet-merge` | none | files | none | — | — | — |
| `plotmerge` | visualisation (post) | `App_yd2rt.exe --merge` | none | files | standard | — | — | — |
| `custom` | any | your `executable` | none | per table | none (set it) | only if you set it | — | — |
| `module` | analysis application | your `Module.hh` program | none | yes | standard | the report's `events` | — | — |
| `delphes` | detector simulation | `DelphesHepMC3` | `.tcl`, append (`set`) | **no** (L11) | filters | the `Delphes` tree | — | `card`, `tcl` |
| `herwig` | event generator | `Herwig run` | `.in`, append (`set`) | — (writes) | filters | produces: runner-written sidecar | `Herwig read` | `card`, `in`, `run` |
| `sherpa` | event generator | `Sherpa` | `.yaml`, render (merge) | — (writes) | none | produces: runner-written sidecar | integration | `card`, `yaml`, `results` |
| `whizard` | process generator | `whizard` | `.sin`, render | — (writes) | filters | produces: runner-written sidecar | integration | `card`, `sin` |
| `madgraph` | process generator | `mg5_aMC` | launch script, render | — (writes a file) | filters | produces: runner-written sidecar | process directory | `card`, `proc`, `process` |

Other folders of `utils/Env/` are not tools in a chain:
- **`yoda/` and `mpl/`** hold the plot backends (`backend.py`, [03 §9](03_Plots.md#9-backends));
- **`figures/`** holds the figures' plugins;
- **`lhapdf/`** is a provider.

Paint (`utils/Apps/Paint/`) is driven by the plot stage, and is never named in `tools` (§18).

**Not tools at all:**
- **Providers** (LHAPDF, FeynRules, SARAH) are plan-time checks. A mapping with `check =
  "lhapdf:bare"` or `"lhapdf:pythia"` refuses an uninstalled PDF set (C10,
  `utils/Env/lhapdf/provider.py`, V60).
- **Analysis algorithms** (FastJet, ROOT libraries) are `// requires:` names in a source.
- **A detector simulation with no command line of its own** (Geant4) is a module program with
  `// requires: geant4`.
- **Statistics** (RooFit, pyhf, uproot, scikit-learn) are custom tools, usually in `post`.

---

## 4. `pythia` — App_Pythia

```toml
[tools.pythia]
tool        = "pythia"
baseconfig  = "photo_ep.cmnd"        # configs/<P>/photo_ep.cmnd
output_file = "events.hepmc"         # a [prelim] FIFO or file; an array fans out (V16)
```

- **Runs** `build/App_Pythia.exe <outputs> <base cards…> <point card>` (§16): the base cards in
  order, then the point card, so its settings win.
- **Card** (`cards/pythia.point.cmnd`, and `cards/pythia.cmnd` = base + point):
  - a header comment;
  - one `Key = value` line per consumed value and per `settings` entry (`on`/`off` for bools);
  - the footer;
  - then the seeds: `Random:setSeed = on`, `Random:seed = <seed>`, and at threads > 1
    `Parallelism:seeds = {…}`.
- **`cards/pythia.cmnd` holds each key once** (V59, `[card] merge`): the base cards' settings without
  comments, less each key the point card sets, then the point card. The particle-data commands that
  add up (`id:onIfMatch` and the rest of `[card] repeatable`) are kept every time.
  - `cards/pythia.json` gives each key's value and where it came from (`photo_ep.cmnd:34`,
    `[quantities.pdf] = NNPDF23lo`, `built-in events`, `[tools.pythia].settings`).
  - App_Pythia still reads the base cards and the point card, which gives the same settings.
- **Keys the runner sets** (`[card] owned`: `Main:numberOfEvents`, `Parallelism:numThreads`, the
  `Random:` seeds, `Parallelism:seeds`, `Beams:LHEF`): a base card's line for one of them is never
  used, and `--plan` and the run say so (V59).
- **Checked** (`[checks] card`, V59): at plan time, `build/App_PythiaCheck.exe` gives every line of
  the card (base settings and point card, before seeds) to Pythia's own reader.
  - A line Pythia rejects (a key it does not know, a value of the wrong kind, a particle its table
    lacks) refuses the plan, with the line's source.
  - No list of keys is kept: a nucleus or an `id:new` particle earlier in the card is read as Pythia
    reads it.
  - Answers are cached by the card's text, in `output/<P>/.cache/checks/`.
- **Footer** `Beams:LHEF = <input>`, only when the tool has an input: a shower of an LHE file from an
  earlier group (MadGraph). The base card sets `Beams:frameType = 4`.
- **Consumes** through the vocabulary: `energies`, `sqrts`, `beam_a`, `beam_b`, `beams`, `pdf`
  (checked installed), `events` and `threads` (04 §3); anything else with `key = { pythia = … }`.
- **Writes** HepMC3 to every output, and the **sidecar** `<first output>.json` (§16). It can
  **deal** its events among a sharded tool's inputs (`[outputs] deal = true`, §5.1).
- **Exports** `pythia_card` = `pythia_cmnd`: `path` (the combined card, seeds included) and `parts`.
- **Identity** includes the binary's sha256; the **version** is the stack's (`stack:pythia8`).
- Ledger: L1–L6, L25.

## 5. `rivet`

```toml
[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["photo_eic", "MC_JETS"]      # "NAME" or "NAME:OPT=V:OPT=V"
options     = { R = 0.4 }                   # applied to every analysis (optional)
output_file = "photo.yoda"
```

| Option | Kind | Notes |
|---|---|---|
| `analyses` | array, **required** | Rivet analyses; inline options as `NAME:OPT=V` |
| `options` | table | options given to every analysis |

- **Runs** `rivet -o <partial output> -a <analysis[:options]>… <input>`, with
  `RIVET_ANALYSIS_PATH = build/Rivet`.
- **Options**, in increasing precedence (the parent→child rule, V54):
  1. `options` (every analysis);
  2. the analysis's own inline `NAME:OPT=V`;
  3. quantities targeting `"<tag>/<analysis>"`.

  Each analysis must have a `.info` (`build/Rivet/`, then `rivet-config --datadir`), and every option
  it is given must be declared in the `.info`'s `Options:` (C9, L19). A quantity's option aimed at an
  analysis the tool does not run is an error.
- **Consumes** nothing through the vocabulary: beams and energies come from the events (L9).
- **σ** is the last event's `GenCrossSection` (L2): App_Pythia re-stamps it with the combined value.
- **Count check**: `/RAW/_EVTCOUNT`'s entries against the producer's sidecar `written` (L7).
- **Identity** includes each project plugin's `.so` (`build/Rivet/Rivet_<analysis>.so`); the
  version is the stack's.
- **Exports** `rivet_analyses`: `analyses` (with this point's options applied, e.g. `photo_eic:R=0.4`)
  and `plugin_path` (`build/Rivet`).
- **Its own code** is `utils/Env/rivet/render.py`'s `options` hook (V60). It handles:
  - the analyses with their options;
  - the `.info` check;
  - `{analyses}` for the argv;
  - the page texts `{opt:NAME}` (V66: each option at the point, the `.info`'s `(default X)` when
    unset).
- **Status** by filters: `Event N (` → progress, `ERROR`/`Exception` → error, `WARN` → warning (the
  "unvalidated" warning ignored).
- Ledger: L7, L9, L10, L19.

### 5.1 Sharded Rivet: `shards = K`

One Rivet process is one core: with ZEUS_2012_I1116258 about 1,500 events/s, a third of it reading
the HepMC text and the rest clustering jets. It sets the pace of a Pythia → Rivet chain whatever
Pythia's threads (measured 2026-09-29: 20 threads left the machine at 4%). `shards = K` runs K Rivet
processes, each on a share of the events, and merges them (V31):

```toml
[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"          # a [prelim] FIFO (or file) written by pythia
analyses    = ["ZEUS_2012_I1116258"]
output_file = "zeus.yoda"
shards      = 10
```

- **The chain does not change** (`tools = [["pythia", "rivet"], "yd2rt"]`). For each point:
  - the runner makes the FIFOs `events.s1.hepmc` … `events.s10.hepmc` in place of `events.hepmc`;
  - App_Pythia deals the events among them (§16);
  - the steps `rivet.1` … `rivet.10` run in the group, each writing
    `output/…/<point>/shards/zeus.s<i>.yoda`, and each is count-checked against **its own share**
    (`written_per_output` in the sidecar);
  - then `rivet.merge`, a step of its own in the next group, runs `rivet-merge -e` (the `merge`
    folder) into the table's `output_file` (`zeus.yoda`, in `results/`).

  The logs are `logs/rivet.<i>.log` and `logs/rivet.merge.log`, and `--plan` shows every step.
- **The events do not change.** Seeds follow the generator's cards, not its argv (V22), so a sharded
  point has the same events as the same point unsharded. The merged YODA is the same, up to the
  rounding of summing in another order. The point's identity does change (its argv), so changing
  `shards` reruns it.
- **Requirements**, refused at plan time otherwise:
  - the tool reads one input and writes one output;
  - the input is a `[prelim]` FIFO or file with exactly one producer in the chain, whose folder can
    deal (`pythia`);
  - every analysis is re-entrant (`Reentrant: true` in its `.info`), because `rivet-merge -e` runs
    `finalize()` again on the summed histograms.

  Other outputs of the producer (a module program's FIFO) still get every event.
- **Quantities aimed at the table reach every shard**: `target = "rivet/photo_eic"` (eic's `radius`)
  or `key = { rivet = … }` gives each `rivet.<i>` the same option, and `--plan` shows it as
  `rivet.1–10:R`.
- **Choosing K.** Each shard is one core, and so is each Pythia thread: `threads + shards` should not
  exceed the machine. Measured on the lab PC (i7-13700K, 24 hardware threads), 200k ZEUS_2012
  events, steady rate after the ~5 s start:

  | `threads` + `shards` | events/s |
  |---|---|
  | 20 + unsharded | ~1,570 |
  | 8 + 8 | ~8,100 |
  | 12 + 10 | ~9,200 |
  | 14 + 10, 10 + 12 | the same as 12 + 10: the CPU is full |

  `threads = 12`, `shards = 10` is what `eic.toml` and `zeus_validation.toml` use.

## 6. `yd2rt` — YODA → ROOT

```toml
[tools.yd2rt]
tool        = "yd2rt"
input       = "photo.yoda"
output_file = "photo.root"
select      = ["/photo_eic/*"]              # optional: YODA path globs
```

| Option | Kind | Notes |
|---|---|---|
| `select` | array | YODA path globs to convert; default every object except `/RAW` and `/TMP` |

It runs `App_yd2rt.exe <input> <partial output> <select…>` (§17). The ROOT file is a product, in
`results/`. Like every tool in `tools`, it needs its `[tools.<tag>]` table (C5), because the table
says what it reads and writes.

## 7. `merge` — rivet-merge, in `post`

```toml
[run.replicas]
sweeps = ["replica"]
tools  = [["pythia", "rivet"]]
post   = ["merge"]

[tools.merge]
tool        = "merge"
input       = "photo.yoda"       # that product of every point
output_file = "merged.yoda"
equivalent  = true               # default: -e, statistically equivalent runs
```

| Option | Kind | Default | Notes |
|---|---|---|---|
| `equivalent` | flag | true | `-e`: runs of one process (seed replicas); statistics add, σ is averaged. `false` merges different processes into their sum |

- **Runs** `rivet-merge [-e] -o <partial output> <every point's input>`, with `RIVET_ANALYSIS_PATH`
  set. It re-runs the analyses' `finalize()`, so they must be re-entrant.
- **Also used by the runner itself:**
  - to merge a sharded Rivet's shards inside a point (§5.1);
  - for each group of a `combine` (04 §5.5);
  - for a `merged` figure's members (03 §7.4).

## 8. `plotmerge` — the sweep in one file, in `post`

```toml
[tools.bundle]
tool        = "plotmerge"
input       = "photo.yoda"
output_file = "sweep.root"       # or sweep.yoda
```

It runs `App_yd2rt.exe --merge <partial output> <point>=<yoda>… --keep-raw --points points.json`
(§17).
- **Into ROOT:** a directory per point, the `paths` tree with a `point` column, and `points.json` as
  a `TNamed`.
- **Into `.yoda`:** one YODA file, with the point as a path prefix.

It is not a statistical merge (that is `merge`). The plot stage makes the same file itself,
`plots/root/<cfg>.root`, so this tool is for a copy elsewhere, or a YODA version.

## 9. `custom`

Any executable: its argv is `{exe} {config} {arguments}` (04 §9.2). Its status is `none` unless the
table sets it, and `HEP_STATUS_FD` is passed when `status = "standard"`.

```toml
[tools.jets_reco]
tool        = "custom"
executable  = "path:python3"
arguments   = ["{repo}/modules/PhotoProduction/delphes_jets.py", "{input}", "{partial:output}"]
input       = "delphes.root"
output_file = "jets_reco.json"
```

**A custom tool in Python** gets the kit's half that applies through `utils/hepkit.py` (V74):
- `Exit`: Kit::Exit's table;
- `Status`: the standard protocol, with a heartbeat, or plain lines on stderr when the fd is not
  given;
- `report(output, …)`: `<output>.json`, written whole;
- `stopping()`.

`delphes_jets.py` is its first user, so its table may say `status = "standard"`
([06 §22](06_Internals.md#22-statushh-and-the-status-protocol)).

## 10. `module` — a Module.hh program

- **argv:** `{exe} {config} --input={input} --output={partial:output} --events={events}
  --sidecar={input_sidecar} {arguments}` (04 §9.3).
- **Status:** standard.
- **Count check:** it reads `events` from the program's report, `<output>.json`, against the
  producer's sidecar.
- **Integrated programs:** an empty `--input=` means an integrated program, which makes its own
  events.

The kit is [06 §21](06_Internals.md#21-modulehh).

## 11. `delphes` — DelphesHepMC3

```toml
[tools.delphes]
tool        = "delphes"
baseconfig  = "delphes_card_ATLAS.tcl"
input       = "showered.hepmc"       # a [prelim] FILE from an earlier group: never a FIFO
output_file = "delphes.root"
```

- **Runs** `DelphesHepMC3 <combined card> <partial output> <input>`.
- **Card**: Tcl, append style, `set {key} {value}` lines; the seed as `set RandomSeed <seed>`.
- **Not streamable** (L11): Delphes sizes its input first and skips a zero-length one, which a FIFO
  always is. A FIFO into it is refused at plan time (C6). It creates its ROOT file before reading the
  card, so it writes the partial name the runner gives.
- **Count check**: the `Delphes` tree's entries (read with uproot) against the sidecar.
- **Seeds**: Delphes is not an event producer, so it never moves the generator's seeds (V22).
- **Exports** `delphes_card` = `delphes_tcl`.

## 12. `herwig` — Herwig 7

```toml
[tools.herwig]
tool        = "herwig"
baseconfig  = "dis_ep.herwig.in"
output_file = "events.hepmc"
```

- **Prepare** (cached per card): `Herwig read --repo=build/Herwig/HerwigDefaults.rpo <card>` →
  `point.run` in the cache entry. The repository is made by `hep build`: Herwig's own install could
  not make it, since its defaults need CT14lo/CT14nlo (L15). A plan without it is refused (C10),
  with `hep build`.
- **Runs** `Herwig run <cache>/point.run -N <events> -s <seed> -d 0`. Events and seed are flags, so
  every point and replica with the same physics shares one read.
- **Card**: ThePEG `set {key} {value}` lines (a later `set` wins). The footer reads HepMC output
  (`read snippets/HepMC.in`, the file name, `saverun point EventGenerator`), and must come last.
- **Beams**: in Herwig's slots, `[beams] slots = ["lepton", "hadron"]` (V62): the snippet puts the
  lepton on beam A, and the runner reorders the run's per-beam values for it.
- **Consumes** `energies` (`Luminosity:BeamEMaxA`, `…B`) and `sqrts` (`Luminosity:Energy`).
- **Sidecar** written by the runner after exit 0 (`written = "requested"`: Herwig makes exactly `-N`
  events or fails).
- **Exports** `herwig_card` = `herwig_in`; `herwig_run`: `path` = the `.run` file, **prepared on
  demand** for a custom tool that asks.
- Ledger: L15.

## 13. `sherpa` — Sherpa 3

```toml
[tools.sherpa]
tool        = "sherpa"
baseconfig  = "photo_ep.sherpa.yaml"
output_file = "events.hepmc"
```

- **Card** (`render.py`): the base YAML files deep-merged in order, then each value assigned at its
  **key path** (`EPA:Q2Max`, `PDF_SET[0]`: a list entry is replaced, never appended), written whole.
  - `sqrts` becomes `BEAM_ENERGIES = [√s/2, √s/2]`.
  - `MPI_PDF_SET` follows `PDF_SET` (it agreed before, or was absent): Sherpa's MPI reads its own key
    and falls back to a PDF that is not installed (L12).
  - The footer is `EVENT_OUTPUT: HepMC3_GenEvent[<output name>]`, and the seed is `RANDOM_SEED:
    <seed>`.
- **The plan owns** `BEAMS`, `BEAM_ENERGIES`, `RANDOM_SEED`, `EVENTS`, `EVENT_OUTPUT` and
  `RESULT_DIRECTORY`: a base card that sets one is refused.
- **Prepare** (the integration, cached by the card without `EVENTS`): `Sherpa -f <card> -e 0
  "RESULT_DIRECTORY: <cache>/Results" "EVENT_OUTPUT: None"`. `EVENT_OUTPUT: None` matters: otherwise
  Sherpa opens the FIFO at initialisation and waits for a reader that only the generation starts.
  The marker is `Results.zip`.
- **Runs** `Sherpa -f <card> "RESULT_DIRECTORY: <cache>/Results"`, in the point's directory. Sherpa
  prepends `./` to the output name (L12), so the name is relative.
- **Consumes** `energies`, `beams`, `sqrts`, `pdf` (checked) and `events`.
- **Sidecar** written by the runner (`written = "requested"`).
- **Exports** `sherpa_card` = `sherpa_yaml`; `sherpa_results`: the integration directory, prepared
  on demand.
- **Notes:**
  - Sherpa writes a YODA variation per extra weight; the plot stage draws the nominal only.
  - With `MI_HANDLER: Amisic`, ep photoproduction made 0 events in 768 s (v1), so the committed card
    has MPI off.
- Ledger: L12, L24.

## 14. `whizard` — Whizard 3

```toml
[tools.whizard]
tool        = "whizard"
baseconfig  = "photo_ep.sin"         # exactly one base card
output_file = "events.hepmc"
```

- **Card** (`render.py`): SINDARIN is a script, so the point card comes **first** and includes the
  base **last** (L13). In order:
  - the plan's assignments;
  - `seed = <seed>`, `sample_format = hepmc`;
  - `$sample = "<output without .hepmc>"` (Whizard appends `.hepmc`);
  - then `include("<base>")`.
- **Beams are names**: PDG codes become the SM model's names (from
  `share/whizard/models/SM.mdl`). The base card states its structure-function chain in a comment,
  `# hep: beam_structure = pdf_builtin, epa`, which is appended as `=> pdf_builtin, epa`.
- **The plan owns** `seed`, `n_events`, `sqrts`, `beams`, `beams_momentum`, `$sample` and
  `sample_format`: a base that assigns one is refused (it would run after the plan's value).
- **Prepare** (integration: library, phase space, grids): `whizard <prepare card>`. The prepare card
  is the point card without `n_events`, `$sample` and `sample_format`, keyed without them and
  `seed`. Generation then runs **in the cache entry** (`[command] cwd`), where Whizard finds them.
- **Consumes** `energies` (`beams_momentum`, in GeV), `beams` and `events` (`n_events`).
- **σ**: Whizard writes none into its events, so Rivet has none; the integration log has it.
- **Limits:** Whizard has no photon structure function, so it does direct photoproduction only
  (L13). Its EPA record has no scattered lepton, so a Rivet analysis using `DISKinematics` cannot run
  on it.
- **Exports** `whizard_card` = `whizard_sin`.

## 15. `madgraph` — MadGraph5_aMC@NLO

```toml
[run.single]
tools = ["madgraph", ["shower", "rivet"], "yd2rt"]

[prelim]
files = ["unweighted.lhe"]
fifo  = ["events.hepmc"]

[tools.madgraph]
tool        = "madgraph"
baseconfig  = "dis_ep.proc_card.mg5"   # the proc card: processes only, no `output` or `launch`
output_file = "unweighted.lhe"

[tools.shower]
tool        = "pythia"
baseconfig  = "shower_lhe.cmnd"          # sets Beams:frameType = 4; the LHEF line is the footer
input       = "unweighted.lhe"
output_file = "events.hepmc"
```

- **Prepare** (keyed on the **proc card only**, `key = "base"`): the proc card plus
  `output <cache>/process -f` → the process directory, built once. The marker is
  `process/bin/generate_events`.
- **Card** (the launch script), in order:
  - `set automatic_html_opening False` (else it opens a browser, 00/B39);
  - `launch <cache>/process -n r<seed>`;
  - shower, detector and analysis off;
  - then `set iseed <seed>`, and one `set <key> <value>` per value.

  Beams become `set lpp1/lpp2` (2212 → 1, −2212 → −1, leptons → 0), from the folder's `[render.lpp]`.
- **Runs** the launch, then unpacks the run's `Events/r<seed>/unweighted_events.lhe.gz` to the
  output: a file, for a `pythia` table in a later group to shower.
- **Consumes** `energies` (`ebeam1`, `ebeam2`: beam 1 is the proc card's first incoming particle),
  `beams` and `events` (`nevents`).
- **Sidecar** written by the runner (`written = "requested"`).
- **Exports** `madgraph_card` = `madgraph_proc`; `madgraph_process`: the process directory, prepared
  on demand.
- Ledger: L14.

---

## 16. App_Pythia — `utils/App_Pythia.cc`

```
App_Pythia.exe [--threads N] [--events N] [--seeds S1,S2,…] [--sidecar FILE] OUTPUT[,OUTPUT…] CARD [CARD…]
```

**Its rules.** Its Pythia rules (the σ combination, the stamping, the seed check, the chunking: L1,
L2, L4, L6, L28) are `utils/PythiaRun.hh`'s. The integrated programs (InprocJets) run them too
(V63), so an integrated point's events and σ are the chain's by construction.

**Outputs.** Every comma-separated OUTPUT gets **every** event (fan-out, V16). An OUTPUT written
**`A+B+C`** is a **deal group**: each event goes to **one** of its members, the first that is free,
starting from a rotating index (so a slow consumer gets fewer). That is how a sharded Rivet gets its
shares (§5.1). `events.s1.hepmc+events.s2.hepmc,to_module.hepmc` deals the events between two Rivet
shards, and still copies every one to a module program.

**How the runner calls it.** `// requires: pythia8 hepmc3 zstd zlib`. The runner calls it as `{exe}
{outputs} {cards}`: the threads, events and seeds are in the point card.

| Behaviour | Ledger |
|---|---|
| Reads the cards in order (the point card last: last wins) | — |
| `PythiaParallel` with `processAsync = on`: callbacks run concurrently, each instance converts with its **own** `Pythia8ToHepMC`, σ is combined under one small lock, and **each output has its own writer and lock**, so formatting the HepMC text is shared among the outputs. (With `processAsync = off` and one writer, the app was capped at ~2,200 events/s whatever its threads: 4 threads took 17.7 s and 20 threads 20.5 s for 40k events.) | L3 |
| Checks the seed list before `init()`: one per thread, each in 1…9·10⁸ (Pythia does not) | L4 |
| Opens the outputs only after `init()` succeeds: a bad card leaves no half-open FIFO | — |
| Runs in chunks of a multiple of the thread count, so SIGINT takes effect within a chunk | L6 |
| Catches in the callback and re-raises on the main thread | L3 |
| σ combined over instances: the ΣW-weighted mean, errors in quadrature | L1 |
| Once more than one instance has contributed, **re-stamps every event's `GenCrossSection` with the combination**, so the last event Rivet reads carries the final σ; at one thread the converter's numbers are untouched (bit for bit the legacy pipeline's) | L2 |
| **Every output ends on the latest σ**: each writes its events one late, and at the end its held event takes the σ of the last event stamped, so every shard of a deal group (and every copy) normalises to the σ an unsharded Rivet would | L28 |
| Several outputs: the same events to each (fan-out, V16), or one of a deal group's members each; a `.gz` or `.zst` suffix picks HepMC3's compressed writer | L25 |
| Events are numbered once, from 0, across the threads; every event carries one shared run info | — |
| Status on `$HEP_STATUS_FD` (06 §22) | — |

**The sidecar**, `<first output>.json` (or `--sidecar`), is written after the outputs are closed. It
holds:
- `tool`, `pythia_version`;
- `requested`, `attempted`, `accepted`;
- **`written`**: what the count check compares; it can be below `requested` (L5);
- `write_failures`;
- `sigma_pb`, `sigma_err_pb`, `sum_w`;
- `threads`, `seeds`, `random_seed`;
- `outputs` (every path, in order);
- **`written_per_output`** (`{"<path>": events, …}`): what a shard's count check compares;
- `cards`, `stopped`.

**Exit codes** (06 §11):

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | card or config |
| 2 | usage |
| 3 | init |
| 5 | output |
| 6 | stopped (outputs and sidecar written, `stopped: true`) |
| 70 | internal |

`App_PythiaCheck.exe CARD` is its card check (§4).

## 17. App_yd2rt — `utils/App_yd2rt.cc`

```
App_yd2rt.exe IN.yoda OUT.root [GLOB …] [--keep-raw]
App_yd2rt.exe --merge OUT.root|OUT.yoda NAME=IN.yoda … [--keep-raw] [--select GLOB] [--points FILE]
```

`// requires: yoda root`.

| YODA | ROOT |
|---|---|
| `Histo1D`, `Estimate1D` | `TH1D` (an Estimate's error is the average of its total down and up errors) |
| `Histo2D`, `Estimate2D` | `TH2D` |
| `Scatter2D` | `TGraphAsymmErrors` |
| `Counter`, `Estimate0D` | a one-bin `TH1D` |

- **Directories nest as the YODA path does**: `/photo_eic/d01-x01-y01` → `photo_eic/d01-x01-y01`.
  A variant path `/photo_eic:R=0.4/…` becomes `photo_eic__R-0.4/…` (`:` → `__`, `=` → `-`). Every
  object's title is its original YODA path, and the `paths` TTree maps each ROOT path back.
- **`/RAW` and `/TMP`** are skipped unless `--keep-raw`, which also writes `<name>__entries` (per-bin
  raw entry counts) beside each `/RAW` histogram: Paint's `min_entries` reads them.
- **`--merge`**: each input's objects go under a directory named for it (its point). The `paths`
  tree gets a `point` column, and `--points` stores `points.json` in the file as the TNamed
  `points.json`. Into a `.yoda` file, the name is a path prefix instead.
- **Exit codes**: 0 ok, 2 usage, 4 input, 5 output.

## 18. Paint's command line

```
Paint.exe PAGE.toml [PAGE.toml …] [--ranges | --ranges-only]
Paint.exe PAGE.toml --dump-ranges
Paint.exe [PAGE.toml] --dump-style
```

Paint draws many pages in one ROOT process (V64; the plot stage sends up to 200 at a time).
- **Several pages:** each page's outcome is a JSON line on stdout, `{"page", "ok", "error"}`, so one
  bad page does not stop the rest.
- **`--ranges`** also writes each page's final ranges and voided bins beside its config
  (`<page>.toml.ranges.json`), for the other backends; **`--ranges-only`** writes them and draws
  nothing.
- **`--dump-ranges`** prints one page's ranges as JSON; **`--dump-style`** prints the merged style
  (base.toml's alone, without a page).
- **Exit codes**: 0 ok, 1 page config or style (with several pages: any failed), 2 usage, 4 input,
  5 output.

**The page document**, written by the runner to `output/…/plots/[<cell>/]<object>.toml`. Its labels
are LaTeX converted to TLatex, which Paint draws:

```toml
[page]
name        = "d06-x01-y01"
output      = "/…/results/…/plots/root/d06-x01-y01"    # without extension
formats     = ["pdf", "png"]
title       = "1 > #eta > 1.5, #it{k}_{#it{T}} alg"
x_label     = "#it{E}_{#it{T}} [GeV]"
y_label     = "d#sigma / d#it{E}_{#it{T}} [pb/GeV]"
logx        = false
logy        = true
y_gutter    = 0.5                  # or "default"
x_gutter    = "default"
ratio       = true
ratio_label = "MC/Data"
normalise   = false
void_empty  = true
min_entries = 10
auto_range  = true
range_pad   = 0
# markers = true                   (a Scatter2D figure, V86)
# heatmap = true, logz, z_label    (a HeatMap page: one [[curve]], V87)

[style]                            # only what the style layers changed (04 §12)
page.dpi = 300

[[curve]]
file   = "/…/plots/root/default.root"
object = "MSTW08lo/ZEUS_2012_I1116258/d06-x01-y01"
raw    = "MSTW08lo/RAW/ZEUS_2012_I1116258/d06-x01-y01"   # optional: for min_entries
label  = "MSTW 2008 LO"
style  = { colour = "#EE3311" }                         # optional: the value's look (V67)
band   = [{ file = "/…/default.root", object = "…" }]   # optional: the envelope's members (V69)

[data]                             # optional
file   = "/…/output/PhotoProduction/.cache/datasets/ZEUS_2012_I1116258.yoda.root"
object = "REF/ZEUS_2012_I1116258/d06-x01-y01"
label  = "ZEUS 2012"
```

A curve object is a `TH1`, a `TGraphAsymmErrors`, or for a heat map a `TH2`. What Paint does with a
page, in order, is [06 §20](06_Internals.md#20-paint-inside).
