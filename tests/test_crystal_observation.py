from __future__ import annotations

from collections import defaultdict

import pytest

from pokemon_crystal_completion.observation import (
    CRYSTAL_BOX_OBSERVATION_BYTES,
    CRYSTAL_PARTY_CAPACITY,
    CRYSTAL_PARTY_STRUCT_LENGTH,
    CRYSTAL_POKEDEX_FLAG_BYTES,
    CrystalObservationBundle,
    CrystalObservationError,
    CrystalStorageObservation,
    decode_crystal_box,
    decode_crystal_inventory,
    decode_crystal_party,
    decode_crystal_pokedex,
    derive_crystal_ownership_progress,
    read_crystal_inventory,
    read_crystal_observation_bundle,
    read_crystal_party,
    read_crystal_pokedex,
    read_crystal_storage,
)
from pokemon_crystal_completion.source_contract import (
    CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL,
    CRYSTAL_OBSERVATION_SYMBOLS,
    CRYSTAL_STORED_BOX_SRAM_SYMBOLS,
)
from pokemon_red_completion.party import StatusCondition


def _party_bytes() -> tuple[bytes, bytes]:
    species = bytes((155, 200, 0xFF, 0, 0, 0, 0))
    structs = bytearray(CRYSTAL_PARTY_CAPACITY * CRYSTAL_PARTY_STRUCT_LENGTH)

    first = 0
    structs[first + 0x00] = 155
    structs[first + 0x01] = 0xAC
    structs[first + 0x02 : first + 0x06] = bytes((1, 0, 2, 3))
    structs[first + 0x08 : first + 0x0B] = bytes((0x01, 0x02, 0x03))
    structs[first + 0x17 : first + 0x1B] = bytes((0xC5, 0, 10, 20))
    structs[first + 0x1F] = 30
    structs[first + 0x20] = 0x08
    structs[first + 0x22 : first + 0x24] = (30).to_bytes(2, "big")
    structs[first + 0x24 : first + 0x26] = (60).to_bytes(2, "big")

    second = CRYSTAL_PARTY_STRUCT_LENGTH
    structs[second + 0x00] = 200
    structs[second + 0x02 : second + 0x06] = bytes((4, 5, 6, 7))
    structs[second + 0x08 : second + 0x0B] = bytes((0x04, 0x05, 0x06))
    structs[second + 0x17 : second + 0x1B] = bytes((12, 13, 14, 15))
    structs[second + 0x1F] = 40
    structs[second + 0x20] = 0x03
    structs[second + 0x22 : second + 0x24] = (0).to_bytes(2, "big")
    structs[second + 0x24 : second + 0x26] = (100).to_bytes(2, "big")
    return species, bytes(structs)


def _flags(*species: int) -> bytes:
    payload = bytearray(CRYSTAL_POKEDEX_FLAG_BYTES)
    for number in species:
        index = number - 1
        payload[index // 8] |= 1 << (index % 8)
    return bytes(payload)


def _species_for_count(species: bytes, count: int) -> bytes:
    payload = bytearray(species)
    payload[count] = 0xFF
    return bytes(payload)


def _box_payload(*specimens: tuple[int | None, int]) -> bytes:
    payload = bytearray(CRYSTAL_BOX_OBSERVATION_BYTES)
    payload[0] = len(specimens)
    payload[1 + len(specimens)] = 0xFF
    structs_start = 22
    for index, (species_id, level) in enumerate(specimens):
        start = structs_start + index * 0x20
        if species_id is None:
            payload[1 + index] = 0xFD
            payload[start] = 172
        else:
            payload[1 + index] = species_id
            payload[start] = species_id
        payload[start + 0x1F] = level
    return bytes(payload)


def _pocket_payload(capacity: int, *stacks: tuple[int, int]) -> bytes:
    payload = bytearray(capacity * 2 + 1)
    for index, (item_id, quantity) in enumerate(stacks):
        payload[index * 2 : index * 2 + 2] = bytes((item_id, quantity))
    payload[len(stacks) * 2] = 0xFF
    return bytes(payload)


def test_party_decoder_uses_gen_two_offsets_endianness_and_pp_mask() -> None:
    species, structs = _party_bytes()
    party = decode_crystal_party(count=2, species=species, structs=structs)

    assert party.species_ids() == (155, 200)
    first, second = party.members
    assert first.level == 30
    assert (first.hp, first.max_hp) == (30, 60)
    assert first.status is StatusCondition.POISON
    assert first.experience == 0x010203
    assert first.held_item_ref == "pokemon.crystal:item:172"
    assert tuple(move.move_id for move in first.moves) == (1, 0, 2, 3)
    assert tuple(move.current_pp for move in first.moves) == (5, 0, 10, 20)
    assert second.status is StatusCondition.SLEEP
    assert second.is_fainted


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        (0x00, StatusCondition.HEALTHY),
        (0x01, StatusCondition.SLEEP),
        (0x07, StatusCondition.SLEEP),
        (0x08, StatusCondition.POISON),
        (0x10, StatusCondition.BURN),
        (0x20, StatusCondition.FREEZE),
        (0x40, StatusCondition.PARALYSIS),
    ),
)
def test_party_decoder_maps_every_valid_persistent_status(
    raw: int, expected: StatusCondition
) -> None:
    species, original = _party_bytes()
    structs = bytearray(original)
    structs[0x20] = raw

    party = decode_crystal_party(
        count=1,
        species=_species_for_count(species, 1),
        structs=bytes(structs),
    )
    assert party.members[0].status is expected


@pytest.mark.parametrize("raw", (0x09, 0x18, 0x80, 0xFF))
def test_party_decoder_rejects_incompatible_status_bits(raw: int) -> None:
    species, original = _party_bytes()
    structs = bytearray(original)
    structs[0x20] = raw

    with pytest.raises(CrystalObservationError, match="incompatible"):
        decode_crystal_party(
            count=1,
            species=_species_for_count(species, 1),
            structs=bytes(structs),
        )


def test_party_decoder_rejects_wrong_stride_species_or_length() -> None:
    species, original = _party_bytes()
    structs = bytearray(original)
    structs[CRYSTAL_PARTY_STRUCT_LENGTH] = 199
    with pytest.raises(CrystalObservationError, match="disagree"):
        decode_crystal_party(count=2, species=species, structs=bytes(structs))
    with pytest.raises(CrystalObservationError, match="288 bytes"):
        decode_crystal_party(count=2, species=species, structs=original[:-1])
    with pytest.raises(CrystalObservationError, match="between zero and six"):
        decode_crystal_party(count=7, species=species, structs=original)
    unterminated = bytearray(species)
    unterminated[2] = 1
    with pytest.raises(CrystalObservationError, match="terminator"):
        decode_crystal_party(count=2, species=bytes(unterminated), structs=original)
    egg = bytearray(species)
    egg[0] = 0xFD
    egg[1] = 0xFF
    with pytest.raises(CrystalObservationError, match="egg-aware"):
        decode_crystal_party(count=1, species=bytes(egg), structs=original)


def test_pokedex_decoder_excludes_event_only_celebi_and_rejects_padding() -> None:
    progress = decode_crystal_pokedex(
        caught=_flags(1, 250, 251),
        seen=_flags(1, 2, 250, 251),
    )

    assert (progress.registered.completed, progress.registered.target) == (2, 250)
    assert (progress.seen.completed, progress.seen.target) == (3, 250)

    with pytest.raises(CrystalObservationError, match="padding"):
        decode_crystal_pokedex(caught=_flags(252), seen=_flags(252))
    with pytest.raises(CrystalObservationError, match="also be seen"):
        decode_crystal_pokedex(caught=_flags(10), seen=_flags())


def test_box_decoder_keeps_eggs_opaque_and_tracks_level_cap_ownership() -> None:
    box = decode_crystal_box(
        _box_payload((1, 100), (None, 5), (251, 42)),
        box_number=4,
    )

    assert box.box_number == 4
    assert box.free_slots == 17
    assert tuple(item.species_id for item in box.specimens) == (1, None, 251)
    assert box.specimens[1].is_egg

    boxes = tuple(
        box
        if number == 4
        else decode_crystal_box(_box_payload(), box_number=number)
        for number in range(1, 15)
    )
    storage = CrystalStorageObservation(current_box_number=4, boxes=boxes)
    assert storage.occupied_slots == 3
    assert storage.free_slots == 277
    assert storage.egg_count == 1
    assert storage.living_species_ids == frozenset({1, 251})
    assert storage.level_cap_species_ids == frozenset({1})

    party_species, structs = _party_bytes()
    ownership = derive_crystal_ownership_progress(
        decode_crystal_party(count=2, species=party_species, structs=structs),
        storage,
    )
    assert (ownership.living.completed, ownership.living.target) == (3, 250)
    assert (ownership.level_cap.completed, ownership.level_cap.target) == (1, 250)
    assert ownership.boxed_specimens == 3
    assert ownership.opaque_eggs == 1
    assert ownership.free_storage_slots == 277


def test_box_decoder_rejects_count_terminator_species_and_level_corruption() -> None:
    excessive = bytearray(_box_payload())
    excessive[0] = 21
    with pytest.raises(CrystalObservationError, match="count"):
        decode_crystal_box(bytes(excessive), box_number=1)

    unterminated = bytearray(_box_payload((1, 5)))
    unterminated[2] = 0
    with pytest.raises(CrystalObservationError, match="terminator"):
        decode_crystal_box(bytes(unterminated), box_number=1)

    mismatch = bytearray(_box_payload((1, 5)))
    mismatch[22] = 2
    with pytest.raises(CrystalObservationError, match="disagree"):
        decode_crystal_box(bytes(mismatch), box_number=1)

    zero_level = bytearray(_box_payload((1, 5)))
    zero_level[22 + 0x1F] = 0
    with pytest.raises(CrystalObservationError, match="level"):
        decode_crystal_box(bytes(zero_level), box_number=1)


def test_inventory_decoder_counts_capture_and_recovery_resources() -> None:
    inventory = decode_crystal_inventory(
        item_count=4,
        items=_pocket_payload(
            20,
            (0x10, 3),
            (0x27, 2),
            (0x09, 4),
            (0xAD, 5),
        ),
        ball_count=2,
        balls=_pocket_payload(12, (0x05, 7), (0xA4, 2)),
    )

    assert inventory.capture_item_count == 9
    assert inventory.recovery_item_count == 10
    assert tuple(item.item_id for item in inventory.items) == (0x10, 0x27, 0x09, 0xAD)


def test_inventory_decoder_rejects_wrong_pocket_duplicate_or_terminator() -> None:
    with pytest.raises(CrystalObservationError, match="wrong pocket"):
        decode_crystal_inventory(
            item_count=1,
            items=_pocket_payload(20, (0x05, 1)),
            ball_count=0,
            balls=_pocket_payload(12),
        )
    with pytest.raises(CrystalObservationError, match="repeats"):
        decode_crystal_inventory(
            item_count=2,
            items=_pocket_payload(20, (0x10, 1), (0x10, 2)),
            ball_count=0,
            balls=_pocket_payload(12),
        )
    unterminated = bytearray(_pocket_payload(12, (0x05, 1)))
    unterminated[2] = 0
    with pytest.raises(CrystalObservationError, match="terminator"):
        decode_crystal_inventory(
            item_count=0,
            items=_pocket_payload(20),
            ball_count=1,
            balls=bytes(unterminated),
        )


class _StableMemory:
    def __init__(self, values: dict[tuple[int, int, int], bytes]) -> None:
        self.values = values
        self.calls: list[tuple[int, int, int]] = []

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        key = (bank, address, length)
        self.calls.append(key)
        return self.values[key]


class _StableStorageMemory:
    def __init__(
        self,
        *,
        current_box_index: int,
        active_box: bytes,
        stored_boxes: dict[int, bytes],
    ) -> None:
        self.current_box_index = current_box_index
        self.active_box = active_box
        self.stored_boxes = stored_boxes
        self.sram_calls: list[tuple[int, int, int]] = []

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        symbol = CRYSTAL_OBSERVATION_SYMBOLS["wCurBox"]
        assert (bank, address, length) == (symbol.bank, symbol.address, 1)
        return bytes((self.current_box_index,))

    def read_cartridge_ram(self, bank: int, address: int, length: int) -> bytes:
        self.sram_calls.append((bank, address, length))
        if (bank, address) == (
            CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.bank,
            CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.address,
        ):
            return self.active_box
        box_number = next(
            number
            for number, symbol in CRYSTAL_STORED_BOX_SRAM_SYMBOLS.items()
            if (symbol.bank, symbol.address) == (bank, address)
        )
        return self.stored_boxes[box_number]


class _StableCombinedMemory:
    def __init__(
        self,
        *,
        wram: dict[tuple[int, int, int], bytes],
        active_box: bytes,
        stored_boxes: dict[int, bytes],
    ) -> None:
        self.wram = wram
        self.active_box = active_box
        self.stored_boxes = stored_boxes
        self.wram_calls: list[tuple[int, int, int]] = []
        self.sram_calls: list[tuple[int, int, int]] = []

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        key = (bank, address, length)
        self.wram_calls.append(key)
        return self.wram[key]

    def read_cartridge_ram(self, bank: int, address: int, length: int) -> bytes:
        self.sram_calls.append((bank, address, length))
        if (bank, address) == (
            CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.bank,
            CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.address,
        ):
            return self.active_box
        box_number = next(
            number
            for number, symbol in CRYSTAL_STORED_BOX_SRAM_SYMBOLS.items()
            if (symbol.bank, symbol.address) == (bank, address)
        )
        return self.stored_boxes[box_number]


def _combined_memory(*, caught: bytes | None = None) -> _StableCombinedMemory:
    species, structs = _party_bytes()
    blank = _box_payload()

    def value(name: str, length: int, payload: bytes) -> tuple[tuple[int, int, int], bytes]:
        symbol = CRYSTAL_OBSERVATION_SYMBOLS[name]
        return (symbol.bank, symbol.address, length), payload

    registered = caught if caught is not None else _flags(1, 155, 200)
    wram = dict(
        (
            value("wPartyCount", 1, bytes((2,))),
            value("wPartySpecies", 7, species),
            value("wPartyMon1", 288, structs),
            value("wPokedexCaught", 32, registered),
            value("wPokedexSeen", 32, registered),
            value("wCurBox", 1, bytes((0,))),
            value("wNumItems", 1, bytes((1,))),
            value("wItems", 41, _pocket_payload(20, (0x10, 3))),
            value("wNumBalls", 1, bytes((1,))),
            value("wBalls", 25, _pocket_payload(12, (0x05, 8))),
        )
    )
    return _StableCombinedMemory(
        wram=wram,
        active_box=_box_payload((1, 100)),
        stored_boxes={number: blank for number in range(1, 15)},
    )


def test_live_read_helpers_request_bank_one_and_double_check_coherence() -> None:
    species, structs = _party_bytes()
    values = {
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wPartyCount"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wPartyCount"].address,
            1,
        ): bytes((2,)),
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wPartySpecies"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wPartySpecies"].address,
            7,
        ): species,
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wPartyMon1"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wPartyMon1"].address,
            288,
        ): structs,
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wPokedexCaught"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wPokedexCaught"].address,
            32,
        ): _flags(1, 2),
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wPokedexSeen"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wPokedexSeen"].address,
            32,
        ): _flags(1, 2, 3),
    }
    memory = _StableMemory(values)

    assert read_crystal_party(memory).size == 2
    assert read_crystal_pokedex(memory).registered.completed == 2
    assert all(bank == 1 for bank, _address, _length in memory.calls)
    counts = CounterLike(memory.calls)
    assert counts.for_symbol("wPartyCount", 1) == 2
    assert counts.for_symbol("wPartySpecies", 7) == 2
    assert counts.for_symbol("wPartyMon1", 288) == 2
    assert counts.for_symbol("wPokedexCaught", 32) == 2
    assert counts.for_symbol("wPokedexSeen", 32) == 2


def test_live_inventory_reader_double_checks_both_pockets() -> None:
    values = {
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wNumItems"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wNumItems"].address,
            1,
        ): bytes((2,)),
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wItems"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wItems"].address,
            41,
        ): _pocket_payload(20, (0x10, 3), (0x09, 1)),
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wNumBalls"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wNumBalls"].address,
            1,
        ): bytes((1,)),
        (
            CRYSTAL_OBSERVATION_SYMBOLS["wBalls"].bank,
            CRYSTAL_OBSERVATION_SYMBOLS["wBalls"].address,
            25,
        ): _pocket_payload(12, (0x05, 8)),
    }
    memory = _StableMemory(values)

    inventory = read_crystal_inventory(memory)

    assert inventory.capture_item_count == 8
    assert inventory.recovery_item_count == 3
    counts = CounterLike(memory.calls)
    assert counts.for_symbol("wNumItems", 1) == 2
    assert counts.for_symbol("wItems", 41) == 2
    assert counts.for_symbol("wNumBalls", 1) == 2
    assert counts.for_symbol("wBalls", 25) == 2


def test_live_storage_reader_uses_active_copy_and_all_other_saved_boxes() -> None:
    blank = _box_payload()
    stored = {number: blank for number in range(1, 15)}
    stored[1] = _box_payload((99, 20))  # stale current-box copy must not be read
    stored[2] = _box_payload((2, 50))
    memory = _StableStorageMemory(
        current_box_index=0,
        active_box=_box_payload((1, 100), (None, 5)),
        stored_boxes=stored,
    )

    storage = read_crystal_storage(memory)

    assert storage.current_box_number == 1
    assert storage.occupied_slots == 3
    assert storage.egg_count == 1
    assert storage.living_species_ids == frozenset({1, 2})
    assert storage.level_cap_species_ids == frozenset({1})
    stale = CRYSTAL_STORED_BOX_SRAM_SYMBOLS[1]
    assert (stale.bank, stale.address, CRYSTAL_BOX_OBSERVATION_BYTES) not in memory.sram_calls
    assert memory.sram_calls.count(
        (
            CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.bank,
            CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.address,
            CRYSTAL_BOX_OBSERVATION_BYTES,
        )
    ) == 2
    assert len(memory.sram_calls) == 28


def test_live_storage_reader_retries_a_torn_active_box() -> None:
    blank = _box_payload()

    class TornActiveMemory(_StableStorageMemory):
        active_reads = 0

        def read_cartridge_ram(self, bank: int, address: int, length: int) -> bytes:
            if (bank, address) == (
                CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.bank,
                CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.address,
            ):
                self.active_reads += 1
                self.sram_calls.append((bank, address, length))
                if self.active_reads == 1:
                    return _box_payload((1, 4))
                return _box_payload((1, 5))
            return super().read_cartridge_ram(bank, address, length)

    memory = TornActiveMemory(
        current_box_index=0,
        active_box=blank,
        stored_boxes={number: blank for number in range(1, 15)},
    )

    storage = read_crystal_storage(memory, maximum_attempts=2)
    assert storage.boxes[0].specimens[0].level == 5
    assert memory.active_reads == 4


class CounterLike:
    def __init__(self, calls: list[tuple[int, int, int]]) -> None:
        self._counts: defaultdict[tuple[int, int, int], int] = defaultdict(int)
        for call in calls:
            self._counts[call] += 1

    def for_symbol(self, name: str, length: int) -> int:
        symbol = CRYSTAL_OBSERVATION_SYMBOLS[name]
        return self._counts[(symbol.bank, symbol.address, length)]


def test_live_party_reader_retries_a_torn_snapshot_then_succeeds() -> None:
    species, structs = _party_bytes()

    class TornOnceMemory:
        count_reads = 0

        def read_wram(self, bank: int, address: int, length: int) -> bytes:
            del bank
            if address == CRYSTAL_OBSERVATION_SYMBOLS["wPartyCount"].address:
                self.count_reads += 1
                return bytes((1 if self.count_reads == 1 else 2,))
            if address == CRYSTAL_OBSERVATION_SYMBOLS["wPartySpecies"].address:
                return species
            if address == CRYSTAL_OBSERVATION_SYMBOLS["wPartyMon1"].address:
                return structs
            raise AssertionError((address, length))

    memory = TornOnceMemory()
    assert read_crystal_party(memory, maximum_attempts=2).size == 2
    assert memory.count_reads == 4


def test_live_party_reader_retries_when_struct_changes_without_roster_change() -> None:
    species, structs = _party_bytes()

    class TornStructOnceMemory:
        struct_reads = 0

        def read_wram(self, bank: int, address: int, length: int) -> bytes:
            del bank, length
            if address == CRYSTAL_OBSERVATION_SYMBOLS["wPartyCount"].address:
                return bytes((2,))
            if address == CRYSTAL_OBSERVATION_SYMBOLS["wPartySpecies"].address:
                return species
            if address == CRYSTAL_OBSERVATION_SYMBOLS["wPartyMon1"].address:
                self.struct_reads += 1
                if self.struct_reads == 1:
                    torn = bytearray(structs)
                    torn[0x22 : 0x24] = (29).to_bytes(2, "big")
                    return bytes(torn)
                return structs
            raise AssertionError(address)

    memory = TornStructOnceMemory()
    assert read_crystal_party(memory, maximum_attempts=2).members[0].hp == 30
    assert memory.struct_reads == 4


def test_live_bundle_is_stable_cross_checked_and_identity_free() -> None:
    memory = _combined_memory()

    bundle = read_crystal_observation_bundle(memory)

    assert isinstance(bundle, CrystalObservationBundle)
    assert bundle.party.species_ids() == (155, 200)
    assert bundle.ownership.living.completed == 3
    assert bundle.public_dict() == {
        "party": {
            "size": 2,
            "capacity": 6,
            "minimum_level": 30,
            "maximum_level": 40,
            "fainted": 1,
        },
        "pokedex": {"registered": 3, "seen": 3, "target": 250},
        "ownership": {
            "living": 3,
            "level_cap": 1,
            "target": 250,
            "boxed_specimens": 1,
            "opaque_eggs": 0,
        },
        "storage": {"current_box": 1, "occupied_slots": 1, "free_slots": 279},
        "resources": {
            "capture_items": 8,
            "recovery_items": 3,
            "item_stacks": 1,
            "ball_stacks": 1,
        },
    }
    assert "155" not in str(bundle.public_dict())
    assert len(memory.sram_calls) == 56


def test_live_bundle_rejects_living_species_missing_from_registered_count() -> None:
    memory = _combined_memory(caught=_flags(155, 200))

    with pytest.raises(CrystalObservationError, match="living ownership exceeds"):
        read_crystal_observation_bundle(memory, maximum_attempts=1)


def test_live_bundle_retries_a_cross_component_change() -> None:
    original = _combined_memory()

    class CrossComponentChange(_StableCombinedMemory):
        caught_reads = 0
        seen_reads = 0

        def read_wram(self, bank: int, address: int, length: int) -> bytes:
            if address == CRYSTAL_OBSERVATION_SYMBOLS["wPokedexCaught"].address:
                self.caught_reads += 1
                return _flags(1, 155, 200) if self.caught_reads <= 2 else _flags(1, 2, 155, 200)
            if address == CRYSTAL_OBSERVATION_SYMBOLS["wPokedexSeen"].address:
                self.seen_reads += 1
                return _flags(1, 155, 200) if self.seen_reads <= 2 else _flags(1, 2, 155, 200)
            return super().read_wram(bank, address, length)

    memory = CrossComponentChange(
        wram=original.wram,
        active_box=original.active_box,
        stored_boxes=original.stored_boxes,
    )

    bundle = read_crystal_observation_bundle(memory, maximum_attempts=2)

    assert bundle.pokedex.registered.completed == 4
    assert memory.caught_reads == 8
    assert memory.seen_reads == 8


@pytest.mark.parametrize("maximum_attempts", (0, -1, True, 1.5))
def test_live_bundle_requires_a_positive_integer_bound(maximum_attempts: object) -> None:
    with pytest.raises(CrystalObservationError, match="positive attempt bound"):
        read_crystal_observation_bundle(  # type: ignore[arg-type]
            _combined_memory(),
            maximum_attempts=maximum_attempts,  # type: ignore[arg-type]
        )
