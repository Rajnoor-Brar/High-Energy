"""Sweeps, pages, the P2 checks, seeds and the point-count gate (docs/07_Record.md §8)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from runner import config, record, sweep, tools
from runner.errors import HepError

from helpers import plan, plans_of, raw

REPO = Path(__file__).resolve().parents[2]
COUNTS = tomllib.loads((REPO / "tests" / "reference" / "point_counts.toml").read_text(encoding="utf-8"))


CASES = [(f"PhotoProduction/{'eic' if run == 'eic' else 'zeus_validation'}", cfg, counts)
         for run, table in COUNTS.items() for cfg, counts in table.items()]


@pytest.mark.parametrize(("name", "cfg", "counts"), CASES, ids=[f"{n.split('/')[1]}/{c}" for n, c, _ in CASES])
def test_point_and_page_counts_equal_the_legacy_table(name, cfg, counts):
    run = config.load(name)
    conf = run.configuration(None if cfg == "default" else cfg)
    points = sweep.points(run, conf)
    assert (len(points), len(sweep.pages(conf, points))) == (counts["points"], counts["pages_v2"])


def test_every_eic_configuration_plans_and_its_seed_blocks_are_disjoint():
    """Within a plan no two points share events (V9, L4). Across configurations the seeds follow the
    generator: the same generator setup (single, pdf's NNPDF23lo point, inproc) gives the same
    seeds, and different setups never overlap."""
    by_basis: dict[str, int] = {}
    blocks = []
    run = config.load("PhotoProduction/eic")
    for key in run.configurations:
        _, _, _, plans = plans_of("PhotoProduction/eic", key)
        spans = sorted((p.seed, p.seed + p.threads) for p in plans)
        assert all(a_end <= b_start for (_, a_end), (b_start, _) in zip(spans, spans[1:])), key
        for p in plans:
            basis = record.seed_basis(p)
            if len(plans) == len({record.seed_basis(q) for q in plans}):   # no clash moved it
                assert by_basis.setdefault(basis, p.seed) == p.seed, key
            blocks.append((p.seed, p.seed + p.threads, basis))
    shared = {k: v for k, v in by_basis.items() if sum(1 for *_, b in blocks if b == k) > 1}
    assert shared, "single, pdf and inproc share a generator setup"
    unique = sorted({(start, end, basis) for start, end, basis in blocks})
    assert all(a[1] <= b[0] or a[2] == b[2] for a, b in zip(unique, unique[1:]))


def test_entangled_quantities_move_together_and_axes_form_a_grid(scratch):
    data = raw(run__cfgs__one__sweeps=["pdf", ["a", "b"]],
               quantities__a={"values": [1, 2, 3], "tags": ["a1", "a2", "a3"], "key": {"pythia": "A:x"}},
               quantities__b={"values": [4, 5, 6], "tags": ["b1", "b2", "b3"], "key": {"pythia": "B:y"}})
    run = config.parse(data, scratch / "t.toml")
    points = sweep.points(run, run.configuration(None))
    assert len(points) == 2 * 3
    assert [p.name for p in points[:3]] == ["MSTW08lo_a1_b1", "MSTW08lo_a2_b2", "MSTW08lo_a3_b3"]


def test_pages_are_the_plot_points_grid():
    run, conf, points, _ = plans_of("PhotoProduction/eic", "energy_pdf")
    pages = sweep.pages(conf, points)
    assert len(pages) == 4 and all(len(members) == 4 for members in pages.values())


def test_the_consumer_table_of_energy_pdf(capsys):
    from runner.cli import print_plan
    run, conf, _, plans = plans_of("PhotoProduction/eic", "energy_pdf")
    for p in plans:
        tools.finalise(p, p.seed)
    print_plan(run, conf, plans[:1])
    text = capsys.readouterr().out
    assert "energies     = 5x41           → pythia:['Beams:eA', 'Beams:eB']" in text
    assert "pdf          = MSTW08lo       → pythia:PDF:pSet" in text
    assert "lepton       = ep             → pythia:Beams:idB" in text


def test_c9_an_undeclared_rivet_option_is_refused(scratch):
    data = raw(tools__rivet__options={"NOSUCH": 3})
    with pytest.raises(HepError, match="does not declare the option NOSUCH") as caught:
        plan(data, scratch)
    assert "ETMIN" in caught.value.hint


def test_c9_an_unknown_analysis_is_refused(scratch):
    with pytest.raises(HepError, match="no analysis 'photo_eci'"):
        plan(raw(tools__rivet__analyses=["photo_eci"]), scratch)


def test_c10_a_pdf_set_that_is_not_installed_is_refused(scratch):
    data = raw(static={"pdf": "x"}, quantities__pdf={"values": ["LHAPDF6:NoSuchSet"], "tags": ["x"]})
    with pytest.raises(HepError, match="not installed") as caught:
        plan(data, scratch)
    assert "lhapdf install NoSuchSet" in caught.value.hint


def one_pdf(value):
    return raw(static={"pdf": "x"}, quantities__pdf={"values": [value], "tags": ["x"]})


@pytest.mark.parametrize("value, line", [("LHAPDF6:MSTW2008lo68cl", "PDF:pSet = LHAPDF6:MSTW2008lo68cl"),
                                         ("LHAPDF6:MSTW2008lo68cl/3", "PDF:pSet = LHAPDF6:MSTW2008lo68cl/3"),
                                         (14, "PDF:pSet = 14")])
def test_pythia_gets_the_pdf_value_as_written(scratch, value, line):
    """No prefix is added: the value is LHAPDF6:<set>[/member], or one of Pythia's own sets."""
    _, _, p = plan(one_pdf(value), scratch)
    assert line in p.writes[p.rendered["pythia"].card_combined].splitlines()


def test_a_bare_lhapdf_set_name_for_pythia_is_refused(scratch):
    with pytest.raises(HepError, match="Pythia reads only as LHAPDF6:MSTW2008lo68cl") as caught:
        plan(one_pdf("MSTW2008lo68cl"), scratch)
    assert 'LHAPDF6:MSTW2008lo68cl' in caught.value.hint


def test_sherpa_takes_the_bare_set_name():
    from runner.quantities import check_provider
    check_provider("lhapdf:bare", "MSTW2008lo68cl", "x")
    with pytest.raises(HepError, match="takes the bare LHAPDF set name"):
        check_provider("lhapdf:bare", "LHAPDF6:MSTW2008lo68cl", "x")


def test_an_override_equal_to_the_base_card_does_not_change_the_identity(scratch):
    same = {"values": [3.2, 3.4], "tags": ["pt32", "pt34"], "key": {"pythia": "MultipartonInteractions:pT0Ref"}}
    _, _, without = plan(raw(quantities__pt0ref=same), scratch)
    _, _, redundant = plan(raw(quantities__pt0ref=same, static={"pt0ref": "pt32"}), scratch)
    _, _, real = plan(raw(quantities__pt0ref=same, static={"pt0ref": "pt34"}), scratch)
    ids = [record.identity(p) for p in (without, redundant, real)]
    assert ids[0] == ids[1] != ids[2]
    assert "MultipartonInteractions:pT0Ref = 3.2" in redundant.writes[redundant.rendered["pythia"].card_point]


def test_points_selects_by_tag_index_and_quantity():
    run, conf, points, _ = plans_of("PhotoProduction/eic", "energy_pdf")
    assert [p.name for p in sweep.select_points(run, conf, points, "MSTW08lo")][:1] == ["5x41_MSTW08lo"]
    assert len(sweep.select_points(run, conf, points, "energies=18x275")) == 4
    assert [p.index for p in sweep.select_points(run, conf, points, "3,16")] == [3, 16]
    with pytest.raises(HepError, match="matches no point"):
        sweep.select_points(run, conf, points, "nothing")


# ── exclude (V42): values a sweep leaves out, by their 1-based place ───────────────────────────

THREE = {"values": [3.0, 3.2, 3.4], "tags": ["pt30", "pt32", "pt34"], "key": {"pythia": "MultipartonInteractions:pT0Ref"}}


def swept(scratch, **changes):
    run = config.parse(raw(**changes), scratch / "t.toml")
    return sweep.points(run, run.configuration(None))


def test_exclude_leaves_values_out_of_the_sweep(scratch):
    got = swept(scratch, quantities__pt0ref={**THREE, "exclude": [2]}, run__cfgs__one__sweeps=["pdf", "pt0ref"])
    assert [p.name for p in got] == ["MSTW08lo_pt30", "MSTW08lo_pt34", "NNPDF23lo_pt30", "NNPDF23lo_pt34"]
    assert [p.index for p in got] == [1, 2, 3, 4]                     # numbered over what is swept
    assert got[1].choice == {"pdf": 0, "pt0ref": 2}                    # the value keeps its own place


def test_an_entangled_group_loses_the_value_any_of_its_quantities_excludes(scratch):
    alphas = {"values": [0.118, 0.130], "tags": ["as118", "as130"], "key": {"pythia": "SigmaProcess:alphaSvalue"},
              "exclude": [1]}
    got = swept(scratch, quantities__alphas=alphas, run__cfgs__one__sweeps=[["pdf", "alphas"]])
    assert [p.name for p in got] == ["NNPDF23lo_as130"]


def test_a_static_value_may_still_be_an_excluded_one(scratch):
    _, _, p = plan(raw(quantities__pt0ref={**THREE, "exclude": [2]}, static={"pt0ref": "pt32"}), scratch)
    assert p.values["pt0ref"] == 1


def test_exclude_changes_no_remaining_point(scratch):
    _, _, before = plan(raw(quantities__pt0ref=THREE, run__cfgs__one__sweeps=["pt0ref"]), scratch)
    _, _, after = plan(raw(quantities__pt0ref={**THREE, "exclude": [2, 3]}, run__cfgs__one__sweeps=["pt0ref"]), scratch)
    assert (before.point.name, before.identity) == (after.point.name, after.identity)


@pytest.mark.parametrize("exclude, message", [
    ([0], "not a value's place"), ([4], "not a value's place"), ([True], "not a value's place"),
    (["pt32"], "not a value's place"), ([1, 2, 3], "leaves no value"),
])
def test_what_exclude_refuses(scratch, exclude, message):
    with pytest.raises(HepError, match=message):
        swept(scratch, quantities__pt0ref={**THREE, "exclude": exclude}, run__cfgs__one__sweeps=["pt0ref"])


def test_an_entangled_group_with_nothing_left_is_refused(scratch):
    alphas = {"values": [0.118, 0.130], "tags": ["as118", "as130"], "key": {"pythia": "SigmaProcess:alphaSvalue"},
              "exclude": [2]}
    with pytest.raises(HepError, match="no value"):
        swept(scratch, quantities__alphas=alphas, quantities__pdf={**raw()["quantities"]["pdf"], "exclude": [1]},
              run__cfgs__one__sweeps=[["pdf", "alphas"]])
