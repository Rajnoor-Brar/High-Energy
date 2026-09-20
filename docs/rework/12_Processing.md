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

- **Backends** share one interface: `fit(hist, model, range, init, limits) → Result(params, errors, cov, chi2, ndf, status)`.
  - `minuit2`: PyROOT `ROOT.Math.Minimizer` (Minuit2).
  - `roofit`: PyROOT RooFit, for extended likelihood and composite PDFs.
  - `scipy`: `scipy.optimize.curve_fit` or `minimize` (scipy 1.18 is installed). This is the fallback when PyROOT is missing, and it is reported in the output.
- **Model library:** a small Python registry. Each model knows its parameter names, its ROOT `TF1` formula and a NumPy callable, so every backend evaluates the same function.
- **Voided bins** (07 §4): NaN bins are excluded from the fit.

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
  - `uproot`: `uproot` + `awkward` + `hist` (all installed).
  - Both must give identical bins (tested in P9-S02).
- **Output:** YODA `Histo1D`/`Histo2D` in `proc.yoda` under `/PROC/<name>`, so `hep plot` treats it like any other result.

## 3. Outputs

```
results/<project>/studies/<study>/proc/
  fits.json          parameters, errors, covariance, chi2/ndf, status, backend, input hashes
  proc.yoda          /PROC/<fit>/curve (Estimate1D of the fitted function), /PROC/<hist>
  proc.root          optional (keep_root = true): RooFitResult, TF1, workspace — for deeper inspection only
  proc.log
```

- **Plotting:** `hep plot` overlays `/PROC/<fit>/curve` on its target histogram when `[plot].show_fits = true`.
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
