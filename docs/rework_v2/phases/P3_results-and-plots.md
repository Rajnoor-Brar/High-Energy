# P3 — Results and plots

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| not started | 3 | P2 | YODA → ROOT conversion; ROOT pages from Paint; `rivet-mkhtml` when asked; `post` tools; a new GUIDE | 2026-09-26 |

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

*(filled during execution)*
