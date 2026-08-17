from __future__ import annotations

from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_training_ground_route as ground_route
from pokemon_red_completion.gen1_traversal import CUT_CAPABILITY, CUT_MOVE_ID
from pokemon_red_completion.observation import Badge, MapId, RawGameState
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)


def _world() -> StrategicScenarioRouteWorld:
    return StrategicScenarioRouteWorld(
        macro_graph=object(),  # type: ignore[arg-type]
        local_graphs={},
        rom=b"rom",
        terrain={},
        rules=SimpleNamespace(
            cut_block_swaps=(SimpleNamespace(before=7, after=9),)
        ),  # type: ignore[arg-type]
        tilesets={},
        water_tilesets=frozenset(),
        object_blockers={},
    )


def test_ground_transition_decodes_its_world_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    decoded: list[bytes] = []

    def decode(rom: bytes) -> StrategicScenarioRouteWorld:
        decoded.append(rom)
        return world

    monkeypatch.setattr(
        ground_route.StrategicScenarioRouteWorld,
        "from_rom",
        decode,
    )

    transition = ground_route.RedVermilionGroundTransition.from_rom(b"immutable-red")

    assert transition.rom == b"immutable-red"
    assert transition.route_world is world
    assert decoded == [b"immutable-red"]


def test_ground_transition_plans_executes_and_proves_the_exact_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    start = TraversalSnapshot(
        map_id=int(MapId.LAVENDER_POKECENTER),
        at=(3, 3),
        ready=True,
        capabilities=frozenset({CUT_CAPABILITY}),
    )
    terminal = TraversalSnapshot(
        map_id=int(MapId.VERMILION_CITY),
        at=ground_route.VERMILION_TRAINING_EXTERIOR,
        ready=True,
    )
    observations = iter((start, terminal))
    observer = SimpleNamespace(observe=lambda: next(observations))
    observer_bindings: dict[str, object] = {}

    def bind_observer(reader, *, hazard_projector, capability_projector):
        observer_bindings.update(
            reader=reader,
            hazard_projector=hazard_projector,
            capability_projector=capability_projector,
        )
        return observer

    monkeypatch.setattr(ground_route, "Gen1TraversalObserver", bind_observer)
    hazard = object()
    monkeypatch.setattr(
        ground_route,
        "Gen1TrainerSightProjector",
        lambda _rom, _reader: hazard,
    )
    plan = object()
    plan_calls: list[tuple[object, int, tuple[int, int]]] = []

    def plan_to_map(_self, observed, goal_map, *, goal_at=None):
        plan_calls.append((observed, goal_map, goal_at))
        return plan

    replanner = object()
    monkeypatch.setattr(StrategicScenarioRouteWorld, "plan_to_map", plan_to_map)
    monkeypatch.setattr(
        StrategicScenarioRouteWorld,
        "replanner",
        lambda _self: replanner,
    )
    field_bindings: dict[str, object] = {}
    field_actions = SimpleNamespace(execute=lambda _action: None)

    def bind_field(delegate, reader, emulator, *, cut_block_swaps):
        field_bindings.update(
            delegate=delegate,
            reader=reader,
            emulator=emulator,
            cut_block_swaps=cut_block_swaps,
        )
        return field_actions

    monkeypatch.setattr(ground_route, "Gen1FieldMovePort", bind_field)
    interruption_handler = object()
    monkeypatch.setattr(
        ground_route,
        "Gen1WildFleeHandler",
        lambda *_args, **_kwargs: interruption_handler,
    )
    executions: list[dict[str, object]] = []

    def execute(plan_value, actions_value, observer_value, **kwargs) -> None:
        executions.append(
            {
                "plan": plan_value,
                "actions": actions_value,
                "observer": observer_value,
                **kwargs,
            }
        )

    monkeypatch.setattr(ground_route, "execute_route", execute)
    actions = SimpleNamespace(execute=lambda _action: None)
    reader = object()
    emulator = object()

    ground_route.RedVermilionGroundTransition(b"rom", world)(
        actions,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
    )

    assert plan_calls == [
        (start, int(MapId.VERMILION_CITY), ground_route.VERMILION_TRAINING_EXTERIOR)
    ]
    assert observer_bindings["hazard_projector"] is hazard
    capabilities = observer_bindings["capability_projector"]
    raw = RawGameState(
        True,
        MapId.LAVENDER_POKECENTER,
        3,
        3,
        1,
        0,
        badge_bits=int(Badge.CASCADE),
        party_hp=(20,),
        party_moves=((CUT_MOVE_ID, 0, 0, 0),),
    )
    assert callable(capabilities)
    assert capabilities(raw) == frozenset({CUT_CAPABILITY})
    assert field_bindings["cut_block_swaps"] == {7: 9}
    assert executions[0]["plan"] is plan
    assert executions[0]["actions"] is field_actions
    assert executions[0]["observer"] is observer
    assert executions[0]["interruption_handler"] is interruption_handler
    assert executions[0]["replanner"] is replanner
    limits = executions[0]["limits"]
    assert limits.max_interruptions == 32
    assert limits.max_replans == 16


def test_ground_transition_rejects_an_unproved_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    observations = iter(
        (
            TraversalSnapshot(map_id=1, at=(1, 1), ready=True),
            TraversalSnapshot(map_id=1, at=(1, 2), ready=True),
        )
    )
    observer = SimpleNamespace(observe=lambda: next(observations))
    monkeypatch.setattr(
        ground_route,
        "Gen1TraversalObserver",
        lambda *_args, **_kwargs: observer,
    )
    monkeypatch.setattr(ground_route, "Gen1TrainerSightProjector", lambda *_args: object())
    monkeypatch.setattr(
        StrategicScenarioRouteWorld,
        "plan_to_map",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(StrategicScenarioRouteWorld, "replanner", lambda _self: object())
    field_actions = SimpleNamespace(execute=lambda _action: None)
    monkeypatch.setattr(ground_route, "Gen1FieldMovePort", lambda *_args, **_kwargs: field_actions)
    monkeypatch.setattr(ground_route, "Gen1WildFleeHandler", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(ground_route, "execute_route", lambda *_args, **_kwargs: None)

    with pytest.raises(RouteExecutionError, match="did not prove"):
        ground_route.RedVermilionGroundTransition(b"rom", world)(
            SimpleNamespace(execute=lambda _action: None),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )
