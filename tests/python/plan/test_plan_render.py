"""Plan building, card rendering and the resolved spec (P1-S05)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import migrated                                              # noqa: E402
from hekit import sweep                                      # noqa: E402
from hekit.adapters import pythia, rivet                     # noqa: E402
from hekit.config import load_config                         # noqa: E402
from hekit.errors import HepError                            # noqa: E402
from hekit.plan import build as builder                      # noqa: E402
from hekit.plan import spec as spec_module                   # noqa: E402
from hekit.plan.cli import as_document                       # noqa: E402

REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "tests" / "golden" / "inputs" / "PhotoProduction"
PLAN = REPO / "tests" / "golden" / "legacy_plan"

#: Settings the new plan owns or adds, which the legacy point cmnd did not have in the same form.
NEW_OR_OWNED = {"random:seed", "parallelism:seeds", "next:numbercount", "init:showchangedsettings",
                "random:setseed", "beams:ida"}


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    """The frozen inputs as a schema-2 project directory (config plus its base card)."""
    directory = tmp_path_factory.mktemp("PhotoProduction")
    for name in ("eic", "zeus_validation"):
        migrated.write_v2(INPUTS / f"{name}.toml", directory / f"{name}.toml")
    (directory / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    return directory


def plan_for(project: Path, name: str = "eic", **arguments):
    config = load_config(project / f"{name}.toml", machine_file=None, project="PhotoProduction")
    selection = sweep.select(config, **arguments)
    return builder.build(config, selection)


def settings_of(card: str) -> dict[str, str]:
    return pythia.card_defaults(card)


# ── counts ───────────────────────────────────────────────────────────────────

def test_energy_pdf_gives_sixteen_points_in_four_pages(project):
    plan = plan_for(project, study="energy_pdf")
    assert len(plan.points) == 16
    assert len(plan.pages) == 4
    assert len(plan.groups) == 16, "every point is its own generation here"


def test_an_option_study_is_one_generation(project):
    plan = plan_for(project, study="radius")
    assert len(plan.points) == 3 and len(plan.groups) == 1
    group = plan.groups[0]
    assert group.analyses == ["photo_eic:R=0.4", "photo_eic:R=0.7", "photo_eic:R=1.0"]
    assert group.name == "eic_18x275_ep_NNLO_pt32_mpi", "named after the events, not the first variant"
    assert len(group.aliases) == 3


def test_every_point_belongs_to_exactly_one_group(project):
    plan = plan_for(project, study="energy_pdf")
    for point in plan.points:
        assert plan.group_of(point.name).identity.hash


# ── the rendered card ────────────────────────────────────────────────────────

def test_card_settings_match_the_legacy_point_cmnd(project):
    """Golden: the same physics settings as the legacy card, seeds aside."""
    plan = plan_for(project, study="pdf")
    legacy = json.loads((PLAN / "eic" / "pdf.json").read_text(encoding="utf-8"))["points"]
    assert len(plan.groups) == len(legacy)
    for group, item in zip(plan.groups, legacy):
        new = settings_of(group.card)
        old = settings_of(item["point_cmnd"])
        for key, value in old.items():
            if key in NEW_OR_OWNED:
                continue
            assert key in new, f"{key} is missing from the rendered card"
            assert float(new[key]) == float(value) if _numeric(value) else new[key] == value
        extra = set(new) - set(old) - NEW_OR_OWNED
        assert not extra, f"unexpected extra settings: {extra}"


def _numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def test_the_card_carries_its_provenance(project):
    plan = plan_for(project, study="single")
    card = plan.groups[0].card
    assert "! hekit point card" in card
    assert f"! identity   : {plan.groups[0].identity.hash}" in card
    assert "--study single" in card
    assert plan.groups[0].identity.inputs["card"] in card        # the base card's sha256


def test_seeds_are_written_as_a_disjoint_block(project):
    plan = plan_for(project, study="pdf")
    blocks = []
    for group in plan.groups:
        settings = settings_of(group.card)
        instances = [int(seed) for seed in settings["parallelism:seeds"].split(",")]
        assert instances == list(group.seeds.instances)
        assert int(settings["random:seed"]) == group.seeds.point == instances[0]
        assert len(instances) == 20
        blocks.append(instances)
    flat = [seed for block in blocks for seed in block]
    assert len(set(flat)) == len(flat), "no instance seed is shared between points"


def test_a_single_thread_run_writes_no_seed_block(project):
    config = load_config(project / "eic.toml", machine_file=None, project="PhotoProduction")
    plan = builder.build(config, sweep.select(config, study="single"))
    with_threads = settings_of(plan.groups[0].card)
    assert "parallelism:seeds" in with_threads
    config = load_config(project / "eic.toml", machine_file=None, project="PhotoProduction",
                         sets=("run.threads=1",))
    plan = builder.build(config, sweep.select(config, study="single"))
    assert "parallelism:seeds" not in settings_of(plan.groups[0].card)


def test_the_seed_list_length_always_matches_the_thread_count(project):
    """D-SEEDS: Pythia indexes Parallelism:seeds without bounds checking, so the length is on us."""
    for threads in (2, 4, 20):
        config = load_config(project / "eic.toml", machine_file=None, project="PhotoProduction",
                             sets=(f"run.threads={threads}",))
        plan = builder.build(config, sweep.select(config, study="pdf"))
        for group in plan.groups:
            assert len(group.seeds.instances) == threads
            assert len(group.spec["run"]["seeds"]["instances"]) == group.spec["run"]["threads"]
            written = settings_of(group.card)["parallelism:seeds"].split(",")
            assert len(written) == threads


def test_beams_and_energies_are_rendered_by_the_adapter(project):
    plan = plan_for(project, study="energies")
    for group in plan.groups:
        settings = settings_of(group.card)
        assert settings["beams:ida"] == "2212" and settings["beams:idb"] == "-11"
        assert settings["beams:frametype"] == "2"
        assert "beams:ea" in settings and "beams:eb" in settings


def test_a_scalar_energy_uses_the_cm_frame_and_warns(tmp_path):
    """A √s with different beams generates in the CM frame, which shifts lab-frame η (04 §3)."""
    (tmp_path / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    path = tmp_path / "cm.toml"
    path.write_text(
        'schema = 2\n[run]\nname = "cm"\nevents = 100\nseed = 7\nthreads = 2\n'
        '[generator]\ntool = "pythia"\ncard = "photo_ep.cmnd"\n'
        '[beams]\nids = [2212, 11]\nenergies = 318.1\n'
        '[rivet]\nanalyses = ["photo_eic"]\n', encoding="utf-8")
    config = load_config(path, machine_file=None, project="PhotoProduction")
    plan = builder.build(config, sweep.select(config))
    settings = settings_of(plan.groups[0].card)
    assert settings["beams:frametype"] == "1" and settings["beams:ecm"] == "318.1"
    assert any("CM frame" in warning for warning in plan.warnings)


def test_a_pinned_energies_quantity_beats_the_beams_section(project):
    """[beams].energies is the file-wide value; a catalogue entry of that type overrides it (03 §3)."""
    plan = plan_for(project, study="single")
    settings = settings_of(plan.groups[0].card)
    assert settings["beams:frametype"] == "2"
    assert (settings["beams:ea"], settings["beams:eb"]) == ("920", "27.5")


# ── what the plan refuses ────────────────────────────────────────────────────

def test_an_override_may_not_set_what_hep_owns(project, tmp_path):
    text = (project / "eic.toml").read_text(encoding="utf-8") + \
        '\n[settle.gen]\n"Beams:eA" = 100\n'
    path = tmp_path / "beams.toml"
    path.write_text(text, encoding="utf-8")
    (tmp_path / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    config = load_config(path, machine_file=None, project="PhotoProduction")
    with pytest.raises(HepError) as raised:
        builder.build(config, sweep.select(config, study="single"))
    assert "hep owns it" in raised.value.message and "[beams] energies" in raised.value.hint


def test_a_card_may_not_choose_the_concurrency_mode(tmp_path):
    card = tmp_path / "bad.cmnd"
    card.write_text("Parallelism:processAsync = on\n", encoding="utf-8")
    with pytest.raises(HepError, match="processasync"):
        pythia.check_card(card.read_text(encoding="utf-8"), str(card))


def test_unknown_analysis_options_are_rejected(project):
    """00/B14: ZEUS_2012_I1116258 declares no options, but the config scans R and ETMIN."""
    with pytest.raises(HepError) as raised:
        plan_for(project, name="zeus_validation", across="radius")
    assert "does not take R" in raised.value.message
    assert "it declares: none" in raised.value.hint


def test_declared_options_are_accepted(project):
    plan = plan_for(project, study="radius")            # photo_eic declares R
    assert plan.groups[0].analyses[0].startswith("photo_eic:R=")


def test_option_parsing_rejects_a_malformed_entry():
    with pytest.raises(HepError, match="is not OPTION=VALUE"):
        rivet.split_analysis("photo_eic:R")


def test_info_options_are_read_from_the_real_plugin():
    info = rivet.read_info("photo_eic", (REPO / "analyses" / "PhotoProduction",))
    assert info.found
    assert {"R", "ETMIN", "YMIN", "YMAX", "WMIN", "WMAX", "Q2MAX"} <= info.options


# ── the resolved spec ────────────────────────────────────────────────────────

def test_the_spec_matches_its_schema(project):
    plan = plan_for(project, study="radius")
    spec = plan.groups[0].spec
    spec_module.check(spec)
    assert spec["meta"]["schema"] == 2
    assert spec["meta"]["hash"].startswith("sha256:")
    assert sorted(spec["meta"]["aliases"]) == ["eic_18x275_ep_NNLO_pt32_mpi_r04",
                                               "eic_18x275_ep_NNLO_pt32_mpi_r07",
                                               "eic_18x275_ep_NNLO_pt32_mpi_r10"]
    assert spec["run"]["seeds"]["instances"][0] == spec["run"]["seed"]
    assert spec["source"]["kind"] == "pythia" and len(spec["source"]["cards"]) == 2
    assert spec["sink"][0]["kind"] == "rivet"
    assert spec["sink"][0]["analyses"] == plan.groups[0].analyses
    assert spec["status"] == {"fd": 3, "heartbeat_ms": 500}


def test_every_spec_of_every_study_validates(project):
    for study in ("single", "pdf", "energies", "energy_pdf", "mpi_grid", "radius", "process"):
        for group in plan_for(project, study=study).groups:
            spec_module.check(group.spec)


def test_a_broken_spec_is_rejected():
    with pytest.raises(HepError, match="invalid"):
        spec_module.check({"meta": {"schema": 2, "point": "p", "hash": "sha256:" + "a" * 64},
                           "run": {"events": 1, "seed": 0, "threads": 1,
                                   "seeds": {"point": 1, "instances": [1]}},
                           "source": {"kind": "pythia"}, "output": {"dir": "/x", "yoda": "a.yoda",
                                                                    "summary": "s.json"},
                           "status": {"fd": 3, "heartbeat_ms": 500}})


def test_module_and_store_sinks_reach_the_spec(project, tmp_path):
    text = (project / "eic.toml").read_text(encoding="utf-8") + \
        '\n[[sinks.module]]\nname = "mymodule"\noptions = { window = 0.01 }\n' \
        '\n[store]\nenabled = true\ncompression = "gz"\n'
    path = tmp_path / "sinks.toml"
    path.write_text(text, encoding="utf-8")
    (tmp_path / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    config = load_config(path, machine_file=None, project="PhotoProduction")
    plan = builder.build(config, sweep.select(config, study="single"))
    kinds = [sink["kind"] for sink in plan.groups[0].spec["sink"]]
    assert kinds == ["rivet", "module", "store"]
    spec_module.check(plan.groups[0].spec)


def test_specs_are_written_where_asked(project, tmp_path):
    plan = plan_for(project, study="pdf")
    written = spec_module.write(plan, tmp_path / "out")
    assert len(written) == 8                                   # four groups: run.toml + point.cmnd
    assert all(path.is_file() for path in written)
    assert (tmp_path / "out" / plan.groups[0].name / "run.toml").read_text(encoding="utf-8")


# ── the commands ─────────────────────────────────────────────────────────────

def run_hep(*arguments: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "hekit.cli", *arguments],
                          capture_output=True, text=True, cwd=cwd, timeout=120)


def test_hep_plan_json_reports_the_counts(project, tmp_path):
    done = run_hep("plan", str(project / "eic.toml"), "--study", "energy_pdf", "--json", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    document = json.loads(done.stdout)
    assert len(document["points"]) == 16 and len(document["pages"]) == 4
    assert len({group["hash"] for group in document["groups"]}) == 16
    assert document["study"] == "energy_pdf"


def test_hep_plan_prints_a_readable_plan(project, tmp_path):
    done = run_hep("plan", str(project / "eic.toml"), "--study", "radius", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "3 points, 1 generations, 1 pages" in done.stdout
    assert "eic_18x275_ep_NNLO_pt32_mpi" in done.stdout
    assert "photo_eic:R=0.4" in done.stdout


def test_hep_plan_explains_where_a_value_came_from(project, tmp_path):
    done = run_hep("plan", str(project / "eic.toml"), "--explain", "run.threads", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "default" in done.stdout and "eic.toml" in done.stdout and "20" in done.stdout


def test_hep_plan_accepts_the_selectors(project, tmp_path):
    done = run_hep("plan", str(project / "eic.toml"), "--across", "pdf", "--pin", "energies=10x100",
                   "--set", "run.events=1000", "--json", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    document = json.loads(done.stdout)
    assert len(document["points"]) == 4
    assert all("10x100" in point["name"] for point in document["points"])
    assert all(point["events"] == 1000 for point in document["points"])


def test_hep_plan_reports_a_bad_selector(project, tmp_path):
    done = run_hep("plan", str(project / "eic.toml"), "--pin", "beams=nonsense", cwd=tmp_path)
    assert done.returncode == 2
    assert "matches no tag or value" in done.stderr


def test_hep_studies_lists_the_studies(project, tmp_path):
    done = run_hep("studies", str(project / "eic.toml"), cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "10 studies" in done.stdout
    assert "energy_pdf" in done.stdout and "16 points" in done.stdout


def test_hep_studies_json(project, tmp_path):
    done = run_hep("studies", str(project / "eic.toml"), "--json", cwd=tmp_path)
    rows = json.loads(done.stdout)
    assert {row["name"] for row in rows} >= {"single", "pdf", "radius"}
    assert next(row for row in rows if row["name"] == "radius")["points"] == 3


def test_planning_writes_nothing_into_the_project(project):
    """The plan renders into a temporary directory, never into results/ (the guard checks the rest)."""
    before = {path: path.stat().st_mtime_ns for path in project.rglob("*") if path.is_file()}
    plan_for(project, study="pdf")
    after = {path: path.stat().st_mtime_ns for path in project.rglob("*") if path.is_file()}
    assert before == after
