"""The plot stage: one page per `plot_points` cell and object, drawn by Paint (rank 4).

docs/04_Config_Reference.md §11, docs/05_Tools_Reference.md §17. After the points, from the complete ones:

* the objects are the 1D objects of the points' YODA product (not /RAW, /TMP or the run counters),
  narrowed by [plot].objects globs;
* the sweep is merged into one ROOT file, results/…/plots/root/<configuration>.root: a directory
  per point, raw entries included (so Paint can void by min_entries) and points.json inside. It is
  rebuilt only when a point's YODA changes, and it is what the pages read;
* titles and axis labels come from the analysis's Rivet .plot file (one label source, v1's D9), its
  LaTeX translated to TLatex (V11), under [plot.object."<glob>"] overrides;
* reference data are drawn only through the explicit [plot.data].map (L18);
* one Paint config per page, output/…/plots/[<page>/]<object>.toml, drawn to
  results/…/plots/root/[<page>/]<object>.<fmt>; the yoda backend writes results/…/plots/yoda/, and
  backend = ["root", "yoda"] (or "both") writes both from the same pages;
* the style is utils/Apps/Paint/base.toml, which Paint reads itself; a page's [style] holds only
  what the run changes: the [plot].root_style file, then [plot.style], then the matching
  [plot.object."<glob>"].style, each checked against base.toml's keys and types.
"""

from __future__ import annotations

import fnmatch
import hashlib
import importlib.util
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

import tomli_w

from . import schema
from .errors import HepError, did_you_mean
from .labels import labels_of, lines_of, macros, root_text, tlatex  # noqa: F401 (tlatex et al. re-exported)
from .paths import build_root, output_root, repo_root, resolve, results_root
from .record import is_complete
from .tools import sha256_file
from .sweep import axes, label_of, tag_of

BACKENDS = tuple(b for b in schema.keys("plot")["backend"]["choices"] if b != "both")
FORMATS = tuple(schema.keys("plot")["formats"]["choices"])
LEGENDS = ("top-right", "top-left", "bottom-right", "bottom-left", "best")
#: Above the frame: the main title and the corners; the legend's first line (V51). [plot] sets them for
#: every page, [plot.object."<glob>"] and [plot.overlay.<name>] for theirs: a child inherits its parent's
#: value and may override it, and a key means the same at both levels.
TITLE_KEYS = ("title", "title_left", "title_right", "legend_header")
DEFAULT = schema.DEFAULT  # "keep it as it is" (V55): a child's is its parent's; [plot]'s sets nothing


def formats_of(settings: dict) -> list[str]:
    """[plot].formats; "default" is Paint's own, pdf (mkhtml writes pdf and png whatever it is given)."""
    value = settings.get("formats", schema.default("plot", "formats"))
    return ["pdf"] if value == DEFAULT else list(value)
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
    plots: Path | None = None                        # results/…/plots: a backend draws into plots/<its name>/
    overlay: str = ""                                # [plot.overlay.<name>]: curves are several objects (V51)


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


def backends(settings: dict) -> list[str]:
    """[plot].backend: a name, a list of names, or "both" (every backend). Paint's first when drawn."""
    value = settings.get("backend", "root")
    value = "root" if value == DEFAULT else value
    names = list(BACKENDS) if value == "both" else [value] if isinstance(value, str) else list(value)
    return sorted(dict.fromkeys(names), key=lambda n: n != "root")


def validate(run) -> None:
    """What [plot] needs beyond the schema (config.check_plot has every key, type and bound): the style
    layers against base.toml, the backends' own limits, and [plot.data]'s file and map together. Keys
    a backend cannot honour are errors at plan time, never dropped (v1's LegendXPos)."""
    settings = run.plot
    where = f"{run.path}: [plot]"
    names = backends(settings)
    if not names:
        raise HepError("[plot].backend names no backend", where=f"{where}.backend", hint='"root", "yoda" or "both"')
    run_style(run)
    for glob, table in settings.get("object", {}).items():
        check_style(table.get("style", {}), f'{where}.object."{glob}".style')
    for name, table in settings.get("overlay", {}).items():
        check_style(table.get("style", {}), f"{where}.overlay.{name}.style")
    for name in names[1:] if names[0] == "root" else names:
        backend(name).validate(settings, beside_root=names[0] == "root")
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
        if key in base and value == DEFAULT:        # set nothing: the layer below, at last base.toml, decides
            continue
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
    """Later layers win, key by key, into nested tables; a "default" value sets nothing."""
    out: dict = {}
    for layer in layers:
        for key, value in layer.items():
            if value == DEFAULT:
                continue
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
    named = settings.get("root_style", DEFAULT)
    layer = style_file(named, run.project, f"{where}.root_style") if named != DEFAULT else {}
    check_style(settings.get("style", {}), f"{where}.style")
    return merge_style(layer, settings.get("style", {}))


# ── the page document as Paint reads it ──────────────────────────────────────────────────────

def for_root(document: dict) -> dict:
    """The page document Paint reads: every label through root_text (the in-memory document keeps the
    labels as written, which the yoda backend converts its own way)."""
    out = {**document, "page": {k: root_text(v) if k in (*TITLE_KEYS, "x_label", "y_label") and isinstance(v, str) else v
                                for k, v in document["page"].items()},
           "curve": [{**c, "label": root_text(c["label"])} for c in document["curve"]]}
    if "data" in document:
        out["data"] = {**document["data"], "label": root_text(document["data"]["label"])}
    return out



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
    return sha256_file(path)


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
        if interface.kind == "product" and not interface.shard and interface.path.suffix == ".yoda":
            return interface.path
    return None


# ── pages ────────────────────────────────────────────────────────────────────────────────────

def pages(run, configuration, plans) -> list[Page]:
    """Write the Paint config of every page from the complete points; returns the pages."""
    settings = run.plot
    complete = [p for p in plans if is_complete(p) and yoda_of(p)]
    if not complete:
        return []
    groups = [g for g in axes(configuration) if not set(g) & set(configuration.combine)]   # merged away (V35)
    page_groups = [g for g in groups if set(g) & set(configuration.plot_points)]
    curve_groups = [g for g in groups if g not in page_groups]

    variants: dict[str, dict[str, list[str]]] = {}      # point → base path → its full paths
    raws = {plan.point.name: raws_of(yoda_of(plan)) for plan in complete}
    for plan in complete:
        for full in objects_of(yoda_of(plan)):
            variants.setdefault(plan.point.name, {}).setdefault(base_of(full), []).append(full)
    objects = list(dict.fromkeys(b for plan in complete for b in variants.get(plan.point.name, {})))
    every = list(objects)                                  # an overlay may name any object, drawn alone or not
    wanted = settings.get("objects", [])
    wanted = [] if wanted == DEFAULT else wanted
    if wanted:
        objects = [o for o in objects if any(fnmatch.fnmatch(o, g) or any(fnmatch.fnmatch(f, g)
                   for v in variants.values() for f in v.get(o, [])) for g in wanted)]
        if not objects:
            raise HepError(f"[plot].objects {wanted} match no object of the points' YODAs",
                           where=f"{run.path}: [plot].objects")

    out_dir = complete[0].out.parent / "plots"
    res_dir = complete[0].res.parent / "plots" / "root"          # Paint's; another backend's: for_backend
    merged = merge({p.point.name: yoda_of(p) for p in complete},
                   complete[0].res.parent / "plots" / "root" / f"{configuration.label}.root", out_dir / "merged.sha256",
                   complete[0].out.parent / "points.json")

    # use_data = false (V44): the [plot.data] table stays but is not drawn; a ratio then divides by
    # each page's first curve, the first value of its curve axis
    data = settings.get("data", {}) if settings.get("use_data", True) is not False else {}
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
            config.write_text(tomli_w.dumps(for_root(document)), encoding="utf-8")
            made.append(Page(rel, config, res_dir / rel, cell=key, object=path, document=document,
                             sources=[yoda_of(plan) for plan, _ in curves], variants=[full for _, full in curves],
                             data=(source, reference) if reference else None,
                             overrides={k for k, v in override.items() if v != DEFAULT},
                             style=merge_style(base, layer), plots=res_dir.parent))

    for name, table in settings.get("overlay", {}).items():     # V51: several objects of a point on one page
        paths = []
        for glob in table["objects"]:
            found = [o for o in every if fnmatch.fnmatch(o.rsplit("/", 1)[-1], glob) or fnmatch.fnmatch(o, glob)]
            if not found:
                raise HepError(f"overlay '{name}': '{glob}' matches no object of the points' YODAs",
                               where=f"{run.path}: [plot.overlay.{name}].objects")
            paths.append(found[0])
        labels = table.get("labels") or [p.rsplit("/", 1)[-1] for p in paths]
        for key, members in by_page.items():
            rel = f"{key}/{name}" if key else name
            page, override = page_settings(settings, paths[0], rel, res_dir / rel, False, child=table)
            curves = [(plan, variants[plan.point.name][path][0], label) for plan in members
                      for path, label in zip(paths, labels) if path in variants.get(plan.point.name, {})]
            layer = merge_style(style, override.get("style", {}))
            document = {"page": page, "style": layer, "curve": [
                {"file": str(merged), "object": f"{plan.point.name}/{root_name(full)}",
                 **({"raw": f"{plan.point.name}/RAW/{root_name(full)}"} if "/RAW" + full in raws[plan.point.name] else {}),
                 "label": label + (f", {_curve_label(run, plan, curve_groups)}" if len(members) > 1 else "")}
                for plan, full, label in curves]}
            config = out_dir / f"{rel}.toml"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(tomli_w.dumps(for_root(document)), encoding="utf-8")
            made.append(Page(rel, config, res_dir / rel, cell=key, object=f"/overlay/{name}", document=document,
                             sources=[yoda_of(plan) for plan, _, _ in curves], variants=[full for _, full, _ in curves],
                             overrides={k for k, v in override.items() if v != DEFAULT},
                             style=merge_style(base, layer), plots=res_dir.parent, overlay=name))
    return made


def page_settings(settings: dict, path: str, rel: str, output: Path, with_data: bool,
                  child: dict | None = None) -> tuple[dict, dict]:
    """A page's [page] table: labels from the analysis's .plot (TLatex), [plot.object] overrides (or
    an overlay's own table, `child`), and the [plot] values. Returns it and the overrides that applied."""
    short = path.rsplit("/", 1)[-1]
    labels = labels_of(path)
    override: dict = {}
    if child is not None:
        override = {k: v for k, v in child.items() if k not in ("objects", "labels")}
    else:
        for glob, table in settings.get("object", {}).items():
            if fnmatch.fnmatch(short, glob) or fnmatch.fnmatch(path, glob):
                override.update(table)

    def pick(name, ours, native, tables=(override, settings)):
        """V55: the most specific table that sets a value wins. "default" keeps it as it is: in a child
        (an object's or an overlay's table) it is the parent's value, as if the key were absent; in the
        last table (the top level) it is `native`, set nothing: what the drawing tool does by itself.
        Nothing set anywhere is `ours`, the runner's default (the schema's)."""
        for table in tables:
            if name in table and table[name] != DEFAULT:
                return table[name]
        return native if tables[-1].get(name) == DEFAULT else ours

    def plot_only(name, ours, native):
        return pick(name, ours, native, tables=(settings,))

    def ours(name):
        return schema.default("plot", name)

    title, header = tlatex(labels.get("Title", "")), tlatex(labels.get("LegendTitle", ""))     # as mkhtml (V51)
    x_label, y_label = tlatex(labels.get("XLabel", "")), tlatex(labels.get("YLabel", ""))
    log_x, log_y = labels.get("LogX") == "1", labels.get("LogY") == "1"
    ratio = labels["RatioPlot"] == "1" if labels.get("RatioPlot") in ("0", "1") else with_data   # mkhtml's rule
    page = {
        "name": rel, "output": str(output), "formats": formats_of(settings),
        "title": pick("title", title, title),
        "title_left": pick("title_left", "", ""),
        "title_right": pick("title_right", "", ""),
        "legend_header": pick("legend_header", header, header),
        "x_label": pick("x_label", x_label, x_label, tables=(override,)),
        "y_label": pick("y_label", y_label, y_label, tables=(override,)),
        "logx": bool(pick("logx", log_x, log_x)),
        "logy": bool(pick("logy", log_y, log_y)),
        "y_gutter": _gutter(pick("y_gutter", ours("y_gutter"), DEFAULT)),
        "x_gutter": _gutter(pick("x_gutter", DEFAULT, DEFAULT)),
        "ratio": bool(pick("ratio", ours("ratio"), ratio)),
        "ratio_label": "MC/Data" if with_data else "Ratio",
        "void_empty": bool(plot_only("void_empty", ours("void_empty"), False)),     # neither tool voids by itself
        "min_entries": int(plot_only("min_entries", ours("min_entries"), 0)),
        "auto_range": bool(plot_only("auto_range", ours("auto_range"), False)),    # the tool's own range
        "range_pad": int(plot_only("range_pad", ours("range_pad"), 0)),
    }
    return page, override


def _gutter(value):
    return value if value == "default" else float(value)


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


def for_backend(page: Page, name: str) -> Page:
    """The page as another backend draws it: into results/…/plots/<name>/ instead of Paint's root/."""
    return replace(page, output=page.plots / name / page.name) if page.plots else page


def draw(run, configuration, plans, say) -> int:
    """The plot stage: Paint on every page, then any other backend on the same pages. Returns the
    number of pages that failed, summed over the backends."""
    if not run.plot:
        return 0
    paint = build_root() / "Paint.exe"
    if not paint.exists():
        raise HepError("build/Paint.exe is not built", hint="hep build")
    todo = pages(run, configuration, plans)
    if not todo:
        say("plot: no complete point has a YODA product to draw")
        return 0
    names = backends(run.plot)
    failed = 0
    if "root" in names:
        for page in todo:
            done = subprocess.run([str(paint), str(page.config)], capture_output=True, text=True)
            if done.returncode != 0:
                failed += 1
                say(f"plot: {page.name} failed: {_why(done)}")
        where = todo[0].config.parent if "/" not in todo[0].name else todo[0].config.parent.parent
        say(f"plot: {len(todo) - failed} of {len(todo)} page(s) drawn; configs in {where}")
    others = [n for n in names if n != "root"]
    if others:                           # the same pages; Paint computes the ranges and voids for them
        for page in todo:
            done = subprocess.run([str(paint), str(page.config), "--dump-ranges"], capture_output=True, text=True)
            if done.returncode != 0:
                raise HepError(f"plot: {page.name}: {_why(done)}", where=str(page.config))
            page.ranges = json.loads(done.stdout)
    for name in others:
        cells: dict[str, list[Page]] = {}
        for page in todo:
            cells.setdefault(page.cell, []).append(for_backend(page, name))
        failed += backend(name).draw(cells, run.plot, say)
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
        config.write_text(tomli_w.dumps(for_root(document)), encoding="utf-8")
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
