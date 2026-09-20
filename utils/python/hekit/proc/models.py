"""The model library: one registry, every backend evaluates the same function (12 §2.1).

**Why a registry rather than a formula string.** The obvious design is to let the config carry a
`TF1` formula and hand it to ROOT. It fails the moment there is a second backend: scipy cannot read
a `TF1` string, so the model would have to be written twice, and two spellings of "a Gaussian plus a
linear background" that differ in the third decimal are indistinguishable from a fitter that
disagrees. So a model is declared once, in Python, and carries three things:

  * **parameter names**, so a config says `init = { mean = 1.1157 }` rather than `[1] = 1.1157`;
  * a **NumPy callable**, which is what actually gets fitted — by *both* the scipy and the Minuit2
    backends, since the latter drives `ROOT::Math::Minimizer` with a Python functor rather than a
    `TF1`. That is what makes "the backends agree" a statement about minimisers rather than about
    transcription;
  * a **`TF1` formula**, needed only for RooFit and for the optional `proc.root`.

**Composition** is `+`: `"gauss + poly2"` is one model whose parameters are the union, in order.
Repeated components are disambiguated by position (`gauss1.mean`, `gauss2.mean`) and unique ones keep
their plain names, because `mean` is what a person writes when there is only one.

**Initial guesses matter more than they look.** A Gaussian fit started at the wrong side of a peak
converges to the wrong answer and reports a good χ², so every component knows how to read a first
guess off the data it is about to be fitted to.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable, Sequence

from ..errors import HepError

try:                                                   # numpy is a hard dependency of the fitters
    import numpy as np
except ImportError:                                    # pragma: no cover - part of the venv
    np = None


Guess = Callable[["np.ndarray", "np.ndarray"], Sequence[float]]


@dataclass(frozen=True)
class Component:
    """One term of a model: what it is called, what it takes, and how to evaluate it."""

    name: str
    params: tuple[str, ...]
    call: Callable[..., "np.ndarray"]
    formula: Callable[[Sequence[int]], str]   # TF1 text, given this term's parameter indices
    guess: Guess
    doc: str = ""


# ── the components ───────────────────────────────────────────────────────────

def _span(x, y):
    """A crude width and height, used by several guesses."""
    height = float(np.max(y)) if len(y) else 1.0
    centre = float(x[int(np.argmax(y))]) if len(x) else 0.0
    width = (float(x[-1]) - float(x[0])) / 6.0 if len(x) > 1 else 1.0
    return height, centre, max(width, 1e-9)


def _gauss(x, amp, mean, sigma):
    sigma = max(abs(float(sigma)), 1e-12)
    return amp * np.exp(-0.5 * ((x - mean) / sigma) ** 2)


def _breitwigner(x, amp, mean, width):
    half = max(abs(float(width)), 1e-12) / 2.0
    return amp * half * half / ((x - mean) ** 2 + half * half)


def _crystalball(x, amp, mean, sigma, alpha, n):
    """Gaussian core with a power-law tail below `mean - alpha*sigma`.

    `alpha` is taken as |alpha| and `n` is held above 1: the function is undefined at n = 1 and the
    minimiser will walk there given the chance.
    """
    sigma = max(abs(float(sigma)), 1e-12)
    alpha = max(abs(float(alpha)), 1e-6)
    n = max(float(n), 1.0 + 1e-6)
    t = (np.asarray(x, dtype=float) - mean) / sigma
    core = np.exp(-0.5 * t * t)
    a = (n / alpha) ** n * math.exp(-0.5 * alpha * alpha)
    b = n / alpha - alpha
    with np.errstate(over="ignore", invalid="ignore"):
        tail = a * np.power(np.maximum(b - t, 1e-12), -n)
    return amp * np.where(t > -alpha, core, tail)


def _voigt(x, amp, mean, sigma, width):
    """A Gaussian convolved with a Lorentzian, through the Faddeeva function."""
    from scipy.special import wofz

    sigma = max(abs(float(sigma)), 1e-12)
    gamma = max(abs(float(width)), 1e-12) / 2.0
    z = ((np.asarray(x, dtype=float) - mean) + 1j * gamma) / (sigma * math.sqrt(2.0))
    profile = np.real(wofz(z)) / (sigma * math.sqrt(2.0 * math.pi))
    peak = np.real(wofz(1j * gamma / (sigma * math.sqrt(2.0)))) / (sigma * math.sqrt(2.0 * math.pi))
    # Normalised so `amp` is the height, which is what a person setting an initial value means.
    return amp * profile / max(peak, 1e-300)


def _expo(x, amp, slope):
    return amp * np.exp(np.clip(slope * np.asarray(x, dtype=float), -700.0, 700.0))


def _threshold(x, amp, onset, power):
    above = np.maximum(np.asarray(x, dtype=float) - onset, 0.0)
    return amp * np.power(above, max(float(power), 1e-6))


def _gauss_guess(x, y):
    height, centre, width = _span(x, y)
    return (height, centre, width)


def _bw_guess(x, y):
    height, centre, width = _span(x, y)
    return (height, centre, 2.0 * width)


def _cb_guess(x, y):
    height, centre, width = _span(x, y)
    return (height, centre, width, 1.5, 3.0)


def _voigt_guess(x, y):
    height, centre, width = _span(x, y)
    return (height, centre, width, width)


def _expo_guess(x, y):
    if len(x) < 2 or np.all(y <= 0):
        return (float(np.max(y)) if len(y) else 1.0, -1.0)
    positive = y > 0
    slope, intercept = np.polyfit(x[positive], np.log(y[positive]), 1)
    return (float(math.exp(intercept)), float(slope))


def _threshold_guess(x, y):
    height, _, _ = _span(x, y)
    onset = float(x[0]) if len(x) else 0.0
    return (height, onset, 0.5)


BUILTIN: dict[str, Component] = {
    "gauss": Component("gauss", ("amp", "mean", "sigma"), _gauss,
                       lambda i: f"[{i[0]}]*exp(-0.5*((x-[{i[1]}])/[{i[2]}])^2)",
                       _gauss_guess, "a Gaussian peak of height `amp`"),
    "breitwigner": Component("breitwigner", ("amp", "mean", "width"), _breitwigner,
                             lambda i: (f"[{i[0]}]*([{i[2]}]/2)^2/"
                                        f"((x-[{i[1]}])^2+([{i[2]}]/2)^2)"),
                             _bw_guess, "a non-relativistic Breit-Wigner"),
    "crystalball": Component("crystalball", ("amp", "mean", "sigma", "alpha", "n"), _crystalball,
                             lambda i: (f"[{i[0]}]*ROOT::Math::crystalball_function("
                                        f"x,[{i[3]}],[{i[4]}],[{i[2]}],[{i[1]}])"),
                             _cb_guess, "a Gaussian core with a power-law tail"),
    "voigt": Component("voigt", ("amp", "mean", "sigma", "width"), _voigt,
                       lambda i: f"[{i[0]}]*TMath::Voigt(x-[{i[1]}],[{i[2]}],[{i[3]}])",
                       _voigt_guess, "a Gaussian convolved with a Lorentzian"),
    "expo": Component("expo", ("amp", "slope"), _expo,
                      lambda i: f"[{i[0]}]*exp([{i[1]}]*x)", _expo_guess,
                      "an exponential, `amp` at x = 0"),
    "threshold": Component("threshold", ("amp", "onset", "power"), _threshold,
                           lambda i: f"[{i[0]}]*pow(max(x-[{i[1]}],0),[{i[2]}])",
                           _threshold_guess, "zero below `onset`, a power law above it"),
}


def _polynomial(order: int) -> Component:
    names = tuple(f"p{index}" for index in range(order + 1))

    def call(x, *coefficients):
        x = np.asarray(x, dtype=float)
        total = np.zeros_like(x, dtype=float)
        for power, coefficient in enumerate(coefficients):
            total = total + coefficient * x ** power
        return total

    def formula(indices):
        terms = [f"[{indices[0]}]"]
        terms += [f"[{indices[power]}]*x^{power}" if power > 1 else f"[{indices[power]}]*x"
                  for power in range(1, order + 1)]
        return "(" + "+".join(terms) + ")"

    def guess(x, y):
        if len(x) <= order:
            return tuple([float(np.mean(y)) if len(y) else 0.0] + [0.0] * order)
        # `polyfit` returns highest power first; the parameters are lowest first.
        return tuple(float(value) for value in np.polyfit(x, y, order)[::-1])

    return Component(f"poly{order}", names, call, formula, guess,
                     f"a polynomial of order {order}")


def component(name: str) -> Component:
    """One term by name. `polyN` is generated, everything else is in `BUILTIN`."""
    key = name.strip().lower()
    if key in BUILTIN:
        return BUILTIN[key]
    matched = re.fullmatch(r"poly(\d+)", key)
    if matched:
        order = int(matched.group(1))
        if order > 12:
            raise HepError(f"poly{order} is too high an order to be meaningful",
                           hint="a fit with more than a dozen free coefficients is not a fit")
        return _polynomial(order)
    known = ", ".join(sorted(BUILTIN) + ["polyN"])
    raise HepError(f"no model called {name!r}", hint=f"one of: {known}")


# ── a whole model ────────────────────────────────────────────────────────────

@dataclass
class Model:
    """A sum of components, with one flat parameter list."""

    text: str
    components: tuple[Component, ...]
    names: tuple[str, ...]
    slices: tuple[tuple[int, int], ...] = field(default_factory=tuple)

    def __call__(self, x, *values):
        if len(values) != len(self.names):
            raise HepError(f"{self.text} takes {len(self.names)} parameters, "
                           f"and was given {len(values)}")
        x = np.asarray(x, dtype=float)
        total = np.zeros_like(x, dtype=float)
        for piece, (start, stop) in zip(self.components, self.slices):
            total = total + piece.call(x, *values[start:stop])
        return total

    def formula(self) -> str:
        """The TF1 spelling, for RooFit and for `proc.root`."""
        return "+".join(piece.formula(list(range(start, stop)))
                        for piece, (start, stop) in zip(self.components, self.slices))

    def guess(self, x, y) -> tuple[float, ...]:
        """A first guess for every parameter, read off the data.

        Components are guessed against what the earlier ones have not already explained, so a peak
        on top of a background does not hand the background the peak's height.
        """
        x = np.asarray(x, dtype=float)
        residual = np.asarray(y, dtype=float).copy()
        values: list[float] = []
        # Backgrounds first: a smooth term fitted to a spectrum with a peak in it is close enough,
        # and subtracting it makes the peak's own guess much better than the raw maximum.
        order = sorted(range(len(self.components)),
                       key=lambda index: 0 if self.components[index].name.startswith(
                           ("poly", "expo")) else 1)
        found: dict[int, tuple[float, ...]] = {}
        for index in order:
            piece = self.components[index]
            made = tuple(float(value) for value in piece.guess(x, residual))
            found[index] = made
            residual = residual - piece.call(x, *made)
        for index in range(len(self.components)):
            values.extend(found[index])
        return tuple(values)

    def index(self, name: str) -> int:
        try:
            return self.names.index(name)
        except ValueError:
            raise HepError(f"{self.text} has no parameter called {name!r}",
                           hint="it has: " + ", ".join(self.names)) from None


def parse(text: str) -> Model:
    """`"gauss + poly2"` → a `Model`. Whitespace and case are ignored."""
    if np is None:                                     # pragma: no cover - part of the venv
        raise HepError("fitting needs numpy")
    pieces = [part.strip() for part in str(text).split("+") if part.strip()]
    if not pieces:
        raise HepError(f"{text!r} names no model", hint="for example: 'gauss + poly1'")
    components = tuple(component(part) for part in pieces)

    # A name is plain when it is the only one of its kind, and numbered when it is not — so
    # `"gauss + poly1"` has `mean`, and `"gauss + gauss"` has `gauss1.mean` and `gauss2.mean`.
    seen: dict[str, int] = {}
    for piece in components:
        seen[piece.name] = seen.get(piece.name, 0) + 1
    counted: dict[str, int] = {}
    names: list[str] = []
    slices: list[tuple[int, int]] = []
    for piece in components:
        start = len(names)
        if seen[piece.name] > 1:
            counted[piece.name] = counted.get(piece.name, 0) + 1
            prefix = f"{piece.name}{counted[piece.name]}."
        else:
            prefix = ""
        names.extend(prefix + parameter for parameter in piece.params)
        slices.append((start, len(names)))
    return Model(text=str(text), components=components, names=tuple(names), slices=tuple(slices))


def from_expression(expr: str, parameters: int | None = None) -> Model:
    """An explicit `TF1` formula, for the cases the library does not cover.

    The parameters are `[0]`, `[1]`, … and are named `p0`, `p1`, … . There is no NumPy callable for
    an arbitrary formula, so this model can only be fitted by a ROOT backend; `scipy` says so rather
    than guessing at a translation.
    """
    indices = sorted({int(found) for found in re.findall(r"\[(\d+)\]", str(expr))})
    if not indices and parameters is None:
        raise HepError(f"the expression {expr!r} has no parameters",
                       hint="parameters are written [0], [1], … as in a ROOT TF1")
    count = parameters if parameters is not None else max(indices) + 1
    names = tuple(f"p{index}" for index in range(count))

    def refuse(x, *values):
        raise HepError("an explicit `expr` can only be fitted by a ROOT backend",
                       hint="use backend = \"minuit2\" or \"roofit\", or a model name instead")

    piece = Component("expr", names, refuse, lambda i: str(expr),
                      lambda x, y: tuple(1.0 for _ in names), "an explicit TF1 formula")
    return Model(text=str(expr), components=(piece,), names=names, slices=((0, len(names)),))
