"""Independent literal Red box layout and private retained-loan invariants."""

from hashlib import sha256

import pytest

from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress, SemanticStateError
from pokemon_red_completion.red_party import PokemonRedPartyReader


class Memory:
    def __init__(self, *, initialized=True):
        self.values = {
            RamAddress.CURRENT_BOX_NUMBER: 0x81 if initialized else 1,
            RamAddress.CURRENT_BOX_COUNT: 0,
        }
        self.banks = {}
        self.bank_reads = 0
        for bank in (2, 3):
            data = bytearray(6 * 0x462 + 7)
            if bank == 3:
                base = 0x462  # Box8, with an actual second slot.
                data[base : base + 4] = bytes([2, 17, 28, 255])
                for slot, species, level, xp, ot, dvs in (
                    (0, 17, 22, 0x010203, b"\x12\x34", b"\x56\x78"),
                    (1, 28, 66, 0x020304, b"\x9a\xbc", b"\xde\xf0"),
                ):
                    at = base + 22 + slot * 33
                    data[at] = species
                    data[at + 3] = level
                    data[at + 12 : at + 14] = ot
                    data[at + 14 : at + 17] = xp.to_bytes(3, "big")
                    data[at + 27 : at + 29] = dvs
            size = 6 * 0x462
            data[size] = 255 - sum(data[:size]) % 256
            for index in range(6):
                data[size + 1 + index] = 255 - sum(data[index * 0x462 : (index + 1) * 0x462]) % 256
            self.banks[bank] = bytes(data)

    def read_u8(self, address):
        return self.values.get(int(address), 0)

    def read_cartridge_ram_u8(self, bank, address):
        self.bank_reads += 1
        return self.banks[bank][address - 0xA000]


def test_storage_identity_decodes_verified_bank_slot_and_matches_party_fingerprint():
    memory = Memory()
    before = memory.values.copy(), memory.banks.copy()
    members = PokemonRedStateReader(memory).read_box_specimen_identities()
    assert [
        (
            m.box_index,
            m.box_slot,
            m.species_id,
            m.level,
            m.experience,
            m.original_trainer_id,
            m.determinant_values,
        )
        for m in members
    ] == [
        (7, 1, 17, 22, 0x010203, 0x1234, (0x56, 0x78)),
        (7, 2, 28, 66, 0x020304, 0x9ABC, (0xDE, 0xF0)),
    ]
    memory.values.update(
        {
            RamAddress.PARTY_COUNT: 1,
            int(RamAddress.PARTY_MON_1) + 12: 0x12,
            int(RamAddress.PARTY_MON_1) + 13: 0x34,
            int(RamAddress.PARTY_MON_1) + 27: 0x56,
            int(RamAddress.PARTY_MON_1) + 28: 0x78,
        }
    )
    assert (
        members[0].preparation_ref == PokemonRedPartyReader(memory).preparation_specimen_refs()[0]
    )
    assert (
        members[1].preparation_ref
        == "red-preparation:" + sha256(bytes.fromhex("9abcdef0")).hexdigest()
    )
    assert memory.banks == before[1]


def test_live_box_overlays_stale_saved_storage_and_uninitialized_boxes_are_empty():
    memory = Memory()
    memory.values.update(
        {
            RamAddress.CURRENT_BOX_NUMBER: 0x87,
            RamAddress.CURRENT_BOX_COUNT: 1,
            RamAddress.CURRENT_BOX_SPECIES: 64,
            RamAddress.CURRENT_BOX_MONS: 64,
            int(RamAddress.CURRENT_BOX_MONS) + 3: 55,
            int(RamAddress.CURRENT_BOX_MONS) + 12: 0x11,
            int(RamAddress.CURRENT_BOX_MONS) + 14: 1,
            int(RamAddress.CURRENT_BOX_MONS) + 27: 0x22,
        }
    )
    members = PokemonRedStateReader(memory).read_box_specimen_identities()
    assert [(m.box_index, m.species_id, m.level, m.experience) for m in members] == [
        (7, 64, 55, 65536)
    ]
    fresh = Memory(initialized=False)
    assert PokemonRedStateReader(fresh).read_box_specimen_identities() == ()
    assert fresh.bank_reads == 0


def test_storage_identity_rejects_checksum_corruption():
    memory = Memory()
    data = bytearray(memory.banks[3])
    data[0x462 + 22 + 14] ^= 1
    memory.banks[3] = bytes(data)
    with pytest.raises(SemanticStateError, match="checksum"):
        PokemonRedStateReader(memory).read_box_specimen_identities()


def test_storage_identity_rejects_box_change_during_census():
    class Changing(Memory):
        def read_cartridge_ram_u8(self, bank, address):
            self.values[RamAddress.CURRENT_BOX_NUMBER] = 0x82
            return super().read_cartridge_ram_u8(bank, address)

    with pytest.raises(SemanticStateError, match="changed"):
        PokemonRedStateReader(Changing()).read_box_specimen_identities()


def test_storage_identity_rejects_live_fingerprint_change_even_with_same_membership():
    class Changing(Memory):
        def read_u8(self, address):
            value = super().read_u8(address)
            if address == int(RamAddress.CURRENT_BOX_MONS) + 27:
                self.values[int(address)] = value + 1
            return value

    memory = Changing(initialized=False)
    memory.values.update(
        {
            RamAddress.CURRENT_BOX_COUNT: 1,
            RamAddress.CURRENT_BOX_SPECIES: 17,
            RamAddress.CURRENT_BOX_MONS: 17,
            int(RamAddress.CURRENT_BOX_MONS) + 3: 22,
        }
    )
    with pytest.raises(SemanticStateError, match="changed"):
        PokemonRedStateReader(memory).read_box_specimen_identities()
