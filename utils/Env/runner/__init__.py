"""The v2 runner (docs/02_Architecture.md §3).

One flat package. A module imports only from its own rank or a lower one, with no cycles. `RANKS` is
the one table of ranks: tests/runner/test_imports.py enforces it, and tests/runner/test_docs.py holds
02 §3.1 to it. A tool folder's plugin (render.py, backend.py) may import only `PLUGINS_MAY_IMPORT`.
"""

RANKS = {
    "errors": 0, "paths": 0, "schema": 0, "hepfiles": 0, "plugins": 0,
    "config": 1, "quantities": 1, "sweep": 1, "labels": 1, "events": 1,
    "tools": 2,
    "execute": 3, "status": 3, "record": 3,
    "watch": 4, "plot": 4, "post": 4,
    "cli": 5, "house": 5,
}

PLUGINS_MAY_IMPORT = {"errors", "paths", "quantities", "labels", "hepfiles"}
