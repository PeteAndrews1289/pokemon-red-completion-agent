"""Observed Generation-I field party reordering without hidden role choices."""

from __future__ import annotations

from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_field_moves import GEN1_FIELD_MOVE_IDS
from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress, RawGameState


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class MemoryReader(Protocol):
    def read_u8(self, address: int) -> int: ...


class Gen1PartyMenuError(RuntimeError):
    """A field party reorder missed its observed menu or persistence gate."""


def sole_living_party_index(party_hp: tuple[int, ...]) -> int | None:
    """Return a target only when field survival leaves no strategic choice."""

    living = tuple(index for index, hp in enumerate(party_hp) if hp > 0)
    return living[0] if len(living) == 1 else None


def promote_sole_living_party_member(
    emulator: MemoryReader,
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    *,
    label: str,
) -> RawGameState:
    """Move the only living party member to lead so field traversal can resume."""

    before = reader.read()
    target = sole_living_party_index(before.party_hp or ())
    if target is None:
        raise Gen1PartyMenuError(f"{label} lacks exactly one living party member.")
    if target == 0:
        return before
    return swap_party_slots(
        emulator,
        executor,
        reader,
        source_index=target,
        destination_index=0,
        label=label,
    )


def promote_species_to_lead(
    emulator: MemoryReader,
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    species_id: int,
    *,
    label: str,
) -> RawGameState:
    """Promote one observed living species after a healing boundary."""

    before = reader.read()
    species = before.party_species_ids or ()
    try:
        target = species.index(species_id)
    except ValueError as error:
        raise Gen1PartyMenuError(f"{label} target species is absent.") from error
    if target == 0:
        return before
    return swap_party_slots(
        emulator,
        executor,
        reader,
        source_index=target,
        destination_index=0,
        label=label,
    )


def swap_party_slots(
    emulator: MemoryReader,
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    *,
    source_index: int,
    destination_index: int,
    label: str,
) -> RawGameState:
    """Swap two field party slots through live cursors and verify all party order."""

    before = reader.read()
    species = before.party_species_ids or ()
    hp = before.party_hp or ()
    moves = before.party_moves or ()
    if (
        before.battle_state != 0
        or not reader.read_input_readiness().ready
        or source_index == destination_index
        or min(source_index, destination_index) < 0
        or max(source_index, destination_index) >= len(species)
        or len(hp) != len(species)
        or len(moves) != len(species)
        or hp[source_index] <= 0
    ):
        raise Gen1PartyMenuError(f"{label} has an invalid field-party starting gate.")

    expected_species = list(species)
    expected_hp = list(hp)
    expected_moves = list(moves)
    expected_species[source_index], expected_species[destination_index] = (
        expected_species[destination_index],
        expected_species[source_index],
    )
    expected_hp[source_index], expected_hp[destination_index] = (
        expected_hp[destination_index],
        expected_hp[source_index],
    )
    expected_moves[source_index], expected_moves[destination_index] = (
        expected_moves[destination_index],
        expected_moves[source_index],
    )

    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, 180)
    _select_cursor(executor, emulator, 1, label=f"{label} POKéMON")
    _pulse(executor, MacroActionKind.CONFIRM)
    _select_cursor(executor, emulator, source_index, label=f"{label} source")
    _pulse(executor, MacroActionKind.CONFIRM)

    field_move_count = sum(move in GEN1_FIELD_MOVE_IDS for move in moves[source_index])
    switch_row = field_move_count + 1
    _select_cursor(executor, emulator, switch_row, label=f"{label} SWITCH")
    _pulse(executor, MacroActionKind.CONFIRM)
    _select_cursor(executor, emulator, destination_index, label=f"{label} destination")
    _pulse(executor, MacroActionKind.CONFIRM)

    for _ in range(8):
        if reader.read_input_readiness().ready:
            break
        _pulse(executor, MacroActionKind.CANCEL)
    else:
        raise Gen1PartyMenuError(f"{label} did not restore field input.")

    after = reader.read()
    if (
        after.map_id != before.map_id
        or (after.player_x, after.player_y) != (before.player_x, before.player_y)
        or after.battle_state != 0
        or after.party_species_ids != tuple(expected_species)
        or after.party_hp != tuple(expected_hp)
        or after.party_moves != tuple(expected_moves)
        or not reader.read_input_readiness().ready
    ):
        raise Gen1PartyMenuError(f"{label} failed its persistent party-order gate.")
    return after


def _select_cursor(
    executor: ActionExecutor,
    emulator: MemoryReader,
    target: int,
    *,
    label: str,
) -> None:
    for _ in range(12):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            return
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < target else "up",
            frames=120,
        )
    raise Gen1PartyMenuError(f"{label} could not select its observed cursor.")


def _pulse(
    executor: ActionExecutor,
    kind: MacroActionKind,
    value: str | None = None,
    *,
    frames: int = 180,
) -> None:
    executor.execute(MacroAction(kind, value))
    _wait(executor, frames)


def _wait(executor: ActionExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
