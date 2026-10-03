"""The runner's import rank (docs/02_Architecture.md §3), enforced.

A module may import only from its own rank or a lower one, and the import graph has no cycles.
A module missing from RANKS fails, so a new module has to be given its place. Tool plugins
(utils/Env/<tool>/render.py, backend.py) may import only PLUGINS_MAY_IMPORT, and never another plugin.
Both tables are runner/__init__.py's.
"""

from __future__ import annotations

import ast
from pathlib import Path

from runner import PLUGINS_MAY_IMPORT as PLUGIN_MAY_IMPORT, RANKS

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "utils" / "Env" / "runner"
ENV = REPO / "utils" / "Env"


def runner_imports(path: Path) -> set[str]:
    """Runner modules imported by a file, at any depth (deferred imports count too)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 1 and module:                       # from .x import y
                found.add(module.split(".")[0])
            elif node.level == 1:                                # from . import x
                found.update(alias.name for alias in node.names)
            elif module == "runner" or module.startswith("runner."):
                parts = module.split(".")
                found.update(parts[1:2] or [alias.name for alias in node.names])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("runner."):
                    found.add(alias.name.split(".")[1])
    return found


def test_every_runner_module_has_a_rank():
    modules = {p.stem for p in RUNNER.glob("*.py") if p.stem != "__init__"}
    assert modules <= set(RANKS), f"give these a rank in RANKS: {sorted(modules - set(RANKS))}"


def test_no_module_imports_upward():
    violations = []
    for path in sorted(RUNNER.glob("*.py")):
        if path.stem == "__init__":
            continue
        for target in runner_imports(path):
            if target not in RANKS:
                violations.append(f"{path.stem} imports unknown runner module {target}")
            elif RANKS[target] > RANKS[path.stem]:
                violations.append(f"{path.stem} (rank {RANKS[path.stem]}) imports {target} (rank {RANKS[target]})")
    assert not violations, "\n".join(violations)


def test_plugins_import_only_the_allowed_modules():
    violations = []
    for render in sorted([*ENV.glob("*/render.py"), *ENV.glob("*/backend.py")]):
        extra = runner_imports(render) - PLUGIN_MAY_IMPORT
        if extra:
            violations.append(f"{render.relative_to(REPO)} imports {sorted(extra)}")
        tree = ast.parse(render.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                tools = {p.parent.name for p in ENV.glob("*/tool.toml")}
                if any(n.split(".")[0] in tools for n in names):
                    violations.append(f"{render.relative_to(REPO)} imports another tool plugin")
    assert not violations, "\n".join(violations)


def test_there_are_no_import_cycles():
    graph = {p.stem: runner_imports(p) & set(RANKS) for p in RUNNER.glob("*.py") if p.stem != "__init__"}
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 1:
            raise AssertionError("import cycle: " + " -> ".join(trail + [node]))
        if state.get(node) == 2:
            return
        state[node] = 1
        for nxt in graph.get(node, ()):
            visit(nxt, trail + [node])
        state[node] = 2

    for module in graph:
        visit(module, [])
