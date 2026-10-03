"""Planning one point: cards, argv, the connection rules (C6), consumers (C7/C8) and the
standard-configuration exports (V21, C13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from runner.errors import HepError

from helpers import plan, raw

REPO = Path(__file__).resolve().parents[2]
CUSTOM = {"tool": "custom", "executable": "/bin/true"}


def test_the_pythia_card_has_builtins_quantities_and_seeds(scratch):
    _, _, p = plan(raw(static={"pdf": "MSTW08lo"}), scratch)
    card = p.writes[p.rendered["pythia"].card_point]
    assert "Main:numberOfEvents = 10\nParallelism:numThreads = 1\n" in card
    assert "PDF:pSet = LHAPDF6:MSTW2008lo68cl" in card
    assert "Random:setSeed = on\nRandom:seed = 12345" in card
    assert "Parallelism:seeds" not in card                 # one thread: Random:seed alone


def test_several_threads_get_one_seed_each(scratch):
    _, _, p = plan(raw(run__threads=3), scratch)
    card = p.writes[p.rendered["pythia"].card_point]
    assert "Random:seed = 12345" in card and "Parallelism:seeds = {12345,12346,12347}" in card


def test_rivet_argv_writes_partial_then_reads_the_fifo(scratch):
    _, _, p = plan(raw(), scratch)
    argv = p.rendered["rivet"].argv
    assert argv[1:3] == ["-o", str(p.res / "photo.partial.yoda")]
    assert argv[3:5] == ["-a", "photo_eic"] and argv[-1] == str(p.out / "events.hepmc")
    assert p.rendered["rivet"].count_check[1] == p.out / "events.hepmc.json"


def test_an_analysis_option_quantity_reaches_rivet(scratch):
    data = raw(run__one__sweeps=["radius"],
               quantities__radius={"target": "rivet/photo_eic", "key": "R", "values": [0.4, 0.7], "tags": ["r04", "r07"]})
    _, _, p = plan(data, scratch, point=1)
    assert "photo_eic:R=0.7" in p.rendered["rivet"].argv
    assert p.point.name == "r07"



def test_an_inline_analysis_option_beats_the_tables_options(scratch):
    """Child over parent: `analyses = ["photo_eic:R=0.4"]` is the analysis's own value, and the table's
    `options` (for every analysis) give way to it; a quantity, the point's value, is last."""
    data = raw(tools__rivet__analyses=["photo_eic:R=0.4"], tools__rivet__options={"R": 1.0, "ETMIN": 6})
    _, _, p = plan(data, scratch)
    assert "photo_eic:ETMIN=6:R=0.4" in p.rendered["rivet"].argv
    data["run"]["one"]["sweeps"] = ["radius"]
    data["quantities"]["radius"] = {"target": "rivet/photo_eic", "key": "R", "values": [0.7], "tags": ["r07"]}
    _, _, p = plan(data, scratch)
    assert "photo_eic:ETMIN=6:R=0.7" in p.rendered["rivet"].argv

# ── C6: connections ────────────────────────────────────────────────────────────────────────────

def test_c6_a_fifo_into_a_non_streamable_tool_is_refused(scratch):
    data = raw(tools__rivet=None, run__one__tools=[["pythia", "slow"]],
               tools__slow={**CUSTOM, "input": "events.hepmc", "streamable": False})
    with pytest.raises(HepError, match="cannot read a FIFO"):
        plan(data, scratch)


def test_c6_a_fifo_across_groups_is_refused(scratch):
    with pytest.raises(HepError, match="across groups") as caught:
        plan(raw(run__one__tools=["pythia", "rivet"]), scratch)
    assert "L8" in caught.value.hint


def test_c6_a_fifo_has_one_reader(scratch):
    data = raw(run__one__tools=[["pythia", "rivet", "second"]],
               tools__second={**CUSTOM, "input": "events.hepmc"})
    with pytest.raises(HepError, match="2 readers") as caught:
        plan(data, scratch)
    assert "V16" in caught.value.hint


def test_c6_a_fifo_needs_a_writer(scratch):
    with pytest.raises(HepError, match="no writer"):
        plan(raw(run__one__tools=[["rivet"]]), scratch)


def test_c6_an_output_has_one_writer(scratch):
    data = raw(run__one__tools=[["pythia", "rivet"], "again"],
               tools__again={**CUSTOM, "output_file": "photo.yoda"})
    with pytest.raises(HepError, match="written by both"):
        plan(data, scratch)


def test_fan_out_gives_each_reader_its_own_fifo(scratch):
    data = raw(prelim={"fifo": ["a.hepmc", "b.hepmc"]}, run__one__tools=[["pythia", "rivet", "other"]],
               tools__pythia__output_file=["a.hepmc", "b.hepmc"], tools__rivet__input="a.hepmc",
               tools__other={**CUSTOM, "input": "b.hepmc", "streamable": True})
    _, _, p = plan(data, scratch)
    assert p.rendered["pythia"].argv[1] == f"{p.out / 'a.hepmc'},{p.out / 'b.hepmc'}"


# ── C7, C8: consumers ──────────────────────────────────────────────────────────────────────────

def test_c7_a_quantity_nobody_consumes_is_refused(scratch):
    data = raw(run__one__sweeps=["nothing"], quantities__nothing={"values": [1, 2], "tags": ["a", "b"]})
    with pytest.raises(HepError, match="no tool in this chain consumes it"):
        plan(data, scratch)


def test_c8_two_sources_for_one_key_are_refused(scratch):
    data = raw(static={"pdf": "MSTW08lo", "alias": "x"},
               quantities__alias={"values": ["x"], "key": {"pythia": "PDF:pSet"}})
    with pytest.raises(HepError, match="set by both"):
        plan(data, scratch)


# ── V21, C13: standard configurations for custom tools ─────────────────────────────────────────

def test_c13_an_export_is_the_same_card_pythia_gets(scratch):
    data = raw(run__one__tools=[["pythia", "rivet"], "probe"],
               tools__probe={**CUSTOM, "pythia_cmnd": True, "rivet_analyses": True})
    _, _, p = plan(data, scratch)
    import tomllib
    exported = tomllib.loads(p.writes[p.rendered["probe"].config_path])["standard"]
    card = exported["pythia_cmnd"]
    pythia = p.rendered["pythia"]
    assert card["path"] == str(pythia.card_combined)
    assert card["parts"] == [str(x) for x in pythia.card_base] + [str(pythia.card_point)]
    assert pythia.argv[2:] == card["parts"]                # App_Pythia reads exactly these, in order
    assert p.writes[pythia.card_combined].endswith(p.writes[pythia.card_point])
    assert exported["rivet_analyses"]["analyses"] == ["photo_eic"]
    assert p.rendered["probe"].argv[:2] == ["/bin/true", str(p.rendered["probe"].config_path)]


def test_an_exported_tool_is_rendered_without_being_run(scratch):
    data = raw(run__one__tools=["probe"], prelim={}, static={"pdf": "MSTW08lo"},
               tools__probe={**CUSTOM, "pythia_card": True})
    _, _, p = plan(data, scratch)
    assert [s.tag for g in p.groups for s in g] == ["probe"]
    assert "PDF:pSet = LHAPDF6:MSTW2008lo68cl" in p.writes[p.rendered["pythia"].card_point]   # C7 passes via the export
    assert "Random:seed = 12345" in p.writes[p.rendered["pythia"].card_combined]


def test_c13_true_with_two_candidate_tables_must_name_one(scratch):
    data = raw(run__one__tools=[["pythia", "rivet"], "probe"],
               tools__other={"tool": "pythia", "baseconfig": "photo_ep.cmnd"},
               tools__probe={**CUSTOM, "pythia_cmnd": True})
    data["tools"]["main"] = data["tools"].pop("pythia")
    data["run"]["one"]["tools"] = [["main", "rivet"], "probe"]
    with pytest.raises(HepError, match="several pythia tables") as caught:
        plan(data, scratch)
    assert 'pythia_cmnd = "<tag>"' in caught.value.hint


def test_c13_an_unknown_export_suggests_the_offers(scratch):
    data = raw(run__one__tools=[["pythia", "rivet"], "probe"], tools__probe={**CUSTOM, "pythia_cmd": True})
    with pytest.raises(HepError, match="does not export 'cmd'") as caught:
        plan(data, scratch)
    assert "cmnd" in caught.value.hint


def test_a_custom_tool_gets_its_config_and_consumed_quantities(scratch):
    data = raw(run__one__tools=[["pythia", "rivet"], "fit"], static={"pdf": "MSTW08lo"},
               tools__fit={**CUSTOM, "consumes": ["pdf"], "config": {"model": "gauss"}, "arguments": ["{res}/fit.json"]})
    _, _, p = plan(data, scratch)
    import tomllib
    written = tomllib.loads(p.writes[p.rendered["fit"].config_path])
    assert written == {"model": "gauss", "quantities": {"pdf": "LHAPDF6:MSTW2008lo68cl"}}
    assert p.rendered["fit"].argv[-1] == f"{p.res}/fit.json"


# ── V54: an executable is built, or asked for on PATH by name ─────────────────────────────────

def test_a_bare_executable_must_be_built_and_never_falls_back_to_path(scratch):
    data = raw(run__one__tools=[["pythia", "rivet"], "probe"], tools__probe={"tool": "custom", "executable": "true"})
    with pytest.raises(HepError, match="is not built") as caught:
        plan(data, scratch)
    assert 'path:true' in caught.value.hint


def test_path_prefix_takes_the_command_from_path(scratch):
    data = raw(run__one__tools=[["pythia", "rivet"], "probe"], tools__probe={"tool": "custom", "executable": "path:true"})
    _, _, p = plan(data, scratch)
    assert p.rendered["probe"].exe.name == "true" and p.rendered["probe"].exe.is_absolute()
    data["tools"]["probe"]["executable"] = "path:no-such-command-here"
    with pytest.raises(HepError, match="is not a command on PATH"):
        plan(data, scratch)


def test_the_combined_card_carries_the_base_settings_without_comments(scratch):
    """V54: the card that runs is the base's settings, under one `! from <base>` line, then the point card."""
    _, _, p = plan(raw(), scratch)
    step = p.rendered["pythia"]
    combined = p.writes[step.card_combined].splitlines()
    base = step.card_base[0]
    assert combined[0] == f"! from {base}"
    settings = [line for line in combined[1:] if not line.startswith("!")]
    assert settings and all(line.strip() and line.strip()[0].isalnum() for line in settings)
    assert not any(" ! " in line for line in settings)                         # trailing comments gone
    kept = [l.split("!")[0].rstrip() for l in base.read_text().splitlines() if l.strip()[:1].isalnum()]
    assert settings[:len(kept)] == kept                                        # every setting, in order


def test_a_tcl_comment_line_inside_braces_is_kept(scratch):
    from runner import tools
    card = scratch / "c.tcl"
    card.write_text("# top\nset ExecutionPath {\n  A\n#  B\n}\n\n# end\nset X 1  # not a comment in Tcl\n")
    folder = tools.folders()["delphes"]
    assert tools.clean_base(card, folder) == [f"# from {card}", "set ExecutionPath {", "  A", "#  B", "}",
                                              "set X 1  # not a comment in Tcl"]
