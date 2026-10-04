"""Housekeeping (V74): `hep ls`, `hep explain`, `hep status`, `hep clean`, and `hep overlay` split from
`hep plot`. Everything under the test's own output/ and results/."""

from __future__ import annotations

import argparse

import pytest

from runner import cli, house
from runner.errors import HepError


@pytest.fixture
def trees(scratch, monkeypatch):
    monkeypatch.setenv("HEKIT_OUTPUT", str(scratch / "output"))
    monkeypatch.setenv("HEKIT_RESULTS", str(scratch / "results"))
    return scratch


def planned(name: str, key: str):
    return cli.build_plans(argparse.Namespace(config=name, set=[], points=None, rerun=False, only=None), key)


def test_ls_lists_every_configuration_and_marks_what_runs():
    lines = house.ls("PhotoProduction")
    assert "PhotoProduction/eic   run eic" in lines
    assert any(line.startswith("  * pdf ") for line in lines)                 # [run].configuration
    assert any(line.startswith("    single ") for line in lines)
    with pytest.raises(HepError, match="no run TOML"):
        house.ls("NoSuchProject")


@pytest.mark.parametrize("key, shown", [
    ("plot.y_gutter", "default  0.5"), ("[plot].normalise", "choices  area, false"),
    ("quantities.pdf.styles", "(a table each)"), ("run.one.event_count", "[configuration].event_count"),
    ("event_count", "[run].event_count"), ("tools.rivet.shards", "min      1"),
    ("plot.band", "(<q> envelope)")])                                        # V90: a key's notes
def test_explain_reads_the_schema(key, shown):
    assert any(shown in line for line in house.explain(key))


def test_explain_suggests_a_near_key():
    with pytest.raises(HepError) as error:
        house.explain("plot.yguter")
    assert "y_gutter" in error.value.hint


def test_status_says_what_each_point_is(trees):
    p = planned("PhotoProduction/eic", "pdf")
    first, second, third = p.every[:3]
    second.out.mkdir(parents=True)
    (second.out / "logs").mkdir()                                       # begun, not done
    third.out.mkdir(parents=True)
    (third.out / ".complete").write_text("an older identity\n")         # complete once, since changed
    lines = house.status([p], {})
    assert lines[0].startswith("eic · pdf (PhotoProduction/eic/01_pdf): 1 stale, 1 incomplete, 2 to run")
    states = {line.split()[0]: line[27:37].strip() for line in lines[1:]}     # "  <name:24> <state:10> …"
    assert states[first.point.name] == "to run" and states[second.point.name] == "incomplete"
    assert states[third.point.name] == "stale"
    assert house.status([p], {str(p.run.path): ["pdf"]})[0].endswith("[running]")


def test_clean_takes_only_what_no_plan_uses_and_never_results(trees):
    p = planned("PhotoProduction/eic", "single")
    point = p.every[0]
    base_out, base_res = point.out.parent, point.res.parent
    (base_out / "oldtag" / "logs").mkdir(parents=True)                  # a point a quantity's tags no longer make
    (base_res / "oldtag").mkdir(parents=True)
    point.res.mkdir(parents=True)
    (point.res / "photo.partial.yoda").write_text("x")                  # an attempt's leftover
    (point.res / "photo.yoda").write_text("kept")
    (base_out / "plots").mkdir()
    old_run = trees / "output" / "PhotoProduction" / "old" / "01_x"
    old_run.mkdir(parents=True)
    targets, kept = house.clean_targets([p], everything=False)
    assert set(targets) == {base_out / "oldtag", point.res / "photo.partial.yoda"}
    assert kept == [base_res / "oldtag"]
    everything, _ = house.clean_targets([p], everything=True)
    assert old_run in everything and (point.res / "photo.yoda") not in everything
    house.remove(targets)
    assert not (base_out / "oldtag").exists() and (point.res / "photo.yoda").read_text() == "kept"
    assert (base_res / "oldtag").exists() and (base_out / "plots").exists()


def test_clean_asks_unless_told(trees, monkeypatch, capsys):
    p = planned("PhotoProduction/eic", "single")
    (p.every[0].out.parent / "oldtag").mkdir(parents=True)
    args = argparse.Namespace(config="PhotoProduction/eic", dry_run=False, yes=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(HepError, match="not deleted"):
        cli.cmd_clean(args)
    assert (p.every[0].out.parent / "oldtag").exists()
    args.dry_run = True
    assert cli.cmd_clean(args) == 0 and "(dry run)" in capsys.readouterr().out
    args.dry_run, args.yes = False, True
    assert cli.cmd_clean(args) == 0 and not (p.every[0].out.parent / "oldtag").exists()


def test_plot_takes_a_config_and_overlay_takes_files():
    with pytest.raises(HepError, match="overlaid by hep overlay"):
        cli.cmd_plot(argparse.Namespace(config="a.yoda", configuration=None, set=[]))
    with pytest.raises(HepError, match="is not a YODA or ROOT file"):
        cli.cmd_overlay(argparse.Namespace(files=["a.yoda", "notes.txt"], output=None, labels=None, objects=[],
                                           formats="png", ratio=False, style=None))


def test_results_load_reads_the_manifest(trees):
    """V77: runner.results reads points.json, plans nothing."""
    import json
    from runner import results
    p = planned("PhotoProduction/eic", "pdf")
    from runner import record
    path = p.every[0].out.parent / "points.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record.points_manifest(p.every, p.run, p.configuration), default=str))
    points = results.load("PhotoProduction/eic", "pdf")
    assert [q.name for q in points] == [q.point.name for q in p.every]
    first = points[0]
    assert first.values["pdf"].tag == "MSTW08lo" and first.values["pdf"].swept and not first.complete
    assert first.yoda() == p.every[0].res / "photo.yoda"
    assert set(results.runs("PhotoProduction/eic")) == {"pdf"}
    with pytest.raises(HepError, match="no results yet"):
        results.load("PhotoProduction/eic", "single")


def test_reproduce_refuses_a_setup_that_changed(trees, capsys):
    """V77: a provenance whose identity is not today's plan's is a different point."""
    import json
    p = planned("PhotoProduction/eic", "single")
    point = p.every[0]
    point.out.mkdir(parents=True)
    (point.out / "provenance.json").write_text(json.dumps({
        "config_file": str(p.run.path), "configuration": "single", "point": point.point.name, "run": "eic",
        "project": "PhotoProduction", "identity": "0" * 64, "seed": 1, "sets": []}))
    with pytest.raises(HepError, match="not reproduced"):
        cli.cmd_reproduce(argparse.Namespace(provenance=str(point.out), anyway=False, plain=True))
    assert "changed since it ran" in capsys.readouterr().out
