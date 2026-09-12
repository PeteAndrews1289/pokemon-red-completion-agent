"""Bounded, verified Red trainer blackout for renewable-income support.

This component intentionally loses one already-active trainer battle after its
income has been earned.  It is deterministic infrastructure beneath a learned
high-level RESUPPLY choice: it creates no learner label and owns no authority to
choose whether a blackout is strategically desirable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from .actions import MacroAction, MacroActionKind
from .battle_recovery import ProtectedRecoveryError, switch_active_battler
from .battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    BattleActionExecutor,
    BattleRuntimeError,
    BattleRuntimeTiming,
    execute_observed_trainer_move,
)
from .observation import BattleMenuPhase, InputReadiness, RawGameState
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_party_pp import RedPartyPpError, decode_red_party_pp

_TRAINER_BATTLE = 2
_CURRENT_PP_MASK = 0x3F


class ControlledBlackoutReader(Protocol):
    def read(self) -> RawGameState: ...

    def read_battle_menu_state(self, raw: RawGameState): ...

    def read_active_trainer_identity(self) -> tuple[int, int, int]: ...

    def read_last_blackout_map(self) -> int: ...

    def read_input_readiness(self) -> InputReadiness: ...


class ControlledBlackoutEmulator(Protocol):
    frame_count: int
    pressed_buttons: frozenset[str]

    def read_u8(self, address: int) -> int: ...


class RedControlledBlackoutError(RuntimeError):
    """The controlled loss left its exact bound or failed verification."""


@dataclass(frozen=True, slots=True)
class RedControlledBlackoutOrigin:
    map_id: int
    trainer_identity: tuple[int, int, int]
    last_blackout_map: int
    money: int
    bag_items: tuple[tuple[int, int], ...]
    badge_bits: int
    event_flags: bytes
    party_species: tuple[int, ...]
    party_levels: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_moves: tuple[tuple[int, ...], ...]
    party_pp: tuple[tuple[int, ...], ...]


@dataclass(slots=True)
class RedControlledBlackoutBinding:
    origin: RedControlledBlackoutOrigin
    claimed: bool = False


@dataclass(frozen=True, slots=True)
class RedControlledBlackoutResult:
    starting_money: int
    ending_money: int
    destination_map: int
    moves_selected: tuple[int, ...]
    forced_switches: tuple[int, ...]
    actions: int
    frames: int

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.controlled-blackout.v1",
            "status": "verified_controlled_blackout",
            "starting_money": self.starting_money,
            "ending_money": self.ending_money,
            "money_retained": self.ending_money,
            "money_lost": self.starting_money - self.ending_money,
            "destination_map": self.destination_map,
            "moves_selected": list(self.moves_selected),
            "forced_switches": list(self.forced_switches),
            "actions": self.actions,
            "frames": self.frames,
            "learned_goal_authority": False,
            "learned_battle_authority": False,
            "forced_support_step": True,
            "training_examples": 0,
        }


@dataclass(slots=True)
class _CountingActions:
    delegate: BattleActionExecutor
    count: int = 0

    def execute(self, action: MacroAction) -> object:
        result = self.delegate.execute(action)
        self.count += 1
        return result


def _complete_origin(reader: ControlledBlackoutReader) -> RedControlledBlackoutOrigin:
    raw = reader.read()
    required = (
        raw.map_id,
        raw.player_money,
        raw.bag_items,
        raw.badge_bits,
        raw.event_flags,
        raw.party_species_ids,
        raw.party_levels,
        raw.party_hp,
        raw.party_max_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
        raw.active_party_index,
        raw.battler_hp,
        raw.enemy_hp,
    )
    if (
        raw.battle_state != _TRAINER_BATTLE
        or any(value is None for value in required)
        or raw.party_count != len(raw.party_species_ids or ())
        or raw.party_count != len(raw.party_levels or ())
        or raw.party_count != len(raw.party_hp or ())
        or raw.party_count != len(raw.party_max_hp or ())
        or raw.party_count != len(raw.party_status or ())
        or raw.party_count != len(raw.party_moves or ())
        or raw.party_count != len(raw.party_pp or ())
        or raw.party_count is None
        or raw.party_count <= 0
        or not 0 <= cast(int, raw.active_party_index) < raw.party_count
        or any(hp <= 0 for hp in raw.party_hp or ())
        or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
    ):
        raise RedControlledBlackoutError(
            "controlled blackout requires a complete living trainer MAIN boundary"
        )
    last_blackout_map = reader.read_last_blackout_map()
    identity = reader.read_active_trainer_identity()
    if (
        type(last_blackout_map) is not int  # noqa: E721
        or not 0 <= last_blackout_map <= 0xFF
        or len(identity) != 3
        or any(type(value) is not int or not 0 <= value <= 0xFF for value in identity)
    ):
        raise RedControlledBlackoutError("controlled blackout identity is incomplete")
    return RedControlledBlackoutOrigin(
        map_id=cast(int, raw.map_id),
        trainer_identity=identity,
        last_blackout_map=last_blackout_map,
        money=cast(int, raw.player_money),
        bag_items=tuple(raw.bag_items or ()),
        badge_bits=cast(int, raw.badge_bits),
        event_flags=bytes(raw.event_flags or b""),
        party_species=tuple(raw.party_species_ids or ()),
        party_levels=tuple(raw.party_levels or ()),
        party_max_hp=tuple(raw.party_max_hp or ()),
        party_moves=tuple(raw.party_moves or ()),
        party_pp=tuple(raw.party_pp or ()),
    )


def bind_red_controlled_blackout(
    reader: ControlledBlackoutReader,
) -> RedControlledBlackoutBinding:
    """Bind the exact active battle without advancing emulator time or input."""

    return RedControlledBlackoutBinding(_complete_origin(reader))


def choose_minimum_damage_slot(raw: RawGameState) -> int:
    """Choose a usable status move first, otherwise the lowest raw power."""

    moves, pp = raw.battler_moves, raw.battler_pp
    if moves is None or pp is None or len(moves) != 4 or len(pp) != 4:
        raise RedControlledBlackoutError("controlled blackout lacks a complete move inventory")
    candidates: list[tuple[int, int, int]] = []
    for slot, (move_id, packed_pp) in enumerate(zip(moves, pp, strict=True), start=1):
        if move_id == 0 or packed_pp & _CURRENT_PP_MASK == 0:
            continue
        if raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0:
            continue
        try:
            move = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move_id))
        except Exception as error:
            raise RedControlledBlackoutError("controlled blackout move catalog differs") from error
        status_rank = 0 if move.category == "status" and move.power == 0 else 1
        candidates.append((status_rank, move.power, slot))
    if not candidates:
        raise RedControlledBlackoutError("controlled blackout has no usable observed move")
    return min(candidates)[2]


def _require_battle_preserved(
    reader: ControlledBlackoutReader,
    raw: RawGameState,
    origin: RedControlledBlackoutOrigin,
) -> None:
    if (
        raw.map_id != origin.map_id
        or raw.battle_state != _TRAINER_BATTLE
        or reader.read_active_trainer_identity() != origin.trainer_identity
        or reader.read_last_blackout_map() != origin.last_blackout_map
        or raw.player_money != origin.money
        or raw.bag_items != origin.bag_items
        or raw.badge_bits != origin.badge_bits
        or raw.event_flags != origin.event_flags
        or raw.party_species_ids != origin.party_species
        or raw.party_levels != origin.party_levels
        or raw.party_max_hp != origin.party_max_hp
        or raw.party_moves != origin.party_moves
    ):
        raise RedControlledBlackoutError("controlled blackout changed its protected battle state")


def _party_fully_restored(raw: RawGameState, origin: RedControlledBlackoutOrigin) -> bool:
    if (
        raw.party_species_ids != origin.party_species
        or raw.party_levels != origin.party_levels
        or raw.party_max_hp != origin.party_max_hp
        or raw.party_moves != origin.party_moves
        or raw.party_hp != origin.party_max_hp
        or raw.party_status is None
        or any(raw.party_status)
        or raw.party_pp is None
    ):
        return False
    try:
        for moves, packed in zip(raw.party_moves or (), raw.party_pp, strict=True):
            decoded = decode_red_party_pp(moves, packed)
            if decoded.current_total != decoded.maximum_total:
                return False
    except RedPartyPpError:
        return False
    return True


def _pulse(actions: _CountingActions, kind: MacroActionKind, frames: int) -> None:
    actions.execute(MacroAction(kind))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def execute_red_controlled_blackout(
    binding: RedControlledBlackoutBinding,
    reader: ControlledBlackoutReader,
    emulator: ControlledBlackoutEmulator,
    executor: BattleActionExecutor,
    *,
    timing: BattleRuntimeTiming = DEFAULT_BATTLE_RUNTIME_TIMING,
    maximum_turn_boundaries: int = 256,
    maximum_dialogue_pulses: int = 256,
    maximum_forced_switches: int = 5,
) -> RedControlledBlackoutResult:
    """Consume one binding and prove the cartridge-native loss transition."""

    for name, value in (
        ("maximum_turn_boundaries", maximum_turn_boundaries),
        ("maximum_dialogue_pulses", maximum_dialogue_pulses),
        ("maximum_forced_switches", maximum_forced_switches),
    ):
        if type(value) is not int or value <= 0:  # noqa: E721
            raise ValueError(f"{name} must be a positive integer")
    if not isinstance(binding, RedControlledBlackoutBinding):
        raise TypeError("binding must be a RedControlledBlackoutBinding")
    if binding.claimed:
        raise RedControlledBlackoutError("controlled blackout binding was already claimed")
    binding.claimed = True
    if _complete_origin(reader) != binding.origin:
        raise RedControlledBlackoutError("controlled blackout origin changed before first input")

    start_frame = emulator.frame_count
    actions = _CountingActions(executor)
    selected: list[int] = []
    switches: list[int] = []
    all_fainted = False

    for _ in range(maximum_turn_boundaries):
        raw = reader.read()
        if raw.battle_state != _TRAINER_BATTLE:
            if any(raw.party_hp or ()):
                raise RedControlledBlackoutError(
                    "controlled blackout ended as an unexpected victory"
                )
            all_fainted = True
            break
        _require_battle_preserved(reader, raw, binding.origin)
        party_hp = raw.party_hp or ()
        if not any(party_hp):
            all_fainted = True
            break
        if (raw.battler_hp or 0) <= 0:
            living = next((index for index, hp in enumerate(party_hp) if hp > 0), None)
            if living is None:
                all_fainted = True
                break
            if len(switches) >= maximum_forced_switches:
                raise RedControlledBlackoutError("controlled blackout exceeded forced switches")
            try:
                switch_active_battler(
                    actions,
                    reader,  # type: ignore[arg-type]
                    emulator,
                    living,
                    label="controlled blackout forced replacement",
                    wait_frames=timing.dialogue_wait_frames,
                )
            except ProtectedRecoveryError as error:
                raise RedControlledBlackoutError(
                    "controlled blackout forced replacement failed"
                ) from error
            switches.append(living)
            continue

        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.MOVE:
            _pulse(actions, MacroActionKind.CANCEL, timing.menu_wait_frames)
            continue
        if menu.phase is BattleMenuPhase.UNKNOWN:
            prompt = getattr(reader, "trainer_switch_prompt_visible", None)
            kind = (
                MacroActionKind.CANCEL
                if callable(prompt) and bool(prompt(raw))
                else MacroActionKind.CONFIRM
            )
            _pulse(actions, kind, timing.dialogue_wait_frames)
            continue
        if menu.phase is not BattleMenuPhase.MAIN:
            raise RedControlledBlackoutError("controlled blackout exposed an invalid battle menu")
        slot = choose_minimum_damage_slot(raw)
        try:
            execute_observed_trainer_move(
                reader,
                actions,
                slot,
                expected_map=binding.origin.map_id,
                timing=timing,
                label="controlled blackout turn",
            )
        except BattleRuntimeError as error:
            raise RedControlledBlackoutError("controlled blackout move execution failed") from error
        selected.append(slot)
    if not all_fainted:
        raise RedControlledBlackoutError("controlled blackout exceeded its turn boundary")

    for _ in range(maximum_dialogue_pulses):
        raw = reader.read()
        if raw.battle_state == _TRAINER_BATTLE:
            _require_battle_preserved(reader, raw, binding.origin)
            if any(raw.party_hp or ()):
                raise RedControlledBlackoutError("controlled blackout revived before battle exit")
            _pulse(actions, MacroActionKind.CONFIRM, timing.dialogue_wait_frames)
            continue
        if raw.battle_state not in {0, None}:
            raise RedControlledBlackoutError(
                "controlled blackout exited to an invalid battle state"
            )
        if any(raw.party_hp or ()) and raw.player_money == binding.origin.money:
            raise RedControlledBlackoutError("controlled blackout ended as an unexpected victory")
        if reader.read_input_readiness().ready:
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing.dialogue_wait_frames)
    else:
        raise RedControlledBlackoutError("controlled blackout exceeded its settlement boundary")

    final = reader.read()
    expected_money = binding.origin.money // 2
    if (
        final.battle_state != 0
        or final.map_id != binding.origin.last_blackout_map
        or final.player_money != expected_money
        or final.bag_items != binding.origin.bag_items
        or final.badge_bits != binding.origin.badge_bits
        or final.event_flags != binding.origin.event_flags
        or not _party_fully_restored(final, binding.origin)
        or not reader.read_input_readiness().ready
        or emulator.pressed_buttons
    ):
        raise RedControlledBlackoutError("controlled blackout terminal verification failed")
    frames = emulator.frame_count - start_frame
    if frames < 0:
        raise RedControlledBlackoutError("controlled blackout frame counter moved backwards")
    return RedControlledBlackoutResult(
        binding.origin.money,
        expected_money,
        binding.origin.last_blackout_map,
        tuple(selected),
        tuple(switches),
        actions.count,
        frames,
    )


__all__ = [
    "RedControlledBlackoutBinding",
    "RedControlledBlackoutError",
    "RedControlledBlackoutOrigin",
    "RedControlledBlackoutResult",
    "bind_red_controlled_blackout",
    "choose_minimum_damage_slot",
    "execute_red_controlled_blackout",
]
