# Audit 2 — a health check

A health check of the whole framework after the figures work (V80–V89), done on 2026-10-04 at
`c33c5df` (branch `rework`). It asks what is missing, broken, left over, pending, contradictory,
inefficient or needlessly convoluted, and which design and structural changes are worth making.

**Read:** `utils/Env/runner/` (plot, config, cli, tools), `utils/Env/figures/`, the yoda and mpl
backends, `tests/`, docs 03, 04 and 08_Figures (in git: `git show c5cbaa3:docs/audit_1/08_Figures.md`), and the working tree.
**State:** 534 tests pass; `hep check` passes on every config.

Each item is scored as in audit 1: Priority = (Impact + Risk) × (6 − Effort),
each 1–5. Ids are `H<n>`; a step that fixes one cites it and gets a V-row in
[07_Record](../07_Record.md). Nothing here is built without the user's order.

## Findings, by priority

| # | Pri | Kind | Finding | Fix |
|---|---|---|---|---|
| H1 | 40 | oversight | `configs/PhotoProduction/photo_zs.cmnd` is **untracked**, yet `InProcZeus.toml`, `zeus_seedSweep.toml` and `zeus_validation.toml` use it. Committing the configs without it breaks all three. | Commit it along with the configs (H4). |
| H4 | 35 | pending | The migrated `configs/` (V79, plus `eic.toml` at V80) have been uncommitted for review for some time. The diff is 17 files, −1365/+271, and includes the deletion of `herwig/sherpa/whizard/madgraph.toml` and their cards (now in `tests/fixtures`). The longer it waits, the harder the review: `configs_before/` sits in a temporary scratchpad. | The user reviews it (`migrate_dry.diff`). Then commit it in one commit with H1. |
| H11 | 25 | pending | Two 1D backends exist for one purpose. `yoda/backend.py` (424 lines, frozen) and `mpl/backend.py` (468 lines) have waited on the user's mpl verification since V71. That removal is the largest deletion available. | The user compares the mpl pages with mkhtml. Then the yoda backend goes, mpl stops following mkhtml, and `"both"` is redefined (B4c §6–7). |
| H2 | 20 | contradiction | A `compare` figure is drawn by the plot stage of **every** configuration of this file that it names (`plot.draw`, l.1092). 08_Figures F1 S2 says "the last configuration it names", while docs/04 §11.2 says "each". Under `sweep_runs` with 6 configurations, the pages are drawn up to 6 times; the merge is stamped, but Paint isn't. | Draw it only at the last of its own configurations in `run.runs()` order, or when `hep plot` names one. Update 04 to match 08. |
| H6 | 20 | duplication | In `plot._pages`, the defined loop (l.615–664) and the overlay loop (l.666–713) each build the same curve dict and write the page TOML, the `Page(...)` call included, about 45 lines each. `_heatmap` and `files()` repeat the write-config step. | Add `_curve(plan, full, merged, raws, label, look, folded)` and `_write(document, out_dir, rel, …) -> Page`, used by all four. |
| H7 | 20 | duplication | The "stamp beside target, rebuild when digest differs" pattern appears 5 times: `convert`, `merge`, `_scanned`, `point_yodas`, `_merged`. | Add `_cached(target, stamp, digest, make)` in plot.py (or `tools.py` beside `sha256_file`). |
| H13 | 20 | tests | Not covered: `derive.scan_value`'s `integral`, `mean` and `entries` (only `sigma` and `bin:N`), `projection-y`, a sheet's error path (no pdflatex, mixed sizes), and compare drawing once (H2). | One integration test per gap. They need YODA's Python, so they are slow tests. |
| H12 | 16 | inefficiency / fragile | `figures/sheet.py`: the PDF falls back to a hard-coded 336×303 pt (a copy of base.toml's size). It sizes every cell from the first page only, so pages of mixed sizes misalign. Other gaps: the yoda backend's sheets are skipped silently, a sheet can't take compare pages, and the default `columns = min(3, n)` isn't stated in docs/04. | Take the size from `base.toml`'s `page.size`, or from pdfinfo for each page; take the largest. Say when the yoda backend is skipped, and document the default. |
| H14 | 16 | docs | docs/04 §11.2's `class` row is a single 2,900-character table cell. docs/03 (User Guide) shows only defined and overlay figures: there is no merged, compare, derived, scan, sheet or HeatMap example. | Give §11.2 one subsection per class, with keys, pages and an example. Add a short "Figures" walk-through to 03. |
| H5 | 15 | convolution | `config.check_plot` (l.628–697) holds about 70 lines of hand-written `if kind == …` rules, saying which keys each class requires, forbids or counts. The scan `y` regex repeats `derive.SCAN`, and `op` repeats `derive.OPS`. | Make it declarative in `schema/run.toml`: `[figure_class.<class>] needs / forbids / objects = 1\|2\|"any"`, and generate the checks. `derive.py` reads its choices from the schema. This follows the master/base.toml idea. |
| H9 | 15 | structure | The classes are dispatched in three places. `pages()` loops over merged and scan, `draw()` over sheet and compare, and `derived_figures`/`_labels_from` handle derived. `Figure` is a flat union of every class's fields (15 positional arguments in `figures()`). `plot.py` is 1,287 lines. | Split out `runner/figures.py`: `Figure` built by keyword from its table, and a class → builder table (members, yodas, out_dir, the `_pages` call). `plot.py` keeps the styles, page writing, Paint and draw. Do this together with H6 and H7. |
| H3 | 15 | leftover | References remain to `hep plot FILE…`, renamed at V74: the hint at `cli.py:584`, the section comment at `plot.py:1183`, and the `write_index(…, "hep plot", …)` title at `plot.py:1285`. | Change them to `hep overlay`. |
| H8 | 10 | leftovers | Leftovers in `plot.py`: the wrappers `objects_of`, `raws_of` and `_sha`, the alias `base_of`, `import json` inside `_root_curves` (already imported at the top), and `STYLE_CHOICES`/`COUNTERS`, which sit glued to `formats_of` with no blank line. In `derive._base`, the plugin repeats `hepfiles.base_path`. | Call `hepfiles` directly. The plugin keeps its own copy (it may not import the runner), with a comment saying why. |
| H10 | 10 | inefficiency | `figures(run)` is re-parsed about 6 times per draw, in `validate`, `check_figures` (×3), `point_yodas` and `draw` (×2). `compared()` reloads the other run TOMLs at both check and draw. | Cache it per run (`functools.cache` keyed on `id(run)`, or a cached attribute on `RunConfig`). Have `compared` load each ref once. |
| H16 | 8 | complexity | Hot spots in `tools.py` (1,359 lines): `_render` (≈137 lines, with the nested `claim`/`apply`), `_argv` (≈110) and `plan_point` (≈100). They work and are tested, but are hard to change. | Later: split `_render` per kind of mapping. Not now. |
| H15 | 6 | features | Known limits: heat maps are Paint-only (no mpl), a scan's x must be numeric (no named values, so no PDF-set scans), and sheets have no shared y title or legend. | Leave them until a use asks for one. List them in 08 as "Open". |

**Carried over (no action without the user's word):**
- F8 `--more`;
- F9 Slurm/HTCondor;
- K15 `HEKIT_*` rename;
- Paint's PDF lines look about 2× too thick;
- the held C++/Rivet items (K3, K4, K7, K8, K10, yd2rt's dead parameter), which change identities when rebuilt;
- `extends`/`common.toml` ("not now");
- the user's stray files, left alone: `docs/Untitled-1.md`, `configs/PhotoProduction/xx/`, `photo_eic.plot`.

**Healthy:**
- all suites pass;
- the schema and its JSON are in sync;
- `flags.mk` finds all its libraries;
- the identity and stamp scheme is consistent;
- every figure class has at least one integration test;
- no TODO or FIXME debt in `utils/`.

## Remediation plan (each step is its own local commit, with tests, a V-entry and doc rows)

- **R0, the user's (no code):** H1 + H4 (review, then commit configs together with `photo_zs.cmnd`) and H11 (verify mpl).
- **R1, quick fixes (one session, behaviour kept apart from H2):**
  - **S1:** H3, H8, H10 and H7, a pure tidy. The page TOMLs stay byte-identical (check with the stamp tests and `test_plot_stage`).
  - **S2:** H2, compare drawn once, plus its test from H13.
- **R2, structure:**
  - **S1:** H9 + H6, with `runner/figures.py` and a builder table. `_pages` loses its duplicated curve/page code. The page TOMLs stay byte-identical (diff `output/tests` before and after).
  - **S2:** H5, the figure-class rules moved into `schema/run.toml`. `test_a_figure_is_checked_when_the_file_is_read` keeps every message, and `make schema` regenerates the JSON.
- **R3, edges and docs:**
  - **S1:** H12, the sheet size and messages, plus the H13 tests that remain.
  - **S2:** H14, docs/04 §11.2 per class and the docs/03 walk-through. `test_docs` keeps every key documented.
- **Later:** H16, H15 and the carried-over items.

## Verification

- `source ~/HEP/setup.sh` before every make or pytest; one pytest session at a time; tests never write to `results/` or `configs/`.
- Each step:
  - `make test` passes, and the slow suite passes for steps that touch plot (`tests/integration/test_plot_stage.py`, `test_hep_plot.py`);
  - `hep check` passes on every `configs/` TOML.
- R1 S1 and R2 S1: the page TOMLs under `output/tests/pytest/…/plots/` match before and after (saved to the scratchpad, then `diff -r`).
- Commits stay local, never pushed, with the `Co-Authored-By: Claude Opus 5.5` line. `configs/` stays untouched; there are no rebuilds of App_*/modules/Rivet (Paint isn't touched either).
- The R-phases start only on the user's order, one step at a time.
