"""Derived histograms from a Delphes ROOT file, by two engines that must agree (12 §2.2).

```toml
[[proc.hist]]
name = "jet_pt"
source = "delphes"                # the group's delphes.root
tree = "Delphes"
expression = "Jet.PT"
selection = "Jet.PT > 5 && abs(Jet.Eta) < 3.5"
bins = [40, 0, 80]
engine = "auto"                   # auto → rdf when PyROOT is importable, else uproot
```

**The selection cuts *elements*, not events.** A Delphes branch is jagged — one entry per jet, per
event — so `Jet.PT > 5` is an array of booleans per event, and what the config means is "the jets
that pass", not "the events in which some jet passes". RDF spells that `Jet.PT[cut]` and awkward
spells it `Jet_PT[cut]`; both are elementwise, and an engine that quietly filtered whole events
instead would give a different (and plausible) answer.

**The two engines evaluate different languages, and that is the whole difficulty.** RDF compiles
C++; uproot works on awkward arrays in Python. `&&` is `&` there, and — the trap — Python's `&`
binds *tighter* than a comparison, so `a > 5 & b < 3` does not mean what it looks like. Translating
by string substitution gets this wrong silently. So the translation goes through Python's own
parser: `&&` → `and`, parse to an AST, then rewrite `and`/`or`/`not` into `&`/`|`/`~` **as tree
nodes**, where precedence is structural and cannot be got wrong.

That translator is why "the engines agree" is a test worth having rather than a tautology.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from ..errors import HepError

ENGINES = ("rdf", "uproot")


@dataclass
class Filled:
    """One `[[proc.hist]]` entry, filled."""

    name: str
    engine: str
    edges: list[float] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    errors: list[float] = field(default_factory=list)
    entries: int = 0
    source: str = ""

    @property
    def total(self) -> float:
        return float(sum(self.values))


# ── the expression language ──────────────────────────────────────────────────

class _ToArray(ast.NodeTransformer):
    """`and`/`or`/`not` → `&`/`|`/`~`, and `Jet.PT` → the name `Jet_PT`.

    A tree rewrite rather than a text substitution, so the parentheses Python's parser already
    worked out are kept. `a > 5 and b < 3` becomes `(a > 5) & (b < 3)`; substituting `&` into the
    text would have produced `a > (5 & b) < 3`.
    """

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        operator = ast.BitAnd() if isinstance(node.op, ast.And) else ast.BitOr()
        values = [self.visit(value) for value in node.values]
        combined = values[0]
        for value in values[1:]:
            combined = ast.BinOp(left=combined, op=operator, right=value)
        return ast.copy_location(combined, node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        if isinstance(node.op, ast.Not):
            return ast.copy_location(
                ast.UnaryOp(op=ast.Invert(), operand=self.visit(node.operand)), node)
        return self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        # `Jet.PT` is one branch name, not an attribute of anything.
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return self.generic_visit(node)
        parts.append(current.id)
        name = "_".join(reversed(parts))
        self.names.add(name)
        return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id not in _ALLOWED_CALLS:
            self.names.add(node.id)
        return node


#: The only functions an expression may call. Everything here means the same thing to C++ and to
#: awkward, which is the point: a function that exists on one side only would pass the translator
#: and fail the "engines agree" row.
_ALLOWED_CALLS = {"abs", "sqrt", "log", "log10", "exp", "sin", "cos", "tan", "min", "max"}


def _pythonise(text: str) -> str:
    """C++ spelling → Python spelling, before parsing. Only the operators; names are left alone."""
    text = str(text)
    text = text.replace("&&", " and ").replace("||", " or ")
    # `!` is `not`, but `!=` is `!=`. Replace only a `!` that is not followed by `=`.
    text = re.sub(r"!(?!=)", " not ", text)
    # `ast.parse(mode="eval")` rejects leading whitespace as an indent, and a leading `!` leaves
    # some behind.
    return text.strip()


def translate(text: str) -> tuple[Any, set[str]]:
    """A C++-ish expression → a compiled Python expression over awkward arrays, and its branches."""
    try:
        tree = ast.parse(_pythonise(text), mode="eval")
    except SyntaxError as error:
        raise HepError(f"cannot read the expression {text!r}: {error.msg}",
                       hint="the language is C++-ish: Jet.PT > 5 && abs(Jet.Eta) < 3.5") from None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS:
                shown = getattr(node.func, "id", "that")
                raise HepError(f"{shown!r} cannot be called in an expression",
                               hint="allowed: " + ", ".join(sorted(_ALLOWED_CALLS)))
        if isinstance(node, (ast.Lambda, ast.Subscript, ast.comprehension)):
            raise HepError(f"the expression {text!r} is too clever for this language",
                           hint="branch names, numbers, arithmetic, comparisons and "
                                + ", ".join(sorted(_ALLOWED_CALLS)))

    rewriter = _ToArray()
    rewritten = ast.fix_missing_locations(rewriter.visit(tree))
    return compile(rewritten, "<hekit-proc-hist>", "eval"), rewriter.names


def branches_of(*expressions: str) -> list[str]:
    """The branch names an expression needs, in `Jet.PT` spelling."""
    found: set[str] = set()
    for text in expressions:
        if text:
            found |= translate(text)[1]
    return sorted(name.replace("_", ".", 1) if "_" in name else name for name in found)


# ── the engines ──────────────────────────────────────────────────────────────

def available(engine: str) -> bool:
    if engine == "rdf":
        try:
            import ROOT
            return bool(hasattr(ROOT, "RDataFrame"))
        except Exception:
            return False
    if engine == "uproot":
        try:
            import awkward  # noqa: F401
            import uproot   # noqa: F401
            return True
        except ImportError:
            return False
    raise HepError(f"no histogram engine called {engine!r}",
                   hint="one of: " + ", ".join(ENGINES))


def choose(preference: str = "auto") -> str:
    if preference and preference != "auto":
        if not available(preference):
            raise HepError(f"the {preference} engine is not available here",
                           hint="rdf needs PyROOT; uproot needs uproot and awkward")
        return preference
    for engine in ENGINES:
        if available(engine):
            return engine
    raise HepError("no histogram engine is available",
                   hint="install uproot and awkward, or make PyROOT importable")


def _binning(bins: Sequence[float]) -> tuple[int, float, float]:
    if len(bins) != 3:
        raise HepError(f"bins must be [n, low, high], not {list(bins)!r}")
    count, low, high = int(bins[0]), float(bins[1]), float(bins[2])
    if count <= 0:
        raise HepError(f"a histogram with {count} bins keeps nothing")
    if not high > low:
        raise HepError(f"the range [{low}, {high}] is empty")
    return count, low, high


def fill_uproot(path: Path, tree: str, expression: str, selection: str,
                bins: Sequence[float], *, name: str = "") -> Filled:
    """uproot + awkward: read the branches, cut elementwise, histogram what is left."""
    import awkward as ak
    import numpy as np
    import uproot

    count, low, high = _binning(bins)
    code, wanted = translate(expression)
    cut_code, cut_names = translate(selection) if selection else (None, set())

    with uproot.open(str(path)) as handle:
        if tree not in handle:
            raise HepError(f"{path} has no tree called {tree!r}",
                           hint="it has: " + ", ".join(sorted(handle.keys(cycle=False))[:8]))
        branch_tree = handle[tree]
        namespace: dict[str, Any] = {}
        for holder in sorted(wanted | cut_names):
            # `Jet.PT` reaches the translator as the identifier `Jet_PT`, because a dot is an
            # attribute to Python's parser. Which spelling the *file* uses is the file's business:
            # Delphes writes `Jet.PT`, a plain ROOT tree usually writes `Jet_PT`, and a config
            # should not have to know. So both are tried.
            branch = _branch_in(branch_tree, holder)
            if branch is None:
                raise HepError(f"{path}:{tree} has no branch {holder.replace('_', '.', 1)!r}",
                               hint="it has: " + ", ".join(_leaf_names(branch_tree)[:8]))
            namespace[holder] = branch_tree[branch].array()

    values = eval(code, {"__builtins__": {}, **_MATH}, namespace)          # noqa: S307
    if cut_code is not None:
        mask = eval(cut_code, {"__builtins__": {}, **_MATH}, namespace)    # noqa: S307
        values = values[mask]

    flat = ak.to_numpy(ak.ravel(values)) if hasattr(values, "ndim") else np.asarray(values)
    flat = np.asarray(flat, dtype=float)
    counts, edges = np.histogram(flat, bins=count, range=(low, high))
    return Filled(name=name, engine="uproot", edges=[float(edge) for edge in edges],
                  values=[float(value) for value in counts],
                  errors=[float(np.sqrt(value)) for value in counts],
                  entries=int(flat.size), source=str(path))


def _branch_in(tree: Any, holder: str) -> str | None:
    """The branch this identifier means, in whichever spelling the file uses."""
    for candidate in (holder, holder.replace("_", ".", 1), holder.replace("_", "/", 1)):
        if candidate in tree:
            return candidate
    return None


def _leaf_names(tree: Any) -> list[str]:
    """The branches a reader would actually name, for an error message."""
    return sorted(name for name in tree.keys() if "/" not in name) or sorted(tree.keys())


def fill_rdf(path: Path, tree: str, expression: str, selection: str,
             bins: Sequence[float], *, name: str = "") -> Filled:
    """`ROOT.RDataFrame`, with implicit multithreading.

    The selection is applied as an element mask — `(expr)[cut]` — not as `Filter`, which would drop
    whole events. See the header note.
    """
    import ROOT

    count, low, high = _binning(bins)
    ROOT.EnableImplicitMT()
    frame = ROOT.RDataFrame(tree, str(path))
    column = f"({expression})[{selection}]" if selection else f"({expression})"
    frame = frame.Define("_hekit_value", column)
    handle = frame.Histo1D(ROOT.RDF.TH1DModel(name or "hist", "", count, low, high),
                           "_hekit_value")
    histogram = handle.GetValue()

    edges = [float(histogram.GetBinLowEdge(index + 1)) for index in range(count)]
    edges.append(float(histogram.GetBinLowEdge(count) + histogram.GetBinWidth(count)))
    values = [float(histogram.GetBinContent(index + 1)) for index in range(count)]
    errors = [float(histogram.GetBinError(index + 1)) for index in range(count)]
    return Filled(name=name, engine="rdf", edges=edges, values=values, errors=errors,
                  entries=int(histogram.GetEntries()), source=str(path))


_MATH: dict[str, Any] = {}


def _load_math() -> None:
    """The allowed calls, as awkward-aware functions. Filled once, lazily."""
    if _MATH:
        return
    import numpy as np

    _MATH.update({"abs": np.abs, "sqrt": np.sqrt, "log": np.log, "log10": np.log10,
                  "exp": np.exp, "sin": np.sin, "cos": np.cos, "tan": np.tan,
                  "min": np.minimum, "max": np.maximum})


def fill(spec: dict, path: Path, *, engine: str = "auto") -> Filled:
    """One `[[proc.hist]]` entry, by whichever engine is asked for."""
    _load_math()
    name = str(spec.get("name") or "hist")
    tree = str(spec.get("tree") or "Delphes")
    expression = str(spec.get("expression") or spec.get("expr") or "")
    selection = str(spec.get("selection") or spec.get("cut") or "")
    if not expression:
        raise HepError(f"[[proc.hist]] {name!r} has no `expression` to histogram")
    if not Path(path).is_file():
        raise HepError(f"no such file: {path}",
                       hint="`hep run` with [delphes] first; 12 §2.2 reads the group's delphes.root")

    chosen = choose(engine or str(spec.get("engine") or "auto"))
    bins = spec.get("bins") or []
    if chosen == "rdf":
        return fill_rdf(Path(path), tree, expression, selection, bins, name=name)
    return fill_uproot(Path(path), tree, expression, selection, bins, name=name)


def as_yoda(filled: Filled, *, path: str = "") -> Any:
    """`/PROC/<name>`, so `hep plot` treats it like any other result (12 §3).

    **A `BinnedEstimate1D`, not a `Histo1D`**, and that is a deliberate departure from 12 §3's
    wording. YODA 2 splits the two: a `Histo1D` is a *fillable accumulator* that keeps weight sums,
    and a `BinnedEstimate1D` is a **finished** value with uncertainties per bin — which is what a
    finalized Rivet analysis writes and what this project's plot pipeline recognises
    (`plot/io.is_binned_1d`). A derived histogram is finished the moment it is filled: nothing will
    add to it, and its uncertainty is its own √N rather than something to be inferred later. Writing
    a `Histo1D` here would produce a file that is correct, sums correctly, and is silently skipped by
    every plotting path — which is the opposite of "treat it like any other result".
    """
    import yoda

    made = yoda.BinnedEstimate1D(list(filled.edges), path or f"/PROC/{filled.name}", filled.name)
    for index, value in enumerate(filled.values):
        entry = made.bin(index + 1)
        error = filled.errors[index] if index < len(filled.errors) else 0.0
        entry.setVal(float(value))
        entry.setErr(float(error), "stats")
    return made


def total_of(made: Any) -> float:
    """The sum over an object `as_yoda` produced, whichever type it is."""
    try:
        return float(sum(entry.val() for entry in made.bins()))
    except Exception:
        return float(made.sumW())


def same_bins(left: Filled, right: Filled, *, tolerance: float = 0.0) -> list[str]:
    """What differs between two engines' answers. Empty means identical, which is the requirement."""
    problems: list[str] = []
    if len(left.edges) != len(right.edges):
        return [f"{len(left.edges)} edges against {len(right.edges)}"]
    for index, (one, two) in enumerate(zip(left.edges, right.edges)):
        if abs(one - two) > 1e-9:
            problems.append(f"edge {index}: {one} against {two}")
    for index, (one, two) in enumerate(zip(left.values, right.values)):
        if abs(one - two) > tolerance:
            problems.append(f"bin {index}: {one} against {two}")
    return problems
