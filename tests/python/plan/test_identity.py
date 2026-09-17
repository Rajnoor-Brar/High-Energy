"""Identity hashing and seed blocks (P1-S04): 00/B1, 00/B2, 00/B15, D21.

The verification runs on the real PhotoProduction catalogue — the frozen legacy inputs translated to
schema 2 — so the properties are checked on the points that are actually run, not on toy data.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sweep"))
import v1_to_v2                                          # noqa: E402  the test translation helper
from hekit import sweep                                  # noqa: E402
from hekit.config import load_config                     # noqa: E402
from hekit.errors import HepError                        # noqa: E402
from hekit.plan import hashing, seeds                    # noqa: E402
from hekit.sweep.expand import Assignment                # noqa: E402

REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "tests" / "golden" / "inputs" / "PhotoProduction"
CARD = (INPUTS / "photo_ep.cmnd").read_bytes()
STUDIES = ("single", "pdf", "energies", "energy_pdf", "mpi", "mpi_onoff", "mpi_grid",
           "pthatmin", "process", "radius")


@pytest.fixture(scope="module")
def eic(tmp_path_factory) -> Path:
    return v1_to_v2.write_v2(INPUTS / "eic.toml", tmp_path_factory.mktemp("v2") / "eic.toml")


def points_of(path: Path, **arguments) -> tuple:
    config = load_config(path, machine_file=None, project="PhotoProduction")
    selection = sweep.select(config, **arguments)
    return config, sweep.expand(config, selection)


def identities(path: Path, **arguments) -> dict[str, str]:
    """point name → identity hash."""
    config, points = points_of(path, **arguments)
    return {point.name: hashing.identity_of(point, tool="pythia", card_bytes=CARD,
                                            card_text=CARD.decode()).hash
            for point in points}


# ── the hash covers the physics and nothing else ─────────────────────────────

def test_the_same_point_has_the_same_hash_in_every_study(eic):
    """00/B1: identity, not position. `18x275_ep_NNLO_pt32_mpi` appears in three studies."""
    seen: dict[str, set[str]] = {}
    for study in STUDIES:
        for name, digest in identities(eic, study=study).items():
            seen.setdefault(name, set()).add(digest)
    shared = [name for name in seen if sum(name in identities(eic, study=s) for s in STUDIES) > 1]
    assert shared, "the studies should overlap in at least one point"
    for name in shared:
        assert len(seen[name]) == 1, f"{name} hashed differently in different studies"
    assert "eic_18x275_ep_NNLO_pt32_mpi" in seen


def test_a_setting_equal_to_the_card_does_not_change_the_hash(eic):
    """00/B15: the base card already says pTHatMin = 6, so `pth6` is the base sample."""
    base = identities(eic, study="single")
    pthatmin = identities(eic, study="pthatmin")
    pth6 = next(digest for name, digest in pthatmin.items() if name.endswith("pth6"))
    assert pth6 in base.values(), "pth6 must hash like the point without the override"
    others = [digest for name, digest in pthatmin.items() if not name.endswith("pth6")]
    assert all(digest not in base.values() for digest in others)


def test_analysis_options_do_not_change_the_hash(eic):
    """The radius study varies only an analysis option, so all three points are one generation."""
    assert len(set(identities(eic, study="radius").values())) == 1


def test_generation_settings_do_change_the_hash(eic):
    assert len(set(identities(eic, study="pdf").values())) == 4
    assert len(set(identities(eic, study="energies").values())) == 4


def test_hash_is_independent_of_catalogue_order(eic, tmp_path):
    """Shuffling the quantity tables must not move a hash.

    The *name* does follow the catalogue, because it lists the tags in declaration order: identity is
    what the physics is, the name is how a person finds it.
    """
    import tomllib

    import tomli_w

    document = tomllib.loads(eic.read_text(encoding="utf-8"))
    names = list(document["quantity"])
    random.Random(4).shuffle(names)
    document["quantity"] = {name: document["quantity"][name] for name in names}
    shuffled = tmp_path / "shuffled.toml"
    shuffled.write_text(tomli_w.dumps(document), encoding="utf-8")
    shuffled_identities, original = identities(shuffled, study="pdf"), identities(eic, study="pdf")
    assert sorted(shuffled_identities.values()) == sorted(original.values())
    assert set(shuffled_identities) != set(original), "the names follow the catalogue order"


def test_equal_hashes_become_one_generation_with_aliases(eic):
    """00/B15 in the grouping: `pth6` and the base point are one generation under two names."""
    config, points = points_of(eic, across="pthatmin")
    base_config, base_points = points_of(eic, study="single")
    groups = hashing.group_by_identity(points + base_points, tool="pythia", card_bytes=CARD,
                                       card_text=CARD.decode())
    assert len(groups) == 4, "four distinct pTHatMin samples, not five"
    aliased = [identity for identity, _ in groups if len(identity.names) > 1]
    assert len(aliased) == 1
    assert sorted(aliased[0].names) == ["eic_27x920_ep_NNLO_pt32_mpi",
                                        "eic_27x920_ep_NNLO_pt32_mpi_pth6"]


def test_the_card_bytes_are_part_of_the_hash(eic):
    config, points = points_of(eic, study="single")
    first = hashing.identity_of(points[0], tool="pythia", card_bytes=CARD, card_text=CARD.decode())
    edited = CARD.replace(b"PhaseSpace:pTHatMin = 6.", b"PhaseSpace:pTHatMin = 4.")
    second = hashing.identity_of(points[0], tool="pythia", card_bytes=edited, card_text=edited.decode())
    assert first.hash != second.hash


def test_the_tool_and_its_version_are_part_of_the_hash(eic):
    config, points = points_of(eic, study="single")
    one = hashing.identity_of(points[0], tool="pythia", card_bytes=CARD, card_text=CARD.decode(),
                              tool_version="8.317")
    two = hashing.identity_of(points[0], tool="pythia", card_bytes=CARD, card_text=CARD.decode(),
                              tool_version="8.318")
    assert one.hash != two.hash


def test_numbers_hash_by_value_not_by_spelling():
    defaults = {"a:b": "6."}
    assert hashing.effective_settings([Assignment("A:b", 6.0, "x")], defaults) == {}
    assert hashing.effective_settings([Assignment("A:b", 6, "x")], defaults) == {}
    assert hashing.effective_settings([Assignment("A:b", 7, "x")], defaults) == {"a:b": 7}


def test_booleans_match_the_card_however_it_spells_them():
    for spelling in ("on", "true", "1", "  on "):
        assert hashing.effective_settings([Assignment("PartonLevel:MPI", True, "x")],
                                          {"partonlevel:mpi": spelling}) == {}
    assert hashing.effective_settings([Assignment("PartonLevel:MPI", False, "x")],
                                      {"partonlevel:mpi": "on"}) == {"partonlevel:mpi": False}


def test_a_missing_card_is_reported():
    with pytest.raises(HepError, match="base card not found"):
        hashing.read_card(Path("/nowhere/photo_ep.cmnd"))


# ── seeds ────────────────────────────────────────────────────────────────────

def test_instance_blocks_never_overlap_for_the_whole_catalogue(eic):
    """00/B2: every point of every study, at 20 threads, with no shared instance seed."""
    collected: dict[str, str] = {}
    for study in STUDIES:
        collected.update({digest: name for name, digest in identities(eic, study=study).items()})
    blocks = seeds.assign([(name, digest) for digest, name in collected.items()],
                          run_seed=270403, threads=20)
    assert len(blocks) == len(collected)
    used: dict[int, str] = {}
    for digest, seed_block in blocks.items():
        assert len(seed_block.instances) == 20
        for seed in seed_block.instances:
            assert seed not in used, f"{seed} shared by {used.get(seed)} and {digest}"
            used[seed] = digest
    assert min(used) >= seeds.MIN_SEED and max(used) <= seeds.MAX_SEED


def test_a_points_seed_does_not_depend_on_the_study(eic):
    """The same point run from two studies gets the same block."""
    energies = identities(eic, study="energies")
    single = identities(eic, study="single")
    shared_name = next(name for name in single if name in energies)
    one = seeds.block(270403, single[shared_name], 20)
    two = seeds.block(270403, energies[shared_name], 20)
    assert one == two


def test_the_seed_follows_the_run_seed(eic):
    digest = next(iter(identities(eic, study="single").values()))
    assert seeds.block(1, digest, 20) != seeds.block(2, digest, 20)


def test_blocks_are_aligned_and_wide_enough():
    assert seeds.stride_for(20) == 1024
    assert seeds.stride_for(1024) == 1024
    assert seeds.stride_for(1025) == 2048
    assert seeds.stride_for(0) == 1024
    block = seeds.block(270403, "a" * 64, 20)
    assert (block.point - seeds.MIN_SEED) % block.stride == 0
    assert block.instances == tuple(range(block.point, block.point + 20))


def test_raising_the_thread_count_keeps_the_first_seeds():
    """Up to the stride, more threads only extends the block."""
    digest = "b" * 64
    small = seeds.block(270403, digest, 4)
    large = seeds.block(270403, digest, 40)
    assert large.instances[:4] == small.instances
    assert large.point == small.point


def test_a_collision_is_resolved_deterministically(monkeypatch):
    """Two different hashes landing in one block: the smaller hash keeps it, and both are checked."""
    monkeypatch.setattr(seeds, "block_index", lambda run_seed, digest, stride: 7)
    blocks = seeds.assign([("one", "f" * 64), ("two", "a" * 64)], run_seed=1, threads=8)
    first, second = blocks["a" * 64], blocks["f" * 64]
    assert first.displaced == 0 and second.displaced == 1
    assert set(first.instances).isdisjoint(second.instances)
    again = seeds.assign([("two", "a" * 64), ("one", "f" * 64)], run_seed=1, threads=8)
    assert again == blocks, "the outcome must not depend on the order of the points"


def test_aliases_share_one_block(eic):
    config, points = points_of(eic, across="pthatmin")
    groups = hashing.group_by_identity(points, tool="pythia", card_bytes=CARD, card_text=CARD.decode())
    blocks = seeds.assign([(identity.names[0], identity.hash) for identity, _ in groups],
                          run_seed=270403, threads=20)
    assert len(blocks) == len(groups)


def test_disjointness_is_enforced():
    overlapping = {"a" * 64: seeds.SeedBlock(point=10, instances=(10, 11), stride=1024),
                   "b" * 64: seeds.SeedBlock(point=11, instances=(11, 12), stride=1024)}
    with pytest.raises(HepError, match="used by two generations"):
        seeds.check_disjoint(overlapping)


def test_seeds_stay_inside_pythias_range():
    with pytest.raises(HepError, match="leave the valid range"):
        seeds.check_disjoint({"a" * 64: seeds.SeedBlock(point=seeds.MAX_SEED,
                                                        instances=(seeds.MAX_SEED, seeds.MAX_SEED + 1),
                                                        stride=1024)})


def test_the_legacy_policy_reproduces_the_old_seeds():
    """`seed_policy = "legacy"` exists so golden comparisons can reproduce old results."""
    assert [seeds.legacy_block(270403, position, 20, 20).point for position in (1, 2, 3, 4)] == \
        [270403, 270423, 270443, 270463]
    assert seeds.legacy_block(270403, 1, 1, 20).instances[:3] == (270403, 270404, 270405)
    with pytest.raises(HepError, match="outside 1.."):
        seeds.legacy_block(900_000_000, 5, 20, 1)


def test_the_seed_policy_is_a_config_key(eic):
    config = load_config(eic, machine_file=None, project="PhotoProduction")
    assert config.run.seed_policy == "identity"
    assert config.run.legacy_seed_step == 20


# ── the skip rule ────────────────────────────────────────────────────────────

def test_skip_only_when_name_hash_and_output_all_match():
    identity = hashing.Identity(hash="a" * 64, names=["p"])
    assert hashing.skip_decision(identity, "p", None) == "run"
    assert hashing.skip_decision(identity, "p", hashing.Existing("p", "a" * 64, complete=True)) == "skip"
    assert hashing.skip_decision(identity, "p", hashing.Existing("p", "a" * 64, complete=False)) == "run"
    assert hashing.skip_decision(identity, "p", hashing.Existing("p", "b" * 64, complete=True)) == "conflict"


def test_a_conflict_explains_the_way_out():
    identity = hashing.Identity(hash="a" * 64, names=["p"])
    error = hashing.conflict_message("p", identity, hashing.Existing("p", "b" * 64, complete=True))
    assert "different physics" in error.message and "--rerun" in error.hint
