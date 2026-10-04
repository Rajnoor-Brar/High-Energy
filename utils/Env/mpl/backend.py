"""utils/Env/mpl/backend.py — `[plot] backend = "mpl"`: the pages drawn with matplotlib, in this process.

docs/04_Config_Reference.md §11, docs/03_Plots.md §9 (V71). The same pages the yoda backend hands
rivet-mkhtml, drawn without it. **Until the user has verified them, they must match mkhtml's pages**, so
everything mkhtml decides comes from the library mkhtml runs on, called directly:

* the plot settings: rivet's `get_plot_configs` over the analyses' `.plot` files and the block the yoda
  backend writes for the page (`_plot_block`: ranges, log axes, legend, overridden labels);
* the curves: the points' objects with the page's voids, normalisation and band envelopes (the yoda
  backend's own transforms, applied in memory), made scatters by `mkPlotFriendlyScatter`;
* the numbers: YODA's `reshape`, `rebinTo` and `safeDiv` (so the ratio is mkhtml's, rebinned onto the
  reference by inverse relative variance), its legend placement (`legendDefaults`), colour cycle
  (`LineProperties`) and text macros (`preprocess`), and YODA's `default.mplstyle`;
* the drawing: the calls of mkhtml's generated script (YODA's `mkPlottingScript1D`), made here, then the
  yoda backend's own fixes (ratio ticks, a "best" legend, the titles), so no script is written or rerun.

The values are rounded to the 7 digits mkhtml's data files hold. Pages go to results/…/plots/mpl/, laid
out as Paint's, with an index.html (INDEX). Like the yoda backend, it honours only the style keys mkhtml
can (until verified, it is mkhtml's look).
"""

from __future__ import annotations

import importlib.util
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from runner.errors import HepError
from runner.hepfiles import base_path
from runner.labels import mathtext
from runner.paths import build_root

INDEX = True                               # the core writes plots/mpl/index.html (V70's write_index)
_YODA = Path(__file__).resolve().parents[1] / "yoda" / "backend.py"
_STYLES = ["-", "--", "-.", ":"]
_BREAK = '"+"\\n"+r"'                    # YODA's preprocess writes \newline as code for the script's r"…" strings


def _raw(text: str) -> str:
    """A text as mkhtml's script has it in an r"…" literal (the legend's): its \newline a line break."""
    return text.replace(_BREAK, "\n")


def _mkhtml_backend():
    """The yoda backend's module: its transforms and fixes, which mkhtml's pages are made with."""
    spec = importlib.util.spec_from_file_location("hep_yoda_backend", _YODA)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(settings: dict, beside_root: bool = False, curve_styles: list[dict] = ()) -> None:
    """mkhtml's limits, as the yoda backend's (the pages are mkhtml's until verified)."""
    try:
        _mkhtml_backend().validate(settings, beside_root=beside_root, curve_styles=curve_styles)
    except HepError as error:
        raise HepError(str(error.message).replace('backend = "yoda"', 'backend = "mpl"').replace("the yoda backend", "the mpl backend"),
                       where=error.where, hint=error.hint) from None


def draw(cells: dict, settings: dict, say) -> int:
    """Every page of every cell; returns how many were not drawn."""
    pages = [p for every in cells.values() for p in every]
    for page in pages:
        page.output.parent.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(len(pages), os.cpu_count() or 1))
    jobs = [(page, settings) for page in pages]
    if workers == 1:
        outcomes = [_one(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(_one, jobs))
    failed = 0
    for page, why in zip(pages, outcomes):
        if why:
            failed += 1
            say(f"plot (mpl): {page.name} failed: {why}")
    say(f"plot (mpl): {len(pages) - failed} of {len(pages)} page(s) drawn in {len(cells)} page set(s)")
    return failed


def _one(job) -> str:
    page, settings = job
    try:
        _page(page, settings)
        return ""
    except Exception as error:                     # one page's failure is that page's (as Paint's)
        return f"{type(error).__name__}: {error}"


# ── one page ───────────────────────────────────────────────────────────────────────────────────

def _page(page, settings: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import yoda

    yb = _mkhtml_backend()
    os.environ["RIVET_ANALYSIS_PATH"] = str(build_root() / "Rivet")
    os.environ["RIVET_DATA_PATH"] = os.pathsep.join(filter(None, [str(build_root() / "Rivet"), os.environ.get("RIVET_DATA_PATH")]))
    hists, features, window = _inputs(yb, yoda, page)
    with matplotlib.rc_context():
        plt.style.use(_style_file(yoda))
        plt.rcParams["legend.fontsize"] = page.style["text"]["legend"]     # what LegendFontSize sets (V50)
        plt.rcParams["legend.title_fontsize"] = page.style["text"]["header"]
        fig = _figure(plt, hists, features, page, yb, window)
        formats = settings.get("formats", ["pdf"])
        titled = any(page.document["page"].get(k) for k in ("title", "title_left", "title_right"))
        for fmt in (["pdf"] if formats == "default" else formats):
            fig.savefig(f"{page.output}.{fmt}", format=fmt.upper(), **({"bbox_inches": "tight"} if titled else {}))
        plt.close(fig)


def _style_file(yoda) -> str:
    for where in yoda.getYodaDataPath():
        path = Path(where) / "plotting" / "default.mplstyle"
        if path.is_file():
            return str(path)
    raise HepError("YODA's default.mplstyle is not found", hint=f"searched {yoda.getYodaDataPath()}")


def _inputs(yb, yoda, page):
    """The page's curves as mkhtml gets them, its plot settings, and its ratio window."""
    import yoda.plotting.utils as putils
    from rivet.plotting.make_plots import type_conversion
    from yoda.plotting.mlp_preprocessor import preprocess
    import rivet

    doc, area = page.document["page"], page.document["page"].get("normalise") == "area"
    voided = page.ranges.get("voided", []) if not page.overlay else []
    read: dict = {}

    def objects(path):
        if path not in read:
            read[path] = yoda.read(str(path))
        return read[path]

    curves = []                                    # (title, object) per MC curve, mkhtml's order
    bands = page.bands or [[]] * len(page.sources)
    if page.overlay:
        for (source, variant), curve in zip(zip(page.sources, page.variants), page.document["curve"]):
            copy = objects(source)[variant].clone()
            copy.setPath(page.object)
            if area:
                yb._normalise(copy)
            curves.append((mathtext(curve["label"]), copy, {"ConnectBins": 0} if doc.get("markers") else {}))
    else:
        order = list(dict.fromkeys(page.sources))   # one file per point, as the yoda backend's argv
        for source in order:
            mine = [(v, b, c) for s, v, b, c in zip(page.sources, page.variants, bands, page.document["curve"]) if s == source]
            for variant, members, curve in sorted(mine, key=lambda m: m[0]):   # mkhtml sorts a file's variants
                copy = objects(source)[variant].clone()
                if voided:
                    yb._void(copy, voided, source)
                if area:
                    yb._normalise(copy)
                if members:
                    drawn = []
                    for member, mvariant in members:
                        m = objects(member)[mvariant].clone()
                        if voided:
                            yb._void(m, voided, member)
                        if area:
                            yb._normalise(m)
                        drawn.append(m)
                    yb._envelope(copy, drawn)
                look = {k: v for k, v in {"LineColor": curve.get("style", {}).get("colour"),
                                          "LineStyle": curve.get("style", {}).get("line"),
                                          "LineWidth": curve.get("style", {}).get("width")}.items() if v is not None}
                if members:
                    look.update(ErrorBand=1, ErrorBars=0)
                if doc.get("markers"):                         # V86: points, as mkhtml draws data
                    look["ConnectBins"] = 0
                title = mathtext(curve["label"].split(" [")[0]) + rivet.extractOptionString(variant)
                curves.append((title, copy, look))

    reference = None
    if page.data and page.ranges.get("data_bins", 0) > 0 and not page.overlay:
        reference = yb._reference(yoda, page)

    window = None
    if doc["ratio"]:
        drawn = [yb._bins(c) for _, c, _ in curves]
        ref = yb._bins(reference) if reference is not None else (drawn[0] if drawn else None)
        if drawn:
            window = yb.ratio_window(drawn + ([ref] if reference is not None else []), ref, page.ranges["x"], page.style["ratio"])

    # the settings: the analysis's .plot files, then the page's block (rivet's own reader)
    from rivet.plotting import plot2yaml
    block = page.config.with_name(page.config.name + ".mpl.plot")
    block.write_text(yb._plot_block(page, window), encoding="utf-8")
    plot_id = base_path(page.object)
    features = plot2yaml.get_plot_configs(plot_id, plotdirs=rivet.getAnalysisPlotPaths(), config_files=[str(block)])
    features.pop("LegendFontSize", None)                       # its rcParams are set directly
    features["RatioPlot"] = int(bool(doc["ratio"]))
    if reference is not None and doc["ratio"]:                 # rivet's: the reference's, over the .plot's
        features["RatioPlotYLabel"] = reference.annotation("RatioPlotYLabel", "MC/Data")
    for key in list(features):
        if any(key.endswith(s) for s in ("Title", "Label")) and isinstance(features[key], str):
            features[key] = preprocess(features[key])

    hists = {}                                                 # label → (scatter, its features)
    if reference is not None:
        reference.setAnnotation("IsRef", True)
        label = mathtext(page.document["data"]["label"])
        hists[label] = (putils.mkPlotFriendlyScatter(reference), {"IsRef": True, "LineColor": "black", "Title": preprocess(label)})
    for i, (title, obj, look) in enumerate(curves):
        feats = {"Title": preprocess(str(type_conversion(title))), "ErrorBars": 1}
        feats.update({k: type_conversion(str(v)) for k, v in look.items()})
        key = f"{i:02d}"
        while key in hists:
            key = "_" + key
        hists[key] = (putils.mkPlotFriendlyScatter(obj), feats)
    return hists, features, window


def _r(values):
    """As mkhtml's data file holds them: 7 significant digits."""
    import numpy as np
    return np.array([float(f"{v:.6e}") for v in np.asarray(values, dtype=float).ravel()]).reshape(np.shape(values))


def _figure(plt, hists: dict, features: dict, page, yb, window):
    """mkhtml's mkPlottingScript1D and mkCurves1D, as calls (YODA 2.1)."""
    import matplotlib as mpl
    import numpy as np
    import yoda.plotting.utils as putils
    from yoda.plotting.fetch_data import LineProperties

    data = {k: h for k, (h, _) in hists.items()}
    feats = [f for _, f in hists.values()]
    logx, logy = int(features.get("LogX", 0)), int(features.get("LogY", 1))
    nonzero = any(np.any(h.yVals()) for h in data.values())
    xscale, yscale = ("log" if logx else "linear"), ("log" if logy and nonzero else "linear")

    xmin = float(features.get("XMin", min(min(h.xMins()) for h in data.values())))
    xmax = float(features.get("XMax", max(max(h.xMaxs()) for h in data.values())))
    xlim = (xmin, xmax)
    ylim = _ylim(features, data)

    # the legend, as mkhtml's 'Legend'
    entries = []
    for i, label in enumerate(data):
        entry = str(feats[i].get("Title", f"Curve {i + 1}")).replace(".yoda.gz", "").replace(".yoda", "")
        if entries and entry == "":
            continue
        entry = entry or "Curve 0"
        if entry.count("_") and entry.count("$") < 2:
            entry = entry.replace("_", r"\_")
        entries.append(_raw(entry))
    posx, posy, anchor, align = putils.legendDefaults(next(iter(data.values())), xlim, ylim, logx, logy)
    legend_xy = (float(features.get("LegendXPos", posx)), float(features.get("LegendYPos", posy)))
    anchor, align = features.get("LegendAnchor", anchor), features.get("LegendAlign", align)

    ratios = [list(data)] if features.get("RatioPlot", 1) else []
    ratio_logy = features.get("RatioPlotLogY", 0)

    fig_w, fig_h = plt.rcParams["figure.figsize"]
    specs = [float(features.get("PlotSizeY", 6))] + [float(features.get("RatioPlotYSize", 3)) for _ in ratios]
    fig_w *= float(features.get("PlotSizeX", 10)) / 10.0
    fig_h *= sum(specs) / 9.0
    if ratios:
        fig, (ax, rax) = plt.subplots(2, 1, sharex=True, figsize=(fig_w, fig_h), gridspec_kw={"height_ratios": tuple(specs)})
    else:
        fig, ax = plt.subplots(1, 1)
        rax = None
    plt.subplots_adjust(left=plt.rcParams["figure.subplot.left"], right=plt.rcParams["figure.subplot.right"],
                        top=plt.rcParams["figure.subplot.top"], bottom=plt.rcParams["figure.subplot.bottom"])
    if rax is not None:
        lo, hi = float(features.get("RatioPlotYMin", 0.5)), float(features.get("RatioPlotYMax", 1.4999))
        tick = (hi - lo) / 5.0
        rax.yaxis.set_major_locator(mpl.ticker.MultipleLocator(round(tick, -int(math.floor(math.log10(abs(tick)))))))
        rax.set_ylim(lo, hi)
        rax.set_ylabel(features.get("RatioPlotYLabel", "Ratio"))

    defaults = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    colours, nxt = [], 0
    for f in feats:
        if "LineColor" in f:
            colours.append(f["LineColor"])
        else:
            colours.append(defaults[nxt % len(defaults)])
            nxt += 1
    for (label, h), f in zip(data.items(), feats):            # command-line tags become annotations
        for tag in ("Title", "LineStyle", "LineWidth", "ErrorBars", "ErrorBand", "ConnectBins"):
            if tag in f:
                h.setAnnotation(tag, f[tag])
        if f.get("IsRef"):
            h.setAnnotation("ConnectBins", 0)

    handles = _curves(ax, rax, data, feats, colours, plt)

    legend = ax.legend(list(handles.values()), entries, title=_raw(str(features.get("LegendTitle", ""))),
                       alignment="right" if align == "r" else "left",
                       **({"loc": "best"} if page.style["legend"]["position"] == "best" else {"loc": anchor, "bbox_to_anchor": legend_xy}),
                       **({"markerfirst": False} if align == "r" else {}))
    ax.add_artist(legend)

    x_label, y_label = features.get("XLabel", ""), features.get("YLabel", "")
    if rax is not None:
        rax.set_xlabel(x_label)
        rax.xaxis.set_label_coords(1.0, float(features.get("XLabelSep", -0.15)))
    else:
        ax.set_xlabel(x_label)
        ax.xaxis.set_label_coords(1.0, float(features.get("XLabelSep", -0.05)))
    ax.set_ylabel(y_label, ha="right", va="top")
    ax.yaxis.set_label_coords(float(features.get("YLabelSep", -0.11)), 1.0)
    ax.set_title(features.get("Title", ""), loc="left")
    ax.set_xscale(xscale)
    ax.set_yscale(yscale)
    if rax is not None:
        rax.set_yscale("log" if ratio_logy else "linear")
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    plt.rcParams["xtick.top"] = features.get("XTwosidedTicks", True)
    plt.rcParams["ytick.right"] = features.get("YTwosidedTicks", True)
    if logy:
        ax.yaxis.set_major_locator(mpl.ticker.LogLocator(base=10.0, numticks=np.inf))
        ax.yaxis.set_minor_locator(mpl.ticker.LogLocator(base=10.0, subs=np.arange(0.1, 1, 0.1), numticks=np.inf))
    if rax is not None and ratio_logy:
        rax.yaxis.set_major_locator(mpl.ticker.LogLocator(base=10.0, numticks=np.inf))
        rax.yaxis.set_minor_locator(mpl.ticker.LogLocator(base=10.0, subs=np.arange(0.1, 1, 0.1), numticks=np.inf))
    if rax is not None:
        fig.align_ylabels((ax, rax))
        # the yoda backend's fix: ratio.divisions, ROOT's rule (ratio_ticks)
        lo, hi = rax.get_ylim()
        divisions = int(page.style["ratio"]["divisions"])
        n1, n2 = max(divisions % 100, 1), (divisions // 100) % 100
        rax.yaxis.set_major_locator(mpl.ticker.MultipleLocator(yb._step((hi - lo) / n1)))
        if n2 > 1:
            rax.yaxis.set_minor_locator(mpl.ticker.AutoMinorLocator(n2))
    _titles(ax, page)
    return fig


def _ylim(features: dict, data: dict) -> tuple[float, float]:
    """mkhtml's y range when the page leaves it to the tool (no gutter); else the page's YMin/YMax."""
    import numpy as np
    import yoda.plotting.utils as putils
    biggest = np.nanmax([putils.safeMax(h.yVals(), 1.0) for h in data.values()])
    if features.get("YMax") is not None:
        ymax = float(features["YMax"])
    elif features.get("LogY", 1):
        ymax = 1.1 * 10 ** math.ceil(math.log10(biggest)) if biggest > 0 else 1.0
    else:
        ymax = 1.1 * biggest if biggest > 0.0 else 0.9 * biggest
    smallest = np.nanmin([putils.safeMin(h.yVals(), 0.0) for h in data.values()])
    positive = [y for h in data.values() for y in h.yVals() if y > 0]
    if features.get("YMin") is not None:
        ymin = float(features["YMin"])
    elif features.get("LogY", 1):
        ymin = 0.9 * 10 ** math.floor(math.log10(min(positive))) if positive else 0.11 * ymax
    elif features.get("ShowZero", 1):
        ymin = 0 if smallest > -1e-4 else 1.1 * smallest
    else:
        ymin = 1.1 * smallest if smallest < -1e-4 else 0 if smallest < 1e-4 else 0.9 * smallest
    if math.isclose(ymin, ymax):
        ymax = 10 * ymin if ymin else 1.0
    return float(ymin), float(ymax)


def _curves(ax, rax, data: dict, feats: list, colours: list, plt) -> dict:
    """mkCurves1D's numbers and the script's drawing of them: the main panel, then the ratio panel."""
    import numpy as np
    import yoda.plotting.utils as putils
    from yoda.plotting.fetch_data import LineProperties

    errors = [f.get("ErrorBars", 1) for f in feats]
    props = LineProperties(colours, _STYLES)
    ref_label, ref = next(iter(data.items()))
    ref_x = 0.5 * (ref.xMins() + ref.xMaxs())
    ref_edges = np.append(ref.xMins(), max(ref.xMaxs()))
    ratio_keys = ["RatioPlot"] if rax is not None else []
    handles, styles = {}, {}
    for i, (k, ao) in enumerate(data.items()):
        colidx, linestyle = next(props)
        zorder = 5 + i
        x = 0.5 * (ao.xMins() + ao.xMaxs())
        edges = np.append(ao.xMins(), max(ao.xMaxs()))
        y, xerr, yerr = putils.reshape(ref_x, ref_edges, ao)
        y, xerr, yerr = _r(y), np.abs(_r(xerr)), np.abs(_r(yerr))
        band = None
        if str(ao.annotation("ErrorBand", "0")) != "0":
            by, _, be = putils.reshape(ref_x, ref_edges, ao)
            dn, up = by - np.abs(be[0]), by + np.abs(be[1])
            band = (_r(np.insert(dn, 0, dn[0])), _r(np.insert(up, 0, up[0])))
        s = {"color": colours[colidx], "zorder": zorder}
        for r, pre in enumerate([""] + ratio_keys):
            histstyle = ao.annotation(pre + "ConnectBins", s["histstyle"] if pre else 1)
            s[pre] = {
                "linestyle": ao.annotation(pre + "LineStyle", ao.annotation("LineStyle", linestyle)),
                "linewidth": ao.annotation(pre + "LineWidth", ao.annotation("LineWidth", 1)),
                "alpha": ao.annotation(pre + "LineOpacity", ao.annotation("LineOpacity", 1.0)),
                "marker": ao.annotation(pre + "MarkerStyle", s[""]["marker"] if pre else "none" if histstyle else "o"),
                "markersize": ao.annotation(pre + "MarkerSize", ao.annotation("MarkerSize", 2)),
                "capsize": ao.annotation(pre + "ErrorCapSize", ao.annotation("ErrorCapSize", 0.0)),
                "xbars": int(ao.annotation(pre + "ErrorBars", ao.annotation("ErrorBars", int(errors[i])))),
                "ybars": int(ao.annotation(pre + "ErrorBars", ao.annotation("ErrorBars", int(errors[i] and True)))),
                "steps": None if ao.annotation(pre + "ConnectMarkers", ao.annotation("ConnectMarkers", 0)) else "steps-pre",
                "histstyle": histstyle,
            }
            if not pre:
                s["histstyle"] = histstyle
        styles[k] = s
        main = s[""]
        if not all(np.isnan(v) for v in y):
            if main["histstyle"]:
                xpos = edges if main["steps"] else x
                ypos = np.insert(y, 0, y[0]) if main["steps"] else y
                ax.plot(xpos, ypos, color=s["color"], linestyle=main["linestyle"], alpha=main["alpha"],
                        linewidth=main["linewidth"], drawstyle=main["steps"], solid_joinstyle="miter", zorder=zorder, label=k)
            tmp = ax.errorbar(x, y, xerr=np.array(xerr) * main["xbars"], yerr=np.array(yerr) * main["ybars"],
                              fmt=main["marker"], capsize=main["capsize"], alpha=main["alpha"], markersize=main["markersize"],
                              ecolor=s["color"], color=s["color"], zorder=zorder)
            tmp[-1][0].set_linestyle(main["linestyle"])
            tmp[-1][0].set_linewidth(main["linewidth"])
            if ao.annotation("Title", None):
                handles[k] = tmp
            if band is not None:
                ax.fill_between(edges, band[0], band[1], color=s["color"], alpha=0.2, hatch=None, step="pre",
                                zorder=zorder, edgecolor=None)
    if rax is None:
        return handles

    # the ratio panel: every curve over the first (the reference), on its bins (mkhtml's rebinning)
    ref_y = putils.reshape(ref_x, ref_edges, ref, True)[0]
    ref_xerr = [np.abs(ref_x - ref_edges[:-1]), np.abs(ref_edges[1:] - ref_x)]
    for k, ao in data.items():
        s, rs = styles[k], styles[k]["RatioPlot"]
        y, _, yerr = putils.reshape(ref_x, ref_edges, ao, True)
        ratio = _r(putils.safeDiv(y, ref_y))
        downs, ups = _r(np.abs(putils.safeDiv(yerr[0], ref_y))), _r(np.abs(putils.safeDiv(yerr[1], ref_y)))
        if all(np.isnan(v) for v in ratio):
            continue
        if rs["histstyle"]:
            xpos = ref_edges if rs["steps"] else ref_x
            ypos = np.insert(ratio, 0, ratio[0]) if rs["steps"] else ratio
            rax.plot(xpos, ypos, color=s["color"], linewidth=s[""]["linewidth"], linestyle=rs["linestyle"], alpha=rs["alpha"],
                     drawstyle=rs["steps"], zorder=s["zorder"], solid_joinstyle="miter")
        tmp = rax.errorbar(ref_x, ratio, xerr=np.array(ref_xerr) * rs["xbars"], yerr=np.array([downs, ups]) * rs["ybars"],
                           fmt=rs["marker"], capsize=rs["capsize"], alpha=rs["alpha"], markersize=rs["markersize"],
                           ecolor=s["color"], color=s["color"])
        tmp[-1][0].set_linestyle(rs["linestyle"])
        tmp[-1][0].set_linewidth(rs["linewidth"])
        if str(ao.annotation("ErrorBand", "0")) != "0":
            by, _, be = putils.reshape(ref_x, ref_edges, ao, True)
            den = np.insert(ref_y, 0, ref_y[0])
            dn, up = by - np.abs(be[0]), by + np.abs(be[1])
            rax.fill_between(ref_edges, _r(putils.safeDiv(np.insert(dn, 0, dn[0]), den)), _r(putils.safeDiv(np.insert(up, 0, up[0]), den)),
                             color=s["color"], hatch=None, alpha=0.2, step="pre", zorder=s["zorder"], edgecolor=None)
    return handles


def _titles(ax, page) -> None:
    """The yoda backend's titles(): title above the frame, title_left and title_right over its corners."""
    settings, text = page.document["page"], page.style["text"]
    left, right, main = (mathtext(settings.get(k, "")) for k in ("title_left", "title_right", "title"))
    place = dict(xycoords="axes fraction", textcoords="offset points", va="bottom")
    if left:
        ax.annotate(left, (0, 1), xytext=(0, 3), ha="left", fontsize=text["corner"], **place)
    if right:
        ax.annotate(right, (1, 1), xytext=(0, 3), ha="right", fontsize=text["corner"], **place)
    if main:
        lift = 3 + (1.5 * text["corner"] if left or right else 0)
        ax.annotate(main, (0.5, 1), xytext=(0, lift), ha="center", fontsize=text["page_title"], **place)
