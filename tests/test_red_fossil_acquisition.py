from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.observation import (
    EVENT_FLAG_BYTES,
    CurrentMapObject,
    EventFlag,
    ItemId,
    MapId,
    RawGameState,
    RedCurrentBoxState,
    RedPokedexState,
    SemanticStateError,
)
from pokemon_red_completion.red_fossil_acquisition import (
    RED_FOSSIL_TARGETS,
    RedFossilAcquisitionError,
    RedFossilExecution,
    RedFossilGoalProvider,
    RedFossilPhase,
    RedFossilTiming,
    RedRoutedFossilRevival,
    available_red_fossil_targets,
    bind_available_fossil_acquisition,
    fossil_target_by_item,
    observe_red_fossil,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def _events(*flags: EventFlag) -> bytes:
    result = bytearray(EVENT_FLAG_BYTES)
    for flag in flags:
        result[int(flag) // 8] |= 1 << (int(flag) % 8)
    return bytes(result)


def _raw(*, events: bytes | None = None, item: ItemId | None = ItemId.HELIX_FOSSIL):
    bag = () if item is None else ((int(item), 1),)
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_11,
        player_x=0,
        player_y=6,
        party_count=6,
        battle_state=0,
        bag_item_ids=tuple(row[0] for row in bag),
        bag_items=bag,
        event_flags=_events() if events is None else events,
        party_species_ids=(1, 2, 3, 4, 5, 6),
    )


class _Reader:
    def __init__(self) -> None:
        self.raw = _raw()
        self.owned = frozenset[int]()
        self.box = RedCurrentBoxState(0, (7, 8), (10, 11))
        self.pending = (0, 0)
        self.reads = 0
        self.facing = "up"
        self.objects = (
            CurrentMapObject(1, 0x20, (2, 5), 1, 24),
            CurrentMapObject(2, 0x20, (6, 7), 2, 20),
        )

    def read(self) -> RawGameState:
        self.reads += 1
        return self.raw

    def read_pokedex_state(self) -> RedPokedexState:
        return RedPokedexState(self.owned, self.owned)

    def read_current_box_state(self) -> RedCurrentBoxState:
        return self.box

    def read_fossil_reviver_identity(self) -> tuple[int, int]:
        return self.pending

    def read_input_readiness(self):
        return SimpleNamespace(ready=True)

    def read_bottom_dialogue_box_visible(self) -> bool:
        return False

    def read_player_facing(self) -> str:
        return self.facing

    def read_current_map_objects(self) -> tuple[CurrentMapObject, ...]:
        return self.objects


def test_fossil_constants_match_pinned_cartridge_layout() -> None:
    assert MapId.CINNABAR_LAB == 0xA7
    assert MapId.CINNABAR_LAB_FOSSIL_ROOM == 0xAA
    assert EventFlag.GAVE_FOSSIL_TO_LAB == 0x2E0
    assert EventFlag.LAB_STILL_REVIVING_FOSSIL == 0x2E1
    assert EventFlag.LAB_HANDING_OVER_FOSSIL_MON == 0x2E2
    assert ItemId.OLD_AMBER == 0x1F
    assert tuple(target.national_dex_number for target in RED_FOSSIL_TARGETS) == (140, 138, 142)


@pytest.mark.parametrize("map_id", [MapId.CINNABAR_POKECENTER, MapId.CINNABAR_MART,
                                    MapId.CINNABAR_LAB_TRADE_ROOM])
def test_local_cinnabar_indoor_service_needs_no_fly_or_teleport(map_id):
    executor = RedRoutedFossilRevival(None, _Reader(), None, None)
    observer = SimpleNamespace(observe=lambda: SimpleNamespace(map_id=int(map_id)))
    assert executor._reach_cinnabar(None, observer) is False


@pytest.mark.parametrize("fault", [None, "remote", "no_item", "unreachable",
                                    "unsupported", "stale"])
def test_fossil_menu_quotes_real_local_route_without_inputs(monkeypatch, fault):
    from pokemon_red_completion import red_fossil_acquisition as module

    reader = _Reader()
    reader.raw = replace(reader.raw, map_id=int(
        MapId.ROUTE_11 if fault == "remote" else MapId.CINNABAR_POKECENTER))
    if fault == "no_item":
        reader.raw = replace(reader.raw, bag_items=(), bag_item_ids=())
    observation = SimpleNamespace(raw=reader.raw, collection_observation=SimpleNamespace(
        owned_species=frozenset(), specimens=()))
    observed = object() if fault == "stale" else observation
    state = [b"source"]
    emulator = SimpleNamespace(frame_count=0, save_state_bytes=lambda: state[0])
    actions = SimpleNamespace(actions_executed=0)
    runtime = SimpleNamespace(reader=reader, emulator=emulator,
                              adapter=SimpleNamespace(observe=lambda: observed))
    calls = []

    def quote(start, destination):
        calls.append(destination)
        if fault == "unreachable":
            raise RoutePlanningError("unavailable")
        return SimpleNamespace(cost=30)

    world = SimpleNamespace(plan_feasible_to_map=quote)
    world.with_current_observation = lambda r: world
    monkeypatch.setattr("pokemon_red_completion.red_player_field_goals._field_ready",
                        lambda r: True)
    monkeypatch.setattr(module.RedRoutedFossilRevival, "_ports",
                        lambda e: (None, SimpleNamespace(observe=lambda: object())))
    monkeypatch.setattr(module, "_supported_plan", lambda *a, **kw: fault != "unsupported")
    if fault == "stale":
        with pytest.raises(ValueError, match="stale"):
            module.fossil_acquisition_bindings(runtime, observation, actions, world)
    else:
        rows = module.fossil_acquisition_bindings(runtime, observation, actions, world)
        assert len(rows) == (1 if fault is None else 0)
        if rows:
            assert rows[0].kind is GoalKind.ACQUIRE_SPECIES
            assert rows[0].search_source_ref == RED_FOSSIL_TARGETS[1].source_ref
            state[0] = b"changed"
            with pytest.raises(RedFossilAcquisitionError, match="stale or consumed"):
                rows[0].execute()
            assert rows[0].verify(GoalExecutionReport(1, 1, {})).status.value == "failed"
    assert calls == ([] if fault in ("remote", "no_item", "stale") else [int(
        MapId.CINNABAR_LAB_FOSSIL_ROOM)])
    assert actions.actions_executed == emulator.frame_count == 0


def test_inventory_derives_one_generic_ready_target_without_input() -> None:
    reader = _Reader()
    reads = reader.reads

    targets = available_red_fossil_targets(reader)

    assert tuple(target.item_id for target in targets) == (ItemId.HELIX_FOSSIL,)
    assert targets[0].national_dex_number == 138
    assert reader.reads > reads
    assert reader.raw == _raw()


def test_fossil_phase_is_recoverable_across_leave_and_return() -> None:
    reader = _Reader()
    target = fossil_target_by_item(int(ItemId.HELIX_FOSSIL))
    reader.pending = (int(target.item_id), target.internal_species_id)
    reader.raw = _raw(
        events=_events(
            EventFlag.GAVE_FOSSIL_TO_LAB,
            EventFlag.LAB_STILL_REVIVING_FOSSIL,
        ),
        item=None,
    )
    assert observe_red_fossil(reader, target).phase is RedFossilPhase.WAITING_FOR_OUTSIDE

    reader.raw = replace(
        reader.raw,
        event_flags=_events(EventFlag.GAVE_FOSSIL_TO_LAB),
    )
    assert observe_red_fossil(reader, target).phase is RedFossilPhase.READY_TO_COLLECT

    reader.owned = frozenset({138})
    reader.raw = replace(reader.raw, event_flags=_events())
    completed = observe_red_fossil(reader, target)
    assert completed.phase is RedFossilPhase.COMPLETE
    assert not completed.executable


def test_fossil_target_fails_closed_on_ambiguous_inventory_or_storage() -> None:
    reader = _Reader()
    reader.raw = replace(
        reader.raw,
        bag_items=((int(ItemId.HELIX_FOSSIL), 1), (int(ItemId.OLD_AMBER), 1)),
    )
    assert available_red_fossil_targets(reader) == ()

    reader.raw = _raw()
    reader.box = RedCurrentBoxState(0, tuple(range(1, 21)), (10,) * 20)
    assert available_red_fossil_targets(reader) == ()


def test_fossil_target_rejects_unknown_item() -> None:
    with pytest.raises(RedFossilAcquisitionError, match="unsupported fossil"):
        fossil_target_by_item(0xFF)


def _available_binding(kind: GoalKind, name: str) -> ExecutableGoalBinding:
    report = GoalExecutionReport(1, 1, {})
    return ExecutableGoalBinding(
        name,
        kind,
        0.2,
        0.1,
        lambda: report,
        lambda _report: GoalVerification.succeeded(),
    )


def test_fossil_binding_replaces_only_a_masked_high_level_acquisition_slot() -> None:
    story = _available_binding(GoalKind.ADVANCE_STORY, "story")
    masked = GoalOpportunity(
        "capture",
        GoalKind.ACQUIRE_SPECIES,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
    )
    original = GoalBindingSet((story.opportunity, masked), (story,))
    fossil = _available_binding(GoalKind.ACQUIRE_SPECIES, "fossil")

    updated = bind_available_fossil_acquisition(original, fossil)

    assert updated.opportunities == (story.opportunity, fossil.opportunity)
    assert updated.bindings == (story, fossil)

    capture = _available_binding(GoalKind.ACQUIRE_SPECIES, "wild")
    available = GoalBindingSet((story.opportunity, capture.opportunity), (story, capture))
    assert bind_available_fossil_acquisition(available, fossil) is available


@pytest.mark.parametrize("allowed,fault", [(False, None), (True, None), (True, "primitive")])
def test_fossil_reuses_opted_in_native_escape_before_fly_with_all_costs(
    monkeypatch, allowed, fault,
):
    from pokemon_red_completion import red_fossil_acquisition as module
    from pokemon_red_completion.actions import MacroAction, MacroActionKind
    from pokemon_red_completion.executor import CountingExecutor
    from pokemon_red_completion.red_dig_recovery import DigEscapePlan, RedDigRecoveryError
    from pokemon_red_completion.route_executor import TraversalSnapshot

    reader = _Reader()
    reader.raw = replace(reader.raw, map_id=int(MapId.POKEMON_MANSION_B1F))
    em = SimpleNamespace(frame_count=0)
    calls = []

    def dispatch(action):
        em.frame_count += action.repeat

    actions = CountingExecutor(SimpleNamespace(execute=dispatch))
    observer = SimpleNamespace(observe=lambda: TraversalSnapshot(
        reader.raw.map_id, (reader.raw.player_y, reader.raw.player_x), True, mode="land",
    ))
    escape = DigEscapePlan(int(MapId.POKEMON_MANSION_B1F), (6, 0), 5, (4, 11), 0, 22)

    def quote(*args):
        calls.append("quote")
        return escape

    def dig(world, port, emulator, controller, quoted):
        assert quoted is escape and port is reader and controller is actions
        calls.append("dig")
        controller.execute(MacroAction(MacroActionKind.WAIT, repeat=7))
        if fault:
            raise RedDigRecoveryError("native escape resource mismatch")
        reader.raw = replace(reader.raw, map_id=5, player_y=4, player_x=11)
        return {"verified_escape": True}

    def reach(self, field_actions, traversal):
        assert field_actions is actions and traversal is observer
        assert reader.raw.map_id == (5 if allowed else int(MapId.POKEMON_MANSION_B1F))
        calls.append("fly")
        field_actions.execute(MacroAction(MacroActionKind.WAIT, repeat=7))
        reader.raw = replace(reader.raw, map_id=int(MapId.CINNABAR_ISLAND))
        return allowed

    target = fossil_target_by_item(int(ItemId.HELIX_FOSSIL))

    def route(self, field_actions, traversal, destination_map, **kwargs):
        calls.append("lab")
        field_actions.execute(MacroAction(MacroActionKind.WAIT, repeat=7))
        reader.raw = replace(reader.raw, map_id=destination_map, bag_items=(), bag_item_ids=())
        reader.owned = frozenset({target.national_dex_number})
        reader.box = RedCurrentBoxState(0, (*reader.box.species_ids, target.internal_species_id),
                                       (*reader.box.levels, 30))
        return 1

    monkeypatch.setattr(module, "plan_dig_escape", quote)
    monkeypatch.setattr(module, "execute_dig_escape", dig)
    monkeypatch.setattr(RedRoutedFossilRevival, "_ports", lambda self: (actions, observer))
    monkeypatch.setattr(RedRoutedFossilRevival, "_reach_cinnabar", reach)
    monkeypatch.setattr(RedRoutedFossilRevival, "_route", route)
    executor = RedRoutedFossilRevival(actions, reader, em, SimpleNamespace(),
                                     allow_dig_departure=allowed)
    if fault:
        with pytest.raises(RedDigRecoveryError, match="resource mismatch"):
            executor.execute(target)
        assert calls == ["quote", "dig"] and actions.actions_executed == 1
        return
    report = executor.execute(target)
    assert report.passed and report.dig_escape_used is allowed
    assert calls == (["quote", "dig"] if allowed else []) + ["fly", "lab"]
    assert report.actions_executed == actions.actions_executed == 2 + int(allowed)
    assert report.frames_executed == em.frame_count == 7 * report.actions_executed
    assert report.public_dict().get("dig_escape_used", False) is allowed


@pytest.mark.parametrize("flag", [1, "yes", None])
def test_fossil_native_escape_requires_boolean_opt_in(flag):
    with pytest.raises(ValueError, match="boolean permission"):
        RedRoutedFossilRevival(None, None, None, None, allow_dig_departure=flag)


def test_fossil_provider_verifies_new_registration_and_retained_specimen() -> None:
    reader = _Reader()
    target = fossil_target_by_item(int(ItemId.HELIX_FOSSIL))
    before_collection = SimpleNamespace(owned_species=frozenset(), specimens=())
    before = SimpleNamespace(collection_observation=before_collection)

    class Adapter:
        def observe(self):
            specimen = SimpleNamespace(species_ref=target.species_ref)
            return SimpleNamespace(
                collection_observation=SimpleNamespace(
                    owned_species=frozenset({target.species_ref}),
                    specimens=(specimen,),
                ),
                raw=reader.raw,
                input_ready=True,
            )

    class Executor:
        def execute(self, selected):
            initial = observe_red_fossil(reader, selected)
            reader.raw = _raw(item=None)
            reader.owned = frozenset({selected.national_dex_number})
            reader.box = RedCurrentBoxState(
                0,
                (*reader.box.species_ids, selected.internal_species_id),
                (*reader.box.levels, 30),
            )
            final = observe_red_fossil(reader, selected)
            return RedFossilExecution(selected, initial, final, 5, 500, True, 32, 48)

    binding = RedFossilGoalProvider(
        target,
        Adapter(),  # type: ignore[arg-type]
        reader,
        Executor(),  # type: ignore[arg-type]
    ).binding(before)  # type: ignore[arg-type]
    assert binding is not None

    report = binding.execute()
    verdict = binding.verify(report)

    assert verdict.status.value == "succeeded"
    assert report.evidence["national_dex_number"] == 138
    assert report.evidence["species_specific_route_steps"] == 0


def test_fossil_interaction_replans_to_roaming_scientists_live_position(
    monkeypatch,
) -> None:
    reader = _Reader()
    reader.raw = replace(
        reader.raw,
        map_id=MapId.CINNABAR_LAB_FOSSIL_ROOM,
        player_y=3,
        player_x=5,
    )
    # This is the exact live race caught by CB: the scientist moved right,
    # leaving the formerly blocked (2, 5) square open.
    reader.objects = (
        CurrentMapObject(1, 0x20, (2, 6), 1, 24),
        CurrentMapObject(2, 0x20, (6, 7), 2, 20),
    )

    class Actions:
        actions_executed = 0

        def execute(self, action):
            pytest.fail(f"should route before sending a facing input: {action}")

    routed = []

    def approach(self, _actions, _observer, scientist_at):
        routed.append(scientist_at)
        reader.raw = replace(reader.raw, player_x=6)
        return 1

    monkeypatch.setattr(RedRoutedFossilRevival, "_route_to_scientist", approach)
    executor = RedRoutedFossilRevival(
        Actions(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        SimpleNamespace(frame_count=0),
        SimpleNamespace(),  # type: ignore[arg-type]
    )

    assert executor._position_and_face_scientist(  # noqa: SLF001
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
    ) == 1
    assert routed == [(2, 6)]
    assert (reader.raw.player_y, reader.raw.player_x) == (3, 6)


def test_fossil_facing_does_not_wait_before_the_interaction_boundary() -> None:
    reader = _Reader()
    reader.raw = replace(
        reader.raw,
        map_id=MapId.CINNABAR_LAB_FOSSIL_ROOM,
        player_y=2,
        player_x=5,
    )
    reader.facing = "up"
    reader.objects = (
        CurrentMapObject(1, 0x20, (2, 6), 1, 24),
        CurrentMapObject(2, 0x20, (6, 7), 2, 20),
    )

    class Actions:
        actions_executed = 0

        def __init__(self) -> None:
            self.actions = []

        def execute(self, action):
            self.actions.append(action)
            if action.kind is MacroActionKind.MOVE:
                reader.facing = str(action.value)

    actions = Actions()
    executor = RedRoutedFossilRevival(
        actions,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        SimpleNamespace(frame_count=0),
        SimpleNamespace(),  # type: ignore[arg-type]
    )

    assert executor._position_and_face_scientist(  # noqa: SLF001
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
    ) == 0
    assert [(action.kind, action.value) for action in actions.actions] == [
        (MacroActionKind.MOVE, "right")
    ]


def test_fossil_interaction_polls_when_scientist_is_behind_counter(
    monkeypatch,
) -> None:
    reader = _Reader()
    reader.raw = replace(
        reader.raw,
        map_id=MapId.CINNABAR_LAB_FOSSIL_ROOM,
        player_y=2,
        player_x=5,
    )
    reader.facing = "right"
    reader.objects = (
        CurrentMapObject(1, 0x20, (2, 7), 1, 24),
        CurrentMapObject(2, 0x20, (6, 7), 2, 20),
    )

    class Actions:
        actions_executed = 0

        def __init__(self) -> None:
            self.actions = []

        def execute(self, action):
            self.actions.append(action)
            assert action.kind is MacroActionKind.WAIT
            reader.objects = (
                CurrentMapObject(1, 0x20, (2, 6), 1, 24),
                CurrentMapObject(2, 0x20, (6, 7), 2, 20),
            )

    actions = Actions()
    timing = RedFossilTiming(npc_poll_frames=24)
    executor = RedRoutedFossilRevival(
        actions,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        SimpleNamespace(frame_count=0),
        SimpleNamespace(),  # type: ignore[arg-type]
        timing=timing,
    )
    monkeypatch.setattr(
        RedRoutedFossilRevival,
        "_route_to_scientist",
        lambda *_args: None,
    )

    assert executor._position_and_face_scientist(  # noqa: SLF001
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
    ) == 0
    assert len(actions.actions) == 1
    assert actions.actions[0].repeat == 24


def test_fossil_route_recovers_one_verified_transient_off_graph_square() -> None:
    state = [TraversalSnapshot(170, (2, 5), True)]

    class Observer:
        def observe(self):
            return state[0]

    class World:
        def plan_feasible_to_map(self, start, _destination_map, *, goal_at=None):
            assert goal_at is None
            if start.at == (3, 5):
                return SimpleNamespace(cost=23, steps=())
            raise RoutePlanningError("off graph")

    class Actions:
        actions_executed = 0

        def __init__(self) -> None:
            self.actions = []

        def execute(self, action):
            self.actions.append(action)
            assert action.kind is MacroActionKind.MOVE
            assert action.value == "down"
            state[0] = replace(state[0], at=(3, 5))

    actions = Actions()
    executor = RedRoutedFossilRevival(
        actions,  # type: ignore[arg-type]
        _Reader(),  # type: ignore[arg-type]
        SimpleNamespace(frame_count=0),
        World(),  # type: ignore[arg-type]
    )

    executor._recover_to_routable_neighbor(  # noqa: SLF001
        actions,  # type: ignore[arg-type]
        Observer(),  # type: ignore[arg-type]
        8,
        goal_at=None,
        original_error=RoutePlanningError("off graph"),
    )

    assert state[0].at == (3, 5)
    assert [(action.kind, action.value) for action in actions.actions] == [
        (MacroActionKind.MOVE, "down")
    ]


@pytest.mark.parametrize("method", ["transport", "scientist"])
@pytest.mark.parametrize("already_fainted", [False, True])
def test_fossil_routes_wire_existing_guarded_flees_without_trainer_authority(
    monkeypatch, method, already_fainted,
) -> None:
    from pokemon_red_completion import red_fossil_acquisition as module
    from pokemon_red_completion.red_resource_goal_router import _MAX_ROUTE_FLEES, _ROUTE_LIMITS
    from pokemon_red_completion.red_routed_recovery import RedRoutedRecoveryError

    reader = _Reader()
    reader.raw = replace(reader.raw, party_count=3, party_species_ids=(1, 2, 3),
                         party_hp=(0 if already_fainted else 30, 40, 50))
    snapshot = TraversalSnapshot(int(MapId.POKEMON_MANSION_B1F), (17, 10), True)
    plan = SimpleNamespace(cost=1, steps=(object(),))
    world = SimpleNamespace(plan_feasible_to_map=lambda *a, **k: plan,
                            replanner=lambda: None)
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=0)
    executor = RedRoutedFossilRevival(actions, reader, emulator, world,
                                     route_limits=_ROUTE_LIMITS)
    seen = []

    def execute(quoted, route_actions, observer, **kwargs):
        assert quoted is plan and route_actions is actions
        assert kwargs["limits"] is _ROUTE_LIMITS
        handler = kwargs["interruption_handler"]
        assert handler.maximum_flees == _MAX_ROUTE_FLEES
        assert handler.maximum_trainer_battles == handler.maximum_scripted_dialogues == 0
        assert handler.post_prep_species == (1, 2, 3)
        assert handler.post_prep_living_slots == ((1, 2) if already_fainted else (0, 1, 2))
        assert handler.inner.maximum_trainer_battles == 0
        handler._require_preserved_living_slots(reader.raw)
        with pytest.raises(RedRoutedRecoveryError, match="slot 1 fainted"):
            handler._require_preserved_living_slots(replace(reader.raw, party_hp=(30, 0, 50)))
        seen.append(handler)
        return SimpleNamespace(passed=True, executed_steps=(object(),))

    monkeypatch.setattr(module, "execute_route", execute)
    monkeypatch.setattr(module, "_supported_plan", lambda *a, **k: True)
    observer = SimpleNamespace(observe=lambda: snapshot)
    if method == "transport":
        assert executor._route(actions, observer, module.FOSSIL_ROOM_MAP_ID) == 1
    else:
        assert executor._route_to_scientist(actions, observer, (3, 5)) == 1
    assert len(seen) == 1
    assert actions.actions_executed == emulator.frame_count == 0


def test_fossil_scientist_remains_routable_outside_the_viewport() -> None:
    reader = _Reader()
    reader.objects = (
        CurrentMapObject(1, 0x20, (2, 5), 1, 0xFF),
        CurrentMapObject(2, 0x20, (6, 7), 2, 20),
    )
    executor = RedRoutedFossilRevival(
        SimpleNamespace(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        SimpleNamespace(frame_count=0),
        SimpleNamespace(),  # type: ignore[arg-type]
    )

    scientist = executor._scientist()  # noqa: SLF001

    assert scientist.at == (2, 5)
    assert not scientist.visible


def test_fossil_dialogue_settles_before_observing_box_state() -> None:
    target = fossil_target_by_item(int(ItemId.HELIX_FOSSIL))

    class TransitionalReader(_Reader):
        def __init__(self) -> None:
            super().__init__()
            self.dialogue = False
            self.nickname_prompt = False
            self.raw = replace(
                self.raw,
                map_id=MapId.CINNABAR_LAB_FOSSIL_ROOM,
                player_y=3,
                player_x=5,
            )

        def read_bottom_dialogue_box_visible(self) -> bool:
            return self.dialogue

        def read_current_box_state(self) -> RedCurrentBoxState:
            if self.dialogue:
                raise SemanticStateError("box insertion is still in progress")
            return super().read_current_box_state()

    reader = TransitionalReader()

    class Actions:
        def __init__(self) -> None:
            self.actions_executed = 0
            self.actions = []

        def execute(self, action):
            self.actions_executed += 1
            self.actions.append(action)
            if action.kind is MacroActionKind.INTERACT:
                reader.dialogue = True
            elif action.kind is MacroActionKind.CONFIRM and not reader.nickname_prompt:
                # GivePokemon sets the owned bit before SendNewMonToBox asks
                # for a nickname.  Its box structures are not consistent yet.
                reader.owned = frozenset({target.national_dex_number})
                reader.nickname_prompt = True
            elif action.kind is MacroActionKind.CANCEL and reader.nickname_prompt:
                reader.dialogue = False
                reader.nickname_prompt = False
                reader.raw = replace(reader.raw, bag_items=(), bag_item_ids=())
                reader.box = RedCurrentBoxState(
                    reader.box.box_index,
                    (*reader.box.species_ids, target.internal_species_id),
                    (*reader.box.levels, 30),
                )

    actions = Actions()
    executor = RedRoutedFossilRevival(
        actions,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        SimpleNamespace(frame_count=0),
        SimpleNamespace(),  # type: ignore[arg-type]
    )

    route_steps = executor._advance_scientist_until(  # noqa: SLF001
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        target,
        RedFossilPhase.COMPLETE,
    )

    assert route_steps == 0
    assert [action.kind for action in actions.actions] == [
        MacroActionKind.INTERACT,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CANCEL,
        MacroActionKind.WAIT,
    ]
