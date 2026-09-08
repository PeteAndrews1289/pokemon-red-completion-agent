"""One observed Full Restore turn and exact bag accounting for bounded recovery."""

from __future__ import annotations

from .actions import MacroActionKind
from .battle_recovery import (
    ActionExecutor,
    EmulatorState,
    ProtectedRecoveryError,
    _pulse,
    _select_bag_item,
    _select_battle_main_command,
    _select_cursor,
)
from .observation import BattleMenuPhase, ItemId, PokemonRedStateReader, RawGameState


def bag_after_full_restores(
    initial: tuple[tuple[int, int], ...],
    spent: int,
) -> tuple[tuple[int, int], ...]:
    """Exact permissible bag, preserving every other item and its order."""
    if type(spent) is not int or not 0 <= spent <= 2:
        raise ValueError("recovery supports at most two Full Restores")
    if len({item for item, _ in initial}) != len(initial) or any(qty <= 0 for _, qty in initial):
        raise ValueError("initial recovery bag differs")
    if dict(initial).get(int(ItemId.FULL_RESTORE), 0) < spent:
        raise ValueError("Full Restore stock cannot fund recovery")
    return tuple(
        (item, remaining)
        for item, qty in initial
        if (remaining := qty - (spent if item == ItemId.FULL_RESTORE else 0)) > 0
    )


def trainer_bag_within_budget(
    before: RawGameState,
    after: RawGameState,
    maximum: int,
) -> bool:
    if type(maximum) is not int or not 0 <= maximum <= 2 or before.bag_items is None:
        return False
    available = dict(before.bag_items).get(int(ItemId.FULL_RESTORE), 0)
    return any(
        after.bag_items == bag_after_full_restores(before.bag_items, spent)
        for spent in range(min(maximum, available) + 1)
    )


def use_active_full_restore(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    expected: RawGameState,
    incoming_bound: int,
    wait_frames: int = 180,
) -> RawGameState:
    """Use exactly one owned item; bound all menus and verify the enemy reply.

    Caller owns the strategic HP calculation and resource budget. This executor
    does not select a different member, attack, retry a spent item or rewind.
    """
    raw = reader.read()
    slot = raw.active_party_index
    if (
        raw != expected
        or raw.battle_state != 2
        or slot is None
        or raw.party_hp is None
        or raw.party_max_hp is None
        or raw.party_status is None
        or raw.bag_items is None
        or not 0 <= slot < len(raw.party_hp)
        or not all(hp > 0 for hp in raw.party_hp)
        or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
        or type(incoming_bound) is not int
        or incoming_bound < 0
        or raw.party_max_hp[slot] <= incoming_bound
        or (raw.party_hp[slot] == raw.party_max_hp[slot] and raw.party_status[slot] == 0)
    ):
        raise ProtectedRecoveryError("Full Restore requires a qualified needy active member")
    expected_bag = bag_after_full_restores(raw.bag_items, 1)
    _select_battle_main_command(actions, reader, 1, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    _select_bag_item(actions, emulator, ItemId.FULL_RESTORE, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    _select_cursor(actions, emulator, slot, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    for index in range(48):
        after = reader.read()
        if (
            after.battle_state != 2
            or after.map_id != raw.map_id
            or after.active_party_index != slot
            or after.party_species_ids != raw.party_species_ids
            or after.party_hp is None
            or not all(hp > 0 for hp in after.party_hp)
        ):
            raise ProtectedRecoveryError("Full Restore lost its living trainer boundary")
        if reader.read_battle_menu_state(after).phase is BattleMenuPhase.MAIN:
            if (
                after.bag_items != expected_bag
                or after.party_pp != raw.party_pp
                or after.party_hp[slot] < raw.party_max_hp[slot] - incoming_bound
                or any(after.party_hp[i] != hp for i, hp in enumerate(raw.party_hp) if i != slot)
            ):
                raise ProtectedRecoveryError(
                    "Full Restore item, PP or incoming damage proof differs"
                )
            return after
        _pulse(
            actions,
            MacroActionKind.CANCEL if index % 4 == 3 else MacroActionKind.CONFIRM,
            wait_frames=wait_frames,
        )
    raise ProtectedRecoveryError("Full Restore did not return to MAIN within its bound")
