"""Portable prospective challenge for the next executable option, not a label.

These are declared previews, distinct from observed battle history. A preview
never claims a win probability, matchup quality or whole-chapter completion.
Missing knowledge differs from a verified noncombat option. Identities stay in
the adapter's private evidence, not in this feature contract.
"""

from dataclasses import asdict, dataclass
from math import isfinite
from statistics import median

CHALLENGE_SCHEMA = "pokemon.core.option-challenge.v1"
CHALLENGE_NAMES = (
    "present",
    "combat_required",
    "opposition_known",
    "opponent_fraction",
    "maximum_level_deficit",
    "median_level_deficit",
)


@dataclass(frozen=True)
class OptionChallenge:
    combat_required: bool
    opposition_known: bool
    opponent_fraction: float
    maximum_level_deficit: float
    median_level_deficit: float

    def __post_init__(self):
        if type(self.combat_required) is not bool or type(self.opposition_known) is not bool:
            raise ValueError("challenge presence flags must be explicit booleans")
        values = (self.opponent_fraction, self.maximum_level_deficit, self.median_level_deficit)
        if any(type(v) not in (int, float) or not isfinite(v) for v in values):
            raise ValueError("challenge measurements must be finite")
        if not 0 <= self.opponent_fraction <= 1 or any(not -1 <= v <= 1 for v in values[1:]):
            raise ValueError("challenge measurements outside bounds")
        if (not self.combat_required or not self.opposition_known) and any(values):
            raise ValueError("absent opposition cannot invent measurements")
        if self.opposition_known and (not self.combat_required or self.opponent_fraction == 0):
            raise ValueError("known opposition requires a nonempty combat preview")

    @classmethod
    def from_levels(cls, *, combat_levels, opponent_levels):
        for levels in (combat_levels, opponent_levels):
            if (
                not isinstance(levels, tuple)
                or not 1 <= len(levels) <= 6
                or any(type(n) is not int or not 1 <= n <= 100 for n in levels)
            ):
                raise ValueError("challenge preview requires bounded immutable levels")
        own = median(combat_levels)
        return cls(
            True,
            True,
            len(opponent_levels) / 6,
            (max(opponent_levels) - own) / 100,
            (median(opponent_levels) - own) / 100,
        )

    def public_dict(self):
        return dict(schema=CHALLENGE_SCHEMA, **asdict(self))

    @classmethod
    def from_public(cls, document):
        fields = set(CHALLENGE_NAMES[1:])
        if (
            not isinstance(document, dict)
            or set(document) != fields | {"schema"}
            or document["schema"] != CHALLENGE_SCHEMA
        ):
            raise ValueError("challenge document contract differs")
        return cls(**{k: document[k] for k in fields})


def challenge_feature_names(kinds):
    return tuple(f"challenge.{kind.value}_x_{name}" for kind in kinds for name in CHALLENGE_NAMES)


def challenge_vector(challenge, kind, kinds):
    values = (
        (0.0,) * len(CHALLENGE_NAMES)
        if challenge is None
        else (
            1.0,
            float(challenge.combat_required),
            float(challenge.opposition_known),
            challenge.opponent_fraction,
            challenge.maximum_level_deficit,
            challenge.median_level_deficit,
        )
    )
    return tuple(v if k is kind else 0.0 for k in kinds for v in values)
