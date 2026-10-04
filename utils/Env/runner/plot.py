"""The plot stage: one page per `plot_points` cell and object, drawn by Paint (rank 4).

docs/04_Config_Reference.md §11, docs/05_Tools_Reference.md §17. After the points, from the complete ones:

* the objects are the 1D objects of the points' YODA product (not /RAW, /TMP or the run counters),
  narrowed by [plot].objects globs;
* the sweep is merged into one ROOT file, results/…/plots/root/<configuration>.root: a directory
  per point, raw entries included (so Paint can void by min_entries) and points.json inside. It is
  rebuilt only when a point's YODA changes, and it is what the pages read;
* titles and axis labels come from the analysis's Rivet .plot file (one label source, v1's D9), under
  a figure's own ([plot.figures.<figure>], V80); every text is LaTeX (V65), and may cite the points (V66):
  {cell}, {q:<quantity>} (a value's label), and what the tools' folders give ({opt:ETMIN}: Rivet's);
* reference data are drawn only through the explicit [plot.data].map (L18);
* one Paint config per page, output/…/plots/[<page>/]<object>.toml, drawn to
  results/…/plots/root/[<page>/]<object>.<fmt>; the yoda backend writes results/…/plots/yoda/, and
  backend = ["root", "yoda"] (or "both") writes both from the same pages;
* the style is utils/Apps/Paint/base.toml, which Paint reads itself; a page's [style] holds only
  what the run changes: the [plot].root_style file, then [plot.style], then its figure's style, each
  checked against base.toml's keys and types.
"""

from __future__ import annotations

import fnmatch
import hashlib
import html
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

import tomli_w

from . import hepfiles, plugins, schema
from .errors import HepError, did_you_mean
from .labels import canonical, labels_of, lines_of, macros, root_text, tlatex  # noqa: F401 (tlatex et al. re-exported)
from .paths import build_root, output_root, repo_root, resolve, results_root
from .record import is_complete
from .tools import merge_files, sha256_file
from .sweep import axes, label_of, tag_of

BACKENDS = tuple(b for b in schema.keys("plot")["backend"]["choices"] if b != "both")
FORMATS = tuple(schema.keys("plot")["formats"]["choices"])
LEGENDS = ("top-right", "top-left", "bottom-right", "bottom-left", "best")
#: Above the frame: the main title and the corners; the legend's first line (V51). [plot] sets them for
#: every page, a figure ([plot.figures.<figure>]) for its own: it inherits [plot]'s value and may
#: override it, and a key means the same at both levels.
TITLE_KEYS = ("title", "title_left", "title_right", "legend_header")
DEFAULT = schema.DEFAULT  # "keep it as it is" (V55): a child's is its parent's; [plot]'s sets nothing
PLACEHOLDER = re.compile(r"\{(cell|[a-z]+:[A-Za-z0-9_.:+-]+)\}")    # V66; a LaTeX group never has the colon


def formats_of(settings: dict) -> list[str]:
    """[plot].formats; "default" is Paint's own, pdf (mkhtml writes pdf and png whatever it is given)."""
    value = settings.get("formats", schema.default("plot", "formats"))
    return ["pdf"] if value == DEFAULT else list(value)
STYLE_CHOICES = {"page.font": ("serif", "sans", "mono"), "curves.errors": ("bars", "band", "none"),
                 "legend.position": LEGENDS}
COUNTERS = hepfiles.COUNTERS
#: Pages per Paint process (V64): ROOT starts once per batch, and argv stays short.
PAINT_BATCH = 200


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
    overrides: set = field(default_factory=set)     # the keys its figure set
    ranges: dict = field(default_factory=dict)      # Paint --dump-ranges, for other backends
    style: dict = field(default_factory=dict)       # base.toml with the page's [style] over it
    plots: Path | None = None                        # results/…/plots: a backend draws into plots/<its name>/
    overlay: str = ""                                # an overlay figure's name: curves are several objects (V51)
    bands: list = field(default_factory=list)        # per curve: its band members' (YODA, object), V69


@dataclass(frozen=True)
class Figure:
    """A recipe for pages (V80): [plot.figures.<key>]."""
    key: str
    kind: str                # its class: defined, overlay, merged, compare, derived, scan
    type: str                # what is drawn; "" from the objects
    name: str                # its pages' file stem (an overlay's; a defined figure's pages are the objects')
    objects: tuple           # globs
    labels: tuple            # an overlay's, one per object
    table: dict              # what it sets for its pages: [plot]'s page keys, x_label, y_label, style
    where: str
    over: tuple = ()         # a merged figure's: the axes it merges (V82)
    configurations: tuple = ()   # a compare figure's (V83); () under sweep_runs: its configurations
    op: str = ""             # a derived figure's (V84)
    x: str = ""              # a scan figure's quantity … (V85)
    y: str = ""              # … and the number it reads of each point


def figures(run) -> list[Figure]:
    """The declared figures, in file order. The implicit one, [plot].objects as defined pages, is pages()'."""
    from .config import figure_tables
    out = []
    for key, (table, written) in figure_tables(run.plot or {}).items():
        out.append(Figure(key, table.get("class", "defined"), table.get("type", ""), table.get("name", key),
                          tuple(table.get("objects", ())), tuple(table.get("labels", ())),
                          {k: v for k, v in table.items() if k not in schema.FIGURE_OWN}, f"{run.path}: {written}",
                          tuple(table.get("over", ())), tuple(table.get("configurations", ())), table.get("op", ""),
                          table.get("x", ""), table.get("y", "")))
    return out


def _matches(path: str, glob: str, fulls=()) -> bool:
    """An object glob against the short name (d01-x01-y01), the option-free path, or any variant's path."""
    return (fnmatch.fnmatch(path.rsplit("/", 1)[-1], glob) or fnmatch.fnmatch(path, glob)
            or any(fnmatch.fnmatch(f, glob) for f in fulls))


def backend(name: str):
    """A backend other than Paint: utils/Env/<name>/backend.py, with validate(settings) and
    draw(cells, settings, say) -> failed pages."""
    path = repo_root() / "utils" / "Env" / name / "backend.py"
    if not path.is_file():
        raise HepError(f"no plot backend '{name}'", hint=f"expected {path}")
    return plugins.load(path, "backend")


def backends(settings: dict) -> list[str]:
    """[plot].backend: a name, a list of names, or "both" (every backend). Paint's first when drawn."""
    value = settings.get("backend", "root")
    value = "root" if value == DEFAULT else value
    names = ["root", "yoda"] if value == "both" else [value] if isinstance(value, str) else list(value)   # "both": V28's pair
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
    for figure in figures(run):
        check_style(figure.table.get("style", {}), f"{figure.where}.style")
    for name in names[1:] if names[0] == "root" else names:
        backend(name).validate(settings, beside_root=names[0] == "root",
                               curve_styles=[s for q in run.quantities.values() for s in q.styles])
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
    out = {**document, "page": {k: tlatex(v) if k in (*TITLE_KEYS, "x_label", "y_label") and isinstance(v, str) else v
                                for k, v in document["page"].items()},
           "curve": [{**c, "label": tlatex(c["label"])} for c in document["curve"]]}
    if "data" in document:
        out["data"] = {**document["data"], "label": tlatex(document["data"]["label"])}
    return out



# ── inputs ───────────────────────────────────────────────────────────────────────────────────

def root_name(path: str) -> str:
    """The object's name in App_yd2rt's file: /photo_eic:R=0.4/d01-x01-y01 → photo_eic__R-0.4/d01-x01-y01."""
    return path.lstrip("/").replace(":", "__").replace("=", "-").replace(" ", "_")


base_of = hepfiles.base_path


def objects_of(yoda: Path) -> list[str]:
    """The 1D objects of a YODA file that get pages (hepfiles.objects: .gz too)."""
    return hepfiles.objects(yoda)


def raws_of(yoda: Path) -> set[str]:
    """The /RAW Histo1D twins a YODA file has, whose entries App_yd2rt keeps (hepfiles.raw_twins)."""
    return hepfiles.raw_twins(yoda)


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
        places = hepfiles.rivet_dirs()
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
    complete = [p for p in plans if is_complete(p) and yoda_of(p)]
    if not complete:
        return []
    check_figures(run, configuration)
    declared = figures(run)
    out_dir = complete[0].out.parent / "plots"
    res_dir = complete[0].res.parent / "plots" / "root"          # Paint's; another backend's: for_backend
    page_groups, curve_groups = axes_of(configuration)
    sources = point_yodas(run, complete)
    root = merge(sources, res_dir / f"{configuration.label}.root", out_dir / "merged.sha256",
                 complete[0].out.parent / "points.json")
    drawn = [f for f in declared if f.kind in ("defined", "overlay")] + derived_figures(declared)
    made = _pages(run, complete, sources, root, drawn, page_groups, curve_groups, out_dir, res_dir, implicit=True,
                  labels_from=_labels_from(declared, sources))
    for figure in (f for f in declared if f.kind == "merged"):        # V82: points merged over an axis, for it alone
        members, yodas = _merged(run, figure, complete, sources, page_groups + curve_groups, out_dir / "merged" / figure.name)
        kept = [g for g in curve_groups if not set(g) & set(figure.over)]
        root = merge(yodas, res_dir / figure.name / f"{configuration.label}.root", out_dir / "merged" / f"{figure.name}.sha256")
        made += _pages(run, members, yodas, root, [replace(figure, kind="defined")], page_groups, kept,
                       out_dir, res_dir, implicit=False, folder=figure.name)
    for figure in (f for f in declared if f.kind == "scan"):          # V85: a number per point against a quantity
        members, yodas = _scanned(run, figure, complete, sources, page_groups + curve_groups, out_dir / "scan" / figure.name)
        kept = [g for g in curve_groups if figure.x not in g]
        root = merge(yodas, res_dir / "scan" / f"{figure.name}.root", out_dir / "scan" / f"{figure.name}.sha256")
        table = {"x_label": figure.x, "y_label": SCAN_LABELS.get(figure.y, figure.y.replace(":", " ")), **figure.table}
        made += _pages(run, members, yodas, root, [replace(figure, kind="defined", objects=(f"/FIGURES/{figure.name}",),
                                                           table=table, type=figure.type or "Scatter2D")],
                       page_groups, kept, out_dir, res_dir, implicit=False)
    return made


#: A scan figure's y axis title when it sets none (V85).
SCAN_LABELS = {"sigma": r"$\sigma$ [pb]", "entries": "entries", "integral": "integral", "mean": "mean"}


def _scanned(run, figure: Figure, complete: list, sources: dict, groups: list, where: Path) -> tuple[list, dict]:
    """A scan figure's members (V85): per value of the axes other than x, a stand-in plan named by their
    tags, its YODA one Scatter2D /FIGURES/<name>: a point per value of x, at that value, its y the number
    the figure reads of the point (utils/Env/figures/derive.py), its x range reaching halfway to its
    nearer neighbour on both sides, so it is centred on its value and every backend can draw it as a
    bin (a scan is drawn as markers, V86). Remade only when a member's YODA or the figure changed."""
    module = plugins.load(repo_root() / "utils" / "Env" / "figures" / "derive.py", "derive")
    quantity = run.quantities[figure.x]
    kept = [g for g in groups if figure.x not in g]
    by: dict[tuple, list] = {}
    for plan in complete:
        by.setdefault(tuple(plan.point.choice[g[0]] for g in kept), []).append(plan)
    where.mkdir(parents=True, exist_ok=True)
    glob = figure.objects[0] if figure.objects else ""
    members, yodas = [], {}
    for key, plans in by.items():
        name = "_".join(tag_of(run.quantities[g[0]], i) for g, i in zip(kept, key)) or "scan"
        plans = sorted(plans, key=lambda p: float(quantity.values[p.values[figure.x]]))
        target, stamp = where / f"{name}.yoda", where / f"{name}.sha256"
        xs = [float(quantity.values[p.values[figure.x]]) for p in plans]
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        halves = [min([g for g in (gaps[i - 1] if i else None, gaps[i] if i < len(gaps) else None) if g] or [1.0]) / 2
                  for i in range(len(xs))]
        digest = ("\n".join(f"{p.point.name} {_sha(sources[p.point.name])}" for p in plans)
                  + f"\n{figure.y} {glob} {xs} {halves}")
        if not (target.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == digest):
            points = []
            for plan, x, half in zip(plans, xs, halves):
                lo, hi = x - half, x + half
                try:
                    value, error = module.scan_value(str(sources[plan.point.name]), figure.y, glob)
                except ValueError as error:
                    raise HepError(f"figure '{figure.key}' at {plan.point.name}: {error}", where=figure.where) from None
                points.append((x, x - lo, hi - x, value, error))
            target.write_text(module.scatter(f"/FIGURES/{figure.name}", points), encoding="utf-8")
            stamp.write_text(digest, encoding="utf-8")
        first = plans[0]
        members.append(replace(first, point=replace(first.point, name=name),
                               values={q: i for q, i in first.values.items() if q != figure.x}))
        yodas[name] = target
    return members, yodas


#: A compare figure's curve axis (V83): the configuration, in its members' choice; not a quantity name.
CONFIGURATION = "@configuration"


def compare_pages(run, figure: Figure, sets: list[tuple]) -> list[Page]:
    """A compare figure's pages (V83): its objects' pages, one per page cell of the configurations, whose
    curves are every configuration's points (or combined groups), labelled by the configuration first.
    `sets`: (configuration, its complete plans) in the figure's order. Into
    output/…/<run>/compare/<name>/ and results/…/<run>/compare/<name>/<backend>/."""
    members, yodas = [], {}
    for number, (c, plans) in enumerate(sets):
        label = figure.labels[number] if figure.labels else c.configuration.label if c.own \
            else f"{c.run.name} {c.configuration.label}"
        sources = point_yodas(c.run, plans)
        for plan in plans:
            name = f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', c.ref)}_{plan.point.name}"
            members.append(replace(plan, point=replace(plan.point, name=name, choice={**plan.point.choice, CONFIGURATION: number}),
                                   context={**plan.context, "curve_label": label, **({} if c.own else {"run": c.run})}))
            yodas[name] = sources[plan.point.name]
    first = next(plans[0] for c, plans in sets if c.own)                 # this run's folder (V88)
    out_dir = first.out.parent.parent / "compare" / figure.name
    res_dir = first.res.parent.parent / "compare" / figure.name / "root"
    page_groups, curve_groups = axes_of(sets[0][0].configuration)
    root = merge(yodas, res_dir / f"{figure.name}.root", out_dir / "merged.sha256")
    return _pages(run, members, yodas, root, [replace(figure, kind="defined")], page_groups,
                  [[CONFIGURATION]] + curve_groups, out_dir, res_dir, implicit=False)


def derived_figures(declared: list) -> list[Figure]:
    """A derived figure draws its object as a defined figure does (V84): /FIGURES/<name>, its pages."""
    return [replace(f, kind="defined", objects=(f"/FIGURES/{f.name}",)) for f in declared if f.kind == "derived"]


def _labels_from(declared: list, sources: dict) -> dict[str, str]:
    """A derived object's labels are its first object's (.plot): /FIGURES/<name> → that object's path."""
    out = {}
    every = list(dict.fromkeys(base_of(o) for path in sources.values() for o in objects_of(path)))
    for figure in (f for f in declared if f.kind == "derived"):
        first = next((o for o in every if not o.startswith("/FIGURES") and _matches(o, figure.objects[0])), None)
        if first:
            out[f"/FIGURES/{figure.name}"] = first
    return out


def point_yodas(run, complete: list) -> dict[str, Path]:
    """Each complete point's YODA, as the pages read it: its product, or with a derived figure (V84) a
    copy with the derived objects after its own (output/…/plots/derived/<point>.yoda), made by
    utils/Env/figures/derive.py and remade only when the product or the figures changed."""
    plain = {p.point.name: yoda_of(p) for p in complete}
    derived = [f for f in figures(run) if f.kind == "derived"]
    if not derived:
        return plain
    module = plugins.load(repo_root() / "utils" / "Env" / "figures" / "derive.py", "derive")
    where = complete[0].out.parent / "plots" / "derived"
    where.mkdir(parents=True, exist_ok=True)
    specs = [(f.name, f.op, list(f.objects)) for f in derived]
    out = {}
    for name, source in plain.items():
        target, stamp = where / f"{name}.yoda", where / f"{name}.sha256"
        digest = f"{_sha(source)} {json.dumps(specs)}"
        if not (target.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == digest):
            text = [hepfiles.yoda_text(source).rstrip("\n") + "\n\n"]
            for figure, spec in zip(derived, specs):
                try:
                    text.append(module.derive(str(source), [spec]))
                except ValueError as error:
                    raise HepError(f"figure '{figure.key}' at {name}: {error}", where=figure.where) from None
            target.write_text("".join(text), encoding="utf-8")
            stamp.write_text(digest, encoding="utf-8")
        out[name] = target
    return out


def _merged(run, figure: Figure, complete: list, sources: dict, groups: list, where: Path) -> tuple[list, dict]:
    """A merged figure's members: per value of the axes it does not merge, one stand-in plan named by
    their tags, its YODA the members' merged by the combine folder's command; rebuilt only when a
    member's YODA changed (a stamp of their sha256, as merge's)."""
    kept = [g for g in groups if not set(g) & set(figure.over)]
    by: dict[tuple, list] = {}
    for plan in complete:
        by.setdefault(tuple(plan.point.choice[g[0]] for g in kept), []).append(plan)
    members, yodas = [], {}
    for key, plans in by.items():
        name = "_".join(tag_of(run.quantities[g[0]], i) for g, i in zip(kept, key)) or "merged"
        target = where / f"{name}.yoda"
        stamp = where / f"{name}.sha256"
        digest = "\n".join(f"{p.point.name} {_sha(sources[p.point.name])}" for p in plans)
        if not (target.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == digest):
            merge_files([sources[p.point.name] for p in plans], target)
            stamp.write_text(digest, encoding="utf-8")
        first = plans[0]
        members.append(replace(first, point=replace(first.point, name=name),
                               values={q: i for q, i in first.values.items() if q not in figure.over}))
        yodas[name] = target
    return members, yodas


def _pages(run, complete: list, yodas: dict, merged: Path, declared: list, page_groups: list, curve_groups: list,
           out_dir: Path, res_dir: Path, *, implicit: bool, folder: str = "", labels_from: dict | None = None) -> list[Page]:
    """The pages of these figures from these members (a point, or a merged figure's stand-in: its name
    is its directory in `merged`, the ROOT file of their YODAs `yodas`). `implicit`: [plot].objects's
    pages too. `folder`: the figure's own, between the cell and the object."""
    settings = run.plot
    variants: dict[str, dict[str, list[str]]] = {}      # member → base path → its full paths
    raws = {plan.point.name: raws_of(yodas[plan.point.name]) for plan in complete}
    two_d: set[str] = set()                                # V87: heat maps, a page per member
    for plan in complete:
        for full in objects_of(yodas[plan.point.name]):
            variants.setdefault(plan.point.name, {}).setdefault(base_of(full), []).append(full)
        for full in hepfiles.objects_2d(yodas[plan.point.name]):
            variants.setdefault(plan.point.name, {}).setdefault(base_of(full), []).append(full)
            two_d.add(base_of(full))
    objects = list(dict.fromkeys(b for plan in complete for b in variants.get(plan.point.name, {})))
    every = list(objects)                                  # a figure may name any object, drawn alone or not

    def fulls(o):
        return [f for v in variants.values() for f in v.get(o, [])]

    wanted = settings.get("objects", [])                   # the implicit figure: defined pages of these
    wanted = [] if wanted == DEFAULT else wanted
    if not implicit:
        objects = []
    elif wanted:
        objects = [o for o in objects if any(fnmatch.fnmatch(o, g) or any(fnmatch.fnmatch(f, g) for f in fulls(o))
                                             for g in wanted)]
        if not objects:
            raise HepError(f"[plot].objects {wanted} match no object of the points' YODAs",
                           where=f"{run.path}: [plot].objects")
    claimed: dict[str, Figure] = {}                        # a declared defined figure takes its objects' pages
    for figure in (f for f in declared if f.kind == "defined"):
        found = [o for o in every if any(_matches(o, g, fulls(o)) for g in figure.objects)]
        if not found:
            raise HepError(f"figure '{figure.key}': {list(figure.objects)} match no object of the points' YODAs",
                           where=f"{figure.where}.objects")
        for o in found:
            if o in claimed:
                raise HepError(f"figures '{claimed[o].key}' and '{figure.key}' both make the pages of {o}",
                               where=f"{figure.where}.objects",
                               hint="one recipe per page: narrow a glob; what every page shares goes in [plot]")
            claimed[o] = figure
    objects = [o for o in every if o in objects or o in claimed]

    # use_data = false (V44): the [plot.data] table stays but is not drawn; a ratio then divides by
    # each page's first curve, the first value of its curve axis. A figure may set it, and band, for its own
    data = settings.get("data", {})
    data_file = source = None

    def band_of(override) -> list:
        return list(chosen("band", [], [], (override, settings)) or [])

    by_page: dict[str, list] = {}
    for plan in complete:                                  # a member of another run reads its own quantities (V88)
        key = "_".join(tag_of(_run_of(run, plan).quantities[g[0]], plan.point.choice[g[0]]) for g in page_groups)
        by_page.setdefault(key, []).append(plan)

    style, base = run_style(run), base_style()
    known = {plan.point.name: texts_of(_run_of(run, plan), plan, ", ".join(
                 label_of(_run_of(run, plan).quantities[g[0]], plan.point.choice[g[0]]) for g in page_groups))
             for plan in complete}
    where = f"{run.path}: [plot]"

    def page_fill(plans):
        return filler(list({p.point.name: known[p.point.name] for p in plans}.values()), where)

    def curve_fill(plan):
        return filler([known[plan.point.name]], where)

    def place(key, stem):
        return "/".join(part for part in (key, folder, stem) if part)

    for figure in declared:                                # what a figure draws is what its objects are
        mine = [o for o in objects if claimed.get(o) is figure] if figure.kind == "defined" else []
        flat = [o for o in mine if o not in two_d]
        if figure.type == "HeatMap" and flat:
            raise HepError(f"figure '{figure.key}' is a HeatMap, and {flat[0]} is a 1D object", where=f"{figure.where}.type",
                           hint="a heat map draws a 2D object; leave type out to draw each as it is")
        if figure.type in ("Hist1D", "Scatter2D") and set(mine) & two_d:
            raise HepError(f"figure '{figure.key}' is a {figure.type}, and {sorted(set(mine) & two_d)[0]} is a 2D object",
                           where=f"{figure.where}.type", hint='a 2D object is drawn as a heat map: type = "HeatMap", or leave it out')

    made = []
    for key, members in by_page.items():
        for path in objects:
            short = path.rsplit("/", 1)[-1]
            rel = place(key, short)
            figure = claimed.get(path)
            override = override_of(figure.table if figure else None)
            if path in two_d:                                  # V87: a page per member and variant
                made += [_heatmap(run, plan, full, place(key, f"{short}/{plan.point.name}"), settings, override,
                                  merged, out_dir, res_dir, run_style(run), key, curve_fill(plan))
                         for plan in members for full in variants.get(plan.point.name, {}).get(path, [])]
                continue
            drawn = data if chosen("use_data", True, True, (override, settings)) is not False else {}
            reference = drawn.get("map", {}).get(short) if drawn else None
            if reference and data_file is None:                # converted once, when a page draws it
                source = data_source(data["file"], run)
                data_file = convert(source, output_root() / run.project / ".cache" / "datasets" / f"{source.stem}.root")
            band = band_of(override)
            line_groups = [g for g in curve_groups if not set(g) & set(band)]     # what tells a band curve from another
            curves = [(plan, full) for plan in members for full in variants.get(plan.point.name, {}).get(path, [])]
            fill = page_fill([plan for plan, _ in curves] or members)
            folded = _banded(curves, curve_groups, band, lambda p, f: variants[p.point.name][path].index(f))
            envelope = f" ({', '.join(band)} envelope)" if band else ""
            page, override = page_settings(settings, (labels_from or {}).get(path, path), rel, res_dir / rel,
                                           reference is not None, fill=fill, child=override)
            if figure is not None and figure.type == "Scatter2D":
                page["markers"] = True                                       # V86
            several = {plan.point.name for plan, _ in curves if len(variants[plan.point.name][path]) > 1}
            layer = merge_style(style, override.get("style", {}))
            document = {"page": page, "style": layer, "curve": [
                {"file": str(merged), "object": f"{plan.point.name}/{root_name(full)}",
                 **({"raw": f"{plan.point.name}/RAW/{root_name(full)}"} if "/RAW" + full in raws[plan.point.name] else {}),
                 "label": _curve_label(run, plan, line_groups, curve_fill(plan))
                          + (f" [{full.strip('/').split('/')[0].partition(':')[2]}]" if plan.point.name in several else "")
                          + (envelope if folded_members else ""),
                 **({"style": look} if (look := _curve_look(run, plan, line_groups)) else {}),
                 **({"band": [{"file": str(merged), "object": f"{m.point.name}/{root_name(f)}"} for m, f in folded_members]}
                    if folded_members else {})}
                for plan, full, folded_members in folded]}
            if reference:
                document["data"] = {"file": str(data_file), "object": root_name(reference),
                                    "label": canonical(fill(data.get("legend", "Data")))}
            config = out_dir / f"{rel}.toml"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(tomli_w.dumps(for_root(document)), encoding="utf-8")
            made.append(Page(rel, config, res_dir / rel, cell=key, object=path, document=document,
                             sources=[yodas[plan.point.name] for plan, _, _ in folded], variants=[full for _, full, _ in folded],
                             bands=[[(yodas[m.point.name], f) for m, f in ms] for _, _, ms in folded],
                             data=(source, reference) if reference else None,
                             overrides={k for k, v in override.items() if v != DEFAULT},
                             style=merge_style(base, layer), plots=res_dir.parent))

    for figure in (f for f in declared if f.kind == "overlay"):     # V51: several objects of a point on one page
        name, table = figure.name, figure.table
        paths = []
        for glob in figure.objects:
            found = [o for o in every if _matches(o, glob)]
            if not found:
                raise HepError(f"figure '{figure.key}': '{glob}' matches no object of the points' YODAs",
                               where=f"{figure.where}.objects")
            if found[0] in two_d:
                raise HepError(f"figure '{figure.key}': {found[0]} is a 2D object, which a heat map draws alone",
                               where=f"{figure.where}.objects", hint="an overlay draws 1D objects together")
            paths.append(found[0])
        labels = list(figure.labels) or [p.rsplit("/", 1)[-1] for p in paths]
        for key, members in by_page.items():
            rel = place(key, name)
            named = {}
            for plan in members:
                for path, label in zip(paths, labels):
                    if path in variants.get(plan.point.name, {}):
                        named[(plan.point.name, variants[plan.point.name][path][0])] = canonical(curve_fill(plan)(label))
            curves = [(plan, full) for plan in members for (point, full) in named if point == plan.point.name]
            band = band_of(table)
            line_groups = [g for g in curve_groups if not set(g) & set(band)]
            folded = _banded(curves, curve_groups, band, lambda p, f: f)          # V69, an overlay's own band
            envelope = f" ({', '.join(band)} envelope)" if band else ""
            page, override = page_settings(settings, paths[0], rel, res_dir / rel, False, child=table,
                                           fill=page_fill([plan for plan, _ in curves] or members))
            if figure.type == "Scatter2D":
                page["markers"] = True                                       # V86
            layer = merge_style(style, override.get("style", {}))
            lines = {plan.point.name for plan, _, _ in folded}
            document = {"page": page, "style": layer, "curve": [
                {"file": str(merged), "object": f"{plan.point.name}/{root_name(full)}",
                 **({"raw": f"{plan.point.name}/RAW/{root_name(full)}"} if "/RAW" + full in raws[plan.point.name] else {}),
                 "label": named[(plan.point.name, full)]
                          + (f", {_curve_label(run, plan, line_groups, curve_fill(plan))}" if len(lines) > 1 else "")
                          + (envelope if folded_members else ""),
                 **({"band": [{"file": str(merged), "object": f"{m.point.name}/{root_name(f)}"} for m, f in folded_members]}
                    if folded_members else {})}
                for plan, full, folded_members in folded]}
            config = out_dir / f"{rel}.toml"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(tomli_w.dumps(for_root(document)), encoding="utf-8")
            made.append(Page(rel, config, res_dir / rel, cell=key, object=f"/overlay/{name}", document=document,
                             sources=[yodas[plan.point.name] for plan, _, _ in folded], variants=[full for _, full, _ in folded],
                             bands=[[(yodas[m.point.name], f) for m, f in ms] for _, _, ms in folded],
                             overrides={k for k, v in override.items() if v != DEFAULT},
                             style=merge_style(base, layer), plots=res_dir.parent, overlay=name))
    return made


def _heatmap(run, plan, full: str, rel: str, settings: dict, override: dict, merged: Path, out_dir: Path,
             res_dir: Path, style: dict, cell: str, fill) -> Page:
    """A heat map page (V87): one member's 2D object, its .plot labels (ZLabel, LogZ too), its figure's
    and [plot]'s titles, coloured by Paint; no ratio, data, voiding or range."""
    labels = labels_of(full)
    page, override = page_settings(settings, full, rel, res_dir / rel, False, fill=fill, child=override)
    page.update({"heatmap": True, "ratio": False, "z_label": canonical(fill(labels.get("ZLabel", ""))),
                 "logz": bool(chosen("logz", labels.get("LogZ") == "1", labels.get("LogZ") == "1", (override, settings)))})
    layer = merge_style(style, override.get("style", {}))
    document = {"page": page, "style": layer, "curve": [{"file": str(merged), "object": f"{plan.point.name}/{root_name(full)}",
                                                         "label": plan.point.name}]}
    config = out_dir / f"{rel}.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(tomli_w.dumps(for_root(document)), encoding="utf-8")
    return Page(rel, config, res_dir / rel, cell=cell, object=base_of(full), document=document, sources=[],
                variants=[full], overrides={k for k, v in override.items() if v != DEFAULT},
                style=merge_style(base_style(), layer), plots=res_dir.parent)


def texts_of(run, plan, cell: str) -> dict[str, str]:
    """What a page text may cite at a point (V66): {cell}, {q:<quantity>} (the label of its value at the
    point, swept or static) and the texts the tools' folders give (rivet: {opt:NAME})."""
    out = {"cell": cell}
    for name, index in plan.values.items():
        if name in run.quantities:
            out[f"q:{name}"] = label_of(run.quantities[name], index)
    for step in plan.rendered.values():
        out.update(step.texts)
    return out


def axes_of(configuration) -> tuple[list, list]:
    """The sweep's axes that make pages (plot_points) and those that make curves; a combined axis is
    merged away (V35) and is neither."""
    groups = [g for g in axes(configuration) if not set(g) & set(configuration.combine)]
    pages_ = [g for g in groups if set(g) & set(configuration.plot_points)]
    return pages_, [g for g in groups if g not in pages_]


def check_figures(run, configuration) -> None:
    """At plan time too: a band (V69), [plot]'s or a figure's, and a merged figure's `over` (V82) name
    curve axes of the configuration, and a figure does not band what it merges."""
    curve_groups = axes_of(configuration)[1]
    settings = run.plot or {}
    hint = f"curve axes: {', '.join(g[0] for g in curve_groups) or 'none'} (swept, not plot_points or combined)"
    tables = [("[plot]", settings, ())] + [(f.where.split(": ", 1)[1], f.table, f.over) for f in figures(run)]
    for at, table, over in tables:
        band = table.get("band", [])
        for key, names in (("band", band if isinstance(band, list) else []), ("over", over)):
            for name in names:
                if not any(name in g for g in curve_groups):
                    raise HepError(f"{at}.{key} names {name}, which is not a curve axis of {configuration.key}",
                                   where=f"{run.path}: {at}.{key}", hint=hint)
        if set(band if isinstance(band, list) else []) & set(over):
            raise HepError(f"{at} both merges and bands {sorted(set(band) & set(over))[0]}", where=f"{run.path}: {at}.band",
                           hint="a merged axis is one curve already: band another, or merge less")
    for figure in (f for f in figures(run) if f.kind == "compare"):
        compared(run, figure)
    for figure in (f for f in figures(run) if f.kind == "scan"):                    # V85
        at = f"{run.path}: {figure.where.split(': ', 1)[1]}.x"
        if not any(figure.x in g for g in curve_groups):
            raise HepError(f"a scan figure's x names {figure.x}, which is not a curve axis of {configuration.key}",
                           where=at, hint=hint)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in run.quantities[figure.x].values):
            raise HepError(f"a scan figure's x, {figure.x}, has values that are not numbers", where=at,
                           hint="its values are the x axis: a quantity of numbers (a scan of named values is not drawn yet)")
        if figure.x in (figure.table.get("band") or []):
            raise HepError(f"a scan figure's x, {figure.x}, is its axis: it cannot be banded", where=f"{at.removesuffix('.x')}.band")


@dataclass(frozen=True)
class Compared:
    """One configuration of a compare figure: `ref` as the figure names it ("cfg", or
    "<Project>/<config>:<cfg>" in another run TOML, V88), its run and its configuration."""
    ref: str
    run: object
    configuration: object

    @property
    def own(self) -> bool:
        return ":" not in self.ref


def compared(run, figure: Figure) -> list[Compared]:
    """A compare figure's configurations (V83): those it names, else the sweep_runs ones; two at least,
    one of them this file's, every one with the same page and curve axes (another run's page axes with
    the same tags too), so that their pages pair up."""
    from .config import load
    at = f"{figure.where}.configurations"
    keys = list(figure.configurations) or (run.runs(None) if run.sweep_runs else [])
    if len(keys) < 2:
        raise HepError("a compare figure needs two configurations or more", where=at,
                       hint='configurations = ["a", "b"], or [run].sweep_runs: its configurations')
    if len(set(keys)) != len(keys):
        raise HepError("a compare figure names a configuration twice", where=at)
    out = []
    for ref in keys:
        owner, key = (run, ref) if ":" not in ref else (None, ref.rsplit(":", 1)[1])
        if owner is None:
            try:
                owner = load(ref.rsplit(":", 1)[0])
            except HepError as error:
                raise HepError(f"a compare figure names '{ref}': {error.message}", where=at, hint=error.hint) from None
        if key not in owner.configurations:
            raise HepError(f"a compare figure names '{ref}', which is not a configuration", where=at,
                           hint=did_you_mean(key, list(owner.configurations)) or f"configurations: {', '.join(owner.configurations)}")
        out.append(Compared(ref, owner, owner.configurations[key]))
    if not any(c.own for c in out):
        raise HepError("a compare figure names a configuration of its own file too", where=at,
                       hint="its pages are drawn by that configuration's plot stage, into this run's compare/")
    shapes = {c.ref: axes_of(c.configuration) for c in out}
    first = out[0]
    for c in out[1:]:
        if shapes[c.ref] != shapes[first.ref]:
            raise HepError(f"a compare figure's configurations differ in their axes: {first.ref} {_shape(shapes[first.ref])}, "
                           f"{c.ref} {_shape(shapes[c.ref])}", where=at,
                           hint="compared configurations sweep the same quantities, with the same plot_points and combine")
    for c in (c for c in out if not c.own):              # another run's page cells must be this run's
        for group in shapes[c.ref][0]:
            mine, theirs = run.quantities[group[0]], c.run.quantities[group[0]]
            if [tag_of(mine, i) for i in range(len(mine.values))] != [tag_of(theirs, i) for i in range(len(theirs.values))]:
                raise HepError(f"'{c.ref}' has other values of {group[0]}, a page axis, than this file", where=at,
                               hint="its pages pair with this run's by the page axes' tags")
    if figure.labels and len(figure.labels) != len(out):
        raise HepError(f"a compare figure's labels give one label per configuration ({len(out)})", where=f"{figure.where}.labels")
    return out


def _shape(shape) -> str:
    pages_, curves = shape
    return f"(pages: {', '.join(g[0] for g in pages_) or 'none'}; curves: {', '.join(g[0] for g in curves) or 'none'})"


def check_texts(run, plans) -> None:
    """V66 at plan time: every placeholder the run TOML's texts cite ([plot] and its children, the
    quantities' labels) is one the points have, so a typo costs no point run. Whether a page text has one
    value on its page is known only with the pages, at the plot stage."""
    if not run.plot:
        return
    cited: list[tuple[str, str]] = []

    def walk(value, at):
        if isinstance(value, str):
            cited.extend((m.group(1), at) for m in PLACEHOLDER.finditer(value))
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{at}.{k}")
        elif isinstance(value, list):
            for v in value:
                walk(v, at)
    walk(run.plot, "[plot]")
    for name, quantity in run.quantities.items():
        walk(quantity.labels, f"[quantities.{name}].labels")
    known = {"cell"} | {k for plan in plans for k in texts_of(run, plan, "")}
    for key, at in cited:
        if key not in known:
            raise HepError(f"a page text cites {{{key}}}, which is nothing the points have", where=f"{run.path}: {at}",
                           hint=did_you_mean(key, sorted(known)) or f"they have: {', '.join('{' + k + '}' for k in sorted(known))}")


def filler(known: list[dict[str, str]], where: str):
    """A function filling a text's placeholders from the points it speaks for: a page's (all its curves'
    points: a value must be the same at every one) or a curve's (its own point)."""
    def fill(text: str) -> str:
        def one(match):
            key = match.group(1)
            values = {k.get(key) for k in known}
            if None in values:
                cited = sorted({k for d in known for k in d})
                raise HepError(f"a page text cites {{{key}}}, which is nothing the points have", where=where,
                               hint=did_you_mean(key, cited) or f"they have: {', '.join('{' + k + '}' for k in cited)}")
            if len(values) > 1:
                raise HepError(f"a page text cites {{{key}}}, which differs between the curves of the page: "
                               f"{', '.join(sorted(values))}", where=where,
                               hint="cite it in the curves' labels (a quantity's labels), or make it a plot_points axis")
            return values.pop()
        return PLACEHOLDER.sub(one, text) if isinstance(text, str) else text
    return fill


def page_settings(settings: dict, path: str, rel: str, output: Path, with_data: bool,
                  child: dict | None = None, fill=lambda text: text) -> tuple[dict, dict]:
    """A page's [page] table: labels from the analysis's .plot, its figure's own values (`child`), and the
    [plot] values, their placeholders filled (`fill`, V66). Returns it and the figure's values."""
    labels = labels_of(path)
    override = override_of(child)

    def pick(name, ours, native, tables=(override, settings)):
        return chosen(name, ours, native, tables)

    def ours(name):
        return schema.default("plot", name)

    title, header = labels.get("Title", ""), labels.get("LegendTitle", "")     # as mkhtml (V51); LaTeX, as all text (V65)
    x_label, y_label = labels.get("XLabel", ""), labels.get("YLabel", "")
    log_x, log_y = labels.get("LogX") == "1", labels.get("LogY") == "1"
    ratio = labels["RatioPlot"] == "1" if labels.get("RatioPlot") in ("0", "1") else with_data   # mkhtml's rule
    page = {
        "name": rel, "output": str(output), "formats": formats_of(settings),
        "title": canonical(fill(pick("title", title, title))),
        "title_left": canonical(fill(pick("title_left", "", ""))),
        "title_right": canonical(fill(pick("title_right", "", ""))),
        "legend_header": canonical(fill(pick("legend_header", header, header))),
        "x_label": canonical(fill(pick("x_label", x_label, x_label, tables=(override,)))),
        "y_label": canonical(fill(pick("y_label", y_label, y_label, tables=(override,)))),
        "logx": bool(pick("logx", log_x, log_x)),
        "logy": bool(pick("logy", log_y, log_y)),
        "y_gutter": _gutter(pick("y_gutter", ours("y_gutter"), DEFAULT)),
        "x_gutter": _gutter(pick("x_gutter", DEFAULT, DEFAULT)),
        "ratio": bool(pick("ratio", ours("ratio"), ratio)),
        "ratio_label": "MC/Data" if with_data else "Ratio",
        "normalise": pick("normalise", ours("normalise"), False),                 # V68: "area" or false
        "void_empty": bool(pick("void_empty", ours("void_empty"), False)),     # neither tool voids by itself
        "min_entries": int(pick("min_entries", ours("min_entries"), 0)),
        "auto_range": bool(pick("auto_range", ours("auto_range"), False)),    # the tool's own range
        "range_pad": int(pick("range_pad", ours("range_pad"), 0)),
    }
    return page, override


def override_of(child: dict | None) -> dict:
    """What a figure's own table sets for its pages: any [plot] key marked `page` in the schema, and
    x_label, y_label, style. The implicit figure sets nothing of its own."""
    return {k: v for k, v in (child or {}).items() if k not in schema.FIGURE_OWN}


def chosen(name: str, ours, native, tables: tuple):
    """V55: the most specific table that sets a value wins. "default" keeps it as it is: in a child
    (an object's or an overlay's table) it is the parent's value, as if the key were absent; in the
    last table (the top level) it is `native`, set nothing: what the drawing tool does by itself.
    Nothing set anywhere is `ours`, the runner's default (the schema's)."""
    for table in tables:
        if name in table and table[name] != DEFAULT:
            return table[name]
    return native if tables[-1].get(name) == DEFAULT else ours


def _gutter(value):
    return value if value == "default" else float(value)


def _banded(curves: list, curve_groups: list, band: list, of_plan) -> list:
    """V69: the page's curves with the band quantities folded: one curve per value of the other curve
    axes (and per variant of the object, `of_plan(plan, full)` its place), the band axes' first value,
    with the others as its members. Without `band`: every curve, no members."""
    if not band:
        return [(plan, full, []) for plan, full in curves]
    banded = [g for g in curve_groups if set(g) & set(band)]
    rest = [g for g in curve_groups if g not in banded]
    groups: dict = {}
    for plan, full in curves:
        key = (tuple(plan.point.choice[g[0]] for g in rest), of_plan(plan, full))
        groups.setdefault(key, []).append((plan, full))
    out = []
    for members in groups.values():
        members.sort(key=lambda pf: tuple(pf[0].point.choice[g[0]] for g in banded))
        out.append((*members[0], members[1:]))
    return out


def _run_of(run, plan):
    """The run whose quantities a member's choice indexes: its own, for another run's (V88)."""
    return plan.context.get("run") or run


def _curve_look(run, plan, curve_groups) -> dict:
    """A curve's own look (V67): the styles of its curve axes' values at its point, a later axis's key
    over an earlier's. Empty: the page style's palette, in turn."""
    run = _run_of(run, plan)
    look: dict = {}
    for group in curve_groups:
        for name in group:
            if name in run.quantities and run.quantities[name].styles:
                look.update(run.quantities[name].styles[plan.point.choice[name]])
    return look


def _curve_label(run, plan, curve_groups, fill=lambda text: text) -> str:
    """The curve axes' labels at its point, after its own (a compared configuration's, V83); the run's
    name when it has neither."""
    run = _run_of(run, plan)
    own = [canonical(fill(plan.context["curve_label"]))] if plan.context.get("curve_label") else []
    labels = [canonical(fill(label_of(run.quantities[g[0]], plan.point.choice[g[0]]))) for g in curve_groups
              if g[0] in run.quantities]
    return ", ".join(own + labels) or run.name


def _paint(paint: Path, configs: list[Path], mode: list[str] = ()) -> dict[str, tuple[bool, str]]:
    """Paint on many pages, PAINT_BATCH per process (V64): each config's (ok, why)."""
    outcomes: dict[str, tuple[bool, str]] = {}
    for start in range(0, len(configs), PAINT_BATCH):
        batch = [str(c) for c in configs[start:start + PAINT_BATCH]]
        done = subprocess.run([str(paint), *batch, *mode], capture_output=True, text=True)
        if len(batch) == 1:
            outcomes[batch[0]] = (done.returncode == 0, _why(done) if done.returncode else "")
            continue
        for line in done.stdout.splitlines():
            if line.startswith("{"):
                entry = json.loads(line)
                outcomes[entry["page"]] = (entry["ok"], entry["error"])
        for config in batch:                                  # a crash leaves the rest without a line
            outcomes.setdefault(config, (False, _why(done)))
    return outcomes


def _why(done: subprocess.CompletedProcess) -> str:
    if done.returncode < 0 or done.returncode > 128:
        return f"Paint crashed (signal {abs(done.returncode) % 128})"
    for line in reversed((done.stderr + done.stdout).splitlines()):
        if line.strip() and not set(line.strip()) <= set("=-#"):
            return line.strip()[-200:]
    return f"exit {done.returncode}"


def write_index(where: Path, title: str, pages: list[tuple[str, str, Path]]) -> Path:
    """V70: <where>/index.html, the ROOT pages as mkhtml's index is the yoda backend's: a section per
    plot_points cell, each page shown by its PNG or SVG (an embedded PDF otherwise) and linked to every
    format drawn. `pages`: (cell, name, output without extension), in order."""
    def rel(path: Path) -> str:
        return html.escape(str(path.relative_to(where)) if path.is_relative_to(where) else str(path), quote=True)

    body, cells = [], {}
    for cell, name, output in pages:
        cells.setdefault(cell, []).append((name, output))
    for cell, members in cells.items():
        if cell:
            body.append(f"<h2>{html.escape(cell)}</h2>")
        body.append('<div class="grid">')
        for name, output in members:
            made = [output.with_name(f"{output.name}.{f}") for f in FORMATS]
            made = [m for m in made if m.is_file()]
            shown = next((m for m in made if m.suffix in (".png", ".svg")), None)
            pdf = next((m for m in made if m.suffix == ".pdf"), None)
            if shown:
                view = f'<a href="{rel(pdf or shown)}"><img src="{rel(shown)}" alt="{html.escape(name)}"></a>'
            elif pdf:
                view = f'<object data="{rel(pdf)}" type="application/pdf"><a href="{rel(pdf)}">{html.escape(name)}</a></object>'
            else:
                continue
            links = " ".join(f'<a href="{rel(m)}">{m.suffix[1:]}</a>' for m in made)
            body.append(f"<figure>{view}<figcaption>{html.escape(name.rsplit('/', 1)[-1])} · {links}</figcaption></figure>")
        body.append("</div>")
    index = where / "index.html"
    index.write_text(
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>" + html.escape(title) + "</title><style>"
        "body{font-family:sans-serif;margin:1.5em}.grid{display:flex;flex-wrap:wrap;gap:1em}"
        "figure{margin:0;width:22em}img,object{width:100%;height:auto;min-height:18em;border:1px solid #ddd}"
        "figcaption{font-size:.85em;color:#444}</style></head><body><h1>" + html.escape(title) + "</h1>\n"
        + "\n".join(body) + "\n</body></html>\n", encoding="utf-8")
    return index


def for_backend(page: Page, name: str) -> Page:
    """The page as another backend draws it: into results/…/plots/<name>/ instead of Paint's root/."""
    return replace(page, output=page.plots / name / page.name) if page.plots else page


def draw(run, configuration, plans, say, others=None) -> int:
    """The plot stage: Paint on every page, then any other backend on the same pages. Returns the
    number of pages that failed, summed over the backends. Then each compare figure that names this
    configuration (V83), once all of its configurations have complete points: `others(key)` gives
    another configuration's plans."""
    if not run.plot:
        return 0
    paint = build_root() / "Paint.exe"
    if not paint.exists():
        raise HepError("build/Paint.exe is not built", hint="hep build")
    todo = pages(run, configuration, plans)
    failed = _draw(run, paint, todo, f"{run.name} · {configuration.label}", say) if todo else 0
    if not todo:
        say("plot: no complete point has a YODA product to draw")
    for figure in (f for f in figures(run) if f.kind == "compare"):
        named = compared(run, figure)
        if configuration.key not in {c.ref for c in named if c.own}:
            continue
        sets, waiting = [], []
        for c in named:
            mine = plans if c.own and c.ref == configuration.key else (others(c.ref) if others else [])
            complete = [p for p in mine if is_complete(p) and yoda_of(p)]
            if complete:
                sets.append((c, complete))
            else:
                waiting.append(c.ref)
        if waiting:
            say(f"plot: compare {figure.name} waits for {', '.join(waiting)}: no complete point yet")
            continue
        made = compare_pages(run, figure, sets)
        say(f"plot: compare {figure.name}, {len(named)} configurations")
        failed += _draw(run, paint, made, f"{run.name} · {figure.name}", say)
    return failed


def _draw(run, paint: Path, todo: list[Page], title: str, say) -> int:
    """Paint on these pages, then the other backends on the same pages, an index each."""
    names = backends(run.plot)
    others = [n for n in names if n != "root"]
    # One Paint for many pages (V64): it draws them (root) and writes each page's ranges beside its config
    # for the other backends (--ranges), or only the ranges (--ranges-only, a yoda-only run).
    mode = ["--ranges"] if others and "root" in names else ["--ranges-only"] if others else []
    failed = 0
    outcomes = _paint(paint, [p.config for p in todo], mode)
    for page in todo:
        ok, why = outcomes[str(page.config)]
        if not ok:
            failed += 1
            say(f"plot: {page.name} failed: {why}")
        elif others:
            page.ranges = json.loads(page.config.with_name(page.config.name + ".ranges.json").read_text())
    if "root" in names:
        where = todo[0].config.parent if "/" not in todo[0].name else todo[0].config.parent.parent
        say(f"plot: {len(todo) - failed} of {len(todo)} page(s) drawn; configs in {where}")
        drawn = [(p.cell, p.name, p.output) for p in todo if outcomes[str(p.config)][0]]
        if drawn:                                            # V70: the ROOT pages' own index
            write_index(todo[0].plots / "root", title, drawn)
    if others and failed:
        todo = [p for p in todo if p.ranges]                 # a page Paint could not read has no ranges
    maps = [p for p in todo if p.document["page"].get("heatmap")]
    if others and maps:                                      # V87: Paint's alone, for now
        say(f"plot: {len(maps)} heat map page(s) drawn by Paint only ({', '.join(others)} draw 1D pages)")
        todo = [p for p in todo if not p.document["page"].get("heatmap")]
    for name in others:
        cells: dict[str, list[Page]] = {}                    # a page set: one folder of pages (a cell's, or a merged figure's in it)
        for page in todo:
            cells.setdefault(page.name.rpartition("/")[0], []).append(for_backend(page, name))
        module = backend(name)
        failed += module.draw(cells, run.plot, say)
        if getattr(module, "INDEX", False):                  # a backend without its own index.html (V71)
            drawn = [p for every in cells.values() for p in every
                     if any(p.output.with_name(f"{p.output.name}.{f}").is_file() for f in FORMATS)]
            if drawn:
                write_index(todo[0].plots / name, title, [(p.cell, p.name, p.output) for p in drawn])
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
            raws = raws_of(p)
            found = {o: (f"{tags[i]}/{root_name(o)}",
                         f"{tags[i]}/RAW/{root_name(o)}" if "/RAW" + o in raws else None)
                     for o in objects_of(p)}
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
    failed, written = 0, {}
    for path in pages_of:
        rel = path.strip("/").replace(":", "__")
        page, _ = page_settings(settings, path, rel, outdir / rel, False)
        document = {"page": page, "style": layer, "curve": [
            {"file": str(file), "object": found[path][0], **({"raw": found[path][1]} if found[path][1] else {}),
             "label": label} for label, file, found in curves if path in found]}
        config = work / f"{rel}.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(tomli_w.dumps(for_root(document)), encoding="utf-8")
        written[str(config)] = rel
    drawn = []
    for config, (ok, why) in _paint(paint, [Path(c) for c in written]).items():
        if not ok:
            failed += 1
            say(f"plot: {written[config]} failed: {why}")
        else:
            drawn.append(("", written[config], outdir / written[config]))
    if drawn:
        write_index(outdir, "hep plot", drawn)                 # V70
    say(f"plot: {len(pages_of) - failed} of {len(pages_of)} page(s), {len(curves)} curve(s) → {outdir}")
    return failed
