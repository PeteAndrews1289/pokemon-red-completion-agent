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


@dataclass(frozen=True, slots=True)
class StoryRouteQuote:
    """Executor-planned remaining route to its own objective endpoint.

    A quoted plan, not an observed outcome or an objective/location identity.
    Only the story-branch head reads it; legacy V16 vectors never include it.
    """
    remaining_cost: float
    remaining_boundaries: int

    def __post_init__(self):
        if (type(self.remaining_cost) not in (int, float) or self.remaining_cost != self.remaining_cost
                or self.remaining_cost < 0 or self.remaining_cost == float("inf")
                or type(self.remaining_boundaries) is not int or self.remaining_boundaries < 0):
            raise ValueError("story route quote requires finite non-negative planned values")
        object.__setattr__(self, "remaining_cost", float(self.remaining_cost))


def planned_route_quote(start_map, plan):
    """Count planned map changes on an existing route plan; never re-plan.

    A plan without an explicit step list or numeric cost yields no quote
    (unknown remaining route), never an invented value.
    """
    steps, cost = getattr(plan, "steps", None), getattr(plan, "cost", None)
    if steps is None or type(cost) not in (int, float):
        return None
    maps = [start_map, *(step.expected_map for step in steps)]
    boundaries = sum(1 for a, b in zip(maps, maps[1:]) if a != b)
    return StoryRouteQuote(float(cost), boundaries)


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
