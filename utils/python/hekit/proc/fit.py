"""Running one fit: histogram in, `Result` and a drawable curve out (12 §2.1).

This is the part that knows about YODA. The backends know about minimising and the models know about
functions; neither should have to know that a `Histo1D` keeps its heights as sums over bin widths,
or that a bin can be voided.

**Two kinds of object, and only one of them divides by the bin width.**

  * a **`Histo1D`** keeps `sumW`: a *sum of weights over the bin*. What a fit wants is the density,
    `sumW / width`, because that is what the model is a function of. Skipping the division produces
    a fit that looks right on a uniform binning and is silently wrong on a variable one — which is
    exactly the binning a physics histogram tends to have;
  * a **`BinnedEstimate1D`** — which is what a *finalized* Rivet analysis actually writes, and so
    what nearly every fit here will target — keeps `val()`: the finished number, in whatever units
    the analysis chose, already divided by the width if the analysis divided. Dividing it again
    would be wrong by a factor of the bin width, and on a uniform binning that is a constant, so the
    fit would still converge and the amplitude would quietly be wrong.

The uncertainty follows the same split: `errW()` for a histogram, `totalErrAvg()` — the symmetrised
total over every error source — for an estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..errors import HepError
from . import backends, models


@dataclass
class Curve:
    """The fitted function, sampled for drawing (12 §3)."""

    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    low: float = 0.0
    high: float = 0.0


@dataclass
class Fitted:
    """Everything one `[[proc.fit]]` entry produced."""

    name: str
    target: str
    model: str
    result: backends.Result
    curve: Curve
    bins_used: int = 0
    bins_dropped: int = 0
    point: str = ""


def is_estimate(obj: Any) -> bool:
    """Whether this is a finalized `BinnedEstimate1D` rather than a raw `Histo1D`.

    Asked of a *bin*, not of the object: YODA's class names have changed between versions and its
    binned types share a base, but a bin that has `val()` is an estimate and one that has `sumW()`
    is a histogram, in every version this project has seen.
    """
    try:
        entries = list(obj.bins())
    except Exception:
        return False
    return bool(entries) and hasattr(entries[0], "val")


def bins_of(histogram: Any) -> tuple[list[float], list[float], list[float], list[float]]:
    """Centres, values, uncertainties and widths — see the header note on which is which.

    A voided bin (07 §4) comes back as NaN and is dropped by `backends.prepare`, not here: dropping
    it silently at this level would lose the count that the fit report prints.
    """
    centres: list[float] = []
    heights: list[float] = []
    errors: list[float] = []
    widths: list[float] = []
    entries = list(histogram.bins())
    estimate = bool(entries) and hasattr(entries[0], "val")
    for entry in entries:
        width = float(entry.xMax() - entry.xMin())
        if width <= 0:
            continue
        centres.append(float(entry.xMid()))
        widths.append(width)
        try:
            if estimate:
                # Already the finished number; do **not** divide by the width.
                heights.append(float(entry.val()))
                errors.append(float(entry.totalErrAvg()))
            else:
                heights.append(float(entry.sumW()) / width)
                # `errW` is the square root of sumW2 — the uncertainty on the sum.
                errors.append(float(entry.errW()) / width)
        except Exception:
            # A voided bin (`setVal(nan)` + `rmErrs()`) or one with no error source at all: NaN, and
            # `backends.prepare` drops it and counts it.
            heights.append(float("nan"))
            errors.append(float("nan"))
    return centres, heights, errors, widths


def _points_of(histogram: Any, window: Sequence[float] | None) -> backends.Points:
    centres, heights, errors, widths = bins_of(histogram)
    if not centres:
        raise HepError("that object has no bins to fit",
                       hint="a counter or a scatter cannot be fitted; name a Histo1D")
    return backends.prepare(centres, heights, errors, widths, window=window)


def model_for(spec: dict) -> models.Model:
    """The model named by one `[[proc.fit]]` entry: a library expression, or an explicit formula."""
    expression = str(spec.get("expr") or "").strip()
    named = str(spec.get("model") or "").strip()
    if expression and named:
        raise HepError(f"fit {spec.get('name', '?')!r} gives both `model` and `expr`",
                       hint="one or the other: `model` names the library, `expr` is a TF1 formula")
    if expression:
        return models.from_expression(expression)
    if named:
        return models.parse(named)
    raise HepError(f"fit {spec.get('name', '?')!r} names no model",
                   hint="model = \"gauss + poly1\", or expr = \"[0]*exp([1]*x)\"")


def sample(model: models.Model, result: backends.Result, low: float, high: float,
           count: int = 200) -> Curve:
    """The fitted function over the fit range, for `/PROC/<fit>/curve`."""
    if not (high > low):
        return Curve()
    values = result.values(model.names)
    step = (high - low) / max(count - 1, 1)
    xs = [low + step * index for index in range(count)]
    try:
        ys = [float(value) for value in model(xs, *values)]
    except Exception:                                  # an `expr` model has no Python callable
        return Curve(low=low, high=high)
    return Curve(x=xs, y=ys, low=low, high=high)


def run_one(histogram: Any, spec: dict, *, backend: str = "auto") -> Fitted:
    """One `[[proc.fit]]` entry against one histogram."""
    name = str(spec.get("name") or "fit")
    window = spec.get("range") or None
    model = model_for(spec)
    points = _points_of(histogram, window)

    chosen = backends.choose(backend or spec.get("backend") or "auto")
    module = backends.load(chosen)
    result = module.fit(model, points,
                        init=spec.get("init") or {},
                        limits=spec.get("limits") or {},
                        likelihood=str(spec.get("likelihood") or "chi2"))

    low = float(window[0]) if window else float(min(points.x))
    high = float(window[1]) if window else float(max(points.x))
    return Fitted(name=name, target=str(spec.get("target") or ""), model=model.text,
                  result=result, curve=sample(model, result, low, high),
                  bins_used=points.used, bins_dropped=points.dropped)


def as_json(fitted: Fitted) -> dict:
    """One entry of `fits.json` (12 §3)."""
    result = fitted.result
    return {
        "name": fitted.name,
        "target": fitted.target,
        "point": fitted.point,
        "model": fitted.model,
        "backend": result.backend,
        "status": result.status,
        "valid": result.valid,
        "message": result.message,
        "params": {name: _finite(value) for name, value in result.params.items()},
        "errors": {name: _finite(value) for name, value in result.errors.items()},
        "covariance": [[_finite(value) for value in row] for row in result.covariance],
        "chi2": _finite(result.chi2),
        "ndf": result.ndf,
        "chi2_per_ndf": _finite(result.chi2_per_ndf),
        "bins": {"used": fitted.bins_used, "dropped": fitted.bins_dropped},
        "range": [fitted.curve.low, fitted.curve.high],
    }


def _finite(value: float) -> float | None:
    """JSON has no NaN. A parameter that could not be determined is `null`, not a fake number."""
    value = float(value)
    return value if math.isfinite(value) else None
