# 04 — Configuration reference

Every key a run TOML accepts, what it means, its default, and what is checked. This is written from
the code (`utils/Env/runner/config.py`, `quantities.py`, `sweep.py`, `tools.py`, `plot.py`), and a
test holds it to the code: every key the loader accepts appears here
(`tests/runner/test_docs.py`). For worked examples of whole pipelines, see
[03_User_Guide.md](03_User_Guide.md). For each standard tool's own keys and behaviour, see
[05_Tools_Reference.md](05_Tools_Reference.md).

**Conventions in this document.** *Type* uses TOML's words (string, integer, float, bool, array,
table). "number" is an integer or a float. A key marked **required** has no default. Everything is
checked **at plan time**, before any process starts: `hep run … --plan` runs every check below.

---

## 1. Files, and which wins

| File | Holds | Written by |
|---|---|---|
| native base cards: `configs/<P>/*.cmnd`, `.in`, `.yaml`, `.sin`, `.mg5`, `.tcl` | the physics | you; never modified by the runner |
| the run TOML: `configs/<P>/<run>.toml` | configurations, quantities, tools, wiring, plots | you |
| `utils/Env/master.toml`, optionally overlaid by a project's master | how each standard tool consumes named quantities (§3) | the framework; a project may add to it |
| `utils/Apps/Paint/base.toml`, optionally a style file | the look of the ROOT pages (§12) | the framework; you, to change every page |

**Physics stays in the native card.** A quantity renders an *override* into a point card; the base
card is read first and the override is applied by the tool's own rule (last wins for Pythia, a
YAML merge for Sherpa, …; see [05](05_Tools_Reference.md)).

**Precedence of a value, lowest to highest:**

```
utils/Env/master.toml  <  [master].master_toml  <  [quantities.<q>].key / target  <  --set
[static]  <  [run.<cfg>].static  <  --set static.<q>=…  <  the value a sweep gives the point
[run].event_count, threads  <  [run.<cfg>].event_count, threads  <  --set
base.toml  <  [plot].root_style file  <  [plot.style]  <  [plot.object."<glob>"].style
```

A run TOML has exactly these top-level sections; any other is an error (C1):
`[master]`, `[run]`, `[prelim]`, `[static]`, `[tools]`, `[quantities]`, `[plot]`.

---

## 2. Paths

Every key that takes a path has **one** convention root. There is no search path and no fallback.

| Written as | Resolves to |
|---|---|
| `name` or `sub/name` | the key's convention root (table below) + `name` |
| `./sub/name` | the **repository root** + `sub/name` (never the working directory, V13) |
| `/abs/path` | as written |
| `../x`, `a/../b` | **an error** (C12): write `./…` or an absolute path |

| Key | Root of a bare name | Example |
|---|---|---|
| `hep run <config>`, `hep plot <config>` | `configs/`, `.toml` optional | `PhotoProduction/eic` → `configs/PhotoProduction/eic.toml` |
| `[master].master_toml` | `configs/<project>/` | `master.toml` |
| `[tools.*].baseconfig` | `configs/<project>/` | `photo_ep.cmnd` |
| `[tools.*].executable` | `build/<project>/`, which must exist; `path:<command>` asks for a command on `PATH` by name (V54) | `Lambda.exe` → `build/Lambda/Lambda.exe`; `path:python3` |
| `[tools.*].status = "filters:<file>"` | `configs/<project>/` | `filters:fit_filters.toml` |
| `[prelim].fifo`, `[prelim].files` | the point's **output** directory | `events.hepmc` |
| `[tools.*].input` | a `[prelim]` name or another tool's `output_file` by name; otherwise a path under the point's output directory | `events.hepmc` |
| `[tools.*].output_file` | a `[prelim]` name → the point's output directory; **any other name → the point's results directory** (a product) | `photo.yoda` → `results/…/<point>/photo.yoda` |
| `[plot].root_style` | `configs/<project>/`, `.toml` optional | `talk` → `configs/<P>/talk.toml` |
| `[plot.data].file` | `datasets/`, or `rivet:<Analysis>` for Rivet's own reference data | `rivet:ZEUS_2012_I1116258` |

**The one judgement:** an interface file named in `[prelim]` is technical and lives in `output/`;
anything else a tool writes is a product and lives in `results/`. So a HepMC file kept for another
configuration goes in `[prelim] files`.

**Where a point lives** (V45, V46: `<run>` is `[run].name`, or the configuration's own `name`; `<cfg>` is `NN_<label>` when there is a
serial, the configuration's if it sets one, else `[run]`'s, and `<label>` is the table key when the
configuration's `label` is empty or unset):

```
output/<P>/<run>/<cfg>/<point>/     cards/  config/  logs/  FIFOs and [prelim] files  provenance.json  .complete
results/<P>/<run>/<cfg>/<point>/    the products
```

The point directory is the swept quantities' tags joined by `_`, in `sweeps` order, or `point`
when nothing is swept. Two points with the same name are an error (C11).

---

## 3. `[master]` and the master TOML

```toml
[master]
master_toml = "master.toml"      # optional: configs/<project>/master.toml overlays the framework's
include     = ["common.toml"]    # optional: run TOMLs whose tables this one starts from (V56)
```

| Key | Type | Default | Notes |
|---|---|---|---|
| `master_toml` | string (path) | none | overlays `utils/Env/master.toml` key by key: an entry for a (tool, quantity) pair replaces the framework's. The file must exist. |
| `include` | string or array (paths) | none | files under `configs/<project>/` (`.toml` optional) whose tables the run starts from, in order; **this file wins** (V56). A quantity, tool table or configuration of the file replaces the included one whole; `[plot]`, `[static]`, `[prelim]` and `[run]`'s own keys merge key by key, tables recursively. An included file has no `[master]` of its own. `--show-config` lists what came from where. |

A master TOML maps a **quantity name** to what it means for one **tool type**:

```toml
[quantities.pythia.compatible_quantities]           # [quantities.<tool>.compatible_quantities]
sqrts    = { key = "Beams:eCM" }                      # the card line  Beams:eCM = value
energies = { keys = ["Beams:eA", "Beams:eB"] }        # an array value spread over several keys, in order
pdf      = { key = "PDF:pSet", check = "pythia_pdf" }  # the value as written; a provider check (C10)

[quantities.herwig.compatible_quantities]
seed_offset = { flag = "-x" }                         # a command-line argument instead of a card line
```

Each entry takes **exactly one** of `key`, `keys`, `flag` (`format` and `check` are additions).
`check` is a provider check (C10), with the `lhapdf install <set>` line to type when a set is not
under `LHAPDF_DATA_PATH`. `"lhapdf"` takes a bare set name, `<set>[/member]`, as Sherpa does.
`"pythia_pdf"` takes the value exactly as Pythia's `PDF:pSet` reads it (V40: no prefix is added):
`"LHAPDF6:<set>[/member]"`, whose set must be installed; one of Pythia's own set numbers (`13`); or
a grid file. A bare name that is an installed LHAPDF set is refused with the `LHAPDF6:` spelling,
since Pythia would read it as a file. The `render` form mentioned in `master.toml`'s header is not
implemented (F11): a tool with a `render.py` takes plain `key` mappings and interprets the keys
itself (a YAML path for Sherpa, a SINDARIN variable for Whizard).

**What the framework's master maps** (`utils/Env/master.toml`):

| Quantity | pythia | sherpa | herwig | whizard | madgraph |
|---|---|---|---|---|---|
| `energies` `[E_A, E_B]` | `Beams:eA`, `Beams:eB` | `BEAM_ENERGIES` | `Luminosity:BeamEMaxB`, `…MaxA` (×GeV) | `beams_momentum` | `ebeam1`, `ebeam2` |
| `sqrts` | `Beams:eCM` | `BEAM_ENERGIES = [√s/2, √s/2]` | `Luminosity:Energy` | — | — |
| `beam_a`, `beam_b` | `Beams:idA`, `Beams:idB` | — | — | — | — |
| `beams` `[id_A, id_B]` | `Beams:idA`, `Beams:idB` | `BEAMS` | — | `beams` (model names) | `lpp1`, `lpp2` |
| `pdf` (checked, C10) | `PDF:pSet = <value>`: write `"LHAPDF6:<set>"`, or a Pythia set number | `PDF_SET[0]` (and `MPI_PDF_SET`): the bare `<set>` | — | — | — |
| `events` (built-in) | `Main:numberOfEvents` | `EVENTS` | (the `-N` flag) | `n_events` | `nevents` |
| `threads` (built-in) | `Parallelism:numThreads` | — | — | — | — |

`rivet` maps nothing: it reads beams and energies from the events, and its analysis options are
always targeted explicitly (§8.1).

---

## 4. `[run]`

```toml
[run]
serial        = 3                   # optional: every configuration's folder becomes 03_<label> (a configuration may override it)
name          = "eic"
project       = "PhotoProduction"
configuration = "pdf"               # the default; `hep run <config> <configuration>` picks another
sweep_runs    = false               # true: `hep run <config>` runs every configuration, in turn (§4.1)
event_count   = 1_000_000           # defaults for every configuration
threads       = 20
description   = "EIC photoproduction studies"
```

| Key | Type | Default | Notes |
|---|---|---|---|
| `name` | string | **required** | the run's directory name |
| `project` | string | **required** | the subfolder of `configs/`, `modules/`, `output/`, `results/`; must equal the folder the file is in, when it is under `configs/` |
| `configuration` | string | **required** unless `sweep_runs` | must name a `[run.<cfg>]` table (C2). Under `sweep_runs` it may be left out; `hep run <config>` then ignores it |
| `sweep_runs` | boolean | false | `hep run <config>` runs every configuration not `swept = false`, one after another (§4.1) |
| `seed_type` | string | `"identity"` | default for configurations: how a point's seeds are chosen, `"identity"`, `"manual"` or `"random"` (02 §8) |
| `manual_seed` | integer | none | default for configurations: under `seed_type = "manual"`, every point's seed (from 1 to the point's generators' `[card] seed_range`: 899,999,999 for Pythia, checked when the point is planned, V54); ignored otherwise (`--plan` says so) |
| `serial` | integer | none | the prefix `NN_` of each configuration's folder, `<name>/NN_<label>`: **location, never identity** (V12). A configuration's `serial` overrides it (V45). Changing it starts a fresh location. |
| `event_count` | integer | none | default for configurations; one of the two must set it |
| `threads` | integer | 1 | default for configurations. `0` means every core, **resolved to a number at plan time** |
| `parallelism` | integer | 1 | default for configurations: how many points run at once (V36). `threads` stays each point's; never part of an identity or a seed, so changing it reruns nothing |
| `description` | string | "" | |

Every other table inside `[run]` is a configuration (§5). Any other key is an error (C1).

### 4.1 `sweep_runs`: every configuration, one run after another

With `sweep_runs = true`, `hep run <config>` runs each configuration not marked `swept = false`, in the
order of the file. Each is **a run of its own**: exactly what `hep run <config> <cfg>` does (its own
title, blocks, verdict, journal, `points.json` and plots, in its own `<run>/<cfg>/` folder),
after one header line of its `title`:

```
run 01 - Proton PDFs -
eic · pdf: 4 point(s), 1000000 events, 12 threads
── point 1/4: MSTW08lo ── ok after 12min 4s
…
4 done, 0 failed, 0 skipped

run 02 - Beam energies -
eic · energies: 4 point(s), 1000000 events, 12 threads
…
```

- **Every run is planned before the first starts**, so a config error in any of them exits 2 with
  nothing run. Each is planned again when its turn comes, so edits to the TOML made meanwhile
  count; a run an edit has broken fails alone (exit 2 for it, and the next one starts).
- **A failed run leaves the next to start.** Ctrl-C stops the running run (exit 6, as always) and
  **starts no more**.
- The exit code: 6 if a run was stopped; else 1 if any failed; else 0.
- `hep run <config> <cfg>` runs just that one, whether or not the sweep is on or it is `swept`.
- `--plan` prints every run's plan under its header; `--rerun`, `--set` and `--only plot` apply to
  each; `--only pre|post` skips the runs without that stage. `--points` is refused: its tags belong
  to one configuration, so name it (`hep run eic pdf --points …`).
- Being in a sweep changes no run: not its identity, its seeds or its folder.

---

## 5. `[run.<configuration>]`

```toml
[run.defaults]                               # optional (V56): keys every configuration starts from
tools       = [["pythia", "rivet"], "yd2rt"]
threads     = 20

[run.energy_pdf]
serial      = 3
label       = "energy_pdf"                   # folder name (after the serial); defaults to the table key
title       = "Beams x PDFs"                 # the header line under [run].sweep_runs (§4.1)
description = "Beams x PDF grid: one page per energy, PDF curves on each"
event_count = 500_000                        # overrides [run]
threads     = 20
sweeps      = ["energies", "pdf"]            # 4 × 4 = 16 points
plot_points = ["energies"]                   # 4 pages; the PDFs are the curves on each
tools       = [["pythia", "rivet"], "yd2rt"] # group 1 together (FIFO), then group 2
pre         = []                             # run once, before every point
post        = []                             # run once, after every point
static      = { energies = "18x275" }        # this configuration's own static values
prelim      = { fifo = ["events.hepmc"] }    # replaces [prelim] for this configuration
```

A configuration's value is **its own, else the one it `extends`'s (in turn), else `[run.defaults]`'s,
else `[run]`'s, else the default** (V56); `"default"` in a layer is the next layer's value (V55).
`label`, `title`, `extends` and `swept` are each configuration's own, and `[run.defaults]` refuses
them; `defaults` is never a configuration. `hep run CONFIG --show-config` prints every value with the
layer it came from.

```toml
[run.pdfs]
sweeps      = ["pdf"]
event_count = 10_000_000

[run.pdfs_100M]
extends     = "pdfs"                         # everything of pdfs, then these
event_count = 100_000_000
label       = "PDFs_100M"
```

| Key | Type | Default | Notes |
|---|---|---|---|
| `extends` | string | none | another configuration this one starts from (chains are followed; a circle is refused) |
| `tools` | array | **required** (here or in a layer) | §5.3 |
| `sweeps` | array | `[]` | §5.1; `[]` is one point |
| `plot_points` | array of strings | `[]` | §5.2 |
| `combine` | array of strings | `[]` | swept quantities whose points are merged into one curve (§5.5) |
| `event_count` | integer | `[run].event_count` | required here if `[run]` has none |
| `threads` | integer | `[run].threads`, else 1 | `0` = every core |
| `parallelism` | integer | `[run].parallelism`, else 1 | points at once; `--plan` and the run's title say about how many cores that is, and warn past the machine's |
| `pre`, `post` | array | `[]` | the form of `tools` (§5.4) |
| `static` | table | `{}` | merged over `[static]` and the layers', key by key (§7); a `"default"` keeps the layer below's |
| `prelim` | table | `[prelim]` | the nearest layer's **replaces** `[prelim]` whole for this configuration (its chain's interfaces); `{}` means none |
| `serial` | integer | `[run].serial` | overrides `[run].serial` for this configuration: its points go to `<P>/<run name>/NN_<label>/` (V45) |
| `name` | string | `[run].name` | the run folder above this configuration's: `<P>/<name>/NN_<label>/` (V46) |
| `label` | string | the table key | the configuration's folder, after the serial: `NN_<label>`; empty means the table key (V45) |
| `title` | string | the table key | the header line of the run under `[run].sweep_runs`: `run 02 - <title> -` (§4.1) |
| `swept` | boolean | true | `false` leaves this configuration out of `[run].sweep_runs` (§4.1); `hep run <config> <cfg>` still runs it |
| `seed_type` | string | `[run].seed_type` | `"identity"`: from the generator's identity; `"manual"`: exactly the given seed; `"random"`: drawn when the point runs (02 §8) |
| `manual_seed` | integer | `[run].manual_seed` | the seed of every point under `"manual"`; a quantity targeting `<tool>/seed` gives a point its own |
| `description` | string | "" | |

### 5.1 `sweeps`

- A **string** is an independent axis. The points are the grid (Cartesian product) of the axes.
- An **array** is an **entangled** group: its quantities move together, value *i* with value *i*,
  so they need equal value counts (C3). The group is one axis of the grid.
- Order decides the point names (tags joined in `sweeps` order) and the running order.
- Every name must be a declared quantity; none may appear twice (C3).
- A quantity's `exclude = [i, …]` (1-based) leaves those values out of every sweep of it (§8).

```toml
sweeps = ["energies", ["pdf", "alphas"], "mpi"]    # 4 × 3 × 2 = 24 points: pdf and alphas zipped
```

### 5.2 `plot_points`

Each name must be swept here (C4). The **pages** are the grid of their values, and every other
swept quantity becomes the **curves** on a page. `[]` is one page with every point as a curve.
Naming one member of an entangled group selects the group.

| `sweeps` | `plot_points` | Page folders | Curves per page |
|---|---|---|---|
| `["pdf"]` | `[]` | 1 (no folder) | 4 |
| `["energies", "pdf"]` | `["energies"]` | 4 (`5x41/`, …) | 4 |
| `["pt0ref", "mpi"]` | `["mpi"]` | 2 | 3 |

### 5.3 `tools`

- Each entry is a **tool tag** (a key of `[tools.<tag>]`) or an **array of tags** that run
  **together** as one group (one level only; C5). An empty group is an error.
- Groups run in order; a group starts only when the previous one succeeded and its products passed
  their checks.
- **`"@<quantity>"`** is replaced, per point, by the tool tag that quantity's value names (V19):
  `tools = [["@generator", "spectra"]]` with `values = ["pythia", "herwig", "sherpa"]`. The quantity
  must be swept or static, and every value must be a tool tag (C5).
- A tag that is only *exported* to another tool (§9.4) need not be in `tools`: it is configured and
  rendered, not run.

### 5.4 `pre` and `post`

The same form as `tools`, run **once**:

| | When | Where | Inputs | Identity |
|---|---|---|---|---|
| `pre` | before the first point; a failure stops the run | `…/<cfg>/pre/` | `{points}` (the manifest) | its own; **part of every point's**, so a changed pre stage reruns the points |
| `post` | after the points, **only when every point is complete** | `…/<cfg>/post/` | an `input` naming a product of the points reads that product **of every point** (`{inputs}`, `{named_inputs}`); `{points}` | its own plus every point's: it reruns when any point changes |

Neither takes quantities or `[prelim]`. A point may not be named `pre` or `post`. A pre tool's
products are interfaces every point may name as `input`. A post tool may not write a file with the
name of the points' product.

### 5.5 `combine`

`combine = ["replica"]` (V35) merges the points that differ **only** in the combined quantities: each
group becomes one curve with their statistics added. The typical use is seed replicas, so one PDF's
five 1M-event seeds become one 5M-event curve:

```toml
[run.default]
sweeps  = ["pdf", "replica"]        # 4 PDFs × 5 seeds = 20 points
combine = ["replica"]               # 4 groups, one per PDF: rivet-merge -e of its 5 seeds
tools   = [["pythia", "rivet"]]

[quantities.replica]
target = "pythia/seed"              # a seed block of its own per value (§8); renders nothing
values = [1, 2, 3, 4, 5]
tags   = ["s1", "s2", "s3", "s4", "s5"]
```

| | |
|---|---|
| The groups | points with the same values of every other swept quantity; named by those values' tags (`MSTW08lo`), or `combined` when every swept quantity is combined |
| The merge | a stage per group, after its points: the `merge` tool (`rivet-merge -e`, [05 §5](05_Tools_Reference.md#5-merge--rivet-merge-in-post)) of the points' YODA product into `results/…/<cfg>/<group>/<product>`, beside the points' folders; skipped when complete, rerun when any of its points changes; `--plan` lists them |
| The pages | drawn from the groups, not the points: the combined quantities are neither pages nor curves; `plot_points` and the curves are the other swept quantities |
| Rules (C14) | each name is swept here as an axis of its own (not inside an entangled group), and is not in `plot_points` |

The points themselves keep their own products, and another configuration with the same sweeps and
no `combine` (`plot_points = ["pdf"]`, say) draws each seed as its own curve, from the same seeds
and events. Whole example: `configs/PhotoProduction/zeus_seedSweep.toml`.

---

## 6. `[prelim]`

Interfaces that exist before any tool starts, so neither end of a connection risks a missing file.

```toml
[prelim]
fifo     = ["events.hepmc"]                  # mkfifo, fresh per attempt, removed when the point ends
files    = ["showered.hepmc"]                # created empty (the writer truncates), kept
commands = [["lhapdf", "ls", "--installed"]] # argv arrays, run in order before the first group
```

| Key | Type | Notes |
|---|---|---|
| `fifo` | array of names | named pipes in the point's output directory. A FIFO connects tools **in one group** only, has **one reader**, and never feeds a tool that is not `streamable` (C6). |
| `files` | array of names | regular files in the point's output directory, **kept**: the way to keep events for another configuration |
| `commands` | array of argv arrays | run in the point's output directory; output to `logs/prelim.log`; a nonzero exit fails the point. Placeholders: `{repo}`, `{out}`, `{res}`, `{file:<name>}` |

A name declared twice is an error. `[run.<cfg>].prelim` replaces this table for one configuration.

---

## 7. `[static]` and selectors

```toml
[static]
energies = "27x920"     # a tag …
lepton   = -11          # … or an exact value (numbers compare numerically: 6 finds 6.0) …
pdf      = "#2"         # … or "#N", the N-th value (1-based)
```

- A static value applies **only when the quantity is not swept** in the active configuration.
- Every key must be a declared quantity. `[run.<cfg>].static` is merged over it, and
  `--set static.<q>=…` over both.
- A quantity that is neither swept nor static is **inactive**: it renders nothing, and the base
  card's value stands.
- **Selector order** (static values and `--points q=…`): a declared **tag**, then an exact
  **value**, then **`#N`**. A selector that matches nothing lists the tags.

---

## 8. `[quantities.<q>]`

```toml
[quantities.pdf]                     # in the master: no key needed; Pythia reads the value as written
values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]
tags   = ["MSTW08lo", "NNPDF23lo"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 LO"]

[quantities.pt0ref]                  # not in the master: name the key per tool
key    = { pythia = "MultipartonInteractions:pT0Ref" }
values = [3.0, 3.2, 3.4]

[quantities.radius]                  # a Rivet analysis option
target = "rivet/photo_eic"
key    = "R"
values = [0.4, 0.7, 1.0]

[quantities.masstol]                 # two consumers, a key for each
target = ["lamriv/Lamriv", "lambda"]
key    = { lamriv = "MASSTOL", lambda = "mass_tolerance" }
values = [0.05, 0.10, 0.15, 0.25]
```

| Key | Type | Default | Notes |
|---|---|---|---|
| `values` | array | **required**, non-empty | scalars or arrays (an energy pair) |
| `tags` | array of strings | derived | one per value. The default is the value with anything but `A–Za–z0–9.+-` replaced by `-`. Tags name point directories: keep them short and unique. |
| `labels` | array of strings | the tags | legend text, in ROOT **TLatex** (`e^{-}`, `#sqrt{s}`; V11). Only `_{…}`, `^{…}` and `#<name>` are markup: a bare `_` or `^` is the character (`"PDF4LHC21_40"`), in ROOT and yoda alike (V41). `\_`, `\^` and `\#` also give the character, even before a brace; in TOML write them in single quotes, `'PDF4LHC21\_40'`, since in `"…"` a backslash starts a TOML escape |
| `exclude` | array of integers | `[]` | values a sweep leaves out, by their **1-based** place (as `static = "#2"` and `--points 2` count): `exclude = [2]` sweeps the others. The remaining points keep their names and identities and are numbered 1… over what is swept. In an entangled group, a value any member excludes leaves the group. `static` may still pick an excluded value. Refused: a place outside 1…len(values), or none left (V42) |
| `key` | string, or table `{<tag or tool type> = "<key>"}` | none | the native key. A string needs a `target`. A table entry for a tool tag wins over one for its type. |
| `target` | string or array | none | restricts the consumers (§8.1) |
| `format` | string | "" | a Python format for the value: `"{}*GeV"` |
| `description` | string | "" | |

### 8.1 Who consumes a quantity

Decided at plan time, for every **active** quantity (swept, or with a static value):

**With `target`**, each target is `"<tag>"`, `"<tag>/<analysis>"` or `"<tag>/seed"`; the tag must be
a `[tools.<tag>]` table, and a target not in this configuration's chain is skipped.

| Target | Tool | Effect |
|---|---|---|
| `"<tag>/seed"` | any | a **replica**: enters the generator's identity, so its seeds; renders nothing. Under `seed_type = "manual"` the value **is** the point's seed (an integer) |
| `"<tag>/<analysis>"` | rivet (any tool with `analyses`) | an **analysis option** `<analysis>:<key>=<value>`; `key` is the option's name and is required. It must be declared in the analysis's `.info` (C9). |
| `"<tag>"` | `custom` or `module` | a **config key**: `key` (or the quantity's name) in the tool's extracted config (§9.2) |
| `"<tag>"` | a tool with a card | the native `key`, else the master's mapping for this tool type, else an error |

**Without `target`**, every tool in the chain (and every exported tool) is asked, in order:

1. the quantity's `key` table has an entry for its tag or its tool type → that native key;
2. else the master maps the quantity for its tool type → the master's mapping;
3. else the quantity is in the tool's `consumes` list (custom and module tools) → its config.

**Zero consumers is an error** (C7): a value that changes a directory name and nothing else is what
v1 kept finding (00/B14, 00/B40). More than one consumer is fine, and `--plan` prints the table. In
an `@quantity` chain a consumer among the configuration's alternatives is enough, and the selector
quantity is consumed by the choice itself.

**Two sources for one native key** in one card (a quantity and a built-in, two quantities) is an
error (C8). An override equal to the base card's value is written, but does not change the identity.

### 8.2 Replicas

```toml
[quantities.replica]
target = "pythia/seed"
values = [1, 2, 3]
tags   = ["s1", "s2", "s3"]
```

Statistically equivalent runs: the value enters the generator's identity, so each point gets its own
seed block. Seeds are never written by hand (02 §8).

### 8.3 Built-in quantities

`events` (the configuration's `event_count`) and `threads` are provided by the runner and reach a
tool only through the master (the table in §3). They need no consumer. Declared as quantities, they
can be swept or set statically (V56): each point then has that event count or thread count in place
of the configuration's, and it reaches the tools as the built-in does.

```toml
[quantities.events]
values = [10_000_000, 25_000_000, 50_000_000]
tags   = ["010M", "025M", "050M"]
```

---

## 9. `[tools.<tag>]`

### 9.1 Keys every tool table takes

```toml
[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
output_file = "photo.yoda"
analyses    = ["photo_eic"]        # a key of the rivet folder's [options]
```

| Key | Type | Default | Notes |
|---|---|---|---|
| `tool` | string | **required** | a standard tool (a folder of `utils/Env/`, [05 §1](05_Tools_Reference.md#1-the-standard-tools-at-a-glance)), `"custom"` or `"module"` |
| `baseconfig` | string or array | `[]` | native base card(s), read in order (root `configs/<project>/`). Tools with a card only. |
| `input` | string or array | `[]` | what it reads: `[prelim]` names, another tool's `output_file`, a pre product, (post) a product of every point, or a path. The first input is `{input}`. |
| `output_file` | string or array | `[]` | what it writes. An array is fan-out: App_Pythia writes the same events to each (V16). Exactly one writer per output (C6). |
| `timeout` | number (s) | 0 (none) | the tool fails when it runs longer |
| `stall_after` | number (s) | 300 | the tool fails when silent this long: no log line, status message or heartbeat (a prepare step waits at least 3600) |
| `status` | string | the folder's | `"standard"` (`$HEP_STATUS_FD`), `"filters"` (the folder's `filters.toml`), `"filters:<file>"` (your rules, root `configs/<P>/`), `"none"` |
| `streamable` | bool | the folder's | may it read a FIFO? |
| `consumes_events` | bool | the folder's | is its event count checked against the producer's sidecar? |
| `shards` | integer ≥ 1 | 1 | K > 1: K processes of this tool, each on a share of the events, merged into its `output_file` by the folder's merge tool (V31; rivet, [05 §3.1](05_Tools_Reference.md#31-sharded-rivet-shards--k)). The chain is unchanged. |
| `executable` | string | the folder's | custom and module: bare → `build/<project>/<name>` (must be built); `path:<command>` → `PATH` |
| `arguments` | array | `[]` | custom and module: argv after the config; placeholders (§10) |
| `consumes` | array of names | `[]` | custom and module: quantities written into the config |
| `config` | table | none | custom and module: `[tools.<tag>.config]`, extracted to a file (§9.2) |

Every other key is **tool-specific**, checked against the tool folder's `[options]` schema (type
and `required`), or, for custom and module tools, a standard-configuration request (§9.4). An
unknown key is an error with the keys the tool takes (C1).

### 9.2 Custom tools

```toml
[tools.fit]
tool        = "custom"
executable  = "fit_peaks.py"                # build/<P>/fit_peaks.py, else a command on PATH; ./… from the repo
arguments   = ["{in:lambda.yoda}", "{res}/fit.json"]
input       = "lambda.yoda"
output_file = "fit.json"
consumes    = ["energy"]                    # written under [quantities] in its config
status      = "filters:fit_filters.toml"

[tools.fit.config]                          # written verbatim to output/…/<point>/config/fit.toml
model  = "gauss+poly2"
window = [1.09, 1.14]
```

The runner writes `output/…/<point>/config/<tag>.toml` when the table has a `config`, consumes a
quantity, or requests an export, and passes it as the **first argument** (the folder's argv is
`{exe} {config} {arguments}`). It holds:

- the `[tools.<tag>.config]` table, verbatim;
- consumed values: a value mapped to a **config key** (`target = "fit"`, `key = "window"`) is set
  at that key (dotted keys nest: `"cuts.window"`); a value consumed **by its quantity name**
  (`consumes`, or a target with no key) goes under `[quantities]`;
- `[standard.<key>]` tables for export requests (§9.4).

A custom tool is count-checked only if its table sets `consumes_events = true` and its folder names
how to read the count (the `custom` folder names none). A product it writes should go to
`{partial:output}`: the runner renames it after the checks pass.

### 9.3 Module tools

```toml
[tools.lambda]
tool        = "module"
executable  = "Lambda.exe"                  # build/Lambda/Lambda.exe, from modules/Lambda/Lambda.cc
input       = "to_module.hepmc"
output_file = "lambda.root"

[tools.lambda.config]
mass_tolerance = 0.15
```

As a custom tool, for a program built with `utils/Module.hh`
([05 §18](05_Tools_Reference.md#18-modulehh)). It always gets a config, and its argv is
`{exe} {config} --input={input} --output={partial:output} --events={events} --sidecar={input_sidecar} {arguments}`.
Its count is checked from its report (`<output>.json`, key `events`).

### 9.4 Standard configurations (exports)

A custom or module tool may ask for the configuration the runner renders for a **standard** tool,
and use it however it likes: this is how an **integrated program** (Pythia and Rivet in one process)
gets the same card and seeds as the chain.

```toml
[tools.jets]
tool           = "module"
executable     = "InprocJets.exe"
output_file    = "photo.yoda"
pythia_cmnd    = true                        # the pythia table's rendered card
rivet_analyses = true                        # the rivet table's analysis list
```

| Rule | |
|---|---|
| The key | `<tool>_<export>`, bool, default false; `"<tag>"` instead of `true` names the table |
| Which table | `true`: the table tagged `<tool>`, else the only table with `tool = "<tool>"`; several candidates are an error (C13) |
| What exists | every tool with a card exports `<tool>_card` automatically; the rest are declared in the folder's `[exports]` ([05](05_Tools_Reference.md) lists them per tool). An export a tool does not offer is an error, with the ones it does (C13). |
| Rendered as in a chain | the same card a process of that tool would get for this point, **seeds included**; the table need not be in `tools` |
| Consumed | the quantities the exported tool consumes count as consumed (C7) |
| Prepared on demand | an export with `needs_prepare` (`herwig_run`, `sherpa_results`, `madgraph_process`) runs that tool's prepare step (cached) before this tool's group |
| In the config | `[standard.<key>]` with `tool`, `tag` and, for a card, `path` (base + point card in one file) and `parts` (the files in reading order); for values, the named values (`analyses`, `plugin_path`); for a prepared product, `path` |
| On the command line | `{std:<key>}` is the export's `path` |
| Identity | includes the exported tool's identity |

The program then owns what the chain would have done: σ over threads (L1), the final σ to Rivet
(L2), catching at thread boundaries (L3). There is no FIFO, so the runner checks its exit code and
its outputs.

---

## 10. Placeholders

`{name}` in a folder's argv, env, cwd, card lines and footers, and in a custom tool's `arguments`,
is replaced from the point's plan. `{{` and `}}` are literal braces. An argument that is exactly
one placeholder whose value is a list is **spliced** into argv (`{inputs}` becomes several
arguments; empty becomes none). An unknown placeholder is an error with the nearest name.

| Placeholder | Is |
|---|---|
| `{repo}` | the repository root |
| `{exe}` | the tool's executable |
| `{out}`, `{res}` | the point's output and results directories |
| `{config}` | the extracted config file (custom, module), or empty |
| `{arguments}` | the table's `arguments`, expanded |
| `{input}` | the first input's path |
| `{inputs}` | every input's path (post: that product of every point, in point order) |
| `{named_inputs}` | post: `<point>=<path>` for every point |
| `{in:<name>}` | the path of the input named `<name>` |
| `{file:<name>}` | the path of a `[prelim]` FIFO or file |
| `{input_sidecar}` | the first input's producer sidecar, **only** when that producer ran in an earlier group (a file); empty in a FIFO chain |
| `{output}`, `{outputs}` | the first output's final path / every output's, comma-joined |
| `{partial:output}` | the first product's partial name (`photo.partial.yoda`), which the runner renames after the checks |
| `{output_name}` | the first output's file name |
| `{q:<quantity>}` | the point's value of an active quantity |
| `{threads}`, `{events}` | the configuration's |
| `{seed}` | the point's seed (filled in last: identities stay seed-free) |
| `{cards}` | the base cards, then the point card |
| `{card}` | the combined card (base + point card in one file) |
| `{analyses}` | rivet: `-a <analysis[:options]>` for each |
| `{prepared}`, `{prepare_card}` | the tool's prepare cache entry / the card its prepare step reads |
| `{std:<key>}` | an export's `path` (§9.4) |
| `{points}` | pre and post: `points.json` |
| `{<option>}` | every key of the folder's `[options]`: its value, empty when unset; `kind = "flag"` → the flag or nothing |

---

## 11. `[plot]`

The plot stage runs after the points (and after `post`), from the **complete** points only, and
again on `hep run … --only plot` or `hep plot <config>`. A configuration without a `[plot]` table
draws nothing.

```toml
[plot]
backend     = "root"               # "root" | "yoda" | "both" | ["root", "yoda"]
formats     = ["pdf", "png"]
objects     = ["/photo_eic/d0*"]
ratio       = true
y_gutter    = 0.5
x_gutter    = "default"
logy        = true
auto_range  = true
void_empty  = false
min_entries = 10
range_pad   = 1
root_style  = "talk.toml"

[plot.data]
file   = "rivet:ZEUS_2012_I1116258"
legend = "ZEUS 2012"
[plot.data.map]
"d01-x01-y01" = "/REF/ZEUS_2012_I1116258/d01-x01-y01"

[plot.style]
page.dpi        = 300
legend.position = "top-left"

[plot.object."d04-*"]
logy     = true
y_gutter = 2.0
style.legend.position = "bottom-left"
```

| Key | Type | Default | Notes |
|---|---|---|---|
| `backend` | string or array | `"root"` | `"root"` (Paint), `"yoda"` (rivet-mkhtml), `"both"` or an array (both, from the same pages: V28) |
| `formats` | array | `["pdf"]` | `pdf`, `png`, `svg`, `eps`. mkhtml writes pdf and png always. |
| `objects` | array of globs | every 1D object | matched against the option-free YODA path (`/photo_eic/d01-x01-y01`) or any variant's path. No object matching is an error. |
| `ratio` | bool | false | a ratio pad: each curve over the data, or over the first curve when there are no data |
| `use_data` | bool | true | `false`: the `[plot.data]` table stays in the file but is not drawn, and a `ratio` divides each curve by the page's first curve, the first value of its curve axis (V44) |
| `title` | string | the `.plot`'s `Title` | the main title, centred above the frame (V51). Every page; `[plot.object."<glob>"]` and `[plot.overlay.<name>]` override it for theirs |
| `title_left`, `title_right` | string | `""` | small text just above the frame's top-left and top-right corners (V51), inherited the same way |
| `legend_header` | string | the `.plot`'s `LegendTitle` | the legend's first line (V51), inherited the same way. Children inherit every key their parent has and a key means the same at both levels |
| `overlay` | tables | none | `[plot.overlay.<name>] objects = [globs], labels = [...]`: one page per cell, `<cell>/<name>`, whose curves are those objects of each point (label: the overlay's, plus the point's when a page has several points); takes the `[plot.object]` keys too, inheriting from `[plot]`; a ratio divides by the first curve (V51) |
| `y_gutter` | number ≥ 0 or `"default"` | `0.5` | the top of the y axis at (1 + g) × the largest drawn value (on a log axis, g of the decades shown); `0`: no headroom. `"default"`: no gutter, the tool's own range (V29, V55) |
| `x_gutter` | number ≥ 0 or `"default"` | `"default"` | widens x by g of its span, symmetrically (in decades on a log axis). `"default"`: the range the bins give |
| `logx`, `logy` | bool | the `.plot` file's `LogX`/`LogY` | |
| `auto_range` | bool | true | trim x to the bins with content, in curves and data |
| `range_pad` | integer | 0 | whole bins kept either side of the filled ones |
| `void_empty` | bool | false | blank a bin that is zero in **every** curve |
| `min_entries` | integer | 0 | blank a bin that fewer raw entries went into, in **any** curve (read from the `/RAW` twin; objects without one are not voided this way) |
| `root_style` | string (path) | none | a style file over base.toml (§12). Refused by the yoda backend alone. |
| `data` | table | none | §11.1 |
| `style` | table | `{}` | §12 |
| `object` | table | `{}` | §11.2 |

**`"default"` means "keep it as it is"** (V55, which replaces V37's meaning): in `[plot]` it sets
nothing, and the drawing tool does what it does by itself; in a child (`[plot.object."<glob>"]`,
`[plot.overlay.<name>]`) it is `[plot]`'s value, as if the key were left out. A key left out of
`[plot]` takes the runner's default, from `utils/Env/schema/run.toml` (a missing `y_gutter` is 0.5,
a missing `auto_range` is true). In `[plot]`:

| Key | `"default"` gives |
|---|---|
| `min_entries`, `range_pad` | 0: every bin drawn |
| `void_empty` | false: neither Paint nor mkhtml voids a bin by itself |
| `auto_range` | off: the tool's own x range |
| `y_gutter`, `x_gutter` | no gutter: the tool's own range (as before) |
| `logx`, `logy` | the analysis's `.plot` `LogX`/`LogY` |
| `ratio` | the `.plot`'s `RatioPlot`, else a ratio pad when the page has reference data (mkhtml's rule) |
| `formats` | Paint's own, pdf (mkhtml writes pdf and png anyway) |
| `objects` | every object |
| `backend` | `"root"` |
| `root_style` | no style file: base.toml |

In `[plot.object."<glob>"]` a `"default"` keeps `[plot]`'s value (`logy = "default"` there is
`[plot].logy`, and the `.plot`'s when `[plot]` sets none); `x_label` and `y_label`, which only a child
sets, keep the `.plot`'s labels. In a style layer (§12) a `"default"` value sets nothing: the layer
below decides, and at the bottom base.toml, Paint's own look. In `[run.<cfg>]` a `"default"` is
`[run]`'s value (`threads = "default"`).
`--set plot.min_entries=default` works for one run.

`[plot].legend` is no longer a key: it moved to the style, `legend.position` (the error says so).

**What a page is.** One page per `plot_points` cell and object. Its curves are the cell's complete
points; a point whose YODA holds several variants of the object (a swept analysis option) gives one
curve per variant, labelled `… [R=0.4]`. A curve's label is the curve quantities' labels joined with
`, ` (the run's name when nothing is swept). Weight variations (`/x[…]`), `/RAW`, `/TMP` and the run
counters never get pages.

**Labels** come from the analysis's Rivet `.plot` file (our plugins' copies in `build/Rivet/`, then
Rivet's data directory): `Title` (else `LegendTitle`), `XLabel`, `YLabel`, `LogX`, `LogY`, later
blocks winning. LaTeX becomes TLatex, with math letters set italic (`$E_T$` → `#it{E}_{#it{T}}`).
The ratio pad is labelled `MC/Data` with data, `Ratio` without.

**The order of operations on a page** (load-bearing, inherited from v1): void across the page →
align the data to the MC bins → auto-range over curves and data → gutters → draw.

### 11.1 `[plot.data]`

| Key | Type | Default | Notes |
|---|---|---|---|
| `file` | string | **required with a map** | `rivet:<Analysis>`: Rivet's own reference file (`build/Rivet/`, then `rivet-config --datadir`, `.yoda` or `.yoda.gz`); otherwise a path under `datasets/` (not in git) |
| `legend` | string | `"Data"` | the data's legend entry |
| `map` | table | **required** | MC object name (`d01-x01-y01`) → reference path. **Explicit only**, never matched by name (L18). A file without a map, or a map without a file, is an error. |

The reference is drawn on the pages its map names, **aligned** to the drawn binning: cut to its
longest run of bins whose edges are all MC edges, or dropped (with a warning) when none line up.

### 11.2 `[plot.object."<glob>"]`

Per-object overrides, matched against the object's short name (`d04-x01-y01`) or its full path;
every matching table applies, in file order.

| Key | Overrides |
|---|---|
| `title`, `x_label`, `y_label` | the `.plot` labels (TLatex as written) |
| `logx`, `logy`, `ratio` | the `[plot]` values |
| `y_gutter`, `x_gutter` | the `[plot]` values (same rules) |
| `style` | a style layer for these objects only (§12) |

---

## 12. The style

The look of the ROOT pages is TOML (V27). **`utils/Apps/Paint/base.toml`** holds every key with its
default (rivet-mkhtml's look); edit it to change every page. Over it, key by key:

1. `[plot].root_style` — a style file (a bare name under `configs/<project>/`, `.toml` optional);
   `hep plot FILE… --style FILE` for files;
2. `[plot.style]`;
3. `[plot.object."<glob>"].style`, for the objects it matches.

Each layer names **only what it changes**, in base.toml's tables. A key base.toml does not have is
an error with the nearest spelling; so is a value of another kind (a number for a number, a pair of
numbers for a pair, an array for the palette). The runner checks at plan time, and Paint checks
again. A page's config holds only what the layers changed; `build/Paint.exe PAGE.toml
--dump-style` prints the whole merged style. Sizes are **points** (1/72 in) of the page.

| Key | Default | Means |
|---|---|---|
| `page.size` | `[4.67, 4.21]` | inches: the PDF's page; the PNG is size × dpi pixels |
| `page.dpi` | `150` | PNG resolution (150 → 701 × 632) |
| `page.font` | `"serif"` | `serif`, `sans`, `mono` (ROOT's Times, Helvetica, Courier) |
| `page.margins.left`, `.right`, `.top`, `.bottom` | `0.16`, `0.032`, `0.066`, `0.11` | fractions of the page around the axes |
| `text.title` | `10.0` | axis titles |
| `text.labels` | `8.0` | tick labels |
| `text.legend` | `9.0` | legend entries, in points; the yoda backend follows it (`LegendFontSize`) |
| `text.header` | `9.0` | the legend's first line (`legend_header`); the yoda backend follows it (`legend.title_fontsize`, V50) |
| `text.page_title` | `12.0` | `title`, above the frame |
| `text.corner` | `9.0` | `title_left`, `title_right` |
| `curves.palette` | `["#EE3311", "#3366FF", "#109618", "#FF9900", "#990099"]` | curve colours in order: `#rrggbb`, ROOT names with offsets (`kBlue+1`) or numbers |
| `curves.width` | `1.0` | points: steps and error bars |
| `curves.errors` | `"bars"` | `bars` (at the bin centres), `band`, `none` |
| `data.colour` | `"kBlack"` | |
| `data.marker` | `20` | ROOT marker style |
| `data.marker_size` | `2.0` | points |
| `data.x_bars` | `true` | the bin width as a horizontal bar |
| `axes.tick_length` | `6.0` | points; minor ticks are half |
| `axes.ticks_all_sides` | `true` | ticks on the top and right edges too |
| `axes.titles_at_ends` | `true` | x title at the right end, y title at the top; `false` centres them |
| `axes.title_offset` | `[1.0, 1.55]` | x, y: ROOT's title offsets |
| `axes.label_offset` | `2.5` | points between an axis and its labels |
| `legend.position` | `"top-right"` | `top-right`, `top-left`, `bottom-right`, `bottom-left`, `best`, or `[x, y]`: the legend's top-right corner in fractions of the frame (then right-aligned). `best` (V49): Paint takes the corner with the fewest drawn points under the legend; yoda lets matplotlib choose (`loc='best'`). Both choose within the y range they draw, so give headroom with a numeric `y_gutter` (e.g. `0.5`, which on a log axis is half the decades shown) when the legend must not touch the curves |
| `legend.inset` | `[5.0, 5.0]` | points from the frame's corner (x, y), for a named position |
| `legend.spacing` | `1.2` | line pitch, × the legend text size |
| `legend.symbol` | `16.0` | points: the width of the "+" beside an entry |
| `legend.gap` | `5.0` | points between the "+" and its text |
| `ratio.heights` | `[2.0, 1.0]` | the main pad to the ratio pad |
| `ratio.range` | `[0.5, 1.5]` | always shown; widened to the ratios drawn … |
| `ratio.limits` | `[0.0, 3.0]` | … but never past these |
| `ratio.divisions` | `512` | the ratio pad's y ticks, ROOT's `n1 + 100·n2`: at most n1 labelled divisions (0.1 apart on the usual ~0.4–1.5), each cut into n2 by minor ticks; `508` gives 0.2. The yoda backend follows it too |
| `ratio.decimals` | `true` | labels `1.0, 1.2` rather than `1, 1.2` |

**The yoda backend** honours a `legend.position` corner (or `best`), `text.legend`, `text.header`, `ratio.divisions`, and `ratio.range` with `ratio.limits` (V48: it works out each page's window by Paint's rule, so both backends show the same window). Alone, it refuses
`root_style` and every other style key; beside the root backend (`"both"`) those are Paint's to honour and allowed,
but a legend at `[x, y]` is still refused, because the two page sets would disagree about it.

---

## 13. Validation rules

All checked at plan time. Every error names **where** (the file and key) and gives a **hint** (what
to do), and a misspelt name gets the nearest spelling. `hep run` exits 2 on any of them, before
anything runs.

| # | Rule | Example message |
|---|---|---|
| **C1** | An unknown section or key is an error; a tool-specific key is checked against the tool folder's `[options]` (type, `required`). | `unknown key 'min_entry'` · `did you mean 'min_entries'?` |
| **C2** | `[run].configuration`, and a configuration named on the command line, must name a `[run.<cfg>]`. | `no configuration 'energy-pdf'` |
| **C3** | Every `sweeps` entry names a declared quantity; entangled quantities have equal value counts; no quantity is swept twice. | `entangled quantities need equal value counts` · `pdf: 4, alphas: 3` |
| **C4** | `plot_points` names only quantities swept in this configuration. | `plot_points names 'mpi', which is not swept here` |
| **C5** | Every `tools`/`pre`/`post` entry is a `[tools.<tag>]` table; groups nest one level; an `@q` entry's values are tool tags. | `'pythya' is not a [tools.<tag>] table` · `did you mean 'pythia'?` |
| **C6** | Connections: a FIFO within one group only, one reader per FIFO, a writer for every FIFO, no FIFO into a non-streamable tool; a file read in a later group than its writer, never the same one; every input made by someone or already on disk; one writer per output. | `'delphes' cannot read a FIFO` · `use a [prelim] file and put it in a later group` |
| **C7** | Every active quantity has at least one consumer in the chain (in an `@q` chain: among the alternatives). | `[quantities.lepton] is set but no tool in this chain consumes it` |
| **C8** | One source per native key in one card. | `'PDF:pSet' is set by both [quantities.pdf] = … and …` |
| **C9** | A Rivet analysis has a `.info` (our plugins in `build/Rivet/`, or Rivet's), and every option it is given is declared there (L19). | `'photo_eic' does not declare the option RADIUS` · `declared: ETMIN, ETMIN2, R` |
| **C10** | Providers: a PDF set named by a checked mapping is installed; base configs exist; executables are built; files a tool folder needs (`[checks] files`, e.g. Herwig's repository) exist. | `the PDF set 'CT14lo' is not installed` · `lhapdf install CT14lo` |
| **C11** | Point directory names are unique. | `these points would share a directory: …` |
| **C12** | Paths: no `../`; a missing file is reported under its convention root. | `'../cards/x.cmnd' climbs out of its root` |
| **C13** | A standard-configuration request names an export its tool offers and resolves to exactly one table. | `pythia_cmnd = true matches several pythia tables: pythia, shower` · `name one: pythia_cmnd = "<tag>"` |
| **C14** | `combine` names quantities swept here as axes of their own, none of them in `plot_points`. | `combine names 'pdf', which is not swept here as an axis of its own` · `'replica' is both combined and a page axis (plot_points)` |

The plot checks follow the same shape: an unknown backend, format, gutter value, `[plot.data]` key,
`[plot.object]` key or style key; a data file without a map; a style key a backend cannot honour.

---

## 14. Commands

### `hep run`

```
hep run CONFIG [CONFIGURATION] [--plan] [--points SEL] [--set KEY=VALUE]… [--rerun]
                               [--only pre|post|plot] [--plain]
```

Options and positionals may come in any order (`hep run eic --plain pdf`, V54).

| Option | Does |
|---|---|
| `CONFIG` | `configs/<CONFIG>[.toml]`, or `./path` from the repository root |
| `CONFIGURATION` | overrides `[run].configuration`; under `[run].sweep_runs`, runs only this one (§4.1) |
| `--why` | for each point and stage that would run, what changed since it last completed (from its `identity.json`): `events: 10 → 20`, `tools.pythia.card: + PDF:pSet = …`; run nothing (V57) |
| `--show-config` | print each configuration's resolved values and the layer each came from (its own, `extends`, `[run.defaults]`, `[run]`, default), and what `[master].include` gave; run nothing (V56) |
| `--plan` | print everything and run nothing: per point, the values and their consumers, the groups and each tool's argv, what each reads and writes, the prepare steps and whether they are cached, the output and results directories and whether the point is complete; the pre and post stages; the page count |
| `--points SEL` | run a subset: comma-separated point names, single tags, 1-based indices, or `quantity=tag`. The others keep their state (and `points.json` lists all). Refused under a sweep of several runs: name the configuration. |
| `--set KEY=VALUE` | override one value of the TOML for this invocation, by dotted key, before anything is checked (repeatable). The value is read as TOML, else as a string: `--set run.event_count=50000`, `--set run.pdf.threads=8`, `--set static.energies=18x275`, `--set 'plot.formats=["png"]'`. |
| `--rerun` | run complete points (and the pre and post stages) again |
| `--only plot` | draw the pages from the complete points; run nothing |
| `--only pre`, `--only post` | run only that stage, whether or not it is complete |
| `--plain` | plain lines instead of the live view (also when stdout is not a terminal) |

The order: pre stage → every point not complete (in point order) → `points.json` → post stage →
plot stage. A failed point does not stop the others. **Exit codes:** 0 everything done or skipped;
1 a point, the post stage or a page failed; 2 a config error, before anything ran; 6 stopped by the
user (Ctrl-C: SIGINT, then SIGTERM, then SIGKILL to the running tools; a second Ctrl-C is the
default behaviour). Under `[run].sweep_runs` (§4.1), each run has these codes; the command exits 6 if
one was stopped, else 1 if any failed, else 0.

### `hep plot`

```
hep plot CONFIG [CONFIGURATION] [--set KEY=VALUE]…
hep plot FILE… [-o DIR] [--labels A,B,…] [--objects GLOB…] [--formats pdf,png] [--ratio] [--style FILE]
```

With a config: its pages, as after a run (`--only plot`); under `[run].sweep_runs`, every swept
configuration's, each under its `run NN - <title> -` line. With files (every target ends `.yoda`,
`.yoda.gz` or `.root`): one page per object any of them holds, one curve per file, or one per point
of a merged sweep file (labelled from the `points.json` inside it). `-o` defaults to
`results/plots/<first file's stem>/`; `--labels` gives one label per file; `--style` is a style
file over base.toml.

### `hep check`

```
hep check [CONFIG…]
```

Loads each config (with none given, every `configs/<Project>/*.toml` that has a `[run]`), validates
its `[plot]` and plans every configuration's points: every C-rule, path, consumer, connection and
card, with nothing run or written (V57). It prints one line per config, the error of each that fails,
and exits 0, or 2 when any failed: for a pre-commit hook, or before a long sweep.

### `hep watch`

```
hep watch [CONFIG [CONFIGURATION]] [--plain]
```

Follows a job from another terminal through its journal, `output/…/<cfg>/status.jsonl`; with no
config, the most recently written journal; under `[run].sweep_runs` with no configuration, the swept
configuration's journal written to last. It prints the same blocks as the run, and leaves when the
run finishes. A run of a sweep names the next run's journal when it finishes, so the watch follows
on to it, and leaves after the last or on a stop.

### `hep build` and `make`

```
hep build [TARGET…] [--tests] [--clean] [--configure] [-j N]
hep make <path>/<X>.exe | <path>/<x>.so | all | tests | test | test-slow | configure | list | clean
```

`hep make …` is `make …` from the repository root, wherever it is typed (V54).

`hep build` is `make all` from the repository root (every module program, Rivet plugin and app, and
Herwig's repository), on every core by default. `--tests` adds the C++ tests, `--clean` empties
`build/` first, `--configure` probes the toolchain again. The make rules are in
[06 §2](06_Developer_Guide.md#2-the-build).

### Environment

| Variable | Set by | Means |
|---|---|---|
| `HEKIT_ROOT` | `~/HEP/setup.sh` | the repository (else found from the runner's own location) |
| `HEKIT_OUTPUT`, `HEKIT_RESULTS` | you, tests | replace `output/` and `results/` (the tests point them into `output/tests/`) |
| `HEKIT_CONFIGS` | tests | replaces `configs/` as the root of run TOMLs and their cards (the tests point it at `tests/fixtures/configs/`) |
| `HEP_STATUS_FD` | the runner, per tool | the status pipe of a `status = "standard"` tool |
| `RIVET_ANALYSIS_PATH` | the rivet and merge folders, per run | `build/Rivet` (not set in the shell on purpose) |
| `LHAPDF_DATA_PATH`, `GEANT4_DATA_DIR`, `ONNXRUNTIME_DIR` | `utils/Env/hep_env.sh` | the toolchain's data |

---

## 15. Files the runner writes

**Per point** (`output/…/<point>/`):

| File | Holds |
|---|---|
| `cards/<tag>.point.<ext>` | the overrides (append style) |
| `cards/<tag>.<ext>` | base + point card in one file (what an export hands out); for render style, the whole card |
| `cards/<tag>.prepare.<ext>` | the card a prepare step reads, when the tool's `render.py` makes one |
| `config/<tag>.toml` | a custom or module tool's extracted config |
| `logs/<tag>.log`, `logs/<tag>.prepare.log`, `logs/prelim.log` | stdout and stderr |
| `provenance.json` | `point`, `run`, `project`, `configuration`, `config_file`; `values` (each active quantity's index, tag and value); `identity`, `seed`, `threads`, `events`; per tool `tag`, `tool`, `exe`, `exe_sha256`, `version`, `argv`, `ran`, `card`, `card_sha256`, `config`, `result` (exit, seconds, note); `host`, `platform`, `user`, `git` (`revision`, `dirty`), `started`, `finished` |
| `identity.json` | the parts the identity hashes (each tool's card lines, argv, binaries, options; threads, events, groups, prelim, the seed rule), written when the point completes, for `--why` (V57) |
| `.complete` | the point's identity, written **last**; its absence means the point is not done |

**Per configuration** (`output/…/<cfg>/`):

| File | Holds |
|---|---|
| `points.json` | `run`, `project`, `configuration`, `config_file`, `plot_points`, and per point: `name`, `index`, `values` (tag, label, value, swept), `page`, `products` (name → path), `results`, `output`, `identity`, `seed`, `complete`. Every point, even under `--points`. |
| `status.jsonl` | the journal: every status message as `{"point", "tool", "t", "k", …}`, plus the runner's own `run` (started, finished with a `verdict`), `point` (started, done / failed / stopped with `cause` and `msg`) and `exit` (`code`, `seconds`) records |
| `plots/[<cell>/]<object>.toml` | each page's Paint config ([05 §17](05_Tools_Reference.md#17-paint)) |
| `plots/merged.sha256` | what the merged sweep file was built from |

**Beside products**: an event producer's **sidecar** `<first output>.json` (App_Pythia's, or
`{"written": N, "source": "requested"}` written by the runner for generators that always make what
they are asked for); a module program's **report** `<output>.json` (`events`, `sum_w`,
`sigma_pb`, …), which travels with its product when it is renamed.

**Prepare caches**: `output/<P>/.cache/<tool>/<key>/`, with a `.prepared` stamp once the step
succeeded and left its marker. **Reference data** converted for Paint:
`output/<P>/.cache/datasets/<name>.root`.
