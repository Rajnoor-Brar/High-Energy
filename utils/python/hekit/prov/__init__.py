"""Provenance: what produced a result (07 §2).

`hep-run` writes `run.summary.json` with what only it knows; this package folds that into the
configuration, the git state, the tool versions and the hashes of every input and output, and stamps
the YODA itself so a file that leaves its directory still says which point it is.
"""

from .git import git_state  # noqa: F401
from . import stamp  # noqa: F401  (the module; `stamp.stamp()` is the function)
from .provenance import Provenance, assemble, sha256  # noqa: F401
from .stamp import read_stamp  # noqa: F401
