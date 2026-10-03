"""The run TOML's own checks (docs/04_Config_Reference.md §13): one bad file per rule, each with where and hint."""

from __future__ import annotations

import pytest

from runner.errors import HepError

from helpers import parse, plan, raw


def fails(data, scratch, match):
    with pytest.raises(HepError, match=match) as caught:
        parse(data, scratch)
    assert caught.value.where
    return caught.value


def test_the_base_config_parses(scratch):
    run = parse(raw(), scratch)
    assert run.configuration(None).tools == [["pythia", "rivet"]]
    assert run.configuration(None).threads == 1


def test_c1_an_unknown_key_suggests_the_right_one(scratch):
    error = fails(raw(run__one__sweps=["pdf"]), scratch, "unknown key 'sweps'")
    assert "sweeps" in error.hint


def test_c1_an_unknown_section(scratch):
    error = fails(raw(tool={"x": {}}), scratch, r"unknown section \[tool\]")
    assert "tools" in error.hint


def test_c1_a_wrong_type(scratch):
    fails(raw(run__event_count="many"), scratch, "must be an integer")


def test_c2_the_default_configuration_must_exist(scratch):
    fails(raw(run__configuration="nope"), scratch, "not a \\[run.<name>\\] table")


def test_c2_a_named_configuration_must_exist(scratch):
    run = parse(raw(), scratch)
    with pytest.raises(HepError, match="no configuration 'on'") as caught:
        run.configuration("on")
    assert "one" in caught.value.hint


def test_c3_sweeps_name_declared_quantities(scratch):
    fails(raw(run__one__sweeps=["pfd"]), scratch, "not a \\[quantities")


def test_c3_entangled_groups_have_equal_lengths(scratch):
    data = raw(run__one__sweeps=[["pdf", "other"]], quantities__other={"values": [1, 2, 3]})
    fails(data, scratch, "equal value counts")


def test_c4_plot_points_must_be_swept(scratch):
    fails(raw(run__one__sweeps=["pdf"], run__one__plot_points=["energies"]), scratch, "not swept")


def test_c5_tools_name_tool_tables(scratch):
    error = fails(raw(run__one__tools=[["pythia", "rivt"]]), scratch, "not a \\[tools.<tag>\\] table")
    assert "rivet" in error.hint


def test_c5_groups_nest_one_level(scratch):
    fails(raw(run__one__tools=[[["pythia"]]]), scratch, "nest one level")


def test_c12_climbing_out_is_refused(scratch):
    with pytest.raises(HepError, match="climbs out"):
        plan(raw(tools__pythia__baseconfig="../photo_ep.cmnd"), scratch)


def test_static_values_resolve_by_tag_value_or_index(scratch):
    for selector in ("NNPDF23lo", "LHAPDF6:NNPDF23_lo_as_0130_qed", "#2"):
        _, _, p = plan(raw(static={"pdf": selector}), scratch)
        assert p.values["pdf"] == 1


def test_a_bad_static_value_names_the_choices(scratch):
    with pytest.raises(HepError, match="not a value") as caught:
        plan(raw(static={"pdf": "NNPDF23"}), scratch)
    assert "NNPDF23lo" in caught.value.hint


def test_set_overrides_one_value(scratch):
    from runner.config import apply_sets
    data = raw()
    apply_sets(data, ["run.one.threads=4", "static.pdf=MSTW08lo"])
    run = parse(data, scratch)
    assert run.configuration("one").threads == 4 and run.static == {"pdf": "MSTW08lo"}


# ── V58: the vocabulary's shapes ──────────────────────────────────────────────────────────────

def test_a_vocabulary_quantity_takes_values_of_its_shape(scratch):
    good = raw(quantities__energies={"values": [[275, 18], [920, 27.5]], "tags": ["a", "b"]})
    parse(good, scratch)
    error = fails(raw(quantities__energies={"values": [275, 18]}), scratch, r"value 1 is 275, not a list of 2")
    assert "beam A, beam B" in error.hint
    fails(raw(quantities__beams={"values": [[2212, "e-"]]}), scratch, "not a list of 2")
    fails(raw(quantities__pdf={"values": [True]}), scratch, "not a string or an integer")


def test_a_quantity_the_vocabulary_lacks_is_the_users_own(scratch):
    parse(raw(quantities__pt0ref={"values": ["anything", 3.2], "key": {"pythia": "MultipartonInteractions:pT0Ref"}}), scratch)


def test_every_folder_maps_only_vocabulary_names():
    from runner import quantities
    master = quantities.load_master("PhotoProduction", None)
    names = set(quantities.vocabulary())
    for tool, table in master["quantities"].items():
        assert set(table["compatible_quantities"]) <= names, tool
    assert quantities.BUILTIN == ("events", "threads")
