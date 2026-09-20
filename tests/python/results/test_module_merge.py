"""Combining seed replicas of a module's objects (P8-S01, 07 §3).

`rivet-merge -e` cannot do this half: it re-runs each Rivet analysis' `finalize` from the `/RAW/`
copies, and a user module has neither — its `finalize` is in a shared library and its objects have no
raw twin. So `hekit` merges them, and the rule follows from the scaling contract: a module's objects
are already in cross-section units, so replicas **average**, they do not add.

That is the test that matters. Adding two replicas of the same point would give twice the
cross-section, and it would look entirely plausible.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "utils" / "python"))

yoda = pytest.importorskip("yoda")

from hekit.errors import HepError                                        # noqa: E402
from hekit.results import merge                                          # noqa: E402


def histo(path: str, weight: float):
    made = yoda.Histo1D(4, 0.0, 4.0, path)
    for index in range(4):
        made.fill(index + 0.5, weight)
    return made


def replica(directory: Path, *, events: int, weight: float, name: str = "/ToyJets/h") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "run.summary.json").write_text(
        json.dumps({"run": {"events": events}}), encoding="utf-8")
    path = directory / "analysis.yoda"
    yoda.write([histo(name, weight), histo("/photo_eic/d01-x01-y01", weight)], str(path))
    return path


# ── the rule ─────────────────────────────────────────────────────────────────

def test_equal_replicas_average_rather_than_add():
    """Two runs of the same point measure the same σ. Adding them would double it."""
    one, two = histo("/ToyJets/h", 10.0), histo("/ToyJets/h", 10.0)
    merged = merge.merge_objects([one, two], [1000.0, 1000.0])
    assert merged.sumW() == pytest.approx(one.sumW())


def test_a_bigger_replica_counts_for_more():
    """Σ(wᵢ·Oᵢ)/Σwᵢ: a run that saw three times as much pulls the answer three times as hard."""
    small, large = histo("/ToyJets/h", 4.0), histo("/ToyJets/h", 8.0)
    merged = merge.merge_objects([small, large], [1000.0, 3000.0])
    # (1·4 + 3·8) / 4 = 7 per bin, against 6 for an unweighted mean.
    assert merged.sumW() == pytest.approx(7.0 * 4)


def test_an_unscaled_object_is_summed():
    """A raw count means the total, and the caller has to say which objects those are."""
    one, two = histo("/ToyJets/n", 10.0), histo("/ToyJets/n", 10.0)
    merged = merge.merge_objects([one, two], [1000.0, 1000.0], unscaled=["/ToyJets/n"])
    assert merged.sumW() == pytest.approx(one.sumW() * 2)


def test_one_replica_is_itself():
    one = histo("/ToyJets/h", 10.0)
    assert merge.merge_objects([one], [1000.0]).sumW() == pytest.approx(one.sumW())


def test_replicas_that_contributed_nothing_are_an_error():
    one = histo("/ToyJets/h", 10.0)
    with pytest.raises(HepError) as raised:
        merge.merge_objects([one], [0.0])
    assert "contributed nothing" in str(raised.value)


def test_mismatched_weights_are_an_error():
    one = histo("/ToyJets/h", 10.0)
    with pytest.raises(HepError):
        merge.merge_objects([one, one], [1.0])


# ── picking out the module's objects ─────────────────────────────────────────

def test_only_the_modules_objects_are_taken():
    """Rivet's are `rivet-merge -e`'s business; this rule is wrong for a ratio."""
    found = merge.module_paths(
        ["/ToyJets/h", "/ToyJets/n", "/photo_eic/d01-x01-y01", "/RAW/_XSEC"], ["ToyJets"])
    assert found == ["/ToyJets/h", "/ToyJets/n"]


def test_a_file_merge_writes_only_the_module_objects(tmp_path):
    first = replica(tmp_path / "s1", events=1000, weight=10.0)
    second = replica(tmp_path / "s2", events=1000, weight=10.0)

    out = merge.merge_files([first, second], ["ToyJets"], tmp_path / "merged.yoda")
    objects = yoda.read(str(out))
    assert sorted(objects) == ["/ToyJets/h"]
    assert objects["/ToyJets/h"].sumW() == pytest.approx(40.0), "the mean, not the sum"


def test_the_weights_come_from_each_replicas_summary(tmp_path):
    first = replica(tmp_path / "s1", events=1000, weight=4.0)
    second = replica(tmp_path / "s2", events=3000, weight=8.0)

    out = merge.merge_files([first, second], ["ToyJets"], tmp_path / "merged.yoda")
    assert yoda.read(str(out))["/ToyJets/h"].sumW() == pytest.approx(7.0 * 4)


def test_a_replica_with_no_summary_is_refused(tmp_path):
    first = replica(tmp_path / "s1", events=1000, weight=10.0)
    (tmp_path / "s1" / "run.summary.json").unlink()
    with pytest.raises(HepError) as raised:
        merge.merge_files([first], ["ToyJets"], tmp_path / "merged.yoda")
    assert "run.summary.json" in str(raised.value)


def test_a_file_with_no_module_objects_says_so(tmp_path):
    first = replica(tmp_path / "s1", events=1000, weight=10.0)
    with pytest.raises(HepError) as raised:
        merge.merge_files([first], ["Nothing"], tmp_path / "merged.yoda")
    assert "no module objects" in str(raised.value)


def test_a_replica_missing_an_object_is_refused(tmp_path):
    first = replica(tmp_path / "s1", events=1000, weight=10.0)
    second = tmp_path / "s2" / "analysis.yoda"
    (tmp_path / "s2").mkdir(parents=True)
    (tmp_path / "s2" / "run.summary.json").write_text(
        json.dumps({"run": {"events": 1000}}), encoding="utf-8")
    yoda.write([histo("/ToyJets/other", 1.0)], str(second))

    with pytest.raises(HepError) as raised:
        merge.merge_files([first, second], ["ToyJets"], tmp_path / "merged.yoda")
    assert "missing from some replicas" in str(raised.value)
