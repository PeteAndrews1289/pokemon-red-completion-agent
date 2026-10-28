"""Portable facts about one optional training intent, never a recommended choice."""

from dataclasses import asdict, dataclass
from math import isfinite

PREPARATION_SCHEMA = "pokemon.core.option-preparation.v1"
PREPARATION_NAMES = (
    "present",
    "current_level",
    "target_level",
    "level_gain",
    "remaining_xp",
    "hp_fraction",
    "pp_known",
    "pp_fraction",
    "existing_combat_intent",
    "undecided_intent",
    "evolution_known",
    "evolution_distance",
    "evolution_in_target",
)


@dataclass(frozen=True)
class OptionPreparation:
    current_level: int
    target_level: int
    remaining_xp: int
    hp_fraction: float
    pp_fraction: float | None
    existing_combat_intent: bool
    undecided_intent: bool
    evolution_level: int | None

    def __post_init__(self) -> None:
        if (
            type(self.current_level) is not int
            or type(self.target_level) is not int
            or not 1 <= self.current_level < self.target_level <= 100
        ):
            raise ValueError("preparation requires a genuine bounded level target")
        if type(self.remaining_xp) is not int or not 1 <= self.remaining_xp <= 2_000_000:
            raise ValueError("preparation needs a measured positive XP requirement")
        for value in (self.hp_fraction, self.pp_fraction):
            if value is not None and (
                type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1
            ):
                raise ValueError("preparation resource fraction differs")
        if self.hp_fraction is None:
            raise ValueError("preparation HP must be observed")
        if (
            type(self.existing_combat_intent) is not bool
            or type(self.undecided_intent) is not bool
            or self.existing_combat_intent == self.undecided_intent
        ):
            raise ValueError("preparation intent must be combat or explicitly undecided")
        if self.evolution_level is not None and (
            type(self.evolution_level) is not int or not 1 <= self.evolution_level <= 100
        ):
            raise ValueError("preparation evolution level differs")

    def vector(self) -> tuple[float, ...]:
        evolution = self.evolution_level
        return (
            1.0,
            self.current_level / 100,
            self.target_level / 100,
            (self.target_level - self.current_level) / 100,
            self.remaining_xp / (self.remaining_xp + 1000),
            self.hp_fraction,
            float(self.pp_fraction is not None),
            self.pp_fraction or 0.0,
            float(self.existing_combat_intent),
            float(self.undecided_intent),
            float(evolution is not None),
            max(0, evolution - self.current_level) / 100 if evolution is not None else 0.0,
            float(evolution is not None and evolution <= self.target_level),
        )

    def public_dict(self):
        return dict(schema=PREPARATION_SCHEMA, **asdict(self))

    @classmethod
    def from_public(cls, document):
        names = set(cls.__dataclass_fields__)
        if (
            not isinstance(document, dict)
            or set(document) != names | {"schema"}
            or document["schema"] != PREPARATION_SCHEMA
        ):
            raise ValueError("preparation document contract differs")
        return cls(**{name: document[name] for name in names})


def preparation_feature_names() -> tuple[str, ...]:
    return tuple("preparation." + name for name in PREPARATION_NAMES)


def preparation_vector(preparation: OptionPreparation | None) -> tuple[float, ...]:
    return (0.0,) * len(PREPARATION_NAMES) if preparation is None else preparation.vector()
