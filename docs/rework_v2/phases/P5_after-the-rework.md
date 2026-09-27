# P5 — After the rework: the user's additions

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| **done** | 1 | P4 | markers in output/, plots/root and plots/yoda, one line per point, a pre stage, the sweep in one file, `hep plot` | 2026-09-27 |

## Goal

The user's requests after P4 (2026-09-27):

- "an option for a post/pre sweep tool call": `post` existed (V15); `pre` is new.
- "a tool (plotmerge) that merges yoda/root files from a sweep into singular file".
- "an hep plot option (hep plot config) to merge and emit outputs to auto link paint.exe".
- "files like .complete and provenance.json be in outputs".
- "plots/yoda be for yoda outputs, plots/root/ for root emitted png/pdfs".
- A finished point is one block: `── point 2/4: NNPDF23lo ── ok after 71.8 s`, then `done → …`.

## S1 — Everything above

| # | Row | Expect |
|---|---|---|
| 1 | `hep run PhotoProduction/eic pdf` | one block per point; `results/<point>/` holds the products only; `.complete` and `provenance.json` are in `output/<point>/` |
| 2 | its plot stage | `results/…/plots/root/pdf.root` (a directory per point, `points.json` inside), and the pages drawn from it into `plots/root/` |
| 3 | `hep plot` on that file | one curve per point, labelled by the swept values |
| 4 | `hep plot a.yoda b.yoda` | one page per object, a curve per file, no run TOML |
| 5 | a `plotmerge` post tool | one ROOT (or YODA) file with every point |
| 6 | a `pre` tool | its product is an input of every point; a changed pre reruns them; a failure stops the run |

## Log

### S1 — 2026-09-27 — done

| Row | Result |
|---|---|
| 1 | eic `pdf`, 4 points at 3k events: `── point 1/4: MSTW08lo ── ok after 4.7 s` / `   done → …/MSTW08lo`; results hold `photo.yoda` and `photo.root`; `.complete` and `provenance.json` are in `output/…/MSTW08lo/` |
| 2 | `results/…/01_pdf/plots/root/pdf.root`: `MSTW08lo/photo_eic/…`, `…/RAW/…__entries`, the `paths` tree with a `point` column, `points.json`; 17 pages beside it. It is rebuilt only when a point's YODA changes. |
| 3 | `hep plot …/pdf.root --objects '/photo_eic/d02*' --ratio`: 4 curves, "MSTW 2008 LO", "NNPDF 2.3 QCD+QED LO", … |
| 4 | `hep plot` on the two legacy YODAs: 17 pages, 2 curves, labels from the .plot files (`test_hep_plot.py`) |
| 5 | `plotmerge` in post, into `sweep.root` and `sweep.yoda` (`test_post.py`) |
| 6 | `test_post.py`: the pre product reaches every point's argv, its identity is in theirs, a failing pre prints `── pre (before every point) ── FAILED [fetch]` and stops the run, and a point may not be named `pre` |

**How:**
- **App_yd2rt `--merge OUT NAME=IN.yoda …`**: into ROOT, each input under a directory named for it,
  with `--points` storing `points.json` as a TNamed; into `.yoda`, the name as a path prefix. The
  plot stage and the `plotmerge` folder both use it, and the per-point conversion cache is gone.
- **The pre stage** (`post.py`): planned like post (no quantities, `{points}`), in `<cfg>/pre/`. Its
  products are `pre` interfaces of every point, and `plan.upstream` carries its identity.
- **`hep plot`** (`cli.py`, `plot.files`): file mode when every target ends `.yoda`, `.yoda.gz` or
  `.root`, else a configuration. ROOT files are read with uproot (lazily, as for the Delphes count).
- **The views** print a block when a point ends; a tool that did its job says nothing. `hep watch`
  builds the same block from the journal, whose records are now timestamped.
- **Consequence:** complete points from before this change keep their `.complete` in results/, which
  nothing reads now: they run once more (the seed rule of P4 S1 had already changed their identity).
- Tests: `test_hep_plot.py` 4, `test_post.py` +5 (pre 3, plotmerge 2), `test_status.py` +1 (the block);
  `make test` 170, `make test-slow` 18.

### S2 — 2026-09-27 — done: the ROOT pages look like the YODA ones

The user asked for this ("configure root style to look more like yoda plots"). It closes the style
review left open in P3 S2 task 3. The reference was the same zeus page drawn by both backends
(`plots/root/d06-x01-y01` and `plots/yoda/ZEUS_2012_I1116258/d06-x01-y01`).

| mkhtml (`default.mplstyle`) | Paint now | Paint before |
|---|---|---|
| a 4.67 × 4.21 in page | the PDF at that size, the PNG 700 × 630 | 900 × 600 px |
| Palatino, 10 pt; ticks 8 pt | Times (ROOT 133, sized in pixels, one size in both pads), `font_size` in points | Helvetica, sized per pad |
| colours EE3311, 3366FF, 109618, FF9900, 990099 | the same | kBlue+1, kRed+1, … |
| ticks inside, on all four sides, minor ticks | the same | left and bottom only |
| MC: steps, with bars at the bin centres | the same; a run of bins does not drop to the axis at its ends (`HIST ][`) | steps over a 25% band |
| data: black points, drawn under the MC | the same | black points on top |
| legend: no frame, data first, a "+" beside each entry, the title as its header | the same (drawn by hand: TLegend puts its symbols on the left only) | TLegend, symbols on the left |
| ratio: a third of the axes, no gap, the data at 1 with their errors, labels 0.6 … 1.4 | the same; the range still widens past 0.5–1.5 when a curve needs it | a grey band, a dashed line at 1 |
| math in italics | `tlatex` sets math letters as `#it{…}` | upright |

- The labels at the pad joint (the main pad's "0", the ratio's top label) are dropped, as in mkhtml.
- `configs/PhotoProduction/eic.toml` dropped its `[plot.style]` (900 × 600, font 13), which would
  have undone the new defaults.
- Tests: the tlatex expectations are now italic (`test_plot.py`, `test_plot_stage.py`).

### S3 — 2026-09-27 — done: the style in TOML, after the legacy Paint

The user asked for this ("Take inspiration from pre-rework Paint utility about toml based style
config … at the very least … output dpi (for png), legends placement, and text sizes etc"). The
current style is saved as `base.toml`, and a run names its own file with `plot.root_style`.

**What the legacy Paint did.** `legacy/utils/Paint/` (read in git at `0c3df8f^`):
- a defaults file, `configs/defaults/Paint.toml`, under the user's config, merged table by table
  (`Book.hh`), which `[paint].default_style` could replace or turn off;
- named sub-tables (`axis`, `canvas`, `legend`, `title_box`, `stats`), each key read into a struct
  (`Style.hh`);
- `use =` preset chains, and image, text and brush scales.

Kept: the defaults file under the overrides, the table-by-table merge, and the sub-tables. Not
kept: the preset chains and the scales. Three layers do the same job, and `dpi` with sizes in
points replaces the scales.

| Layer (later wins) | Where |
|---|---|
| the base style | `utils/Apps/Paint/base.toml`: every key, commented; Paint reads it itself (`Style.hh`), found beside `build/`, else under `$HEKIT_ROOT` |
| a style file | `[plot].root_style = "talk.toml"`: a bare name is under `configs/<Project>/`, `.toml` optional; `hep plot FILE… --style FILE` |
| inline | `[plot.style]` |
| per object | `[plot.object."<glob>"].style` |

The tables:
- `[page]`: size (in), dpi, font, margins;
- `[text]`: title, labels, legend, header (pt);
- `[curves]`: palette, width, errors (bars, band or none);
- `[data]`: colour, marker, marker size, x bars;
- `[axes]`: tick length, ticks on all sides, titles at the ends, offsets;
- `[legend]`: position (a corner, or [x, y]), inset, spacing, symbol, gap;
- `[ratio]`: heights, range, limits, divisions, decimals.

- A page's config holds only what the layers changed. `Paint.exe [PAGE.toml] --dump-style` prints
  the whole style after the merge.
- Checked twice, against base.toml's keys and kinds: at plan time (`plot.check_style`, with the
  nearest spelling) and by Paint (`Style.hh`).
- `[plot].legend` and `[plot.object].legend` moved to `legend.position`, and the old key says so.
  The yoda backend honours only a `legend.position` corner and refuses the rest, `root_style`
  included. Before this, `canvas` was accepted there and silently ignored.
- The ratio pad's top is trimmed by 0.5% of its range, so a label at the pad joint (3.0 at the
  limit) is not drawn.
- Tests:
  - `test_plot.py`: +8 refusals, 2 layer tests, and the yoda refusals;
  - `test_plot_stage.py`: +1, only the changed keys reach a page;
  - `test_paint.py`: +2, `--dump-style` equals base.toml, the merge, and dpi 100 → 467 × 421 px.
