# 02 — User guide

How to get work done: set up, run, read what came out, and build the pipelines you need, each shown
as a recipe from a run TOML. Every key is in [04](04_Config_Reference.md), every command and tool in
[05](05_Commands_and_Tools.md), the plots and figures in [03](03_Plots.md). Why it works this way is
[01](01_Overview.md); how, [06](06_Internals.md).

---

## 1. Set up and build

```bash
load_hep            # or: source ~/HEP/setup.sh — the ~/HEP stack, the venv, `hep` on PATH
hep build           # every app, module program and Rivet plugin, and Herwig's repository
```

`hep build` takes these options:
- `--tests` also builds the C++ tests;
- `--configure` probes the toolchain again (after installing a library);
- `--clean` empties `build/` first;
- `-j N` limits the jobs.

To build one source, `make` it by its path (`hep make …` works from anywhere); the output lands where
the convention says:

| Source | `make` | Output |
|---|---|---|
| `modules/<P>/<X>.cc` | `make modules/<P>/<X>.exe` | `build/<P>/<X>.exe` |
| `modules/<P>/Rivet/<x>.cc`, `modules/<P>/Rivet_<x>.cc` | `make modules/<P>/Rivet/<x>.so` | `build/Rivet/Rivet_<x>.so` + its `.info`, `.plot`, `.yoda` |
| `utils/App_<X>.cc` | `make utils/App_<X>.exe` | `build/App_<X>.exe` |
| `utils/Apps/<X>/main.cc` | `make utils/Apps/<X>.exe` | `build/<X>.exe` |

A source says what it links in one line near the top: `// requires: pythia8 hepmc3 fastjet`. The
names it may use are those of `utils/Env/stack.toml` (`pythia8 hepmc3 yoda root fastjet lhapdf rivet
geant4 toml zstd zlib onnx delphes`), or `none`. Without the line it links everything that was found.
A folder or file whose name starts with `_` is parked: `hep build` skips it.

The shell gives you `hep_status` (installed versions), `hep_cd PROJECT
[configs|modules|results|output]`, `hep_refresh`, `quit` (leave the environment) and `hep_help`.

---

## 2. A first run

```bash
hep run PhotoProduction/eic single --plan    # what would run: cards, argv, connections; runs nothing
hep run PhotoProduction/eic single --set run.event_count=50000
```

`single` is one point:
- App_Pythia generates 27.5 × 920 GeV e⁺p photoproduction into a FIFO;
- Rivet's `photo_eic` reads it;
- the YODA is converted to ROOT;
- 17 pages are drawn against ZEUS data.

The terminal shows the running tools, then one block:

```
── point 1/1: point ── ok after 42.3 s
   done → results/PhotoProduction/eic/03_single/point
```

| Look in | For |
|---|---|
| `results/PhotoProduction/eic/03_single/point/` | `photo.yoda`, `photo.root`: the products |
| `results/PhotoProduction/eic/03_single/plots/root/` | the pages (`d01-x01-y01.pdf`, …), `index.html`, and `single.root`, the sweep in one file |
| `output/PhotoProduction/eic/03_single/point/` | `cards/`, `logs/`, `provenance.json`, `.complete` |

Run the same command again and nothing happens: the point is complete with the same identity. Change
anything that decides the result (a card, an event count, a binary) and it runs again.

```bash
hep run PhotoProduction/eic energy_pdf       # 16 points: 4 beam energies × 4 PDFs
hep watch                                    # from another terminal: follow the latest job
hep plot PhotoProduction/eic energy_pdf      # redraw its pages from what is on disk
```

---

## 3. Anatomy of a run TOML

A run TOML has seven sections. Here is a small, complete one:

```toml
# configs/PhotoProduction/mini.toml
[run]
name          = "mini"
project       = "PhotoProduction"
configuration = "pdf"             # what `hep run PhotoProduction/mini` runs
event_count   = 100_000
threads       = 8

[run.pdf]                         # a configuration: one recipe
description = "Two proton PDFs at the static beams"
sweeps      = ["pdf"]             # 2 points
tools       = [["pythia", "rivet"], "yd2rt"]   # group 1 runs together (FIFO), then group 2

[prelim]
fifo = ["events.hepmc"]           # made before the tools start, per point

[static]                          # values of quantities that are not swept
energies = "27x920"

[quantities.energies]             # the vocabulary knows it: Pythia's Beams:eA, Beams:eB
values = [[920, 27.5], [275, 18]]
tags   = ["27x920", "18x275"]

[quantities.pdf]                  # PDF:pSet = <value>, as written
values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]   # or Pythia's own sets: 13, 14
tags   = ["MSTW08lo", "NNPDF23lo"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 LO"]

[tools.pythia]
tool        = "pythia"
baseconfig  = "photo_ep.cmnd"     # configs/PhotoProduction/photo_ep.cmnd: the physics
output_file = "events.hepmc"      # a [prelim] name: into the FIFO

[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["photo_eic"]
output_file = "photo.yoda"        # not a [prelim] name: a product, in results/

[tools.yd2rt]
tool        = "yd2rt"
input       = "photo.yoda"
output_file = "photo.root"

[plot]
formats = ["pdf", "png"]
ratio   = true
```

- **The physics is in the base card.** A quantity renders an override into the point card
  (`cards/pythia.point.cmnd`). It is read after the base, so it wins.
- **Quantities reach tools** in one of three ways (04 §8.1):
  - through the tool folders' `quantities.toml` (`energies`, `pdf`, `sqrts`, `beams`, `beam_a`,
    `beam_b` for Pythia);
  - through `key = { pythia = "…" }`;
  - through a `target`.

  A quantity that is set but reaches no tool is refused (C7): a value that changes a directory name
  and nothing else is the failure this framework is built to refuse.
- **Connections are named**: `output_file` and `input` say what goes where. A FIFO connects tools in
  one group; between groups the interface is a file (C6).
- **Paths**: a bare name goes under its key's convention root (`baseconfig` under `configs/<P>/`),
  `./x` is from the repository root, and `/x` is absolute (04 §2).
- **Labels are LaTeX**, as a physicist writes them (`$p_{T}$ > 4 GeV`, `$\sqrt{s}$`). Words outside
  `$…$` are text, as written. A label in ROOT's TLatex (`#sqrt{s}`, `p_{T}` with no `$`) is refused
  with its LaTeX as the hint, and `hep migrate` rewrites old files (§10).

---

## 4. Sweeps and points

Each recipe below is a pattern you can copy. The shipped configurations that use it are named, so
you can run them.

### 4.1 One point

`sweeps = []`. Any active quantities come from `[static]`. → `eic single`.

### 4.2 A sweep: one quantity, one page

```toml
[run.pdf]
sweeps = ["pdf"]
tools  = [["pythia", "rivet"], "yd2rt"]
```

One page per histogram, with a curve per PDF. → `eic pdf`, `zeus_validation default`.

### 4.3 A grid, split into pages

```toml
[run.energy_pdf]
sweeps      = ["energies", "pdf"]     # 4 × 4 = 16 points
plot_points = ["energies"]            # a page folder per energy; the PDFs are the curves
tools       = [["pythia", "rivet"], "yd2rt"]
```

`plot_points` names the quantities that make **pages**; every other swept quantity makes
**curves**. → `eic energy_pdf`, `eic mpi_grid`, `lambda cuts_grid`.

### 4.4 Quantities that move together

```toml
sweeps = ["energies", ["pdf", "alphas"]]    # pdf and alphas zipped: value i with value i
```

An inner list is one axis whose quantities have equal value counts (a PDF with its matching αs).
A quantity's `exclude = [N, …]` leaves values out of a sweep (1-based).

### 4.5 A configuration's own fixed values

```toml
[run.mpi]
sweeps = ["pt0ref"]
tools  = [["pythia", "rivet"], "yd2rt"]
static = { energies = "18x275" }      # over [static], for this configuration only
```

→ `eic mpi`, `eic radius`. A static value is a tag, an exact value, or `"#N"`. `--set
static.energies=10x100` changes it for one invocation.

### 4.6 A quantity Pythia does not know by name

```toml
[quantities.pt0ref]
key    = { pythia = "MultipartonInteractions:pT0Ref" }
values = [3.0, 3.2, 3.4]
tags   = ["pt30", "pt32", "pt34"]
labels = ['$p_{T0}^{\mathrm{ref}}$ = 3.0 GeV', '$p_{T0}^{\mathrm{ref}}$ = 3.2 GeV', '$p_{T0}^{\mathrm{ref}}$ = 3.4 GeV']
```

- **Quoting:** write LaTeX labels in **single** quotes. In `"…"`, TOML reads a backslash as an
  escape and refuses the file.
- **Underscores:** only a brace makes a sub- or superscript, so `"PDF4LHC21_40"` shows its
  underscores as they are.
- **No-op overrides:** an override equal to the base card's own value is written, but does not change
  the identity.

### 4.7 Analysis options

```toml
[quantities.radius]
target = "rivet/photo_eic"      # tool tag / analysis
key    = "R"                    # the option, as the .info declares it
values = [0.4, 0.7, 1.0]
tags   = ["r04", "r07", "r10"]
```

Rivet runs `photo_eic:R=0.4`, and so on. An option the `.info` does not declare is refused (C9):
Rivet would ignore it silently and give identical curves. Each variant is a curve on the object's
page, labelled `… [R=0.4]`.

**Each value is its own generation** (V9): a three-value option sweep runs Pythia three times. To
avoid that, keep the events once as a `[prelim] files` entry and analyse them in another
configuration (§5.1 shows the file interface). → `eic radius`, `lambda sets`.

### 4.8 Every configuration, one run after another

To run several of a TOML's configurations in one go, list them, or say `true` for all:

```toml
[run]
sweep_runs = ["pdf", "energies"]   # hep run eic: these, in this order (true: every one, in file order)

[run.pdf]
title = "Proton PDFs"              # the header line: run 01 - Proton PDFs -

[run.delphes]                      # not listed: hep run eic delphes still runs it
```

- **Each configuration is an ordinary run**, with its own title, blocks, verdict and folder, exactly
  as `hep run eic <cfg>` would make it.
- **They are all checked before the first starts**, so a typo in the last one costs nothing.
- **They are pipelined**: a run starts once the run before has started all its points, and they
  share the machine's cores.
- **A failed run lets the next one start**; Ctrl-C stops everything.
- **`hep watch` follows the whole sweep**, from one run to the next.

That is what a shell loop can't do. In `for c in …; do hep run eic $c; done`, a Ctrl-C only ends the
current run (hep exits 6 and bash carries on), and a typo in a later configuration shows up hours in.
`hep run eic pdf` still runs only `pdf`, and `--set run.sweep_runs=false` turns the sweep off for one
call.

---

## 5. Generators and chains

### 5.1 A file chain: generator → Delphes → your analysis

```toml
[run.delphes]
sweeps = []
tools  = ["pythia_file", "delphes", "jets_reco"]    # three groups, strictly in order
prelim = { files = ["showered.hepmc"] }             # a file: every hop crosses a group

[tools.pythia_file]
tool        = "pythia"
baseconfig  = "photo_ep.cmnd"
output_file = "showered.hepmc"

[tools.delphes]
tool        = "delphes"                             # not streamable: a FIFO here is refused (L11)
baseconfig  = "delphes_card_ATLAS.tcl"
input       = "showered.hepmc"
output_file = "delphes.root"

[tools.jets_reco]
tool        = "custom"
executable  = "path:python3"
arguments   = ["{repo}/modules/PhotoProduction/delphes_jets.py", "{input}", "{partial:output}"]
input       = "delphes.root"
output_file = "jets_reco.json"
```

Delphes' tree is count-checked against the generator's sidecar. The `[prelim]` file stays in
`output/`, so another configuration can read it with `input = "./output/…/showered.hepmc"`.
→ `eic delphes`.

### 5.2 Other generators

The chain is the same; only the generator's table changes. Their slow preparation (Sherpa's and
Whizard's integration, `Herwig read`, MadGraph's process directory) is cached per card under
`output/<P>/.cache/`, so a rerun, a replica or another event count reuses it.

```toml
[tools.sherpa]
tool        = "sherpa"
baseconfig  = "photo_ep.sherpa.yaml"     # the plan owns BEAMS, EVENTS, RANDOM_SEED, EVENT_OUTPUT
output_file = "events.hepmc"
```

| Generator | Base card | Notes |
|---|---|---|
| `herwig` | `.in` | `hep build` makes its repository; seed and events are flags |
| `sherpa` | `.yaml` | keys are paths into the YAML (`PDF_SET[0]`, `EPA:Q2Max`); `MPI_PDF_SET` follows `PDF_SET` |
| `whizard` | `.sin` | one base card, included after the plan's settings; beams by the model's names; direct photoproduction only |
| `madgraph` | proc card | writes an LHE **file**; shower it with a `pythia` table in a later group (its base card sets `Beams:frameType = 4`) |

A MadGraph chain is `tools = ["madgraph", ["shower", "rivet"], "yd2rt"]`, with
`[prelim] files = ["unweighted.lhe"]` and `fifo = ["events.hepmc"]` (05 §15).

Keep each generator's configurations in a run TOML of their own when their quantities differ:
eic's `pt0ref` is a Pythia key, and in a Sherpa chain nothing would consume it (C7). The shipped
examples are under `tests/fixtures/configs/PhotoProduction/` (`herwig.toml`, `sherpa.toml`,
`whizard.toml`, `madgraph.toml`).

### 5.3 The same study with several generators

```toml
[run.compare]
sweeps = ["generator"]
tools  = [["@generator", "spectra"], "yd2rt"]   # "@q": the tool tag the point's value names

[quantities.generator]
values = ["pythia", "herwig", "sherpa"]          # tool tags
tags   = ["py8", "hw7", "sh3"]
labels = ["Pythia 8.317", "Herwig 7.3", "Sherpa 3.0.5"]
```

This needs a `[tools.pythia]`, a `[tools.herwig]` and a `[tools.sherpa]`, each writing
`events.hepmc`. A value that only one of them consumes (Sherpa's `BEAMS`) is accepted, since it
reaches a tool of the configuration. → `Comparison/generators`.

### 5.4 Something every point needs, made once

```toml
[run.pdf]
sweeps = ["pdf"]
pre    = ["fetch"]                                # once, before every point
tools  = [["pythia", "rivet"]]

[tools.fetch]
tool        = "custom"
executable  = "./modules/PhotoProduction/fetch_lhe.sh"   # your script
arguments   = ["{partial:output}"]
output_file = "shared.lhe"                        # every point may name it: input = "shared.lhe"
```

A changed pre stage reruns the points; a failed one stops the run.

---

## 6. Your own programs

### 6.1 An analysis program

When Rivet is not the right tool (candidate reconstruction, ML features, detector level), write a
program with the module kit ([06 §21](06_Internals.md#21-modulehh)):

```toml
[run.single]
sweeps = []
tools  = [["pythia", "lamriv", "lambda"], "yd2rt"]

[prelim]
fifo = ["to_rivet.hepmc", "to_module.hepmc"]     # one FIFO per reader

[tools.pythia]
tool        = "pythia"
baseconfig  = "lambda.cmnd"
output_file = ["to_rivet.hepmc", "to_module.hepmc"]   # fan-out: the same events to both

[tools.lambda]
tool        = "module"
executable  = "Lambda.exe"                        # build/Lambda/Lambda.exe
input       = "to_module.hepmc"
output_file = "lambda.root"

[tools.lambda.config]                              # its config: argument 1
mass_tolerance = 0.15

[quantities.masstol]                               # one quantity, two consumers
target = ["lamriv/Lamriv", "lambda"]
key    = { lamriv = "MASSTOL", lambda = "mass_tolerance" }
values = [0.05, 0.10, 0.15, 0.25]
```

- **Sweeping its options:** a module's options can be swept; the value lands in its config
  (`mass_tolerance`).
- **Scaling:** fill with raw weights and scale **once** after the loop. Beside a Rivet histogram,
  scale as a density (`out.scale(σ/ΣW, "width")`, L21).

→ `Lambda/lambda`: the Rivet analysis and the module on the same events, agreeing to YODA's
precision.

### 6.2 An integrated program

One process that runs Pythia (and Rivet) itself, with the runner's sweeps and seeds:

```toml
[run.inproc]
sweeps = []
tools  = ["jets", "yd2rt"]
prelim = {}                                       # no FIFO: the events never leave the process

[tools.jets]
tool           = "module"
executable     = "InprocJets.exe"
output_file    = "photo.yoda"
pythia_cmnd    = true                             # the pythia table's point card (not run)
rivet_analyses = true                             # the rivet table's analysis list
```

**What it gets:** the program reads `job.standard("pythia_cmnd")`: the same card, seeds included,
that App_Pythia would have got, so `inproc` and `single` give the same events.

**What it owns:** what the chain would do (04 §9.4): σ over threads, the final σ to Rivet, the
counting.

**Speed:** Pythia runs on the configuration's `threads`, and `rivet_threads = K` in
`[tools.jets.config]` runs K Rivets on threads of their own, merged at the end. With 12 + 12 it is
about 1.5× faster than the sharded chain (§7.1). K above 1 needs the SISCone patch in `~/HEP` (L29).

The whole files are `configs/PhotoProduction/InProcEIC.toml` and `InProcZeus.toml`. How it is built:
[06 §21](06_Internals.md#21-modulehh). → `eic inproc`.

### 6.3 A custom tool, and a Python one

```toml
[tools.fit]
tool        = "custom"
executable  = "path:python3"                      # a command on PATH, asked for by name (V54)
arguments   = ["./modules/Lambda/fit_mass.py", "{in:lambda.root}", "{partial:output}"]   # your script
input       = "lambda.root"
output_file = "fit.json"
consumes    = ["sqrts"]                           # → [quantities] in its config

[tools.fit.config]
window = [1.09, 1.14]
```

- **Its config:** the file `output/…/<point>/config/fit.toml` is the first argument. A quantity
  with `target = "fit"` and `key = "window"` sweeps a key of it.
- **Its products:** write them to `{partial:output}`; the runner renames them after the checks.
- **Its status:** set `filters = "my_rules.toml"` for a progress bar from your prints
  ([06 §23](06_Internals.md#23-filterstoml)), or speak the status protocol with `utils/hepkit.py`
  ([06 §22](06_Internals.md#22-statushh-and-the-status-protocol)). `hepkit` also gives the exit
  codes and the report a module writes.

---

## 7. Scale and statistics

### 7.1 More Rivets

A Rivet process uses one core, so in a Pythia → Rivet chain it is the limit (about 1,500 events/s
with ZEUS_2012), and more Pythia threads only wait for it. Split its events among several:

```toml
[run.default]
threads = 12                     # Pythia's threads

[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["ZEUS_2012_I1116258"]
output_file = "zeus.yoda"
shards      = 10                 # 10 Rivet processes, each on a share, merged into zeus.yoda
```

Nothing else changes: not the chain, not the file names, not what the later tools and the pages
read. The runner deals the events among ten FIFOs, runs ten Rivets, checks each one's count, and
merges them with `rivet-merge -e` ([05 §5.1](05_Commands_and_Tools.md#51-sharded-rivet-shards--k)).

- **The result:** the events are the same as unsharded, so the result is the same. The point
  reruns, since its commands changed.
- **Cores:** keep `threads + shards` within the machine's cores.
- **For one run only:** `--set tools.rivet.shards=10 --set run.default.threads=12`.
- **Analyses:** every analysis must be re-entrant (`Reentrant: true` in its `.info`).

### 7.2 Several points at once

When one point cannot fill the machine (a Rivet that stops scaling, or many short points each
spending ~5 s in Pythia's init), run several points at once:

```toml
[run]
threads     = 5                  # each point's Pythia threads, as before
parallelism = 4                  # 4 points at a time: ~4 × (5 + its Rivets) cores; "auto": as many as fit
```

- **The results don't change:** every point gets exactly the result it gets one at a time.
  `parallelism` is not in any identity or seed, so it reruns nothing either.
- **The output stays apart:** each point keeps its own folder, and the view prints each point's
  block whole when it ends (in the order they finish).
- **Planning:** `--plan` prints the estimate ("4 at once (~24 of 24 cores)") and warns past the
  machine. For one run: `--set run.parallelism=4`.

### 7.3 Replicas, merged

```toml
[run.replicas]
sweeps = ["replica"]
tools  = [["pythia", "rivet"]]
post   = ["merge"]                   # once, after every point is complete

[quantities.replica]
target = "pythia/seed"               # only changes the seed
values = [1, 2, 3]
tags   = ["s1", "s2", "s3"]

[tools.merge]
tool        = "merge"                # rivet-merge -e
input       = "photo.yoda"           # that product of every point
output_file = "merged.yoda"          # → results/…/replicas/post/merged.yoda
```

→ `eic replicas`, `lambda replicas`. The post stage runs only when every point is complete, and
reruns when any point changes.

**Seeds per curve, merged** (`combine`, [04 §5.5](04_Config_Reference.md#55-combine)): sweep the
replica beside the quantity you compare, and merge each value's seeds into one curve.

```toml
[run.default]
sweeps  = ["pdf", "replica"]         # 4 PDFs × 5 seeds
combine = ["replica"]                # one curve per PDF: its 5 seeds merged, 5× the statistics
tools   = [["pythia", "rivet"]]
```

- **Where they go:** the merged YODAs are `results/…/default/<pdf>/zeus.yoda`, beside the seeds'
  own folders, and the pages are drawn from them.
- **The spread:** a second configuration with the same sweeps and no `combine` gets the same seeds,
  and draws each as its own curve: how far one seed's result wanders. → `zeus_seedSweep` (and its
  `spread`).
- **For one figure only:** to merge for one figure while the run keeps the seeds apart, use a
  `merged` figure ([03 §7.4](03_Plots.md#74-merged-points-merged-for-this-figure)).

### 7.4 Seeds, and repeating a run

By default a point's seeds follow its generator's identity, so the same setup always gives the same
events. A `Random:seed` in your card is ignored, because the runner writes its own after it. To
choose the seeds yourself:

```toml
[run]
seed_type   = "manual"           # "identity" (default) | "manual" | "random"
manual_seed = 3245364            # every point's seed; [run.<cfg>] can set its own

[quantities.seed]                # or one exact seed per point, swept like anything else
target = "pythia/seed"
values = [1001, 2001, 3001]
```

- **`"manual"`:** a point gets exactly its seed; at `threads = 12` its threads get seed … seed + 11.
  Space swept seeds by at least `threads`: two points with the same setup whose blocks overlap would
  repeat events, so the plan refuses them. Points with different physics may share one seed.
- **`"random"`:** a new seed is drawn each time a point runs. A complete point keeps its sample (it
  is skipped as usual), and `--rerun` draws again.
- **Repeating a run:** every point's `provenance.json` records the seed it used, and `--plan` shows
  each point's seed.
  - `hep reproduce output/…/<point>/provenance.json` runs the point again exactly as it ran, beside
    the original, and compares the products (§10).
  - Or set `seed_type = "manual"` and that seed.

---

## 8. Watching, subsets and reruns

| You want | Type |
|---|---|
| to look before running | `hep run CONFIG CFG --plan` |
| what would rerun, and why | `--why` (what changed since each point last completed) |
| each value and where it came from | `--show-config` |
| a subset | `--points 27x920_MSTW08lo,pdf=NNPDF23lo,3` (names, tags, `q=tag`, indices) |
| fewer events, once | `--set run.event_count=50000` (dotted keys into the TOML, repeatable) |
| a finished point again | `--rerun` (with `--points` for one) |
| only the pages | `--only plot`, or `hep plot CONFIG CFG` |
| only the post (or pre) tools | `--only post` / `--only pre` |
| plain lines (logs, CI) | `--plain` (automatic when not a terminal) |
| to follow a job elsewhere | `hep watch [CONFIG [CFG]]` (a `--journal` run's file: `hep watch --file …`) |
| a desktop notification at the end | `[run] notify = "desktop"` |
| a point faster | `shards = K` on the Rivet table (§7.1); more Pythia `threads` alone do not help |
| many points faster | `parallelism = K` or `"auto"` (§7.2) |

The identity covers cards, argv, binaries, analyses and their plugins, events and threads, and the
seeds derive from it. So a rerun of an unchanged point does nothing, and a changed one reruns by
itself. Threads are part of the identity: `--set run.pdf.threads=8` makes every point "to run".

---

## 9. When something fails

The run goes on to the next point, and the point's block names the tool to blame. Then:

1. Read `output/…/<point>/logs/<tool>.log` (and `<tool>.prepare.log`, `prelim.log`): a failed tool's
   last 200 lines. For a tool's whole output, run again with `--logs`.
2. A product that failed its checks keeps its `.partial` name, and the point has no `.complete`, so
   it runs again next time.
3. *"rivet analysed N events; the producer wrote M"*: the chain broke mid-stream. Look at the
   generator's log first.
4. *"… was silent for 300 s"*: a stall. Raise `stall_after` on the tool if it is legitimately quiet.
5. Fix it, then `hep run … --points <that point>`. Complete points are skipped anyway.
6. More to look at:
   - `--plan` shows the exact argv and cards;
   - `--journal` writes the job's every event to `output/…/<cfg>/status.jsonl`;
   - `provenance.json` records every binary and card of a finished point.

Ctrl-C stops the job cleanly: the running tools get SIGINT, then SIGTERM, then SIGKILL. The exit is
6, and the same command resumes. `hep run` exits:
- 0 when everything is done;
- 1 when a point, a stage or a page failed;
- 2 for a config error (nothing ran).

Common refusals, and what they mean:

| Message | Means |
|---|---|
| `[quantities.X] is set but no tool in this chain consumes it` | nothing would change with X: give it a `key`, a `target`, or drop it (C7) |
| `'delphes' cannot read a FIFO` | use a `[prelim] files` entry and put Delphes in a later group (C6) |
| `FIFO 'x' connects A and B across groups` | put A and B in one group, or use a file (C6) |
| `'photo_eic' does not declare the option X` | the option is not in the analysis's `.info` (C9) |
| `the PDF set 'X' is not installed` | `lhapdf install X` (C10) |
| `'…' is TLatex; labels are LaTeX` | write the LaTeX the hint gives, or `hep migrate` the file (§10) |
| `[plot.overlay] is a figure now` | `[plot.figures.<name>] class = "overlay"`, or `hep migrate` |
| `base config not found` | the card is not under `configs/<P>/` (write `./path` for elsewhere) |
| `build/App_Pythia.exe is not built` | `hep build` |
| `unknown section [schema]` | a v1 (hekit) run TOML: the schema is 04; `git show HEAD:<file>` has the current one |

---

## 10. Housekeeping: check, status, clean, migrate, reproduce

```bash
hep check                                   # every config: loaded, validated, every point planned; runs nothing
hep ls PhotoProduction                      # every config and its configurations (* = what hep run runs)
hep explain plot.y_gutter                   # a key's type, default and meaning
hep status PhotoProduction/eic              # each point: complete, stale, incomplete or to run
hep status --stack                          # each package's version
hep clean PhotoProduction/eic --dry-run     # what the runner made and no plan uses (output/ only)
hep migrate PhotoProduction/eic             # a diff of the file in today's forms; --apply writes it
hep reproduce output/…/<point>/provenance.json   # the point again, beside it, compared
```

- **Before a long sweep, or as a pre-commit hook:** `hep check` exits 2 when any config is not
  well.
- **Clean:** `hep clean` never removes a result. It lists first and asks (`--yes` elsewhere), and it
  refuses while a job runs.
- **Migrate:** `hep migrate` rewrites old forms by line, so comments and layout stay:
  - TLatex labels;
  - `swept = false`;
  - `[plot.overlay]` and `[plot.object]`;
  - a bare `executable`;
  - base-card lines the runner owns.
- **Reproduce:** `hep reproduce` stops and says what changed when the setup is no longer the one the
  provenance records; `--anyway` runs today's setup with the recorded seed.

Each command is in [05 §1](05_Commands_and_Tools.md#1-commands).

---

## 11. Reading results from Python

```python
import sys
sys.path.insert(0, "utils/Env")             # from the repository root
from runner import results

for point in results.load("PhotoProduction/eic", "energy_pdf"):
    print(point.name, point.values["pdf"].label, point.complete, point.yoda())
```

`results.load(CONFIG, CONFIGURATION)` (V77) reads a configuration's `points.json` and returns its
points. Each has:
- `name`;
- `values` (quantity → its `tag`, `label`, `value`, `swept`);
- `products` (name → path), `results`, `output`;
- `complete`, `identity`, `seed`;
- `yoda()` / `root()` for the product of that kind.

`results.runs(CONFIG)` gives every configuration that has run. It plans nothing, so it needs no tool
installed: for notebooks and statistics tools.

---

## 12. A new project

1. `configs/<Project>/`: the native base card(s) and a run TOML with `project = "<Project>"`.
2. `modules/<Project>/`: Rivet plugins in `Rivet/<name>.cc` (with `.info`, `.plot`, `.yoda`), and
   programs as `<Name>.cc` with a `// requires:` line. Headers beside them are shared by both.
3. `hep build`, then `hep check <Project>/<run>`, then `hep run <Project>/<run> --plan`.
4. A quantity the vocabulary does not map gets a `key`. One your project uses everywhere can go in
   `configs/<Project>/master.toml`, named by `[master] master_toml = "master.toml"`.
5. Tables several run TOMLs share can live in one file that each names in `[master] include` (04 §1).
