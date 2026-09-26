# 12 — Processing layer (ROOT)

Date: 2026-09-17 · Status: Proposed · Steps: P9-S01, P9-S02

**Decision D15.** ROOT is used to **compute** — fits, statistics, columnar processing. It is **not** where events or results are stored:
- **Events** are stored as HepMC3 (11).
- **Results** are stored as YODA (07).
- **Exception:** the ROOT trees Delphes writes, which are that tool's own output format.

## 1. Where ROOT is used, and where it is not

| Stage | ROOT? | Why |
|---|---|---|
| Event loop (`hep-run`, modules) | **No** by default | Modules book YODA; kinematics come from `Phys`. This avoids ROOT global state (`gDirectory`, `gStyle`, thread-safety set-up) and a heavy link. `hep-run` links ROOT only when in-process Delphes is built (deferred). |
| Event storage | **No** | HepMC3 store (D13) |
| Result storage | **No** (optional exports only) | YODA is the single format (D14). `yoda2root` is available on request. |
| Post-run fits and statistics | **Yes** | Minuit2 / RooFit are the strongest fitters available here |
| Delphes output analysis | **Yes** | RDataFrame over `delphes.root` |
| Plotting | **No** | `rivet-mkhtml` + mplhep (07). Paint is retired. |
| Interactive inspection | Optional | `root`, `TBrowser` for Delphes files and exports |

**Prerequisite.** `import ROOT` must work in the venv. P0-S02 adds `$HEP_INSTALL/root/lib` to `PYTHONPATH`, and `hep doctor` checks it.

## 2. `hep proc`

```
hep proc CONFIG [selectors…] [--only NAME] [--backend auto|minuit2|roofit|scipy]
```

- **Inputs:** results that `hep run` has already produced (group `analysis.yoda` files, `delphes.root`).
- **Outputs:** written into the study directory (07 §1).
- **Idempotence:** re-running with unchanged inputs and config is a no-op (hash check, like points).
- **`--only NAME` merges.** It recomputes that one entry and **keeps** the others already in `fits.json` and `proc.yoda`, because "redo just this fit" should not discard the other four. A full run writes the complete set and replaces, so what is on disk is then exactly what the config says.

### 2.1 Fits

```toml
[[proc.fit]]
name     = "lambda_peak"                    # output key
target   = "/mymodule/m_ppi"                # YODA path (variant options allowed: "/photo_eic:R=0.4/d01-x01-y01")
points   = "all"                            # or a list of point names / a page
model    = "gauss + poly2"                  # built-in library: gauss, crystalball, breitwigner, voigt, expo, polyN, threshold
# expr   = "[0]*exp(-0.5*((x-[1])/[2])**2) + [3]"   # alternative: explicit formula
range    = [1.08, 1.16]
init     = { mean = 1.1157, sigma = 0.002 }
limits   = { sigma = [0.0001, 0.02] }
backend  = "auto"                           # auto → minuit2 if PyROOT importable, else scipy
likelihood = "chi2"                         # chi2 | poisson (binned)
```

- **Backends** share one interface: `fit(model, points, init, limits, likelihood) → Result(params, errors, cov, chi2, ndf, status, backend)`.
  - `minuit2`: PyROOT `ROOT.Math.Minimizer` (Minuit2), driven with a `ROOT::Math::Functor` that wraps **the model's own NumPy callable** — not a `TF1`. So Minuit2 and scipy minimise a byte-identical objective and "do the backends agree" is a question about minimisers rather than about transcribing a formula twice. Measured in P9-S01: **3.9 × 10⁻⁶** worst relative difference over five parameters.
  - `roofit`: PyROOT RooFit, for extended likelihood and composite PDFs. This is the one backend that *does* use the `TF1` spelling (through `RooGenericPdf`), and its parameters are not comparable to the others' term by term.
  - `scipy`: **`least_squares` for a χ²** and `minimize` for a Poisson likelihood. The split matters: a χ² is a nonlinear least-squares problem, and a general minimiser handles the parameter scaling badly. P9-S01 measured `L-BFGS-B` stopping at χ²/ndf = 12.5 with 5σ biases where `least_squares` and Minuit2 both reach χ²/ndf ≈ 0.8. This is the fallback when PyROOT is missing, and it is reported in the output rather than substituted silently.
- **Model library:** a small Python registry — `gauss`, `breitwigner`, `crystalball`, `voigt`, `expo`, `polyN`, `threshold`. Each knows its **parameter names** (so a config writes `init = { mean = … }` and not `[1] = …`), a NumPy callable and a `TF1` formula. Composition is `+`; repeated components are numbered (`gauss1.mean`), and a lone one keeps the plain name.
- **Initial guesses are read off the data**, background terms first so a peak's guess is made against what the background has not already explained. A Gaussian started on the wrong side of a peak converges somewhere plausible and wrong.
- **Voided bins** (07 §4): NaN bins are excluded from the fit, and so are bins with no uncertainty — a zero error is an infinite weight. Both are *counted*, and the count is in `fits.json`.
- **What is being fitted matters.** A `Histo1D` bin carries `sumW`, a sum over the bin, so the fit uses `sumW / width`; a **`BinnedEstimate1D`** — which is what a finalized Rivet analysis writes, and so what nearly every fit targets — carries `val()`, already finished, and must **not** be divided again. On a uniform binning that error is a constant factor, so the fit still converges and the amplitude is quietly wrong.

### 2.2 Derived histograms on Delphes output

```toml
[[proc.hist]]
name   = "jet_pt"
source = "delphes"                          # the group's delphes.root
tree   = "Delphes"
expr   = "Jet.PT"
cut    = "Jet.PT > 5 && abs(Jet.Eta) < 3.5"
bins   = [40, 0, 80]
engine = "auto"                             # auto → rdf if PyROOT, else uproot+hist
```

- **Engines:**
  - `rdf`: `ROOT.RDataFrame` with `EnableImplicitMT`.
  - `uproot`: `uproot` + `awkward` (both installed).
  - Both must give identical bins (measured in P9-S02: identical on every expression tested, including the precedence case below).
- **The selection cuts *elements*, not events.** A Delphes branch is jagged, so `Jet.PT > 5` is a boolean per jet; what the config means is "the jets that pass", not "the events in which one does". Both engines apply it as an element mask (`Jet.PT[cut]`), never as an event filter.
- **One expression language, translated once.** RDF compiles C++ and uproot evaluates Python, so `&&`, `||` and `!` have to be converted — and the trap is that Python's `&` binds **tighter** than a comparison, so rewriting the text turns `a > 5 && b < 3` into `a > (5 & b) < 3`: valid, different, silent. The translation therefore goes through Python's own parser and rewrites `and`/`or`/`not` as **tree nodes**, where precedence is structural. Calls are restricted to a list that means the same thing on both sides (`abs`, `sqrt`, `log`, `log10`, `exp`, `sin`, `cos`, `tan`, `min`, `max`).
- **Branch spelling is the file's business:** Delphes writes `Jet.PT`, a plain ROOT tree writes `Jet_PT`, and a config may use either.
- **Output:** `/PROC/<name>` in `proc.yoda` — a **`BinnedEstimate1D`**, not a `Histo1D`. YODA 2 splits the two: a `Histo1D` is a fillable accumulator and an estimate is a *finished* value with uncertainties, which is what a finalized Rivet analysis writes and what the plot pipeline recognises. A derived histogram is finished the moment it is filled, and writing a `Histo1D` would give a file that is correct, sums correctly, and is silently skipped by every plotting path.
- **On a page** a derived histogram is its *own* figure — unlike a fitted curve, which is an overlay on the histogram it was fitted to.

## 3. Outputs

```
results/<project>/studies/<study>/proc/
  fits.json          parameters, errors, covariance, chi2/ndf, status, backend, input hashes
  proc.yoda          /PROC/<fit>/curve (Estimate1D of the fitted function), /PROC/<hist>
  proc.root          optional (keep_root = true): RooFitResult, TF1, workspace — for deeper inspection only
  proc.log
```

- **Plotting:** `hep plot` overlays `/PROC/<fit>/curve` on its target histogram when `[plot].show_fits = true`. The curve is **renamed to its target** on a copy — a plotter overlays objects whose paths match, and `/PROC/peak/curve` matches nothing. When several points on a page were each fitted, their curves are kept apart by an analysis option (`/photo_eic:fit=<point>/…`), which `io.plot_key` strips, so they all land on the one figure instead of overwriting each other.
- **Tables:** `hep compare` and `hep show` print fit tables from `fits.json`.
- **Provenance:** each entry records the input YODA sha256, the proc config hash, the backend and version, and PyROOT availability.

## 4. Design notes

- **One statistics module.** χ²/ndf, pulls and aligned-bin handling are shared by `hep compare` (07 §5) and `hep proc`, in `hekit.results.stats`.
- **No ROOT import at start-up.** `import ROOT` is slow and prints banners, so it is imported lazily inside the backend, never at `hep` start-up.
- **Thread use.** PyROOT runs in the `hep` process for fits (cheap). Heavy RDF jobs run as a supervised stage (a subprocess), so the dashboard stays responsive and a crash stays contained.
- **Deferred:** ROOT-native canvases (a `backend = "root"` for `hep plot`). Add one only if publication needs require it (10 §4).

## 5. Not in scope
- Unfolding (RooUnfold is not installed).
- TMVA (ONNX Runtime covers inference; 05 §6).
- Storing per-candidate tables (decision D-DERIVED is deferred; P8-S04 records the options, their
  dependency cost here, and the revisit trigger — the first ML training dataset).
