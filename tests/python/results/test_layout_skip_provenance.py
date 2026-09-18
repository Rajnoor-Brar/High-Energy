"""The results layout, the skip rule and provenance (P3-S03).

The rules being tested are the ones the old pipeline got wrong: a killed run must never be mistaken for
a finished one (00/B3), a changed configuration must never be silently skipped, paths must not depend
on the working directory (00/B18), and every write must be atomic.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import migrated                                              # noqa: E402
from hekit.config import load_config                         # noqa: E402
from hekit.prov import provenance, stamp                     # noqa: E402
from hekit.results import Layout, State, decide, layout as layout_module, manifest  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "tests" / "golden" / "inputs" / "PhotoProduction"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "configs"
    directory.mkdir()
    migrated.write_v2(INPUTS / "eic.toml", directory / "eic.toml")
    (directory / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    return directory


@pytest.fixture
def config(project: Path):
    return load_config(project / "eic.toml", machine_file=None, project="PhotoProduction")


@pytest.fixture
def layout(config, redirect_results: Path) -> Layout:
    return Layout.of(config)


def write_result(directory: Path, *, point: str, point_hash: str, stopped: bool = False,
                 yoda: bool = True) -> Path:
    """A point directory that looks like one hep-run just wrote."""
    directory.mkdir(parents=True, exist_ok=True)
    name = "analysis.partial.yoda" if stopped else "analysis.yoda"
    if yoda:
        (directory / name).write_text("BEGIN YODA_COUNTER_V3 /_EVTCOUNT\nEND YODA_COUNTER_V3\n",
                                      encoding="utf-8")
    (directory / "run.summary.json").write_text(json.dumps(
        {"schema": 2, "point": point, "hash": point_hash,
         "run": {"events": 100, "stopped": stopped}}), encoding="utf-8")
    return directory


# ── the layout ───────────────────────────────────────────────────────────────

def test_the_layout_follows_07_section_1(layout: Layout, redirect_results: Path):
    assert layout.root == redirect_results / "PhotoProduction"
    assert layout.point("eic_5x41_ep") == layout.root / "points" / "eic_5x41_ep"
    assert layout.logs("eic_5x41_ep").name == "logs"
    assert layout.studies == layout.root / "studies"
    assert layout.legacy == layout.root / "legacy", "D-Q4's frozen results live here"


def test_a_point_is_named_by_physics_and_never_numbered(layout: Layout):
    """The audit's serial drift: the same physics must not land at a new path on every run."""
    first = layout.point("eic_5x41_ep_NNPDF23lo")
    second = layout.point("eic_5x41_ep_NNPDF23lo")
    assert first == second
    assert not layout_module.SERIAL.match(first.name)


def test_a_study_run_gets_the_next_serial(layout: Layout):
    """D-Q3: the serial distinguishes runs, and one series covers every study, as `01_`…`04_` did."""
    first = layout.new_study("pdf")
    second = layout.new_study("pdf")
    third = layout.new_study("energy")
    assert [path.name for path in (first, second, third)] == ["01_pdf", "02_pdf", "03_energy"]
    assert layout.next_serial() == 4


def test_a_label_is_part_of_the_name_and_is_made_safe(layout: Layout):
    directory = layout.new_study("pdf", label="thesis v2 / final")
    assert directory.name == "01_pdf_thesis_v2_final"


def test_serials_can_be_switched_off(layout: Layout):
    """`[run].serial = false` gives the roadmap's original proposal back."""
    directory = layout.new_study("pdf", serial=False)
    assert directory.name == "pdf"
    assert layout.study_name("pdf", label="note") == "pdf_note"


def test_study_runs_are_listed_newest_first(layout: Layout):
    for _ in range(3):
        layout.new_study("pdf")
    layout.new_study("energy")
    assert [path.name for path in layout.study_runs("pdf")] == ["03_pdf", "02_pdf", "01_pdf"]
    assert layout.latest_study("pdf").name == "03_pdf"
    assert layout.latest_study("nothing") is None


def test_the_serial_survives_a_gap(layout: Layout):
    (layout.studies / "07_pdf").mkdir(parents=True)
    assert layout.new_study("energy").name == "08_energy"


def test_a_directory_that_already_exists_does_not_collide(layout: Layout):
    """Two `hep run`s started together must not both take 01."""
    (layout.studies / "01_pdf").mkdir(parents=True)
    taken = {(layout.studies / "01_pdf")}
    for _ in range(3):
        directory = layout.new_study("pdf")
        assert directory not in taken
        taken.add(directory)


def test_orphan_point_directories_are_found(layout: Layout):
    write_result(layout.point("good"), point="good", point_hash="sha256:a")
    (layout.point("empty")).mkdir(parents=True)
    (layout.point("preview")).mkdir(parents=True)
    (layout.point("preview") / "run.toml").write_text("", encoding="utf-8")
    assert [path.name for path in layout.orphans()] == ["empty", "preview"]


# ── working directory independence (00/B18) ──────────────────────────────────

def test_the_layout_does_not_depend_on_the_working_directory(project: Path, tmp_path: Path):
    """Verification row 'CWD independence': the old tools resolved paths against the cwd, so a run
    from elsewhere wrote elsewhere."""
    script = (
        "import json, sys; sys.path.insert(0, %r)\n"
        "from pathlib import Path\n"
        "from hekit.config import load_config\n"
        "from hekit.results import Layout\n"
        "config = load_config(Path(%r), machine_file=None, project='PhotoProduction')\n"
        "layout = Layout.of(config)\n"
        "print(json.dumps({'root': str(layout.root), 'point': str(layout.point('p'))}))\n"
    ) % (str(REPO / "utils" / "python"), str(project / "eic.toml"))
    environment = dict(os.environ, HEKIT_RESULTS=str(tmp_path / "results"))
    seen = []
    for where in ("/", str(tmp_path)):
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                              cwd=where, env=environment, timeout=120)
        assert done.returncode == 0, done.stderr
        seen.append(json.loads(done.stdout))
    assert seen[0] == seen[1]
    assert seen[0]["root"] == str(tmp_path / "results" / "PhotoProduction")


# ── the skip rule ────────────────────────────────────────────────────────────

def test_a_finished_result_of_the_same_inputs_is_skipped(layout: Layout):
    directory = write_result(layout.point("p"), point="p", point_hash="sha256:aa")
    decision = decide(directory, name="p", wanted_hash="sha256:aa")
    assert decision.state is State.COMPLETE and decision.skip


def test_a_stopped_run_is_rerun_not_skipped(layout: Layout):
    """00/B3: the old rule looked for the final name, so a killed run was skipped for ever."""
    directory = write_result(layout.point("p"), point="p", point_hash="sha256:aa", stopped=True)
    decision = decide(directory, name="p", wanted_hash="sha256:aa")
    assert decision.state is State.PARTIAL and decision.run
    assert "stopped" in decision.reason
    assert "analysis.partial.yoda" in decision.hint


def test_a_summary_that_says_stopped_wins_over_a_final_name(layout: Layout):
    """Belt and braces: if both ever appear, the summary is believed."""
    directory = write_result(layout.point("p"), point="p", point_hash="sha256:aa")
    (directory / "run.summary.json").write_text(json.dumps(
        {"hash": "sha256:aa", "run": {"events": 3, "stopped": True}}), encoding="utf-8")
    assert decide(directory, name="p", wanted_hash="sha256:aa").run


def test_the_same_name_with_a_different_hash_is_an_error_with_a_hint(layout: Layout):
    """Verification row 'Name collision'. The configuration moved under an existing result."""
    directory = write_result(layout.point("p"), point="p", point_hash="sha256:old")
    decision = decide(directory, name="p", wanted_hash="sha256:new")
    assert decision.state is State.MISMATCH
    assert decision.skip, "it must not quietly overwrite somebody's result"
    assert "different identity" in decision.reason
    assert "--rerun" in decision.hint
    assert decision.found_hash == "sha256:old"


def test_rerun_overrides_everything(layout: Layout):
    directory = write_result(layout.point("p"), point="p", point_hash="sha256:old")
    assert decide(directory, name="p", wanted_hash="sha256:new", rerun=True).run


def test_a_missing_or_empty_directory_runs(layout: Layout):
    assert decide(layout.point("nothing"), name="p", wanted_hash="sha256:a").state is State.MISSING
    empty = layout.point("empty")
    empty.mkdir(parents=True)
    assert decide(empty, name="p", wanted_hash="sha256:a").state is State.INCOMPLETE


def test_a_result_with_no_recorded_hash_is_still_usable(layout: Layout):
    """A directory from before provenance existed should not be a hard error."""
    directory = layout.point("old")
    directory.mkdir(parents=True)
    (directory / "analysis.yoda").write_text("", encoding="utf-8")
    assert decide(directory, name="old", wanted_hash="sha256:a").skip


# ── atomic writes ────────────────────────────────────────────────────────────

def test_a_write_leaves_no_temporary_behind(tmp_path: Path):
    directory = tmp_path / "point"
    path = layout_module.write_json(directory / "run.summary.json", {"ok": True})
    assert path.is_file()
    assert [entry.name for entry in directory.iterdir()] == ["run.summary.json"]


def test_the_temporary_keeps_the_extension(tmp_path: Path):
    """`run.json.tmp` would be unreadable by anything that identifies a format by suffix."""
    assert layout_module.marked("analysis.yoda", "tmp") == "analysis.tmp.yoda"
    assert layout_module.marked("run.summary.json", "partial") == "run.summary.partial.json"
    assert layout_module.marked("logfile", "tmp") == "logfile.tmp"


def test_a_payload_that_cannot_be_serialised_creates_nothing(tmp_path: Path):
    class Unserialisable:
        pass

    directory = tmp_path / "point"
    with pytest.raises(TypeError):
        layout_module.write_json(directory / "bad.json", {"x": Unserialisable()})
    assert not directory.exists(), "it fails before it touches the disk"


def test_a_failed_rename_removes_its_temporary(tmp_path: Path):
    """The temporary must not survive a write that got as far as the disk and then failed."""
    directory = tmp_path / "point"
    directory.mkdir()
    (directory / "manifest.json").mkdir()            # a directory where the file should go
    with pytest.raises(OSError):
        layout_module.write_json(directory / "manifest.json", {"ok": True})
    assert [entry.name for entry in directory.iterdir()] == ["manifest.json"]
    assert not list(directory.glob("*.tmp.*")), "no temporary left behind"


def test_an_existing_file_is_replaced_whole(tmp_path: Path):
    path = tmp_path / "manifest.json"
    layout_module.write_json(path, {"first": True})
    layout_module.write_json(path, {"second": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"second": True}


# ── the study manifest ───────────────────────────────────────────────────────

def test_a_manifest_records_the_selection_and_points_at_the_points(layout: Layout):
    directory = layout.new_study("pdf", label="note")
    point = write_result(layout.point("eic_5x41_ep"), point="eic_5x41_ep", point_hash="sha256:aa")
    record = manifest.Manifest.for_run(directory, "pdf", project="PhotoProduction", label="note",
                                       cli="hep run configs/... --study pdf")
    record.add_point("eic_5x41_ep", point_hash="sha256:aa", directory=point, state="complete",
                     aliases=["eic_5x41_ep_NNPDF23lo"])
    record.add_page("by_pdf", members=["eic_5x41_ep"], path=layout.pages(directory) / "by_pdf")
    written = record.write()

    payload = manifest.read(directory)
    assert written.name == "manifest.json"
    assert payload["schema"] == 2 and payload["study"] == "pdf"
    assert payload["serial"] == 1 and payload["label"] == "note"
    assert payload["points"][0]["hash"] == "sha256:aa"
    assert payload["points"][0]["aliases"] == ["eic_5x41_ep_NNPDF23lo"]
    assert payload["started"] and payload["finished"]


def test_a_manifest_stores_relative_paths_so_results_can_move(layout: Layout):
    directory = layout.new_study("pdf")
    point = write_result(layout.point("p"), point="p", point_hash="sha256:aa")
    record = manifest.Manifest.for_run(directory, "pdf")
    record.add_point("p", point_hash="sha256:aa", directory=point)
    record.write()
    stored = manifest.read(directory)["points"][0]["path"]
    assert not Path(stored).is_absolute(), stored
    assert stored == os.path.join("points", "p")


def test_reading_a_missing_manifest_says_none(tmp_path: Path):
    assert manifest.read(tmp_path) is None


# ── provenance ───────────────────────────────────────────────────────────────

def test_provenance_folds_the_run_summary_into_the_whole_story(layout: Layout, tmp_path: Path):
    card = tmp_path / "point.cmnd"
    card.write_text("Main:numberOfEvents = 100\n", encoding="utf-8")
    directory = write_result(layout.point("p"), point="p", point_hash="sha256:aa")
    spec = {"meta": {"point": "p", "hash": "sha256:aa"},
            "source": {"cards": [str(card)]},
            "sink": [{"kind": "rivet", "analyses": ["photo_eic:R=0.4"], "paths": []}]}
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))

    record = provenance.assemble(
        spec=spec, summary=summary,
        origin={"config": "configs/PhotoProduction/eic.v2.toml", "study": "pdf"},
        outputs=[directory / "analysis.yoda"], pdf_sets=["NNPDF23_lo_as_0130_qed"])
    path = record.write(directory)
    payload = provenance.read(directory)

    assert path.name == "provenance.json"
    assert payload["schema"] == 2 and payload["point"] == "p" and payload["hash"] == "sha256:aa"
    assert payload["origin"]["study"] == "pdf"
    assert payload["run"] == summary["run"], "hep-run's numbers, not a second copy of them"
    assert payload["cards"][0]["sha256"] and payload["cards"][0]["bytes"] == card.stat().st_size
    assert payload["outputs"][0]["path"].endswith("analysis.yoda")
    assert payload["resources"]["pdf_sets"] == ["NNPDF23_lo_as_0130_qed"]
    assert payload["tools"]["hekit"]
    assert payload["host"] and payload["user"] and payload["created"]
    assert "git" in payload


def test_provenance_says_so_when_there_is_no_summary(layout: Layout):
    """A run that died before writing one must not get invented numbers."""
    record = provenance.assemble(spec={"meta": {"point": "p", "hash": "sha256:aa"}}, summary=None,
                                 origin={}, exit_code=3)
    document = record.document()
    assert document["run"]["stopped"] is True and document["run"]["events"] == 0
    assert "no summary" in document["run"]["note"]
    assert document["exit"] == 3


def test_an_unreadable_input_costs_one_field_and_not_the_run(tmp_path: Path):
    record = provenance.assemble(spec={"meta": {"point": "p"}, "source": {"cards": ["/nowhere.cmnd"]}},
                                 summary={"run": {}}, origin={})
    assert record.cards[0]["sha256"] == "" and record.cards[0]["bytes"] == 0


def test_an_analysis_plugin_is_hashed_when_it_can_be_found(tmp_path: Path):
    """The digest is what makes "the same analysis" checkable across two results."""
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    plugin = plugins / "Rivet_photo_eic.so"
    plugin.write_bytes(b"not really a library")
    spec = {"sink": [{"kind": "rivet", "analyses": ["photo_eic:R=0.4"], "paths": [str(plugins)]}]}
    found = provenance.resources_of(spec)
    assert found["analyses"]["photo_eic"]["so_sha256"] == provenance.sha256(plugin)
    assert found["analyses"]["photo_eic"]["path"] == str(plugin)


# ── the YODA stamp ───────────────────────────────────────────────────────────

def test_a_yoda_is_stamped_with_its_identity(tmp_path: Path):
    """Verification row 'Annotations': a file that leaves its directory still says what it is."""
    yoda = pytest.importorskip("yoda")
    path = tmp_path / "analysis.yoda"
    counter = yoda.Counter("/_EVTCOUNT")
    counter.fill(1.0)
    histogram = yoda.Histo1D(2, 0.0, 1.0, "/photo_eic/d01-x01-y01")
    histogram.fill(0.5)
    yoda.write([counter, histogram], str(path))

    assert stamp.stamp(path, "eic_5x41_ep", "sha256:aa", git="0a10209-dirty")
    found = stamp.read_stamp(path)
    assert found == {"HekitPoint": "eic_5x41_ep", "HekitHash": "sha256:aa",
                     "HekitGit": "0a10209-dirty"}
    # and nothing else was lost on the way through
    objects = yoda.read(str(path))
    assert "/photo_eic/d01-x01-y01" in objects
    assert not list(path.parent.glob("*.tmp.*")), "the rewrite is atomic too"


def test_stamping_something_that_is_not_a_result_fails_quietly(tmp_path: Path):
    pytest.importorskip("yoda")
    missing = tmp_path / "nothing.yoda"
    assert stamp.stamp(missing, "p", "sha256:aa") is False
    junk = tmp_path / "junk.yoda"
    junk.write_text("this is not a yoda file\n", encoding="utf-8")
    assert stamp.stamp(junk, "p", "sha256:aa") is False
    assert junk.read_text(encoding="utf-8") == "this is not a yoda file\n", "left exactly as it was"


def test_the_git_label_says_whether_the_tree_was_dirty():
    assert stamp.git_label({"sha": "0a10209", "dirty": False}) == "0a10209"
    assert stamp.git_label({"sha": "0a10209", "dirty": True}) == "0a10209-dirty"
    assert stamp.git_label({"sha": None}) == "unknown"


def test_reading_the_locale_back_after_yoda(tmp_path: Path):
    """00/B29: YODA's reader resets LC_ALL to "C" and does not restore it, which broke the next
    non-ASCII write in the same process."""
    import locale

    yoda = pytest.importorskip("yoda")
    path = tmp_path / "analysis.yoda"
    yoda.write([yoda.Counter("/_EVTCOUNT")], str(path))
    before = locale.setlocale(locale.LC_ALL)
    stamp.stamp(path, "p", "sha256:aa")
    assert locale.setlocale(locale.LC_ALL) == before
    (tmp_path / "after.txt").write_text("σ = 70 819 pb — em dash", encoding="utf-8")
