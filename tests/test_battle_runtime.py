from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_policy import choose_cerulean_rival_move_slot
from pokemon_red_completion.battle_runtime import (
    BattleRuntimeError,
    BattleRuntimeTimeoutError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.observation import (
    BULBASAUR_SPECIES_ID,
    PIDGEOTTO_SPECIES_ID,
    TACKLE_MOVE_ID,
    WATER_GUN_MOVE_ID,
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    MapId,
    RawGameState,
)

READY = InputReadiness(0, 0, 0, 0, 0, 0)
NOT_READY = InputReadiness(1, 0, 0, 0, 0, 0)
TAIL_WHIP_MOVE_ID = 0x27
BUBBLE_MOVE_ID = 0x91
DIG_MOVE_ID = 0x5B


def _raw(
    *,
    map_id: int = MapId.CERULEAN_CITY,
    battle_state: int | None = 2,
    party_count: int | None = 1,
    hp: int | None = 26,
    enemy_species_id: int | None = PIDGEOTTO_SPECIES_ID,
    enemy_hp: int | None = 20,
    moves: tuple[int, ...] | None = (
        TACKLE_MOVE_ID,
        TAIL_WHIP_MOVE_ID,
        BUBBLE_MOVE_ID,
        WATER_GUN_MOVE_ID,
    ),
    pp: tuple[int, ...] | None = (35, 30, 30, 11),
    player_attack_stage: int | None = 7,
    player_accuracy_stage: int | None = 7,
    enemy_defense_stage: int | None = 6,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=21,
        player_y=6,
        party_count=party_count,
        battle_state=battle_state,
        party_species_ids=(0xB3,) if party_count else (),
        first_party_hp=hp,
        first_party_max_hp=49,
        first_party_status=0,
        first_party_moves=moves,
        first_party_pp=pp,
        enemy_species_id=enemy_species_id,
        enemy_hp=enemy_hp,
        player_attack_stage=player_attack_stage,
        player_accuracy_stage=player_accuracy_stage,
        enemy_defense_stage=enemy_defense_stage,
    )


class FakeRuntime:
    def __init__(
        self,
        *,
        raw: RawGameState | None = None,
        menu: BattleMenuState | None = None,
        controls: InputReadiness = NOT_READY,
        on_action: Callable[[MacroAction], None] | None = None,
    ) -> None:
        self.raw = raw or _raw()
        self.menu = menu or BattleMenuState(
            BattleMenuPhase.MAIN,
            selected_main_command=0,
        )
        self.controls = controls
        self.on_action = on_action
        self.actions: list[MacroAction] = []

    def read(self) -> RawGameState:
        return self.raw

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        assert raw is self.raw
        return self.menu

    def read_input_readiness(self) -> InputReadiness:
        return self.controls

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if self.on_action is not None:
            self.on_action(action)


def test_runtime_rejects_selected_slot_when_required_move_id_differs() -> None:
    runtime = FakeRuntime()

    def expose_move_menu(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )

    runtime.on_action = expose_move_menu

    with pytest.raises(BattleRuntimeError, match="selected move id"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            required_move_id=DIG_MOVE_ID,
        )

    assert runtime.raw.first_party_pp == (35, 30, 30, 11)


class AdaptiveRivalSimulation(FakeRuntime):
    """Two-opponent battle with bounded dialogue and post-battle cleanup."""

    def __init__(
        self,
        *,
        first_main_command: int = 0,
        between_opponent_dialogues: int = 3,
        completion_dialogues: int = 2,
    ) -> None:
        super().__init__(
            menu=BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=first_main_command,
            )
        )
        self.between_opponent_dialogues = between_opponent_dialogues
        self.completion_dialogues = completion_dialogues
        self.defeated_opponents = 0
        self.bulbasaur_tail_whipped = False

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.MOVE:
            self._move_cursor(str(action.value))
            return
        if action.kind is not MacroActionKind.CONFIRM:
            raise AssertionError(f"controller emitted unsupported action {action.kind}")

        if self.raw.battle_state == 0:
            self.completion_dialogues -= 1
            if self.completion_dialogues <= 0:
                self.controls = READY
            return
        if self.menu.phase is BattleMenuPhase.MAIN:
            assert self.menu.selected_main_command == 0
            self.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if self.menu.phase is BattleMenuPhase.MOVE:
            slot = self.menu.selected_move_slot
            assert slot is not None
            pp = list(self.raw.first_party_pp or ())
            pp[slot - 1] -= 1
            self.raw = replace(self.raw, first_party_pp=tuple(pp))
            if (
                self.raw.enemy_species_id == BULBASAUR_SPECIES_ID
                and slot == 2
                and not self.bulbasaur_tail_whipped
            ):
                self.bulbasaur_tail_whipped = True
                self.raw = replace(self.raw, enemy_defense_stage=6)
                self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
                self.between_opponent_dialogues = 1
                return
            self.defeated_opponents += 1
            self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            if self.defeated_opponents == 2:
                self.raw = replace(self.raw, battle_state=0)
            return

        if self.defeated_opponents == 1:
            self.between_opponent_dialogues -= 1
            if self.between_opponent_dialogues <= 0:
                self.raw = replace(
                    self.raw,
                    enemy_species_id=BULBASAUR_SPECIES_ID,
                    enemy_hp=20,
                    player_attack_stage=6,
                    enemy_defense_stage=(
                        self.raw.enemy_defense_stage if self.bulbasaur_tail_whipped else 7
                    ),
                )
                self.menu = BattleMenuState(
                    BattleMenuPhase.MAIN,
                    selected_main_command=0,
                )

    def _move_cursor(self, direction: str) -> None:
        if self.menu.phase is BattleMenuPhase.MAIN:
            command = self.menu.selected_main_command
            command = {
                (1, "up"): 0,
                (2, "left"): 0,
                (3, "up"): 2,
            }.get((command, direction), command)
            self.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=command,
            )
            return
        if self.menu.phase is BattleMenuPhase.MOVE:
            slot = self.menu.selected_move_slot
            assert slot is not None
            slot += 1 if direction == "down" else -1
            self.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=slot,
            )


class SleepRecoverySimulation(FakeRuntime):
    def __init__(self, *, sleep_dialogue_pulses: int = 0) -> None:
        super().__init__()
        self.sleep_started = False
        self.sleep_dialogue_pulses = sleep_dialogue_pulses

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.CANCEL:
            assert self.menu.phase is BattleMenuPhase.MOVE
            self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
            return
        if action.kind is not MacroActionKind.CONFIRM:
            raise AssertionError(f"unsupported sleep simulation action {action.kind}")
        if self.raw.battle_state == 0:
            self.controls = READY
            return
        if self.menu.phase is BattleMenuPhase.MAIN:
            if not self.sleep_started:
                self.sleep_started = True
                self.raw = replace(self.raw, first_party_status=4)
                self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            else:
                self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        if self.menu.phase is BattleMenuPhase.UNKNOWN:
            if self.sleep_dialogue_pulses:
                self.sleep_dialogue_pulses -= 1
                return
            count = (self.raw.first_party_status or 0) & 0x07
            next_count = 1 if count == 4 else 0
            self.raw = replace(self.raw, first_party_status=next_count)
            if next_count == 0:
                self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        pp = list(self.raw.first_party_pp or ())
        pp[0] -= 1
        self.raw = replace(self.raw, first_party_pp=tuple(pp), battle_state=0, enemy_hp=0)
        self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)


class OffSlotSleepPPSimulation(SleepRecoverySimulation):
    def execute(self, action: MacroAction) -> None:
        recovering = (
            action.kind is MacroActionKind.CONFIRM
            and self.menu.phase is BattleMenuPhase.UNKNOWN
            and bool((self.raw.first_party_status or 0) & 0x07)
        )
        super().execute(action)
        if recovering:
            pp = list(self.raw.first_party_pp or ())
            pp[3] -= 1
            self.raw = replace(self.raw, first_party_pp=tuple(pp))


def _non_wait_actions(runtime: FakeRuntime) -> list[MacroAction]:
    return [action for action in runtime.actions if action.kind is not MacroActionKind.WAIT]


def test_adaptive_controller_recovers_a_decreasing_sleep_counter() -> None:
    runtime = SleepRecoverySimulation()

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert final.first_party_pp == (34, 30, 30, 11)
    assert MacroAction(MacroActionKind.CANCEL) in runtime.actions


def test_adaptive_controller_bounds_but_survives_a_long_sing_sequence() -> None:
    runtime = SleepRecoverySimulation(sleep_dialogue_pulses=30)

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert final.first_party_pp == (34, 30, 30, 11)
    assert runtime.sleep_dialogue_pulses == 0


def test_sleep_recovery_rejects_an_off_slot_pp_decrement() -> None:
    runtime = OffSlotSleepPPSimulation()

    with pytest.raises(BattleRuntimeError, match="off-slot PP"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
        )


def test_adaptive_controller_rechecks_species_and_switches_water_gun_to_tackle() -> None:
    runtime = AdaptiveRivalSimulation()
    policy_species: list[int | None] = []

    def policy(raw: RawGameState) -> int:
        policy_species.append(raw.enemy_species_id)
        return choose_cerulean_rival_move_slot(raw)

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert policy_species == [
        PIDGEOTTO_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
    ]
    assert final.battle_state == 0
    assert final.first_party_hp == 26
    assert final.first_party_pp == (34, 29, 30, 10)
    moves = [
        action.value for action in _non_wait_actions(runtime) if action.kind is MacroActionKind.MOVE
    ]
    assert moves == ["down", "down", "down", "down"]
    assert runtime.controls.ready
    assert runtime.actions[-1] == MacroAction(MacroActionKind.WAIT)
    assert {action.kind for action in runtime.actions} <= {
        MacroActionKind.MOVE,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
    }


def test_policy_is_called_once_while_main_cursor_moves_to_fight() -> None:
    runtime = AdaptiveRivalSimulation(first_main_command=3)
    policy_species: list[int | None] = []

    def policy(raw: RawGameState) -> int:
        policy_species.append(raw.enemy_species_id)
        return choose_cerulean_rival_move_slot(raw)

    run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert policy_species == [
        PIDGEOTTO_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
    ]
    assert [action.value for action in _non_wait_actions(runtime)[:2]] == ["up", "left"]


def test_unknown_semantic_screens_survive_level_up_and_move_learning_dialogue() -> None:
    runtime = AdaptiveRivalSimulation(
        between_opponent_dialogues=6,
        completion_dialogues=4,
    )

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        choose_cerulean_rival_move_slot,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert runtime.defeated_opponents == 2
    assert sum(action.kind is MacroActionKind.CONFIRM for action in runtime.actions) >= 14


@pytest.mark.parametrize("slot", [0, 5, True])
def test_invalid_policy_slot_fails_before_opening_fight(slot: int) -> None:
    runtime = FakeRuntime()

    with pytest.raises(BattleRuntimeError, match="invalid one-based slot"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: slot,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


def test_policy_exception_fails_without_pressing_through() -> None:
    runtime = FakeRuntime()

    def rejecting_policy(_raw: RawGameState) -> int:
        raise ValueError("unsupported enemy")

    with pytest.raises(BattleRuntimeError, match="policy rejected"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            rejecting_policy,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


def test_transient_main_menu_with_zero_enemy_hp_never_calls_policy() -> None:
    calls = 0
    runtime = FakeRuntime(raw=_raw(enemy_hp=0))

    def finish_transition(action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.controls = READY

    runtime.on_action = finish_transition

    def policy(_raw: RawGameState) -> int:
        nonlocal calls
        calls += 1
        return 1

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert calls == 0
    assert final.battle_state == 0
    assert runtime.actions
    assert all(action.kind is MacroActionKind.WAIT for action in runtime.actions)


def test_stale_main_after_pp_decrement_uses_cancel_without_spending_twice() -> None:
    runtime = FakeRuntime()
    policy_calls = 0

    def resolve_stale_main(action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.CONFIRM and runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if action.kind is MacroActionKind.CONFIRM and runtime.menu.phase is BattleMenuPhase.MOVE:
            pp = list(runtime.raw.first_party_pp or ())
            pp[0] -= 1
            runtime.raw = replace(runtime.raw, first_party_pp=tuple(pp))
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=0,
            )
            return
        if action.kind is MacroActionKind.CANCEL:
            runtime.raw = replace(runtime.raw, enemy_hp=10)
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            return
        if action.kind is MacroActionKind.CONFIRM and runtime.menu.phase is BattleMenuPhase.UNKNOWN:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.controls = READY

    runtime.on_action = resolve_stale_main

    def policy(_raw: RawGameState) -> int:
        nonlocal policy_calls
        policy_calls += 1
        return 1

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert policy_calls == 1
    assert final.first_party_pp == (34, 30, 30, 11)
    non_wait = _non_wait_actions(runtime)
    assert MacroAction(MacroActionKind.CANCEL) in non_wait
    assert sum(action.kind is MacroActionKind.CONFIRM for action in non_wait) == 3


def test_main_menu_requires_live_enemy_hp_evidence() -> None:
    runtime = FakeRuntime(raw=_raw(enemy_hp=None))

    with pytest.raises(BattleRuntimeError, match="enemy HP evidence"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (_raw(moves=(0, TAIL_WHIP_MOVE_ID, BUBBLE_MOVE_ID, WATER_GUN_MOVE_ID)), "move evidence"),
        (_raw(pp=None), "lacks PP evidence"),
        (_raw(pp=(0, 30, 30, 11)), "no usable PP"),
    ],
)
def test_policy_choice_requires_move_and_usable_pp_evidence(
    raw: RawGameState,
    message: str,
) -> None:
    runtime = FakeRuntime(raw=raw)

    with pytest.raises(BattleRuntimeError, match=message):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


def test_attack_requires_persistent_pp_decrement() -> None:
    runtime = FakeRuntime()

    def ignore_attack(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM and runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )

    runtime.on_action = ignore_attack
    timing = replace(
        BattleRuntimeTiming(),
        max_pp_confirmation_pulses=3,
        max_attack_confirmation_pulses=2,
    )

    with pytest.raises(BattleRuntimeError, match="PP-decrement gate"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            timing=timing,
        )

    confirms = [action for action in runtime.actions if action.kind is MacroActionKind.CONFIRM]
    assert len(confirms) == 3


def test_attack_rejects_pp_change_larger_than_one() -> None:
    runtime = FakeRuntime()

    def spend_two_pp(action: MacroAction) -> None:
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if runtime.menu.phase is BattleMenuPhase.MOVE:
            pp = list(runtime.raw.first_party_pp or ())
            pp[0] -= 2
            runtime.raw = replace(runtime.raw, first_party_pp=tuple(pp))
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)

    runtime.on_action = spend_two_pp

    with pytest.raises(BattleRuntimeError, match="invalid amount"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )


def test_faster_enemy_attack_text_is_confirmed_until_latched_move_spends_pp() -> None:
    runtime = FakeRuntime()
    opponent_text_pulses = 2

    def resolve_opponent_first_turn(action: MacroAction) -> None:
        nonlocal opponent_text_pulses
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if runtime.menu.phase is BattleMenuPhase.MOVE:
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            return
        opponent_text_pulses -= 1
        if opponent_text_pulses == 0:
            runtime.raw = replace(
                runtime.raw,
                battle_state=0,
                first_party_pp=(34, 30, 30, 11),
            )
            runtime.controls = READY

    runtime.on_action = resolve_opponent_first_turn
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=replace(BattleRuntimeTiming(), required_ready_reads=1),
    )

    assert final.first_party_pp == (34, 30, 30, 11)
    assert opponent_text_pulses == 0
    assert [
        action.kind for action in runtime.actions if action.kind is MacroActionKind.CONFIRM
    ] == [MacroActionKind.CONFIRM] * 4


def test_pp_proof_waits_out_delayed_move_menu_without_confirming_twice() -> None:
    runtime = FakeRuntime()
    delayed_waits = 0

    def delay_menu_cleanup(action: MacroAction) -> None:
        nonlocal delayed_waits
        if action.kind is MacroActionKind.CONFIRM:
            if runtime.menu.phase is BattleMenuPhase.MAIN:
                runtime.menu = BattleMenuState(
                    BattleMenuPhase.MOVE,
                    selected_move_slot=1,
                )
                return
            if runtime.menu.phase is BattleMenuPhase.MOVE:
                runtime.raw = replace(
                    runtime.raw,
                    first_party_pp=(34, 30, 30, 11),
                )
                return
        if (
            action.kind is MacroActionKind.WAIT
            and runtime.menu.phase is BattleMenuPhase.MOVE
            and runtime.raw.first_party_pp == (34, 30, 30, 11)
        ):
            delayed_waits += 1
            if delayed_waits == 3:
                runtime.raw = replace(runtime.raw, battle_state=0)
                runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
                runtime.controls = READY

    runtime.on_action = delay_menu_cleanup
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=replace(BattleRuntimeTiming(), required_ready_reads=1),
    )

    assert final.battle_state == 0
    assert delayed_waits == 3
    assert sum(action.kind is MacroActionKind.CONFIRM for action in runtime.actions) == 2


def test_last_pp_can_be_spent_when_decrement_reaches_zero() -> None:
    runtime = FakeRuntime(raw=_raw(pp=(1, 30, 30, 11)))

    def finish_on_attack(action: MacroAction) -> None:
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if runtime.menu.phase is BattleMenuPhase.MOVE:
            runtime.raw = replace(
                runtime.raw,
                battle_state=0,
                first_party_pp=(0, 30, 30, 11),
            )
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            runtime.controls = READY

    runtime.on_action = finish_on_attack
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=replace(BattleRuntimeTiming(), required_ready_reads=1),
    )

    assert final.first_party_pp == (0, 30, 30, 11)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (_raw(battle_state=1), "wild battle"),
        (_raw(battle_state=0), "must start"),
        (_raw(map_id=MapId.ROUTE_24), "left expected map"),
        (_raw(hp=0), "party lead fainted"),
        (_raw(party_count=0, hp=None), "lacks living party-lead evidence"),
    ],
)
def test_initial_gate_fails_closed(
    raw: RawGameState,
    message: str,
) -> None:
    runtime = FakeRuntime(raw=raw)

    with pytest.raises(BattleRuntimeError, match=message):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"battle_state": 1}, "wild battle"),
        ({"map_id": MapId.ROUTE_24}, "left expected map"),
        ({"first_party_hp": 0}, "party lead fainted"),
    ],
)
def test_runtime_gate_rechecks_wild_map_and_hp_after_every_pulse(
    replacement: dict[str, int | MapId],
    message: str,
) -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.UNKNOWN))

    def corrupt_after_confirm(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM:
            runtime.raw = replace(runtime.raw, **replacement)

    runtime.on_action = corrupt_after_confirm

    with pytest.raises(BattleRuntimeError, match=message):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )


@pytest.mark.parametrize(
    "menu",
    [
        BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=9),
        BattleMenuState(
            BattleMenuPhase.MAIN,
            selected_main_command=0,
            selected_move_slot=1,
        ),
        BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=0),
        BattleMenuState(
            BattleMenuPhase.UNKNOWN,
            selected_main_command=0,
        ),
    ],
)
def test_invalid_semantic_menu_fails_closed(menu: BattleMenuState) -> None:
    runtime = FakeRuntime(menu=menu)

    with pytest.raises(BattleRuntimeError, match="invalid semantic battle menu"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


def test_unlatched_move_menu_is_cancelled_before_policy_or_pp_change() -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1))
    policy_observations: list[tuple[BattleMenuPhase, tuple[int, ...] | None]] = []

    def on_action(action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.CANCEL:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=0,
            )
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        pp = list(runtime.raw.first_party_pp or ())
        pp[0] -= 1
        runtime.raw = replace(
            runtime.raw,
            battle_state=0,
            enemy_hp=0,
            first_party_pp=tuple(pp),
        )
        runtime.controls = READY

    runtime.on_action = on_action

    def policy(raw: RawGameState) -> int:
        policy_observations.append((runtime.menu.phase, raw.first_party_pp))
        return 1

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert policy_observations == [(BattleMenuPhase.MAIN, (35, 30, 30, 11))]
    non_wait = _non_wait_actions(runtime)
    assert non_wait[0] == MacroAction(MacroActionKind.CANCEL)
    assert final.first_party_pp == (34, 30, 30, 11)


def test_unknown_menu_is_bounded_dialogue_not_unbounded_button_spam() -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.UNKNOWN))
    timing = replace(BattleRuntimeTiming(), max_runtime_pulses=3)

    with pytest.raises(BattleRuntimeTimeoutError, match="bounded runtime pulses"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            timing=timing,
        )

    assert [action.kind for action in runtime.actions] == [
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CANCEL,
        MacroActionKind.WAIT,
    ]


def test_status_suppressed_turn_can_return_without_spending_pp() -> None:
    runtime = FakeRuntime(raw=replace(_raw(), first_party_status=0x40))
    confirmations = 0

    def suppress_then_finish(action: MacroAction) -> None:
        nonlocal confirmations
        if action.kind is not MacroActionKind.CONFIRM:
            return
        confirmations += 1
        if confirmations == 1:
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        else:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.controls = READY

    runtime.on_action = suppress_then_finish
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert final.first_party_pp == (35, 30, 30, 11)


def test_completion_rechecks_living_lead_before_returning() -> None:
    runtime = FakeRuntime(
        raw=_raw(battle_state=0, hp=0),
        controls=READY,
    )

    with pytest.raises(BattleRuntimeError, match="party lead fainted"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dialogue_wait_frames", 0),
        ("max_runtime_pulses", False),
        ("required_ready_reads", -1),
    ],
)
def test_timing_requires_positive_integer_fields(field: str, value: int) -> None:
    with pytest.raises(ValueError, match=field):
        BattleRuntimeTiming(**{field: value})


@pytest.mark.parametrize("expected_map", [-1, 0x100, True])
def test_expected_map_requires_an_unsigned_byte(expected_map: int) -> None:
    runtime = FakeRuntime()

    with pytest.raises(ValueError, match="unsigned one-byte"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=expected_map,
        )
