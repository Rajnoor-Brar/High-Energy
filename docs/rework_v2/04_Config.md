# 04 — Configuration

This document formalises the run TOML from *Brief §Configurations* ([00_Brief.md](00_Brief.md)):
every section, its keys, what they mean, and what is checked. Examples are complete TOML. The
translations in §8 are the v1 configs rewritten in this schema, so they can be compared line for
line.

---

## 1. Three kinds of file

| File | Holds | Who writes it |
|---|---|---|
| **native base cards** (`configs/<P>/*.cmnd`, `.in`, `.yaml`, `.sin`, `proc_card.dat`) | the physics | the user; never modified by the runner |
| **run TOML** (`configs/<P>/<run>.toml`) | configurations, sweeps, tools, wiring, plots | the user |
| **master TOML** (`utils/Env/master.toml`, optionally overlaid by `configs/<P>/master.toml`) | how each standard tool consumes named quantities | the framework, and the project if it needs to |

**Physics stays in the native card** (v1's D3, *Brief §Configurations*: "configuration will be
provide to processes via config files"). A quantity *renders an override* into a point card. The
base card is read first and the override is applied by each tool's own rule, for example
append-last-wins for Pythia (see [05_Tools.md](05_Tools.md)).

---

## 2. `[master]`

```toml
[master]
master_toml = "master.toml"     # → configs/<project>/master.toml; optional
```

`utils/Env/master.toml` always loads first. A project master, if named, **overlays** it, key by
key. **Precedence, lowest to highest:**

```
utils/Env/master.toml   <   [master].master_toml   <   [quantities.<q>] in the run TOML   <   --set
```

The default master's shape, the brief's `[quantities.{standard_tool}.compatible_quantities]`:

```toml
# utils/Env/master.toml (excerpt)

[quantities.pythia.compatible_quantities]
energies = { keys = ["Beams:eA", "Beams:eB"] }     # a pair → two keys, in order
sqrts    = { key = "Beams:eCM" }
beam_a   = { key = "Beams:idA" }
beam_b   = { key = "Beams:idB" }
pdf      = { key = "PDF:pSet", format = "LHAPDF6:{}" }
events   = { key = "Main:numberOfEvents" }          # built-in quantity (§6.3)
threads  = { key = "Parallelism:numThreads" }       # built-in quantity (§6.3)

[quantities.herwig.compatible_quantities]
energies = { render = "beam_energies" }             # a function in utils/Env/herwig/render.py
pdf      = { render = "pdf_set" }
events   = { flag = "-N" }                          # a command-line flag, not a card line
seed     = { flag = "-s" }

# rivet has no compatible quantities: it reads beams and energies from the events, and its
# analysis options are always targeted explicitly (target = "<tag>/<analysis>", §6.1)
```

A mapping entry takes exactly one of these forms:

| Form | Means |
|---|---|
| `key = "K"` | the card line `K = value` |
| `keys = ["K1", "K2"]` | a list value spread over several keys, in order |
| `format = "LHAPDF6:{}"` | added to `key`: how the value is written |
| `flag = "-N"` | a command-line argument instead of a card line |
| `render = "fn"` | a named function in the tool's `render.py`, for dialects a key cannot express (Sherpa YAML paths, Whizard beam structure) |

**Why the mapping is data.** v1 decided a quantity's effect with a nine-way `type` dispatch in
code (`sweep/expand.py:95`). Here the same knowledge is a table the user can read and a project can
extend, and the runner only needs to apply it.

---

## 3. `[run]`

```toml
[run]
serial        = 3                   # optional: directory prefix 03_ (03_Layout_Build.md §3)
name          = "eic"               # the run's directory name
project       = "PhotoProduction"   # → configs/, modules/, output/, results/ subfolder
configuration = "pdf"               # default; `hep run <config> <configuration>` overrides
event_count   = 1_000_000           # optional defaults inherited by every configuration
threads       = 20
```

| Key | Type | Required | Notes |
|---|---|---|---|
| `serial` | int ≥ 0 | no | location only, never identity (V12) |
| `name` | string, filename-safe | yes | |
| `project` | string | yes | must match the folder the file is in |
| `configuration` | string | yes | must name a `[run.<cfg>]` |
| `event_count`, `threads` | int | no | defaults for configurations that do not set them. `threads = 0` means hardware concurrency, **resolved to an integer at plan time** (v1's "resolved means resolved"). |

---

## 4. `[run.<configuration>]`

```toml
[run.energy_pdf]
serial      = 4
name        = "energy_pdf"                      # directory name; defaults to the table key
description = "one page per energy, PDF curves on each"
event_count = 500_000                           # overrides [run]
threads     = 20
sweeps      = ["energies", "pdf"]               # grid: 4 energies × 4 PDFs = 16 points
plot_points = ["energies"]                      # 4 pages; the PDFs are the curves on each
tools       = [["pythia", "rivet"], "yd2rt"]    # group 1 together (FIFO), then group 2
post        = []                                # tools run once after all points (V15)
static      = { lepton = "ep" }                 # this configuration's own static values
```

### 4.1 `sweeps`

The brief: *"sweeps = [thisQuantity, [these two, together], and this]"*.

- A **string** entry is an independent axis. The points are the **grid** (Cartesian product) of
  all independent axes.
- A **list** entry is an **entangled** group: its quantities move together, value *i* with
  value *i*, so they must have equal value counts. The group is one axis of the grid.
- Order matters for point naming (tags are joined in `sweeps` order) and for iteration order.
- `sweeps = []` means one point.

```toml
sweeps = ["energies", ["pdf", "alphas"], "mpi"]
# energies: 4 values;  pdf+alphas: 3 values each, zipped;  mpi: 2 values
# → 4 × 3 × 2 = 24 points
```

The semantics are v1's coupled `across`, which the runner writes fresh in about 40 lines. For
reference, the v1 code is in git at `utils/python/hekit/sweep/select.py:49,72` and
`sweep/expand.py:188`.

### 4.2 `plot_points`

The brief: *"plots will be separated by grid of point based on these quantities"*.

- Each listed quantity must be swept. The **pages** are the grid of their values, and **every
  other swept quantity becomes the curves** on each page.
- `plot_points = []` (the default) is one page with every point as a curve.
- An entangled group is one axis. Naming its first member selects the group. Naming a second
  member of the same group adds nothing, and the plan says so (following the brief).

| `sweeps` | `plot_points` | Pages | Curves per page |
|---|---|---|---|
| `["pdf"]` | `[]` | 1 | 4 PDFs |
| `["energies", "pdf"]` | `["energies"]` | 4 | 4 PDFs |
| `["pt0ref", "mpi"]` | `["mpi"]` | 2 | 3 pT0Ref values |

This is v1's `overlay` turned inside out. v1 named the one quantity that became curves; v2 names
the quantities that become pages, which is what the brief asks for.

### 4.3 `tools` and `post`

The brief: *"tools = [firstThis, [these ones, together with &], thenthis] (sequence of tool call
for each point)"*.

- Each entry is a **tool tag**, a key of `[tools.<tag>]`, or a **list** of tags that run
  **together** as one group.
- Groups run in order, and a group starts only when the previous one succeeded.
- A bare standard tool name with no `[tools.<name>]` table is allowed when that tool needs no
  options (`yd2rt`). Otherwise it is an error.
- `post` has the same form, and runs **once after all points**, with the points manifest (02 §6).
  It is planned as one more point, `<cfg>/post/`, with no quantities. An `input` naming a product
  of the points (`input = "photo.yoda"`) reads that product of every point, spliced into argv by
  `{inputs}`, and `{points}` is `points.json`. Its identity includes every point's, so it reruns
  when any point changes. It runs only when every point is complete: a merge over a subset would
  look like the whole.

### 4.4 `static` inside a configuration

`[run.<cfg>].static` sets values for this configuration only, on top of the file-wide `[static]`
(§6.2). It replaces v1's `[study.<s>.pin]`.

---

## 5. `[prelim]`

The brief: interface files *"tools are given agree upon file that is already made for them so
neither risks inexistence error"*, plus *"other options that need to be evaluated, or executed
BEFORE running tools"*.

```toml
[prelim]
fifo     = ["events.hepmc"]              # mkfifo in the point's output directory
files    = ["showered.hepmc"]            # created empty; the writer truncates; kept after the point
commands = [["lhapdf", "ls", "--installed"]]   # argv lists, run in order before group 1 (placeholders allowed)
```

- Entries are **per point** and live in the point's output directory (03 §2).
- FIFOs are removed when the point ends; files are kept.
- A `[run.<cfg>.prelim]` table overrides `[prelim]` for one configuration.
- A `[prelim]` name is how tools refer to an interface: `input = "events.hepmc"`. The connection
  rules in [02_Architecture.md §5](02_Architecture.md#5-connections-how-data-moves-between-tools)
  are checked against these names.

---

## 6. Quantities and static values

### 6.1 `[quantities.<q>]`

```toml
[quantities.pdf]
values = ["MSTW2008lo68cl", "NNPDF23_lo_as_0130_qed", "NNPDF23_nlo_as_0119_qed", "PDF4LHC21_40"]
tags   = ["MSTW08lo", "NNPDF23lo", "NNPDF23nlo", "PDF4LHC21"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 LO", "NNPDF 2.3 NLO", "PDF4LHC21"]
# no key/target: consumed by every tool in the chain whose master mapping names `pdf`

[quantities.pt0ref]
key    = { pythia = "MultipartonInteractions:pT0Ref" }     # not in the master: say it here
values = [3.0, 3.2, 3.4]
tags   = ["pt30", "pt32", "pt34"]
labels = ["pT0Ref = 3.0 GeV", "pT0Ref = 3.2 GeV", "pT0Ref = 3.4 GeV"]

[quantities.radius]
target = "rivet/photo_eic"      # tool tag / analysis: a Rivet analysis option
key    = "R"
values = [0.4, 0.7, 1.0]
tags   = ["r04", "r07", "r10"]
```

| Key | Type | Notes |
|---|---|---|
| `values` | list (scalars or lists) | required |
| `tags` | list of filename-safe strings | required when swept (point names); same length as `values` |
| `labels` | list of strings | legend text, in ROOT TLatex (`#sqrt{s}`, `e^{-}`; V11) |
| `key` | string, or table `{<tool tag or tool type> = key}` | the native key. Overrides the master for the tools named. |
| `target` | string or list: `"<tag>"` or `"<tag>/<analysis>"` | restricts the consumers to these tools. `/<analysis>` makes it a Rivet analysis option, checked against the `.info` (`00/B14`). |
| `format` | string | how the value is written, e.g. `"LHAPDF6:{}"` |
| `description` | string | shown by `--plan` |

**Who consumes a quantity**, decided at plan time:

1. With `target`: exactly the named tools.
2. Without `target`: every tool in the configuration's chain that has a mapping for the quantity,
   either in the master TOML (by tool type) or in this quantity's `key` table (by tool tag or type).
3. **Zero consumers is an error**, naming the quantity and the tools in the chain. This is the
   check that stops v1's `00/B14`/`00/B40` shape: a swept value that changes a directory name and
   nothing else.
4. More than one consumer is allowed (for example `energies` to both Pythia and a module's config),
   and `--plan` prints the full quantity × tool table.

### 6.2 `[static]`

The brief: *"quantity = value/preset used when not sweeped"*.

```toml
[static]
energies = "27x920"     # a tag of [quantities.energies] …
lepton   = -11          # … or a raw value
pdf      = "#2"         # … or a 1-based index
```

- A static value applies **only when the quantity is not swept** in the active configuration.
- A value resolves as a tag first, then as an exact value (numeric-aware), then as `#N`. This is
  v1's `resolve_selector` (`sweep/quantity.py:91`, decision D-B22).
- A quantity that is neither swept nor static is **inactive**: it renders nothing, and the base
  card's value stands.
- Precedence: `[static]` < `[run.<cfg>].static` < `--set static.<q>=…`.

### 6.3 Built-in quantities

`events`, `threads` and `seed` are provided by the runner, not declared.

| Name | Value |
|---|---|
| `events` | `event_count` |
| `threads` | `threads` |
| `seed` | the step's seed block (02 §7) |

They reach each tool through the master mapping like any other quantity. Unlike declared
quantities they need no consumer: a Rivet step consumes no `events`.

**Replicas.** Statistically equivalent runs are made with a declared quantity that targets the
seed and nothing else:

```toml
[quantities.replica]
target = "pythia/seed"      # enters the generator's identity, so its seed block; renders nothing
values = [1, 2, 3]
tags   = ["s1", "s2", "s3"]
```

The seed itself is never written by hand. It is always derived from the identity (v1's D21).

---

## 7. `[tools.<tag>]`

### 7.1 Common keys

| Key | Type | Notes |
|---|---|---|
| `tool` | string | a folder in `utils/Env/` (`pythia`, `rivet`, `yd2rt`, `module`, `paint`, `herwig`, …) or `"custom"` |
| `baseconfig` | string or list | native base card(s), read in order. Root `configs/<project>/`. |
| `input` | string or list | `[prelim]` names, earlier `output_file`s, or paths |
| `output_file` | string or list | a list gives fan-out: one output per consumer (V16) |
| `timeout`, `stall_after` | seconds | per-tool overrides of the runner defaults |
| `status` | `"standard"`, `"filters"`, `"filters:<file>"`, `"none"` | overrides the tool folder's default (05 §3) |
| *(tool-specific)* | | validated against the tool folder's `[options]` schema, e.g. rivet's `analyses` and `options` |

### 7.2 Custom tools

```toml
[tools.fit]
tool       = "custom"
executable = "FitPeaks.exe"                           # → build/<project>/FitPeaks.exe
arguments  = ["{config}", "{in:lambda.yoda}", "{res}/fit.json"]
input      = "lambda.yoda"
output_file = "fit.json"
consumes   = ["energy"]                               # quantities written into its config
status     = "filters:fit_filters.toml"               # → configs/<project>/fit_filters.toml

[tools.fit.config]                                    # extracted to output/…/<point>/config/fit.toml
model   = "gauss+poly2"
window  = [1.09, 1.14]
```

- `[tools.<tag>.config]` is written verbatim to `config/<tag>.toml`, **plus** a `[quantities]`
  table with the point's values of everything in `consumes`. That file is passed as the **first
  argument**, as the brief specifies, followed by `arguments`.
- A quantity can also target a key inside the extracted config: `target = "fit"`,
  `key = "window"` sets `window` directly. So a custom tool's settings can be swept, which v1's
  modules could not do (`00/B40`).
- `executable` resolves under `build/<project>/`. Use `./…` for anything else.

### 7.3 Standard configurations for custom tools

A custom tool, or a module program, can ask for the configuration the runner renders for a
**standard** tool, and then use it however it likes. The typical use is an **integrated process
run**: one program that runs Pythia, and perhaps Rivet or FastJet, in its own process. The runner
still owns the sweeps, seeds and cards, and the program gets the same point card App_Pythia would
have got.

```toml
[run.inproc]
description = "Pythia + Rivet in one process, same sweeps and seeds as the chain"
sweeps      = ["pdf"]
tools       = ["jets", "yd2rt"]            # pythia is never spawned here; jets runs it in-process

[tools.pythia]                             # configured, not spawned: it describes Pythia's card
tool       = "pythia"
baseconfig = "photo_ep.cmnd"

[tools.rivet]
tool     = "rivet"
analyses = ["photo_eic"]

[tools.jets]
tool           = "custom"
executable     = "InprocJets.exe"          # modules/PhotoProduction/InprocJets.cc
output_file    = "photo.yoda"
pythia_cmnd    = true                      # ask for the pythia table's rendered card (default false)
rivet_analyses = true                      # ask for the rivet table's analysis list
```

The tool's extracted config (its first argument) then carries one `[standard.<key>]` table per
request. Every path in it is absolute:

```toml
# output/PhotoProduction/03_eic/inproc/MSTW08lo/config/jets.toml   (generated)
[standard.pythia_cmnd]
tool  = "pythia"
tag   = "pythia"
path  = "/home/…/output/PhotoProduction/03_eic/inproc/MSTW08lo/cards/pythia.cmnd"   # one file: base, then point overrides
parts = ["/home/…/configs/PhotoProduction/photo_ep.cmnd",
         "/home/…/output/PhotoProduction/03_eic/inproc/MSTW08lo/cards/pythia.point.cmnd"]

[standard.rivet_analyses]
tool        = "rivet"
tag         = "rivet"
analyses    = ["photo_eic"]
plugin_path = "/home/…/build/Rivet"

[quantities]                               # as for any custom tool (§7.2)
pdf = "MSTW2008lo68cl"
```

**Rules:**

- **The keys.** A request is a `<tool>_<export>` key in a `custom` or `module` table. It is **bool,
  default false**.
  - **Every tool that renders a card exports it automatically** as `<tool>_card`, giving `path`
    and `parts`. So `sherpa_card`, `herwig_card`, `delphes_card` and so on exist with no
    declaration.
  - **Named exports are aliases or extras.** `pythia_cmnd` is an alias of `pythia_card`. Things
    that are not a card are declared in the tool folder, for example `rivet_analyses` (values) or
    `herwig_run` and `sherpa_results` (products of a prepare step).
  - The full list is in [05 §2](05_Tools.md#2-the-standard-tools).
- **Which table.** `true` means the tool table tagged `<tool>`, or else the only table with
  `tool = "<tool>"`. If several tables qualify, that is an error. The string form,
  `pythia_cmnd = "shower"`, names the table.
- **Rendered exactly as in a chain.** The exported card is the one that tool would get as a
  process, for this point: base config, consumed quantities, events, threads and **the point's
  identity seeds** (02 §7). An in-process `PythiaParallel` therefore sees the same events
  App_Pythia would. A serial `Pythia8::Pythia` reads `Random:seed`, which is always written as well,
  so it is reproducible too.
- **Configured without being run.** The referenced table need not appear in `tools`. If it does,
  the process and the custom tool get the same card.
- **Quantities count as consumed.** Any quantity the exported tool consumes counts as consumed
  (rule C7), because the export is its route to a process.
- **Prepare on demand.** An export that needs a prepare step (`herwig_run`, `sherpa_results`,
  `madgraph_process`) makes the runner run that step, cached, before the custom tool's group.
- **On the command line too.** `{std:<key>}` in `arguments` expands to the export's `path`, for
  programs that take a card on the command line (03 §2).
- **Identity and provenance** include the exported cards' text.
- **The program takes on the chain's duties.** An integrated program owns what the chain would
  have done: combining σ over threads (L1), passing the final σ to Rivet (L2), catching at thread
  boundaries (L3), and any event counting. There is no FIFO, so the runner checks only the exit
  code and that the declared outputs exist. `Module.hh` provides `job.standard("pythia_cmnd")`
  ([05 §5](05_Tools.md#5-the-module-kit-utilsmodulehh)), and a Python tool reads the table with
  `tomllib`.

---

## 8. Worked translations

Each translation keeps the physics and the studies of the v1 file and changes only the schema.
The v1 → v2 mapping, once:

| v1 (schema 2) | v2 |
|---|---|
| `[run] events, seed, threads` | `[run]`/`[run.<cfg>] event_count, threads`. The seed comes from identity; the base `seed` is not needed. |
| `[generator] tool, card` | `[tools.<tag>] tool, baseconfig` |
| `[beams] ids` | quantities (`beam_a`, `beam_b`) or the base card |
| `[rivet] analyses, paths` | `[tools.<tag>] tool = "rivet", analyses`. The path is always `build/Rivet/`. |
| `[quantity.<q>] type = …` | `[quantities.<q>]` + master mapping, `key` or `target` |
| `[static.use]` + `use = N` | `[static]` |
| `[study.<s>] across, overlay, pin` | `[run.<s>] sweeps, plot_points, static` |
| `[plot]`, `[plot.data]`, `[plot.style]` | `[plot]`, `[plot.data]`, `[plot.style]` (§9) |
| `[[analyzers.module]]` + `.options` | `[tools.<tag>] tool = "module"` + `[tools.<tag>.config]` |
| `[proc.export]` | the `yd2rt` tool |

### 8.1 `configs/PhotoProduction/eic.toml`

Seven of v1's eleven studies are shown. The other four (`mpi_onoff`, `pthatmin`, `process`, and the
`single` variants) follow the same pattern.

```toml
# configs/PhotoProduction/eic.toml — v2 schema
# hep run PhotoProduction/eic            (configuration from [run])
# hep run PhotoProduction/eic energy_pdf

[run]
serial        = 3
name          = "eic"
project       = "PhotoProduction"
configuration = "pdf"
event_count   = 1_000_000
threads       = 20

[run.single]
description = "One run at the static point"
sweeps      = []
tools       = [["pythia", "rivet"], "yd2rt"]

[run.pdf]
serial      = 1
description = "Proton-PDF comparison at the static beams"
sweeps      = ["pdf"]
tools       = [["pythia", "rivet"], "yd2rt"]

[run.energies]
serial      = 2
description = "Beam-energy comparison at the static PDF"
sweeps      = ["energies"]
tools       = [["pythia", "rivet"], "yd2rt"]

[run.energy_pdf]
serial      = 3
description = "Beams x PDF grid: one page per energy, PDF curves on each"
sweeps      = ["energies", "pdf"]
plot_points = ["energies"]
tools       = [["pythia", "rivet"], "yd2rt"]

[run.mpi]
serial      = 4
description = "MPI pT0Ref scan at 18x275"
sweeps      = ["pt0ref"]
tools       = [["pythia", "rivet"], "yd2rt"]
static      = { energies = "18x275" }

[run.mpi_grid]
serial      = 5
description = "pT0Ref x MPI grid: one page per MPI setting"
sweeps      = ["pt0ref", "mpi"]
plot_points = ["mpi"]
tools       = [["pythia", "rivet"], "yd2rt"]
static      = { energies = "18x275" }

[run.radius]
serial      = 6
description = "Jet radius R at 18x275 (three points, three generations: V9)"
sweeps      = ["radius"]
tools       = [["pythia", "rivet"], "yd2rt"]
static      = { energies = "18x275" }

[prelim]
fifo = ["events.hepmc"]

[static]
energies = "27x920"
lepton   = "ep"
pdf      = "NNPDF23lo"
pt0ref   = "pt32"
mpi      = "mpi"

[tools.pythia]
tool        = "pythia"
baseconfig  = "photo_ep.cmnd"
output_file = "events.hepmc"

[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["photo_eic"]
output_file = "photo.yoda"

[tools.yd2rt]
tool        = "yd2rt"
input       = "photo.yoda"
output_file = "photo.root"

[quantities.energies]
values = [[41, 5], [100, 10], [275, 18], [920, 27.5]]
tags   = ["5x41", "10x100", "18x275", "27x920"]
labels = ["5x41 GeV", "10x100 GeV", "18x275 GeV", "27x920 GeV"]

[quantities.lepton]
key    = { pythia = "Beams:idB" }
values = [11, -11]
tags   = ["em", "ep"]
labels = ["e^{-}", "e^{+}"]

[quantities.pdf]
values = ["MSTW2008lo68cl", "NNPDF23_lo_as_0130_qed", "NNPDF23_nlo_as_0119_qed", "PDF4LHC21_40"]
tags   = ["MSTW08lo", "NNPDF23lo", "NNPDF23nlo", "PDF4LHC21"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 QCD+QED LO", "NNPDF 2.3 QCD+QED NLO", "PDF4LHC21"]

[quantities.pt0ref]
key    = { pythia = "MultipartonInteractions:pT0Ref" }
values = [3.0, 3.2, 3.4]
tags   = ["pt30", "pt32", "pt34"]
labels = ["p_{T0}^{ref} = 3.0 GeV", "p_{T0}^{ref} = 3.2 GeV", "p_{T0}^{ref} = 3.4 GeV"]

[quantities.mpi]
key    = { pythia = "PartonLevel:MPI" }
values = [true, false]
tags   = ["mpi", "nompi"]
labels = ["MPI on", "MPI off"]

[quantities.radius]
target = "rivet/photo_eic"
key    = "R"
values = [0.4, 0.7, 1.0]
tags   = ["r04", "r07", "r10"]
labels = ["R = 0.4", "R = 0.7", "R = 1.0"]

[plot]
backend     = "root"
formats     = ["pdf", "png"]
objects     = ["/photo_eic/*"]
ratio       = true
y_gutter    = 1.5
auto_range  = true
void_empty  = false
min_entries = 1

[plot.data]
file   = "zeus_eic.yoda"
legend = "ZEUS 2012"

[plot.data.map]      # explicit, never matched by name (00/B5)
"d01-x01-y01" = "/REF/ZEUS_2012_I1116258/d01-x01-y01"
"d02-x01-y01" = "/REF/ZEUS_2012_I1116258/d02-x01-y01"
"d09-x01-y01" = "/REF/ZEUS_2012_I1116258/d09-x01-y01"

[plot.style]
font_size = 13
canvas    = [900, 600]
```

What this shows:

- **The radius configuration** is three points and **three** Pythia runs. v2 does not share
  events between points (V9). To avoid regenerating, keep the events as a file from `single`
  and run a Rivet-only configuration on it ([02 §7](02_Architecture.md#7-identity-seeds-and-skip)).
- **`lepton`** is not in the master, so it names its key. **`pdf`** is in the master, so it does
  not.
- **Labels are TLatex** (`e^{-}`), because ROOT is the primary backend (V11).

### 8.2 `configs/Lambda/lambda.toml` — two analysis paths, and a module option sweep

```toml
# configs/Lambda/lambda.toml — v2 schema
[run]
name          = "lambda"
project       = "Lambda"
configuration = "single"
event_count   = 20_000
threads       = 16

[run.single]
description = "One run at 7 TeV, both analysis paths"
sweeps      = []
tools       = [["pythia", "lamriv", "lambda"], ["yd2rt_rivet", "yd2rt_module"]]

[run.masswindow]
description = "Mass-window scan through both paths: four points, each its own 20k-event generation"
sweeps      = ["masstol"]
tools       = [["pythia", "lamriv", "lambda"], ["yd2rt_rivet", "yd2rt_module"]]

[run.energy]
description = "Lambda yield against collision energy"
sweeps      = ["sqrts"]
tools       = [["pythia", "lamriv", "lambda"], ["yd2rt_rivet", "yd2rt_module"]]

[prelim]
fifo = ["to_rivet.hepmc", "to_module.hepmc"]

[static]
sqrts = "7tev"

[tools.pythia]
tool        = "pythia"
baseconfig  = "lambda.cmnd"
output_file = ["to_rivet.hepmc", "to_module.hepmc"]     # fan-out: one FIFO per reader

[tools.lamriv]
tool        = "rivet"
input       = "to_rivet.hepmc"
analyses    = ["Lamriv"]
options     = { RESERVED = 2 }
output_file = "lamriv.yoda"

[tools.lambda]
tool        = "module"
executable  = "Lambda.exe"                  # build/Lambda/Lambda.exe, from modules/Lambda/Lambda.cc
input       = "to_module.hepmc"
output_file = "lambda.yoda"

[tools.lambda.config]
mass_tolerance      = 0.15
cos_theta_tolerance = 0.0
reserved_protons    = 2
track_pt_min        = 0.0
track_eta_max       = 8.0
bins                = 100

[tools.yd2rt_rivet]
tool        = "yd2rt"
input       = "lamriv.yoda"
output_file = "lamriv.root"

[tools.yd2rt_module]
tool        = "yd2rt"
input       = "lambda.yoda"
output_file = "lambda.root"

[quantities.sqrts]
values = [900.0, 7000.0, 13000.0]
tags   = ["900gev", "7tev", "13tev"]
labels = ["900 GeV", "7 TeV", "13 TeV"]

[quantities.masstol]            # one quantity, two consumers, a key for each
target = ["lamriv/Lamriv", "lambda"]
key    = { lamriv = "MASSTOL", lambda = "mass_tolerance" }
values = [0.05, 0.10, 0.15, 0.25]
tags   = ["m050", "m100", "m150", "m250"]
labels = ["#pm 50 MeV", "#pm 100 MeV", "#pm 150 MeV", "#pm 250 MeV"]

[plot]
backend = "root"
formats = ["png"]
objects = ["/Lambda/*", "/Lamriv/*"]
```

What this shows:

- **`00/B40` is closed.** `masstol` reaches the module through its extracted config. v1 could not
  sweep a module option at all.
- **Each point is independent** (V9). Four `masstol` values are four chains of 20k events each,
  which costs seconds at this event count. Both paths see the *same* events within a point, because
  App_Pythia fans out to both.
- **Fan-out is explicit.** Two readers need two FIFOs, and App_Pythia writes both.
- **v1's normalisation mismatch (`00/B42`) is gone.** The module writes its own YODA file, and the
  two paths are compared in plots, not in one file.

### 8.3 A generator comparison as a configuration

The same job as the user's scratch `generator_comparison.cc`, which hard-codes Pythia, reads Herwig and
Sherpa HepMC, and fills four spectra into one ROOT file. As a v2 configuration, the generator
becomes a quantity whose values are **tool tags** (V19). The scratch file itself is left alone:

```toml
# configs/Comparison/generators.toml — v2 schema (P4 S3)
[run]
name          = "generators"
project       = "Comparison"
configuration = "compare"
event_count   = 50_000
threads       = 8

[run.compare]
sweeps = ["generator"]
tools  = [["@generator", "spectra"], "yd2rt"]      # "@q": the tool tag named by q's value

[prelim]
fifo = ["events.hepmc"]

[quantities.generator]
values = ["pythia", "herwig", "sherpa"]
tags   = ["py8", "hw7", "sh3"]
labels = ["Pythia 8.317", "Herwig 7.3", "Sherpa 3.0.5"]

[tools.pythia]
tool        = "pythia"
baseconfig  = "qcd_pp.cmnd"
output_file = "events.hepmc"

[tools.herwig]
tool        = "herwig"
baseconfig  = "qcd_pp.in"
output_file = "events.hepmc"

[tools.sherpa]
tool        = "sherpa"
baseconfig  = "qcd_pp.yaml"
output_file = "events.hepmc"

[tools.spectra]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["particle_spectra"]       # modules/Comparison/Rivet/particle_spectra.cc: pT, E, eta, Nch
output_file = "spectra.yoda"

[plot]
backend = "root"
formats = ["pdf", "svg"]
ratio   = true
```

### 8.4 A file-based chain: MadGraph → Pythia → Delphes → module

```toml
[run.chain]
sweeps = []
tools  = ["madgraph", "shower", "delphes", "ana"]     # four groups, strictly in order

[prelim]
files = ["unweighted.lhe", "showered.hepmc"]           # files, not FIFOs: every hop crosses a group

[tools.madgraph]
tool        = "madgraph"
baseconfig  = "proc_card.dat"
output_file = "unweighted.lhe"

[tools.shower]
tool        = "pythia"
baseconfig  = "shower_lhe.cmnd"                # the plugin adds Beams:frameType = 4, Beams:LHEF
input       = "unweighted.lhe"
output_file = "showered.hepmc"

[tools.delphes]
tool        = "delphes"                        # streamable = false: a FIFO here is refused at plan time
baseconfig  = "delphes_card_CMS.tcl"
input       = "showered.hepmc"
output_file = "delphes.root"

[tools.ana]
tool        = "custom"
executable  = "DelphesJets.exe"                # modules/<P>/DelphesJets.cc, requires: root delphes
arguments   = ["{in:delphes.root}", "{res}/jets.root"]
input       = "delphes.root"
output_file = "jets.root"
```

---

## 9. `[plot]`

Primary graphics are ROOT, through the Paint app, *"unless explictly told to use yoda"*
(*Brief §Plotting*).

```toml
[plot]
backend     = "root"             # "root" (Paint, default) | "yoda" (rivet-mkhtml / matplotlib)
formats     = ["pdf", "png", "svg"]
objects     = ["/photo_eic/*"]   # which histograms get pages; default every 1D object
ratio       = true               # ratio panel against the first curve, or the data
y_gutter    = 1.5                # y axis to 1.5 × the largest y drawn: room for legend and labels
x_gutter    = 1.0                # the same for x (1.0 = none)
logy        = false
auto_range  = true               # trim empty edges, as v1's auto_range
void_empty  = false
min_entries = 1                  # void a bin fewer raw entries went into, in any curve (across the page)
range_pad   = 0                  # auto_range keeps this many whole bins either side of the filled ones
legend      = "top-right"

[plot.data]                      # reference data, optional
file   = "zeus_eic.yoda"         # → datasets/
legend = "ZEUS 2012"
[plot.data.map]                  # MC object → reference object; explicit only (00/B5)
"d01-x01-y01" = "/REF/ZEUS_2012_I1116258/d01-x01-y01"

[plot.style]
canvas    = [900, 600]
font_size = 13
palette   = ["kBlue+1", "kRed+1", "kGreen+2", "kOrange+7"]

[plot.object."d04-x01-y01"]      # per-object overrides, by name or glob
logy     = true
y_gutter = 3.0
```

- Titles and axis labels come from the Rivet `.plot` file, as in v1 (D9): one label source.
  `[plot.object.<name>]` may override them.
- With `backend = "root"`, `[plot]` becomes one Paint config per page:
  `output/…/plots/<page>/<object>.toml`, run by `build/Paint.exe`
  ([05_Tools.md §7](05_Tools.md#7-paint)), drawn to `results/…/plots/<page>/<object>.<fmt>`. The page
  name is the `plot_points` tags joined by `_`; with no `plot_points` the `<page>/` level is absent.
- Pages are drawn after the points, from the **complete** ones, and again on
  `hep run … --only plot` without running anything. Each point's YODA is converted once, with its
  raw entries, into `output/…/plots/inputs/<point>.root` (keyed by its sha256); the reference data
  into `output/<P>/.cache/datasets/`.
- With `backend = "yoda"` (`utils/Env/yoda/backend.py`), the same pages are drawn by `rivet-mkhtml`,
  one page set per cell, with Paint's ranges and voids (`Paint --dump-ranges`). The voided bins
  are blanked in copies of the YODAs, the mapped data are cut to their aligned run and renamed
  `/REF/<analysis>/<object>` (mkhtml's own reference lookup is off), and labels go TLatex → LaTeX.
  mkhtml always writes PDF and PNG. `[plot.style].font_size` and `palette` have no counterpart and
  are refused.
- Keys a backend cannot honour are **errors**, not silently ignored: v1's `LegendXPos` was parsed
  and dropped.

---

## 10. Validation

All checked at plan time, before any process starts. Every error names the key or the file
(`where`) and says what to do (`hint`), using v1's `HepError` and `fields.py`.

| # | Rule |
|---|---|
| C1 | An unknown key is an error, with a did-you-mean suggestion. A tool-specific key is checked against that tool folder's `[options]` schema. |
| C2 | `[run].configuration` and a command-line configuration name must name a `[run.<cfg>]`. |
| C3 | Every `sweeps` entry must be a declared quantity; entangled groups must have equal lengths; no quantity may appear twice. |
| C4 | `plot_points` must be a subset of `sweeps`, where an entangled group counts once. |
| C5 | Every `tools`/`post` entry must be a `[tools.<tag>]` or an options-free standard tool. Nesting is at most one level. An `@q` entry's values must all be tool tags. |
| C6 | The connection rules ([02 §5](02_Architecture.md#5-connections-how-data-moves-between-tools)): FIFOs within a group only, one reader per FIFO, no FIFO into a `streamable = false` tool, every input produced, one writer per output. |
| C7 | Every active quantity (swept, or given a static value) must have at least one consumer (§6.1). |
| C8 | Two sources setting one native key in one card is an error (v1's `_claim`). |
| C9 | A Rivet option quantity's key must be declared in the analysis `.info` (`00/B14`). |
| C10 | Provider checks: PDF sets named by values are installed (LHAPDF); base configs exist; executables are built (with a hint of the `make` target). |
| C11 | Point directory names must be unique (tags must not collide). |
| C12 | Path rules (03 §2): no `../`; a bare name resolves under its convention root, and a missing file is reported with that root spelled out. |
| C13 | A standard-configuration request (§7.3) must name an export its tool offers (did-you-mean otherwise), and must resolve to exactly one tool table. A `true` request that matches several tables must use the string form. |
