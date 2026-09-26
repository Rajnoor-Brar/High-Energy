"""hekit — the Python half of the High-Energy toolkit (CLI `hep`).

The C++ half is `hep-run`; the two communicate through a resolved spec (TOML in) and a status
stream (JSON lines out). See docs/rework/02_Architecture.md.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
