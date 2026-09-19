"""The rules every generator adapter shares (P7-S01, 04 §1, §8).

The framework's job is that five adapters do not become five slightly different pipelines, so the
things that must be identical between them are tested once, here, without running any generator:
which keys a card may not set, what counts as the right number of events, where an executable comes
from, and what a prepare-cache key covers.

The cache is the part worth reading twice. A seed-replica study should integrate **once**, and that
is true only if the hash ignores exactly the right things — the seed and the event count, and
nothing else.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "utils" / "python"))

from hekit.adapters import base, cache, registry
from hekit.errors import HepError


# ── the registry ─────────────────────────────────────────────────────────────

def test_the_known_tools_are_the_designs_tools():
    """04 §2's capability matrix, in its own order — which is what `[generator].tool` documents."""
    assert registry.tools() == ("pythia", "sherpa", "herwig", "whizard", "madgraph", "store")


def test_an_unwritten_adapter_says_which_step_brings_it():
    """The difference between "you misspelled it" and "it is not built yet" is worth keeping."""
    with pytest.raises(HepError) as raised:
        registry.adapter_for("sherpa")
    assert "not written yet" in str(raised.value) and "P7-S03" in str(raised.value)


def test_an_unknown_tool_is_a_different_error():
    with pytest.raises(HepError) as raised:
        registry.adapter_for("pythai")
    assert "no generator called" in str(raised.value)
    assert "pythia" in str(raised.value), "and it suggests the one that was meant"


def test_registering_makes_a_tool_valid_everywhere():
    """The schema reads its choices from here, so the two cannot disagree (they used to)."""
    from hekit.config import schema

    try:
        registry.register("madeup", object(), description="a test")
        assert "madeup" in registry.tools()
        assert "madeup" in schema.GENERATOR.fields["tool"].allowed()
    finally:
        registry.unregister("madeup")
    assert "madeup" not in registry.tools()


# ── beams (04 §8) ────────────────────────────────────────────────────────────

def test_a_card_that_sets_beams_is_refused_for_every_tool():
    """Each tool spells it differently; the rule is the same, and so is the message."""
    for tool, keys in base.BEAM_KEYS.items():
        with pytest.raises(HepError) as raised:
            base.check_beam_keys(tool, [keys[0]])
        assert "sets the beams" in str(raised.value)
        assert "[beams]" in str(raised.value)


def test_beam_keys_are_matched_without_case_or_spacing():
    with pytest.raises(HepError):
        base.check_beam_keys("pythia", ["  Beams:eCM  "])


def test_an_ordinary_setting_is_left_alone():
    base.check_beam_keys("pythia", ["PDF:pSet", "MultipartonInteractions:pT0Ref"])
    base.check_beam_keys("sherpa", ["EVENTS", "SCALES"])


def test_a_tool_with_no_declared_beam_keys_allows_everything():
    """A new adapter is not silently strict before its key list is written."""
    base.check_beam_keys("fake", ["beams", "anything"])


# ── event counts (04 §8) ─────────────────────────────────────────────────────

def test_the_exact_count_is_required():
    base.check_event_count(300, 300, tool="sherpa")
    with pytest.raises(HepError) as raised:
        base.check_event_count(300, 250, tool="sherpa")
    assert "-50" in str(raised.value), "signed from the run's point of view"
    with pytest.raises(HepError):
        base.check_event_count(300, 320, tool="sherpa")


def test_an_open_ended_run_has_no_count_to_check():
    """`events = 0` means "whatever the card says", so there is nothing to compare."""
    base.check_event_count(0, 17, tool="sherpa")


# ── executables (04 §8, N6) ──────────────────────────────────────────────────

def test_the_machine_file_wins_over_path():
    class Config:
        tools = {"sherpa": {"exe": "/opt/sherpa/bin/Sherpa"}}

    assert base.executable_for("sherpa", Config()) == "/opt/sherpa/bin/Sherpa"


def test_without_a_machine_entry_the_name_is_looked_up():
    class Config:
        tools: dict = {}

    # `sh` is on every machine this runs on; the point is that an absolute path is found, not baked in.
    assert base.executable_for("sh", Config()).endswith("sh")


def test_an_unknown_tool_falls_back_to_its_own_name():
    class Config:
        tools: dict = {}

    assert base.executable_for("definitely-not-installed", Config()) == "definitely-not-installed"


# ── the FIFO seam ────────────────────────────────────────────────────────────

def test_the_fifo_lives_beside_the_results(tmp_path):
    """Not in a shared `/tmp` path: that is how two runs corrupted each other's events (00/B19)."""
    path = base.fifo_path(tmp_path)
    assert path.parent == tmp_path
    made = base.make_fifo(path)
    assert made.is_fifo()


def test_a_stale_fifo_is_replaced(tmp_path):
    path = base.fifo_path(tmp_path)
    base.make_fifo(path)
    base.make_fifo(path)                       # must not raise "file exists"
    assert path.is_fifo()


def test_a_stream_source_reads_the_fifo_uncompressed(tmp_path):
    """A pipe between two processes on one machine: compressing it spends CPU to save nothing."""
    document = base.stream_source(base.fifo_path(tmp_path))
    assert document["kind"] == "stream"
    assert document["inputs"] == [str(tmp_path / base.FIFO_NAME)]
    assert document["store"]["compression"] == "none"
    assert document["store"]["shards"] == [], "a stream has no index (11 §4)"


# ── the prepare cache (04 §1) ────────────────────────────────────────────────

SEED_CARD = """# rendered for point A
seed = 11
events = 300
PDF:pSet = MSTW2008lo68cl
"""

OTHER_SEED = """# rendered for point B
seed = 22
events = 300
PDF:pSet = MSTW2008lo68cl
"""

MORE_EVENTS = """# rendered for point C
seed = 11
events = 900000
PDF:pSet = MSTW2008lo68cl
"""

DIFFERENT_PHYSICS = """# rendered for point D
seed = 11
events = 300
PDF:pSet = NNPDF23_lo_as_0130_qed
"""


def test_two_seeds_of_one_point_share_a_prepare_hash():
    """The whole reason the cache exists: a seed study integrates once."""
    assert cache.prepare_hash(SEED_CARD, tool="sherpa") == \
        cache.prepare_hash(OTHER_SEED, tool="sherpa")


def test_the_event_count_does_not_change_the_hash():
    assert cache.prepare_hash(SEED_CARD, tool="sherpa") == \
        cache.prepare_hash(MORE_EVENTS, tool="sherpa")


def test_different_physics_is_a_different_grid():
    assert cache.prepare_hash(SEED_CARD, tool="sherpa") != \
        cache.prepare_hash(DIFFERENT_PHYSICS, tool="sherpa")


def test_a_new_version_of_the_tool_invalidates_the_grid():
    """A grid written by one version is not guaranteed readable by the next (04 §8)."""
    assert cache.prepare_hash(SEED_CARD, tool="sherpa", version="3.0.5") != \
        cache.prepare_hash(SEED_CARD, tool="sherpa", version="3.1.0")


def test_a_different_tool_is_a_different_grid():
    assert cache.prepare_hash(SEED_CARD, tool="sherpa") != \
        cache.prepare_hash(SEED_CARD, tool="whizard")


def test_comments_and_whitespace_do_not_change_the_hash():
    """A rendered card's header carries the point's name and a timestamp."""
    noisy = "# a different header entirely\n\n  seed = 11  \n\nevents = 300\n" \
            "   PDF:pSet   =   MSTW2008lo68cl\n"
    assert cache.prepare_hash(noisy, tool="sherpa") == cache.prepare_hash(SEED_CARD, tool="sherpa")


def test_the_stable_card_keeps_the_physics_and_drops_the_rest():
    stable = cache.stable_card(SEED_CARD, "sherpa")
    assert "PDF:pSet = MSTW2008lo68cl" in stable
    assert "seed" not in stable and "events" not in stable


# ── cache entries ────────────────────────────────────────────────────────────

@pytest.fixture
def cache_root(tmp_path, monkeypatch):
    from hekit.env import paths

    monkeypatch.setattr(paths, "results_root", lambda: tmp_path / "results")
    return tmp_path / "results"


def test_an_entry_is_not_ready_until_it_is_marked(cache_root):
    entry = cache.lookup("proj", "sherpa", SEED_CARD)
    entry.directory.mkdir(parents=True)
    (entry.directory / "grid.dat").write_text("x", encoding="utf-8")
    assert not entry.ready, "a directory with files in it is not a finished prepare"

    cache.mark_ready(entry, version="3.0.5", produced=[entry.directory / "grid.dat"])
    assert entry.ready
    assert entry.meta()["version"] == "3.0.5"


def test_marking_refuses_when_the_promised_output_is_missing(cache_root):
    """Otherwise a failed prepare would be cached and every later point would reuse nothing."""
    entry = cache.lookup("proj", "sherpa", SEED_CARD)
    entry.directory.mkdir(parents=True)
    with pytest.raises(HepError) as raised:
        cache.mark_ready(entry, produced=[entry.directory / "grid.dat"])
    assert "did not produce" in str(raised.value)
    assert not entry.ready


def test_invalidate_leaves_the_files_for_inspection(cache_root):
    entry = cache.lookup("proj", "sherpa", SEED_CARD)
    entry.directory.mkdir(parents=True)
    (entry.directory / "grid.dat").write_text("x", encoding="utf-8")
    cache.mark_ready(entry, produced=[entry.directory / "grid.dat"])
    cache.invalidate(entry)
    assert not entry.ready
    assert (entry.directory / "grid.dat").is_file(), "a failure has to be inspectable"


def test_the_entry_path_is_the_one_the_design_names(cache_root):
    entry = cache.lookup("proj", "sherpa", SEED_CARD)
    assert entry.directory.parent.parent.name == ".cache"
    assert entry.directory.parent.name == "sherpa"
    assert entry.directory.name == entry.hash


def test_entries_lists_what_is_there(cache_root):
    for card in (SEED_CARD, DIFFERENT_PHYSICS):
        entry = cache.lookup("proj", "sherpa", card)
        entry.directory.mkdir(parents=True)
    assert len(cache.entries("proj")) == 2
    assert len(cache.entries("proj", tool="whizard")) == 0
    assert cache.entries("nothing-here") == []


# ── the stage shape ──────────────────────────────────────────────────────────

def test_a_stage_becomes_what_the_planner_shows():
    stage = base.Stage(name="sherpa-generate", role="generate",
                       argv=["Sherpa", "-e", "300"], note="writes the FIFO")
    plan_stage = stage.to_plan_stage()
    assert plan_stage.name == "sherpa-generate"
    assert plan_stage.role == "generate"
    assert plan_stage.command == ["Sherpa", "-e", "300"]
    assert plan_stage.note == "writes the FIFO"


def test_capabilities_refuse_loudly_when_a_tool_is_absent():
    found = base.Capabilities(tool="sherpa", available=False, detail="not on PATH")
    with pytest.raises(HepError) as raised:
        found.require()
    assert "not available" in str(raised.value) and "not on PATH" in str(raised.value)
    base.Capabilities(tool="sherpa", available=True).require()
