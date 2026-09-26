"""The matplotlib/mplhep backend: publication figures from the same `.plot` keys (07 §4).

Two backends draw the same pages, and they must agree about what a plot *says* — its title, axis
labels, log scales, ranges and ratio panel. `rivet-mkhtml` reads those from `.plot` files; this reads
the same files and turns the same keys into matplotlib calls, so relabelling a histogram relabels it
everywhere and there is no second place to keep in sync.

What the two backends differ in is deliberate: `mkhtml` is for browsing a hundred histograms with
ratio panels; this is for the two or three figures that go in a paper, where the font, the size and
the file format matter. Those come from `[plot.style]` and the house style translated from the ROOT
presets the group already used (`hekit.mplstyle`).

This replaces Paint (finding F7): a TOML-configured ROOT canvas becomes a `.plot` file plus a style
sheet, and the histograms come from the same YODA the other backend reads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...errors import HepError
from .. import io, plotfile
from ..page import Page

STYLE_DIR = Path(__file__).resolve().parent.parent / "styles"

#: `.plot` key → what it means here. The names are Rivet's, because they are the ones in the files.
KEYS = {
    "Title": "title",
    "XLabel": "xlabel",
    "YLabel": "ylabel",
    "LogX": "logx",
    "LogY": "logy",
    "XMin": "xmin",
    "XMax": "xmax",
    "YMin": "ymin",
    "YMax": "ymax",
    "RatioPlot": "ratio",
    "RatioPlotYMin": "ratio_ymin",
    "RatioPlotYMax": "ratio_ymax",
    "RatioPlotYLabel": "ratio_ylabel",
    "LegendOnly": "legend_only",
    "LegendTitle": "legend_title",
    "LegendXPos": "legend_x",
    "LegendYPos": "legend_y",
    "MainPanel": "main_panel",
}

BOOLEAN = {"logx", "logy", "ratio", "main_panel"}
NUMERIC = {"xmin", "xmax", "ymin", "ymax", "ratio_ymin", "ratio_ymax", "legend_x", "legend_y"}


def settings_for(block: dict[str, str]) -> dict[str, Any]:
    """One `.plot` block as keyword arguments, with the types the keys imply.

    Unknown keys are kept under their own name rather than dropped: a `.plot` file may carry keys for
    a tool we do not know about, and losing them silently would be the sort of quiet data loss this
    project keeps finding.
    """
    found: dict[str, Any] = {}
    for key, value in block.items():
        name = KEYS.get(key, key)
        if name in BOOLEAN:
            found[name] = str(value).strip() not in {"0", "false", "False", ""}
        elif name in NUMERIC:
            try:
                found[name] = float(value)
            except (TypeError, ValueError):
                continue
        elif name == "legend_only":
            found[name] = str(value).split()
        else:
            found[name] = value
    return found


def plot_settings(page: Page, obj_path: str) -> dict[str, Any]:
    """The `.plot` settings for one histogram: the project's file, then the auto-range override."""
    found: dict[str, Any] = {}
    key = io.plot_key(obj_path) or obj_path
    for source in (page.plot_file, page.ranges):
        if source is None or not Path(source).is_file():
            continue
        blocks = plotfile.parse(source)
        for candidate in (key, obj_path, "/" + key.lstrip("/")):
            if candidate in blocks:
                found.update(settings_for(blocks[candidate]))
                break
    return found


# ── style ────────────────────────────────────────────────────────────────────

@dataclass
class Style:
    """`[plot.style]`, resolved to something matplotlib understands."""

    name: str = "hekit"
    figure: tuple[float, float] | None = None
    font_size: float = 0.0
    dpi: int = 0
    formats: tuple[str, ...] = ("pdf", "png")
    ratio: bool = True

    @classmethod
    def of(cls, config: Any) -> "Style":
        style = getattr(config.plot, "style", None)
        if style is None:                                  # pragma: no cover - schema always has it
            return cls()
        figure = tuple(style.figure) if getattr(style, "figure", None) else None
        return cls(name=style.name, figure=figure, font_size=style.font_size, dpi=style.dpi,
                   formats=tuple(style.formats), ratio=style.ratio)

    def apply(self) -> None:
        import matplotlib.pyplot as pyplot

        if self.name == "hekit":
            pyplot.style.use(str(STYLE_DIR / "hekit.mplstyle"))
        elif self.name and self.name != "none":
            import mplhep

            found = getattr(mplhep.style, self.name, None)
            if found is None:
                raise HepError(f"unknown [plot.style].name: {self.name}",
                               hint="mplhep's styles, 'hekit', or 'none'")
            pyplot.style.use(found)
        if self.figure:
            pyplot.rcParams["figure.figsize"] = list(self.figure)
        if self.font_size:
            pyplot.rcParams["font.size"] = self.font_size
        if self.dpi:
            pyplot.rcParams["savefig.dpi"] = self.dpi


# ── drawing ──────────────────────────────────────────────────────────────────

@dataclass
class Result:
    page: str
    output: Path
    files: list[Path] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.files)

    @property
    def index(self) -> Path:
        return self.output


def histograms_on(page: Page) -> dict[str, list[tuple[str, Any]]]:
    """`{plot key: [(curve legend, object)]}` — what goes on each figure, in curve order."""
    found: dict[str, list[tuple[str, Any]]] = {}
    for curve in page.curves:
        for obj_path, obj in io.read(curve.path).items():
            if obj_path.startswith(("/REF/", "/RAW/")) or not io.is_binned_1d(obj):
                continue
            key = io.plot_key(obj_path)
            if key is None:
                continue
            found.setdefault(key, []).append((curve.legend or curve.name, obj))

    # `hep proc`'s derived histograms are results in their own right (12 §2.2), so they get their
    # own figure rather than being overlaid on someone else's.
    fits = getattr(page, "fits", None)
    if fits is not None and getattr(fits, "path", None) is not None:
        for obj_path, obj in io.read(fits.path).items():
            if not io.is_binned_1d(obj):
                continue                                # a fitted curve: `fits_on` draws those
            key = io.plot_key(obj_path) or obj_path
            found.setdefault(key, []).append((obj.title() or obj_path, obj))
    return found


def fits_on(page: Page) -> dict[str, list[tuple[str, Any]]]:
    """`{plot key: [(name, scatter)]}` — the fitted curves for each figure (12 §3).

    A fit is a `Scatter2D`, not a histogram, so it is collected separately from `histograms_on`:
    it has no bins, takes no part in the ratio panel, and must not be voided or auto-ranged.
    """
    found: dict[str, list[tuple[str, Any]]] = {}
    fits = getattr(page, "fits", None)
    if fits is None or getattr(fits, "path", None) is None:
        return found
    for obj_path, obj in io.read(fits.path).items():
        key = io.plot_key(obj_path)
        if key is None:
            continue
        found.setdefault(key, []).append((str(obj.title() or "fit"), obj))
    return found


def reference_on(page: Page) -> dict[str, Any]:
    """The reference object for each plot, when a data file was overlaid."""
    found: dict[str, Any] = {}
    if page.data is None or page.data.path is None:
        return found
    for obj_path, obj in io.read(page.data.path).items():
        key = io.plot_key(obj_path)
        if key is not None and io.is_binned_1d(obj):
            found[key] = obj
    return found


def _steps(obj: Any) -> tuple[list[float], list[float], list[float]]:
    """(edges, values, errors) with NaN bins left as NaN so voids stay gaps."""
    edges = io.edges_of(obj) or []
    values = io.values_of(obj)
    errors = []
    for index in range(1, len(values) + 1):
        try:
            errors.append(float(obj.bin(index).totalErrAvg()))
        except Exception:                                  # a bin whose errors were removed (a void)
            errors.append(float("nan"))
    return edges, values, errors


def draw_one(key: str, curves: list[tuple[str, Any]], reference: Any | None,
             settings: dict[str, Any], output: Path, *, formats=("pdf", "png"),
             ratio: bool = True, data_legend: str = "Data",
             fits: list[tuple[str, Any]] | None = None) -> list[Path]:
    """One figure, with a ratio panel when there is something to divide by."""
    import matplotlib.pyplot as pyplot
    import numpy

    wanted_ratio = ratio and settings.get("ratio", True) and (reference is not None
                                                              or len(curves) > 1)
    if wanted_ratio:
        figure, (axes, lower) = pyplot.subplots(
            2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1], "hspace": 0.06})
    else:
        figure, axes = pyplot.subplots()
        lower = None

    # mkhtml's rule: the denominator is the reference when there is one, else the first curve.
    denominator = reference if reference is not None else (curves[0][1] if curves else None)

    for name, scatter in (fits or []):
        # A smooth line, drawn under the data: a fit is a claim about the curve, not another
        # measurement, so it must not look like one.
        try:
            xs = [float(point.x()) for point in scatter.points()]
            ys = [float(point.y()) for point in scatter.points()]
        except Exception:
            continue
        if xs:
            axes.plot(xs, ys, linestyle="-", linewidth=1.4, color="0.25", zorder=1.5, label=name)

    for legend, obj in curves:
        edges, values, errors = _steps(obj)
        if not edges:
            continue
        axes.stairs(values, edges, label=legend)
        centres = [(edges[index] + edges[index + 1]) / 2 for index in range(len(values))]
        axes.errorbar(centres, values, yerr=errors, fmt="none", elinewidth=1.0, alpha=0.7)
        if lower is not None and denominator is not None:
            base = io.values_of(denominator)
            if len(base) == len(values):
                with numpy.errstate(divide="ignore", invalid="ignore"):
                    ratios = [value / other if other else float("nan")
                              for value, other in zip(values, base)]
                lower.stairs(ratios, edges)

    if reference is not None:
        edges, values, errors = _steps(reference)
        centres = [(edges[index] + edges[index + 1]) / 2 for index in range(len(values))]
        axes.errorbar(centres, values, yerr=errors, fmt="o", color="black", label=data_legend,
                      markersize=4)
        if lower is not None:
            lower.axhline(1.0, color="black", linewidth=1.0)

    axes.set_title(settings.get("title", ""))
    axes.set_ylabel(settings.get("ylabel", ""))
    if settings.get("logy"):
        axes.set_yscale("log")
    if settings.get("logx"):
        axes.set_xscale("log")
    if settings.get("xmin") is not None or settings.get("xmax") is not None:
        axes.set_xlim(settings.get("xmin"), settings.get("xmax"))
    if settings.get("ymin") is not None or settings.get("ymax") is not None:
        axes.set_ylim(settings.get("ymin"), settings.get("ymax"))
    if curves:
        # `LegendTitle` is where an analysis states the cuts a plot was made under; mkhtml draws it
        # as a legend header, so this does too.
        axes.legend(loc="best", title=settings.get("legend_title") or None)

    bottom = lower if lower is not None else axes
    bottom.set_xlabel(settings.get("xlabel", ""))
    if lower is not None:
        lower.set_ylabel(settings.get("ratio_ylabel", "ratio"), fontsize="small")
        lower.set_ylim(settings.get("ratio_ymin", 0.5), settings.get("ratio_ymax", 1.5))

    output.mkdir(parents=True, exist_ok=True)
    stem = key.strip("/").replace("/", "_")
    written = []
    for suffix in formats:
        path = output / f"{stem}.{suffix}"
        figure.savefig(path)
        written.append(path)
    pyplot.close(figure)
    return written


def draw(page: Page, output: Path, *, style: Style | None = None,
         data_legend: str = "Data") -> Result:
    """Draw every plot of a page into `output`, one file per format."""
    import matplotlib

    matplotlib.use("Agg")                                  # no display, ever: this runs in batch
    style = style or Style()
    style.apply()

    result = Result(page=page.name, output=output)
    curves = histograms_on(page)
    if not curves:
        raise HepError(f"page {page.name} has nothing to draw",
                       hint="the results hold no 1D histograms for this analysis")
    references = reference_on(page)
    fits = fits_on(page)

    for key in sorted(curves):
        settings = plot_settings(page, key)
        try:
            result.files += draw_one(key, curves[key], references.get(key), settings, output,
                                     formats=style.formats, ratio=style.ratio,
                                     data_legend=data_legend, fits=fits.get(key))
        except Exception as error:                         # noqa: BLE001 - one bad plot, not the page
            result.skipped[key] = str(error)
    return result


def index_html(result: Result, page: Page) -> Path:
    """A plain index so a page of figures is browsable like the mkhtml one."""
    rows = []
    for path in sorted(result.files):
        if path.suffix == ".png":
            rows.append(f'<figure><img src="{path.name}" alt="{path.stem}">'
                        f"<figcaption>{path.stem}</figcaption></figure>")
    body = "\n".join(rows) or "<p>no figures</p>"
    html = (f"<!doctype html>\n<meta charset=\"utf-8\">\n<title>{page.name}</title>\n"
            "<style>body{font-family:sans-serif;margin:2rem}figure{display:inline-block;margin:1rem}"
            "img{max-width:46vw}</style>\n"
            f"<h1>{page.name}</h1>\n<p>{page.analysis}</p>\n{body}\n")
    path = result.output / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
