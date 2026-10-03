"""Layers (V56): [run.defaults], extends, [master].include, "default" in a child, sweeping events, --show-config."""

from __future__ import annotations

import pytest
import tomli_w

from runner import cli, config
from runner.errors import HepError

from helpers import parse, plan, raw


def configurations(**tables) -> dict:
    """raw() with [run.one] replaced by these configurations ([run.configuration] = the first)."""
    data = raw()
    del data["run"]["one"]
    data["run"].update(tables)
    data["run"]["configuration"] = next(k for k in tables if k != "defaults")
    return data


def test_run_defaults_reach_every_configuration_and_their_own_keys_win(scratch):
    run = parse(configurations(defaults={"tools": [["pythia", "rivet"]], "event_count": 50},
                               a={}, b={"event_count": 7}), scratch)
    a, b = run.configurations["a"], run.configurations["b"]
    assert a.tools == b.tools == [["pythia", "rivet"]] and (a.event_count, b.event_count) == (50, 7)
    assert a.origins["event_count"] == "[run.defaults]" and b.origins["event_count"] == "[run.b]"
    assert "defaults" not in run.configurations                       # a reserved name, not a configuration


def test_extends_takes_the_parents_keys_but_not_its_folder_or_title(scratch):
    run = parse(configurations(base={"tools": [["pythia", "rivet"]], "sweeps": ["pdf"], "label": "PDFs", "event_count": 9},
                               big={"extends": "base", "event_count": 900}), scratch)
    big = run.configurations["big"]
    assert big.sweeps == ["pdf"] and big.event_count == 900 and big.tools == [["pythia", "rivet"]]
    assert big.label == "big" and big.title == "big"                  # its own label and title
    assert big.origins["sweeps"] == "[run.base]"


def test_extends_chains_and_refuses_a_circle_or_a_missing_parent(scratch):
    chained = parse(configurations(a={"tools": [["pythia", "rivet"]], "threads": 3}, b={"extends": "a"}, c={"extends": "b"}),
                    scratch)
    assert chained.configurations["c"].threads == 3
    with pytest.raises(HepError, match="round in a circle"):
        parse(configurations(a={"extends": "b", "tools": [["pythia"]]}, b={"extends": "a"}), scratch)
    with pytest.raises(HepError, match="not a configuration") as caught:
        parse(configurations(a={"tools": [["pythia", "rivet"]]}, b={"extends": "aa"}), scratch)
    assert "'a'" in caught.value.hint


def test_run_defaults_cannot_set_a_configurations_own_keys(scratch):
    with pytest.raises(HepError, match="each configuration has of its own"):
        parse(configurations(defaults={"label": "x"}, a={"tools": [["pythia", "rivet"]]}), scratch)


def test_default_in_a_child_is_the_next_layers_value(scratch):
    run = parse(configurations(defaults={"threads": 4}, a={"tools": [["pythia", "rivet"]], "threads": "default"}), scratch)
    assert run.configurations["a"].threads == 4 and run.configurations["a"].origins["threads"] == "[run.defaults]"


def test_static_merges_through_the_layers_and_default_at_the_top_unsets(scratch):
    data = configurations(defaults={"static": {"pdf": "NNPDF23lo"}}, a={"tools": [["pythia", "rivet"]]},
                          b={"extends": "a", "static": {"pdf": "default"}})
    run = parse(data, scratch)
    assert run.configurations["b"].static == {"pdf": "NNPDF23lo"}      # "default" keeps the parent's
    data = raw(static={"pdf": "default"})
    assert parse(data, scratch).configuration(None).static == {}       # at the top: not set at all


def test_a_configurations_prelim_replaces_the_files_whole(scratch):
    run = parse(configurations(a={"tools": [["pythia", "rivet"]], "prelim": {"files": ["x.hepmc"]}}), scratch)
    assert run.configurations["a"].prelim == {"files": ["x.hepmc"]}   # no FIFO inherited: its chain's own


def test_include_gives_tables_and_the_file_wins(scratch):
    common = scratch / "common.toml"
    common.write_text(tomli_w.dumps({
        "quantities": {"energies": {"values": [[275, 18]], "tags": ["18x275"]},
                       "pdf": {"values": ["LHAPDF6:MSTW2008lo68cl"], "tags": ["old"]}},
        "plot": {"ratio": True, "y_gutter": 2.0},
        "run": {"defaults": {"event_count": 33}},
    }), encoding="utf-8")
    data = raw(master={"include": [str(common)]}, plot={"y_gutter": 0.3})
    del data["run"]["event_count"]
    path = scratch / "run.toml"
    path.write_text(tomli_w.dumps(data), encoding="utf-8")
    run = config.load(str(path))
    assert run.quantities["energies"].tags == ["18x275"]                # from the include
    assert run.quantities["pdf"].tags == ["MSTW08lo", "NNPDF23lo"]      # the file's own, whole: nothing of "old"
    assert run.plot["ratio"] is True and run.plot["y_gutter"] == 0.3   # tables deep, the file's keys win
    assert run.configuration(None).event_count == 33
    assert run.included == {"quantities.energies": "common.toml", "run.defaults": "common.toml"}


def test_an_include_cannot_include(scratch):
    inner = scratch / "inner.toml"
    inner.write_text('[master]\ninclude = ["x.toml"]\n', encoding="utf-8")
    path = scratch / "run.toml"
    path.write_text(tomli_w.dumps(raw(master={"include": str(inner)})), encoding="utf-8")
    with pytest.raises(HepError, match="do not nest"):
        config.load(str(path))


def test_events_swept_as_a_quantity_set_each_points_count(scratch):
    data = raw(run__one__sweeps=["events"], quantities__events={"values": [100, 2500], "tags": ["e100", "e2500"]})
    _, _, small = plan(data, scratch, point=0)
    _, _, large = plan(data, scratch, point=1)
    assert (small.events, large.events) == (100, 2500)
    assert "Main:numberOfEvents = 2500" in large.writes[large.rendered["pythia"].card_combined]
    assert small.identity != large.identity if small.identity else True


def test_show_config_says_where_each_value_came_from(scratch):
    run = parse(configurations(defaults={"tools": [["pythia", "rivet"]]}, a={"event_count": 5}), scratch)
    lines = cli.show_config(run, ["a"])
    assert any(l.split()[0] == "tools" and l.endswith("[run.defaults]") for l in lines[1:])
    assert any(l.split()[0] == "event_count" and l.endswith("[run.a]") for l in lines[1:])
    assert any(l.split()[0] == "parallelism" and l.endswith("default") for l in lines[1:])
    assert any(l.split()[0] == "label" and l.endswith("default") for l in lines[1:])
