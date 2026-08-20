"""Party-aware field recovery shared by multi-member chapter boundaries."""

from __future__ import annotations

from typing import Protocol

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.celadon import _bag, _party_hp, _party_max_hp, _party_status
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    LavenderTiming,
    _close_menus,
    _open_bag,
    _select_bag_item,
    _select_cursor,
)
from pokemon_red_completion.observation import ItemId, PokemonRedStateReader
from pokemon_red_completion.victory_road import _pulse


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class FieldRecoveryError(RuntimeError):
    """Raised when observed party recovery cannot be planned or verified."""


def plan_party_recovery(
    party_hp: tuple[int, ...],
    party_max_hp: tuple[int, ...],
    party_status: tuple[int, ...],
) -> tuple[tuple[int, ItemId], ...]:
    """Plan one exact recovery item for every affected living party member."""
    if not (len(party_hp) == len(party_max_hp) == len(party_status)):
        raise FieldRecoveryError("Party recovery state is incomplete.")
    plan: list[tuple[int, ItemId]] = []
    for index, (hp, max_hp, status) in enumerate(
        zip(party_hp, party_max_hp, party_status, strict=True)
    ):
        if not 0 < hp <= max_hp:
            raise FieldRecoveryError(
                f"Party member {index + 1} has invalid recovery HP {hp}/{max_hp}."
            )
        if hp < max_hp and status:
            plan.append((index, ItemId.FULL_RESTORE))
        elif hp < max_hp:
            plan.append((index, ItemId.HYPER_POTION))
        elif status:
            plan.append((index, ItemId.FULL_HEAL))
    return tuple(plan)


def use_field_recovery_item(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    party_index: int,
    item: ItemId,
    *,
    timing: LavenderTiming = DEFAULT_LAVENDER_TIMING,
) -> None:
    """Use and verify one recovery item on its planned party member."""
    before_hp = _party_hp(emulator)
    before_max_hp = _party_max_hp(emulator)
    before_status = _party_status(emulator)
    before_quantity = _bag(emulator).get(item, 0)
    if (
        party_index >= len(before_hp)
        or party_index >= len(before_max_hp)
        or party_index >= len(before_status)
        or before_quantity <= 0
    ):
        raise FieldRecoveryError(
            f"{item.name} target {party_index + 1} lacks valid recovery evidence."
        )

    _open_bag(actions, emulator, timing)
    _select_bag_item(actions, emulator, item, timing)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    _select_cursor(actions, emulator, party_index, timing)
    _pulse(actions, MacroActionKind.CONFIRM)

    for _ in range(24):
        current_hp = _party_hp(emulator)
        current_status = _party_status(emulator)
        item_consumed = _bag(emulator).get(item, 0) == before_quantity - 1
        expected_hp = (
            before_hp[party_index]
            if item is ItemId.FULL_HEAL
            else before_max_hp[party_index]
            if item is ItemId.FULL_RESTORE
            else min(before_max_hp[party_index], before_hp[party_index] + 200)
        )
        if (
            item_consumed
            and current_hp[party_index] == expected_hp
            and current_status[party_index] == 0
        ):
            _close_menus(actions, reader, timing)
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise FieldRecoveryError(
        f"{item.name} did not recover party member {party_index + 1}."
    )
