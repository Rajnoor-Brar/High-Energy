"""The four sweep bugs of 00 §4.1, each reproduced against the legacy tool and then shown fixed.

The legacy planner is still in the tree (`tools/rivpyth_common.py`, retired in P4-S06), so every test
here first demonstrates the old behaviour and then the new one. When the legacy module goes, the first
half of each test goes with it and the recorded behaviour stays in this docstring.
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
sys.path.insert(0, str(REPO / "tools"))
import rivpyth_common as legacy       # noqa: E402  the tool being replaced


@pytest.fixture
def write(tmp_path: Path):
    def writer(text: str, name: str) -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path
    return writer


# ── 00/B6: --overlay must not re-group a coupled scan ────────────────────────

V1_COUPLED = """\
[analysis]
cmnd_file   = "photo_ep.cmnd"
event_count = 100
seed        = 1

[yoda]
[rivpyth]
generator  = "generator.exe"
yoda_file  = "x.yoda"
plugin_dir = "."
threads    = 1

[settle.rivet]
plugin = "photo_eic"

[sweep]
across    = [["cmnd.a", "cmnd.b"], "cmnd.c"]
seed_step = 1

[sweep.cmnd.a]
type    = "pythia"
setting = "A:one"
values  = [1, 2]
tags    = ["a1", "a2"]

[sweep.cmnd.b]
type    = "pythia"
setting = "B:two"
values  = [10, 20]
tags    = ["b1", "b2"]

[sweep.cmnd.c]
type    = "pythia"
setting = "C:three"
values  = [100, 200]
tags    = ["c1", "c2"]
"""

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


def test_overlay_alone_uncoupled_the_scan_in_the_legacy_tool(write):
    """Legacy: `--overlay` rebuilt the groups from a flat name list, so a+b became a grid (00/B6)."""
    config = legacy.read_config(write(V1_COUPLED, "v1.toml"))
    assert len(legacy.expand_points(config)) == 4                # 2 coupled × 2 = 4 points
    legacy.apply_overrides(config, None, None, overlay="cmnd.c")
    assert len(legacy.expand_points(config)) == 8, "the legacy tool multiplied a and b apart"


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

V1_MERGE = V1_COUPLED.replace("[yoda]\n", "[yoda]\nplot_merge_type = 2\n").replace(
    'across    = [["cmnd.a", "cmnd.b"], "cmnd.c"]', 'across    = ["cmnd.a"]') + """
[sweep.cmnd.replica]
type   = "seed"
values = [11, 22]
tags   = ["s11", "s22"]

[study.replicas]
across = ["cmnd.replica"]
"""

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


def test_the_legacy_tool_judged_the_file_before_the_study(write):
    """Legacy: a yodamerge file was rejected at load, even when the study it runs scans seeds (00/B7)."""
    with pytest.raises(legacy.ConfigError, match="statistically equivalent"):
        legacy.read_config(write(V1_MERGE, "v1merge.toml"))


def test_the_scan_that_runs_decides(write):
    config = load_config(write(V2_MERGE, "v2merge.toml"), machine_file=None)   # loads fine
    selection = sweep.select(config, study="replicas")                         # seed-only: allowed
    assert [point.suffix for point in sweep.expand(config, selection)] == ["s11", "s22"]
    with pytest.raises(HepError, match="statistically equivalent"):
        sweep.select(config)                                                   # the default scan is not


# ── 00/B9: value rendering must not lose precision ───────────────────────────

def test_the_legacy_tool_rounded_values():
    assert legacy.format_value(0.123456789) == "0.123457"
    assert legacy.format_value(1.0) == "1"
    # two distinct values that the legacy tool rendered identically
    assert legacy.format_value(0.12345671) == legacy.format_value(0.12345672)


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

V1_PIN = V1_COUPLED.replace('across    = [["cmnd.a", "cmnd.b"], "cmnd.c"]', 'across    = ["cmnd.a"]') + """
[sweep.cmnd.pthatmin]
type    = "pythia"
setting = "PhaseSpace:pTHatMin"
values  = [2.0, 3.0, 4.0, 6.0]
tags    = ["pth2", "pth3", "pth4", "pth6"]
"""

V2_PIN = V2_COUPLED.replace('across = ["a+b", "c"]', 'across = ["a"]') + """
[quantity.pthatmin]
type   = "setting"
key    = "PhaseSpace:pTHatMin"
values = [2.0, 3.0, 4.0, 6.0]
tags   = ["pth2", "pth3", "pth4", "pth6"]
"""


def test_the_legacy_tool_read_a_number_as_a_position(write):
    """Legacy: an all-digit selector was an index, so the value 6 could not be pinned (00/B22)."""
    assert legacy.parse_pin("cmnd.pthatmin=6") == ("cmnd.pthatmin", 6)
    config = legacy.read_config(write(V1_PIN, "v1pin.toml"))
    with pytest.raises(legacy.ConfigError, match="outside 1..4"):
        legacy.apply_overrides(config, None, None, pins=["cmnd.pthatmin=6"])


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
