"""Resolving a store, and refusing what a replay cannot do (P5-S02, 11 §4–5).

A replay is "these events, analysed this way". Two consequences the planner has to enforce, and both
are here: a sweep that would change the events is an error rather than a silently ignored setting,
and identity is the store's hash plus the group's analyses — so a new analysis is a new point while an
analysis *option* is still one generation (03 §4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hekit.adapters import store as store_adapter
from hekit.errors import HepError
from hekit.store import index as index_module


def a_store(directory: Path, *, point: str = "eic_5x41_ep", store_hash: str = "ab") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "events.0.hepmc.zst").write_bytes(b"shard zero")
    (directory / index_module.NAME).write_text(json.dumps({
        "version": 1, "format": "hepmc3-ascii", "compression": "zst", "point": point,
        "hash": "sha256:" + store_hash * 32, "provenance": "../provenance.json",
        "generator": {"tool": "pythia", "version": "8.317"},
        "beams": {"ids": [2212, -11], "energies": [920.0, 27.5]},
        "threads": 1, "seeds": [11], "weights": ["Weight"],
        "xsec_pb": 70818.73, "xsec_err_pb": 2212.24, "events": 10, "stopped": False,
        "shards": [{"file": "events.0.hepmc.zst", "worker": 0, "events": 10, "bytes": 10,
                    "sha256": "c" * 64}],
    }), encoding="utf-8")
    return directory


# ── resolving ────────────────────────────────────────────────────────────────

def test_a_path_to_a_store_resolves(tmp_path):
    store = a_store(tmp_path / "events")
    assert store_adapter.resolve(str(store)) == store


def test_a_point_directory_resolves_to_its_events(tmp_path):
    """`--input results/…/points/eic_5x41_ep` is what a user has in hand."""
    point = tmp_path / "points" / "eic_5x41_ep"
    a_store(point / "events")
    assert store_adapter.resolve(str(point)) == point / "events"


def test_a_point_name_is_looked_up_in_the_results_tree(redirect_results):
    a_store(redirect_results / "PhotoProduction" / "points" / "eic_5x41_ep" / "events")
    found = store_adapter.resolve("eic_5x41_ep", project="PhotoProduction")
    assert found.parent.name == "eic_5x41_ep"


def test_a_store_is_found_even_from_another_project(redirect_results):
    """A replay config rarely lives in the project directory whose events it reads."""
    a_store(redirect_results / "PhotoProduction" / "points" / "eic_5x41_ep" / "events")
    assert store_adapter.resolve("eic_5x41_ep", project="SomethingElse").is_dir()


def test_a_hash_resolves_to_its_store(redirect_results):
    a_store(redirect_results / "P" / "points" / "one" / "events", point="one", store_hash="ab")
    a_store(redirect_results / "P" / "points" / "two" / "events", point="two", store_hash="ef")
    found = store_adapter.resolve("sha256:" + "ef" * 32)
    assert found.parent.name == "two"


def test_an_unknown_reference_says_how_to_find_one(redirect_results):
    with pytest.raises(HepError, match="no event store for 'nothing'"):
        store_adapter.resolve("nothing")
    with pytest.raises(HepError, match="hep store ls"):
        store_adapter.resolve("nothing")


def test_an_empty_input_is_an_error():
    with pytest.raises(HepError, match="is empty"):
        store_adapter.resolve("")


# ── the spec's [source.store] ────────────────────────────────────────────────

def test_the_spec_carries_what_the_index_says(tmp_path):
    """`hep` reads the JSON so `hep-run` does not have to (02 §2): the index stays the source of
    truth, and the C++ side needs no JSON parser."""
    document = store_adapter.store_document(a_store(tmp_path / "events"))
    assert document["compression"] == "zst"
    assert document["shards"] == ["events.0.hepmc.zst"] and document["workers"] == [0]
    assert document["events"] == 10
    assert document["xsec_pb"] == 70818.73 and document["xsec_err_pb"] == 2212.24
    assert document["beam_ids"] == [2212, -11] and document["beam_energies"] == [920.0, 27.5]
    assert document["weights"] == ["Weight"] and document["stopped"] is False
    assert "queue" not in document
    assert store_adapter.store_document(a_store(tmp_path / "events"), queue=16)["queue"] == 16


def test_a_partial_store_is_carried_through(tmp_path):
    store = a_store(tmp_path / "events")
    path = store / index_module.NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["stopped"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert store_adapter.store_document(store)["stopped"] is True


def test_the_origin_line_describes_the_store(tmp_path):
    text = store_adapter.replay_origin(a_store(tmp_path / "events"))
    assert "10 events" in text and "1 zst shards" in text


# ── what a replay may not scan ───────────────────────────────────────────────

class Quantity:
    def __init__(self, kind: str):
        self.type = kind


class Config:
    def __init__(self, **quantities):
        self.quantities = {name: Quantity(kind) for name, kind in quantities.items()}


class Selection:
    def __init__(self, across=(), overlay="", pins=None):
        self.across = list(across)
        self.overlay = overlay
        self.pins = pins or {}


@pytest.mark.parametrize("kind", sorted(store_adapter.GENERATION_TYPES))
def test_a_quantity_that_changes_the_events_is_refused(kind):
    """The step's planner row: a store plus an `energies` quantity is an error with a hint."""
    config = Config(thing=kind)
    with pytest.raises(HepError) as raised:
        store_adapter.check_quantities(config, Selection(across=["thing"]))
    assert f"thing ({kind})" in raised.value.message
    assert "the events already exist" in raised.value.hint
    assert 'tool = "pythia"' in raised.value.hint


def test_an_analysis_quantity_is_allowed():
    config = Config(radius=Quantity("option").type, plugin="analysis")
    store_adapter.check_quantities(config, Selection(across=["radius", "plugin"]))


def test_a_coupled_group_is_checked_too():
    config = Config(a="option", b="energies")
    with pytest.raises(HepError, match=r"b \(energies\)"):
        store_adapter.check_quantities(config, Selection(across=[["a", "b"]]))


def test_an_overlay_and_a_pin_are_checked():
    config = Config(pdf="setting")
    with pytest.raises(HepError, match="pdf"):
        store_adapter.check_quantities(config, Selection(overlay="pdf"))
    with pytest.raises(HepError, match="pdf"):
        store_adapter.check_quantities(config, Selection(pins={"pdf": "#1"}))


def test_a_quantity_the_config_does_not_declare_is_left_to_the_sweep_engine():
    """Not this module's error to raise: the sweep engine already says what it does not know."""
    store_adapter.check_quantities(Config(), Selection(across=["mystery"]))


# ── identity: what makes a replay a new point (11 §4) ────────────────────────

class Point:
    def __init__(self, name: str, analyses: list[str]):
        self.name = name
        self.analyses = analyses
        self.settings = []
        self.beams = None
        self.energies = None
        self.events = 0
        self.seed = None
        self.cards = []


def group(points, store_hash: str):
    from hekit.plan import hashing

    return hashing.group_by_identity(points, tool="store", card_bytes=None, card_text="",
                                     tool_version="", store_hash=store_hash)


def test_two_option_variants_of_one_store_are_one_generation():
    """03 §4 holds for a replay too: the options do not change the events, so one read serves both.

    Hashing the analyses *per point* made two generations that shared a directory, and the second
    quietly overwrote the first — found by replaying a real store (P5-S02).
    """
    groups = group([Point("r04", ["photo_eic:R=0.4"]), Point("r10", ["photo_eic:R=1.0"])],
                   "sha256:" + "ab" * 32)
    assert len(groups) == 1
    identity, members = groups[0]
    assert [point.name for point in members] == ["r04", "r10"]
    assert identity.inputs["analyses"] == ["photo_eic:R=0.4", "photo_eic:R=1.0"]


def test_a_different_analysis_set_is_a_different_point():
    """"Replaying it with a new analysis is a new point" (11 §4)."""
    one = group([Point("a", ["photo_eic"])], "sha256:" + "ab" * 32)[0][0]
    two = group([Point("a", ["photo_eic", "photo_5x41"])], "sha256:" + "ab" * 32)[0][0]
    assert one.hash != two.hash


def test_a_different_store_is_a_different_point():
    one = group([Point("a", ["photo_eic"])], "sha256:" + "ab" * 32)[0][0]
    two = group([Point("a", ["photo_eic"])], "sha256:" + "cd" * 32)[0][0]
    assert one.hash != two.hash


def test_replaying_the_same_store_the_same_way_is_the_same_point():
    """Which is what lets the skip rule recognise a replay it has already done (07 §1)."""
    one = group([Point("a", ["photo_eic"])], "sha256:" + "ab" * 32)[0][0]
    two = group([Point("a", ["photo_eic"])], "sha256:" + "ab" * 32)[0][0]
    assert one.hash == two.hash
