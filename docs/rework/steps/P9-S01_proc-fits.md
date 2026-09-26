# P9-S01 — hep proc: fits

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P9 — ROOT processing layer |
| Depends on | [P4-S04](P4-S04_compare.md) |
| Blocks | [P9-S02](P9-S02_proc-rdf-delphes.md) |
| Effort | 1.5 d |
| Findings / decisions | D15; R15; 12 §2.1 |
| Updated | 2026-09-20 |

## Goal

`hep proc` fits YODA histograms with Minuit2/RooFit (PyROOT) or scipy and writes `fits.json`, fitted curves as YODA and optional `.root`.

## Context

- PyROOT importable after P0-S02; lazy import.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `hekit/results/stats.py` | shared statistics | reuse |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/proc/{models,backends/{minuit2,roofit,scipy}}`
- `[[proc.fit]]`
- outputs + provenance
- `[plot].show_fits`

**Out (non-goals)**

- Unfolding, TMVA

## Design notes

- One model registry → ROOT TF1 formula + NumPy callable.

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- `utils/python/hekit/proc/{models,fit,outputs,cli}.py`, `proc/backends/{__init__,scipy,minuit2,roofit}.py`
- `utils/python/hekit/plot/fits.py` + `[plot].show_fits` in `page.py`, `cli.py`, both backends
- `[[proc.fit]]` gains `points`, `expr`, `limits`, `likelihood`, `keep_root`
- `tests/python/proc/test_fitting.py`, `tests/integration/test_proc.py` (ctest `proc`)

## Verification

| Check | Command | Expected | Measured |
|---|---|---|---|
| Recovery | synthetic Gaussian + background | parameters within 1σ | 4 of 5 within 0.52σ, the amplitude at 1.6σ; χ²/ndf = 0.835. Asserted as \|pull\| < 3 for one seed **plus** a pull RMS in [0.5, 1.8] over 20 seeds — the single-seed 1σ form fails ~30 % of the time by construction |
| Backends agree | minuit2 vs scipy | ≤ 1e-3 relative | **3.9 × 10⁻⁶** worst of five parameters |
| Fallback | monkeypatch ROOT import failure | scipy used and reported | `import ROOT` broken at `builtins.__import__`: `auto` → scipy, an explicit `minuit2` errors with a way out, and the command says so on stderr |
| Overlay | `hep plot` with show_fits | curve drawn | curve renamed onto its target, both points' fits on the one figure, `photo_eic_d01-x01-y01.png` drawn |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated (12 §2.1 and §3; the generated config reference)
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — **done.** All four rows measured. 17 unit tests, 10 integration tests, ctest `proc`.

  **One registry, and the backends really do fit the same function.** The obvious design — a `TF1`
  formula for ROOT and a NumPy callable for scipy — makes "do the backends agree" a question about
  whether someone transcribed a formula twice correctly. So the Minuit2 backend drives
  `ROOT::Math::Minimizer` with a `Functor` wrapping **the model's own NumPy callable**, and the two
  minimise a byte-identical objective. They agree to **3.9 × 10⁻⁶**.

  **A χ² is not a general minimisation, and that was worth a measurement.** The first scipy backend
  used `L-BFGS-B` on the objective; on a Gaussian whose amplitude is ~1e5 and whose width is ~2e-3
  it stopped at **χ²/ndf = 12.5**, with background parameters **4.9σ** from truth, while Minuit2 on
  the same data reached 0.835. Scaling, not tolerance. `least_squares` on the residual vector fixes
  it (0.835, matching Minuit2 to six figures), so the χ² path uses that and `minimize` is kept for
  the Poisson likelihood, which is not a sum of squares.

  **The recovery row as written is a flaky test.** "Parameters within 1σ" fails about 30 % of the
  time for five parameters and one seed, whatever the code does. Asserted instead as |pull| < 3 on
  a fixed seed — the broken minimiser above produced 4.9σ, so it discriminates — plus the **pull
  distribution** over 20 seeds: mean ≈ 0 and RMS in [0.5, 1.8]. That second test is the one a single
  fit cannot make: errors uniformly half their true size give perfect-looking parameters and an RMS
  of 2.

  **Two traps found by running it against real results.**

  - **A finalized Rivet object is a `BinnedEstimate1D`, not a `Histo1D`.** Its bins carry `val()`
    and `totalErrAvg()`, and the value is already finished — dividing by the bin width, which is
    exactly right for a `Histo1D`'s `sumW`, would scale the fitted amplitude by 1/width. On a
    uniform binning that is a constant, so the fit still converges and the amplitude is quietly
    wrong. `bins_of` now asks the bin which kind it is, and an integration test compares the fitted
    function against the bin values it passed through.
  - **A colon in a YODA title is unparseable.** `Title: fit: et_falloff` is not valid YAML, and YODA
    writes annotations as a YAML block — so the file writes cleanly and the *next* command fails on
    reading it.

  **The overlay needed a rename, and then a way to keep several apart.** `/PROC/<fit>/curve` says
  which fit a curve is, which is what `fits.json` wants and the wrong thing for drawing: a plotter
  overlays objects whose paths match. So `show_fits` copies each curve to its target's path. That
  collapses when several points on a page were each fitted — same path, one survivor — so each
  carries an analysis **option** (`/photo_eic:fit=<point>/…`), which `io.plot_key` strips. Both fits
  then land on the one figure, which is exactly the mechanism two option variants already use.

  **Deviations.** `[[proc.fit]]` gained the keys 12 §2.1 documents but the schema lacked (`points`,
  `expr`, `limits`, `likelihood`, `keep_root`), and `[plot]` gained `show_fits`; the generated
  config reference was regenerated with them. `hep proc --only`, `--backend`, `--out` and
  `--keep-root` are as designed. `[[proc.hist]]` is P9-S02 and untouched.
