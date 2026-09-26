"""HepMC3 event stores: what a run wrote, and whether it is still whole (11, decision D13).

A store is a directory of per-worker shards plus `events.index.json`, written last. The index is the
source of truth for a replay — σ, beams, weight names and counts come from it — so everything here
reads the index first and the shards only to check them.
"""

from . import index, verify  # noqa: F401  the modules; `verify.verify()` is the function
from .index import Index, Shard, read, schema_path, validate  # noqa: F401
from .verify import Report  # noqa: F401

# `verify` stays the module, not the function: a package that re-exports a function under one of its
# own module names hides the module from `from . import verify` (the same trap as `prov.stamp`).
