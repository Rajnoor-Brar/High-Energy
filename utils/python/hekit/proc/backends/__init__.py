"""Fitting backends, behind one interface (12 §2.1).

Every backend takes the same thing — points, a `Model`, initial values, limits — and returns the same
`Result`. That is what lets `hep proc --backend` be a real choice rather than three commands, and
what makes "minuit2 and scipy agree to 1e-3" a check worth running.

**The data is prepared once, here, not per backend.** Which bins are inside the range, which are
voided (07 §4: a NaN bin is a bin that was deliberately blanked, and fitting it would be fitting a
hole), and which have no error to divide by — all of that is a property of the histogram, not of the
minimiser, and doing it three times is three chances to do it differently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from ...errors import HepError

try:
    import numpy as np
except ImportError:                                    # pragma: no cover - part of the venv
    np = None


#: Backends in the order `auto` tries them. ROOT first when it is importable, because Minuit2 is what
#: the rest of the field uses and its errors are the ones a reader will expect.
ORDER = ("minuit2", "roofit", "scipy")


@dataclass
class Points:
    """The bins a fit actually sees."""

    x: Any                      # bin centres
    y: Any                      # heights
    error: Any                  # uncertainties, already guarded against zero
    widths: Any                 # bin widths, for a poisson likelihood and for drawing
    used: int = 0               # bins kept
    dropped: int = 0            # bins inside the range that were voided or unusable

    def __len__(self) -> int:
        return int(len(self.x))


@dataclass
class Result:
    """What every backend returns."""

    params: dict[str, float]
    errors: dict[str, float]
    covariance: list[list[float]] = field(default_factory=list)
    chi2: float = float("nan")
    ndf: int = 0
    status: str = "ok"
    backend: str = ""
    message: str = ""
    valid: bool = True

    @property
    def chi2_per_ndf(self) -> float:
        return self.chi2 / self.ndf if self.ndf > 0 else float("nan")

    def values(self, names: Sequence[str]) -> tuple[float, ...]:
        return tuple(float(self.params[name]) for name in names)


def prepare(x, y, error, widths, *, window: Sequence[float] | None = None) -> Points:
    """The bins inside the range that can be fitted, and a count of those that cannot.

    Dropped, and counted rather than silently skipped:

      * **voided bins** — NaN, which 07 §4 uses to mean "blanked on purpose". A fitter that treats
        NaN as data returns NaN parameters and a NaN χ², which looks like a broken fit rather than
        a bad input;
      * **bins with no uncertainty** — a zero error is an infinite weight, so one empty bin would
        otherwise dominate the whole fit.
    """
    if np is None:                                     # pragma: no cover - part of the venv
        raise HepError("fitting needs numpy")
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    error = np.asarray(error, dtype=float)
    widths = np.asarray(widths, dtype=float)

    inside = np.ones_like(x, dtype=bool)
    if window is not None and len(window) == 2:
        low, high = float(window[0]), float(window[1])
        if not high > low:
            raise HepError(f"the fit range [{low}, {high}] is empty",
                           hint="range = [low, high], low < high")
        inside = (x >= low) & (x <= high)

    candidates = int(np.count_nonzero(inside))
    usable = inside & np.isfinite(x) & np.isfinite(y) & np.isfinite(error) & (error > 0)
    kept = int(np.count_nonzero(usable))
    if kept == 0:
        raise HepError("no bins left to fit",
                       hint=f"{candidates} bins are in range; they are empty, voided (07 §4) "
                            "or have no uncertainty")
    return Points(x=x[usable], y=y[usable], error=error[usable], widths=widths[usable],
                  used=kept, dropped=candidates - kept)


def chi2_of(model, points: Points, values: Sequence[float]) -> float:
    """χ² of a parameter set. The objective every backend minimises, so they minimise one thing."""
    predicted = model(points.x, *values)
    residual = (points.y - predicted) / points.error
    return float(np.sum(residual * residual))


def poisson_of(model, points: Points, values: Sequence[float]) -> float:
    """−2 ln L for binned Poisson counts, up to a constant.

    Heights are densities, so the expected *count* in a bin is height × width. Bins whose expectation
    goes non-positive are pushed to a tiny positive number rather than producing a NaN: a minimiser
    that wanders there should be told the answer is bad, not handed an undefined one.
    """
    predicted = np.maximum(model(points.x, *values) * points.widths, 1e-12)
    observed = np.maximum(points.y * points.widths, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = predicted - observed + np.where(observed > 0,
                                               observed * np.log(observed / predicted), 0.0)
    return float(2.0 * np.sum(term))


def objective(model, points: Points, likelihood: str):
    """The function a backend minimises, chosen once."""
    if likelihood == "poisson":
        return lambda values: poisson_of(model, points, values)
    return lambda values: chi2_of(model, points, values)


def starting_values(model, points: Points, init: dict[str, float]) -> list[float]:
    """The model's own guess, overridden by whatever the config named."""
    values = list(model.guess(points.x, points.y))
    for name, value in (init or {}).items():
        values[model.index(name)] = float(value)
    return [float(value) if math.isfinite(float(value)) else 0.0 for value in values]


def bounds_of(model, limits: dict[str, Sequence[float]]) -> list[tuple[float, float]]:
    """Per-parameter bounds, unbounded where the config says nothing."""
    made = [(-math.inf, math.inf) for _ in model.names]
    for name, pair in (limits or {}).items():
        if len(pair) != 2:
            raise HepError(f"limits.{name} must be [low, high]")
        low, high = float(pair[0]), float(pair[1])
        if not high > low:
            raise HepError(f"limits.{name} = [{low}, {high}] is empty")
        made[model.index(name)] = (low, high)
    return made


def load(name: str):
    """One backend module by name."""
    from importlib import import_module

    if name not in ORDER:
        raise HepError(f"no fitting backend called {name!r}",
                       hint="one of: " + ", ".join(ORDER))
    return import_module(f".{name}", __name__)


def available(name: str) -> bool:
    """Whether this backend can run here. Never raises: `auto` asks it about each in turn."""
    try:
        return bool(load(name).available())
    except Exception:                                  # pragma: no cover - a broken backend
        return False


def choose(preference: str = "auto") -> str:
    """The backend to use, and the reason it is that one.

    `auto` prefers Minuit2 because it is what the field uses, and falls back to scipy when PyROOT is
    not importable — which is reported in the output rather than being a silent substitution, since
    "which fitter produced this number" is exactly the sort of thing that goes unrecorded and is then
    unanswerable six months later.
    """
    if preference and preference != "auto":
        if not available(preference):
            raise HepError(f"the {preference} backend is not available here",
                           hint="PyROOT is needed for minuit2 and roofit; "
                                "use --backend scipy, or backend = \"scipy\"")
        return preference
    for name in ORDER:
        if available(name):
            return name
    raise HepError("no fitting backend is available",
                   hint="install scipy, or make PyROOT importable")
