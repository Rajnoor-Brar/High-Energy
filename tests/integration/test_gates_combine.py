"""V35, end to end (slow: real Pythia and Rivet): two PDFs × two seeds with `combine = ["replica"]`.
Each PDF's merged YODA holds both seeds' events, and the pages have one curve per PDF, labelled by
the PDF, drawn from the merged files."""

from __future__ import annotations

import tomllib

import pytest

from support import hep
yoda = pytest.importorskip("yoda")

pytestmark = pytest.mark.slow

RUN = """\
[run]
name          = "seeds"
project       = "PhotoProduction"
configuration = "one"
event_count   = 1000
threads       = 2

[run.one]
sweeps  = ["pdf", "replica"]
combine = ["replica"]
tools   = [["pythia", "rivet"]]

[prelim]
fifo = ["events.hepmc"]

[tools.pythia]
tool        = "pythia"
baseconfig  = "photo_ep.cmnd"
output_file = "events.hepmc"

[tools.rivet]
tool        = "rivet"
input       = "events.hepmc"
analyses    = ["photo_eic"]
output_file = "photo.yoda"

[quantities.pdf]
values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_nlo_as_0119_qed"]
tags   = ["MSTW08lo", "NNPDF23nlo"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 NLO"]

[quantities.replica]
target = "pythia/seed"
values = [1, 2]
tags   = ["s1", "s2"]

[plot]
backend = "root"
formats = ["png"]
objects = ["*d01-x01-y01"]
"""


def test_each_pdf_is_its_seeds_merged_and_drawn_as_one_curve(scratch):
    config = scratch / "seeds.toml"
    config.write_text(RUN, encoding="utf-8")
    done = hep(scratch, config)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    assert "── combined: MSTW08lo" in done.stdout
    results = scratch / "results" / "PhotoProduction" / "seeds" / "one"
    for pdf in ("MSTW08lo", "NNPDF23nlo"):
        seeds = [yoda.read(str(results / f"{pdf}_{s}" / "photo.yoda"))["/RAW/_EVTCOUNT"].numEntries() for s in ("s1", "s2")]
        merged = yoda.read(str(results / pdf / "photo.yoda"))["/RAW/_EVTCOUNT"].numEntries()
        assert merged == sum(seeds) and min(seeds) > 900
    page = tomllib.loads(next((scratch / "output" / "PhotoProduction" / "seeds" / "one" / "plots").glob("*d01*.toml"))
                         .read_text(encoding="utf-8"))
    assert [c["label"] for c in page["curve"]] == ["MSTW 2008 LO", "NNPDF 2.3 NLO"]
    assert [c["object"].split("/")[0] for c in page["curve"]] == ["MSTW08lo", "NNPDF23nlo"]   # the groups, not the seeds
