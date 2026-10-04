"""utils/Env/figures/derive.py — a derived figure's objects (V84), from a point's YODA, with YODA's Python.

The runner stays standard library; this plugin is where YODA's arithmetic is. `derive(source, specs)`:
for each spec (name, op, objects), the object `/FIGURES/<name>` per variant of the first object (an
analysis option set, `/photo_eic:R=0.4/…` → `/FIGURES:R=0.4/<name>`), as YODA text to append to the
point's file:

* ratio, difference, sum: of the two objects, each an estimate (a histogram is made one, as finalize
  would), on the same binning; a ratio's errors are YODA's (uncorrelated);
* projection-x, projection-y: a 2D histogram's marginal on that axis.

Errors are ValueError, with what is wrong; the caller says where.
"""

from __future__ import annotations

import fnmatch
import os
import tempfile

OPS = ("ratio", "difference", "sum", "projection-x", "projection-y")


def _yoda():
    try:
        import yoda
    except ImportError:
        raise ValueError("a derived figure needs YODA's Python (load_hep)") from None
    return yoda


def _short(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _base(path: str) -> str:
    analysis, _, rest = path.strip("/").partition("/")
    return f"/{analysis.split(':')[0]}/{rest}"


def _options(path: str) -> str:
    return path.strip("/").split("/", 1)[0].partition(":")[2]


def _found(objects: dict, glob: str) -> dict[str, object]:
    """The object a glob names, per variant (options → object); one base object, else an error."""
    named = [p for p in objects if not p.startswith(("/RAW/", "/TMP/", "/_")) and "[" not in p
             and (fnmatch.fnmatch(_short(p), glob) or fnmatch.fnmatch(_base(p), glob) or fnmatch.fnmatch(p, glob))]
    bases = sorted({_base(p) for p in named})
    if len(bases) != 1:
        raise ValueError(f"'{glob}' names {'no object' if not bases else 'several objects: ' + ', '.join(bases[:4])}"
                         " of the point's YODA; a derived figure's objects name one each")
    return {_options(p): objects[p] for p in named}


def _estimate(ao):
    return ao.mkEstimate() if hasattr(ao, "mkEstimate") else ao


def _derived(yoda, op: str, found: list[dict], options: str):
    if op.startswith("projection-"):
        ao = found[0][options]
        if not hasattr(ao, "mkMarginalHisto"):
            raise ValueError(f"{op} projects a 2D histogram, and {ao.path()} is a {type(ao).__name__}")
        return ao.mkMarginalHisto(0 if op.endswith("x") else 1)
    if options not in found[1]:
        raise ValueError(f"{found[1][next(iter(found[1]))].path()} has no variant '{options}' to pair with")
    a, b = _estimate(found[0][options]), _estimate(found[1][options])
    try:
        return {"ratio": lambda: a / b, "difference": lambda: a - b, "sum": lambda: a + b}[op]()
    except Exception as error:            # YODA's: "Arithmetic operation requires compatible binning!"
        raise ValueError(f"{op} of {a.path()} and {b.path()}: {error}") from None


def derive(source: str, specs: list[tuple[str, str, list[str]]]) -> str:
    """The derived objects of one point's YODA, as YODA text."""
    yoda = _yoda()
    objects = yoda.read(source)
    made = []
    for name, op, globs in specs:
        if op not in OPS:
            raise ValueError(f"op = '{op}' is not one of {', '.join(OPS)}")
        found = [_found(objects, glob) for glob in globs]
        for options in found[0]:
            ao = _derived(yoda, op, found, options)
            ao.setPath(f"/FIGURES{':' + options if options else ''}/{name}")
            made.append(ao)
    handle, path = tempfile.mkstemp(suffix=".yoda")
    os.close(handle)
    try:
        yoda.write(made, path)
        with open(path, encoding="utf-8") as text:
            return text.read()
    finally:
        os.unlink(path)
