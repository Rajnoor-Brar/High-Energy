"""utils/Env/figures/derive.py — a derived figure's objects (V84), from a point's YODA, with YODA's Python.

The runner stays standard library; this plugin is where YODA's arithmetic is. `derive(source, specs)`:
for each spec (name, op, objects), the object `/FIGURES/<name>` per variant of the first object (an
analysis option set, `/photo_eic:R=0.4/…` → `/FIGURES:R=0.4/<name>`), as YODA text to append to the
point's file:

* ratio, difference, sum: of the two objects, each an estimate (a histogram is made one, as finalize
  would), on the same binning; a ratio's errors are YODA's (uncorrelated);
* projection-x, projection-y: a 2D histogram's marginal on that axis.

`scan_value(source, y, glob)` (V85): one number of a point's YODA, (value, error), for a scan figure:
sigma (/_XSEC), entries (the object's raw twin's, else /RAW/_EVTCOUNT's), integral (Σ value × width over
the bins, errors in quadrature; a histogram's own), mean (an estimate's value-weighted bin centre; a
histogram's x mean), bin:N (the N-th bin, from 1). `scatter(name, points)` writes the scan as YODA text.

Errors are ValueError, with what is wrong; the caller says where.
"""

from __future__ import annotations

import fnmatch
import os
import tempfile

OPS = ("ratio", "difference", "sum", "projection-x", "projection-y")
SCAN = ("sigma", "entries", "integral", "mean", "bin:N")


def _yoda():
    try:
        import yoda
    except ImportError:
        raise ValueError("derived and scan figures need YODA's Python (load_hep)") from None
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
                         " of the point's YODA; a derived or scan figure's objects name one each")
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


def scan_value(source: str, y: str, glob: str = "") -> tuple[float, float]:
    """One number of a point's YODA and its error (see the module's doc)."""
    yoda = _yoda()
    objects = yoda.read(source)
    if y == "sigma":
        xsec = objects.get("/_XSEC")
        if xsec is None:
            raise ValueError("the point's YODA has no /_XSEC")
        return xsec.val(), xsec.totalErrAvg()
    if y == "entries" and not glob:
        count = objects.get("/RAW/_EVTCOUNT")
        if count is None:
            raise ValueError("the point's YODA has no /RAW/_EVTCOUNT")
        return float(count.numEntries()), float(count.numEntries()) ** 0.5
    found = _found(objects, glob)
    ao = found[next(iter(found))]                       # its first variant
    if y == "entries":
        raw = objects.get("/RAW" + ao.path())
        if raw is None or not hasattr(raw, "numEntries"):
            raise ValueError(f"{ao.path()} has no raw histogram to count entries of")
        return float(raw.numEntries()), float(raw.numEntries()) ** 0.5
    if hasattr(ao, "integral") and y in ("integral", "mean"):     # a histogram
        if y == "integral":
            return ao.integral(), ao.integralError() if hasattr(ao, "integralError") else 0.0
        return ao.xMean(), ao.xStdErr() if hasattr(ao, "xStdErr") else 0.0
    bins = _estimate(ao).bins()
    if y == "integral":
        return (sum(b.val() * b.xWidth() for b in bins),
                sum((b.totalErrAvg() * b.xWidth()) ** 2 for b in bins) ** 0.5)
    if y == "mean":
        weight = sum(b.val() * b.xWidth() for b in bins)
        if not weight:
            raise ValueError(f"{ao.path()} is empty: it has no mean")
        return sum(b.xMid() * b.val() * b.xWidth() for b in bins) / weight, 0.0
    if y.startswith("bin:"):
        number = int(y[4:])
        if not 1 <= number <= len(bins):
            raise ValueError(f"{ao.path()} has {len(bins)} bins, not a bin {number}")
        return bins[number - 1].val(), bins[number - 1].totalErrAvg()
    raise ValueError(f"y = '{y}' is not one of {', '.join(SCAN)}")


def scatter(path: str, points: list[tuple[float, float, float, float, float]]) -> str:
    """A Scatter2D as YODA text: points (x, x−, x+, y, ±y), as YODA writes it."""
    rows = "".join(f"{x:.6e}\t{lo:.6e}\t{hi:.6e}\t{y:.6e}\t{e:.6e}\t{e:.6e}\n" for x, lo, hi, y, e in points)
    return (f"BEGIN YODA_SCATTER2D_V3 {path}\nPath: {path}\nTitle: \nType: Scatter2D\n---\n"
            f"# val1\terr1-\terr1+\tval2\terr2-\terr2+\n{rows}END YODA_SCATTER2D_V3\n\n")
