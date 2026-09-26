"""`[proc.export]`: a ROOT file of the histograms a point produced (12 §2.3).

**Why this is in Python and not a sink.** D7 and D14 make YODA the results format, and D15 keeps ROOT
out of `hep-run` entirely — the event loop links Pythia and YODA and nothing else. A module that
wrote ROOT directly would put a second results format inside the event loop and contradict both. So
the run still produces one `analysis.yoda`, and this turns it into ROOT afterwards, in the half that
is *allowed* to know about ROOT.

That is not a workaround; it is the reason the split exists. The YODA file stays the record — it
carries the annotations, it is what `hep plot` and `hep compare` read, and it is what provenance
hashes — and the ROOT file is a **derived view** you can delete and regenerate. `hep clean` treats
it as such.

**Where it goes.** Beside its source, as `analysis.root` in the point's own directory, because it is
one-to-one with that point's `analysis.yoda`. Fits are study-level and go to `studies/…/proc/`;
this is not, and putting it there would need a point name in the filename to stay unambiguous.

**Structure.** A YODA path `/Lambda/selected_mass` becomes a TDirectory `Lambda` holding a TH1D
`selected_mass`, so the module namespace survives the trip and `TBrowser` shows what the analysis
looks like. Counters become a one-bin TH1D, which is what a counter is.

The writer is `uproot`, not PyROOT: it is already a dependency, it needs no ROOT at import time, and
it writes `fSumw2` correctly — so a build with no PyROOT can still export. PyROOT is used only if
uproot is missing.
"""

from __future__ import annotations

import fnmatch
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import HepError
from ..plot import io


@dataclass
class Exported:
    """What one export wrote."""

    path: Path
    objects: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    engine: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.objects)


def wanted(name: str, patterns: list[str]) -> bool:
    """Does this YODA path match any of `[proc.export].select`? No patterns means everything."""
    if not patterns:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def directory_and_name(obj_path: str) -> tuple[str, str]:
    """`/Lambda/selected_mass` → `("Lambda", "selected_mass")`; a bare name gets no directory."""
    parts = [part for part in str(obj_path).strip("/").split("/") if part]
    if len(parts) <= 1:
        return "", parts[0] if parts else "histogram"
    return "/".join(parts[:-1]), parts[-1]


def _bins(obj: Any) -> tuple[list[float], list[float], list[float], float] | None:
    """`(edges, sumW, sumW2, entries)` for a fillable 1D histogram, or None if it is not one."""
    edges = io.edges_of(obj)
    getter = getattr(obj, "bins", None)
    if edges is None or getter is None:
        return None
    try:
        bins = list(getter())
    except TypeError:                                      # pragma: no cover - not a binned object
        return None
    if len(bins) != len(edges) - 1:
        return None
    try:
        sum_w = [float(b.sumW()) for b in bins]
        sum_w2 = [float(b.sumW2()) for b in bins]
        entries = float(sum(b.numEntries() for b in bins))
    except AttributeError:                                 # an Estimate, which has no sumW
        return None
    return edges, sum_w, sum_w2, entries


def _counter(obj: Any) -> tuple[float, float] | None:
    """`(sumW, sumW2)` for a `Counter`."""
    if type(obj).__name__ != "Counter":
        return None
    try:
        return float(obj.sumW()), float(obj.sumW2())
    except AttributeError:                                 # pragma: no cover
        return None


def _estimate(obj: Any) -> tuple[list[float], list[float], list[float]] | None:
    """`(edges, values, errors)` for a finished `BinnedEstimate1D` — what `hep proc` itself writes.

    An estimate has no weight sums, only a value and an error band, so the ROOT histogram gets the
    error as its bin error and an entry count of zero. That is honest: the thing genuinely is not a
    fillable histogram any more.
    """
    if not io.is_binned_1d(obj):
        return None
    edges = io.edges_of(obj)
    if edges is None:
        return None
    values = io.values_of(obj)
    errors: list[float] = []
    for point in obj.bins():
        try:
            low, high = point.errAvg(), point.errAvg()
        except (AttributeError, TypeError):                # pragma: no cover - no error source
            low = high = 0.0
        errors.append(abs(float(low)) if math.isfinite(float(low or 0.0)) else 0.0)
        _ = high
    if len(values) != len(edges) - 1:
        return None
    return edges, values, errors


def export(source: Path | str, destination: Path | str, *,
           select: list[str] | None = None, title: str = "") -> Exported:
    """Write the histograms of one `analysis.yoda` into a ROOT file."""
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise HepError(f"there is no {source.name} to export",
                       where=str(source),
                       hint="`hep run` first; `hep runs` lists what exists")

    objects = io.read(source)
    patterns = list(select or [])
    result = Exported(path=destination)

    payload: list[tuple[str, str, dict]] = []
    for obj_path in sorted(objects):
        if obj_path.startswith("/RAW/"):                   # Rivet's pre-finalize copies
            continue
        if not wanted(obj_path, patterns):
            continue
        obj = objects[obj_path]
        directory, name = directory_and_name(obj_path)

        binned = _bins(obj)
        if binned is not None:
            edges, sum_w, sum_w2, entries = binned
            payload.append((directory, name,
                            {"edges": edges, "values": sum_w, "variances": sum_w2,
                             "entries": entries, "title": _title_of(obj, name)}))
            result.objects.append(obj_path)
            continue

        estimate = _estimate(obj)
        if estimate is not None:
            edges, values, errors = estimate
            payload.append((directory, name,
                            {"edges": edges, "values": values,
                             "variances": [error * error for error in errors],
                             "entries": 0.0, "title": _title_of(obj, name)}))
            result.objects.append(obj_path)
            continue

        counted = _counter(obj)
        if counted is not None:
            total, total2 = counted
            payload.append((directory, name,
                            {"edges": [0.0, 1.0], "values": [total], "variances": [total2],
                             "entries": 1.0, "title": _title_of(obj, name)}))
            result.objects.append(obj_path)
            continue

        result.skipped[obj_path] = f"{type(obj).__name__} has no 1D binning"

    if not payload:
        result.skipped.setdefault("", "nothing matched [proc.export].select")
        return result

    destination.parent.mkdir(parents=True, exist_ok=True)
    result.engine = _write(payload, destination, title=title or source.stem)
    return result


def _title_of(obj: Any, fallback: str) -> str:
    try:
        if obj.hasAnnotation("Title"):
            return str(obj.annotation("Title"))
    except (AttributeError, TypeError):                    # pragma: no cover
        pass
    return fallback


def _write(payload: list[tuple[str, str, dict]], destination: Path, *, title: str) -> str:
    """uproot if it is importable, PyROOT otherwise. Both produce a TH1D per entry."""
    try:
        import uproot
    except ImportError:                                    # pragma: no cover - uproot is installed
        return _write_pyroot(payload, destination, title=title)

    import numpy
    from uproot.writing.identify import to_TAxis, to_TH1x

    with uproot.recreate(destination) as handle:
        for directory, name, item in payload:
            edges = [float(edge) for edge in item["edges"]]
            values = [float(value) for value in item["values"]]
            variances = [float(value) for value in item["variances"]]

            # ROOT's arrays carry underflow and overflow. Nothing here has them — a YODA flow bin is
            # not the same object — so they are written as zero rather than guessed at.
            data = numpy.array([0.0, *values, 0.0], dtype=numpy.float64)
            sumw2 = numpy.array([0.0, *variances, 0.0], dtype=numpy.float64)
            axis = to_TAxis("xaxis", "", len(values), edges[0], edges[-1])
            if not _uniform(edges):
                axis = to_TAxis("xaxis", "", len(values), edges[0], edges[-1],
                                fXbins=numpy.array(edges, dtype=numpy.float64))

            histogram = to_TH1x(
                fName=name, fTitle=str(item["title"]), data=data,
                fEntries=float(item["entries"]), fTsumw=float(sum(values)),
                fTsumw2=float(sum(variances)), fTsumwx=0.0, fTsumwx2=0.0,
                fSumw2=sumw2, fXaxis=axis)
            handle[f"{directory}/{name}" if directory else name] = histogram
    return "uproot"


def _uniform(edges: list[float], tolerance: float = 1e-9) -> bool:
    if len(edges) < 3:
        return True
    width = (edges[-1] - edges[0]) / (len(edges) - 1)
    return all(abs((edges[i + 1] - edges[i]) - width) <= tolerance * max(1.0, abs(width))
               for i in range(len(edges) - 1))


def _write_pyroot(payload: list[tuple[str, str, dict]], destination: Path, *,
                  title: str) -> str:   # pragma: no cover - only without uproot
    try:
        import ROOT
    except ImportError as error:
        raise HepError("neither uproot nor PyROOT is available, so no ROOT file can be written",
                       hint="`hep doctor` reports what is installed") from error

    ROOT.gROOT.SetBatch(True)
    handle = ROOT.TFile(str(destination), "RECREATE")
    try:
        for directory, name, item in payload:
            handle.cd()
            target = handle
            if directory:
                target = handle.GetDirectory(directory) or handle.mkdir(directory)
            target.cd()
            edges = [float(edge) for edge in item["edges"]]
            histogram = ROOT.TH1D(name, str(item["title"]), len(edges) - 1,
                                  ROOT.std.vector("double")(edges).data())
            for index, (value, variance) in enumerate(zip(item["values"], item["variances"]), 1):
                histogram.SetBinContent(index, float(value))
                histogram.SetBinError(index, math.sqrt(max(float(variance), 0.0)))
            histogram.SetEntries(float(item["entries"]))
            histogram.Write()
    finally:
        handle.Close()
    return "pyroot"
