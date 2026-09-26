"""Rendering MadGraph's cards and stages (P7-S05, 04 §7).

MadGraph is the adapter that does not hand over events. It hands over a *matrix element*, and Pythia
showers it inside `hep-run` — so the card this adapter renders is a **Pythia** card, the beams go into
a launch script rather than into it, and its stages may not overlap, because a file has to be finished
before anything reads it.

The tests that matter most are the ones about which text goes where: the proc card is what gets built
and what the cache is keyed on, while the rendered card is a five-line Pythia card that mentions no
processes at all. Confusing the two silently built nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "utils" / "python"))

from hekit.adapters import madgraph                                      # noqa: E402
from hekit.errors import HepError                                        # noqa: E402

PROC = """# a proc card
generate e+ e- > mu+ mu-
"""


class Seeds:
    point = 4242


class Point:
    name = "mg_91"
    beams = (11, -11)
    energies = (45.6, 45.6)
    events = 100
    settings: tuple = ()


class Config:
    project = "proj"

    class generator:
        tool = "madgraph"
        card = "proc.dat"
        shower = "shower.cmnd"

    class run:
        events = 100
        name = "mg"

    class rivet:
        mode = "inprocess"
        paths: tuple = ()

    class output:
        root = ""
        tag_style = "tag"

    path = Path("/tmp/mg.toml")
    tools: dict = {}


class Group:
    name = "mg_91"
    card = "Beams:frameType = 4\n"        # the *rendered* card: a Pythia shower card
    base_card = PROC                      # the *proc* card: what is actually built


# ── which text is which ──────────────────────────────────────────────────────

def test_the_cache_keys_on_the_proc_card():
    """Not on the rendered card, which says nothing about the processes."""
    assert madgraph.cache_text(Group()) == PROC


def test_the_prepare_stage_writes_the_proc_card(tmp_path, monkeypatch):
    """It wrote the Pythia shower card once, and MadGraph found no `generate` line at all."""
    monkeypatch.setattr(madgraph, "executable", lambda config=None: "mg5_aMC")
    stage = madgraph.prepare(Config(), Group(), tmp_path / "cache")[0]
    (path, text), = stage.writes
    assert "generate e+ e- > mu+ mu-" in text
    assert "Beams:frameType" not in text
    assert text.rstrip().endswith(f"output {tmp_path / 'cache' / 'process'}")
    assert stage.phase == 0 and stage.cwd == tmp_path / "cache"


def test_the_rendered_card_is_a_pythia_card():
    text = madgraph.render_card(Point(), seeds=Seeds(), threads=1, lhe="/results/mg_91/events.lhe")
    assert "Beams:frameType = 4" in text
    assert "Beams:LHEF = /results/mg_91/events.lhe" in text
    # The LHE header fixes the beams; a card that repeated them would be a second, ignored opinion.
    assert "Beams:idA" not in text and "Beams:eA" not in text


# ── the launch script (04 §7) ────────────────────────────────────────────────

def test_the_launch_script_carries_the_run_control():
    text = madgraph.launch_script(Point(), seeds=Seeds(), process_dir=Path("/cache/process"))
    assert "launch /cache/process" in text
    assert "set nevents 100" in text
    assert "set iseed 4242" in text
    assert "shower=OFF" in text, "Pythia showers in hep-run, not here"


def test_beam_ids_become_lpp_and_energies_ebeam():
    text = madgraph.launch_script(Point(), seeds=Seeds(), process_dir=Path("/c"))
    assert "set lpp1 0" in text and "set lpp2 0" in text          # leptons
    assert "set ebeam1 45.6" in text and "set ebeam2 45.6" in text


def test_a_proton_beam_is_lpp_one():
    class Protons(Point):
        beams = (2212, -2212)

    text = madgraph.launch_script(Protons(), seeds=Seeds(), process_dir=Path("/c"))
    assert "set lpp1 1" in text and "set lpp2 -1" in text


def test_a_scalar_energy_is_split_between_the_beams():
    class Symmetric(Point):
        energies = (91.2,)

    text = madgraph.launch_script(Symmetric(), seeds=Seeds(), process_dir=Path("/c"))
    assert "set ebeam1 45.6" in text and "set ebeam2 45.6" in text


def test_an_id_with_no_beam_type_is_a_planning_error():
    with pytest.raises(HepError) as raised:
        madgraph.lpp_for(22)
    assert "no MadGraph beam type" in str(raised.value)


def test_a_run_card_override_reaches_the_launch_script():
    class WithCut(Point):
        settings = (("run_card.ptj", 20, "[quantity.ptj]"),)

    text = madgraph.launch_script(WithCut(), seeds=Seeds(), process_dir=Path("/c"))
    assert "set ptj 20" in text
    assert "[quantity.ptj]" in text


def test_a_quantity_may_not_set_what_the_plan_owns():
    for key in ("run_card.nevents", "iseed", "run_card.ebeam1"):
        class Bad(Point):
            settings = ((key, 1, "[quantity.x]"),)

        with pytest.raises(HepError):
            madgraph.check_overrides(Bad(), "eic.toml")


# ── the proc card's own rules ────────────────────────────────────────────────

def test_a_proc_card_may_not_output_or_launch():
    for line in ("output /somewhere\n", "launch\n"):
        with pytest.raises(HepError) as raised:
            madgraph.check_card(PROC + line, "proc.dat")
        assert "hep writes those" in str(raised.value)


def test_a_proc_card_with_no_process_is_refused():
    with pytest.raises(HepError) as raised:
        madgraph.check_card("# nothing here\n", "proc.dat")
    assert "generates no process" in str(raised.value)


def test_the_processes_are_what_the_identity_sees():
    found = madgraph.card_defaults(PROC)
    assert found["process:0"] == "e+ e- > mu+ mu-"


def test_a_multi_jet_card_warns_about_merging():
    """Out of scope to validate; cheap to notice that nobody set any (04 §7)."""
    multi = "generate p p > w+ j\nadd process p p > w+ j j\n"
    assert "merging" in madgraph.merging_warning(multi)
    assert madgraph.merging_warning(PROC) == ""


# ── the stages may not overlap ───────────────────────────────────────────────

def test_the_stages_run_one_after_another(tmp_path, monkeypatch):
    """A file has to be finished before anything reads it, unlike a FIFO's two ends."""
    monkeypatch.setattr(madgraph, "executable", lambda config=None: "mg5_aMC")
    from hekit.adapters import cache as cache_module
    from hekit.env import paths

    monkeypatch.setattr(paths, "results_root", lambda: tmp_path / "results")
    stages = madgraph.stages(Config(), Group(), tmp_path / "point" / "events.hepmc")
    assert [stage.name for stage in stages] == ["madgraph-launch", "madgraph-unpack"]
    assert [stage.phase for stage in stages] == [1, 2]
    assert madgraph.prepare(Config(), Group(), tmp_path / "c")[0].phase == 0


def test_the_adapter_says_it_does_not_stream():
    """Which is what keeps `hep-run` in a later phase, and stops a FIFO being made for nothing."""
    assert madgraph.STREAMS is False


def test_the_unpack_stage_decompresses_into_the_point(tmp_path, monkeypatch):
    """Pythia's gzip support is build-dependent (01 §4), and the card cannot name a cache path."""
    monkeypatch.setattr(madgraph, "executable", lambda config=None: "mg5_aMC")
    from hekit.env import paths

    monkeypatch.setattr(paths, "results_root", lambda: tmp_path / "results")
    stage = madgraph.unpack(Config(), Group(), tmp_path / "point" / "events.hepmc")
    assert stage.argv[0] == "sh", "a redirect needs a shell"
    assert any(str(entry).endswith(".lhe.gz") for entry in stage.argv)
    assert stage.produces == [madgraph.lhe_path(Config(), Group())]
    assert stage.produces[0].name == "events.lhe"
