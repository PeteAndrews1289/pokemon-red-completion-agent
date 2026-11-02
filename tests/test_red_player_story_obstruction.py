from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_story_obstruction as s
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.route_executor import TraversalHazard, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


@pytest.mark.parametrize("fault", [None, "other_hazard", "shared_sight", "already_open"])
def test_only_the_exact_trainer_sight_can_unlock_hypothetical_route(monkeypatch, fault):
    target = TrainerSightZone(51, 4, 202, 3, (18, 2), TrainerFacing.LEFT, 1, 1380, False, True)
    zones = (target,)
    hazards = (TraversalHazard((18, 1), "trainer_sight"),)
    if fault == "other_hazard":
        hazards += (TraversalHazard((18, 1), "unrelated"),)
    if fault == "shared_sight":
        zones += (replace(target, sprite_index=3, event_flag=1379),)
    if fault == "already_open":
        hazards = ()
    start = TraversalSnapshot(51, (19, 1), True, mode="land", hazards=hazards)
    candidate = N(trainer=target)
    calls = []

    def route(observation, destination):
        assert destination == 2
        calls.append(observation)
        if observation.hazards:
            raise RoutePlanningError("trainer blocks exit")
        return object()

    def inventory(rom, world, actual, observed_zones, **kwargs):
        assert actual is start and observed_zones == zones
        assert actual.hazards == hazards
        return (candidate,)

    monkeypatch.setattr(s, "local_trainer_funding_candidates", inventory)
    result = s.blocking_story_trainers(b"rom", N(plan_feasible_to_map=route), start, zones, 2)
    assert result == ((candidate,) if fault is None else ())
    assert start.hazards == hazards
    assert len(calls) == (1 if fault == "already_open" else 2)


@pytest.mark.parametrize("resolver_enabled", [False, True])
def test_obstruction_actor_uses_only_the_observed_exact_contract(monkeypatch, resolver_enabled):
    raw = N(map_id=157)
    runtime = N(reader=N(read=lambda: raw, read_current_map_objects=lambda: ()))
    start, contract, original, scoped, binding = (object() for _ in range(5))
    target = N(trainer=N(event_flag=321), approach=N(cost=1))
    observed = []
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **kw: N(observe=lambda: start))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **kw: None)
    monkeypatch.setattr(s, "trainer_headers", lambda *a, **kw: ())
    monkeypatch.setattr(s, "map_object_events", lambda *a: ())
    monkeypatch.setattr(s, "trainer_sight_zones", lambda *a: ())
    monkeypatch.setattr(s, "blocking_story_trainers", lambda *a, **kw: (target,))

    def quote(rom, actual, **kwargs):
        assert rom == b"rom" and actual is raw
        assert kwargs["map_id"] == 157 and kwargs["defeated_event"] == 321
        return contract

    def resolve(actual):
        assert actual is contract
        observed.append(actual)
        return scoped

    def bind(r, a, **kwargs):
        assert r is runtime and a is actions
        assert kwargs["contract"] is contract
        assert kwargs["battler"] is (scoped if resolver_enabled else original)
        assert kwargs["completes_objective"] is False
        return binding

    actions = N(actions_executed=0)
    monkeypatch.setattr(s.StoryTrainerContract, "from_cartridge", quote)
    monkeypatch.setattr(s, "story_battle_binding", bind)
    assert (
        s.obstructing_story_battle_binding(
            runtime,
            actions,
            objective_id="defeat_koga",
            route=N(rom=b"rom", route_world=object()),
            battler=original,
            trainer_battler_for_contract=resolve if resolver_enabled else None,
        )
        is binding
    )
    assert observed == ([contract] if resolver_enabled else [])
    assert actions.actions_executed == 0


@pytest.mark.parametrize("invalid", [1, "actor", object()])
def test_obstruction_resolver_rejects_untyped_dispatch_before_observation(invalid):
    with pytest.raises(TypeError, match="resolver must be callable"):
        s.obstructing_story_battle_binding(
            None,
            None,
            objective_id="defeat_koga",
            route=None,
            battler=None,
            trainer_battler_for_contract=invalid,
        )


@pytest.mark.parametrize("enabled,permission", [(False, True), (True, False), (True, True)])
def test_surf_story_obstruction_retains_only_actual_enabled_field_permission(
    monkeypatch, enabled, permission,
):
    raw, observed, permission_queries = N(map_id=22), [], []
    runtime = N(reader=N(read=lambda: raw), emulator=object())
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "cut_capabilities", lambda _: frozenset({"move:cut"}))

    def allowed(emulator, actual):
        assert emulator is runtime.emulator and actual is raw
        permission_queries.append(actual)
        return N(allowed=permission)

    monkeypatch.setattr(s, "surf_permission", allowed)
    monkeypatch.setattr(s, "surf_capabilities", lambda actual, *, surf_allowed:
                        frozenset({"move:surf"}) if surf_allowed else frozenset())
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **kw: object())

    def observer(reader, **kwargs):
        assert reader is runtime.reader
        start = N(map_id=22, capabilities=kwargs["capability_projector"](raw))
        return N(observe=lambda: start)

    def frontier(world, start, destination):
        assert destination == s.DESTINATIONS["reach_cinnabar"]
        observed.append(start.capabilities)
        raise RoutePlanningError("safe diagnostic end before any trainer binding")

    monkeypatch.setattr(s, "Gen1TraversalObserver", observer)
    monkeypatch.setattr(s, "story_frontier_target", frontier)
    actions = N(actions_executed=0)
    assert s.obstructing_story_battle_binding(
        runtime, actions, objective_id="reach_cinnabar",
        route=N(rom=b"rom", route_world=object(), allow_surf=True),
        battler=object(), frontier=True, allow_surf=enabled,
    ) is None
    expected = {"move:cut"} | ({"move:surf"} if enabled and permission else set())
    assert observed == [frozenset(expected)]
    assert len(permission_queries) == int(enabled)
    assert actions.actions_executed == 0


@pytest.mark.parametrize("invalid", [None, 0, 1, "yes"])
def test_obstruction_surf_requires_explicit_boolean(invalid):
    with pytest.raises(TypeError, match="Surf scope"):
        s.obstructing_story_battle_binding(
            None, None, objective_id="reach_cinnabar", route=None,
            battler=None, allow_surf=invalid,
        )


def test_obstruction_surf_cannot_outgrow_executor_permission():
    with pytest.raises(ValueError, match="Surf-enabled"):
        s.obstructing_story_battle_binding(
            None, None, objective_id="reach_cinnabar", route=N(allow_surf=False),
            battler=None, allow_surf=True,
        )
