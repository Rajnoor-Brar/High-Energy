"""Backends that draw a prepared page (07 §4).

`mkhtml` (the default) hands the page to `rivet-mkhtml`, which is right for browsing many histograms
with ratio panels and Rivet's own reference data. `mpl` (P4-S03) renders publication figures from the
**same** `.plot` keys, so one label source serves both.
"""

from . import mkhtml  # noqa: F401
