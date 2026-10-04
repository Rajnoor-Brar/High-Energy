# 03 — Plots and figures

How the pages are made and how to get the ones you want: the plot stage, `[plot]` in practice,
reference data, curves and bands, the style, the seven figure classes, what can be drawn, the
backends, and overlays of any files. Every key is in [04 §11](04_Config_Reference.md#11-plot) and
[04 §12](04_Config_Reference.md#12-the-style); how the stage works inside is
[06 §13](06_Internals.md#13-the-plot-stage-inside).

---

## 1. Objects, figures and pages

Three words carry the whole chapter:

- An **object** is data: a histogram, estimate or scatter in a point's YODA
  (`/ZEUS_2012_I1116258/d01-x01-y01`), one copy per point.
- A **page** is output: one drawn file, a frame with curves, a legend, perhaps a ratio pad.
- A **figure** is a recipe for pages:
  - which objects;
  - how the pages are built (its **class**);
  - what is drawn (its **type**);
  - how it looks (any `[plot]` page key, and a style layer).

  One figure gives a page per `plot_points` cell, and per object when it names a glob.

`[plot].objects` is an **implicit figure**: every object it matches (by default, every 1D and 2D
object) gets its own page. A run that declares no figure draws the analysis's histograms, one page
each per cell, and that is often all you need. Figures are for the pages you want *besides* or
*instead of* those.

```toml
[plot]                                # what every page shares
ratio = true

[plot.figures.eta_algorithms]         # one more page per cell: three objects of each point
class   = "overlay"
objects = ["d02-x01-y01", "d11-x01-y01", "d12-x01-y01"]
labels  = ["$k_{T}$", "anti-$k_{T}$", "SISCone"]
style.ratio.range = [0.8, 1.1]        # any [plot] page key or style key, for these pages only
```

---

## 2. The plot stage

The plot stage runs after the points and the stages, from the **complete** points only. It also
runs on `hep run … --only plot` and on `hep plot CONFIG [CFG]`, which redraw without running
anything. A configuration whose run TOML has no `[plot]` draws nothing.

1. **The sweep in one file.** Every complete point's YODA is merged into
   `results/…/plots/root/<cfg>.root`, with a directory per point and the raw entries. It is rebuilt
   only when a point's YODA changed.
2. **One page document per page**, in `output/…/plots/[<cell>/]<object>.toml`. It holds:
   - the labels from the analysis's Rivet `.plot` file;
   - the `[plot]` values and the page's figure's own;
   - the curves;
   - the mapped data;
   - what the style layers change.
3. **Draw**: Paint on every page, then any other backend on the same documents (§9). A failed page
   is counted, and the run exits 1, but the others are drawn.

The pages go to `results/…/plots/<backend>/[<cell>/]<object>.<fmt>`, with an `index.html` per
backend: a section per cell, each page shown and linked to every format drawn.

**What a page is made of.**
- **Curves:** its curves are the cell's complete points (or combined groups). A point whose YODA
  holds several variants of the object (a swept analysis option) gives one curve per variant,
  labelled `… [R=0.4]`.
- **Curve labels:** a curve's label is the curve quantities' labels joined with `, `, or the run's
  name when nothing is swept.
- **Not pages:** weight variations (`/x[…]`), `/RAW`, `/TMP` and the run counters never get pages.

**Labels.**
- **Where they come from:** titles and axis labels come from the analysis's `.plot` file (our
  plugins' copies in `build/Rivet/`, then Rivet's data directory): `Title` (else `LegendTitle`),
  `XLabel`, `YLabel`, `ZLabel`, `LogX`, `LogY`, `LogZ`, `RatioPlot`, later blocks winning.
- **They are LaTeX**, and Paint draws them through TLatex, with math letters set italic (`$E_T$` →
  `#it{E}_{#it{T}}`).
- **Line breaks:** YODA's macros (`\GeV`, `\TeV`, `\pT`) work in every backend, and `\newline` (or
  `\\`) breaks a title into lines. A `$…$` left open across the break is closed and reopened for
  you.
- **The ratio pad** is labelled `MC/Data` with data, and `Ratio` without.

---

## 3. `[plot]` in practice

```toml
[plot]
backend     = "root"              # "mpl", "yoda", or a list of them; "both" is root and yoda
formats     = ["pdf", "png"]
objects     = ["/photo_eic/d0*"]  # which objects get their own pages (default: every one)
ratio       = true
y_gutter    = 0.5                 # the y axis reaches 1.5 × the largest value; "default": ROOT decides
x_gutter    = "default"           # no x gutter; 0.1 widens x by 10 %
auto_range  = true                # trim x to the filled bins …
range_pad   = 1                   # … keeping one bin either side
void_empty  = true                # blank bins empty in every curve
min_entries = 10                  # blank bins fewer raw entries went into, in any curve
normalise   = "area"              # every curve, and the data, to unit area: compare shapes
title       = "{cell}"            # placeholders cite the points (04 §10)
root_style  = "talk"              # configs/<P>/talk.toml, over the base style
```

**Placeholders.** Every page text may cite the points it is drawn from:
- `{cell}`, the page's `plot_points` values;
- `{q:<quantity>}`, the label of its value;
- what a tool folder gives, such as Rivet's `{opt:NAME}`, an analysis option at the point.

A page text's placeholder must have one value across the page's curves; a curve label's is its own
point's. A cited name the points don't have is refused at plan time.

**`"default"` keeps it as it is.** In `[plot]` it sets nothing, and the drawing tool does what it
does by itself: no gutter, no voiding, the `.plot`'s log axes and ratio. In a figure it is `[plot]`'s
value. A key left out of `[plot]` takes the runner's default from the schema: a missing `y_gutter`
is 0.5. The full table is [04 §11](04_Config_Reference.md#11-plot).

**The order on a page** (load-bearing, inherited from v1): void across the page → align the data to
the MC bins → normalise → auto-range over curves and data → gutters → draw.

---

## 4. Reference data and ratios

```toml
[plot]
ratio = true                              # MC/Data in a ratio pad

[plot.data]
file   = "rivet:ZEUS_2012_I1116258"       # Rivet's own reference data; a bare name is under datasets/
legend = "ZEUS 2012"

[plot.data.map]                           # explicit: never matched by name (L18)
"d01-x01-y01" = "/REF/ZEUS_2012_I1116258/d01-x01-y01"
"d09-x01-y01" = "/REF/ZEUS_2012_I1116258/d09-x01-y01"
```

- **Where the data are drawn:** only on the pages the map names, **aligned** to the MC's bins. They
  are cut to their longest run of bins whose edges line up, or dropped with a warning.
- **Why the map is explicit:** ZEUS's `d08` and `photo_eic`'s `d08` are different observables, so
  the map is never inferred.
- **The ratio pad:** each curve over the data.
- **Without data, or with `use_data = false`** (the table stays but is not drawn), each curve is
  divided by the page's first curve: the first value of its curve axis.

→ `eic`, `zeus_validation`.

---

## 5. Curves: labels, looks and bands

A curve is labelled by its quantities' `labels`, and drawn in the next colour of the style's
palette. A quantity can give each of its values a look of its own, which it keeps on every page:

```toml
[quantities.pdf]
values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 LO"]
styles = [{ colour = "#EE3311" }, { colour = "kBlue+1", line = "dashed", width = 1.5 }]
```

**A band** folds a curve axis into an envelope:

```toml
[plot]
band = ["scale"]          # per value of the other curve axes, one curve (the scale's first value),
                          # with the min–max of all its values shaded around it: the usual scale band
```

The legend entry ends `(scale envelope)`. A band must be a curve axis of the configuration: swept,
not `plot_points`, and not combined. Every backend draws it.

---

## 6. The style

Every ROOT page starts from `utils/Apps/Paint/base.toml`, which gives it rivet-mkhtml's look:
- serif text;
- ticks inside, on all four sides;
- steps with error bars at the bin centres;
- black data points;
- a frameless legend;
- a ratio pad a third of the height.

Edit base.toml to change every page. Over it, key by key:

1. `[plot].root_style`: a style file of the run, under `configs/<P>/`;
2. `[plot.style]`, inline;
3. a figure's `style`, for its pages.

Each layer names **only what it changes**, in base.toml's tables:

```toml
# configs/PhotoProduction/talk.toml       (root_style = "talk")
[page]
dpi = 300                 # PNG resolution; the PDF stays vector
[text]
title  = 12.0             # points
legend = 9.0
[legend]
position = "top-left"     # a corner, "best", or [x, y]: its top-right corner, in fractions of the frame
[curves]
errors = "band"
```

- **Misspelt keys:** an unknown key, or a value of another kind, is refused at plan time, with the
  nearest spelling.
- **Seeing the merged style:** `build/Paint.exe <page>.toml --dump-style` prints a page's whole
  style; the page documents are in `output/…/plots/`.
- **The reference:** every key and its default is [04 §12](04_Config_Reference.md#12-the-style).
- **Ratio ticks:** denser or sparser ratio-pad ticks are `ratio = { divisions = 508 }` (0.2 apart)
  or `515`.

---

## 7. Figures

### 7.1 Declaring a figure

```toml
[plot.figures.tails]          # the figure's key
class   = "defined"           # how its pages are built (the default)
type    = "Hist1D"            # what is drawn; left out, from the objects
# name  = "…"                 # its pages' file stem, default the key (an overlay's page, a merged figure's folder)
objects = ["d04-*"]           # globs: the short name, the option-free path, or a variant's path
# any [plot] page key, x_label, y_label, and style.<…>: for these pages only
```

**What a figure inherits.** A figure takes **every page key of `[plot]`**:
- the titles and `legend_header`;
- `logx`, `logy`, `logz`;
- the gutters;
- `ratio`, `normalise`, `auto_range`, `range_pad`, `void_empty`, `min_entries`;
- `use_data`, `band`.

It also takes `x_label`, `y_label` and `style`. Each means what it means in `[plot]`, for the
figure's pages only; left out, or `"default"`, it is `[plot]`'s. What concerns the whole run stays
in `[plot]` alone: `backend`, `formats`, `objects`, `data`, `root_style`.

**When it is checked.** A figure is checked twice:
- **when the file is read:** its class's keys, and the keys it may not take;
- **at plan time:** the axes it names, and the configurations it compares.

A glob that matches no object of the points is refused at the plot stage. The old
`[plot.overlay.<name>]` and `[plot.object."<glob>"]` tables are refused with the figure to write,
and `hep migrate` rewrites them.

| Class | Built from | Pages |
|---|---|---|
| `defined` | an analysis object | `<cell>/<object>` |
| `overlay` | several objects of each point | `<cell>/<name>` |
| `merged` | the points merged over an axis, for this figure only | `<cell>/<name>/<object>` |
| `compare` | the same objects across configurations, of this or other run TOMLs | `<run>/compare/<name>/<cell>/<object>` |
| `derived` | a new object per point: a ratio, difference, sum or projection | `<cell>/<name>` |
| `scan` | one number per point against a swept quantity | `<cell>/<name>` |
| `sheet` | drawn pages, tiled in a grid | `plots/<backend>/sheets/<name>` |

### 7.2 `defined`: an object's own pages

```toml
[plot.figures.tails]
objects  = ["d04-*"]
logy     = true
y_gutter = 2.0
style.legend.position = "bottom-left"
```

The objects' own pages, with this figure's keys. A defined figure **takes over** the pages of the
objects it matches, also those `[plot].objects` leaves out. Two declared defined figures that match
the same object are refused: there is one recipe per page, so narrow a glob, and put what every page
shares in `[plot]`. A defined figure takes no `labels` or `name`: its pages are the objects' own.

### 7.3 `overlay`: several objects on one page

```toml
[plot.figures.eta_algorithms]
class   = "overlay"
objects = ["d02-x01-y01", "d11-x01-y01", "d12-x01-y01"]
labels  = ["$k_{T}$", "anti-$k_{T}$", "SISCone"]
style.ratio.range = [0.8, 1.1]
```

One page per cell, `<cell>/eta_algorithms`, with a curve per object and point:
- **labels:** each curve is labelled by `labels` (default: the objects' names), followed by the
  point's own label when the page has several points;
- **the ratio:** it divides by the first curve;
- **a band:** it folds the points into each object's envelope.

The page's titles are the first object's. Objects must be 1D.

### 7.4 `merged`: points merged for this figure

```toml
[plot.figures.avg]
class   = "merged"
objects = ["d01-*", "d05-*"]
over    = ["replica"]            # curve axes merged away
title   = "five seeds merged"
```

The objects' pages, under the figure's folder (`<cell>/avg/<object>`). For each value of the other
curve axes, the points' YODAs are merged by the combine folder's command (`rivet-merge -e`:
statistics add, σ averaged). That happens once per change of a member's YODA, into
`output/…/plots/merged/avg/`.

The run keeps its points apart, and only this figure merges them; `combine` merges them for the
whole configuration ([02 §7.3](02_User_Guide.md#73-replicas-merged)). `over` must name curve axes,
and the figure may not also `band` them.

### 7.5 `compare`: configurations side by side

```toml
[plot.figures.statistics]
class          = "compare"
objects        = ["d0*"]
configurations = ["default01", "default1", "default4"]   # default: the sweep_runs ones
labels         = ["1M", "10M", "40M"]                    # default: each configuration's label

[plot.figures.chains]
class          = "compare"
objects        = ["d01-*"]
configurations = ["default", "PhotoProduction/InProcZeus:default"]   # another run TOML's
```

**The pages.** These are the objects' pages across configurations, in this run's
`compare/<name>/<cell>/<object>`, a folder per backend. Each curve is a configuration and a point (or
a combined group), labelled by the configuration first, then the point's curve axes.

**What it needs.**
- **Configurations:** two or more, and at least one of this file. They must have the same page and
  curve axes, which is checked at plan time.
- **Another run TOML:** `"<Project>/<config>:<cfg>"` names a configuration of it. Its points are
  read as its last run left them, labelled `<its run> <its label>` by default, and by its own
  quantities. Its page axes must have this run's tags.

**When it is drawn.** It is drawn by the plot stage of each of this file's configurations it names,
once every configuration has complete points; until then the stage says what it waits for.
`hep plot` draws it too.

### 7.6 `derived`: a new object per point

```toml
[plot.figures.r15]
class   = "derived"
op      = "ratio"                         # ratio, difference, sum (two objects); projection-x, -y (one 2D)
objects = ["d01-x01-y01", "d05-x01-y01"]
y_label = "d01 / d05"
ratio   = false
```

**The new object.** It is `/FIGURES/<name>` in every point, and `/FIGURES:R=0.4/<name>` per
analysis-option variant.
- **The ops:**
  - `ratio`, `difference` and `sum` of its two objects (histograms made estimates first), on the
    same binning, else refused naming both;
  - `projection-x` and `projection-y` of one 2D object: summed over the other axis, as a Scatter2D
    whose x ranges are the bins.
- **Where it is written:** it is appended to a copy of each point's YODA
  (`output/…/plots/derived/`), remade when the product or the figures change, by
  `utils/Env/figures/derive.py` with YODA's Python (`load_hep`).

**Using it.** It is then an object like any other:
- its pages are `<cell>/r15`;
- its labels are its first object's `.plot` ones (set `y_label`);
- an overlay, merged or compare figure may name it (`"r15"`).

### 7.7 `scan`: one number per point

```toml
[plot.figures.sigma_vs_pt0]
class = "scan"
x     = "pt0ref"                  # a curve axis whose values are numbers
y     = "sigma"                   # sigma, entries, integral, mean, bin:N
# objects = ["d01-x01-y01"]       # integral, mean, bin:N read one object; entries may name one
```

**What it reads.** One number per point, against `x`:
- `sigma`: the point's `/_XSEC`;
- `entries`: its events, or its object's raw entries;
- `integral`, `mean` and `bin:N`: of its one object.

**The pages.** A page per cell, `<cell>/<name>`, with a curve per value of the other curve axes. Each
curve is a Scatter2D: a point per `x` value, with an x range halfway to its neighbours, centred on
it. So every backend can draw it as a bin; it is drawn as markers. The axis titles are the
quantity's name and the number read, until you set `x_label` and `y_label`.

**The limits.** `x` cannot be a page axis, nor banded. A quantity of names (PDF sets) cannot be an
`x` yet.

### 7.8 `sheet`: drawn pages in a grid

```toml
[plot.figures.paper_fig3]
class   = "sheet"
pages   = ["18x275/d02-x01-y01", "18x275/eta_algorithms", "*/r15"]   # globs of page names, in order
columns = 3                                                         # default: up to 3
```

- **What it makes:** after the configuration's pages are drawn, the pages the globs name are tiled
  `columns` wide into `plots/<backend>/sheets/<name>.pdf` and `.png`. Each pad is its page exactly
  as it was drawn alone:
  - pdflatex places the PDFs, as vectors;
  - PIL pastes the PNGs.
- **Which backends:** Paint's and mpl's pages.
- **What it takes:** a sheet takes no page keys; its pages' figures set those.
- **When it fails:** a glob that names no page fails the sheet.
- **Its limits:** it has no shared y title or legend, and it does not take compare figures' pages.

---

## 8. Types: Hist1D, Scatter2D, HeatMap

| `type` | Drawn as | Default for |
|---|---|---|
| `Hist1D` | steps per curve, error bars at the bin centres (or a band, or none: `curves.errors`) | a 1D object |
| `Scatter2D` | a marker per bin at its centre with its error bar, in the curve's colour (`data.marker`, `data.marker_size`), as Paint draws data; the legend shows the marker | a scan |
| `HeatMap` | one 2D object coloured by value, its scale on the right (`z_label`, `logz`: from the `.plot`'s `ZLabel` and `LogZ`) | a 2D object (`Histo2D`, `Estimate2D`) |

**Scatter2D on other backends.** For a Scatter2D page, the page document says `markers = true`, and
mkhtml and mpl draw its curves as they draw points (`ConnectBins=0`, with their x bars).

**HeatMap pages.** A heat map is drawn per point of the cell, as `<cell>/<object>/<point>`. It has
no ratio, data, voiding or range. **Paint alone draws heat maps**: mkhtml and mpl draw the 1D pages,
and the plot stage says so.

**What is refused:** a 1D object as a HeatMap, a 2D object as a Hist1D or Scatter2D, and a 2D object
in an overlay. To see a 2D object in 1D, project it with a derived figure.

---

## 9. Backends

| `backend =` | Draws with | Pages in | Honours |
|---|---|---|---|
| `"root"` (default) | `build/Paint.exe`, up to 200 pages per process | `plots/root/` | every `[plot]` key, every figure and type, the whole style |
| `"mpl"` | matplotlib in this process, a pool of workers (`utils/Env/mpl/backend.py`, V71) | `plots/mpl/` + `index.html` | **mkhtml's pages, pixel for pixel** (until the user has verified it), about 18× faster than mkhtml; 1D pages only |
| `"yoda"` | `rivet-mkhtml`, one call per page set (`utils/Env/yoda/backend.py`) | `plots/yoda/[<cell>/]<analysis>/<object>.{pdf,png}` + `index.html` | the same pages with Paint's ranges and voids; frozen (V71) |
| `["root", "mpl"]`, `"both"` | each, from the same page documents | each tree | as each; `"both"` is root and yoda |

**What the other backends honour.** They draw the same page documents with the ranges and voided
bins Paint computed, so every backend shows the same window. They keep mkhtml's look, so only these
carry over:
- a `legend.position` corner (or `best`);
- `text.legend`;
- `text.header`;
- `ratio.divisions`;
- `ratio.range` with `ratio.limits`.

**What is refused.** Alone, they refuse `root_style` and every other style key. Beside the root
backend those are Paint's to honour, and are allowed. A legend at `[x, y]` is still refused, because
the two page sets would disagree about it.

**How the yoda backend draws.** It writes per page set:
- copies of the point YODAs, with the voided bins blanked;
- `reference.yoda`: the mapped reference objects cut to their aligned span, renamed
  `/REF/<analysis>/<object>` (mkhtml's own reference lookup is off: explicit only, L18);
- `pages.plot`, which per object holds:
  - `XMin`/`XMax`/`YMin`/`YMax` (left out where a gutter of `"default"` leaves the range to the
    tool);
  - `LogX`, `LogY`, `RatioPlot`;
  - the legend corner;
  - label overrides.

It then runs `rivet-mkhtml --no-rivet-refs -o <dir> -c pages.plot <yodas…> [reference.yoda
--reflabel …]`, with `-f SVG`/`-f EPS` for those formats. Last, it writes `ratio.divisions`' locators
into each page's script just before it saves, and runs the script again: YODA's generator has no key
for the ratio pad's ticks.

**How the mpl backend draws.** It draws the pages mkhtml would, without mkhtml:
- rivet's `get_plot_configs` reads the `.plot` files and the yoda backend's block for the page;
- the yoda backend's transforms (void, normalise, envelope, the cut reference) run in memory;
- YODA's own helpers give every number, with its `default.mplstyle`;
- mkhtml's generated script's calls are made directly, with the yoda backend's fixes applied before
  saving.

`tests/integration/test_plot_stage.py` checks every page and overlay PNG against mkhtml's, pixel for
pixel.

Writing a backend is [06 §18](06_Internals.md#18-adding-a-plot-backend).

---

## 10. Any files, overlaid: `hep overlay`

```bash
hep overlay a.yoda b.yoda --labels "Tune A,Tune B" --ratio --objects "/MC_JETS/*"
hep overlay results/PhotoProduction/eic/01_pdf/plots/root/pdf.root      # a sweep: a curve per point
```

**No run TOML is needed.** You get one page per object any file holds, with one curve per file, or
one per point of a merged sweep file, labelled from its `points.json`.

**Options:**
- `-o DIR`: where the pages go (default `results/plots/<first file>/`);
- `--formats pdf,png`;
- `--style FILE`: a style file over base.toml.

The pages are Paint's, with an `index.html` beside them. The options are in
[05 §1.2](05_Commands_and_Tools.md#12-hep-plot-and-hep-overlay).
