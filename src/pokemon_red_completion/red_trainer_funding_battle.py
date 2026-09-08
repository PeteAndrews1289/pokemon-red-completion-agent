"""Prepared trainer battle execution for ordinary funding objectives.

Proves interaction boundary, undefeated state, full living party and active
trainer identity before and during combat. Bounded intro and settlement
transitions ensure no unhandled dialogue or stray inputs escape to the
overworld. Payout is validated against cartridge quotes without Pay Day.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleActionExecutor,
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
    BattleStateReader,
    MoveSlotPolicy,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.observation import (
    RawGameState,
    event_flag_is_set,
)
from pokemon_red_completion.red_trainer_funding import TrainerFundingCandidate


class TrainerFundingBattleReader(BattleStateReader, Protocol):
    """Semantic battle reader extended with facing, dialogue, and identity reads."""

    def read_player_facing(self) -> str: ...

    def read_bottom_dialogue_box_visible(self) -> bool: ...

    def read_trainer_battle_identity(self) -> tuple[int, int, int, int]: ...

    def read_pending_trainer_battle_identity(self) -> tuple[int, int] | None: ...


class TrainerFundingBattleError(BattleRuntimeError):
    """Raised when prepared trainer funding fails preconditions or execution."""


@dataclass(frozen=True, slots=True)
class TrainerFundingBattleReceipt:
    """Proved outcome of one completed ordinary trainer battle."""

    target: TrainerFundingCandidate
    initial_state: RawGameState
    final_state: RawGameState
    initial_money: int
    final_money: int
    payout: int

    def __post_init__(self) -> None:
        if not isinstance(self.target, TrainerFundingCandidate):
            raise TypeError("target must be a TrainerFundingCandidate")
        if not isinstance(self.initial_state, RawGameState) or not isinstance(
            self.final_state, RawGameState
        ):
            raise TypeError("receipt states must be RawGameState values")
        for name in ("initial_money", "final_money", "payout"):
            val = getattr(self, name)
            if type(val) is not int or isinstance(val, bool):
                raise TypeError(f"{name} must be an integer")
        if self.payout != self.final_money - self.initial_money:
            raise ValueError("payout must equal final_money - initial_money")


battle_runner: Callable[..., RawGameState] = run_adaptive_trainer_battle


def _check_postbattle_fatal(
    st: RawGameState,
    init: RawGameState,
    tgt: TrainerFundingCandidate,
) -> None:
    if st.battle_state != 0:
        raise TrainerFundingBattleError(f"unsupported post-battle state {st.battle_state}")
    if st.battle_result != 0:
        raise TrainerFundingBattleError(
            f"trainer battle did not end in victory (battle_result={st.battle_result})"
        )
    if st.map_id != tgt.trainer.map_id:
        raise TrainerFundingBattleError(
            f"player map {st.map_id} differs from target map {tgt.trainer.map_id}"
        )
    if (st.player_y, st.player_x) != tgt.approach.terminal_at:
        raise TrainerFundingBattleError(
            f"player position {(st.player_y, st.player_x)} lost terminal {tgt.approach.terminal_at}"
        )
    if st.party_count != init.party_count or st.party_species_ids != init.party_species_ids:
        raise TrainerFundingBattleError("party species changed after battle")
    if (
        st.party_hp is None
        or len(st.party_hp) != init.party_count
        or any(type(hp) is not int or isinstance(hp, bool) or hp <= 0 for hp in st.party_hp)
    ):
        raise TrainerFundingBattleError("party HP missing, truncated, or fainted during battle")
    if st.bag_items != init.bag_items:
        raise TrainerFundingBattleError("bag items mutated during battle")


def _is_settled(
    st: RawGameState,
    rdr: TrainerFundingBattleReader,
    init: RawGameState,
    tgt: TrainerFundingCandidate,
    exp_money: int,
) -> bool:
    if st.battle_state != 0:
        return False
    if st.battle_result != 0:
        return False
    if st.map_id != tgt.trainer.map_id:
        return False
    if (st.player_y, st.player_x) != tgt.approach.terminal_at:
        return False
    if st.party_species_ids != init.party_species_ids:
        return False
    if (
        st.party_hp is None
        or len(st.party_hp) != init.party_count
        or any(type(hp) is not int or isinstance(hp, bool) or hp <= 0 for hp in st.party_hp)
    ):
        return False
    if st.bag_items != init.bag_items:
        return False
    if st.player_money != exp_money:
        return False
    if not event_flag_is_set(st.event_flags, tgt.trainer.event_flag):
        return False
    if not rdr.read_input_readiness().ready:
        return False
    return not rdr.read_bottom_dialogue_box_visible()


def _raise_settle_failure(
    st: RawGameState,
    rdr: TrainerFundingBattleReader,
    init: RawGameState,
    tgt: TrainerFundingCandidate,
    exp_money: int,
) -> None:
    _check_postbattle_fatal(st, init, tgt)
    if not event_flag_is_set(st.event_flags, tgt.trainer.event_flag):
        raise TrainerFundingBattleError(f"defeated event flag {tgt.trainer.event_flag} was not set")
    if st.player_money != exp_money:
        raise TrainerFundingBattleError(
            f"player money {st.player_money} does not match expected {exp_money}"
        )
    if rdr.read_bottom_dialogue_box_visible():
        raise TrainerFundingBattleError("exhausted settle pulses before dialogue finished")
    if not rdr.read_input_readiness().ready:
        raise TrainerFundingBattleError("exhausted settle pulses before input became ready")
    raise TrainerFundingBattleError(
        "exhausted settle pulses before reaching settled overworld state"
    )


def run_prepared_trainer_funding(
    reader: TrainerFundingBattleReader,
    executor: BattleActionExecutor,
    *,
    target: TrainerFundingCandidate,
    validate_target: Callable[[], None],
    move_slot_policy: MoveSlotPolicy,
    timing: BattleRuntimeTiming,
    maximum_intro_pulses: int = 32,
    maximum_settle_pulses: int = 32,
) -> TrainerFundingBattleReceipt:
    """Execute a prepared ordinary trainer battle to claim verified funding."""
    if (
        type(maximum_intro_pulses) is not int
        or isinstance(maximum_intro_pulses, bool)
        or maximum_intro_pulses <= 0
    ):
        raise ValueError("maximum_intro_pulses must be a positive integer")
    if (
        type(maximum_settle_pulses) is not int
        or isinstance(maximum_settle_pulses, bool)
        or maximum_settle_pulses <= 0
    ):
        raise ValueError("maximum_settle_pulses must be a positive integer")
    if not isinstance(target, TrainerFundingCandidate):
        raise TypeError("target must be a TrainerFundingCandidate")
    if not callable(validate_target):
        raise TypeError("validate_target must be callable")
    if not callable(move_slot_policy):
        raise TypeError("move_slot_policy must be callable")
    if not isinstance(timing, BattleRuntimeTiming):
        raise TypeError("timing must be a BattleRuntimeTiming")

    if (
        target.quote.opponent_id != target.trainer.trainer_class
        or target.quote.trainer_set != target.trainer.trainer_set
    ):
        raise ValueError("target quote identity does not match target trainer identity")
    if not target.quote.party:
        raise ValueError("target quote party cannot be empty")
    if target.trainer.defeated:
        raise TrainerFundingBattleError("target trainer is already marked defeated")

    validate_target()

    initial = reader.read()
    if initial.battle_state != 0:
        raise TrainerFundingBattleError(
            f"initial battle state {initial.battle_state} must be 0 (overworld)"
        )
    if initial.map_id != target.trainer.map_id:
        raise TrainerFundingBattleError(
            f"initial map {initial.map_id} does not match target map {target.trainer.map_id}"
        )
    if (initial.player_y, initial.player_x) != target.approach.terminal_at:
        raise TrainerFundingBattleError(
            f"player position {(initial.player_y, initial.player_x)} "
            f"does not match terminal {target.approach.terminal_at}"
        )
    facing = reader.read_player_facing()
    if facing != target.interaction_facing.value:
        raise TrainerFundingBattleError(
            f"player facing {facing!r} does not match "
            f"interaction facing {target.interaction_facing.value!r}"
        )
    if not reader.read_input_readiness().ready:
        raise TrainerFundingBattleError("initial input readiness is not ready")
    if reader.read_bottom_dialogue_box_visible():
        raise TrainerFundingBattleError("dialogue box is visible before interaction")
    if initial.event_flags is None or event_flag_is_set(
        initial.event_flags, target.trainer.event_flag
    ):
        raise TrainerFundingBattleError(
            f"trainer event flag {target.trainer.event_flag} is already set or unreadable"
        )
    if (
        initial.party_count is None
        or type(initial.party_count) is not int
        or not 1 <= initial.party_count <= 6
    ):
        raise TrainerFundingBattleError("initial party_count is missing or invalid")
    if initial.party_species_ids is None or len(initial.party_species_ids) != initial.party_count:
        raise TrainerFundingBattleError("initial party_species_ids is missing or length mismatch")
    if initial.party_hp is None or len(initial.party_hp) != initial.party_count:
        raise TrainerFundingBattleError("initial party_hp is missing or length mismatch")
    if any(type(hp) is not int or isinstance(hp, bool) or hp <= 0 for hp in initial.party_hp):
        raise TrainerFundingBattleError("initial party contains fainted or non-positive HP pokemon")
    if initial.bag_items is None:
        raise TrainerFundingBattleError("initial bag_items is missing")
    if (
        initial.player_money is None
        or type(initial.player_money) is not int
        or isinstance(initial.player_money, bool)
        or not 0 <= initial.player_money <= 999999
    ):
        raise TrainerFundingBattleError("initial player_money is missing or invalid")

    expected_pending = (target.trainer.trainer_class, target.trainer.trainer_set)

    def pending_start() -> bool:
        pending = reader.read_pending_trainer_battle_identity()
        if pending is not None and pending != expected_pending:
            raise TrainerFundingBattleError("pending trainer identity does not match target")
        return pending is not None

    resuming_pending = pending_start()
    if not resuming_pending:
        executor.execute(MacroAction(MacroActionKind.INTERACT))
        executor.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_wait_frames))

    state = reader.read()
    intro_count = 0
    while state.battle_state != 2:
        if state.battle_state == 1:
            raise TrainerFundingBattleError("trainer interaction entered wild battle")
        if state.battle_state != 0:
            raise TrainerFundingBattleError(f"unsupported battle state {state.battle_state}")
        pending = pending_start()
        dialogue = reader.read_bottom_dialogue_box_visible()
        if not pending and not dialogue and reader.read_input_readiness().ready:
            if intro_count == 0 and not resuming_pending:
                raise TrainerFundingBattleError(
                    "trainer interaction produced no dialogue or battle"
                )
            raise TrainerFundingBattleError("trainer dialogue closed without entering battle")
        if intro_count >= maximum_intro_pulses:
            raise TrainerFundingBattleError("exhausted intro pulses before entering trainer battle")
        # The cartridge owns an armed transition. Wait without another button;
        # only an observed dialogue or the legacy not-ready preamble gets CONFIRM.
        if not pending:
            executor.execute(MacroAction(MacroActionKind.CONFIRM))
        executor.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_wait_frames))
        intro_count += 1
        state = reader.read()

    expected_identity = (
        target.trainer.trainer_class,
        target.trainer.trainer_class - 200,
        target.trainer.trainer_class,
        target.trainer.trainer_set,
    )
    active_identity = reader.read_trainer_battle_identity()
    if active_identity != expected_identity:
        raise TrainerFundingBattleError(
            f"active battle identity {active_identity} does not match expected {expected_identity}"
        )
    if state.party_species_ids != initial.party_species_ids:
        raise TrainerFundingBattleError("party species changed before battle runner")
    if (
        state.party_hp is None
        or len(state.party_hp) != initial.party_count
        or any(type(hp) is not int or isinstance(hp, bool) or hp <= 0 for hp in state.party_hp)
    ):
        raise TrainerFundingBattleError(
            "party HP missing, truncated, or fainted before battle runner"
        )

    def _guard(current_raw: RawGameState) -> None:
        if current_raw.battle_state != 2:
            raise TrainerFundingBattleError(
                f"battle state {current_raw.battle_state} must be 2 during combat"
            )
        identity = reader.read_trainer_battle_identity()
        if identity != expected_identity:
            raise TrainerFundingBattleError(
                f"active battle identity {identity} does not match expected {expected_identity}"
            )
        if (
            current_raw.party_count != initial.party_count
            or current_raw.party_species_ids != initial.party_species_ids
        ):
            raise TrainerFundingBattleError("party species changed during battle")
        if (
            current_raw.party_hp is None
            or len(current_raw.party_hp) != initial.party_count
            or any(
                type(hp) is not int or isinstance(hp, bool) or hp <= 0
                for hp in current_raw.party_hp
            )
        ):
            raise TrainerFundingBattleError("party HP missing, truncated, or fainted during battle")

    def _wrapped_policy(current_raw: RawGameState) -> int:
        _guard(current_raw)
        moves = current_raw.battler_moves
        pp = current_raw.battler_pp
        if moves is None or not 1 <= len(moves) <= 4:
            raise TrainerFundingBattleError("active battler moves unreadable during combat")
        if pp is None or len(pp) != len(moves):
            raise TrainerFundingBattleError("active battler PP unreadable during combat")
        slot = move_slot_policy(current_raw)
        if type(slot) is not int or isinstance(slot, bool) or not 1 <= slot <= len(moves):
            raise TrainerFundingBattleError(f"move slot policy returned invalid slot {slot!r}")
        if moves[slot - 1] <= 0 or pp[slot - 1] <= 0:
            raise TrainerFundingBattleError("selected move is empty or exhausted")
        if moves[slot - 1] == 6:
            raise TrainerFundingBattleError(
                "move slot policy selected Pay Day (move ID 6), excluded from ordinary funding"
            )
        return slot

    intent = BattleIntent(
        objective_id="trainer_funding",
        battle_plan_id="ordinary-trainer-funding",
    )
    battle_final = battle_runner(
        reader,
        executor,
        _wrapped_policy,
        expected_map=target.trainer.map_id,
        intent=intent,
        timing=timing,
        label="trainer funding battle",
        consume_battle_start_schedule=False,
        move_decision_guard=_guard,
    )
    if not isinstance(battle_final, RawGameState):
        raise TrainerFundingBattleError("battle runner did not return RawGameState")

    expected_money = target.quote.expected_money_after(initial.player_money)
    state = battle_final
    _check_postbattle_fatal(state, initial, target)

    settle_count = 0
    while not _is_settled(state, reader, initial, target, expected_money):
        if settle_count >= maximum_settle_pulses:
            _raise_settle_failure(state, reader, initial, target, expected_money)
        if not reader.read_bottom_dialogue_box_visible() and reader.read_input_readiness().ready:
            _raise_settle_failure(state, reader, initial, target, expected_money)
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        executor.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_wait_frames))
        settle_count += 1
        state = reader.read()
        _check_postbattle_fatal(state, initial, target)

    final_money = state.player_money
    if final_money is None:
        raise TrainerFundingBattleError("settled trainer payout is unreadable")
    payout = final_money - initial.player_money
    return TrainerFundingBattleReceipt(
        target=target,
        initial_state=initial,
        final_state=state,
        initial_money=initial.player_money,
        final_money=final_money,
        payout=payout,
    )
