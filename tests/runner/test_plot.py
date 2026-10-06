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
              figures={"f": {"objects": ["d04-*"], "logy": True, "style": {"legend": {"position": [0.5, 0.9]}}}})


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
    ({"figures": {"f": {"objects": ["d01*"], "LegendXPos": 0.5}}}, "LegendXPos"),         # v1 parsed it and dropped it
    ({"figures": {"f": {"objects": ["d01*"], "legend": "centre"}}}, "legend"),
    ({"y_gutter": -1}, "gutter"),
    ({"x_gutter": "auto"}, "gutter"),
    ({"figures": {"f": {"objects": ["d01*"], "y_gutter": -0.5}}}, "gutter"),
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
    ("5x41 GeV (#sqrt{s} = 28.6 GeV)", r"5x41 GeV $(\sqrt{\mathrm{s}}$ = 28.6 GeV)"),   # upright, as TLatex drew it
    ("p_{T0}^{ref} = 3.0 GeV", r"$\mathrm{p}_{\mathrm{T0}}^{\mathrm{ref}}$ = 3.0 GeV"),
    ("#hat{p}_{T} > 2 GeV", r"$\hat{\mathrm{p}}_{\mathrm{T}}$ $>$ 2 GeV"),
    ("R: 0.4", "R  0.4"),                                                 # ':' separates mkhtml's options
    ("PDF4LHC21_40_pdfas", "PDF4LHC21_40_pdfas"),                        # TLatex's rule: a bare _ is itself
    ("E_T jets", "E_T jets"),
    (r"PDF4LHC21\_40", "PDF4LHC21_40"),                                  # the escapes are the characters
    (r"\#1 \^2", "#1 ^2"),
    (r"x_1\_a_{2}", r"$\mathrm{x}\_1\_\mathrm{a}_{2}$"),                 # literal underscores inside math
    ("E_{T} > 5", r"$\mathrm{E}_{\mathrm{T}}$ $>$ 5"),                    # V51: > in LaTeX's text font is ¿
])
def test_a_tlatex_label_is_read_as_latex_and_mkhtml_gets_it(root, latex):
    """V65: one label language. A TLatex label (a config not yet migrated) is converted on reading."""
    from runner import labels
    assert labels.mathtext(labels.canonical(root)) == latex


@pytest.mark.parametrize("label", ["5x41 GeV (#sqrt{s} = 28.6 GeV)", "p_{T0}^{ref} = 3.0 GeV", "#hat{p}_{T} > 2 GeV",
                                   "PDF4LHC21_40_pdfas", "e^{-}", "E_{T} > 5", "#bf{x}_{1}", "k_{T}, 18x275"])
def test_a_tlatex_label_draws_the_same_in_root_after_the_round_trip(label):
    from runner import labels
    assert labels.tlatex(labels.canonical(label)) == label


def test_tlatex_keeps_text_as_text():
    """V65: the sub- and superscript rule is math's; a bare _ in text stays the character (V41)."""
    from runner import labels
    assert labels.tlatex("PDF4LHC21_40 x_1") == "PDF4LHC21_40 x_1"
    assert labels.tlatex(r"$x\_1$") == "#it{x}_1"           # math italic; \_ the character


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
    validated(scratch, y_gutter="default", x_gutter=0, figures={"f": {"objects": ["d04*"], "y_gutter": "default"}})
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
                           data=(source, "/REF/ZEUS_2012_I1116258/d01-x01-y01"), document={"page": {}})
    ref = yoda_backend._reference(yoda, page)
    whole = yoda.read(str(page.data[0]))[page.data[1]]
    assert ref.path() == "/REF/photo_eic/d01-x01-y01"
    assert list(ref.xEdges()) == [17, 21, 25, 29, 35, 41, 47] and len(whole.xEdges()) > 7
    page.document["page"]["normalise"] = "area"                         # V68: the data as the curves
    area = yoda_backend._reference(yoda, page)
    assert sum(b.val() * (b.xMax() - b.xMin()) for b in area.bins()) == pytest.approx(1.0)
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


def page(settings, path="/photo_eic/d01-x01-y01", with_data=True, child=None):
    return plot.page_settings(settings, path, "d01", Path("/tmp/x"), with_data, child=child)[0]


def test_default_is_what_the_tool_does_by_itself():
    ours = page({})                                                    # nothing set: the runner's defaults
    native = page({key: "default" for key in ("logy", "ratio", "auto_range", "void_empty", "min_entries", "y_gutter")})
    assert ours["auto_range"] and not native["auto_range"]             # the tool's own range
    assert (native["void_empty"], native["min_entries"]) == (False, 0)
    assert native["logy"] and native["y_gutter"] == "default"          # photo_eic's .plot says LogY=1
    assert native["ratio"] and not page({"ratio": "default"}, with_data=False)["ratio"]   # mkhtml's rule


def test_an_objects_default_keeps_what_plot_says():
    """V55: "default" in a child is its parent's value; only at the top level does the tool decide."""
    settings = {"logy": False, "title": "every page"}
    shown = page(settings, child={"objects": ["d01-*"], "logy": "default", "title": "default"})
    assert shown["logy"] is False and shown["title"] == "every page"   # [plot]'s, inherited
    assert page({}, child={"logy": "default"})["logy"] == page({})["logy"]   # no parent: as if absent


def test_a_figure_overrides_every_page_key_of_plot(scratch):
    """Every [plot] key marked `page` in the schema is a figure's too, meaning the same for its pages."""
    from runner import schema
    page_keys = {k for k, e in schema.keys("plot").items() if e.get("page")}
    assert {"auto_range", "void_empty", "min_entries", "range_pad", "use_data", "band", "ratio"} <= page_keys
    assert page_keys | {"x_label", "y_label", "style"} | set(schema.FIGURE_OWN) == set(schema.keys("figure"))
    assert not {"backend", "formats", "data", "root_style"} & set(schema.keys("figure"))
    settings = {"auto_range": True, "min_entries": 5}
    shown = page(settings, child={"auto_range": False, "min_entries": "default", "range_pad": 2, "void_empty": True})
    assert (shown["auto_range"], shown["min_entries"], shown["range_pad"], shown["void_empty"]) == (False, 5, 2, True)
    overlay = {"objects": ["d01-*"], "ratio": True, "style": {"ratio": {"range": [0.8, 1.1]}}, "use_data": False}
    validated(scratch, ratio=False, figures={"f": {**overlay, "class": "overlay"}, "g": {"objects": ["d03-*"], "min_entries": 3},
                                             "h": {"objects": ["d02-*"], "use_data": False, "band": []}})


def test_a_figure_band_must_be_a_curve_axis_too(scratch):
    from helpers import plan
    run, conf, _ = plan(raw(run__cfgs__one__sweeps=["pdf"], run__cfgs__one__plot_points=["pdf"],
                            plot={"figures": {"f": {"objects": ["d01-*"], "band": ["pdf"]}}}), scratch)
    with pytest.raises(HepError, match=r"\[plot.figures.f\].band names pdf"):
        plot.check_figures(run, conf)


def test_a_merged_figure_merges_curve_axes_it_does_not_band(scratch):
    """V82: over names curve axes, checked at plan time, and is not banded too."""
    from helpers import plan
    run, conf, _ = plan(raw(run__cfgs__one__sweeps=["pdf"], run__cfgs__one__plot_points=["pdf"],
                            plot={"figures": {"m": {"class": "merged", "objects": ["d01-*"], "over": ["pdf"]}}}), scratch)
    with pytest.raises(HepError, match=r"\[plot.figures.m\].over names pdf, which is not a curve axis"):
        plot.check_figures(run, conf)
    run, conf, _ = plan(raw(run__cfgs__one__sweeps=["pdf"],
                            plot={"figures": {"m": {"class": "merged", "objects": ["d01-*"], "over": ["pdf"], "band": ["pdf"]}}}), scratch)
    with pytest.raises(HepError, match="both merges and bands pdf"):
        plot.check_figures(run, conf)
    run.plot["figures"]["m"].pop("band")
    plot.check_figures(run, conf)


def test_a_compare_figure_pairs_configurations_of_one_shape(scratch):
    """V83: two configurations or more, the sweep_runs ones by default, each with the same axes."""
    from helpers import plan
    figure = {"class": "compare", "objects": ["d01-*"]}
    run, conf, _ = plan(raw(run__cfgs__one__sweeps=["pdf"], plot={"figures": {"c": figure}}), scratch)
    with pytest.raises(HepError, match="needs two configurations or more"):
        plot.check_figures(run, conf)
    run, conf, _ = plan(raw(run__cfgs__one__sweeps=["pdf"], run__cfgs__two={"tools": ["pythia"], "sweeps": []},
                            plot={"figures": {"c": {**figure, "configurations": ["one", "two"]}}}), scratch)
    with pytest.raises(HepError, match=r"differ in their axes: one \(pages: none; curves: pdf\), two \(pages: none; curves: none\)"):
        plot.check_figures(run, conf)
    from helpers import parse
    run = parse(raw(run__sweep_runs=True, run__configuration=None, run__cfgs__one__sweeps=["pdf"],
                    run__cfgs__two={"tools": ["pythia"], "sweeps": ["pdf"]}, plot={"figures": {"c": figure}}), scratch)
    assert [c.ref for c in plot.compared(run, plot.figures(run)[0])] == ["one", "two"]


@pytest.mark.parametrize("figure, message", [
    ({"class": "overlay"}, "a figure needs objects"),
    ({"objects": ["d01-*"], "labels": ["a"]}, "a defined figure takes no labels"),
    ({"objects": ["d01-*"], "name": "x"}, "a defined figure takes no name"),
    ({"class": "overlay", "objects": ["d01-*", "d02-*"], "labels": ["a"]}, "one label per object"),
    ({"class": "stacked", "objects": ["d01-*"]}, "class must be one of defined, overlay"),
    ({"objects": ["d01-*"], "formats": ["png"]}, "unknown key 'formats'"),
    ({"class": "merged", "objects": ["d01-*"]}, "is a merged figure's, and it needs one"),
    ({"class": "merged", "objects": ["d01-*"], "over": ["pdf"], "labels": ["a"]}, "a merged figure takes no labels"),
    ({"class": "overlay", "objects": ["d01-*"], "over": ["pdf"]}, "a overlay figure merges nothing"),
    ({"objects": ["d01-*"], "configurations": ["a", "b"]}, "configurations is a compare figure's"),
    ({"class": "derived", "objects": ["d01-*", "d05-*"]}, "is a derived figure's, and it needs one"),
    ({"objects": ["d01-*"], "op": "ratio"}, "a defined figure derives nothing"),
    ({"class": "derived", "op": "ratio", "objects": ["d01-*"]}, 'op = "ratio" takes 2 objects, not 1'),
    ({"class": "derived", "op": "projection-x", "objects": ["a", "b"]}, 'takes 1 object, not 2'),
    ({"class": "derived", "op": "quotient", "objects": ["a", "b"]}, "op must be one of ratio"),
    ({"class": "scan", "x": "pdf"}, "a scan figure needs x, and y one of"),
    ({"class": "scan", "x": "pdf", "y": "median", "objects": ["d01-*"]}, "not 'median'"),
    ({"class": "scan", "x": "pdf", "y": "bin:2"}, "a figure needs objects"),
    ({"class": "scan", "x": "pdf", "y": "sigma", "objects": ["a", "b"]}, 'y = "sigma" reads one object'),
    ({"objects": ["d01-*"], "x": "pdf"}, "x and y are a scan figure's"),
    ({"class": "sheet"}, "a sheet needs pages"),
    ({"class": "sheet", "pages": ["*/d01*"], "logy": True}, "a sheet takes no logy"),
    ({"objects": ["d01-*"], "columns": 2}, "pages and columns are a sheet's"),
    ({"class": "compare", "objects": ["d01-*"], "configurations": ["a", "b"], "labels": ["x"]}, "one label per configuration"),
])
def test_a_figure_is_checked_when_the_file_is_read(scratch, figure, message):
    with pytest.raises(HepError, match=message):
        validated(scratch, figures={"f": figure})


@pytest.mark.parametrize("old", ["overlay", "object"])
def test_the_tables_figures_replaced_are_refused_with_the_figure_to_write(scratch, old):
    """V81, break and migrate: hep migrate rewrites them."""
    with pytest.raises(HepError, match=rf"\[plot.{old}\] is a figure now") as error:
        validated(scratch, **{old: {"d01-*": {"objects": ["d01-*"]}}})
    assert error.value.hint == "hep migrate rewrites it"


def test_the_figures_of_a_run_in_file_order(scratch):
    run = validated(scratch, figures={"tails": {"objects": ["d04-*"], "logy": True},
                                      "eta": {"class": "overlay", "objects": ["d02-*", "d03-*"], "name": "algorithms"}})
    shown = [(f.key, f.kind, f.name, f.objects, f.table) for f in plot.figures(run)]
    assert shown == [("tails", "defined", "tails", ("d04-*",), {"logy": True}),
                     ("eta", "overlay", "algorithms", ("d02-*", "d03-*"), {})]


def test_a_style_default_falls_through_to_the_layer_below():
    plot.check_style({"legend": {"position": "default"}, "ratio": {"divisions": "default"}}, "here")
    merged = plot.merge_style({"legend": {"position": "top-left"}}, {"legend": {"position": "default"}})
    assert merged == {"legend": {"position": "top-left"}}
    assert plot.merge_style({}, {"legend": {"position": "default"}}) == {"legend": {}}


def test_an_object_value_of_the_wrong_kind_is_refused(scratch):
    with pytest.raises(HepError, match="must be true or false"):
        validated(scratch, figures={"f": {"objects": ["d01-*"], "logy": "yes"}})
    validated(scratch, figures={"f": {"objects": ["d01-*"], "logy": "default", "ratio": True}})


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


def test_a_page_text_cites_the_points():
    """V66: {cell}, {q:…} and a folder's texts are filled before the text is read as LaTeX."""
    fill = plot.filler([{"cell": "18x275", "opt:ETMIN": "17"}] * 2, "here")
    shown = plot.page_settings({"legend_header": "$E_T > {opt:ETMIN}$ GeV", "title": "{cell}"},
                               "/photo_eic/d01-x01-y01", "d01", Path("/tmp/x"), True, fill=fill)[0]
    assert shown["legend_header"] == "$E_T > 17$ GeV" and shown["title"] == "18x275"
    assert fill(r"$\mathrm{d}\sigma/\mathrm{d}E_T$") == r"$\mathrm{d}\sigma/\mathrm{d}E_T$"   # LaTeX groups untouched


def test_a_page_text_that_differs_between_its_curves_is_refused():
    with pytest.raises(HepError, match="differs between the curves"):
        plot.filler([{"q:pdf": "MSTW"}, {"q:pdf": "NNPDF"}], "here")("{q:pdf}")
    with pytest.raises(HepError, match="nothing the points have"):
        plot.filler([{"opt:ETMIN": "17"}], "here")("{opt:ETMN}")


def test_a_quantity_value_has_its_own_curve_look(scratch):
    """V67: styles = [...], one per value, reach the value's curves; a later curve axis's key wins."""
    from helpers import plan
    styles = [{"colour": "#EE3311", "line": "dashed"}, {"width": 2.0, "colour": "default"}]
    data = raw(run__cfgs__one__sweeps=["pdf"], quantities__pdf__styles=styles)
    run, _, first = plan(data, scratch)
    _, _, second = plan(data, scratch, point=1)
    assert plot._curve_look(run, first, [["pdf"]]) == {"colour": "#EE3311", "line": "dashed"}
    assert plot._curve_look(run, second, [["pdf"]]) == {"width": 2.0}          # "default": the palette's colour
    assert plot._curve_look(run, first, []) == {}


@pytest.mark.parametrize("styles, message", [
    ([{"line": "wavy"}, {}], "is not one"), ([{"colour": "#EE3311"}], "one entry per value"),
    ([{"color": "#EE3311"}, {}], "did you mean 'colour'"), ([{"width": 0}, {}], "is not one")])
def test_a_curve_look_is_checked(scratch, styles, message):
    with pytest.raises(HepError, match=message):
        parse(raw(quantities__pdf__styles=styles), scratch)


def test_the_yoda_backend_draws_hex_colours_only(scratch):
    run = parse(raw(plot={"backend": "both"}, quantities__pdf__styles=[{"colour": "kRed"}, {}]), scratch)
    with pytest.raises(HepError, match="cannot draw the curve colour"):
        plot.validate(run)
    plot.validate(parse(raw(plot={"backend": "both"}, quantities__pdf__styles=[{"colour": "#EE3311"}, {}]), scratch))


def test_normalise_is_a_page_key_a_child_may_set(scratch):
    """V68: false unless asked; an object's table overrides [plot]'s; "area" or false only."""
    assert page({})["normalise"] is False
    assert page({"normalise": "area"})["normalise"] == "area"
    assert page({"normalise": "area"}, child={"normalise": False})["normalise"] is False
    with pytest.raises(HepError, match="must be one of area, false"):
        validated(scratch, normalise="peak")


def test_the_yoda_backend_normalises_as_paint(yoda_backend):
    import yoda
    estimate = yoda.BinnedEstimate1D([0.0, 1.0, 3.0], "/x")
    estimate.bin(1).setVal(2.0), estimate.bin(1).setErr(0.5), estimate.bin(2).setVal(1.0)
    assert yoda_backend._normalise(estimate)
    assert [estimate.bin(i).val() for i in (1, 2)] == [0.5, 0.25] and estimate.bin(1).errDownUp("")[1] == 0.125


def test_a_cited_placeholder_is_checked_before_any_point_runs(scratch):
    """V66: a typo is refused at plan time, with what the points have."""
    from helpers import plan
    run, _, p = plan(raw(static={"pdf": "MSTW08lo"}, plot={"title": "{opt:ETMIN} {q:pdf}", "figures": {"o": {"class": "overlay", "objects": ["d01-*"], "labels": ["{cell}"]}}}), scratch)
    plot.check_texts(run, [p])
    run, _, p = plan(raw(plot={"legend_header": "{opt:ETMN}"}), scratch)
    with pytest.raises(HepError, match=r"cites \{opt:ETMN\}") as error:
        plot.check_texts(run, [p])
    assert "opt:ETMIN" in error.value.hint


def test_a_band_folds_its_axis_into_one_curve_per_other_value():
    """V69: per value of the other curve axes (and variant), the band axis's first value with the rest as members."""
    from types import SimpleNamespace as P
    plans = [P(point=P(name=f"{e}_{p}", choice={"energy": e, "pdf": p})) for e in (0, 1) for p in (2, 0, 1)]
    curves = [(plan, "/a/d01") for plan in plans]
    folded = plot._banded(curves, [["energy"], ["pdf"]], ["pdf"], lambda plan, full: 0)
    assert [(c.point.name, [m.point.name for m, _ in ms]) for c, _, ms in folded] == [
        ("0_0", ["0_1", "0_2"]), ("1_0", ["1_1", "1_2"])]
    assert [len(ms) for _, _, ms in plot._banded(curves, [["energy"], ["pdf"]], [], lambda *a: 0)] == [0] * 6


def test_a_band_must_be_a_curve_axis(scratch):
    from helpers import plan
    run, conf, _ = plan(raw(run__cfgs__one__sweeps=["pdf"], run__cfgs__one__plot_points=["pdf"], plot={"band": ["pdf"]}), scratch)
    with pytest.raises(HepError, match="not a curve axis"):
        plot.check_figures(run, conf)
    run, conf, _ = plan(raw(run__cfgs__one__sweeps=["pdf"], plot={"band": ["pdf"]}), scratch)
    plot.check_figures(run, conf)


def test_the_yoda_backend_draws_the_envelope_as_the_errors(yoda_backend):
    import yoda
    central, low, high = (yoda.BinnedEstimate1D([0.0, 1.0, 2.0], "/x") for _ in range(3))
    for estimate, values in ((central, (2.0, 1.0)), (low, (1.5, float("nan"))), (high, (3.0, 1.0))):
        for i, v in enumerate(values, start=1):
            estimate.bin(i).setVal(v), estimate.bin(i).setErr(0.1)
    assert yoda_backend._envelope(central, [low, high])
    assert central.bin(1).errDownUp("") == (-0.5, 1.0) and not central.bin(2).sources()   # a NaN member: no band


def test_the_root_pages_get_an_index(scratch):
    """V70: a section per cell, each page by its PNG (linked to its PDF), else an embedded PDF."""
    for name in ("cell_a/d01.png", "cell_a/d01.pdf", "cell_b/d01.pdf"):
        (scratch / name).parent.mkdir(parents=True, exist_ok=True)
        (scratch / name).write_bytes(b"x")
    index = plot.write_index(scratch, "run <1>", [("cell_a", "cell_a/d01", scratch / "cell_a" / "d01"),
                                                  ("cell_b", "cell_b/d01", scratch / "cell_b" / "d01"),
                                                  ("cell_b", "cell_b/gone", scratch / "cell_b" / "gone")])
    text = index.read_text(encoding="utf-8")
    assert "<title>run &lt;1&gt;</title>" in text and text.count("<h2>") == 2
    assert '<a href="cell_a/d01.pdf"><img src="cell_a/d01.png"' in text
    assert '<object data="cell_b/d01.pdf"' in text and "gone" not in text


def test_mpl_is_a_backend_and_both_is_still_root_and_yoda(scratch):
    """V71: "mpl" may be named; "both" keeps V28's meaning; mpl refuses what mkhtml cannot do, in its own name."""
    assert plot.backends({"backend": "both"}) == ["root", "yoda"]
    assert plot.backends({"backend": ["mpl", "root"]}) == ["root", "mpl"]
    with pytest.raises(HepError, match='backend = "mpl"'):
        validated(scratch, backend="mpl", style={"page": {"dpi": 100}})
    mpl = plot.backend("mpl")
    from yoda.plotting.mlp_preprocessor import preprocess
    assert mpl._raw(preprocess(r"$a$\newline$b$")) == "$a$\n$b$" and mpl.INDEX


@pytest.mark.parametrize("label, latex", [
    ("E_{T} > 4 GeV", "$E_{T}$ > 4 GeV"), ("#hat{p}_{T} > 2 GeV", r"$\hat{p}_{T}$ > 2 GeV"),
    ("p_{T0}^{ref} = 3.0 GeV", r"$p_{T0}^{\mathrm{ref}}$ = 3.0 GeV"), ("anti-k_{T}", "anti-$k_{T}$"),
    ("27x920 GeV (#sqrt{s} = 318.1 GeV)", r"27x920 GeV ($\sqrt{s}$ = 318.1 GeV)"), ("e^{-}", "$e^{-}$"),
    ("MPI_{on}", r"$\mathrm{MPI}_{\mathrm{on}}$"), ("MSTW 2008 LO", "MSTW 2008 LO"), ("PDF4LHC21_40", "PDF4LHC21_40")])
def test_natural_latex_is_what_a_physicist_writes(label, latex):
    """V79: the configs' migration. Symbols in math, one letter italic, words upright; plain text as is."""
    from runner import labels
    assert labels.natural(label) == latex


def test_a_tlatex_label_in_a_run_toml_is_refused_with_its_latex(scratch):
    """V79 (B5, break and migrate)."""
    with pytest.raises(HepError, match="is TLatex") as error:
        parse(raw(quantities__pdf__labels=["E_{T} > 4", "b"]), scratch)
    assert "$E_{T}$ > 4" in error.value.hint and "hep migrate" in error.value.hint
    with pytest.raises(HepError, match="is TLatex"):
        validated(scratch, figures={"o": {"class": "overlay", "objects": ["d01-*"], "labels": ["k_{T}"]}})
    validated(scratch, title="$E_T$ jets", data={"file": "zeus_eic.yoda", "legend": "ZEUS", "map": {"d01-x01-y01": "/REF/X/d01"}})
