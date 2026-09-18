

# ── hep analyses and hep build (the two commands the CLI claimed but never had) ──

def test_analyses_lists_a_project_plugin_with_its_options():
    """`hep analyses` reads the same `.info` files Rivet does, so a locally built analysis is
    listed beside the published ones (06 §5)."""
    from hekit.env.cli import _analysis_entries
    from hekit.plot.plotfile import search_paths

    found = _analysis_entries("photo_eic", extra_paths=search_paths("PhotoProduction"))
    if not found:
        pytest.skip("the PhotoProduction plugin is not built")
    entry = found[0]
    assert entry["name"] == "photo_eic"
    assert "photoproduction" in entry["summary"].lower()
    assert any(option.startswith("R=") for option in entry["options"]), entry["options"]


def test_analyses_prefers_the_build_tree():
    """The same order as the plugin search: a listed analysis is the one Rivet would load."""
    from hekit.env.cli import _analysis_entries
    from hekit.plot.plotfile import search_paths

    found = _analysis_entries("photo_eic", extra_paths=search_paths("PhotoProduction"))
    if not found or found[0]["path"] == "(installed with Rivet)":
        pytest.skip("the PhotoProduction plugin is not built")
    assert "/build/" in found[0]["path"], found[0]["path"]


def test_an_info_file_is_parsed_loosely(tmp_path):
    """An unreadable or odd `.info` costs one row, never the command."""
    from hekit.env.cli import _read_info

    path = tmp_path / "x.info"
    path.write_text("Name: x\nSummary: 'A thing'\nOptions:\n - R=#   # radius\n - N=#\nStatus: OK\n",
                    encoding="utf-8")
    found = _read_info(path)
    assert found["summary"] == "A thing"
    assert found["options"] == ["R=#   # radius", "N=#"]
    assert _read_info(tmp_path / "missing.info") == {}


def test_build_wraps_cmake_without_running_it(tmp_path):
    """`hep build --analyses PROJECT` replaces `make PROJECT/x.so` (08 §2)."""
    from click.testing import CliRunner

    from hekit.env.cli import build

    result = CliRunner().invoke(build, ["--dry-run", "--analyses", "PhotoProduction"])
    assert result.exit_code == 0, result.output
    line = result.output.strip().splitlines()[-1]
    assert line.startswith("cmake --build ")
    assert "--target rivet_PhotoProduction" in line


def test_build_configures_first_when_asked(tmp_path):
    from click.testing import CliRunner

    from hekit.env.cli import build

    result = CliRunner().invoke(build, ["--dry-run", "--clean", "-j", "4"])
    lines = result.output.strip().splitlines()
    assert any(line.startswith("cmake -E rm -rf") for line in lines)
    assert any(line.startswith("cmake -S ") for line in lines)
    assert lines[-1].endswith("-j 4")
