"""A story item's real route must expose its already-approved water capability."""

from dataclasses import dataclass, fields
from types import SimpleNamespace as N

import pytest
from test_red_player_story_field_item import setup

from pokemon_red_completion import red_player_field_item as item
from pokemon_red_completion import red_training_ground_route as ground
from pokemon_red_completion.observation import Badge, ItemId, MapId
from pokemon_red_completion.route_plan import RoutePlanningError


def scoped_route(original, enabled):
    @dataclass
    class ScopedRoute(type(original)):
        allow_surf: bool = False

    return ScopedRoute(
        **{field.name: getattr(original, field.name) for field in fields(original)},
        allow_surf=enabled,
    )


@pytest.mark.parametrize("enabled,permission", [(False, True), (True, False), (True, True)])
def test_remote_item_approach_preserves_the_executors_water_scope(monkeypatch, enabled, permission):
    runtime, actions, route, raw, state, calls, _ = setup(monkeypatch)
    route = scoped_route(route, enabled)
    raw.map_id = int(MapId.LAVENDER_POKECENTER)
    offered = N(story_objective_ref="obtain_secret_key")

    def water_approach(*_args, **kwargs):
        assert kwargs["frontier"] and kwargs["stop_at_map_boundary"]
        return offered if kwargs.get("allow_surf", False) and permission else None

    monkeypatch.setattr(item, "story_travel_binding", water_approach)
    row = item.field_item_story_option(
        runtime, actions, route=route,
        objective_id="obtain_secret_key", item_id=int(ItemId.SECRET_KEY),
    )
    assert (row is not None) is (enabled and permission)
    assert not calls and actions.actions_executed == runtime.emulator.frame_count == 0
    assert state.payload == b"source" and not state.latched


@pytest.mark.parametrize("enabled,permission,alive,badge", [
    (False, True, True, True),
    (True, False, True, True),
    (True, True, False, True),
    (True, True, True, False),
    (True, True, True, True),
])
def test_local_item_water_path_needs_every_live_permission(
    monkeypatch, enabled, permission, alive, badge,
):
    runtime, actions, route, raw, state, calls, _ = setup(monkeypatch)
    route = scoped_route(route, enabled)
    raw.party_count = 1
    raw.party_hp = (100 if alive else 0,)
    raw.party_moves = ((57, 0, 0, 0),)
    raw.badge_bits = int(Badge.SOUL) if badge else 0
    monkeypatch.setattr(ground, "surf_permission", lambda *_a: N(allowed=permission))

    def observe(_reader, **kwargs):
        capabilities = kwargs["capability_projector"](raw)
        return N(observe=lambda: N(
            map_id=raw.map_id, at=(14, 5), capabilities=capabilities,
        ))

    def water_path(_world, start, _map_id, *, goal_at):
        if "move:surf" not in start.capabilities:
            raise RoutePlanningError("the item approach crosses water")
        return N(cost=1, terminal_at=goal_at)

    monkeypatch.setattr(item, "Gen1TraversalObserver", observe)
    monkeypatch.setattr(type(route.route_world), "plan_feasible_to_map", water_path)
    row = item.field_item_story_option(
        runtime, actions, route=route,
        objective_id="obtain_secret_key", item_id=int(ItemId.SECRET_KEY),
    )
    assert (row is not None) is (enabled and permission and alive and badge)
    assert not calls and actions.actions_executed == runtime.emulator.frame_count == 0
    assert state.payload == b"source" and not state.latched
