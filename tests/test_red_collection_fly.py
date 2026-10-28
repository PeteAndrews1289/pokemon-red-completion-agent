from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_gen1_fly import FlyWorld
from test_red_goal_skills import _adapter, _raw, _Reader

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_field_moves import Gen1FieldMoveError
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroPath, MacroTransition
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.local_router import LocalGraph, LocalPath
from pokemon_red_completion.red_collection_fly import bind_collection_fly, red_fly_landings
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    bind_capture_fly_profile,
    bind_evolution_fly_profile,
    build_native_boxed_evolution_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_routed_semantic_goal import FreshRedGoalObservation
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError, RouteSegment
from pokemon_red_completion.routed_semantic_goal import RoutedSemanticGoalError


def cartridge():
    # Independent offset/stride/data literals. Every row has a different landing
    # and pointer; the selected row is not the first or last.
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


def test_cartridge_decode_preserves_nonuniform_rows_and_repointed_coordinates():
    result = dict(red_fly_landings(cartridge()))
    assert result[0] == (6, 9)
    assert result[5] == (6, 9)
    assert result[10] == (16, 19)
    assert result[21] == (18, 21)
    rom = bytearray(cartridge())
    rom[0x6472:0x6474] = bytes((0xF0, 0x71))  # map10's pointer
    rom[0x71F0:0x71F6] = bytes((0x99, 0xC7, 21, 28, 1, 0))
    assert dict(red_fly_landings(bytes(rom)))[10] == (21, 28)


@pytest.mark.parametrize("offset,value", [(0x6448, 4), (0x6449, 1), (0x644B, 0x80), (0x7004, 1)])
def test_malformed_cartridge_refuses_to_invent_a_landing(offset, value):
    rom = bytearray(cartridge())
    rom[offset] = value
    with pytest.raises(CartridgeReadError):
        red_fly_landings(bytes(rom))


def test_truncated_table_and_aliased_pointers_reject():
    with pytest.raises(CartridgeReadError):
        red_fly_landings(bytes(10))
    rom = bytearray(cartridge())
    rom[0x644E:0x6450] = rom[0x644A:0x644C]
    with pytest.raises(CartridgeReadError):
        red_fly_landings(bytes(rom))


class Scene(FlyWorld):
    frame_count = 0
    walk_calls = 0
    dialogue_on_walk = False
    dialogue_cancels = 0
    destination_map = 89
    destination_at = (3, 3)

    def execute(self, action):
        self.frame_count += action.repeat
        if self.stage == "dialogue" and action.kind is MacroActionKind.CANCEL:
            self.actions.append(action)
            self.dialogue_cancels += 1
            if self.fault != "stuck_dialogue":
                self.stage = "landed"
                if self.fault == "dialogue_battle":
                    self.raw = replace(self.raw, battle_state=1)
                elif self.fault == "dialogue_lost_position":
                    self.raw = replace(self.raw, player_x=None)
            return
        if self.stage == "landed" and action.kind is MacroActionKind.MOVE:
            self.walk_calls += 1
            y, x = self.destination_at
            self.raw = replace(self.raw, map_id=self.destination_map, player_x=x, player_y=y)
            if self.dialogue_on_walk:
                self.stage = "dialogue"
            return
        super().execute(action)

    def read_bottom_dialogue_box_visible(self):
        return self.stage == "dialogue"

    def read_retained_outside_map(self):
        return None


@pytest.fixture
def scene():
    from test_red_goal_context_profile import _supply_transition_profile

    game = Scene(available=(5,), selected=5)
    counted = CountingExecutor(game)
    template = _adapter(_Reader(raw=_raw(), ready=True)).observe()
    adapter = SimpleNamespace(observe=lambda: replace(
        template, raw=game.raw, input_ready=game.read_input_readiness().ready,
    ))
    observer = SimpleNamespace(
        observe=lambda: TraversalSnapshot(
            game.raw.map_id,
            (game.raw.player_y, game.raw.player_x),
            game.read_input_readiness().ready,
            interruption=("scripted_dialogue" if game.read_bottom_dialogue_box_visible() else None),
            mode="land",
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
    edge = MacroEdge(89)
    plan = RoutePlan(
        MacroPath((5, 89), (edge,)),
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
    world = SimpleNamespace(
        rom=cartridge(),
        local_graphs={5: LocalGraph({(6, 9): ()})},
        object_blockers={5: frozenset()},
        macro_graph=MacroGraph({5: (edge,)}),
        plan_feasible_to_map=lambda *a, **k: plan,
    )
    runtime = SimpleNamespace(reader=game, emulator=game, adapter=adapter, profile=profile)
    router = SimpleNamespace(
        runtime=runtime,
        actions=counted,
        world=world,
        maximum_controller_actions=6000,
        maximum_emulator_frames=600000,
        routed_recovery=False,
        interruption_handler_wrapper=None,
        _replan=lambda request: plan,
    )

    def bind():
        fresh = FreshRedGoalObservation("0" * 64, adapter.observe(), observer.observe())
        return bind_collection_fly(router, spec, provider, fresh, observer)

    return SimpleNamespace(
        game=game,
        router=router,
        spec=spec,
        provider=provider,
        observer=observer,
        bind=bind,
        provider_calls=provider_calls,
        skill_passed=skill_passed,
        plan=plan,
    )


def test_real_fly_controller_then_walk_and_fresh_skill_share_actual_accounting(scene):
    binding = scene.bind()
    assert binding.kind is GoalKind.EVOLVE_SPECIES
    assert scene.game.actions == [] and scene.provider_calls == []
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert scene.game.flight_confirms == 1 and scene.game.walk_calls == 1
    assert scene.provider_calls == [(89, 3, 3)]
    assert report.actions_executed == scene.router.actions.actions_executed
    assert report.frames_executed == scene.game.frame_count
    with pytest.raises(RoutedSemanticGoalError):
        binding.execute()


def test_fly_onward_handler_uses_existing_resource_route_allowances(scene, monkeypatch):
    import pokemon_red_completion.red_routed_recovery as recovery
    from pokemon_red_completion.red_resource_goal_router import _MAX_ROUTE_FLEES

    real = recovery.guarded_collection_route_handler
    calls = []

    def handler(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(recovery, "guarded_collection_route_handler", handler)
    report = scene.bind().execute()
    assert report.actions_executed > 0
    assert calls == [dict(route_name="collection Fly onward walk",
        maximum_flees=_MAX_ROUTE_FLEES,
        maximum_scripted_dialogues=4, allow_field_faints=True, emulator=scene.game)]


def test_fly_onward_walk_dismisses_native_dialogue_before_destination(scene):
    scene.game.dialogue_on_walk = True
    binding = scene.bind()
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert scene.game.dialogue_cancels == 1
    assert scene.provider_calls == [(89, 3, 3)]
    assert scene.game.read_input_readiness().ready
    assert report.actions_executed == scene.router.actions.actions_executed
    assert report.frames_executed == scene.game.frame_count


def test_fly_dialogue_recovery_is_bounded_and_never_runs_unready_destination(scene):
    scene.game.dialogue_on_walk = True
    scene.game.fault = "stuck_dialogue"
    binding = scene.bind()
    with pytest.raises(RuntimeError, match="dialogue"):
        binding.execute()
    assert scene.game.dialogue_cancels == 8
    assert not scene.provider_calls


@pytest.mark.parametrize("fault", ["dialogue_battle", "dialogue_lost_position"])
def test_fly_dialogue_cannot_authorize_an_invalid_field_boundary(scene, fault):
    scene.game.dialogue_on_walk = True
    scene.game.fault = fault
    binding = scene.bind()
    # A separately verified successor battle may now leave the text handler.
    # This fixture's stale observer still calls it field-ready; the independent
    # fresh destination guard must reject that mismatch before invoking a skill.
    message = ("fresh Red destination differs from the route terminal"
               if fault == "dialogue_battle" else "scripted dialogue lost its traversal position")
    with pytest.raises(RuntimeError, match=message):
        binding.execute()
    assert scene.game.dialogue_cancels == 1
    assert not scene.provider_calls


@pytest.mark.parametrize("enabled", [False, True])
def test_mart_uses_same_verified_fly_and_fresh_destination_only_when_enabled(scene, enabled):
    from test_red_resupply_fly import supply_spec
    spec = supply_spec(scene, enabled=enabled)
    fresh = FreshRedGoalObservation(
        "0" * 64, scene.router.runtime.adapter.observe(), scene.observer.observe()
    )
    binding = bind_collection_fly(scene.router, spec, scene.provider, fresh, scene.observer)
    assert not scene.game.actions and not scene.provider_calls
    if not enabled:
        assert binding is None
        return
    assert binding.kind is GoalKind.RESUPPLY
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert scene.provider_calls == [(89, 3, 3)]
    assert scene.game.flight_confirms == 1
    assert report.evidence["field_moves"] == {"cuts": 0, "surfs": 0, "flights": 1}
    assert report.actions_executed == scene.router.actions.actions_executed
    assert report.frames_executed == scene.game.frame_count


@pytest.mark.parametrize(
    "change", ["badge", "holder", "fainted", "indoor", "unvisited", "blocked_landing", "no_route"]
)
def test_unavailable_transport_stays_action_free(scene, change):
    game = scene.game
    if change == "badge":
        game.raw = replace(game.raw, badge_bits=0)
    if change == "holder":
        game.raw = replace(game.raw, party_moves=((1,), (2,), (3,)))
    if change == "fainted":
        game.raw = replace(game.raw, party_hp=(200, 0, 34))
    if change == "indoor":
        game.raw = replace(game.raw, map_id=89)
    if change == "unvisited":
        game.available = ()
    if change == "blocked_landing":
        scene.router.world.object_blockers = {5: frozenset({(6, 9)})}
    if change == "no_route":

        def no_route(*a, **k):
            raise RoutePlanningError("no onward route")

        scene.router.world.plan_feasible_to_map = no_route
    assert scene.bind() is None
    assert not game.actions and not scene.provider_calls


@pytest.mark.parametrize("fault", ["money_change", "specimen_change", "wrong_landing", "no_menu"])
def test_field_move_fault_never_executes_onward_skill(scene, fault):
    binding = scene.bind()
    scene.game.fault = fault
    with pytest.raises(Gen1FieldMoveError):
        binding.execute()
    assert scene.game.walk_calls == 0 and scene.provider_calls == []
    assert scene.game.flight_confirms <= 1


def test_stale_origin_rejects_before_controller_input(scene):
    binding = scene.bind()
    scene.game.raw = replace(scene.game.raw, player_x=12)
    with pytest.raises(Gen1FieldMoveError, match="origin changed"):
        binding.execute()
    assert scene.game.actions == []


def test_unexpected_coordinate_on_correct_town_never_walks(scene):
    original = scene.game.execute

    def shifted(action):
        original(action)
        if scene.game.stage == "landed" and not scene.game.walk_calls:
            scene.game.raw = replace(scene.game.raw, player_x=10)

    scene.game.execute = shifted
    binding = scene.bind()
    with pytest.raises(Gen1FieldMoveError, match="landing differs"):
        binding.execute()
    assert scene.game.flight_confirms == 1
    assert scene.game.walk_calls == 0 and scene.provider_calls == []


def test_legacy_profile_cannot_gain_fly_access_implicitly(scene):
    old_profile = parse_red_goal_context_profile(build_native_boxed_evolution_profile_payload(
        scene.router.runtime.profile, source_species=96, target_species=97, evolution_level=26,
    ))
    old = next(s for s in old_profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    fresh = FreshRedGoalObservation(
        "0" * 64, scene.router.runtime.adapter.observe(), scene.observer.observe()
    )
    assert bind_collection_fly(scene.router, old, scene.provider, fresh, scene.observer) is None
    assert scene.game.actions == []


def test_destination_failure_is_not_laundered_as_flight_success(scene):
    binding = scene.bind()
    scene.skill_passed[0] = False
    report = binding.execute()
    assert binding.verify(report).status.value == "failed"
    assert scene.provider_calls == [(89, 3, 3)]


def test_budget_limits_flight_inputs_before_overrun(scene):
    scene.router.maximum_controller_actions = 1
    binding = scene.bind()
    with pytest.raises(RuntimeError, match="budget"):
        binding.execute()
    assert scene.router.actions.actions_executed == 1
    assert scene.game.walk_calls == 0 and scene.provider_calls == []


def test_opt_in_preserves_previous_profile_and_rejects_nonboolean():
    import json

    from test_red_goal_context_profile import _supply_transition_profile

    original = parse_red_goal_context_profile(
        build_native_boxed_evolution_profile_payload(
            _supply_transition_profile(), source_species=96, target_species=97, evolution_level=26
        )
    )
    updated = bind_evolution_fly_profile(original)
    old = next(s for s in original.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    new = next(s for s in updated.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    assert "fly_transport" not in old.parameters and new.parameters["fly_transport"] is True
    assert [s for s in original.providers if s.kind is not GoalKind.EVOLVE_SPECIES] == [
        s for s in updated.providers if s.kind is not GoalKind.EVOLVE_SPECIES
    ]
    payload = json.loads(
        build_native_boxed_evolution_profile_payload(
            original, source_species=96, target_species=97, evolution_level=26
        )
    )
    next(s for s in payload["providers"] if s["kind"] == "evolve_species")["parameters"][
        "fly_transport"
    ] = 1
    with pytest.raises(RedGoalContextProfileError, match="Fly transport"):
        parse_red_goal_context_profile(
            (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )


def _indoor_capture_profile(profile):
    from pokemon_red_completion.red_goal_context_profile import (
        _thaw,
        build_red_goal_context_profile_payload,
    )

    rows = []
    for provider in profile.providers:
        parameters = _thaw(provider.parameters)
        if provider.kind is GoalKind.ACQUIRE_SPECIES:
            parameters.update(map_id=214, source_id="wild:PokemonMansion2F:grass")
        rows.append((provider.kind, provider.mechanic, parameters))
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(rows)
    ))


@pytest.mark.parametrize("enabled,count", [(False, 6), (True, 0), (True, 6)])
def test_fly_capture_route_work_is_explicit_read_only_and_uses_real_observation(
    scene, monkeypatch, enabled, count
):
    from test_red_living_dex_wild_corridor import _local_discovery_profile

    import pokemon_red_completion.red_resource_goal_router as routing

    spec = next(s for s in bind_capture_fly_profile(_local_discovery_profile()).providers
                if s.kind is GoalKind.ACQUIRE_SPECIES)
    target = spec.parameters["map_id"]
    scene.provider.kind = GoalKind.ACQUIRE_SPECIES
    scene.router.quote_capture_route_work = enabled
    scene.router.world.macro_graph = MacroGraph({5: (MacroEdge(target),)})
    scene.router.world.plan_feasible_to_map = lambda *_a, **_k: scene.plan
    diagnostics, seen = [], []
    scene.router.actions.record_diagnostic_event = (
        lambda kind, payload: diagnostics.append((kind, payload))
    )

    def quote(plan, observed, rom, reader):
        seen.append(observed.raw.map_id)
        assert observed.raw == scene.game.raw
        assert plan is scene.plan and reader is scene.game
        return dict(ordinary_trainers_crossed=count)

    monkeypatch.setattr(routing, "ordinary_route_work_quote", quote)
    real = scene.router.runtime.adapter.observe()
    # Qualification may project a different future departure map; it must not
    # reinterpret real current-map object positions as belonging to that map.
    projected = replace(real, raw=replace(real.raw, map_id=0))
    fresh = FreshRedGoalObservation("0"*64, projected,
                                   replace(scene.observer.observe(), map_id=0))
    binding = bind_collection_fly(scene.router, spec, scene.provider, fresh, scene.observer)
    assert binding is not None and scene.game.actions == []
    base = min(1.0, .42 + len(scene.plan.steps)/1000)
    assert binding.estimated_effort == pytest.approx(min(1.0, base + (count/16 if enabled else 0)))
    assert binding.estimated_risk == pytest.approx(min(1.0, .18 + (count/8 if enabled else 0)))
    assert seen == ([scene.game.raw.map_id] if enabled else [])
    assert len(diagnostics) == int(enabled)
    if enabled:
        assert diagnostics[0][1]["transport_leg"] == "post_fly_walking"
        assert diagnostics[0][1]["source_id"] == spec.parameters["source_id"]


@pytest.mark.parametrize("succeeded", [True, False])
@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("indoor", [False, True])
def test_capture_uses_declared_or_observed_boundary_and_keeps_source_history(
    scene, monkeypatch, succeeded, observed, indoor
):
    from test_red_living_dex_wild_corridor import _local_discovery_profile

    import pokemon_red_completion.red_observed_local_capture as local
    from pokemon_red_completion.red_goal_context_profile import bind_observed_local_capture_profile

    profile = bind_capture_fly_profile(_local_discovery_profile())
    if observed:
        profile = bind_observed_local_capture_profile(profile)
    if indoor:
        profile = _indoor_capture_profile(profile)
    spec = next(s for s in profile.providers if s.kind is GoalKind.ACQUIRE_SPECIES)
    target = spec.parameters["map_id"]
    declared_at = (spec.parameters["player_y"], spec.parameters["player_x"])
    live_arrival = observed and indoor
    goal_at = (3, 4) if live_arrival else declared_at
    assert (target, goal_at) != (89, (3, 3))
    scene.provider.kind = GoalKind.ACQUIRE_SPECIES
    scene.skill_passed[0] = succeeded
    scene.game.destination_map, scene.game.destination_at = target, goal_at
    segment = replace(scene.plan.segments[0], target_map=target,
                      transition=MacroTransition((6, 9), goal_at, "down"))
    plan = replace(scene.plan, macro_path=MacroPath((5, target), (MacroEdge(target),)),
                   segments=(segment,), terminal_at=goal_at)
    scene.router.world.macro_graph = MacroGraph({5: (MacroEdge(target),)})

    def plan_to(start, map_id, *, goal_at):
        assert map_id == target
        # The observed profile must not ask for the disconnected static patch.
        assert goal_at == (None if live_arrival else scene.game.destination_at)
        assert start.map_id == 5 and start.at == (6, 9)
        return plan

    scene.router.world.plan_feasible_to_map = plan_to
    observed_calls = []

    def live_bind(router, selected_spec, observation):
        observed_calls.append((selected_spec, observation))
        assert router is scene.router and selected_spec is spec
        assert observation.raw.map_id == target
        assert (observation.raw.player_y, observation.raw.player_x) == goal_at
        assert scene.game.flight_confirms == scene.game.walk_calls == 1
        offer = scene.provider.offer(observation)
        return replace(offer.binding, search_source_ref=(
            "pokemon.red:acquisition:" + str(spec.parameters["source_id"])
        ))

    monkeypatch.setattr(local, "bind_observed_local_capture", live_bind)
    fresh = FreshRedGoalObservation(
        "0" * 64, scene.router.runtime.adapter.observe(), scene.observer.observe()
    )
    binding = bind_collection_fly(scene.router, spec, scene.provider, fresh, scene.observer)
    assert scene.game.actions == [] and scene.provider_calls == [] and observed_calls == []
    assert binding.kind is GoalKind.ACQUIRE_SPECIES
    assert binding.search_source_ref == "pokemon.red:acquisition:" + spec.parameters["source_id"]
    report = binding.execute()
    assert binding.verify(report).status.value == ("succeeded" if succeeded else "failed")
    assert scene.provider_calls == [(target, *goal_at)]
    assert scene.game.flight_confirms == scene.game.walk_calls == 1
    assert report.actions_executed == scene.router.actions.actions_executed
    assert report.frames_executed == scene.game.frame_count
    assert len(observed_calls) == int(live_arrival)
    assert (spec.parameters["player_y"], spec.parameters["player_x"]) == declared_at


@pytest.mark.parametrize("fault", ["unreachable", "wrong_source", "wrong_kind"])
def test_observed_capture_arrival_never_reinstates_static_provider(scene, monkeypatch, fault):
    from test_red_living_dex_wild_corridor import _local_discovery_profile

    import pokemon_red_completion.red_observed_local_capture as local
    from pokemon_red_completion.red_goal_context_profile import bind_observed_local_capture_profile

    profile = _indoor_capture_profile(bind_observed_local_capture_profile(bind_capture_fly_profile(
        _local_discovery_profile()
    )))
    spec = next(s for s in profile.providers if s.kind is GoalKind.ACQUIRE_SPECIES)
    target, arrival = spec.parameters["map_id"], (3, 4)
    scene.provider.kind = GoalKind.ACQUIRE_SPECIES
    scene.game.destination_map, scene.game.destination_at = target, arrival
    scene.router.world.macro_graph = MacroGraph({5: (MacroEdge(target),)})
    scene.router.world.plan_feasible_to_map = lambda *_a, **_k: replace(
        scene.plan,
        macro_path=MacroPath((5, target), (MacroEdge(target),)),
        segments=(replace(scene.plan.segments[0], target_map=target,
                          transition=MacroTransition((6, 9), arrival, "down")),),
        terminal_at=arrival,
    )

    def live_bind(_router, _spec, observation):
        if fault == "unreachable":
            return None
        return ExecutableGoalBinding(
            "wrong-observed-child",
            GoalKind.RESTORE_TEAM if fault == "wrong_kind" else GoalKind.ACQUIRE_SPECIES,
            .1, .1,
            lambda: pytest.fail("a changed-source/kind child must not run"),
            lambda _: GoalVerification.succeeded(),
            search_source_ref=("pokemon.red:acquisition:" + (
                "wild:Route1:grass" if fault == "wrong_source" else spec.parameters["source_id"]
            )),
        )

    monkeypatch.setattr(local, "bind_observed_local_capture", live_bind)
    fresh = FreshRedGoalObservation(
        "0" * 64, scene.router.runtime.adapter.observe(), scene.observer.observe()
    )
    binding = bind_collection_fly(scene.router, spec, scene.provider, fresh, scene.observer)
    assert binding is not None and scene.game.actions == []
    if fault == "unreachable":
        report = binding.execute()
        assert binding.verify(report).status.value == "failed"
        assert report.actions_executed == scene.router.actions.actions_executed
    else:
        with pytest.raises(RuntimeError, match="source|kind"):
            binding.execute()
    assert scene.provider_calls == []
    assert scene.game.flight_confirms == scene.game.walk_calls == 1


def test_capture_fly_opt_in_is_strict_and_survives_source_retargeting():
    import json

    from test_red_living_dex_wild_corridor import _graph, _local_discovery_profile, _terrain

    from pokemon_red_completion.red_goal_context_profile import (
        _thaw,
        build_red_goal_context_profile_payload,
    )
    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        derive_red_living_dex_wild_corridor,
        retarget_red_wild_profile,
    )

    original = _local_discovery_profile()
    updated = bind_capture_fly_profile(original)
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    moved = retarget_red_wild_profile(updated, corridor)
    for profile in (updated, moved):
        capture = next(s for s in profile.providers if s.kind is GoalKind.ACQUIRE_SPECIES)
        assert capture.parameters["fly_transport"] is True
        assert all("fly_transport" not in s.parameters for s in profile.providers
                   if s.kind is not GoalKind.ACQUIRE_SPECIES)
    assert all("fly_transport" not in s.parameters for s in original.providers)
    data = json.loads(build_red_goal_context_profile_payload(
        profile_id=updated.profile_id,
        providers=tuple((s.kind, s.mechanic, _thaw(s.parameters)) for s in updated.providers),
    ))
    capture = next(s for s in data["providers"] if s["kind"] == "acquire_species")
    capture["parameters"]["fly_transport"] = 1
    with pytest.raises(RedGoalContextProfileError, match="capture Fly transport"):
        parse_red_goal_context_profile(
            (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )


def test_legacy_capture_profile_does_not_gain_fly_access(scene):
    from test_red_living_dex_wild_corridor import _local_discovery_profile

    spec = next(s for s in _local_discovery_profile().providers
                if s.kind is GoalKind.ACQUIRE_SPECIES)
    fresh = FreshRedGoalObservation(
        "0" * 64, scene.router.runtime.adapter.observe(), scene.observer.observe()
    )
    assert bind_collection_fly(scene.router, spec, scene.provider, fresh, scene.observer) is None
    assert scene.game.actions == [] and scene.provider_calls == []
