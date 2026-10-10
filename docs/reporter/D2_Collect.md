# D2: collect, from result folders and from a plain folder

[00_Plan.md](00_Plan.md) §5.1, §5.3, D-R12, D-R13. Collecting turns a deck's sources into blocks of
labelled panels, copied into `reports/<name>/panels/`. No run TOML is read: result folders are taken
as they are on disk.

## S1: `deck.toml`, and blocks from result folders

**Tasks**
- **The schema:** `utils/Env/schema/deck.toml`, with every key's type, default and doc.
  - `[deck]`: `size`, `labels`, `titles`, `columns`, `targets`, `backend` (default `root`);
  - `[blocks.<name>]`: `from`, `folders`, `pages`, `label` (`"events"`, the default, or `"folder"`), `extra`, `columns`, `size`, `labels`, `titles`, `title`.

  `runner/schema.py` reads a second schema file: `spec(name)`, with `run` as today's default. `runner/docs.py`'s `keys <table>` finds deck tables there, as `keys deck` and `keys block`.
- `deck.load(dir)`: reads and checks `deck.toml`. An unknown key is refused with the nearest one, as run TOMLs are.
- **Blocks from `results/`:**
  - `from = "<Project>/<run>"` is `results_root()/<Project>/<run>/` (`runner/paths.py`, so tests use `HEKIT_RESULTS`);
  - `folders` are names or globs of its configuration folders (`01_PDFs_010M`), names in the order given, globs in natural order;
  - each folder's `plots/<backend>/` gives the pages, matched by `pages` (globs, with or without the cell);
  - one block per page, named `<block>-<short>`, where `short` is the page's stem without `-x01-y01` when that is unique among the block's pages, else the whole stem (`zeus-d01`);
  - a panel per folder, its file the page's PDF (or PNG when no PDF was drawn).
- **Labels** (D-R13), with `label = "events"`, the default:
  1. the folder's first point's `provenance.json` `events`, under `output_root()/<Project>/<run>/<folder>/`;
  2. else its YODA's `/RAW/_EVTCOUNT` `numEntries`, read as text from `results/…/<folder>/<point>/*.yoda[.gz]`;
  3. shown to 2 significant figures with k, M or G (`9,999,062` → `10M`).

  `label = "folder"` gives the folder's label, without its serial (`PDFs_010M`). Two panels of a block with one label are refused, naming both folders.
- **`extra`:** a path pattern under the deck, with `{page}`, `{short}` and `{block}`. It is appended as the block's last panel, labelled by its name. A missing file is refused.
- **Copy** into `panels/<block>/<label>.<ext>`. A file is copied again only when its hash changes, and a panel that is gone is removed.
- **Refusals:**
  - an unknown key;
  - a `from` that is not a results folder;
  - a folder or page glob that matches nothing, naming where it looked;
  - duplicate labels.

**Verification**
- `tests/runner/test_deck.py`, on a scratch results tree (`HEKIT_RESULTS`, `HEKIT_OUTPUT`): two result folders with `plots/root/` pages (PDF only) and a point's YODA with `/RAW/_EVTCOUNT`, and one with `provenance.json`. It checks:
  - the blocks and their order, and the short names;
  - labels from provenance, from the YODA (`9999062` → `10M`), and by folder;
  - `extra` appended;
  - a second collection copies nothing;
  - the refusals.

**Log**
- 2026-10-10: done, with S2 (one module, `runner/deck.py`).
  - **Schema:** `utils/Env/schema/deck.toml`; `schema.spec(name)`, `DECK_TABLES`; `docs.py` renders `keys deck` and `keys block` (04 §15). `paths.reports_root()` and `$HEKIT_REPORTS` (set by conftest).
  - **Found on the real results:** ZEUS `03_PDFs_150M` and `03_PDFs_200M` have no Paint pages, only mpl's, so `backend` takes a list in order of preference. A missing page's refusal names the backend that drew it (`backend = ["root", "mpl"]`).
  - **Labels:** EIC's YODA counts are about 2 % short of what was asked (980k for 1M) and EIC's `output/` is gone, so a label is the events asked for: provenance, else the count the folder's name ends in, else the YODA's. A `title` is a pattern too (`ZEUS {short} · PDFs`).
  - **Probe:** batch_1's ZEUS and EIC halves as a recipe over the real results: 9 blocks, 44 panels, 40 copied in under a second; a second run copies 0.
  - `tests/runner/test_deck.py`: 18 tests. Docs: 04 §15 (generated), 05 (generated), 07 V103.

## S2: folder mode, and `--list`

**Tasks**
- **Folder mode:** with no `deck.toml`, every PDF and PNG in the deck's folder (not `panels/`, `figures/` or `build/`) is grouped by a regex with groups `block` and `panel`.
  - The default is `^(?P<block>.+)_(?P<panel>[^_]+)$`; a `[deck] group = "…"` key overrides it.
  - Panels are in natural order (1M < 10M < 150M), images after PDFs.
  - A panel name of a count with k, M or G is labelled `10M events`; any other is shown as it is.
- `hep deck <dir> --list` prints the blocks, their panels and labels, and the files each came from, then stops. It writes nothing.

**Verification**
- batch_1's file names give its 10 blocks with their panels, the hand-made page's (`eta_algorithms` and `eta_algorithmsAB` share block `eta`).
- A custom regex works; a regex without `block` is refused.
- `--list` writes nothing.

**Log**
- 2026-10-10: done with S1: folder mode (`[deck].group`, natural order, `10M events` labels for counted names) and `hep deck <deck> --list`.
