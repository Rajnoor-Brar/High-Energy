"""Rendering a Sherpa card (P7-S03, 04 §4).

Sherpa's card is YAML, so "base plus overrides" is a deep merge, and the things worth pinning are the
ones a flat card never had to think about: a nested override that must not destroy its siblings, a
list that must replace rather than extend, and the keys the plan owns appearing exactly once.

Two of these tests exist because the real run failed on them first. `EVENT_OUTPUT` has to be relative
— Sherpa prepends `./` and an absolute path becomes `.//home/...` — and `MPI_PDF_SET` has to follow
`PDF_SET` or Sherpa falls back to a compiled default that is not installed and dies naming a PDF the
card never mentioned.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "utils" / "python"))

yaml = pytest.importorskip("yaml")

from hekit.adapters import sherpa                                        # noqa: E402
from hekit.errors import HepError                                        # noqa: E402

BASE = """
BEAM_SPECTRA: [Monochromatic, EPA]
EPA:
  Q2Max: 1.0
  Form_Factor: 1
PDF_LIBRARY: [LHAPDFSherpa, CJKSherpa]
PDF_SET: [NNPDF23_lo_as_0130_qed, CJKLLO]
ME_GENERATORS: [Comix]
SCALES: METS{H_T2/4}{H_T2/4}{H_T2/4}
"""


class Seeds:
    point = 4242


class Point:
    name = "p1"
    beams = (2212, 11)
    energies = (275.0, 18.0)
    events = 300
    settings: tuple = ()


def render(**extra) -> dict:
    text = sherpa.render_card(Point(), seeds=Seeds(), threads=1, base_text=BASE, **extra)
    return yaml.safe_load("\n".join(line for line in text.splitlines()
                                    if not line.startswith("#")))


# ── the merge ────────────────────────────────────────────────────────────────

def test_a_nested_override_keeps_its_siblings():
    """`EPA:Q2Max` must not take `Form_Factor` with it — that is what a *deep* merge means."""
    class WithOverride(Point):
        settings = (("EPA:Q2Max", 4.5, "[quantity.q2]"),)

    text = sherpa.render_card(WithOverride(), seeds=Seeds(), threads=1, base_text=BASE)
    document = yaml.safe_load("\n".join(l for l in text.splitlines() if not l.startswith("#")))
    assert document["EPA"] == {"Q2Max": 4.5, "Form_Factor": 1}


def test_a_dotted_path_works_too():
    class WithOverride(Point):
        settings = (("EPA.Q2Max", 2.0, "[quantity.q2]"),)

    text = sherpa.render_card(WithOverride(), seeds=Seeds(), threads=1, base_text=BASE)
    document = yaml.safe_load("\n".join(l for l in text.splitlines() if not l.startswith("#")))
    assert document["EPA"]["Q2Max"] == 2.0


def test_a_list_replaces_rather_than_extends():
    """Sherpa's lists are positional — one entry per beam — so appending would mean something else."""
    merged = sherpa.merge({"PDF_SET": ["a", "b"]}, {"PDF_SET": ["c", "d"]})
    assert merged["PDF_SET"] == ["c", "d"]


def test_the_base_is_not_mutated():
    document = yaml.safe_load(BASE)
    before = dict(document["EPA"])
    sherpa.merge(document, {"EPA": {"Q2Max": 9.0}})
    assert document["EPA"] == before


# ── what the plan owns ───────────────────────────────────────────────────────

def test_the_plan_writes_the_beams_and_the_run_control():
    document = render()
    assert document["BEAMS"] == [2212, 11]
    assert document["BEAM_ENERGIES"] == [275.0, 18.0]
    assert document["RANDOM_SEED"] == 4242
    assert document["EVENTS"] == 300


def test_a_scalar_sqrt_s_is_split_between_the_beams():
    class Symmetric(Point):
        energies = (200.0,)

    text = sherpa.render_card(Symmetric(), seeds=Seeds(), threads=1, base_text=BASE)
    document = yaml.safe_load("\n".join(l for l in text.splitlines() if not l.startswith("#")))
    assert document["BEAM_ENERGIES"] == [100.0, 100.0]


def test_a_base_card_may_not_set_the_beams():
    with pytest.raises(HepError) as raised:
        sherpa.check_card("BEAMS: [2212, 11]\n", "base.yaml")
    assert "the plan owns" in str(raised.value)


def test_a_quantity_may_not_set_the_seed():
    class Bad(Point):
        settings = (("RANDOM_SEED", 7, "[quantity.s]"),)

    with pytest.raises(HepError) as raised:
        sherpa.check_overrides(Bad(), "eic.toml")
    assert "the plan owns" in str(raised.value)


def test_an_ordinary_nested_key_is_fine():
    sherpa.check_card("EPA:\n  Q2Max: 1.0\n", "base.yaml")


# ── the two that the first real run found ────────────────────────────────────

def test_the_event_output_is_relative_to_the_working_directory():
    """Sherpa prepends `./`, so an absolute path becomes `.//home/...` and cannot be opened."""
    document = render(fifo="/results/proj/points/p1/events.hepmc")
    assert document["EVENT_OUTPUT"] == "HepMC3_GenEvent[events.hepmc]"
    assert "/" not in document["EVENT_OUTPUT"].split("[")[1]


def test_the_event_output_keeps_the_whole_name():
    """`HepMC3_GenEvent[events]` writes a file called `events` — measured. The FIFO is not that."""
    document = render(fifo="/tmp/x/events.hepmc")
    assert "events.hepmc" in document["EVENT_OUTPUT"]


def test_the_mpi_pdf_follows_the_hard_process_pdf():
    """Otherwise Sherpa falls back to a compiled default that is not installed, and dies."""
    document = render()
    assert document["MPI_PDF_SET"] == document["PDF_SET"]
    assert document["MPI_PDF_LIBRARY"] == document["PDF_LIBRARY"]


def test_a_card_that_chose_its_own_mpi_pdf_is_left_alone():
    """A different PDF for the MPI is a physics choice; this is a safety net, not an opinion."""
    text = BASE + "MPI_PDF_SET: [CT14lo, CJKLLO]\n"
    rendered = sherpa.render_card(Point(), seeds=Seeds(), threads=1, base_text=text)
    document = yaml.safe_load("\n".join(l for l in rendered.splitlines()
                                        if not l.startswith("#")))
    assert document["MPI_PDF_SET"] == ["CT14lo", "CJKLLO"]


# ── native mode ──────────────────────────────────────────────────────────────

def test_native_mode_asks_sherpa_to_run_rivet():
    document = render(mode="native", analyses=["photo_eic"], fifo="/tmp/x/events.hepmc")
    assert document["ANALYSIS"] == "Rivet"
    assert document["RIVET"]["--analyses"] == ["photo_eic"]
    assert document["ANALYSIS_OUTPUT"] == "analysis"
    assert "EVENT_OUTPUT" not in document, "no FIFO when nothing is reading it"


def test_inprocess_mode_does_not_ask_for_rivet():
    document = render(fifo="/tmp/x/events.hepmc")
    assert "ANALYSIS" not in document
    assert document["EVENT_OUTPUT"].startswith("HepMC3_GenEvent[")


# ── the identity hash ────────────────────────────────────────────────────────

def test_card_defaults_flattens_the_tree():
    found = sherpa.card_defaults(BASE)
    assert found["epa:q2max"] == "1.0"
    assert found["pdf_set"] == "NNPDF23_lo_as_0130_qed, CJKLLO"


def test_a_value_yaml_cannot_type_is_still_read():
    """`METS{H_T2/4}` has braces in it; the card must survive being parsed."""
    assert "scales" in sherpa.card_defaults(BASE)


def test_an_invalid_card_says_so():
    with pytest.raises(HepError) as raised:
        sherpa.card_defaults("BEAMS: [1, 2\nEPA: {\n")
    assert "not valid YAML" in str(raised.value)


def test_a_card_that_is_not_a_mapping_is_refused():
    with pytest.raises(HepError):
        sherpa.card_defaults("- just\n- a list\n")


# ── stages ───────────────────────────────────────────────────────────────────

class Config:
    project = "proj"

    class generator:
        tool = "sherpa"
        card = "base.yaml"

    class run:
        events = 300
        name = "sh"

    class rivet:
        mode = "inprocess"
        paths: tuple = ()

    class output:
        root = ""
        tag_style = "tag"

    path = Path("/tmp/eic.toml")
    tools: dict = {}


class Group:
    name = "sh_18x275"
    card = BASE


def test_the_prepare_stage_integrates_into_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sherpa, "executable", lambda config=None: "Sherpa")
    stages = sherpa.prepare(Config(), Group(), tmp_path / "cache")
    assert len(stages) == 1
    stage = stages[0]
    assert stage.role == "prepare"
    assert "-e" in stage.argv and "0" in stage.argv, "integration generates no events"
    assert any(entry.startswith("RESULT_DIRECTORY:") for entry in stage.argv)
    # Without this the integration opens the FIFO at start-up and waits for a reader for ever.
    assert "EVENT_OUTPUT: None" in stage.argv
    assert stage.cwd == tmp_path / "cache"
    assert stage.produces == [tmp_path / "cache" / "Results.zip"]


def test_the_prepare_stage_is_what_the_planner_shows(tmp_path, monkeypatch):
    monkeypatch.setattr(sherpa, "executable", lambda config=None: "Sherpa")
    plan_stage = sherpa.prepare(Config(), Group(), tmp_path / "cache")[0].to_plan_stage()
    assert plan_stage.role == "prepare"
    assert plan_stage.cwd == str(tmp_path / "cache"), "a stage's directory survives the plan"
