"""The two Lambda analysis paths must agree (00/B42).

`analyses/Lambda/Lamriv.cc` (a Rivet analysis) and `modules/Lambda/Lambda.cc` (a C++ module sink)
measure the same thing from the **same** shared reconstruction, `modules/Lambda/Reconstruction.hh`.
Running both on one sample therefore compares the two *framework* paths, not two implementations of
the physics — which is exactly what makes this test worth having: any disagreement is a framework
defect, and there is nowhere else for it to hide.

It has already caught one. Rivet's `finalize` writes a **density** (dσ/dx); `Results::Final::normalise`
scales by σ/Σw and leaves per-bin integrals. The two differed by exactly the bin width — 125x on the
mass axis, 0.25x on p_z — and nothing complained, because both are plausible numbers in plausible
units. That is 00/B42, and this test is what holds the workaround in place.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs" / "Lambda" / "lambda.toml"
EVENTS = 2000

SETS = ("unvalidated", "validated", "selected")
PROPERTIES = ("mass", "energy", "momentum", "pt", "pz", "eta", "count")


def _yoda():
    return pytest.importorskip("yoda", reason="YODA's Python bindings are not importable")


def _plugin_built() -> bool:
    return (REPO / "build" / "analyses" / "Lambda" / "Rivet_Lamriv.so").is_file()


def _module_built() -> bool:
    return (REPO / "build" / "modules" / "Lambda" / "libhekit_Lambda.so").is_file()


pytestmark = pytest.mark.skipif(
    not (_plugin_built() and _module_built()),
    reason="needs `hep build --analyses Lambda --modules Lambda`")


@pytest.fixture(scope="module")
def objects(tmp_path_factory):
    """One short run with both sinks attached, into a scratch results root."""
    results = tmp_path_factory.mktemp("results")
    environment = dict(os.environ, HEKIT_RESULTS=str(results))
    arguments = ["--plain", "run", str(CONFIG), "--study", "single", "--events", str(EVENTS)]
    done = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO / 'utils' / 'python')!r});"
         f" from hekit.cli import main; raise SystemExit(main({arguments!r}))"],
        cwd=REPO, env=environment, capture_output=True, text=True, timeout=1800,
        stdin=subprocess.DEVNULL)
    assert done.returncode == 0, (done.stderr or done.stdout)[-4000:]

    found = sorted(Path(results).rglob("analysis.yoda"))
    assert found, f"no analysis.yoda under {results}\n{done.stdout}"
    return _yoda().read(str(found[0]))


def _total(histogram) -> float:
    """The integral, whichever YODA type this is.

    Rivet's finalized objects are `BinnedEstimate1D` and a module's are a scaled `BinnedHisto1D`,
    so there is no single accessor — which is itself part of why 00/B42 went unnoticed.
    """
    try:
        return float(sum(histogram.vals()))
    except (AttributeError, TypeError):
        return float(sum(single.sumW() for single in histogram.bins()))


def _rivet_prefix(objects) -> str:
    """`/Lamriv…/`. Rivet puts analysis options in the path, so the name carries `:RESERVED=2`."""
    for path in objects:
        if path.startswith("/Lamriv"):
            return "/" + path.strip("/").split("/")[0] + "/"
    raise AssertionError("no /Lamriv objects: was the plugin found? " + ", ".join(sorted(objects)))


def test_both_paths_ran(objects):
    prefix = _rivet_prefix(objects)
    rivet = {path for path in objects if path.startswith(prefix)}
    module = {path for path in objects if path.startswith("/Lambda/")}
    assert len(rivet) == len(SETS) * len(PROPERTIES)
    # The module books one extra object the analysis does not: its own event counter.
    assert len(module) == len(SETS) * len(PROPERTIES) + 1


@pytest.mark.parametrize("candidate_set", SETS)
@pytest.mark.parametrize("prop", PROPERTIES)
def test_the_two_paths_agree(objects, candidate_set, prop):
    """Same events, same reconstruction, same scaling — so the integrals must match exactly.

    The tolerance is floating-point, not statistical: this is not two samples being compared, it is
    one sample written twice.
    """
    prefix = _rivet_prefix(objects)
    name = f"{candidate_set}_{prop}"
    rivet = objects.get(prefix + name)
    module = objects.get(f"/Lambda/{name}")
    assert rivet is not None and module is not None, name

    from_rivet, from_module = _total(rivet), _total(module)
    assert from_module != 0.0, f"{name}: the module filled nothing"
    assert from_rivet == pytest.approx(from_module, rel=1e-9), (
        f"{name}: Rivet {from_rivet:.6e} vs module {from_module:.6e} "
        f"(ratio {from_rivet / from_module:.6f}). A ratio equal to the bin width is 00/B42.")


def test_the_sets_nest(objects):
    """selected ⊆ validated ⊆ unvalidated — the property the three sets are defined by."""
    prefix = _rivet_prefix(objects)
    for source in (prefix, "/Lambda/"):
        totals = [_total(objects[f"{source}{name}_count"]) for name in SETS]
        assert totals[0] > 0.0, f"{source}: nothing was reconstructed at all"
        # The counts are σ-weighted, so compare the mean multiplicities the histograms encode.
        means = []
        for name in SETS:
            histogram = objects[f"{source}{name}_count"]
            values = list(histogram.vals()) if hasattr(histogram, "vals") else \
                [single.sumW() for single in histogram.bins()]
            weight = sum(values)
            means.append(sum(index * value for index, value in enumerate(values)) / weight
                         if weight else 0.0)
        assert means[0] >= means[1] >= means[2], f"{source}: sets do not nest: {means}"
