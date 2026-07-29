"""Closed-loop execution for adaptive, semantically observed trainer battles.

This module deliberately stays above :class:`FrameSafeExecutor`: it emits only
qualified macro-actions and consumes only the public semantic state exposed by
the revision-pinned observation adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    RawGameState,
)

_WILD_BATTLE_STATE = 1
_TRAINER_BATTLE_STATE = 2
_FIGHT_COMMAND = 0
_CURRENT_PP_MASK = 0x3F
_MIN_MOVE_SLOT = 1
_MAX_MOVE_SLOT = 4


class BattleActionExecutor(Protocol):
    """The macro-action surface provided by ``FrameSafeExecutor``."""

    def execute(self, action: MacroAction) -> object: ...


class BattleStateReader(Protocol):
    """Semantic subset of ``PokemonRedStateReader`` used by the controller."""

    def read(self) -> RawGameState: ...

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState: ...

    def read_input_readiness(self) -> InputReadiness: ...


class MoveSlotPolicy(Protocol):
    """A pure policy that chooses a one-based move slot from current evidence."""

    def __call__(self, state: RawGameState, /) -> int: ...


class BattleRuntimeError(RuntimeError):
    """Raised when a trainer battle loses required semantic evidence."""


class BattleRuntimeTimeoutError(BattleRuntimeError):
    """Raised when a battle does not finish inside its bounded pulse budget."""


@dataclass(frozen=True, slots=True)
class BattleRuntimeTiming:
    """Frame waits and finite retry budgets for one adaptive trainer battle."""

    dialogue_wait_frames: int = 180
    menu_wait_frames: int = 120
    attack_wait_frames: int = 180
    completion_wait_frames: int = 1
    max_runtime_pulses: int = 360
    max_main_navigation_pulses: int = 4
    max_move_menu_transition_pulses: int = 4
    max_move_navigation_pulses: int = 4
    max_pp_confirmation_pulses: int = 6
    max_attack_confirmation_pulses: int = 3
    max_post_attack_transition_pulses: int = 12
    max_sleep_recovery_pulses: int = 16
    required_ready_reads: int = 2

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_BATTLE_RUNTIME_TIMING = BattleRuntimeTiming()


def run_adaptive_trainer_battle(
    reader: BattleStateReader,
    executor: BattleActionExecutor,
    move_slot_policy: MoveSlotPolicy,
    *,
    expected_map: int,
    required_move_id: int | None = None,
    timing: BattleRuntimeTiming = DEFAULT_BATTLE_RUNTIME_TIMING,
    label: str = "trainer battle",
) -> RawGameState:
    """Finish one already-active trainer battle with semantic feedback.

    The policy is called exactly once for each newly observed main battle-menu
    turn. Its choice is latched while the controller moves to FIGHT, proves the
    requested move cursor, and proves that the selected move spent exactly one
    current PP. Unknown menu state is treated as dialogue between turns and
    after a cursor-proven attack confirmation, where bounded CONFIRM pulses
    cover opponent-first attack text, level-up text, and move-learning prompts.
    """

    if (
        not isinstance(expected_map, int)
        or isinstance(expected_map, bool)
        or not 0 <= expected_map <= 0xFF
    ):
        raise ValueError("expected_map must be an unsigned one-byte map id")
    if not isinstance(label, str) or not label:
        raise ValueError("label must be a non-empty string")
    if required_move_id is not None and (
        not isinstance(required_move_id, int)
        or isinstance(required_move_id, bool)
        or not 1 <= required_move_id <= 0xFF
    ):
        raise ValueError("required_move_id must be a non-zero one-byte move id")

    initial = reader.read()
    _require_present_state(initial, expected_map=expected_map, label=label)
    if initial.battle_state != _TRAINER_BATTLE_STATE:
        raise BattleRuntimeError(f"{label} must start in an active trainer battle.")

    ready_reads = 0
    for _ in range(timing.max_runtime_pulses):
        raw = reader.read()
        _require_present_state(raw, expected_map=expected_map, label=label)

        if raw.battle_state == 0:
            if reader.read_input_readiness().ready:
                ready_reads += 1
                if ready_reads >= timing.required_ready_reads:
                    return raw
                _wait(executor, timing.completion_wait_frames)
            else:
                ready_reads = 0
                _pulse(
                    executor,
                    MacroAction(MacroActionKind.CONFIRM),
                    timing.dialogue_wait_frames,
                )
            continue

        if raw.battle_state != _TRAINER_BATTLE_STATE:
            raise BattleRuntimeError(
                f"{label} changed to unsupported battle state {raw.battle_state!r}."
            )

        ready_reads = 0
        menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(
                executor,
                MacroAction(MacroActionKind.CONFIRM),
                timing.dialogue_wait_frames,
            )
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            initial_pp = raw.first_party_pp
            _pulse(
                executor,
                MacroAction(MacroActionKind.CANCEL),
                timing.menu_wait_frames,
            )
            normalized = reader.read()
            _require_active_trainer_state(
                normalized,
                expected_map=expected_map,
                label=label,
            )
            if normalized.first_party_pp != initial_pp:
                raise BattleRuntimeError(
                    f"{label} changed PP while normalizing an unlatched move menu."
                )
            normalized_menu = _validated_menu(
                reader.read_battle_menu_state(normalized),
                label=label,
            )
            if normalized_menu.phase is not BattleMenuPhase.MAIN:
                raise BattleRuntimeError(
                    f"{label} failed to cancel an unlatched move menu to MAIN."
                )
            continue
        if raw.enemy_hp is None:
            raise BattleRuntimeError(
                f"{label} lacks live enemy HP evidence at the MAIN menu."
            )
        if raw.enemy_hp <= 0:
            _wait(executor, timing.dialogue_wait_frames)
            continue

        slot = _choose_usable_slot(move_slot_policy, raw, label=label)
        initial_pp = _current_pp(raw, slot=slot, label=label)
        _execute_policy_turn(
            reader,
            executor,
            expected_map=expected_map,
            initial_raw=raw,
            initial_menu=menu,
            slot=slot,
            initial_pp=initial_pp,
            required_move_id=required_move_id,
            timing=timing,
            label=label,
        )

    raise BattleRuntimeTimeoutError(
        f"{label} exceeded {timing.max_runtime_pulses} bounded runtime pulses."
    )


def _execute_policy_turn(
    reader: BattleStateReader,
    executor: BattleActionExecutor,
    *,
    expected_map: int,
    initial_raw: RawGameState,
    initial_menu: BattleMenuState,
    slot: int,
    initial_pp: int,
    required_move_id: int | None,
    timing: BattleRuntimeTiming,
    label: str,
) -> None:
    raw = initial_raw
    menu = initial_menu

    for _ in range(timing.max_main_navigation_pulses + 1):
        if menu.phase is not BattleMenuPhase.MAIN:
            raise BattleRuntimeError(f"{label} lost the semantic main battle menu.")
        command = menu.selected_main_command
        if command == _FIGHT_COMMAND:
            break
        direction = {
            1: "up",
            2: "left",
            3: "up",
        }.get(command)
        if direction is None:
            raise BattleRuntimeError(f"{label} exposed an invalid main battle-menu command.")
        _pulse(
            executor,
            MacroAction(MacroActionKind.MOVE, direction),
            timing.menu_wait_frames,
        )
        raw = reader.read()
        _require_active_trainer_state(raw, expected_map=expected_map, label=label)
        menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
    else:
        raise BattleRuntimeError(f"{label} could not navigate to FIGHT inside its bound.")

    if menu.selected_main_command != _FIGHT_COMMAND:
        raise BattleRuntimeError(f"{label} could not navigate to FIGHT inside its bound.")

    _pulse(
        executor,
        MacroAction(MacroActionKind.CONFIRM),
        timing.menu_wait_frames,
    )
    move_menu: BattleMenuState | None = None
    for _ in range(timing.max_move_menu_transition_pulses):
        raw = reader.read()
        _require_active_trainer_state(raw, expected_map=expected_map, label=label)
        menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
        if menu.phase is BattleMenuPhase.MOVE:
            move_menu = menu
            break
        if (
            menu.phase is BattleMenuPhase.MAIN
            and menu.selected_main_command == _FIGHT_COMMAND
        ):
            _pulse(
                executor,
                MacroAction(MacroActionKind.CONFIRM),
                timing.menu_wait_frames,
            )
            continue
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _wait(executor, timing.menu_wait_frames)
            continue
        raise BattleRuntimeError(f"{label} exposed an invalid FIGHT-menu transition.")
    if move_menu is None:
        if _recover_sleep_transition(
            reader,
            executor,
            expected_map=expected_map,
            slot=slot,
            initial_pp=initial_pp,
            initial_pp_vector=initial_raw.first_party_pp,
            timing=timing,
            label=label,
        ):
            return
        raise BattleRuntimeError(f"{label} never exposed a semantic move menu.")

    menu = move_menu
    for _ in range(timing.max_move_navigation_pulses + 1):
        if menu.phase is not BattleMenuPhase.MOVE:
            raise BattleRuntimeError(f"{label} lost the semantic move menu.")
        selected_slot = menu.selected_move_slot
        if selected_slot == slot:
            break
        if selected_slot is None:
            raise BattleRuntimeError(f"{label} exposed an invalid move-menu cursor.")
        direction = "down" if selected_slot < slot else "up"
        _pulse(
            executor,
            MacroAction(MacroActionKind.MOVE, direction),
            timing.menu_wait_frames,
        )
        raw = reader.read()
        _require_active_trainer_state(raw, expected_map=expected_map, label=label)
        menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
    else:
        raise BattleRuntimeError(
            f"{label} could not select move slot {slot} inside its bound."
        )

    if menu.selected_move_slot != slot:
        raise BattleRuntimeError(
            f"{label} could not select move slot {slot} inside its bound."
        )
    if required_move_id is not None:
        moves = raw.first_party_moves
        if moves is None or len(moves) < slot or moves[slot - 1] != required_move_id:
            observed = None if moves is None or len(moves) < slot else moves[slot - 1]
            raise BattleRuntimeError(
                f"{label} selected move id {observed!r}, "
                f"expected {required_move_id:#04x} in slot {slot}."
            )
    _confirm_attack_with_pp_gate(
        reader,
        executor,
        expected_map=expected_map,
        initial_raw=initial_raw,
        slot=slot,
        initial_pp=initial_pp,
        timing=timing,
        label=label,
    )


def _confirm_attack_with_pp_gate(
    reader: BattleStateReader,
    executor: BattleActionExecutor,
    *,
    expected_map: int,
    initial_raw: RawGameState,
    slot: int,
    initial_pp: int,
    timing: BattleRuntimeTiming,
    label: str,
) -> None:
    confirmation_count = 1
    _pulse(
        executor,
        MacroAction(MacroActionKind.CONFIRM),
        timing.attack_wait_frames,
    )

    for _ in range(timing.max_pp_confirmation_pulses):
        raw = reader.read()
        _require_present_state(raw, expected_map=expected_map, label=label)
        current_pp = _current_pp(
            raw,
            slot=slot,
            label=label,
            require_usable=False,
        )
        if current_pp == initial_pp - 1:
            _await_selected_turn_effect(
                reader,
                executor,
                expected_map=expected_map,
                raw=raw,
                initial_raw=initial_raw,
                slot=slot,
                spent_pp=current_pp,
                timing=timing,
                label=label,
            )
            return
        if current_pp != initial_pp:
            raise BattleRuntimeError(
                f"{label} move slot {slot} changed PP by an invalid amount."
            )
        if raw.battle_state != _TRAINER_BATTLE_STATE:
            raise BattleRuntimeError(
                f"{label} ended without the required move-slot {slot} PP decrement."
            )

        menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
        if menu.phase is BattleMenuPhase.MOVE:
            if menu.selected_move_slot != slot:
                raise BattleRuntimeError(
                    f"{label} changed move cursor before its PP decrement."
                )
            if confirmation_count >= timing.max_attack_confirmation_pulses:
                break
            confirmation_count += 1
            _pulse(
                executor,
                MacroAction(MacroActionKind.CONFIRM),
                timing.attack_wait_frames,
            )
            continue
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(
                executor,
                MacroAction(MacroActionKind.CONFIRM),
                timing.attack_wait_frames,
            )
            continue
        raise BattleRuntimeError(
            f"{label} left move selection without its required PP decrement."
        )

    raise BattleRuntimeError(
        f"{label} failed its bounded move-slot {slot} PP-decrement gate."
    )


def _recover_sleep_transition(
    reader: BattleStateReader,
    executor: BattleActionExecutor,
    *,
    expected_map: int,
    slot: int,
    initial_pp: int,
    initial_pp_vector: tuple[int, ...] | None,
    timing: BattleRuntimeTiming,
    label: str,
) -> bool:
    """Recover only the Gen I sleep countdown that suppresses move selection."""

    raw = reader.read()
    sleep_count = (raw.first_party_status or 0) & 0x07
    if sleep_count == 0:
        return False

    previous_count = sleep_count
    saw_decrease = False
    for _ in range(timing.max_sleep_recovery_pulses):
        _require_active_trainer_state(raw, expected_map=expected_map, label=label)
        if (raw.first_party_hp or 0) <= 0:
            raise BattleRuntimeError(f"{label} fainted during sleep recovery.")
        if _current_pp(raw, slot=slot, label=label, require_usable=False) != initial_pp:
            raise BattleRuntimeError(
                f"{label} changed PP during sleep recovery without a selected attack."
            )
        if raw.first_party_pp != initial_pp_vector:
            raise BattleRuntimeError(
                f"{label} changed an off-slot PP value during sleep recovery."
            )

        _pulse(
            executor,
            MacroAction(MacroActionKind.CONFIRM),
            timing.dialogue_wait_frames,
        )
        raw = reader.read()
        current_count = (raw.first_party_status or 0) & 0x07
        if current_count == 0:
            menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
            if menu.phase is BattleMenuPhase.MOVE:
                _pulse(
                    executor,
                    MacroAction(MacroActionKind.CANCEL),
                    timing.menu_wait_frames,
                )
            return True
        if current_count > previous_count:
            raise BattleRuntimeError(
                f"{label} sleep counter increased during bounded recovery."
            )
        saw_decrease = saw_decrease or current_count < previous_count
        previous_count = current_count

    if not saw_decrease:
        raise BattleRuntimeError(
            f"{label} sleep counter never decreased during bounded recovery."
        )
    raise BattleRuntimeError(f"{label} exceeded its bounded sleep recovery.")


def _await_selected_turn_effect(
    reader: BattleStateReader,
    executor: BattleActionExecutor,
    *,
    expected_map: int,
    raw: RawGameState,
    initial_raw: RawGameState,
    slot: int,
    spent_pp: int,
    timing: BattleRuntimeTiming,
    label: str,
) -> None:
    """Latch one PP-proven turn until its semantic effect becomes observable."""

    saw_unknown = False
    for _ in range(timing.max_post_attack_transition_pulses):
        if raw.battle_state == 0:
            return
        if _selected_turn_effect_observed(initial_raw, raw):
            return
        menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            saw_unknown = True
            _pulse(
                executor,
                MacroAction(MacroActionKind.CONFIRM),
                timing.attack_wait_frames,
            )
        elif menu.phase is BattleMenuPhase.MAIN:
            if saw_unknown:
                return
            # A stale MAIN signature can appear immediately after PP is spent.
            # B cannot select FIGHT and therefore cannot spend a second PP.
            _pulse(
                executor,
                MacroAction(MacroActionKind.CANCEL),
                timing.attack_wait_frames,
            )
        else:
            _wait(executor, timing.attack_wait_frames)
        raw = reader.read()
        _require_present_state(raw, expected_map=expected_map, label=label)
        current_pp = _current_pp(
            raw,
            slot=slot,
            label=label,
            require_usable=False,
        )
        if current_pp != spent_pp:
            raise BattleRuntimeError(
                f"{label} changed move-slot {slot} PP after its single-attack proof."
            )
    if raw.battle_state == 0:
        return
    if _selected_turn_effect_observed(initial_raw, raw):
        return
    raise BattleRuntimeError(
        f"{label} never exposed the selected turn's semantic effect."
    )


def _selected_turn_effect_observed(
    initial: RawGameState,
    current: RawGameState,
) -> bool:
    return (
        current.enemy_species_id != initial.enemy_species_id
        or current.enemy_hp != initial.enemy_hp
        or current.enemy_defense_stage != initial.enemy_defense_stage
        or current.first_party_hp != initial.first_party_hp
        or current.first_party_status != initial.first_party_status
        or current.player_attack_stage != initial.player_attack_stage
        or current.player_accuracy_stage != initial.player_accuracy_stage
    )


def _choose_usable_slot(
    policy: MoveSlotPolicy,
    raw: RawGameState,
    *,
    label: str,
) -> int:
    try:
        slot = policy(raw)
    except Exception as error:
        raise BattleRuntimeError(
            f"{label} move-slot policy rejected the current MAIN-menu turn."
        ) from error
    if (
        not isinstance(slot, int)
        or isinstance(slot, bool)
        or not _MIN_MOVE_SLOT <= slot <= _MAX_MOVE_SLOT
    ):
        raise BattleRuntimeError(
            f"{label} move-slot policy returned invalid one-based slot {slot!r}."
        )

    moves = raw.first_party_moves
    index = slot - 1
    if moves is None or len(moves) <= index or moves[index] == 0:
        raise BattleRuntimeError(
            f"{label} move-slot policy selected slot {slot} without move evidence."
        )
    _current_pp(raw, slot=slot, label=label)
    return slot


def _current_pp(
    raw: RawGameState,
    *,
    slot: int,
    label: str,
    require_usable: bool = True,
) -> int:
    pp = raw.first_party_pp
    index = slot - 1
    if pp is None or len(pp) <= index:
        raise BattleRuntimeError(f"{label} lacks PP evidence for move slot {slot}.")
    current_pp = pp[index] & _CURRENT_PP_MASK
    if require_usable and current_pp <= 0:
        raise BattleRuntimeError(f"{label} move slot {slot} has no usable PP.")
    return current_pp


def _validated_menu(menu: BattleMenuState, *, label: str) -> BattleMenuState:
    if menu.phase is BattleMenuPhase.UNKNOWN:
        valid = menu.selected_main_command is None and menu.selected_move_slot is None
    elif menu.phase is BattleMenuPhase.MAIN:
        command = menu.selected_main_command
        valid = (
            isinstance(command, int)
            and not isinstance(command, bool)
            and 0 <= command <= 3
            and menu.selected_move_slot is None
        )
    elif menu.phase is BattleMenuPhase.MOVE:
        slot = menu.selected_move_slot
        valid = (
            isinstance(slot, int)
            and not isinstance(slot, bool)
            and _MIN_MOVE_SLOT <= slot <= _MAX_MOVE_SLOT
            and menu.selected_main_command is None
        )
    else:
        valid = False
    if not valid:
        raise BattleRuntimeError(f"{label} exposed an invalid semantic battle menu.")
    return menu


def _require_active_trainer_state(
    raw: RawGameState,
    *,
    expected_map: int,
    label: str,
) -> None:
    _require_present_state(raw, expected_map=expected_map, label=label)
    if raw.battle_state != _TRAINER_BATTLE_STATE:
        raise BattleRuntimeError(f"{label} left its active trainer battle unexpectedly.")


def _require_present_state(
    raw: RawGameState,
    *,
    expected_map: int,
    label: str,
) -> None:
    if raw.map_id != expected_map:
        raise BattleRuntimeError(
            f"{label} left expected map {expected_map:#04x} for {raw.map_id!r}."
        )
    if raw.party_count is None or raw.party_count <= 0 or raw.first_party_hp is None:
        raise BattleRuntimeError(f"{label} lacks living party-lead evidence.")
    if raw.first_party_hp <= 0:
        raise BattleRuntimeError(f"{label} party lead fainted.")
    if raw.battle_state == _WILD_BATTLE_STATE:
        raise BattleRuntimeError(f"{label} changed to an unexpected wild battle.")
    if raw.battle_state not in {0, _TRAINER_BATTLE_STATE}:
        raise BattleRuntimeError(
            f"{label} exposed unsupported battle state {raw.battle_state!r}."
        )


def _pulse(
    executor: BattleActionExecutor,
    action: MacroAction,
    wait_frames: int,
) -> None:
    executor.execute(action)
    _wait(executor, wait_frames)


def _wait(executor: BattleActionExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
