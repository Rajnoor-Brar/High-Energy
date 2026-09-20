"""Rendering SINDARIN (P7-S04, 04 §5).

Whizard is the adapter where "base plus overrides" runs backwards: the point card goes **first** and
includes the base, because SINDARIN executes top to bottom and `integrate`/`simulate` read whatever
is set when they run. So the rule the other adapters state as "later wins" is here "the base may not
set what the plan owns", and it is the first thing tested.

The rest are things a real run found: particle names come from the model file, the beams line is
assembled from two halves, and the integration needs a card of its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "utils" / "python"))

from hekit.adapters import whizard                                       # noqa: E402
from hekit.errors import HepError                                        # noqa: E402

BASE = """# a base card
# hep: beam_structure = pdf_builtin, epa
model = SM
epa_q_max = 1.0 GeV
epa_mass = 0.000510998928
process p1 = q, A => q, gl
integrate (p1)
simulate (p1)
"""



def has_model() -> bool:
    try:
        return bool(whizard.model_names("SM"))
    except HepError:
        return False


class Seeds:
    point = 4242


class Point:
    name = "p1"
    beams = (2212, 11)
    energies = (275.0, 18.0)
    events = 50
    settings: tuple = ()


needs_model = pytest.mark.skipif(not has_model(), reason="Whizard's model files are not installed")


# ── the insertion rule (04 §5) ───────────────────────────────────────────────

def test_a_base_that_sets_the_event_count_is_refused():
    """It runs *after* the point card, so it would silently replace the plan's value."""
    with pytest.raises(HepError) as raised:
        whizard.check_card(BASE + "n_events = 1000\n", "photo_ep.sin")
    assert "the plan owns" in str(raised.value)
    assert "read *after*" in str(raised.value), "the message has to explain why the order matters"


def test_a_base_that_sets_the_seed_or_the_sample_is_refused():
    for line in ("seed = 7\n", '$sample = "x"\n', "sample_format = hepmc\n", "sqrts = 91.2\n"):
        with pytest.raises(HepError):
            whizard.check_card(BASE + line, "photo_ep.sin")


def test_an_ordinary_base_is_fine():
    whizard.check_card(BASE, "photo_ep.sin")


def test_a_quantity_may_not_set_the_event_count():
    class Bad(Point):
        settings = (("n_events", 10, "[quantity.n]"),)

    with pytest.raises(HepError):
        whizard.check_overrides(Bad(), "eic.toml")


# ── the beams, assembled from two halves ─────────────────────────────────────

@needs_model
def test_particle_names_come_from_the_model_file():
    """Whizard speaks its model's language; a hard-coded table would rot."""
    assert whizard.particle_name(2212) == "p"
    assert whizard.particle_name(11) == "e1"
    assert whizard.particle_name(-11) == "E1"
    assert whizard.particle_name(22) == "A"


@needs_model
def test_an_id_the_model_cannot_name_is_a_planning_error():
    with pytest.raises(HepError) as raised:
        whizard.particle_name(9999999)
    assert "no name for PDG" in str(raised.value)


def test_the_structure_function_chain_comes_from_the_base():
    assert whizard.beam_structure(BASE) == "pdf_builtin, epa"
    assert whizard.beam_structure("model = SM\n") == ""


@needs_model
def test_the_beams_line_joins_the_plans_half_and_the_cards_half():
    text = whizard.render_card(Point(), seeds=Seeds(), threads=1, base_text=BASE)
    assert "beams = p, e1 => pdf_builtin, epa" in text


@needs_model
def test_an_energy_pair_becomes_beams_momentum():
    text = whizard.render_card(Point(), seeds=Seeds(), threads=1, base_text=BASE)
    assert "beams_momentum = 275.0, 18.0" in text
    assert "sqrts =" not in text, "a pair is not a scalar"


@needs_model
def test_a_scalar_energy_becomes_sqrts():
    class Symmetric(Point):
        beams = (11, -11)
        energies = (91.2,)

    text = whizard.render_card(Symmetric(), seeds=Seeds(), threads=1, base_text=BASE)
    assert "sqrts = 91.2" in text
    assert "beams_momentum" not in text


# ── the order, and the run control ───────────────────────────────────────────

@needs_model
def test_the_base_is_included_last():
    """Everything the plan decides has to be assigned before the base's `integrate` reads it."""
    text = whizard.render_card(Point(), seeds=Seeds(), threads=1, base_text=BASE,
                               card_path="/cards/photo_ep.sin")
    include = text.index('include("/cards/photo_ep.sin")')
    for setting in ("beams =", "seed =", "n_events =", "?rebuild_grids"):
        assert text.index(setting) < include, f"{setting} must come before the include"


@needs_model
def test_the_sample_drops_whizards_own_suffix():
    """Whizard appends `.hepmc` to `$sample`, so the stem must not already carry it."""
    text = whizard.render_card(Point(), seeds=Seeds(), threads=1, base_text=BASE,
                               fifo="/results/p/events.hepmc")
    assert '$sample = "/results/p/events"' in text
    assert "sample_format = hepmc" in text


@needs_model
def test_a_setting_is_written_with_its_origin():
    class WithOverride(Point):
        settings = (("epa_q_max", 4.5, "[quantity.q2]"),)

    text = whizard.render_card(WithOverride(), seeds=Seeds(), threads=1, base_text=BASE)
    assert "epa_q_max = 4.5" in text
    assert "[quantity.q2]" in text


def test_a_string_setting_is_quoted():
    assert whizard.value("hello") == '"hello"'
    assert whizard.value(True) == "true"
    assert whizard.value(2.5) == "2.5"


# ── the integration card ─────────────────────────────────────────────────────

def test_the_integration_card_generates_nothing():
    """Otherwise the integration opens the FIFO and waits for a reader that has not started."""
    point_card = ('beams = p, e1\nseed = 1\nn_events = 50\n'
                  'sample_format = hepmc\n$sample = "/x/events"\ninclude("base.sin")\n')
    integration = whizard.integration_card(point_card)
    assert "n_events = 0" in integration
    assert "$sample" not in integration
    assert "sample_format" not in integration
    assert 'include("base.sin")' in integration, "it still has to build the processes"
    assert "beams = p, e1" in integration, "and integrate the right ones"


def test_the_parton_level_flag_is_reported():
    assert whizard.parton_level(BASE) is True
    assert whizard.parton_level(BASE + "?hadronization_active = true\n") is False


# ── the identity hash ────────────────────────────────────────────────────────

def test_card_defaults_reads_the_assignments():
    found = whizard.card_defaults(BASE)
    assert found["epa_q_max"] == "1.0 GeV"
    assert "process" not in found, "a process declaration is not an assignment"


def test_comments_are_not_settings():
    assert whizard.card_defaults("# seed = 9\n") == {}
