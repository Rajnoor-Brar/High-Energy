"""P4 S2's tool folders at plan time: Delphes, Sherpa and Herwig (no generator runs here).

render.py is tested with the runner's own Override (L26: a look-alike fake hid F1 in v1).
"""

from __future__ import annotations

import json
import shutil

import pytest

from runner import execute, tools
from runner.errors import HepError
from runner.quantities import Override

from helpers import plans

NEEDS = {"sherpa": shutil.which("Sherpa"), "herwig": shutil.which("Herwig"), "delphes": shutil.which("DelphesHepMC3")}


# ── Delphes (L11) ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not NEEDS["delphes"], reason="load_hep: DelphesHepMC3")
def test_delphes_reads_a_file_from_an_earlier_group_and_is_count_checked():
    [p] = plans("PhotoProduction/eic", "delphes")
    step = p.rendered["delphes"]
    assert step.argv[1:] == [str(step.card_combined), str(step.products[0][1]), str(p.interfaces["showered.hepmc"].path)]
    assert step.count_check[2] == "root:Delphes" and step.count_check[1] == p.rendered["pythia_file"].sidecar
    assert p.writes[step.card_combined].rstrip().endswith(f"set RandomSeed {p.seed}")


@pytest.mark.skipif(not NEEDS["delphes"], reason="load_hep: DelphesHepMC3")
def test_a_fifo_into_delphes_is_refused():
    with pytest.raises(HepError, match="'delphes' cannot read a FIFO"):
        plans("PhotoProduction/eic", "delphes", sets=["run.delphes.prelim.fifo=['showered.hepmc']",
                                                       "run.delphes.prelim.files=[]",
                                                       "run.delphes.tools=[['pythia_file', 'delphes'], 'jets_reco']"])


def test_the_root_count_reader_needs_the_file(scratch):
    assert execute.read_count(scratch / "missing.root", "root:Delphes") is None


# ── Sherpa (L12, L26) ─────────────────────────────────────────────────────────────────────────

def render():
    return tools.folders()["sherpa"].plugin


BASE = """PDF_LIBRARY: [LHAPDFSherpa, CJKSherpa]
PDF_SET: [NNPDF23_lo_as_0130_qed, CJKLLO]
MPI_PDF_SET: [NNPDF23_lo_as_0130_qed, CJKLLO]
EPA:
  Q2Max: 1.0
"""


def test_render_merges_the_overrides_into_the_whole_card():
    yaml = pytest.importorskip("yaml")
    text = render().card([BASE], [Override("PDF_SET[0]", "MSTW2008lo68cl", "[quantities.pdf] = MSTW08lo"),
                                  Override("BEAM_ENERGIES", [275, 18], "[quantities.energies] = 18x275"),
                                  Override("EPA:Q2Max", 2.0, "test")], {"tag": "sherpa"})
    card = yaml.safe_load(text)
    assert card["PDF_SET"] == ["MSTW2008lo68cl", "CJKLLO"]
    assert card["MPI_PDF_SET"] == card["PDF_SET"]                 # MPI follows the PDF it agreed with
    assert card["BEAM_ENERGIES"] == [275, 18] and card["EPA"]["Q2Max"] == 2.0


def test_render_leaves_a_deliberately_different_mpi_pdf_alone():
    yaml = pytest.importorskip("yaml")
    base = BASE.replace("MPI_PDF_SET: [NNPDF23_lo_as_0130_qed", "MPI_PDF_SET: [CT18NLO")
    card = yaml.safe_load(render().card([base], [Override("PDF_SET[0]", "MSTW2008lo68cl", "x")], {}))
    assert card["MPI_PDF_SET"][0] == "CT18NLO"


def test_render_refuses_what_the_plan_owns_and_missing_entries():
    with pytest.raises(HepError, match="plan owns"):
        render().card([BASE + "RANDOM_SEED: 7\n"], [], {"tag": "sherpa"})
    with pytest.raises(HepError, match=r"no PDF_SET\[2\]"):
        render().card([BASE], [Override("PDF_SET[2]", "X", "x")], {})


@pytest.mark.skipif(not NEEDS["sherpa"], reason="load_hep: Sherpa")
def test_sherpa_integration_is_keyed_by_the_card_without_its_event_count():
    few, many = plans("PhotoProduction/sherpa", sets=["run.event_count=100"]), plans("PhotoProduction/sherpa", sets=["run.event_count=9000"])
    assert few[0].rendered["sherpa"].prepare_dir == many[0].rendered["sherpa"].prepare_dir
    assert few[0].identity != many[0].identity
    by_pdf = plans("PhotoProduction/sherpa", "pdf")
    assert len({p.rendered["sherpa"].prepare_dir for p in by_pdf}) == 2    # other physics, other integration
    step = few[0].rendered["sherpa"]
    assert "EVENT_OUTPUT: None" in step.prepare_argv and step.prepare_needed
    card = few[0].writes[step.card_combined]
    assert "EVENTS: 100" in card and f"RANDOM_SEED: {few[0].seed}" in card and "EVENT_OUTPUT: HepMC3_GenEvent[events.hepmc]" in card


# ── Herwig (L15) ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not NEEDS["herwig"], reason="load_hep: Herwig")
def test_herwig_reads_once_and_runs_with_flag_seeds():
    try:
        [p] = plans("PhotoProduction/herwig")
    except HepError as error:
        pytest.skip(error.message)                                 # no repository: hep build
    step = p.rendered["herwig"]
    assert step.argv[-6:] == ["-N", "2000", "-s", str(p.seed), "-d", "0"]
    assert "{seed}" in step.identity_parts["argv"]                # the identity is seed-free
    assert p.writes[step.card_combined].rstrip().endswith("saverun point EventGenerator")
    assert "set /Herwig/EventHandlers/Luminosity:BeamEMaxB 275*GeV" in p.writes[step.card_combined]
    assert step.sidecar_written == 2000


@pytest.mark.skipif(not NEEDS["herwig"], reason="load_hep: Herwig")
def test_an_export_that_needs_a_prepare_runs_it_for_a_tool_herwig_is_not_in():
    try:
        [p] = plans("PhotoProduction/herwig", "export")
    except HepError as error:
        pytest.skip(error.message)
    herwig, probe = p.rendered["herwig"], p.rendered["probe"]
    assert herwig.group < 0 and herwig.prepare_needed
    assert probe.argv[-1] == str(herwig.prepare_dir / "point.run")


def test_a_runner_written_sidecar_says_what_was_asked_for(scratch):
    step = tools.Step(tag="sherpa", tool=None, folder=None, group=0, exe=scratch)
    step.sidecar, step.sidecar_written = scratch / "events.hepmc.json", 500
    assert execute._settle([step], {}) is None
    assert json.loads(step.sidecar.read_text())["written"] == 500
