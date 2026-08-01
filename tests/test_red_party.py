from __future__ import annotations

import pytest

from pokemon_red_completion.observation import PARTY_LIMIT, RamAddress
from pokemon_red_completion.party import (
    MOVE_SLOT_LIMIT,
    PARTY_SLOT_LIMIT,
    PartyRole,
    StatusCondition,
)
from pokemon_red_completion.red_party import (
    EXPERIENCE_OFFSET,
    HP_OFFSET,
    LEVEL_OFFSET,
    MAX_HP_OFFSET,
    MOVES_OFFSET,
    PARTY_STRUCT_STRIDE,
    PP_OFFSET,
    RED_BALANCED_ROSTER,
    SPECIES_OFFSET,
    STATUS_OFFSET,
    STRUCT_BASE,
    PartyReadError,
    PokemonRedPartyReader,
    decode_status,
    member_field_address,
)


class RecordingMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values
        self.reads: list[int] = []

    def read_u8(self, address: int) -> int:
        self.reads.append(int(address))
        return self.values.get(int(address), 0)


def write_member(
    values: dict[int, int],
    index: int,
    *,
    species_id: int,
    level: int,
    hp: int,
    max_hp: int,
    status: int = 0,
    moves: tuple[int, ...] = (55, 57, 0, 0),
    pp: tuple[int, ...] = (15, 10, 0, 0),
    experience: int = 0,
) -> None:
    def put(offset: int, value: int) -> None:
        values[member_field_address(index, offset)] = value

    put(SPECIES_OFFSET, species_id)
    put(LEVEL_OFFSET, level)
    put(HP_OFFSET, (hp >> 8) & 0xFF)
    put(HP_OFFSET + 1, hp & 0xFF)
    put(MAX_HP_OFFSET, (max_hp >> 8) & 0xFF)
    put(MAX_HP_OFFSET + 1, max_hp & 0xFF)
    put(STATUS_OFFSET, status)
    for slot in range(MOVE_SLOT_LIMIT):
        put(MOVES_OFFSET + slot, moves[slot])
        put(PP_OFFSET + slot, pp[slot])
    for byte in range(3):
        put(EXPERIENCE_OFFSET + byte, (experience >> (8 * (2 - byte))) & 0xFF)


def memory_with(*members: dict[str, object], count: int | None = None) -> RecordingMemory:
    values: dict[int, int] = {
        int(RamAddress.PARTY_COUNT): len(members) if count is None else count
    }
    for index, spec in enumerate(members):
        write_member(values, index, **spec)  # type: ignore[arg-type]
    return RecordingMemory(values)


BLASTOISE = {
    "species_id": 0x1C,
    "level": 55,
    "hp": 160,
    "max_hp": 180,
    "moves": (57, 58, 55, 0),
    "pp": (15, 10, 5, 0),
    "experience": 200_000,
}
DUGTRIO = {"species_id": 0x76, "level": 48, "hp": 90, "max_hp": 120}


# --- offsets must agree with the already-verified named symbols --------------


@pytest.mark.parametrize(
    ("index", "offset", "symbol"),
    (
        (0, SPECIES_OFFSET, RamAddress.PARTY_MON_1),
        (0, HP_OFFSET, RamAddress.PARTY_MON_1_HP),
        (0, STATUS_OFFSET, RamAddress.PARTY_MON_1_STATUS),
        (0, MOVES_OFFSET, RamAddress.PARTY_MON_1_MOVES),
        (0, PP_OFFSET, RamAddress.PARTY_MON_1_PP),
        (0, LEVEL_OFFSET, RamAddress.PARTY_MON_1_LEVEL),
        (0, MAX_HP_OFFSET, RamAddress.PARTY_MON_1_MAX_HP),
        (1, HP_OFFSET, RamAddress.PARTY_MON_2_HP),
        (1, STATUS_OFFSET, RamAddress.PARTY_MON_2_STATUS),
        (1, MOVES_OFFSET, RamAddress.PARTY_MON_2_MOVES),
        (1, PP_OFFSET, RamAddress.PARTY_MON_2_PP),
        (1, LEVEL_OFFSET, RamAddress.PARTY_MON_2_LEVEL),
        (1, MAX_HP_OFFSET, RamAddress.PARTY_MON_2_MAX_HP),
        (2, HP_OFFSET, RamAddress.PARTY_MON_3_HP),
        (2, STATUS_OFFSET, RamAddress.PARTY_MON_3_STATUS),
        (2, MOVES_OFFSET, RamAddress.PARTY_MON_3_MOVES),
        (2, PP_OFFSET, RamAddress.PARTY_MON_3_PP),
        (2, LEVEL_OFFSET, RamAddress.PARTY_MON_3_LEVEL),
        (2, MAX_HP_OFFSET, RamAddress.PARTY_MON_3_MAX_HP),
    ),
)
def test_derived_offsets_match_the_pinned_named_symbols(
    index: int, offset: int, symbol: RamAddress
) -> None:
    assert member_field_address(index, offset) == int(symbol)


def test_struct_stride_matches_the_distance_between_named_slots() -> None:
    assert int(RamAddress.PARTY_MON_2_HP) - int(RamAddress.PARTY_MON_1_HP) == PARTY_STRUCT_STRIDE
    assert int(RamAddress.PARTY_MON_3_HP) - int(RamAddress.PARTY_MON_2_HP) == PARTY_STRUCT_STRIDE
    assert int(RamAddress.PARTY_MON_1) == STRUCT_BASE


def test_member_field_address_rejects_out_of_range_slots() -> None:
    with pytest.raises(ValueError, match="party index"):
        member_field_address(PARTY_LIMIT, HP_OFFSET)
    with pytest.raises(ValueError, match="party index"):
        member_field_address(-1, HP_OFFSET)


# --- status decoding --------------------------------------------------------


@pytest.mark.parametrize(
    ("byte", "expected"),
    (
        (0x00, StatusCondition.HEALTHY),
        (0x01, StatusCondition.SLEEP),
        (0x07, StatusCondition.SLEEP),
        (0x08, StatusCondition.POISON),
        (0x10, StatusCondition.BURN),
        (0x20, StatusCondition.FREEZE),
        (0x40, StatusCondition.PARALYSIS),
        (0x88, StatusCondition.POISON),
    ),
)
def test_status_byte_decoding(byte: int, expected: StatusCondition) -> None:
    assert decode_status(byte) is expected


# --- reading ----------------------------------------------------------------


def test_reader_projects_every_counted_member_in_active_party_order() -> None:
    reader = PokemonRedPartyReader(memory_with(BLASTOISE, DUGTRIO))
    observed = reader.read()

    assert observed.size == 2
    assert observed.is_incomplete
    assert observed.species_ids() == (0x1C, 0x76)

    lead = observed.members[0]
    assert lead.slot == 1
    assert lead.level == 55
    assert lead.hp == 160
    assert lead.max_hp == 180
    assert lead.status is StatusCondition.HEALTHY
    assert lead.experience == 200_000
    assert tuple(entry.move_id for entry in lead.known_moves) == (57, 58, 55)
    assert lead.total_pp == 30

    assert observed.members[1].slot == 2
    assert observed.minimum_level == 48
    assert observed.level_spread == 7


def test_reader_returns_an_empty_party_before_the_starter_is_obtained() -> None:
    observed = PokemonRedPartyReader(memory_with()).read()
    assert observed.size == 0
    assert observed.is_incomplete
    assert observed.weakest_trainable_member is None


def test_reader_reads_a_full_six_member_party() -> None:
    members = [
        {"species_id": species, "level": 50 + index, "hp": 100, "max_hp": 120}
        for index, species in enumerate(RED_BALANCED_ROSTER.species_ids)
    ]
    observed = PokemonRedPartyReader(memory_with(*members)).read()
    assert observed.is_complete
    assert observed.size == PARTY_SLOT_LIMIT
    assert observed.species_ids() == RED_BALANCED_ROSTER.species_ids
    assert RED_BALANCED_ROSTER.missing_from(observed) == ()
    assert RED_BALANCED_ROSTER.unplanned_in(observed) == ()


def test_reader_clamps_a_party_count_above_the_game_limit() -> None:
    members = [
        {"species_id": 0x1C + index, "level": 50, "hp": 100, "max_hp": 120}
        for index in range(PARTY_LIMIT)
    ]
    observed = PokemonRedPartyReader(memory_with(*members, count=9)).read()
    assert observed.size == PARTY_LIMIT


def test_reader_masks_power_point_bonus_bits() -> None:
    """The top two PP bits are PP Up counters, not part of the remaining total."""

    spec = dict(BLASTOISE, pp=(0xCF, 0x8A, 0x00, 0x00), moves=(57, 58, 0, 0))
    observed = PokemonRedPartyReader(memory_with(spec)).read()
    lead = observed.members[0]
    assert tuple(entry.current_pp for entry in lead.moves[:2]) == (15, 10)
    assert lead.total_pp == 25


def test_reader_decodes_status_and_faint_state() -> None:
    spec = dict(BLASTOISE, status=0x08, hp=0)
    observed = PokemonRedPartyReader(memory_with(spec)).read()
    lead = observed.members[0]
    assert lead.status is StatusCondition.POISON
    assert lead.is_fainted
    assert observed.fainted_count == 1
    assert observed.is_wiped_out


def test_reader_decodes_multi_byte_experience() -> None:
    spec = dict(BLASTOISE, experience=0x0F4240)
    observed = PokemonRedPartyReader(memory_with(spec)).read()
    assert observed.members[0].experience == 0x0F4240


def test_reader_leaves_level_progress_unknown_without_a_species_curve() -> None:
    observed = PokemonRedPartyReader(memory_with(BLASTOISE)).read()
    assert observed.members[0].experience is not None
    assert observed.members[0].level_progress is None


# --- incoherent memory ------------------------------------------------------


def test_reader_rejects_a_counted_slot_without_a_species() -> None:
    memory = memory_with(BLASTOISE, count=2)
    with pytest.raises(PartyReadError, match="holds no species"):
        PokemonRedPartyReader(memory).read()


def test_reader_rejects_a_member_without_maximum_health() -> None:
    spec = dict(BLASTOISE, hp=0, max_hp=0)
    with pytest.raises(PartyReadError, match="no maximum health"):
        PokemonRedPartyReader(memory_with(spec)).read()


def test_reader_rejects_health_above_maximum() -> None:
    spec = dict(BLASTOISE, hp=200, max_hp=180)
    with pytest.raises(PartyReadError, match="health above its maximum"):
        PokemonRedPartyReader(memory_with(spec)).read()


# --- declared roster --------------------------------------------------------


def test_declared_roster_covers_six_distinct_roles_and_species() -> None:
    assert len(RED_BALANCED_ROSTER.slots) == PARTY_SLOT_LIMIT
    assert len({slot.role for slot in RED_BALANCED_ROSTER.slots}) == PARTY_SLOT_LIMIT
    assert len(set(RED_BALANCED_ROSTER.species_ids)) == PARTY_SLOT_LIMIT
    assert set(RED_BALANCED_ROSTER.species_ids) == {0x1C, 0x76, 0x40, 0x68, 0x84, 0x2B}


def test_declared_roster_records_no_unexplained_substitution() -> None:
    assert RED_BALANCED_ROSTER.substitutions == ()
    assert all(slot.substitution_reason is None for slot in RED_BALANCED_ROSTER.slots)


def test_declared_roster_binds_the_starter_lineage_to_the_lead_role() -> None:
    lead = next(
        slot for slot in RED_BALANCED_ROSTER.slots if slot.role is PartyRole.LEAD_ATTACKER
    )
    assert lead.species_id == 0x1C
    utility = next(
        slot for slot in RED_BALANCED_ROSTER.slots if slot.role is PartyRole.FIELD_UTILITY
    )
    assert utility.species_id == 0x40


def test_roster_reports_gaps_against_a_partial_party() -> None:
    observed = PokemonRedPartyReader(memory_with(BLASTOISE, DUGTRIO)).read()
    missing = RED_BALANCED_ROSTER.missing_from(observed)
    assert tuple(slot.species_id for slot in missing) == (0x40, 0x68, 0x84, 0x2B)
