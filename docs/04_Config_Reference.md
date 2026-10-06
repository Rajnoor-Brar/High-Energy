# 04 — Configuration reference

Every key a run TOML accepts: its type, default and meaning, and what is checked. **The key tables
are generated** from `utils/Env/schema/run.toml` and `utils/Apps/Paint/base.toml` (`make docs`, V91),
the same source `hep explain KEY` and the editor schema read, so they cannot drift from the code. The
prose around them says what a table cannot.
- **Worked pipelines:** [02](02_User_Guide.md).
- **Plots and figures:** [03](03_Plots.md).
- **Each standard tool's own keys:** [05](05_Commands_and_Tools.md).

**Conventions.**
- *Type* uses TOML's words: a string, an integer, a number (an integer or a float), true or false,
  a list, a table.
- A key marked **required** has no default; a key that may take `"default"` says so.
- Everything is checked **at plan time**, before any process starts: `hep check` and `hep run …
  --plan` run every check below.

---

## 1. Files, and which wins

| File | Holds | Written by |
|---|---|---|
| native base cards: `configs/<P>/*.cmnd`, `.in`, `.yaml`, `.sin`, `.mg5`, `.tcl` | the physics | you; never modified by the runner |
| the run TOML: `configs/<P>/<run>.toml` | configurations, quantities, tools, wiring, plots | you |
| `utils/Env/quantities.toml` (what each quantity name means) and each tool folder's `quantities.toml` (how that tool consumes it), optionally overlaid by a project's master | how each standard tool consumes named quantities (§3) | the framework; a project may add to it |
| `utils/Apps/Paint/base.toml`, optionally a style file | the look of the pages (§12) | the framework; you, to change every page |

**Physics stays in the native card.** A quantity renders an *override* into a point card. The base
card is read first, and the override is applied by the tool's own rule: last wins for Pythia, a
YAML merge for Sherpa, and so on (see [05](05_Commands_and_Tools.md)).

**Precedence of a value, lowest to highest:**

```
utils/Env/<tool>/quantities.toml  <  [config].master  <  [quantities.<q>].key / target  <  --set
[static]  <  [run.cfgs.<cfg>].static  <  --set static.<q>=…  <  the value a sweep gives the point
[run]  <  [run.defaults]  <  extends  <  [run.cfgs.<cfg>]  <  --set
[config].import files  <  this file
base.toml  <  [plot].root_style file  <  [plot.style]  <  [plot.figures.<figure>].style
[plot]  <  [plot.figures.<figure>]
```

A run TOML has exactly these top-level sections, and any other is an error (C1): `[config]`,
`[run]`, `[prelim]`, `[static]`, `[tools]`, `[quantities]`, `[plot]`.

**`"default"` means "keep it as it is"** (V55). Only a key whose type says so takes it:
- **in a child** (a configuration over `[run]`, a figure over `[plot]`, a style layer over the one
  below), it is the parent's value, as if the key were left out;
- **at the top level**, it sets nothing, and the tool decides.

A key left out takes the runner's default (the tables' *Default*). `--set key=default` works for one
run.

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
| `[config].master`, `[config].import` | `configs/<project>/` | `master.toml` |
| `[tools.*].baseconfig` | `configs/<project>/` | `photo_ep.cmnd` |
| `[tools.*].executable` | `build/<project>/`, which must exist; `path:<command>` asks for a command on `PATH` by name (V54) | `Lambda.exe` → `build/Lambda/Lambda.exe`; `path:python3` |
| `[tools.*].filters` | `configs/<project>/` | `fit_filters.toml` |
| `[prelim].fifo`, `[prelim].files` | the point's **output** directory | `events.hepmc` |
| `[tools.*].input` | a `[prelim]` name or another tool's `output_file` by name; otherwise a path under the point's output directory | `events.hepmc` |
| `[tools.*].output_file` | a `[prelim]` name → the point's output directory; **any other name → the point's results directory** (a product) | `photo.yoda` → `results/…/<point>/photo.yoda` |
| `[plot].root_style` | `configs/<project>/`, `.toml` optional | `talk` → `configs/<P>/talk.toml` |
| `[plot.data].file` | `datasets/`, or `rivet:<Analysis>` for Rivet's own reference data | `rivet:ZEUS_2012_I1116258` |

**The one judgement:** an interface file named in `[prelim]` is technical and lives in `output/`;
anything else a tool writes is a product and lives in `results/`. So a HepMC file kept for another
configuration goes in `[prelim] files`.

**Where a point lives** (V45, V46):

```
output/<P>/<run>/<cfg>/<point>/     cards/  config/  logs/  FIFOs and [prelim] files  provenance.json  .complete
results/<P>/<run>/<cfg>/<point>/    the products
```

- `<run>` is `[run].name`, or the configuration's own `name`.
- `<cfg>` is `NN_<label>` when there is a serial (the configuration's if it sets one, else
  `[run]`'s), and `<label>` otherwise. `<label>` is the table key when the configuration's `label`
  is empty or unset.
- `<point>` is the swept quantities' tags joined by `_`, in `sweeps` order, or `point` when nothing
  is swept. Two points with the same name are an error (C11).

---

## 3. `[config]`

How the file is read (V93; it was `[master]`, which is refused with the `[config]` to write, and
`hep migrate` rewrites it).

```toml
[config]
import = ["common.toml"]         # optional: run TOMLs whose tables this one starts from; this file wins
master = "master.toml"           # optional: configs/<project>/master.toml overlays the tool folders' mappings
```

<!-- generated: keys config -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `master` | a string |  | overlays the tool folders' mappings key by key (`[quantities.<tool>.compatible_quantities]`): an entry for a (tool, quantity) pair replaces the framework's. The file must exist. |
| `import` | a string or a list (a string or a table each) |  | run TOMLs this one starts from, in order, named as `hep run` names a config: `name` is this project's (`configs/<project>/name.toml`), `<Project>/<name>` another project's, `./…` from the repository root; `.toml` optional. **This file wins** (V56): a quantity, tool table or configuration of the file replaces the imported one whole; `[plot]`, `[static]`, `[prelim]` and `[run]`'s own keys merge key by key, tables recursively. Imports nest (V94): an imported file's own imports come first, depth-first; a circle is refused. Another project's file keeps its bare paths (cards, filters, styles, executables) its own project's, so its tools plan as they do in it. The file that imports sets its own `[run].name` and `project`, and shares them with no imported run. An entry may be `{ from = "<config>", only = ["quantities", "run.default", …] }`: only those sections or dotted keys of that file, each of which it must have (V95). `--show-config` says where each quantity, tool and configuration came from. |
| `drop` | a list (a string each) |  | dotted keys (`run.default4`, `plot.figures.statistics`, `quantities.radius`, `tools.jets`) taken out of what the imports brought in, before this file's own tables are laid over them (V95). Each must name something an import gave, so a misspelt drop is refused rather than keeping what it meant to remove; a file that imports nothing has nothing to drop. |
| `vars` | a table |  | `name = value`, cited in any string of the file as `{var:name}` and replaced when the file is read, after its imports and `--set`, so an identity sees only the result (V96). A string that is exactly one var takes its value as it is: `event_count = "{var:events}"` is an integer, and a list stays a list; inside a longer string a var must be a scalar (`"rivet:{var:ana}"`). An unknown name is refused with the nearest. An imported file's `{var:…}` takes this file's value, so a shared file can be written with parameters. Imports are read before vars, so an import's name cannot cite one; `--set config.vars.<name>=…` changes one for a run. |
| `meta` | a table |  | descriptive: it never changes a run (V97). Any key is free text for people (`author`, `references`, …) except `versions = { pythia8 = "8.317", rivet = "4.1.3" }`: the packages of `utils/Env/stack.toml` the file was run with, each version a string. A version the stack does not have (`6.5` matches 6.5.6) is a **warning** in `--plan`, at the run's start and in `hep check`, which still passes: the run goes ahead, at your own risk. A package stack.toml does not name is refused, since its warning could never come. |
<!-- /generated -->

**`import`** (V56, V94). The imported files are read in order, then this file's tables are laid over
them:
- a quantity, tool table or configuration of the file replaces the imported one whole;
- `[plot]`, `[static]`, `[prelim]` and `[run]`'s own keys merge key by key, tables recursively;
- `"default"` in this file keeps the imported value.

Its rules:
- **Names:** an import is named as `hep run` names a config: `zeus_common` is this project's,
  `PhotoProduction/zeus_validation` another project's, and `./…` is from the repository root.
- **Nesting:** an imported file is read the same way first, so its own imports come before it,
  depth-first. A circle is refused, naming it.
- **Another project's file:** its bare paths stay its own project's (the keys the schema marks
  `path`: `baseconfig`, `filters`, `executable`, `root_style`, `master`). They are made absolute
  when it is read, so its tools find their cards and plan to the same identities as in their own
  file.
- **Location:** the file that imports sets its own `[run].name` and `project`; location is never
  imported. No imported file may be the same run, or both would write the same folders.
- **Part of a file** (V95): an entry `{ from = "zeus_validation", only = ["tools", "quantities",
  "run.default"] }` takes only those sections or dotted keys, each of which the file must have.
- **Taking out** (V95): `drop = ["run.default4", "plot.figures.statistics"]` removes dotted keys from
  what the imports gave, before this file's tables. Each must name something an import gave, and a
  file that imports nothing has nothing to drop. An imported file's own `drop` applies to its own
  imports.

`--show-config` lists where each quantity, tool and configuration came from, through every file
(`run.default from zeus_validation.toml ← zeus_common.toml`).

**`vars`** (V96). Names said once and cited anywhere in the file:

```toml
[config.vars]
ana    = "ZEUS_2012_I1116258"
events = 1_000_000

[run]
event_count = "{var:events}"        # one var, the whole value: an integer, as written there

[tools.rivet]
analyses = ["{var:ana}"]

[plot.data]
file = "rivet:{var:ana}"            # inside a longer string: a scalar, as text
```

They are replaced when the file is read, after its imports and `--set` (`--set
config.vars.events=50000`), so a point's identity is that of the same file written out. An imported
file's `{var:…}` takes this file's value: a shared file can be written with parameters. An unknown
name is refused with the nearest. `{var:…}` is the run TOML's own; the page texts' placeholders
(`{cell}`, `{q:…}`, `{opt:…}`, §10) are filled later, per page.

**`meta`** (V97). About the file, for people; it never changes a run:

```toml
[config.meta]
author     = "R. Brar"
references = ["ZEUS, Nucl. Phys. B 864 (2012) 1"]
versions   = { pythia8 = "8.317", rivet = "4.1.3", lhapdf = "6.5" }   # the stack the file was run with
```

`versions` names packages of `utils/Env/stack.toml`, each with a version string. When the stack has
another version, `--plan`, the run's start and `hep check` say so as a **warning**, and the run goes
ahead at your own risk. What is written is compared: `6.5` matches 6.5.6. A package stack.toml does
not name is refused, since its warning could never come. Every other key is free.

**The vocabulary** (`utils/Env/quantities.toml`, V58) says what each quantity name means for every
tool:
- its **shape**: `energies` is two numbers, `[beam A, beam B]`; `beams` is two PDG ids; `pdf` is a
  string or a set number;
- its **unit**.

A run TOML's quantity of that name is checked against the shape when the file is read (`[[275,
18]]`, not `[275, 18]`). A name the vocabulary does not have is the user's own, and reaches a tool
through its `key` or `target` (§8.1).

**Each tool folder** says how that tool consumes the vocabulary, in
`utils/Env/<tool>/quantities.toml`; a project master overlays those mappings in the same form:

```toml
[quantities.pythia.compatible_quantities]           # [quantities.<tool>.compatible_quantities]
sqrts    = { key = "Beams:eCM" }                      # the card line  Beams:eCM = value
energies = { keys = ["Beams:eA", "Beams:eB"] }        # an array value spread over several keys, in order
pdf      = { key = "PDF:pSet", check = "lhapdf:pythia" }  # the value as written; a provider check (C10)

[quantities.herwig.compatible_quantities]
seed_offset = { flag = "-x" }                         # a command-line argument instead of a card line
```

- **One form per entry:** each entry takes **exactly one** of `key`, `keys` and `flag`; `format` and
  `check` are additions.
- **`check`** is a provider check (C10), giving the `lhapdf install <set>` line to type when a set is
  not under `LHAPDF_DATA_PATH`.
  - `"lhapdf:bare"` takes a bare set name, `<set>[/member]`, as Sherpa does.
  - `"lhapdf:pythia"` takes the value exactly as Pythia's `PDF:pSet` reads it (V40: no prefix is
    added). That is `"LHAPDF6:<set>[/member]"`, whose set must be installed; one of Pythia's own set
    numbers (`13`, checked against its `PDFSelection.xml`, V60); or a grid file.
  - A bare name that is an installed LHAPDF set is refused with the `LHAPDF6:` spelling, since Pythia
    would read it as a file.
- **A tool with a `render.py`** takes plain `key` mappings and interprets the keys itself: a YAML
  path for Sherpa, a SINDARIN variable for Whizard.

**What the tool folders map:**

| Quantity | pythia | sherpa | herwig | whizard | madgraph |
|---|---|---|---|---|---|
| `energies` `[E_A, E_B]` | `Beams:eA`, `Beams:eB` | `BEAM_ENERGIES` | `Luminosity:BeamEMaxA`, `…MaxB` (×GeV), in Herwig's slots (lepton on A) | `beams_momentum` | `ebeam1`, `ebeam2` |
| `sqrts` | `Beams:eCM` | `BEAM_ENERGIES = [√s/2, √s/2]` | `Luminosity:Energy` | — | — |
| `beam_a`, `beam_b` | `Beams:idA`, `Beams:idB` | — | — | — | — |
| `beams` `[id_A, id_B]` | `Beams:idA`, `Beams:idB` | `BEAMS` | — | `beams` (model names) | `lpp1`, `lpp2` |
| `pdf` (checked, C10) | `PDF:pSet = <value>`: write `"LHAPDF6:<set>"`, or a Pythia set number | `PDF_SET[0]` (and `MPI_PDF_SET`): the bare `<set>` | — | — | — |
| `events` (built-in) | `Main:numberOfEvents` | `EVENTS` | (the `-N` flag) | `n_events` | `nevents` |
| `threads` (built-in) | `Parallelism:numThreads` | — | — | — | — |

**Beam order** (V62).
- `energies` and `beams` are lists in **the run's** beam order, `[beam A, beam B]`.
- A point that gives `beams` (or `beam_a` and `beam_b`) names that order. One that gives none
  follows the convention `[hadron, lepton]`, which every card so far assumes.
- A tool whose card needs its beams in fixed slots says so (`[beams] slots`: Herwig's
  `EPCollider.in`, lepton on A), and the runner reorders every per-beam value for it, the ids and
  the energies together.
- The other tools take the order as given.

`rivet` maps nothing: it reads beams and energies from the events, and its analysis options are
always targeted explicitly (§8.1).

---

## 4. `[run]`

```toml
[run]
serial        = 3                   # optional: every configuration's folder becomes 03_<label>
name          = "eic"
project       = "PhotoProduction"
configuration = "pdf"               # the default; `hep run <config> <configuration>` picks another
event_count   = 1_000_000           # defaults for every configuration
threads       = 20
description   = "EIC photoproduction studies"
```

<!-- generated: keys run -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | a string | **required** | the run's directory name |
| `project` | a string | **required** | the subfolder of `configs/`, `modules/`, `output/`, `results/`; must equal the folder the file is in, when it is under `configs/` |
| `cfgs` | a table |  | the configurations, each `[run.cfgs.<cfg>]` (V98; they were `[run.<cfg>]`, which is refused with the form to write, and `hep migrate` rewrites it). A configuration's key is its name for `hep run <config> <cfg>`, `sweep_runs`, `extends` and compare figures, and its folder unless it sets a `label`. Any name may be used, a [run] key's included. |
| `defaults` | a table |  | keys every configuration starts from (V56), below each configuration's own and the one it `extends`, above `[run]`'s. It is not a configuration; it may not set `label`, `title` or `extends`, which are each configuration's own. |
| `configuration` | a string |  | must name a `[run.cfgs.<cfg>]` table (C2). Under `sweep_runs` it may be left out; `hep run <config>` then ignores it |
| `serial` | an integer |  | the prefix `NN_` of each configuration's folder, `<name>/NN_<label>`: **location, never identity** (V12). A configuration's `serial` overrides it (V45). Changing it starts a fresh location. A configuration inherits it from `[run]`. |
| `event_count` | an integer, ≥ 1 |  | default for configurations; one of the two must set it A configuration inherits it from `[run]`. |
| `threads` | an integer, ≥ 0 | `1` | default for configurations. `0` means every core, **resolved to a number at plan time** A configuration inherits it from `[run]`. |
| `parallelism` | an integer or a string: `"auto"`, ≥ 1 | `1` | default for configurations: how many points run at once (V36); `"auto"` (V75): as many as the cores hold, `os.cpu_count() // the costliest point's cores`. `threads` stays each point's; never part of an identity or a seed, so changing it reruns nothing A configuration inherits it from `[run]`. |
| `description` | a string |  | what the run is for |
| `sweep_runs` | true or false or a list (a string each) | `false` | `true`: `hep run <config>` runs every configuration, one after another, in the order of the file; `["a", "b"]` (V79): these, in this order (04 §4.1) |
| `notify` | a string: `"none"`, `"desktop"` | `"none"` | `"desktop"` (V76): a desktop notification (`notify-send`) when `hep run` ends, with its verdict; never fails a run |
| `seed_type` | a string: `"identity"`, `"manual"`, `"random"` | `"identity"` | default for configurations: how a point's seeds are chosen, `"identity"`, `"manual"` or `"random"` (06 §8) A configuration inherits it from `[run]`. |
| `manual_seed` | an integer, ≥ 1 |  | default for configurations: under `seed_type = "manual"`, every point's seed (from 1 to the point's generators' `[card] seed_range`: 899,999,999 for Pythia, checked when the point is planned, V54); ignored otherwise (`--plan` says so) A configuration inherits it from `[run]`. |
<!-- /generated -->

The configurations are `[run.cfgs.<cfg>]` (§5); any other key or table in `[run]` is an error (C1).
`[run].configuration` is required unless `sweep_runs` is set. An integer `event_count` must be set
here or in every configuration.

### 4.1 `sweep_runs`: every configuration, one run after another

With `sweep_runs = true`, `hep run <config>` runs every configuration, in the order of the file.
With a list, `sweep_runs = ["pdf", "energies"]` (V79), it runs those, in the list's order. A name
that is not a configuration, or one named twice, is refused.

Each one is **a run of its own**: exactly what `hep run <config> <cfg>` does, with its own title,
blocks, verdict, journal, `points.json` and plots, in its own folder. Each starts after one header
line of its `title`:

```
run 01 - Proton PDFs -
eic · pdf: 4 point(s), 1000000 events, 12 threads
── point 1/4: MSTW08lo ── ok after 12min 4s
…
4 done, 0 failed, 0 skipped
```

- **Every run is planned before the first starts**, so a config error in any of them exits 2 with
  nothing run. Each is planned again when its turn comes, so edits to the TOML made meanwhile
  count; a run an edit has broken fails alone.
- **The runs are pipelined** (V75): a run starts once the one before has started all its points,
  and its points take the cores the earlier run's last points leave free.
  - Each run's own order (pre, points, combined, post, plots), folder, journal and verdict are kept.
  - While two runs overlap, a block's heading names its run: `── point 1/4 (energies): 5x41 ── ok
    after …`.
- **A failed run lets the next start.** Ctrl-C stops the running runs (exit 6) and **starts no
  more**.
- **The exit code** is 6 if a run was stopped, else 1 if any failed, else 0.
- **Running one:** `hep run <config> <cfg>` runs just that one, whether or not the sweep lists it.
- **Options:**
  - `--plan` prints every run's plan under its header;
  - `--rerun`, `--set` and `--only plot` apply to each;
  - `--only pre|post` skips the runs without that stage;
  - `--points` is refused: name the configuration.
- **Being in a sweep changes no run**: not its identity, its seeds or its folder.

---

## 5. `[run.cfgs.<cfg>]`

The configurations are the tables of `[run.cfgs]` (V98). `[run]` itself holds only its own keys
(§4), so a misspelt table there is an error, never a configuration, and a configuration may have any
name, `threads` or `defaults` included. The old form, `[run.<cfg>]`, is refused with the table to
write, and `hep migrate` rewrites it, commented-out configurations included. A configuration's
dotted path is `run.cfgs.<cfg>.<key>`: `--set run.cfgs.pdf.threads=8`, `drop = ["run.cfgs.default4"]`,
`hep explain run.cfgs.pdf.threads`.

```toml
[run.defaults]                               # optional (V56): keys every configuration starts from
tools       = [["pythia", "rivet"], "yd2rt"]
threads     = 20

[run.cfgs.energy_pdf]
serial      = 3
label       = "energy_pdf"                   # folder name (after the serial); defaults to the table key
title       = "Beams x PDFs"                 # the header line under [run].sweep_runs (§4.1)
description = "Beams x PDF grid: one page per energy, PDF curves on each"
event_count = 500_000                        # overrides [run]
sweeps      = ["energies", "pdf"]            # 4 × 4 = 16 points
plot_points = ["energies"]                   # 4 pages; the PDFs are the curves on each
tools       = [["pythia", "rivet"], "yd2rt"] # group 1 together (FIFO), then group 2
static      = { energies = "18x275" }        # this configuration's own static values
prelim      = { fifo = ["events.hepmc"] }    # replaces [prelim] for this configuration

[run.cfgs.pdfs_100M]
extends     = "energy_pdf"                   # everything of energy_pdf, then these
event_count = 100_000_000
label       = "PDFs_100M"
```

A configuration's value is, in order:
1. its own;
2. else the one it `extends`'s, in turn;
3. else `[run.defaults]`'s;
4. else `[run]`'s;
5. else the default (V56).

`"default"` in a layer is the next layer's value. `label`, `title` and `extends` belong to each
configuration alone, and `[run.defaults]` refuses them; `[run.defaults]` is never a configuration. A chain
of `extends` is followed, and a circle is refused. `hep run CONFIG --show-config` prints every value
with the layer it came from.

<!-- generated: keys configuration -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `extends` | a string |  | another configuration this one starts from (chains are followed; a circle is refused) |
| `serial` | an integer, or `"default"` |  | overrides `[run].serial` for this configuration: its points go to `<P>/<run name>/NN_<label>/` (V45) |
| `name` | a string |  | the run folder above this configuration's: `<P>/<name>/NN_<label>/` (V46) |
| `label` | a string |  | the configuration's folder, after the serial: `NN_<label>`; empty means the table key (V45) |
| `title` | a string |  | the header line of the run under `[run].sweep_runs`: `run 02 - <title> -` (04 §4.1) |
| `description` | a string |  | what the configuration is for |
| `event_count` | an integer, ≥ 1, or `"default"` |  | required here if `[run]` has none |
| `threads` | an integer, ≥ 0, or `"default"` |  | `0` = every core |
| `parallelism` | an integer or a string: `"auto"`, ≥ 1, or `"default"` |  | points at once (`"auto"`: cores ÷ a point's cores, V75); `--plan` and the run's title say about how many cores that is, and warn past the machine's |
| `swept` | true or false | `true` | false: [run].sweep_runs leaves this configuration out |
| `seed_type` | a string: `"identity"`, `"manual"`, `"random"`, or `"default"` |  | `"identity"`: from the generator's identity; `"manual"`: exactly the given seed; `"random"`: drawn when the point runs (06 §8) |
| `manual_seed` | an integer, ≥ 1, or `"default"` |  | the seed of every point under `"manual"`; a quantity targeting `<tool>/seed` gives a point its own |
| `sweeps` | a list |  | 04 §5.1; `[]` is one point |
| `plot_points` | a list (a string each) |  | 04 §5.2 |
| `combine` | a list (a string each) |  | swept quantities whose points are merged into one curve (04 §5.5) |
| `tools` | a list | **required** | 04 §5.3 |
| `pre` | a list |  | the form of `tools` (04 §5.4) |
| `post` | a list |  | the form of `tools` (04 §5.4) |
| `static` | a table |  | merged over `[static]` and the layers', key by key (04 §7); a `"default"` keeps the layer below's |
| `prelim` | a table |  | the nearest layer's **replaces** `[prelim]` whole for this configuration (its chain's interfaces); `{}` means none |
<!-- /generated -->

### 5.1 `sweeps`

- A **string** is an independent axis. The points are the grid (Cartesian product) of the axes.
- An **array** is an **entangled** group: its quantities move together, value *i* with value *i*,
  so they need equal value counts (C3). The group is one axis of the grid.
- The order decides the point names (tags joined in `sweeps` order) and the running order.
- Every name must be a declared quantity, and none may appear twice (C3).
- A quantity's `exclude = [i, …]` (1-based) leaves those values out of every sweep of it (§8).

```toml
sweeps = ["energies", ["pdf", "alphas"], "mpi"]    # 4 × 3 × 2 = 24 points: pdf and alphas zipped
```

### 5.2 `plot_points`

Each name must be swept here (C4). The **pages** are the grid of their values, and every other
swept quantity becomes the **curves** on a page. `[]` is one page, with every point as a curve.
Naming one member of an entangled group selects the group.

| `sweeps` | `plot_points` | Page folders | Curves per page |
|---|---|---|---|
| `["pdf"]` | `[]` | 1 (no folder) | 4 |
| `["energies", "pdf"]` | `["energies"]` | 4 (`5x41/`, …) | 4 |
| `["pt0ref", "mpi"]` | `["mpi"]` | 2 | 3 |

### 5.3 `tools`

- **Entries:** each entry is a **tool tag** (a key of `[tools.<tag>]`) or an **array of tags** that
  run **together** as one group (one level only; C5). An empty group is an error.
- **Order:** groups run in order. A group starts only when the previous one succeeded and its
  products passed their checks.
- **`"@<quantity>"`** is replaced, per point, by the tool tag that quantity's value names (V19):
  `tools = [["@generator", "spectra"]]` with `values = ["pythia", "herwig", "sherpa"]`. The quantity
  must be swept or static, and every value must be a tool tag (C5).
- **Exported tags:** a tag that is only *exported* to another tool (§9.4) need not be in `tools`; it
  is configured and rendered, not run.

### 5.4 `pre` and `post`

The same form as `tools`, run **once**:

| | When | Where | Inputs | Identity |
|---|---|---|---|---|
| `pre` | before the first point; a failure stops the run | `…/<cfg>/pre/` | `{points}` (the manifest) | its own; **part of every point's**, so a changed pre stage reruns the points |
| `post` | after the points, **only when every point is complete** | `…/<cfg>/post/` | an `input` naming a product of the points reads that product **of every point** (`{inputs}`, `{named_inputs}`); `{points}` | its own plus every point's: it reruns when any point changes |

- **What they take:** neither takes quantities or `[prelim]`.
- **Names:** a point may not be named `pre` or `post`.
- **Pre products** are interfaces every point may name as `input`.
- **Post outputs:** a post tool may not write a file with the name of the points' product.

### 5.5 `combine`

`combine = ["replica"]` (V35) merges the points that differ **only** in the combined quantities, so
each group becomes one curve with their statistics added. The typical use is seed replicas, so that
one PDF's five 1M-event seeds become one 5M-event curve:

```toml
[run.cfgs.default]
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
| The merge | a stage per group, after its points: the `merge` tool (`rivet-merge -e`, [05 §7](05_Commands_and_Tools.md#7-merge--rivet-merge-in-post)) of the points' YODA product into `results/…/<cfg>/<group>/<product>`, beside the points' folders; skipped when complete, rerun when any of its points changes; `--plan` lists them |
| The pages | drawn from the groups, not the points: the combined quantities are neither pages nor curves |
| Rules (C14) | each name is swept here as an axis of its own (not inside an entangled group), and is not in `plot_points` |

The points keep their own products. Another configuration with the same sweeps and no `combine`
draws each seed as its own curve, from the same seeds and events. To merge for one figure only, use
a `merged` figure ([03 §7.4](03_Plots.md#74-merged-points-merged-for-this-figure)). The whole
example is `configs/PhotoProduction/zeus_seedSweep.toml`.

---

## 6. `[prelim]`

Interfaces that exist before any tool starts, so neither end of a connection risks a missing file.

```toml
[prelim]
fifo     = ["events.hepmc"]                  # mkfifo, fresh per attempt, removed when the point ends
files    = ["showered.hepmc"]                # created empty (the writer truncates), kept
commands = [["lhapdf", "ls", "--installed"]] # argv arrays, run in order before the first group
```

<!-- generated: keys prelim -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `fifo` | a list (a string each) |  | named pipes in the point's output directory. A FIFO connects tools **in one group** only, has **one reader**, and never feeds a tool that is not `streamable` (C6). |
| `files` | a list (a string each) |  | regular files in the point's output directory, **kept**: the way to keep events for another configuration |
| `commands` | a list |  | run in the point's output directory; output to `logs/prelim.log`; a nonzero exit fails the point. Placeholders: `{repo}`, `{out}`, `{res}`, `{file:<name>}` |
<!-- /generated -->

A name declared twice is an error. `[run.cfgs.<cfg>].prelim` replaces this table for one configuration.

---

## 7. `[static]` and selectors

```toml
[static]
energies = "27x920"     # a tag …
lepton   = -11          # … or an exact value (numbers compare numerically: 6 finds 6.0) …
pdf      = "#2"         # … or "#N", the N-th value (1-based)
```

- **When it applies:** a static value applies **only when the quantity is not swept** in the
  active configuration.
- **What it may name:** every key must be a declared quantity. `[run.cfgs.<cfg>].static` is merged over
  it, and `--set static.<q>=…` over both.
- **Inactive quantities:** a quantity that is neither swept nor static is **inactive**. It renders
  nothing, and the base card's value stands.
- **Selector order** (static values and `--points q=…`): a declared **tag**, then an exact
  **value**, then **`#N`**. A selector that matches nothing lists the tags.

---

## 8. `[quantities.<q>]`

```toml
[quantities.pdf]                     # in the vocabulary: no key needed; Pythia reads the value as written
values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]
tags   = ["MSTW08lo", "NNPDF23lo"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 LO"]

[quantities.pt0ref]                  # not in the vocabulary: name the key per tool
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

<!-- generated: keys quantity -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `values` | a list | **required** | scalars or arrays (an energy pair) |
| `tags` | a list |  | one per value. The default is the value with anything but `A–Za–z0–9.+-` replaced by `-`. Tags name point directories: keep them short and unique. |
| `labels` | a list |  | legend text, in **LaTeX** (`$e^-$`, `$\sqrt{s}$`), the one label language of every text a run TOML gives a page (V65): math in `$…$`, the rest text, where a bare `_` or `^` is the character (`"PDF4LHC21_40"`). A label written in ROOT's TLatex (`#sqrt{s}`, `p_{T}` with no `$`) is refused, with its LaTeX as the hint; `hep migrate` rewrites it (V79). `\_`, `\^` and `\#` also give the character, even before a brace; in TOML write them in single quotes, `'PDF4LHC21\_40'`, since in `"…"` a backslash starts a TOML escape |
| `shape` | a string or a list |  | the values' shape, in the vocabulary's grammar (V76): `"pdg"`, `"float\|int"`, `["float", "float"]`; checked when the TOML is read. For a quantity of your own (one the vocabulary, `utils/Env/quantities.toml`, does not name); a vocabulary quantity has its own shape |
| `styles` | a list (a table each) |  | one per value (V67): its curves' look, `{ colour, line, width }`. `colour` is `"#rrggbb"`, a ROOT name (`"kBlue+1"`) or number (the yoda backend draws `#rrggbb` only); `line` is `solid`, `dashed`, `dotted` or `dashdot`; `width` is in points. A key left out, or `"default"`, is the style's; curves with no colour take the palette in turn, as mkhtml's take its cycle. A value keeps its look on every page, so a PDF is one colour throughout. With two curve axes, the later one's keys win |
| `key` | a string or a table |  | the native key. A string needs a `target`. A table entry for a tool tag wins over one for its type. |
| `target` | a string or a list |  | restricts the consumers (04 §8.1) |
| `format` | a string |  | a Python format for the value: `"{}*GeV"` |
| `description` | a string |  | what the quantity is |
| `exclude` | a list |  | values a sweep leaves out, by their **1-based** place (as `static = "#2"` and `--points 2` count): `exclude = [2]` sweeps the others. The remaining points keep their names and identities and are numbered 1… over what is swept. In an entangled group, a value any member excludes leaves the group. `static` may still pick an excluded value. Refused: a place outside 1…len(values), or none left (V42) |
<!-- /generated -->

### 8.1 Who consumes a quantity

This is decided at plan time, for every **active** quantity (swept, or with a static value).

**With `target`**, each target is `"<tag>"`, `"<tag>/<analysis>"` or `"<tag>/seed"`. The tag must
be a `[tools.<tag>]` table, and a target not in this configuration's chain is skipped.

| Target | Tool | Effect |
|---|---|---|
| `"<tag>/seed"` | any | a **replica**: enters the generator's identity, so its seeds; renders nothing. Under `seed_type = "manual"` the value **is** the point's seed (an integer) |
| `"<tag>/<analysis>"` | rivet (any tool with `analyses`) | an **analysis option** `<analysis>:<key>=<value>`; `key` is the option's name and is required. It must be declared in the analysis's `.info` (C9) |
| `"<tag>"` | `custom` or `module` | a **config key**: `key` (or the quantity's name) in the tool's extracted config (§9.2) |
| `"<tag>"` | a tool with a card | the native `key`, else the master's mapping for this tool type, else an error |

**Without `target`**, every tool in the chain (and every exported tool) is asked, in order:

1. the quantity's `key` table has an entry for its tag or its tool type → that native key;
2. else the master maps the quantity for its tool type → the master's mapping;
3. else the quantity is in the tool's `consumes` list (custom and module tools) → its config.

**Zero consumers is an error** (C7): a value that changes a directory name and nothing else is what
v1 kept finding (00/B14, 00/B40).
- More than one consumer is fine, and `--plan` prints the table.
- In an `@quantity` chain, a consumer among the configuration's alternatives is enough, and the
  selector quantity is consumed by the choice itself.

**Two sources for one native key** in one card (a quantity and a built-in, or two quantities) is an
error (C8). An override equal to the base card's value is written, but does not change the identity.

### 8.2 Replicas

```toml
[quantities.replica]
target = "pythia/seed"
values = [1, 2, 3]
tags   = ["s1", "s2", "s3"]
```

Replicas are statistically equivalent runs. The value enters the generator's identity, so each point
gets its own seed block. Seeds are never written by hand ([06 §8](06_Internals.md#8-identity-seeds-and-skip)).

### 8.3 Built-in quantities

`events` (the configuration's `event_count`) and `threads` are provided by the runner. They reach a
tool only through the master (the table in §3), and need no consumer. Declared as quantities, they
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

<!-- generated: keys tool -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `tool` | a string | **required** | a standard tool (a folder of `utils/Env/`, 05 §3), `"custom"` or `"module"` |
| `baseconfig` | a string or a list |  | native base card(s), read in order (root `configs/<project>/`). Tools with a card only. |
| `input` | a string or a list |  | what it reads: `[prelim]` names, another tool's `output_file`, a pre product, (post) a product of every point, or a path. The first input is `{input}`. |
| `output_file` | a string or a list |  | what it writes. An array is fan-out: App_Pythia writes the same events to each (V16). Exactly one writer per output (C6). |
| `timeout` | a number, ≥ 0 |  | the tool fails when it runs longer |
| `stall_after` | a number, ≥ 0 |  | the tool fails when silent this long: no log line, status message or heartbeat (a prepare step waits at least 3600) |
| `status` | a string: `"standard"`, `"filters"`, `"none"` |  | `"standard"` (`$HEP_STATUS_FD`), `"filters"` (the folder's `filters.toml`), `"none"` |
| `filters` | a string |  | your own rules in place of the folder's, root `configs/<P>/`; implies `status = "filters"` (V61) |
| `executable` | a string |  | custom and module: bare → `build/<project>/<name>` (must be built); `path:<command>` → `PATH` |
| `arguments` | a list |  | custom and module: argv after the config; placeholders (04 §10) |
| `consumes` | a list (a string each) |  | custom and module: quantities written into the config |
| `config` | a table |  | custom and module: `[tools.<tag>.config]`, extracted to a file (04 §9.2) |
| `streamable` | true or false |  | may it read a FIFO? |
| `consumes_events` | true or false |  | is its event count checked against the producer's sidecar? |
| `settings` | a table |  | native card settings as written, `"HeavyIon:mode" = 1`, with no base card needed: over the base card, refused when a quantity sets the same key (one source per key, C8); a tool with no card refuses them (V59) |
| `cores` | an integer, ≥ 1 |  | how many cores it keeps busy, for `--plan`'s note and the crowded warning (V60); an integrated program is estimated as the generator's threads and one more |
| `shards` | an integer, ≥ 1 | `1` | K > 1: K processes of this tool, each on a share of the events, merged into its `output_file` by the folder's merge tool (V31; rivet, 05 §5.1). The chain is unchanged. |
<!-- /generated -->

Every other key is **tool-specific**. It is checked against the tool folder's `[options]` (type and
`required`, 05 §4–15), or, for custom and module tools, taken as a standard-configuration request
(§9.4). An unknown key is an error that lists the keys the tool takes (C1).

### 9.2 Custom tools

```toml
[tools.fit]
tool        = "custom"
executable  = "fit_peaks.py"                # build/<P>/fit_peaks.py (path:<command> for PATH); ./… from the repo
arguments   = ["{in:lambda.yoda}", "{res}/fit.json"]
input       = "lambda.yoda"
output_file = "fit.json"
consumes    = ["energy"]                    # written under [quantities] in its config
filters     = "fit_filters.toml"

[tools.fit.config]                          # written verbatim to output/…/<point>/config/fit.toml
model  = "gauss+poly2"
window = [1.09, 1.14]
```

The runner writes `output/…/<point>/config/<tag>.toml` when the table has a `config`, consumes a
quantity, or requests an export. It passes it as the **first argument** (the folder's argv is
`{exe} {config} {arguments}`). The file holds:

- the `[tools.<tag>.config]` table, verbatim;
- consumed values:
  - a value mapped to a **config key** (`target = "fit"`, `key = "window"`) is set at that key
    (dotted keys nest: `"cuts.window"`);
  - a value consumed **by its quantity name** (`consumes`, or a target with no key) goes under
    `[quantities]`;
- `[standard.<key>]` tables for export requests (§9.4).

A custom tool is count-checked only if its table sets `consumes_events = true` and its folder names
how to read the count (the `custom` folder names none). A product it writes should go to
`{partial:output}`; the runner renames it after the checks pass.

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

A module tool works as a custom tool does, for a program built with `utils/Module.hh`
([06 §21](06_Internals.md#21-modulehh)). It always gets a config, and its argv is
`{exe} {config} --input={input} --output={partial:output} --events={events}
--sidecar={input_sidecar} {arguments}`. Its count is checked from its report (`<output>.json`, key
`events`).

### 9.4 Standard configurations (exports)

A custom or module tool may ask for the configuration the runner renders for a **standard** tool, and
use it however it likes. This is how an **integrated program** (Pythia and Rivet in one process) gets
the same card and seeds as the chain.

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
| What exists | every tool with a card exports `<tool>_card` automatically; the rest are declared in the folder's `[exports]` (05 lists them per tool). An export a tool does not offer is an error, with the ones it does (C13) |
| Rendered as in a chain | the same card a process of that tool would get for this point, **seeds included**; the table need not be in `tools` |
| Consumed | the quantities the exported tool consumes count as consumed (C7) |
| Prepared on demand | an export with `needs_prepare` (`herwig_run`, `sherpa_results`, `madgraph_process`) runs that tool's prepare step (cached) before this tool's group |
| In the config | `[standard.<key>]` with `tool`, `tag` and, for a card, `path` (base + point card in one file) and `parts` (the files in reading order); for values, the named values (`analyses`, `plugin_path`); for a prepared product, `path` |
| On the command line | `{std:<key>}` is the export's `path` |
| Identity | includes the exported tool's identity |

The program then owns what the chain would have done: σ over threads (L1), the final σ to Rivet (L2),
and catching at thread boundaries (L3). There is no FIFO, so the runner checks its exit code and its
outputs.

---

## 10. Placeholders

**In argv, cards and arguments.** `{name}` is replaced from the point's plan in:
- a folder's argv, env, cwd, card lines and footers;
- a custom tool's `arguments`.

The rules:
- `{{` and `}}` are literal braces.
- An argument that is exactly one placeholder whose value is a list is **spliced** into argv:
  `{inputs}` becomes several arguments, and an empty list becomes none.
- An unknown placeholder is an error with the nearest name.

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

**In the run TOML itself**, `{var:name}` is a `[config.vars]` value (§3), replaced when the file is
read, everywhere, before any of these.

**In page texts** (V66). These are the titles, `legend_header`, the axis labels, `[plot.data].legend`,
a figure's `labels`, the quantities' `labels` and the `.plot`'s own. They may cite the points:

| Placeholder | Is |
|---|---|
| `{cell}` | the page's `plot_points` values, joined |
| `{q:<quantity>}` | the label of the quantity's value at the point, swept or static |
| `{opt:NAME}`, `{opt:<analysis>:NAME}` | Rivet's: the analysis option at the point (the `.info`'s `(default X)` when not set) |

A page text's placeholder must have one value across the page's curves; a curve label's is its own
point's. A cited name the points don't have is refused at plan time, with the nearest name.

---

## 11. `[plot]`

The plot stage, and how to use it, is [03](03_Plots.md). A configuration whose run TOML has no
`[plot]` draws nothing.

<!-- generated: keys plot -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `backend` | a string or a list (a string each): `"root"`, `"yoda"`, `"mpl"`, `"both"`, or `"default"` | `"root"` | `"root"` (Paint), `"yoda"` (rivet-mkhtml; frozen, V71), `"mpl"` (matplotlib, mkhtml's pages drawn in-process: V71), `"both"` (root and yoda, V28) or an array of them, from the same pages |
| `formats` | a list (a string each): `"pdf"`, `"png"`, `"svg"`, `"eps"`, or `"default"` | `["pdf"]` | `pdf`, `png`, `svg`, `eps`. mkhtml writes pdf and png always. The root backend writes `plots/root/index.html` (V70): a section per `plot_points` cell, each page by its PNG or SVG, else an embedded PDF, linked to every format; add `png` for thumbnails a browser shows at once |
| `band` | a list (a string each) |  | curve axes drawn as an envelope (V69): per value of the other curve axes, one curve, the band quantity's first value, with the min–max of all its values shaded around it in the curve's colour (the usual PDF or scale band). Its legend entry ends `(<q> envelope)`; its own statistical errors are not drawn. A name that is not a curve axis of the configuration (swept, not `plot_points`, not combined) is refused at plan time. The yoda backend draws the same envelope as mkhtml's error band |
| `objects` | a list (a string each), or `"default"` |  | matched against the option-free YODA path (`/photo_eic/d01-x01-y01`) or any variant's path. No object matching is an error. |
| `ratio` | true or false, or `"default"` | `false` | a ratio pad: each curve over the data, or over the first curve when there are no data |
| `y_gutter` | a number, ≥ 0, or `"default"` | `0.5` | the top of the y axis at (1 + g) × the largest drawn value (on a log axis, g of the decades shown); `0`: no headroom. `"default"`: no gutter, the tool's own range (V29, V55) |
| `x_gutter` | a number, ≥ 0, or `"default"` |  | widens x by g of its span, symmetrically (in decades on a log axis). `"default"`: the range the bins give |
| `logy` | true or false, or `"default"` |  | log y (default: the .plot's) |
| `logx` | true or false, or `"default"` |  | log x (default: the .plot's) |
| `logz` | true or false, or `"default"` |  | a heat map's colour scale (V87) |
| `auto_range` | true or false, or `"default"` | `true` | trim x to the bins with content, in curves and data |
| `normalise` | a string or true or false: `"area"`, `false`, or `"default"` | `false` | `"area"` (V68): every curve, and the data, scaled to unit area, Σ value × bin width over the bins drawn (after voiding and the data's alignment), so pages compare shapes. Both backends scale the same way. The y label stays the `.plot`'s: set `y_label` (e.g. `"$1/\sigma\,\mathrm{d}\sigma/\mathrm{d}E_T$"`) on the pages it applies to. A figure (04 §11.2) may set it for its own |
| `void_empty` | true or false, or `"default"` | `false` | blank a bin that is zero in **every** curve |
| `use_data` | true or false | `true` | `false`: the `[plot.data]` table stays in the file but is not drawn, and a `ratio` divides each curve by the page's first curve, the first value of its curve axis (V44) |
| `min_entries` | an integer, ≥ 0, or `"default"` | `0` | blank a bin that fewer raw entries went into, in **any** curve (read from the `/RAW` twin; objects without one are not voided this way) |
| `range_pad` | an integer, ≥ 0, or `"default"` | `0` | whole bins kept either side of the filled ones |
| `root_style` | a string, or `"default"` |  | a style file over base.toml (04 §12). Refused by the yoda backend alone. |
| `title` | a string, or `"default"` |  | the main title, centred above the frame (V51). Every page; a figure (04 §11.2) overrides it for its own |
| `title_left` | a string, or `"default"` |  | small text just above the frame's top-left and top-right corners (V51), inherited the same way |
| `title_right` | a string, or `"default"` |  | small text just above the frame's top-left and top-right corners (V51), inherited the same way |
| `legend_header` | a string, or `"default"` |  | the legend's first line (V51), inherited the same way. Children inherit every key their parent has and a key means the same at both levels |
| `data` | a table |  | 04 §11.1 |
| `style` | a table |  | 04 §12 |
| `figures` | a table |  | `[plot.figures.<figure>]`: a recipe for pages, with every page key of `[plot]` for its own (04 §11.2, V80) |
<!-- /generated -->

**What `"default"` gives in `[plot]`** (it sets nothing; the drawing tool decides):

| Key | `"default"` gives |
|---|---|
| `min_entries`, `range_pad` | 0: every bin drawn |
| `void_empty` | false: neither Paint nor mkhtml voids a bin by itself |
| `normalise` | false: neither tool scales a curve by itself |
| `auto_range` | off: the tool's own x range |
| `y_gutter`, `x_gutter` | no gutter: the tool's own range |
| `logx`, `logy`, `logz` | the analysis's `.plot` `LogX`/`LogY`/`LogZ` |
| `ratio` | the `.plot`'s `RatioPlot`, else a ratio pad when the page has reference data (mkhtml's rule) |
| `formats` | Paint's own, pdf (mkhtml writes pdf and png anyway) |
| `objects` | every object |
| `backend` | `"root"` |
| `root_style` | no style file: base.toml |

In a figure, a `"default"` keeps `[plot]`'s value, and the `.plot`'s when `[plot]` sets none.
`x_label` and `y_label`, which only a figure sets, keep the `.plot`'s labels.

`[plot].legend` is no longer a key: it moved to the style, as `legend.position`, and the error says
so.

### 11.1 `[plot.data]`

<!-- generated: keys data -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `file` | a string |  | `rivet:<Analysis>`: Rivet's own reference file (`build/Rivet/`, then `rivet-config --datadir`, `.yoda` or `.yoda.gz`); otherwise a path under `datasets/` (not in git) |
| `legend` | a string | `"Data"` | the data's legend entry |
| `map` | a table |  | MC object name (`d01-x01-y01`) → reference path. **Explicit only**, never matched by name (L18). A file without a map, or a map without a file, is an error. |
<!-- /generated -->

A file without a map, or a map without a file, is an error. The reference is drawn on the pages its
map names, **aligned** to the drawn binning: cut to its longest run of bins whose edges are all MC
edges, or dropped (with a warning) when none line up.

### 11.2 `[plot.figures.<figure>]`

A figure is a recipe for pages (V80); its classes, each with an example, are
[03 §7](03_Plots.md#7-figures). These are its own keys:

<!-- generated: keys figure -->
| Key | Type | Default | Meaning |
|---|---|---|---|
| `class` | a string: `"defined"`, `"overlay"`, `"merged"`, `"compare"`, `"derived"`, `"scan"`, `"sheet"` | `"defined"` | how the pages are built. `defined`: an analysis object's own pages, `<cell>/<object>`, its curves the cell's points (and option variants). `overlay`: several objects of each point on one page, `<cell>/<name>`; a curve per object and point, labelled by `labels` (plus the point's, when the page has several); a ratio divides by the first curve. `merged` (V82): the objects' pages, `<cell>/<name>/<object>`, with the points merged over the `over` axes: per value of the other axes, their YODAs merged by the combine folder's command (`rivet-merge -e`: statistics add, σ averaged), once per change of a member's YODA, into `output/…/plots/merged/<name>/`. The run keeps its points apart; the figure alone merges them (`combine` merges them for the whole configuration). `sheet` (V89): drawn pages laid out in a grid (`pages`, `columns`; below). `compare` (V83): the objects' pages across configurations, `<run>/compare/<name>/<cell>/<object>` beside the configurations' own folders (in `output/` and `results/`, a folder per backend). A curve per configuration and point (or combined group), labelled by the configuration (`labels`, else its `label`) and then the point's curve axes. The configurations must have the same page and curve axes (checked at plan time); the figure is drawn by the plot stage of each of them once all have complete points, and says what it waits for otherwise (`hep plot` draws it too). `derived` (V84): a new object per point, `/FIGURES/<name>` (`/FIGURES:R=0.4/<name>` per analysis-option variant): `op = "ratio"`, `"difference"` or `"sum"` of its two objects (histograms made estimates first; the same binning, else an error naming both), or `"projection-x"`/`"projection-y"` of its one 2D object (summed over the other axis: a histogram's weights, an estimate's values × widths, as a Scatter2D whose x ranges are the bins). It is appended to a copy of each point's YODA (`output/…/plots/derived/`, remade when the product or the figures change, by `utils/Env/figures/derive.py`: YODA's Python, so `load_hep`), and is then an object like any: its pages `<cell>/<name>` (labels from its first object's `.plot`; set `y_label`), an overlay or a merged or compare figure may name it (`"r15"`). `scan` (V85): one number per point against a swept quantity: `x` a curve axis whose values are numbers, `y` = `sigma` (the point's `/_XSEC`), `entries` (its events, or its object's raw entries), or `integral`, `mean`, `bin:N` of its one object. A page per cell, `<cell>/<name>`, a curve per value of the other curve axes: a Scatter2D, a point per x value with an x range halfway to its neighbours centred on it (so every backend can draw it as a bin; it is drawn as markers, `type = "Scatter2D"`). Axis titles: the quantity's name and the y read, until set. A quantity of names (PDF sets) cannot be an x yet |
| `type` | a string: `"Hist1D"`, `"Scatter2D"`, `"HeatMap"` |  | what is drawn: `Hist1D`, steps per curve; `Scatter2D` (V86), a marker per bin at its centre with its y error, in the curve's colour (`data.marker`, `data.marker_size` of the style), as Paint draws data; the legend shows the marker. The page TOML says `markers = true`; mkhtml and mpl draw the curves as they draw points (`ConnectBins=0`, with their x bars). `HeatMap` (V87): a 2D object (a YODA `Histo2D` or `Estimate2D`), the default for one: a page per point of the cell, `<cell>/<object>/<point>`, coloured by value with its scale on the right (labels from the `.plot`, `ZLabel` and `LogZ` too; no ratio, data or voiding). Paint draws heat maps; mkhtml and mpl draw the 1D pages only, and the plot stage says so. A 1D object cannot be a HeatMap, a 2D object neither a Hist1D nor a Scatter2D, nor in an overlay |
| `name` | a string |  | an overlay's page file stem, a merged figure's folder. A defined figure takes none: its pages are the objects' own |
| `objects` | a list (a string each) |  | matched against the short name (`d04-x01-y01`), the option-free path or a variant's path. A glob matching no object of the points is an error, at the plot stage |
| `op` | a string: `"ratio"`, `"difference"`, `"sum"`, `"projection-x"`, `"projection-y"` |  | a derived figure's: `ratio`, `difference`, `sum` (two objects), `projection-x`, `projection-y` (one) |
| `x` | a string |  | a scan figure's quantity (a numeric curve axis) and number (`sigma`, `entries`, `integral`, `mean`, `bin:N`); `sigma` and `entries` need no object |
| `y` | a string |  | a scan figure's quantity (a numeric curve axis) and number (`sigma`, `entries`, `integral`, `mean`, `bin:N`); `sigma` and `entries` need no object |
| `pages` | a list (a string each) |  | a sheet's (V89): the drawn pages whose names (`18x275/d02-x01-y01`, `*/eta_algorithms`) the globs match, in the globs' order, tiled `columns` wide into `plots/<backend>/sheets/<name>.pdf` and `.png`, each pad the page as it was drawn alone (pdflatex places the PDFs as vectors; PIL pastes the PNGs). For Paint's and mpl's pages. A sheet takes no page keys (its pages' figures set those); a glob naming no page fails the sheet |
| `columns` | an integer, ≥ 1 |  | a sheet's (V89): the drawn pages whose names (`18x275/d02-x01-y01`, `*/eta_algorithms`) the globs match, in the globs' order, tiled `columns` wide into `plots/<backend>/sheets/<name>.pdf` and `.png`, each pad the page as it was drawn alone (pdflatex places the PDFs as vectors; PIL pastes the PNGs). For Paint's and mpl's pages. A sheet takes no page keys (its pages' figures set those); a glob naming no page fails the sheet |
| `over` | a list (a string each) |  | a merged figure's: curve axes of the configuration (swept, not `plot_points`, not combined), checked at plan time; it may not also `band` them |
| `configurations` | a list (a string each) |  | a compare figure's, two or more, in curve order; one at least of this file. `"<Project>/<config>:<cfg>"` (V88) names a configuration of another run TOML: its points (as its last run left them) are curves beside this run's, labelled `<its run> <its label>` by default and by its own quantities; its page axes must have this run's tags. The pages are this run's (`<run>/compare/<name>/`), drawn by this run's plot stage or `hep plot` |
| `labels` | a list (a string each) |  | an overlay's: one legend label per object; a compare figure's: one per configuration (default: each configuration's `label`) |
| `x_label` | a string, or `"default"` |  | the axis titles (LaTeX) |
| `y_label` | a string, or `"default"` |  | the axis titles (LaTeX) |
| `style` | a table |  | a style layer for these pages (04 §12) |
| *every page key of `[plot]`* | as there | `[plot]`'s | `band`, `ratio`, `y_gutter`, `x_gutter`, `logy`, `logx`, `logz`, `auto_range`, `normalise`, `void_empty`, `use_data`, `min_entries`, `range_pad`, `title`, `title_left`, `title_right`, `legend_header`: the figure's value, for its pages only |
<!-- /generated -->

When each rule is checked:

| When | What is checked |
|---|---|
| when the file is read | each class's keys: a scan's `x` and `y`, a derived figure's `op` and its object count, a merged figure's `over`, a sheet's `pages`; the keys a class may not take (`labels` on a defined figure, `pages` on any but a sheet) |
| at plan time | the axes a band, `over` or a scan's `x` names, the configurations a compare figure names |
| at the plot stage | that its globs match objects, and that two defined figures do not claim one object |

`[plot.overlay.<name>]` and `[plot.object."<glob>"]` are figures now (V81). They are refused with the
figure to write, and `hep migrate` rewrites them:
- an overlay becomes `[plot.figures.<name>]` with `class = "overlay"`;
- an object table becomes `[plot.figures.<glob, as a name>]` with `objects = ["<glob>"]`;
- in a figure, a style key written bare (`ratio.range = …`) becomes `style.ratio.range`.

Object tables that matched the same object (they were applied in file order) become figures that
overlap, which the plot stage refuses: merge them by hand.

---

## 12. The style

The look of the ROOT pages is TOML (V27). **`utils/Apps/Paint/base.toml`** holds every key with its
default (rivet-mkhtml's look); edit it to change every page. Over it, key by key:

1. `[plot].root_style`: a style file (a bare name under `configs/<project>/`, `.toml` optional);
   `hep overlay FILE… --style FILE` for files;
2. `[plot.style]`;
3. a figure's `style` (`[plot.figures.<figure>]`), for its pages.

**What a layer may hold.** Each layer names **only what it changes**, in base.toml's tables, and is
checked:
- a key base.toml does not have is an error, with the nearest spelling;
- so is a value of another kind: a number for a number, a pair of numbers for a pair, a list for the
  palette;
- the runner checks at plan time, and Paint checks again.

**What a page holds.** A page's document holds only what the layers changed; `build/Paint.exe
PAGE.toml --dump-style` prints the whole merged style. Sizes are **points** (1/72 in) of the page,
unless said otherwise.

<!-- generated: style -->
| Key | Default | Means |
|---|---|---|
| `page.size` | `[4.67, 4.21]` | inches: the PDF's page; the PNG is size × dpi pixels |
| `page.dpi` | `300` | PNG resolution: 300 → 1400 × 1264 pixels |
| `page.font` | `"serif"` | serif \| sans \| mono (ROOT's Times, Helvetica, Courier) |
| `page.margins.left` | `0.16` | fractions of the page, around the axes |
| `page.margins.right` | `0.032` | fractions of the page, around the axes |
| `page.margins.top` | `0.066` | fractions of the page, around the axes |
| `page.margins.bottom` | `0.11` | fractions of the page, around the axes |
| `text.title` | `10.0` | axis titles |
| `text.labels` | `8.0` | tick labels |
| `text.legend` | `9.0` | legend entries (the yoda backend follows it) |
| `text.header` | `9.0` | the legend's first line: legend_header |
| `text.page_title` | `12.0` | title, centred above the frame |
| `text.corner` | `9.0` | title_left and title_right, just above the frame's corners |
| `curves.palette` | `["#EE3311", "#3366FF", "#109618", "#FF9900", "#990099"]` | #rrggbb, ROOT names (kBlue+1) or numbers |
| `curves.width` | `1.0` | points: the steps and their error bars |
| `curves.errors` | `"bars"` | bars (at the bin centres) \| band \| none |
| `data.colour` | `"kBlack"` | the reference data |
| `data.marker` | `20` | ROOT's marker style |
| `data.marker_size` | `2.0` | points |
| `data.x_bars` | `true` | the bin width as a horizontal bar |
| `axes.tick_length` | `6.0` | points; minor ticks are half as long |
| `axes.ticks_all_sides` | `true` | ticks on the top and right edges too |
| `axes.titles_at_ends` | `true` | the x title at the right end, the y title at the top; false centres them |
| `axes.title_offset` | `[1.0, 1.55]` | x, y: ROOT's title offsets (larger is further from the axis) |
| `axes.label_offset` | `2.5` | points between an axis and its tick labels |
| `legend.position` | `"top-right"` | top-right \| top-left \| bottom-right \| bottom-left, or [x, y]: its top-right corner in fractions of the frame (then right-aligned) |
| `legend.inset` | `[5.0, 5.0]` | points from the frame's corner (x, y), for a named position |
| `legend.spacing` | `1.2` | line pitch, × the legend's text size |
| `legend.symbol` | `16.0` | points: the width of the "+" beside each entry |
| `legend.gap` | `5.0` | points between the "+" and its text |
| `ratio.heights` | `[2.0, 1.0]` | the main pad to the ratio pad (mkhtml's 6:3) |
| `ratio.range` | `[0.5, 1.5]` | always shown; widened to the ratios drawn … |
| `ratio.limits` | `[0.0, 3.0]` | … but never past these |
| `ratio.divisions` | `512` | ROOT's axis divisions: at most 12 labelled (0.1 on ~0.4–1.5), 5 minor each |
| `ratio.decimals` | `true` | labels 1.0, 1.2, … rather than 1, 1.2, … |
<!-- /generated -->

**What the other backends honour.** mkhtml and mpl draw with mkhtml's own look. They honour:
- a `legend.position` corner (or `best`: Paint takes the corner with the fewest drawn points under
  the legend, and matplotlib chooses its own);
- `text.legend` and `text.header`;
- `ratio.divisions`;
- `ratio.range` with `ratio.limits` (V48: each page's window by Paint's rule, so both show the same
  window).

**What they refuse.** Alone, they refuse `root_style` and every other style key. Beside the root
backend those are Paint's to honour, and are allowed, but a legend at `[x, y]` is still refused,
because the two page sets would disagree about it. A `best` legend, like any other, is placed within
the y range drawn, so give it headroom with a numeric `y_gutter`.

---

## 13. Validation rules

All of these are checked at plan time. Every error names **where** (the file and key) and gives a
**hint** (what to do), and a misspelt name gets the nearest spelling. `hep run` exits 2 on any of
them, before anything runs.

| # | Rule | Example message |
|---|---|---|
| **C1** | An unknown section or key is an error; a tool-specific key is checked against the tool folder's `[options]` (type, `required`). | `unknown key 'min_entry'` · `did you mean 'min_entries'?` |
| **C2** | `[run].configuration`, and a configuration named on the command line, must name a `[run.cfgs.<cfg>]`. | `no configuration 'energy-pdf'` |
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

The plot checks follow the same shape:
- an unknown backend, format, gutter value, `[plot.data]` key, figure key or style key;
- a data file without a map;
- a style key a backend cannot honour;
- a band or `over` that is not a curve axis;
- a figure's class rules (§11.2);
- a TLatex label (V79);
- a page text citing a placeholder the points don't have.

---

## 14. Files the runner writes

**Per point** (`output/…/<point>/`):

| File | Holds |
|---|---|
| `cards/<tag>.point.<ext>` | the overrides (append style) |
| `cards/<tag>.<ext>` | base + point card in one file (what an export hands out); for render style, the whole card |
| `cards/<tag>.json` | each key's value and where it came from (a folder with `[card] merge`: pythia, V59) |
| `cards/<tag>.prepare.<ext>` | the card a prepare step reads, when the tool's `render.py` makes one |
| `config/<tag>.toml` | a custom or module tool's extracted config |
| `logs/<tag>.log`, `logs/<tag>.prepare.log`, `logs/prelim.log` | a failed tool's last 200 lines of stdout and stderr (a failed `[prelim]` command's output); with `--logs`, every tool's whole output (V72) |
| `provenance.json` | `point`, `run`, `project`, `configuration`, `config_file`, `sets`; `values` (each active quantity's index, tag and value); `identity`, `seed`, `threads`, `events`; per tool `tag`, `tool`, `exe`, `exe_sha256`, `version`, `argv`, `ran`, `card`, `card_sha256`, `config`, `result` (exit, seconds, note); `host`, `platform`, `user`, `git` (`revision`, `dirty`), `started`, `finished` |
| `identity.json` | the parts the identity hashes (each tool's card lines, argv, binaries, options; threads, events, groups, prelim, the seed rule), written when the point completes, for `--why` (V57) |
| `.complete` | the point's identity, written **last**; its absence means the point is not done |

**Per configuration** (`output/…/<cfg>/`):

| File | Holds |
|---|---|
| `points.json` | `run`, `project`, `configuration`, `config_file`, `plot_points`, and per point: `name`, `index`, `values` (tag, label, value, swept), `page`, `products` (name → path), `results`, `output`, `identity`, `seed`, `complete`. Every point, even under `--points` |
| `status.jsonl` | only with `--journal` (V72): the run's events as `{"v", "point", "tool", "t", "k", …}`: every status message, plus the runner's own `run` (started, finished with a `verdict`), `point` (started, done / failed / stopped with `cause` and `msg`) and `exit` (`code`, `seconds`) records |
| `plots/[<cell>/][<figure>/]<object>.toml` | each page's document, as Paint reads it, and `<page>.toml.ranges.json` beside it for the other backends |
| `plots/merged.sha256` | what the merged sweep file was built from |
| `plots/derived/`, `plots/merged/<figure>/`, `plots/scan/<figure>/` | the figures' own YODAs and their stamps (03 §7) |

**Beside products:**
- an event producer's **sidecar** `<first output>.json`: App_Pythia's, or `{"written": N, "source":
  "requested"}`, written by the runner for generators that always make what they are asked for;
- a module program's **report** `<output>.json` (`events`, `sum_w`, `sigma_pb`, …), which travels
  with its product when it is renamed.

**Caches:**
- **prepare caches:** `output/<P>/.cache/<tool>/<key>/`, with a `.prepared` stamp once the step
  succeeded and left its marker;
- **card checks:** `output/<P>/.cache/checks/`;
- **reference data converted for Paint:** `output/<P>/.cache/datasets/<name>.root`.

Where everything goes, as a tree, is [06 §14](06_Internals.md#14-where-files-go).
