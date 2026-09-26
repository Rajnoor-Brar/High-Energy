# P3 — Results and plots

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| **in progress** | 3 | P2 | YODA → ROOT conversion; ROOT pages from Paint; `rivet-mkhtml` when asked; `post` tools; a new GUIDE | 2026-09-26 |

## Goal

*Brief §Plotting*:

- ROOT is the primary graphics;
- YODA is converted into **non-temporary** ROOT files;
- a compiled, config-driven Paint app draws pdf/png/svg with gutters;
- YODA plotting remains when a config asks for it (V10).

Also in this phase:

- `post`, the after-all-points tools (V15);
- the user-facing guide, because from here on v2 is the thing people use.

Design: [04 §9](../04_Config.md#9-plot); [05_Tools.md](../05_Tools.md) §§6–7. Ledger: **L17, L18**.

---

## S1 — App_yd2rt

**Tasks**

1. **`utils/App_yd2rt.cc`**, as in [05 §6](../05_Tools.md#6-appyd2rt-utilsappyd2rtcc):
   - one directory per analysis;
   - `Histo1D` → `TH1D` with errors, `Histo2D` → `TH2D`, `Scatter2D`/`Estimate1D` →
     `TGraphAsymmErrors`, `Counter` → a one-bin `TH1D`;
   - safe names for variant paths, with a `paths` TTree to map back;
   - `/RAW` skipped.
2. **`utils/Env/yd2rt/tool.toml`**. Add `yd2rt` to the eic configurations' `tools`.
3. **Reference data**: `datasets/*.yoda` is converted once into
   `output/<P>/.cache/datasets/*.root` at plan time, keyed by the file's sha256.

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | yd2rt on an eic `pdf` YODA, read back with `uproot` | every `TH1D`'s contents and errors equal the YODA's to 1e-12, across all objects |
| 2 | `/photo_eic:R=0.4/d01-x01-y01` | round-trips through the `paths` tree |
| 3 | change only yd2rt's options, then rerun | the whole point reruns, because identity is per point (V9). Record the wall time: it is R5's cost, measured. |

---

## S2 — Paint and the plot stage

**Tasks**

1. **`utils/Apps/Paint/`** → `build/Paint.exe PAGE.toml`, as in
   [05 §7](../05_Tools.md#7-paint). The order is load → void → data → auto-range → gutters →
   draw → save.
   - The algorithms of v1's `plot/transform.py` and `plot/data.py` are read in git and written
     again in C++.
   - The style layer follows `legacy/utils/Paint/`, also read in git.
   - `--dump-ranges` for tests.
2. **`plot.py`** in the runner:
   - pages from `plot_points` × `objects`;
   - titles and axis labels from the Rivet `.plot` files, with `[plot.object]` overrides;
   - write `output/…/plots/<page>.toml` and run Paint for each page;
   - `--only plot`;
   - keys a backend cannot honour are **errors**.
3. Default `[plot.style]`. The user looks at the first eic pages, and the defaults are adjusted
   once (06 §5).

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | `hep run PhotoProduction/eic energy_pdf --only plot` | 4 pages per object, in pdf and png; the count equals `--plan`'s |
| 2 | `y_gutter = 1.5` | `--dump-ranges`: y max = 1.5 × the largest drawn value, exactly |
| 3 | `auto_range` on a histogram with empty edge bins | the range is trimmed to the first and last filled bins, matching v1's test vectors (in git: `tests/python/plot/`) |
| 4 | the eic `pdf` pages with the ZEUS data at 27x920 | data points drawn only where the map says (L18); unmapped objects get no data |
| 5 | an unsupported `[plot]` key | an error at plan time |

---

## S3 — The YODA backend, `post`, and the guide

**Tasks**

1. **`utils/Env/yoda/`**: `backend = "yoda"` runs `rivet-mkhtml -f PDF,PNG -o <plots dir>`, with each
   point YODA as a curve (`file.yoda:Title=<label>`) and the TLatex labels translated to LaTeX for
   the common subset (V11). About 100 lines.
2. **`post = [...]`**: post tools run once after all points, with `{file:points.json}`. The worked
   example is seed replicas merged with `rivet-merge` (the `replica` quantity, 04 §6.3).
3. **`docs/GUIDE.md`**, rewritten for v2. It is short: how to write a run TOML, `hep run`/`watch`/
   `build`, `make X.exe`, where things go, and what to do when a point fails.

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | `energy_pdf` with `backend = "yoda"` | an mkhtml page set with the same pages as S2's |
| 2 | a replicas configuration (3 seeds) + a `rivet-merge` post tool | `merged.yoda` has 3 × the entries of one point |
| 3 | a post tool reading `points.json` | gets every point's values, tags and product paths |

**Done when** every row of S1–S3 passes.

---

## Rollback

Revert the step commits.

## Log

### S1 — 2026-09-26 — done

| Row | Result |
|---|---|
| 1 | App_yd2rt on the legacy reference YODA, read back with uproot and compared with YODA's own Python reading: **all 17 Estimate1D objects** have equal edges, and contents and errors equal to 1e-12 (`tests/integration/test_yd2rt.py`) |
| 2 | `/photo_eic:R=0.4/d01-x01-y01` becomes `photo_eic__R-0.4/d01-x01-y01`, and the `paths` TTree maps it back |
| 3 | Changing only yd2rt's `select`, then rerunning: the whole point reruns, **16.1 s instead of 0.2 s** (identity per point, V9). This is R5's cost, measured. |

**Deviations:**
- **Rivet 4 writes final histograms as `Estimate1D`**, with the unscaled fills as `Histo1D` under
  `/RAW`. Both become `TH1D`. An Estimate's error is the average of its total down and up errors,
  where 05 §6 had said `TGraphAsymmErrors`. Photo_eic's errors are symmetric, and a `TH1D` is what
  Paint overlays and divides.
- **Directories nest** as the YODA path does (`RAW/photo_eic/…`), and only `:`/`=` are mapped.
- **Products take their final names per group**, after that group's count checks. Before, the rename
  waited for the last group, so a later group could not read an earlier product (yd2rt reads rivet's
  YODA). `.complete` is still written last.
- **Tool options are placeholders**: every `[options]` key of a tool folder, empty when unset. yd2rt
  takes its select globs as extra arguments.
- **The reference-data conversion is left to S2**, where Paint needs it.
- `yd2rt` is in every eic and zeus chain as a second group.

### S2 — 2026-09-26 — done, except the style review (task 3)

`utils/Apps/Paint/` is 636 lines (`Page.hh` 92, `Transform.hh` 175, `Draw.hh` 276, `main.cc` 93),
against the 900 estimated. `plot.py` is 296.

| Row | Result |
|---|---|
| 1 | `hep run PhotoProduction/eic energy_pdf` at 3k events (16 points, 1 min 37 s), then `--only plot`: **68 pages = 4 per object × 17, in pdf and png**, 12 s. `--plan` prints "4 page(s) per object". |
| 2 | `y_gutter = 1.5`: y max = 1.5 × the largest drawn value to 1e-9, the largest checked against uproot's reading of the inputs; on a log axis the gutter is half the decades shown; `x_gutter = 1.2` widens x by 1.2, about its centre (`test_paint.py`) |
| 3 | **Auto-range equals the legacy `auto_range.plot` for 17/17 objects**, and the **voided bins equal the legacy ydmrg output for 17/17** (min_entries = 10, pad 1, across both curves); v1's own vectors pass too: the void rules, pad 0/1, nothing filled, alignment to the longest run, unaligned data dropped (`test_paint.py`, 15 tests) |
| 4 | energy_pdf at 27x920: `[data]` on d01–d12, none on d13–d17. Data whose edges line up nowhere are dropped (`data_bins = 0`). |
| 5 | An unknown key in `[plot]`, `[plot.style]`, `[plot.data]` or `[plot.object."…"]` (v1's `LegendXPos`), an unknown backend, format or legend position, and a data file without a map: refused at plan time (`test_plot.py`, 9 cases) |

**Deviations and additions:**
- **`range_pad`** is a `[plot]` key (default 0, as in v1); the legacy plots used 1.
- **The ratio pad follows the ratios.** At 18x275 every MC/ZEUS ratio is about 0.07, which a fixed
  0.5–1.5 pad hid. The range is now at least 0.5–1.5, widened to the ratios drawn, within 0–3.
- **A curve with every bin voided** (5x41 at 3k events: no jet passes the cuts) stays in the legend
  as "(no entries)" instead of leaving a blank row.
- **LaTeX → TLatex**: `\mathrm{…}`/`\text{…}` keep their group after `_`/`^` (`E_T^\text{jet}` →
  `E_{T}^{jet}`); the title falls back to the `.plot`'s `LegendTitle`, since photo_eic's `Title` is empty.
- **zeus_validation draws the ZEUS data.** `datasets/zeus_eic.yoda` has the same numbers as Rivet's
  `ZEUS_2012_I1116258.yoda.gz` (only the titles differ), so its `[plot.data]` maps d01–d12 one to one.
- A page that crashes is reported by its signal, not by ROOT's stack-trace banner. The first draw
  crashed on exit, because the pads were freed twice (by the canvas and by the keep-alive list).
- Tests: `test_paint.py` 15, `test_plot_stage.py` 6, `test_plot.py` 20; `make test` 124 (was 83).
- **Open: task 3, the style review.** The defaults (legend rows, font size, gutter 1.5) are what the
  first pages used. With 4 curves, a header and data, the top-right legend overlaps the data peak on
  the η pages. They are adjusted once, after the user has looked at the pages.
