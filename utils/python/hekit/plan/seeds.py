"""Seeds derived from a point's identity, in blocks that never overlap (03 §5, D21).

The legacy scheme was `seed + (position − 1) · seed_step`, which had two consequences:

* the same physics point got a different seed in different studies, because the seed followed its
  position in the expansion (00/B1);
* Pythia hands parallel instance *i* the seed `seed + i` when `Parallelism:seeds` is unset, so two
  points whose base seeds were closer together than the thread count shared random-number streams —
  with 20 threads and `seed_step = 1`, neighbouring points shared 19 of their 20 streams (00/B2).

Here a point's base seed comes from its identity hash, so it is the same in every study and independent
of catalogue order, and each point owns a whole **block** of consecutive seeds, one per instance. The
block is written into the card as `Parallelism:seeds`, so Pythia uses exactly those.

The function:

    stride       = the smallest power of two that is ≥ max(threads, 1) and ≥ 1024
    blocks       = (900_000_000 − 1) // stride            # Pythia accepts 1 … 900_000_000
    index        = int.from_bytes(sha256(b"hekit-seed/v1|" + run_seed + "|" + hash)[:8]) % blocks
    base_seed    = 1 + index · stride
    instances    = [base_seed + i for i in range(threads)]

A block is therefore aligned and `stride` wide, so two points either share their whole block or no seed
at all. Sharing is possible — 9·10⁸ seeds cannot hold 2²⁵⁶ hashes — so `assign()` checks the plan and
moves the loser of a collision to the next free block, deterministically by hash order. That is the only
case in which a point's seed depends on the rest of the plan, and it is recorded in provenance. For a
16-point plan with the default stride the chance of that happening is about 1 in 7000.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ..errors import HepError

#: Pythia's `Random:seed` accepts 1 … 900000000 (0 means "use the time").
MAX_SEED = 900_000_000
MIN_SEED = 1
#: Smallest block, so that raising the thread count does not move a point's seeds.
MIN_STRIDE = 1024
#: Domain separator, so these seeds can never coincide with another hash use.
DOMAIN = b"hekit-seed/v1|"


@dataclass(frozen=True)
class SeedBlock:
    """The seeds of one generation: the point seed and one seed per instance."""

    point: int
    instances: tuple[int, ...]
    stride: int
    #: How many blocks the point was moved by a collision; 0 means its identity block.
    displaced: int = 0

    @property
    def end(self) -> int:
        return self.point + self.stride - 1


def stride_for(threads: int) -> int:
    """Block width: a power of two, at least 1024 and at least the thread count."""
    if threads < 0:
        raise HepError(f"thread count cannot be negative: {threads}")
    stride = MIN_STRIDE
    while stride < max(threads, 1):
        stride *= 2
    return stride


def block_count(stride: int) -> int:
    return (MAX_SEED - MIN_SEED) // stride


def block_index(run_seed: int, identity_hash: str, stride: int) -> int:
    """Where a point's block sits, from its identity alone."""
    digest = sha256(DOMAIN + str(run_seed).encode() + b"|" + identity_hash.encode()).digest()
    return int.from_bytes(digest[:8], "big") % block_count(stride)


def block(run_seed: int, identity_hash: str, threads: int, *, displaced: int = 0) -> SeedBlock:
    """The seed block of one point, before any plan-level collision check."""
    stride = stride_for(threads)
    index = (block_index(run_seed, identity_hash, stride) + displaced) % block_count(stride)
    base = MIN_SEED + index * stride
    return SeedBlock(point=base, instances=tuple(base + i for i in range(max(threads, 1))),
                     stride=stride, displaced=displaced)


def legacy_block(run_seed: int, position: int, step: int, threads: int) -> SeedBlock:
    """The pre-rework seeds, for golden comparisons only (`[run].seed_policy = "legacy"`).

    `seed + (position − 1) · step`, with the instance seeds Pythia would have chosen itself
    (`seed + i`). Reproduces 00/B1 and 00/B2 on purpose.
    """
    base = run_seed + (position - 1) * step
    if not MIN_SEED <= base <= MAX_SEED:
        raise HepError(f"legacy seed {base} is outside 1..{MAX_SEED}",
                       hint="lower [run].seed or [run].legacy_seed_step")
    return SeedBlock(point=base, instances=tuple(base + i for i in range(max(threads, 1))),
                     stride=max(step, 1))


def assign(identities: list[tuple[str, str]], *, run_seed: int, threads: int) -> dict[str, SeedBlock]:
    """Seed blocks for a whole plan, guaranteed disjoint.

    `identities` is `(name, hash)` per generation. Points that share a hash share one block, because
    they are one generation. A collision between *different* hashes is resolved by letting the smaller
    hash keep the block and probing upwards for the other, so the outcome does not depend on the order
    the points were expanded.
    """
    stride = stride_for(threads)
    if block_count(stride) < len({hash for _, hash in identities}):
        raise HepError("more generations than seed blocks", where="[run].threads",
                       hint=f"with {threads} threads there are {block_count(stride)} blocks")
    blocks: dict[str, SeedBlock] = {}
    taken: dict[int, str] = {}
    for name, identity_hash in sorted(identities, key=lambda item: item[1]):
        if identity_hash in blocks:
            continue
        displaced = 0
        while True:
            candidate = block(run_seed, identity_hash, threads, displaced=displaced)
            index = (candidate.point - MIN_SEED) // stride
            if index not in taken:
                taken[index] = identity_hash
                blocks[identity_hash] = candidate
                break
            displaced += 1
            if displaced > len(identities) + 1:      # pragma: no cover - needs a crafted collision
                raise HepError("cannot place a seed block without overlap",
                               hint="raise [run].seed or reduce the number of points")
    check_disjoint(blocks)
    return blocks


def check_disjoint(blocks: dict[str, SeedBlock]) -> None:
    """No two generations may share an instance seed (03 §5)."""
    seen: dict[int, str] = {}
    for identity_hash, seeds in blocks.items():
        for seed in seeds.instances:
            if seed in seen and seen[seed] != identity_hash:
                raise HepError(f"instance seed {seed} is used by two generations "
                               f"({seen[seed][:12]} and {identity_hash[:12]})",
                               hint="this is a bug in the seed allocation; please report the plan")
            seen[seed] = identity_hash
        if not all(MIN_SEED <= seed <= MAX_SEED for seed in seeds.instances):
            raise HepError(f"instance seeds leave the valid range 1..{MAX_SEED}",
                           hint="reduce [run].threads")
