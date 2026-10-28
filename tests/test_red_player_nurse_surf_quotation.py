"""A water-separated Center must agree with the route's native Surf permission."""
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_field_goals as goals
from pokemon_red_completion.gen1_traversal import SURF_CAPABILITY
from pokemon_red_completion.observation import Badge, MapId, RawGameState
from pokemon_red_completion.route_plan import RoutePlanningError


@pytest.mark.parametrize("enabled,forced_bike,expected", [
    (True, False, int(MapId.ROCK_TUNNEL_POKECENTER)),
    (False, False, None),
    (True, True, None),
])
def test_water_separated_nursing_is_offered_only_with_executable_surf(
    monkeypatch, enabled, forced_bike, expected,
):
    raw = RawGameState(True, MapId.POWER_PLANT, 17, 20, 1, 0,
                       badge_bits=int(Badge.CASCADE | Badge.SOUL),
                       party_hp=(50,), party_moves=((15, 57, 0, 0),))
    runtime = N(reader=N(read=lambda: raw),
                emulator=N(read_u8=lambda _: (1 << 5) if forced_bike else 0))
    monkeypatch.setattr(goals, "_field_ready", lambda _: True)
    monkeypatch.setattr(goals, "Gen1TrainerSightProjector", lambda *a, **k: object())

    def observer(reader, *, capability_projector, hazard_projector):
        return N(observe=lambda: N(capabilities=capability_projector(reader.read())))

    monkeypatch.setattr(goals, "Gen1TraversalObserver", observer)

    def plan(start, center, *, goal_at):
        assert goal_at == (3, 3)
        if SURF_CAPABILITY not in start.capabilities:
            raise RoutePlanningError("the Center is across water")
        return N(cost=7 if center == int(MapId.ROCK_TUNNEL_POKECENTER) else 20)

    route = N(allow_surf=enabled, rom=b"fixture", route_world=N(plan_feasible_to_map=plan))
    selected = goals.nearest_reachable_player_center(runtime, route=route, centers=frozenset({
        int(MapId.ROCK_TUNNEL_POKECENTER), int(MapId.CERULEAN_POKECENTER),
    }))
    assert selected == expected
