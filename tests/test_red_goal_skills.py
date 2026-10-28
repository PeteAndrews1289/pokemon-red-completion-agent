from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MapId,
    RamAddress,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist
from pokemon_red_completion.red_acquisition import (
    RedAreaExecutionError,
    RedAreaExecutionPolicy,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_collection import (
    red_collection_observation,
    red_internal_species_number,
    red_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_manager import PokemonRedGoalStateAdapter
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedBoxSwitchGoalProvider,
    RedCenterRestoreGoalProvider,
    RedControlRecoveryGoalProvider,
    RedEncounterDiscoveryGoalProvider,
    RedEncounterSourceDevelopmentGoalProvider,
    RedFieldRestoreGoalProvider,
    RedGoalSkillAvailability,
    RedGoalSkillError,
    RedMartPurchase,
    RedMartResupplyGoalProvider,
    RedProgressGoalProvider,
    RedRouteGoalProvider,
    finish_center_dialogue,
)
from pokemon_red_completion.red_party import party_observation_from_raw
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan


def _graph() -> QuestGraph:
    return QuestGraph(
        (
            Objective(
                "first",
                "First",
                frozenset({"story:first"}),
                Specialist.INTERACTION,
            ),
        )
    )


def _raw(
    *,
    hp: int = 180,
    hyper_potions: int = 0,
    poke_balls: int = 0,
) -> RawGameState:
    from pokemon_red_completion.observation import EventFlag

    events = bytearray(320)
    events[EventFlag.OAK_GOT_PARCEL // 8] |= 1 << (EventFlag.OAK_GOT_PARCEL % 8)
    bag = tuple(
        (int(item), quantity)
        for item, quantity in (
            (ItemId.HYPER_POTION, hyper_potions),
            (ItemId.POKE_BALL, poke_balls),
        )
        if quantity
    )
    return RawGameState(
        event_flags=bytes(events),
        game_started=True,
        map_id=1,
        player_x=2,
        player_y=3,
        party_count=1,
        battle_state=0,
        bag_item_ids=tuple(item for item, _quantity in bag),
        bag_items=bag,
        party_species_ids=(0x1C,),
        party_levels=(55,),
        party_hp=(hp,),
        party_max_hp=(180,),
        party_status=(0,),
        party_moves=((57, 58, 55, 0),),
        party_pp=((15, 10, 5, 0),),
    )


class _Reader:
    def __init__(self, *, raw: RawGameState, ready: bool) -> None:
        self.raw = raw
        self.ready = ready
        self.dialogue = False
        self.facing = "up"
        self.pokedex = RedPokedexState(frozenset({9}), frozenset({9}))
        self.boxes = RedBoxCollectionState(
            tuple(RedCurrentBoxState(index, (), ()) for index in range(12)),
            0,
            False,
        )

    def read(self) -> RawGameState:
        return self.raw

    def read_pokedex_state(self) -> RedPokedexState:
        return self.pokedex

    def read_all_box_states(self) -> RedBoxCollectionState:
        return self.boxes

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0 if self.ready else 1, 0, 0, 0, 0)

    def read_overworld_start_menu_visible(self):
        return getattr(self, "start_menu", False)

    def read_bottom_dialogue_box_visible(self) -> bool:
        return self.dialogue

    def read_player_facing(self) -> str:
        return self.facing

    def read_generic_pc_session_active(self) -> bool:
        return getattr(self, "pc_active", False)


class _Observer:
    def observe_raw(self, _raw: RawGameState) -> GameState:
        return GameState(GameMode.OVERWORLD, frozenset(), "test")

    def observe(self) -> GameState:
        return self.observe_raw(_raw())


class _ActionPort:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader
        self.frame_count = 100
        self.pressed_buttons = frozenset()

    def execute(self, action: MacroAction) -> MacroAction:
        self.frame_count += action.repeat
        if action.kind is MacroActionKind.CANCEL:
            self.reader.ready = True
        return action

    def read_u8(self, _address: int) -> int:
        return 0


def _adapter(reader: _Reader) -> PokemonRedGoalStateAdapter:
    return PokemonRedGoalStateAdapter(reader, _Observer(), _graph())


def test_control_recovery_is_available_only_at_a_blocked_nonbattle_boundary() -> None:
    reader = _Reader(raw=_raw(), ready=False)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedControlRecoveryGoalProvider(
        actions,
        reader,  # type: ignore[arg-type]
        port,
        adapter,
        wait_attempts=1,
        cancel_attempts=1,
        confirm_attempts=1,
        settle_frames=1,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert report.actions_executed == 3
    assert verdict.status.value == "succeeded"
    assert reader.ready

    second = provider.offer(adapter.observe())
    assert second.binding is None
    assert second.kind is GoalKind.RECOVER_CONTROL


@pytest.mark.parametrize("resource_change", [False, True])
def test_opt_in_control_recovery_closes_ready_dialogue_without_changing_resources(resource_change):
    reader = _Reader(raw=_raw(), ready=True)
    reader.dialogue = True

    class DialoguePort(_ActionPort):
        def execute(self, action):
            if action.kind is MacroActionKind.CANCEL:
                reader.dialogue = False
                if resource_change:
                    reader.raw = replace(reader.raw, party_hp=(179,))
            return super().execute(action)

    port = DialoguePort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    default = RedControlRecoveryGoalProvider(actions, reader, port, adapter)
    assert default.offer(adapter.observe()).binding is None
    provider = replace(default, settle_dialogue=True, wait_attempts=1, settle_frames=1)
    offer = provider.offer(adapter.observe())
    assert offer.binding is not None
    report = offer.binding.execute()
    assert report.actions_executed > 0 and not reader.dialogue
    expected = "failed" if resource_change else "succeeded"
    assert offer.binding.verify(report).status.value == expected
    assert provider.offer(adapter.observe()).binding is None


def test_dialogue_settlement_opt_in_is_strict_boolean():
    with pytest.raises(TypeError, match="boolean"):
        RedControlRecoveryGoalProvider(None, None, None, None, settle_dialogue=1)


@pytest.mark.parametrize("closes", [True, False])
def test_start_menu_recovery_cancels_without_confirming_or_querying_strategy(closes):
    reader = _Reader(raw=_raw(), ready=True)
    reader.start_menu = True
    seen = []

    class MenuPort(_ActionPort):
        def execute(self, action):
            seen.append(action.kind)
            if action.kind is MacroActionKind.CANCEL and closes:
                reader.start_menu = False
            return super().execute(action)

    port = MenuPort(reader)
    adapter = _adapter(reader)
    provider = RedControlRecoveryGoalProvider(
        CountingExecutor(port), reader, port, adapter,
        wait_attempts=1, cancel_attempts=1, confirm_attempts=1, settle_frames=1,
    )
    assert not adapter.observe().input_ready
    offer = provider.offer(adapter.observe())
    assert offer.binding is not None
    if closes:
        report = offer.binding.execute()
        assert offer.binding.verify(report).status.value == "succeeded"
        assert adapter.observe().input_ready
        reader.start_menu = True
        assert offer.binding.verify(report).status.value == "failed"
    else:
        with pytest.raises(RedGoalSkillError, match="bounded control recovery"):
            offer.binding.execute()
    assert MacroActionKind.CANCEL in seen
    assert MacroActionKind.CONFIRM not in seen


@pytest.mark.parametrize("entry_kind", [MacroActionKind.WAIT, MacroActionKind.CANCEL])
def test_control_recovery_stops_before_input_after_battle_entry(entry_kind):
    reader = _Reader(raw=_raw(), ready=False)
    seen = []

    class BattleEntryPort(_ActionPort):
        def execute(self, action):
            seen.append(action.kind)
            if action.kind is entry_kind:
                reader.raw = replace(reader.raw, battle_state=2)
            return action

    port = BattleEntryPort(reader)
    provider = RedControlRecoveryGoalProvider(
        CountingExecutor(port), reader, port, _adapter(reader), wait_attempts=1
    )
    with pytest.raises(RedGoalSkillError, match="entered battle"):
        provider._recover()
    assert seen == (
        [MacroActionKind.WAIT]
        if entry_kind is MacroActionKind.WAIT
        else [MacroActionKind.WAIT, MacroActionKind.CANCEL, MacroActionKind.WAIT]
    )


def test_field_restore_consumes_declared_item_and_verifies_fresh_party_state(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    reader = _Reader(raw=_raw(hp=100, hyper_potions=1), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)

    def recover(
        received_actions,
        _reader,
        _emulator,
        party_index: int,
        item: ItemId,
    ) -> None:  # type: ignore[no-untyped-def]
        assert party_index == 0
        assert item is ItemId.HYPER_POTION
        received_actions.execute(MacroAction(MacroActionKind.WAIT))
        reader.raw = replace(
            reader.raw,
            bag_item_ids=(),
            bag_items=(),
            party_hp=(180,),
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills.use_field_recovery_item",
        recover,
    )
    provider = RedFieldRestoreGoalProvider(
        actions,
        reader,  # type: ignore[arg-type]
        port,
        adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    assert offer.binding.opportunity.availability is GoalAvailability.AVAILABLE
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert report.actions_executed == 1
    assert verdict.status.value == "succeeded"
    assert reader.raw.party_hp == (180,)


def test_field_restore_masks_damage_when_the_required_item_is_absent() -> None:
    reader = _Reader(raw=_raw(hp=100), ready=True)
    port = _ActionPort(reader)
    adapter = _adapter(reader)
    provider = RedFieldRestoreGoalProvider(
        CountingExecutor(port),
        reader,  # type: ignore[arg-type]
        port,
        adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is None
    assert offer.kind is GoalKind.RESTORE_TEAM


class _CenterPort(_ActionPort):
    def execute(self, action: MacroAction) -> MacroAction:
        self.frame_count += action.repeat
        if action.kind is MacroActionKind.MOVE and action.value == "up":
            assert self.reader.raw.player_y is not None
            self.reader.raw = replace(
                self.reader.raw,
                player_y=self.reader.raw.player_y - 1,
            )
        elif action.kind is MacroActionKind.CONFIRM and self.reader.raw.player_y == 3:
            self.reader.raw = replace(
                self.reader.raw,
                party_hp=self.reader.raw.party_max_hp,
                party_status=(0,),
                party_pp=((15, 10, 5, 0),),
            )
        return action


@pytest.mark.parametrize("updates_anchor", [True, False])
def test_full_health_nurse_must_complete_the_requested_indigo_checkpoint(updates_anchor):
    reader = _Reader(raw=replace(_raw(), map_id=MapId.INDIGO_PLATEAU_LOBBY,
        player_x=7, player_y=7, party_moves=((55, 0, 0, 0),),
        party_pp=((25, 0, 0, 0),)), ready=True)
    state = {"anchor": 15, "confirms": 0}
    reader.read_last_blackout_map = lambda: state["anchor"]

    class CheckpointPort(_ActionPort):
        def execute(self, action):
            self.frame_count += action.repeat
            if action.kind is MacroActionKind.CONFIRM:
                state["confirms"] += 1
                if updates_anchor and state["confirms"] == 3:
                    state["anchor"] = int(MapId.INDIGO_PLATEAU)
            return action

    port = CheckpointPort(reader)
    offer = RedCenterRestoreGoalProvider(CountingExecutor(port), reader, port, _adapter(reader),
        settle_frames=1, dialogue_attempts=4, require_full_pp_restore=True,
        include_indigo_lobby=True, require_indigo_checkpoint=True).offer(_adapter(reader).observe())
    assert offer.binding is not None and state["confirms"] == 0
    if not updates_anchor:
        with pytest.raises(RedGoalSkillError, match="did not restore"):
            offer.binding.execute()
        assert state["confirms"] == 4 and state["anchor"] == 15
        return
    report = offer.binding.execute()
    assert state["confirms"] == 3 and state["anchor"] == 9
    assert offer.binding.verify(report).status.value == "succeeded"
    state["anchor"] = 15
    assert offer.binding.verify(report).status.value == "failed"


@pytest.mark.parametrize("kwargs", [
    {"require_indigo_checkpoint": 1},
    {"require_indigo_checkpoint": True},
    {"require_indigo_checkpoint": True, "include_indigo_lobby": True},
])
def test_indigo_checkpoint_cannot_be_implicitly_enabled(kwargs):
    reader = _Reader(raw=_raw(), ready=True)
    port = _ActionPort(reader)
    with pytest.raises((TypeError, ValueError)):
        RedCenterRestoreGoalProvider(
            CountingExecutor(port), reader, port, _adapter(reader), **kwargs
        )


@pytest.mark.parametrize("opt_in", [False, True])
def test_indigo_nurse_layout_is_explicit_and_fully_verified(opt_in):
    reader = _Reader(
        raw=replace(
            _raw(hp=100),
            map_id=MapId.INDIGO_PLATEAU_LOBBY,
            player_x=7,
            player_y=11,
            player_money=1000,
            party_moves=((55, 0, 0, 0),),
            party_pp=((2, 0, 0, 0),),
        ),
        ready=True,
    )

    class IndigoPort(_ActionPort):
        def execute(self, action):
            self.frame_count += action.repeat
            if action.kind is MacroActionKind.MOVE:
                assert action.value == "up" and reader.raw.player_y > 7
                reader.raw = replace(reader.raw, player_y=reader.raw.player_y - 1)
            if action.kind is MacroActionKind.CONFIRM:
                assert (reader.raw.player_y, reader.raw.player_x) == (7, 7)
                reader.raw = replace(
                    reader.raw,
                    party_hp=reader.raw.party_max_hp,
                    party_status=(0,),
                    party_pp=((25, 0, 0, 0),),
                )
            return action

    port = IndigoPort(reader)
    initial_frames = port.frame_count
    offer = RedCenterRestoreGoalProvider(
        CountingExecutor(port),
        reader,
        port,
        _adapter(reader),
        settle_frames=1,
        require_full_pp_restore=True,
        include_indigo_lobby=opt_in,
    ).offer(_adapter(reader).observe())
    if not opt_in:
        assert offer.binding is None and port.frame_count == initial_frames
        return
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert (reader.raw.player_y, reader.raw.player_x) == (7, 7)
    reader.raw = replace(reader.raw, player_money=reader.raw.player_money - 1)
    assert offer.binding.verify(report).status.value == "failed"


def test_center_restore_reaches_nurse_and_verifies_whole_party_recovery() -> None:
    reader = _Reader(
        raw=replace(
            _raw(hp=100),
            map_id=MapId.CELADON_POKECENTER,
            player_x=3,
            player_y=7,
        ),
        ready=True,
    )
    port = _CenterPort(reader)
    provider = RedCenterRestoreGoalProvider(
        CountingExecutor(port),
        reader,  # type: ignore[arg-type]
        port,
        _adapter(reader),
        settle_frames=1,
    )

    offer = provider.offer(_adapter(reader).observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert reader.raw.player_y == 3
    assert reader.raw.party_hp == reader.raw.party_max_hp


@pytest.mark.parametrize("wait_frames", [1, 120])
def test_center_receipt_excludes_separately_metered_input_after_offer(wait_frames):
    reader = _Reader(raw=replace(
        _raw(hp=100), map_id=MapId.CELADON_POKECENTER, player_x=3, player_y=7),
        ready=True)
    port = _CenterPort(reader)
    actions = CountingExecutor(port)
    offer = RedCenterRestoreGoalProvider(
        actions, reader, port, _adapter(reader), settle_frames=1,
    ).offer(_adapter(reader).observe())
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=wait_frames))
    before_actions, before_frames = actions.actions_executed, port.frame_count
    report = offer.binding.execute()
    assert report.actions_executed == actions.actions_executed - before_actions
    assert report.frames_executed == port.frame_count - before_frames
    assert actions.actions_executed == report.actions_executed + 1
    assert offer.binding.verify(report).status.value == "succeeded"


@pytest.mark.parametrize("facing", ["up", "left", "right", "down"])
@pytest.mark.parametrize("indigo", [False, True])
def test_center_restore_faces_nurse_after_sideways_route_arrival(facing, indigo):
    nurse_at = (7, 7) if indigo else (3, 3)
    reader = _Reader(
        raw=replace(
            _raw(hp=0),
            map_id=MapId.INDIGO_PLATEAU_LOBBY if indigo else MapId.CINNABAR_POKECENTER,
            player_y=nurse_at[0],
            player_x=nurse_at[1],
            party_status=(16,),
            party_pp=((1, 0, 0, 0),),
        ),
        ready=True,
    )
    reader.facing = facing
    moves = []

    class FacingPort(_ActionPort):
        def execute(self, action):
            if action.kind is MacroActionKind.MOVE:
                assert action.value == "up"
                moves.append(action.value)
                reader.facing = "up"  # Counter blocks walking, not turning.
            if action.kind is MacroActionKind.CONFIRM:
                assert reader.facing == "up"
                assert (reader.raw.player_y, reader.raw.player_x) == nurse_at
                reader.raw = replace(
                    reader.raw,
                    party_hp=reader.raw.party_max_hp,
                    party_status=(0,),
                    party_pp=((15, 10, 5, 0),),
                )
            return super().execute(action)

    port = FacingPort(reader)
    offer = RedCenterRestoreGoalProvider(
        CountingExecutor(port),
        reader,
        port,
        _adapter(reader),
        settle_frames=1,
        include_indigo_lobby=indigo,
    ).offer(_adapter(reader).observe())
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert moves == ([] if facing == "up" else ["up"])
    assert (reader.raw.player_y, reader.raw.player_x) == nurse_at


@pytest.mark.parametrize(
    "fault", ["position", "facing", "battle", "cash", "hp", "pp", "status", "bag"]
)
def test_center_nurse_facing_refuses_changed_boundary_before_dialogue(fault):
    reader = _Reader(
        raw=replace(
            _raw(hp=100),
            map_id=MapId.CINNABAR_POKECENTER,
            player_y=3,
            player_x=3,
            player_money=1000,
        ),
        ready=True,
    )
    reader.facing = "left"
    confirms = []

    class UnsafeFacingPort(_ActionPort):
        def execute(self, action):
            if action.kind is MacroActionKind.MOVE:
                reader.facing = "up" if fault != "facing" else "left"
                change = {
                    "position": {"player_y": 2},
                    "facing": {},
                    "battle": {"battle_state": 1},
                    "cash": {"player_money": 999},
                    "hp": {"party_hp": (99,)},
                    "pp": {"party_pp": ((14, 10, 5, 0),)},
                    "status": {"party_status": (16,)},
                    "bag": {"bag_items": ((4, 1),)},
                }[fault]
                reader.raw = replace(reader.raw, **change)
            if action.kind is MacroActionKind.CONFIRM:
                confirms.append(action)
            return super().execute(action)

    port = UnsafeFacingPort(reader)
    binding = (
        RedCenterRestoreGoalProvider(
            CountingExecutor(port),
            reader,
            port,
            _adapter(reader),
            settle_frames=1,
        )
        .offer(_adapter(reader).observe())
        .binding
    )
    with pytest.raises(RedGoalSkillError, match="nurse facing"):
        binding.execute()
    assert not confirms


@pytest.mark.parametrize("pp", [(24, 0, 0, 0), (25, 0, 0, 0), (0, 0, 0, 0), (0x40 | 29, 0, 0, 0)])
def test_full_center_mode_restores_nonempty_pp_and_preserves_legacy_mode(pp):
    from pokemon_red_completion.red_goal_skills import _raw_party_fully_restored

    reader = _Reader(
        raw=replace(
            _raw(),
            map_id=MapId.LAVENDER_POKECENTER,
            player_x=3,
            player_y=7,
            party_moves=((55, 0, 0, 0),),
            party_pp=(pp,),
        ),
        ready=True,
    )
    reader.raw = replace(reader.raw, party_hp=reader.raw.party_max_hp, party_status=(0,))

    class FullCenterPort(_CenterPort):
        def execute(self, action):
            result = super().execute(action)
            if action.kind is MacroActionKind.CONFIRM:
                full = (0x40 | 30) if pp[0] & 0x40 else 25
                reader.raw = replace(reader.raw, party_pp=((full, 0, 0, 0),))
            return result

    port = FullCenterPort(reader)
    offer = RedCenterRestoreGoalProvider(
        CountingExecutor(port),
        reader,
        port,
        _adapter(reader),
        settle_frames=1,
        require_full_pp_restore=True,
    ).offer(_adapter(reader).observe())
    assert offer.binding is not None
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert _raw_party_fully_restored(reader.raw) and reader.raw.player_y == 3


@pytest.mark.parametrize("pages", [1, 3, 7])
def test_center_healing_does_not_complete_while_farewell_is_visible(pages):
    reader = _Reader(
        raw=replace(_raw(hp=100), map_id=MapId.CINNABAR_POKECENTER, player_x=3, player_y=3),
        ready=True,
    )

    class FarewellPort(_CenterPort):
        cancels = 0

        def execute(self, action):
            result = super().execute(action)
            if action.kind is MacroActionKind.CONFIRM:
                reader.dialogue = True
            if action.kind is MacroActionKind.CANCEL:
                self.cancels += 1
                reader.dialogue = self.cancels < pages
            return result

    port = FarewellPort(reader)
    offer = RedCenterRestoreGoalProvider(
        CountingExecutor(port), reader, port, _adapter(reader), settle_frames=1
    ).offer(_adapter(reader).observe())
    report = offer.binding.execute()
    assert port.cancels == pages
    assert not reader.dialogue
    assert report.actions_executed == 2 + 2 * pages


@pytest.mark.parametrize("visible,at_nurse", [(True, True), (False, True), (True, False)])
def test_travel_departure_reuses_farewell_only_at_its_boundary(visible, at_nurse):
    from pokemon_red_completion.red_goal_skills import prepare_center_departure

    reader = _Reader(
        raw=replace(
            _raw(), map_id=MapId.CINNABAR_POKECENTER, player_x=3 if at_nurse else 4, player_y=3
        ),
        ready=True,
    )
    reader.dialogue = visible

    class Port(_ActionPort):
        def execute(self, action):
            if action.kind is MacroActionKind.CANCEL:
                reader.dialogue = False
            return super().execute(action)

    actions = CountingExecutor(Port(reader))
    prepare_center_departure(actions, reader)
    assert actions.actions_executed == (2 if visible and at_nurse else 0)
    assert reader.raw.player_x == (3 if at_nurse else 4)


@pytest.mark.parametrize("active", [False, True])
def test_center_departure_closes_actual_pc_session_not_merely_ready_flags(active):
    from pokemon_red_completion.red_goal_skills import prepare_center_departure

    reader = _Reader(
        raw=replace(_raw(), map_id=MapId.VERMILION_POKECENTER, player_x=13, player_y=4), ready=True
    )
    reader.pc_active = active
    before = reader.raw

    class Port(_ActionPort):
        def execute(self, action):
            if action.kind is MacroActionKind.CANCEL:
                reader.pc_active = False
            return super().execute(action)

    actions = CountingExecutor(Port(reader))
    prepare_center_departure(actions, reader)
    assert actions.actions_executed == (2 if active else 0)
    assert reader.raw == before
    assert not reader.pc_active


def test_center_farewell_stuck_fails_without_movement():
    reader = _Reader(
        raw=replace(_raw(), map_id=MapId.CINNABAR_POKECENTER, player_x=3, player_y=3), ready=True
    )
    reader.dialogue = True
    actions = CountingExecutor(_ActionPort(reader))
    with pytest.raises(RedGoalSkillError, match="farewell"):
        finish_center_dialogue(actions, reader, maximum_attempts=2, settle_frames=1)
    assert actions.actions_executed == 4
    assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)


@pytest.mark.parametrize("change", ["battle", "location", "unhealed"])
def test_center_farewell_rejects_unsafe_boundary_before_input(change):
    raw = replace(_raw(), map_id=MapId.CINNABAR_POKECENTER, player_x=3, player_y=3)
    raw = replace(
        raw,
        **{
            "battle": {"battle_state": 1},
            "location": {"player_x": 4},
            "unhealed": {"party_hp": (1,)},
        }[change],
    )
    reader = _Reader(raw=raw, ready=True)
    actions = CountingExecutor(_ActionPort(reader))
    with pytest.raises(RedGoalSkillError, match="healed nurse boundary"):
        finish_center_dialogue(actions, reader)
    assert actions.actions_executed == 0


class _MartPort(_ActionPort):
    def read_u8(self, address: int) -> int:
        if address == RamAddress.TOP_MENU_ITEM_X:
            return 5
        if address == RamAddress.TOP_MENU_ITEM_Y:
            return 4
        return 0


@pytest.mark.parametrize("status", [0, 8])
def test_max_potion_is_hp_recovery_not_a_status_cure(status):
    reader = _Reader(
        raw=replace(
            _raw(hp=1),
            party_status=(status,),
            bag_item_ids=(int(ItemId.MAX_POTION),),
            bag_items=((int(ItemId.MAX_POTION), 1),),
        ),
        ready=True,
    )
    observation = _adapter(reader).observe()
    assert observation.recovery_item_count == 1
    plan, unavailable = RedFieldRestoreGoalProvider._plan(observation, affordable_single_item=True)
    if status:
        assert not plan and unavailable is GoalUnavailableReason.MISSING_RESOURCE
    else:
        assert plan == ((0, ItemId.MAX_POTION),) and unavailable is None


def test_mart_resupply_proves_balanced_resources_and_exact_economy(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    reader = _Reader(
        raw=replace(
            _raw(hyper_potions=1, poke_balls=1),
            map_id=MapId.VIRIDIAN_MART,
            player_x=2,
            player_y=4,
            player_money=5_000,
        ),
        ready=True,
    )
    port = _MartPort(reader)
    actions = CountingExecutor(port)
    prices = {int(ItemId.POKE_BALL): 200, int(ItemId.POTION): 300}

    def buy(
        received_actions,
        _emulator,
        _timing,
        *,
        absolute_index: int,
        item: int,
        quantity: int,
        target_bag_quantity: int,
    ) -> None:  # type: ignore[no-untyped-def]
        assert absolute_index in {0, 1}
        inventory = dict(reader.raw.bag_items or ())
        inventory[item] = target_bag_quantity
        assert reader.raw.player_money is not None
        reader.raw = replace(
            reader.raw,
            bag_item_ids=tuple(inventory),
            bag_items=tuple(inventory.items()),
            player_money=reader.raw.player_money - prices[item] * quantity,
        )
        received_actions.execute(MacroAction(MacroActionKind.WAIT))

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills._buy_mart_item",
        buy,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills._close_menus",
        lambda received_actions, _reader, _timing: received_actions.execute(
            MacroAction(MacroActionKind.CANCEL)
        ),
    )
    provider = RedMartResupplyGoalProvider(
        map_id=MapId.VIRIDIAN_MART,
        player_x=2,
        player_y=4,
        interaction_direction="up",
        purchases=(
            RedMartPurchase(0, ItemId.POKE_BALL, 3, 200),
            RedMartPurchase(1, ItemId.POTION, 2, 300),
        ),
        actions=actions,
        reader=reader,  # type: ignore[arg-type]
        emulator=port,
        adapter=_adapter(reader),
        wait_frames=1,
    )

    offer = provider.offer(_adapter(reader).observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert dict(reader.raw.bag_items or ()) == {
        int(ItemId.HYPER_POTION): 1,
        int(ItemId.POKE_BALL): 4,
        int(ItemId.POTION): 2,
    }
    assert reader.raw.player_money == 3_800
    assert report.evidence["money_spent"] == 1_200


def _exact_reserve_fixture():
    reader = _Reader(
        raw=replace(
            _raw(poke_balls=20),
            map_id=MapId.SAFFRON_MART,
            player_x=2,
            player_y=5,
            player_money=11921,
            bag_items=((4, 20), (20, 7), (15, 5), (11, 1), (14, 1)),
        ),
        ready=True,
    )
    port = _MartPort(reader)
    actions = CountingExecutor(port)
    provider = RedMartResupplyGoalProvider(
        MapId.SAFFRON_MART,
        2,
        5,
        "left",
        (
            RedMartPurchase(1, ItemId.HYPER_POTION, 3, 1500),
            RedMartPurchase(5, ItemId.REVIVE, 4, 1500),
            RedMartPurchase(4, ItemId.FULL_HEAL, 1, 600),
        ),
        actions,
        reader,
        port,
        _adapter(reader),
        wait_frames=1,
        reserve_targets=((ItemId.HYPER_POTION, 3), (ItemId.REVIVE, 4), (ItemId.FULL_HEAL, 1)),
    )
    return reader, actions, provider


def _stub_exact_purchase(monkeypatch, reader):
    def buy(actions, _emulator, _timing, *, absolute_index, item, quantity, target_bag_quantity):
        prices = {18: 1500, 53: 1500, 52: 600}
        assert absolute_index == {18: 1, 53: 5, 52: 4}[item]
        bag = dict(reader.raw.bag_items)
        assert bag.get(item, 0) + quantity == target_bag_quantity
        bag[item] = target_bag_quantity
        reader.raw = replace(
            reader.raw,
            bag_items=tuple(bag.items()),
            player_money=reader.raw.player_money - prices[item] * quantity,
        )
        actions.execute(MacroAction(MacroActionKind.WAIT))

    monkeypatch.setattr("pokemon_red_completion.red_goal_skills._buy_mart_item", buy)
    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills._close_menus",
        lambda actions, *_: actions.execute(MacroAction(MacroActionKind.CANCEL)),
    )


def test_exact_reserves_distinguish_potions_and_status_cures_from_missing_revives(monkeypatch):
    reader, actions, provider = _exact_reserve_fixture()
    before = provider.adapter.observe()
    assert before.evidence.resources == 1.0
    legacy = replace(provider, reserve_targets=())
    assert legacy.offer(before).binding is None
    offer = provider.offer(before)
    assert offer.binding is not None
    quote = provider.resource_quote(before)
    assert quote.purchase_cost == 11100 and quote.funding_proceeds == 0
    assert [(v.resource, v.available, v.target, v.purchased) for v in quote.reserves] == [
        ("recovery", 0, 8, 8)
    ]
    _stub_exact_purchase(monkeypatch, reader)
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert reader.raw.player_money == 821
    assert dict(reader.raw.bag_items) == {4: 20, 20: 7, 15: 5, 11: 1, 14: 1, 18: 3, 53: 4, 52: 1}
    assert provider.adapter.observe().evidence.resources == 1.0
    assert provider.offer(provider.adapter.observe()).binding is None
    count = actions.actions_executed
    with pytest.raises(RedGoalSkillError, match="origin changed"):
        offer.binding.execute()
    assert actions.actions_executed == count


@pytest.mark.parametrize(
    "fault",
    [
        "cash",
        "full_bag",
        "wrong_deficit",
        "blocked",
        "battle",
        "location",
    ],
)
def test_exact_reserves_reject_unexecutable_orders_before_input(fault):
    reader, actions, provider = _exact_reserve_fixture()
    if fault == "cash":
        reader.raw = replace(reader.raw, player_money=11099)
    elif fault == "full_bag":
        reader.raw = replace(reader.raw, bag_items=tuple((i, 1) for i in range(70, 90)))
    elif fault == "wrong_deficit":
        reader.raw = replace(reader.raw, bag_items=(*reader.raw.bag_items, (53, 1)))
    elif fault == "blocked":
        reader.ready = False
    elif fault == "battle":
        reader.raw = replace(reader.raw, battle_state=1)
    elif fault == "location":
        reader.raw = replace(reader.raw, player_x=3)
    assert provider.offer(provider.adapter.observe()).binding is None
    assert actions.actions_executed == 0


@pytest.mark.parametrize(
    "targets",
    [
        [],
        None,
        ((ItemId.REVIVE, 4),),
        ((ItemId.REVIVE, 4), (ItemId.REVIVE, 4)),
        ((53, 4),),
        ((ItemId.REVIVE, True),),
        ((ItemId.REVIVE, 100),),
        ((ItemId.REVIVE, 0),),
        ((ItemId.HM01_CUT, 1),),
    ],
)
def test_exact_reserves_validate_explicit_contract(targets):
    _, _, provider = _exact_reserve_fixture()
    with pytest.raises(ValueError):
        replace(provider, reserve_targets=targets)


@pytest.mark.parametrize(
    "fault",
    [
        "cash",
        "quantity",
        "other_item",
        "hp",
        "pp",
        "position",
        "readiness",
        "pokedex",
    ],
)
def test_exact_reserve_verifier_rejects_mutated_terminal(monkeypatch, fault):
    reader, _, provider = _exact_reserve_fixture()
    offer = provider.offer(provider.adapter.observe())
    _stub_exact_purchase(monkeypatch, reader)
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    if fault == "cash":
        reader.raw = replace(reader.raw, player_money=822)
    elif fault in {"quantity", "other_item"}:
        bag = dict(reader.raw.bag_items)
        bag[53 if fault == "quantity" else 4] += 1
        reader.raw = replace(reader.raw, bag_items=tuple(bag.items()))
    elif fault == "hp":
        reader.raw = replace(reader.raw, party_hp=(1,))
    elif fault == "pp":
        reader.raw = replace(reader.raw, party_pp=((0, 0, 0, 0),))
    elif fault == "position":
        reader.raw = replace(reader.raw, player_x=3)
    elif fault == "readiness":
        reader.ready = False
    elif fault == "pokedex":
        reader.pokedex = RedPokedexState(frozenset({9, 10}), frozenset({9, 10}))
    assert offer.binding.verify(report).status.value == "failed"


def test_exact_reserve_rejects_stale_bound_resources_before_input():
    reader, actions, provider = _exact_reserve_fixture()
    offer = provider.offer(provider.adapter.observe())
    reader.raw = replace(reader.raw, player_money=11920)
    with pytest.raises(RedGoalSkillError, match="origin changed"):
        offer.binding.execute()
    assert actions.actions_executed == 0


def _internal_species_id(national_number: int) -> int:
    for internal in range(1, 191):
        try:
            if red_internal_species_number(internal) == national_number:
                return internal
        except ValueError:
            continue
    raise AssertionError(f"no internal species id for {national_number}")


class _AreaExecutor:
    def __init__(
        self,
        reader: _Reader,
        actions: CountingExecutor,
        source_id: str = "wild:Route1:grass",
    ) -> None:
        self.reader = reader
        self.actions = actions
        self.source_id = source_id
        self.encountered: str | None = None

    def read_collection(self):  # type: ignore[no-untyped-def]
        return red_collection_observation(
            self.reader.pokedex,
            party_observation_from_raw(self.reader.raw),
            self.reader.boxes,
        )

    def encountered_species_ref(self) -> str | None:
        return self.encountered

    def seek_encounter(self) -> None:
        survey = summarize_red_area_survey(
            self.source_id,
            self.read_collection(),
        )
        self.encountered = survey.missing_species_refs[0]
        self.actions.execute(MacroAction(MacroActionKind.WAIT))

    def capture_encounter(self, species_ref: str) -> bool:
        assert species_ref == self.encountered
        national = red_species_number(species_ref)
        boxes = list(self.reader.boxes.boxes)
        current = boxes[self.reader.boxes.current_box_index]
        boxes[current.box_index] = RedCurrentBoxState(
            current.box_index,
            (*current.species_ids, _internal_species_id(national)),
            (*current.levels, 3),
        )
        self.reader.boxes = RedBoxCollectionState(
            tuple(boxes),
            self.reader.boxes.current_box_index,
            True,
        )
        self.reader.pokedex = RedPokedexState(
            self.reader.pokedex.owned_species.union({national}),
            self.reader.pokedex.seen_species.union({national}),
        )
        self.encountered = None
        self.actions.execute(MacroAction(MacroActionKind.WAIT))
        return True

    def flee_encounter(self) -> None:
        self.encountered = None

    def switch_box(self, _box_index: int) -> None:
        raise AssertionError("Route 1 fixture has storage room")


class _DiscoveryExecutor(_AreaExecutor):
    def seek_encounter(self) -> None:
        super().seek_encounter()
        assert self.encountered is not None
        national = red_species_number(self.encountered)
        self.reader.pokedex = RedPokedexState(
            self.reader.pokedex.owned_species,
            self.reader.pokedex.seen_species.union({national}),
        )

    def flee_encounter(self) -> None:
        assert self.encountered is not None
        self.encountered = None
        self.actions.execute(MacroAction(MacroActionKind.WAIT))


@pytest.mark.parametrize("escape_bypasses", [0, 2])
def test_area_survey_provider_captures_and_independently_reloads_collection(
    escape_bypasses: int,
) -> None:
    reader = _Reader(raw=_raw(poke_balls=20), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    area = _AreaExecutor(reader, actions)
    area.capture_escape_bypasses = escape_bypasses
    area.capture_throw_preparations = [{"target_status": "healthy", "throw_executed": False}]
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=area,
        actions=actions,
        emulator=port,
        adapter=adapter,
        policy=RedAreaExecutionPolicy(
            max_actions=20,
            max_encounters=20,
            capture_in_requirement_order=True,
        ),
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "succeeded"
    assert report.evidence["captures"] >= 2
    assert report.evidence["capture_throw_preparations"] == tuple(area.capture_throw_preparations)
    assert report.evidence["capture_support"] == {
        "status_attempts": 0,
        "verified_status_observations": 0,
        "party_preparations": 0,
        **({"escape_setup_bypasses": 2} if escape_bypasses else {}),
        "prepared_throws": 1,
        "prepared_asleep": 0,
        "prepared_paralyzed": 0,
        "prepared_full_hp": 0,
    }
    assert not summarize_red_area_survey(
        "wild:Route1:grass",
        adapter.observe().collection_observation,
    ).missing_species_refs


@pytest.mark.parametrize("unsafe", [False, True])
@pytest.mark.parametrize("balls_remaining", [0, 1, 20])
def test_area_survey_labels_verified_no_find_without_claiming_success(
    unsafe,
    balls_remaining,
) -> None:
    reader = _Reader(raw=_raw(poke_balls=20), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)

    class ExhaustedArea(_AreaExecutor):
        def seek_encounter(self):
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            raise RedAreaExecutionError("bounded search", reason_code="survey_leg_limit_exceeded")

    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=ExhaustedArea(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
    )
    offer = provider.offer(adapter.observe())
    assert offer.binding is not None
    report = offer.binding.execute()
    reader.raw = replace(reader.raw, bag_items=_raw(poke_balls=balls_remaining).bag_items)
    if unsafe:
        reader.ready = False
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "failed"
    assert verdict.failure_reason is (
        GoalFailureReason.OUTCOME_NOT_VERIFIED
        if unsafe
        else GoalFailureReason.CAPTURE_ITEMS_EXHAUSTED
        if balls_remaining == 0
        else GoalFailureReason.SEARCH_EXHAUSTED
    )
    assert report.evidence["search_exhausted"] is True
    assert report.evidence["search_stop_reason"] == "survey_leg_limit_exceeded"
    assert report.evidence["capture_survey"] == {
        "semantic_actions": 1,
        "encounters_seen": 0,
        "captures": 0,
        "flees": 0,
        "search_exhausted": True,
        "safety_stopped": False,
        "search_stop_reason": "survey_leg_limit_exceeded",
    }
    assert report.evidence["captures"] == 0
    assert report.evidence["encounters_seen"] == 0
    assert (
        report.evidence["initial_missing_specimens"] == report.evidence["final_missing_specimens"]
    )
    assert report.actions_executed == 1
    assert report.frames_executed > 0


@pytest.mark.parametrize("caught", [False, True])
@pytest.mark.parametrize("reserved_master_ball", [False, True])
def test_area_survey_last_ball_stops_before_another_encounter_and_retains_costs(
    caught,
    reserved_master_ball,
):
    reader = _Reader(raw=_raw(poke_balls=1), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    calls = []

    class LastBallArea(_AreaExecutor):
        def seek_encounter(self):
            calls.append("seek")
            assert calls == ["seek"], "must not search again without balls"
            super().seek_encounter()

        def capture_encounter(self, species_ref):
            if caught:
                super().capture_encounter(species_ref)
            else:
                self.encountered = None
                self.actions.execute(MacroAction(MacroActionKind.WAIT))
            reader.raw = replace(reader.raw, bag_items=_raw(poke_balls=0).bag_items)
            if reserved_master_ball:
                reader.raw = replace(
                    reader.raw,
                    bag_items=(
                        *(reader.raw.bag_items or ()),
                        (int(ItemId.MASTER_BALL), 1),
                    ),
                )
            return caught

    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=LastBallArea(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
    )
    binding = provider.offer(adapter.observe()).binding
    assert binding is not None
    report = binding.execute()
    assert report.actions_executed == 2 and report.frames_executed > 0
    assert report.evidence["capture_survey"]["capture_items_exhausted"] is True
    from pokemon_red_completion.capture_survey import CaptureSurveySummary

    diagnostic = CaptureSurveySummary.from_evidence(report.evidence)
    assert diagnostic is not None
    assert diagnostic.public_dict() == report.evidence["capture_survey"]
    assert report.evidence["search_exhausted"] is False
    assert report.evidence["encounters_seen"] == 1
    assert report.evidence["captures"] == int(caught)
    assert report.evidence["flees"] == int(not caught)
    verdict = binding.verify(report)
    assert verdict.status.value == ("succeeded" if caught else "failed")
    if not caught:
        assert verdict.failure_reason is GoalFailureReason.CAPTURE_ITEMS_EXHAUSTED
        # The marker alone cannot certify exhaustion or a safe terminal boundary.
        reader.raw = replace(reader.raw, bag_items=_raw(poke_balls=1).bag_items)
        assert binding.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
        reader.raw = replace(reader.raw, bag_items=_raw(poke_balls=0).bag_items)
        reader.ready = False
        assert binding.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED


@pytest.mark.parametrize("fault", [None, "unready", "active", "fainted", "wrong_exit", "error"])
def test_last_ball_failure_returns_to_exact_source_without_claiming_a_catch(fault):
    reader = _Reader(raw=_raw(poke_balls=1), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    returns = []

    class LastBallArea(_AreaExecutor):
        def capture_encounter(self, species_ref):
            self.encountered = None
            actions.execute(MacroAction(MacroActionKind.WAIT))
            reader.raw = replace(reader.raw, player_x=3, bag_items=())
            if fault == "unready":
                reader.ready = False
            elif fault == "active":
                reader.raw = replace(reader.raw, battle_state=1)
            elif fault == "fainted":
                reader.raw = replace(reader.raw, party_hp=(0,))
            return False

    def normalize():
        returns.append(True)
        if fault == "error":
            raise RuntimeError("failed return route")
        actions.execute(MacroAction(MacroActionKind.WAIT))
        if fault != "wrong_exit":
            reader.raw = replace(reader.raw, player_x=2)

    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=LastBallArea(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
        boundary=lambda current: (
            RedGoalSkillAvailability.available()
            if current.raw.player_x == 2
            else RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        ),
        normalize_after_capture=normalize,
    )
    binding = provider.offer(adapter.observe()).binding
    assert binding is not None
    if fault == "error":
        with pytest.raises(RuntimeError, match="failed return route"):
            binding.execute()
        return
    report = binding.execute()
    verdict = binding.verify(report)
    assert report.evidence["captures"] == 0
    assert verdict.status.value == "failed"
    assert bool(returns) is (fault in {None, "wrong_exit"})
    assert report.evidence["source_normalized"] is bool(returns)
    if fault is None:
        assert verdict.failure_reason is GoalFailureReason.CAPTURE_ITEMS_EXHAUSTED
        assert report.actions_executed == 3 and report.frames_executed > 0
    elif fault == "wrong_exit":
        assert verdict.failure_reason is GoalFailureReason.WORLD_STATE_DIVERGED


@pytest.mark.parametrize("when", ["before_execution", "after_flee", "after_capture"])
def test_area_survey_stops_on_faint_without_another_search_or_normalization(when):
    reader = _Reader(raw=_raw(poke_balls=20), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    calls = []

    def faint():
        reader.raw = replace(reader.raw, party_hp=(0,))

    class FaintingArea(_AreaExecutor):
        def seek_encounter(self):
            calls.append("seek")
            assert calls.count("seek") == 1, "must not search again after a faint"
            super().seek_encounter()
            if when == "after_flee":
                self.encountered = red_species_ref(150)  # Not a Route1 requirement.

        def flee_encounter(self):
            calls.append("flee")
            super().flee_encounter()
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            faint()

        def capture_encounter(self, species_ref):
            calls.append("capture")
            result = super().capture_encounter(species_ref)
            faint()
            return result

    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=FaintingArea(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
        policy=RedAreaExecutionPolicy(capture_quota=1),
        normalize_after_capture=lambda: pytest.fail("unsafe endpoint must not walk to normalize"),
    )
    binding = provider.offer(adapter.observe()).binding
    assert binding is not None
    if when == "before_execution":
        faint()
    report = binding.execute()
    assert report.evidence["safety_stopped"] is True
    assert report.evidence["source_normalized"] is False
    assert report.evidence["search_exhausted"] is False
    assert "search_stop_reason" not in report.evidence
    assert report.evidence["captures"] == int(when == "after_capture")
    assert report.evidence["flees"] == int(when == "after_flee")
    assert report.evidence["encounters_seen"] == int(when != "before_execution")
    assert calls == ([] if when == "before_execution" else ["seek", when.removeprefix("after_")])
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST
    # Availability participates in older checkpoint fingerprints. Keep its
    # projection stable; the execution-time safety check prevents searching.
    assert provider.resource_availability(adapter.observe()).executable
    # A fabricated safety marker cannot invent a faint in the referee's fresh read.
    reader.raw = replace(reader.raw, party_hp=(180,))
    assert binding.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED


def test_area_survey_preserves_old_offer_but_stops_for_fainted_non_lead_before_input():
    raw = replace(
        _raw(poke_balls=20),
        party_count=2,
        party_species_ids=(28, 114),
        party_levels=(55, 10),
        party_hp=(180, 0),
        party_max_hp=(180, 35),
        party_status=(0, 0),
        party_moves=((57, 58, 55, 0), (106, 0, 0, 0)),
        party_pp=((15, 10, 5, 0), (30, 0, 0, 0)),
    )
    reader = _Reader(raw=raw, ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=_AreaExecutor(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
    )
    assert adapter.observe().party.members[0].hp == 180
    binding = provider.offer(adapter.observe()).binding
    assert binding is not None
    report = binding.execute()
    assert report.evidence["safety_stopped"] is True
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST
    assert actions.actions_executed == 0
    reader.raw = replace(raw, party_hp=(180, 35))
    assert provider.offer(adapter.observe()).binding is not None
    assert actions.actions_executed == 0


def test_area_survey_verifies_one_required_duplicate_precursor() -> None:
    reader = _Reader(raw=_raw(poke_balls=20), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    source_id = "wild:Route14:grass"
    before_survey = summarize_red_area_survey(
        source_id,
        adapter.observe().collection_observation,
    )
    normalizations = 0

    def normalize_after_capture() -> None:
        nonlocal normalizations
        normalizations += 1
        actions.execute(MacroAction(MacroActionKind.WAIT))

    provider = RedAreaSurveyGoalProvider(
        source_id=source_id,
        area_executor=_AreaExecutor(reader, actions, source_id),
        actions=actions,
        emulator=port,
        adapter=adapter,
        boundary=lambda _observation: RedGoalSkillAvailability.available(),
        normalize_after_capture=normalize_after_capture,
        policy=RedAreaExecutionPolicy(
            max_actions=20,
            max_encounters=20,
            capture_in_requirement_order=True,
            capture_quota=1,
        ),
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    survey = summarize_red_area_survey(
        source_id,
        adapter.observe().collection_observation,
    )
    assert verdict.status.value == "succeeded"
    assert normalizations == 1
    assert report.evidence["captures"] == 1
    assert report.evidence["source_normalized"] is True
    assert report.evidence["initial_missing_specimens"] == before_survey.missing_specimen_count
    assert report.evidence["final_missing_specimens"] == before_survey.missing_specimen_count - 1
    assert survey.missing_species_refs[0] == red_species_ref(17)


def test_area_survey_reserves_master_ball_for_nonordinary_targets() -> None:
    reader = _Reader(
        raw=replace(
            _raw(),
            bag_item_ids=(int(ItemId.MASTER_BALL),),
            bag_items=((int(ItemId.MASTER_BALL), 1),),
        ),
        ready=True,
    )
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=_AreaExecutor(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is None
    assert offer.kind is GoalKind.ACQUIRE_SPECIES


def test_local_discovery_refuses_exhausted_source_but_not_unseen_target() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedEncounterDiscoveryGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=_DiscoveryExecutor(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
        source_species_numbers=(9,),
    )
    observed = adapter.observe()
    assert observed.evidence.world_knowledge.satisfaction < 1.0
    assert provider.offer(observed).unavailable_reason is GoalUnavailableReason.NO_LEGAL_TARGET
    assert replace(provider, source_species_numbers=(9, 16)).offer(observed).binding is not None
    assert replace(provider, source_species_numbers=None).offer(observed).binding is not None
    assert actions.actions_executed == 0


@pytest.mark.parametrize("numbers", [(), (True,), (0,), (152,), (9, 9), (16, 9)])
def test_local_discovery_rejects_invalid_species(numbers) -> None:
    reader = _Reader(raw=_raw(), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    with pytest.raises(RedGoalSkillError, match="local species"):
        RedEncounterDiscoveryGoalProvider(
            source_id="wild:Route1:grass",
            area_executor=_DiscoveryExecutor(reader, actions),
            actions=actions,
            emulator=port,
            adapter=_adapter(reader),
            source_species_numbers=numbers,
        )


def test_encounter_discovery_learns_a_new_sighting_without_capturing() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedEncounterDiscoveryGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=_DiscoveryExecutor(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
        maximum_seek_steps=4,
        maximum_encounters=2,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert report.evidence == {
        "bounded": True,
        "encounters_seen": 1,
        "new_sighting_count": 1,
        "captures": 0,
    }
    assert reader.pokedex.owned_species == frozenset({9})
    assert len(reader.pokedex.seen_species) == 2


@pytest.mark.parametrize("limit", [
    "survey_leg_limit_exceeded", "seek_step_limit_reached", "encounter_limit_reached",
])
def test_discovery_returns_a_measured_failed_miss_and_exits_the_last_encounter(limit):
    reader = _Reader(raw=_raw(), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)

    class NoFindArea(_DiscoveryExecutor):
        def seek_encounter(self):
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            if limit == "survey_leg_limit_exceeded":
                raise RedAreaExecutionError("bounded patrol", reason_code=limit)
            if limit == "encounter_limit_reached":
                self.encountered = red_species_ref(9)

    area = NoFindArea(reader, actions)
    provider = RedEncounterDiscoveryGoalProvider(
        "wild:Route1:grass", area, actions, port, _adapter(reader),
        maximum_seek_steps=2, maximum_encounters=1,
    )
    offer = provider.offer(provider.adapter.observe())
    assert offer.binding is not None
    before_frames = port.frame_count
    report = offer.binding.execute()
    assert report.evidence["search_stop_reason"] == limit
    assert report.evidence["search_exhausted"] is True
    assert report.evidence["new_sighting_count"] == report.evidence["captures"] == 0
    assert report.actions_executed == actions.actions_executed > 0
    assert report.frames_executed == port.frame_count - before_frames > 0
    assert area.encountered is None
    assert offer.binding.verify(report).failure_reason is GoalFailureReason.SEARCH_EXHAUSTED


@pytest.mark.parametrize("fault", [
    "unready", "battle", "fainted", "identity", "new_seen", "no_actions", "no_frames",
    "reason", "false_count",
])
def test_discovery_no_find_verifier_rejects_unsafe_or_unproven_misses(fault):
    reader = _Reader(raw=_raw(), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)

    class ExhaustedArea(_DiscoveryExecutor):
        def seek_encounter(self):
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            raise RedAreaExecutionError("bounded patrol", reason_code="survey_leg_limit_exceeded")

    provider = RedEncounterDiscoveryGoalProvider(
        "wild:Route1:grass", ExhaustedArea(reader, actions), actions, port, _adapter(reader),
    )
    offer = provider.offer(provider.adapter.observe())
    assert offer.binding is not None
    report = offer.binding.execute()
    if fault == "unready":
        reader.ready = False
    elif fault == "battle":
        reader.raw = replace(reader.raw, battle_state=1)
    elif fault == "fainted":
        reader.raw = replace(reader.raw, party_hp=(0,))
    elif fault == "identity":
        reader.raw = replace(reader.raw, party_species_ids=(_internal_species_id(16),))
    elif fault == "new_seen":
        reader.pokedex = replace(reader.pokedex, seen_species=frozenset({9, 16}))
    elif fault == "no_actions":
        report = replace(report, actions_executed=0)
    elif fault == "no_frames":
        report = replace(report, frames_executed=0)
    else:
        key, value = (
            ("search_stop_reason", "unknown")
            if fault == "reason" else ("new_sighting_count", False)
        )
        report = replace(report, evidence={**report.evidence, key: value})
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "failed"
    assert verdict.failure_reason is not GoalFailureReason.SEARCH_EXHAUSTED


@pytest.mark.parametrize("fault", ["control", "still_encountered"])
def test_discovery_does_not_swallow_unexpected_search_errors(fault):
    reader = _Reader(raw=_raw(), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)

    class BrokenArea(_DiscoveryExecutor):
        def seek_encounter(self):
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            if fault == "still_encountered":
                self.encountered = red_species_ref(9)
            raise RedAreaExecutionError("not a safe miss", reason_code=(
                "control_failed" if fault == "control" else "survey_leg_limit_exceeded"
            ))

    provider = RedEncounterDiscoveryGoalProvider(
        "wild:Route1:grass", BrokenArea(reader, actions), actions, port, _adapter(reader),
    )
    offer = provider.offer(provider.adapter.observe())
    assert offer.binding is not None
    with pytest.raises(RedAreaExecutionError, match="not a safe miss"):
        offer.binding.execute()


def test_box_switch_provider_requires_and_verifies_more_active_headroom(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    reader = _Reader(raw=_raw(), ready=True)
    raw = reader.raw
    reader.raw = replace(
        raw,
        party_count=6,
        party_species_ids=raw.party_species_ids * 6,
        party_levels=raw.party_levels * 6,
        party_hp=raw.party_hp * 6,
        party_max_hp=raw.party_max_hp * 6,
        party_status=raw.party_status * 6,
        party_moves=raw.party_moves * 6,
        party_pp=raw.party_pp * 6,
    )
    boxes = list(reader.boxes.boxes)
    boxes[0] = RedCurrentBoxState(0, (0x1C,) * 19, (55,) * 19)
    reader.boxes = RedBoxCollectionState(tuple(boxes), 0, True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills.open_bills_pc",
        lambda _actions, _reader: None,
    )

    def perform_switch(
        received_actions,
        _reader,
        *,
        target_box_index: int,
    ):  # type: ignore[no-untyped-def]
        received_actions.execute(MacroAction(MacroActionKind.WAIT))
        reader.boxes = RedBoxCollectionState(reader.boxes.boxes, target_box_index, True)
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills.switch_box",
        perform_switch,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills._close_menus",
        lambda _actions, _reader, _timing: None,
    )
    provider = RedBoxSwitchGoalProvider(
        target_box_index=1,
        pc_boundary=lambda _observation: True,
        actions=actions,
        reader=reader,  # type: ignore[arg-type]
        emulator=port,
        adapter=adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "succeeded"
    assert adapter.observe().immediate_capture_slots == 20


class _RouteWorld:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader
        self.frame_count = 0
        self.pressed_buttons = frozenset()
        self.at = (2, 3)

    def execute(self, action: MacroAction) -> MacroAction:
        self.frame_count += 1
        if action.kind is MacroActionKind.MOVE:
            assert action.value == "right"
            self.at = (3, 3)
            self.reader.raw = replace(self.reader.raw, player_x=3, player_y=3)
            self.reader.pokedex = RedPokedexState(
                self.reader.pokedex.owned_species,
                self.reader.pokedex.seen_species.union({10}),
            )
        return action

    def observe(self) -> TraversalSnapshot:
        return TraversalSnapshot(1, self.at, True)

    def read_u8(self, _address: int) -> int:
        return 0


def test_route_goal_executes_only_an_acknowledged_plan_and_verifies_terminal() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    world = _RouteWorld(reader)
    actions = CountingExecutor(world)
    adapter = _adapter(reader)
    edge = LocalEdge((3, 3), "right")
    plan = RoutePlan(
        macro_path=MacroPath((1,), ()),
        start_at=(2, 3),
        start_mode=None,
        segments=(),
        terminal_approach=LocalPath(
            ((2, 3), (3, 3)),
            (edge,),
            (None, None),
        ),
        terminal_at=(3, 3),
        terminal_mode=None,
    )
    provider = RedRouteGoalProvider(
        destination_ref="local-unseen-boundary",
        plan=plan,
        actions=actions,
        traversal_observer=world,
        emulator=world,
        adapter=adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "succeeded"
    assert report.evidence["acknowledged_steps"] == 1
    assert world.at == (3, 3)


@dataclass
class _ProgressAdapter:
    current: object
    graph: QuestGraph

    def observe(self):  # type: ignore[no-untyped-def]
        return self.current


@pytest.mark.parametrize(
    "kind",
    (
        GoalKind.DEVELOP_TEAM,
        GoalKind.EVOLVE_SPECIES,
        GoalKind.RESTORE_TEAM,
        GoalKind.RESUPPLY,
        GoalKind.EXPLORE,
    ),
)
def test_progress_provider_requires_fresh_semantic_improvement(kind: GoalKind) -> None:
    reader = _Reader(raw=_raw(), ready=True)
    before = _adapter(reader).observe()
    evidence = before.evidence
    if kind is GoalKind.DEVELOP_TEAM:
        after_evidence = replace(
            evidence,
            team_readiness=min(1.0, evidence.team_readiness + 0.1),
        )
    elif kind is GoalKind.EVOLVE_SPECIES:
        after_evidence = replace(
            evidence,
            evolution=CompletionProgress(
                evidence.evolution.completed + 1,
                evidence.evolution.target,
            ),
        )
    elif kind is GoalKind.RESTORE_TEAM:
        evidence = replace(evidence, safety=0.5)
        before = replace(before, evidence=evidence)
        after_evidence = replace(evidence, safety=1.0)
    elif kind is GoalKind.RESUPPLY:
        after_evidence = replace(evidence, resources=0.5)
    else:
        after_evidence = replace(
            evidence,
            world_knowledge=CompletionProgress(
                evidence.world_knowledge.completed + 1,
                evidence.world_knowledge.target,
            ),
        )
    after = replace(before, evidence=after_evidence)
    adapter = _ProgressAdapter(before, _graph())

    def execute() -> GoalExecutionReport:
        adapter.current = after
        return GoalExecutionReport(1, 1, {"bounded": True})

    provider = RedProgressGoalProvider(
        kind=kind,
        binding_ref=f"pokemon.red:test:{kind.value}",
        adapter=adapter,  # type: ignore[arg-type]
        boundary=lambda _observation: RedGoalSkillAvailability.available(),
        executor=execute,
        estimated_effort=0.1,
        estimated_risk=0.1,
    )

    offer = provider.offer(before)
    assert offer.binding is not None
    assert offer.binding.verify(offer.binding.execute()).status.value == "succeeded"


def test_red_encounter_source_development_offer_is_action_free_and_verified() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    adapter = _adapter(reader)
    executions = 0

    def execute() -> GoalExecutionReport:
        nonlocal executions
        executions += 1
        reader.raw = replace(reader.raw, party_levels=(56,))
        return GoalExecutionReport(3, 90, {"bounded": True, "completed_battles": 1})

    provider = RedEncounterSourceDevelopmentGoalProvider(
        source_ref="encounter-source-fixture",
        binding_ref="pokemon.red:development:encounter-source-fixture",
        adapter=adapter,
        boundary=lambda _observation: RedGoalSkillAvailability.available(),
        executor=execute,
    )

    offer = provider.offer(adapter.observe())

    assert executions == 0
    assert offer.binding is not None
    assert offer.binding.kind is GoalKind.DEVELOP_TEAM
    verdict = offer.binding.verify(offer.binding.execute())
    assert executions == 1
    assert verdict.status.value == "succeeded"


def test_red_encounter_source_development_preserves_unavailable_boundary() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    adapter = _adapter(reader)
    provider = RedEncounterSourceDevelopmentGoalProvider(
        source_ref="encounter-source-fixture",
        binding_ref="pokemon.red:development:encounter-source-fixture",
        adapter=adapter,
        boundary=lambda _observation: RedGoalSkillAvailability.unavailable(
            GoalUnavailableReason.MISSING_CAPABILITY
        ),
        executor=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is None
    assert offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY


@pytest.mark.parametrize("invalid_boundary", (None, True, "available"))
def test_red_encounter_source_development_rejects_invalid_boundary_evidence(
    invalid_boundary: object,
) -> None:
    reader = _Reader(raw=_raw(), ready=True)
    adapter = _adapter(reader)
    provider = RedEncounterSourceDevelopmentGoalProvider(
        source_ref="encounter-source-fixture",
        binding_ref="pokemon.red:development:encounter-source-fixture",
        adapter=adapter,
        boundary=lambda _observation: invalid_boundary,  # type: ignore[arg-type,return-value]
        executor=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
    )

    with pytest.raises(RedGoalSkillError, match="invalid boundary evidence"):
        provider.offer(adapter.observe())


def test_red_encounter_source_development_rejects_invalid_fresh_boundary() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    adapter = _adapter(reader)
    boundary_calls = 0

    def boundary(_observation: object) -> RedGoalSkillAvailability | object:
        nonlocal boundary_calls
        boundary_calls += 1
        if boundary_calls == 1:
            return RedGoalSkillAvailability.available()
        return "invalid-fresh-boundary"

    provider = RedEncounterSourceDevelopmentGoalProvider(
        source_ref="encounter-source-fixture",
        binding_ref="pokemon.red:development:encounter-source-fixture",
        adapter=adapter,
        boundary=boundary,  # type: ignore[arg-type]
        executor=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
    )
    offer = provider.offer(adapter.observe())
    assert offer.binding is not None

    with pytest.raises(RedGoalSkillError, match="invalid fresh boundary evidence"):
        offer.binding.verify(offer.binding.execute())
