"""`hep migrate` (V79): run TOMLs and cards rewritten in today's forms, by line, comments kept."""

from __future__ import annotations

import argparse

import pytest

from runner import cli, config, migrate, tools
from runner.errors import HepError

OLD = """\
[run]
name        = "sw"
project     = "PhotoProduction"
event_count = 1
sweep_runs  = true                 # every configuration but c

[run.a]
tools  = ["jets"]
sweeps = ["cut"]

[run.c]
swept  = false
tools  = ["jets"]
sweeps = ["cut"]

[tools.jets]
tool       = "custom"
consumes   = ["cut"]
executable = "python3"             # the interpreter

[quantities.cut]
values = [4.0, 5.0]
labels = ["E_{T} > 4 GeV",
          "E_{T} > 5 GeV"]         # thresholds

[plot]
title = "#sqrt{s} = 318 GeV"
"""


def test_a_toml_is_rewritten_line_by_line(scratch):
    path = scratch / "sw.toml"
    path.write_text(OLD, encoding="utf-8")
    run = config.load(str(path), strict=False)
    new = migrate.toml_text(OLD, run, run.project)
    assert 'sweep_runs  = ["a"] # every configuration but c' in new
    assert "swept" not in new
    assert 'executable = "path:python3" # the interpreter' in new
    assert 'labels = ["$E_{T}$ > 4 GeV", "$E_{T}$ > 5 GeV"] # thresholds' in new
    assert "title = '$\\sqrt{s}$ = 318 GeV'" in new
    new = migrate.cfgs_text(new)                                    # V98: [run.a] → [run.cfgs.a]
    assert "[run.cfgs.a]" in new and "[run.cfgs.c]" in new
    path.write_text(new, encoding="utf-8")
    config.load(str(path))                                          # it reads strictly now


def test_long_arrays_wrap_under_their_bracket():
    text = migrate._wrapped("labels = ", "[" + ", ".join(f'"label number {n}"' for n in range(8)) + "]", "", width=60)
    lines = text.splitlines()
    assert len(lines) > 1 and all(len(l) <= 60 for l in lines) and lines[1].startswith(" " * len("labels = ["))


def test_a_card_loses_the_lines_the_runner_sets():
    folder = tools.folders()["pythia"]
    card = "! a comment\nMain:numberOfEvents = 100\nPDF:pSet = 13\nRandom:seed = 0   ! time\n"
    assert migrate.card_text(card, folder) == "! a comment\nPDF:pSet = 13\n"


def test_the_command_diffs_then_applies(scratch, capsys):
    path = scratch / "sw.toml"
    path.write_text(OLD, encoding="utf-8")
    with pytest.raises(HepError, match=r"configurations are \[run.cfgs.<cfg>\] now"):
        config.load(str(path))
    assert cli.cmd_migrate(argparse.Namespace(configs=[str(path)], apply=False)) == 0
    shown = capsys.readouterr().out
    assert "-swept  = false" in shown and "+[run.cfgs.a]" in shown and "(a dry run" in shown
    assert path.read_text(encoding="utf-8") == OLD
    assert cli.cmd_migrate(argparse.Namespace(configs=[str(path)], apply=True)) == 0
    assert "migrated 1 file(s)" in capsys.readouterr().out
    config.load(str(path))
    assert cli.cmd_migrate(argparse.Namespace(configs=[str(path)], apply=False)) == 0
    assert "nothing to migrate" in capsys.readouterr().out


FIGURES = """\
[run]
name    = "fig"
configuration = "a"
event_count = 1
project = "PhotoProduction"

[run.a]
tools  = ["jets"]
sweeps = []

[tools.jets]
tool       = "custom"
executable = "path:python3"

[plot]
ratio = true

[plot.object."d04-*"]              # the tails
logy = true

[plot.object."/photo_eic/d0[5-6]*".style]
legend.position = "top-left"

[plot.overlay.eta]
objects = ["d02-x01-y01", "d11-x01-y01"]
ratio   = true
ratio.range  = [0.8, 1.1]
ratio.limits = [0.8, 1.1]
"""


def test_the_old_figure_tables_become_figures(scratch, capsys):
    """V81: overlays and object tables as [plot.figures]; a bare style key (not TOML beside ratio = true)
    under style. The text is migrated first, so the file reads once migrated."""
    new = migrate.figure_text(FIGURES)
    assert '[plot.figures.d04]              # the tails\nobjects = ["d04-*"]\nlogy = true\n' in new
    assert '[plot.figures.d0_5_6]\nobjects = ["/photo_eic/d0[5-6]*"]\n[plot.figures.d0_5_6.style]\nlegend.position' in new
    assert '[plot.figures.eta]\nclass = "overlay"\nobjects' in new
    assert "ratio   = true\nstyle.ratio.range  = [0.8, 1.1]\nstyle.ratio.limits = [0.8, 1.1]\n" in new
    assert "legend.position" in new and "style.legend.position" not in new           # a style table already
    path = scratch / "fig.toml"
    path.write_text(FIGURES, encoding="utf-8")
    assert cli.cmd_migrate(argparse.Namespace(configs=[str(path)], apply=True)) == 0
    run = config.load(str(path))
    assert run.plot["figures"]["eta"]["style"] == {"ratio": {"range": [0.8, 1.1], "limits": [0.8, 1.1]}}
    assert run.plot["figures"]["d04"] == {"objects": ["d04-*"], "logy": True}


def test_run_defaults_move_into_run():
    """V99: its keys after [run]'s own, its value where both set one (it was the nearer layer)."""
    text = '[run]\nname = "x"\nthreads = 4      # all\n\n[run.defaults]\nthreads = 8\ntools = ["a"]   # every one\n\n[run.cfgs.a]\nsweeps = []\n'
    new = migrate.defaults_text(text)
    assert new == '[run]\nname = "x"\nthreads = 8\ntools = ["a"]   # every one\n\n[run.cfgs.a]\nsweeps = []\n'
    assert migrate.defaults_text(new) == new


def test_master_becomes_config(scratch):
    """V93: the table and its two keys renamed, by line; the file then reads."""
    common = scratch / "common.toml"
    common.write_text('[static]\nenergies = "27x920"\n', encoding="utf-8")
    text = OLD.replace("[run]\n", f'[master]                           # how the file is read\ninclude     = ["{common}"]\n\n[run]\n', 1)
    new = migrate.config_text(text)
    assert new.startswith(f'[config]                           # how the file is read\nimport     = ["{common}"]\n')
    assert migrate.config_text(new) == new
