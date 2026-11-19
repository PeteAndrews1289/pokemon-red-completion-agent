"""TRAIN setup stays isolated and every changed byte is disclosed."""

from types import SimpleNamespace

import pytest
from test_red_team_training import FakeMemory

from pokemon_red_completion.red_collection_teacher_learning import (
    set_isolated_training_member_level,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader, member_field_address


class Memory(FakeMemory):
    def __init__(self):
        super().__init__()
        self.writes = {}

    def read_u8(self, address):
        return self.writes.get(int(address), super().read_u8(address))

    def write_u8(self, address, value):
        self.writes[int(address)] = value


def cartridge():
    return SimpleNamespace(
        species=lambda _: SimpleNamespace(
            stats_with_dvs=lambda level, dvs: SimpleNamespace(
                max_hp=100, attack=101, defense=102, speed=103, special=104
            ),
            intrinsic_moves_at_level=lambda level: (33, 45, 163),
            experience_at_level=lambda level: level**3,
        )
    )


def test_teacher_level_fixture_changes_only_selected_member_and_matches_derived_party():
    memory = Memory()
    memory.set_party([(0x1C, 48), (59, 22), (0x40, 25)])
    before = PokemonRedPartyReader(memory).read()
    rows = set_isolated_training_member_level(
        memory,
        partition="train",
        isolated_training_setup=True,
        party_index=1,
        level=49,
        cartridge=cartridge(),
    )
    after = PokemonRedPartyReader(memory).read()
    assert after.members[0] == before.members[0] and after.members[2] == before.members[2]
    target = after.members[1]
    assert target.level == 49 and target.experience == 49**3 and target.hp == target.max_hp == 100
    assert [m.move_id for m in target.known_moves] == [33, 45, 163]
    assert all(r["after"] == memory.read_u8(r["address"]) for r in rows)
    assert all(
        member_field_address(1, 0) <= r["address"] <= member_field_address(1, 43) for r in rows
    )
    assert len(rows) == len(memory.writes)


@pytest.mark.parametrize(
    "bad",
    [
        {"partition": "development"},
        {"isolated_training_setup": False},
        {"party_index": True},
        {"party_index": 3},
        {"level": True},
        {"level": 0},
        {"level": 100},
    ],
)
def test_teacher_level_fixture_refuses_non_train_or_invalid_setup_without_writes(bad):
    memory = Memory()
    memory.set_party([(0x1C, 48), (59, 22), (0x40, 25)])
    kw = dict(
        partition="train",
        isolated_training_setup=True,
        party_index=1,
        level=49,
        cartridge=cartridge(),
    )
    kw.update(bad)
    with pytest.raises(ValueError):
        set_isolated_training_member_level(memory, **kw)
    assert memory.writes == {}


def test_alternate_supplied_species_is_train_only_and_baselines_native_stock():
    from pokemon_red_completion.observation import RamAddress

    memory = Memory()
    memory.set_party([(0x1C, 48), (59, 22), (0x40, 25)])
    before = PokemonRedPartyReader(memory).read()
    cart = cartridge()
    original = cart.species

    def species(code):
        row = original(code)
        row.types = (26, 26)
        row.catch_rate = 45
        row.national_number = 148
        return row

    cart.species = species
    rows = set_isolated_training_member_level(
        memory,
        partition="train",
        isolated_training_setup=True,
        party_index=1,
        level=54,
        cartridge=cart,
        species_id=89,
    )
    after = PokemonRedPartyReader(memory).read()
    assert after.members[1].species_id == 89 and after.members[1].level == 54
    assert after.members[0] == before.members[0] and after.members[2] == before.members[2]
    assert memory.read_u8(int(RamAddress.PARTY_SPECIES) + 1) == 89
    index = 147
    for base in (int(RamAddress.POKEDEX_OWNED), int(RamAddress.POKEDEX_SEEN)):
        assert memory.read_u8(base + index // 8) & (1 << (index % 8))
    assert all(memory.read_u8(row["address"]) == row["after"] for row in rows)


@pytest.mark.parametrize("species", [True, 0, 191, "89"])
def test_invalid_supplied_species_cannot_write(species):
    memory = Memory()
    memory.set_party([(59, 22)])
    with pytest.raises(ValueError):
        set_isolated_training_member_level(
            memory,
            partition="train",
            isolated_training_setup=True,
            party_index=0,
            level=54,
            cartridge=cartridge(),
            species_id=species,
        )
    assert not memory.writes


def test_explicit_level_fixture_preserves_owned_moves_including_travel():
    memory=Memory();memory.set_party([(28,40),(64,37)])
    memory.write_u8(member_field_address(1,8),19)
    memory.write_u8(member_field_address(1,9),15)
    memory.write_u8(member_field_address(1,29),15)
    before=PokemonRedPartyReader(memory).read().members[1]
    rows=set_isolated_training_member_level(memory,partition='train',isolated_training_setup=True,party_index=1,level=46,cartridge=cartridge(),preserve_moves=True)
    after=PokemonRedPartyReader(memory).read().members[1]
    assert [m.move_id for m in after.moves]==[m.move_id for m in before.moves]
    assert after.level==46 and after.experience==46**3 and rows


@pytest.mark.parametrize('extra',[dict(preserve_moves=1),dict(preserve_moves=True,species_id=89)])
def test_invalid_move_preservation_cannot_write(extra):
    memory=Memory();memory.set_party([(28,40),(64,37)])
    with pytest.raises(ValueError):set_isolated_training_member_level(memory,partition='train',isolated_training_setup=True,party_index=1,level=46,cartridge=cartridge(),**extra)
    assert memory.writes=={}
