"""Fitting: the model library, the backends, and whether they find the right answer (P9-S01, 12 §2.1).

Three of this step's four Verification rows live here.

**Recovery** is checked against a synthetic spectrum whose true parameters are known — a Gaussian
peak on a falling linear background, Poisson-fluctuated. The assertion is on **pulls**, (fitted −
true) / error, not on the values: a fit that recovers the mean to four decimals but claims an
uncertainty ten times too small is wrong in the way that matters, and only a pull notices. One seed
asserts |pull| ≤ 3 — a real failure moves them much further than that, and the P9-S01 log records a
broken minimiser producing 4.9σ — while a sweep over twenty seeds checks the pull *distribution* is
unit-width, which is the statement "the errors mean what they say".

**Backends agree** compares Minuit2 with scipy on the same data. It is a statement about minimisers
rather than about transcription, because both drive the same Python callable (see
`backends/minuit2.py`).

**Fallback** makes `import ROOT` fail and checks `auto` reaches scipy — by breaking the import
itself rather than by stubbing `available()`, since the thing being tested is that a missing PyROOT
is survivable.
"""

from __future__ import annotations

import builtins
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "utils" / "python"))

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from hekit.errors import HepError                                        # noqa: E402
from hekit.proc import backends, models                                  # noqa: E402

TRUE = {"amp": 90000.0, "mean": 1.1157, "sigma": 0.0025,
        "p0": 30000.0, "p1": -20000.0}
LOW, HIGH, BINS = 1.08, 1.16, 60


def spectrum(seed: int):
    """A Gaussian peak on a falling background, Poisson-fluctuated, as fittable points."""
    edges = np.linspace(LOW, HIGH, BINS + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    width = float(edges[1] - edges[0])
    density = (TRUE["amp"] * np.exp(-0.5 * ((centres - TRUE["mean"]) / TRUE["sigma"]) ** 2)
               + TRUE["p0"] + TRUE["p1"] * centres)
    counts = np.random.default_rng(seed).poisson(np.maximum(density * width, 0.0))
    # Heights and their uncertainties, as a histogram would carry them.
    heights = counts / width
    errors = np.sqrt(np.maximum(counts, 1.0)) / width
    widths = np.full_like(centres, width)
    return backends.prepare(centres, heights, errors, widths, window=(LOW, HIGH))


def pulls(result, names=("amp", "mean", "sigma", "p0", "p1")) -> dict[str, float]:
    made = {}
    for name in names:
        error = result.errors.get(name, float("nan"))
        if not error or not math.isfinite(error) or error <= 0:
            made[name] = float("nan")
        else:
            made[name] = (result.params[name] - TRUE[name]) / error
    return made


# ── the model library ────────────────────────────────────────────────────────

def test_a_model_is_parsed_into_named_parameters():
    model = models.parse("gauss + poly1")
    assert model.names == ("amp", "mean", "sigma", "p0", "p1")
    assert model.index("sigma") == 2
    with pytest.raises(HepError):
        model.index("nonsense")


def test_repeated_components_are_numbered():
    """`mean` is what a person writes when there is one peak; two need telling apart."""
    model = models.parse("gauss + gauss")
    assert model.names == ("gauss1.amp", "gauss1.mean", "gauss1.sigma",
                           "gauss2.amp", "gauss2.mean", "gauss2.sigma")


def test_unknown_models_say_what_there_is():
    with pytest.raises(HepError) as raised:
        models.parse("parabola")
    assert "gauss" in str(raised.value)
    with pytest.raises(HepError):
        models.parse("poly99")


def test_a_model_evaluates_as_the_sum_of_its_parts():
    model = models.parse("gauss + poly1")
    x = np.array([1.0, 2.0, 3.0])
    got = model(x, 2.0, 2.0, 1.0, 5.0, 0.5)
    expected = 2.0 * np.exp(-0.5 * ((x - 2.0) / 1.0) ** 2) + 5.0 + 0.5 * x
    assert np.allclose(got, expected)


def test_every_builtin_has_a_formula_and_evaluates():
    """A component with a broken NumPy callable or formula is caught here, not in a run."""
    x = np.linspace(0.5, 3.0, 12)
    for name in list(models.BUILTIN) + ["poly0", "poly3"]:
        model = models.parse(name)
        values = model.guess(x, np.exp(-x) + 1.0)
        assert len(values) == len(model.names)
        out = np.asarray(model(x, *values), dtype=float)
        assert out.shape == x.shape
        assert np.all(np.isfinite(out)), name
        assert "[0]" in model.formula() or "@" in model.formula()


def test_an_explicit_expression_cannot_be_fitted_by_scipy():
    """It has no NumPy callable, and says so rather than guessing a translation."""
    model = models.from_expression("[0]*exp([1]*x)")
    assert model.names == ("p0", "p1")
    with pytest.raises(HepError):
        model(np.array([1.0]), 1.0, 1.0)


# ── preparing the data ───────────────────────────────────────────────────────

def test_voided_and_errorless_bins_are_dropped_and_counted():
    """07 §4: a NaN bin was blanked on purpose, and a zero error is an infinite weight."""
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([1.0, float("nan"), 3.0, 4.0, 5.0])
    error = np.array([1.0, 1.0, 0.0, 1.0, 1.0])
    points = backends.prepare(x, y, error, np.ones_like(x))
    assert points.used == 3 and points.dropped == 2


def test_a_range_selects_bins_and_an_empty_one_is_refused():
    x = np.arange(1.0, 11.0)
    points = backends.prepare(x, x, np.ones_like(x), np.ones_like(x), window=(3.0, 6.0))
    assert points.used == 4
    with pytest.raises(HepError):
        backends.prepare(x, x, np.ones_like(x), np.ones_like(x), window=(6.0, 3.0))
    with pytest.raises(HepError):
        backends.prepare(x, x, np.zeros_like(x), np.ones_like(x))


# ── Verification row: recovery ───────────────────────────────────────────────

@pytest.mark.parametrize("backend", ["scipy", "minuit2"])
def test_recovery(backend):
    if not backends.available(backend):
        pytest.skip(f"{backend} is not available here")
    model = models.parse("gauss + poly1")
    points = spectrum(7)
    result = backends.load(backend).fit(model, points, init={"mean": 1.1157, "sigma": 0.003})

    assert result.valid, result.status
    assert result.ndf == points.used - len(model.names)
    assert 0.3 < result.chi2_per_ndf < 2.0, f"chi2/ndf = {result.chi2_per_ndf}"
    for name, pull in pulls(result).items():
        assert abs(pull) < 3.0, f"{name} is {pull:.2f} sigma from truth"


def test_the_errors_mean_what_they_say():
    """The pull distribution over many seeds: centred on zero, width one.

    This is the assertion that a single fit cannot make. Errors that are uniformly half the truth
    give perfect-looking parameters and a pull RMS of 2.
    """
    model = models.parse("gauss + poly1")
    collected: list[float] = []
    for seed in range(40, 60):
        result = backends.load("scipy").fit(model, spectrum(seed),
                                            init={"mean": 1.1157, "sigma": 0.003})
        if not result.valid:
            continue
        collected.extend(value for value in pulls(result).values() if math.isfinite(value))

    assert len(collected) > 50
    values = np.array(collected)
    assert abs(float(np.mean(values))) < 0.5, "the fit is biased"
    assert 0.5 < float(np.sqrt(np.mean(values ** 2))) < 1.8, "the errors are the wrong size"


# ── Verification row: the backends agree ─────────────────────────────────────

def test_backends_agree():
    if not backends.available("minuit2"):
        pytest.skip("PyROOT is not available here")
    model = models.parse("gauss + poly1")
    points = spectrum(7)
    init = {"mean": 1.1157, "sigma": 0.003}

    one = backends.load("scipy").fit(model, points, init=init)
    two = backends.load("minuit2").fit(model, points, init=init)
    assert one.valid and two.valid

    for name in model.names:
        left, right = one.params[name], two.params[name]
        relative = abs(left - right) / max(abs(left), 1e-12)
        assert relative <= 1e-3, f"{name}: {left} vs {right} ({relative:.2e})"
    assert abs(one.chi2 - two.chi2) / max(one.chi2, 1e-12) <= 1e-3


# ── Verification row: the fallback ───────────────────────────────────────────

def test_auto_falls_back_to_scipy_without_pyroot(monkeypatch):
    """The import itself is broken, not `available()` — that is what a machine without PyROOT is."""
    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "ROOT" or name.startswith("ROOT."):
            raise ImportError("no ROOT here")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "ROOT", raising=False)
    monkeypatch.setattr(builtins, "__import__", refuse)

    assert backends.available("minuit2") is False
    assert backends.available("roofit") is False
    assert backends.available("scipy") is True
    assert backends.choose("auto") == "scipy"

    # Asking for it explicitly is an error with a way out, not a silent substitution.
    with pytest.raises(HepError) as raised:
        backends.choose("minuit2")
    assert "scipy" in str(raised.value)


def test_a_fit_reports_which_backend_ran():
    """`auto` choosing differently from run to run is only safe if the choice is recorded."""
    model = models.parse("gauss + poly1")
    result = backends.load("scipy").fit(model, spectrum(7), init={"mean": 1.1157})
    assert result.backend == "scipy"


# ── likelihoods and limits ───────────────────────────────────────────────────

def test_a_poisson_likelihood_also_recovers_the_peak():
    model = models.parse("gauss + poly1")
    result = backends.load("scipy").fit(model, spectrum(7), init={"mean": 1.1157, "sigma": 0.003},
                                        likelihood="poisson")
    assert abs(result.params["mean"] - TRUE["mean"]) < 0.002


def test_limits_are_respected():
    model = models.parse("gauss + poly1")
    result = backends.load("scipy").fit(
        model, spectrum(7), init={"mean": 1.1157},
        limits={"sigma": [0.004, 0.02]})          # deliberately excludes the true 0.0025
    assert result.params["sigma"] >= 0.004 - 1e-9


def test_a_bad_limit_is_refused():
    model = models.parse("gauss")
    points = spectrum(7)
    with pytest.raises(HepError):
        backends.load("scipy").fit(model, points, limits={"sigma": [1.0, 0.0]})
    with pytest.raises(HepError):
        backends.load("scipy").fit(model, points, limits={"nonexistent": [0.0, 1.0]})
