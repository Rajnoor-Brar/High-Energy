#!/usr/bin/env python3
"""Freeze the behaviour of the legacy PhotoProduction tools as golden fixtures (rework P0-S04).

    python tests/golden/capture_legacy.py inputs      # refresh inputs/ from configs/ (then re-run `plan`)
    python tests/golden/capture_legacy.py plan        # legacy_plan/<config>/<case>.json
    python tests/golden/capture_legacy.py mini        # run the tools on legacy_mini.toml -> legacy_run/
    python tests/golden/capture_legacy.py inventory   # read-only results_inventory.json

The planner is exercised through the pure functions of tools/rivpyth_common.py on frozen copies of the
configs (inputs/), from a temporary CWD, so the fixtures do not move when configs/ is edited. The mini run
uses its own scratch CWD (output/scratch/legacy_mini). Nothing here writes into results/ or configs/.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "golden"
INPUTS = GOLDEN / "inputs"
PLAN_DIR = GOLDEN / "legacy_plan"
RUN_DIR = GOLDEN / "legacy_run"
MINI_CONFIG = GOLDEN / "legacy_mini.toml"
MINI_CWD = REPO / "output" / "scratch" / "legacy_mini"
PROJECT = "PhotoProduction"
CONFIGS = ("eic", "zeus_validation")
INPUT_FILES = ("eic.toml", "zeus_validation.toml", "photo_ep.cmnd")

sys.path.insert(0, str(REPO / "tools"))
import rivpyth_common as rc  # noqa: E402  (legacy planner; pure functions)

# Command-line overrides captured next to the studies: (case name, arguments). Studies are added per config.
EXTRA_CASES: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "eic": [
        ("cli_pin_beams", {"pins": ["cmnd.beams=10x100"]}),
        ("cli_single_pin", {"study": "single", "pins": ["cmnd.beams=18x275"]}),
        ("cli_across_overlay", {"across": "cmnd.beams,cmnd.pdf", "overlay": "cmnd.beams"}),
        ("cli_across_together", {"across": "cmnd.pdf,cmnd.pthatmin", "style": "together"}),
        ("cli_couple_mismatch", {"across": "cmnd.beams+cmnd.lepton"}),
    ],
    "zeus_validation": [
        ("cli_across_process", {"across": "cmnd.process"}),
    ],
}


# yoda.read() resets LC_ALL to "C" and does not restore it, which makes the locale default
# encoding ASCII (00/B29). Every text read and write below therefore names its encoding.

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


@contextlib.contextmanager
def inputs_cwd() -> Iterator[Path]:
    """A temporary CWD whose configs/<project> is the frozen inputs directory."""
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="golden-plan-") as workdir:
        root = Path(workdir)
        (root / "configs").mkdir()
        (root / "configs" / PROJECT).symlink_to(INPUTS / PROJECT)
        os.chdir(root)
        try:
            yield root
        finally:
            os.chdir(previous)


def cases(config_name: str) -> list[tuple[str, dict[str, Any]]]:
    """Default expansion, every [study.<name>] (file order), then the extra CLI cases."""
    with inputs_cwd():
        config = rc.read_config(Path(f"configs/{PROJECT}/{config_name}.toml"))
    return [("default", {}), *((name, {"study": name}) for name in config["studies"]),
            *EXTRA_CASES.get(config_name, [])]


def expand_case(config_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Everything the legacy tools derive from a config + CLI selection, as plain data."""
    result: dict[str, Any] = {"config": f"configs/{PROJECT}/{config_name}.toml", "arguments": arguments}
    with inputs_cwd() as root:
        try:
            config = rc.read_config(Path(result["config"]))
            rc.apply_overrides(config, arguments.get("across"), arguments.get("style"), arguments.get("overlay"),
                               arguments.get("study"), arguments.get("pins", []))
            points = rc.expand_points(config)
        except rc.ConfigError as error:
            result["error"] = str(error)
            return result

        sweep: rc.Sweep = config["sweep"]
        result["sweep"] = {
            "groups": [[q.key for q in group] for group in sweep.groups],
            "overlay": [q.key for q in sweep.overlay] if sweep.overlay else None,
            "uses": {q.key: q.use for q in sweep.quantities},
            "constant_suffix": rc.constant_suffix(config),
        }
        result["points"] = []
        for point in points:
            plan = rc.execution_plan(config, point)
            scratch_cmnd = root / "point_cmnd" / Path(plan["point_cmnd"]).name
            rc.write_point_cmnd(config, {**plan, "point_cmnd": str(scratch_cmnd)}, point)
            result["points"].append({
                "number": point.number,
                "suffix": point.suffix,
                "legend": point.legend,
                "curve_legend": rc.curve_legend(config, point),
                "analysis": point.analysis,
                "plugin": point.plugin,
                "choice": point.choice,
                "page": [list(item) for item in point.page],
                "settings": [list(item) for item in point.settings],
                "plan": plan,
                "ydplt_dir": str(Path("results") / config["project"] / Path(plan["yoda_file"]).stem),
                "point_cmnd": scratch_cmnd.read_text(encoding="utf-8"),
            })
        result["pages"] = []
        if sweep.across:   # ydmrg refuses a sweep without scanned quantities
            for page, members in rc.group_pages(points).items():
                page_yoda = Path(rc.resolve_yoda_file(config, rc.page_suffix(config, page)))
                result["pages"].append({
                    "suffix": rc.page_suffix(config, page),
                    "yoda_file": str(page_yoda),
                    "output_dir": str(page_yoda.parent / page_yoda.stem),
                    "analysis": rc.common_analysis(config, members),
                    "members": [point.number for point in members],
                    "legends": [rc.curve_legend(config, point) for point in members],
                })
    return result


# ── subcommands ──────────────────────────────────────────────────────────────

def capture_inputs() -> None:
    target = INPUTS / PROJECT
    target.mkdir(parents=True, exist_ok=True)
    for name in INPUT_FILES:
        shutil.copyfile(REPO / "configs" / PROJECT / name, target / name)
        print(f"inputs: {name}")


def capture_plan() -> None:
    manifest = {
        "captured": datetime.date.today().isoformat(),
        "tool": {"tools/rivpyth_common.py": sha256(REPO / "tools" / "rivpyth_common.py")},
        "inputs": {name: sha256(INPUTS / PROJECT / name) for name in INPUT_FILES},
        "cases": {},
    }
    shutil.rmtree(PLAN_DIR / "eic", ignore_errors=True)
    shutil.rmtree(PLAN_DIR / "zeus_validation", ignore_errors=True)
    for config_name in CONFIGS:
        for case, arguments in cases(config_name):
            data = expand_case(config_name, arguments)
            write_json(PLAN_DIR / config_name / f"{case}.json", data)
            summary = data.get("error") or f"{len(data['points'])} points, {len(data['pages'])} pages"
            manifest["cases"][f"{config_name}/{case}"] = summary
            print(f"plan: {config_name}/{case}: {summary}")
    write_json(PLAN_DIR / "MANIFEST.json", manifest)


def run_logged(command: list[str], log: Path, env: dict[str, str] | None = None) -> int:
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(command)}\n")
        handle.flush()
        return subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, env=env).returncode


def capture_mini() -> None:
    """Run rivpyth, ydmrg and ydplt on the mini config in a scratch CWD; keep outputs and plot inputs."""
    shutil.rmtree(MINI_CWD, ignore_errors=True)
    (MINI_CWD / "configs" / PROJECT).mkdir(parents=True)
    (MINI_CWD / "results").mkdir()
    for name in ("output", "sources", "datasets"):
        (MINI_CWD / name).symlink_to(REPO / name)
    (MINI_CWD / "configs" / PROJECT / "photo_ep.cmnd").symlink_to(INPUTS / PROJECT / "photo_ep.cmnd")
    (MINI_CWD / "configs" / PROJECT / "legacy_mini.toml").symlink_to(MINI_CONFIG)
    config_arg = f"configs/{PROJECT}/legacy_mini.toml"
    tools = REPO / "tools"
    log = MINI_CWD / "run.log"
    os.chdir(MINI_CWD)
    statuses = {}
    for tool in ("rivpyth", "ydmrg", "ydplt"):
        statuses[tool] = run_logged([sys.executable, str(tools / tool), config_arg], log)
        print(f"mini: {tool} -> {statuses[tool]}")
        if statuses[tool]:
            raise SystemExit(f"mini: {tool} failed; see {log}")

    config = rc.read_config(Path(config_arg))
    rc.apply_overrides(config, None, None)
    points = rc.expand_points(config)
    plans = {point.number: rc.execution_plan(config, point) for point in points}

    shutil.rmtree(RUN_DIR, ignore_errors=True)
    (RUN_DIR / "cmnd").mkdir(parents=True)
    for point in points:
        plan = plans[point.number]
        shutil.copyfile(plan["yoda_file"], RUN_DIR / Path(plan["yoda_file"]).name)
        shutil.copyfile(plan["point_cmnd"], RUN_DIR / "cmnd" / Path(plan["point_cmnd"]).name)

    # Plot inputs exactly as ydmrg (overlay page) and ydplt (point 1) build them, in kept work directories.
    def relative(value: str) -> str:
        return value.replace(str(RUN_DIR) + "/", "").replace(str(MINI_CWD) + "/", "")

    mkhtml = {}
    for page, members in rc.group_pages(points).items():
        workdir = RUN_DIR / "ydmrg"
        workdir.mkdir()
        analysis = rc.common_analysis(config, members)
        yodas = rc.unify_yodas(members, [Path(plans[p.number]["yoda_file"]) for p in members], analysis, workdir)
        yodas = rc.void_bins(config, yodas, workdir)
        curves = [(path, rc.curve_legend(config, point)) for path, point in zip(yodas, members)]
        arguments = rc.plot_arguments(config, curves, analysis, workdir)
        ranges = rc.auto_range_plot(config, analysis, [p for p, _ in curves] + list(workdir.glob("*_data.yoda")),
                                    workdir)
        page_yoda = Path(rc.resolve_yoda_file(config, rc.page_suffix(config, page)))
        mkhtml["ydmrg"] = {"output_dir": str(page_yoda.parent / page_yoda.stem),
                           "plot_file": str(rc.plot_file_for(config, analysis) or "") or None,
                           "ranges": relative(str(ranges)) if ranges else None,
                           "inputs": [relative(item) for item in arguments]}
    first = points[0]
    workdir = RUN_DIR / "ydplt_p1"
    workdir.mkdir()
    yodas = rc.unify_yodas([first], [Path(plans[1]["yoda_file"])], first.plugin, workdir)
    yodas = rc.void_bins(config, yodas, workdir)
    arguments = rc.plot_arguments(config, [(yodas[0], rc.curve_legend(config, first))], first.plugin, workdir)
    ranges = rc.auto_range_plot(config, first.plugin, [*yodas, *workdir.glob("*_data.yoda")], workdir)
    mkhtml["ydplt_p1"] = {"output_dir": str(Path("results") / PROJECT / Path(plans[1]["yoda_file"]).stem),
                          "ranges": relative(str(ranges)) if ranges else None,
                          "inputs": [relative(item) for item in arguments]}

    text = log.read_text(encoding="utf-8")
    generated = [dict(zip(("generated", "threads", "written"), map(int, match)))
                 for match in re.findall(r"Generated (\d+) events across (\d+) threads; wrote (\d+)", text)]
    import yoda
    counts = {}
    for point in points:
        aos = yoda.read(plans[point.number]["yoda_file"])
        counter = aos["/RAW/_EVTCOUNT"]
        counts[Path(plans[point.number]["yoda_file"]).name] = {
            "numEntries": counter.numEntries(), "sumW": counter.sumW(), "xsec_pb": aos["/_XSEC"].val()}
    pages = {str(index.parent.relative_to(MINI_CWD)): sorted(str(plot.relative_to(index.parent).with_suffix(""))
                                                             for plot in index.parent.glob("*/*.pdf"))
             for index in sorted((MINI_CWD / "results" / PROJECT).glob("*/index.html"))}
    write_json(RUN_DIR / "run.json", {
        "captured": datetime.date.today().isoformat(),
        "config": config_arg,
        "inputs": {"legacy_mini.toml": sha256(MINI_CONFIG), "photo_ep.cmnd": sha256(INPUTS / PROJECT / "photo_ep.cmnd"),
                   config["data_file"]: sha256(MINI_CWD / config["data_file"]) if config["use_data"] else None},
        "statuses": statuses,
        "generator": generated,
        "yoda": counts,
        "html_pages": pages,
        "mkhtml": mkhtml,
    })
    shutil.copyfile(log, MINI_CWD / "run.kept.log")   # timings are not reproducible; the log stays in scratch
    print(f"mini: {len(points)} points, generator {generated}, yoda {counts}")


YODA_SKIP = ("RAW", "TMP")


def yoda_summary(path: Path) -> dict[str, Any]:
    import yoda
    try:
        aos = yoda.read(str(path))
    except Exception as error:   # a truncated file is a finding, not a crash
        return {"readable": False, "error": str(error)}
    analyses = sorted({key.split("/")[1] for key in aos
                       if key.count("/") >= 2 and key.split("/")[1] not in YODA_SKIP and not key.split("/")[1].startswith("_")})
    counter = aos.get("/RAW/_EVTCOUNT")
    xsec = aos.get("/_XSEC")
    return {"readable": True, "objects": len(aos), "analyses": analyses,
            "numEntries": counter.numEntries() if counter else None,
            "sumW": counter.sumW() if counter else None,
            "xsec_pb": xsec.val() if xsec else None}


def cmnd_summary(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    header = dict(re.findall(r"^! (run config|base cmnd|base sha256|point|analysis)\s*: (.*)$", text, re.M))
    events = re.findall(r"^Main:numberOfEvents\s*=\s*(\d+)", text, re.M)
    return {"sha256": sha256(path), "header": header, "numberOfEvents": int(events[-1]) if events else None,
            "reconstructed": "reconstructed" in text}


def capture_inventory() -> None:
    """Read-only description of results/<project>: YODAs with counts and matching cmnds, plot directories."""
    root = REPO / "results" / PROJECT
    yodas, directories = [], []
    for path in sorted(root.glob("*.yoda")):
        name = path.name
        serial = re.match(r"(\d\d)_", name)
        entry = {"path": str(path.relative_to(REPO)), "bytes": path.stat().st_size, "sha256": sha256(path),
                 "serial": serial.group(1) if serial else None, **yoda_summary(path)}
        cmnd = root / "cmnd" / (path.stem + ".cmnd")
        entry["cmnd"] = cmnd_summary(cmnd) if cmnd.is_file() else None
        flags = []
        if entry["serial"] is None:
            flags.append("no_serial")
        if re.search(r"_p\d\d$", path.stem):
            flags.append("positional_name")
        if entry["cmnd"] is None:
            flags.append("no_cmnd")
        else:
            if entry["cmnd"]["reconstructed"]:
                flags.append("cmnd_reconstructed")
            expected = entry["cmnd"]["numberOfEvents"]
            # Main:numberOfEvents counts next() attempts (PythiaParallel::run); failed events never reach Rivet.
            # The failure rate is energy dependent (about 2 % at 5x41, 1e-4 at 27x920), so only a large
            # shortfall marks a run as short; the old runs carry no written-event count to compare with.
            if expected and entry.get("numEntries") is not None:
                entry["missing_fraction"] = round(1 - entry["numEntries"] / expected, 6)
                if entry["missing_fraction"] > 0.05:
                    flags.append("short")
            if entry.get("analyses") and entry["cmnd"]["header"].get("analysis", "").split(":")[0] not in entry["analyses"]:
                flags.append("analysis_mismatch")
        if not entry.get("readable"):
            flags.append("unreadable")
        entry["flags"] = flags
        yodas.append(entry)
    by_sha: dict[str, list[str]] = {}
    for entry in yodas:
        by_sha.setdefault(entry["sha256"], []).append(entry["path"])
    for entry in yodas:
        twins = [p for p in by_sha[entry["sha256"]] if p != entry["path"]]
        if twins:
            entry["flags"].append("duplicate")
            entry["duplicate_of"] = twins
    for path in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "cmnd"):
        files = [f for f in path.rglob("*") if f.is_file()]
        index = path / "index.html"
        index_text = index.read_text(encoding="utf-8", errors="replace") if index.is_file() else ""
        directories.append({
            "path": str(path.relative_to(REPO)), "files": len(files), "bytes": sum(f.stat().st_size for f in files),
            "analyses": sorted(p.name for p in path.iterdir() if p.is_dir()),
            "index_sha256": sha256(index) if index.is_file() else None,
            "index_mentions_tmp": "/tmp/" in index_text,
            "has_yoda": (root / (path.name + ".yoda")).is_file(),
        })
    orphan_cmnds = sorted(c.name for c in (root / "cmnd").glob("*.cmnd") if not (root / (c.stem + ".yoda")).is_file()) \
        if (root / "cmnd").is_dir() else []
    serials: dict[str, set[str]] = {}
    for entry in yodas:
        if entry["serial"]:
            config = (entry["cmnd"] or {}).get("header", {}).get("run config", "?")
            serials.setdefault(entry["serial"], set()).add(config)
    write_json(GOLDEN / "results_inventory.json", {
        "captured": datetime.date.today().isoformat(),
        "root": str(root.relative_to(REPO)),
        "totals": {"yoda": len(yodas), "directories": len(directories),
                   "files": sum(1 for f in root.rglob("*") if f.is_file()),
                   "bytes": sum(f.stat().st_size for f in root.rglob("*") if f.is_file())},
        "serial_configs": {serial: sorted(configs) for serial, configs in sorted(serials.items())},
        "orphan_cmnds": orphan_cmnds,
        "yoda": yodas,
        "directories": directories,
    })
    flagged = {e["path"]: e["flags"] for e in yodas if e["flags"]}
    print(f"inventory: {len(yodas)} yoda, {len(directories)} directories; flagged: {json.dumps(flagged, indent=1)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=("inputs", "plan", "mini", "inventory"), nargs="+")
    for what in parser.parse_args().what:
        {"inputs": capture_inputs, "plan": capture_plan, "mini": capture_mini, "inventory": capture_inventory}[what]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
