"""The plot stage's plan-time checks and translations (P3 S2 row 5, V11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from runner import plot
from runner.errors import HepError

from helpers import parse, raw

REPO = Path(__file__).resolve().parents[2]


def validated(scratch, **plot_table):
    run = parse(raw(plot=plot_table), scratch)
    plot.validate(run)
    return run


def test_a_valid_plot_table_passes(scratch):
    validated(scratch, backend="root", formats=["pdf", "png", "svg"], y_gutter=1.5, range_pad=1,
              data={"file": "zeus_eic.yoda", "legend": "ZEUS", "map": {"d01-x01-y01": "/REF/X/d01-x01-y01"}},
              style={"canvas": [900, 600]}, object={"d04-*": {"logy": True, "legend": "top-left"}})


@pytest.mark.parametrize("table, message", [
    ({"lgend": "top-right"}, "lgend"),                                   # the schema: an unknown key
    ({"backend": "matplotlib"}, "backend"),
    ({"formats": ["jpg"]}, "formats"),
    ({"legend": "middle"}, "legend"),
    ({"style": {"colour": "red"}}, "colour"),
    ({"object": {"d01*": {"LegendXPos": 0.5}}}, "LegendXPos"),         # v1 parsed it and dropped it
    ({"object": {"d01*": {"legend": "centre"}}}, "legend"),
    ({"data": {"file": "zeus_eic.yoda"}}, "no map"),                     # L18: explicit only
    ({"data": {"map": {"d01-x01-y01": "/REF/X/d01"}}}, "no file"),
])
def test_keys_no_backend_honours_are_errors(scratch, table, message):
    with pytest.raises(HepError, match=message):
        validated(scratch, **table)


@pytest.mark.parametrize("latex, root", [
    (r"$\mathrm{d}\sigma / \mathrm{d}E_T$ [pb/GeV]", "d#sigma / dE_{T} [pb/GeV]"),
    (r"$-3.5 < \eta < 3.5, k_T$ alg ", "-3.5 < #eta < 3.5, k_{T} alg"),
    (r"$E_T^\text{jet}$ [GeV]", "E_{T}^{jet} [GeV]"),
    (r"$x_\gamma^\mathrm{obs}$", "x_{#gamma}^{obs}"),
    (r"$\frac{1}{N}\,\mathrm{d}N/\mathrm{d}p_\perp$", "#frac{1}{N} dN/dp_{#perp}"),
    (r"$Q^2 \le 1$ GeV$^2$", "Q^{2} #leq 1 GeV^{2}"),
    ("plain text", "plain text"),
])
def test_latex_becomes_tlatex(latex, root):
    assert plot.tlatex(latex) == root


def test_root_names_follow_app_yd2rt():
    assert plot.root_name("/photo_eic:R=0.4/d01-x01-y01") == "photo_eic__R-0.4/d01-x01-y01"
    assert plot.root_name("/REF/ZEUS_2012_I1116258/d01-x01-y01") == "REF/ZEUS_2012_I1116258/d01-x01-y01"


def test_objects_skip_raw_tmp_and_the_counters():
    found = plot.objects_of(REPO / "tests" / "reference" / "legacy_run" / "mini_27x920_ep_MSTW.yoda")
    assert sorted(found) == [f"/photo_eic/d{n:02d}-x01-y01" for n in range(1, 18)]


@pytest.mark.skipif(not (REPO / "build" / "Rivet" / "photo_eic.plot").exists(), reason="make the Rivet plugins")
def test_labels_come_from_the_rivet_plot_file_for_every_variant():
    plain, variant = plot.labels_of("/photo_eic/d01-x01-y01"), plot.labels_of("/photo_eic:R=0.7/d01-x01-y01")
    assert plain == variant
    assert plain["LogY"] == "1" and "E_T" in plain["XLabel"]
