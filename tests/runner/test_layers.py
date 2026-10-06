"""Layers (V56): [run.defaults], extends, [config].import (V93), "default" in a child, sweeping events, --show-config."""

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
    data = raw(config={"import": [str(common)]}, plot={"y_gutter": 0.3})
    del data["run"]["event_count"]
    path = scratch / "run.toml"
    path.write_text(tomli_w.dumps(data), encoding="utf-8")
    run = config.load(str(path))
    assert run.quantities["energies"].tags == ["18x275"]                # from the include
    assert run.quantities["pdf"].tags == ["MSTW08lo", "NNPDF23lo"]      # the file's own, whole: nothing of "old"
    assert run.plot["ratio"] is True and run.plot["y_gutter"] == 0.3   # tables deep, the file's keys win
    assert run.configuration(None).event_count == 33
    assert run.included == {"quantities.energies": "common.toml", "run.defaults": "common.toml"}


def test_imports_nest_depth_first_and_say_where_from(scratch):
    """V94: an imported file's own imports come first; the file over it wins; origins name the path."""
    inner = scratch / "inner.toml"
    inner.write_text(tomli_w.dumps({"quantities": {"energies": {"values": [[275, 18]], "tags": ["18x275"]}},
                                    "plot": {"ratio": True, "y_gutter": 2.0}}), encoding="utf-8")
    middle = scratch / "middle.toml"
    middle.write_text(tomli_w.dumps({"config": {"import": str(inner)}, "plot": {"y_gutter": 1.0}}), encoding="utf-8")
    path = scratch / "run.toml"
    path.write_text(tomli_w.dumps(raw(config={"import": str(middle)})), encoding="utf-8")
    run = config.load(str(path))
    assert run.quantities["energies"].tags == ["18x275"] and run.plot == {"ratio": True, "y_gutter": 1.0}
    assert run.included == {"quantities.energies": "middle.toml ← inner.toml"}


def test_an_import_circle_is_refused(scratch):
    a, b = scratch / "a.toml", scratch / "b.toml"
    a.write_text(tomli_w.dumps(raw(run__name="a", config={"import": str(b)})), encoding="utf-8")
    b.write_text(tomli_w.dumps({"config": {"import": str(a)}}), encoding="utf-8")
    with pytest.raises(HepError, match="imports go round in a circle: a.toml → b.toml → a.toml"):
        config.load(str(a))


def test_a_file_that_imports_has_its_own_location(scratch):
    """V94: [run].name and project are never imported, and no imported run may share them."""
    other = scratch / "other.toml"
    other.write_text(tomli_w.dumps(raw()), encoding="utf-8")
    path = scratch / "run.toml"
    path.write_text(tomli_w.dumps({"config": {"import": str(other)}, "run": {"project": "PhotoProduction"}}), encoding="utf-8")
    with pytest.raises(HepError, match=r"sets its own \[run\].name"):
        config.load(str(path))
    path.write_text(tomli_w.dumps({"config": {"import": str(other)}, "run": {"project": "PhotoProduction", "name": "t"}}),
                    encoding="utf-8")
    with pytest.raises(HepError, match="other.toml is the run PhotoProduction/t too"):
        config.load(str(path))


def test_another_projects_file_brings_its_cards_and_plans_the_same(scratch, monkeypatch):
    """V94: `<Project>/<name>`; its bare card paths stay its project's, so its points keep their identities."""
    import shutil
    from runner import quantities, record, sweep, tools
    from runner.paths import configs_root
    fixtures = configs_root()
    root = scratch / "configs"
    (root / "Other").mkdir(parents=True)
    (root / "PhotoProduction").mkdir()
    shutil.copy(fixtures / "PhotoProduction" / "photo_ep.cmnd", root / "Other" / "photo_ep.cmnd")
    monkeypatch.setenv("HEKIT_CONFIGS", str(root))
    (root / "Other" / "other.toml").write_text(tomli_w.dumps(raw(run__name="other", run__project="Other")), encoding="utf-8")
    (root / "PhotoProduction" / "mine.toml").write_text(tomli_w.dumps(
        {"config": {"import": "Other/other"}, "run": {"name": "mine", "project": "PhotoProduction"}}), encoding="utf-8")

    def identity(name):
        run = config.load(name)
        conf = run.configuration(None)
        plan = tools.plan_point(run, conf, sweep.points(run, conf)[0], quantities.load_master(run.project, run.master_toml))
        return run, record.identity(plan)

    theirs, mine = identity("Other/other"), identity("PhotoProduction/mine")
    assert mine[0].tools["pythia"].baseconfig == [str(root / "Other" / "photo_ep.cmnd")]
    assert mine[0].included["tools.pythia"] == "other.toml" and mine[0].project == "PhotoProduction"
    assert mine[1] == theirs[1]


def test_master_is_config_now(scratch):
    """V93 (break and migrate): [master] is refused with what to write."""
    with pytest.raises(HepError, match=r"\[master\] is \[config\] now") as error:
        parse(raw(master={"master_toml": "m.toml"}), scratch)
    assert "hep migrate" in error.value.hint


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
