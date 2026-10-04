# 08 — Figures: one recipe table, six ways to build a page

## Context

The user wants anything `[plot]` sets on a page to be overridable per figure. They cited `eic.toml:282-286`, an overlay with its own ratio range. Asked which figure kinds hep supports "by origin or construction", they asked to discuss figures before building more. Today there are only two kinds:
- the implicit per-object pages;
- `[plot.overlay.<name>]`.

`[plot.object."<glob>"]` only tunes pages that already exist. The user's configs reach for figures that can't be written:
- **across configurations:** zeus `default01…default4` and eic `ener0…ener3` differ only in `event_count`;
- **scans:** lambda's "Λ yield against collision energy", eic `pthatmin`;
- **object arithmetic:** the `eta_algorithms` algorithms against one another;
- **2D objects**, which never get pages.

**Terms (as agreed):**
- **objects** are the data: a histogram in a point's YODA;
- **pages** are the output: one drawn file;
- **figures** are the recipes. One figure gives a page per `plot_points` cell, and per object when it names a glob.

**The user's decisions (2026-10-04):**
- `[plot]` holds the options. `[plot.figures.<figure>]` declares figures, and each figure inherits every page option from `[plot]` unless it overrides it, `style.*` included. This is one table family, not one per kind.
- A figure has:
  - **`class`**: how it is built. `defined | overlay | compare | scan | derived | merged`, all six.
  - **`type`**: what is drawn. `Hist1D | Scatter2D | HeatMap`, inferred from the objects unless set.
  - **`name`**: the pages' file stem.
- `[plot].objects` stays an **implicit `defined` figure**, so a run with no figures draws what it draws today. A declared `defined` figure takes over the pages of the objects it matches, with no duplicates.
- The uncommitted per-figure override work is folded into F0. That work covers:
  - `page = true` in `schema/run.toml`;
  - the child keys derived in `schema.keys("plot_child")`;
  - `override_of` and `chosen` in `plot.py`;
  - per-figure `use_data`, `band` and the range keys;
  - bands on overlays;
  - 2 tests.

## The design

**One principle:** a figure only **constructs YODA objects and chooses curves**. Drawing stays one path: a page TOML, then Paint, yoda or mpl. Every class therefore gets ratio, bands, data, styles, placeholders, overrides and all three backends for free. Only the `HeatMap` type needs new drawing code.

```toml
[plot]                                # every page key, for every figure
ratio = true
[plot.style]
legend.position = "best"

[plot.figures.eta_algorithms]
class   = "overlay"                   # default "defined"
objects = ["d02-x01-y01", "d11-x01-y01", "d12-x01-y01"]
labels  = ['$k_{T}$', 'anti-$k_{T}$', "SISCone"]
style.ratio.range = [0.8, 1.1]        # any [plot] key or style key, for these pages only

[plot.figures.statistics]
class          = "compare"
objects        = ["d0*"]
configurations = ["default01", "default0", "default1", "default2", "default3", "default4"]
```

| class | built from | per-class keys | pages |
|---|---|---|---|
| `defined` | an analysis object, per cell | `objects` (globs) | `<cell>/<object>`, as today |
| `overlay` | several objects of each point | `objects`, `labels` | `<cell>/<name>` |
| `merged` | points merged over an axis, for this figure only (e.g. replicas), while the run keeps them apart | `objects`, `over = ["replica"]` | `<cell>/<name>/<object>` |
| `compare` | the same objects across configurations; a curve is configuration × curve axes, labelled by the configuration's `label` | `objects`, `configurations` (default: the `sweep_runs` members) | `results/<P>/<run>/compare/<name>/…` |
| `derived` | arithmetic per point: `op = "ratio" \| "difference" \| "sum" \| "projection-x" \| "projection-y"` | `objects = [a, b]` | `<cell>/<name>` |
| `scan` | one number per point against a swept quantity: `y = "sigma" \| "integral" \| "mean" \| "bin:N" \| "entries"` of an object or the run counters | `x = "<quantity>"`, `y`, `objects` | `<cell>/<name>` |

- **`type`:**
  - inferred: 1D objects → `Hist1D`, 2D → `HeatMap`, `scan` → `Scatter2D`;
  - setting it changes how the curves are drawn: `Scatter2D` is markers without bin bars.
- **Validation at plan time (`hep check`):**
  - unknown classes or types;
  - a missing per-class key;
  - globs that match nothing;
  - `compare` naming an unknown configuration;
  - `scan`'s `x` not being a curve axis;
  - two declared `defined` figures matching the same object. One recipe per page; shared settings belong in `[plot]`.
- **Break and migrate:**
  - `[plot.overlay.X]` → `[plot.figures.X] class = "overlay"`;
  - `[plot.object."g"]` → `[plot.figures.<slug>] objects = ["g"]`.

  The old tables are refused with a hint. `hep migrate` rewrites them, and the user's `configs/` are migrated only on their order.

## Phases (2 steps each; each step is its own commit with tests, docs/04 rows and a V-entry)



**F0: the model**
- **S1: `[plot.figures]`, `defined` and `overlay`.**
  - Fold in the pending override work.
  - Add a `Figure` dataclass and `figures(run)` (the implicit figure plus the declared ones) in `utils/Env/runner/plot.py`.
  - `pages()` loops over figures instead of objects and then overlays, and reuses `override_of`, `chosen`, `page_settings` and `_banded`.
  - Schema: a `figure` table in `utils/Env/schema/run.toml` (from `plot_child` and `overlay`), with `class`, `type` and `name`. `schema.py` and `config.check_plot` change to match.
  - Update `check_texts` and `check_band`, and regenerate `run.schema.json`.
- **S2: migrate and docs.**
  - `runner/migrate.py` rewrites `[plot.object]` and `[plot.overlay]`. `config.load(strict=)` refuses them with a hint.
  - Rewrite docs/04 §11 (objects, pages, figures).
  - Migrate the fixtures; `hep migrate` is offered for `configs/`.

**F1: across points and configurations**
- **S1: `merged`.** Points merged over `over`, through the combine folder: reuse `post._combiner()` and its merge command. The result is cached by a sha stamp, as `plot.merge()` does. The merged YODAs join the configuration's ROOT as synthetic points.
- **S2: `compare`.**
  - The curves come from several configurations' merged ROOTs.
  - The figure is drawn by the plot stage of the last configuration it names (under `sweep_runs`), or by `hep plot`.
  - Pages go to `results/<P>/<run>/compare/<name>/<backend>/`.
  - Configurations with incomplete points are left out, with a warning.

**F2: constructed objects**
- **S1: `derived`.** Python `yoda` arithmetic per point writes `<point out>/figures.yoda` with objects `/FIGURES/<name>`. `plot.merge()` takes it as well, so the result is an ordinary object: it gets pages, overlays and bands.
- **S2: `scan`.**
  - One `Estimate1D` per remaining curve axis.
  - The numbers come from the point's YODA: `/_XSEC`, `_EVTCOUNT`, and an object's integral, mean or bin, using `hepfiles` helpers.
  - A quantity with numeric values gets a numeric x axis. A non-numeric one (e.g. PDFs) gets one bin per value, labelled by the quantity's labels. Paint learns bin labels.

**F3: types**
- **S1: `Scatter2D`.** A curve's look gains `markers` without x bars. It applies in Paint, mpl and yoda.
- **S2: `HeatMap`.**
  - 2D objects stop being skipped (`hepfiles.objects` by type).
  - Paint draws a `TH2` as COLZ; `App_yd2rt` already converts `Histo2D` and `Estimate2D` → `TH2D`.
  - mpl uses `yoda.plotting`'s `mkPlottingScript2D`, and mkhtml draws them itself.
  - A `HeatMap` page has no ratio pad and no curves to overlay. A figure that asks for those is refused.

**F4: layout (a design note first, as B4c was):** a grid of pads (cells or figures on one sheet), and `compare` across run TOMLs. The user decides after the note.

## Verification

- Each step:
  - `make test` passes (the fast suite);
  - a fixture config per class in `tests/fixtures/configs/` runs in the slow suite (one pytest session at a time, never writing to `results/` or `configs/`);
  - `hep check` refuses bad figures before any point runs.
- F0:
  - with no figures declared, the user's pages come out byte-identical to today's (the same page TOMLs);
  - `hep migrate` produces valid TOML from `eic.toml`;
  - `hep check` passes on all the migrated configs.
- F3: pixel parity between Paint and mpl on one page per type.
- Commits stay local, with the attribution line. The configs are migrated only on the user's order and left uncommitted.

## Progress

| Phase | Steps | State |
|---|---|---|
| F0 | S1 S2 | S1 (V80: `[plot.figures]`, defined and overlay, every page key per figure), S2 (V81: the old tables refused, `hep migrate` rewrites them) done: F0 complete |
| F1 | S1 S2 | S1 (V82: `merged`), S2 (V83: `compare`) done: F1 complete |
| F2 | S1 S2 | S1 (V84: `derived`), S2 (V85: `scan`, numeric x; named x waits for a categorical axis) done: F2 complete |
| F3 | S1 S2 | S1 (V86: `Scatter2D`, markers), S2 (V87: `HeatMap`, Paint's; mpl and mkhtml draw 1D pages only) done: F3 complete |
| F4 | note | |
