"""Certified generic execution scope, without objective or location identities."""
from dataclasses import dataclass

STORY_UNIT_SCHEMA = "pokemon.player.option-story-unit.v1"
STORY_UNIT_FEATURE_NAMES = (
    "story_unit.present", "story_unit.movement", "story_unit.interaction",
    "story_unit.requires_further_selected_unit",
)

@dataclass(frozen=True, slots=True)
class OptionStoryUnit:
    """What the selected executor does on success; never a success prediction."""
    mode: str
    requires_further_selected_unit: bool

    def __post_init__(self):
        if type(self.mode) is not str or self.mode not in {"movement", "interaction"}:
            raise ValueError("story unit requires a generic certified execution mode")
        if type(self.requires_further_selected_unit) is not bool:
            raise ValueError("story unit completion scope must be boolean")

    def public_dict(self):
        return dict(schema=STORY_UNIT_SCHEMA, mode=self.mode,
                    requires_further_selected_unit=self.requires_further_selected_unit)

    @classmethod
    def from_public(cls, document):
        if (type(document) is not dict
                or set(document) != {"schema", "mode", "requires_further_selected_unit"}
                or document["schema"] != STORY_UNIT_SCHEMA):
            raise ValueError("story unit public contract differs")
        return cls(document["mode"], document["requires_further_selected_unit"])


def story_unit_vector(unit):
    if unit is None:
        return (0., 0., 0., 0.)
    if type(unit) is not OptionStoryUnit:
        raise TypeError("typed story unit required")
    unit.__post_init__()
    return (1., float(unit.mode == "movement"), float(unit.mode == "interaction"),
            float(unit.requires_further_selected_unit))


def story_unit_from_vector(values):
    values = tuple(values)
    if len(values) != 4 or any(type(v) not in (int, float) or v not in (0., 1.) for v in values):
        raise ValueError("story unit vector differs")
    if values == (0., 0., 0., 0.):
        return None
    if (len(values) != 4 or any(type(v) not in (int, float) or v not in (0., 1.) for v in values)
            or values[0] != 1. or values[1] + values[2] != 1.):
        raise ValueError("story unit vector differs")
    return OptionStoryUnit("movement" if values[1] else "interaction", bool(values[3]))
