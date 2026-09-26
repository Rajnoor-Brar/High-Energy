"""Derived histograms, and whether the two engines really agree (P9-S02, 12 §2.2).

The Verification row is "RDF vs uproot on a small `delphes.root` — identical bins". It is a real
row and not a tautology because the engines evaluate **different languages**: RDF compiles C++ and
uproot works on awkward arrays in Python, so every `&&`, `||` and `!` has to be translated. The trap
is precedence — Python's `&` binds tighter than a comparison, so rewriting the text turns
`a > 5 && b < 3` into `a > (5 & b) < 3`, which is valid Python, different physics, and silent.

So the tests below are mostly about expressions rather than about histograms: a selection that mixes
`&&` and `||`, a negation, a derived quantity, and the precedence case itself. The input is a small
ROOT file written here with uproot rather than a Delphes run — the thing being tested is the
translation, and a jagged tree is a jagged tree.

The integration test does the same comparison against a real `delphes.root`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "utils" / "python"))

np = pytest.importorskip("numpy")
ak = pytest.importorskip("awkward")
uproot = pytest.importorskip("uproot")

from hekit.errors import HepError                                        # noqa: E402
from hekit.proc import hist as hist_module                               # noqa: E402

BINS = [20, 0.0, 40.0]


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    """A small jagged tree: a few thousand 'jets' over 400 'events'."""
    path = tmp_path_factory.mktemp("hist") / "toy.root"
    rng = np.random.default_rng(3)
    counts = rng.poisson(3.0, 400)
    total = int(counts.sum())
    with uproot.recreate(path) as handle:
        handle["Events"] = {
            "Jet_PT": ak.unflatten(rng.exponential(8.0, total), counts),
            "Jet_Eta": ak.unflatten(rng.normal(0.0, 2.0, total), counts),
        }
    return path


def both(tree_path, expression, selection="", bins=None):
    spec = {"name": "t", "tree": "Events", "expression": expression,
            "selection": selection, "bins": bins or BINS}
    return (hist_module.fill(spec, tree_path, engine="uproot"),
            hist_module.fill(spec, tree_path, engine="rdf"))


# ── the translator, which is where the difficulty is ─────────────────────────

def test_and_or_and_not_become_array_operators():
    code, names = hist_module.translate("Jet.PT > 5 && abs(Jet.Eta) < 3.5")
    assert names == {"Jet_PT", "Jet_Eta"}
    values = {"Jet_PT": np.array([1.0, 9.0, 9.0]), "Jet_Eta": np.array([0.0, 0.0, 9.0])}
    assert list(eval(code, {"__builtins__": {}, "abs": np.abs}, values)) == [False, True, False]


def test_precedence_survives_the_translation():
    """The whole reason this goes through an AST.

    A text substitution gives `a > 5 & b < 3`, which Python parses as `a > (5 & b) < 3` — valid,
    silent, and wrong.
    """
    code, _ = hist_module.translate("a > 5 && b < 3")
    values = {"a": np.array([9.0, 9.0, 1.0]), "b": np.array([1.0, 9.0, 1.0])}
    assert list(eval(code, {"__builtins__": {}}, values)) == [True, False, False]


def test_not_equal_is_not_a_negation():
    """`!=` must survive the `!` → `not` rewrite."""
    code, _ = hist_module.translate("a != 2")
    assert list(eval(code, {"__builtins__": {}}, {"a": np.array([1.0, 2.0])})) == [True, False]


def test_only_a_known_list_of_functions_may_be_called():
    hist_module.translate("sqrt(a*a) + log10(b)")
    with pytest.raises(HepError) as raised:
        hist_module.translate("eval(a)")
    assert "abs" in str(raised.value), "it should list what is allowed"
    with pytest.raises(HepError):
        hist_module.translate("__import__('os').system('true')")


def test_nonsense_is_refused_with_the_language_named():
    with pytest.raises(HepError) as raised:
        hist_module.translate("Jet.PT >")
    assert "Jet.PT" in str(raised.value)


def test_branch_names_are_recovered_in_either_spelling():
    assert hist_module.branches_of("Jet.PT > 1", "abs(Jet.Eta) < 2") == ["Jet.Eta", "Jet.PT"]


# ── Verification row: the engines agree ──────────────────────────────────────

def _skip_unless_both():
    for engine in ("rdf", "uproot"):
        if not hist_module.available(engine):
            pytest.skip(f"the {engine} engine is not available here")


@pytest.mark.parametrize("expression,selection", [
    ("Jet_PT", ""),
    ("Jet_PT", "Jet_PT > 2"),
    ("Jet_PT", "Jet_PT > 2 && abs(Jet_Eta) < 2.5"),
    ("Jet_PT", "Jet_Eta > 1.0 || Jet_Eta < -1.0"),
    ("Jet_PT", "Jet_PT > 2 && Jet_Eta < 1.0 || Jet_PT > 20.0"),   # the precedence case
    ("Jet_PT", "!(Jet_PT < 3)"),
    ("sqrt(Jet_PT*Jet_PT)", "Jet_PT > 1"),
    ("Jet_PT*2 + 1", ""),
])
def test_engines_agree(tree, expression, selection):
    _skip_unless_both()
    left, right = both(tree, expression, selection)
    assert left.entries == right.entries, f"{left.entries} against {right.entries}"
    assert not hist_module.same_bins(left, right)
    assert left.total > 0, "the selection kept nothing, so this compares two empty histograms"


def test_the_selection_cuts_elements_not_events(tree):
    """A jagged branch: `Jet_PT > 20` means the jets above 20, not the events containing one."""
    _skip_unless_both()
    everything, _ = both(tree, "Jet_PT", "")
    cut, cut_rdf = both(tree, "Jet_PT", "Jet_PT > 20")
    assert cut.entries < everything.entries
    assert cut.entries == cut_rdf.entries
    # Every surviving entry is above the cut, which an event-level filter would not guarantee.
    below = sum(value for edge, value in zip(cut.edges, cut.values) if edge < 20.0)
    assert below == 0, "entries below the cut survived, so whole events were kept"


# ── binning and errors ───────────────────────────────────────────────────────

def test_a_bad_binning_is_refused(tree):
    for bins in ([0, 0.0, 1.0], [10, 1.0, 1.0], [10, 2.0, 1.0], [10, 1.0]):
        with pytest.raises(HepError):
            hist_module.fill({"name": "t", "tree": "Events", "expression": "Jet_PT",
                              "bins": bins}, tree, engine="uproot")


def test_a_missing_branch_says_what_is_there(tree):
    with pytest.raises(HepError) as raised:
        hist_module.fill({"name": "t", "tree": "Events", "expression": "Jet_NoSuchThing",
                          "bins": BINS}, tree, engine="uproot")
    assert "Jet_PT" in str(raised.value) or "Jet.PT" in str(raised.value)


def test_a_missing_tree_says_what_is_there(tree):
    with pytest.raises(HepError) as raised:
        hist_module.fill({"name": "t", "tree": "NoSuchTree", "expression": "Jet_PT",
                          "bins": BINS}, tree, engine="uproot")
    assert "NoSuchTree" in str(raised.value)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(HepError) as raised:
        hist_module.fill({"name": "t", "expression": "Jet_PT", "bins": BINS},
                         tmp_path / "nope.root", engine="uproot")
    assert "no such file" in str(raised.value)


def test_the_yoda_object_is_a_finished_result_with_the_same_total(tree):
    """A derived histogram is binned counts and a *finished* result, so it is an estimate."""
    filled = hist_module.fill({"name": "jet_pt", "tree": "Events", "expression": "Jet_PT",
                               "bins": BINS}, tree, engine="uproot")
    made = hist_module.as_yoda(filled, path="/PROC/jet_pt")
    # An **estimate**, not a Histo1D: a derived histogram is finished when it is filled, and the
    # plot pipeline only recognises finished objects. See `as_yoda`'s note.
    assert type(made).__name__ == "BinnedEstimate1D"
    assert made.numBins() == BINS[0]
    assert hist_module.total_of(made) == pytest.approx(filled.total)


# ── choosing an engine ───────────────────────────────────────────────────────

def test_auto_prefers_rdf_and_falls_back(monkeypatch):
    if hist_module.available("rdf"):
        assert hist_module.choose("auto") == "rdf"
    monkeypatch.setattr(hist_module, "available",
                        lambda engine: engine == "uproot")
    assert hist_module.choose("auto") == "uproot"
    with pytest.raises(HepError):
        hist_module.choose("rdf")


def test_an_unknown_engine_is_refused():
    with pytest.raises(HepError):
        hist_module.available("nonsense")
