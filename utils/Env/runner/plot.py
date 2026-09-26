"""The plot stage: one page per `plot_points` cell and object, drawn by Paint (rank 4).

docs/rework_v2/04_Config.md §9, 05_Tools.md §7. After the points, from the complete ones:

* the objects are the 1D objects of the points' YODA product (not /RAW, /TMP or the run counters),
  narrowed by [plot].objects globs;
* each point's YODA is converted once, raw entries included, into output/…/plots/inputs/, keyed by
  its sha256, so Paint can void by min_entries;
* titles and axis labels come from the analysis's Rivet .plot file (one label source, v1's D9), its
  LaTeX translated to TLatex (V11), under [plot.object."<glob>"] overrides;
* reference data are drawn only through the explicit [plot.data].map (L18);
* one Paint config per page, output/…/plots/[<page>/]<object>.toml, drawn to the same place under
  results/.
"""

from __future__ import annotations

import fnmatch
import functools
import hashlib
import importlib.util
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from .errors import HepError, did_you_mean
from .paths import build_root, output_root, repo_root, resolve
from .record import is_complete
from .sweep import axes, label_of, tag_of

BACKENDS = ("root", "yoda")
FORMATS = ("pdf", "png", "svg", "eps")
LEGENDS = ("top-right", "top-left", "bottom-right", "bottom-left")
DATA_KEYS = ("file", "legend", "map")
STYLE_KEYS = ("canvas", "font_size", "palette")
OBJECT_KEYS = ("title", "x_label", "y_label", "logx", "logy", "y_gutter", "x_gutter", "ratio", "legend")
COUNTERS = ("/_XSEC", "/_EVTCOUNT")


@dataclass
class Page:
    name: str            # "<cell>/<object>", or "<object>" with no plot_points
    config: Path         # the Paint config
    output: Path         # without extension
    cell: str = ""       # the plot_points tags, "" with no plot_points
    object: str = ""     # the YODA path without analysis options: what the page is of
    document: dict = field(default_factory=dict)    # the Paint config, as written
    sources: list = field(default_factory=list)     # each curve's YODA …
    variants: list = field(default_factory=list)    # … and its object there (options included)
    data: tuple | None = None                       # (reference YODA, its object path)
    overrides: set = field(default_factory=set)     # [plot.object] keys that applied
    ranges: dict = field(default_factory=dict)      # Paint --dump-ranges, for other backends


def backend(name: str):
    """A backend other than Paint: utils/Env/<name>/backend.py, with validate(settings) and
    draw(cells, settings, say) -> failed pages."""
    path = repo_root() / "utils" / "Env" / name / "backend.py"
    if not path.is_file():
        raise HepError(f"no plot backend '{name}'", hint=f"expected {path}")
    spec = importlib.util.spec_from_file_location(f"hep_backend_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(run) -> None:
    """Keys a backend cannot honour are errors at plan time, never dropped (v1's LegendXPos)."""
    settings = run.plot
    where = f"{run.path}: [plot]"

    def one_of(value, allowed, key):
        if value not in allowed:
            raise HepError(f"{key} must be one of {', '.join(allowed)}, not '{value}'", where=f"{where}.{key}")

    def only(table, allowed, name):
        for key in table:
            if key not in allowed:
                raise HepError(f"[plot.{name}] has no key '{key}'", where=f"{where}.{name}",
                               hint=did_you_mean(key, allowed) or f"its keys: {', '.join(allowed)}")

    one_of(settings.get("backend", "root"), BACKENDS, "backend")
    one_of(settings.get("legend", "top-right"), LEGENDS, "legend")
    for fmt in settings.get("formats", []):
        one_of(fmt, FORMATS, "formats")
    only(settings.get("data", {}), DATA_KEYS, "data")
    only(settings.get("style", {}), STYLE_KEYS, "style")
    for glob, table in settings.get("object", {}).items():
        only(table, OBJECT_KEYS, f'object."{glob}"')
        if "legend" in table:
            one_of(table["legend"], LEGENDS, f'object."{glob}".legend')
    if settings.get("backend", "root") != "root":
        backend(settings["backend"]).validate(settings)
    data = settings.get("data", {})
    if data and not data.get("map"):
        raise HepError("[plot.data] names a file but no map", where=f"{where}.data",
                       hint='reference data are matched only through an explicit map (L18): "d01-x01-y01" = "/REF/…/d01-x01-y01"')
    if data and "file" not in data:
        raise HepError("[plot.data] has a map but no file", where=f"{where}.data")


# ── LaTeX ($…$ in Rivet .plot files) → ROOT TLatex (V11) ──────────────────────────────────────

_COMMANDS = {"text": "", "mathrm": "", "rm": "", "mathit": "", "textrm": "", "mathbf": "#bf",
             "left": "", "right": "", "le": "#leq", "ge": "#geq", "to": "#rightarrow", "ell": "l"}


def tlatex(text: str) -> str:
    """`$\\mathrm{d}\\sigma/\\mathrm{d}E_T$ [pb/GeV]` → `d#sigma/dE_{T} [pb/GeV]`."""
    out = text.replace("$", "")
    out = re.sub(r"\\[,;:! ]", " ", out)
    upright = r"\\(?:mathrm|text|textrm|mathit|operatorname|mbox)\s*\{([^{}]*)\}"
    out = re.sub(r"(?<=[_^])" + upright, r"{\1}", out)                 # E_T^\text{jet} keeps its group
    out = re.sub(upright, r"\1", out)
    out = re.sub(r"\\mathbf\s*\{([^{}]*)\}", r"#bf{\1}", out)
    out = re.sub(r"\\([A-Za-z]+)", lambda m: _COMMANDS.get(m.group(1), "#" + m.group(1)), out)
    out = re.sub(r"([_^])(#[A-Za-z]+|[A-Za-z0-9+*-])", r"\1{\2}", out)   # p_\perp → p_{#perp}, \pi^- → #pi^{-}
    out = re.sub(r"\{\s+", "{", out)
    return re.sub(r"\s+", " ", out).strip()


@functools.cache
def _plot_blocks(analysis: str) -> tuple:
    """The `# BEGIN PLOT` blocks of an analysis's .plot file: build/Rivet first, then Rivet's own."""
    places = [build_root() / "Rivet"]
    try:
        found = subprocess.run(["rivet-config", "--datadir"], capture_output=True, text=True, timeout=30)
        places += [Path(p) for p in found.stdout.strip().split(":") if p]
    except (OSError, subprocess.SubprocessError):
        pass
    for place in places:
        path = place / f"{analysis}.plot"
        if not path.is_file():
            continue
        blocks = []
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, body in re.findall(r"^# BEGIN PLOT (\S+)\n(.*?)^# END PLOT", text, re.S | re.M):
            keys = dict(line.split("=", 1) for line in body.splitlines() if "=" in line and not line.startswith("#"))
            try:
                blocks.append((re.compile(pattern), {k.strip(): v.strip() for k, v in keys.items()}))
            except re.error:
                continue
        return tuple(blocks)
    return ()


def labels_of(path: str) -> dict:
    """The .plot keys that apply to a YODA path, later blocks winning, as in Rivet."""
    analysis, short = path.strip("/").split("/", 1)[0].split(":")[0], path.rsplit("/", 1)[-1]
    keys: dict = {}
    for pattern, block in _plot_blocks(analysis):
        if pattern.match(f"/{analysis}/{short}"):
            keys.update(block)
    return keys


# ── inputs ───────────────────────────────────────────────────────────────────────────────────

def root_name(path: str) -> str:
    """The object's name in App_yd2rt's file: /photo_eic:R=0.4/d01-x01-y01 → photo_eic__R-0.4/d01-x01-y01."""
    return path.lstrip("/").replace(":", "__").replace("=", "-").replace(" ", "_")


def base_of(path: str) -> str:
    """/photo_eic:R=0.4/d01-x01-y01 → /photo_eic/d01-x01-y01: a page is of the object, and each
    variant (a swept analysis option) is a curve on it, as in v1."""
    analysis, _, rest = path.strip("/").partition("/")
    return f"/{analysis.split(':')[0]}/{rest}"


def objects_of(yoda: Path) -> list[str]:
    """The 1D objects of a YODA file that get pages: the nominal weight only (Sherpa writes a
    variation per extra weight, as /x[EXTRA__MEWeight])."""
    text = yoda.read_text(encoding="utf-8", errors="replace")
    found = re.findall(r"^BEGIN YODA_(?:ESTIMATE1D|HISTO1D|SCATTER2D)_V\d+ (\S+)$", text, re.M)
    return [p for p in found if not p.startswith(("/RAW/", "/TMP/")) and p not in COUNTERS
            and not p.endswith("]")]            # /x[EXTRA__NTrials]: a weight variation, not a page


def raws_of(yoda: Path) -> set[str]:
    """The /RAW Histo1D twins a YODA file has, whose entries App_yd2rt keeps. A ratio made in
    finalize has none (or an Estimate1D one), and gets no min_entries."""
    text = yoda.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"^BEGIN YODA_HISTO1D_V\d+ (/RAW/\S+)$", text, re.M))    # entries: Histo1D only


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert(yoda: Path, target: Path) -> Path:
    """App_yd2rt --keep-raw, once per content: the stamp beside the target holds the YODA's sha256."""
    stamp = target.with_name(target.name + ".sha256")
    digest = _sha(yoda)
    if target.exists() and stamp.exists() and stamp.read_text().strip() == digest:
        return target
    app = build_root() / "App_yd2rt.exe"
    if not app.exists():
        raise HepError("build/App_yd2rt.exe is not built", hint="hep build")
    target.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([str(app), str(yoda), str(target), "--keep-raw"], capture_output=True, text=True)
    if done.returncode != 0:
        raise HepError(f"converting {yoda.name} failed: {done.stderr.strip()[-300:]}", where=str(yoda))
    stamp.write_text(digest + "\n")
    return target


def data_source(name: str, run) -> Path:
    """[plot.data].file: `rivet:<Analysis>` is Rivet's own reference file (its data directory, or
    build/Rivet for ours), which every installation has; anything else is under datasets/."""
    if name.startswith("rivet:"):
        analysis = name.split(":", 1)[1]
        places = [build_root() / "Rivet"]
        try:
            found = subprocess.run(["rivet-config", "--datadir"], capture_output=True, text=True, timeout=30)
            places += [Path(p) for p in found.stdout.strip().split(":") if p]
        except (OSError, subprocess.SubprocessError):
            pass
        for place in places:
            for candidate in (place / f"{analysis}.yoda", place / f"{analysis}.yoda.gz"):
                if candidate.is_file():
                    return candidate
        raise HepError(f"Rivet has no reference data for {analysis}", where=f"{run.path}: [plot.data].file",
                       hint=f"looked for {analysis}.yoda[.gz] in {', '.join(map(str, places))}")
    source = resolve(name, "data", project=run.project, where=f"{run.path}: [plot.data].file")
    if not source.is_file():
        raise HepError("the reference data file does not exist", where=str(source),
                       hint="datasets/ is not in git; `rivet:<Analysis>` names Rivet's own reference data")
    return source


def yoda_of(plan) -> Path | None:
    for interface in plan.interfaces.values():
        if interface.kind == "product" and interface.path.suffix == ".yoda":
            return interface.path
    return None


# ── pages ────────────────────────────────────────────────────────────────────────────────────

def pages(run, configuration, plans) -> list[Page]:
    """Write the Paint config of every page from the complete points; returns the pages."""
    settings = run.plot
    complete = [p for p in plans if is_complete(p) and yoda_of(p)]
    if not complete:
        return []
    groups = axes(configuration)
    page_groups = [g for g in groups if set(g) & set(configuration.plot_points)]
    curve_groups = [g for g in groups if g not in page_groups]

    variants: dict[str, dict[str, list[str]]] = {}      # point → base path → its full paths
    raws = {plan.point.name: raws_of(yoda_of(plan)) for plan in complete}
    for plan in complete:
        for full in objects_of(yoda_of(plan)):
            variants.setdefault(plan.point.name, {}).setdefault(base_of(full), []).append(full)
    objects = list(dict.fromkeys(b for plan in complete for b in variants.get(plan.point.name, {})))
    wanted = settings.get("objects", [])
    if wanted:
        objects = [o for o in objects if any(fnmatch.fnmatch(o, g) or any(fnmatch.fnmatch(f, g)
                   for v in variants.values() for f in v.get(o, [])) for g in wanted)]
        if not objects:
            raise HepError(f"[plot].objects {wanted} match no object of the points' YODAs",
                           where=f"{run.path}: [plot].objects")

    out_dir, res_dir = complete[0].out.parent / "plots", complete[0].res.parent / "plots"
    inputs = {p.point.name: convert(yoda_of(p), out_dir / "inputs" / f"{p.point.name}.root") for p in complete}

    data = settings.get("data", {})
    data_file = source = None
    if data:
        source = data_source(data["file"], run)
        data_file = convert(source, output_root() / run.project / ".cache" / "datasets" / f"{source.stem}.root")

    by_page: dict[str, list] = {}
    for plan in complete:
        key = "_".join(tag_of(run.quantities[g[0]], plan.point.choice[g[0]]) for g in page_groups)
        by_page.setdefault(key, []).append(plan)

    style = settings.get("style", {})
    made = []
    for key, members in by_page.items():
        for path in objects:
            short = path.rsplit("/", 1)[-1]
            rel = f"{key}/{short}" if key else short
            labels = labels_of(path)
            override: dict = {}
            for glob, table in settings.get("object", {}).items():
                if fnmatch.fnmatch(short, glob) or fnmatch.fnmatch(path, glob):
                    override.update(table)

            def pick(name, default):
                return override.get(name, settings.get(name, default))

            reference = data.get("map", {}).get(short) if data else None
            page = {
                "name": rel, "output": str(res_dir / rel), "formats": settings.get("formats", ["pdf"]),
                "title": override.get("title", tlatex(labels.get("Title") or labels.get("LegendTitle", ""))),
                "x_label": override.get("x_label", tlatex(labels.get("XLabel", ""))),
                "y_label": override.get("y_label", tlatex(labels.get("YLabel", ""))),
                "logx": bool(pick("logx", labels.get("LogX") == "1")),
                "logy": bool(pick("logy", labels.get("LogY") == "1")),
                "y_gutter": float(pick("y_gutter", 1.5)), "x_gutter": float(pick("x_gutter", 1.0)),
                "ratio": bool(pick("ratio", False)), "legend": pick("legend", "top-right"),
                "ratio_label": "MC/Data" if reference else "Ratio",
                "void_empty": bool(settings.get("void_empty", False)),
                "min_entries": int(settings.get("min_entries", 0)),
                "auto_range": bool(settings.get("auto_range", True)),
                "range_pad": int(settings.get("range_pad", 0)),
            }
            curves = [(plan, full) for plan in members for full in variants.get(plan.point.name, {}).get(path, [])]
            several = {plan.point.name for plan, _ in curves if len(variants[plan.point.name][path]) > 1}
            document = {"page": page, "style": dict(style), "curve": [
                {"file": str(inputs[plan.point.name]), "object": root_name(full),
                 **({"raw": "RAW/" + root_name(full)} if "/RAW" + full in raws[plan.point.name] else {}),
                 "label": _curve_label(run, plan, curve_groups)
                          + (f" [{full.strip('/').split('/')[0].partition(':')[2]}]" if plan.point.name in several else "")}
                for plan, full in curves]}
            if reference:
                document["data"] = {"file": str(data_file), "object": root_name(reference),
                                    "label": data.get("legend", "Data")}
            config = out_dir / f"{rel}.toml"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(tomli_w.dumps(document), encoding="utf-8")
            made.append(Page(rel, config, res_dir / rel, cell=key, object=path, document=document,
                             sources=[yoda_of(plan) for plan, _ in curves], variants=[full for _, full in curves],
                             data=(source, reference) if reference else None, overrides=set(override)))
    return made


def _curve_label(run, plan, curve_groups) -> str:
    if not curve_groups:
        return run.name
    return ", ".join(label_of(run.quantities[g[0]], plan.point.choice[g[0]]) for g in curve_groups)


def _why(done: subprocess.CompletedProcess) -> str:
    if done.returncode < 0 or done.returncode > 128:
        return f"Paint crashed (signal {abs(done.returncode) % 128})"
    for line in reversed((done.stderr + done.stdout).splitlines()):
        if line.strip() and not set(line.strip()) <= set("=-#"):
            return line.strip()[-200:]
    return f"exit {done.returncode}"


def draw(run, configuration, plans, say) -> int:
    """The plot stage: Paint on every page. Returns the number of pages that failed."""
    if not run.plot:
        return 0
    paint = build_root() / "Paint.exe"
    if not paint.exists():
        raise HepError("build/Paint.exe is not built", hint="hep build")
    todo = pages(run, configuration, plans)
    if not todo:
        say("plot: no complete point has a YODA product to draw")
        return 0
    name = run.plot.get("backend", "root")
    if name != "root":                   # the same pages; Paint computes the ranges and voids for it
        cells: dict[str, list[Page]] = {}
        for page in todo:
            done = subprocess.run([str(paint), str(page.config), "--dump-ranges"], capture_output=True, text=True)
            if done.returncode != 0:
                raise HepError(f"plot: {page.name}: {_why(done)}", where=str(page.config))
            page.ranges = json.loads(done.stdout)
            cells.setdefault(page.cell, []).append(page)
        return backend(name).draw(cells, run.plot, say)
    failed = 0
    for page in todo:
        done = subprocess.run([str(paint), str(page.config)], capture_output=True, text=True)
        if done.returncode != 0:
            failed += 1
            say(f"plot: {page.name} failed: {_why(done)}")
    where = todo[0].config.parent if "/" not in todo[0].name else todo[0].config.parent.parent
    say(f"plot: {len(todo) - failed} of {len(todo)} page(s) drawn; configs in {where}")
    return failed
