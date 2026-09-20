"""The RooFit backend, for the fits the other two cannot express (12 §2.1).

Minuit2 and scipy both minimise a χ² or a binned Poisson likelihood over a fixed function. RooFit
exists here for what that leaves out: an **extended** likelihood, where the total yield is itself a
fitted parameter rather than a normalisation fixed by the histogram.

It is built with `RooGenericPdf` from the model's `TF1` spelling — the one place that spelling is
used for fitting rather than for display — because a `RooGenericPdf` takes a formula and this is the
backend whose job is to be RooFit rather than to be interchangeable. That means a model must have a
formula; the `expr` escape hatch works here for exactly the same reason it does not work with scipy.

Not the default, and `auto` reaches Minuit2 first: a RooFit result is a PDF fit, so its `amp`-like
parameters mean something different from the other backends' and the two are not comparable
parameter by parameter. Ask for it deliberately.
"""

from __future__ import annotations

import math
import re
from typing import Any

from ...errors import HepError
from . import Points, Result, chi2_of, starting_values, bounds_of


def available() -> bool:
    try:
        import ROOT
        return bool(hasattr(ROOT, "RooRealVar"))
    except Exception:
        return False


def _roofit_formula(formula: str, count: int) -> str:
    """`TF1` spelling → `RooGenericPdf` spelling.

    `[0]` becomes `@1` (`@0` is the observable), `x` becomes `@0`, and `^` becomes `pow`. Everything
    else is already common to both.
    """
    text = re.sub(r"\[(\d+)\]", lambda m: f"@{int(m.group(1)) + 1}", formula)
    text = re.sub(r"\bx\b", "@0", text)
    # `a^b` → `pow(a,b)` for the simple operand shapes the model library produces.
    while "^" in text:
        text = re.sub(r"([\w@.\)\]]+|\([^()]*\))\s*\^\s*([\w@.\(]+|\([^()]*\))",
                      r"pow(\1,\2)", text, count=1)
    return text


def fit(model, points: Points, *, init=None, limits=None, likelihood: str = "chi2") -> Result:
    import ROOT

    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)

    start = starting_values(model, points, init or {})
    bounds = bounds_of(model, limits or {})
    count = len(model.names)

    low = float(min(points.x - points.widths / 2.0))
    high = float(max(points.x + points.widths / 2.0))
    observable = ROOT.RooRealVar("x", "x", low, high)

    variables = []
    for index, name in enumerate(model.names):
        lower, upper = bounds[index]
        if not math.isfinite(lower):
            lower = start[index] - 10.0 * max(abs(start[index]), 1.0)
        if not math.isfinite(upper):
            upper = start[index] + 10.0 * max(abs(start[index]), 1.0)
        variables.append(ROOT.RooRealVar(name, name, start[index], lower, upper))

    arguments = ROOT.RooArgList(observable)
    for variable in variables:
        arguments.add(variable)
    pdf = ROOT.RooGenericPdf("model", _roofit_formula(model.formula(), count), arguments)

    # The histogram, as RooFit sees it: counts, so the likelihood is the Poisson one it is built for.
    histogram = ROOT.TH1D("proc_fit_input", "", len(points.x), low, high)
    for index in range(len(points.x)):
        histogram.SetBinContent(index + 1, float(points.y[index] * points.widths[index]))
        histogram.SetBinError(index + 1, float(points.error[index] * points.widths[index]))
    data = ROOT.RooDataHist("data", "data", ROOT.RooArgList(observable), histogram)

    outcome = pdf.fitTo(data, ROOT.RooFit.Save(True), ROOT.RooFit.PrintLevel(-1),
                        ROOT.RooFit.SumW2Error(True))

    values = [float(variable.getVal()) for variable in variables]
    errors = [float(variable.getError()) for variable in variables]
    covariance = [[float(outcome.covarianceMatrix()[row][column]) for column in range(count)]
                  for row in range(count)] if outcome else []
    converged = bool(outcome) and outcome.status() == 0

    return Result(
        params=dict(zip(model.names, values)),
        errors=dict(zip(model.names, errors)),
        covariance=covariance,
        chi2=chi2_of(model, points, values),
        ndf=max(len(points) - count, 0),
        status="ok" if converged else f"did not converge (RooFit status "
                                      f"{outcome.status() if outcome else '?'})",
        backend="roofit",
        message="RooGenericPdf, extended = false",
        valid=converged,
    )
