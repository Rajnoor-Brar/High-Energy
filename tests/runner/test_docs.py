"""The manual, held to the code (docs/06_Developer_Guide.md §8).

* every relative link in docs/ resolves, anchors included;
* every TOML block parses, and every complete run TOML example loads through the runner's parser;
* every key the runner accepts is in the reference: config.py's tables, [plot.data] and
  [plot.object] keys, base.toml's style keys, and every tool folder's options;
* every tool folder has its section in 05;
* every section the code cites (`docs/04_Config_Reference.md §9.4`, `04 §9.4`) exists, and every id
  it cites (V22, L18, C7, F10, R1, 00/B5) is in the record.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from runner import config, plot, tools

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
PAGES = sorted(DOCS.glob("*.md"))
NUMBERED = {p.name[:2]: p for p in PAGES if p.name[:2].isdigit()}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    out = heading.strip().lower()
    out = re.sub(r"[^\w\- ]", "", out)
    return out.replace(" ", "-")


def headings(path: Path) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^#{1,6} (.+)$", text(path), re.M)]


def sections(path: Path) -> set[str]:
    """Section numbers of a page: `## 9. …` → 9, `### 9.4 …` → 9.4."""
    return {m.group(1) for h in headings(path) if (m := re.match(r"(\d+(?:\.\d+)*)\.?\s", h))}


def blocks(path: Path, lang: str) -> list[str]:
    return re.findall(r"^```" + lang + r"\n(.*?)^```", text(path), re.S | re.M)


def reference() -> str:
    return text(NUMBERED["04"]) + text(NUMBERED["05"])


def test_the_manual_is_the_seven_pages_and_its_index():
    assert sorted(NUMBERED) == ["01", "02", "03", "04", "05", "06", "07"]
    assert (DOCS / "README.md").exists()


@pytest.mark.parametrize("page", PAGES + [REPO / "bots" / "BOT.md"], ids=lambda p: p.name)
def test_every_relative_link_resolves(page):
    for target in re.findall(r"\]\(([^)\s]+)\)", text(page)):
        if re.match(r"[a-z]+://", target) or target.startswith("mailto:"):
            continue
        name, _, anchor = target.partition("#")
        path = (page.parent / name).resolve() if name else page
        assert path.exists(), f"{page.name}: {target}"
        if anchor and path.suffix == ".md":
            assert anchor in {slug(h) for h in headings(path)}, f"{page.name}: #{anchor} is not a heading of {path.name}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_toml_block_parses_and_complete_runs_load(page, scratch):
    for block in blocks(page, "toml"):
        data = tomllib.loads(block)                    # raises on a bad block
        run = data.get("run", {})
        complete = {"name", "project", "configuration"} <= set(run) and isinstance(run.get(run["configuration"]), dict)
        if complete:                                     # a whole run TOML, not a fragment of one
            config.parse(data, scratch / "example.toml")   # C1–C5 on the example itself


def test_every_key_the_loader_accepts_is_documented():
    """Every key of the schema (utils/Env/schema/run.toml, V55) is in the reference."""
    from runner import schema
    ref = reference()
    missing = [f"[{table}] {key}" for table in schema.TABLES for key in schema.keys(table) if f"`{key}`" not in ref]
    assert not missing, "not in 04/05: " + ", ".join(missing)


def test_the_editor_schema_is_current():
    """run.schema.json is generated from run.toml (`make schema`): it must say what run.toml says."""
    import json
    from runner import schema
    written = json.loads(schema.path().with_name("run.schema.json").read_text(encoding="utf-8"))
    assert written == json.loads(json.dumps(schema.json_schema())), "run `make schema`"


def test_every_style_key_is_documented():
    ref = text(NUMBERED["04"])

    def dotted(table: dict, at: str = "") -> list[str]:
        out = []
        for key, value in table.items():
            name = f"{at}.{key}" if at else key
            out += dotted(value, name) if isinstance(value, dict) else [name]
        return out

    keys = dotted(plot.base_style())
    missing = [k for k in keys if f"`{k}`" not in ref and f"`{k.rsplit('.', 1)[0]}.{k.rsplit('.', 1)[1]}`" not in ref
               and not (k.startswith("page.margins.") and "`page.margins.left`" in ref)]
    assert not missing, "base.toml keys not in 04 §12: " + ", ".join(missing)


def test_every_tool_folder_and_its_options_are_documented():
    tools_page = text(NUMBERED["05"])
    for name, folder in tools.folders().items():
        assert re.search(rf"^## \d+\. `{name}`", tools_page, re.M), f"05 has no section for {name}"
        for option in folder.spec.get("options", {}):
            assert f"`{option}`" in tools_page, f"05 does not document {name}'s option {option}"


# ── what the code cites ─────────────────────────────────────────────────────────────────────────

CODE = [p for top in ("utils", "modules", "tests", "configs") for p in (REPO / top).rglob("*")
        if p.is_file() and p.suffix in (".py", ".hh", ".cc", ".toml", ".sh", ".in", ".cmnd", ".yaml", ".sin", ".mg5")
        and "reference/legacy_run" not in str(p) and "/_" not in str(p.relative_to(REPO))]
CODE += [REPO / "Makefile", REPO / "utils" / "Env" / "hep", REPO / "utils" / "Env" / "run"]


def code_text() -> list[tuple[Path, str]]:
    out = []
    for path in CODE:
        try:
            out.append((path, path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return out


def test_every_cited_section_exists():
    long = re.compile(r"docs/(0[1-7])_[A-Za-z_]+\.md(?: §([0-9]+(?:\.[0-9]+)?))?")
    short = re.compile(r"(?<![\w/.§])(0[1-7]) §([0-9]+(?:\.[0-9]+)?)")
    bad = []
    for path, body in code_text():
        for m in long.finditer(body):
            page = NUMBERED.get(m.group(1))
            if page is None or not m.group(0).startswith(f"docs/{page.name}"):
                bad.append(f"{path.relative_to(REPO)}: {m.group(0)} (no such page)")
            elif m.group(2) and m.group(2) not in sections(page):
                bad.append(f"{path.relative_to(REPO)}: {m.group(0)}")
        for m in short.finditer(body):
            page = NUMBERED[m.group(1)]
            if m.group(2) not in sections(page):
                bad.append(f"{path.relative_to(REPO)}: {m.group(0)}")
    assert not bad, "citations of sections that do not exist:\n  " + "\n  ".join(bad)


def test_every_cited_id_is_in_the_record():
    record = text(NUMBERED["07"]) + text(NUMBERED["04"])     # C1–C13 are the reference's table
    known = set(re.findall(r"\*\*((?:V|L|F|R|C)\d+)\*\*", record)) | set(re.findall(r"\b(00/B\d+)\b", record))
    known |= set(re.findall(r"\| (D\d+|D-Q\d+) \|", record))
    cited = re.compile(r"(?<![\w/-])((?:V|L|F|R|C)\d{1,2}|00/B\d+|D\d{1,2})(?![\w.])")
    bad = []
    for path, body in code_text():
        if path.suffix in (".cmnd", ".yaml", ".sin", ".mg5", ".in"):   # cards: physics text, not citations
            continue
        for m in cited.finditer(body):
            ident = m.group(1)
            if ident in known:
                continue
            line = body[body.rfind("\n", 0, m.start()) + 1: body.find("\n", m.end())]
            if not re.search(r"(#|//|\"\"\"|'''|^\s*\S*\s*\"|hint|where)", line) and path.suffix != ".py":
                continue
            bad.append(f"{path.relative_to(REPO)}: {ident}: {line.strip()[:100]}")
    assert not bad, "ids the record does not have:\n  " + "\n  ".join(bad)


def test_the_rank_table_in_02_is_the_runners():
    """02 §3.1's table of modules and ranks is runner/__init__.py's RANKS, row for row."""
    from runner import RANKS
    section = text(NUMBERED["02"]).split("### 3.1 The runner", 1)[1].split("\n### ", 1)[0]
    rows = {m: int(r) for r, m in re.findall(r"^\| (\d) \| `(\w+)\.py` \|", section, re.M)}
    assert rows == RANKS

