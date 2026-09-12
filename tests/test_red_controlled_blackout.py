from __future__ import annotations

from dataclasses import replace

import pytest

import pokemon_red_completion.red_controlled_blackout as controlled
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import execute_observed_trainer_move
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    RawGameState,
)

READY = InputReadiness(0, 0, 0, 0, 0)
NOT_READY = InputReadiness(1, 0, 0, 0, 0)
MAP = 120
ANCHOR = 5
IDENTITY = (243, 43, 2)


def state(**changes: object) -> RawGameState:
    values: dict[str, object] = {
        "game_started": True,
        "map_id": MAP,
        "player_x": 3,
        "player_y": 4,
        "party_count": 2,
        "battle_state": 2,
        "badge_bits": 255,
        "bag_item_ids": (4,),
        "bag_items": ((4, 7),),
        "event_flags": bytes(range(16)),
        "party_species_ids": (1, 2),
        "party_levels": (50, 40),
        "party_hp": (40, 30),
        "party_max_hp": (40, 30),
        "party_status": (0, 0),
        "party_moves": ((45, 33, 0, 0), (45, 33, 0, 0)),
        "party_pp": ((10, 20, 0, 0), (11, 19, 0, 0)),
        "first_party_level": 50,
        "first_party_hp": 40,
        "first_party_max_hp": 40,
        "first_party_status": 0,
        "first_party_moves": (45, 33, 0, 0),
        "first_party_pp": (10, 20, 0, 0),
        "enemy_species_id": 3,
        "enemy_hp": 65,
        "enemy_level": 65,
        "enemy_max_hp": 200,
        "active_party_index": 0,
        "active_party_species_id": 1,
        "active_party_level": 50,
        "active_party_hp": 40,
        "active_party_max_hp": 40,
        "active_party_status": 0,
        "active_party_moves": (45, 33, 0, 0),
        "active_party_pp": (10, 20, 0, 0),
        "player_money": 101,
    }
    values.update(changes)
    return RawGameState(**values)  # type: ignore[arg-type]


class Reader:
    def __init__(self, raw: RawGameState | None = None) -> None:
        self.raw = raw or state()
        self.anchor = ANCHOR
        self.identity = IDENTITY

    def read(self) -> RawGameState:
        return self.raw

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        assert raw is self.raw
        return BattleMenuState(
            BattleMenuPhase.MAIN if raw.battle_state == 2 else BattleMenuPhase.UNKNOWN,
            selected_main_command=0 if raw.battle_state == 2 else None,
        )

    def read_active_trainer_identity(self) -> tuple[int, int, int]:
        return self.identity

    def read_last_blackout_map(self) -> int:
        return self.anchor

    def read_input_readiness(self) -> InputReadiness:
        return READY if self.raw.battle_state == 0 else NOT_READY


class Emulator:
    frame_count = 0
    pressed_buttons: frozenset[str] = frozenset()

    def read_u8(self, _address: int) -> int:
        return 0


class Executor:
    def __init__(self, reader: Reader, emulator: Emulator) -> None:
        self.reader = reader
        self.emulator = emulator
        self.actions: list[MacroAction] = []

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        self.emulator.frame_count += max(1, action.repeat)
        if (
            action.kind is MacroActionKind.CONFIRM
            and self.reader.raw.battle_state == 2
            and not any(self.reader.raw.party_hp or ())
        ):
            self.reader.raw = final_state(self.reader.raw)
        return object()


def final_state(raw: RawGameState, *, map_id: int = ANCHOR) -> RawGameState:
    return replace(
        raw,
        map_id=map_id,
        battle_state=0,
        party_hp=raw.party_max_hp,
        party_status=(0, 0),
        party_pp=((40, 35, 0, 0), (40, 35, 0, 0)),
        first_party_hp=40,
        first_party_pp=(40, 35, 0, 0),
        active_party_index=None,
        active_party_species_id=None,
        active_party_level=None,
        active_party_hp=None,
        active_party_max_hp=None,
        active_party_status=None,
        active_party_moves=None,
        active_party_pp=None,
        player_money=50,
    )


def test_binding_is_action_free_and_changed_origin_is_claimed_before_input() -> None:
    reader, emulator = Reader(), Emulator()
    executor = Executor(reader, emulator)
    binding = controlled.bind_red_controlled_blackout(reader)
    assert emulator.frame_count == 0
    reader.raw = replace(reader.raw, player_money=100)
    with pytest.raises(controlled.RedControlledBlackoutError, match="origin changed"):
        controlled.execute_red_controlled_blackout(binding, reader, emulator, executor)
    assert binding.claimed
    assert executor.actions == []
    with pytest.raises(controlled.RedControlledBlackoutError, match="already claimed"):
        controlled.execute_red_controlled_blackout(binding, reader, emulator, executor)


def test_minimum_damage_prefers_status_then_lowest_power_and_skips_disabled() -> None:
    assert controlled.choose_minimum_damage_slot(state()) == 1
    damaging = state(
        active_party_moves=(33, 57, 70, 0),
        active_party_pp=(20, 10, 15, 0),
    )
    assert controlled.choose_minimum_damage_slot(damaging) == 1
    disabled = replace(damaging, player_disabled_move_slot=1, player_disable_turns=2)
    assert controlled.choose_minimum_damage_slot(disabled) == 3


def test_public_observed_turn_admits_a_proven_player_faint() -> None:
    class TurnRuntime:
        def __init__(self) -> None:
            self.raw = state()
            self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)

        def read(self) -> RawGameState:
            return self.raw

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            assert raw is self.raw
            return self.menu

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.CONFIRM and self.menu.phase is BattleMenuPhase.MAIN:
                self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            elif action.kind is MacroActionKind.CONFIRM and self.menu.phase is BattleMenuPhase.MOVE:
                self.raw = replace(
                    self.raw,
                    party_hp=(0, 30),
                    first_party_hp=0,
                    party_pp=((9, 20, 0, 0), (11, 19, 0, 0)),
                    first_party_pp=(9, 20, 0, 0),
                    active_party_hp=0,
                    active_party_pp=(9, 20, 0, 0),
                )
                self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            return object()

    runtime = TurnRuntime()
    assert execute_observed_trainer_move(runtime, runtime, 1, expected_map=MAP)
    assert runtime.raw.active_party_hp == 0


def test_success_uses_forced_switch_and_verifies_odd_money_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, emulator = Reader(), Emulator()
    executor = Executor(reader, emulator)
    binding = controlled.bind_red_controlled_blackout(reader)

    def move(_reader, actions, slot, **_kwargs):
        actions.execute(MacroAction(MacroActionKind.WAIT))
        hp = list(reader.raw.party_hp or ())
        active = reader.raw.active_party_index or 0
        hp[active] = 0
        reader.raw = replace(
            reader.raw,
            party_hp=tuple(hp),
            first_party_hp=hp[0],
            active_party_hp=0,
        )
        return True

    def switch(_actions, _reader, _emulator, party_index, **_kwargs):
        hp = reader.raw.party_hp or ()
        reader.raw = replace(
            reader.raw,
            active_party_index=party_index,
            active_party_species_id=(reader.raw.party_species_ids or ())[party_index],
            active_party_level=(reader.raw.party_levels or ())[party_index],
            active_party_hp=hp[party_index],
            active_party_max_hp=(reader.raw.party_max_hp or ())[party_index],
            active_party_status=(reader.raw.party_status or ())[party_index],
            active_party_moves=(reader.raw.party_moves or ())[party_index],
            active_party_pp=(reader.raw.party_pp or ())[party_index],
        )

    monkeypatch.setattr(controlled, "execute_observed_trainer_move", move)
    monkeypatch.setattr(controlled, "switch_active_battler", switch)
    result = controlled.execute_red_controlled_blackout(binding, reader, emulator, executor)
    assert result.ending_money == 50
    assert result.forced_switches == (1,)
    assert result.moves_selected == (1, 1)
    assert result.public_dict()["training_examples"] == 0
    assert result.public_dict()["learned_battle_authority"] is False


def test_terminal_destination_or_resource_mutation_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, emulator = Reader(), Emulator()
    executor = Executor(reader, emulator)
    binding = controlled.bind_red_controlled_blackout(reader)

    def move(_reader, actions, _slot, **_kwargs):
        actions.execute(MacroAction(MacroActionKind.WAIT))
        reader.raw = replace(
            reader.raw,
            party_hp=(0, 0),
            first_party_hp=0,
            active_party_hp=0,
        )
        return True

    original_final = final_state

    def wrong_final(raw: RawGameState, *, map_id: int = ANCHOR) -> RawGameState:
        return replace(original_final(raw, map_id=99), bag_items=((4, 6),))

    monkeypatch.setattr(controlled, "execute_observed_trainer_move", move)
    monkeypatch.setitem(globals(), "final_state", wrong_final)
    with pytest.raises(controlled.RedControlledBlackoutError, match="terminal verification"):
        controlled.execute_red_controlled_blackout(binding, reader, emulator, executor)


def test_unexpected_victory_and_turn_bound_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    reader, emulator = Reader(), Emulator()
    executor = Executor(reader, emulator)
    binding = controlled.bind_red_controlled_blackout(reader)

    def victory(_reader, actions, _slot, **_kwargs):
        actions.execute(MacroAction(MacroActionKind.WAIT))
        reader.raw = replace(reader.raw, battle_state=0, enemy_hp=0)
        return True

    monkeypatch.setattr(controlled, "execute_observed_trainer_move", victory)
    with pytest.raises(controlled.RedControlledBlackoutError, match="unexpected victory"):
        controlled.execute_red_controlled_blackout(binding, reader, emulator, executor)

    reader2, emulator2 = Reader(), Emulator()
    executor2 = Executor(reader2, emulator2)
    binding2 = controlled.bind_red_controlled_blackout(reader2)
    monkeypatch.setattr(
        controlled,
        "execute_observed_trainer_move",
        lambda *_args, **_kwargs: True,
    )
    with pytest.raises(controlled.RedControlledBlackoutError, match="turn boundary"):
        controlled.execute_red_controlled_blackout(
            binding2,
            reader2,
            emulator2,
            executor2,
            maximum_turn_boundaries=1,
        )
