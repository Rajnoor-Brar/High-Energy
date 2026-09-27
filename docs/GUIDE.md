# Guide

How to use the framework. The design and its reasons are in [rework_v2/](rework_v2/README.md);
this page covers only what you type and where things end up.

## 1. Set up and build

```bash
load_hep            # or: source ~/HEP/setup.sh — the ~/HEP stack, the venv, `hep` on PATH
hep build           # every app, module program and Rivet plugin (make all)
```

`hep build --tests` also builds the C++ tests, `--configure` probes the toolchain again (after
installing a library), and `--clean` empties `build/` first.

To compile a single source, `make` it by its path. The output lands where the convention says:

| Source | Output |
|---|---|
| `utils/App_<X>.cc` | `build/App_<X>.exe` |
| `utils/Apps/<X>/main.cc` (`make utils/Apps/<X>.exe`) | `build/<X>.exe` |
| `modules/<P>/<X>.cc` | `build/<P>/<X>.exe` |
| `modules/<P>/Rivet/<x>.cc` or `modules/<P>/Rivet_<x>.cc` (`make ….so`) | `build/Rivet/Rivet_<x>.so`, with its `.info`/`.plot`/`.yoda` copied beside it |

A source names its libraries in one line near the top, for example
`// requires: pythia8 hepmc3 fastjet` (known: pythia8 hepmc3 yoda root fastjet lhapdf rivet geant4 toml zstd
zlib onnx delphes). A Geant4 simulation is such a program: `// requires: geant4`, run as `tool = "module"`. A folder or file whose name starts with `_` is parked, and
`make all` never builds it.

## 2. Where things are

| Path | What |
|---|---|
| `configs/<P>/` | run TOMLs and native base cards (`photo_ep.cmnd`, …) |
| `modules/<P>/` | your C++: programs, and Rivet analyses under `Rivet/` or as `Rivet_*.cc` |
| `datasets/` | your own reference data (not in git); Rivet's are named `rivet:<Analysis>` |
| `output/<P>/<run>/<cfg>/<point>/` | technical files: `cards/`, `config/`, `logs/<tool>.log`, FIFOs, `provenance.json`, `.complete` |
| `results/<P>/<run>/<cfg>/<point>/` | the products only (`photo.yoda`, `photo.root`) |
| `results/<P>/<run>/<cfg>/plots/root/` | the ROOT pages (`<cell>/<object>.pdf`) and `<cfg>.root`, the whole sweep in one file |
| `results/<P>/<run>/<cfg>/plots/yoda/` | the pages of `backend = "yoda"` (rivet-mkhtml) |
| `results/<P>/<run>/<cfg>/pre/`, `…/post/` | the products of the pre and post tools |
| `build/` | everything compiled |
| `utils/Env/` | the `hep` command, the runner, and one folder per standard tool |

`<run>` and `<cfg>` get a `NN_` prefix when they have a `serial`. A point is named by the tags of
its swept values (`27x920_MSTW08lo`).

## 3. Run

```bash
hep run PhotoProduction/eic                      # the configuration named in [run]
hep run PhotoProduction/eic energy_pdf --plan    # points, cards, argv and connections; runs nothing
hep run PhotoProduction/eic energy_pdf           # run it
hep watch                                        # from another terminal: the live view of the latest job
hep plot PhotoProduction/eic energy_pdf          # redraw its pages (as after a run)
hep plot a.yoda b.yoda --labels A,B --ratio      # overlay any YODA/ROOT files, no run TOML
```

Each point prints one block when it ends:

```
── point 2/4: NNPDF23lo ── ok after 71.8 s
   done → results/PhotoProduction/zeus/default/NNPDF23lo
```

A failed point's block names the tool to blame, with its exit and message.

| Option | Does |
|---|---|
| `--plan` | print the plan, with each point's state (complete / to run) |
| `--points 27x920_MSTW08lo,pdf=NNPDF23lo,3` | run a subset: point names, `quantity=tag` or indices |
| `--set run.event_count=50000` | override one value for this invocation (dotted keys, repeatable) |
| `--rerun` | run complete points again |
| `--only plot` / `--only pre` / `--only post` | redraw the pages, or rerun the pre or post tools, and nothing else |
| `--plain` | plain lines instead of the live view |

A point that is complete with the same identity is skipped, so a second `hep run` does nothing.
Slow preparation (Sherpa's integration, Herwig's read) is cached by card under `output/<P>/.cache/`:
a rerun, a replica or another event count reuses it.
The identity covers cards, argv, binaries, analyses, events and threads, and the seeds are derived
from it. Change anything and the points it affects run again.

`hep run ./path/to/file.toml` takes a path from the repository root instead of `configs/`.

## 4. A run TOML

```toml
[run]
name          = "eic"
project       = "PhotoProduction"
configuration = "pdf"             # the default one
event_count   = 1_000_000
threads       = 20

[run.pdf]                         # a configuration
sweeps      = ["pdf"]             # a string is an axis; ["a", "b"] move together (value i with value i)
plot_points = []                  # quantities that split pages; the other swept ones become curves
tools       = [["pythia", "rivet"], "yd2rt"]   # an inner list runs together (FIFO); groups run in order
pre         = []                  # tools run once, before every point (their products: inputs of every point)
post        = []                  # tools run once, after every point
static      = { energies = "18x275" }          # this configuration's fixed values

[prelim]
fifo = ["events.hepmc"]           # interfaces made before the tools start (per point)

[static]                          # values used when a quantity is not swept
energies = "27x920"
pdf      = "NNPDF23lo"

[tools.pythia]
tool        = "pythia"
baseconfig  = "photo_ep.cmnd"     # → configs/<P>/photo_ep.cmnd
output_file = "events.hepmc"

[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["photo_eic"]
output_file = "photo.yoda"        # not in [prelim]: a product, under results/

[quantities.pdf]
values = ["MSTW2008lo68cl", "NNPDF23_lo_as_0130_qed"]
tags   = ["MSTW08lo", "NNPDF23lo"]          # names in paths and on the command line
labels = ["MSTW 2008 LO", "NNPDF 2.3 LO"]   # legend text (TLatex)
```

**Quantities** reach tools in one of three ways:
- through `utils/Env/master.toml`, which knows that `pdf` is Pythia's `PDF:pSet` and `energies` is
  `Beams:eA`/`Beams:eB`;
- with `key = { pythia = "MultipartonInteractions:pT0Ref" }`;
- with `target = "rivet/photo_eic"` and `key = "R"`, which sets an analysis option.

A quantity that is set but that no tool in the chain consumes is refused. So is a Rivet option the
analysis's `.info` does not declare, and a PDF set that is not installed.

**Replicas** are a quantity that targets the seed: `target = "pythia/seed"`, `values = [1, 2, 3]`.

**Paths.** A bare name goes under the convention root for its key (`baseconfig` under `configs/<P>/`,
`executable` under `build/<P>/`, `[plot.data].file` under `datasets/`). `./x` is from the repository
root, and `/x` is absolute.

The complete schema, the validation rules, and translated examples are in
[rework_v2/04_Config.md](rework_v2/04_Config.md).

## 5. Tools

| `tool =` | What | Notes |
|---|---|---|
| `pythia` | `build/App_Pythia.exe`: `.cmnd` cards → HepMC3 | the seeds are written into the card; σ is combined over threads |
| `rivet` | `rivet` reading HepMC | `analyses`, `options`; its YODA's event count is checked against Pythia's |
| `yd2rt` | `build/App_yd2rt.exe`: YODA → ROOT | `select = ["/photo_eic/*"]`; the ROOT file is a product |
| `merge` | `rivet-merge` over one product of every point | post only: `input = "photo.yoda"`; `equivalent = false` sums different processes |
| `plotmerge` | one file for the sweep: every point's YODA, each in its own directory | post only: `input = "photo.yoda"`, `output_file = "sweep.root"` (or `.yoda`) |
| `module` | a `utils/Module.hh` program, `build/<P>/<X>.exe` | its `[config]`, `--input`/`--output`; count-checked from its report |
| `delphes` | `DelphesHepMC3` with a Tcl card | reads a **file** from an earlier group (never a FIFO); counted from the `Delphes` tree |
| `sherpa` | Sherpa 3 with a YAML card | the integration is cached per card (`output/<P>/.cache/sherpa/`) |
| `herwig` | Herwig 7 | `Herwig read` is cached per card; needs `hep build` for its repository |
| `whizard` | Whizard 3 with a SINDARIN card | the integration is cached; direct photoproduction only (no resolved photon) |
| `madgraph` | MadGraph5_aMC@NLO | the process directory is built once per proc card; shower the LHE with a `pythia` table (`Beams:frameType = 4`) |
| `custom` | any executable | `executable`, `arguments`, `[tools.<tag>.config]` |

A **custom tool** gets `output/…/config/<tag>.toml` as its first argument. It holds its
`[tools.<tag>.config]`, the quantities it consumes, and, if it asks with `pythia_cmnd = true` or
`rivet_analyses = true`, the rendered configuration of those standard tools under
`[standard.<key>]`. It also takes placeholders in `arguments`:
- `{output}` and `{partial:output}`;
- `{input}` and `{inputs}`;
- `{out}` and `{res}`, the point's directories;
- `{q:<quantity>}`;
- `{std:<tool>_<export>}`;
- in `pre` and `post`, `{points}`, the path of `points.json`; in `post`, `{named_inputs}` (`point=path`).

A tool that writes `output_file` as a product should write it to `{partial:output}`. The runner
renames it after the checks pass.

**Pre tools** run once, before the first point (a download, a shared build). What they write is an
input every point may name (`input = "shared.lhe"`), and a changed pre stage reruns the points. A
failed pre stage stops the run.

**Post tools** run once, after every point is complete. An `input` naming a product of the points
(`input = "photo.yoda"`) reads that product from every point, and `{inputs}` splices those paths
into argv. `points.json` has every point's values, tags, labels and product paths.

## 6. Plots

Pages are drawn after the points, one per `plot_points` cell and histogram. The sweep is first
merged into one ROOT file, `results/…/plots/root/<cfg>.root` (a directory per point, the raw entries
and `points.json` inside), and the pages are drawn from it to `results/…/plots/root/<cell>/<object>.pdf`
(no `<cell>/` when nothing splits the pages).

`hep plot FILE…` draws the same kind of pages from any files: YODA files (one curve each), ROOT files
from `yd2rt`, or a merged sweep (one curve per point, labelled by its swept values). Options:
`-o DIR` (default `results/plots/<first file>`), `--labels A,B`, `--objects GLOB…`, `--formats`,
`--ratio`, `--style FILE`.

```toml
[plot]
formats     = ["pdf", "png"]      # pdf, png, svg, eps
ratio       = true                # a ratio panel: against the data if drawn, else the first curve
y_gutter    = 1.5                 # the y axis reaches 1.5 × the largest value drawn
x_gutter    = 1.0
auto_range  = true                # trim x to the filled bins (range_pad whole bins either side)
min_entries = 1                   # void bins fewer raw entries went into, across all curves
objects     = ["/photo_eic/d0*"]  # which histograms get pages (default: every 1D object)
root_style  = "talk.toml"         # a style file over the base style (configs/<Project>/talk.toml)

[plot.data]                       # reference data: drawn only where the map says
file = "rivet:ZEUS_2012_I1116258"   # Rivet's own reference data; a bare name is under datasets/
map  = { "d01-x01-y01" = "/REF/ZEUS_2012_I1116258/d01-x01-y01" }

[plot.style]                      # the style, inline: over root_style
page.dpi        = 300
legend.position = "top-left"

[plot.object."d04-*"]             # per-object overrides: title, x_label, y_label, logx, logy, style
logy = true
style.legend.position = "bottom-left"
```

Titles and axis labels come from the analysis's Rivet `.plot` file, translated to ROOT's TLatex.
The default backend is ROOT, drawn by `build/Paint.exe` from one page config per page, which you can
find in `output/…/plots/`. `backend = "yoda"` draws the same pages with the same ranges using
`rivet-mkhtml`, one HTML page set per cell, in `results/…/plots/yoda/`. A key a backend cannot
honour is an error, not ignored.

**The style.** Every ROOT page starts from `utils/Apps/Paint/base.toml`: rivet-mkhtml's look, with
every key commented. Edit it to change all pages:
- the page size and PNG dpi;
- the font and the text sizes (in points);
- the palette, line width and error style;
- the data markers, ticks and axis titles;
- the legend's position and spacing;
- the ratio pad.

For one run, name only the keys you change: in a style file (`root_style`), in `[plot.style]`,
or per object in `[plot.object."<glob>"].style`, later layers winning. A misspelt key is an error
at plan time. `build/Paint.exe PAGE.toml --dump-style` prints a page's whole style.

## 7. When a point fails

The run goes on to the next point, and the summary names the tool to blame. Then:

1. Read `output/…/<point>/logs/<tool>.log`, and the verdict line of the run.
2. A product that did not pass its checks keeps its `.partial` name, and the point has no
   `output/…/<point>/.complete`, so it will run again.
3. "rivet analysed N events; the producer wrote M" means the chain broke mid-stream. Look at the
   generator's log first.
4. Fix it, then `hep run … --points <that point>`. The complete points are skipped anyway.
5. `hep run … --plan` shows the exact argv and cards, and `output/…/<cfg>/status.jsonl` is the
   job's full event journal.

Ctrl-C stops the job cleanly: the running tools get SIGTERM, then SIGKILL. Exit codes are 0 for
done, 1 when a point or page failed, 2 for a config error, and 6 when stopped.

## 8. Tests

```bash
make test           # C++ tests, then pytest (fast)
make test-slow      # the physics gates and failure injection (real processes, minutes)
```

Tests write only under `output/tests/`, and a guard fails the run if anything under `results/` or
`configs/` changes.
