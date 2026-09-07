from dataclasses import replace

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
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID


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
    native = bind_native_boxed_evolution(runtime, object())
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
    native = bind_native_boxed_evolution(runtime, object())
    actions = CountingExecutor(_ActionDelegate())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert (offer.binding is not None) is available
    if not available:
        assert offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert actions.actions_executed == 0


def test_native_execution_rechecks_escort_before_any_input(tmp_path):
    from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest

    runtime, reader, _ = runtime_fixture(tmp_path)
    native = bind_native_boxed_evolution(runtime, object())
    reader.raw = replace(
        reader.raw,
        party_species_ids=(red_internal_species_id(16), *reader.raw.party_species_ids[1:]),
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
def test_partial_evolution_resumes_in_party_without_repeating_storage(
    tmp_path, monkeypatch, trainee_hp
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
        calls.append(kwargs)
        actions.execute(MacroAction(MacroActionKind.WAIT))
        raise EvolutionTrainingPaused(4, 0)

    monkeypatch.setattr(module.context, "run_red_team_balancing", train)
    monkeypatch.setattr(
        module,
        "RedGoalBoxedEvolutionExecutor",
        lambda **kwargs: pytest.fail("resume must not repeat storage"),
    )
    monkeypatch.setattr(module, "wild_tables", lambda rom: {int(MapId.ROUTE_11): [(10, 0x21)]})
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"))
    actions = CountingExecutor(_ActionDelegate())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert offer.binding is not None
    report = offer.binding.execute()
    assert report.evidence["evolution_partial"] is True
    assert report.actions_executed == 1
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
    [(22, 35, [22]), (165, 35, [165]), (165, 32, [22, 165]), (171, 35, [22, 165])],
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


def test_unimplemented_low_level_venue_does_not_become_an_evolution_offer(tmp_path):
    runtime, _, _ = runtime_fixture(tmp_path, source=11, target=12, evolution_level=10, level=4)
    native = bind_native_boxed_evolution(runtime, object())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, CountingExecutor(_ActionDelegate())).offer(
        native.adapter.observe()
    )
    assert offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY


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
    native = bind_native_boxed_evolution(runtime, object())
    provider = native.provider_for(GoalKind.EVOLVE_SPECIES, CountingExecutor(_ActionDelegate()))
    observed = native.adapter.observe()
    assert provider.resource_availability(observed).executable
    assert provider.offer(observed).unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert (reader.raw.player_x, reader.raw.player_y) == (5, 22)


def test_native_executor_refuses_consuming_only_precursor_before_any_input(tmp_path):
    from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest

    runtime, _, _ = runtime_fixture(tmp_path, count=1)
    native = bind_native_boxed_evolution(runtime, object())
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


def test_native_wiring_executes_existing_engine_with_same_budgets_and_observers(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from test_red_resource_goal_router import _World

    import pokemon_red_completion.red_native_boxed_evolution as module
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
    from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest
    from pokemon_red_completion.route_executor import TraversalSnapshot

    runtime, _, _ = runtime_fixture(tmp_path)
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
    assert received[0]["route_to_pc"].plan.terminal_at == (4, 13)
    assert received[0]["route_to_training"].plan.start_at == (4, 13)
    assert received[0]["route_to_training"].plan.terminal_at == (3, 3)
    assert training[0][0][0] is actions
    assert training[0][1]["policy"].max_battles == 32
    assert training[0][1]["policy"].max_steps == 2000
    assert training[0][1]["allow_direct_evolution"] is True
    assert training[0][1]["evolution_battle_quantum"] == 4
    assert [v.map_id for v in training[0][1]["venues"]] == [MapId.ROUTE_11]
    assert received[0]["pc_facing"] == "up"
    assert training[0][1]["evolution_target"] == (
        red_internal_species_id(77),
        red_internal_species_id(78),
    )
    assert received[0]["observe_collection"]() == runtime.adapter.observe().collection_observation
