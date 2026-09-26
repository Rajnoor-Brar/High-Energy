"""utils/Env/yoda/backend.py — `[plot] backend = "yoda"`: the same pages drawn by rivet-mkhtml.

docs/rework_v2/04_Config.md §9, V10/V11. The runner hands over the pages it wrote for Paint, with
Paint's --dump-ranges of each: the x and y ranges (auto_range, gutters) and the voided bins. Per
plot_points cell this writes

* the curves' YODAs with the voided bins blanked (value NaN, no errors), as v1 did;
* reference.yoda: the mapped reference objects, renamed /REF/<analysis>/<object> so that mkhtml
  pairs them with the MC (its own reference lookup is off: explicit only, L18);
* pages.plot: per object the ranges, log axes, legend corner, and the [plot.object] label
  overrides in LaTeX; the rest of the labels mkhtml reads from the analysis's own .plot;

and runs rivet-mkhtml into results/…/plots/<cell>/. mkhtml always writes PDF and PNG; svg and eps
are added. [plot.style] font_size and palette have no mkhtml counterpart and are refused.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from runner.errors import HepError
from runner.paths import build_root

FORMATS = {"pdf": None, "png": None, "svg": "SVG", "eps": "EPS"}       # None: mkhtml writes it anyway
LEGEND = {"top-right": {"LegendAlign": "r"}, "top-left": {"LegendAlign": "l", "LegendXPos": "0.05"},
          "bottom-right": {"LegendAlign": "r", "LegendYPos": "0.4"},
          "bottom-left": {"LegendAlign": "l", "LegendXPos": "0.05", "LegendYPos": "0.4"}}
_MATH = {"bf": "mathbf", "it": "mathit", "LT": "<", "GT": ">"}


def validate(settings: dict) -> None:
    style = settings.get("style", {})
    for key in ("font_size", "palette"):
        if key in style:
            raise HepError(f'[plot.style].{key} cannot be honoured by backend = "yoda"', where="[plot.style]",
                           hint="rivet-mkhtml has its own fonts and colours; drop the key, or use backend = \"root\"")


def latex(text: str) -> str:
    """TLatex → LaTeX for the common subset, word by word: '#sqrt{s} = 28.6 GeV' → '$\\sqrt{s}$ = 28.6 GeV'."""
    def word(w: str) -> str:
        if not re.search(r"[#_^]", w):
            return w
        w = re.sub(r"#([A-Za-z]+)", lambda m: _MATH.get(m.group(1), "\\" + m.group(1)), w)
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
        if not voided:
            continue
        estimate = objects[page.object]
        if "Estimate" not in estimate.type():
            raise HepError(f"cannot void bins of {page.object}, a {estimate.type()}", where=str(source))
        for index in voided:
            estimate.bin(index).setVal(float("nan"))
            estimate.bin(index).rmErrs()
        changed = True
    if not changed:
        return source
    yoda.write(list(objects.values()), str(target))
    return target


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


def _plot_block(page) -> str:
    settings = page.document["page"]
    (xlo, xhi), (ylo, yhi) = page.ranges["x"], page.ranges["y"]
    keys = {"XMin": f"{xlo:.10g}", "XMax": f"{xhi:.10g}", "YMin": f"{ylo:.10g}", "YMax": f"{yhi:.10g}",
            "LogX": str(int(settings["logx"])), "LogY": str(int(settings["logy"])),
            "RatioPlot": str(int(settings["ratio"])), **LEGEND[settings["legend"]]}
    for key, native in (("title", "Title"), ("x_label", "XLabel"), ("y_label", "YLabel")):
        if key in page.overrides:
            keys[native] = latex(settings[key])
    if settings["logy"] and not ylo > 0:
        del keys["YMin"]
    body = "".join(f"{k}={v}\n" for k, v in keys.items() if not (isinstance(v, str) and v in ("nan", "inf")))
    return f"# BEGIN PLOT {_base(page.object)}\n{body}# END PLOT\n"


def draw(cells: dict, settings: dict, say) -> int:
    import yoda
    failed = 0
    for cell, pages in cells.items():
        first = pages[0]
        work = first.config.parent / "yoda"
        work.mkdir(parents=True, exist_ok=True)
        outdir = first.output.parent
        labels = [c["label"] for c in first.document["curve"]]
        curves = [_voided(yoda, source, pages, work / f"{i:02d}_{source.parent.name}.yoda")
                  for i, source in enumerate(first.sources)]
        argv = ["rivet-mkhtml", "--no-rivet-refs", "-o", str(outdir), "-c", str(work / "pages.plot")]
        argv += [x for f in settings.get("formats", ["pdf"]) if FORMATS[f] for x in ("-f", FORMATS[f])]
        argv += [] if settings.get("ratio", False) else ["--no-ratio"]
        argv += [f"{path}:Title={latex(label)}" for path, label in zip(curves, labels)]

        references = [_reference(yoda, page) for page in pages if page.data and page.ranges.get("data_bins", 0) > 0]
        if references:
            yoda.write(references, str(work / "reference.yoda"))
            argv += [str(work / "reference.yoda"), "--reflabel", latex(settings.get("data", {}).get("legend", "Data"))]
        (work / "pages.plot").write_text("\n".join(_plot_block(p) for p in pages), encoding="utf-8")

        env = dict(os.environ, RIVET_ANALYSIS_PATH=str(build_root() / "Rivet"),
                   RIVET_DATA_PATH=os.pathsep.join(filter(None, [str(build_root() / "Rivet"), os.environ.get("RIVET_DATA_PATH")])))
        done = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=work)
        (work / "mkhtml.log").write_text(" ".join(argv) + "\n" + done.stdout + done.stderr, encoding="utf-8")
        drawn = [p for p in pages if (outdir / _base(p.object).split("/")[1] / f"{p.object.rsplit('/', 1)[-1]}.pdf").exists()]
        if done.returncode != 0 or len(drawn) != len(pages):
            failed += len(pages) - len(drawn)
            say(f"plot: rivet-mkhtml for {cell or 'the page'}: {len(drawn)} of {len(pages)} drawn "
                f"(exit {done.returncode}; see {work / 'mkhtml.log'})")
    total = sum(len(p) for p in cells.values())
    say(f"plot (yoda): {total - failed} of {total} page(s) drawn in {len(cells)} page set(s)")
    return failed
