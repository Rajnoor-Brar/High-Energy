"""--why and hep check (V57): what changed since a point completed; every configuration planned."""

from __future__ import annotations

import argparse

import pytest
import tomli_w

from runner import cli, record

from helpers import plan, raw


@pytest.fixture(autouse=True)
def own_output(scratch, monkeypatch):
    """Each test's points under its own output/: a completed point must not be another test's."""
    monkeypatch.setenv("HEKIT_OUTPUT", str(scratch / "output"))


def completed(data, scratch):
    """Plan the point and record it complete, as execute.run_point does at the end."""
    _, _, p = plan(data, scratch)
    p.identity = record.identity(p)
    p.out.mkdir(parents=True, exist_ok=True)
    record.write_identity(p)
    record.write_atomic(record.complete_marker(p), p.identity + "\n")
    return p


def test_the_identity_is_the_hash_of_its_recorded_parts(scratch):
    p = completed(raw(), scratch)
    import hashlib, json
    parts = json.loads(record.identity_record(p).read_text(encoding="utf-8"))
    assert hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest() == p.identity
    assert record.why(p) == []                                           # complete: nothing to say


def test_why_names_what_changed(scratch):
    completed(raw(), scratch)
    _, _, again = plan(raw(run__event_count=20, tools__rivet__analyses=["photo_eic:R=0.4"]), scratch)
    again.identity = record.identity(again)
    lines = record.why(again)
    assert "events: 10 → 20" in lines
    assert any(l.startswith("tools.rivet.analyses: ") and "R=0.4" in l for l in lines)
    assert any("Main:numberOfEvents = 20" in l and l.startswith("tools.pythia.card: +") for l in lines)


def test_why_without_a_record(scratch):
    _, _, p = plan(raw(), scratch)
    p.identity = record.identity(p)
    assert "never run" in record.why(p)[0]


def test_check_plans_every_configuration_and_fails_with_2(scratch, capsys):
    ok = argparse.Namespace(configs=["PhotoProduction/eic", "PhotoProduction/zeus_validation"])
    assert cli.cmd_check(ok) == 0
    bad = scratch / "bad.toml"
    bad.write_text(tomli_w.dumps(raw(run__one__sweeps=["pfd"])), encoding="utf-8")
    assert cli.cmd_check(argparse.Namespace(configs=[str(bad)])) == 2
    out = capsys.readouterr().out
    assert "ok    PhotoProduction/eic: 13 configuration(s)" in out and "FAIL  " + str(bad) in out
