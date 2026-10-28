from unittest.mock import MagicMock

import pytest

from pokemon_red_completion.observation import MapId, RamAddress
from pokemon_red_completion.red_safari_training_setup import (
    RED_ROM_SHA256,
    redirect_fresh_lab_exit,
    set_isolated_safari_context,
)


def memory():
    result = bytearray(0x10000)
    result[RamAddress.CURRENT_MAP] = MapId.OAKS_LAB
    result[RamAddress.OAKS_LAB_SCRIPT] = 10
    result[0xD3AE] = 2
    result[0xD3AF:0xD3B7] = bytes((11, 4, 2, 255, 11, 5, 2, 255))
    return result


def apply(target, **changes):
    arguments = dict(
        rom_sha256=RED_ROM_SHA256,
        isolated_training_setup=True,
        controller_released=True,
        battle_state=0,
    )
    arguments.update(changes)
    return redirect_fresh_lab_exit(target, **arguments)


def test_exact_six_byte_patch_only_and_complete_receipt():
    target = memory()
    before = bytes(target)
    receipt = apply(target)
    changed = {i for i, (a, b) in enumerate(zip(before, target, strict=True)) if a != b}
    assert changed == {row["address"] for row in receipt}
    assert len(receipt) == 6
    assert all(before[row["address"]] == row["before"] for row in receipt)
    assert all(target[row["address"]] == row["after"] for row in receipt)
    assert target[RamAddress.CURRENT_MAP] == MapId.OAKS_LAB
    assert target[0xD3AF:0xD3B7] == bytes((11, 4, 0, 156, 11, 5, 0, 156))


@pytest.mark.parametrize("changes", [
    {"rom_sha256": "0" * 64}, {"isolated_training_setup": False},
    {"isolated_training_setup": 1}, {"controller_released": False},
    {"battle_state": 1}, {"battle_state": False},
])
def test_scope_refusal_before_any_write(changes):
    target = memory()
    before = bytes(target)
    with pytest.raises(ValueError):
        apply(target, **changes)
    assert bytes(target) == before


@pytest.mark.parametrize("address", [
    RamAddress.CURRENT_MAP, RamAddress.OAKS_LAB_SCRIPT, 0xD365, 0xD3AE,
    *range(0xD3AF, 0xD3B7),
])
def test_full_boundary_validation_before_any_write(address):
    target = memory()
    target[address] ^= 1
    before = bytes(target)
    with pytest.raises(ValueError):
        apply(target)
    assert bytes(target) == before


def test_no_second_application():
    target = memory()
    apply(target)
    before = bytes(target)
    with pytest.raises(ValueError):
        apply(target)
    assert bytes(target) == before


def test_failed_readback_is_not_success():
    target = MagicMock()
    target.__getitem__.side_effect = memory().__getitem__
    with pytest.raises(ValueError, match="readback"):
        apply(target)


def context(target, **updates):
    args = dict(rom_sha256=RED_ROM_SHA256, isolated_training_setup=True,
                controller_released=True, battle_state=0,
                registered_species=(1, 113, 151), money=1500)
    args.update(updates)
    return set_isolated_safari_context(target, **args)


def test_context_changes_only_disclosed_dex_cash_bytes_preserving_old_flags():
    target = memory()
    target[RamAddress.CURRENT_MAP] = MapId.SAFARI_ZONE_GATE
    target[RamAddress.POKEDEX_OWNED] = 64
    before = bytes(target)
    receipt = context(target)
    changed = {i for i, (a, b) in enumerate(zip(before, target, strict=True)) if a != b}
    assert changed == {r["address"] for r in receipt}
    allowed = {*range(RamAddress.POKEDEX_OWNED, RamAddress.POKEDEX_OWNED+19),
               *range(RamAddress.POKEDEX_SEEN, RamAddress.POKEDEX_SEEN+19),
               *range(RamAddress.PLAYER_MONEY, RamAddress.PLAYER_MONEY+3)}
    assert changed <= allowed
    assert target[RamAddress.POKEDEX_OWNED] == target[RamAddress.POKEDEX_SEEN] == 65
    assert target[RamAddress.PLAYER_MONEY:RamAddress.PLAYER_MONEY+3] == bytes([0, 0x15, 0])
    assert all(before[r["address"]] == r["before"] for r in receipt)


@pytest.mark.parametrize("updates", [
    dict(isolated_training_setup=False), dict(controller_released=False),
    dict(rom_sha256="0"*64), dict(battle_state=1), dict(battle_state=False),
    dict(money=499), dict(money=1_000_000), dict(money=True),
    dict(registered_species=(0,)), dict(registered_species=(152,)),
    dict(registered_species=(1, 1)), dict(registered_species=(True,)),
])
def test_context_rejects_bad_request_before_writes(updates):
    target = memory()
    target[RamAddress.CURRENT_MAP] = MapId.SAFARI_ZONE_GATE
    before = bytes(target)
    with pytest.raises(ValueError):
        context(target, **updates)
    assert bytes(target) == before


def test_context_rejects_other_map():
    target = memory()
    before = bytes(target)
    with pytest.raises(ValueError):
        context(target)
    assert bytes(target) == before
