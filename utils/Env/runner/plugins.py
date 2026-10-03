"""Loading a folder's Python by path (rank 0, V61): render.py, backend.py, provider.py.

The plugins sit in utils/Env/<folder>/ beside their data, not in a package, so they are loaded by
path, once per process; a plugin imports only runner.PLUGINS_MAY_IMPORT (test_imports.py).
"""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path

from .errors import HepError


@functools.cache
def load(path: Path, kind: str):
    """The module at `path` (utils/Env/<folder>/<kind>.py), loaded once."""
    if not path.is_file():
        raise HepError(f"no {kind} plugin", hint=f"expected {path}")
    spec = importlib.util.spec_from_file_location(f"hep_{kind}_{path.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # importable by name: a process pool's workers find it (V71)
    spec.loader.exec_module(module)
    return module
