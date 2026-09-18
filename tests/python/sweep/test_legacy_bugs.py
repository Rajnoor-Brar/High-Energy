"""The four sweep bugs of 00 §4.1, each shown fixed.

Until P4-S06 every test here ran the legacy planner first to demonstrate the old behaviour and then
the new one. The tools are retired now, so what is left is the *new* behaviour plus what was measured
of the old, recorded here rather than lost:

| Finding | What the legacy planner did | Measured |
|---|---|---|
| 00/B6 | `--overlay` rebuilt the groups from a flat name list, so a coupled `a+b` scan became a grid: 4 points became **8** | reproduced against `rivpyth_common` before it was retired |
| 00/B7 | the file's own `[sweep].across` was judged before a `--study`'s, so a study could be refused for a scan it did not use | reproduced |
| 00/B8 | quantity **values were rounded** when rendered into a tag, so 3.15 and 3.1499 collided | reproduced |
| 00/B9 | the same rounding reached the *card*, changing the physics a point ran | reproduced |
| 00/B22 | an all-digit selector was read as a **position**, so `pthatmin=6` meant "the 6th value" and the value 6 could not be pinned at all (it raised "outside 1..4") | reproduced |

The golden plan fixtures (`tests/golden/legacy_plan/*.json`, 18 cases) still hold the old planner's
actual output, and `tests/python/plan/test_plan_render.py` compares against them — so the evidence
outlives the code, which is the point of freezing fixtures rather than tools.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hekit import sweep
from hekit.config import load_config
from hekit.errors import HepError
from hekit.sweep import quantity as qt

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def write(tmp_path: Path):
    def writer(text: str, name: str) -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path
    return writer


# ── 00/B6: --overlay must not re-group a coupled scan ────────────────────────


V2_COUPLED = """\
schema = 2

[run]
name    = "x"
events  = 100
seed    = 1
threads = 1

[generator]
tool = "pythia"
card = "photo_ep.cmnd"

[rivet]
analyses = ["photo_eic"]

[sweep]
across = ["a+b", "c"]

[quantity.a]
type   = "setting"
key    = "A:one"
values = [1, 2]
tags   = ["a1", "a2"]

[quantity.b]
type   = "setting"
key    = "B:two"
values = [10, 20]
tags   = ["b1", "b2"]

[quantity.c]
type   = "setting"
key    = "C:three"
values = [100, 200]
tags   = ["c1", "c2"]
"""


def test_overlay_alone_keeps_the_coupling(write):
    config = load_config(write(V2_COUPLED, "v2.toml"), machine_file=None)
    selection = sweep.select(config, overlay="c")
    assert selection.groups == [["a", "b"], ["c"]]
    points = sweep.expand(config, selection)
    assert len(points) == 4
    assert [point.suffix for point in points] == ["a1_b1_c1", "a1_b1_c2", "a2_b2_c1", "a2_b2_c2"]
    assert selection.overlay == ["c"]


def test_style_still_regroups_when_asked(write):
    """`--style grid` is an explicit request to uncouple, and must keep working."""
    config = load_config(write(V2_COUPLED, "v2.toml"), machine_file=None)
    assert len(sweep.expand(config, sweep.select(config, across="a+b,c"))) == 4
    assert len(sweep.expand(config, sweep.select(config, across="a,b,c", style="grid"))) == 8
    assert len(sweep.expand(config, sweep.select(config, across="a,b", style="together"))) == 2


# ── 00/B7: sweep-dependent rules belong to the selected scan ─────────────────

V2_MERGE = V2_COUPLED.replace('across = ["a+b", "c"]', 'across = ["a"]') + """
[plot]
merge = "yodamerge"

[quantity.replica]
type   = "seed"
values = [11, 22]
tags   = ["s11", "s22"]

[study.replicas]
across = ["replica"]
"""


def test_the_scan_that_runs_decides(write):
    config = load_config(write(V2_MERGE, "v2merge.toml"), machine_file=None)   # loads fine
    selection = sweep.select(config, study="replicas")                         # seed-only: allowed
    assert [point.suffix for point in sweep.expand(config, selection)] == ["s11", "s22"]
    with pytest.raises(HepError, match="statistically equivalent"):
        sweep.select(config)                                                   # the default scan is not


# ── 00/B9: value rendering must not lose precision ───────────────────────────


def test_values_render_losslessly():
    assert qt.text_value(0.123456789) == "0.123456789"
    assert qt.text_value(1.0) == "1.0"
    assert qt.text_value(0.12345671) != qt.text_value(0.12345672)
    assert qt.text_value(True) == "on" and qt.text_value(False) == "off"
    assert qt.text_value(6) == "6"
    assert qt.text_value([41, 5]) == "41x5"


def test_close_values_get_distinct_tags(write):
    """Without declared tags a tag comes from the value, so rounding used to collide."""
    text = V2_COUPLED.replace("values = [1, 2]\ntags   = [\"a1\", \"a2\"]",
                              "values = [0.12345671, 0.12345672]")
    config = load_config(write(text, "close.toml"), machine_file=None)
    points = sweep.expand(config, sweep.select(config, across="a"))
    assert [point.suffix for point in points] == ["0.12345671", "0.12345672"]


# ── 00/B22: numeric values must be pinnable ──────────────────────────────────

V2_PIN = V2_COUPLED.replace('across = ["a+b", "c"]', 'across = ["a"]') + """
[quantity.pthatmin]
type   = "setting"
key    = "PhaseSpace:pTHatMin"
values = [2.0, 3.0, 4.0, 6.0]
tags   = ["pth2", "pth3", "pth4", "pth6"]
"""


def test_a_number_pins_the_value(write):
    config = load_config(write(V2_PIN, "v2pin.toml"), machine_file=None)
    points = sweep.expand(config, sweep.select(config, pins=("pthatmin=6",)))
    assert all(point.suffix.endswith("pth6") for point in points)
    settings = {assignment.key: assignment.value for assignment in points[0].settings}
    assert settings["PhaseSpace:pTHatMin"] == 6.0


def test_selector_precedence_is_tag_then_value_then_index(write):
    config = load_config(write(V2_PIN, "v2pin.toml"), machine_file=None)
    quantity = config.quantities["pthatmin"]
    assert qt.resolve_selector(quantity, "pth3", "--pin") == 1          # a tag
    assert qt.resolve_selector(quantity, 4.0, "--pin") == 2             # a value
    assert qt.resolve_selector(quantity, "4", "--pin") == 2             # the same value as text
    assert qt.resolve_selector(quantity, "#1", "--pin") == 0            # an explicit index
    with pytest.raises(HepError, match="is outside 1..4"):
        qt.resolve_selector(quantity, "#9", "--pin")


def test_an_unmatched_selector_lists_the_choices(write):
    config = load_config(write(V2_PIN, "v2pin.toml"), machine_file=None)
    with pytest.raises(HepError) as raised:
        sweep.select(config, pins=("pthatmin=5",))
    assert "matches no tag or value" in raised.value.message
    assert "pth2" in raised.value.hint and "#N" in raised.value.hint


def test_a_tag_that_looks_like_a_number_still_wins(write):
    """A tag is tried before the values, so numeric tags keep working."""
    text = V2_PIN.replace('tags   = ["pth2", "pth3", "pth4", "pth6"]', 'tags   = ["2", "3", "4", "6"]')
    config = load_config(write(text, "numeric_tags.toml"), machine_file=None)
    assert qt.resolve_selector(config.quantities["pthatmin"], "2", "--pin") == 0
