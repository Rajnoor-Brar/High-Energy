"""The Minuit2 backend, through `ROOT::Math::Minimizer` (12 §2.1).

**It minimises the same Python function scipy does.** The obvious way to fit with ROOT is to build a
`TF1` from a formula string and call `TH1::Fit`; this does not, because then the two backends would
be fitting two *transcriptions* of the model and "do the backends agree" would be asking whether
someone typed the formula twice correctly. Driving `ROOT::Math::Minimizer` with a
`ROOT::Math::Functor` that wraps the model's own NumPy callable means the objective is byte-identical
between backends, so a disagreement is a disagreement between **minimisers**, which is the thing
worth measuring.

The cost is one Python call per Migrad step. For the fits this project does — tens of parameters at
most, hundreds of bins — that is milliseconds, and the clarity is worth more.

**Two lifetime traps**, both of which crash rather than fail:

  * the `Functor` and the Python callable it wraps must outlive the minimiser, so both are held in
    locals until `Minimize()` has returned;
  * `Minimizer::X()` returns a bare `const double*` with no length. Indexing it is fine; handing it
    to `list()` or iterating it reads past the end and segfaults. Every read below is indexed.
"""

from __future__ import annotations

import math
from typing import Any

from ...errors import HepError
from . import Points, Result, bounds_of, chi2_of, objective, starting_values


def available() -> bool:
    """Whether PyROOT is importable *and* Minuit2 is in this build."""
    try:
        import ROOT
    except Exception:
        return False
    try:
        minimizer = ROOT.Math.Factory.CreateMinimizer("Minuit2", "Migrad")
        return bool(minimizer)
    except Exception:                                  # pragma: no cover - a ROOT without Minuit2
        return False


def fit(model, points: Points, *, init=None, limits=None, likelihood: str = "chi2") -> Result:
    import ROOT

    start = starting_values(model, points, init or {})
    bounds = bounds_of(model, limits or {})
    cost = objective(model, points, likelihood)
    count = len(model.names)

    def evaluate(values: Any) -> float:
        # `values` is a const double*; the number of parameters is known, so read exactly that many.
        current = [float(values[index]) for index in range(count)]
        answer = cost(current)
        # Migrad walks into regions where a model is undefined; a NaN there ends the fit with no
        # message at all, so it is reported as "very bad" instead and the minimiser turns around.
        return answer if math.isfinite(answer) else 1e300

    functor = ROOT.Math.Functor(evaluate, count)
    minimizer = ROOT.Math.Factory.CreateMinimizer("Minuit2", "Migrad")
    if not minimizer:                                  # pragma: no cover - checked by available()
        raise HepError("this ROOT has no Minuit2", hint="use --backend scipy")
    minimizer.SetFunction(functor)
    minimizer.SetMaxFunctionCalls(100000)
    minimizer.SetMaxIterations(10000)
    minimizer.SetTolerance(1e-4)
    minimizer.SetPrintLevel(0)
    # χ² and −2 lnL are both twice the negative log-likelihood, so one unit of the objective is one
    # σ² — which is exactly what an error definition of 1 means.
    minimizer.SetErrorDef(1.0)

    for index, name in enumerate(model.names):
        low, high = bounds[index]
        step = max(abs(start[index]) * 0.1, 1e-3)
        if math.isfinite(low) and math.isfinite(high):
            minimizer.SetLimitedVariable(index, name, start[index], step, low, high)
        elif math.isfinite(low):
            minimizer.SetLowerLimitedVariable(index, name, start[index], step, low)
        elif math.isfinite(high):
            minimizer.SetUpperLimitedVariable(index, name, start[index], step, high)
        else:
            minimizer.SetVariable(index, name, start[index], step)

    converged = bool(minimizer.Minimize())
    values = [float(minimizer.X()[index]) for index in range(count)]
    errors = [float(minimizer.Errors()[index]) for index in range(count)]
    covariance = [[float(minimizer.CovMatrix(row, column)) for column in range(count)]
                  for row in range(count)]

    status = minimizer.Status()
    return Result(
        params=dict(zip(model.names, values)),
        errors=dict(zip(model.names, errors)),
        covariance=covariance,
        chi2=chi2_of(model, points, values),
        ndf=max(len(points) - count, 0),
        status="ok" if converged else f"did not converge (Minuit2 status {status})",
        backend="minuit2",
        message=f"edm={minimizer.Edm():.3g}, calls={minimizer.NCalls()}",
        valid=converged,
    )
