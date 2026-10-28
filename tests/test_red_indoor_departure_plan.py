from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.red_indoor_departure_plan import bounded_indoor_departure


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        "water",
        "interrupted",
        "outside",
        "third_map",
        "field_move",
        "ledge",
        "too_long",
        "empty",
        "terminal",
    ],
)
def test_indoor_departure_requires_one_bounded_direct_walking_exit(invalid):
    start = NS(ready=True, interruption=None, mode="land", map_id=89, last_outside_map=5)
    step = NS(
        source_map=89,
        expected_map=5,
        kind="warp",
        action_kind=MacroActionKind.MOVE,
        action="down",
        source_mode="land",
        expected_mode="land",
    )
    plan = NS(steps=(step,), terminal_map=5, terminal_mode="land")
    if invalid == "water":
        start.mode = "water"
    elif invalid == "interrupted":
        start.interruption = "wild_battle"
    elif invalid == "outside":
        start.last_outside_map = 89
    elif invalid == "third_map":
        step.expected_map = 90
    elif invalid == "field_move":
        step.action_kind = MacroActionKind.FIELD_MOVE
    elif invalid == "ledge":
        step.kind = "ledge"
    elif invalid == "too_long":
        plan.steps = (step,) * 129
    elif invalid == "empty":
        plan.steps = ()
    elif invalid == "terminal":
        plan.terminal_map = 6
    world = NS(plan_feasible_to_map=lambda *_: plan)
    result = bounded_indoor_departure(start, world)
    assert result is (plan if invalid is None else None)


@pytest.mark.parametrize("damage", [None, "gap", "outdoor_detour", "early_exit"])
def test_multifloor_departure_keeps_one_continuous_indoor_chain(damage):
    start = NS(ready=True, interruption=None, mode="land", map_id=212, last_outside_map=10)

    def step(source, destination):
        return NS(
            source_map=source,
            expected_map=destination,
            kind="warp",
            action_kind=MacroActionKind.MOVE,
            action="down",
            source_mode="land",
            expected_mode="land",
        )

    steps = [step(212, 211), step(211, 210), step(210, 10)]
    if damage == "gap":
        steps[1].source_map = 209
    elif damage == "outdoor_detour":
        steps[0].expected_map = 7
    elif damage == "early_exit":
        steps = [step(212, 10), step(10, 210), step(210, 10)]
    plan = NS(steps=tuple(steps), terminal_map=10, terminal_mode="land")
    assert bounded_indoor_departure(start, NS(plan_feasible_to_map=lambda *_: plan)) is (
        plan if damage is None else None
    )
