"""The new sweep engine reproduces the legacy point sets, pages and legends (P1-S03).

The legacy fixtures were captured in P0-S04 from the frozen inputs in `tests/golden/inputs/`. Here the
same inputs are translated to schema 2 in memory (`v1_to_v2.py`) and expanded by `hekit.sweep`. What is
compared is what the audit called the golden fixture: **point sets and pages**, not names or seeds —
point names gain the run-name prefix, and seeds are identity-derived from P1-S04 onwards.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import migrated                                              # noqa: E402
from hekit import sweep                                      # noqa: E402
from hekit.config import load_config                         # noqa: E402

REPO = Path(__file__).resolve().parents[3]
GOLDEN = REPO / "tests" / "golden"
INPUTS = GOLDEN / "inputs" / "PhotoProduction"
PLAN = GOLDEN / "legacy_plan"

# The migration renames the quantities so that a name matches its type: v1 `cmnd.beams` held energy
# pairs and becomes `energies`, and the lepton setting becomes `beams` with `side = "b"` (03 §3). Tag
# renames (00/B12) and dropping undeclared options (00/B14) are switched off here, so that point names
# and counts can be compared with the legacy fixtures like with like.
#: Legacy case name → the selection arguments that reproduce it with the new engine.
CASES: dict[str, dict[str, object]] = {
    "eic/default": {},
    "eic/single": {"study": "single"},
    "eic/pdf": {"study": "pdf"},
    "eic/energies": {"study": "energies"},
    "eic/energy_pdf": {"study": "energy_pdf"},
    "eic/mpi": {"study": "mpi"},
    "eic/mpi_onoff": {"study": "mpi_onoff"},
    "eic/mpi_grid": {"study": "mpi_grid"},
    "eic/pthatmin": {"study": "pthatmin"},
    "eic/process": {"study": "process"},
    "eic/radius": {"study": "radius"},
    "eic/cli_pin_beams": {"pins": ("energies=10x100",)},
    "eic/cli_single_pin": {"study": "single", "pins": ("energies=18x275",)},
    "eic/cli_across_overlay": {"across": "energies,pdf", "overlay": "energies"},
    "eic/cli_across_together": {"across": "pdf,pthatmin", "style": "together"},
    "zeus_validation/default": {},
    "zeus_validation/cli_across_process": {"across": "process"},
}


@pytest.fixture(scope="module")
def translated(tmp_path_factory) -> dict[str, Path]:
    """Both frozen inputs as schema-2 files in a temporary directory."""
    directory = tmp_path_factory.mktemp("v2")
    return {name: migrated.write_v2(INPUTS / f"{name}.toml", directory / f"{name}.toml")
            for name in ("eic", "zeus_validation")}


def same_analysis(new: str, old: str) -> bool:
    """Compare analysis strings, reading option values as numbers.

    00/B9 made value rendering lossless, so a jet radius of 1.0 is now written `R=1.0` where the legacy
    `%g` produced `R=1`. Rivet parses the option as a double, so the physics is identical.
    """
    def parts(text: str) -> tuple:
        base, *options = text.split(":")
        normalised = []
        for option in options:
            key, _, value = option.partition("=")
            try:
                normalised.append((key, float(value)))
            except ValueError:
                normalised.append((key, value))
        return base, tuple(sorted(normalised))

    return parts(new) == parts(old)


def legacy(case: str) -> dict:
    return json.loads((PLAN / f"{case}.json").read_text(encoding="utf-8"))


def expand(path: Path, arguments: dict) -> tuple:
    config = load_config(path, machine_file=None, project="PhotoProduction")
    selection = sweep.select(config, **arguments)
    points = sweep.expand(config, selection)
    return config, selection, points


@pytest.mark.parametrize("case", CASES, ids=list(CASES))
def test_point_sets_match_the_legacy_fixture(case, translated):
    stem, _, _ = case.partition("/")
    config, selection, points = expand(translated[stem], CASES[case])
    expected = legacy(case)

    assert len(points) == len(expected["points"]), "point count"
    # the tag part of a point name, which is what the legacy suffix was
    assert [point.suffix for point in points] == [item["suffix"] for item in expected["points"]]
    assert [point.legend for point in points] == [item["legend"] for item in expected["points"]]
    for point, item in zip(points, expected["points"]):
        assert same_analysis(point.analyses[0], item["analysis"]), f"{point.analyses[0]} vs {item['analysis']}"


@pytest.mark.parametrize("case", CASES, ids=list(CASES))
def test_pages_match_the_legacy_fixture(case, translated):
    stem, _, _ = case.partition("/")
    config, selection, points = expand(translated[stem], CASES[case])
    expected = legacy(case)
    pages = sweep.group_pages(points)

    if not selection.groups:            # a single point has no page (ydmrg refuses such a run)
        assert expected["pages"] == []
        return
    assert len(pages) == len(expected["pages"]), "page count"
    for (key, members), expected_page in zip(pages.items(), expected["pages"]):
        assert [point.number for point in members] == expected_page["members"]
        assert [sweep.curve_legend(config, selection, point) for point in members] \
            == expected_page["legends"]
        # the tag part must match exactly; the "by_<curves>" ending names the *new* quantity names,
        # because the migration renamed the energy quantity (v1 `beams`) to `energies`
        new_suffix = sweep.page_suffix(config, selection, key)
        assert new_suffix.split("_by_")[0] == expected_page["suffix"].split("_by_")[0]
        assert new_suffix.endswith("by_" + "_".join(selection.overlay))


def test_the_settings_of_a_point_carry_the_legacy_values(translated):
    """The values a point applies, compared with the legacy point cmnd (which rendered them as text)."""
    config, selection, points = expand(translated["eic"], {"study": "pdf"})
    expected = legacy("eic/pdf")["points"]
    for point, item in zip(points, expected):
        rendered = {key: value for key, value, _ in item["settings"]}
        # native settings the new engine keeps as native settings
        for assignment in point.settings:
            assert str(assignment.value) == rendered[assignment.key] or \
                   sweep.text_value(assignment.value) == rendered[assignment.key]
        # the beams and energies moved out of the native settings into their own fields (03 §3)
        assert point.energies == [920, 27.5]
        assert point.beams == [2212, -11]     # the lepton pin moved into the beams field
        assert rendered["Beams:eA"] == "920" and rendered["Beams:idB"] == "-11"


def test_event_groups_share_one_generation(translated):
    """The radius study scans an analysis option, so its three points are one event group (03 §4)."""
    config, selection, points = expand(translated["eic"], {"study": "radius"})
    groups = sweep.event_groups(points)
    assert len(points) == 3 and len(groups) == 1
    assert sorted(point.analyses[0] for point in points) == \
        ["photo_eic:R=0.4", "photo_eic:R=0.7", "photo_eic:R=1.0"]     # lossless: R=1.0, not R=1 (00/B9)


def test_generation_studies_do_not_share_generations(translated):
    config, selection, points = expand(translated["eic"], {"study": "pdf"})
    assert len(sweep.event_groups(points)) == len(points) == 4


def test_translation_is_faithful_enough_to_load(translated):
    for path in translated.values():
        config = load_config(path, machine_file=None, project="PhotoProduction")
        assert config.generator.card == "photo_ep.cmnd"
        assert config.run.threads == 20
        assert config.rivet.analyses and config.rivet.paths == ["."]
