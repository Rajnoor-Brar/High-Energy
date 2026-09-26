"""Path resolution (docs/rework_v2/03_Layout_Build.md §2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from runner import paths
from runner.errors import HepError

REPO = Path(__file__).resolve().parents[2]


def test_the_repository_is_found_by_its_markers():
    assert paths.repo_root() == REPO


def test_hekit_root_must_be_the_repository(monkeypatch, scratch):
    monkeypatch.setenv("HEKIT_ROOT", str(scratch))
    with pytest.raises(HepError, match="is not the repository"):
        paths.repo_root()


def test_a_bare_name_takes_its_keys_convention_root():
    assert paths.resolve("photo_ep.cmnd", "baseconfig", project="PhotoProduction") == \
        REPO / "configs" / "PhotoProduction" / "photo_ep.cmnd"
    assert paths.resolve("Lambda.exe", "executable", project="Lambda") == REPO / "build" / "Lambda" / "Lambda.exe"
    assert paths.resolve("zeus_eic.yoda", "data") == REPO / "datasets" / "zeus_eic.yoda"


def test_dot_slash_is_the_repository_root_not_the_working_directory(monkeypatch, scratch):
    monkeypatch.chdir(scratch)
    assert paths.resolve("./tests/reference/point_counts.toml", "baseconfig", project="X") == \
        REPO / "tests" / "reference" / "point_counts.toml"


def test_an_absolute_path_is_kept():
    assert paths.resolve("/tmp/x.cmnd", "baseconfig", project="P") == Path("/tmp/x.cmnd")


@pytest.mark.parametrize("value", ["../x.cmnd", "a/../b", ".."])
def test_climbing_out_is_refused(value):
    with pytest.raises(HepError, match="climbs out") as caught:
        paths.resolve(value, "baseconfig", project="P")
    assert "./" in caught.value.hint


def test_an_explicit_root_wins():
    assert paths.resolve("events.hepmc", "prelim", root=Path("/o/p")) == Path("/o/p/events.hepmc")


def test_config_lookup_makes_toml_optional(scratch):
    target = REPO / "configs" / "PhotoProduction" / "eic.toml"
    assert paths.config_file("PhotoProduction/eic") == target
    assert paths.config_file("PhotoProduction/eic.toml") == target
    with pytest.raises(HepError, match="no run config"):
        paths.config_file("PhotoProduction/nope")


def test_tests_write_into_output_tests():
    assert "output/tests" in str(paths.results_root())
    assert "output/tests" in str(paths.output_root())
