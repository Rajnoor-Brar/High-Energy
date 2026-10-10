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
- 2026-10-10: done. `apt_packages` gets a "decks and sheets" group (`pandoc`, `poppler-utils`, `texlive-latex-recommended`), as does `build_by_hand.txt` step 1; the Brewfile `pandoc` and `poppler`; a line in the stack README §4 and a row in the Mac README's table. `test_stack_build.py` checks the three are in the list. The user's own `cores`/`root_cores` edit in `settings.toml` was left out of the commit (only these lines were staged).

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
- 2026-10-10: done. 03 §11 (decks: the files, a talk from result folders, `deck.md`, folder mode), 04 §15 (generated tables, with D2), 05 §1.8 `hep deck` (and its generated table), 06 §2.1 (`deck`, `viewer`) and §14 (a deck's tree), 07 V102–V104, `docs/README.md`'s index lines. `test_docs.py`'s link check now skips code (fenced blocks and inline spans), where a deck.md example's `![](zeus-d01)` names a block, not a file. `make docs` leaves nothing stale.
