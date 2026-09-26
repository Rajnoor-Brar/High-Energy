"""Measuring what a run actually costs, and choosing a concurrency mode from the numbers (05 §3).

05 §3 is explicit about this: *measure, don't guess*. The question `auto` has to answer is whether
the analysis is expensive enough that letting k events be in flight at once pays for itself, and the
honest way to answer it is to run the thing three ways and time it:

1. **generation only** — no analyzers at all. The ceiling: nothing can be faster than this;
2. **generation with the config's analyzers, serially** — what a run costs today;
3. **generation with the config's analyzers, sharded** — if the analyzers allow it. If they do not, the
   measurement is replaced by the reason, which is a more useful answer than a number.

The difference between (1) and (2) is the analyzer cost, which is exactly assumption A4 ("is Rivet's CPU
cost per event comparable to Pythia's?"). The difference between (2) and (3) is whether sharding is
worth turning on, and it is measured rather than predicted because the prediction has too many terms:
how well the analysis parallelises, how much of it is under a lock, and what the machine is doing.

A replay is timed too when a store can be made, because "generate once, analyse many" (11) only pays
if reading is much cheaper than generating, and that ratio is a property of the machine's disk.

**Nothing here writes into `results/`.** A benchmark is not a result: it runs in a scratch directory
and its numbers are cached per machine, keyed by what was measured.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from ..errors import HepError

#: Small by default: a benchmark that takes as long as the run it is advising is not worth running.
DEFAULT_EVENTS = 2000

#: How much faster sharded has to be before it is worth the extra moving parts. Below this the two
#: modes are the same run with more ways to go wrong, and `serial` is the better default.
WORTH_IT = 1.15


@dataclass
class Measurement:
    """One timed run."""

    name: str
    events: int = 0
    wall_s: float = 0.0
    mode: str = ""
    threads: int = 0
    refused: str = ""                 # why this one could not be measured, if it could not
    detail: str = ""                  # the hint that came with the refusal

    @property
    def rate(self) -> float:
        return self.events / self.wall_s if self.wall_s > 0 else 0.0

    @property
    def measured(self) -> bool:
        return not self.refused and self.wall_s > 0


@dataclass
class Report:
    """What `hep bench` found, and what it concludes."""

    project: str = ""
    point: str = ""
    machine: str = ""
    threads: int = 0
    events: int = 0
    measurements: list[Measurement] = field(default_factory=list)
    mode: str = "serial"
    reason: str = ""
    analyzer_share: float = 0.0           # fraction of the wall clock the analyzers account for, serially
    speedup: float = 0.0              # sharded vs serial, when both were measured

    def of(self, name: str) -> Measurement | None:
        for measurement in self.measurements:
            if measurement.name == name:
                return measurement
        return None


def recommend(generation: Measurement, serial: Measurement, sharded: Measurement) -> tuple[str, str]:
    """The decision rule of 05 §3, from measurements rather than from assumptions.

    Pure, so the table in the step can be a unit test rather than a run.

    The order of the questions matters. "Is it allowed?" comes before "is it faster?", because a
    sharded run of an analysis that clusters jets is not a faster run — it is a different, wrong
    answer (00/B31). Only then does the margin decide.
    """
    if not serial.measured:
        return "serial", "the serial run could not be measured, so there is nothing to compare"

    if sharded.refused:
        return "serial", sharded.refused
    if not sharded.measured:
        return "serial", "the sharded run could not be measured"

    speedup = serial.wall_s / sharded.wall_s if sharded.wall_s > 0 else 0.0
    if speedup >= WORTH_IT:
        return "sharded", (f"sharded is {speedup:.2f}x faster than serial "
                           f"({serial.wall_s:.1f}s -> {sharded.wall_s:.1f}s)")

    # It is allowed and it does not help. Say *why* it does not, because the two reasons lead
    # somewhere different: cheap analyzers mean the generator is the bottleneck and more threads would
    # help, whereas an expensive-but-unparallelisable analyzer means something is under a lock.
    if generation.measured and serial.wall_s <= generation.wall_s * 1.1:
        return "serial", ("the analyzers cost almost nothing next to generation "
                          f"({serial.wall_s:.1f}s vs {generation.wall_s:.1f}s generating only), "
                          "so there is nothing to parallelise")
    return "serial", (f"sharded is only {speedup:.2f}x faster, which is not worth the extra moving "
                      f"parts (the threshold is {WORTH_IT:.2f}x)")


def analyzer_share(generation: Measurement, serial: Measurement) -> float:
    """What fraction of a serial run's wall clock the analyzers account for. This is assumption A4."""
    if not (generation.measured and serial.measured) or serial.wall_s <= 0:
        return 0.0
    return max(0.0, (serial.wall_s - generation.wall_s) / serial.wall_s)


# ── running the measurements ─────────────────────────────────────────────────

def machine_id() -> str:
    """Enough to notice that a cached number came from somewhere else."""
    return f"{platform.node()}-{platform.machine()}-{os.cpu_count()}cpu"


def cache_path(project: str, point: str) -> Path:
    from ..env import paths

    return paths.scratch_root() / "bench" / f"{project}_{point}_{machine_id()}.json"


def load_cached(project: str, point: str) -> Report | None:
    path = cache_path(project, point)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        measurements = [Measurement(**entry) for entry in raw.pop("measurements", [])]
        return Report(measurements=measurements, **raw)
    except Exception:                                  # noqa: BLE001 - a stale cache is not an error
        return None


def save_cached(report: Report) -> Path:
    path = cache_path(report.project, report.point)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = asdict(report)
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return path


def prepare_variant(config: Any, group: Any, directory: Path, name: str, *, analyzers: list,
                    mode: str, events: int) -> Path:
    """Write one variant's card and spec into its own directory, and return the spec's path."""
    import copy

    from ..plan import naming
    from ..plan import spec as spec_module

    target = (directory / name).resolve()
    target.mkdir(parents=True, exist_ok=True)

    document = copy.deepcopy(spec_module.document(config, group, origin="hep bench"))
    document["meta"]["point"] = f"bench_{group.name}"
    document["run"]["events"] = int(events)
    document["run"]["mode"] = mode
    document["analyzer"] = analyzers

    card_name = naming.card_path(config, group.name, config.generator.tool).name
    document = spec_module.relocated(document, target, card_name)
    if group.card:
        (target / card_name).write_text(group.card, encoding="utf-8")

    path = target / "run.toml"
    path.write_text(spec_module.dumps(document), encoding="utf-8")
    return path


def time_run(binary: str, spec_path: Path, *, timeout: int = 3600) -> tuple[float, dict, list[str]]:
    """Run one spec and return (wall seconds, its summary, the notices about the mode).

    The wall clock is the binary's own, from the summary: it excludes process start-up and Pythia's
    initialisation, which are the same in every variant and would flatten the differences being
    measured.
    """
    directory = spec_path.parent
    status = directory / "status.jsonl"
    started = time.monotonic()
    done = subprocess.run(
        ["sh", "-c", 'exec 3>"$1"; shift; exec "$@"', "sh", str(status), binary, str(spec_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=directory)
    elapsed = time.monotonic() - started
    if done.returncode != 0:
        # `hep-run` prints "hep-run: <what went wrong>" and then an indented hint. The first line is
        # the reason, and a refused leg is reported with it verbatim rather than with a wrapper
        # sentence about exit codes — "photo_eic clusters jets" is the answer the reader wants.
        lines = [line.strip() for line in (done.stderr or "").splitlines() if line.strip()]
        head = lines[0] if lines else f"hep-run exited {done.returncode}"
        head = head.removeprefix("hep-run:").strip()
        rest = " ".join(line.removeprefix("hint:").strip() for line in lines[1:])
        raise HepError(head or f"hep-run exited {done.returncode}", hint=rest)

    summary_path = directory / "run.summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    notices: list[str] = []
    if status.is_file():
        for line in status.read_text(encoding="utf-8").splitlines():
            try:
                message = json.loads(line)
            except ValueError:                         # pragma: no cover - a truncated last line
                continue
            if message.get("k") == "log" and message.get("source") == "run":
                notices.append(message.get("msg", ""))
    return (summary.get("run", {}).get("wall_s") or elapsed), summary, notices


def prepare_replay(config: Any, group: Any, directory: Path, store: Path, *, analyzers: list,
                   events: int) -> Path:
    """The replay leg: the same analyzers, fed from the store the `store` leg just wrote (11 §4)."""
    import copy

    from ..adapters import store as store_adapter
    from ..plan import spec as spec_module

    target = (directory / "replay").resolve()
    target.mkdir(parents=True, exist_ok=True)

    document = copy.deepcopy(spec_module.document(config, group, origin="hep bench replay"))
    document["meta"]["point"] = f"bench_replay_{group.name}"
    document["run"] = {"events": 0, "seed": 0, "threads": 0, "mode": "serial",
                       "seeds": {"point": 0, "instances": []}}
    document["source"] = {"kind": "store", "input": str(store),
                          "store": store_adapter.store_document(store)}
    document["analyzer"] = analyzers
    document["output"] = {"dir": str(target), "yoda": "analysis.yoda",
                          "summary": "run.summary.json"}

    path = target / "run.toml"
    path.write_text(spec_module.dumps(document), encoding="utf-8")
    return path


def measure(config: Any, group: Any, binary: str, directory: Path, *, events: int,
            threads: int, replay: bool = True) -> Report:
    """Run the variants and build the report. This is the part that takes minutes."""
    report = Report(project=getattr(config, "project", ""), point=group.name,
                    machine=machine_id(), threads=threads, events=events)

    real_analyzers = list(spec_analyzers(config, group))
    plans = [
        # No analyzers at all: `hep-run` then uses its counting analyzer, which needs no HepMC record, so
        # this really is generation and nothing else.
        ("generation", [], "serial"),
        ("serial", real_analyzers, "serial"),
        ("sharded", real_analyzers, "sharded"),
    ]
    for name, analyzers, mode in plans:
        measurement = Measurement(name=name, mode=mode, threads=threads)
        try:
            path = prepare_variant(config, group, directory, name, analyzers=analyzers, mode=mode,
                                   events=events)
            wall, summary, notices = time_run(binary, path)
            measurement.wall_s = wall
            measurement.events = summary.get("run", {}).get("events", 0)
            measurement.mode = summary.get("run", {}).get("mode", mode)
            measurement.threads = summary.get("run", {}).get("threads", threads)
            if mode == "sharded" and measurement.mode != "sharded":
                # It ran, but serially: the analyzers would not be shared out, and the notice says why.
                measurement.refused = next((notice for notice in notices if notice), "") or \
                    "the analyzers would not be sharded"
        except HepError as error:
            # A refusal is an answer, not a failure: an analysis that clusters jets stops a sharded
            # run on purpose (00/B31), and that is exactly what the recommendation needs to know.
            if mode == "sharded":
                measurement.refused = error.message
                measurement.detail = error.hint
            else:
                raise
        report.measurements.append(measurement)

    if replay:
        report.measurements.append(_replay_leg(config, group, binary, directory,
                                               analyzers=real_analyzers, events=events))

    generation = report.of("generation") or Measurement("generation")
    serial = report.of("serial") or Measurement("serial")
    sharded = report.of("sharded") or Measurement("sharded")
    report.mode, report.reason = recommend(generation, serial, sharded)
    report.analyzer_share = analyzer_share(generation, serial)
    if serial.measured and sharded.measured:
        report.speedup = serial.wall_s / sharded.wall_s if sharded.wall_s > 0 else 0.0
    return report


def _replay_leg(config: Any, group: Any, binary: str, directory: Path, *, analyzers: list,
                events: int) -> Measurement:
    """Write a store, then time reading it back through the same analyzers.

    Reported, never used by `recommend`: it answers a different question — is "generate once,
    analyse many" (11) worth it on this machine's disk? — and the answer depends on how often the
    analysis will change, which is not something a benchmark can know.
    """
    measurement = Measurement(name="replay", mode="serial", threads=0)
    try:
        store_dir = (directory / "store" / "events").resolve()
        store_analyzer = [{"kind": "store", "dir": str(store_dir), "compression": "zst"}]
        store_spec = prepare_variant(config, group, directory, "store", analyzers=store_analyzer,
                                     mode="serial", events=events)
        time_run(binary, store_spec)

        path = prepare_replay(config, group, directory, store_dir, analyzers=analyzers, events=events)
        wall, summary, _ = time_run(binary, path)
        measurement.wall_s = wall
        measurement.events = summary.get("run", {}).get("events", 0)
        measurement.threads = summary.get("run", {}).get("threads", 0)
    except HepError as error:
        # A machine without zstd, or a build without HepMC3: the other legs still stand.
        measurement.refused = error.message
        measurement.detail = error.hint
    return measurement


def spec_analyzers(config: Any, group: Any) -> list[dict]:
    from ..plan import spec as spec_module

    return spec_module.analyzer_documents(config, group)
