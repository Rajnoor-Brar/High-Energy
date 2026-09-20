"""The docs describe the system that exists (P10-S02).

Documentation rots in two ways, and both are checkable, so neither has to be caught by a reader:

* **a link points at nothing.** Every relative link in `docs/**` is resolved against the file it is
  written in — including `#anchors`, which are checked against the headings of the target file,
  because a link to a section that was renamed is exactly as broken as one to a missing file and
  much harder to notice;
* **a command is documented that does not exist**, or exists and is not documented. Both directions
  matter: the first sends a reader to type something that fails, and the second means a command
  nobody can find.

`legacy/` is excluded from everything here. It is frozen by design and describes code that no longer
runs; holding it to the current system's links would be asking it to lie.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "utils" / "python"))

from hekit.cli import COMMANDS                                           # noqa: E402

DOCS = REPO / "docs"

#: `[text](target)`, with the target captured. Skips images and bare autolinks.
LINK = re.compile(r"(?<!!)\[[^\]^]*?\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^#+\s+(.*?)\s*$", re.MULTILINE)


def documents() -> list[Path]:
    return sorted(path for path in DOCS.rglob("*.md") if "legacy" not in path.parts)


def anchor_of(heading: str) -> str:
    """GitHub's slug: lowercase, punctuation dropped, spaces to hyphens."""
    text = heading.strip().lower()
    text = re.sub(r"[`*_~]", "", text)
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text).strip("-")


def anchors_in(path: Path) -> set[str]:
    return {anchor_of(heading) for heading in HEADING.findall(path.read_text(encoding="utf-8"))}


# ── Verification row: links ──────────────────────────────────────────────────

def test_every_relative_link_resolves():
    broken: list[str] = []
    for document in documents():
        text = document.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, _, anchor = target.partition("#")
            if not path_part:                       # a link within this document
                if anchor and anchor not in anchors_in(document):
                    broken.append(f"{document.relative_to(REPO)} → #{anchor}")
                continue
            destination = (document.parent / path_part).resolve()
            if not destination.exists():
                broken.append(f"{document.relative_to(REPO)} → {target}")
            elif anchor and destination.suffix == ".md" and anchor not in anchors_in(destination):
                broken.append(f"{document.relative_to(REPO)} → {target} (no such heading)")
    assert not broken, "broken links:\n  " + "\n  ".join(broken)


def test_the_docs_do_not_point_into_legacy_for_current_behaviour():
    """`legacy/` may be *named*, but the guide and the map must not send a reader there to learn
    how the system works."""
    for name in ("GUIDE.md", "MAP.md"):
        text = (DOCS / name).read_text(encoding="utf-8")
        for target in LINK.findall(text):
            assert not target.startswith("../legacy/"), f"{name} links into legacy/: {target}"


# ── Verification row: commands ───────────────────────────────────────────────

def documented_commands(path: Path) -> set[str]:
    """`hep <name>` as it appears in a document."""
    text = path.read_text(encoding="utf-8")
    return {name for name in re.findall(r"\bhep\s+([a-z][a-z-]*)", text) if name in COMMANDS}


def test_every_command_is_documented():
    """A command nobody can find is one nobody uses."""
    covered = documented_commands(DOCS / "GUIDE.md") | documented_commands(DOCS / "MAP.md") \
        | documented_commands(REPO / "docs" / "rework" / "08_CLI.md")
    missing = sorted(set(COMMANDS) - covered)
    assert not missing, f"undocumented commands: {', '.join(missing)}"


def test_every_documented_command_exists():
    """The other direction: a reader must not be told to type something that fails."""
    for name in ("GUIDE.md", "MAP.md"):
        path = DOCS / name
        text = path.read_text(encoding="utf-8")
        # Anything spelled `hep <word>` should be a real command, not a plausible invention.
        for candidate in re.findall(r"`hep\s+([a-z][a-z-]*)", text):
            assert candidate in COMMANDS, f"{name} mentions `hep {candidate}`, which does not exist"


def test_the_guide_and_map_exist_and_are_not_stubs():
    for name in ("GUIDE.md", "MAP.md"):
        text = (DOCS / name).read_text(encoding="utf-8")
        assert len(text) > 2000, f"{name} is a stub"
        assert "TODO" not in text and "TBD" not in text, f"{name} still has placeholders"


def test_the_namespaces_the_map_lists_are_the_ones_that_exist():
    """The map's table of C++ namespaces against the facade headers on disk."""
    text = (DOCS / "MAP.md").read_text(encoding="utf-8")
    on_disk = {path.stem for path in (REPO / "utils").glob("*.hh")}
    for namespace in on_disk:
        assert f"`{namespace}`" in text, f"{namespace} is not in MAP.md"


def test_the_config_reference_is_committed_and_current():
    """The generated reference is part of the docs, so it must not drift from the schema."""
    from hekit.config.reference import markdown

    committed = REPO / "docs" / "rework" / "reference" / "config.md"
    assert committed.is_file()
    assert committed.read_text(encoding="utf-8") == markdown(), \
        "run: hep config reference --write docs/rework/reference/config.md"
