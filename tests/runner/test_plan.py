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


def test_the_combined_card_holds_each_key_once(scratch):
    """V54, V59: the card on disk is the base's settings without comments, each key once (a base line
    the point card sets is left out: the point card's value is the one used), then the point card."""
    import json
    from runner import tools
    _, _, p = plan(raw(), scratch)
    step = p.rendered["pythia"]
    combined = p.writes[step.card_combined].splitlines()
    assert combined[0] == f"! from {step.card_base[0]}"
    parse = tools.card_parser(step.folder)
    keys = [parsed[0] for parsed in map(parse, combined) if parsed]
    assert len(keys) == len(set(keys))                                         # every key once
    assert "main:numberofevents" in keys and not any(" ! " in l for l in combined if not l.startswith("!"))
    settings = json.loads(p.writes[step.card_combined.with_suffix(".json")])
    assert settings["Main:numberOfEvents"] == {"value": "10", "from": "built-in events"}
    assert settings["PhaseSpace:pTHatMin"]["from"].startswith("photo_ep.cmnd:")
    assert any("which the runner sets" in note for note in p.notes) is ("Random:seed" in step.card_base[0].read_text(encoding="utf-8"))


def test_repeatable_commands_are_kept_every_time(scratch):
    from runner import tools
    base = scratch / "b.cmnd"
    base.write_text("23:onMode = off\n23:onIfMatch = 11 -11\n23:onIfMatch = 13 -13\nPDF:pSet = 13\n", encoding="utf-8")
    data = raw(tools__pythia__baseconfig=str(base), tools__pythia__settings={"23:onIfMatch": "15 -15", "PDF:pSet": 8})
    _, _, p = plan(data, scratch)
    card = p.writes[p.rendered["pythia"].card_combined]
    assert card.count("23:onIfMatch") == 3 and card.count("PDF:pSet") == 1 and "PDF:pSet = 8" in card


def test_settings_reach_the_card_and_a_second_source_is_refused(scratch):
    _, _, p = plan(raw(tools__pythia__settings={"HeavyIon:mode": 1}), scratch)
    assert "HeavyIon:mode = 1" in p.writes[p.rendered["pythia"].card_point]
    data = raw(tools__pythia__settings={"PDF:pSet": 8}, run__one__sweeps=["pdf"])
    with pytest.raises(HepError, match="set by both"):
        plan(data, scratch)
    with pytest.raises(HepError, match="no card for settings"):
        plan(raw(tools__rivet__settings={"x": 1}), scratch)


def test_a_tcl_comment_line_inside_braces_is_kept(scratch):
    from runner import tools
    card = scratch / "c.tcl"
    card.write_text("# top\nset ExecutionPath {\n  A\n#  B\n}\n\n# end\nset X 1  # not a comment in Tcl\n")
    folder = tools.folders()["delphes"]
    assert tools.clean_base(card, folder) == [f"# from {card}", "set ExecutionPath {", "  A", "#  B", "}",
                                              "set X 1  # not a comment in Tcl"]


@pytest.mark.skipif(not (Path(__file__).resolve().parents[2] / "build" / "App_PythiaCheck.exe").exists(),
                    reason="make utils/App_PythiaCheck.exe")
def test_pythia_reads_the_card_and_a_rejected_line_names_its_source(scratch, monkeypatch):
    """V59: [checks] card. Pythia's own reader, so a nucleus or an id:new particle needs no list of ours."""
    from runner import tools
    monkeypatch.setenv("HEKIT_OUTPUT", str(scratch / "output"))
    _, _, good = plan(raw(tools__pythia__settings={"9999999:new": "x void 1 0 0 1.0", "9999999:m0": 2.0,
                                                    "HeavyIon:mode": 1}), scratch)
    tools.check_cards(good)                                                 # no error: every line read
    _, _, bad = plan(raw(tools__pythia__settings={"PDF:pSett": 13}), scratch)
    with pytest.raises(HepError, match=r"rejects 1 line.*'PDF:pSett = 13' \(\[tools.pythia\].settings\)"):
        tools.check_cards(bad)
    assert list((scratch / "output").glob("*/.cache/checks/pythia/*.json"))   # cached by the card's text


def test_a_tables_own_filters_file_replaces_the_folders(scratch, monkeypatch):
    """V61: filters = "<file>" (configs/<P>/…, ./… from the repo) in place of status = "filters:<file>"."""
    rules = scratch / "mine.toml"
    rules.write_text('[[rule]]\nmatch = "^Done"\nemit = "phase"\n', encoding="utf-8")
    _, _, p = plan(raw(tools__rivet__filters=str(rules)), scratch)
    assert p.rendered["rivet"].status == "filters" and p.rendered["rivet"].filters == [{"match": "^Done", "emit": "phase"}]
    with pytest.raises(HepError, match="status must be one of"):
        plan(raw(tools__rivet__status="filters:mine.toml"), scratch)


def test_rivet_gives_the_pages_its_options_with_the_info_defaults(scratch):
    """V66: {opt:NAME} is the option at the point, given or the .info's "(default X)"."""
    data = raw(tools__rivet__options={"ETMIN": 17})
    _, _, p = plan(data, scratch)
    texts = p.rendered["rivet"].texts
    assert texts["opt:ETMIN"] == texts["opt:photo_eic:ETMIN"] == "17"
    assert texts["opt:ETMIN2"] == "10.0" and texts["opt:Q2MAX"] == "1.0"     # photo_eic.info's defaults
