"""runner/deck.py (docs/reporter/D2_Collect.md, V103): a deck's blocks from result folders (deck.toml) or from its
folder's own files, labelled and copied into panels/. Every tree here is tmp_path's: HEKIT_RESULTS,
HEKIT_OUTPUT and the deck folder."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from runner import cli, deck
from runner.errors import HepError

YODA = """BEGIN YODA_COUNTER_V3 /RAW/_EVTCOUNT
Path: /RAW/_EVTCOUNT
Title: ~
Type: Counter
---
# sumW       	sumW2        	numEntries
{n:e} 	{n:e} 	{n:e}
END YODA_COUNTER_V3
"""


@pytest.fixture()
def trees(tmp_path, monkeypatch):
    """results/P/zeus/ with three result folders, each with drawn pages and a point's YODA; one of them
    has its provenance in output/. Returns (the deck's folder, the run's results folder)."""
    results, output = tmp_path / "results", tmp_path / "output"
    monkeypatch.setenv("HEKIT_RESULTS", str(results))
    monkeypatch.setenv("HEKIT_OUTPUT", str(output))
    run = results / "P" / "zeus"
    for folder, n in (("01_PDFs_010M", 9_999_062), ("02_seeds", 24_998_000), ("03_PDFs_150M", 149_998_000)):
        for backend, pages in (("root", ("d01-x01-y01", "d02-x01-y01")), ("mpl", ("d01-x01-y01", "d02-x01-y01", "d09-x01-y01"))):
            plots = run / folder / "plots" / backend
            plots.mkdir(parents=True, exist_ok=True)
            for name in pages:
                (plots / f"{name}.pdf").write_bytes(f"%PDF {folder} {backend} {name}".encode())
        (run / folder / "plots" / "root" / "sheets").mkdir()
        (run / folder / "plots" / "root" / "sheets" / "grid.pdf").write_bytes(b"%PDF sheet")
        (run / folder / "MSTW08lo").mkdir()
        (run / folder / "MSTW08lo" / "zeus.yoda").write_text(YODA.format(n=n))
    point = output / "P" / "zeus" / "03_PDFs_150M" / "MSTW08lo"
    point.mkdir(parents=True)
    (point / "provenance.json").write_text(json.dumps({"events": 150_000_000}))
    folder = tmp_path / "talk"
    (folder / "extras").mkdir(parents=True)
    for short in ("d01", "d02"):
        (folder / "extras" / f"zeus_{short}_AB.png").write_bytes(b"\x89PNG fake")
    return folder, run


def recipe(folder: Path, text: str) -> Path:
    (folder / "deck.toml").write_text(text)
    return folder


ZEUS = '''
[blocks.zeus]
from = "P/zeus"
folders = ["01_PDFs_010M", "02_seeds", "03_PDFs_150M"]
pages = ["d0[12]-*"]
'''


def test_counts_are_written_as_people_say_them():
    assert [deck.count(n) for n in (9_999_062, 24_998_000, 149_998_000, 980_000, 1234, 1e9, 7)] == \
        ["10M", "25M", "150M", "980k", "1.2k", "1G", "7"]
    assert sorted(["150M", "10M", "1M", "d10", "d2"], key=deck.natural) == ["1M", "10M", "150M", "d2", "d10"]


def test_a_recipe_block_per_page_with_a_panel_per_folder(trees):
    folder, run = trees
    made = deck.load(str(recipe(folder, ZEUS + 'extra = "extras/zeus_{short}_AB.png"\ntitle = "ZEUS {short}"\n')))
    assert made.recipe and [b.name for b in made.blocks] == ["zeus-d01", "zeus-d02"]
    first = made.blocks[0]
    assert first.title == "ZEUS d01" and first.size == "full" and first.labels and not first.titles
    # asked for: the name's count (01_PDFs_010M), the provenance (03_PDFs_150M); else the YODA's count (02_seeds)
    assert [p.label for p in first.panels] == ["10M", "25M", "150M", "AB"]
    assert first.panels[0].source == run / "01_PDFs_010M" / "plots" / "root" / "d01-x01-y01.pdf"
    assert first.panels[-1].origin == "extras/zeus_d01_AB.png"
    named = deck.load(str(recipe(folder, ZEUS + 'label = "folder"\n')))
    assert [p.label for p in named.blocks[0].panels] == ["PDFs_010M", "seeds", "PDFs_150M"]


def test_a_block_takes_pages_from_the_backends_it_prefers(trees):
    folder, run = trees
    with pytest.raises(HepError, match="pages: 'd09-\\*' names no page drawn in plots/root/") as refused:
        deck.load(str(recipe(folder, ZEUS.replace('"d0[12]-*"', '"d09-*"'))))
    assert refused.value.hint == 'mpl drew it there: backend = ["root", "mpl"]'
    made = deck.load(str(recipe(folder, ZEUS.replace('"d0[12]-*"', '"d09-*"') + 'backend = ["root", "mpl"]\n')))
    assert made.blocks[0].panels[0].origin == "01_PDFs_010M/plots/mpl/d09-x01-y01"
    # one folder's Paint pages are missing (as the user's 03_PDFs_150M): it is refused, then taken from mpl
    (run / "03_PDFs_150M" / "plots" / "root" / "d01-x01-y01.pdf").unlink()
    with pytest.raises(HepError, match="03_PDFs_150M has no page d01-x01-y01 in plots/root/") as refused:
        deck.load(str(recipe(folder, ZEUS)))
    assert refused.value.hint == 'mpl drew it there: backend = ["root", "mpl"]'
    mixed = deck.load(str(recipe(folder, ZEUS + 'backend = ["root", "mpl"]\n'))).blocks[0].panels
    assert [p.origin.split("/")[2] for p in mixed] == ["root", "root", "mpl"]


def test_collecting_copies_once_and_removes_what_is_gone(trees):
    folder, run = trees
    made = deck.load(str(recipe(folder, ZEUS + 'extra = "extras/zeus_{short}_AB.png"\n')))
    assert deck.gather(made) == 6                                   # 2 blocks × 3 folders; the extras stay put
    copied = folder / "panels" / "zeus-d01" / "01_10M.pdf"
    assert copied.read_bytes() == b"%PDF 01_PDFs_010M root d01-x01-y01"
    assert made.blocks[0].panels[0].file == copied and made.blocks[0].panels[-1].file == folder / "extras" / "zeus_d01_AB.png"
    assert deck.gather(deck.load(str(folder))) == 0
    (run / "01_PDFs_010M" / "plots" / "root" / "d01-x01-y01.pdf").write_bytes(b"%PDF redrawn")
    assert deck.gather(deck.load(str(folder))) == 1 and copied.read_bytes() == b"%PDF redrawn"
    recipe(folder, ZEUS.replace('"d0[12]-*"', '"d01-*"'))
    deck.gather(deck.load(str(folder)))
    assert not (folder / "panels" / "zeus-d02").exists()


@pytest.mark.parametrize("text, message", [
    (ZEUS + "folder = []\n", "unknown key 'folder'"),
    ('[blocks.zeus]\nfrom = "P/zeus"\npages = ["d01*"]\n', "'folders' is required"),
    (ZEUS.replace("02_seeds", "02_seed"), "no result folder 02_seed"),
    (ZEUS.replace('"P/zeus"', '"P/zues"'), "no results for P/zues"),
    (ZEUS.replace('"P/zeus"', '"zeus"'), 'is not "<Project>/<run>"'),
    (ZEUS.replace('"d0[12]-*"', '"d07*"'), "pages: 'd07\\*' names no page"),
    (ZEUS.replace('"02_seeds", ', '"02_seeds", "02_*", ') + 'label = "folder"\n', None),
    (ZEUS + 'extra = "extras/{nope}.png"\n', "extra 'extras/\\{nope\\}.png' cannot be filled"),
    (ZEUS + 'extra = "extras/missing_{short}.png"\n', "no file extras/missing_d01.png"),
    ("[deck]\nsize = \"huge\"\n" + ZEUS, "size must be one of full, half, a4, square"),
    ("[decks]\n" + ZEUS, "unknown table \\[decks\\]"),
])
def test_mistakes_are_refused(trees, text, message):
    folder, _ = trees
    if message is None:                                    # a glob naming a folder already listed: taken once
        assert len(deck.load(str(recipe(folder, text))).blocks[0].panels) == 3
        return
    with pytest.raises(HepError, match=message):
        deck.load(str(recipe(folder, text)))


def test_two_folders_with_one_label_are_refused(trees):
    folder, run = trees
    shutil.copytree(run / "01_PDFs_010M", run / "04_PDFs_010M")            # a rerun of the same count
    with pytest.raises(HepError, match="01_PDFs_010M and 04_PDFs_010M are both labelled 10M"):
        deck.load(str(recipe(folder, ZEUS.replace('"02_seeds", "03_PDFs_150M"', '"04_PDFs_010M"'))))


def test_folder_mode_groups_files_by_name(tmp_path):
    folder = tmp_path / "batch"
    folder.mkdir()
    for name in ("zeus_d01_PDFs_010M.pdf", "zeus_d01_PDFs_150M.pdf", "zeus_d01_PDFs_025M.pdf", "zeus_d01_PDFs_AB.png",
                 "eta_algorithms.pdf", "eta_algorithmsAB.png", "deck.pdf", "notes.txt"):
        (folder / name).write_bytes(b"x")
    made = deck.load(str(folder))
    assert not made.recipe and [b.name for b in made.blocks] == ["eta", "zeus_d01_PDFs"]
    eta, zeus = made.blocks
    assert [p.label for p in zeus.panels] == ["10M events", "25M events", "150M events", "AB"]
    assert [p.label for p in eta.panels] == ["algorithms", "algorithmsAB"] and zeus.title == "zeus d01 PDFs"
    assert deck.gather(made) == 0 and not (folder / "panels").exists()          # nothing to copy: it is all here
    recipe(folder, "[deck]\ngroup = '^(?P<block>[a-z]+)_(?P<panel>.+)$'\n")
    assert [b.name for b in deck.load(str(folder)).blocks] == ["eta", "zeus"]
    recipe(folder, "[deck]\ngroup = '^(?P<name>.+)$'\n")
    with pytest.raises(HepError, match="group needs a block group"):
        deck.load(str(folder))


def test_hep_deck_list_writes_nothing(trees, capsys, monkeypatch):
    folder, _ = trees
    recipe(folder, ZEUS)
    monkeypatch.setenv("HEKIT_REPORTS", str(folder.parent))
    assert cli.main(["deck", folder.name, "--list"]) == 0
    out = capsys.readouterr().out
    assert "zeus-d01  \"zeus d01\"  3 panel(s), full, columns auto" in out and "150M  03_PDFs_150M/plots/root/d01-x01-y01" in out
    assert not (folder / "panels").exists()
    assert cli.main(["deck", "nowhere", "--list"]) == 2
