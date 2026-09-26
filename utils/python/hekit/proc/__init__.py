"""Processing: fits and derived histograms over results that already exist (12).

ROOT lives here and nowhere else. D15 is explicit that `hep-run` never links ROOT — it generates and
analyses, and everything that wants a fitter, RDataFrame or a workspace happens afterwards, in
Python, against files on disk. So every import of ROOT in this package is **lazy**: inside the
function that needs it, never at module scope, so `hep --help` and every other command stay fast and
a machine without PyROOT still runs the rest of the toolkit.
"""
