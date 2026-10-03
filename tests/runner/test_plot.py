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
    ({"y_gutter": -1}, "gutter"),
    ({"x_gutter": "auto"}, "gutter"),
    ({"object": {"d01*": {"y_gutter": -0.5}}}, "gutter"),
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
    (r"$Q^2<1\ GeV^2 \newline -3.5 < \eta < 3.5$",                         # V47: math open across the break
     "#splitline{#it{Q}^{2}<1 #it{GeV}^{2}}{-3.5 < #eta < 3.5}"),
    (r"$Q^2 < 1$ GeV$^2$\newline$-3.5 < \eta < 3.5$", "#splitline{#it{Q}^{2} < 1 GeV^{2}}{-3.5 < #eta < 3.5}"),
    (r"a \\ b \\ c", "#splitline{a}{#splitline{b}{c}}"),                    # LaTeX's \\, three lines
    (r"$\pT$ [\GeV], $\sqrt{s} = 13\,\TeV$", "{#it{p}_{T}} [GeV], #sqrt{#it{s}} = 13 TeV"),   # YODA's macros
])
def test_latex_becomes_tlatex(latex, root):
    assert plot.tlatex(latex) == root


def test_a_title_s_lines_each_close_their_math():
    assert plot.lines_of(r"$a \newline b$") == ["$a$", "$b$"]
    assert plot.lines_of(r"$a$ x\newline$b$") == ["$a$ x", "$b$"]
    assert plot.lines_of("no break") == ["no break"]


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
    ("#hat{p}_{T} > 2 GeV", r"$\hat{p}_{T}$ $>$ 2 GeV"),
    ("R: 0.4", "R  0.4"),                                                 # ':' separates mkhtml's options
    ("PDF4LHC21_40_pdfas", "PDF4LHC21_40_pdfas"),                        # TLatex's rule: a bare _ is itself
    ("E_T jets", "E_T jets"),
    (r"PDF4LHC21\_40", "PDF4LHC21_40"),                                  # the escapes are the characters
    (r"\#1 \^2", "#1 ^2"),
    (r"x_1\_a_{2}", r"$x\_1\_a_{2}$"),                                   # literal underscores inside math
    ("E_{T} > 5", "$E_{T}$ $>$ 5"),                                       # V51: > in LaTeX's text font is ¿
])
def test_tlatex_becomes_latex_for_mkhtml(yoda_backend, root, latex):
    assert yoda_backend.latex(root) == latex


@pytest.mark.parametrize("label, root", [
    ("PDF4LHC21_40_pdfas", "PDF4LHC21_40_pdfas"),                        # TLatex draws a bare _ as itself
    (r"PDF4LHC21\_40\_pdfas", "PDF4LHC21_40_pdfas"),
    ("p_{T0}^{ref} #sqrt{s}", "p_{T0}^{ref} #sqrt{s}"),
    (r"a\_{b}", "a#kern[0]{_}{b}"),                                       # before a brace: kept apart from it
    (r"\#1 \\ x", "#1 \\ x"),
])
def test_labels_as_root_draws_them(label, root):
    assert plot.root_text(label) == root


def test_paint_gets_root_labels_and_the_page_keeps_them_as_written():
    document = {"page": {"title": r"a\_b", "ratio": True}, "style": {},
                "curve": [{"file": "f", "object": "o", "label": r"PDF4LHC21\_40"}], "data": {"label": r"ZEUS\_2012"}}
    root = plot.for_root(document)
    assert (root["page"]["title"], root["curve"][0]["label"], root["data"]["label"]) == ("a_b", "PDF4LHC21_40", "ZEUS_2012")
    assert document["curve"][0]["label"] == r"PDF4LHC21\_40" and root["page"]["ratio"] is True


def test_a_backslash_in_a_double_quoted_label_says_how_to_write_it(scratch):
    from runner import config
    path = scratch / "bad.toml"
    path.write_text('[run]\nname = "x"\n[quantities.pdf]\nlabels = ["PDF4LHC21\\_40"]\n', encoding="utf-8")
    with pytest.raises(HepError, match="not valid TOML") as caught:
        config.load(str(path))
    assert "single quotes" in caught.value.hint


def test_the_yoda_backend_refuses_what_mkhtml_cannot_do(scratch):
    validated(scratch, backend="yoda", style={"legend": {"position": "top-left"}})
    for style, key in (({"text": {"title": 12}}, "text.title"), ({"curves": {"palette": ["kRed"]}}, "palette"),
                       ({"legend": {"position": [0.5, 0.5]}}, "legend.position")):
        with pytest.raises(HepError, match=key):
            validated(scratch, backend="yoda", style=style)
    with pytest.raises(HepError, match="root_style"):
        validated(scratch, backend="yoda", root_style="/x.toml")


def test_no_gutter_leaves_mkhtml_its_own_range(yoda_backend, scratch):
    validated(scratch, y_gutter="default", x_gutter=0, object={"d04*": {"y_gutter": "default"}})
    page = plot.Page("d01", scratch / "d01.toml", scratch / "d01", object="/A/d01",
                     document={"page": {"logx": False, "logy": False, "ratio": False}},
                     style=plot.base_style(), ranges={"x": [0, 1], "y": [0, 2], "x_tool": False, "y_tool": True})
    block = yoda_backend._plot_block(page)
    assert "XMin=0" in block and "YMin" not in block and "YMax" not in block


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


def test_the_yoda_backend_gives_the_ratio_the_divisions_paint_has(scratch):
    """mkhtml's ratio ticks are a fifth of the pad's range, and its script's set_yscale() resets any
    locator set before it: ratio.divisions' locators go just before the figure is saved."""
    yoda_backend = plot.backend("yoda")
    script = scratch / "d02-x01-y01.py"
    script.write_text("ratio0_ax.yaxis.set_major_locator(mpl.ticker.MultipleLocator(0.2))\n"
                      "ratio0_ax.set_ylim(0.5, 1.4999)\nratio0_ax.set_yscale('linear')\n"
                      "plt.savefig('x.pdf')\nplt.savefig('x.png')\n", encoding="utf-8")
    assert yoda_backend.ratio_ticks(script, 512)
    text = script.read_text(encoding="utf-8")
    assert text.index("MultipleLocator(0.1)") > text.index("set_yscale") and text.index("MultipleLocator(0.1)") < text.index("plt.savefig")
    assert "AutoMinorLocator(5)" in text
    assert not yoda_backend.ratio_ticks(script, 512)                    # already so: no second run
    assert yoda_backend.ratio_ticks(script, 508) and "MultipleLocator(0.2))\nratio0_ax.yaxis.set_minor" in script.read_text()
    assert script.read_text(encoding="utf-8").count(yoda_backend.MARK) == 1


# ── "default": keep it as it is (V55): a child's is its parent's; [plot]'s sets nothing ──────────

DRAWING = ("backend", "formats", "objects", "ratio", "y_gutter", "x_gutter", "logy", "logx", "auto_range",
           "void_empty", "min_entries", "range_pad", "root_style")


def test_every_drawing_option_takes_default(scratch):
    run = validated(scratch, **{key: "default" for key in DRAWING})
    assert plot.backends(run.plot) == ["root"] and plot.formats_of(run.plot) == ["pdf"]
    assert plot.run_style(run) == {}                                   # no root_style file


def page(settings, path="/photo_eic/d01-x01-y01", with_data=True):
    return plot.page_settings(settings, path, "d01", Path("/tmp/x"), with_data)[0]


def test_default_is_what_the_tool_does_by_itself():
    ours = page({})                                                    # nothing set: the runner's defaults
    native = page({key: "default" for key in ("logy", "ratio", "auto_range", "void_empty", "min_entries", "y_gutter")})
    assert ours["auto_range"] and not native["auto_range"]             # the tool's own range
    assert (native["void_empty"], native["min_entries"]) == (False, 0)
    assert native["logy"] and native["y_gutter"] == "default"          # photo_eic's .plot says LogY=1
    assert native["ratio"] and not page({"ratio": "default"}, with_data=False)["ratio"]   # mkhtml's rule


def test_an_objects_default_keeps_what_plot_says():
    """V55: "default" in a child is its parent's value; only at the top level does the tool decide."""
    settings = {"logy": False, "title": "every page", "object": {"d01-*": {"logy": "default", "title": "default"}}}
    shown = page(settings)
    assert shown["logy"] is False and shown["title"] == "every page"   # [plot]'s, inherited
    assert page({"object": {"d01-*": {"logy": "default"}}})["logy"] == page({})["logy"]   # no parent: as if absent


def test_a_style_default_falls_through_to_the_layer_below():
    plot.check_style({"legend": {"position": "default"}, "ratio": {"divisions": "default"}}, "here")
    merged = plot.merge_style({"legend": {"position": "top-left"}}, {"legend": {"position": "default"}})
    assert merged == {"legend": {"position": "top-left"}}
    assert plot.merge_style({}, {"legend": {"position": "default"}}) == {"legend": {}}


def test_an_object_value_of_the_wrong_kind_is_refused(scratch):
    with pytest.raises(HepError, match="must be true or false"):
        validated(scratch, object={"d01-*": {"logy": "yes"}})
    validated(scratch, object={"d01-*": {"logy": "default", "ratio": True}})


def test_the_yoda_backend_has_nothing_to_honour_in_a_default(scratch):
    validated(scratch, backend="yoda", style={"legend": {"position": "default"}, "page": {"dpi": "default"}})


def test_macros_are_expanded_by_us_in_and_out_of_math():
    """V48: Rivet's own \\GeV needs \\xspace, which matplotlib's LaTeX does not define."""
    assert plot.macros(r"$Q^2<1\ \GeV^2$ in \GeV, \pT") == r"$Q^2<1\ \mathrm{GeV}^2$ in GeV, $p_\mathrm{T}$"


@pytest.mark.parametrize("curves, expected", [
    ([[(0, 1, 1.0, 0.0), (1, 2, 1.0, 0.0)]], (0.5, 1.5)),                   # all near 1: the range
    ([[(0, 1, 2.0, 0.1), (1, 2, 1.0, 0.0)]], (0.5, 1.1 * 2.1)),             # widened, with Paint's 10 %
    ([[(0, 1, 8.0, 0.0)]], (0.5, 3.0)),                                     # never past the limits
    ([[(5, 6, 9.0, 0.0)]], (0.5, 1.5)),                                     # a bin outside x is not looked at
])
def test_the_yoda_ratio_window_is_paint_s(yoda_backend, curves, expected):
    reference = [(0, 1, 1.0, 0.0), (1, 2, 1.0, 0.0), (5, 6, 1.0, 0.0)]
    window = yoda_backend.ratio_window(curves, reference, (0, 2), {"range": [0.5, 1.5], "limits": [0.0, 3.0]})
    assert window == pytest.approx(expected)


def test_a_best_legend_lets_matplotlib_choose(yoda_backend, scratch):
    """V49: mkhtml anchors the legend at a corner; "best" leaves the spot to matplotlib."""
    script = scratch / "page.py"
    script.write_text("ax.add_artist(ax.legend(legend_items,\n    loc='upper right',\n"
                      "    bbox_to_anchor=(0.97, 0.97),markerfirst=False))\n", encoding="utf-8")
    assert yoda_backend.best_legend(script) and "loc='best',markerfirst=False))" in script.read_text()
    assert not yoda_backend.best_legend(script)                          # once only


def test_yoda_sizes_the_legend_title_by_text_header(yoda_backend):
    """V50: matplotlib sizes a legend title from legend.title_fontsize (else font.size), not from the
    entries; the backend sets both, from text.legend and text.header."""
    from types import SimpleNamespace
    page = SimpleNamespace(document={"page": {"logx": False, "logy": False, "ratio": False}}, overrides={},
                           ranges={"x": (0, 1), "y": (0, 1)}, object="/photo_eic/d01-x01-y01",
                           style={"legend": {"position": "top-right"}, "text": {"legend": 7.0, "header": 8.5}})
    block = yoda_backend._plot_block(page)
    assert "LegendFontSize=7; plt.rcParams['legend.title_fontsize'] = 8.5" in block
