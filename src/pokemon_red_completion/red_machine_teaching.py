"""Explicit, cartridge-compatible TM/HM lessons through native menus.

The caller chooses the member and replaced move. This executor does not pick a
training strategy, obtain an unowned machine, or edit Pokémon memory.
"""

from __future__ import annotations

from dataclasses import dataclass

from .actions import MacroActionKind
from .red_battle_practice_cartridge import _TMHM_MOVES, RedPracticeCartridge
from .rom import verify_rom_bytes

_HM_MOVES = frozenset({15, 19, 57, 70, 148})


@dataclass(frozen=True, slots=True)
class RedMachineLesson:
    item_id: int
    party_slot: int
    replace_slot: int
    species_id: int
    before_moves: tuple[int, ...]
    move_id: int


def plan_machine_lesson(rom, reader, *, item_id, party_slot, replace_slot) -> RedMachineLesson:
    verify_rom_bytes(rom)
    if (
        type(item_id) is not int
        or not 196 <= item_id <= 250
        or type(party_slot) is not int
        or not 1 <= party_slot <= 6
        or type(replace_slot) is not int
        or not 1 <= replace_slot <= 4
    ):
        raise ValueError("invalid TM lesson selection")
    raw = reader.read()
    if (
        not raw.party_species_ids
        or not raw.party_moves
        or not raw.party_pp
        or party_slot > len(raw.party_species_ids)
        or raw.bag_items is None
        or dict(raw.bag_items).get(item_id, 0) <= 0
    ):
        raise ValueError("TM lesson lacks owned machine/party evidence")
    return _lesson_for_observed_moves(rom, item_id=item_id, party_slot=party_slot,
        replace_slot=replace_slot, species_id=raw.party_species_ids[party_slot - 1],
        moves=raw.party_moves[party_slot - 1])


def plan_observed_machine_lesson(rom, *, bag_items, species_id, moves,
                                 item_id, party_slot, replace_slot):
    """Quote observed storage moves; execution still rechecks the actual party."""
    verify_rom_bytes(rom)
    if (type(item_id) is not int or not 196 <= item_id <= 250
            or type(party_slot) is not int or not 1 <= party_slot <= 6
            or type(replace_slot) is not int or not 1 <= replace_slot <= 4):
        raise ValueError("invalid TM lesson selection")
    if (type(species_id) is not int or not 1 <= species_id <= 255
            or not isinstance(moves, tuple) or len(moves) != 4
            or any(type(m) is not int or not 0 <= m <= 165 for m in moves)
            or bag_items is None or dict(bag_items).get(item_id, 0) <= 0):
        raise ValueError("TM quote lacks observed moves/owned machine evidence")
    return _lesson_for_observed_moves(rom, item_id=item_id, party_slot=party_slot,
        replace_slot=replace_slot, species_id=species_id, moves=moves)


def _lesson_for_observed_moves(rom, *, item_id, party_slot, replace_slot, species_id, moves):
    move = _TMHM_MOVES[item_id - 201 if item_id >= 201 else 50 + item_id - 196]
    if (
        len(moves) != 4
        or (0 in moves and replace_slot != moves.index(0) + 1)
        or (0 in moves and any(moves[moves.index(0) :]))
        or move in moves
        or moves[replace_slot - 1] in _HM_MOVES
        or move not in RedPracticeCartridge(rom).species(species_id).tmhm_moves
    ):
        raise ValueError("TM lesson is incompatible, redundant or would forget an HM")
    return RedMachineLesson(item_id, party_slot, replace_slot, species_id, moves, move)


def execute_machine_lesson(
    emulator, actions, reader, lesson: RedMachineLesson, *, rom: bytes
) -> None:
    from .lavender import LavenderTiming, _close_menus, _open_bag, _select_bag_item, _select_cursor
    from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
    from .surge import _pulse

    before = reader.read()
    if (
        before.battle_state
        or not reader.read_input_readiness().ready
        or reader.read_bottom_dialogue_box_visible()
    ):
        raise ValueError("TM lesson needs field control")
    if (
        plan_machine_lesson(
            rom,
            reader,
            item_id=lesson.item_id,
            party_slot=lesson.party_slot,
            replace_slot=lesson.replace_slot,
        )
        != lesson
    ):
        raise ValueError("TM lesson changed before execution")
    updated_moves = [list(row) for row in before.party_moves]
    updated_moves[lesson.party_slot - 1][lesson.replace_slot - 1] = lesson.move_id
    expected_moves = tuple(tuple(row) for row in updated_moves)
    expected_bag = dict(before.bag_items)
    if lesson.item_id >= 201:
        expected_bag[lesson.item_id] -= 1
    expected_bag = {k: v for k, v in expected_bag.items() if v}
    updated_pp = [list(row) for row in before.party_pp]
    updated_pp[lesson.party_slot - 1][lesson.replace_slot - 1] = RED_BATTLE_CATALOG.resolve_move(
        pokemon_red_move_ref(lesson.move_id)
    ).max_pp
    expected_pp = tuple(tuple(row) for row in updated_pp)
    boxes, dex, pc = (
        reader.read_all_box_states(),
        reader.read_pokedex_state(),
        reader.read_pc_items(),
    )

    def protected():
        current = reader.read()
        for field in (
            "map_id",
            "player_x",
            "player_y",
            "player_money",
            "party_species_ids",
            "party_levels",
            "party_hp",
            "party_status",
            "badge_bits",
            "event_flags",
            "battle_state",
        ):
            if getattr(current, field) != getattr(before, field):
                raise RuntimeError("TM lesson changed protected " + field)
        if (
            reader.read_all_box_states() != boxes
            or reader.read_pokedex_state() != dex
            or reader.read_pc_items() != pc
        ):
            raise RuntimeError("TM lesson changed protected collection/PC")
        return current

    timing = LavenderTiming(wait_frames=120)
    _open_bag(actions, emulator, timing)
    _select_bag_item(actions, emulator, lesson.item_id, timing)
    stage = "party"
    for _ in range(96):
        raw = protected()
        if raw.party_moves == expected_moves and dict(raw.bag_items or ()) == expected_bag:
            _close_menus(actions, reader, timing)
            after = protected()
            if after.party_pp != expected_pp or after.party_moves != expected_moves:
                raise RuntimeError("TM lesson result or PP differs")
            return
        prompt = reader.read_machine_learning_input()
        if stage == "party" and prompt is not None and prompt[0] == "party":
            _select_cursor(actions, emulator, lesson.party_slot - 1, timing)
            _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            stage = "forget"
        elif stage == "forget" and prompt is not None and prompt[0] == "forget":
            _select_cursor(actions, emulator, lesson.replace_slot - 1, timing)
            _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            stage = "finish"
        elif prompt is not None and prompt[0] == "yes_no" and stage != "finish":
            _select_cursor(actions, emulator, 0, timing)
            _pulse(actions, MacroActionKind.CONFIRM, frames=120)
        elif prompt is not None:
            raise RuntimeError("TM lesson reached an unexpected selection boundary")
        else:
            _pulse(actions, MacroActionKind.CONFIRM, frames=120)
    raise RuntimeError("TM lesson did not settle within its bound")
