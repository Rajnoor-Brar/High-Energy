"""Reading and writing YODA for plots (07 §4).

Ported from `rivpyth_common`'s `read_yoda`, `split_object_path` and `is_reference`, with two things the
originals could not do:

* **the locale is put back.** YODA's reader sets `LC_ALL` to `C` and leaves it there (00/B29), which
  breaks the next non-ASCII write in the same process — a plot pipeline reads dozens of files, so this
  is not theoretical;
* **curve namespaces.** A page overlays several points, and the old `ydmrg` put them all in one
  namespace, so two curves from different points could land on the same object path and one would win
  silently (00/B17). `namespaced()` gives every curve its own prefix, derived from the point name.
"""

from __future__ import annotations

import contextlib
import locale
from pathlib import Path
from typing import Any

from ..errors import HepError

#: Paths Rivet uses for its own bookkeeping; never plotted.
INTERNAL = {"TMP", "RAW"}


@contextlib.contextmanager
def locale_kept():
    """YODA's reader resets `LC_ALL`; this puts it back (00/B29)."""
    saved = locale.setlocale(locale.LC_ALL)
    try:
        yield
    finally:
        with contextlib.suppress(locale.Error):
            locale.setlocale(locale.LC_ALL, saved)


def read(path: Path | str) -> dict[str, Any]:
    """Every object in a YODA file, by path."""
    try:
        import yoda
    except ImportError as error:                  # pragma: no cover - yoda is a hard dependency
        raise HepError("the YODA Python bindings are needed to plot",
                       hint="`hep doctor` reports what is importable") from error
    try:
        with locale_kept():
            return yoda.read(str(path))
    except Exception as error:
        raise HepError(f"cannot read {path}: {error}") from None


def write(objects, path: Path | str) -> Path:
    """Write objects atomically, keeping the `.yoda` suffix on the temporary (P0-S03)."""
    import yoda

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    values = list(objects.values()) if isinstance(objects, dict) else list(objects)
    try:
        with locale_kept():
            yoda.write(values, str(temporary))
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def split_object_path(path: str) -> tuple[str, str] | None:
    """`(analysis, histogram)` for a plottable object, or None for Rivet's own bookkeeping.

    `/photo_eic:R=0.4/d01-x01-y01` → `("photo_eic:R=0.4", "d01-x01-y01")`. The analysis keeps its
    options, because an option variant is a separate curve on the same plot (03 §4).
    """
    parts = path.removeprefix("/REF").split("/", 2)
    if len(parts) < 3 or not parts[1] or not parts[2]:
        return None
    if parts[1] in INTERNAL or parts[1].startswith("_") or parts[2].startswith("_"):
        return None
    return parts[1], parts[2]


def base_analysis(analysis: str) -> str:
    """`photo_eic:R=0.4` → `photo_eic`: options pick a curve, not a plot."""
    return analysis.split(":", 1)[0]


def options_of(analysis: str) -> dict[str, str]:
    """The options of a variant, as a mapping (`R=0.4,ETMIN=7` → `{"R": "0.4", "ETMIN": "7"}`)."""
    _, _, rest = analysis.partition(":")
    found: dict[str, str] = {}
    for entry in rest.split(","):
        if "=" in entry:
            key, _, value = entry.partition("=")
            found[key.strip()] = value.strip()
    return found


def is_reference(obj: Any, path: str) -> bool:
    if path.startswith("/REF/"):
        return True
    return obj.hasAnnotation("IsRef") and str(obj.annotation("IsRef")) not in {"0", "false", "False"}


def plot_key(obj_path: str) -> str | None:
    """The plot an object belongs to: analysis **without** options, plus the histogram name.

    Two option variants share a plot and are drawn as two curves on it, so they must agree about
    which bins are voided and what the x range is (07 §4).
    """
    parsed = split_object_path(obj_path)
    if parsed is None:
        return None
    return f"/{base_analysis(parsed[0])}/{parsed[1]}"


def namespaced(obj_path: str, curve: str) -> str:
    """Move an object into a curve's own namespace (00/B17).

    `ydmrg` merged every point's objects into one namespace, so two curves could occupy the same path
    and one silently replaced the other. A curve prefix makes that impossible, and `hep plot` uses the
    point name — which is unique by construction (03 §5).
    """
    if not curve:
        return obj_path
    prefix = "/REF" if obj_path.startswith("/REF/") else ""
    rest = obj_path.removeprefix("/REF")
    return f"{prefix}/{curve}{rest}"


def denamespaced(obj_path: str, curve: str) -> str:
    prefix = "/REF" if obj_path.startswith("/REF/") else ""
    rest = obj_path.removeprefix("/REF")
    marker = f"/{curve}/"
    return prefix + rest[len(f"/{curve}"):] if rest.startswith(marker) else obj_path


def histograms(objects: dict[str, Any], *, analysis: str = "", include_ref: bool = False) -> dict[str, Any]:
    """The plottable 1D objects of a file, optionally restricted to one analysis."""
    found = {}
    for path, obj in objects.items():
        parsed = split_object_path(path)
        if parsed is None:
            continue
        if path.startswith("/REF/") and not include_ref:
            continue
        if analysis and base_analysis(parsed[0]) != base_analysis(analysis):
            continue
        found[path] = obj
    return found


def edges_of(obj: Any) -> list[float] | None:
    getter = getattr(obj, "xEdges", None)
    if getter is None:
        return None
    try:
        return [float(edge) for edge in getter()]
    except (AttributeError, TypeError):           # pragma: no cover - a non-1D object
        return None


def values_of(obj: Any) -> list[float]:
    try:
        return [float(value) for value in obj.vals()]
    except (AttributeError, TypeError):           # pragma: no cover
        return []


def is_binned_1d(obj: Any) -> bool:
    return type(obj).__name__ == "BinnedEstimate1D"
