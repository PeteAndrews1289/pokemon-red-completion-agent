from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context import (
    _VERIFIED_TO_CINNABAR,
    _ActionDelegate,
    _capture,
    _Emulator,
    _Reader,
    _targeted_team_profile,
)

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_collection import (
    RedBoxCollectionState,
    RedCurrentBoxState,
    red_internal_species_id,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_native_boxed_evolution_profile_payload,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_native_boxed_evolution import (
    bind_native_boxed_evolution,
    bind_native_evolution_goal_reserve,
)
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID


@pytest.mark.parametrize("axis", ["actions", "frames"])
@pytest.mark.parametrize("large", [False, True])
def test_goal_reserve_counts_transport_and_stops_before_local_budget(tmp_path, axis, large):
    runtime, reader, _ = runtime_fixture(tmp_path, count=1)
    actions = CountingExecutor(_ActionDelegate())
    actions.actions_executed = 19
    runtime.emulator.frame_count = 101
    maximum_actions, maximum_frames = (30000, 3000000) if large else (3000, 300000)
    scoped = bind_native_evolution_goal_reserve(
        runtime, actions, maximum_actions=maximum_actions, maximum_frames=maximum_frames,
    )
    original = reader.read()
    assert runtime.evolution_stop_requested is None
    assert scoped.evolution_stop_requested() is False
    if axis == "actions":
        boundary = maximum_actions - min(3000, maximum_actions // 4)
        actions.actions_executed += boundary - 1
        assert scoped.evolution_stop_requested() is False
        actions.actions_executed += 1
    else:
        boundary = maximum_frames - min(250000, maximum_frames // 4)
        runtime.emulator.frame_count += boundary - 1
        assert scoped.evolution_stop_requested() is False
        runtime.emulator.frame_count += 1
    assert scoped.evolution_stop_requested() is True
    assert reader.read() == original


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, None])
@pytest.mark.parametrize("axis", ["maximum_actions", "maximum_frames"])
def test_goal_reserve_rejects_invalid_limits_before_runtime_access(value, axis):
    limits = dict(maximum_actions=30000, maximum_frames=3000000)
    limits[axis] = value
    with pytest.raises(ValueError, match="positive integers"):
        bind_native_evolution_goal_reserve(None, None, **limits)


@pytest.mark.parametrize("requested", [True, False, "untyped"])
def test_goal_reserve_preserves_existing_stop_authority(tmp_path, requested):
    runtime, _, _ = runtime_fixture(tmp_path, count=1)
    runtime = replace(runtime, evolution_stop_requested=lambda: requested)
    actions = CountingExecutor(_ActionDelegate())
    scoped = bind_native_evolution_goal_reserve(
        runtime, actions, maximum_actions=30000, maximum_frames=3000000,
    )
    if requested == "untyped":
        with pytest.raises(TypeError, match="return a boolean"):
            scoped.evolution_stop_requested()
    else:
        assert scoped.evolution_stop_requested() is requested
    assert actions.actions_executed == 0 and runtime.emulator.frame_count == 0


@pytest.mark.parametrize("axis", ["actions", "frames"])
def test_goal_reserve_rejects_counters_moving_backwards(tmp_path, axis):
    runtime, _, _ = runtime_fixture(tmp_path, count=1)
    actions = CountingExecutor(_ActionDelegate())
    actions.actions_executed = 19
    runtime.emulator.frame_count = 101
    scoped = bind_native_evolution_goal_reserve(
        runtime, actions, maximum_actions=30000, maximum_frames=3000000,
    )
    if axis == "actions":
        actions.actions_executed -= 1
    else:
        runtime.emulator.frame_count -= 1
    with pytest.raises(RuntimeError, match="counters moved backwards"):
        scoped.evolution_stop_requested()


@pytest.mark.parametrize("location,covered,available", [
    (MapId.CERULEAN_POKECENTER,True,True),
    (MapId.CERULEAN_POKECENTER,False,False),
    (MapId.CERULEAN_GYM,True,False),
])
def test_declared_local_venue_can_use_non_blastoise_party_but_keeps_native_coverage(
    tmp_path,monkeypatch,location,covered,available,
):
    import pokemon_red_completion.red_native_boxed_evolution as module
    runtime,reader,_=runtime_fixture(tmp_path,count=1)
    source=red_internal_species_id(77)
    reader.raw=replace(reader.raw,map_id=location,player_x=3,player_y=3,
        party_species_ids=(*tuple(179 if s==BLASTOISE_SPECIES_ID else s
                                  for s in reader.raw.party_species_ids[:5]),source))
    venue=replace(module.context.ROUTE_11_TRAINING_VENUE,
        is_in_center=lambda raw:raw.map_id==MapId.CERULEAN_POKECENTER)
    monkeypatch.setattr(module,"wild_tables",lambda _: {venue.map_id:((10,165),)})
    monkeypatch.setattr(module,"collection_finisher",lambda *a,**k: object() if covered else None)
    native=bind_native_boxed_evolution(runtime,SimpleNamespace(rom=b"test"),training_venues=(venue,))
    actions=CountingExecutor(_ActionDelegate())
    observation=native.adapter.observe()
    assert BLASTOISE_SPECIES_ID not in observation.party.species_ids()
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(observation)
    assert (offer.binding is not None) == available
    assert actions.actions_executed==0


@pytest.mark.parametrize("vacates,unsafe,moving", [
    (True, False, True), (False, False, True), (True, True, True), (True, False, False),
])
@pytest.mark.parametrize("map_id,goal,standing", [
    (171, (4, 13), (5, 13)),
    (133, (4, 13), (5, 13)),
    (133, (3, 3), (4, 3)),
])
def test_pc_replanner_waits_for_live_moving_target_without_ignoring_blockers(
    monkeypatch, vacates, unsafe, moving, map_id, goal, standing,
):
    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.route_executor import ReplanRequest, TraversalSnapshot
    from pokemon_red_completion.route_plan import RoutePlanningError

    other = (2, 11)
    raw = SimpleNamespace(map_id=map_id, player_y=standing[0], player_x=standing[1], player_money=123,
                          bag_items=((1, 1),), badge_bits=255, event_flags=b"", battle_state=0)
    waits, delegated = [], []

    def objects():
        return (SimpleNamespace(at=goal, moving=moving),) if not waits or not vacates else ()

    def observe():
        return SimpleNamespace(input_ready=not (unsafe and waits), raw=raw,
                               party="party", collection_observation="dex")

    def live():
        return TraversalSnapshot(map_id, standing, True, mode="land", occupied=frozenset(
            {other, goal} if not waits or not vacates else {other}))

    def delegate(request):
        delegated.append(request)
        if goal in request.blocked[map_id]:
            raise RoutePlanningError("PC remains occupied")
        return "same PC route"

    runtime = SimpleNamespace(reader=SimpleNamespace(read_current_map_objects=objects),
                              adapter=SimpleNamespace(observe=observe))
    world = SimpleNamespace(replanner=lambda: delegate,
                            with_current_observation=lambda reader: world)
    actions = SimpleNamespace(execute=lambda action: waits.append(action))
    monkeypatch.setattr(module, "Gen1TraversalObserver",
                        lambda reader: SimpleNamespace(observe=live))
    request = ReplanRequest(live(), map_id, goal, {map_id: frozenset({goal, other})}, 1)
    replan = module.native_evolution_pc_replanner(runtime, world, actions)
    if not moving:
        with pytest.raises(RoutePlanningError, match="occupied"):
            replan(request)
        assert not waits
    elif unsafe:
        with pytest.raises(module.context.RedGoalContextError, match="protected native"):
            replan(request)
        assert len(waits) == 1 and not delegated
    elif not vacates:
        with pytest.raises(module.context.RedGoalContextError, match="within its bound"):
            replan(request)
        assert len(waits) == 16 and not delegated
    else:
        assert replan(request) == "same PC route"
        assert len(waits) == 1
        assert delegated[0].goal_map == request.goal_map and delegated[0].goal_at == goal
        assert delegated[0].blocked[map_id] == frozenset({other})
        assert request.blocked[map_id] == frozenset({goal, other})
    assert all(action.kind is MacroActionKind.WAIT and action.repeat == 120 for action in waits)


@pytest.mark.parametrize("current_map,goal_map,goal", [
    (133, 133, (3, 4)), (133, 171, (3, 3)), (6, 6, (3, 3)),
])
def test_center_waiter_does_not_intervene_at_other_destinations(current_map, goal_map, goal):
    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.route_executor import ReplanRequest, TraversalSnapshot

    calls = []

    def forbidden(*args, **kwargs):
        pytest.fail("unrecognized destination must delegate without waits or observations")

    runtime = SimpleNamespace(reader=SimpleNamespace(read_current_map_objects=forbidden))
    world = SimpleNamespace(replanner=lambda: lambda request: calls.append(request) or "original route")
    actions = SimpleNamespace(execute=forbidden)
    request = ReplanRequest(TraversalSnapshot(current_map, (4, 3), True), goal_map, goal, {}, 1)
    assert module.native_evolution_pc_replanner(runtime, world, actions)(request) == "original route"
    assert calls == [request]


@pytest.mark.parametrize("mode", [None, 0, 1, "yes"])
def test_guarded_venue_mode_requires_an_explicit_boolean(mode):
    with pytest.raises(ValueError, match="guarded-venue mode"):
        bind_native_boxed_evolution(None, None, allow_guarded_venue_escapes=mode)


@pytest.mark.parametrize("kind", ["ordinary", "escort", "volatile"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("covered", [False, True])
@pytest.mark.parametrize("excluded", [frozenset(), frozenset({150})])
def test_guarded_evolution_venue_needs_existing_defensive_coverage(
    monkeypatch,
    kind,
    enabled,
    covered,
    excluded,
):
    import pokemon_red_completion.red_native_boxed_evolution as module

    calls = []
    monkeypatch.setattr(module.context, "MANSION_VOLATILE_ENEMY_SPECIES", frozenset({55}))
    monkeypatch.setattr(module.context, "MANSION_ESCORT_ENEMY_SPECIES", frozenset({136}))

    def escape(*args, **kwargs):
        calls.append(("escape", kwargs))
        return object() if covered else None

    def finisher(*args, **kwargs):
        calls.append(("finisher", kwargs))
        return object() if covered else None

    monkeypatch.setattr(module, "collection_escape_escort", escape)
    monkeypatch.setattr(module, "collection_finisher", finisher)
    species = {"ordinary": 33, "escort": 136, "volatile": 55}[kind]
    admitted = enabled or kind == "ordinary"
    assert module.native_evolution_encounter_supported(
        "party", 89, "policy", 35, species, allow_guarded_escapes=enabled,
        excluded_helper_species=excluded,
    ) is (admitted and covered)
    assert calls == (
        []
        if not admitted
        else [
            ("escape", dict(enemy_level=35, enemy_species=species, resources=False,
                            excluded_helper_species=excluded))
            if kind in ("volatile", "escort")
            else ("finisher", dict(enemy_level=35, enemy_species=species, resources=False,
                                  excluded_helper_species=excluded))
        ]
    )


@pytest.fixture(autouse=True)
def native_encounter_tables(monkeypatch):
    # Explicit, nonuniform fixture; individual execution tests override it.
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_evolution.wild_tables",
        lambda rom: {22: [(10, 0x21), (15, 0x6C)], 165: [(20, 0x3B)]},
    )


@pytest.mark.parametrize(
    "fault", [None, "different_ref", "different_species", "no_guard", "no_loan"]
)
def test_boxed_training_declines_an_active_retained_fingerprint_before_pc_input(fault):
    from pokemon_red_completion.red_native_boxed_evolution import (
        boxed_loan_has_retained_fingerprint_collision,
    )

    box = SimpleNamespace(
        species_id=14 if fault == "different_species" else 13,
        preparation_ref="other" if fault == "different_ref" else "active",
    )
    guard = SimpleNamespace(
        reader=SimpleNamespace(preparation_specimen_refs=lambda: ("active",)),
        loanable_refs=frozenset() if fault == "no_loan" else frozenset({"loan"}),
    )
    runtime = SimpleNamespace(
        adapter=SimpleNamespace(party_guard=None if fault == "no_guard" else guard),
        reader=SimpleNamespace(read_box_specimen_identities=lambda: (box,)),
    )
    assert boxed_loan_has_retained_fingerprint_collision(runtime, 13) is (fault is None)


@pytest.mark.parametrize("limit", [1, 128, 129, 512])
def test_declared_evolution_work_size_is_bounded(limit):
    from pokemon_red_completion.red_native_boxed_evolution import validate_native_evolution_quanta

    assert validate_native_evolution_quanta(limit) == limit


@pytest.mark.parametrize("limit", [0, 513, True, 1.5, "512", None])
def test_native_binder_rejects_invalid_work_size_before_runtime_access(limit):
    with pytest.raises(ValueError, match="quantum limit"):
        bind_native_boxed_evolution(None, None, maximum_quanta=limit)


@pytest.mark.parametrize('limit',[0,-1,True,1.5,float('inf'),None])
def test_native_wall_guard_rejects_invalid_size_before_runtime_access(limit):
    with pytest.raises(ValueError,match='wall limit'):
        bind_native_boxed_evolution(None,None,maximum_wall_seconds=limit)


@pytest.mark.parametrize(
    "failure", [None, "unsupported_route", "transport", "position", "party", "money"]
)
@pytest.mark.parametrize("live_route_replanning", [False, True])
def test_retained_center_tile_is_routed_to_nurse_before_training(
    tmp_path, monkeypatch, failure, live_route_replanning
):
    from pokemon_red_completion import red_native_boxed_evolution as module
    from pokemon_red_completion import red_resource_goal_router, route_executor

    runtime, reader, _ = runtime_fixture(tmp_path)
    reader.raw = replace(reader.raw, player_x=13, player_y=4)
    start = SimpleNamespace(map_id=reader.raw.map_id, at=(4, 13))
    route, calls = object(), []
    monkeypatch.setattr(
        module, "Gen1TraversalObserver", lambda r: SimpleNamespace(observe=lambda: start)
    )
    monkeypatch.setattr(
        red_resource_goal_router,
        "_walking_plan",
        lambda p: p is route and failure != "unsupported_route",
    )

    def plan(observed, target, *, goal_at):
        assert observed is start and target == reader.raw.map_id and goal_at == (3, 3)
        calls.append("plan")
        return route

    def prepare(actions, r):
        assert r is reader
        calls.append("settle_pc")

    def execute(p, actions, observer, *, limits, **options):
        assert p is route and calls[-2:] == ["plan", "settle_pc"]
        assert options == ({"replanner": replanner} if live_route_replanning else {})
        calls.append("transport")
        reader.raw = replace(reader.raw, player_x=3, player_y=3)
        if failure == "position":
            reader.raw = replace(reader.raw, player_x=4)
        elif failure == "party":
            reader.raw = replace(reader.raw, party_hp=tuple(hp - 1 for hp in reader.raw.party_hp))
        elif failure == "money":
            reader.raw = replace(reader.raw, player_money=(reader.raw.player_money or 0) + 1)
        return SimpleNamespace(passed=failure != "transport")

    monkeypatch.setattr(module, "prepare_center_departure", prepare)
    monkeypatch.setattr(route_executor, "execute_route", execute)
    replanner = object()
    observed_world = SimpleNamespace(plan_feasible_to_map=plan, replanner=lambda: replanner)

    def live_world(r):
        assert r is reader
        calls.append("live_overlay")
        return observed_world

    world = SimpleNamespace(plan_feasible_to_map=plan, with_current_observation=live_world)
    options = {"live_route_replanning": True} if live_route_replanning else {}
    if failure:
        with pytest.raises(module.context.RedGoalContextError):
            module.prepare_native_training_center(runtime, world, object(), **options)
    else:
        module.prepare_native_training_center(runtime, world, object(), **options)
        assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)
    assert calls == (["live_overlay"] if live_route_replanning else []) + (
        ["plan"] if failure == "unsupported_route" else ["plan", "settle_pc", "transport"]
    )


@pytest.mark.parametrize(
    "moves,pp,disabled,expected",
    [
        ((52, 39, 23, 0), (25, 30, 20, 0), 0, 3),
        ((52, 39, 23, 0), (25, 30, 20, 0), 3, 1),
        ((39, 23, 52, 0), (30, 20, 25, 0), 0, 2),
        ((52, 39, 23, 0), (25, 30, 0, 0), 0, 1),
    ],
)
def test_native_training_selects_damage_not_tail_whip_or_fixed_slot(moves, pp, disabled, expected):
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_native_boxed_evolution import native_training_move_slot

    state = RawGameState(
        game_started=True,
        map_id=22,
        player_x=0,
        player_y=0,
        party_count=1,
        battle_state=1,
        active_party_species_id=red_internal_species_id(77),
        enemy_species_id=red_internal_species_id(19),
        active_party_moves=moves,
        active_party_pp=pp,
        player_disabled_move_slot=disabled,
    )
    assert native_training_move_slot(state) == expected


def test_native_training_refuses_status_only_or_self_destruct():
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_native_boxed_evolution import native_training_move_slot
    from pokemon_red_completion.red_team_training import _PauseForTeamTrainingRecovery

    state = RawGameState(
        game_started=True,
        map_id=22,
        player_x=0,
        player_y=0,
        party_count=1,
        battle_state=1,
        active_party_species_id=red_internal_species_id(77),
        enemy_species_id=red_internal_species_id(19),
        active_party_moves=(39, 120, 0, 0),
        active_party_pp=(30, 5, 0, 0),
    )
    with pytest.raises(_PauseForTeamTrainingRecovery):
        native_training_move_slot(state)


@pytest.mark.parametrize("hp,disabled,allowed", [(100, 0, True), (90, 0, False), (100, 1, False)])
def test_collection_turn_guard_uses_real_moves_health_and_disable(hp, disabled, allowed):
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_native_boxed_evolution import native_training_move_guard
    from pokemon_red_completion.red_team_training import _PauseForTeamTrainingRecovery

    raw = RawGameState(
        game_started=True,
        map_id=22,
        player_x=0,
        player_y=0,
        party_count=2,
        battle_state=1,
        active_party_species_id=BLASTOISE_SPECIES_ID,
        enemy_species_id=0x21,
        active_party_moves=(33, 0, 0, 0),
        active_party_pp=(20, 0, 0, 0),
        active_party_hp=hp,
        active_party_max_hp=100,
        player_disabled_move_slot=disabled,
    )
    # Tackle is usable even though the historic Blastoise move list omits it.
    if allowed:
        native_training_move_guard(raw)
    else:
        with pytest.raises(_PauseForTeamTrainingRecovery):
            native_training_move_guard(raw)


def test_storage_cannot_deposit_the_only_finisher(tmp_path):
    from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest

    runtime, reader, _ = runtime_fixture(tmp_path)
    reader.raw = replace(reader.raw, party_moves=(((100, 0, 0, 0),) * 5 + ((33, 0, 0, 0),)))
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    actions = CountingExecutor(_ActionDelegate())
    request = RedBoxedLevelEvolutionGoalRequest(
        red_internal_species_id(77),
        red_internal_species_id(78),
        0,
        1,
        6,
        red_internal_species_id(106),
    )
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert offer.binding is None
    assert offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    with pytest.raises(Exception, match="training capability is unavailable"):
        native.boxed_level_evolution_executor(request, actions)
    assert actions.actions_executed == 0


def runtime_fixture(tmp_path, *, source=77, target=78, evolution_level=40, count=2, level=32):
    reader = _Reader()
    reader.raw = replace(
        reader.raw,
        map_id=MapId.CINNABAR_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=6,
        party_species_ids=(
            BLASTOISE_SPECIES_ID,
            *(red_internal_species_id(n) for n in (83, 51, 143, 135, 106)),
        ),
        party_levels=(54, 55, 55, 55, 55, 55),
        party_hp=(150, 40, 40, 40, 40, 40),
        party_max_hp=(150, 40, 40, 40, 40, 40),
        party_status=(0,) * 6,
        party_moves=((1, 0, 0, 0),) * 6,
        party_pp=((20, 0, 0, 0),) * 6,
    )
    reader.boxes = RedBoxCollectionState(
        (
            RedCurrentBoxState(0, (red_internal_species_id(source),) * count, (level,) * count),
            *(RedCurrentBoxState(i, (), ()) for i in range(1, 12)),
        ),
        0,
        False,
    )
    base = _targeted_team_profile("native-boxed-test")
    original = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=base.profile_id,
            providers=(
                *((s.kind, s.mechanic, dict(s.parameters)) for s in base.providers),
                (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            ),
        )
    )
    profile = parse_red_goal_context_profile(
        build_native_boxed_evolution_profile_payload(
            original,
            source_species=source,
            target_species=target,
            evolution_level=evolution_level,
        )
    )
    runtime = build_red_goal_context_runtime(
        profile=profile,
        capture=_capture(tmp_path, verified_objective_ids=_VERIFIED_TO_CINNABAR),
        emulator=_Emulator(),
        reader=reader,
    )
    return runtime, reader, original


@pytest.mark.parametrize(
    "count,reason",
    [
        (0, GoalUnavailableReason.NO_LEGAL_TARGET),
        (1, GoalUnavailableReason.NO_LEGAL_TARGET),
        (2, None),
        (3, GoalUnavailableReason.NO_LEGAL_TARGET),
    ],
)
def test_native_availability_preserves_precursor_and_declares_engine_multiplicity(
    tmp_path, count, reason
):
    runtime, _, _ = runtime_fixture(tmp_path, count=count)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    actions = CountingExecutor(_ActionDelegate())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert offer.unavailable_reason is reason
    assert (offer.binding is not None) == (reason is None)
    assert runtime.boxed_level_evolution_executor is None
    assert actions.actions_executed == 0


@pytest.mark.parametrize("escort_level,available", [(54, True), (55, True), (63, True)])
def test_native_direct_evolution_can_use_a_capped_escape_escort(tmp_path, escort_level, available):
    runtime, reader, _ = runtime_fixture(tmp_path)
    reader.raw = replace(reader.raw, party_levels=(escort_level, 55, 55, 55, 55, 55))
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    actions = CountingExecutor(_ActionDelegate())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert (offer.binding is not None) is available
    if not available:
        assert offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert actions.actions_executed == 0


def test_native_execution_rechecks_finisher_capability_before_any_input(tmp_path):
    from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest

    runtime, reader, _ = runtime_fixture(tmp_path)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    reader.raw = replace(
        reader.raw,
        party_moves=((100, 0, 0, 0),) * 6,
    )
    actions = CountingExecutor(_ActionDelegate())
    request = RedBoxedLevelEvolutionGoalRequest(
        red_internal_species_id(77),
        red_internal_species_id(78),
        0,
        1,
        6,
        red_internal_species_id(106),
    )
    with pytest.raises(Exception, match="training capability is unavailable"):
        native.boxed_level_evolution_executor(request, actions)
    assert actions.actions_executed == 0


@pytest.mark.parametrize("trainee_hp", [40, 1])
@pytest.mark.parametrize("reserve_stop", [False, True, 512])
def test_partial_evolution_resumes_in_party_without_repeating_storage(
    tmp_path, monkeypatch, trainee_hp, reserve_stop
):
    from types import SimpleNamespace

    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.actions import MacroAction, MacroActionKind
    from pokemon_red_completion.red_team_training import EvolutionTrainingPaused

    runtime, reader, _ = runtime_fixture(tmp_path)
    source = red_internal_species_id(77)
    reader.raw = replace(
        reader.raw,
        party_species_ids=(*reader.raw.party_species_ids[:5], source),
        party_levels=(63, 55, 55, 55, 55, 33),
        party_hp=(150, 40, 40, 40, 40, trainee_hp),
    )
    reader.boxes = replace(
        reader.boxes,
        boxes=(
            RedCurrentBoxState(0, (source, red_internal_species_id(106)), (30, 55)),
            *reader.boxes.boxes[1:],
        ),
    )
    calls = []

    def train(actions, *args, **kwargs):
        assert reader.raw.party_hp == reader.raw.party_max_hp
        calls.append(kwargs)
        actions.execute(MacroAction(MacroActionKind.WAIT))
        raise EvolutionTrainingPaused(4, 2)

    def restore(current, actions):
        assert current.reader is reader
        if reader.raw.party_hp != reader.raw.party_max_hp:
            actions.execute(MacroAction(MacroActionKind.WAIT))
            reader.raw = replace(reader.raw, party_hp=reader.raw.party_max_hp)
            return 1
        return 0

    monkeypatch.setattr(module, "restore_native_center_party", restore)
    monkeypatch.setattr(module.context, "run_red_team_balancing", train)
    monkeypatch.setattr(
        module,
        "RedGoalBoxedEvolutionExecutor",
        lambda **kwargs: pytest.fail("resume must not repeat storage"),
    )
    monkeypatch.setattr(module, "wild_tables", lambda rom: {int(MapId.ROUTE_11): [(10, 0x21)]})
    runtime.evolution_stop_requested = (lambda: True) if reserve_stop else None
    native = bind_native_boxed_evolution(
        runtime,
        SimpleNamespace(rom=b"test"),
        maximum_quanta=512 if reserve_stop == 512 else 128 if reserve_stop else 1,
    )
    actions = CountingExecutor(_ActionDelegate())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert offer.binding is not None
    report = offer.binding.execute()
    assert report.evidence["evolution_partial"] is True
    assert report.evidence["settlement_reserve_reached"] is bool(reserve_stop)
    assert report.evidence["healing_trips"] == (0 if reserve_stop else 2 + (trainee_hp != 40))
    assert report.actions_executed == (0 if reserve_stop else 1 if trainee_hp == 40 else 2)
    if reserve_stop:
        assert not calls
    else:
        assert calls[0]["allow_direct_evolution"] is True
    assert offer.binding.verify(report).status.value == "failed"
    assert (
        native.provider_for(GoalKind.EVOLVE_SPECIES, actions)
        .offer(native.adapter.observe())
        .binding
        is not None
    )


@pytest.mark.parametrize(
    "current_map,level,expected_maps",
    [(22, 35, [22]), (165, 35, [165]), (165, 32, [165]), (171, 35, [165])],
)
def test_native_quantum_keeps_only_an_eligible_current_venue(
    tmp_path, monkeypatch, current_map, level, expected_maps
):
    from types import SimpleNamespace

    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.red_team_training import EvolutionTrainingPaused

    runtime, reader, _ = runtime_fixture(tmp_path)
    source = red_internal_species_id(77)
    reader.raw = replace(
        reader.raw,
        map_id=current_map,
        party_species_ids=(*reader.raw.party_species_ids[:5], source),
        party_levels=(63, 55, 55, 55, 55, level),
    )
    reader.boxes = replace(
        reader.boxes,
        boxes=(RedCurrentBoxState(0, (source,), (30,)), *reader.boxes.boxes[1:]),
    )
    monkeypatch.setattr(module, "wild_tables", lambda rom: {22: [(10, 0x21)], 165: [(10, 0x21)]})
    received = []

    def train(*args, **kwargs):
        received.extend(venue.map_id for venue in kwargs["venues"])
        raise EvolutionTrainingPaused(4, 0)

    monkeypatch.setattr(module.context, "run_red_team_balancing", train)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    native.party_level_evolution_executor(
        source, red_internal_species_id(78), CountingExecutor(_ActionDelegate())
    )
    assert received == expected_maps


def test_registered_native_evolution_derives_and_forwards_level_helper_exclusions(
    tmp_path, monkeypatch
):
    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.red_team_training import EvolutionTrainingPaused

    runtime, reader, _ = runtime_fixture(tmp_path)
    source, target = red_internal_species_id(77), red_internal_species_id(78)
    reader.raw = replace(
        reader.raw, party_species_ids=(*reader.raw.party_species_ids[:5], source),
        party_levels=(63, 55, 55, 55, 55, 33),
    )
    registration = SimpleNamespace(
        evolution_allowed=lambda *args: True, sha256="a" * 64,
    )
    runtime = replace(runtime, registration_policy=registration)
    edges_read, calls = [], []

    def edges(rom):
        edges_read.append(rom)
        return frozenset({(source, target, 40), (150, 151, 36)})

    def train(*args, **kwargs):
        calls.append(kwargs)
        raise EvolutionTrainingPaused(4, 0)

    monkeypatch.setattr(module, "level_evolution_edges", edges)
    monkeypatch.setattr(module.context, "run_red_team_balancing", train)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"catalog-fixture"))
    report = native.party_level_evolution_executor(
        source, target, CountingExecutor(_ActionDelegate())
    )
    assert report.evidence["evolution_partial"] is True
    assert edges_read == [b"catalog-fixture"]
    assert calls[0]["evolution_target"] == (source, target)
    assert calls[0]["allow_direct_evolution"] is True
    assert calls[0]["excluded_collection_helper_species"] == frozenset({source, 150})


def test_low_level_recipient_can_share_experience_without_a_direct_fighting_venue(tmp_path):
    runtime, _, _ = runtime_fixture(tmp_path, source=11, target=12, evolution_level=10, level=4)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, CountingExecutor(_ActionDelegate())).offer(
        native.adapter.observe()
    )
    assert offer.binding is not None


@pytest.mark.parametrize("stop", ["quanta", "reserve", "wall", "long_wall", "no_progress"])
def test_extended_evolution_batch_keeps_progress_and_stop_guards(tmp_path, monkeypatch, stop):
    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.red_team_training import EvolutionTrainingPaused

    runtime, reader, _ = runtime_fixture(tmp_path)
    source = red_internal_species_id(77)
    reader.raw = replace(
        reader.raw,
        party_species_ids=(*reader.raw.party_species_ids[:5], source),
        party_levels=(63, 55, 55, 55, 55, 33),
    )
    reader.boxes = replace(
        reader.boxes,
        boxes=(RedCurrentBoxState(0, (source,), (30,)), *reader.boxes.boxes[1:]),
    )
    calls = []

    def train(*args, **kwargs):
        calls.append(kwargs)
        raise EvolutionTrainingPaused(4, 2)

    monkeypatch.setattr(module.context, "run_red_team_balancing", train)
    monkeypatch.setattr(module, "restore_native_center_party", lambda *args: 1)
    monkeypatch.setattr(module, "prepare_native_training_center", lambda *args: None)
    monkeypatch.setattr(
        module,
        "PokemonRedPartyReader",
        lambda _: SimpleNamespace(
            read=lambda: SimpleNamespace(
                members=(
                    SimpleNamespace(
                        species_id=source,
                        experience=100 if stop == "no_progress" else 100 + len(calls),
                    ),
                )
            ),
        ),
    )
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(
            monotonic=lambda: 1801 if stop == 'long_wall' and len(calls)>=140 else
                601 if stop in ('wall','long_wall') and len(calls)>=130 else 0,
        ),
    )
    runtime.evolution_stop_requested = lambda: stop == "reserve" and len(calls) >= 130
    native = bind_native_boxed_evolution(
        runtime,
        SimpleNamespace(rom=b"test"),
        maximum_quanta=129 if stop == "quanta" else 512,
        maximum_wall_seconds=1800 if stop=='long_wall' else 600,
    )
    actions = CountingExecutor(_ActionDelegate())
    if stop == "no_progress":
        with pytest.raises(module.context.RedGoalContextError, match="no verified XP progress"):
            native.party_level_evolution_executor(source, red_internal_species_id(78), actions)
        assert len(calls) == 1
    else:
        report = native.party_level_evolution_executor(
            source,
            red_internal_species_id(78),
            actions,
        )
        assert len(calls) == (129 if stop == "quanta" else 140 if stop=='long_wall' else 130)
        assert report.evidence["evolution_partial"] is True
        assert report.evidence["settlement_reserve_reached"] is (stop == "reserve")
        assert report.evidence["wall_limit_reached"] is (stop in ('wall','long_wall'))
        assert report.evidence["completed_training_battles"] == 4 * len(calls)
        assert report.evidence["healing_trips"] == 3 * len(calls)


def test_profile_transition_preserves_every_other_skill_and_rejects_wrong_evolution(tmp_path):
    runtime, _, original = runtime_fixture(tmp_path)
    assert [s for s in runtime.profile.providers if s.kind is not GoalKind.EVOLVE_SPECIES] == [
        s
        for s in original.providers
        if s.kind not in {GoalKind.EVOLVE_SPECIES, GoalKind.DEVELOP_TEAM}
    ]
    assert all(s.kind is not GoalKind.DEVELOP_TEAM for s in runtime.profile.providers)
    assert runtime.profile.profile_id == original.profile_id
    assert runtime.profile.profile_sha256 != original.profile_sha256
    with pytest.raises(Exception, match="canonical Red level evolution"):
        build_native_boxed_evolution_profile_payload(
            original, source_species=77, target_species=78, evolution_level=10
        )


def test_field_resource_check_keeps_real_position_and_does_not_advertise_local_skill(tmp_path):
    runtime, reader, _ = runtime_fixture(tmp_path)
    reader.raw = replace(reader.raw, map_id=MapId.POKEMON_MANSION_1F, player_x=5, player_y=22)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    provider = native.provider_for(GoalKind.EVOLVE_SPECIES, CountingExecutor(_ActionDelegate()))
    observed = native.adapter.observe()
    assert provider.resource_availability(observed).executable
    assert provider.offer(observed).unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert (reader.raw.player_x, reader.raw.player_y) == (5, 22)


def test_native_executor_refuses_consuming_only_precursor_before_any_input(tmp_path):
    from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest

    runtime, _, _ = runtime_fixture(tmp_path, count=1)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    actions = CountingExecutor(_ActionDelegate())
    request = RedBoxedLevelEvolutionGoalRequest(
        red_internal_species_id(77),
        red_internal_species_id(78),
        0,
        1,
        6,
        red_internal_species_id(106),
    )
    with pytest.raises(Exception, match="two retained precursors"):
        native.boxed_level_evolution_executor(request, actions)
    assert actions.actions_executed == 0


def test_profile_expansion_retains_nested_resource_declarations():
    # The real profile includes nested immutable purchase rows; no shallow copy.
    from pokemon_red_completion.observation import ItemId
    from pokemon_red_completion.red_goal_context_profile import (
        RedGoalMechanic,
        build_red_goal_context_profile_payload,
    )

    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="nested-native-profile",
            providers=(
                (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
                (GoalKind.DEVELOP_TEAM, RedGoalMechanic.BALANCED_TEAM, {}),
                (
                    GoalKind.RESUPPLY,
                    RedGoalMechanic.MART_RESUPPLY,
                    {
                        "map_id": int(MapId.VIRIDIAN_MART),
                        "player_x": 4,
                        "player_y": 2,
                        "interaction_direction": "up",
                        "purchases": [
                            {
                                "absolute_index": 0,
                                "item_id": int(ItemId.POKE_BALL),
                                "quantity": 10,
                                "unit_price": 200,
                            }
                        ],
                    },
                ),
            ),
        )
    )
    expanded = parse_red_goal_context_profile(
        build_native_boxed_evolution_profile_payload(
            profile,
            source_species=77,
            target_species=78,
            evolution_level=40,
        )
    )
    assert expanded.providers[-1] == profile.providers[-1]


@pytest.mark.parametrize("native_escort", [False, True])
def test_native_wiring_executes_existing_engine_with_same_budgets_and_observers(
    tmp_path, monkeypatch, native_escort,
):
    from types import SimpleNamespace

    from test_red_resource_goal_router import _World

    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
    from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest
    from pokemon_red_completion.route_executor import TraversalSnapshot

    runtime, _, _ = runtime_fixture(tmp_path)
    if native_escort:
        runtime.reader.raw = replace(runtime.reader.raw, party_species_ids=(
            179, *runtime.reader.raw.party_species_ids[1:],
        ))
    world = _World()
    world.rom = b"test"
    monkeypatch.setattr(
        module,
        "wild_tables",
        lambda rom: {
            int(MapId.ROUTE_11): [(10, 0x21)],
            int(MapId.DIGLETTS_CAVE): [(20, red_internal_species_id(50))],
        },
    )
    observed = TraversalSnapshot(int(MapId.CINNABAR_POKECENTER), (3, 3), True)
    monkeypatch.setattr(
        module, "Gen1TraversalObserver", lambda _: SimpleNamespace(observe=lambda: observed)
    )
    monkeypatch.setattr(
        module,
        "RedCenterRestoreGoalProvider",
        lambda *args: SimpleNamespace(offer=lambda _: SimpleNamespace(binding=None)),
    )
    received = []
    monkeypatch.setattr(module, "finish_center_dialogue", lambda actions, reader: None)

    def engine(**kwargs):
        received.append(kwargs)

        def execute(request, actions):
            runtime.reader.raw = replace(
                runtime.reader.raw,
                party_species_ids=(
                    *runtime.reader.raw.party_species_ids[:5],
                    request.precursor_internal_species_id,
                ),
                party_levels=(54, 55, 55, 55, 55, 32),
            )
            result = kwargs["train_evolution"](
                request.precursor_internal_species_id, request.evolved_internal_species_id
            )
            assert result.battles_completed == 1
            return GoalExecutionReport(0, 0, {"engine_completed": True})

        return execute

    training = []

    def train(*args, **kwargs):
        training.append((args, kwargs))
        return None, 1, 0

    monkeypatch.setattr(module, "RedGoalBoxedEvolutionExecutor", engine)
    monkeypatch.setattr(module.context, "run_red_team_balancing", train)
    native = bind_native_boxed_evolution(runtime, world)
    actions = CountingExecutor(_ActionDelegate())
    request = RedBoxedLevelEvolutionGoalRequest(
        red_internal_species_id(77),
        red_internal_species_id(78),
        0,
        1,
        6,
        red_internal_species_id(106),
    )
    report = native.boxed_level_evolution_executor(request, actions)
    assert report.evidence == {"engine_completed": True}
    assert received[0]["reader"] is runtime.reader
    bound_escort = received[0]["escort_internal_species_id"]
    assert bound_escort in runtime.reader.raw.party_species_ids
    assert (bound_escort == BLASTOISE_SPECIES_ID) is not native_escort
    assert received[0]["route_to_pc"].plan.terminal_at == (4, 13)
    assert received[0]["route_to_training"].plan.start_at == (4, 13)
    assert received[0]["route_to_training"].plan.terminal_at == (3, 3)
    assert training[0][0][0] is actions
    assert training[0][1]["policy"].max_battles == 32
    assert training[0][1]["policy"].max_steps == 2000
    assert training[0][1]["allow_direct_evolution"] is True
    assert training[0][1]["collection_shared_experience"] is True
    assert training[0][1]["collection_encounters"] == {
        22: [(10, 0x21)],
        197: [(20, 0x3B)],
    }
    assert training[0][1]["evolution_battle_quantum"] == 4
    assert callable(training[0][1]["decision_sink"])
    assert callable(training[0][1]["candidate_decision_sink"])
    assert callable(training[0][1]["execution_summary_sink"])
    assert callable(training[0][1]["move_decision_sink"])
    assert "decision_authority" not in training[0][1]
    assert "candidate_decision_authority" not in training[0][1]
    assert [v.map_id for v in training[0][1]["venues"]] == [MapId.ROUTE_11, MapId.DIGLETTS_CAVE]
    assert received[0]["pc_facing"] == "up"
    assert training[0][1]["evolution_target"] == (
        red_internal_species_id(77),
        red_internal_species_id(78),
    )
    assert received[0]["observe_collection"]() == runtime.adapter.observe().collection_observation


@pytest.mark.parametrize("location", [MapId.VERMILION_POKECENTER, MapId.CINNABAR_POKECENTER])
@pytest.mark.parametrize("prefer_highest", [False, True])
def test_stronger_venue_preference_preserves_executable_local_transport(
    tmp_path, monkeypatch, location, prefer_highest,
):
    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.red_team_training import EvolutionTrainingPaused

    runtime, reader, _ = runtime_fixture(tmp_path, count=1)
    source, target = red_internal_species_id(77), red_internal_species_id(78)
    reader.raw = replace(reader.raw, map_id=location,
        party_species_ids=(*reader.raw.party_species_ids[:5], source),
        party_levels=(54, 55, 55, 55, 55, 32))
    candidates = (module.context.ROUTE_11_TRAINING_VENUE,
                  module.context.DIGLETTS_CAVE_TRAINING_VENUE,
                  module.context.MANSION_TRAINING_VENUE)
    monkeypatch.setattr(module, "wild_tables",
                        lambda rom: {v.map_id: ((10, 0x21),) for v in candidates})
    monkeypatch.setattr(module, "restore_native_center_party", lambda *args: 0)
    received = []

    def train(*args, **kwargs):
        received.append(kwargs["venues"])
        raise EvolutionTrainingPaused(0, 0)

    monkeypatch.setattr(module.context, "run_red_team_balancing", train)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"),
        prefer_highest_supported_venue=prefer_highest)
    actions = CountingExecutor(_ActionDelegate())
    native.party_level_evolution_executor(source, target, actions)
    local = tuple(v for v in candidates if v.is_in_center(reader.raw))
    expected = ((max(local, key=lambda v: v.band.maximum_encounter_level),)
                if prefer_highest else local)
    assert tuple(v.map_id for v in received[0]) == tuple(v.map_id for v in expected)
    assert actions.actions_executed == runtime.emulator.frame_count == 0



@pytest.mark.parametrize("prior_quanta", [0, 1])
def test_safe_venue_exhaustion_settles_and_preserves_prior_work(tmp_path, monkeypatch, prior_quanta):
    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.actions import MacroAction, MacroActionKind
    from pokemon_red_completion.red_team_training import EvolutionTrainingPaused, EvolutionVenueExhausted

    runtime, reader, _ = runtime_fixture(tmp_path)
    source, target = red_internal_species_id(77), red_internal_species_id(78)
    reader.raw = replace(reader.raw, party_species_ids=(*reader.raw.party_species_ids[:5], source),
                         party_levels=(63, 55, 55, 55, 55, 33))
    reader.boxes = replace(reader.boxes,
        boxes=(RedCurrentBoxState(0, (source,), (30,)), *reader.boxes.boxes[1:]))
    calls, settlements = [], []
    settle = module.settle_native_evolution

    def train(actions, *args, **kwargs):
        calls.append(kwargs)
        actions.execute(MacroAction(MacroActionKind.WAIT))
        if len(calls) <= prior_quanta:
            raise EvolutionTrainingPaused(4, 2)
        raise EvolutionVenueExhausted(0, 2)

    def settle_once(*args):
        settlements.append(True)
        return settle(*args)

    monkeypatch.setattr(module.context, "run_red_team_balancing", train)
    monkeypatch.setattr(module, "prepare_native_training_center", lambda *a: None)
    monkeypatch.setattr(module, "restore_native_center_party", lambda *a: 1)
    monkeypatch.setattr(module, "settle_native_evolution", settle_once)
    monkeypatch.setattr(module, "PokemonRedPartyReader", lambda _: SimpleNamespace(
        read=lambda: SimpleNamespace(members=(SimpleNamespace(
            species_id=source, experience=100 + len(calls)),))))
    monkeypatch.setattr(module, "wild_tables", lambda _: {int(MapId.ROUTE_11): [(10, 0x21)]})
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"), maximum_quanta=128)
    actions = CountingExecutor(_ActionDelegate())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert offer.binding is not None
    report = offer.binding.execute()
    assert len(calls) == prior_quanta + 1
    assert settlements == [True]
    assert report.actions_executed == actions.actions_executed == prior_quanta + 1
    assert report.evidence["evolution_partial"] is True
    assert report.evidence["training_venue_exhausted"] is True
    assert report.evidence["no_verified_win_in_quantum"] is True
    assert report.evidence["no_verified_win"] is (prior_quanta == 0)
    assert report.evidence["completed_training_battles"] == 4 * prior_quanta
    assert report.evidence["healing_trips"] == 3 * (prior_quanta + 1)
    assert report.evidence["settlement_reserve_reached"] is False
    assert offer.binding.verify(report).status.value == "failed"
    assert reader.raw.battle_state == 0 and reader.read_input_readiness().ready



@pytest.mark.parametrize("in_party", [False, True])
@pytest.mark.parametrize("transport_answer", [False, True, 1, "ready"])
def test_native_transport_quotes_exact_retained_party_before_any_input(
    tmp_path, monkeypatch, in_party, transport_answer,
):
    import pokemon_red_completion.red_native_boxed_evolution as module
    runtime, reader, _ = runtime_fixture(tmp_path)
    source = red_internal_species_id(77)
    if in_party:
        reader.raw = replace(reader.raw,
            party_species_ids=(*reader.raw.party_species_ids[:5], source),
            party_levels=(63, 55, 55, 55, 55, 33))
        reader.boxes = replace(reader.boxes,
            boxes=(RedCurrentBoxState(0, (source,), (30,)), *reader.boxes.boxes[1:]))
    observed = []
    def quote(party):
        observed.append(party)
        return transport_answer
    venue = replace(module.context.MANSION_TRAINING_VENUE, native_transport_ready=quote)
    monkeypatch.setattr(module, "wild_tables", lambda _: {venue.map_id: [(30, 0x21)]})
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"), training_venues=(venue,))
    actions = CountingExecutor(_ActionDelegate())
    before = native.adapter.observe()
    expected = before.party
    if not in_party:
        spec = next(s for s in native.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)
        request = module.context._RedTeamGoalProvider(native, spec, actions)._boxed_evolution_request(before)
        expected = replace(expected, members=tuple(
            replace(m,slot=i+1) for i,m in enumerate(
                m for m in expected.members if m.slot != request.deposit_party_slot)))
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(before)
    assert observed and all(p == expected for p in observed)
    assert expected.size == (6 if in_party else 5)
    assert (offer.binding is not None) is (transport_answer is True)
    assert actions.actions_executed == 0 and runtime.emulator.frame_count == 0


@pytest.mark.parametrize("invalid", [False, True, 1, "route"])
def test_native_transport_probe_must_be_a_callable_before_admission(invalid):
    from pokemon_red_completion.red_goal_context import MANSION_TRAINING_VENUE
    with pytest.raises(TypeError, match="native_transport_ready"):
        replace(MANSION_TRAINING_VENUE, native_transport_ready=invalid)


@pytest.mark.parametrize("remote_ready", [False,True])
@pytest.mark.parametrize("local_peer", [False,True])
def test_model_venue_inventory_checks_transport_before_offering(tmp_path,monkeypatch,remote_ready,local_peer):
    import pokemon_red_completion.red_native_boxed_evolution as module
    runtime,reader,_=runtime_fixture(tmp_path,count=1)
    reader.raw=replace(reader.raw,map_id=MapId.VERMILION_POKECENTER,player_x=3,player_y=3,
        party_species_ids=(*reader.raw.party_species_ids[:5],red_internal_species_id(77)))
    mansion=module.context.MANSION_TRAINING_VENUE
    venues=(mansion,module.context.ROUTE_11_TRAINING_VENUE) if local_peer else(mansion,)
    monkeypatch.setattr(module,"validate_native_evolution_venue_model",lambda *a:None)
    monkeypatch.setattr(module,"wild_tables",lambda _: {v.map_id:((10,165),)for v in venues})
    monkeypatch.setattr(module,"collection_finisher",lambda *a,**k:object())
    monkeypatch.setattr(module,"native_evolution_encounter_supported",lambda *a,**k:True)
    probes=[]
    monkeypatch.setattr(module,"_mansion_transport_ready",lambda rt,world,party:probes.append(party)or remote_ready)
    native=bind_native_boxed_evolution(runtime,SimpleNamespace(rom=b"test"),training_venues=venues,
        venue_model=object(),venue_model_sha256="a"*64)
    actions=CountingExecutor(_ActionDelegate());before=reader.raw
    offered=native.provider_for(GoalKind.EVOLVE_SPECIES,actions).offer(native.adapter.observe())
    assert (offered.binding is not None)==(remote_ready or local_peer)
    assert probes and actions.actions_executed==0 and reader.raw==before
