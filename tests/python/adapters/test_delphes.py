"""The external Delphes stage (P7-S08, 05 §5).

Delphes is an analyzer with a process behind it, not a generator, so what is worth pinning is the wiring:
which file it reads, which phase it runs in, and what is left behind afterwards.

The phase is the part that is *not* what the design assumed. 05 §5 described a FIFO tee with Delphes
reading it alongside `hep-run`; `DelphesHepMC3` sizes its input and skips anything of length zero, so
it cannot read a pipe at all. The tee writes a file and Delphes runs after — which is why the stage's
phase has its own test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "utils" / "python"))

from hekit.adapters import delphes                                       # noqa: E402
from hekit.errors import HepError                                        # noqa: E402


class Delphes:
    card = "cards/cms.tcl"
    keep_events = False


class Config:
    project = "proj"
    delphes = Delphes()
    path = Path("/cfg/eic.toml")
    tools: dict = {}


class Group:
    name = "p1"

    class identity:
        hash = "a" * 64


class NoDetector(Config):
    class delphes:
        card = ""
        keep_events = False


# ── when it is asked for ─────────────────────────────────────────────────────

def test_a_card_turns_it_on():
    assert delphes.enabled(Config()) is True
    assert delphes.enabled(NoDetector()) is False


def test_the_card_resolves_next_to_the_config():
    assert delphes.card_path(Config()) == Path("/cfg/cards/cms.tcl")


def test_an_absolute_card_is_left_alone():
    class Absolute(Config):
        class delphes:
            card = "/opt/delphes/cards/cms.tcl"
            keep_events = False

    assert delphes.card_path(Absolute()) == Path("/opt/delphes/cards/cms.tcl")


def test_asking_for_a_stage_without_a_card_is_an_error():
    with pytest.raises(HepError) as raised:
        delphes.card_path(NoDetector())
    assert "no card" in str(raised.value)


# ── the wiring ───────────────────────────────────────────────────────────────

def test_the_analyzer_points_at_the_intermediate(tmp_path):
    document = delphes.analyzer_document(tmp_path)
    assert document["kind"] == "delphes"
    assert document["dir"] == str(tmp_path / delphes.FIFO_NAME)


def test_the_stage_reads_the_intermediate_and_writes_root(tmp_path):
    stage = delphes.stage(Config(), Group(), tmp_path)
    assert stage.role == "detector"
    assert str(tmp_path / delphes.OUTPUT) in stage.argv
    assert str(tmp_path / delphes.FIFO_NAME) in stage.argv
    assert str(Path("/cfg/cards/cms.tcl")) in stage.argv
    assert stage.produces == [tmp_path / delphes.OUTPUT]


def test_the_stage_clears_a_stale_output_first(tmp_path):
    """Delphes refuses to overwrite, which is a good rule and a bad interaction with `--rerun`."""
    stage = delphes.stage(Config(), Group(), tmp_path)
    assert stage.argv[0] == "sh"
    assert "rm -f" in stage.argv[2]


def test_the_stage_does_not_claim_a_phase_of_its_own(tmp_path):
    """The planner sets it, because it depends on which phase `hep-run` ended up in."""
    stage = delphes.stage(Config(), Group(), tmp_path)
    assert stage.resolved_phase == 1, "the role's default; the planner overrides it"


# ── the sidecar ──────────────────────────────────────────────────────────────

def local_config(card: Path):
    """A config whose card really exists. A nested class body cannot see the enclosing local."""
    class Local(Config):
        pass

    Local.delphes = type("D", (), {"card": str(card), "keep_events": False})()
    return Local()


def test_the_sidecar_names_what_produced_the_root_file(tmp_path):
    card = tmp_path / "cms.tcl"
    card.write_text("set X 1\n", encoding="utf-8")

    found = delphes.sidecar(local_config(card), Group(), tmp_path)
    assert found["point"] == "p1"
    assert found["hash"] == "a" * 64
    assert found["card"] == str(card)
    assert len(found["card_sha256"]) == 64, "so a changed card is visible without diffing it"
    assert found["output"].endswith(delphes.OUTPUT)


def test_the_sidecar_is_written_beside_the_root_file(tmp_path):
    import json

    card = tmp_path / "cms.tcl"
    card.write_text("set X 1\n", encoding="utf-8")

    path = delphes.write_sidecar(local_config(card), Group(), tmp_path)
    assert path.name == delphes.SIDECAR
    assert json.loads(path.read_text(encoding="utf-8"))["point"] == "p1"


def test_a_missing_card_still_produces_a_sidecar(tmp_path):
    """A card that has been moved since the run should not stop the run being described."""
    found = delphes.sidecar(Config(), Group(), tmp_path)
    assert found["card_sha256"] == ""
