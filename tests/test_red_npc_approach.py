from dataclasses import dataclass
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_npc_approach as npc


@pytest.mark.parametrize(
    "fault", [None, "blocked", "moving", "missing", "stale", "hazard", "offmap_hazard"]
)
def test_reachable_npc_side_and_fail_closed(monkeypatch, fault):
    target = NS(y=5, x=7, object_index=1, movement=0 if fault == "moving" else 255)
    monkeypatch.setattr(
        npc, "map_object_events", lambda *a: () if fault == "missing" else (target,)
    )
    calls = []
    state = NS(
        map_id=141 if fault == "offmap_hazard" else 235,
        player_y=12,
        player_x=7,
        battle_state=0,
        event_flags=bytes(256),
    )
    monkeypatch.setattr(npc, "trainer_headers", lambda *a, **kw: ())
    monkeypatch.setattr(npc, "trainer_sight_zones", lambda *a: ())
    monkeypatch.setattr(
        npc,
        "static_trainer_sight_zones",
        lambda *a: (NS(lane=((5, 8),)),) if fault == "offmap_hazard" else (),
    )

    class World:
        def with_current_blocks(self, blocks):
            return self

        def plan_to_map(self, *args, **kwargs):
            raise AssertionError("optimistic reachability must not choose an interaction side")

        def plan_feasible_to_map(self, start, goal, *, goal_at):
            if fault == "blocked" or goal_at != (5, 8):
                raise npc.RoutePlanningError("warp or wall")
            return NS(terminal_approach=NS(edges=(1, 2)), segments=())

    @dataclass
    class Route:
        route_world: object = None
        full_event_offsets: bool = False
        observe_terrain: bool = False
        destination_map: int = 0
        destination_at: tuple = ()
        maximum_readiness_waits: int = 16

        def __call__(self, *args):
            calls.append("route")
            if fault != "stale":
                state.player_y, state.player_x = self.destination_at

    monkeypatch.setattr(npc.RedVermilionGroundTransition, "from_rom", lambda _: Route(World()))
    monkeypatch.setattr(npc, "Gen1TrainerSightProjector", lambda *a, **kw: None)
    monkeypatch.setattr(
        npc,
        "Gen1TraversalObserver",
        lambda *a, **kw: NS(
            observe=lambda: NS(map_id=235, hazards=(NS(at=(5, 8)),) if fault == "hazard" else ())
        ),
    )
    monkeypatch.setattr(npc, "_face_trainer_boundary", lambda a, r, d: calls.append(d))
    reader = NS(
        read=lambda: state,
        read_current_map_blocks=lambda: None,
        read_current_map_objects=lambda: (),
    )
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            npc.approach_npc(NS(), reader, NS(), rom=b"rom", map_id=235, object_index=1)
        assert "left" not in calls
    else:
        result = npc.approach_npc(NS(), reader, NS(), rom=b"rom", map_id=235, object_index=1)
        assert result["at"] == (5, 8) and calls == ["route", "left"]
