import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_joypad_rle import decode_direction_runs


def test_all_directions_and_duplicate_segments_keep_their_order():
    assert decode_direction_runs(bytes.fromhex("40 02 40 03 10 76 20 01 80 03 ff")) == (
        ((-1, 0), 2), ((-1, 0), 3), ((0, 1), 118), ((0, -1), 1), ((1, 0), 3),
    )
    assert decode_direction_runs(bytes.fromhex("40 7f ff")) == (((-1, 0), 127),)
    assert decode_direction_runs(bytes.fromhex("10 01 ff"), max_steps=1) == (((0, 1), 1),)


@pytest.mark.parametrize("limit", [True, False, 0, -1, 128, 1.0, "127", None])
def test_step_limit_has_exact_integer_type_and_bounds(limit):
    with pytest.raises(CartridgeReadError):
        decode_direction_runs(bytes.fromhex("40 01 ff"), max_steps=limit)


@pytest.mark.parametrize("data", [
    b"", b"\xff", b"\x40", b"\x40\x01", b"\x40\xff",
    bytes.fromhex("40 01 ff 00"), bytes.fromhex("40 01 ff ff ff"),
    bytes.fromhex("40 01 80 ff"), bytes.fromhex("00 01 ff"),
    bytes.fromhex("50 01 ff"), bytes.fromhex("c0 01 ff"), bytes.fromhex("30 01 ff"),
    bytes.fromhex("40 00 ff"), bytes.fromhex("40 80 ff"), bytes.fromhex("40 ff ff"),
    bytes.fromhex("40 40 80 40 ff"), "4001ff", bytearray(b"\x40\x01\xff"), None,
])
def test_malformed_payloads_fail_closed(data):
    with pytest.raises(CartridgeReadError):
        decode_direction_runs(data)


def test_total_limit_is_not_a_per_segment_limit():
    with pytest.raises(CartridgeReadError):
        decode_direction_runs(bytes.fromhex("40 03 80 03 ff"), max_steps=5)
