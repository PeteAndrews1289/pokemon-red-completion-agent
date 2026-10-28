"""Opt-in native Struggle continuations, with no hidden choice or RAM writes."""

from dataclasses import dataclass, replace

from .actions import MacroAction, MacroActionKind
from .battle_runtime import (
    _ACTIVE_BATTLE_STATE,
    _BATTLE_POLICY_OVERRIDE,
    DEFAULT_BATTLE_RUNTIME_TIMING,
    BattleRuntimeError,
    _await_next_battle_decision,
    _MeasuredTurnExecutor,
    _pulse,
    _require_present_turn_state,
    _terminal_enemy_roster_hp,
    _validated_menu,
    _wait,
)
from .observation import BattleMenuPhase, RawGameState


def forced_struggle_available(raw: RawGameState) -> bool:
    """Deliberately exclude disabled positive-PP moves and living reserves."""
    return model_struggle_available(raw) and not any(
        hp > 0 for i, hp in enumerate(raw.party_hp) if i != raw.active_party_index
    )


def model_struggle_available(raw: RawGameState) -> bool:
    """Zero-PP FIGHT is legal even with reserves; choosing it is NOT forced."""
    return (
        raw.battle_state == 2
        and raw.battler_hp is not None
        and raw.battler_hp > 0
        and raw.party_hp is not None
        and type(raw.active_party_index) is int
        and 0 <= raw.active_party_index < len(raw.party_hp)
        and raw.party_hp[raw.active_party_index] > 0
        and raw.battler_pp is not None
        and len(raw.battler_pp) == 4
        and all(type(pp) is int and 0 <= pp <= 255 and pp & 63 == 0 for pp in raw.battler_pp)
        and raw.enemy_hp is not None
        and raw.enemy_hp > 0
    )


def disabled_forced_struggle_available(raw: RawGameState) -> bool:
    """A separate native singleton: the last usable move is presently Disabled.

    Red's AnyMoveToSelect ignores that slot. Other encoded PP bytes must be
    exactly zero here: the disabled branch does not mask their PP-Up bits.
    Existing zero-PP/model-choice admission is deliberately unchanged.
    """
    hp, pp, moves = raw.party_hp, raw.battler_pp, raw.battler_moves
    slot, turns, active = (
        raw.player_disabled_move_slot, raw.player_disable_turns, raw.active_party_index
    )
    return bool(
        raw.battle_state == 2 and raw.battler_hp is not None and raw.battler_hp > 0
        and hp and type(active) is int and 0 <= active < len(hp)
        and hp[active] == raw.battler_hp
        and all(value == 0 for index, value in enumerate(hp) if index != active)
        and pp is not None and len(pp) == 4
        and all(type(value) is int and 0 <= value <= 255 for value in pp)
        and moves is not None and len(moves) == 4
        and all(type(move) is int and 0 <= move <= 165 for move in moves)
        and type(slot) is int and 1 <= slot <= 4
        and type(turns) is int and 1 <= turns <= 8
        and moves[slot - 1] > 0 and pp[slot - 1] & 63 > 0
        and all(value == 0 for index, value in enumerate(pp) if index != slot - 1)
        and raw.enemy_hp is not None and raw.enemy_hp > 0
    )


@dataclass(frozen=True)
class ForcedStruggleExecution:
    initial_state: RawGameState
    final_state: RawGameState
    actions_executed: int
    frames_executed: int
    terminal_enemy_roster_hp: tuple[int, ...] | None = None
    suppression: str | None = None
    authority: str = "forced_mechanic"

    def __post_init__(self):
        if self.authority not in {"forced_mechanic", "learner"}:
            raise ValueError("Struggle execution authority is unsupported")

    def terminal_referee_evidence(self):
        """Preserve the defeated foe after battle exit clears the active roster."""
        if self.terminal_enemy_roster_hp is None:
            return {}
        before = self.initial_state.enemy_party_hp
        after = self.terminal_enemy_roster_hp
        if before is None or len(before) != len(after):
            raise BattleRuntimeError("forced Struggle terminal roster identity is missing")
        return {
            "referee_opponent_roster_hp_before": list(before),
            "referee_opponent_roster_hp_after": list(after),
            "opponent_faints": sum(a > 0 and b == 0 for a, b in zip(before, after, strict=True)),
        }

    def public_dict(self):
        return {
            "schema": (
                "pokemon.red.model-struggle-turn.v1"
                if self.authority == "learner"
                else "pokemon.red.forced-struggle-turn.v1"
            ),
            "authority": self.authority,
            "selected_move_ref": None if self.suppression else "pokemon.red.gb.us.rev0:move:165",
            "move_slot": None,
            "cartridge_selection_observed": self.suppression is None,
            "suppression": self.suppression,
            "departed_main_menu": True,
            "pp_spent": 0,
            "actions_executed": self.actions_executed,
            "frames_executed": self.frames_executed,
            # Selection/attempt is proved; status, misses, immunity or a faster
            # opponent can prevent execution. Never claim damage or recoil here.
            "execution_claim": "suppressed_before_selection"
            if self.suppression
            else "attempt_only",
            "final_battle_state": self.final_state.battle_state,
            "terminal_enemy_roster_hp": (
                list(self.terminal_enemy_roster_hp)
                if self.terminal_enemy_roster_hp is not None
                else None
            ),
            **(
                dict(
                    availability_basis="last_usable_move_disabled",
                    disabled_move_slot=self.initial_state.player_disabled_move_slot,
                    disable_turns=self.initial_state.player_disable_turns,
                    encoded_pp_before=list(self.initial_state.battler_pp),
                    learned_choice=False,
                    train_admission_authorized=False,
                )
                if disabled_forced_struggle_available(self.initial_state) else {}
            ),
        }


def execute_forced_struggle_turn(
    reader, executor, *, expected_map, timing=DEFAULT_BATTLE_RUNTIME_TIMING
):
    """Confirm FIGHT once, then settle without selecting another attack."""
    return _execute_struggle_turn(
        reader, executor, expected_map=expected_map, timing=timing, model_selected=False
    )


def execute_model_struggle_turn(
    reader, executor, *, expected_map, timing=DEFAULT_BATTLE_RUNTIME_TIMING
):
    """Execute an already selected semantic Struggle; never choose it here."""
    return _execute_struggle_turn(
        reader, executor, expected_map=expected_map, timing=timing, model_selected=True
    )


def execute_disabled_forced_struggle_turn(
    reader, executor, *, expected_map, timing=DEFAULT_BATTLE_RUNTIME_TIMING
):
    """Only the disabled-last-move singleton; retain the original native proof."""
    return _execute_struggle_turn(
        reader, executor, expected_map=expected_map, timing=timing,
        model_selected=False, disabled_only=True,
    )


def _execute_struggle_turn(
    reader, executor, *, expected_map, timing, model_selected, disabled_only=False
):
    label = "model Struggle" if model_selected else "forced Struggle"
    available = (
        disabled_forced_struggle_available if disabled_only
        else model_struggle_available if model_selected else forced_struggle_available
    )
    if _BATTLE_POLICY_OVERRIDE.get() is not None:
        raise BattleRuntimeError("forced Struggle forbids policy override")
    initial = reader.read()
    if initial.map_id != expected_map or not available(initial):
        raise BattleRuntimeError(
            "disabled Struggle requires an observed singleton Disable boundary"
            if disabled_only else f"{label} requires true zero PP"
            + ("" if model_selected else " and no living reserve")
        )
    menu = _validated_menu(reader.read_battle_menu_state(initial), label=label)
    if menu.phase is not BattleMenuPhase.MAIN or reader.trainer_switch_prompt_visible(initial):
        raise BattleRuntimeError("forced Struggle requires an unambiguous MAIN boundary")
    measured = _MeasuredTurnExecutor(executor)
    # Red skips move selection entirely during sleep/freeze or an enemy's
    # ongoing trapping turn. An old selected-move byte is not fresh evidence.
    status = initial.battler_status or 0
    suppression = (
        "sleep"
        if status & 7
        else "freeze"
        if status & 32
        else "trapping"
        if initial.enemy_using_trapping_move
        else None
    )
    token = _ACTIVE_BATTLE_STATE.set(2)
    try:
        for _ in range(timing.max_main_navigation_pulses + 1):
            if menu.phase is not BattleMenuPhase.MAIN:
                raise BattleRuntimeError("forced Struggle lost MAIN")
            if menu.selected_main_command == 0:
                break
            direction = {1: "up", 2: "left", 3: "up"}.get(menu.selected_main_command)
            if direction is None:
                raise BattleRuntimeError("forced Struggle invalid command")
            _pulse(measured, MacroAction(MacroActionKind.MOVE, direction), timing.menu_wait_frames)
            raw = reader.read()
            if raw.map_id != expected_map or not available(raw):
                raise BattleRuntimeError("forced Struggle precondition changed")
            menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
        else:
            raise BattleRuntimeError("forced Struggle navigation limit")
        # Only this confirmation may initiate a turn. CANCEL can advance text
        # but cannot choose FIGHT at a stale/new MAIN signature.
        _pulse(measured, MacroAction(MacroActionKind.CONFIRM), timing.menu_wait_frames)
        departed = False
        selected = False
        for _ in range(timing.max_post_attack_transition_pulses):
            raw = reader.read()
            _require_present_turn_state(
                raw, expected_map=expected_map, label=label, allow_player_faint=True
            )
            menu = _validated_menu(reader.read_battle_menu_state(raw), label=label)
            departed |= menu.phase is not BattleMenuPhase.MAIN
            selected |= reader.read_player_struggle_selected()
            if menu.phase is BattleMenuPhase.MOVE:
                raise BattleRuntimeError("forced Struggle unexpectedly opened move selection")
            if departed and (selected or suppression is not None):
                break
            _wait(measured, timing.menu_wait_frames)
        else:
            raise BattleRuntimeError("forced Struggle selection/departure unproved")
        _await_next_battle_decision(
            reader,
            measured,
            expected_map=expected_map,
            expected_battle_state=2,
            initial_raw=initial,
            slot=1,
            move_executed=False,
            timing=replace(timing, max_post_attack_transition_pulses=40),
            label=label,
        )
        final = reader.read()
        _require_present_turn_state(
            final, expected_map=expected_map, label=label, allow_player_faint=True
        )
        if final.battle_state not in (0, 2) or (
            final.battle_state == 2 and final.active_party_index != initial.active_party_index
        ):
            raise BattleRuntimeError("forced Struggle changed battle/active identity")
        if final.battle_state == 2 and final.battler_pp != initial.battler_pp:
            raise BattleRuntimeError("forced Struggle changed PP")
        roster = _terminal_enemy_roster_hp(reader) if final.battle_state == 0 else None
        if final.battle_state == 0 and (
            not roster or any(roster) or not final.party_hp or not any(final.party_hp)
        ):
            raise BattleRuntimeError("forced Struggle exit lacks terminal trainer proof")
        return ForcedStruggleExecution(
            initial,
            final,
            measured.actions_executed,
            measured.frames_executed,
            roster,
            suppression,
            "learner" if model_selected else "forced_mechanic",
        )
    finally:
        _ACTIVE_BATTLE_STATE.reset(token)
