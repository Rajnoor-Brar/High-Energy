"""Where a plan's outputs live (07 §1).

One directory per **generation**, not per point: analysis-only variants of the same events share it
(03 §4). Study directories hold what a particular selection produced — manifests, plots, comparisons —
so a point is never copied when two studies reach the same physics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..env import paths

DEFAULT_ROOT = "results/{project}"


def results_root(config: Any) -> Path:
    """`[output].root`, with `HEKIT_RESULTS` honoured for the default template.

    The default resolves through `hekit.env.paths`, so a test that sets `HEKIT_RESULTS` redirects
    everything. A custom template is taken literally (relative to the repository root).
    """
    template = config.output.root or DEFAULT_ROOT
    if template == DEFAULT_ROOT:
        return paths.results_root() / config.project
    rendered = Path(template.format(project=config.project))
    return rendered if rendered.is_absolute() else paths.repo_root() / rendered


def point_dir(config: Any, group_name: str) -> Path:
    return results_root(config) / "points" / group_name


def study_dir(config: Any, study: str) -> Path:
    return results_root(config) / "studies" / (study or "adhoc")


def page_dir(config: Any, study: str, page_name: str) -> Path:
    return study_dir(config, study) / "plots" / page_name


def card_path(config: Any, group_name: str, tool: str) -> Path:
    suffix = {"pythia": "cmnd", "sherpa": "yaml", "whizard": "sin", "herwig": "in"}.get(tool, "card")
    return point_dir(config, group_name) / f"point.{suffix}"
