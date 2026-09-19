"""`hep events`: looking at events (P5-S03, 06 §5).

This is the replacement for Pythia's fixed-width `event.list()`, so what matters is that the numbers
are right (pT, η, φ derived from the four-momentum), that the roles are classified the way a reader
expects, and that a compressed shard can be looked at without decompressing all of it.

The fixture is a HepMC3 file written here rather than a generated one: the renderer is being tested,
not the generator.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from hekit.errors import HepError
from hekit.term import events as events_module
from hekit.term.cli import events as events_command

HepMC3 = pytest.importorskip("pyHepMC3").HepMC3


def an_event_file(path: Path, *, events: int = 2) -> Path:
    """A small but honest HepMC3 file: beams, a hard pair, and two final particles."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = HepMC3.WriterAscii(str(path))
    for number in range(events):
        event = HepMC3.GenEvent(HepMC3.Units.GEV, HepMC3.Units.MM)
        event.set_event_number(number)
        beam_a = HepMC3.GenParticle(HepMC3.FourVector(0.0, 0.0, 920.0, 920.0), 2212, 4)
        beam_b = HepMC3.GenParticle(HepMC3.FourVector(0.0, 0.0, -27.5, 27.5), -11, 4)
        # pT = 5, eta = 0 exactly, phi = 0: the numbers in the table are checkable by hand.
        out_a = HepMC3.GenParticle(HepMC3.FourVector(5.0, 0.0, 0.0, 5.1), 211, 1)
        out_b = HepMC3.GenParticle(HepMC3.FourVector(-3.0, 4.0, 0.0, 5.1), -211, 1)
        out_a.set_generated_mass(0.14)
        out_b.set_generated_mass(0.14)
        vertex = HepMC3.GenVertex()
        vertex.add_particle_in(beam_a)
        vertex.add_particle_in(beam_b)
        vertex.add_particle_out(out_a)
        vertex.add_particle_out(out_b)
        event.add_vertex(vertex)
        event.weights().append(1.0)
        writer.write_event(event)
    writer.close()
    return path


# ── the numbers ──────────────────────────────────────────────────────────────

def test_kinematics_are_derived_from_the_four_momentum(tmp_path):
    found = events_module.read_events(an_event_file(tmp_path / "events.hepmc"), limit=1)
    assert len(found) == 1
    pion = next(entry for entry in found[0].particles if entry.pid == 211)
    assert pion.pt == pytest.approx(5.0)
    assert pion.eta == pytest.approx(0.0)
    assert pion.phi == pytest.approx(0.0)
    assert pion.mass == pytest.approx(0.14)

    other = next(entry for entry in found[0].particles if entry.pid == -211)
    assert other.pt == pytest.approx(5.0)
    assert other.phi == pytest.approx(math.atan2(4.0, -3.0))


def test_a_beam_along_z_has_no_finite_eta(tmp_path):
    """Infinite rather than a huge number, and the table shows an em dash rather than nonsense."""
    found = events_module.read_events(an_event_file(tmp_path / "events.hepmc"), limit=1)
    beam = next(entry for entry in found[0].particles if entry.pid == 2212)
    assert math.isinf(beam.eta) and beam.eta > 0
    assert beam.pt == 0.0


def test_particles_are_named_not_numbered(tmp_path):
    found = events_module.read_events(an_event_file(tmp_path / "events.hepmc"), limit=1)
    names = {entry.name for entry in found[0].particles}
    assert "p" in names and "pi+" in names and "pi-" in names
    assert "e+" in names


def test_an_unknown_pdg_id_falls_back_to_the_number():
    assert events_module.pdg_name(9999999) == "9999999"


# ── roles and selection ──────────────────────────────────────────────────────

def test_roles_follow_the_hepmc_status(tmp_path):
    found = events_module.read_events(an_event_file(tmp_path / "events.hepmc"), limit=1)[0]
    roles = {entry.pid: entry.role for entry in found.particles}
    assert roles[2212] == "beam" and roles[-11] == "beam"
    assert roles[211] == "final" and roles[-211] == "final"


def test_final_and_hard_select_what_they_say(tmp_path):
    found = events_module.read_events(an_event_file(tmp_path / "events.hepmc"), limit=1)[0]
    final = events_module.select(found, final=True)
    assert {entry.pid for entry in final} == {211, -211}
    hard = events_module.select(found, hard=True)
    assert {entry.pid for entry in hard} == {2212, -11}
    assert len(events_module.select(found)) == 4
    assert len(events_module.select(found, limit=2)) == 2


def test_mothers_and_daughters_are_linked(tmp_path):
    found = events_module.read_events(an_event_file(tmp_path / "events.hepmc"), limit=1)[0]
    pion = next(entry for entry in found.particles if entry.pid == 211)
    beam = next(entry for entry in found.particles if entry.pid == 2212)
    assert pion.mothers and beam.index in pion.mothers
    assert beam.daughters and pion.index in beam.daughters


def test_the_summary_labels_the_running_cross_section(tmp_path):
    """A per-event σ is the generator's running estimate; the run's value lives in the index (11 §4)."""
    found = events_module.read_events(an_event_file(tmp_path / "events.hepmc"), limit=1)[0]
    found.xsec_pb = 1234.0
    text = events_module.summary_of(found)
    assert "4 particles, 2 final" in text
    assert "sigma(so far)" in text


# ── reading compressed shards without decompressing all of them ──────────────

@pytest.mark.parametrize("codec,command", [("gz", "gzip"), ("zst", "zstd")])
def test_a_compressed_shard_is_read(tmp_path, codec, command):
    if shutil.which(command) is None:                    # pragma: no cover - environment
        pytest.skip(f"{command} is not installed")
    plain = an_event_file(tmp_path / "events.hepmc", events=5)
    compressed = tmp_path / f"events.hepmc.{codec}"
    with open(compressed, "wb") as handle:
        subprocess.run([command, "-c", str(plain)], stdout=handle, check=True)

    found = events_module.read_events(compressed, limit=2)
    assert len(found) == 2, "only what was asked for, without decompressing the rest"
    assert [event.number for event in found] == [0, 1]


def test_a_store_directory_reads_its_first_shard(tmp_path):
    """Every shard is a valid sample on its own (11 §1), so the first one answers the question."""
    import json

    store = tmp_path / "events"
    an_event_file(store / "events.0.hepmc", events=3)
    (store / "events.index.json").write_text(json.dumps({
        "version": 1, "format": "hepmc3-ascii", "compression": "none", "events": 3,
        "shards": [{"file": "events.0.hepmc", "worker": 0, "events": 3}],
    }), encoding="utf-8")
    assert len(events_module.read_events(store, limit=3)) == 3


def test_a_directory_that_is_not_a_store_is_refused(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(HepError):
        events_module.read_events(tmp_path / "empty")


# ── rendering ────────────────────────────────────────────────────────────────

def render(target, *arguments) -> str:
    result = CliRunner().invoke(events_command, [str(target), *arguments], obj={"plain": True})
    assert result.exit_code == 0, result.output
    return result.output


def test_the_table_is_printed(tmp_path):
    """The step's row: `hep events <store> -n 2 --final` prints a table."""
    text = render(an_event_file(tmp_path / "events.hepmc", events=3), "-n", "2", "--final")
    assert "event 0" in text and "event 1" in text
    assert "particle" in text and "pT" in text and "eta" in text
    assert "pi+" in text and "pi-" in text
    assert "p " not in text.split("event 0")[1].split("\n")[2], "final-state only: no beams"
    assert "2 final" in text


def test_the_tree_is_printed(tmp_path):
    text = render(an_event_file(tmp_path / "events.hepmc"), "-n", "1", "--tree")
    assert "event 0" in text
    assert "p" in text and "pi+" in text
    assert "└" in text or "->" in text or "-" in text


def test_a_file_can_be_given_with_from(tmp_path):
    path = an_event_file(tmp_path / "somewhere.hepmc")
    result = CliRunner().invoke(events_command, ["--from", str(path), "-n", "1"],
                                obj={"plain": True})
    assert result.exit_code == 0, result.output
    assert "event 0" in result.output


def test_an_unknown_target_says_how_to_find_one(redirect_results):
    result = CliRunner().invoke(events_command, ["nothing_like_this"], obj={"plain": True})
    assert result.exit_code != 0
    assert "no events for" in str(result.exception) or "no events for" in result.output


def test_with_nothing_to_look_at_it_says_so(redirect_results):
    result = CliRunner().invoke(events_command, [], obj={"plain": True})
    assert result.exit_code != 0
    assert "no event stores" in str(result.exception) or "no event stores" in result.output
