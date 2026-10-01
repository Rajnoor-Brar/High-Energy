"""utils/Env/yoda/backend.py — `[plot] backend = "yoda"`: the same pages drawn by rivet-mkhtml.

docs/04_Config_Reference.md §11, V10/V11. The runner hands over the pages it wrote for Paint, with
Paint's --dump-ranges of each: the x and y ranges (auto_range, gutters; none where no gutter leaves
them to the tool) and the voided bins. Per
plot_points cell this writes

* the curves' YODAs with the voided bins blanked (value NaN, no errors), as v1 did;
* reference.yoda: the mapped reference objects, renamed /REF/<analysis>/<object> so that mkhtml
  pairs them with the MC (its own reference lookup is off: explicit only, L18);
* pages.plot: per object the ranges, log axes, legend corner (style legend.position), and the [plot.object] label
  overrides in LaTeX; the rest of the labels mkhtml reads from the analysis's own .plot;

and runs rivet-mkhtml into results/…/plots/<cell>/. mkhtml always writes PDF and PNG; svg and eps
are added. Of the style (utils/Apps/Paint/base.toml) mkhtml can honour a legend corner and the ratio
pad's y ticks (ratio.divisions: YODA's generator puts them at a fifth of the range, so each page's
script is redone with ROOT's rule and run again); any other [plot.style] or
[plot.object."<glob>"].style key, and [plot].root_style, are refused. Beside
the root backend (backend = ["root", "yoda"]) they are Paint's to honour and are allowed, except a
legend placed at [x, y]: the two page sets would then disagree about where the legend is, not
only about its look.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import sys
from pathlib import Path

from runner.errors import HepError
from runner.paths import build_root

FORMATS = {"pdf": None, "png": None, "svg": "SVG", "eps": "EPS"}       # None: mkhtml writes it anyway
LEGEND = {"top-right": {"LegendAlign": "r"}, "top-left": {"LegendAlign": "l", "LegendXPos": "0.05"},
          "bottom-right": {"LegendAlign": "r", "LegendYPos": "0.4"},
          "bottom-left": {"LegendAlign": "l", "LegendXPos": "0.05", "LegendYPos": "0.4"},
          "best": {"LegendAlign": "r"}}                # then matplotlib's loc='best' (best_legend)
_MATH = {"bf": "mathbf", "it": "mathit", "LT": "<", "GT": ">"}
HONOURED = {("legend", "position"), ("ratio", "divisions"), ("ratio", "range"), ("ratio", "limits"), ("text", "legend"), ("text", "header")}             # style keys mkhtml can follow
MARK = "# ratio ticks: ratio.divisions (utils/Env/yoda/backend.py)"


def validate(settings: dict, beside_root: bool = False) -> None:
    hint = 'rivet-mkhtml has its own look; drop the key, or use backend = "root"'
    if "root_style" in settings and not beside_root:
        raise HepError('[plot].root_style cannot be honoured by backend = "yoda"', where="[plot].root_style", hint=hint)
    layers = [("[plot.style]", settings.get("style", {}))] + [
        (f'[plot.object."{glob}"].style', table.get("style", {})) for glob, table in settings.get("object", {}).items()]
    for where, layer in layers:
        for table, keys in layer.items():
            for key, value in keys.items() if isinstance(keys, dict) else [(None, keys)]:
                if value == "default":                  # sets nothing, so there is nothing to honour
                    continue
                placed = (table, key) == ("legend", "position") and not isinstance(value, str)
                if placed or (not beside_root and (table, key) not in HONOURED):
                    name = f"{table}.{key}" if key else table
                    raise HepError(f'{where} {name} cannot be honoured by backend = "yoda"', where=where,
                                   hint=hint + " (only legend.position, text.legend, text.header and ratio.divisions, range and limits carry over)")


def latex(text: str) -> str:
    """TLatex → matplotlib mathtext for the common subset, word by word: '#sqrt{s} = 28.6 GeV' →
    '$\\sqrt{s}$ = 28.6 GeV'. TLatex's rules hold (V41): only `_{…}`, `^{…}` and `#<name>` are math;
    a bare _ or ^, and the escapes \\_ \\^ \\#, are the characters ('PDF4LHC21_40' stays as written)."""
    def word(w: str) -> str:
        if not re.search(r"(?<!\\)(?:[_^]\{|#[A-Za-z])", w):
            return re.sub(r"\\([_^#\\])", r"\1", w)
        w = re.sub(r"(?<!\\)#([A-Za-z]+)", lambda m: _MATH.get(m.group(1), "\\" + m.group(1)), w)
        w = re.sub(r"\\_|(?<!\\)_(?!\{)", "\x00", w).replace("\x00", r"\_")     # literal underscores in math
        return f"${w}$"
    return " ".join(word(w) for w in text.split(" ")).replace(":", " ")    # ':' separates mkhtml options


def _base(path: str) -> str:
    """/photo_eic:R=0.4/d01-x01-y01 → /photo_eic/d01-x01-y01 (plot keys and references ignore options)."""
    analysis, _, rest = path.strip("/").partition("/")
    return f"/{analysis.split(':')[0]}/{rest}"


def _voided(yoda, source: Path, pages: list, target: Path) -> Path:
    objects = yoda.read(str(source))
    changed = False
    for page in pages:
        voided = page.ranges.get("voided", [])
        for path in {v for s, v in zip(page.sources, page.variants) if s == source} if voided else ():
            changed |= _void(objects[path], voided, source)
    if not changed:
        return source
    yoda.write(list(objects.values()), str(target))
    return target


def _void(estimate, voided: list, source: Path) -> bool:
    if "Estimate" not in estimate.type():
        raise HepError(f"cannot void bins of {estimate.path()}, a {estimate.type()}", where=str(source))
    for index in voided:
        estimate.bin(index).setVal(float("nan"))
        estimate.bin(index).rmErrs()
    return True


def _reference(yoda, page):
    """The mapped reference object, cut to the run of bins Paint aligned to the MC edges (mkhtml's
    ratio needs every reference edge to be an MC edge), renamed /REF/<analysis>/<object>."""
    source = yoda.read(str(page.data[0]))[page.data[1]]
    lo, hi = page.ranges["data_x"]
    keep = [i for i in range(1, source.numBins() + 1)
            if source.bin(i).xMin() >= lo - 1e-9 * abs(lo) and source.bin(i).xMax() <= hi + 1e-9 * abs(hi)]
    edges = [source.bin(i).xMin() for i in keep] + [source.bin(keep[-1]).xMax()]
    out = yoda.BinnedEstimate1D(edges, "/REF" + _base(page.object))
    for k, i in enumerate(keep, start=1):
        out.bin(k).setVal(source.bin(i).val())
        for name in source.bin(i).sources():
            out.bin(k).setErr(source.bin(i).errDownUp(name), name)
    return out


def _bins(obj) -> list[tuple[float, float, float, float]]:
    """(x low, x high, value, error) per bin of a histogram (as drawn: per unit x) or an estimate."""
    estimate = obj.mkEstimate() if hasattr(obj, "mkEstimate") else obj
    out = []
    for i in range(1, estimate.numBins() + 1):
        b = estimate.bin(i)
        try:
            error = b.totalErrAvg()
        except Exception:                        # an estimate with no error source
            error = 0.0
        out.append((b.xMin(), b.xMax(), b.val(), error))
    return out


def ratio_window(curves: list, reference, x: tuple, ratio_style: dict) -> tuple[float, float]:
    """Paint's rule for the ratio pad (Draw.hh ratioRange), so both backends show the same window:
    at least `range`, widened to every ratio drawn (0.9 × (r − err), 1.1 × (r + err)) on bins in the
    x range, never past `limits` (V48). `curves` and `reference` are lists of `_bins`."""
    lo, hi = ratio_style["range"]
    by_edges = {(round(a, 9), round(b, 9)): (v, e) for a, b, v, e in reference}
    for curve in curves:
        for a, b, value, error in curve:
            ref = by_edges.get((round(a, 9), round(b, 9)))
            if ref is None or not ref[0] or not (b > x[0] and a < x[1]):
                continue
            r, err = value / ref[0], error / abs(ref[0])
            if math.isfinite(r):
                lo, hi = min(lo, 0.9 * (r - err)), max(hi, 1.1 * (r + err))
    limits = ratio_style["limits"]
    return max(lo, limits[0]), min(hi, limits[1])


def _plot_block(page, window: tuple[float, float] | None = None) -> str:
    settings = page.document["page"]
    (xlo, xhi), (ylo, yhi) = page.ranges["x"], page.ranges["y"]
    keys = {"XMin": f"{xlo:.10g}", "XMax": f"{xhi:.10g}", "YMin": f"{ylo:.10g}", "YMax": f"{yhi:.10g}",
            "LogX": str(int(settings["logx"])), "LogY": str(int(settings["logy"])),
            "RatioPlot": str(int(settings["ratio"])), **LEGEND[page.style["legend"]["position"]],
            # mkhtml writes `plt.rcParams['legend.fontsize'] = <value>` into the page's script as given, so
            # the title's size rides along: matplotlib sizes a legend title from legend.title_fontsize,
            # else from font.size, never from the entries' size (V50)
            "LegendFontSize": f"{page.style['text']['legend']:g}; "
                              f"plt.rcParams['legend.title_fontsize'] = {page.style['text']['header']:g}"}
    if window and settings["ratio"]:
        top = window[1] - 1e-4 * (window[1] - window[0])     # as mkhtml's 1.4999: no tick label at the pad's top
        keys["RatioPlotYMin"], keys["RatioPlotYMax"] = f"{window[0]:.6g}", f"{top:.6g}"
    for key, native in (("title", "Title"), ("x_label", "XLabel"), ("y_label", "YLabel")):
        if key in page.overrides:
            keys[native] = latex(settings[key])
    from runner.plot import labels_of, lines_of, macros
    for native, text in labels_of(page.object).items():  # mkhtml draws each line apart: close math per line (V47)
        if native in ("Title", "LegendTitle", "XLabel", "YLabel") and native not in keys:   # and our macros (V48)
            fixed = "\\newline".join(lines_of(macros(text)))
            if fixed != text:
                keys[native] = fixed
    if settings["logy"] and not ylo > 0:
        del keys["YMin"]
    for axis in ("x", "y"):                  # no gutter: the range is mkhtml's to choose, as it is ROOT's for Paint
        if page.ranges.get(f"{axis}_tool"):
            keys.pop(f"{axis.upper()}Min", None), keys.pop(f"{axis.upper()}Max", None)
    body = "".join(f"{k}={v}\n" for k, v in keys.items() if not (isinstance(v, str) and v in ("nan", "inf")))
    return f"# BEGIN PLOT {_base(page.object)}\n{body}# END PLOT\n"


def _step(width: float) -> float:
    """The smallest 1, 2 or 5 × 10^k at least `width`: ROOT's choice for at most n divisions."""
    power = 10.0 ** math.floor(math.log10(width))
    return next(m * power for m in (1, 2, 5, 10) if m * power >= width * (1 - 1e-9))


def best_legend(script: Path) -> bool:
    """legend.position = "best" (V49): mkhtml anchors its legend at a corner; matplotlib's own
    loc='best' puts it where it covers the fewest drawn points. Rewrites the script; True when it
    changed, and the script must run again."""
    text = script.read_text(encoding="utf-8")
    new = re.sub(r"loc='[a-z ]+',(\s*)bbox_to_anchor=\([^)]*\)", r"loc='best'", text)
    if new == text:
        return False
    script.write_text(new, encoding="utf-8")
    return True


def ratio_ticks(script: Path, divisions: int) -> bool:
    """The ratio pad's y ticks as ROOT's `divisions` (n1 + 100·n2) says: at most n1 labelled
    divisions of the pad's range, each cut into n2 by minor ticks. Rewrites mkhtml's script; True
    when it changed, and the script must run again."""
    text = script.read_text(encoding="utf-8")
    limits = re.search(r"ratio0_ax\.set_ylim\(([-+\d.eE]+), ([-+\d.eE]+)\)", text)
    save = text.find("plt.savefig(")
    if not limits or save < 0:
        return False
    lo, hi = float(limits.group(1)), float(limits.group(2))
    n1, n2 = max(divisions % 100, 1), (divisions // 100) % 100
    # just before the figure is saved: the script's later set_yscale() resets an axis's locators
    lines = (f"{MARK}\nratio0_ax.yaxis.set_major_locator(mpl.ticker.MultipleLocator({_step((hi - lo) / n1):g}))\n"
             + (f"ratio0_ax.yaxis.set_minor_locator(mpl.ticker.AutoMinorLocator({n2}))\n" if n2 > 1 else ""))
    old = re.search(re.escape(MARK) + r"\n(?:ratio0_ax\.yaxis\.set_m[a-z]+_locator\([^\n]*\)\n)+", text)
    if old and old.group(0) == lines:
        return False
    if old:
        text = text[:old.start()] + text[old.end():]
        save = text.find("plt.savefig(")
    script.write_text(text[:save] + lines + text[save:], encoding="utf-8")
    return True


def draw(cells: dict, settings: dict, say) -> int:
    import yoda
    failed = 0
    for cell, pages in cells.items():
        first = pages[0]
        work = first.config.parent / "yoda"
        work.mkdir(parents=True, exist_ok=True)
        outdir = first.output.parent
        # one file per point (its variants are curves mkhtml draws from it); labels by point
        sources = list(dict.fromkeys(s for page in pages for s in page.sources))
        label_of = {s: c["label"].split(" [")[0] for page in pages for s, c in zip(page.sources, page.document["curve"])}
        labels = [label_of[s] for s in sources]
        curves = [_voided(yoda, source, pages, work / f"{i:02d}_{source.parent.name}.yoda")
                  for i, source in enumerate(sources)]
        argv = ["rivet-mkhtml", "--no-rivet-refs", "-o", str(outdir), "-c", str(work / "pages.plot")]
        formats = settings.get("formats", ["pdf"])
        argv += [x for f in (["pdf"] if formats == "default" else formats) if FORMATS[f] for x in ("-f", FORMATS[f])]
        argv += [] if any(p.document["page"]["ratio"] for p in pages) else ["--no-ratio"]
        argv += [f"{path}:Title={latex(label)}" for path, label in zip(curves, labels)]

        references = [_reference(yoda, page) for page in pages if page.data and page.ranges.get("data_bins", 0) > 0]
        if references:
            yoda.write(references, str(work / "reference.yoda"))
            argv += [str(work / "reference.yoda"), "--reflabel", latex(settings.get("data", {}).get("legend", "Data"))]
        voided, cache = dict(zip(sources, curves)), {}

        def objects(path):
            if path not in cache:
                cache[path] = yoda.read(str(path))
            return cache[path]

        windows = {}
        for page in [p for p in pages if p.document["page"]["ratio"]]:
            drawn_curves = [_bins(objects(voided[s])[v]) for s, v in zip(page.sources, page.variants)]
            if not drawn_curves:
                continue
            with_data = page.data and page.ranges.get("data_bins", 0) > 0
            reference = _bins(_reference(yoda, page)) if with_data else drawn_curves[0]
            windows[page.name] = ratio_window(drawn_curves + ([reference] if with_data else []), reference,
                                              page.ranges["x"], page.style["ratio"])
        (work / "pages.plot").write_text("\n".join(_plot_block(p, windows.get(p.name)) for p in pages), encoding="utf-8")

        env = dict(os.environ, RIVET_ANALYSIS_PATH=str(build_root() / "Rivet"),
                   RIVET_DATA_PATH=os.pathsep.join(filter(None, [str(build_root() / "Rivet"), os.environ.get("RIVET_DATA_PATH")])))
        done = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=work)
        (work / "mkhtml.log").write_text(" ".join(argv) + "\n" + done.stdout + done.stderr, encoding="utf-8")
        drawn = [p for p in pages if (outdir / _base(p.object).split("/")[1] / f"{p.object.rsplit('/', 1)[-1]}.pdf").exists()]
        for page in list(drawn):
            script = outdir / _base(page.object).split("/")[1] / f"{page.object.rsplit('/', 1)[-1]}.py"
            if not script.is_file():
                continue
            ticks = page.document["page"]["ratio"] and ratio_ticks(script, int(page.style["ratio"]["divisions"]))
            best = page.style["legend"]["position"] == "best" and best_legend(script)
            if ticks or best:
                again = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=script.parent)
                if again.returncode != 0:
                    drawn.remove(page)
                    say(f"plot: {script.name} rewritten (ratio ticks, best legend): {again.stderr.strip()[-200:]}")
        if done.returncode != 0 or len(drawn) != len(pages):
            failed += len(pages) - len(drawn)
            say(f"plot: rivet-mkhtml for {cell or 'the page'}: {len(drawn)} of {len(pages)} drawn "
                f"(exit {done.returncode}; see {work / 'mkhtml.log'})")
    total = sum(len(p) for p in cells.values())
    say(f"plot (yoda): {total - failed} of {total} page(s) drawn in {len(cells)} page set(s)")
    return failed
