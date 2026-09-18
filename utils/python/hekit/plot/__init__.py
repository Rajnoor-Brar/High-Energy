"""Plotting: load, select, transform, overlay data (07 §4).

The pipeline is the legacy one, reorganised: select points → load YODA → pick analysis variants →
unify names → void empty bins → align reference data → auto-range → hand to a backend (P4-S02, P4-S03).
"""

from . import data, io, plotfile, select, transform  # noqa: F401
from .select import Curve  # noqa: F401
