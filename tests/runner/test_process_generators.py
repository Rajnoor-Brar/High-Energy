"""P4 S3 at plan time: Whizard and MadGraph cards, the @generator chain and its C7 rule, and two
plot-stage fixes the new tools exposed. render.py is exercised with the runner's Override (L26)."""

from __future__ import annotations

import shutil

import pytest

from runner import plot, quantities, sweep, tools
from runner.errors import HepError
from runner.quantities import Override

from helpers import parse, plans, raw, render_context


# ── Whizard (L13) ─────────────────────────────────────────────────────────────────────────────

WHIZARD_BASE = "# hep: beam_structure = pdf_builtin, epa\nmodel = SM\nintegrate (x)\nsimulate (x)\n"


@pytest.mark.skipif(not shutil.which("whizard"), reason="load_hep: whizard (its model file names the beams)")
def test_whizard_card_sets_everything_before_it_includes_the_base():
    plugin = tools.folders()["whizard"].plugin
    text = plugin.card([WHIZARD_BASE], [Override("beams", [2212, -11], "q"), Override("beams_momentum", [275, 18], "q"),
                                        Override("n_events", 100, "built-in")],
                       render_context("whizard", tag="whizard", output="/p/events.hepmc", base_paths=["/c/photo_ep.sin"]))
    lines = text.splitlines()
    assert "beams = p, E1 => pdf_builtin, epa    # q" in lines
    assert "beams_momentum = 275.0 GeV, 18.0 GeV    # q" in lines
    assert lines.index("seed = {seed}") < lines.index('include("/c/photo_ep.sin")') == len(lines) - 1
    assert '$sample = "/p/events"' in lines                     # Whizard appends .hepmc itself
    integration = plugin.prepare_card(lines, [WHIZARD_BASE], {})
    assert "n_events" not in integration and "$sample" not in integration and "include(" in integration


def test_whizard_refuses_a_base_that_sets_what_the_plan_owns():
    plugin = tools.folders()["whizard"].plugin
    with pytest.raises(HepError, match="n_events"):
        plugin.card([WHIZARD_BASE + "n_events = 5\n"], [], render_context("whizard", tag="whizard", base_paths=["/b"]))


# ── MadGraph (L14) ────────────────────────────────────────────────────────────────────────────

PROC = "import model sm\ngenerate p e- > e- j\n"


def test_madgraph_launch_script_and_proc_card():
    plugin = tools.folders()["madgraph"].plugin
    launch = plugin.card([PROC], [Override("beams", [2212, 11], "q"), Override("ebeam1", 275, "q"),
                                  Override("nevents", 1000, "built-in")], render_context("madgraph", tag="madgraph")).splitlines()
    assert launch[:2] == ["set automatic_html_opening False", "launch {prepared}/process -n r{seed}"]   # 00/B39
    assert {"set lpp1 1", "set lpp2 0", "set ebeam1 275", "set nevents 1000", "set iseed {seed}"} <= set(launch)
    proc = plugin.prepare_card(launch, [PROC], {"prepared": "/cache/k"}).splitlines()
    assert proc[0] == "set automatic_html_opening False" and proc[-1] == "output /cache/k/process -f"
    with pytest.raises(HepError, match="own `output` line"):
        plugin.card([PROC + "output here\n"], [], render_context("madgraph", tag="madgraph"))


@pytest.mark.skipif(not shutil.which("mg5_aMC"), reason="load_hep: mg5_aMC")
def test_madgraph_is_built_once_per_proc_card_and_showered_from_a_file():
    few, many = plans("PhotoProduction/madgraph", sets=["run.event_count=10"]), plans("PhotoProduction/madgraph")
    mg = few[0].rendered["madgraph"]
    assert mg.prepare_dir == many[0].rendered["madgraph"].prepare_dir      # key = "base": the proc card only
    assert f"r{few[0].seed}" in mg.argv[-2] and mg.argv[-1] == str(few[0].interfaces["unweighted.lhe"].path)
    card = few[0].writes[few[0].rendered["shower"].card_combined]
    assert f"Beams:LHEF = {few[0].interfaces['unweighted.lhe'].path}" in card and "Beams:eCM" not in card
    assert "{prepared}" not in few[0].writes[mg.card_combined]


def test_a_pythia_card_without_an_input_has_no_lhef_line(scratch):
    from helpers import plan
    _, _, p = plan(raw(), scratch)
    assert "Beams:LHEF" not in p.writes[p.rendered["pythia"].card_combined]


# ── @generator (V19) and C7 ───────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not (shutil.which("Herwig") and shutil.which("Sherpa")), reason="load_hep: Herwig and Sherpa")
def test_each_point_runs_its_own_generator_and_takes_what_it_consumes():
    try:
        by = {p.point.name: p for p in plans("Comparison/generators")}
    except HepError as error:
        pytest.skip(error.message)                                    # Herwig's repository: hep build
    assert [s.tag for s in by["hw7"].groups[0]] == ["herwig", "spectra"]
    assert by["hw7"].consumers["beams"] == []                           # Herwig's snippet fixes its beams
    assert [m.tag for m in by["sh3"].consumers["beams"]] == ["sherpa"]
    assert "BEAM_ENERGIES: [6500.0, 6500.0]" in by["sh3"].writes[by["sh3"].rendered["sherpa"].card_combined]
    assert "Beams:eCM = 13000.0" in by["py8"].writes[by["py8"].rendered["pythia"].card_combined]


def test_an_at_chain_still_refuses_a_value_no_alternative_consumes(scratch):
    data = raw(run__cfgs__one__tools=[["@gen", "rivet"]], run__cfgs__one__sweeps=["gen"],
               quantities__gen={"values": ["pythia"], "tags": ["py"]},
               quantities__nothing={"values": [1], "key": {"herwig": "X"}}, static={"nothing": 1})
    run = parse(data, scratch)
    conf = run.configuration(None)
    with pytest.raises(HepError, match="no tool in this chain consumes"):
        tools.plan_point(run, conf, sweep.points(run, conf)[0], quantities.load_master(run.project, run.master_toml))


# ── the plot stage ────────────────────────────────────────────────────────────────────────────

def test_weight_variations_and_estimate_raws_are_not_pages_or_entries(scratch):
    yoda = scratch / "w.yoda"
    yoda.write_text("BEGIN YODA_ESTIMATE1D_V3 /A/x\nEND YODA_ESTIMATE1D_V3\n"
                    "BEGIN YODA_ESTIMATE1D_V3 /A/x[EXTRA__NTrials]\nEND YODA_ESTIMATE1D_V3\n"
                    "BEGIN YODA_HISTO1D_V3 /RAW/A/x\nEND YODA_HISTO1D_V3\n"
                    "BEGIN YODA_ESTIMATE1D_V3 /A/ratio\nEND YODA_ESTIMATE1D_V3\n"
                    "BEGIN YODA_ESTIMATE1D_V3 /RAW/A/ratio\nEND YODA_ESTIMATE1D_V3\n")
    assert plot.objects_of(yoda) == ["/A/x", "/A/ratio"]
    assert plot.raws_of(yoda) == {"/RAW/A/x"}
