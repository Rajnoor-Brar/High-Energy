"""runner/deck.py's build (docs/reporter/D3_Build.md, V104): composites, deck.md through pandoc to every
target, the viewer, --init. Panels are PDFs and PNGs made by PIL in a tmp_path results tree."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from runner import cli, deck
from runner.errors import HepError

TOOLS = all(shutil.which(t) for t in ("pdflatex", "pdftoppm", "pdfinfo"))
needs_tools = pytest.mark.skipif(not TOOLS, reason="pdflatex and poppler draw the composites")
needs_pandoc = pytest.mark.skipif(not (TOOLS and shutil.which("pandoc")), reason="pandoc makes the slides")

TALK = """---
title: A test talk
---

# Statistics

## Event count
![](zeus-d01)

## Two of them, beside words
:::: columns
::: column
- tails settle
:::
::: column
![](zeus-d01){panels="10M 50M" size=half}
:::
::::
"""


def plot(path: Path, colour: str) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (336, 303), colour).save(path, "PDF", resolution=72)
    return path


@pytest.fixture()
def talk(tmp_path, monkeypatch):
    """A deck over two result folders of P/zeus, each with a drawn page d01."""
    results = tmp_path / "results"
    monkeypatch.setenv("HEKIT_RESULTS", str(results))
    monkeypatch.setenv("HEKIT_OUTPUT", str(tmp_path / "output"))
    for folder, colour in (("01_PDFs_010M", "lightblue"), ("01_PDFs_050M", "lightgreen")):
        plot(results / "P" / "zeus" / folder / "plots" / "root" / "d01-x01-y01.pdf", colour)
    folder = tmp_path / "talk"
    folder.mkdir()
    (folder / "deck.toml").write_text('[blocks.zeus]\nfrom = "P/zeus"\nfolders = ["01_PDFs_*"]\npages = ["d01-*"]\n')
    return folder


def pages(pdf: Path) -> int:
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    return int(info.split("Pages:")[1].split()[0])


@needs_pandoc
def test_a_deck_builds_every_target_and_leaves_deck_md(talk):
    (talk / "deck.md").write_text(TALK)
    before = (talk / "deck.md").read_bytes()
    made = deck.load(str(talk))
    deck.gather(made)
    said = []
    out = deck.build(made, say=said.append)
    assert [p.name for p in out] == ["deck.pdf", "overleaf.zip", "deck.pptx", "deck.html", "index.html"]
    assert "deck: 2 composite(s), 2 drawn" in said[0]                          # the block's, and its half variant
    assert pages(talk / "deck.pdf") == 4                                         # title, section, two slides
    with zipfile.ZipFile(talk / "deck.pptx") as pptx:
        names = pptx.namelist()
        assert "ppt/slides/slide4.xml" in names and any(n.startswith("ppt/media/") for n in names)
        assert 'cx="9144000" cy="5143500"' in pptx.read("ppt/presentation.xml").decode()   # 16:9
    html = (talk / "deck.html").read_text()
    assert "http://" not in html and "https://" not in html and html.count("data:image/png;base64") >= 2
    with zipfile.ZipFile(talk / "overleaf.zip") as bundle:
        names = bundle.namelist()
        assert "deck.tex" in names and "figures/zeus-d01.pdf" in names
        assert "figures/zeus-d01.pdf" in bundle.read("deck.tex").decode()
    built = (talk / "build" / "deck.vector.md").read_text()
    assert "![](figures/zeus-d01.pdf)" in built and "panels=" not in built   # our attributes are taken out
    assert (talk / "deck.md").read_bytes() == before
    said.clear()
    deck.build(deck.load(str(talk)), ["pdf"], said.append)
    assert "deck: 2 composite(s), 0 drawn" in said[0]                          # nothing changed: nothing redrawn


@needs_tools
def test_the_viewer_needs_no_pandoc_and_slides_without_deck_md(talk, monkeypatch):
    made = deck.load(str(talk))
    deck.gather(made)
    assert "## zeus d01" in deck.talk(made).text and "# zeus" in deck.talk(made).text   # a section per table
    real = shutil.which
    monkeypatch.setattr(deck.shutil, "which", lambda name: None if name == "pandoc" else real(name))
    index = deck.build(made, ["viewer"], lambda _: None)
    assert [p.name for p in index] == ["index.html"]
    text = index[0].read_text()
    assert 'href="figures/zeus-d01.pdf"' in text and "panels/zeus-d01/01_10M.pdf" in text
    with pytest.raises(HepError, match="pandoc, which is not on PATH"):
        deck.build(made, ["pdf"], lambda _: None)


@needs_tools
def test_references_name_blocks_and_panels(talk):
    made = deck.load(str(talk))
    (talk / "deck.md").write_text("## x\n![](zeus-d1)\n")
    with pytest.raises(HepError, match="no block zeus-d1") as refused:
        deck.talk(made)
    assert "zeus-d01" in refused.value.hint
    (talk / "deck.md").write_text('## x\n![](zeus-d01){panels="10M 100M"}\n')
    with pytest.raises(HepError, match="zeus-d01 has no panel '100M'"):
        deck.talk(made)
    (talk / "deck.md").write_text("## x\n![](zeus-d01){size=huge}\n")
    with pytest.raises(HepError, match="size must be one of"):
        deck.talk(made)
    (talk / "deck.md").write_text("## x\n![](extras/photo.png){width=50%}\n")
    assert deck.talk(made).references[0][1] is None                            # a path is passed as it is


def test_init_writes_deck_md_once(talk, monkeypatch, capsys):
    monkeypatch.setenv("HEKIT_REPORTS", str(talk.parent))
    assert cli.main(["deck", talk.name, "--init"]) == 0
    assert "![](zeus-d01)" in (talk / "deck.md").read_text()
    assert cli.main(["deck", talk.name, "--init"]) == 2                          # there already: refused
    assert "is there already" in capsys.readouterr().err
    loose = talk.parent / "loose"
    loose.mkdir()
    plot(loose / "eta_algorithms.pdf", "white")
    assert cli.main(["deck", "loose", "--init"]) == 0
    assert (loose / "deck.toml").read_text().startswith("# deck.toml") and (loose / "deck.md").is_file()
    assert cli.main(["deck", talk.name, "--only", "slides"]) == 2
