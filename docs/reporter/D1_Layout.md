# D1: layout, a composite figure shared with `sheet`

[00_Plan.md](00_Plan.md) §4, D-R6, D-R9, D-R11. A composite figure is one block's panels in a grid,
with labels and an optional title, sized for a slide's content area.
- It is drawn once, as a vector PDF: pdflatex places the panels' PDFs or PNGs.
- Its PNG is rendered from that PDF by `pdftoppm`, so the two are the same picture.

`utils/Env/figures/sheet.py` does the PDF half of this for `sheet` (V89) today, and pastes PNGs with
PIL for the other half.

## S1: `figures/layout.py`, and `sheet` moved onto it

**Tasks**
- Rename `utils/Env/figures/sheet.py` to `utils/Env/figures/layout.py`. It is loaded by `plugins.load` as now, and `plot.sheet` (`runner/plot.py:1113`) loads it under its new name.
- `layout.grid(n, box, columns=None)`:
  - the rows and columns for n panels in a box (width × height, in pt);
  - columns automatic (the grid whose cells are closest to the panels' aspect) or given;
  - each cell's rectangle.
- `layout.pdf(panels, target, box, columns, labels, title)`:
  - writes a one-page LaTeX file at the box's size (geometry, no margins);
  - places each panel by `\includegraphics`, keeping its aspect, centred in its cell;
  - draws its label above it;
  - runs pdflatex in a scratch dir and writes `target.pdf`.

  Panels may be PDF or PNG (an `extra` image). Its error handling stays as `_pdf` has it (`ValueError` with pdflatex's last log line).
- `layout.png(pdf, target, dpi)`: `pdftoppm -png -singlefile -r <dpi>` of the composite PDF. A missing `pdftoppm` is a `ValueError` naming poppler.
- **`tile()` for sheets keeps its signature:**
  - the PDF as today, its pages' own size times the grid;
  - its PNG now rendered from that PDF by `layout.png` instead of pasted by PIL, so it no longer needs the pages' PNGs (D-R6).

  PIL leaves this module.

**Verification**
- `tests/runner/test_layout.py`:
  - the grid for 1–6 panels in a full and a half box;
  - a composite PDF of one page at the box's size (`pdfinfo`);
  - a PNG of the expected pixels at a dpi;
  - a panel's aspect kept;
  - a PNG `extra` placed.
- `tests/integration/test_plot_stage.py::test_a_sheet_tiles_drawn_pages` passes, with its PNG check reading the rendered PNG; its docstring and V89's 04 text say "rendered from its PDF".

**Log**
- (empty)

## S2: sizes, labels and titles

**Tasks**
- Size presets by name, in one table in `layout.py`, as boxes:
  - `full`: a 16:9 slide's content area under its title, measured from pandoc's Beamer and pptx output (about 16:8.5);
  - `half`: one of two columns of that area;
  - `a4`: A4 landscape;
  - `square`.
- `labels` and `titles` switches:
  - a label is drawn in a strip above its panel;
  - a title in a strip above the grid, the panels shrinking to fit.
- Labels and titles are LaTeX-escaped (`_`, `%`, `&`, `#`, `$` unless the text is math).

**Verification**
- The four presets' page sizes.
- With and without labels and title, the panel rectangles shrink as expected.
- A label with `_` and `%` builds.

**Log**
- (empty)
