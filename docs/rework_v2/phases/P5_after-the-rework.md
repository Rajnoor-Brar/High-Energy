# P5 — After the rework: the user's additions

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| **done** | 1 | P4 | markers in output/, plots/root and plots/yoda, one line per point, a pre stage, the sweep in one file, `hep plot` | 2026-09-27 |

## Goal

The user's requests after P4 (2026-09-27):

- "an option for a post/pre sweep tool call": `post` existed (V15); `pre` is new.
- "a tool (plotmerge) that merges yoda/root files from a sweep into singular file".
- "an hep plot option (hep plot config) to merge and emit outputs to auto link paint.exe".
- "files like .complete and provenance.json be in outputs".
- "plots/yoda be for yoda outputs, plots/root/ for root emitted png/pdfs".
- A finished point is one block: `── point 2/4: NNPDF23lo ── ok after 71.8 s`, then `done → …`.

## S1 — Everything above

| # | Row | Expect |
|---|---|---|
| 1 | `hep run PhotoProduction/eic pdf` | one block per point; `results/<point>/` holds the products only; `.complete` and `provenance.json` are in `output/<point>/` |
| 2 | its plot stage | `results/…/plots/root/pdf.root` (a directory per point, `points.json` inside), and the pages drawn from it into `plots/root/` |
| 3 | `hep plot` on that file | one curve per point, labelled by the swept values |
| 4 | `hep plot a.yoda b.yoda` | one page per object, a curve per file, no run TOML |
| 5 | a `plotmerge` post tool | one ROOT (or YODA) file with every point |
| 6 | a `pre` tool | its product is an input of every point; a changed pre reruns them; a failure stops the run |

## Log

### S1 — 2026-09-27 — done

| Row | Result |
|---|---|
| 1 | eic `pdf`, 4 points at 3k events: `── point 1/4: MSTW08lo ── ok after 4.7 s` / `   done → …/MSTW08lo`; results hold `photo.yoda` and `photo.root`; `.complete` and `provenance.json` are in `output/…/MSTW08lo/` |
| 2 | `results/…/01_pdf/plots/root/pdf.root`: `MSTW08lo/photo_eic/…`, `…/RAW/…__entries`, the `paths` tree with a `point` column, `points.json`; 17 pages beside it. It is rebuilt only when a point's YODA changes. |
| 3 | `hep plot …/pdf.root --objects '/photo_eic/d02*' --ratio`: 4 curves, "MSTW 2008 LO", "NNPDF 2.3 QCD+QED LO", … |
| 4 | `hep plot` on the two legacy YODAs: 17 pages, 2 curves, labels from the .plot files (`test_hep_plot.py`) |
| 5 | `plotmerge` in post, into `sweep.root` and `sweep.yoda` (`test_post.py`) |
| 6 | `test_post.py`: the pre product reaches every point's argv, its identity is in theirs, a failing pre prints `── pre (before every point) ── FAILED [fetch]` and stops the run, and a point may not be named `pre` |

**How:**
- **App_yd2rt `--merge OUT NAME=IN.yoda …`**: into ROOT, each input under a directory named for it,
  with `--points` storing `points.json` as a TNamed; into `.yoda`, the name as a path prefix. The
  plot stage and the `plotmerge` folder both use it, and the per-point conversion cache is gone.
- **The pre stage** (`post.py`): planned like post (no quantities, `{points}`), in `<cfg>/pre/`. Its
  products are `pre` interfaces of every point, and `plan.upstream` carries its identity.
- **`hep plot`** (`cli.py`, `plot.files`): file mode when every target ends `.yoda`, `.yoda.gz` or
  `.root`, else a configuration. ROOT files are read with uproot (lazily, as for the Delphes count).
- **The views** print a block when a point ends; a tool that did its job says nothing. `hep watch`
  builds the same block from the journal, whose records are now timestamped.
- **Consequence:** complete points from before this change keep their `.complete` in results/, which
  nothing reads now: they run once more (the seed rule of P4 S1 had already changed their identity).
- Tests: `test_hep_plot.py` 4, `test_post.py` +5 (pre 3, plotmerge 2), `test_status.py` +1 (the block);
  `make test` 170, `make test-slow` 18.
