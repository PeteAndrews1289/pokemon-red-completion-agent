from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.red_story_sight_entry import planned_sight_approaches, sight_entry_edge
from pokemon_red_completion.route_executor import TraversalHazard, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


@pytest.mark.parametrize(
    "fault", [None, "unreachable", "blocked_source", "other_hazard", "overlap"]
)
def test_preview_plans_to_sight_but_cannot_bypass_live_visibility(fault):
    target = TrainerSightZone(14, 1, 202, 1, (3, 5), TrainerFacing.LEFT, 1, 12, False, False)
    zones = (target,)
    if fault == "overlap":
        from dataclasses import replace

        zones += (replace(target, sprite_index=2, event_flag=13),)
    contract = N(map_id=14, defeated_event=12, trainer_identity=(202, 2, 1))
    hazards = (TraversalHazard((3, 4), "trainer_sight"),)
    if fault == "other_hazard":
        hazards += (TraversalHazard((3, 4), "unrelated"),)
    start = TraversalSnapshot(
        14,
        (3, 2),
        True,
        mode="land",
        hazards=hazards,
        occupied=frozenset({(3, 3)}) if fault == "blocked_source" else frozenset(),
    )
    edge = LocalEdge((3, 4), "right")
    calls = []

    def plan(actual, destination, *, goal_at):
        assert actual is start and actual.hazards == hazards
        assert destination == 14 and goal_at == (3, 3)
        calls.append(goal_at)
        if fault == "unreachable":
            raise RoutePlanningError("no guarded route")
        return N(terminal_at=goal_at, cost=1)

    world = N(local_graphs={14: LocalGraph({(3, 3): (edge,)})}, plan_feasible_to_map=plan)
    result = planned_sight_approaches(world, start, zones, contract)
    assert bool(result) is (fault is None)
    if result:
        assert result[0][1] == edge and result[0][0].terminal_at == (3, 3)
    assert target.visible is False
    # Planning does not make an offscreen trainer executable.
    with pytest.raises(ValueError, match="live declared trainer"):
        sight_entry_edge(start, (edge,), zones, contract)
