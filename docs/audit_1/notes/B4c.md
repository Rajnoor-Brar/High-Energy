# B4c: replace rivet-mkhtml with a matplotlib renderer of the page document

> The manual was rebuilt at V92 (`docs/audit_2/02_Manual.md`): links here to its old pages (`01_Philosophy` … `06_Developer_Guide`) are history; `git show a029c21:docs/<page>` has them.

A design note for the user's decision (audit 1, P4 S3; [04 B4](../04_Bold_Proposals.md#b4--the-plot-stack-one-page-document-two-honest-renderers-no-patched-scripts)).
It gives the mechanics, the evidence collected on 2026-10-03, the options, and a recommendation. Nothing
here is built.

---

## 1. Where things stand

The runner writes one **page document** per page (`output/…/plots/<cell>/<object>.toml`): the `[page]`
settings, the curves (with `style` and `band` since V67 and V69), the data, and the style layer over
`utils/Apps/Paint/base.toml`. Paint draws it and writes `<page>.ranges.json` (V64): the final x and y
ranges, voided bins, the data's aligned run, and whether a range was left to the tool.

The **yoda backend** (`utils/Env/yoda/backend.py`, 419 lines, plus `backend.toml`) turns the same pages
into a rivet-mkhtml run per cell:

| What the backend does | Why |
|---|---|
| writes a copy of every curve YODA per cell, with voided bins blanked, normalised (V68) and with band envelopes as errors (V69) | mkhtml reads files, so every per-page change must exist as a file |
| cuts and renames the reference to `/REF/<analysis>/<object>` | mkhtml pairs MC and data by path |
| writes `pages.plot` (ranges, log axes, labels, legend keys from `backend.toml`) | mkhtml's settings language |
| **rewrites mkhtml's generated Python** for ratio ticks, a `best` legend and the titles, then **runs each script again** (`ratio_ticks`, `best_legend`, `titles`, `_finish`) | mkhtml has no setting for them |
| sets `LegendFontSize` to `"<size>; plt.rcParams['legend.title_fontsize'] = …"` | the only way to size the legend title (V50) |
| runs each overlay in a throwaway folder and copies the pages out | mkhtml rebuilds its whole `-o` folder |
| refuses 29 of base.toml's 35 style keys (`HONOURED` keeps 6), and curve colours that are not `#rrggbb` (V67) | mkhtml cannot follow them |

---

## 2. Evidence

- **Cost per feature.** 13 of the 27 commits since V47 changed `yoda/backend.py`. Every F7 feature this
  phase (V66–V69) needed a second implementation there: placeholders reaching `pages.plot`, per-file
  `LineColor`, normalised copies, envelopes written as errors for `ErrorBand`.
- **Speed.** The eic fixture's `energy_pdf` (4 cells × 19 objects = 76 pages, pdf + png): Paint takes
  **3.7 s** for the whole plot stage, the yoda backend **75 s**, about 1 s per page. The time is mkhtml's:
  one Python process per page script, and a second run for each patched one.
- **Disagreements, beyond the look.** On the PDF band page (`eic pdf`, d01), the ratio line where one
  data bin spans two MC bins (17–21 GeV) is 1.06 in Paint, which matches the main pad (MC ≈ 322 over the
  data bin, data 300), and about 1.3 in mkhtml, which puts the MC onto the data bins its own way. Both
  pages are "right" by their own tool, but they disagree, and the user has no lever on mkhtml's choice.
- **What mkhtml gives that we would lose.** Its look (which `base.toml` already copies, V50), its
  `index.html` (the root backend has had one since V70), and that "the yoda backend is Rivet's own tool",
  a reference point for a reader who knows mkhtml.

---

## 3. Mechanics of the replacement

`utils/Env/mpl/backend.py`, a backend plugin like `yoda` (V61's loader: `validate(settings, …)` and
`draw(cells, settings, say)`), about 300 lines.

**Inputs, all already written:**
- the page document, as the runner holds it (`Page.document`, before `for_root`): texts in LaTeX (V65),
  which matplotlib's mathtext draws directly, so no converter is needed;
- `Page.style`, base.toml merged with the page's layers, the same table Paint reads;
- `Page.ranges`, Paint's ranges file: x and y ranges, voided bins, the data's run. So the renderer does
  **none** of the range arithmetic (auto range, gutters, log decades, the voiding rule), and the two page
  sets cannot disagree about it;
- the curves from the points' YODAs (`Page.sources`, `variants`, `bands`) and the reference, read with
  `yoda` in memory: the per-cell YODA copies, the `/REF` renaming and `pages.plot` all go.

**Drawing, by Paint's rules** (so the pages match Paint's, not mkhtml's):
- steps per run of finite bins (`ax.stairs`), errors as bars at the centres, a band, or none
  (`curves.errors`); the curve's pen from its `style`, else the palette in turn;
- normalise and envelopes by the same formulas as Paint (`Σ y·Δx`, min–max), applied in memory;
- the data with markers and x bars (`data.*`);
- the ratio pad (`ratio.heights`, `range`, `limits`), each curve rebinned onto the reference as Paint's
  `rebinned()` does, with ticks by ROOT's `divisions` rule (today's `_step`, kept);
- the legend from `legend.*` (position, inset, spacing, the "+" symbol), with `best` as matplotlib's own;
- titles, corners and the legend header by `text.*`, sizes in points as `base.toml` states them.

**Running:** one Python process for the stage; pages drawn in a process pool of `os.cpu_count()` workers.
At about 0.1–0.2 s per page, the 76 pages would take a few seconds.

**What goes:** in `yoda/backend.py`, `_voided`, `_void`, `_envelope`, `_normalise`, `_reference`,
`_plot_block`, `best_legend`, `ratio_ticks`, `titles`, `_finish`, `_mkhtml`, `_overlay` and the
`LegendFontSize` trick; `backend.toml`'s `[legend]` and `[style] honoured`; every "cannot be honoured by
backend = yoda" refusal. About 350 lines out, about 300 in, and one implementation per feature after.

**What stays:** Paint is still the reference renderer and the source of the ranges. `rivet-mkhtml` stays
installed, and anyone can run it on the points' YODAs by hand.

---

## 4. The prototype and how it is judged

Building it is a step of its own (it would be P4 S4). Before the old backend is deleted, the prototype is
checked with three things:
1. **Numbers.** For every page of `tests/integration/test_plot_stage.py` and the eic `energy_pdf` and `pdf`
   (band) runs, the drawn values (steps, ratio, band edges) read back from the matplotlib artists equal
   Paint's to 1e-9, and the axis limits equal `ranges.json`. This is a test, not a judgement by eye.
2. **The look.** Side-by-side PNGs (Paint, mkhtml, mpl) for one zeus_validation cell and the eic band
   page, with a written list of every difference that remains (fonts, the "+" symbol, tick lengths).
3. **Speed.** The 76-page stage, timed against the 75 s above.

---

## 5. Options

| | What | For | Against |
|---|---|---|---|
| **A (recommended)** | Build `mpl`, then delete the yoda backend. `backend = "yoda"` is refused with a hint (`"mpl"`), as with break and migrate | one implementation per feature; every style key honoured; ~20× faster; no patched scripts | the pages are no longer mkhtml's own; a few days of work |
| **B** | Build `mpl` beside the yoda backend; freeze the yoda backend (no new features, and new keys are refused there) | mkhtml's pages stay available | two backends to keep in step for what exists; refusals grow with every feature |
| **C** | Keep things as they are | no work | every plot feature costs two implementations; 1 s per page |

**Recommendation: A.** The yoda backend has become a second plotting program written through mkhtml's
settings and a regex over its output. A renderer that reads the same document and Paint's ranges keeps
only the drawing.

**To decide:**
1. A, B or C.
2. If A or B: the backend's name (`"mpl"`, or reuse `"yoda"` for the new one).
3. If A: whether `config`'s `backend = "yoda"` lines migrate automatically in the final phase (along with
   the other config migrations), or are refused until edited.

---

## 6. Decision (the user, 2026-10-03)

**Option B, named `"mpl"`.** The matplotlib renderer is built beside the yoda backend, which is frozen: it
gets no new features, and new keys are refused there. **Until the user has verified it, `mpl`'s pages
must match mkhtml's output**, not Paint's where the two differ. So §3 changes in one respect: where
mkhtml and Paint draw differently (the ratio of a data bin spanning several MC bins, the legend's
symbols, mkhtml's fonts and tick lengths), `mpl` follows mkhtml. It still takes the ranges and voided bins
from Paint's ranges file, since the yoda backend already hands mkhtml those. §4's first check therefore
compares `mpl` with mkhtml's own generated data (`<object>__data.py`) rather than with Paint, and the
side-by-side is `mpl` against mkhtml. Built as P4 S4.

---

## 7. Built (V71)

`utils/Env/mpl/backend.py` draws mkhtml's pages from the libraries mkhtml uses, without generating or
running a script. The measurements of §4:
1. **Numbers and look.** Not compared with Paint, as the decision asked, but with mkhtml itself: the PNGs are
   **pixel-identical** on all 19 pages of the eic band sweep and on all 80 pages of `energy_pdf` (four
   cells, titles, per-value styles, a normalised object, a best legend, an overlay). A slow test,
   `test_the_mpl_backend_draws_mkhtml_s_pages_pixel_for_pixel`, keeps that true on the plot-stage pages.
2. **Speed.** `energy_pdf`'s 80 pages (pdf + png): **5.6 s** against mkhtml's 100 s.

**Next, after the user has verified the pages:** the mpl backend stops following mkhtml where Paint is
the reference (the ratio rule, every style key), takes over the yoda backend's transforms, and the yoda
backend goes (option A's remaining half).
