from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.domain import GameMode
from pokemon_red_completion.observation import (
    BROCK_GYM_LEADER_NUMBER,
    BROCK_OPPONENT_ID,
    BROCK_TRAINER_CLASS_ID,
    BUBBLE_MOVE_ID,
    CERULEAN_ROCKET_TRIGGER_X,
    EVENT_FLAG_BYTES,
    EXITING_DOOR_MOVEMENT_MASK,
    OAKS_LAB_SELECTION_READY_SCRIPT,
    OAKS_LAB_STARTER_OBTAINED_SCRIPT,
    POKEDEX_FLAG_BYTES,
    RED_BOX_DATA_BYTES,
    RED_BOX_LIMIT,
    RED_BOX_SRAM_BASE,
    RED_BOX_STRUCT_STRIDE,
    RED_BOXES_PER_SRAM_BANK,
    REDS_HOUSE_2F_NOOP_SCRIPT,
    SCRIPTED_MOVEMENT_STATUS_MASK,
    SQUIRTLE_SPECIES_ID,
    Badge,
    CurrentMapBlocks,
    CurrentMapBlocksError,
    CurrentMapObject,
    CurrentMapObjectError,
    CurrentStrengthBoulder,
    CurrentStrengthBoulderError,
    EventFlag,
    InputReadiness,
    ItemId,
    MapId,
    MenuCursorState,
    NorthboundPhase,
    OaksErrandPhase,
    OaksErrandState,
    OpeningPhase,
    OverworldMovementMode,
    OverworldMovementModeError,
    PewterChapterState,
    PewterProgressError,
    PewterProgressTracker,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
    SemanticStateError,
    SemanticStateTracker,
    SurgePhase,
    SurgeProgressError,
    SurgeProgressTracker,
    SurgeState,
    TravelBoundary,
    VisibleMapObject,
    VisibleMapObjectError,
    event_flag_is_set,
    location_label,
    semantic_facts,
)
from pokemon_red_completion.referee import (
    CHAMPION_DEFEATED_FACT,
    CompletionReferee,
)
from pokemon_red_completion.route import HALL_OF_FAME_FACT


class RecordingMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values
        self.reads: list[int] = []

    def read_u8(self, address: int) -> int:
        self.reads.append(int(address))
        return self.values.get(int(address), 0)


@pytest.mark.parametrize("corrupt", [None, 0, 8, 19, 100, 119])
def test_bottom_dialogue_requires_frame_not_ready_movement_flags(corrupt):
    # Literal independently specified screenshot-frame tiles, not constants
    # imported from the detector under test. Middle border and lower corners
    # distinguish a frame from lone font tiles and unrelated smaller menus.
    base = 0xC3A0 + 240
    values = {base: 0x79, base + 19: 0x7B, base + 100: 0x7D, base + 119: 0x7E}
    values.update({base + x: 0x7A for x in range(1, 19)})
    if corrupt is not None:
        values[base + corrupt] = 0
    reader = PokemonRedStateReader(RecordingMemory(values))
    assert reader.read_input_readiness().ready
    assert reader.read_bottom_dialogue_box_visible() is (corrupt is None)


@pytest.mark.parametrize("encoded,direction", [(0, "down"), (4, "up"), (8, "left"), (12, "right")])
def test_player_facing_decodes_cardinal_sprite_state(encoded, direction):
    assert (
        PokemonRedStateReader(RecordingMemory({0xC109: encoded})).read_player_facing() == direction
    )


def test_invalid_player_facing_does_not_guess():
    with pytest.raises(SemanticStateError, match="facing"):
        PokemonRedStateReader(RecordingMemory({0xC109: 3})).read_player_facing()


class BankedRecordingMemory(RecordingMemory):
    def __init__(
        self,
        values: dict[int, int],
        cartridge_values: dict[tuple[int, int], int],
    ) -> None:
        super().__init__(values)
        self.cartridge_values = cartridge_values
        self.cartridge_reads: list[tuple[int, int]] = []

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        self.cartridge_reads.append((bank, address))
        return self.cartridge_values.get((bank, address), 0)


def test_retained_outside_map_uses_the_engine_wlastmap_byte() -> None:
    # Literal address is independent of RamAddress so a shifted production
    # constant cannot change both the implementation and fixture together.
    memory = RecordingMemory({0xD365: MapId.ROUTE_7})

    assert PokemonRedStateReader(memory).read_retained_outside_map() == MapId.ROUTE_7
    assert memory.reads == [0xD365]


def test_last_blackout_map_uses_the_engine_healing_anchor_byte() -> None:
    # Literal upstream address is intentional: deriving the fixture from
    # RamAddress would let a wrong production constant change both sides.
    memory = RecordingMemory({0xD719: MapId.LAVENDER_POKECENTER})

    assert PokemonRedStateReader(memory).read_last_blackout_map() == MapId.LAVENDER_POKECENTER
    assert memory.reads == [0xD719]


def test_visible_map_objects_use_the_engine_unavailable_marker_and_live_coordinates() -> None:
    # Literal upstream addresses are intentional: deriving this fixture from
    # RamAddress would let a wrong production constant change both sides of
    # the test and survive.
    slot_1_state_1 = 0xC110
    slot_1_state_2 = 0xC210
    slot_2_state_1 = 0xC120
    slot_3_state_1 = 0xC130
    slot_3_state_2 = 0xC230
    reader = PokemonRedStateReader(
        RecordingMemory(
            {
                0xD4E1: 3,
                0xD5CE: 0xFF,
                slot_1_state_1: 41,
                slot_1_state_1 + 1: 1,
                slot_1_state_1 + 2: 0x10,
                slot_1_state_2 + 4: 5,
                slot_1_state_2 + 5: 7,
                slot_2_state_1: 6,
                slot_2_state_1 + 2: 0xFF,
                slot_3_state_1: 16,
                slot_3_state_1 + 1: 3,
                slot_3_state_1 + 2: 0x30,
                slot_3_state_2 + 4: 10,
                slot_3_state_2 + 5: 6,
            }
        )
    )

    visible = reader.read_visible_map_objects()

    assert visible == (
        VisibleMapObject(1, 41, (1, 3), 1, 0x10),
        VisibleMapObject(3, 16, (6, 2), 3, 0x30),
    )
    assert visible[0].moving is False
    assert visible[1].moving is True
    assert reader.read_visible_object_coordinates() == frozenset({(1, 3), (6, 2)})


def test_raw_state_reads_the_saffron_guard_flag_from_an_independent_address() -> None:
    # wStatusFlags6 starts the timer; wStatusFlags1 carries the guard bit.
    memory = RecordingMemory({0xD732: 0x01, 0xD728: 0x40})

    raw = PokemonRedStateReader(memory).read()

    assert raw.status_flags_1 == 0x40
    assert 0xD728 in memory.reads


def test_raw_state_reads_repel_steps_from_the_revision_pinned_address() -> None:
    memory = RecordingMemory({0xD732: 0x01, 0xD0DB: 37})

    raw = PokemonRedStateReader(memory).read()

    assert raw.repel_remaining_steps == 37
    assert 0xD0DB in memory.reads


def test_visible_map_object_read_refuses_impossible_count_and_coordinates() -> None:
    with pytest.raises(VisibleMapObjectError, match="impossible sprite count"):
        PokemonRedStateReader(RecordingMemory({0xD4E1: 16})).read_visible_map_objects()


def test_strength_boulders_keep_offscreen_slots_and_use_map_sprite_movement_bytes() -> None:
    # Independent literals: state tables C100/C200, sprite count D4E1, and
    # wMapSpriteData D4E4. Slot 2 is deliberately off-screen but still blocks.
    reader = PokemonRedStateReader(
        RecordingMemory(
            {
                0xD4E1: 3,
                0xD5CE: 0xFF,
                0xC110: 0x3F,
                0xC111: 1,
                0xC112: 0x10,
                0xC214: 19,
                0xC215: 9,
                0xD4E4: 0x10,
                0xC120: 0x3F,
                0xC121: 0,
                0xC122: 0xFF,
                0xC224: 6,
                0xC225: 18,
                0xD4E6: 0x10,
                0xC130: 0x3F,
                0xC234: 14,
                0xC235: 6,
                0xD4E8: 0x00,
            }
        )
    )

    assert reader.read_current_strength_boulders() == (
        CurrentStrengthBoulder(1, (15, 5), 1, 0x10, 0x10),
        CurrentStrengthBoulder(2, (2, 14), 0, 0xFF, 0x10),
    )
    assert reader.read_current_strength_boulders()[0].visible
    assert not reader.read_current_strength_boulders()[1].visible


def test_strength_boulder_read_refuses_impossible_coordinates_and_duplicates() -> None:
    with pytest.raises(CurrentStrengthBoulderError, match="invalid padded coordinate"):
        PokemonRedStateReader(
            RecordingMemory(
                {
                    0xD4E1: 1,
                    0xD5CE: 0xFF,
                    0xC110: 0x3F,
                    0xC214: 3,
                    0xC215: 9,
                    0xD4E4: 0x10,
                }
            )
        ).read_current_strength_boulders()

    with pytest.raises(CurrentStrengthBoulderError, match="multiple Strength boulders"):
        PokemonRedStateReader(
            RecordingMemory(
                {
                    0xD4E1: 2,
                    0xD5CE: 0xFF,
                    0xC110: 0x3F,
                    0xC214: 8,
                    0xC215: 9,
                    0xD4E4: 0x10,
                    0xC120: 0x3F,
                    0xC224: 8,
                    0xC225: 9,
                    0xD4E6: 0x10,
                }
            )
        ).read_current_strength_boulders()


def test_strength_boulders_exclude_toggle_hidden_slots_not_merely_offscreen_ones() -> None:
    reader = PokemonRedStateReader(
        RecordingMemory(
            {
                0xD4E1: 2,
                0xC110: 0x3F,
                0xC114: 0,
                0xC214: 8,
                0xC215: 9,
                0xD4E4: 0x10,
                0xC120: 0x3F,
                0xC122: 0xFF,
                0xC224: 12,
                0xC225: 13,
                0xD4E6: 0x10,
                0xD5CE: 2,
                0xD5CF: 0x60,
                0xD5D0: 0xFF,
                0xD5B2: 0x01,
            }
        )
    )

    assert reader.read_current_strength_boulders() == (
        CurrentStrengthBoulder(1, (4, 5), 0, 0, 0x10),
    )


def test_current_map_objects_keep_dynamic_offscreen_coordinates_and_exclude_hidden() -> None:
    reader = PokemonRedStateReader(
        RecordingMemory(
            {
                0xD4E1: 3,
                0xC110: 6,
                0xC111: 1,
                0xC112: 0x20,
                0xC119: 0x0C,
                0xC214: 9,
                0xC215: 11,
                0xC120: 7,
                0xC121: 3,
                0xC122: 0xFF,
                0xC224: 7,
                0xC225: 7,
                0xC130: 8,
                0xC234: 12,
                0xC235: 13,
                0xD5CE: 3,
                0xD5CF: 0x60,
                0xD5D0: 0xFF,
                0xD5B2: 0x01,
            }
        )
    )

    assert reader.read_current_map_objects() == (
        CurrentMapObject(1, 6, (5, 7), 1, 0x20, 0x0C),
        CurrentMapObject(2, 7, (3, 3), 3, 0xFF),
    )
    assert reader.read_current_map_objects()[0].visible
    assert not reader.read_current_map_objects()[1].visible
    assert reader.read_current_map_objects()[1].moving
    assert reader.read_current_object_coordinates() == frozenset({(5, 7), (3, 3)})


def test_trainer_engagement_requires_seen_flag_and_script_control() -> None:
    stale_field_success = PokemonRedStateReader(RecordingMemory({0xCD60: 0x01}))
    scripted_trainer = PokemonRedStateReader(RecordingMemory({0xCD60: 0x01, 0xCD6B: 0xF0}))
    trainer_text_script = PokemonRedStateReader(RecordingMemory({0xCD60: 0x01, 0xDA39: 0x01}))
    movement_without_seen_flag = PokemonRedStateReader(
        RecordingMemory({0xCC57: 0x02, 0xCD6B: 0xF0})
    )

    assert not stale_field_success.trainer_engagement_active()
    assert scripted_trainer.trainer_engagement_active()
    assert trainer_text_script.trainer_engagement_active()
    assert not movement_without_seen_flag.trainer_engagement_active()


def test_cerulean_rocket_custom_preamble_is_a_typed_trainer_engagement() -> None:
    event_byte = int(RamAddress.EVENT_FLAGS) + int(EventFlag.BEAT_CERULEAN_ROCKET_THIEF) // 8
    event_mask = 1 << (int(EventFlag.BEAT_CERULEAN_ROCKET_THIEF) % 8)
    preamble = {
        RamAddress.CURRENT_MAP: MapId.CERULEAN_CITY,
        RamAddress.PLAYER_X: CERULEAN_ROCKET_TRIGGER_X,
        RamAddress.PLAYER_Y: 9,
        RamAddress.PLAYER_MOVING_DIRECTION: 8,
    }

    assert PokemonRedStateReader(RecordingMemory(preamble)).trainer_engagement_active()
    assert not PokemonRedStateReader(
        RecordingMemory({**preamble, event_byte: event_mask})
    ).trainer_engagement_active()
    assert not PokemonRedStateReader(
        RecordingMemory({**preamble, RamAddress.PLAYER_X: CERULEAN_ROCKET_TRIGGER_X - 1})
    ).trainer_engagement_active()
    assert not PokemonRedStateReader(
        RecordingMemory({**preamble, RamAddress.JOY_IGNORE: 1})
    ).trainer_engagement_active()


def test_current_map_objects_refuse_duplicate_active_coordinates() -> None:
    with pytest.raises(CurrentMapObjectError, match="multiple current map objects"):
        PokemonRedStateReader(
            RecordingMemory(
                {
                    0xD4E1: 2,
                    0xD5CE: 0xFF,
                    0xC110: 6,
                    0xC214: 8,
                    0xC215: 9,
                    0xC120: 7,
                    0xC224: 8,
                    0xC225: 9,
                }
            )
        ).read_current_map_objects()

    slot_state_1 = 0xC110
    slot_state_2 = 0xC210
    with pytest.raises(VisibleMapObjectError, match="invalid padded coordinate"):
        PokemonRedStateReader(
            RecordingMemory(
                {
                    0xD4E1: 1,
                    slot_state_1: 41,
                    slot_state_1 + 2: 0x10,
                    slot_state_2 + 4: 3,
                    slot_state_2 + 5: 7,
                }
            )
        ).read_visible_map_objects()


def test_current_map_blocks_read_the_unpadded_live_grid_with_the_engine_stride() -> None:
    # Independent source literals: map id D35E, height/width D368/D369,
    # wOverworldMap C6E8, and a three-block border on every side.
    width = 3
    stride = width + 6
    origin = 0xC6E8 + 3 * stride + 3
    reader = PokemonRedStateReader(
        RecordingMemory(
            {
                0xD35E: 6,
                0xD368: 2,
                0xD369: width,
                origin: 0x10,
                origin + 1: 0x11,
                origin + 2: 0x12,
                origin + stride: 0x20,
                origin + stride + 1: 0x21,
                origin + stride + 2: 0x22,
            }
        )
    )

    assert reader.read_current_map_blocks() == CurrentMapBlocks(
        6,
        ((0x10, 0x11, 0x12), (0x20, 0x21, 0x22)),
    )


def test_current_map_blocks_refuse_dimensions_that_overrun_the_live_buffer() -> None:
    with pytest.raises(CurrentMapBlocksError, match="impossible block dimensions"):
        PokemonRedStateReader(
            RecordingMemory({0xD35E: 6, 0xD368: 255, 0xD369: 255})
        ).read_current_map_blocks()


def _saved_box_banks(
    boxes: dict[int, tuple[tuple[int, ...], tuple[int, ...]]],
) -> dict[tuple[int, int], int]:
    values: dict[tuple[int, int], int] = {}
    for bank_offset, bank in enumerate((2, 3)):
        bank_payload = bytearray(RED_BOXES_PER_SRAM_BANK * RED_BOX_DATA_BYTES)
        for bank_box_index in range(RED_BOXES_PER_SRAM_BANK):
            box_index = bank_offset * RED_BOXES_PER_SRAM_BANK + bank_box_index
            species_ids, levels = boxes.get(box_index, ((), ()))
            start = bank_box_index * RED_BOX_DATA_BYTES
            bank_payload[start] = len(species_ids)
            for slot_index, (species_id, level) in enumerate(zip(species_ids, levels, strict=True)):
                bank_payload[start + 1 + slot_index] = species_id
                structure = start + 22 + slot_index * RED_BOX_STRUCT_STRIDE
                bank_payload[structure] = species_id
                bank_payload[structure + 3] = level
        for offset, value in enumerate(bank_payload):
            if value:
                values[(bank, RED_BOX_SRAM_BASE + offset)] = value
        checksum_base = RED_BOX_SRAM_BASE + len(bank_payload)
        values[(bank, checksum_base)] = (~sum(bank_payload)) & 0xFF
        for bank_box_index in range(RED_BOXES_PER_SRAM_BANK):
            start = bank_box_index * RED_BOX_DATA_BYTES
            payload = bank_payload[start : start + RED_BOX_DATA_BYTES]
            values[(bank, checksum_base + 1 + bank_box_index)] = (~sum(payload)) & 0xFF
    return values


def _events(*events: EventFlag) -> bytes:
    payload = bytearray(EVENT_FLAG_BYTES)
    for event in events:
        byte_index, bit = divmod(int(event), 8)
        payload[byte_index] |= 1 << bit
    return bytes(payload)


def _raw(
    *,
    map_id: MapId = MapId.PALLET_TOWN,
    events: tuple[EventFlag, ...] = (),
    badges: Badge | None = None,
    party_count: int = 1,
    party_species_ids: tuple[int, ...] | None = None,
    battle_state: int = 0,
    player_x: int = 0,
    player_y: int = 0,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=int(map_id),
        player_x=player_x,
        player_y=player_y,
        party_count=party_count,
        battle_state=battle_state,
        badge_bits=int(badges or Badge(0)),
        bag_item_ids=(),
        event_flags=_events(*events),
        party_species_ids=party_species_ids,
    )


def test_celadon_center_has_public_location_and_objective_fact() -> None:
    raw = _raw(map_id=MapId.CELADON_POKECENTER, player_x=3, player_y=3)

    assert location_label(raw.map_id) == "celadon_pokecenter"
    assert "location:celadon_city" in semantic_facts(raw)


def test_gold_teeth_have_a_semantic_skill_affordance_fact() -> None:
    raw = replace(_raw(map_id=MapId.FUCHSIA_POKECENTER), bag_item_ids=(ItemId.GOLD_TEETH,))

    assert "item:gold_teeth" in semantic_facts(raw)


def test_pre_hm_koga_layout_has_a_semantic_skill_affordance_fact() -> None:
    raw = replace(_raw(map_id=MapId.FUCHSIA_POKECENTER), first_party_moves=(44, 39, 61, 55))

    assert "move:koga_attack_slot_3" in semantic_facts(raw)
    assert "move:koga_attack_slot_3" in semantic_facts(
        replace(raw, first_party_moves=(44, 39, 58, 55))
    )
    assert "move:koga_attack_slot_3" not in semantic_facts(
        replace(raw, first_party_moves=(44, 70, 61, 55))
    )


def test_reader_hides_pregame_scratch_state() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 0,
            RamAddress.CURRENT_MAP: MapId.HALL_OF_FAME,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert raw == RawGameState(False, None, None, None, None, None)
    assert memory.reads == [RamAddress.STATUS_FLAGS_6]


def test_reader_decodes_money_as_a_semantic_decimal_resource() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            int(RamAddress.PLAYER_MONEY): 0x01,
            int(RamAddress.PLAYER_MONEY) + 1: 0x23,
            int(RamAddress.PLAYER_MONEY) + 2: 0x45,
        }
    )

    assert PokemonRedStateReader(memory).read().player_money == 12_345


def test_reader_exposes_every_party_members_moves_and_pp() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.PARTY_COUNT: 2,
            RamAddress.PARTY_SPECIES: 0x1C,
            int(RamAddress.PARTY_SPECIES) + 1: 0x68,
            RamAddress.PARTY_MON_1_MOVES: 0x39,
            int(RamAddress.PARTY_MON_1_MOVES) + 1: 0x3A,
            RamAddress.PARTY_MON_1_PP: 15,
            int(RamAddress.PARTY_MON_1_PP) + 1: 10,
            RamAddress.PARTY_MON_2_MOVES: 0x57,
            int(RamAddress.PARTY_MON_2_MOVES) + 1: 0x62,
            RamAddress.PARTY_MON_2_PP: 10,
            int(RamAddress.PARTY_MON_2_PP) + 1: 20,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert raw.party_moves == ((0x39, 0x3A, 0, 0), (0x57, 0x62, 0, 0))
    assert raw.party_pp == ((15, 10, 0, 0), (10, 20, 0, 0))


def test_reader_rejects_invalid_money_digits() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            int(RamAddress.PLAYER_MONEY): 0x0A,
        }
    )

    with pytest.raises(SemanticStateError, match="packed decimal"):
        PokemonRedStateReader(memory).read()


def test_reader_decodes_owned_and_seen_national_pokedex_flags() -> None:
    values: dict[int, int] = {}

    def mark(address: RamAddress, national_number: int) -> None:
        byte_index, bit_index = divmod(national_number - 1, 8)
        target = int(address) + byte_index
        values[target] = values.get(target, 0) | (1 << bit_index)

    for national_number in (1, 9, 106, 151):
        mark(RamAddress.POKEDEX_OWNED, national_number)
        mark(RamAddress.POKEDEX_SEEN, national_number)
    mark(RamAddress.POKEDEX_SEEN, 150)
    memory = RecordingMemory(values)

    state = PokemonRedStateReader(memory).read_pokedex_state()

    assert state == RedPokedexState(
        owned_species=frozenset((1, 9, 106, 151)),
        seen_species=frozenset((1, 9, 106, 150, 151)),
    )
    assert memory.reads == [
        *(int(RamAddress.POKEDEX_OWNED) + index for index in range(POKEDEX_FLAG_BYTES)),
        *(int(RamAddress.POKEDEX_SEEN) + index for index in range(POKEDEX_FLAG_BYTES)),
    ]


def test_pokedex_state_rejects_owned_species_that_are_not_seen() -> None:
    with pytest.raises(ValueError, match="owned species"):
        RedPokedexState(
            owned_species=frozenset((25,)),
            seen_species=frozenset(),
        )


def test_reader_cross_checks_current_box_species_and_levels() -> None:
    values = {
        RamAddress.CURRENT_BOX_NUMBER: 0x82,
        RamAddress.CURRENT_BOX_COUNT: 2,
        int(RamAddress.CURRENT_BOX_SPECIES): 0x54,
        int(RamAddress.CURRENT_BOX_SPECIES) + 1: 0x3A,
        int(RamAddress.CURRENT_BOX_MONS): 0x54,
        int(RamAddress.CURRENT_BOX_MONS) + 3: 44,
        int(RamAddress.CURRENT_BOX_MONS) + RED_BOX_STRUCT_STRIDE: 0x3A,
        int(RamAddress.CURRENT_BOX_MONS) + RED_BOX_STRUCT_STRIDE + 3: 73,
    }

    state = PokemonRedStateReader(RecordingMemory(values)).read_current_box_state()

    assert state == RedCurrentBoxState(
        box_index=2,
        species_ids=(0x54, 0x3A),
        levels=(44, 73),
    )


def test_reader_exposes_semantic_linear_menu_cursor_state() -> None:
    memory = RecordingMemory(
        {
            RamAddress.CURRENT_MENU_ITEM: 2,
            RamAddress.LIST_SCROLL_OFFSET: 5,
            RamAddress.MAX_MENU_ITEM: 4,
            RamAddress.TOP_MENU_ITEM_X: 10,
            RamAddress.TOP_MENU_ITEM_Y: 12,
        }
    )

    state = PokemonRedStateReader(memory).read_menu_cursor_state()

    assert state == MenuCursorState(
        selected_visible_index=2,
        scroll_offset=5,
        maximum_visible_index=4,
        top_x=10,
        top_y=12,
    )
    assert state.selected_absolute_index == 7


def test_reader_identifies_only_the_live_trainer_switch_prompt() -> None:
    cursor_address = int(RamAddress.TILE_MAP) + 8 * 20 + 1
    values = {
        RamAddress.TOP_MENU_ITEM_Y: 8,
        RamAddress.TOP_MENU_ITEM_X: 1,
        RamAddress.CURRENT_MENU_ITEM: 0,
        RamAddress.MAX_MENU_ITEM: 1,
        RamAddress.MENU_WATCHED_KEYS: 0x03,
        RamAddress.MENU_CURSOR_LOCATION: cursor_address & 0xFF,
        int(RamAddress.MENU_CURSOR_LOCATION) + 1: cursor_address >> 8,
        cursor_address: 0xED,
    }
    reader = PokemonRedStateReader(RecordingMemory(values))
    prompt = RawGameState(
        game_started=True,
        map_id=MapId.MT_MOON_B2F,
        player_x=11,
        player_y=19,
        party_count=2,
        battle_state=2,
        enemy_hp=35,
    )

    assert reader.trainer_switch_prompt_visible(prompt)
    assert not reader.trainer_switch_prompt_visible(replace(prompt, enemy_hp=0))
    assert not reader.trainer_switch_prompt_visible(replace(prompt, party_count=1))


def test_reader_rejects_incoherent_current_box_memory() -> None:
    memory = RecordingMemory(
        {
            RamAddress.CURRENT_BOX_NUMBER: 0,
            RamAddress.CURRENT_BOX_COUNT: 1,
            RamAddress.CURRENT_BOX_SPECIES: 0x54,
            RamAddress.CURRENT_BOX_MONS: 0x3A,
            int(RamAddress.CURRENT_BOX_MONS) + 3: 44,
        }
    )

    with pytest.raises(SemanticStateError, match="species list disagrees"):
        PokemonRedStateReader(memory).read_current_box_state()


def test_all_box_reader_treats_uninitialized_backing_boxes_as_logically_empty() -> None:
    memory = RecordingMemory(
        {
            RamAddress.CURRENT_BOX_NUMBER: 2,
            RamAddress.CURRENT_BOX_COUNT: 1,
            RamAddress.CURRENT_BOX_SPECIES: 0x54,
            RamAddress.CURRENT_BOX_MONS: 0x54,
            int(RamAddress.CURRENT_BOX_MONS) + 3: 44,
        }
    )

    state = PokemonRedStateReader(memory).read_all_box_states()

    assert state == RedBoxCollectionState(
        boxes=tuple(
            RedCurrentBoxState(2, (0x54,), (44,))
            if index == 2
            else RedCurrentBoxState(index, (), ())
            for index in range(RED_BOX_LIMIT)
        ),
        current_box_index=2,
        storage_initialized=False,
    )
    assert state.counts == (0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def test_all_box_reader_verifies_saved_banks_and_overlays_the_live_box() -> None:
    cartridge_values = _saved_box_banks(
        {
            0: ((0x54,), (44,)),
            7: ((0x3A, 0x40), (73, 50)),
        }
    )
    memory = BankedRecordingMemory(
        {
            RamAddress.CURRENT_BOX_NUMBER: 0x82,
            RamAddress.CURRENT_BOX_COUNT: 1,
            RamAddress.CURRENT_BOX_SPECIES: 0x1C,
            RamAddress.CURRENT_BOX_MONS: 0x1C,
            int(RamAddress.CURRENT_BOX_MONS) + 3: 88,
        },
        cartridge_values,
    )

    state = PokemonRedStateReader(memory).read_all_box_states()

    assert state.storage_initialized
    assert state.boxes[0] == RedCurrentBoxState(0, (0x54,), (44,))
    assert state.boxes[2] == RedCurrentBoxState(2, (0x1C,), (88,))
    assert state.boxes[7] == RedCurrentBoxState(7, (0x3A, 0x40), (73, 50))
    assert state.counts == (1, 0, 1, 0, 0, 0, 0, 2, 0, 0, 0, 0)


def test_all_box_reader_rejects_missing_port_and_corrupt_checksum() -> None:
    work_ram = {
        RamAddress.CURRENT_BOX_NUMBER: 0x80,
        RamAddress.CURRENT_BOX_COUNT: 0,
    }
    with pytest.raises(SemanticStateError, match="cartridge-RAM port"):
        PokemonRedStateReader(RecordingMemory(work_ram)).read_all_box_states()

    cartridge_values = _saved_box_banks({})
    cartridge_values[(2, RED_BOX_SRAM_BASE)] = 1
    with pytest.raises(SemanticStateError, match="bank 2 failed"):
        PokemonRedStateReader(
            BankedRecordingMemory(work_ram, cartridge_values)
        ).read_all_box_states()


def test_reader_extracts_bounded_bag_and_event_state() -> None:
    champion_byte, champion_bit = divmod(int(EventFlag.BEAT_CHAMPION_RIVAL), 8)
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.CURRENT_MAP: MapId.CHAMPIONS_ROOM,
            RamAddress.PLAYER_X: 4,
            RamAddress.PLAYER_Y: 7,
            RamAddress.PARTY_COUNT: 9,
            RamAddress.PARTY_SPECIES: SQUIRTLE_SPECIES_ID,
            int(RamAddress.PARTY_SPECIES) + 1: 0xB0,
            int(RamAddress.PARTY_SPECIES) + 2: 0x15,
            int(RamAddress.PARTY_SPECIES) + 3: 0x54,
            int(RamAddress.PARTY_SPECIES) + 4: 0x99,
            int(RamAddress.PARTY_SPECIES) + 5: 0x01,
            RamAddress.IS_IN_BATTLE: 0,
            RamAddress.OBTAINED_BADGES: int(Badge.BOULDER | Badge.CASCADE),
            RamAddress.NUM_BAG_ITEMS: 2,
            RamAddress.BAG_ITEMS: 0x3F,
            int(RamAddress.BAG_ITEMS) + 1: 3,
            int(RamAddress.BAG_ITEMS) + 2: 0x48,
            int(RamAddress.BAG_ITEMS) + 3: 1,
            int(RamAddress.EVENT_FLAGS) + champion_byte: 1 << champion_bit,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert raw.party_count == 6
    assert raw.party_species_ids == (
        SQUIRTLE_SPECIES_ID,
        0xB0,
        0x15,
        0x54,
        0x99,
        0x01,
    )
    assert raw.bag_item_ids == (0x3F, 0x48)
    assert raw.bag_items == ((0x3F, 3), (0x48, 1))
    assert len(raw.party_levels or ()) == 6
    assert len(raw.party_hp or ()) == 6
    assert len(raw.party_max_hp or ()) == 6
    assert len(raw.party_status or ()) == 6
    assert event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)


def test_reader_exposes_pinned_player_disable_slot_and_turns() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.IS_IN_BATTLE: 2,
            RamAddress.PARTY_COUNT: 1,
            RamAddress.PLAYER_DISABLED_MOVE: 0x16,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert RamAddress.PLAYER_DISABLED_MOVE == 0xD06D
    assert raw.player_disabled_move_slot == 1
    assert raw.player_disable_turns == 6


def test_reader_exposes_pinned_player_special_stage() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.IS_IN_BATTLE: 2,
            RamAddress.PARTY_COUNT: 1,
            RamAddress.PLAYER_SPECIAL_STAGE: 10,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert RamAddress.PLAYER_SPECIAL_STAGE == 0xCD1D
    assert raw.player_special_stage == 10


def test_reader_exposes_pinned_enemy_trapping_status() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.IS_IN_BATTLE: 2,
            RamAddress.PARTY_COUNT: 1,
            RamAddress.ENEMY_BATTLE_STATUS_1: 1 << 5,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert RamAddress.ENEMY_BATTLE_STATUS_1 == 0xD067
    assert raw.enemy_using_trapping_move is True


def test_reader_exposes_the_active_battler_without_overwriting_the_field_lead() -> None:
    second_base = int(RamAddress.PARTY_MON_1) + 44
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.IS_IN_BATTLE: 1,
            RamAddress.PARTY_COUNT: 2,
            RamAddress.PARTY_SPECIES: SQUIRTLE_SPECIES_ID,
            int(RamAddress.PARTY_SPECIES) + 1: 0x40,
            RamAddress.PARTY_MON_1: SQUIRTLE_SPECIES_ID,
            RamAddress.PARTY_MON_1_LEVEL: 30,
            RamAddress.PARTY_MON_1_HP: 0,
            int(RamAddress.PARTY_MON_1_HP) + 1: 80,
            RamAddress.PARTY_MON_1_MAX_HP: 0,
            int(RamAddress.PARTY_MON_1_MAX_HP) + 1: 90,
            RamAddress.PLAYER_MON_NUMBER: 1,
            second_base: 0x40,
            second_base + 1: 0,
            second_base + 2: 42,
            second_base + 4: 0x40,
            second_base + 8: 0x40,
            second_base + 9: 0x1C,
            second_base + 29: 20,
            second_base + 30: 15,
            second_base + 33: 20,
            second_base + 34: 0,
            second_base + 35: 52,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert raw.first_party_level == 30
    assert raw.first_party_hp == 80
    assert raw.party_levels == (30, 20)
    assert raw.party_hp == (80, 42)
    assert raw.party_max_hp == (90, 52)
    assert raw.party_status == (0, 0x40)
    assert raw.active_party_index == 1
    assert raw.active_party_species_id == 0x40
    assert raw.battler_level == 20
    assert raw.battler_hp == 42
    assert raw.battler_max_hp == 52
    assert raw.battler_status == 0x40
    assert raw.battler_moves == (0x40, 0x1C, 0, 0)
    assert raw.battler_pp == (20, 15, 0, 0)


def test_reader_translates_the_stable_pokedex_gate_from_pinned_symbols() -> None:
    events = _events(
        EventFlag.BATTLED_RIVAL_IN_OAKS_LAB,
        EventFlag.GOT_POKEDEX,
        EventFlag.OAK_GOT_PARCEL,
        EventFlag.GOT_OAKS_PARCEL,
    )
    values = {
        RamAddress.STATUS_FLAGS_6: 1,
        RamAddress.CURRENT_MAP: MapId.OAKS_LAB,
        RamAddress.PLAYER_X: 5,
        RamAddress.PLAYER_Y: 3,
        RamAddress.PARTY_COUNT: 1,
        RamAddress.PARTY_SPECIES: SQUIRTLE_SPECIES_ID,
        RamAddress.PARTY_MON_1_HP: 0,
        int(RamAddress.PARTY_MON_1_HP) + 1: 21,
        RamAddress.PARTY_MON_1_LEVEL: 6,
        RamAddress.PARTY_MON_1_MAX_HP: 0,
        int(RamAddress.PARTY_MON_1_MAX_HP) + 1: 21,
        RamAddress.NUM_BAG_ITEMS: 0,
        RamAddress.IS_IN_BATTLE: 0,
        RamAddress.BATTLE_RESULT: 0,
        RamAddress.JOY_IGNORE: 0,
        RamAddress.OAKS_LAB_SCRIPT: 18,
        RamAddress.VIRIDIAN_MART_SCRIPT: 2,
    }
    values.update(
        {int(RamAddress.EVENT_FLAGS) + index: value for index, value in enumerate(events) if value}
    )
    reader = PokemonRedStateReader(RecordingMemory(values))

    raw = reader.read()
    state = reader.read_oaks_errand_state(raw)

    assert RamAddress.VIRIDIAN_MART_SCRIPT == 0xD60D
    assert RamAddress.PLAYER_FACING_DIRECTION == 0xC109
    assert MapId.ROUTE_1 == 0x0C
    assert MapId.VIRIDIAN_MART == 0x2A
    assert MapId.PEWTER_MART == 0x38
    assert ItemId.POTION == 0x14
    assert EventFlag.GOT_OAKS_PARCEL == 0x039
    assert ItemId.OAKS_PARCEL == 0x46
    assert raw.first_party_level == 6
    assert raw.first_party_hp == raw.first_party_max_hp == 21
    assert state.phase is OaksErrandPhase.POKEDEX_OBTAINED
    assert state.pokedex_snapshot


def test_reader_encapsulates_bedroom_input_symbols() -> None:
    memory = RecordingMemory(
        {
            RamAddress.JOY_IGNORE: 0,
            RamAddress.REDS_HOUSE_2F_SCRIPT: REDS_HOUSE_2F_NOOP_SCRIPT,
        }
    )

    input_state = PokemonRedStateReader(memory).read_bedroom_input_state()

    assert input_state.ready
    assert memory.reads == [
        RamAddress.JOY_IGNORE,
        RamAddress.REDS_HOUSE_2F_SCRIPT,
    ]


@pytest.mark.parametrize(
    ("raw", "memory_values", "expected_phase"),
    (
        (
            _raw(
                map_id=MapId.REDS_HOUSE_2F,
                party_count=0,
                player_x=3,
                player_y=6,
            ),
            {
                RamAddress.JOY_IGNORE: 0,
                RamAddress.REDS_HOUSE_2F_SCRIPT: REDS_HOUSE_2F_NOOP_SCRIPT,
            },
            OpeningPhase.BEDROOM_READY,
        ),
        (
            _raw(
                map_id=MapId.REDS_HOUSE_1F,
                party_count=0,
                player_x=7,
                player_y=1,
            ),
            {RamAddress.JOY_IGNORE: 0},
            OpeningPhase.DOWNSTAIRS,
        ),
        (
            _raw(
                map_id=MapId.PALLET_TOWN,
                party_count=0,
                player_x=5,
                player_y=6,
            ),
            {
                RamAddress.JOY_IGNORE: 0,
                RamAddress.PALLET_TOWN_SCRIPT: 0,
            },
            OpeningPhase.PALLET_FREE,
        ),
        (
            _raw(
                map_id=MapId.PALLET_TOWN,
                events=(EventFlag.OAK_APPEARED_IN_PALLET,),
                party_count=0,
                player_x=10,
                player_y=1,
            ),
            {RamAddress.JOY_IGNORE: 0xFC},
            OpeningPhase.OAK_ESCORT,
        ),
        (
            _raw(
                map_id=MapId.OAKS_LAB,
                events=(
                    EventFlag.FOLLOWED_OAK_INTO_LAB,
                    EventFlag.FOLLOWED_OAK_INTO_LAB_2,
                    EventFlag.OAK_ASKED_TO_CHOOSE_MON,
                ),
                party_count=0,
                player_x=5,
                player_y=3,
            ),
            {
                RamAddress.JOY_IGNORE: 0,
                RamAddress.OAKS_LAB_SCRIPT: OAKS_LAB_SELECTION_READY_SCRIPT,
            },
            OpeningPhase.STARTER_SELECTION_READY,
        ),
        (
            _raw(
                map_id=MapId.OAKS_LAB,
                events=(EventFlag.GOT_STARTER,),
                party_count=1,
                party_species_ids=(SQUIRTLE_SPECIES_ID,),
                player_x=7,
                player_y=4,
            ),
            {
                RamAddress.JOY_IGNORE: 0,
                RamAddress.OAKS_LAB_SCRIPT: OAKS_LAB_STARTER_OBTAINED_SCRIPT,
            },
            OpeningPhase.STARTER_OBTAINED,
        ),
    ),
)
def test_opening_phase_translation_uses_semantic_gates(
    raw: RawGameState,
    memory_values: dict[int, int],
    expected_phase: OpeningPhase,
) -> None:
    control = PokemonRedStateReader(RecordingMemory(memory_values)).read_opening_control_state(raw)

    assert control.phase is expected_phase


def test_opening_selection_gate_requires_both_follow_events_and_exact_script() -> None:
    events_without_second_follow = (
        EventFlag.FOLLOWED_OAK_INTO_LAB,
        EventFlag.OAK_ASKED_TO_CHOOSE_MON,
    )
    raw = _raw(
        map_id=MapId.OAKS_LAB,
        events=events_without_second_follow,
        party_count=0,
        player_x=5,
        player_y=3,
    )
    memory = RecordingMemory(
        {
            RamAddress.JOY_IGNORE: 0,
            RamAddress.OAKS_LAB_SCRIPT: OAKS_LAB_SELECTION_READY_SCRIPT,
        }
    )

    control = PokemonRedStateReader(memory).read_opening_control_state(raw)

    assert control.phase is OpeningPhase.UNKNOWN
    assert not control.followed_oak_into_lab
    assert control.asked_to_choose


@pytest.mark.parametrize(
    ("player_x", "joy_ignore", "lab_script"),
    (
        (6, 0, OAKS_LAB_SELECTION_READY_SCRIPT),
        (5, 0xF0, OAKS_LAB_SELECTION_READY_SCRIPT),
        (5, 0, OAKS_LAB_SELECTION_READY_SCRIPT - 1),
    ),
)
def test_opening_selection_gate_rejects_near_misses(
    player_x: int,
    joy_ignore: int,
    lab_script: int,
) -> None:
    raw = _raw(
        map_id=MapId.OAKS_LAB,
        events=(
            EventFlag.FOLLOWED_OAK_INTO_LAB,
            EventFlag.FOLLOWED_OAK_INTO_LAB_2,
            EventFlag.OAK_ASKED_TO_CHOOSE_MON,
        ),
        party_count=0,
        player_x=player_x,
        player_y=3,
    )
    memory = RecordingMemory(
        {
            RamAddress.JOY_IGNORE: joy_ignore,
            RamAddress.OAKS_LAB_SCRIPT: lab_script,
        }
    )

    control = PokemonRedStateReader(memory).read_opening_control_state(raw)

    assert control.phase is OpeningPhase.UNKNOWN


def test_opening_control_mask_is_translated_without_exposing_button_logic() -> None:
    raw = _raw(
        events=(EventFlag.OAK_APPEARED_IN_PALLET,),
        party_count=0,
        player_x=10,
        player_y=1,
    )

    control = PokemonRedStateReader(
        RecordingMemory({RamAddress.JOY_IGNORE: 0xFC})
    ).read_opening_control_state(raw)

    assert control.phase is OpeningPhase.OAK_ESCORT
    assert control.confirm_allowed
    assert control.cancel_allowed
    assert not control.movement_allowed
    assert not control.all_controls_allowed


def test_semantic_tracker_requires_and_preserves_clean_run_evidence() -> None:
    with pytest.raises(SemanticStateError, match="clean run"):
        SemanticStateTracker(_raw())

    tracker = SemanticStateTracker(RawGameState(False, None, None, None, None, None))
    pewter = tracker.observe(
        _raw(
            map_id=MapId.PEWTER_CITY,
            events=(EventFlag.GOT_STARTER, EventFlag.GOT_POKEDEX),
            badges=Badge.BOULDER,
        )
    )
    later = tracker.observe(_raw(map_id=MapId.CERULEAN_CITY))

    assert {
        "system:clean_power_on",
        "story:adventure_begun",
        "party:starter_obtained",
        "story:pokedex_received",
        "location:pewter_city",
        "badge:boulder",
    } <= pewter.facts
    assert "location:pewter_city" in later.facts
    assert later.location == "cerulean_city"


def test_completion_requires_champion_event_and_hall_map_together() -> None:
    referee = CompletionReferee()

    map_only_tracker = SemanticStateTracker(RawGameState(False, None, None, None, None, None))
    map_only = map_only_tracker.observe(_raw(map_id=MapId.HALL_OF_FAME))
    assert map_only.mode is GameMode.HALL_OF_FAME
    assert HALL_OF_FAME_FACT not in map_only.facts
    assert not referee.inspect(map_only).complete

    tracker = SemanticStateTracker(RawGameState(False, None, None, None, None, None))
    champion_room = tracker.observe(
        _raw(
            map_id=MapId.CHAMPIONS_ROOM,
            events=(EventFlag.BEAT_CHAMPION_RIVAL,),
        )
    )
    assert CHAMPION_DEFEATED_FACT in champion_room.facts
    assert HALL_OF_FAME_FACT not in champion_room.facts
    assert not referee.inspect(champion_room).complete

    hall = tracker.observe(
        _raw(
            map_id=MapId.HALL_OF_FAME,
            events=(EventFlag.BEAT_CHAMPION_RIVAL,),
        )
    )
    assert referee.inspect(hall).complete


def test_event_lookup_rejects_negative_and_short_buffers() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        event_flag_is_set(b"", -1)
    assert not event_flag_is_set(b"\x01", EventFlag.BEAT_CHAMPION_RIVAL)


def _post_pokedex_raw(
    map_id: MapId,
    player_x: int,
    player_y: int,
    *,
    battle_state: int = 0,
    battle_result: int = 0,
    beat_brock: bool = False,
    got_tm34: bool = False,
    badges: Badge | None = None,
    parcel_in_bag: bool = False,
    tm34_in_bag: bool = False,
    party_count: int = 1,
    first_party_hp: int = 21,
    first_party_max_hp: int = 21,
    first_party_level: int = 6,
    first_party_moves: tuple[int, ...] | None = None,
    first_party_pp: tuple[int, ...] | None = None,
) -> RawGameState:
    events = (
        EventFlag.GOT_POKEDEX,
        EventFlag.OAK_GOT_PARCEL,
        EventFlag.GOT_OAKS_PARCEL,
    )
    if beat_brock:
        events += (EventFlag.BEAT_BROCK,)
    if got_tm34:
        events += (EventFlag.GOT_TM34,)
    bag_items = []
    if parcel_in_bag:
        bag_items.append(ItemId.OAKS_PARCEL)
    if tm34_in_bag:
        bag_items.append(ItemId.TM34_BIDE)
    return RawGameState(
        game_started=True,
        map_id=int(map_id),
        player_x=player_x,
        player_y=player_y,
        party_count=party_count,
        battle_state=battle_state,
        badge_bits=int(badges or Badge(0)),
        bag_item_ids=tuple(bag_items),
        event_flags=_events(*events),
        party_species_ids=(SQUIRTLE_SPECIES_ID,) if party_count else (),
        first_party_level=first_party_level if party_count else None,
        first_party_hp=first_party_hp if party_count else None,
        first_party_max_hp=first_party_max_hp if party_count else None,
        first_party_status=0 if party_count else None,
        battle_result=battle_result,
        first_party_moves=first_party_moves if party_count else None,
        first_party_pp=first_party_pp if party_count else None,
    )


def _pewter_memory(overrides: dict[int, int] | None = None) -> RecordingMemory:
    values: dict[int, int] = {
        RamAddress.JOY_IGNORE: 0,
        RamAddress.SIMULATED_JOYPAD_INDEX: 0,
        RamAddress.NPC_MOVEMENT_SCRIPT_TABLE: 0,
        RamAddress.PLAYER_MOVING_DIRECTION: 0,
        RamAddress.STATUS_FLAGS_5: 0,
        RamAddress.MOVEMENT_FLAGS: 0,
        RamAddress.CURRENT_MAP_SCRIPT: 0,
        RamAddress.OAKS_LAB_SCRIPT: 18,
        RamAddress.PALLET_TOWN_SCRIPT: 5,
        RamAddress.VIRIDIAN_CITY_SCRIPT: 0,
        RamAddress.VIRIDIAN_FOREST_SCRIPT: 0,
        RamAddress.PEWTER_CITY_SCRIPT: 0,
        RamAddress.PEWTER_GYM_SCRIPT: 0,
        RamAddress.BEAT_GYM_FLAGS: 0,
        RamAddress.CURRENT_OPPONENT: 0,
        RamAddress.TRAINER_CLASS: 0,
        RamAddress.ENGAGED_TRAINER_CLASS: 0,
        RamAddress.GYM_LEADER_NUMBER: 0,
    }
    if overrides is not None:
        values.update(overrides)
    return RecordingMemory(values)


def _stable_pewter_state() -> PewterChapterState:
    raw = _post_pokedex_raw(MapId.PEWTER_CITY, 18, 35)
    return PokemonRedStateReader(_pewter_memory()).read_pewter_chapter_state(raw)


def _live_brock_state() -> PewterChapterState:
    raw = _post_pokedex_raw(
        MapId.PEWTER_GYM,
        4,
        2,
        battle_state=2,
    )
    memory = _pewter_memory(
        {
            RamAddress.PEWTER_GYM_SCRIPT: 3,
            RamAddress.CURRENT_MAP_SCRIPT: 3,
            RamAddress.CURRENT_OPPONENT: BROCK_OPPONENT_ID,
            RamAddress.TRAINER_CLASS: BROCK_TRAINER_CLASS_ID,
            RamAddress.ENGAGED_TRAINER_CLASS: BROCK_OPPONENT_ID,
            RamAddress.GYM_LEADER_NUMBER: BROCK_GYM_LEADER_NUMBER,
        }
    )
    return PokemonRedStateReader(memory).read_pewter_chapter_state(raw)


def _brock_ready_state() -> PewterChapterState:
    raw = _post_pokedex_raw(
        MapId.PEWTER_GYM,
        4,
        13,
        first_party_hp=21,
        first_party_max_hp=27,
        first_party_level=9,
        first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
        first_party_pp=(35, 30, 26, 0),
    )
    return PokemonRedStateReader(_pewter_memory()).read_pewter_chapter_state(raw)


def _brock_victory_state() -> PewterChapterState:
    raw = _post_pokedex_raw(
        MapId.PEWTER_GYM,
        4,
        2,
        beat_brock=True,
        got_tm34=True,
        badges=Badge.BOULDER,
        tm34_in_bag=True,
        first_party_hp=26,
        first_party_max_hp=33,
        first_party_level=12,
        first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
        first_party_pp=(35, 30, 23, 0),
    )
    memory = _pewter_memory({RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER)})
    return PokemonRedStateReader(memory).read_pewter_chapter_state(raw)


def test_pewter_chapter_symbols_are_exact_for_the_supported_revision() -> None:
    assert {
        address: int(address)
        for address in (
            RamAddress.NPC_MOVEMENT_SCRIPT_TABLE,
            RamAddress.ENGAGED_TRAINER_CLASS,
            RamAddress.SIMULATED_JOYPAD_INDEX,
            RamAddress.TRAINER_CLASS,
            RamAddress.IS_IN_BATTLE,
            RamAddress.CURRENT_OPPONENT,
            RamAddress.GYM_LEADER_NUMBER,
            RamAddress.PARTY_MON_1_MOVES,
            RamAddress.PARTY_MON_1_PP,
            RamAddress.PLAYER_MOVING_DIRECTION,
            RamAddress.VIRIDIAN_CITY_SCRIPT,
            RamAddress.PEWTER_CITY_SCRIPT,
            RamAddress.PEWTER_GYM_SCRIPT,
            RamAddress.VIRIDIAN_FOREST_SCRIPT,
            RamAddress.BEAT_GYM_FLAGS,
            RamAddress.STATUS_FLAGS_5,
            RamAddress.MOVEMENT_FLAGS,
            RamAddress.CURRENT_MAP_SCRIPT,
        )
    } == {
        address: expected
        for address, expected in (
            (RamAddress.NPC_MOVEMENT_SCRIPT_TABLE, 0xCC57),
            (RamAddress.ENGAGED_TRAINER_CLASS, 0xCD2D),
            (RamAddress.SIMULATED_JOYPAD_INDEX, 0xCD38),
            (RamAddress.TRAINER_CLASS, 0xD031),
            (RamAddress.IS_IN_BATTLE, 0xD057),
            (RamAddress.CURRENT_OPPONENT, 0xD059),
            (RamAddress.GYM_LEADER_NUMBER, 0xD05C),
            (RamAddress.PARTY_MON_1_MOVES, 0xD173),
            (RamAddress.PARTY_MON_1_PP, 0xD188),
            (RamAddress.PLAYER_MOVING_DIRECTION, 0xD528),
            (RamAddress.VIRIDIAN_CITY_SCRIPT, 0xD5F4),
            (RamAddress.PEWTER_CITY_SCRIPT, 0xD5F7),
            (RamAddress.PEWTER_GYM_SCRIPT, 0xD5FC),
            (RamAddress.VIRIDIAN_FOREST_SCRIPT, 0xD618),
            (RamAddress.BEAT_GYM_FLAGS, 0xD72A),
            (RamAddress.STATUS_FLAGS_5, 0xD730),
            (RamAddress.MOVEMENT_FLAGS, 0xD736),
            (RamAddress.CURRENT_MAP_SCRIPT, 0xDA39),
        )
    }
    assert {
        map_id: int(map_id)
        for map_id in (
            MapId.ROUTE_2,
            MapId.VIRIDIAN_FOREST_NORTH_GATE,
            MapId.ROUTE_2_GATE,
            MapId.VIRIDIAN_FOREST_SOUTH_GATE,
            MapId.VIRIDIAN_FOREST,
            MapId.PEWTER_GYM,
        )
    } == {
        MapId.ROUTE_2: 0x0D,
        MapId.VIRIDIAN_FOREST_NORTH_GATE: 0x2F,
        MapId.ROUTE_2_GATE: 0x31,
        MapId.VIRIDIAN_FOREST_SOUTH_GATE: 0x32,
        MapId.VIRIDIAN_FOREST: 0x33,
        MapId.PEWTER_GYM: 0x36,
    }
    assert EventFlag.GOT_POKEDEX == 0x025
    assert EventFlag.OAK_GOT_PARCEL == 0x038
    assert EventFlag.GOT_OAKS_PARCEL == 0x039
    assert EventFlag.GOT_TM34 == 0x076
    assert EventFlag.BEAT_BROCK == 0x077
    brock_byte, brock_bit = divmod(int(EventFlag.BEAT_BROCK), 8)
    assert int(RamAddress.EVENT_FLAGS) + brock_byte == 0xD755
    assert 1 << brock_bit == 0x80
    assert BROCK_OPPONENT_ID == 0xEA
    assert BROCK_TRAINER_CLASS_ID == 0x22
    assert BROCK_GYM_LEADER_NUMBER == 1
    assert BUBBLE_MOVE_ID == 0x91
    assert ItemId.TM34_BIDE == 0xEA


def test_reader_encapsulates_the_exact_input_readiness_symbols() -> None:
    memory = _pewter_memory()

    controls = PokemonRedStateReader(memory).read_input_readiness()

    assert controls.ready
    assert memory.reads == [
        RamAddress.JOY_IGNORE,
        RamAddress.SIMULATED_JOYPAD_INDEX,
        RamAddress.NPC_MOVEMENT_SCRIPT_TABLE,
        RamAddress.PLAYER_MOVING_DIRECTION,
        RamAddress.STATUS_FLAGS_5,
        RamAddress.MOVEMENT_FLAGS,
        RamAddress.WALK_COUNTER,
    ]
    assert RamAddress.WALK_COUNTER == 0xCFC5
    assert SCRIPTED_MOVEMENT_STATUS_MASK == 0xA1
    assert EXITING_DOOR_MOVEMENT_MASK == 0x02


@pytest.mark.parametrize(
    ("raw", "expected", "traversal_mode"),
    (
        (0, OverworldMovementMode.WALKING, "land"),
        (1, OverworldMovementMode.BIKING, "land"),
        (2, OverworldMovementMode.SURFING, "water"),
    ),
)
def test_reader_decodes_the_revision_pinned_overworld_movement_mode(
    raw: int,
    expected: OverworldMovementMode,
    traversal_mode: str,
) -> None:
    memory = RecordingMemory({0xD700: raw})

    mode = PokemonRedStateReader(memory).read_overworld_movement_mode()

    assert RamAddress.WALK_BIKE_SURF_STATE == 0xD700
    assert memory.reads == [0xD700]
    assert mode is expected
    assert mode.traversal_mode == traversal_mode


def test_reader_refuses_an_unknown_overworld_movement_mode() -> None:
    with pytest.raises(OverworldMovementModeError, match="unsupported"):
        PokemonRedStateReader(RecordingMemory({0xD700: 3})).read_overworld_movement_mode()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("joy_ignore", 1),
        ("simulated_joypad_index", 1),
        ("npc_movement_script_table", 1),
        ("player_moving_direction", 1),
        ("status_flags_5", 1 << 0),
        ("status_flags_5", 1 << 5),
        ("status_flags_5", 1 << 7),
        ("movement_flags", EXITING_DOOR_MOVEMENT_MASK),
        ("walk_counter", 1),
    ),
)
def test_input_readiness_rejects_each_blocking_field(
    field: str,
    value: int,
) -> None:
    ready = InputReadiness(0, 0, 0, 0, 0)

    assert not replace(ready, **{field: value}).ready


def test_input_readiness_ignores_unrelated_status_bits() -> None:
    controls = InputReadiness(0, 0, 0, 0, 1 << 2)

    assert controls.ready


@pytest.mark.parametrize(
    ("map_id", "x", "y", "boundary", "phase"),
    (
        (
            MapId.PALLET_TOWN,
            12,
            12,
            TravelBoundary.PALLET_LAB_EXTERIOR,
            NorthboundPhase.LAB_EXITED,
        ),
        (
            MapId.VIRIDIAN_CITY,
            21,
            35,
            TravelBoundary.VIRIDIAN_SOUTH_EDGE,
            NorthboundPhase.VIRIDIAN_REACHED,
        ),
        (
            MapId.ROUTE_2,
            7,
            71,
            TravelBoundary.ROUTE_2_SOUTH_EDGE,
            NorthboundPhase.ROUTE_2_SOUTH_REACHED,
        ),
        (
            MapId.ROUTE_2,
            8,
            71,
            TravelBoundary.ROUTE_2_SOUTH_EDGE,
            NorthboundPhase.ROUTE_2_SOUTH_REACHED,
        ),
        (
            MapId.ROUTE_2,
            9,
            71,
            TravelBoundary.ROUTE_2_SOUTH_EDGE,
            NorthboundPhase.ROUTE_2_SOUTH_REACHED,
        ),
        (
            MapId.VIRIDIAN_FOREST_SOUTH_GATE,
            4,
            7,
            TravelBoundary.FOREST_SOUTH_GATE,
            NorthboundPhase.FOREST_GATE_REACHED,
        ),
        (
            MapId.VIRIDIAN_FOREST,
            16,
            47,
            TravelBoundary.FOREST_SOUTH_ENTRY,
            NorthboundPhase.FOREST_ENTERED,
        ),
        (
            MapId.VIRIDIAN_FOREST,
            17,
            47,
            TravelBoundary.FOREST_SOUTH_ENTRY,
            NorthboundPhase.FOREST_ENTERED,
        ),
        (
            MapId.VIRIDIAN_FOREST_NORTH_GATE,
            4,
            7,
            TravelBoundary.FOREST_NORTH_GATE,
            NorthboundPhase.FOREST_CLEARED,
        ),
        (
            MapId.ROUTE_2,
            3,
            11,
            TravelBoundary.ROUTE_2_NORTH_RETURN,
            NorthboundPhase.FOREST_CLEARED,
        ),
        (
            MapId.PEWTER_CITY,
            18,
            35,
            TravelBoundary.PEWTER_SOUTH_EDGE,
            NorthboundPhase.PEWTER_REACHED,
        ),
        (
            MapId.PEWTER_CITY,
            19,
            35,
            TravelBoundary.PEWTER_SOUTH_EDGE,
            NorthboundPhase.PEWTER_REACHED,
        ),
        (
            MapId.PEWTER_GYM,
            4,
            13,
            TravelBoundary.PEWTER_GYM_ENTRANCE,
            NorthboundPhase.PEWTER_GYM_ENTERED,
        ),
    ),
)
def test_pewter_chapter_translates_each_exact_travel_boundary(
    map_id: MapId,
    x: int,
    y: int,
    boundary: TravelBoundary,
    phase: NorthboundPhase,
) -> None:
    raw = _post_pokedex_raw(map_id, x, y)

    state = PokemonRedStateReader(_pewter_memory()).read_pewter_chapter_state(raw)

    assert state.boundary is boundary
    assert state.phase is phase
    assert state.stable_travel_snapshot
    assert state.travel_boundary_snapshot


@pytest.mark.parametrize(
    ("map_id", "x", "y"),
    (
        (MapId.PALLET_TOWN, 12, 11),
        (MapId.VIRIDIAN_CITY, 20, 35),
        (MapId.ROUTE_2, 6, 71),
        (MapId.ROUTE_2, 8, 70),
        (MapId.VIRIDIAN_FOREST_SOUTH_GATE, 5, 7),
        (MapId.VIRIDIAN_FOREST, 15, 47),
        (MapId.VIRIDIAN_FOREST, 16, 46),
        (MapId.ROUTE_2, 4, 11),
        (MapId.PEWTER_CITY, 17, 35),
        (MapId.PEWTER_CITY, 18, 34),
        (MapId.PEWTER_GYM, 5, 13),
    ),
)
def test_pewter_chapter_rejects_nearby_non_boundary_positions(
    map_id: MapId,
    x: int,
    y: int,
) -> None:
    raw = _post_pokedex_raw(map_id, x, y)

    state = PokemonRedStateReader(_pewter_memory()).read_pewter_chapter_state(raw)

    assert state.boundary is TravelBoundary.UNKNOWN
    assert state.phase is NorthboundPhase.UNKNOWN


@pytest.mark.parametrize(
    "changes",
    (
        {"first_party_status": 8},
        {"beat_brock": True},
        {"got_tm34": True},
        {"tm34_in_bag": True},
        {"boulder_badge": True},
        {"boulder_badge_mirror": True},
    ),
)
def test_travel_boundaries_require_an_unbeaten_healthy_lineage(
    changes: dict[str, object],
) -> None:
    state = _boundary_state(MapId.VIRIDIAN_CITY, 21, 35)

    assert not replace(state, **changes).travel_boundary_snapshot


@pytest.mark.parametrize(
    ("map_id", "x", "y"),
    (
        (MapId.VIRIDIAN_FOREST_NORTH_GATE, 4, 7),
        (MapId.ROUTE_2, 3, 11),
        (MapId.PEWTER_CITY, 18, 35),
    ),
)
def test_post_forest_travel_boundaries_admit_recoverable_poison(
    map_id: MapId,
    x: int,
    y: int,
) -> None:
    poisoned = replace(_boundary_state(map_id, x, y), first_party_status=0x08)

    assert poisoned.travel_boundary_snapshot
    assert poisoned.stable_travel_snapshot
    assert poisoned.unbeaten_brock_transit_invariants
    assert not poisoned.unbeaten_brock_invariants


def test_gym_boundary_remains_healthy_only_after_poison_transit() -> None:
    poisoned = replace(_brock_ready_state(), first_party_status=0x08)

    assert not poisoned.travel_boundary_snapshot
    assert not poisoned.brock_ready_snapshot


def test_pewter_snapshot_requires_a_stable_unbeaten_post_pokedex_state() -> None:
    state = _stable_pewter_state()

    assert state.phase is NorthboundPhase.PEWTER_REACHED
    assert state.boundary is TravelBoundary.PEWTER_SOUTH_EDGE
    assert state.controls.ready
    assert state.post_pokedex_invariants
    assert state.stable_travel_snapshot
    assert state.pewter_snapshot


@pytest.mark.parametrize(
    "changes",
    (
        {"phase": NorthboundPhase.UNKNOWN},
        {"boundary": TravelBoundary.UNKNOWN},
        {"controls": InputReadiness(1, 0, 0, 0, 0)},
        {"local_script": 1},
        {"current_map_script": 1},
        {"oak_lab_script": 17},
        {"got_oaks_parcel": False},
        {"oak_got_parcel": False},
        {"got_pokedex": False},
        {"parcel_in_bag": True},
        {"party_count": 2},
        {"first_party_species": 0xB0},
        {"first_party_hp": 0},
        {"battle_state": 1},
        {"beat_brock": True},
        {"boulder_badge": True},
        {"boulder_badge_mirror": True},
    ),
)
def test_pewter_snapshot_rejects_each_one_field_near_miss(
    changes: dict[str, object],
) -> None:
    assert not replace(_stable_pewter_state(), **changes).pewter_snapshot


def test_reader_recognizes_only_the_exact_live_brock_identity() -> None:
    state = _live_brock_state()

    assert state.phase is NorthboundPhase.BROCK_BATTLE
    assert state.brock_battle_snapshot
    assert state.map_id == MapId.PEWTER_GYM
    assert state.current_opponent == BROCK_OPPONENT_ID
    assert state.trainer_class == BROCK_TRAINER_CLASS_ID
    assert state.engaged_trainer_class == BROCK_OPPONENT_ID
    assert state.gym_leader_number == BROCK_GYM_LEADER_NUMBER


def test_brock_readiness_requires_a_healthy_squirtle_with_bubble_reserve() -> None:
    state = _brock_ready_state()

    assert state.brock_ready_snapshot


@pytest.mark.parametrize(
    "changes",
    (
        {"first_party_status": 8},
        {"first_party_level": 8},
        {"first_party_hp": 18},
        {"first_party_max_hp": 14},
        {"first_party_moves": (0x21, 0x27, 0, 0)},
        {"first_party_pp": (35, 30, 3, 0)},
    ),
)
def test_brock_readiness_rejects_each_party_near_miss(
    changes: dict[str, object],
) -> None:
    state = _brock_ready_state()

    assert not replace(state, **changes).brock_ready_snapshot


@pytest.mark.parametrize(
    "changes",
    (
        {"phase": NorthboundPhase.UNKNOWN},
        {"map_id": MapId.PEWTER_CITY},
        {"battle_state": 1},
        {"local_script": 2},
        {"current_map_script": 2},
        {"oak_lab_script": 17},
        {"got_oaks_parcel": False},
        {"oak_got_parcel": False},
        {"got_pokedex": False},
        {"parcel_in_bag": True},
        {"party_count": 2},
        {"first_party_species": 0xB0},
        {"first_party_hp": 0},
        {"first_party_status": 8},
        {"current_opponent": 0xCD},
        {"trainer_class": 0x05},
        {"engaged_trainer_class": 0xCD},
        {"gym_leader_number": 0},
        {"beat_brock": True},
        {"got_tm34": True},
        {"tm34_in_bag": True},
        {"boulder_badge": True},
        {"boulder_badge_mirror": True},
    ),
)
def test_live_brock_identity_rejects_each_one_field_near_miss(
    changes: dict[str, object],
) -> None:
    assert not replace(_live_brock_state(), **changes).brock_battle_snapshot


def test_post_brock_victory_requires_the_full_concurrent_conjunction() -> None:
    state = _brock_victory_state()

    assert state.phase is NorthboundPhase.BROCK_DEFEATED
    assert state.post_pokedex_invariants
    assert state.controls.ready
    assert state.brock_victory_snapshot


@pytest.mark.parametrize(
    "changes",
    (
        {"phase": NorthboundPhase.UNKNOWN},
        {"map_id": MapId.PEWTER_CITY},
        {"controls": InputReadiness(0, 1, 0, 0, 0)},
        {"local_script": 3},
        {"current_map_script": 3},
        {"oak_lab_script": 17},
        {"got_oaks_parcel": False},
        {"oak_got_parcel": False},
        {"got_pokedex": False},
        {"parcel_in_bag": True},
        {"party_count": 2},
        {"first_party_species": 0xB0},
        {"first_party_hp": 0},
        {"first_party_status": 8},
        {"battle_state": 2},
        {"battle_result": 1},
        {"beat_brock": False},
        {"got_tm34": False},
        {"tm34_in_bag": False},
        {"boulder_badge": False},
        {"boulder_badge_mirror": False},
    ),
)
def test_post_brock_victory_rejects_each_one_field_near_miss(
    changes: dict[str, object],
) -> None:
    assert not replace(_brock_victory_state(), **changes).brock_victory_snapshot


def _pokedex_gate() -> OaksErrandState:
    raw = _post_pokedex_raw(MapId.OAKS_LAB, 5, 3)
    memory = _pewter_memory()
    memory.values[RamAddress.VIRIDIAN_MART_SCRIPT] = 2
    return PokemonRedStateReader(memory).read_oaks_errand_state(raw)


def _boundary_state(
    map_id: MapId,
    x: int,
    y: int,
) -> PewterChapterState:
    return PokemonRedStateReader(_pewter_memory()).read_pewter_chapter_state(
        _post_pokedex_raw(map_id, x, y)
    )


def test_pewter_progress_tracker_requires_the_verified_pokedex_origin() -> None:
    invalid = PokemonRedStateReader(_pewter_memory()).read_oaks_errand_state(
        _post_pokedex_raw(MapId.PEWTER_CITY, 18, 35)
    )

    with pytest.raises(PewterProgressError, match="verified Pokédex boundary"):
        PewterProgressTracker(invalid)


def test_pewter_progress_tracker_latches_every_ordered_boundary_and_brock() -> None:
    tracker = PewterProgressTracker(_pokedex_gate())
    boundaries = (
        (MapId.PALLET_TOWN, 12, 12),
        (MapId.VIRIDIAN_CITY, 21, 35),
        (MapId.ROUTE_2, 8, 71),
        (MapId.VIRIDIAN_FOREST_SOUTH_GATE, 4, 7),
        (MapId.VIRIDIAN_FOREST, 17, 47),
        (MapId.VIRIDIAN_FOREST_NORTH_GATE, 4, 7),
        (MapId.ROUTE_2, 3, 11),
        (MapId.PEWTER_CITY, 18, 35),
        (MapId.PEWTER_GYM, 4, 13),
    )

    for map_id, x, y in boundaries:
        state = (
            _brock_ready_state() if map_id is MapId.PEWTER_GYM else _boundary_state(map_id, x, y)
        )
        assert tracker.observe(state) is state.phase

    assert tracker.reached_boundaries == tuple(TravelBoundary)[1:]
    assert tracker.saw_brock_ready
    assert tracker.observe(_live_brock_state()) is NorthboundPhase.BROCK_BATTLE
    assert tracker.saw_brock_battle
    assert tracker.observe(_brock_victory_state()) is NorthboundPhase.BROCK_DEFEATED
    assert tracker.brock_defeated


def test_pewter_progress_tracker_rejects_a_skipped_boundary() -> None:
    tracker = PewterProgressTracker(_pokedex_gate())

    with pytest.raises(PewterProgressError, match="skipped"):
        tracker.observe(_boundary_state(MapId.VIRIDIAN_CITY, 21, 35))


def test_pewter_progress_tracker_rejects_victory_without_live_battle() -> None:
    tracker = PewterProgressTracker(_pokedex_gate())

    with pytest.raises(PewterProgressError, match="observed live battle"):
        tracker.observe(_brock_victory_state())


def _surge_state(phase: SurgePhase, *, valid: bool = True) -> SurgeState:
    return SurgeState(phase=phase, **{phase.value: valid})


def test_surge_progress_tracker_requires_all_fourteen_gates() -> None:
    tracker = SurgeProgressTracker()

    for phase in SurgePhase:
        assert tracker.observe(_surge_state(phase)) is phase

    assert tracker.saw_live_battle


def test_surge_progress_tracker_rejects_a_skipped_gate() -> None:
    tracker = SurgeProgressTracker()
    tracker.observe(_surge_state(SurgePhase.HM01_READY))

    with pytest.raises(SurgeProgressError, match="skipped"):
        tracker.observe(_surge_state(SurgePhase.BALLS_PURCHASED))


def test_surge_progress_tracker_rejects_false_snapshot() -> None:
    with pytest.raises(SurgeProgressError, match="failed"):
        SurgeProgressTracker().observe(_surge_state(SurgePhase.HM01_READY, valid=False))
