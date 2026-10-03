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
    with pytest.raises(HepError, match="swept is gone"):
        config.load(str(path))
    assert cli.cmd_migrate(argparse.Namespace(configs=[str(path)], apply=False)) == 0
    shown = capsys.readouterr().out
    assert "-swept  = false" in shown and "(a dry run" in shown and path.read_text(encoding="utf-8") == OLD
    assert cli.cmd_migrate(argparse.Namespace(configs=[str(path)], apply=True)) == 0
    assert "migrated 1 file(s)" in capsys.readouterr().out
    config.load(str(path))
    assert cli.cmd_migrate(argparse.Namespace(configs=[str(path)], apply=False)) == 0
    assert "nothing to migrate" in capsys.readouterr().out
