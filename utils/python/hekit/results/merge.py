"""Combining seed replicas of one point (07 §3).

`rivet-merge -e` does the Rivet half properly: it re-runs each analysis' `finalize` from the `/RAW/`
objects, which is the only way a normalised or ratio histogram can be combined correctly. It cannot
do the module half, because it has never heard of user modules — their `finalize` lives in a shared
library it does not load, and there are no `/RAW/` copies of their objects to re-finalize from.

So `hekit` merges those itself, and the rule it uses follows from the scaling contract (05 §5):

* a module's objects are scaled **once**, in `finalize`, by σ/Σw. Two replicas of the same point each
  carry a distribution already in cross-section units, so combining them is a **weighted mean** — by
  Σw, which is how much each replica actually knows — and not a sum. Adding them would give N×σ;
* a module that deliberately left an object unscaled (a raw count) is the case this rule gets wrong,
  and it says so rather than guessing: `unscaled` names those objects and they are **added** instead.

The weights come from each replica's `run.summary.json`, so the combination reflects how much each
run really contributed rather than assuming the replicas are the same size.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..errors import HepError


def module_paths(objects: Iterable[str], modules: Sequence[str]) -> list[str]:
    """The object paths belonging to these modules: `/<module>/<name>` (07 §1)."""
    prefixes = tuple(f"/{name}/" for name in modules)
    return [path for path in objects if path.startswith(prefixes)]


def sum_of_weights(directory: Path) -> float:
    """How much a replica contributed, from the summary `hep-run` wrote (07 §2).

    The **event count**, not Σw: the summary does not carry Σw, and for the unweighted runs this
    project makes the two are the same number. A weighted generator would want Σw recorded here
    first; the weighting below is the only thing that uses it.
    """
    summary = Path(directory) / "run.summary.json"
    if not summary.is_file():
        raise HepError(f"no run.summary.json beside {directory}",
                       hint="a replica has to say how much it contributed before it can be weighted")
    run = json.loads(summary.read_text(encoding="utf-8")).get("run", {})
    return float(run.get("events") or 0)


def merge_objects(replicas: Sequence[Any], weights: Sequence[float], *,
                  unscaled: Sequence[str] = ()) -> Any:
    """Combine one object across replicas: a weighted mean, or a sum for an unscaled one.

    `replicas` are the same object read from each replica's YODA, in the same order as `weights`.
    """
    if not replicas:
        raise HepError("nothing to merge")
    if len(replicas) != len(weights):
        raise HepError(f"{len(replicas)} replicas but {len(weights)} weights")

    if replicas[0].path() in set(unscaled):
        # A raw count: the total across replicas is what it means.
        merged = replicas[0].clone()
        for other in replicas[1:]:
            merged += other
        return merged

    total = float(sum(weights))
    if total <= 0:
        raise HepError(f"the replicas of {replicas[0].path()} contributed nothing",
                       hint="every one of them has zero events")

    # Each replica is already in cross-section units, so the combination is their **mean**, weighted
    # by how much each one knows: Σ(wᵢ·Oᵢ)/Σwᵢ. Adding them would give N times the cross-section.
    merged = replicas[0].clone()
    merged.scaleW(weights[0] / total)
    for other, weight in zip(replicas[1:], weights[1:]):
        scaled = other.clone()
        scaled.scaleW(weight / total)
        merged += scaled
    return merged


def merge_files(paths: Sequence[Path], modules: Sequence[str], out: Path, *,
                unscaled: Sequence[str] = ()) -> Path:
    """Merge the module objects of several replica YODAs into `out`.

    Only the module objects: Rivet's are `rivet-merge -e`'s business, and doing them here would
    combine normalised histograms by a rule that is right for modules and wrong for ratios.
    """
    try:
        import yoda
    except ImportError as error:                       # pragma: no cover - part of the venv
        raise HepError("merging needs the yoda Python module") from error

    if not paths:
        raise HepError("no replicas to merge")
    read = [yoda.read(str(path)) for path in paths]
    weights = [sum_of_weights(Path(path).parent) for path in paths]

    wanted = module_paths(read[0], modules)
    if not wanted:
        raise HepError(f"no module objects in {paths[0]}",
                       hint=f"looked for {', '.join('/' + name + '/' for name in modules)}")

    merged = []
    for path in wanted:
        present = [objects[path] for objects in read if path in objects]
        if len(present) != len(read):
            raise HepError(f"{path} is missing from some replicas",
                           hint="every replica must have booked the same objects")
        merged.append(merge_objects(present, weights, unscaled=unscaled))

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    yoda.write(merged, str(out))
    return out
