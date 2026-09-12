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
