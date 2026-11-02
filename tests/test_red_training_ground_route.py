from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_training_ground_route as ground_route
from pokemon_red_completion.gen1_traversal import CUT_CAPABILITY, CUT_MOVE_ID
from pokemon_red_completion.global_router import MacroEdge, MacroGraph
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
        rules=SimpleNamespace(cut_block_swaps=(SimpleNamespace(before=7, after=9),)),  # type: ignore[arg-type]
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


def test_ground_transition_excludes_unhandled_maps_before_planning(monkeypatch):
    world = replace(
        _world(),
        macro_graph=MacroGraph(
            {
                1: (MacroEdge(2), MacroEdge(127)),
                127: (MacroEdge(2),),
                2: (),
            }
        ),
    )
    snapshot = TraversalSnapshot(map_id=1, at=(1, 1), ready=True)
    monkeypatch.setattr(
        ground_route,
        "Gen1TraversalObserver",
        lambda *args, **kwargs: SimpleNamespace(observe=lambda: snapshot),
    )
    monkeypatch.setattr(ground_route, "Gen1TrainerSightProjector", lambda *args: None)

    def plan(self, *args, **kwargs):
        assert 127 not in self.macro_graph.edges
        assert self.macro_graph.neighbors(1) == (MacroEdge(2),)
        raise RuntimeError("filtered before input")

    monkeypatch.setattr(StrategicScenarioRouteWorld, "plan_feasible_to_map", plan)
    with pytest.raises(RuntimeError, match="filtered before input"):
        ground_route.RedVermilionGroundTransition(
            b"rom", world, destination_map=2, excluded_maps=frozenset({127})
        )(SimpleNamespace(execute=lambda _: pytest.fail("unexpected input")), None, None)
    assert len(world.macro_graph.neighbors(1)) == 2


@pytest.mark.parametrize(
    "options",
    [
        {"full_event_offsets": 1},
        {"observe_terrain": "yes"},
        {"excluded_maps": {127}},
        {"excluded_maps": frozenset({-1})},
        {"destination_map": 127, "excluded_maps": frozenset({127})},
        {"maximum_readiness_waits": 0},
        {"maximum_readiness_waits": 101},
        {"maximum_readiness_waits": True},
        {"transition_settle_frames": 0},
        {"transition_settle_frames": 1201},
        {"transition_settle_frames": True},
        {"maximum_scripted_dialogues": True},
        {"maximum_scripted_dialogues": -1},
        {"maximum_scripted_dialogues": 5},
        {"allow_surf": 1},
        {"allow_wild_faints": 1},
        {"allow_field_faint_dialogue": 1},
        {"allow_field_faint_dialogue": True},
    ],
)
def test_ground_transition_rejects_invalid_observation_or_exclusion_settings(options):
    with pytest.raises((ValueError, TypeError)):
        ground_route.RedVermilionGroundTransition(b"rom", _world(), **options)


@pytest.mark.parametrize(
    "destination",
    [
        (int(MapId.VERMILION_CITY), ground_route.VERMILION_TRAINING_EXTERIOR),
        (int(MapId.CELADON_POKECENTER), (3, 3)),
        (int(MapId.SAFFRON_POKECENTER), (3, 3)),
    ],
)
@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("readiness_waits", [16, 100])
@pytest.mark.parametrize("scripted_dialogues", [0, 2])
@pytest.mark.parametrize("allow_surf", [False, True])
@pytest.mark.parametrize("settle_frames", [120, 264])
def test_ground_transition_plans_executes_and_proves_the_exact_terminal(
    monkeypatch: pytest.MonkeyPatch,
    destination,
    observed,
    readiness_waits,
    scripted_dialogues,
    allow_surf,
    settle_frames,
) -> None:
    world = _world()
    start = TraversalSnapshot(
        map_id=int(MapId.LAVENDER_POKECENTER),
        at=(3, 3),
        ready=True,
        capabilities=frozenset({CUT_CAPABILITY}),
    )
    terminal = TraversalSnapshot(
        map_id=destination[0],
        at=destination[1],
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
        lambda _rom, _reader, **options: hazard,
    )
    plan = object()
    plan_calls: list[tuple[object, int, tuple[int, int]]] = []

    def plan_to_map(_self, observed, goal_map, *, goal_at=None):
        plan_calls.append((observed, goal_map, goal_at))
        return plan

    def replanner(request):
        return request

    terrain_reads = []
    monkeypatch.setattr(
        StrategicScenarioRouteWorld,
        "with_current_blocks",
        lambda self, blocks: terrain_reads.append(blocks) or self,
    )
    monkeypatch.setattr(StrategicScenarioRouteWorld, "plan_feasible_to_map", plan_to_map)
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

    def scripted(*args, **kwargs):
        assert kwargs["maximum_trainer_battles"] == 0
        assert kwargs["maximum_scripted_dialogues"] == scripted_dialogues
        assert kwargs["max_scripted_dialogue_pulses"] == 32
        return interruption_handler

    monkeypatch.setattr(ground_route, "Gen1RouteInterruptionHandler", scripted)
    executions: list[dict[str, object]] = []

    def execute(plan_value, actions_value, observer_value, **kwargs) -> None:
        if observed:
            assert kwargs["replanner"]("request") == "request"
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
    reader = SimpleNamespace(read_current_map_blocks=lambda: "blocks")
    emulator = SimpleNamespace(read_u8=lambda _: 0)

    ground_route.RedVermilionGroundTransition(
        b"rom",
        world,
        destination_map=destination[0],
        destination_at=destination[1],
        full_event_offsets=observed,
        observe_terrain=observed,
        maximum_readiness_waits=readiness_waits,
        transition_settle_frames=settle_frames,
        maximum_scripted_dialogues=scripted_dialogues,
        allow_surf=allow_surf,
    )(
        actions,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
    )

    assert plan_calls == [(start, *destination)]
    assert executions[0]["limits"].max_readiness_waits == readiness_waits
    assert executions[0]["limits"].transition_settle_frames == settle_frames
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
    from pokemon_red_completion.gen1_traversal import SURF_CAPABILITY, SURF_MOVE_ID

    water_raw = replace(
        raw,
        party_count=1,
        badge_bits=int(Badge.CASCADE | Badge.SOUL),
        party_moves=((CUT_MOVE_ID, SURF_MOVE_ID, 0, 0),),
    )
    expected = {CUT_CAPABILITY, SURF_CAPABILITY} if allow_surf else {CUT_CAPABILITY}
    assert capabilities(water_raw) == frozenset(expected)
    assert SURF_CAPABILITY not in capabilities(replace(water_raw, party_hp=(0,)))
    assert SURF_CAPABILITY not in capabilities(replace(water_raw, badge_bits=int(Badge.CASCADE)))
    emulator.read_u8 = lambda _: 1 << 5
    assert SURF_CAPABILITY not in capabilities(water_raw)
    assert field_bindings["cut_block_swaps"] == {7: 9}
    assert executions[0]["plan"] is plan
    assert executions[0]["actions"] is field_actions
    assert executions[0]["observer"] is observer
    assert executions[0]["interruption_handler"] is interruption_handler
    assert terrain_reads == (["blocks", "blocks"] if observed else [])
    if not observed:
        assert executions[0]["replanner"] is replanner
    limits = executions[0]["limits"]
    assert limits.max_interruptions == 32 + scripted_dialogues
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
        "plan_feasible_to_map",
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
