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
from pokemon_red_completion.local_router import LocalEdge, LocalGraph, LocalPath
from pokemon_red_completion.red_goal_context_profile import (
    bind_capture_fly_profile,
    bind_evolution_fly_profile,
    bind_indoor_fly_departure_profile,
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
    profile = bind_indoor_fly_departure_profile(profile)
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
    world.with_current_observation = lambda _reader: world

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


def test_walking_exit_quote_rejects_live_closed_passage_despite_static_route(indoor_scene):
    scene = indoor_scene
    static = scene.router.world
    observed = SimpleNamespace(**vars(static))

    def no_live_exit(*args, **kwargs):
        raise RoutePlanningError("observed indoor passage is closed")

    observed.plan_feasible_to_map = no_live_exit
    observed.with_current_observation = lambda reader: observed
    static.with_current_observation = lambda reader: observed

    assert scene.bind() is None
    assert scene.game.actions == []
    assert scene.game.indoor_walk_calls == scene.game.flight_confirms == 0
    assert scene.provider_calls == []


def test_walking_exit_quote_uses_live_open_passage_despite_stale_closed_map(indoor_scene):
    scene = indoor_scene
    static = scene.router.world
    observed = SimpleNamespace(**vars(static))
    observed.with_current_observation = lambda reader: observed

    def stale_closed_exit(*args, **kwargs):
        raise RoutePlanningError("stale indoor passage is closed")

    static.plan_feasible_to_map = stale_closed_exit
    static.with_current_observation = lambda reader: observed

    binding = scene.bind()
    assert binding is not None
    assert scene.game.actions == []
    assert binding.verify(binding.execute()) == GoalVerification.succeeded()
    assert scene.game.flight_confirms == 1
    assert len(scene.provider_calls) == 1


def _dig_scene(scene, monkeypatch, *, available=True, fault=None):
    from pokemon_red_completion import red_indoor_collection_departure as departure
    from pokemon_red_completion.red_dig_recovery import DigEscapePlan, RedDigRecoveryError

    scene.router.runtime.collection_dig_departure = True
    escape = DigEscapePlan(89, (6, 3), 0, (6, 9), 0, 22)
    quotes, executions = [], []

    def quote(world, reader, raw, start):
        quotes.append((raw.map_id, start.at))
        return escape if available else None

    def execute(world, reader, emulator, actions, plan):
        assert plan is escape
        executions.append(plan)
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=7))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=7))
        if fault == "primitive":
            raise RedDigRecoveryError("native escape resource check failed")
        scene.game.stage = "field"
        scene.game.raw = replace(
            scene.game.raw, map_id=0, player_y=6, player_x=10 if fault == "landing" else 9,
        )
        if fault == "unavailable":
            scene.game.available = ()
        return {"verified_escape": True, "anchor_map": 0, "landing": [6, 9]}

    scene.game.save_state_bytes = lambda: repr((scene.game.raw, scene.game.stage)).encode()
    monkeypatch.setattr(departure, "plan_dig_escape", quote)
    monkeypatch.setattr(departure, "execute_dig_escape", execute)
    return quotes, executions


def test_opted_in_dig_composes_only_the_selected_flight_and_fresh_destination(
    indoor_scene, monkeypatch,
):
    scene = indoor_scene
    quotes, executions = _dig_scene(scene, monkeypatch)
    original = scene.router.world.plan_feasible_to_map

    def no_indoor_walking(start, target, **kwargs):
        assert start.map_id != 89, "escape must not quote the blocked door route"
        return original(start, target, **kwargs)

    scene.router.world.plan_feasible_to_map = no_indoor_walking
    binding = scene.bind()
    assert quotes == [(89, (6, 3))] and not executions and not scene.game.actions
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert len(executions) == 1 and scene.game.indoor_walk_calls == 0
    assert scene.game.flight_confirms == 1 and scene.provider_calls == [(89, 3, 3)]
    assert report.actions_executed == scene.router.actions.actions_executed
    assert report.frames_executed == scene.game.frame_count
    with pytest.raises(RoutedSemanticGoalError, match="already executed"):
        binding.execute()


def test_unavailable_opted_in_escape_retains_ordinary_walking(indoor_scene, monkeypatch):
    quotes, executions = _dig_scene(indoor_scene, monkeypatch, available=False)
    binding = indoor_scene.bind()
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert quotes and not executions and indoor_scene.game.indoor_walk_calls == 1


def test_default_off_departure_does_not_even_quote_dig(indoor_scene, monkeypatch):
    from pokemon_red_completion import red_indoor_collection_departure as departure

    def unexpected(*args):
        raise AssertionError("Dig is not authorized by this runtime")

    monkeypatch.setattr(departure, "plan_dig_escape", unexpected)
    assert indoor_scene.bind() is not None
    assert not indoor_scene.game.actions


@pytest.mark.parametrize("fault", ["landing", "unavailable", "primitive", "budget", "stale"])
def test_dig_departure_failure_never_executes_flight_or_replacement_goal(
    indoor_scene, monkeypatch, fault,
):
    from pokemon_red_completion.red_dig_recovery import RedDigRecoveryError

    quotes, executions = _dig_scene(indoor_scene, monkeypatch, fault=fault)
    if fault == "budget":
        indoor_scene.router.maximum_controller_actions = 1
    binding = indoor_scene.bind()
    if fault == "stale":
        indoor_scene.game.raw = replace(indoor_scene.game.raw, player_money=1)
        with pytest.raises(RoutedSemanticGoalError, match="origin changed"):
            binding.execute()
        assert not executions and not indoor_scene.game.actions
    elif fault == "primitive":
        with pytest.raises(RedDigRecoveryError, match="resource"):
            binding.execute()
        assert indoor_scene.router.actions.actions_executed == 2
    else:
        report = binding.execute()
        assert binding.verify(report).status.value == "failed"
        assert report.actions_executed == indoor_scene.router.actions.actions_executed == 2
        assert report.frames_executed == indoor_scene.game.frame_count == 14
    assert quotes and not indoor_scene.provider_calls
    assert indoor_scene.game.flight_confirms == indoor_scene.game.indoor_walk_calls == 0


def test_walking_departure_does_not_advertise_unsupported_surf_shortcut(indoor_scene):
    scene = indoor_scene
    original = scene.router.world.plan_feasible_to_map
    observed = scene.observer.observe
    scene.observer.observe = lambda: replace(
        observed(), capabilities=frozenset({"move:surf", "move:cut", "event:open"})
    )
    departures = []

    def walking_only(start, target, **kwargs):
        if start.map_id == 89:
            departures.append(start)
            assert start.capabilities == frozenset({"event:open"})
        return original(start, target, **kwargs)

    scene.router.world.plan_feasible_to_map = walking_only
    binding = scene.bind()
    assert binding is not None and len(departures) == 1
    assert "move:surf" in scene.observer.observe().capabilities
    assert not scene.game.actions
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"


def test_walking_departure_replans_with_the_same_executor_capabilities(indoor_scene, monkeypatch):
    import pokemon_red_completion.red_indoor_collection_departure as departure
    from pokemon_red_completion.route_executor import ReplanRequest

    original = departure.RedSemanticTransportRoute
    captured = []

    def transport(**kwargs):
        captured.append(kwargs["replanner"])
        return original(**kwargs)

    monkeypatch.setattr(departure, "RedSemanticTransportRoute", transport)
    received = []

    def replan(request):
        received.append(request)
        return indoor_scene.exit_plan

    indoor_scene.router.world.replanner = lambda: replan
    assert indoor_scene.bind() is not None
    current = replace(indoor_scene.observer.observe(),
                      capabilities=frozenset({"move:surf", "event:open"}))
    request = ReplanRequest(current, 0, (6, 9), {}, 1)
    assert captured[0](request) == indoor_scene.exit_plan
    assert received[0].current.capabilities == frozenset({"event:open"})
    assert request.current.capabilities == frozenset({"move:surf", "event:open"})
    assert not indoor_scene.game.actions


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("known", [False, True])
@pytest.mark.parametrize("in_safari", [False, True])
def test_ordinary_surf_departure_requires_opt_in_and_never_enables_paid_safari(
    indoor_scene, enabled, known, in_safari,
):
    scene = indoor_scene
    scene.router.runtime.collection_surf_departure = enabled
    scene.game.read_safari_session_state = lambda: SimpleNamespace(in_safari_zone=in_safari)
    original_observe, original_plan = scene.observer.observe, scene.router.world.plan_feasible_to_map
    scene.observer.observe = lambda: replace(original_observe(), capabilities=frozenset(
        {"move:cut", "event:open"} | ({"move:surf"} if known else set())))
    starts = []

    def require_live_surf(start, target, **kwargs):
        if start.map_id == 89:
            starts.append(start)
            assert "move:cut" not in start.capabilities
            if "move:surf" not in start.capabilities:
                raise RoutePlanningError("ordinary route requires real Surf")
        return original_plan(start, target, **kwargs)

    scene.router.world.plan_feasible_to_map = require_live_surf
    binding = scene.bind()
    expected = enabled and known and not in_safari
    assert (binding is not None) is expected
    assert bool(starts) and not scene.game.actions
    if binding is not None:
        report = binding.execute()
        assert binding.verify(report).status.value == "succeeded"


def test_surf_departure_replan_preserves_same_explicit_capabilities(indoor_scene, monkeypatch):
    import pokemon_red_completion.red_indoor_collection_departure as departure
    from pokemon_red_completion.route_executor import ReplanRequest

    scene = indoor_scene
    scene.router.runtime.collection_surf_departure = True
    scene.game.read_safari_session_state = lambda: SimpleNamespace(in_safari_zone=False)
    observed = scene.observer.observe
    scene.observer.observe = lambda: replace(observed(), capabilities=frozenset(
        {"move:surf", "move:cut", "event:open"}))
    original_transport, replanners, received = departure.RedSemanticTransportRoute, [], []

    def transport(**kwargs):
        replanners.append(kwargs["replanner"])
        return original_transport(**kwargs)

    def replan(request):
        received.append(request)
        return scene.exit_plan

    monkeypatch.setattr(departure, "RedSemanticTransportRoute", transport)
    scene.router.world.replanner = lambda: replan
    assert scene.bind() is not None
    request = ReplanRequest(scene.observer.observe(), 0, (6, 9), {}, 1)
    assert replanners[0](request) == scene.exit_plan
    assert received[0].current.capabilities == frozenset({"move:surf", "event:open"})
    assert "move:cut" in request.current.capabilities and not scene.game.actions


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("known", [False, True])
@pytest.mark.parametrize("in_safari", [False, True])
def test_retained_indoor_water_quotes_only_an_opted_in_ordinary_land_departure(
    indoor_scene, monkeypatch, enabled, known, in_safari,
):
    import pokemon_red_completion.red_collection_fly as fly
    from pokemon_red_completion.observation import OverworldMovementMode

    scene = indoor_scene
    scene.router.runtime.collection_surf_departure = enabled
    scene.game.read_safari_session_state = lambda: SimpleNamespace(in_safari_zone=in_safari)
    scene.game.read_overworld_movement_mode = lambda: OverworldMovementMode.SURFING
    original_observe = scene.observer.observe
    scene.observer.observe = lambda: replace(original_observe(), mode="water",
        capabilities=frozenset({"move:surf"} if known else ()))
    # Quote a genuine mode-continuous water-to-shore path, not the fixture's
    # default land-start route. Native execution remains separately guarded.
    water_exit = replace(scene.exit_plan, start_mode="water", segments=(
        replace(scene.exit_plan.segments[0],
            approach=LocalPath(((6, 3), (6, 4)), (LocalEdge((6, 4), "right"),),
                               ("water", "land")),
            transition=MacroTransition((6, 4), (6, 9), "down")),))
    original_plan = scene.router.world.plan_feasible_to_map
    scene.router.world.plan_feasible_to_map = lambda start, target, **kwargs: (
        water_exit if start.map_id == 89 and target == 0 else original_plan(start, target, **kwargs))
    original, previews = fly.bind_collection_fly, []

    def quote(*args, **kwargs):
        previews.append((args[3].traversal.mode, kwargs.get("land_departure_projection")))
        return original(*args, **kwargs)

    monkeypatch.setattr(fly, "bind_collection_fly", quote)
    binding = scene.bind()
    expected = enabled and known and not in_safari
    assert (binding is not None) is expected
    assert previews == ([("land", True)] if expected else [])
    assert not scene.game.actions and scene.game.frame_count == 0


def test_prospective_land_flight_cannot_be_executed_or_replace_actual_water_guard(indoor_scene):
    from pokemon_red_completion.gen1_field_moves import Gen1FieldMoveError
    from pokemon_red_completion.observation import OverworldMovementMode
    from pokemon_red_completion.red_collection_fly import bind_collection_fly

    scene = indoor_scene
    scene.router.runtime.collection_surf_departure = True
    scene.game.read_safari_session_state = lambda: SimpleNamespace(in_safari_zone=False)
    scene.game.read_overworld_movement_mode = lambda: OverworldMovementMode.SURFING
    projected = FreshRedGoalObservation("0" * 64,
        replace(scene.adapter.observe(), raw=replace(scene.game.raw,
            map_id=0, player_y=6, player_x=9)),
        replace(scene.observer.observe(), map_id=0, at=(6, 9), mode="land"))
    assert bind_collection_fly(scene.router, scene.spec, scene.provider,
        projected, scene.observer) is None
    preview = bind_collection_fly(scene.router, scene.spec, scene.provider,
        projected, scene.observer, land_departure_projection=True)
    assert preview is not None
    with pytest.raises(Gen1FieldMoveError, match="quotation-only"):
        preview.execute()
    assert not scene.game.actions and scene.game.frame_count == 0


def test_indoor_departure_binds_the_shared_scripted_dialogue_cap(
    indoor_scene, monkeypatch,
):
    import pokemon_red_completion.red_indoor_collection_departure as departure

    original = departure.guarded_collection_route_handler
    calls = []

    def guarded(*args, **kwargs):
        calls.append(kwargs["maximum_scripted_dialogues"])
        return original(*args, **kwargs)

    monkeypatch.setattr(departure, "guarded_collection_route_handler", guarded)

    assert indoor_scene.bind() is not None
    assert calls == [4]
    assert indoor_scene.router.actions.actions_executed == 0


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


@pytest.mark.parametrize("fault", [None, "wrong_exit", "unavailable_after_exit"])
def test_supply_exit_rebinds_actual_flight_and_preserves_failure(indoor_scene, fault):
    from test_red_resupply_fly import supply_spec
    scene = indoor_scene
    spec = supply_spec(scene)
    fresh = FreshRedGoalObservation("0" * 64, scene.adapter.observe(), scene.observer.observe())
    binding = bind_indoor_collection_departure(
        scene.router, spec, scene.provider, fresh, scene.observer
    )
    assert binding is not None and not scene.game.actions
    assert binding.kind is GoalKind.RESUPPLY
    scene.game.fault = fault
    if fault == "wrong_exit":
        with pytest.raises(RouteExecutionError):
            binding.execute()
        assert scene.game.flight_confirms == 0 and not scene.provider_calls
        return
    report = binding.execute()
    assert binding.verify(report).status.value == ("succeeded" if fault is None else "failed")
    assert scene.game.indoor_walk_calls == 1
    assert scene.game.flight_confirms == int(fault is None)
    assert scene.provider_calls == ([(89, 3, 3)] if fault is None else [])
    assert report.actions_executed == scene.router.actions.actions_executed
    assert report.frames_executed == scene.game.frame_count


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


@pytest.mark.parametrize("enabled,departure_count,onward_count", [
    (False, 2, 6), (True, 0, 6), (True, 2, 6),
])
def test_indoor_capture_quotes_both_walking_legs_without_projecting_live_objects(
    indoor_scene, monkeypatch, enabled, departure_count, onward_count
):
    from test_red_living_dex_wild_corridor import _local_discovery_profile
    import pokemon_red_completion.red_resource_goal_router as routing

    scene = indoor_scene
    profile = bind_indoor_fly_departure_profile(bind_capture_fly_profile(_local_discovery_profile()))
    spec = next(s for s in profile.providers if s.kind is GoalKind.ACQUIRE_SPECIES)
    target, goal = spec.parameters["map_id"], (spec.parameters["player_y"], spec.parameters["player_x"])
    scene.provider.kind = GoalKind.ACQUIRE_SPECIES
    scene.router.quote_capture_route_work = enabled
    onward = replace(scene.onward_plan, macro_path=MacroPath((5, target), (MacroEdge(target),)),
        segments=(replace(scene.onward_plan.segments[0], target_map=target,
            transition=MacroTransition((6, 9), goal, "down")),), terminal_at=goal)
    scene.router.world.macro_graph = MacroGraph({89: (MacroEdge(0),), 5: (MacroEdge(target),)})
    scene.router.world.plan_feasible_to_map = lambda start, _map, **_kw: (
        scene.exit_plan if start.map_id == 89 else onward)
    diagnostics, quoted = [], []
    scene.router.actions.record_diagnostic_event = lambda kind, payload: diagnostics.append((kind, payload))

    def quote(plan, observed, _rom, reader):
        assert observed.raw.map_id == reader.read().map_id == 89
        quoted.append(plan)
        return dict(ordinary_trainers_crossed=(departure_count if plan is scene.exit_plan else onward_count))

    monkeypatch.setattr(routing, "ordinary_route_work_quote", quote)
    fresh = FreshRedGoalObservation("0"*64, scene.adapter.observe(), scene.observer.observe())
    binding = bind_indoor_collection_departure(scene.router, spec, scene.provider, fresh, scene.observer)
    base = .42 + (len(onward.steps) + len(scene.exit_plan.steps))/1000
    count = onward_count + departure_count if enabled else 0
    assert binding.estimated_effort == pytest.approx(min(1.0, base + count/16))
    assert binding.estimated_risk == pytest.approx(min(1.0, .18 + count/8))
    assert quoted == ([onward, scene.exit_plan] if enabled else [])
    assert [payload["transport_leg"] for _kind, payload in diagnostics] == (
        ["post_fly_walking", "indoor_departure"] if enabled else [])
    assert scene.game.actions == [] and scene.router.actions.actions_executed == 0


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

    profile = bind_indoor_fly_departure_profile(
        bind_capture_fly_profile(_local_discovery_profile())
    )
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


def test_legacy_fly_profile_keeps_its_original_indoor_menu(indoor_scene):
    legacy = bind_evolution_fly_profile(parse_red_goal_context_profile(
        build_native_boxed_evolution_profile_payload(
            indoor_scene.router.runtime.profile,
            source_species=96, target_species=97, evolution_level=26,
        )
    ))
    legacy_spec = next(s for s in legacy.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    assert "indoor_fly_departure" not in legacy_spec.parameters
    fresh = FreshRedGoalObservation(
        "0" * 64, indoor_scene.adapter.observe(), indoor_scene.observer.observe()
    )
    assert bind_indoor_collection_departure(
        indoor_scene.router, legacy_spec, indoor_scene.provider, fresh, indoor_scene.observer
    ) is None
    enabled = bind_indoor_fly_departure_profile(legacy)
    enabled_spec = next(s for s in enabled.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    assert enabled.profile_sha256 != legacy.profile_sha256
    assert bind_indoor_collection_departure(
        indoor_scene.router, enabled_spec, indoor_scene.provider, fresh, indoor_scene.observer
    ) is not None
    assert indoor_scene.router.actions.actions_executed == 0


def test_capture_retarget_preserves_the_explicit_departure_version():
    from test_red_living_dex_wild_corridor import _graph, _local_discovery_profile, _terrain

    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        derive_red_living_dex_wild_corridor,
        retarget_red_wild_profile,
    )

    profile = bind_indoor_fly_departure_profile(
        bind_capture_fly_profile(_local_discovery_profile())
    )
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph()
    )
    moved = retarget_red_wild_profile(profile, corridor)
    capture = next(s for s in moved.providers if s.kind is GoalKind.ACQUIRE_SPECIES)
    assert capture.parameters["indoor_fly_departure"] is True
    assert capture.parameters["source_id"] == "wild:Route2:grass"


@pytest.mark.parametrize("invalid", [1, "true", None])
def test_indoor_departure_requires_explicit_boolean(indoor_scene, invalid):
    import json

    from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfileError

    document = json.loads(build_native_boxed_evolution_profile_payload(
        indoor_scene.router.runtime.profile,
        source_species=96, target_species=97, evolution_level=26,
    ))
    row = next(p for p in document["providers"] if p["kind"] == "evolve_species")
    row["parameters"]["fly_transport"] = True
    row["parameters"]["indoor_fly_departure"] = invalid
    with pytest.raises(RedGoalContextProfileError, match="explicit boolean"):
        parse_red_goal_context_profile(
            (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )


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
