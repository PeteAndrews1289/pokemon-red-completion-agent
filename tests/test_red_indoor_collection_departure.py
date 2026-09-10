from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_gen1_fly import FlyWorld
from test_red_goal_skills import _adapter, _raw, _Reader

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroPath, MacroTransition
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.local_router import LocalGraph, LocalPath
from pokemon_red_completion.red_goal_context_profile import (
    bind_capture_fly_profile,
    bind_evolution_fly_profile,
    build_native_boxed_evolution_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_indoor_collection_departure import (
    bind_indoor_collection_departure,
)
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter
from pokemon_red_completion.red_routed_semantic_goal import FreshRedGoalObservation
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError, RouteSegment
from pokemon_red_completion.routed_semantic_goal import RoutedSemanticGoalError


def cartridge():
    rom = bytearray(0x8000)
    for index, map_id in enumerate((*range(11), 15, 21)):
        pointer = 0x7000 + index * 8
        rom[0x6448 + index * 4 : 0x644C + index * 4] = bytes(
            (map_id, 0, pointer & 255, pointer >> 8)
        )
        y, x = 6 + index, 9 + index
        if map_id == 5:
            y, x = 6, 9
        rom[pointer : pointer + 6] = bytes((0x40, 0xC7, y, x, y & 1, x & 1))
    return bytes(rom)


class IndoorScene(FlyWorld):
    frame_count = 0
    indoor_walk_calls = 0
    walk_calls = 0
    destination_map = 89
    destination_at = (3, 3)
    exit_map = 0
    exit_at = (6, 9)
    last_outside_map = 0

    def execute(self, action):
        self.frame_count += action.repeat
        if self.stage == "indoor":
            if action.kind is MacroActionKind.MOVE:
                self.indoor_walk_calls += 1
                if self.fault == "wrong_exit":
                    self.raw = replace(self.raw, map_id=self.exit_map, player_y=10, player_x=10)
                else:
                    self.stage = "field"
                    self.raw = replace(
                        self.raw,
                        map_id=self.exit_map,
                        player_y=self.exit_at[0],
                        player_x=self.exit_at[1],
                    )
                    if self.fault == "unavailable_after_exit":
                        self.available = ()
                return
            super().execute(action)
            return
        if self.stage == "landed" and action.kind is MacroActionKind.MOVE:
            self.walk_calls += 1
            y, x = self.destination_at
            self.raw = replace(self.raw, map_id=self.destination_map, player_x=x, player_y=y)
            return
        super().execute(action)


@pytest.fixture
def indoor_scene():
    from test_red_goal_context_profile import _supply_transition_profile

    game = IndoorScene(available=(5,), selected=5)
    game.stage = "indoor"
    game.raw = replace(game.raw, map_id=89, player_x=3, player_y=6)
    game.last_outside_map = 0

    counted = CountingExecutor(game)
    template = _adapter(_Reader(raw=_raw(), ready=True)).observe()
    adapter = SimpleNamespace(observe=lambda: replace(template, raw=game.raw, input_ready=True))

    observer = SimpleNamespace(
        observe=lambda: TraversalSnapshot(
            game.raw.map_id,
            (game.raw.player_y, game.raw.player_x),
            True,
            mode="land",
            last_outside_map=game.last_outside_map,
        )
    )

    profile = bind_evolution_fly_profile(
        parse_red_goal_context_profile(
            build_native_boxed_evolution_profile_payload(
                _supply_transition_profile(),
                source_species=96,
                target_species=97,
                evolution_level=26,
            )
        )
    )
    spec = next(s for s in profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)

    exit_segment = RouteSegment(
        89,
        0,
        LocalPath(((6, 3),), (), ("land",)),
        MacroTransition((6, 3), (6, 9), "down"),
        "warp",
        False,
    )
    exit_plan = RoutePlan(
        MacroPath((89, 0), (MacroEdge(0),)),
        (6, 3),
        "land",
        (exit_segment,),
        None,
        (6, 9),
        "land",
    )

    onward_edge = MacroEdge(89)
    onward_plan = RoutePlan(
        MacroPath((5, 89), (onward_edge,)),
        (6, 9),
        "land",
        (
            RouteSegment(
                5,
                89,
                LocalPath(((6, 9),), (), ("land",)),
                MacroTransition((6, 9), (3, 3), "down"),
                "connection",
                False,
            ),
        ),
        None,
        (3, 3),
        "land",
    )

    provider_calls = []
    skill_passed = [True]

    def offer(observation):
        provider_calls.append(
            (observation.raw.map_id, observation.raw.player_y, observation.raw.player_x)
        )

        def execute():
            counted.execute(MacroAction(MacroActionKind.WAIT))
            return GoalExecutionReport(1, 1, {})

        binding = ExecutableGoalBinding(
            "synthetic-evolution",
            provider.kind,
            0.1,
            0.1,
            execute,
            lambda _: (
                GoalVerification.succeeded()
                if skill_passed[0]
                else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            ),
        )
        return RedGoalBindingOffer.available(binding)

    provider = SimpleNamespace(
        kind=GoalKind.EVOLVE_SPECIES, actions=counted, emulator=game, offer=offer
    )

    def plan_feasible_to_map(start, map_id, *, goal_at=None):
        if start.map_id == 89 and map_id == 0:
            return exit_plan
        if start.map_id == 5 and map_id == 89:
            return onward_plan
        raise RoutePlanningError(f"no plan from {start.map_id} to {map_id}")

    world = SimpleNamespace(
        rom=cartridge(),
        local_graphs={89: LocalGraph({(6, 3): ()}), 5: LocalGraph({(6, 9): ()})},
        object_blockers={89: frozenset(), 5: frozenset()},
        macro_graph=MacroGraph({89: (MacroEdge(0),), 5: (onward_edge,)}),
        plan_feasible_to_map=plan_feasible_to_map,
        replanner=lambda: lambda req: exit_plan if req.start.map_id == 89 else onward_plan,
    )

    runtime = SimpleNamespace(reader=game, emulator=game, adapter=adapter, profile=profile)
    router = RedResourceGoalRouter(
        runtime=runtime,
        actions=counted,
        world=world,
        maximum_controller_actions=6000,
        maximum_emulator_frames=600000,
        routed_recovery=False,
    )

    def bind():
        fresh = FreshRedGoalObservation("0" * 64, adapter.observe(), observer.observe())
        return bind_indoor_collection_departure(router, spec, provider, fresh, observer)

    return SimpleNamespace(
        game=game,
        router=router,
        spec=spec,
        provider=provider,
        observer=observer,
        adapter=adapter,
        bind=bind,
        provider_calls=provider_calls,
        skill_passed=skill_passed,
        exit_plan=exit_plan,
        onward_plan=onward_plan,
    )


def test_indoor_departure_qualification_is_action_free_and_projection_never_executes(indoor_scene):
    binding = indoor_scene.bind()
    assert binding is not None
    assert binding.kind is GoalKind.EVOLVE_SPECIES
    assert indoor_scene.game.actions == []
    assert indoor_scene.game.indoor_walk_calls == 0
    assert indoor_scene.game.flight_confirms == 0
    assert indoor_scene.game.walk_calls == 0
    assert indoor_scene.provider_calls == []


def test_indoor_departure_then_fly_and_destination_share_actual_accounting(indoor_scene):
    binding = indoor_scene.bind()
    assert binding is not None
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert indoor_scene.game.indoor_walk_calls == 1
    assert indoor_scene.game.flight_confirms == 1
    assert indoor_scene.game.walk_calls == 1
    assert indoor_scene.provider_calls == [(89, 3, 3)]
    assert report.actions_executed == indoor_scene.router.actions.actions_executed
    assert report.frames_executed == indoor_scene.game.frame_count


def test_consumed_binding_rejects_second_execution(indoor_scene):
    binding = indoor_scene.bind()
    assert binding is not None
    binding.execute()
    with pytest.raises(RoutedSemanticGoalError):
        binding.execute()


@pytest.mark.parametrize("outside_map", [None, 0x0B, 0x25, 0x30, -1])
def test_qualification_rejects_invalid_last_outside_map(indoor_scene, outside_map):
    indoor_scene.game.last_outside_map = outside_map
    assert indoor_scene.bind() is None
    assert indoor_scene.game.actions == []


def test_qualification_rejects_when_already_outdoors(indoor_scene):
    indoor_scene.game.raw = replace(indoor_scene.game.raw, map_id=5, player_x=9, player_y=6)
    assert indoor_scene.bind() is None
    assert indoor_scene.game.actions == []


def test_qualification_rejects_when_no_exit_route(indoor_scene):
    def no_exit(start, map_id, *, goal_at=None):
        raise RoutePlanningError("no route out")

    indoor_scene.router.world.plan_feasible_to_map = no_exit
    assert indoor_scene.bind() is None
    assert indoor_scene.game.actions == []


def test_qualification_rejects_when_projected_flight_unavailable(indoor_scene):
    indoor_scene.game.available = ()
    assert indoor_scene.bind() is None
    assert indoor_scene.game.actions == []


def test_wrong_exit_prevents_flight(indoor_scene):
    binding = indoor_scene.bind()
    assert binding is not None
    indoor_scene.game.fault = "wrong_exit"
    with pytest.raises(RouteExecutionError, match="route drifted"):
        binding.execute()
    assert indoor_scene.game.flight_confirms == 0
    assert indoor_scene.game.walk_calls == 0
    assert indoor_scene.provider_calls == []


def test_flight_unavailable_at_destination_bind_fails_closed(indoor_scene):
    binding = indoor_scene.bind()
    assert binding is not None
    indoor_scene.game.fault = "unavailable_after_exit"
    report = binding.execute()
    assert binding.verify(report).status.value == "failed"
    assert indoor_scene.game.flight_confirms == 0
    assert indoor_scene.game.walk_calls == 0
    assert indoor_scene.provider_calls == []


@pytest.mark.parametrize("changed_source", [False, True])
def test_capture_source_identity_preserved_and_verified(indoor_scene, monkeypatch, changed_source):
    from test_red_living_dex_wild_corridor import _local_discovery_profile

    import pokemon_red_completion.red_collection_fly as flight

    original = flight.bind_collection_fly
    calls = []

    def bind(*args):
        calls.append(args[3].observation.raw.map_id)
        binding = original(*args)
        if changed_source and len(calls) == 2:
            return replace(binding, search_source_ref="pokemon.red:acquisition:changed")
        return binding

    monkeypatch.setattr(flight, "bind_collection_fly", bind)

    profile = bind_capture_fly_profile(_local_discovery_profile())
    spec = next(s for s in profile.providers if s.kind is GoalKind.ACQUIRE_SPECIES)
    target = spec.parameters["map_id"]
    goal_at = (spec.parameters["player_y"], spec.parameters["player_x"])

    indoor_scene.provider.kind = GoalKind.ACQUIRE_SPECIES
    indoor_scene.game.destination_map, indoor_scene.game.destination_at = target, goal_at

    onward_plan = replace(
        indoor_scene.onward_plan,
        macro_path=MacroPath((5, target), (MacroEdge(target),)),
        segments=(
            replace(
                indoor_scene.onward_plan.segments[0],
                target_map=target,
                transition=MacroTransition((6, 9), goal_at, "down"),
            ),
        ),
        terminal_at=goal_at,
    )
    indoor_scene.router.world.macro_graph = MacroGraph(
        {89: (MacroEdge(0),), 5: (MacroEdge(target),)}
    )

    def plan_to(start, map_id, *, goal_at=None):
        if start.map_id == 89 and map_id == 0:
            return indoor_scene.exit_plan
        if start.map_id == 5 and map_id == target:
            return onward_plan
        raise RoutePlanningError("no route")

    indoor_scene.router.world.plan_feasible_to_map = plan_to
    indoor_scene.router.world.replanner = lambda: (
        lambda req: indoor_scene.exit_plan if req.start.map_id == 89 else onward_plan
    )

    fresh = FreshRedGoalObservation(
        "0" * 64, indoor_scene.adapter.observe(), indoor_scene.observer.observe()
    )
    binding = bind_indoor_collection_departure(
        indoor_scene.router, spec, indoor_scene.provider, fresh, indoor_scene.observer
    )
    assert binding is not None
    assert binding.kind is GoalKind.ACQUIRE_SPECIES
    assert binding.search_source_ref == "pokemon.red:acquisition:" + str(
        spec.parameters["source_id"]
    )

    report = binding.execute()
    assert calls == [0, 0]  # projected first; actual only after the exit is verified
    if changed_source:
        assert binding.verify(report).status.value == "failed"
        assert indoor_scene.provider_calls == []
        assert indoor_scene.game.flight_confirms == 0
        return
    assert binding.verify(report).status.value == "succeeded"
    assert indoor_scene.provider_calls == [(target, *goal_at)]
    assert indoor_scene.game.indoor_walk_calls == 1
    assert indoor_scene.game.flight_confirms == 1
    assert indoor_scene.game.walk_calls == 1
    assert report.actions_executed == indoor_scene.router.actions.actions_executed


@pytest.mark.parametrize("changed", ["money", "party", "position"])
def test_changed_actual_origin_fails_before_departure_input(indoor_scene, changed):
    binding = indoor_scene.bind()
    fields = {"money": {"player_money": 1}, "party": {"party_hp": (1, 2, 3)},
              "position": {"player_x": 4}}[changed]
    indoor_scene.game.raw = replace(indoor_scene.game.raw, **fields)
    with pytest.raises(RoutedSemanticGoalError, match="origin changed"):
        binding.execute()
    assert indoor_scene.router.actions.actions_executed == 0
    assert indoor_scene.game.flight_confirms == 0


@pytest.mark.parametrize("maximum", [1, 2])
def test_exhausted_departure_budget_does_not_start_flight(indoor_scene, maximum):
    indoor_scene.router.maximum_controller_actions = maximum
    binding = indoor_scene.bind()
    assert binding is not None
    report = binding.execute()
    assert binding.verify(report).status.value == "failed"
    assert indoor_scene.router.actions.actions_executed == 2
    assert indoor_scene.game.flight_confirms == 0
    assert indoor_scene.provider_calls == []
    assert indoor_scene.game.walk_calls == 0
    assert report.actions_executed == indoor_scene.router.actions.actions_executed


def test_flight_receives_only_the_remaining_action_budget(indoor_scene):
    indoor_scene.router.maximum_controller_actions = 3
    binding = indoor_scene.bind()
    with pytest.raises(RuntimeError, match="budget"):
        binding.execute()
    assert indoor_scene.router.actions.actions_executed == 3
    assert indoor_scene.game.flight_confirms == 0
    assert indoor_scene.provider_calls == []


def test_different_indoor_and_outdoor_maps(indoor_scene):
    # Changed synthetic indoor map and exit; flight still goes elsewhere.
    indoor_scene.game.raw = replace(indoor_scene.game.raw, map_id=90, player_x=3, player_y=6)
    indoor_scene.game.exit_map = 1
    indoor_scene.game.exit_at = (7, 10)
    indoor_scene.game.last_outside_map = 1
    indoor_scene.game.available = (5,)
    indoor_scene.game.selected = 5

    exit_plan = RoutePlan(
        MacroPath((90, 1), (MacroEdge(1),)),
        (6, 3),
        "land",
        (
            RouteSegment(
                90,
                1,
                LocalPath(((6, 3),), (), ("land",)),
                MacroTransition((6, 3), (7, 10), "down"),
                "warp",
                False,
            ),
        ),
        None,
        (7, 10),
        "land",
    )

    onward_plan = RoutePlan(
        MacroPath((5, 89), (MacroEdge(89),)),
        (6, 9),
        "land",
        (
            RouteSegment(
                5,
                89,
                LocalPath(((6, 9),), (), ("land",)),
                MacroTransition((6, 9), (3, 3), "down"),
                "connection",
                False,
            ),
        ),
        None,
        (3, 3),
        "land",
    )

    def plan_feasible(start, map_id, *, goal_at=None):
        if start.map_id == 90 and map_id == 1:
            return exit_plan
        if start.map_id == 5 and map_id == 89:
            return onward_plan
        raise RoutePlanningError("no route")

    indoor_scene.router.world.local_graphs = {
        90: LocalGraph({(6, 3): ()}),
        5: LocalGraph({(6, 9): ()}),
    }
    indoor_scene.router.world.object_blockers = {90: frozenset(), 5: frozenset()}
    indoor_scene.router.world.macro_graph = MacroGraph(
        {90: (MacroEdge(1),), 5: (MacroEdge(89),)}
    )
    indoor_scene.router.world.plan_feasible_to_map = plan_feasible
    indoor_scene.router.world.replanner = lambda: (
        lambda req: exit_plan if req.start.map_id == 90 else onward_plan
    )

    binding = indoor_scene.bind()
    assert binding is not None
    assert binding.kind is GoalKind.EVOLVE_SPECIES
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert indoor_scene.game.indoor_walk_calls == 1
    assert indoor_scene.game.flight_confirms == 1
