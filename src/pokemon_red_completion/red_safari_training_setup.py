"""Revision-pinned, teacher-only Safari setup; never an actor action.

The pinned pokered WRAM layout places wNumberOfWarps at D3AE and its
four-byte entries at D3AF. Only the two existing lab exit destinations
are changed. The cartridge, not this adapter, subsequently loads the map.
"""

from __future__ import annotations

from typing import Protocol

from pokemon_red_completion.observation import MapId, RamAddress

RED_ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
_NUMBER_OF_WARPS = 0xD3AE
_WARP_ENTRIES = 0xD3AF
_LAST_MAP = 0xD365
_LAB_EXIT_BYTES = (11, 4, 2, 255, 11, 5, 2, 255)


class SetupMemory(Protocol):
    def __getitem__(self, address: int) -> int: ...

    def __setitem__(self, address: int, value: int) -> None: ...


def redirect_fresh_lab_exit(
    memory: SetupMemory,
    *,
    rom_sha256: str,
    isolated_training_setup: bool,
    controller_released: bool,
    battle_state: int,
) -> tuple[dict[str, int], ...]:
    """Validate every precondition before editing; return exact interventions.

    Caller must retain the untouched fresh-power-on origin and claim before
    invoking this adapter. Successful readback is not qualification of the
    resulting native map, nor admission to a TRAIN dataset.
    """
    if (
        isolated_training_setup is not True
        or controller_released is not True
        or type(battle_state) is not int
        or battle_state != 0
        or rom_sha256 != RED_ROM_SHA256
    ):
        raise ValueError("Safari setup requires isolated released Red field control")
    expected = {
        int(RamAddress.CURRENT_MAP): int(MapId.OAKS_LAB),
        int(RamAddress.OAKS_LAB_SCRIPT): 10,
        _NUMBER_OF_WARPS: 2,
        _LAST_MAP: int(MapId.PALLET_TOWN),
        **{_WARP_ENTRIES + i: byte for i, byte in enumerate(_LAB_EXIT_BYTES)},
    }
    if any(int(memory[address]) != value for address, value in expected.items()):
        raise ValueError("fresh lab boundary or native exit layout differs")
    changes = {
        int(RamAddress.OAKS_LAB_SCRIPT): 18,  # cartridge's no-op lab script
        _LAST_MAP: int(MapId.FUCHSIA_CITY),
        _WARP_ENTRIES + 2: 0,
        _WARP_ENTRIES + 3: int(MapId.SAFARI_ZONE_GATE),
        _WARP_ENTRIES + 6: 0,
        _WARP_ENTRIES + 7: int(MapId.SAFARI_ZONE_GATE),
    }
    receipt = tuple(
        {"address": address, "before": int(memory[address]), "after": value}
        for address, value in changes.items()
    )
    for address, value in changes.items():
        memory[address] = value
    if any(int(memory[address]) != value for address, value in changes.items()):
        raise ValueError("Safari setup write readback differs; retain failure, do not replay")
    return receipt


def set_isolated_safari_context(
    memory: SetupMemory, *, rom_sha256: str, isolated_training_setup: bool,
    controller_released: bool, battle_state: int,
    registered_species: tuple[int, ...], money: int,
) -> tuple[dict[str, int], ...]:
    """Teacher-only context variation; never a player action or earned ledger.

    Add declared historical registration flags and set cash on a retained isolated
    gate source. Never clear owned/seen flags or touch party, coordinates, RNG,
    encounter tables, PP or Safari session state. Caller records parent + receipt.
    Synthetic prior registrations/cash receive no completion or income credit.
    """
    if (
        isolated_training_setup is not True or controller_released is not True
        or type(battle_state) is not int or battle_state != 0
        or rom_sha256 != RED_ROM_SHA256
        or int(memory[int(RamAddress.CURRENT_MAP)]) != int(MapId.SAFARI_ZONE_GATE)
        or type(money) is not int or not 500 <= money <= 999999
        or not isinstance(registered_species, tuple)
        or any(type(s) is not int or not 1 <= s <= 151 for s in registered_species)
        or len(set(registered_species)) != len(registered_species)
    ):
        raise ValueError("Safari context requires isolated released valid gate setup")
    changes = {}
    for base in (int(RamAddress.POKEDEX_OWNED), int(RamAddress.POKEDEX_SEEN)):
        for number in registered_species:
            address = base + (number - 1) // 8
            changes[address] = changes.get(address, int(memory[address])) | 1 << ((number - 1) % 8)
    # Every already-owned flag must also remain seen.
    for offset in range(19):
        owned = changes.get(int(RamAddress.POKEDEX_OWNED) + offset,
                            int(memory[int(RamAddress.POKEDEX_OWNED) + offset]))
        address = int(RamAddress.POKEDEX_SEEN) + offset
        changes[address] = changes.get(address, int(memory[address])) | owned
    digits = f"{money:06d}"
    for i in range(3):
        changes[int(RamAddress.PLAYER_MONEY) + i] = int(digits[2*i:2*i+2], 16)
    receipt = tuple(dict(address=a, before=int(memory[a]), after=v)
                    for a, v in sorted(changes.items()) if int(memory[a]) != v)
    for row in receipt:
        memory[row["address"]] = row["after"]
    if any(int(memory[row["address"]]) != row["after"] for row in receipt):
        raise ValueError("Safari context readback differs; retain failure")
    return receipt
