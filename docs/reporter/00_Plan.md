# Reporter: decks for talks and sharing (`hep deck`)

The plan for building talks and shareable reports from the framework's drawn pages. It was agreed
with the user on 2026-10-08, after a discussion of the current features, the new ones, and their
structure. It was reviewed on 2026-10-10 against the code, the results on disk and pandoc itself (§8).
Phase files: [D1_Layout.md](D1_Layout.md), [D2_Collect.md](D2_Collect.md),
[D3_Build.md](D3_Build.md), [D4_Stack_and_Docs.md](D4_Stack_and_Docs.md). Each step is implemented
only on the user's order.

---

## 1. Why

`reports/batch_1/` was assembled by hand:
- pages copied out of `results/` across result folders (event counts) and renamed;
- the user's own `_AB.png` images added;
- a one-off HTML page (blocks, a 2|3|4-column grid, S/M/L/Full sizes, ← →).

None of it can be rebuilt after new runs, and none of it gives slides.

## 2. What exists

| Piece | What it does | Where |
|---|---|---|
| drawn pages | `results/<P>/<run>/<NN>_<label>/plots/<backend>/[<cell>/]<object>.pdf` (and `.png` when `formats` asks) | the plot stage |
| a folder's points | `results/…/<NN>_<label>/<point>/<product>.yoda`, whose `/RAW/_EVTCOUNT` counter holds the events the point ran | the run |
| provenance | `output/…/<NN>_<label>/<point>/provenance.json`: `events`, configuration, config file, … (gone once `output/` is cleaned: 3 of the 7 ZEUS folders keep it) | the run |
| `points.json` | `output/…/<NN>_<label>/points.json`: run, project, configuration, config file, the points' quantities and labels (no event count) | the plot stage |
| tiling | `utils/Env/figures/sheet.py` `tile()`: pages placed by pdflatex (vector PDF) and pasted by PIL (PNG), `columns` wide; `plot.sheet` (V89) loads it | `utils/Env/figures/sheet.py` |
| `index.html` | a plain gallery per backend: a section per cell, fixed thumbnails, format links (V70) | `plot.write_index` |
| the schema | `utils/Env/schema/run.toml` only; `schema.py` reads it and `docs.py` writes its tables (`keys <table>`) | `runner/schema.py`, `runner/docs.py` |
| `hep`'s commands | a fixed list dispatched to `utils/Env/run` | `utils/Env/hep:43` |
| tools on the lab PC | pandoc 3.1.3 (installed 2026-10-10); pdflatex with beamer and every package pandoc's template loads; poppler's `pdftoppm` and `pdfinfo`; LibreOffice | |

## 3. Decisions (D-R1–D-R13)

| # | Decision |
|---|---|
| D-R1 | **Purpose:** talks/slides and sharing. |
| D-R2 | **Input:** a recipe (`deck.toml`, reproducible) and a plain folder of files, both. |
| D-R3 | **A full creator.** The talk's text lives in the user's `deck.md`, which the tool never rewrites after `--init`. Plot sources live in `deck.toml`. |
| D-R4 | **On rebuild, plots refresh and text stays:** a build re-reads `deck.md` and replaces only what it makes. |
| D-R5 | **Copied, self-contained:** a deck is `reports/<name>/` with everything it shows; `deck.toml` and `deck.md` live there. |
| D-R6 | **PNGs are rendered, not required** *(revised 2026-10-10)*: a composite's PNG is made from its PDF by `pdftoppm`, so no page needs a PNG of its own. PDF-only pages work, and sheets get their PNG the same way. |
| D-R7 | **Targets:** Beamer PDF (vector), an Overleaf zip, `.pptx` (which Keynote and Google Slides import), and HTML through pandoc's **dzslides**: one offline file *(engine chosen 2026-10-10)*. **The viewer is kept** as a target of its own, `index.html`, for browsing blocks and panels. |
| D-R8 | **Slide kinds:** title, section, plot grid, a block beside bullets or with a caption below it, and text. |
| D-R9 | **One composite figure per plot slide:** the block's grid is drawn once as a vector PDF and rendered to PNG from it, so it is the same picture in every target. Panel labels and block titles are switchable per deck and per block. |
| D-R10 | **Theme:** plain now (pandoc's default Beamer and pptx); a `template` key later. |
| D-R11 | **Sheets stay, and share the layout:** `sheet` and the deck composites use one layout module. |
| D-R12 | **Pages are picked by result folder** *(2026-10-10)*: `from = "<Project>/<run>"` and `folders` (names or globs) under `results/`. Result folders outlive and drift from run TOMLs (two config files share the run `zeus`; configurations were renamed), so no run TOML is read. |
| D-R13 | **Labels come from the files** *(2026-10-10)*: a panel's event count from its folder's provenance (`events`) when `output/` keeps it, else from its YODA's `/RAW/_EVTCOUNT`, shown to 2 significant figures (`9,999,062` → `10M`); or the folder's label (`label = "folder"`). Two panels of a block with one label are refused. |

## 4. Structure

| Part | Knows runs? | Where |
|---|---|---|
| **layout**: a composite figure (a grid of panels, labels, an optional title, sized to a slide's content area), PDF by pdflatex, PNG by `pdftoppm` from that PDF | no | `utils/Env/figures/layout.py`, grown from `figures/sheet.py` (whose `tile` it keeps for `plot.sheet`) |
| **collect**: `deck.toml` blocks → panels → files, from result folders or a plain folder | the results layout only | `runner/deck.py`, reusing `paths` (`results_root`, `output_root`) |
| **build**: composites, `deck.md` → pandoc → targets, `--init` | no | `runner/deck.py` |
| **viewer**: the batch_1 page made generic, as the deck's `index.html` | no | `runner/viewer.py` (later, plot's `index.html` may use it too) |

**With [docs/framework/](../framework/README.md):** `reports/` is a work dir's folder (its D4), and
the runner moves into HEimdall. So `hep deck` is a work command whose code is the framework's. The
paths here are today's (`utils/Env/…`); the move map carries them.

## 5. A deck's files

```
reports/<name>/
  deck.toml          plot sources and layout (the user's)
  deck.md            the talk (the user's; --init writes it once)
  extras/            the user's own images (optional)
  panels/            copied pages, by block               ┐
  figures/           a composite per block (pdf, png)      │ made by hep deck,
  deck.pdf  deck.pptx  deck.html  overleaf.zip              │ replaced on every build
  index.html         the viewer of blocks and panels       ┘
```

### 5.1 `deck.toml`

```toml
[deck]
size = "full"            # composite size: "full" (a slide's content area), "half" (one of two columns), "a4", "square"
labels = true            # panel labels on the figure
titles = false           # the block's title on the figure (the slide has its own)
targets = ["pdf", "pptx", "html", "overleaf", "viewer"]

[blocks.zeus]            # one block per page: zeus-d01, zeus-d02, …
from = "PhotoProduction/zeus"                        # results/<Project>/<run>/
folders = ["01_PDFs_010M", "01_PDFs_025M", "01_PDFs_050M", "03_PDFs_150M", "03_PDFs_200M"]
pages = ["d01-x01-y01", "d02-x01-y01", "d11-x01-y01", "d12-x01-y01"]
extra = "extras/zeus_{page}_AB.png"                  # the user's own image, as a last panel
columns = 3
```

A block's panels are its folders, in the order given (globs in natural order). Labels follow D-R13.
The schema is `utils/Env/schema/deck.toml`; `make docs` writes its tables into 04.

### 5.2 `deck.md`

Pandoc Markdown: `---` between slides, `#` a section, `##` a slide, and `![](<block>)` a block's
composite.

```markdown
---
title: Photoproduction at EIC and ZEUS
author: R. Brar
date: group meeting, 8 Oct 2026
---

# ZEUS validation

## Event count: d01
![](zeus-d01)

## What changes with statistics
:::: columns
::: column
- tails settle by 50M
- ratio within 5% at 150M
:::
::: column
![](zeus-d11){panels="10M 200M" size="half"}
:::
::::
```

A block reference may take these attributes:
- `panels`: a subset of the block's panels;
- `columns`: the grid's columns;
- `size`: one of the presets.

Each gives a composite of its own. A build copies `deck.md` to `build/deck.md`, with each block
reference replaced by its composite's relative path, then runs:

| Target | Made by | Plots in it |
|---|---|---|
| `deck.pdf` | pandoc `-t beamer -V aspectratio=169`, via pdflatex | vector PDFs |
| `overleaf.zip` | pandoc `-t beamer -s` → `deck.tex`, zipped with `figures/` | vector PDFs |
| `deck.pptx` | pandoc `-t pptx` (16:9 by default) | PNGs |
| `deck.html` | pandoc `-t dzslides -s --embed-resources`: one offline file | PNGs |
| `index.html` | the viewer | panels and composites |

### 5.3 Folder mode

With no `deck.toml`:
- blocks come from file names, grouped by a regex (default `<block>_<panel>`), in natural order (1M < 10M < 150M), with images after PDFs;
- with no `deck.md`, there is one slide per block, titled by it.

## 6. Phases

| Phase | Steps | What it gives |
|---|---|---|
| [D1](D1_Layout.md) layout | S1 the module, sheet moved onto it; S2 sizes, labels and titles | composite figures, shared with `sheet` |
| [D2](D2_Collect.md) collect | S1 `deck.toml` and blocks from result folders; S2 folder mode, `--list` | `panels/` filled and labelled |
| [D3](D3_Build.md) build | S1 composites, pandoc, targets; S2 `--init`, the viewer | `deck.pdf`, `.pptx`, `.html`, `overleaf.zip`, `index.html` |
| [D4](D4_Stack_and_Docs.md) stack and docs | S1 pandoc, poppler and beamer in the stack lists; S2 the manual | installable everywhere, documented |

**Later, separate:** `plot.write_index` through the viewer (sizes, columns, keys for every run's
pages); a `template` key for Beamer themes and pptx reference documents.

## 7. Rules for every step

- One local commit per step, with its tests, staging named paths only.
- A V-row in 07 (from V102), and `make docs` after any schema or CLI help change.
- `source ~/HEP/setup.sh`; one pytest session at a time; tests write into `tmp_path` only.
- Never `results/`, `configs/` or `reports/`: fixtures build scratch trees, through `HEKIT_RESULTS` and `HEKIT_OUTPUT`.
- `reports/` stays out of git.

## 8. Review, 2026-10-10

Checked against the code, the results on disk and pandoc, by probes in the scratchpad.

**Held:**
- pandoc 3.1.3 builds a 16:9 Beamer deck (title, section, plot and column slides);
- it builds a 16:9 `.pptx` from PowerPoint's own layouts ("Title and Content", "Two Content"), rendered correctly by LibreOffice and editable;
- `::: columns` works in both, and in dzslides;
- the existing tiling made a real ZEUS d01 composite from batch_1's PDFs.

**Changed:**

| # | Finding | Change |
|---|---|---|
| R1 | the tiling is `utils/Env/figures/sheet.py`, not `plot.py` | the layout grows from it, as `figures/layout.py` (D1) |
| R2 | `pdftoppm` is installed, and the ZEUS result folders hold PDFs only | composite PNGs are rendered from their PDFs; no page needs a PNG (D-R6 revised) |
| R3 | result folders drift from run TOMLs: `zeus/` holds `01_PDFs_010M` … `03_PDFs_200M` from two config files whose configurations are now `default` … `default4` | pages are picked by result folder (D-R12) |
| R4 | `points.json` has no event count, and `output/` keeps only 3 of 7 ZEUS folders | labels come from provenance, else the YODA's `/RAW/_EVTCOUNT`, else the folder (D-R13) |
| R5 | a full-16:9 composite leaves side margins under a slide title; a six-panel grid in half a slide is unreadable | sizes are a slide's content area (`full`, `half`); `panels`, `columns` and `size` attributes on a block reference |
| R6 | pandoc's reveal.js output loads reveal.js from unpkg.com | HTML through dzslides, offline in one file; the viewer kept as its own target (D-R7) |
| R7 | `make docs` reads only `schema/run.toml`; `hep` dispatches a fixed list of commands | D2 makes schema and docs read a second schema file; D3 adds `deck` to `utils/Env/hep` |
