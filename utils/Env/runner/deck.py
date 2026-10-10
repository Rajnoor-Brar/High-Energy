"""`hep deck` (docs/reporter): a deck of slides from drawn pages, in reports/<deck>/.

A deck's folder holds the user's deck.md (the talk) and deck.toml (where its plots come from:
utils/Env/schema/deck.toml). The plots are blocks, each a grid of panels:

* **From result folders** (a recipe's `[blocks.<name>]`, V103): `from = "<Project>/<run>"`, its result
  `folders` (a panel each) and the `pages` drawn in them (a block each), plus an `extra` file. A panel is
  labelled by its folder's event count (the events asked for: its provenance, else the count its name
  ends in; what the YODA counted only when neither says) or its folder's name. No run TOML is read: result folders are taken as they are on disk (D-R12).
* **From the folder's own files** (folder mode, when the recipe names no block): grouped into blocks
  and panels by a regex over their names, in natural order.

Collecting copies a recipe's panels into panels/<block>/, again only when one changed, so the deck holds
everything it shows (D-R5).

Building (V104) draws each block's composite (figures/<block>.pdf by pdflatex, its .png rendered from
it: utils/Env/figures/layout.py), then turns the user's deck.md into every target with pandoc: a block
reference `![](<block>)` becomes its composite's path, the PDF for Beamer, the PNG for pptx and HTML.
deck.md is only read (D-R4); `--init` writes it once.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
import shutil
import subprocess
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import hepfiles, plugins, schema, viewer
from .errors import HepError, did_you_mean
from .paths import output_root, repo_root, reports_root, results_root

RECIPE = "deck.toml"
TALK = "deck.md"
PANELS = "panels"
OUTPUTS = ("deck.pdf", "deck.pptx", "deck.html", "overleaf.zip", "index.html")
GLOB = re.compile(r"[*?\[]")
COUNT = re.compile(r"^0*(\d+(?:\.\d+)?)([kMG])$")
NAMED = re.compile(r"_0*(\d+(?:\.\d+)?)([kMG])$")          # a result folder's name that ends in its count


@dataclass
class Panel:
    label: str
    source: Path                 # where it came from
    file: Path                   # what the deck shows: its copy under panels/, or the source in the deck
    origin: str                  # for --list: "<folder>/<page>", or the file's name


@dataclass
class Block:
    name: str
    title: str
    panels: list[Panel]
    size: str
    columns: int | None
    labels: bool
    titles: bool
    group: str = ""              # the recipe table it came from: a section of the generated slides


@dataclass
class Deck:
    dir: Path
    settings: dict               # [deck], with the schema's defaults
    blocks: list[Block]
    recipe: bool                 # blocks from deck.toml, not from the folder's files


def natural(text: str) -> list:
    """A sort key that orders numbers by value: 1M < 10M < 150M, d2 < d10."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", text) if t]


def slug(text: str) -> str:
    """A file name's part: anything but letters, digits, . _ - becomes _."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "panel"


def count(n: float) -> str:
    """An event count to 2 significant figures, with k, M or G: 9,999,062 → 10M."""
    if n <= 0:
        return "0"
    rounded = round(n, 1 - math.floor(math.log10(n)))
    for unit, scale in (("G", 1e9), ("M", 1e6), ("k", 1e3), ("", 1.0)):
        if rounded >= scale:
            return f"{rounded / scale:g}{unit}"
    return f"{rounded:g}"


def deck_dir(name: str) -> Path:
    """`hep deck <deck>`: reports/<deck>, unless it starts with ./, ../ or / (a path)."""
    path = Path(name) if name.startswith(("./", "../", "/")) else reports_root() / name
    if not path.is_dir():
        raise HepError(f"no deck folder {path}", hint="make the folder, and put a deck.toml or the plots' files in it")
    return path.resolve()


# ── the event count of a result folder ────────────────────────────────────────────────────────

def requested(output: Path) -> float | None:
    """The events a result folder's points were run with: its first point's provenance `events`, in
    output/ while it is kept."""
    if output.is_dir():
        for point in sorted((p for p in output.iterdir() if p.is_dir()), key=lambda p: natural(p.name)):
            record = point / "provenance.json"
            try:
                value = json.loads(record.read_text(encoding="utf-8")).get("events") if record.is_file() else None
            except (OSError, json.JSONDecodeError):
                value = None
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                return float(value)
    return None


def analysed(results: Path) -> float | None:
    """The events a result folder's first YODA file counted (/RAW/_EVTCOUNT): what Rivet saw, which may
    be a little short of what was asked for."""
    yodas = sorted((p for p in results.glob("*/*.yoda*") if p.parts[-2] != "plots" and p.name.endswith((".yoda", ".yoda.gz"))),
                   key=lambda p: natural(str(p)))
    for yoda in yodas:
        if (found := hepfiles.entries(yoda, "/RAW/_EVTCOUNT") or hepfiles.entries(yoda, "/_EVTCOUNT")):
            return found
    return None


# ── blocks ─────────────────────────────────────────────────────────────────────────────────────

def _settings(values: dict, where: str) -> dict:
    schema.check(values, "deck", where)
    return {key: values.get(key, entry.get("default")) for key, entry in schema.keys("deck").items()}


def _folders(run_dir: Path, entries: list[str], where: str) -> list[str]:
    present = sorted((p.name for p in run_dir.iterdir() if p.is_dir()), key=natural)
    out: list[str] = []
    for entry in entries:
        if GLOB.search(entry):
            found = [name for name in present if fnmatch.fnmatchcase(name, entry)]
            if not found:
                raise HepError(f"folders: '{entry}' names no result folder of {run_dir}", where=where,
                               hint=f"there are: {', '.join(present)}")
        elif entry in present:
            found = [entry]
        else:
            raise HepError(f"no result folder {entry} in {run_dir}", where=where,
                           hint=did_you_mean(entry, present) or f"there are: {', '.join(present)}")
        out += [name for name in found if name not in out]
    return out


def _pages_of(where: Path) -> dict[str, Path]:
    """A folder's drawn pages: name (`d01-x01-y01`, `18x275/d01-x01-y01`) → its PDF, else its PNG. Sheets
    are not pages."""
    pages: dict[str, Path] = {}
    if not where.is_dir():
        return pages
    for path in sorted(where.rglob("*")):
        relative = path.relative_to(where)
        if path.suffix.lower() not in (".pdf", ".png") or relative.parts[0] == "sheets":
            continue
        name = relative.with_suffix("").as_posix()
        if name not in pages or path.suffix.lower() == ".pdf":
            pages[name] = path
    return pages


def _page_matches(name: str, glob: str) -> bool:
    return fnmatch.fnmatchcase(name, glob) or ("/" not in glob and fnmatch.fnmatchcase(name.rsplit("/", 1)[-1], glob))


def _shorts(names: list[str]) -> dict[str, str]:
    """Each page's part of its block's name: without -x01-y01 when that stays unique, `/` as `-`."""
    full = {name: name.replace("/", "-") for name in names}
    trimmed = {name: re.sub(r"-x01-y01$", "", short) for name, short in full.items()}
    return trimmed if len(set(trimmed.values())) == len(names) else full


def _labels(run_dir: Path, project_run: str, folders: list[str], how: str, where: str) -> dict[str, str]:
    if how == "folder":
        labels = {folder: re.sub(r"^\d+_", "", folder) for folder in folders}
    else:
        labels = {}
        for folder in folders:                  # the events asked for; what Rivet counted only when nothing says
            n = requested(output_root() / project_run / folder)
            named = NAMED.search(folder)
            if n is not None:
                labels[folder] = count(n)
            elif named:
                labels[folder] = f"{named[1]}{named[2]}"
            elif (n := analysed(run_dir / folder)) is not None:
                labels[folder] = count(n)
            else:
                raise HepError(f"no event count for {folder}", where=where,
                               hint='no provenance in output/, no count in its name, no YODA with /RAW/_EVTCOUNT; '
                                    'label = "folder" labels it by its name')
    seen: dict[str, str] = {}
    for folder, label in labels.items():
        if label in seen:
            raise HepError(f"{seen[label]} and {folder} are both labelled {label}", where=where,
                           hint='take one of them only, or label = "folder"')
        seen[label] = folder
    return labels


def _pattern(text: str, where: str, what: str, **names: str) -> str:
    try:
        return text.format(**names)
    except (KeyError, IndexError, ValueError) as error:
        raise HepError(f"{what} '{text}' cannot be filled ({error})", where=where,
                       hint=f"its placeholders are {', '.join('{' + n + '}' for n in names)}") from None


def _recipe_blocks(folder: Path, name: str, spec, settings: dict, where: str) -> list[Block]:
    if not isinstance(spec, dict):
        raise HepError("a block is a table, [blocks.<name>]", where=where)
    schema.check(spec, "block", where)
    missing = [key for key, entry in schema.keys("block").items() if entry.get("required") and key not in spec]
    if missing:
        raise HepError(f"'{missing[0]}' is required", where=where, hint=schema.keys("block")[missing[0]]["doc"])
    project_run = spec["from"]
    if project_run.count("/") != 1 or not all(project_run.split("/")):
        raise HepError(f'from = "{project_run}" is not "<Project>/<run>"', where=where)
    run_dir = results_root() / project_run
    if not run_dir.is_dir():
        project = run_dir.parent
        runs = sorted(p.name for p in project.iterdir() if p.is_dir()) if project.is_dir() else []
        raise HepError(f"no results for {project_run} under {results_root()}", where=where,
                       hint=did_you_mean(run_dir.name, runs) or (f"runs there: {', '.join(runs)}" if runs else None))
    folders = _folders(run_dir, spec["folders"], where)
    chosen = spec.get("backend", settings["backend"])
    backends = [chosen] if isinstance(chosen, str) else list(chosen)
    drawn: dict[str, dict[str, Path]] = {}               # folder → page → file, the first backend's that has it
    for f in folders:
        drawn[f] = {}
        for backend in reversed(backends):
            drawn[f].update(_pages_of(run_dir / f / "plots" / backend))
    names: list[str] = []
    def elsewhere(page_glob: str, among: list[str]) -> str | None:
        """Another backend that drew such a page in one of the folders: its name."""
        return next((b for b in ("root", "mpl", "yoda") if b not in backends for f in among
                     if any(_page_matches(p, page_glob) for p in _pages_of(run_dir / f / "plots" / b))), None)

    def use(backend: str) -> str:
        return f"{backend} drew it there: backend = {[*backends, backend]}".replace("'", '"')

    for glob in spec["pages"]:
        found = sorted({p for f in folders for p in drawn[f] if _page_matches(p, glob)}, key=natural)
        if not found:
            other = elsewhere(glob, folders)
            raise HepError(f"pages: '{glob}' names no page drawn in plots/{'|'.join(backends)}/ of these folders",
                           where=where, hint=use(other) if other else f"they are under {run_dir}/<folder>/plots/<backend>/")
        names += [p for p in found if p not in names]
    for f in folders:
        absent = [p for p in names if p not in drawn[f]]
        if absent:
            other = elsewhere(absent[0], [f])
            raise HepError(f"{f} has no page {absent[0]} in plots/{'|'.join(backends)}/", where=where,
                           hint=use(other) if other else f"draw it there (hep plot), or leave {f} out of folders")
    shorts = _shorts(names)
    labels = _labels(run_dir, project_run, folders, spec.get("label", "events"), where)
    blocks = []
    for page in names:
        short = shorts[page]
        block = f"{name}-{short}"
        panels = [Panel(labels[f], drawn[f][page], drawn[f][page],
                        str(drawn[f][page].relative_to(run_dir).with_suffix(""))) for f in folders]
        if "extra" in spec:
            relative = _pattern(spec["extra"], where, "extra", block=block, page=page, short=short)
            path = folder / relative
            if not path.is_file():
                raise HepError(f"no file {relative} in the deck", where=where, hint=f"extra = \"{spec['extra']}\", for {block}")
            panels.append(Panel(path.stem.rsplit("_", 1)[-1], path, path, relative))
        title = _pattern(spec["title"], where, "title", block=block, page=page, short=short) if "title" in spec \
            else f"{name} {short}"
        blocks.append(Block(block, title, panels, spec.get("size", settings["size"]),
                            spec.get("columns", settings["columns"]), spec.get("labels", settings["labels"]),
                            spec.get("titles", settings["titles"]), group=name))
    return blocks


def _label(panel: str) -> str:
    """Folder mode: a panel named by a count (`010M`) is labelled `10M events`; any other as it is."""
    found = COUNT.match(panel)
    return f"{found[1]}{found[2]} events" if found else panel


def _folder_blocks(folder: Path, settings: dict, where: str) -> list[Block]:
    try:
        pattern = re.compile(settings["group"])
    except re.error as error:
        raise HepError(f"group is not a regex: {error}", where=where) from None
    if "block" not in pattern.groupindex:
        raise HepError("group needs a block group, (?P<block>…)", where=where, hint=f"group = '{schema.default('deck', 'group')}'")
    groups: dict[str, list[tuple[str, Path]]] = {}
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in (".pdf", ".png") or path.name in OUTPUTS:
            continue
        found = pattern.fullmatch(path.stem)
        block = found["block"] if found else path.stem
        panel = (found.groupdict().get("panel") or "") if found else ""
        groups.setdefault(block, []).append((panel, path))
    blocks = []
    for block in sorted(groups, key=natural):
        members = sorted(groups[block], key=lambda m: (m[1].suffix.lower() == ".png", natural(m[0]), m[1].name))
        panels = [Panel(_label(panel), path, path, path.name) for panel, path in members]
        blocks.append(Block(block, block.replace("_", " "), panels, settings["size"], settings["columns"],
                            settings["labels"], settings["titles"]))
    return blocks


def load(name: str) -> Deck:
    """A deck: its settings and blocks, from deck.toml's blocks, else from the folder's files."""
    folder = deck_dir(name)
    recipe = folder / RECIPE
    data: dict = {}
    if recipe.is_file():
        try:
            data = tomllib.loads(recipe.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise HepError(f"cannot read {RECIPE}: {error}", where=str(recipe)) from None
    for table in data:
        if table not in ("deck", "blocks"):
            raise HepError(f"unknown table [{table}]", where=str(recipe),
                           hint=did_you_mean(table, ("deck", "blocks")) or "a recipe has [deck] and [blocks.<name>]")
    settings = _settings(data.get("deck", {}), f"{recipe} [deck]")
    named = data.get("blocks", {})
    if named:
        blocks = [b for key, spec in named.items() for b in _recipe_blocks(folder, key, spec, settings, f"{recipe} [blocks.{key}]")]
    else:
        blocks = _folder_blocks(folder, settings, f"{recipe} [deck]")
    if not blocks:
        raise HepError(f"{folder} has no plots", hint="name blocks in deck.toml ([blocks.<name>]), or put PDF or PNG files in the folder")
    seen: set[str] = set()
    for block in blocks:
        if block.name in seen:
            raise HepError(f"two blocks are named {block.name}", where=str(recipe), hint="rename one of the [blocks] tables")
        seen.add(block.name)
    return Deck(folder, settings, blocks, bool(named))


# ── collecting ─────────────────────────────────────────────────────────────────────────────────

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gather(deck: Deck) -> int:
    """A recipe's panels from results/ copied into panels/<block>/<NN>_<label>.<ext>, again only when one
    changed; what no panel is any more is removed. Panels already in the deck (folder mode, extras) stay
    where they are. Returns how many files were copied."""
    root = deck.dir / PANELS
    wanted: set[Path] = set()
    copied = 0
    for block in deck.blocks:
        for number, panel in enumerate(block.panels, 1):
            if panel.source.resolve().is_relative_to(deck.dir):
                continue
            target = root / slug(block.name) / f"{number:02d}_{slug(panel.label)}{panel.source.suffix.lower()}"
            wanted.add(target)
            if not target.is_file() or _sha(target) != _sha(panel.source):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(panel.source, target)
                copied += 1
            panel.file = target
    if root.is_dir():
        for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file() and path not in wanted:
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    return copied


def listing(deck: Deck) -> list[str]:
    """`hep deck --list`: each block, its panels, labels and where each came from."""
    kind = "deck.toml's blocks" if deck.recipe else "the folder's files"
    lines = [f"deck {deck.dir}: {len(deck.blocks)} block(s), from {kind}"]
    for block in deck.blocks:
        columns = block.columns or "auto"
        lines.append(f"  {block.name}  \"{block.title}\"  {len(block.panels)} panel(s), {block.size}, columns {columns}")
        width = max(len(p.label) for p in block.panels)
        for panel in block.panels:
            lines.append(f"    {panel.label:<{width}}  {panel.origin}")
    return lines


# ── building (V104) ────────────────────────────────────────────────────────────────────────────

TARGETS = ("pdf", "pptx", "html", "overleaf", "viewer")
FIGURES = "figures"
BUILD = "build"
#: A Markdown image: `![alt](target){attributes}`. A target with no `.` or `/` names a block.
REFERENCE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<target>[^)\s]+)\)(?P<attrs>\{[^}\n]*\})?")
ATTRIBUTE = re.compile(r'([\w-]+)=("[^"]*"|[^\s}]+)')
OURS = ("panels", "columns", "size")
STARTER = """# deck.toml: where this deck's plots come from (docs/04_Config_Reference.md §15).
# With no [blocks.<name>] table, the deck takes this folder's own PDF and PNG files (folder mode).

[deck]
# size    = "full"        # a composite's size: full, half, a4, square
# labels  = true          # each panel's label on the composites
# titles  = false         # a block's title on its composites
# targets = ["pdf", "pptx", "html", "overleaf", "viewer"]

# [blocks.zeus]           # a block per page, a panel per result folder
# from    = "PhotoProduction/zeus"
# folders = ["01_PDFs_010M", "01_PDFs_025M"]
# pages   = ["d01-x01-y01"]
"""


@dataclass
class Figure:
    """A composite: some of a block's panels, at a size, drawn to `stem`.pdf and .png."""
    block: Block
    panels: list[Panel]
    size: str
    columns: int | None
    stem: Path


@dataclass
class Talk:
    """The slides' source: deck.md (or, without one, slides generated from the blocks), the composites
    it needs, and its references to them."""
    text: str
    own: bool                                          # the user's deck.md, not generated
    figures: dict[Path, Figure] = field(default_factory=dict)
    references: list[tuple[re.Match, Figure | None]] = field(default_factory=list)


def _layout():
    return plugins.load(repo_root() / "utils" / "Env" / "figures" / "layout.py", "layout")


def generated(deck: Deck) -> str:
    """Slides for a deck without deck.md: a title slide, then a slide per block (a section per recipe table)."""
    lines = ["---", f"title: {json.dumps(deck.dir.name)}", "---", ""]
    section = None
    for block in deck.blocks:
        if block.group and block.group != section:
            lines += [f"# {block.group}", ""]
            section = block.group
        lines += [f"## {block.title}", "", f"![]({block.name})", ""]
    return "\n".join(lines)


def _attributes(text: str | None) -> dict[str, str]:
    return {k: v.strip('"') for k, v in ATTRIBUTE.findall(text or "")}


def _chosen(block: Block, wanted: str, where: str) -> list[Panel]:
    """A block's panels by label, in the order given: `panels="10M 200M"` (commas when labels have spaces)."""
    names = [n.strip() for n in (wanted.split(",") if "," in wanted else wanted.split()) if n.strip()]
    labels = {p.label: p for p in block.panels}
    out = []
    for name in names:
        if name not in labels:
            raise HepError(f"{block.name} has no panel {name!r}", where=where,
                           hint=did_you_mean(name, labels) or f"its panels: {', '.join(labels)}")
        out.append(labels[name])
    return out


def talk(deck: Deck) -> Talk:
    """deck.md read (or generated), with its block references resolved into composites."""
    path = deck.dir / TALK
    own = path.is_file()
    made = Talk(path.read_text(encoding="utf-8") if own else generated(deck), own)
    blocks = {b.name: b for b in deck.blocks}
    figures = deck.dir / FIGURES
    for block in deck.blocks:                          # every block's whole composite, for the viewer too
        stem = figures / slug(block.name)
        made.figures[stem] = Figure(block, block.panels, block.size, block.columns, stem)
    for found in REFERENCE.finditer(made.text):
        target = found["target"]
        if "." in target or "/" in target:
            made.references.append((found, None))
            continue
        line = made.text.count("\n", 0, found.start()) + 1
        where = f"{path}:{line}" if own else "the generated slides"
        if target not in blocks:
            raise HepError(f"no block {target}", where=where,
                           hint=did_you_mean(target, blocks) or f"the blocks: {', '.join(blocks)}")
        block, ours = blocks[target], _attributes(found["attrs"])
        panels = _chosen(block, ours["panels"], where) if "panels" in ours else block.panels
        size = ours.get("size", block.size)
        if size not in schema.keys("deck")["size"]["choices"]:
            raise HepError(f"size must be one of {', '.join(schema.keys('deck')['size']['choices'])}, not {size!r}", where=where)
        try:
            columns = int(ours["columns"]) if "columns" in ours else block.columns
        except ValueError:
            raise HepError(f"columns must be a number, not {ours['columns']!r}", where=where) from None
        stem = figures / slug(block.name)
        if panels != block.panels or size != block.size or columns != block.columns:
            variant = hashlib.sha256("\0".join([*(p.label for p in panels), size, str(columns)]).encode()).hexdigest()[:8]
            stem = figures / f"{slug(block.name)}.{variant}"
        made.figures.setdefault(stem, Figure(block, panels, size, columns, stem))
        made.references.append((found, made.figures[stem]))
    return made


def _key(figure: Figure, dpi: int) -> str:
    block = figure.block
    parts = [figure.size, str(figure.columns), str(block.labels), str(block.titles), block.title, str(dpi)]
    parts += [f"{p.label}\0{_sha(p.file)}" for p in figure.panels]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def draw(figure: Figure, dpi: int) -> bool:
    """The composite's PDF and PNG, unless they are there for these panels and settings. True when drawn."""
    stamp = figure.stem.with_name(figure.stem.name + ".sha256")
    key = _key(figure, dpi)
    pdf, png = (figure.stem.with_name(figure.stem.name + e) for e in (".pdf", ".png"))
    if stamp.is_file() and stamp.read_text().strip() == key and pdf.is_file() and png.is_file():
        return False
    block = figure.block
    try:
        _layout().composite([(p.file, p.label if block.labels else "") for p in figure.panels], figure.stem,
                            figure.size, figure.columns, labels=block.labels,
                            title=block.title if block.titles else "", dpi=dpi)
    except ValueError as error:
        raise HepError(f"composite {figure.stem.name}: {error}") from None
    stamp.write_text(key + "\n")
    return True


def _copy(made: Talk, deck: Deck, suffix: str) -> str:
    """deck.md with each block reference pointing at its composite (`suffix` .pdf or .png), its own
    attributes (panels, columns, size) taken out and any others kept."""
    out, at = [], 0
    for found, figure in made.references:
        out.append(made.text[at:found.start()])
        at = found.end()
        if figure is None:
            out.append(found.group(0))
            continue
        kept = [f"{k}={v}" for k, v in ATTRIBUTE.findall(found["attrs"] or "") if k not in OURS]
        path = figure.stem.with_name(figure.stem.name + suffix).relative_to(deck.dir).as_posix()
        out.append(f"![{found['alt']}]({path})" + ("{" + " ".join(kept) + "}" if kept else ""))
    out.append(made.text[at:])
    return "".join(out)


def _embed_flag() -> str:
    """pandoc's flag for one self-contained HTML file: --embed-resources from 2.19, --self-contained before."""
    done = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
    found = re.search(r"pandoc\S*\s+(\d+)\.(\d+)", done.stdout)
    return "--embed-resources" if found and (int(found[1]), int(found[2])) >= (2, 19) else "--self-contained"


def _pandoc(deck: Deck, args: list[str], target: str) -> None:
    done = subprocess.run(["pandoc", *args], cwd=deck.dir, capture_output=True, text=True)
    if done.returncode != 0:
        tail = "\n".join((done.stderr or done.stdout).strip().splitlines()[-6:])
        raise HepError(f"pandoc could not make {target}", where=str(deck.dir), hint=tail or f"exit {done.returncode}")


def _title(made: Talk, deck: Deck) -> str:
    front = re.match(r"---\n(.*?)\n---", made.text, re.S)
    found = re.search(r"^title:\s*(.+)$", front.group(1), re.M) if front else None
    return found.group(1).strip().strip("'\"") if found else deck.dir.name


def build(deck: Deck, only: list[str] | None = None, say: Callable[[str], None] = print) -> list[Path]:
    """The composites, then each target (`only` or [deck].targets): deck.pdf, deck.pptx, deck.html,
    overleaf.zip, index.html. Returns what was made."""
    targets = list(only or deck.settings["targets"])
    made = talk(deck)
    drawn = sum(draw(f, deck.settings["dpi"]) for f in made.figures.values())
    say(f"deck: {len(made.figures)} composite(s), {drawn} drawn" + ("" if made.own else "; no deck.md: a slide per block"))
    slides = [t for t in targets if t != "viewer"]
    if slides and not shutil.which("pandoc"):
        raise HepError("the slides are made by pandoc, which is not on PATH",
                       hint="install it (apt: pandoc; Homebrew: pandoc), or build only the viewer: --only viewer")
    work = deck.dir / BUILD
    work.mkdir(exist_ok=True)
    vector, raster = work / "deck.vector.md", work / "deck.raster.md"
    vector.write_text(_copy(made, deck, ".pdf"), encoding="utf-8")
    raster.write_text(_copy(made, deck, ".png"), encoding="utf-8")
    beamer = ["-t", "beamer", "-V", "aspectratio=169"]
    out: list[Path] = []
    if "pdf" in targets:
        _pandoc(deck, [str(vector.relative_to(deck.dir)), *beamer, "--pdf-engine=pdflatex", "-o", "deck.pdf"], "deck.pdf")
        out.append(deck.dir / "deck.pdf")
    if "overleaf" in targets:
        _pandoc(deck, [str(vector.relative_to(deck.dir)), *beamer, "-s", "-o", f"{BUILD}/deck.tex"], "overleaf.zip")
        local = {found["target"] for found in REFERENCE.finditer(vector.read_text(encoding="utf-8"))}
        with zipfile.ZipFile(deck.dir / "overleaf.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(work / "deck.tex", "deck.tex")
            for name in sorted(local):
                if (deck.dir / name).is_file():
                    bundle.write(deck.dir / name, name)
        out.append(deck.dir / "overleaf.zip")
    if "pptx" in targets:
        _pandoc(deck, [str(raster.relative_to(deck.dir)), "-t", "pptx", "-o", "deck.pptx"], "deck.pptx")
        out.append(deck.dir / "deck.pptx")
    if "html" in targets:
        _pandoc(deck, [str(raster.relative_to(deck.dir)), "-t", "dzslides", "-s", _embed_flag(), "-o", "deck.html"], "deck.html")
        out.append(deck.dir / "deck.html")
    if "viewer" in targets:
        shown = [viewer.Shown(b.name, b.title, [(p.label, p.file) for p in b.panels],
                              (deck.dir / FIGURES / f"{slug(b.name)}.pdf")) for b in deck.blocks]
        out.append(viewer.page(deck.dir / "index.html", _title(made, deck), shown))
    if out:
        say("deck: " + ", ".join(p.name for p in out) + f" in {deck.dir}")
    return out


def init(deck: Deck) -> list[Path]:
    """`hep deck --init`: deck.md, a title slide and a slide per block (a section per recipe table), and a
    starter deck.toml for a folder without one. Never over what is there."""
    talk_file, recipe = deck.dir / TALK, deck.dir / RECIPE
    if talk_file.exists():
        raise HepError(f"{talk_file} is there already", hint="--init writes it once: edit it, or remove it to start again")
    talk_file.write_text(generated(deck), encoding="utf-8")
    made = [talk_file]
    if not recipe.exists():
        recipe.write_text(STARTER, encoding="utf-8")
        made.append(recipe)
    return made
