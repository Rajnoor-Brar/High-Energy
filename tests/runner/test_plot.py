"""The plot stage's plan-time checks and translations (P3 S2 row 5, V11), and the style layers over
utils/Apps/Paint/base.toml (P5 S3)."""

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
              style={"page": {"dpi": 300}, "legend": {"position": "top-left"}},
              object={"d04-*": {"logy": True, "style": {"legend": {"position": [0.5, 0.9]}}}})


@pytest.mark.parametrize("table, message", [
    ({"lgend": "top-right"}, "lgend"),                                   # the schema: an unknown key
    ({"backend": "matplotlib"}, "backend"),
    ({"formats": ["jpg"]}, "formats"),
    ({"legend": "top-left"}, "legend.position"),                         # moved into the style
    ({"style": {"colour": "red"}}, "colour"),
    ({"style": {"text": {"titel": 12}}}, "titel"),
    ({"style": {"page": {"dpi": "high"}}}, "dpi"),
    ({"style": {"legend": {"position": "middle"}}}, "position"),
    ({"style": {"ratio": {"range": [0.5]}}}, "range"),
    ({"style": {"text": 10}}, "table"),
    ({"root_style": "/nowhere/talk.toml"}, "no style file"),
    ({"object": {"d01*": {"LegendXPos": 0.5}}}, "LegendXPos"),         # v1 parsed it and dropped it
    ({"object": {"d01*": {"legend": "centre"}}}, "legend"),
    ({"data": {"file": "zeus_eic.yoda"}}, "no map"),                     # L18: explicit only
    ({"data": {"map": {"d01-x01-y01": "/REF/X/d01"}}}, "no file"),
])
def test_keys_no_backend_honours_are_errors(scratch, table, message):
    with pytest.raises(HepError, match=message):
        validated(scratch, **table)


@pytest.mark.parametrize("latex, root", [
    (r"$\mathrm{d}\sigma / \mathrm{d}E_T$ [pb/GeV]", "d#sigma / d#it{E}_{#it{T}} [pb/GeV]"),
    (r"$-3.5 < \eta < 3.5, k_T$ alg ", "-3.5 < #eta < 3.5, #it{k}_{#it{T}} alg"),
    (r"$E_T^\text{jet}$ [GeV]", "#it{E}_{#it{T}}^{jet} [GeV]"),
    (r"$x_\gamma^\mathrm{obs}$", "#it{x}_{#gamma}^{obs}"),
    (r"$\frac{1}{N}\,\mathrm{d}N/\mathrm{d}p_\perp$", "#frac{1}{#it{N}} d#it{N}/d#it{p}_{#perp}"),
    (r"$Q^2 \le 1$ GeV$^2$", "#it{Q}^{2} #leq 1 GeV^{2}"),
    (r"$m(p\pi^-)$ [GeV]", "#it{m}(#it{p}#pi^{-}) [GeV]"),
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


# ── the yoda backend (utils/Env/yoda/backend.py) ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def yoda_backend():
    return plot.backend("yoda")


@pytest.mark.parametrize("root, latex", [
    ("MSTW 2008 LO", "MSTW 2008 LO"),
    ("5x41 GeV (#sqrt{s} = 28.6 GeV)", r"5x41 GeV $(\sqrt{s}$ = 28.6 GeV)"),
    ("p_{T0}^{ref} = 3.0 GeV", "$p_{T0}^{ref}$ = 3.0 GeV"),
    ("#hat{p}_{T} > 2 GeV", r"$\hat{p}_{T}$ > 2 GeV"),
    ("R: 0.4", "R  0.4"),                                                 # ':' separates mkhtml's options
])
def test_tlatex_becomes_latex_for_mkhtml(yoda_backend, root, latex):
    assert yoda_backend.latex(root) == latex


def test_the_yoda_backend_refuses_what_mkhtml_cannot_do(scratch):
    validated(scratch, backend="yoda", style={"legend": {"position": "top-left"}})
    for style, key in (({"text": {"title": 12}}, "text.title"), ({"curves": {"palette": ["kRed"]}}, "palette"),
                       ({"legend": {"position": [0.5, 0.5]}}, "legend.position")):
        with pytest.raises(HepError, match=key):
            validated(scratch, backend="yoda", style=style)
    with pytest.raises(HepError, match="root_style"):
        validated(scratch, backend="yoda", root_style="/x.toml")


def test_both_backends_draw_the_same_pages_and_the_style_is_paints(scratch):
    assert plot.backends({}) == ["root"] and plot.backends({"backend": "yoda"}) == ["yoda"]
    assert plot.backends({"backend": "both"}) == plot.backends({"backend": ["yoda", "root", "yoda"]}) == ["root", "yoda"]
    (scratch / "talk.toml").write_text("[text]\ntitle = 12\n")
    validated(scratch, backend="both", root_style=str(scratch / "talk.toml"),       # Paint honours these
              style={"text": {"legend": 9}, "legend": {"position": "top-left"}})
    with pytest.raises(HepError, match="legend.position"):                         # the pages would disagree
        validated(scratch, backend=["root", "yoda"], style={"legend": {"position": [0.5, 0.9]}})
    for bad, message in (([], "names no backend"), (["root", "matplotlib"], "backend")):
        with pytest.raises(HepError, match=message):
            validated(scratch, backend=bad)


# ── the style layers ──────────────────────────────────────────────────────────────────────────

def test_a_root_style_file_goes_under_the_inline_style(scratch):
    (scratch / "talk.toml").write_text('[text]\ntitle = 14\nlegend = 12\n[page]\ndpi = 300\n')
    run = validated(scratch, root_style=str(scratch / "talk"), style={"text": {"legend": 9}})   # .toml optional
    assert plot.run_style(run) == {"text": {"title": 14, "legend": 9}, "page": {"dpi": 300}}
    whole = plot.merge_style(plot.base_style(), plot.run_style(run))
    assert whole["text"]["labels"] == plot.base_style()["text"]["labels"] and whole["page"]["size"] == [4.67, 4.21]


def test_a_style_file_is_checked_like_the_inline_style(scratch):
    (scratch / "bad.toml").write_text('[legend]\nplace = "top-left"\n')
    with pytest.raises(HepError, match="place") as error:
        validated(scratch, root_style=str(scratch / "bad.toml"))
    assert "position" in error.value.hint                                  # the nearest spelling


def test_references_are_cut_to_the_aligned_run_and_renamed(yoda_backend):
    yoda = pytest.importorskip("yoda")
    from types import SimpleNamespace
    try:
        source = plot.data_source("rivet:ZEUS_2012_I1116258", SimpleNamespace(path="test", project="PhotoProduction"))
    except HepError:
        pytest.skip("no Rivet reference data")
    page = SimpleNamespace(object="/photo_eic:R=0.7/d01-x01-y01", ranges={"data_x": [17, 47]},
                           data=(source, "/REF/ZEUS_2012_I1116258/d01-x01-y01"))
    ref = yoda_backend._reference(yoda, page)
    whole = yoda.read(str(page.data[0]))[page.data[1]]
    assert ref.path() == "/REF/photo_eic/d01-x01-y01"
    assert list(ref.xEdges()) == [17, 21, 25, 29, 35, 41, 47] and len(whole.xEdges()) > 7
    assert [ref.bin(i).val() for i in range(1, 7)] == [whole.bin(i).val() for i in range(1, 7)]
    assert ref.bin(1).errDownUp("stat") == whole.bin(1).errDownUp("stat")
