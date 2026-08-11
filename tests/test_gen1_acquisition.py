"""Scripted acquisition routes, including independent byte-layout fixtures."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_acquisition import (
    AcquisitionSource,
    CartridgeReadError,
    _decode_direct_gift,
    _decode_dojo_gift,
    _decode_fossil_choices,
    _decode_game_corner_tables,
    _decode_object_block,
    _decode_starter_script,
)
from pokemon_red_completion.generation_one import UNAVAILABLE_IN_BLUE, UNAVAILABLE_IN_RED

RECORD = Path("docs/evidence/acquisition-routes-2026-08-11.json")
TRADE_EVOLUTIONS = {65, 68, 76, 94}
MEW = 151


@pytest.fixture(scope="module")
def record() -> dict:
    if not RECORD.exists():  # pragma: no cover - the record is committed
        pytest.skip(f"{RECORD} has not been produced")
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_every_ordinary_retail_cartridge_route_is_now_in_scope(record: dict) -> None:
    assert record["schema"] == "pokemon-acquisition-routes-v2"
    assert "every ordinary retail-cartridge species route" in record["interpretation"]
    assert "mutually exclusive choices" in record["interpretation"]
    assert "Mew remains absent" in record["interpretation"]
    for route in ("starters", "gifts", "fossils", "Game Corner", "fixed encounters"):
        assert route in record["scope"]


def test_scripted_route_ledger_preserves_costs_choices_and_renewability(record: dict) -> None:
    for title in ("red", "blue"):
        entries = record["by_title"][title]["scripted_acquisitions"]
        assert len(entries) == 30
        assert Counter(item["source"] for item in entries) == {
            "starter": 3,
            "gift": 2,
            "dojo_gift": 2,
            "fossil": 3,
            "game_corner": 6,
            "static": 14,
        }
        assert Counter(item["choice_group"] for item in entries if item["choice_group"]) == {
            "oak_starter": 3,
            "fighting_dojo": 2,
            "mt_moon_fossil": 2,
        }
        repeatable = [item for item in entries if item["repeatable"]]
        assert len(repeatable) == 6
        assert {item["source"] for item in repeatable} == {"game_corner"}
        assert all(item["cost"] is not None for item in repeatable)


def test_fixed_encounters_include_both_snorlax_and_every_legendary(record: dict) -> None:
    for title in ("red", "blue"):
        entries = [
            item
            for item in record["by_title"][title]["scripted_acquisitions"]
            if item["source"] == "static"
        ]
        assert Counter(item["species"] for item in entries) == {
            100: 6,
            101: 2,
            143: 2,
            144: 1,
            145: 1,
            146: 1,
            150: 1,
        }
        assert all(item["map_id"] is not None and item["at"] is not None for item in entries)


def test_red_and_blue_prizes_are_read_independently(record: dict) -> None:
    def prizes(title: str) -> list[dict]:
        return [
            item
            for item in record["by_title"][title]["scripted_acquisitions"]
            if item["source"] == "game_corner"
        ]

    red = prizes("red")
    blue = prizes("blue")
    assert [(item["species"], item["level"], item["cost"]) for item in red] == [
        (63, 9, 180),
        (35, 8, 500),
        (30, 17, 1200),
        (147, 18, 2800),
        (123, 25, 5500),
        (137, 26, 9999),
    ]
    assert [(item["species"], item["level"], item["cost"]) for item in blue] == [
        (63, 6, 120),
        (35, 12, 750),
        (33, 17, 1200),
        (127, 20, 2500),
        (147, 24, 4600),
        (137, 18, 6500),
    ]


def test_parsed_reach_now_has_an_exact_boundary(record: dict) -> None:
    for title, unavailable in (("red", UNAVAILABLE_IN_RED), ("blue", UNAVAILABLE_IN_BLUE)):
        alone = set(record["by_title"][title]["reachable_through_parsed_routes_alone"])
        partnered = set(
            record["by_title"][title]["reachable_through_parsed_routes_with_a_trade_partner"]
        )
        assert len(alone) == 135
        assert len(partnered) == 139
        assert set(range(1, 152)) - alone == set(unavailable) | TRADE_EVOLUTIONS | {MEW}
        assert set(range(1, 152)) - partnered == set(unavailable) | {MEW}


# The remaining tests use bytes written by this test, not a committed output.
# They are the second opinion that catches a decoder and its regenerated record
# agreeing on the same bug.


def test_game_corner_decoder_reads_two_independent_menus_and_level_dictionary() -> None:
    rom = bytearray(64)
    rom[0:4] = bytes([0x10, 0x11, 0x12, 0x50])
    rom[4:8] = bytes([0x20, 0x21, 0x22, 0x50])
    rom[8:15] = bytes([0x01, 0x20, 0x03, 0x40, 0x56, 0x78, 0x50])
    rom[15:22] = bytes([0x09, 0x99, 0x12, 0x34, 0x43, 0x21, 0x50])
    rom[22:34] = bytes(
        [0x10, 5, 0x11, 10, 0x12, 15, 0x20, 20, 0x21, 25, 0x22, 30]
    )
    dex = {0x10: 1, 0x11: 2, 0x12: 3, 0x20: 4, 0x21: 5, 0x22: 6}

    found = _decode_game_corner_tables(
        bytes(rom), entry_offsets=(0, 4), cost_offsets=(8, 15), levels_offset=22, dex=dex
    )

    assert [(item.species, item.level, item.cost) for item in found] == [
        (1, 5, 120),
        (2, 10, 340),
        (3, 15, 5678),
        (4, 20, 999),
        (5, 25, 1234),
        (6, 30, 4321),
    ]
    assert all(item.source is AcquisitionSource.GAME_CORNER for item in found)
    assert all(item.repeatable for item in found)

    broken = bytearray(rom)
    broken[3] = 0
    with pytest.raises(CartridgeReadError, match="does not end"):
        _decode_game_corner_tables(
            bytes(broken),
            entry_offsets=(0, 4),
            cost_offsets=(8, 15),
            levels_offset=22,
            dex=dex,
        )

    broken = bytearray(rom)
    broken[8] = 0xFA
    with pytest.raises(CartridgeReadError, match="packed decimal"):
        _decode_game_corner_tables(
            bytes(broken),
            entry_offsets=(0, 4),
            cost_offsets=(8, 15),
            levels_offset=22,
            dex=dex,
        )


def test_starter_decoder_reads_the_players_pick_not_the_rivals_counterpick() -> None:
    block = bytes.fromhex(
        "3e21ea34123e03ea78563e100602182008"
        "3e22ea34123e04ea78563e200603180f08"
        "3e23ea34123e02ea78563e300604ea"
    )
    found = _decode_starter_script(block, {0x10: 1, 0x20: 4, 0x30: 7})

    assert [(item.species, item.level, item.choice_group) for item in found] == [
        (1, 5, "oak_starter"),
        (4, 5, "oak_starter"),
        (7, 5, "oak_starter"),
    ]

    broken = bytearray(block)
    broken[20] ^= 1
    with pytest.raises(CartridgeReadError, match="rival-species destination"):
        _decode_starter_script(bytes(broken), {0x10: 1, 0x20: 4, 0x30: 7})


def test_gift_and_fossil_decoders_read_operands_instead_of_declared_species() -> None:
    dex = {0x10: 1, 0x20: 2, 0x30: 3, 0x40: 4, 0x50: 5}

    assert _decode_direct_gift(bytes([0x01, 25, 0x10, 0xCD, 0x48, 0x3E]), dex) == (
        1,
        25,
        0x3E48,
    )

    dojo = bytearray(29)
    dojo[0:5] = bytes([0x3E, 0x20, 0xCD, 0x9B, 0x34])
    dojo[20:29] = bytes([0xFA, 0x91, 0xCF, 0x47, 0x0E, 30, 0xCD, 0x48, 0x3E])
    assert _decode_dojo_gift(bytes(dojo), dex) == (2, 30, 0x349B, 0x3E48)

    fossil = bytes(
        [0xFE, 0x29, 0x28, 12, 0xFE, 0x2A, 0x28, 4, 0x06, 0x50, 0x18, 6,
         0x06, 0x40, 0x18, 2, 0x06, 0x30]
    )
    assert _decode_fossil_choices(fossil, dex) == (
        (0x29, 3),
        (0x2A, 4),
        (None, 5),
    )


def test_object_decoder_exercises_plain_item_and_trainer_strides() -> None:
    # border, one warp, two background events, then three differently-sized objects
    raw = bytearray([0xAA, 1, 9, 8, 0, 7, 2, 1, 2, 3, 4, 5, 6, 3])
    raw.extend([0x05, 14, 24, 0xFF, 0xD0, 1])  # plain: six bytes
    raw.extend([0x3D, 15, 25, 0xFF, 0xFF, 0x82, 0x33])  # item: seven bytes
    raw.extend([0x09, 16, 26, 0xFF, 0xD1, 0x43, 0x40, 50])  # trainer: eight bytes

    found = _decode_object_block(bytes(raw), at=0, map_id=42)

    assert len(found) == 3
    assert (found[0].y, found[0].x, found[0].extra) == (10, 20, ())
    assert found[1].is_item and not found[1].is_trainer and found[1].extra == (0x33,)
    assert found[2].is_trainer and not found[2].is_item
    assert (found[2].y, found[2].x, found[2].extra) == (12, 22, (0x40, 50))

    broken = bytearray(raw)
    broken[13] = 4
    with pytest.raises(CartridgeReadError, match="ends inside an object"):
        _decode_object_block(bytes(broken), at=0, map_id=42)
