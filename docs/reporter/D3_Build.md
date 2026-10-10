# D3: build, from composites and `deck.md` to every target

[00_Plan.md](00_Plan.md) §5.2, D-R3, D-R4, D-R7, D-R9. Building draws a composite per block (D1)
from the collected panels (D2), then turns the user's `deck.md` into every target with pandoc
(3.1.3 on the lab PC, installed 2026-10-10).

## S1: composites, pandoc and the targets

**Tasks**
- **Composites:** `figures/<block>.pdf` and `.png`, by `layout` with the block's size, columns, labels and title.
  - A reference with `panels`, `columns` or `size` attributes makes a variant, `figures/<block>.<hash>.pdf`, with its attributes in a sidecar for the viewer.
  - A composite is redrawn only when its panels or settings change (a hash beside it).
- **The build copy:** `build/deck.md` is `deck.md` with every `![…](<block>){…}` replaced by its composite's path relative to the deck:
  - the PDF for Beamer and Overleaf;
  - the PNG for pptx and HTML.

  Other attributes (`width=…`) pass through. A reference with no `.` or `/` that names no block is refused with the nearest block; any image path is passed as it is.
- **The targets:**

  | Target | Command |
  |---|---|
  | `deck.pdf` | `pandoc build/deck.md -t beamer -V aspectratio=169 --pdf-engine=pdflatex` |
  | `overleaf.zip` | `pandoc -t beamer -V aspectratio=169 -s` → `deck.tex`, zipped at its root with the PDF composites under `figures/` |
  | `deck.pptx` | `pandoc -t pptx` (16:9 by pandoc's default reference document) |
  | `deck.html` | `pandoc -t dzslides -s --embed-resources`: one offline file |
  | `index.html` | the viewer (S2) |

  Each target is written beside `deck.md`. The `targets` key, or `--only`, picks some. A pandoc or pdflatex failure names the target and the log's last lines.
- **`hep deck <dir> [--only pdf,pptx,html,overleaf,viewer] [--list]`:**
  - `cmd_deck` and its parser in `runner/cli.py`, beside `overlay`;
  - `deck` added to `utils/Env/hep`'s dispatch list (line 43) and its help.
- **Folder mode without `deck.md`:** the build copy is generated, with a title slide and a slide per block titled by it. Nothing is written to the user's files.

**Verification**
- **A two-slide deck builds every target** (skipped where pandoc is missing):
  - `deck.pdf` has 3 pages at 16:9 (`pdfinfo`);
  - `deck.pptx`'s `ppt/presentation.xml` is 16:9, with a picture on the plot slide;
  - `deck.html` has no `http` reference and its images inlined;
  - `overleaf.zip` unzips to a `deck.tex` that pdflatex compiles.
- **Rebuilding after a panel changes:**
  - the composite and the targets change;
  - `deck.md` is byte for byte the same.
- An unknown block reference is refused, naming the nearest.

**Log**
- (empty)

## S2: `--init`, and the viewer

**Tasks**
- **`hep deck <dir> --init`:**
  - writes `deck.md` once: a title slide, then a section per `[blocks.*]` table and a slide per block;
  - writes a starter `deck.toml` for a folder that has none, from its folder-mode blocks;
  - refuses to overwrite either.
- **The viewer:** `runner/viewer.py` is the batch_1 page made generic.
  - It shows blocks and panels, with S/M/L/Full sizes, 2|3|4 columns, ← →, and the PDF refit.
  - It saves no state between visits.
  - It is the `viewer` target, `index.html`, for browsing and choosing (D-R7).

**Verification**
- `--init` writes a `deck.md` that builds as it is; a second `--init` is refused.
- `index.html` lists every block and panel, and its links resolve.
- **By hand:** batch_1 rebuilt from a recipe:
  - `deck.pdf` (a page per slide, vector plots);
  - `deck.pptx` rendered by LibreOffice;
  - `deck.html` and `index.html` in a browser.

**Log**
- (empty)
