# P9-S02 — hep proc: RDataFrame histograms on Delphes output

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P9 — ROOT processing layer |
| Depends on | [P9-S01](P9-S01_proc-fits.md), [P7-S08](P7-S08_delphes-external.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | D15; R9; 12 §2.2 |
| Updated | 2026-09-20 |

## Goal

`[[proc.hist]]` fills histograms from `delphes.root` via RDataFrame (or uproot+hist) into `proc.yoda`.

## Context

- Heavy RDF jobs run as a supervised stage.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `uproot`, `hist`, PyROOT | engines | use |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/proc/hist.py`
- stage wiring

**Out (non-goals)**

- In-process Delphes

## Design notes

- Same bins from both engines is a test requirement.

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- `utils/python/hekit/proc/hist.py`; `[[proc.hist]]` gains `engine`, and `hep proc` runs them
- derived histograms drawn as their own figures (`plot/fits.py`, `plot/backends/mpl.py`)
- `tests/python/proc/test_hist.py` (22), additions to `tests/integration/test_proc.py`

## Verification

| Check | Command | Expected | Measured |
|---|---|---|---|
| Engines agree | RDF vs uproot on a small delphes.root | identical bins | **identical** on a real `delphes.root` (`Tower.ET`, 785 entries after cuts) and on eight expressions over a jagged tree — plain, cut, `&&`, `\|\|`, `!`, a derived quantity, arithmetic, and the precedence case |
| Plots | `hep plot` | proc histograms shown | `/PROC/<name>` becomes its own figure; the mpl backend picks it up and its integral matches the fill |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated (12 §2 and §2.2; the generated config reference)
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — **done.** Both rows measured. 22 unit tests, 14 integration tests.

  **The step's difficulty is not histogramming, it is that the two engines speak different
  languages.** RDF compiles C++; uproot evaluates Python over awkward arrays. So every `&&`, `||`
  and `!` has to be translated — and the trap is that Python's `&` binds **tighter** than a
  comparison, so a textual rewrite turns `a > 5 && b < 3` into `a > (5 & b) < 3`: valid Python,
  different physics, no error. The translation therefore goes through Python's own parser and
  rewrites `and`/`or`/`not` as **tree nodes**, where precedence is structural and cannot be got
  wrong. A test fits that exact case, and the two engines agree on it.

  **Identical, not close.** On a real `delphes.root`: `Tower.ET` with `> 0.5 && |Eta| < 2.0`, 785
  entries, every bin equal. On a jagged tree written with uproot: eight expressions — plain, cut,
  `&&`, `||`, `!`, a derived `sqrt(x*x)`, arithmetic, and the precedence case — all identical.

  **The selection cuts elements, not events**, and that is a physics decision rather than a detail.
  `Jet.PT > 5` on a jagged branch is a boolean per jet; filtering whole events would give a
  different and entirely plausible answer. Both engines apply it as a mask, and a test checks no
  entry below the cut survives.

  **Two findings.**

  - **`BinnedEstimate1D`, not `Histo1D`** — a departure from 12 §3's wording, for a reason that did
    not exist when it was written. YODA 2 splits a fillable accumulator (`Histo1D`) from a finished
    value with uncertainties (`BinnedEstimate1D`), and this project's plot pipeline recognises only
    the latter (`plot/io.is_binned_1d`). A derived histogram is finished the moment it is filled, so
    writing a `Histo1D` produced a file that was correct, summed correctly, and was **silently
    skipped by every plotting path** — the opposite of 12 §2.2's "treat it like any other result".
    Caught by the Plots row, which is why that row is in the step.
  - **`hep proc --only` was destructive.** It rewrote the whole `fits.json` and `proc.yoda` with
    just the entry it ran, so retuning one fit of five threw the other four away. Found by a
    *test-ordering* failure — the only way it shows up — and fixed: `--only` now merges, keeping
    what it did not recompute, while a full run still replaces so that what is on disk is exactly
    what the config says.

  **Deviations.** `[[proc.hist]]` gained `engine` (the schema had the block but not the key) and
  `source` now defaults to `"delphes"`, meaning the group's own `delphes.root`. Branch names are
  accepted in either spelling — Delphes writes `Jet.PT`, a plain ROOT tree writes `Jet_PT` — because
  which one a file uses is the file's business. Expressions may only call a fixed list of functions
  that mean the same thing to C++ and to numpy; anything else is refused by name rather than failing
  on one engine only.
