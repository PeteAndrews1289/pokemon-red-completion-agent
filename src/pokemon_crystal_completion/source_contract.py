"""Public, revision-pinned authority for the first Pokemon Crystal adapter.

The adapter is deliberately pinned before a private cartridge is opened.  The
source and generated symbol identities are public; the eventual owner-supplied
ROM path is not.  A SHA-1 identifies the supported international v1.1 image,
while a SHA-256 remains a mandatory live-qualification field that can only be
bound from the owner's exact copy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

CRYSTAL_GAME_ID = "pokemon.mainline:crystal:gbc:international:rev1"
CRYSTAL_ADAPTER_ID = "pokemon.crystal.gbc.international.rev1.goal-state.v1"
CRYSTAL_ROM_ENVIRONMENT_VARIABLE = "POKEMON_CRYSTAL_ROM"
CRYSTAL_ROM_HEADER_TITLE = "PM_CRYSTAL"
CRYSTAL_ROM_SIZE_BYTES = 2_097_152
CRYSTAL_ROM_REVISION = 1
CRYSTAL_ROM_SHA1 = "f2f52230b536214ef7c9924f483392993e226cfb"
CRYSTAL_SOURCE_REPOSITORY = "https://github.com/pret/pokecrystal"
CRYSTAL_SOURCE_COMMIT = "7a7881d0d62e0ddbd82dcf10e7116807487ac651"
CRYSTAL_SYMBOLS_COMMIT = "cc6fc04f19c645f5c40f64f8d88b2ab42c7bdde8"
CRYSTAL_SYMBOLS_FILENAME = "pokecrystal11.sym"
CRYSTAL_SYMBOLS_SHA256 = "8a8b7a675bbb0e7b2e18d1604ecae68ac18aa0bd8f879cc58351489352bf8ef3"


class CrystalSourceContractError(ValueError):
    """Raised when revision-specific Crystal authority is incomplete."""


@dataclass(frozen=True, slots=True)
class CrystalMemorySymbol:
    """One allowlisted WRAM symbol derived from the pinned generated map."""

    name: str
    bank: int
    address: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.startswith("w"):
            raise CrystalSourceContractError("Crystal symbol name must be a WRAM label")
        if type(self.bank) is not int or not 0 <= self.bank <= 7:  # noqa: E721
            raise CrystalSourceContractError("Crystal WRAM bank must be between zero and seven")
        if type(self.address) is not int or not 0xC000 <= self.address <= 0xDFFF:  # noqa: E721
            raise CrystalSourceContractError("Crystal WRAM address is outside WRAM")
        if self.address < 0xD000 and self.bank != 0:
            raise CrystalSourceContractError("fixed Crystal WRAM must use bank zero")
        if self.address >= 0xD000 and self.bank == 0:
            raise CrystalSourceContractError("switchable Crystal WRAM needs a non-zero bank")


@dataclass(frozen=True, slots=True)
class CrystalSramSymbol:
    """One allowlisted cartridge-RAM symbol from the pinned generated map."""

    name: str
    bank: int
    address: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.startswith("s"):
            raise CrystalSourceContractError("Crystal SRAM symbol name must be an SRAM label")
        if type(self.bank) is not int or not 0 <= self.bank <= 3:  # noqa: E721
            raise CrystalSourceContractError("Crystal SRAM bank must be between zero and three")
        if type(self.address) is not int or not 0xA000 <= self.address <= 0xBFFF:  # noqa: E721
            raise CrystalSourceContractError("Crystal SRAM address is outside cartridge RAM")


_SYMBOL_ROWS = (
    ("wMenuJoypad", 0, 0xCF73),
    ("wMenuCursorY", 0, 0xCFA9),
    ("wMenuCursorX", 0, 0xCFAA),
    ("wJoypadDisable", 0, 0xCFBE),
    ("wBattleMenuCursorPosition", 1, 0xD0D2),
    ("wCurBattleMon", 1, 0xD0D4),
    ("wBattleMode", 1, 0xD22D),
    ("wMapStatus", 1, 0xD432),
    ("wMapEventStatus", 1, 0xD433),
    ("wScriptMode", 1, 0xD437),
    ("wScriptRunning", 1, 0xD438),
    ("wJohtoBadges", 1, 0xD857),
    ("wKantoBadges", 1, 0xD858),
    ("wNumItems", 1, 0xD892),
    ("wItems", 1, 0xD893),
    ("wNumBalls", 1, 0xD8D7),
    ("wBalls", 1, 0xD8D8),
    ("wPlayerState", 1, 0xD95D),
    ("wCurBox", 1, 0xDB72),
    ("wMapGroup", 1, 0xDCB5),
    ("wMapNumber", 1, 0xDCB6),
    ("wYCoord", 1, 0xDCB7),
    ("wXCoord", 1, 0xDCB8),
    ("wPartyCount", 1, 0xDCD7),
    ("wPartySpecies", 1, 0xDCD8),
    ("wPartyMon1", 1, 0xDCDF),
    ("wPartyMon1Moves", 1, 0xDCE1),
    ("wPartyMon1Exp", 1, 0xDCE7),
    ("wPartyMon1PP", 1, 0xDCF6),
    ("wPartyMon1Level", 1, 0xDCFE),
    ("wPartyMon1Status", 1, 0xDCFF),
    ("wPartyMon1HP", 1, 0xDD01),
    ("wPartyMon1MaxHP", 1, 0xDD03),
    ("wPokedexCaught", 1, 0xDE99),
    ("wEndPokedexCaught", 1, 0xDEB9),
    ("wPokedexSeen", 1, 0xDEB9),
    ("wEndPokedexSeen", 1, 0xDED9),
)

CRYSTAL_OBSERVATION_SYMBOLS: Mapping[str, CrystalMemorySymbol] = MappingProxyType(
    {
        name: CrystalMemorySymbol(name=name, bank=bank, address=address)
        for name, bank, address in _SYMBOL_ROWS
    }
)

CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL = CrystalSramSymbol("sBox", 1, 0xAD10)
_STORED_BOX_ROWS = (
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
CRYSTAL_STORED_BOX_SRAM_SYMBOLS: Mapping[int, CrystalSramSymbol] = MappingProxyType(
    {
        box_number: CrystalSramSymbol(
            name=f"sBox{box_number}",
            bank=bank,
            address=address,
        )
        for box_number, bank, address in _STORED_BOX_ROWS
    }
)


@dataclass(frozen=True, slots=True)
class CrystalSourceContract:
    """Everything public that must match before live Crystal state is read."""

    game_id: str = CRYSTAL_GAME_ID
    adapter_id: str = CRYSTAL_ADAPTER_ID
    rom_header_title: str = CRYSTAL_ROM_HEADER_TITLE
    rom_size_bytes: int = CRYSTAL_ROM_SIZE_BYTES
    rom_revision: int = CRYSTAL_ROM_REVISION
    rom_sha1: str = CRYSTAL_ROM_SHA1
    rom_sha256: str | None = None
    source_repository: str = CRYSTAL_SOURCE_REPOSITORY
    source_commit: str = CRYSTAL_SOURCE_COMMIT
    symbols_commit: str = CRYSTAL_SYMBOLS_COMMIT
    symbols_filename: str = CRYSTAL_SYMBOLS_FILENAME
    symbols_sha256: str = CRYSTAL_SYMBOLS_SHA256

    def __post_init__(self) -> None:
        expected = {
            "game_id": CRYSTAL_GAME_ID,
            "adapter_id": CRYSTAL_ADAPTER_ID,
            "rom_header_title": CRYSTAL_ROM_HEADER_TITLE,
            "rom_size_bytes": CRYSTAL_ROM_SIZE_BYTES,
            "rom_revision": CRYSTAL_ROM_REVISION,
            "rom_sha1": CRYSTAL_ROM_SHA1,
            "source_repository": CRYSTAL_SOURCE_REPOSITORY,
            "source_commit": CRYSTAL_SOURCE_COMMIT,
            "symbols_commit": CRYSTAL_SYMBOLS_COMMIT,
            "symbols_filename": CRYSTAL_SYMBOLS_FILENAME,
            "symbols_sha256": CRYSTAL_SYMBOLS_SHA256,
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise CrystalSourceContractError(f"Crystal {name} differs from the pinned source")
        if self.rom_sha256 is not None:
            _validate_sha256(self.rom_sha256)

    @property
    def live_identity_complete(self) -> bool:
        """Whether the owner's exact bytes have supplied the second digest."""

        return self.rom_sha256 is not None

    def with_owner_rom_sha256(self, sha256: str) -> CrystalSourceContract:
        """Bind the exact private copy without retaining its path or bytes."""

        _validate_sha256(sha256)
        return replace(self, rom_sha256=sha256)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.source-contract.v1",
            "game_id": self.game_id,
            "adapter_id": self.adapter_id,
            "rom": {
                "header_title": self.rom_header_title,
                "revision": self.rom_revision,
                "size_bytes": self.rom_size_bytes,
                "sha1": self.rom_sha1,
                "sha256": self.rom_sha256,
                "sha256_required_before_private_context_access": True,
            },
            "source": {
                "repository": self.source_repository,
                "commit": self.source_commit,
                "symbols_commit": self.symbols_commit,
                "symbols_filename": self.symbols_filename,
                "symbols_sha256": self.symbols_sha256,
            },
            "allowlisted_symbol_count": len(CRYSTAL_OBSERVATION_SYMBOLS),
            "private_path_fields": 0,
            "rom_bytes_fields": 0,
        }


CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT = CrystalSourceContract()


def _validate_sha256(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CrystalSourceContractError("Crystal ROM SHA-256 must be lowercase hexadecimal")


__all__ = [
    "CRYSTAL_ADAPTER_ID",
    "CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL",
    "CRYSTAL_GAME_ID",
    "CRYSTAL_OBSERVATION_SYMBOLS",
    "CRYSTAL_ROM_ENVIRONMENT_VARIABLE",
    "CRYSTAL_ROM_REVISION",
    "CRYSTAL_SOURCE_COMMIT",
    "CRYSTAL_SOURCE_REPOSITORY",
    "CRYSTAL_STORED_BOX_SRAM_SYMBOLS",
    "CRYSTAL_SYMBOLS_COMMIT",
    "CRYSTAL_SYMBOLS_SHA256",
    "CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT",
    "CrystalMemorySymbol",
    "CrystalSramSymbol",
    "CrystalSourceContract",
    "CrystalSourceContractError",
]
