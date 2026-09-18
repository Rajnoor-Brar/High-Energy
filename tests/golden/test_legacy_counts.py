"""Golden fixtures of the legacy PhotoProduction tools (rework P0-S04).

The planner cases run on the frozen inputs in inputs/; recapture with capture_legacy.py after an intended change.
"""

import json

import pytest

import capture_legacy as cl

# (points, ydmrg pages) per case; a study without scanned quantities has no pages.
EXPECTED_COUNTS = {
    ("eic", "default"): (4, 1),
    ("eic", "single"): (1, 0),
    ("eic", "pdf"): (4, 1),
    ("eic", "energies"): (4, 1),
    ("eic", "energy_pdf"): (16, 4),
    ("eic", "mpi"): (3, 1),
    ("eic", "mpi_onoff"): (2, 1),
    ("eic", "mpi_grid"): (6, 2),
    ("eic", "pthatmin"): (4, 1),
    ("eic", "process"): (2, 1),
    ("eic", "radius"): (3, 1),
    ("zeus_validation", "default"): (4, 1),
}

CASES = [(config, case, arguments) for config in cl.CONFIGS for case, arguments in cl.cases(config)]
CASE_IDS = [f"{config}/{case}" for config, case, _ in CASES]


def arguments_of(config: str, case: str) -> dict:
    return next(arguments for c, name, arguments in CASES if (c, name) == (config, case))


def normalised(data: dict) -> dict:
    return json.loads(json.dumps(data))


@pytest.mark.parametrize(("config", "case"), EXPECTED_COUNTS, ids=[f"{c}/{s}" for c, s in EXPECTED_COUNTS])
def test_counts(config, case):
    data = cl.expand_case(config, arguments_of(config, case))
    assert "error" not in data
    assert (len(data["points"]), len(data["pages"])) == EXPECTED_COUNTS[config, case]


def test_page_members_cover_points():
    data = cl.expand_case("eic", arguments_of("eic", "energy_pdf"))
    members = sorted(number for page in data["pages"] for number in page["members"])
    assert members == [point["number"] for point in data["points"]]
    assert all(len(page["members"]) == 4 for page in data["pages"])


def test_radius_option_analysis():
    points = cl.expand_case("eic", arguments_of("eic", "radius"))["points"]
    assert [point["analysis"] for point in points] == ["photo_eic:R=0.4", "photo_eic:R=0.7", "photo_eic:R=1"]


def test_coupling_needs_equal_lengths():
    assert "equal value counts" in cl.expand_case("eic", arguments_of("eic", "cli_couple_mismatch"))["error"]


def test_every_case_has_a_fixture():
    stored = {f"{path.parent.name}/{path.stem}" for path in cl.PLAN_DIR.glob("*/*.json")}
    assert stored == set(CASE_IDS)


@pytest.mark.parametrize(("config", "case", "arguments"), CASES, ids=CASE_IDS)
def test_fixture_matches_legacy_planner(config, case, arguments):
    stored = json.loads((cl.PLAN_DIR / config / f"{case}.json").read_text(encoding="utf-8"))
    assert normalised(cl.expand_case(config, arguments)) == stored


def test_inputs_are_the_fixture_inputs():
    manifest = json.loads((cl.PLAN_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["inputs"] == {name: cl.sha256(cl.INPUTS / cl.PROJECT / name) for name in cl.INPUT_FILES}
    # The live configs are schema 2 now (P4-S06 promoted them), so they are *expected* to differ from
    # these schema-1 fixtures. What must still match is the archive the migration reads from.
    archive = cl.REPO / "legacy" / "configs" / cl.PROJECT
    stale = [name for name in cl.INPUT_FILES
             if (archive / name).is_file()
             and cl.sha256(cl.INPUTS / cl.PROJECT / name) != cl.sha256(archive / name)]
    assert not stale, (f"legacy/configs/{cl.PROJECT} differs from the frozen golden inputs: "
                       f"{', '.join(stale)} — the fixtures no longer describe the archived originals")


def test_mini_run_is_complete():
    yoda = pytest.importorskip("yoda")
    run = json.loads((cl.RUN_DIR / "run.json").read_text(encoding="utf-8"))
    assert run["statuses"] == {"rivpyth": 0, "ydmrg": 0, "ydplt": 0}
    assert len(run["generator"]) == len(run["yoda"]) == 2
    for generator, (name, recorded) in zip(run["generator"], run["yoda"].items()):
        assert generator["generated"] == 5000 and generator["threads"] == 1
        # attempts vs accepted: Rivet sees exactly the events the generator wrote
        assert 4950 <= generator["written"] <= generator["generated"]
        counter = yoda.read(str(cl.RUN_DIR / name))["/RAW/_EVTCOUNT"]
        assert counter.numEntries() == recorded["numEntries"] == generator["written"]
    assert len(run["html_pages"]) == 3 and all(len(plots) == 17 for plots in run["html_pages"].values())
