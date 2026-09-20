"""The scipy backend: always available, and the fallback when PyROOT is not (12 §2.1).

**Two algorithms, because a χ² is not a general minimisation.** A χ² fit is a nonlinear
least-squares problem, and `least_squares` (trust-region reflective) exploits that: it works on the
residual vector, builds its own Jacobian, and is insensitive to the parameters having wildly
different magnitudes. A general minimiser is not. P9-S01 measured the difference on a Gaussian peak
whose amplitude is ~1e5 and whose width is ~2e-3: `L-BFGS-B` stopped early at **χ²/ndf = 12.5**,
with the background parameters 4-5σ from truth, while `least_squares` and Minuit2 both land at
χ²/ndf ≈ 0.8. Scaling, not tolerance — which is why the fix is the right algorithm rather than a
smaller `ftol`.

A Poisson likelihood is not a sum of squares, so that one does go through `minimize`, with tight
tolerances and the covariance from a numerical Hessian.
"""

from __future__ import annotations

import math
from typing import Any

from ...errors import HepError
from . import Points, Result, bounds_of, chi2_of, objective, starting_values

try:
    import numpy as np
except ImportError:                                    # pragma: no cover - part of the venv
    np = None


def available() -> bool:
    try:
        import scipy.optimize  # noqa: F401
        return np is not None
    except ImportError:
        return False


def fit(model, points: Points, *, init=None, limits=None, likelihood: str = "chi2") -> Result:
    start = starting_values(model, points, init or {})
    bounds = bounds_of(model, limits or {})
    cost = objective(model, points, likelihood)

    if likelihood == "poisson":
        values, success, message, covariance = _minimise(cost, start, bounds)
    else:
        values, success, message, covariance = _least_squares(model, points, start, bounds)

    if not covariance:
        covariance = _covariance(cost, values, likelihood)
    errors = [math.sqrt(covariance[index][index])
              if covariance and covariance[index][index] > 0 else float("nan")
              for index in range(len(values))]

    return Result(
        params=dict(zip(model.names, values)),
        errors=dict(zip(model.names, errors)),
        covariance=covariance,
        chi2=chi2_of(model, points, values),
        ndf=max(len(points) - len(values), 0),
        status="ok" if success else "did not converge",
        backend="scipy",
        message=message,
        valid=bool(success),
    )


def _least_squares(model, points: Points, start, bounds):
    """χ²: the residual vector, its own Jacobian, and cov = (JᵀJ)⁻¹."""
    from scipy.optimize import least_squares

    def residual(values):
        return (points.y - model(points.x, *values)) / points.error

    low = [pair[0] for pair in bounds]
    high = [pair[1] for pair in bounds]
    # `least_squares` wants the start strictly inside the bounds, and a guess on a boundary is easy
    # to produce (`limits = { sigma = [0.0001, 0.02] }` with a guess of 0.02).
    clamped = [min(max(value, l + abs(l) * 1e-9 if math.isfinite(l) else value),
                   h - abs(h) * 1e-9 if math.isfinite(h) else value)
               for value, l, h in zip(start, low, high)]
    outcome = least_squares(residual, clamped, bounds=(low, high), method="trf",
                            xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=100000)
    values = [float(value) for value in outcome.x]

    covariance: list[list[float]] = []
    try:
        jacobian = outcome.jac
        # The residuals are already divided by the uncertainty, so JᵀJ *is* the inverse covariance:
        # no extra χ²/ndf rescaling, which would silently absorb a bad fit into the errors.
        inverse = np.linalg.inv(jacobian.T @ jacobian)
        if np.all(np.isfinite(inverse)):
            covariance = [[float(value) for value in row] for row in inverse]
    except Exception:
        covariance = []
    return values, outcome.success, str(outcome.message), covariance


def _minimise(cost, start, bounds):
    """Anything that is not a sum of squares."""
    from scipy.optimize import minimize

    outcome = minimize(cost, start, method="L-BFGS-B",
                       bounds=[(None if low == -math.inf else low,
                                None if high == math.inf else high) for low, high in bounds],
                       options={"ftol": 1e-14, "gtol": 1e-12, "maxiter": 100000})
    return ([float(value) for value in outcome.x], bool(outcome.success),
            str(getattr(outcome, "message", "")), [])


def _covariance(cost, values: list[float], likelihood: str) -> list[list[float]]:
    """The inverse Hessian of the cost, scaled so the result is a parameter covariance.

    χ² and −2 ln L are both *twice* the negative log-likelihood, so the covariance is 2 H⁻¹ where H
    is the Hessian of the cost. Numerical, by central differences: the models are cheap and an
    analytic Hessian per model would be six more things to get wrong.
    """
    if np is None:                                     # pragma: no cover
        return []
    count = len(values)
    if count == 0:
        return []
    centre = np.asarray(values, dtype=float)
    step = np.maximum(np.abs(centre) * 1e-4, 1e-7)
    hessian = np.zeros((count, count), dtype=float)
    for row in range(count):
        for column in range(row, count):
            shifted = centre.copy()
            if row == column:
                base = cost(shifted)
                shifted[row] = centre[row] + step[row]
                plus = cost(shifted)
                shifted[row] = centre[row] - step[row]
                minus = cost(shifted)
                hessian[row][row] = (plus - 2.0 * base + minus) / (step[row] ** 2)
            else:
                def at(first: float, second: float) -> float:
                    point = centre.copy()
                    point[row] += first * step[row]
                    point[column] += second * step[column]
                    return cost(point)

                hessian[row][column] = hessian[column][row] = (
                    at(1, 1) - at(1, -1) - at(-1, 1) + at(-1, -1)
                ) / (4.0 * step[row] * step[column])
    try:
        inverse = np.linalg.inv(hessian)
    except np.linalg.LinAlgError:
        return []
    matrix = 2.0 * inverse
    if not np.all(np.isfinite(matrix)):
        return []
    return [[float(value) for value in row] for row in matrix]
