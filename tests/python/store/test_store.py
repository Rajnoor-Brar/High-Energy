"""The store index, verification and `hep store` (P5-S01, 11 §2).

A store is large, long-lived and copied between machines — the population where files get truncated
and half-copied. The index records every shard's size and digest at the moment it was closed, so what
is worth testing is that a damaged store is *caught and named*, and that a partial one is reported as
valid-but-partial rather than failed, because its events are real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from hekit.errors import HepError
from hekit.store import index as index_module
from hekit.store import verify as verify_module
from hekit.store.cli import info, list_stores, verify as verify_command


def a_store(directory: Path, *, events: int = 30, shards: int = 3, compression: str = "zst",
            stopped: bool = False, index: bool = True) -> Path:
    """A store directory whose index matches its shards."""
    directory.mkdir(parents=True, exist_ok=True)
    per_shard = events // shards
    records = []
    for worker in range(shards):
        name = f"events.{worker}.hepmc" + ("" if compression == "none" else f".{compression}")
        path = directory / name
        path.write_bytes(f"shard {worker} ".encode() + b"x" * (1000 + worker))
        records.append({"file": name, "worker": worker, "events": per_shard,
                        "bytes": path.stat().st_size,
                        "sha256": verify_module.sha256_of(path)})
    if index:
        (directory / index_module.NAME).write_text(json.dumps({
            "version": 1, "format": "hepmc3-ascii", "compression": compression,
            "point": "eic_5x41_ep", "hash": "sha256:" + "ab" * 32,
            "provenance": "../provenance.json",
            "generator": {"tool": "pythia", "version": "8.317"},
            "beams": {"ids": [2212, -11], "energies": [920.0, 27.5]},
            "threads": shards, "seeds": [100 + worker for worker in range(shards)],
            "weights": ["Weight"], "xsec_pb": 70818.73, "xsec_err_pb": 2212.24,
            "events": per_shard * shards, "stopped": stopped, "shards": records,
        }, indent=2), encoding="utf-8")
    return directory


def invoke(command, arguments):
    return CliRunner().invoke(command, arguments, obj={"plain": True})


# ── the index ────────────────────────────────────────────────────────────────

def test_an_index_is_read_as_data(tmp_path):
    index = index_module.read(a_store(tmp_path / "events"))
    assert index.version == 1 and index.format == "hepmc3-ascii"
    assert index.point == "eic_5x41_ep" and index.hash.startswith("sha256:")
    assert index.events == 30 and index.shard_events == 30 and index.consistent
    assert [shard.worker for shard in index.shards] == [0, 1, 2]
    assert index.beam_ids == [2212, -11] and index.beam_energies == [920.0, 27.5]
    assert index.seeds == [100, 101, 102] and index.threads == 3
    assert index.xsec_pb == 70818.73 and index.weights == ["Weight"]
    assert not index.stopped
    assert index.bytes == sum(shard.bytes for shard in index.shards)


def test_the_index_matches_its_committed_schema(tmp_path):
    """The schema is the contract a replay and any other reader rely on (11 §2)."""
    pytest.importorskip("jsonschema")
    index_module.validate(a_store(tmp_path / "events"))
    assert index_module.schema_path().is_file()
    schema = json.loads(index_module.schema_path().read_text(encoding="utf-8"))
    assert schema["properties"]["version"]["const"] == 1
    assert set(schema["required"]) == {"version", "format", "compression", "events", "shards"}


def test_an_index_that_breaks_the_schema_is_refused(tmp_path):
    pytest.importorskip("jsonschema")
    directory = a_store(tmp_path / "events")
    payload = json.loads((directory / index_module.NAME).read_text(encoding="utf-8"))
    payload["compression"] = "rar"
    with pytest.raises(HepError, match="invalid"):
        index_module.validate(payload)


def test_a_missing_index_says_the_store_is_unfinished(tmp_path):
    directory = a_store(tmp_path / "events", index=False)
    with pytest.raises(HepError, match="unfinished"):
        index_module.read(directory)


def test_a_future_index_version_is_refused(tmp_path):
    directory = a_store(tmp_path / "events")
    path = directory / index_module.NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HepError, match="index version 99"):
        index_module.read(directory)


# ── verification ─────────────────────────────────────────────────────────────

def test_an_intact_store_verifies(tmp_path):
    report = verify_module.verify(a_store(tmp_path / "events"), deep=True)
    assert report.ok and report.deep
    assert report.checked_bytes > 0
    assert "digests verified" in report.summary()


def test_a_truncated_shard_is_caught_by_size_alone(tmp_path):
    """The cheap check has to catch the common damage: a half-finished copy."""
    directory = a_store(tmp_path / "events")
    shard = directory / "events.1.hepmc.zst"
    shard.write_bytes(shard.read_bytes()[:-200])

    report = verify_module.verify(directory)
    assert not report.ok
    assert any("truncated" in problem and "events.1" in problem for problem in report.problems)


def test_a_shard_that_changed_without_changing_size_needs_deep(tmp_path):
    directory = a_store(tmp_path / "events")
    shard = directory / "events.2.hepmc.zst"
    data = bytearray(shard.read_bytes())
    data[10] = (data[10] + 1) % 256
    shard.write_bytes(bytes(data))

    assert verify_module.verify(directory).ok, "the size is unchanged, so the cheap check passes"
    deep = verify_module.verify(directory, deep=True)
    assert not deep.ok
    assert any("does not match its recorded digest" in problem for problem in deep.problems)


def test_a_missing_shard_is_named(tmp_path):
    directory = a_store(tmp_path / "events")
    (directory / "events.0.hepmc.zst").unlink()
    report = verify_module.verify(directory)
    assert any("events.0.hepmc.zst is missing" in problem for problem in report.problems)


def test_a_shard_nobody_declared_is_reported(tmp_path):
    """Two runs writing into one directory is how a store quietly gains events it cannot explain."""
    directory = a_store(tmp_path / "events")
    (directory / "events.9.hepmc.zst").write_bytes(b"from somewhere else")
    report = verify_module.verify(directory)
    assert any("events.9.hepmc.zst is not in the index" in problem for problem in report.problems)


def test_a_half_written_store_says_so(tmp_path):
    directory = a_store(tmp_path / "events", index=False)
    (directory / "events.0.hepmc.zst.part").write_bytes(b"still going")
    report = verify_module.verify(directory)
    assert not report.ok
    assert any("unfinished" in problem for problem in report.problems)
    assert any("still being written" in problem for problem in report.problems)


def test_counts_that_do_not_add_up_are_caught(tmp_path):
    directory = a_store(tmp_path / "events")
    path = directory / index_module.NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["events"] = 31
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = verify_module.verify(directory)
    assert any("add up to 30" in problem for problem in report.problems)


def test_a_partial_store_is_valid_and_says_it_is_partial(tmp_path):
    """`stopped: true` is a run that was stopped, not a broken file: its events are real (11 §2)."""
    report = verify_module.verify(a_store(tmp_path / "events", stopped=True))
    assert report.ok
    assert any("partial" in note for note in report.notes)
    assert "partial" in report.index.describe()


# ── the commands ─────────────────────────────────────────────────────────────

def test_store_info_shows_what_the_index_records(tmp_path):
    result = invoke(info, [str(a_store(tmp_path / "events"))])
    assert result.exit_code == 0, result.output
    text = result.output
    assert "eic_5x41_ep" in text and "sha256:" in text
    assert "30" in text and "zst" in text
    assert "2212" in text and "920.0" in text
    assert "7.082e+04 pb" in text
    assert "events.0.hepmc.zst" in text


def test_store_info_can_print_the_index_itself(tmp_path):
    result = invoke(info, [str(a_store(tmp_path / "events")), "--json"])
    payload = json.loads(result.output)
    assert payload["version"] == 1 and len(payload["shards"]) == 3


def test_store_verify_exits_non_zero_on_damage(tmp_path):
    directory = a_store(tmp_path / "events")
    (directory / "events.0.hepmc.zst").unlink()
    result = invoke(verify_command, [str(directory)])
    assert result.exit_code == 1
    assert "is missing" in result.output


def test_store_ls_finds_stores_under_the_results_tree(tmp_path, redirect_results):
    a_store(redirect_results / "PhotoProduction" / "points" / "a_point" / "events")
    result = invoke(list_stores, [])
    assert result.exit_code == 0, result.output
    assert "eic_5x41_ep" in result.output and "zst" in result.output
    assert "complete" in result.output


def test_store_ls_says_when_there_are_none(redirect_results):
    result = invoke(list_stores, [])
    assert result.exit_code == 0 and "no event stores" in result.output


def test_store_ls_has_a_machine_readable_form(tmp_path, redirect_results):
    a_store(redirect_results / "PhotoProduction" / "points" / "a_point" / "events", stopped=True)
    result = invoke(list_stores, ["--json"])
    payload = json.loads(result.output)
    assert payload[0]["events"] == 30 and payload[0]["stopped"] is True
