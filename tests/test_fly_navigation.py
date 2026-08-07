"""Finding a field move in the party menu, without an emulator.

The town map itself cannot be tested here -- it writes to none of the standard
menu RAM, which is a measured fact rather than an assumption, so a fake has
nothing to model and nothing to answer with. What *can* be pinned is the part
that got the run into the town map in the first place: which party slot holds
Fly, and which submenu row it occupies.

That matters more than it looks. Training reorders the party constantly, so a
fixed slot index flies with whichever Pokemon happens to be second.
"""

from __future__ import annotations

import pytest

from pokemon_red_completion.blaine import (
    BlaineChapterError,
    _field_move_menu_indices,
    _fly_menu_indices,
)
from pokemon_red_completion.observation import RamAddress
from pokemon_red_completion.red_party import (
    LEVEL_OFFSET,
    MAX_HP_OFFSET,
    MOVES_OFFSET,
    PARTY_STRUCT_STRIDE,
    PP_OFFSET,
    SPECIES_OFFSET,
    STRUCT_BASE,
)

CUT = 0x0F
FLY = 0x13
SURF = 0x39
STRENGTH = 0x46
PECK = 0x40
TACKLE = 0x21


class FakeMemory:
    """Party memory built from explicit move lists."""

    def __init__(self, members: list[tuple[int, list[int]]]) -> None:
        self.members = members

    def read_u8(self, address: int) -> int:
        addr = int(address)
        if addr == int(RamAddress.PARTY_COUNT):
            return len(self.members)
        species_base = int(RamAddress.PARTY_SPECIES)
        if species_base <= addr < species_base + 6:
            index = addr - species_base
            return self.members[index][0] if index < len(self.members) else 0
        index, offset = divmod(addr - STRUCT_BASE, PARTY_STRUCT_STRIDE)
        if not 0 <= index < len(self.members):
            return 0
        species, moves = self.members[index]
        if offset == SPECIES_OFFSET:
            return species
        if offset == LEVEL_OFFSET:
            return 40
        if offset in (MAX_HP_OFFSET + 1, 2):
            return 80
        if MOVES_OFFSET <= offset < MOVES_OFFSET + 4:
            slot = offset - MOVES_OFFSET
            return moves[slot] if slot < len(moves) else 0
        if PP_OFFSET <= offset < PP_OFFSET + 4:
            slot = offset - PP_OFFSET
            return 20 if slot < len(moves) else 0
        return 0


def test_fly_is_found_wherever_the_party_has_been_reordered_to() -> None:
    """A fixed slot index would fly with the wrong Pokemon.

    Training swaps a trainee into slot one every time the venue changes, so the
    Fly holder does not stay put.
    """

    memory = FakeMemory(
        [
            (0x3B, [TACKLE]),  # the trainee, swapped to the front
            (0x1C, [SURF, STRENGTH]),
            (0x40, [PECK, CUT, FLY]),  # the Fly holder, now third
        ]
    )

    party_index, fly_row = _fly_menu_indices(memory)  # type: ignore[arg-type]

    assert party_index == 2, "it must follow the Pokemon, not a remembered slot"
    # Cut and Fly are its field moves in move order, so Fly is the second row.
    assert fly_row == 1


def test_the_submenu_row_counts_only_field_moves_before_fly() -> None:
    """The submenu lists usable field moves first, in move order.

    Measured, not assumed: this is the layout the party-switch investigation
    established and the town-map run corroborated -- a Pokemon knowing Cut and
    Fly reported a five-entry submenu.
    """

    only_fly = FakeMemory([(0x40, [PECK, FLY])])
    assert _fly_menu_indices(only_fly) == (0, 0)  # type: ignore[arg-type]

    three_before = FakeMemory([(0x1C, [SURF, CUT, STRENGTH, FLY])])
    assert _fly_menu_indices(three_before) == (0, 3)  # type: ignore[arg-type]


def test_a_party_that_cannot_fly_says_so() -> None:
    memory = FakeMemory([(0x3B, [TACKLE]), (0x1C, [SURF])])

    with pytest.raises(BlaineChapterError, match="knows Fly"):
        _fly_menu_indices(memory)  # type: ignore[arg-type]


DIG = 0x5B


def test_dig_follows_its_pokemon_through_a_reorder() -> None:
    """The bug a live run found the moment the party swap started working.

    Field Dig addressed Diglett as the third party member with Dig in move slot
    two. Both were true only while nothing ever moved the party. The first
    successful swap moved it, and the run stopped with "Diglett no longer
    exposes Dig in field slot zero".
    """

    memory = FakeMemory(
        [
            (0x3B, [TACKLE, DIG]),  # Diglett, swapped to the front as a trainee
            (0x1C, [SURF, STRENGTH]),
            (0x40, [PECK, CUT, FLY]),
        ]
    )

    assert _field_move_menu_indices(memory, DIG, "Dig") == (0, 0)  # type: ignore[arg-type]
    # And the same party still finds Fly on the third member, second field row.
    assert _fly_menu_indices(memory) == (2, 1)  # type: ignore[arg-type]


def test_a_field_move_row_counts_only_field_moves_before_it() -> None:
    """Damaging moves do not appear in the submenu, so they do not shift rows."""

    memory = FakeMemory([(0x1C, [TACKLE, SURF, PECK, STRENGTH])])

    assert _field_move_menu_indices(memory, SURF, "Surf") == (0, 0)  # type: ignore[arg-type]
    assert _field_move_menu_indices(memory, STRENGTH, "Strength") == (0, 1)  # type: ignore[arg-type]


def test_a_party_without_the_move_names_it() -> None:
    memory = FakeMemory([(0x3B, [TACKLE]), (0x1C, [SURF])])

    with pytest.raises(BlaineChapterError, match="knows Dig"):
        _field_move_menu_indices(memory, DIG, "Dig")  # type: ignore[arg-type]
