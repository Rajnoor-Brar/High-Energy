"""What `hep proc` writes, and where (12 §3).

```
results/<project>/studies/<study>/proc/
  fits.json     parameters, errors, covariance, chi2/ndf, status, backend, input hashes
  proc.yoda     /PROC/<fit>/curve, so `hep plot` treats a fit like any other result
  proc.root     optional (keep_root): the TF1 and the fit result, for inspection only
```

**The curve is a `Scatter2D`, not a histogram.** A fitted function is a continuous thing sampled for
drawing; a `Histo1D` would claim bin contents it does not have, and anything downstream that summed
it would get a number with no meaning. YODA's own convention for "a curve" is a scatter, and
`rivet-mkhtml` and the mpl backend both already know how to draw one.

**`fits.json` records what produced it**, not only what came out: the backend actually used (which is
not always the one asked for — `auto` falls back), the input YODA's sha256, and the config hash. A
fit whose numbers disagree with yesterday's is nearly always a fit of a different file or by a
different minimiser, and that is unanswerable unless it was written down at the time.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..errors import HepError
from .fit import Fitted, as_json

PROC_DIR = "proc"
FITS_JSON = "fits.json"
PROC_YODA = "proc.yoda"
PROC_ROOT = "proc.root"


def sha256_of(path: Path) -> str:
    """The hash of an input, for the provenance block."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def curve_objects(fits: Sequence[Fitted]) -> list[Any]:
    """`/PROC/<fit>/curve` for each fit that produced one."""
    import yoda

    made = []
    for fitted in fits:
        if not fitted.curve.x:
            continue
        path = f"/PROC/{fitted.name}/curve"
        if fitted.point:
            path = f"/PROC/{fitted.name}/{fitted.point}/curve"
        scatter = yoda.Scatter2D(path=path, title=f"{fitted.model} fit to {fitted.target}")
        for x, y in zip(fitted.curve.x, fitted.curve.y):
            scatter.addPoint(float(x), float(y), 0.0, 0.0)
        made.append(scatter)
    return made


def write_yoda(fits: Sequence[Fitted], directory: Path, *,
               histograms: Sequence[Any] = (), merge: bool = False) -> Path | None:
    """`proc.yoda`: the fitted curves and the derived histograms, in one file (12 §3).

    One file, because `hep plot` reads one file and both kinds are results of the same command. A
    fit is a `Scatter2D` and a derived histogram is a `Histo1D`, which is the honest difference
    between a continuous claim and binned counts.
    """
    import yoda

    from .hist import as_yoda

    objects = curve_objects(fits)
    objects += [as_yoda(filled, path=f"/PROC/{filled.name}") for filled in histograms]
    destination = directory / PROC_YODA
    if merge and destination.is_file():
        # The same rule as `fits.json`: `--only` keeps what it did not recompute.
        made = {obj.path(): obj for obj in yoda.read(str(destination)).values()}
        made.update({obj.path(): obj for obj in objects})
        objects = list(made.values())
    if not objects:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    yoda.write(objects, str(destination))
    return destination


def merge_into(directory: Path, entries: list[dict]) -> list[dict]:
    """Keep the fits an earlier run produced that this one did not recompute.

    Only used by `--only`, and that is the whole reason it exists: "redo just this fit" should not
    quietly throw away the other four. A full run writes the complete set and replaces, because then
    what is on disk is exactly what the config says.
    """
    existing = directory / FITS_JSON
    if not existing.is_file():
        return entries
    try:
        previous = json.loads(existing.read_text(encoding="utf-8")).get("fits", [])
    except (OSError, ValueError):
        return entries
    fresh = {(entry.get("name"), entry.get("point")) for entry in entries}
    kept = [entry for entry in previous if (entry.get("name"), entry.get("point")) not in fresh]
    return kept + entries


def write_json(fits: Sequence[Fitted], directory: Path, *, inputs: dict[str, str],
               config_hash: str = "", pyroot: bool = False, backend: str = "",
               merge: bool = False) -> Path:
    """`fits.json`, with the provenance block 12 §3 asks for."""
    directory.mkdir(parents=True, exist_ok=True)
    entries = [as_json(fitted) for fitted in fits]
    payload = {
        "schema": 1,
        "fits": merge_into(directory, entries) if merge else entries,
        "provenance": {
            "inputs": inputs,
            "config_hash": config_hash,
            "backend": backend,
            "pyroot": pyroot,
        },
    }
    destination = directory / FITS_JSON
    destination.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n",
                           encoding="utf-8")
    return destination


def write_root(fits: Sequence[Fitted], directory: Path, models: dict[str, Any]) -> Path | None:
    """`proc.root`: the fitted `TF1`s, for looking at in a TBrowser. Optional, and never read back.

    Nothing in the toolkit depends on this file — `fits.json` is the record and `proc.yoda` is what
    gets drawn. It exists because a ROOT user will want to open the fit in the thing they already
    know, and refusing that is a worse answer than writing one more file.
    """
    try:
        import ROOT
    except Exception:
        return None
    if not fits:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / PROC_ROOT
    handle = ROOT.TFile(str(destination), "RECREATE")
    try:
        for fitted in fits:
            model = models.get(fitted.name)
            if model is None or not fitted.curve.x:
                continue
            try:
                function = ROOT.TF1(fitted.name, model.formula(),
                                    fitted.curve.low, fitted.curve.high)
                for index, name in enumerate(model.names):
                    function.SetParameter(index, float(fitted.result.params[name]))
                    function.SetParName(index, name)
                    error = fitted.result.errors.get(name, float("nan"))
                    function.SetParError(index, 0.0 if error != error else float(error))
                function.Write()
            except Exception:
                # A formula ROOT will not compile is not worth failing the whole command over: the
                # numbers are already in fits.json and this file is for looking at.
                continue
    finally:
        handle.Close()
    return destination


def summary_line(fitted: Fitted) -> str:
    """One line per fit for the terminal."""
    result = fitted.result
    chi2 = result.chi2_per_ndf
    shown = f"{chi2:.3g}" if chi2 == chi2 else "n/a"
    state = "" if result.valid else f"  [{result.status}]"
    return (f"{fitted.name}: {fitted.model} on {fitted.target} "
            f"({result.backend}, chi2/ndf = {shown}, {fitted.bins_used} bins"
            + (f", {fitted.bins_dropped} dropped" if fitted.bins_dropped else "") + ")" + state)
