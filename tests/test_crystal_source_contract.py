from __future__ import annotations

import json

import pytest

from pokemon_crystal_completion.source_contract import (
    CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL,
    CRYSTAL_OBSERVATION_SYMBOLS,
    CRYSTAL_ROM_ENVIRONMENT_VARIABLE,
    CRYSTAL_STORED_BOX_SRAM_SYMBOLS,
    CRYSTAL_US_REV0_SOURCE_CONTRACT,
    CrystalMemorySymbol,
    CrystalSourceContract,
    CrystalSourceContractError,
    CrystalSramSymbol,
)


def test_crystal_revision_is_pinned_without_a_private_path() -> None:
    contract = CRYSTAL_US_REV0_SOURCE_CONTRACT
    public = contract.public_dict()

    assert contract.game_id == "pokemon.mainline:crystal:gbc:us:rev0"
    assert contract.adapter_id == "pokemon.crystal.gbc.us.rev0.goal-state.v1"
    assert contract.rom_header_title == "PM_CRYSTAL"
    assert contract.rom_size_bytes == 2_097_152
    assert contract.rom_sha1 == "f4cd194bdee0d04ca4eac29e09b8e4e9d818c133"
    assert contract.source_commit == "7a7881d0d62e0ddbd82dcf10e7116807487ac651"
    assert contract.symbols_commit == "cc6fc04f19c645f5c40f64f8d88b2ab42c7bdde8"
    assert contract.symbols_sha256 == (
        "697fe20b3c659273a3ab8aa85db2eb78dcf674a3dd17c98b52fc1dddd37783f2"
    )
    assert contract.rom_sha256 is None
    assert not contract.live_identity_complete
    assert CRYSTAL_ROM_ENVIRONMENT_VARIABLE == "POKEMON_CRYSTAL_ROM"
    encoded = json.dumps(public, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "filename" not in public["rom"]  # type: ignore[operator]
    assert public["private_path_fields"] == 0
    assert public["rom_bytes_fields"] == 0


def test_allowlisted_symbols_match_independent_generated_map_values() -> None:
    expected = {
        "wJoypadDisable": (0, 0xCFBE),
        "wBattleMenuCursorPosition": (1, 0xD0D2),
        "wBattleMode": (1, 0xD22D),
        "wScriptMode": (1, 0xD437),
        "wJohtoBadges": (1, 0xD857),
        "wKantoBadges": (1, 0xD858),
        "wNumBalls": (1, 0xD8D7),
        "wCurBox": (1, 0xDB72),
        "wMapGroup": (1, 0xDCB5),
        "wPartyCount": (1, 0xDCD7),
        "wPartyMon1": (1, 0xDCDF),
        "wPartyMon1Level": (1, 0xDCFE),
        "wPartyMon1HP": (1, 0xDD01),
        "wPokedexCaught": (1, 0xDE99),
        "wEndPokedexSeen": (1, 0xDED9),
    }
    assert len(CRYSTAL_OBSERVATION_SYMBOLS) == 37
    for name, (bank, address) in expected.items():
        symbol = CRYSTAL_OBSERVATION_SYMBOLS[name]
        assert (symbol.bank, symbol.address) == (bank, address)
    assert len(CRYSTAL_OBSERVATION_SYMBOLS) == len(set(CRYSTAL_OBSERVATION_SYMBOLS))


def test_storage_symbols_match_the_pinned_generated_map() -> None:
    assert (
        CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.bank,
        CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL.address,
    ) == (1, 0xAD10)
    assert tuple(
        (box, symbol.bank, symbol.address)
        for box, symbol in CRYSTAL_STORED_BOX_SRAM_SYMBOLS.items()
    ) == (
        (1, 2, 0xA000),
        (2, 2, 0xA450),
        (3, 2, 0xA8A0),
        (4, 2, 0xACF0),
        (5, 2, 0xB140),
        (6, 2, 0xB590),
        (7, 2, 0xB9E0),
        (8, 3, 0xA000),
        (9, 3, 0xA450),
        (10, 3, 0xA8A0),
        (11, 3, 0xACF0),
        (12, 3, 0xB140),
        (13, 3, 0xB590),
        (14, 3, 0xB9E0),
    )


def test_owner_sha256_binding_is_path_free_and_does_not_mutate_the_template() -> None:
    digest = "ab" * 32
    bound = CRYSTAL_US_REV0_SOURCE_CONTRACT.with_owner_rom_sha256(digest)

    assert bound.rom_sha256 == digest
    assert bound.live_identity_complete
    assert CRYSTAL_US_REV0_SOURCE_CONTRACT.rom_sha256 is None
    assert bound.source_commit == CRYSTAL_US_REV0_SOURCE_CONTRACT.source_commit
    assert bound.public_dict()["rom"]["sha256"] == digest  # type: ignore[index]

    for bad in ("AB" * 32, "0" * 63, "g" * 64, ""):
        with pytest.raises(CrystalSourceContractError, match="SHA-256"):
            CRYSTAL_US_REV0_SOURCE_CONTRACT.with_owner_rom_sha256(bad)


def test_symbol_contract_rejects_wrong_bank_or_memory_region() -> None:
    with pytest.raises(CrystalSourceContractError, match="fixed"):
        CrystalMemorySymbol("wFixed", 1, 0xCF00)
    with pytest.raises(CrystalSourceContractError, match="non-zero"):
        CrystalMemorySymbol("wSwitchable", 0, 0xD000)
    with pytest.raises(CrystalSourceContractError, match="outside"):
        CrystalMemorySymbol("wRom", 0, 0x4000)
    with pytest.raises(CrystalSourceContractError, match="between zero and three"):
        CrystalSramSymbol("sBox", 4, 0xA000)
    with pytest.raises(CrystalSourceContractError, match="outside"):
        CrystalSramSymbol("sBox", 1, 0xC000)


@pytest.mark.parametrize(
    "change",
    (
        {"game_id": "pokemon.mainline:crystal:wrong"},
        {"rom_header_title": "WRONG"},
        {"rom_size_bytes": 1},
        {"rom_sha1": "0" * 40},
        {"source_commit": "0" * 40},
        {"symbols_commit": "0" * 40},
        {"symbols_sha256": "0" * 64},
    ),
)
def test_source_contract_rejects_every_drifted_public_pin(change: dict[str, object]) -> None:
    with pytest.raises(CrystalSourceContractError, match="pinned source"):
        CrystalSourceContract(**change)  # type: ignore[arg-type]
