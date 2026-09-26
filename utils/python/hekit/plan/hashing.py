"""What makes a point the same point: the identity hash (03 §5).

The hash covers everything that changes the **generated events** and nothing else, so that two points
which differ only in their name, in their analysis options, or in a setting that merely repeats what the
base card already says, are recognised as one generation (00/B15). The seed is *derived* from the hash,
so it is never an input to it.

Hash inputs, as canonical JSON with sorted keys:

| Key | Why |
|---|---|
| `card` | sha256 of the base card's bytes: editing the card changes the physics |
| `cards` | sha256 of each extra card fragment, in order |
| `settings` | the **effective** overrides only — a value equal to the base card's counts as unset |
| `tool`, `tool_version` | a different generator, or a different version, is different physics |
| `beams`, `energies`, `events` | run control that changes the sample |
| `replica` | which statistical replica this is, for seed studies |
| `input` | for a replay point: the store it replays |
| `version` | this recipe's version, so a future change to the inputs is visible |
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

from ..errors import HepError
from ..sweep.quantity import as_number, text_value

#: Bumped when the set of hash inputs changes, so old and new hashes never compare equal by accident.
RECIPE_VERSION = 1

#: `Key:name = value` in a Pythia command file, with `!` or `#` starting a comment.
PYTHIA_SETTING = re.compile(r"^\s*([A-Za-z0-9_:]+)\s*=\s*([^!#]*)")


def canonical_number(value: Any) -> Any:
    """6 and 6.0 are the same physics, so they must hash the same."""
    number = as_number(value)
    if number is None:
        return value
    return int(number) if float(number).is_integer() else float(number)


def normalise_key(key: str) -> str:
    """Native setting keys are case-insensitive and ignore spaces (Pythia's own rule)."""
    return "".join(str(key).split()).lower()


def card_defaults(tool: str, text: str) -> dict[str, str]:
    """The settings a native card already applies, as `normalised key → value text`.

    Only Pythia is parsed here, because it is the only tool the toolkit drives itself so far. Each
    adapter takes this over in P1-S05; an unknown tool returns nothing, which simply means no override
    is recognised as redundant and the hash is more conservative than it needs to be.
    """
    if tool != "pythia":
        return {}
    settings: dict[str, str] = {}
    for line in text.splitlines():
        match = PYTHIA_SETTING.match(line)
        if match is None:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value:
            settings[normalise_key(key)] = value        # later lines win, as Pythia reads them
    return settings


def same_value(given: Any, in_card: str) -> bool:
    """Whether an override merely repeats what the card says (numerically where possible)."""
    if in_card is None:
        return False
    text = text_value(given)
    if text == in_card.strip():
        return True
    left, right = as_number(given), as_number(in_card)
    if left is not None and right is not None:
        return left == right
    return text.lower() in {in_card.strip().lower(), _boolean_text(in_card)}


def _boolean_text(value: str) -> str:
    """Pythia writes booleans as on/off, true/false or 1/0; map them onto our on/off."""
    lowered = value.strip().lower()
    if lowered in {"on", "true", "yes", "1"}:
        return "on"
    if lowered in {"off", "false", "no", "0"}:
        return "off"
    return lowered


def effective_settings(settings: Any, defaults: dict[str, str]) -> dict[str, Any]:
    """The overrides that actually change something, keyed by normalised key (00/B15).

    `pth6` on a card that already says `PhaseSpace:pTHatMin = 6.` is not a different sample, and
    neither is `allproc` on a card with `Photon:ProcessType = 0`; both hash like the base.
    """
    effective: dict[str, Any] = {}
    for assignment in settings:
        key = normalise_key(assignment.key)
        if same_value(assignment.value, defaults.get(key)):
            continue
        effective[key] = canonical_number(assignment.value)
    return effective


@dataclass
class Identity:
    """The identity of one generation: its hash and the inputs that produced it."""

    hash: str
    inputs: dict[str, Any] = dataclass_field(default_factory=dict)
    #: Point names that share this identity (aliases; the first is the canonical one)
    names: list[str] = dataclass_field(default_factory=list)

    @property
    def short(self) -> str:
        return self.hash[:12]


def read_card(path: Path) -> bytes:
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        raise HepError(f"base card not found: {path}") from None
    except OSError as error:
        raise HepError(f"cannot read the base card {path}: {error.strerror}") from None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity_inputs(point: Any, *, tool: str, card_bytes: bytes | None, card_text: str = "",
                    extra_cards: tuple[bytes, ...] = (), tool_version: str = "",
                    store_hash: str = "") -> dict[str, Any]:
    """The hash inputs for one point (03 §5)."""
    defaults = card_defaults(tool, card_text)
    inputs: dict[str, Any] = {
        "version": RECIPE_VERSION,
        "tool": tool,
        "tool_version": tool_version,
        "card": sha256_bytes(card_bytes) if card_bytes is not None else "",
        "cards": [sha256_bytes(data) for data in extra_cards],
        "settings": effective_settings(point.settings, defaults),
        "beams": [canonical_number(item) for item in point.beams] if point.beams else None,
        "energies": ([canonical_number(item) for item in point.energies]
                     if isinstance(point.energies, list) else canonical_number(point.energies)),
        "events": point.events,
        "replica": canonical_number(point.seed) if point.seed is not None else 0,
    }
    if store_hash:
        # A replay is identified by the store it replays plus its analysis configuration (11 §4).
        # The *analyses* part is added after grouping, in `group_by_identity`, because an
        # analysis-option variant is not a separate generation (03 §4): R=0.4 and R=1.0 replay the
        # same events and belong in one run. Hashing them per point made two generations that shared
        # a directory, and the second overwrote the first.
        inputs["input"] = store_hash
    return inputs


def hash_inputs(inputs: dict[str, Any]) -> str:
    """sha256 of the canonical JSON: sorted keys, no insignificant whitespace, UTF-8."""
    text = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def identity_of(point: Any, **kwargs: Any) -> Identity:
    inputs = identity_inputs(point, **kwargs)
    return Identity(hash=hash_inputs(inputs), inputs=inputs, names=[point.name])


def group_by_identity(points: list[Any], **kwargs: Any) -> list[tuple[Identity, list[Any]]]:
    """One entry per distinct generation; points with an equal hash become aliases of one (03 §5).

    The order is the order the points were expanded, so a plan reads in the order the user wrote it.
    """
    groups: dict[str, tuple[Identity, list[Any]]] = {}
    for point in points:
        identity = identity_of(point, **kwargs)
        if identity.hash in groups:
            existing, members = groups[identity.hash]
            if point.name not in existing.names:
                existing.names.append(point.name)
            members.append(point)
        else:
            groups[identity.hash] = (identity, [point])
    found = list(groups.values())
    return _with_group_analyses(found) if kwargs.get("store_hash") else found


def _with_group_analyses(groups: list[tuple[Identity, list[Any]]]) -> list[tuple[Identity, list[Any]]]:
    """Fold a replay group's whole analysis set into its hash (11 §4).

    A replay is "these events, analysed this way", so the analyses belong in the identity — but the
    *group's* analyses, not each point's. Two replays of one store with different analyses are then
    different points, while two option variants of one analysis stay one generation (03 §4).
    """
    rebuilt: list[tuple[Identity, list[Any]]] = []
    for identity, members in groups:
        analyses = sorted({entry for point in members for entry in point.analyses})
        inputs = dict(identity.inputs)
        inputs["analyses"] = analyses
        rebuilt.append((Identity(hash=hash_inputs(inputs), inputs=inputs, names=identity.names),
                        members))
    return rebuilt


# ── the skip rule (03 §5; used by hekit.results in P3-S03) ───────────────────

@dataclass(frozen=True)
class Existing:
    """What is already on disk for a point name, as far as the skip rule cares."""

    name: str
    hash: str = ""
    complete: bool = False


def skip_decision(identity: Identity, name: str, existing: Existing | None) -> str:
    """"run", "skip" or "conflict" for one point (03 §5).

    A point is skipped only when the name, the hash **and** a complete output all match; a partial
    output is never complete (00/B3). The same name with a different hash is a conflict, not a silent
    overwrite: the user either meant to rerun it or wants a different run name.
    """
    if existing is None:
        return "run"
    if existing.hash and existing.hash != identity.hash:
        return "conflict"
    if not existing.complete:
        return "run"
    return "skip"


def conflict_message(name: str, identity: Identity, existing: Existing) -> HepError:
    return HepError(
        f"'{name}' exists with different physics (stored {existing.hash[:12]}, "
        f"this plan {identity.short})",
        hint="use --rerun to replace it, or change [run].name")
