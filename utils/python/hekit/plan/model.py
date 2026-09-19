"""What a plan is: groups of points, their seeds, their cards and their stage chains (02 §3, 03 §7)."""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

from .hashing import Identity
from .seeds import SeedBlock


@dataclass
class Stage:
    """One process in a group's chain (02 §3). The chain is a closed list, never a general DAG."""

    name: str
    role: str                     # generate | analyse | prepare | detector
    command: list[str] = dataclass_field(default_factory=list)
    note: str = ""
    # Where it runs, when that is not the point directory: an integration runs in the prepare cache
    # (04 §1), and a tool that writes beside its working directory would otherwise fill the results.
    cwd: str = ""
    env: dict[str, str] = dataclass_field(default_factory=dict)
    #: (path, text) pairs the runner writes before spawning this stage.
    writes: list[tuple[str, str]] = dataclass_field(default_factory=list)


@dataclass
class Group:
    """One generation: the events are produced once and every alias and variant shares them."""

    name: str                     # the canonical point name
    identity: Identity
    points: list[Any]             # the points that resolve to this generation
    seeds: SeedBlock
    analyses: list[str]           # every analysis variant of this group, in one Rivet handler
    stages: list[Stage]
    card: str = ""                # rendered native card text
    directory: Path | None = None
    spec: dict[str, Any] = dataclass_field(default_factory=dict)

    @property
    def aliases(self) -> list[str]:
        return [point.name for point in self.points]


@dataclass
class Page:
    """One plot page: the points drawn together as curves."""

    name: str
    suffix: str
    members: list[Any]
    legends: list[str]


@dataclass
class Plan:
    """Everything `hep plan` shows and `hep run` executes."""

    config: Any
    selection: Any
    points: list[Any]
    groups: list[Group]
    pages: list[Page]
    warnings: list[str] = dataclass_field(default_factory=list)

    @property
    def study(self) -> str:
        return self.selection.study

    def group_of(self, point_name: str) -> Group:
        for group in self.groups:
            if point_name in group.aliases:
                return group
        raise KeyError(point_name)
