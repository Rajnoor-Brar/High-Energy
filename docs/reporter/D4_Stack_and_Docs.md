# D4: the stack and the manual

[00_Plan.md](00_Plan.md). Decks need pandoc, poppler (`pdftoppm`) and the Beamer class wherever the
framework is installed, and a place in the manual.

## S1: pandoc, poppler and Beamer in the stack's lists

**Tasks**
- Add `pandoc`, `poppler-utils` (`pdftoppm`, `pdfinfo`) and `texlive-latex-recommended` (the Beamer class), in a "decks and sheets" group, to:
  - `docs/stack/settings.toml`'s `apt_packages`;
  - `docs/stack/build_by_hand.txt`'s step 1.
- The Mac `Brewfile`: `brew "pandoc"` and `brew "poppler"` (Beamer comes with the TeX the user installs).
- A line in `docs/stack/README.md` §4 and in the Mac README's table.
- The lab PC already has all three (pandoc installed by the user 2026-10-10).

**Verification**
- `tests/runner/test_stack_build.py` still passes, and its dry run lists `pandoc` and `poppler-utils`.

**Log**
- (empty)

## S2: the manual

**Tasks**
- **03, a new section:** decks, how to make a talk.
  - the files of `reports/<name>/`;
  - `--init`, then edit `deck.md`, then build;
  - slide kinds and block-reference attributes;
  - folder mode;
  - where each target opens (PowerPoint, Keynote and Google Slides by import; Overleaf by upload; `deck.html` offline in any browser).
- **04:**
  - `deck.toml`'s keys: generated tables from `schema/deck.toml` (`keys deck`, `keys block`);
  - `sheet`'s PNG, now rendered from its PDF.
- **05:** `hep deck` and its options.
- **06:** `figures/layout.py`, `runner/deck.py` and `runner/viewer.py`; the second schema file.
- **07:** the V-rows of D1–D3.
- **README.md:** the index line.
- Run `make docs`.

**Verification**
- `make docs` leaves nothing stale; `tests/runner/test_docs.py` passes.

**Log**
- (empty)
