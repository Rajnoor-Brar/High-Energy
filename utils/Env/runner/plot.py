"""The plot stage: one page per `plot_points` cell and object, drawn by Paint (rank 4).

docs/rework_v2/04_Config.md §9, 05_Tools.md §7. After the points, from the complete ones:

* the objects are the 1D objects of the points' YODA product (not /RAW, /TMP or the run counters),
  narrowed by [plot].objects globs;
* the sweep is merged into one ROOT file, results/…/plots/root/<configuration>.root: a directory
  per point, raw entries included (so Paint can void by min_entries) and points.json inside. It is
  rebuilt only when a point's YODA changes, and it is what the pages read;
* titles and axis labels come from the analysis's Rivet .plot file (one label source, v1's D9), its
  LaTeX translated to TLatex (V11), under [plot.object."<glob>"] overrides;
* reference data are drawn only through the explicit [plot.data].map (L18);
* one Paint config per page, output/…/plots/[<page>/]<object>.toml, drawn to
  results/…/plots/root/[<page>/]<object>.<fmt>; the yoda backend writes results/…/plots/yoda/;
* the style is utils/Apps/Paint/base.toml, which Paint reads itself; a page's [style] holds only
  what the run changes: the [plot].root_style file, then [plot.style], then the matching
  [plot.object."<glob>"].style, each checked against base.toml's keys and types.
"""

from __future__ import annotations

import fnmatch
import functools
import hashlib
import importlib.util
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from .errors import HepError, did_you_mean
from .paths import build_root, output_root, repo_root, resolve, results_root
from .record import is_complete
from .sweep import axes, label_of, tag_of

BACKENDS = ("root", "yoda")
FORMATS = ("pdf", "png", "svg", "eps")
LEGENDS = ("top-right", "top-left", "bottom-right", "bottom-left")
DATA_KEYS = ("file", "legend", "map")
OBJECT_KEYS = ("title", "x_label", "y_label", "logx", "logy", "y_gutter", "x_gutter", "ratio", "style")
STYLE_CHOICES = {"page.font": ("serif", "sans", "mono"), "curves.errors": ("bars", "band", "none"),
                 "legend.position": LEGENDS}
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
    style: dict = field(default_factory=dict)       # base.toml with the page's [style] over it


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
    for fmt in settings.get("formats", []):
        one_of(fmt, FORMATS, "formats")
    only(settings.get("data", {}), DATA_KEYS, "data")
    run_style(run)
    for glob, table in settings.get("object", {}).items():
        only(table, OBJECT_KEYS, f'object."{glob}"')
        check_style(table.get("style", {}), f'{where}.object."{glob}".style')
    if settings.get("backend", "root") != "root":
        backend(settings["backend"]).validate(settings)
    data = settings.get("data", {})
    if data and not data.get("map"):
        raise HepError("[plot.data] names a file but no map", where=f"{where}.data",
                       hint='reference data are matched only through an explicit map (L18): "d01-x01-y01" = "/REF/…/d01-x01-y01"')
    if data and "file" not in data:
        raise HepError("[plot.data] has a map but no file", where=f"{where}.data")


# ── the style: utils/Apps/Paint/base.toml and the layers over it ─────────────────────────────

def base_style() -> dict:
    """utils/Apps/Paint/base.toml: every style key, with its default. Paint reads the same file."""
    path = repo_root() / "utils" / "Apps" / "Paint" / "base.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise HepError(f"cannot read the base style: {error}", where=str(path)) from None


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_style(layer: dict, where: str, base: dict | None = None, at: str = "") -> None:
    """A style layer names only keys base.toml has, each a value of the same kind: a number for a
    number, a pair for a pair, a list for the palette. legend.position is a corner or [x, y]."""
    base = base_style() if base is None else base
    for key, value in layer.items():
        name = f"{at}.{key}" if at else key
        if key not in base:
            raise HepError(f"the style has no key '{name}'", where=where,
                           hint=did_you_mean(key, list(base)) or f"utils/Apps/Paint/base.toml has: {', '.join(base)}")
        mine = base[key]
        if isinstance(mine, dict) or isinstance(value, dict):
            if not (isinstance(mine, dict) and isinstance(value, dict)):
                raise HepError(f"style '{name}' must be {'a table' if isinstance(mine, dict) else 'a value'}", where=where)
            check_style(value, where, mine, name)
            continue
        if name == "legend.position" and isinstance(value, list):
            ok = len(value) == 2 and all(_number(v) for v in value)
        elif _number(mine):
            ok = _number(value)
        elif isinstance(mine, list):
            ok = isinstance(value, list) and bool(value) and (
                len(value) == len(mine) and all(_number(v) for v in value) if all(_number(v) for v in mine)
                else all(isinstance(v, (str, int)) and not isinstance(v, bool) for v in value))
        else:
            ok = type(value) is type(mine)
        if not ok:
            raise HepError(f"style '{name}' = {value!r} is not of the kind base.toml gives it ({mine!r})", where=where)
        if name in STYLE_CHOICES and isinstance(value, str) and value not in STYLE_CHOICES[name]:
            raise HepError(f"style '{name}' must be one of {', '.join(STYLE_CHOICES[name])}, not '{value}'", where=where)


def merge_style(*layers: dict) -> dict:
    """Later layers win, key by key, into nested tables."""
    out: dict = {}
    for layer in layers:
        for key, value in layer.items():
            out[key] = merge_style(out.get(key, {}), value) if isinstance(value, dict) else value
    return out


def style_file(value: str, project: str = "", where: str = "") -> dict:
    """A style layer from a file: [plot].root_style (configs/<Project>/…), or `hep plot --style`."""
    path = resolve(value, "root_style", project=project, where=where) if project else Path(value).resolve()
    if path.suffix != ".toml":
        path = path.with_name(path.name + ".toml")
    try:
        layer = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise HepError(f"no style file {path}", where=where or str(path)) from None
    except tomllib.TOMLDecodeError as error:
        raise HepError(f"cannot parse the style file: {error}", where=str(path)) from None
    check_style(layer, str(path))
    return layer


def run_style(run) -> dict:
    """What a run changes of the base style: its root_style file, then [plot.style]."""
    settings = run.plot
    where = f"{run.path}: [plot]"
    layer = style_file(settings["root_style"], run.project, f"{where}.root_style") if "root_style" in settings else {}
    check_style(settings.get("style", {}), f"{where}.style")
    return merge_style(layer, settings.get("style", {}))


# ── LaTeX ($…$ in Rivet .plot files) → ROOT TLatex (V11) ──────────────────────────────────────

_COMMANDS = {"text": "", "mathrm": "", "rm": "", "mathit": "", "textrm": "", "mathbf": "#bf",
             "left": "", "right": "", "le": "#leq", "ge": "#geq", "to": "#rightarrow", "ell": "l"}


def _italic(math: str) -> str:
    """Letters in math are italic, as LaTeX sets them: E_T → #it{E}_#it{T}; commands and upright groups are not."""
    upright = r"\\(?:mathrm|text|textrm|operatorname|mbox|mathbf)\s*\{[^{}]*\}"
    return re.sub(upright + r"|\\[A-Za-z]+|([A-Za-z]+)", lambda m: f"#it{{{m[1]}}}" if m[1] else m[0], math)


def tlatex(text: str) -> str:
    """`$\\mathrm{d}\\sigma/\\mathrm{d}E_T$ [pb/GeV]` → `d#sigma/d#it{E}_{#it{T}} [pb/GeV]`."""
    out = "".join(_italic(part) if i % 2 else part for i, part in enumerate(text.split("$")))
    out = re.sub(r"\\[,;:! ]", " ", out)
    upright = r"\\(?:mathrm|text|textrm|mathit|operatorname|mbox)\s*\{([^{}]*)\}"
    out = re.sub(r"(?<=[_^])" + upright, r"{\1}", out)                 # E_T^\text{jet} keeps its group
    out = re.sub(upright, r"\1", out)
    out = re.sub(r"\\mathbf\s*\{([^{}]*)\}", r"#bf{\1}", out)
    out = re.sub(r"\\([A-Za-z]+)", lambda m: _COMMANDS.get(m.group(1), "#" + m.group(1)), out)
    out = re.sub(r"([_^])(#[A-Za-z]+(?:\{[^{}]*\})?|[A-Za-z0-9+*-])", r"\1{\2}", out)   # p_\perp → p_{#perp}, \pi^- → #pi^{-}
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


def merge(sources: dict[str, Path], target: Path, stamp: Path, points: Path | None = None) -> Path:
    """App_yd2rt --merge: every point's YODA into one ROOT file, a directory per point. Rebuilt only
    when a point's YODA changed (the stamp holds each name and sha256)."""
    digest = "\n".join(f"{name} {_sha(path)}" for name, path in sources.items())
    if target.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == digest:
        return target
    app = build_root() / "App_yd2rt.exe"
    if not app.exists():
        raise HepError("build/App_yd2rt.exe is not built", hint="hep build")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.stem + ".partial" + target.suffix)
    argv = [str(app), "--merge", str(partial), *(f"{name}={path}" for name, path in sources.items()), "--keep-raw"]
    if points is not None and points.is_file():
        argv += ["--points", str(points)]
    done = subprocess.run(argv, capture_output=True, text=True)
    if done.returncode != 0:
        raise HepError(f"merging the sweep failed: {done.stderr.strip()[-300:]}", where=str(target))
    partial.replace(target)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(digest, encoding="utf-8")
    return target


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

    out_dir = complete[0].out.parent / "plots"
    res_dir = complete[0].res.parent / "plots" / ("yoda" if settings.get("backend", "root") == "yoda" else "root")
    merged = merge({p.point.name: yoda_of(p) for p in complete},
                   complete[0].res.parent / "plots" / "root" / f"{configuration.name}.root", out_dir / "merged.sha256",
                   complete[0].out.parent / "points.json")

    data = settings.get("data", {})
    data_file = source = None
    if data:
        source = data_source(data["file"], run)
        data_file = convert(source, output_root() / run.project / ".cache" / "datasets" / f"{source.stem}.root")

    by_page: dict[str, list] = {}
    for plan in complete:
        key = "_".join(tag_of(run.quantities[g[0]], plan.point.choice[g[0]]) for g in page_groups)
        by_page.setdefault(key, []).append(plan)

    style, base = run_style(run), base_style()
    made = []
    for key, members in by_page.items():
        for path in objects:
            short = path.rsplit("/", 1)[-1]
            rel = f"{key}/{short}" if key else short
            reference = data.get("map", {}).get(short) if data else None
            page, override = page_settings(settings, path, rel, res_dir / rel, reference is not None)
            curves = [(plan, full) for plan in members for full in variants.get(plan.point.name, {}).get(path, [])]
            several = {plan.point.name for plan, _ in curves if len(variants[plan.point.name][path]) > 1}
            layer = merge_style(style, override.get("style", {}))
            document = {"page": page, "style": layer, "curve": [
                {"file": str(merged), "object": f"{plan.point.name}/{root_name(full)}",
                 **({"raw": f"{plan.point.name}/RAW/{root_name(full)}"} if "/RAW" + full in raws[plan.point.name] else {}),
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
                             data=(source, reference) if reference else None, overrides=set(override),
                             style=merge_style(base, layer)))
    return made


def page_settings(settings: dict, path: str, rel: str, output: Path, with_data: bool) -> tuple[dict, dict]:
    """A page's [page] table: labels from the analysis's .plot (TLatex), [plot.object] overrides,
    and the [plot] values. Returns it and the overrides that applied."""
    short = path.rsplit("/", 1)[-1]
    labels = labels_of(path)
    override: dict = {}
    for glob, table in settings.get("object", {}).items():
        if fnmatch.fnmatch(short, glob) or fnmatch.fnmatch(path, glob):
            override.update(table)

    def pick(name, default):
        return override.get(name, settings.get(name, default))

    page = {
        "name": rel, "output": str(output), "formats": settings.get("formats", ["pdf"]),
        "title": override.get("title", tlatex(labels.get("Title") or labels.get("LegendTitle", ""))),
        "x_label": override.get("x_label", tlatex(labels.get("XLabel", ""))),
        "y_label": override.get("y_label", tlatex(labels.get("YLabel", ""))),
        "logx": bool(pick("logx", labels.get("LogX") == "1")),
        "logy": bool(pick("logy", labels.get("LogY") == "1")),
        "y_gutter": float(pick("y_gutter", 1.5)), "x_gutter": float(pick("x_gutter", 1.0)),
        "ratio": bool(pick("ratio", False)),
        "ratio_label": "MC/Data" if with_data else "Ratio",
        "void_empty": bool(settings.get("void_empty", False)),
        "min_entries": int(settings.get("min_entries", 0)),
        "auto_range": bool(settings.get("auto_range", True)),
        "range_pad": int(settings.get("range_pad", 0)),
    }
    return page, override


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


# ── hep plot FILE…: pages from any YODA or ROOT files, no run TOML ────────────────────────────

def _is_plot_file(path: str) -> bool:
    return path.endswith((".yoda", ".yoda.gz", ".root"))


def _root_curves(path: Path, label: str | None) -> list[tuple[str, Path, dict[str, tuple[str, str | None]]]]:
    """The curves a ROOT file holds: one per point of a merged sweep (its paths tree has a point
    column), else one. Each: (label, file, {yoda path: (object, raw object or None)})."""
    import json

    import uproot
    with uproot.open(path) as file:
        keys = {k.split(";")[0] for k in file.keys()}
        if "paths" not in keys:                         # not App_yd2rt's: every 1D object, by its path
            found = {"/" + k: (k, None) for k in keys
                     if not k.startswith("RAW/") and "/RAW/" not in k and not k.endswith("__entries")
                     and file[k].classname.startswith(("TH1", "TGraph"))}
            return [(label or path.stem, path, found)]
        table = file["paths"].arrays(library="np")
        names = {}
        if "points.json" in keys:                        # a sweep: the legend is the swept values
            try:
                for entry in json.loads(file["points.json"].member("fTitle"))["points"]:
                    swept = [v["label"] for v in entry["values"].values() if v.get("swept")]
                    names[entry["name"]] = ", ".join(swept) or entry["name"]
            except (ValueError, KeyError, TypeError):
                pass
    points = table["point"] if "point" in table else [""] * len(table["root_path"])
    curves: dict[str, dict] = {}
    for point, rpath, ypath in zip(points, table["root_path"], table["yoda_path"]):
        ypath, rpath = str(ypath), str(rpath)
        if ypath.startswith(("/RAW/", "/TMP/")) or ypath in COUNTERS or ypath.endswith("]"):
            continue
        raw_path = f"{point}/RAW/{rpath[len(point) + 1:]}" if point else f"RAW/{rpath}"
        raw = raw_path if raw_path in keys and f"{raw_path}__entries" in keys else None
        curves.setdefault(str(point), {})[ypath] = (rpath, raw)
    if len(curves) == 1 and "" in curves:
        return [(label or path.stem, path, curves[""])]
    return [(names.get(p, p), path, objects) for p, objects in curves.items()]


def files(targets: list[str], outdir: Path | None, *, labels: list[str] | None = None, objects: list[str] = (),
          formats: list[str] = ("pdf", "png"), ratio: bool = False, style: str | None = None, say=print) -> int:
    """Overlay YODA and ROOT files through Paint: one page per object any of them holds, one curve
    per file (per point, for a merged sweep). YODA files are merged into one ROOT file first.
    `style` is a style file over base.toml, as [plot].root_style is for a run."""
    paths = [Path(t).resolve() for t in targets]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise HepError(f"no such file: {', '.join(missing)}")
    if labels and len(labels) != len(paths):
        raise HepError(f"--labels gives {len(labels)} names for {len(paths)} files")
    paint = build_root() / "Paint.exe"
    if not paint.exists():
        raise HepError("build/Paint.exe is not built", hint="hep build")
    key = hashlib.sha256("\n".join(map(str, paths)).encode()).hexdigest()[:12]
    work = output_root() / "plots" / key
    outdir = (outdir or (results_root() / "plots" / paths[0].name.split(".")[0])).resolve()

    yodas = [(i, p) for i, p in enumerate(paths) if p.name.endswith((".yoda", ".yoda.gz"))]
    curves: list[tuple[str, Path, dict]] = [None] * len(paths)       # in the order given
    if yodas:
        tags = {i: f"f{i}" for i, _ in yodas}
        merged = merge({tags[i]: p for i, p in yodas}, work / "files.root", work / "files.sha256")
        for i, p in yodas:
            raws = raws_of(p) if not p.name.endswith(".gz") else set()
            found = {o: (f"{tags[i]}/{root_name(o)}",
                         f"{tags[i]}/RAW/{root_name(o)}" if "/RAW" + o in raws else None)
                     for o in (objects_of(p) if not p.name.endswith(".gz") else _gz_objects(p))}
            curves[i] = [(labels[i] if labels else p.name.split(".")[0], merged, found)]
    for i, p in enumerate(paths):
        if curves[i] is None:
            curves[i] = _root_curves(p, labels[i] if labels else None)
    curves = [c for group in curves for c in group]

    pages_of = list(dict.fromkeys(o for _, _, found in curves for o in found))
    if objects:
        pages_of = [o for o in pages_of if any(fnmatch.fnmatch(o, g) for g in objects)]
    if not pages_of:
        raise HepError("no 1D object to draw" + (f" matches {list(objects)}" if objects else ""))
    settings = {"formats": list(formats), "ratio": ratio, "auto_range": True}
    layer = style_file(style) if style else {}
    failed = 0
    for path in pages_of:
        rel = path.strip("/").replace(":", "__")
        page, _ = page_settings(settings, path, rel, outdir / rel, False)
        document = {"page": page, "style": layer, "curve": [
            {"file": str(file), "object": found[path][0], **({"raw": found[path][1]} if found[path][1] else {}),
             "label": label} for label, file, found in curves if path in found]}
        config = work / f"{rel}.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(tomli_w.dumps(document), encoding="utf-8")
        done = subprocess.run([str(paint), str(config)], capture_output=True, text=True)
        if done.returncode != 0:
            failed += 1
            say(f"plot: {rel} failed: {_why(done)}")
    say(f"plot: {len(pages_of) - failed} of {len(pages_of)} page(s), {len(curves)} curve(s) → {outdir}")
    return failed


def _gz_objects(path: Path) -> list[str]:
    import gzip
    text = gzip.open(path, "rt", encoding="utf-8", errors="replace").read()
    found = re.findall(r"^BEGIN YODA_(?:ESTIMATE1D|HISTO1D|SCATTER2D)_V\d+ (\S+)$", text, re.M)
    return [p for p in found if not p.startswith(("/RAW/", "/TMP/")) and p not in COUNTERS and not p.endswith("]")]
