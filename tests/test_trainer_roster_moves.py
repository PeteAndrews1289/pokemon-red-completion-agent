"""Referee-only preservation of native trainer special moves; no policy feature."""

import pytest

from pokemon_red_completion.observation import (
    PARTY_MOVES_OFFSET,
    PARTY_STRUCT_STRIDE,
    PokemonRedStateReader,
    RamAddress,
    SemanticStateError,
)


class Memory:
    def __init__(self):
        self.data = {
            int(RamAddress.IS_IN_BATTLE): 2,
            int(RamAddress.ENEMY_PARTY_COUNT): 2,
            int(RamAddress.ENEMY_PARTY_SPECIES): 27,
            int(RamAddress.ENEMY_PARTY_SPECIES) + 1: 152,
            int(RamAddress.ENEMY_PARTY_SPECIES) + 2: 255,
        }
        for index, (species, moves) in enumerate(
            ((27, (33, 106, 55, 0)), (152, (33, 55, 106, 61)))
        ):
            base = int(RamAddress.ENEMY_PARTY_MON_1) + index * PARTY_STRUCT_STRIDE
            self.data[base] = species
            self.data.update({base + PARTY_MOVES_OFFSET + i: move for i, move in enumerate(moves)})

    def read_u8(self, address):
        return self.data.get(int(address), 0)


def test_preserves_native_override_and_zero_padding_without_writing():
    memory = Memory()
    before = dict(memory.data)
    assert PokemonRedStateReader(memory).read_enemy_party_roster_moves() == (
        (33, 106, 55, 0),
        (33, 55, 106, 61),
    )
    assert memory.data == before


@pytest.mark.parametrize(
    "address,value",
    [
        (RamAddress.IS_IN_BATTLE, 0),
        (RamAddress.IS_IN_BATTLE, 1),
        (RamAddress.ENEMY_PARTY_COUNT, 0),
        (RamAddress.ENEMY_PARTY_COUNT, 7),
        (int(RamAddress.ENEMY_PARTY_SPECIES) + 2, 0),
        (RamAddress.ENEMY_PARTY_MON_1, 152),
        (int(RamAddress.ENEMY_PARTY_MON_1) + PARTY_MOVES_OFFSET, 0),
        (int(RamAddress.ENEMY_PARTY_MON_1) + PARTY_MOVES_OFFSET + 1, 166),
    ],
)
def test_refuses_invalid_roster(address, value):
    memory = Memory()
    memory.data[int(address)] = value
    with pytest.raises(SemanticStateError):
        PokemonRedStateReader(memory).read_enemy_party_roster_moves()


def test_refuses_mid_read_change():
    class Changing(Memory):
        reads = 0

        def read_u8(self, address):
            if int(address) == int(RamAddress.ENEMY_PARTY_MON_1) + PARTY_MOVES_OFFSET:
                self.reads += 1
                return 33 if self.reads == 1 else 55
            return super().read_u8(address)

    with pytest.raises(SemanticStateError, match="changed"):
        PokemonRedStateReader(Changing()).read_enemy_party_roster_moves()
