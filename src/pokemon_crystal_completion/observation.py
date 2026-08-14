"""Game-specific memory readers and semantic state extraction for Pokemon Crystal.

Only this module consumes the revision-pinned WRAM symbols.  Higher layers see
portable party and completion observations.  Raw reading is deliberately
bank-aware because most Crystal campaign state lives in switchable WRAM bank
one; treating ``0xd000`` as one flat address would silently read whichever bank
the game happened to leave selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pokemon_crystal_completion.source_contract import (
    CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL,
    CRYSTAL_OBSERVATION_SYMBOLS,
    CRYSTAL_STORED_BOX_SRAM_SYMBOLS,
    CrystalSramSymbol,
)
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)

CRYSTAL_SPECIES_COUNT = 251
CRYSTAL_NON_EVENT_REGISTRATION_TARGET = 250
CRYSTAL_PARTY_STRUCT_LENGTH = 0x30
CRYSTAL_PARTY_CAPACITY = 6
CRYSTAL_PARTY_SPECIES_LIST_LENGTH = CRYSTAL_PARTY_CAPACITY + 1
CRYSTAL_POKEDEX_FLAG_BYTES = 32
CRYSTAL_EGG_SPECIES_ID = 0xFD
CRYSTAL_BOX_COUNT = 14
CRYSTAL_BOX_CAPACITY = 20
CRYSTAL_BOX_STRUCT_LENGTH = 0x20
CRYSTAL_BOX_SPECIES_LIST_LENGTH = CRYSTAL_BOX_CAPACITY + 1
CRYSTAL_BOX_OBSERVATION_BYTES = (
    1 + CRYSTAL_BOX_SPECIES_LIST_LENGTH + CRYSTAL_BOX_CAPACITY * CRYSTAL_BOX_STRUCT_LENGTH
)
CRYSTAL_TOTAL_STORAGE_CAPACITY = CRYSTAL_BOX_COUNT * CRYSTAL_BOX_CAPACITY

_MON_SPECIES = 0x00
_MON_ITEM = 0x01
_MON_MOVES = 0x02
_MON_EXP = 0x08
_MON_PP = 0x17
_MON_LEVEL = 0x1F
_MON_STATUS = 0x20
_MON_HP = 0x22
_MON_MAX_HP = 0x24


class CrystalObservationError(ValueError):
    """Raised when a raw Crystal read is incoherent or semantically invalid."""


class CrystalBankedMemoryReader(Protocol):
    """Read an exact WRAM bank without changing emulator state."""

    def read_wram(self, bank: int, address: int, length: int) -> bytes: ...


class CrystalStorageMemoryReader(CrystalBankedMemoryReader, Protocol):
    """Read exact WRAM and cartridge-RAM banks without changing either."""

    def read_cartridge_ram(self, bank: int, address: int, length: int) -> bytes: ...


class CrystalBattleMenuPhase(StrEnum):
    UNKNOWN = "unknown"
    MAIN = "main"
    MOVE = "move"


class CrystalPocket(StrEnum):
    ITEMS = "items"
    BALLS = "balls"


@dataclass(frozen=True, slots=True)
class CrystalBattleMenuState:
    """Revision-pinned menu meaning without exposing menu RAM to route code."""

    phase: CrystalBattleMenuPhase
    selected_move_slot: int | None = None
    selected_main_command: int | None = None


class CrystalBattleStateReader(Protocol):
    """Semantic subset of the Crystal StateReader used by the controller."""

    # Note: A full RawGameState for Crystal will be defined here later.
    def read_battle_menu_state(self, raw: object) -> CrystalBattleMenuState: ...


@dataclass(frozen=True, slots=True)
class CrystalPokedexProgress:
    """Seen and caught progress against the non-event Crystal registration target."""

    registered: CompletionProgress
    seen: CompletionProgress

    def __post_init__(self) -> None:
        if self.registered.target != CRYSTAL_NON_EVENT_REGISTRATION_TARGET:
            raise CrystalObservationError("Crystal registered target differs")
        if self.seen.target != CRYSTAL_NON_EVENT_REGISTRATION_TARGET:
            raise CrystalObservationError("Crystal seen target differs")
        if self.registered.completed > self.seen.completed:
            raise CrystalObservationError("caught Crystal species must also be seen")


@dataclass(frozen=True, slots=True)
class CrystalStoredSpecimen:
    """One visible PC occupant; egg internals deliberately remain hidden."""

    box_number: int
    slot: int
    species_id: int | None
    level: int
    is_egg: bool = False

    def __post_init__(self) -> None:
        if type(self.box_number) is not int or not 1 <= self.box_number <= CRYSTAL_BOX_COUNT:
            raise CrystalObservationError("Crystal stored specimen box is invalid")
        if type(self.slot) is not int or not 1 <= self.slot <= CRYSTAL_BOX_CAPACITY:
            raise CrystalObservationError("Crystal stored specimen slot is invalid")
        if type(self.level) is not int or not 1 <= self.level <= 100:
            raise CrystalObservationError("Crystal stored specimen level is invalid")
        if not isinstance(self.is_egg, bool):
            raise CrystalObservationError("Crystal stored egg flag is invalid")
        if self.is_egg:
            if self.species_id is not None:
                raise CrystalObservationError("Crystal egg cannot expose its hidden species")
        elif type(self.species_id) is not int or not 1 <= self.species_id <= CRYSTAL_SPECIES_COUNT:
            raise CrystalObservationError("Crystal stored species is outside the Pokédex")


@dataclass(frozen=True, slots=True)
class CrystalBoxObservation:
    box_number: int
    specimens: tuple[CrystalStoredSpecimen, ...]

    def __post_init__(self) -> None:
        if type(self.box_number) is not int or not 1 <= self.box_number <= CRYSTAL_BOX_COUNT:
            raise CrystalObservationError("Crystal box number is invalid")
        if len(self.specimens) > CRYSTAL_BOX_CAPACITY or any(
            not isinstance(item, CrystalStoredSpecimen)
            for item in self.specimens
        ):
            raise CrystalObservationError("Crystal box specimens are invalid")
        if tuple(item.slot for item in self.specimens) != tuple(
            range(1, len(self.specimens) + 1)
        ) or any(item.box_number != self.box_number for item in self.specimens):
            raise CrystalObservationError("Crystal box specimen ordering is invalid")

    @property
    def free_slots(self) -> int:
        return CRYSTAL_BOX_CAPACITY - len(self.specimens)


@dataclass(frozen=True, slots=True)
class CrystalStorageObservation:
    """All 14 boxes, with the live active-box copy replacing its saved copy."""

    current_box_number: int
    boxes: tuple[CrystalBoxObservation, ...]

    def __post_init__(self) -> None:
        if (
            type(self.current_box_number) is not int
            or not 1 <= self.current_box_number <= CRYSTAL_BOX_COUNT
        ):
            raise CrystalObservationError("Crystal current box is invalid")
        if tuple(box.box_number for box in self.boxes) != tuple(
            range(1, CRYSTAL_BOX_COUNT + 1)
        ):
            raise CrystalObservationError("Crystal storage must contain all boxes in order")

    @property
    def occupied_slots(self) -> int:
        return sum(len(box.specimens) for box in self.boxes)

    @property
    def free_slots(self) -> int:
        return CRYSTAL_TOTAL_STORAGE_CAPACITY - self.occupied_slots

    @property
    def egg_count(self) -> int:
        return sum(item.is_egg for box in self.boxes for item in box.specimens)

    @property
    def living_species_ids(self) -> frozenset[int]:
        return frozenset(
            item.species_id
            for box in self.boxes
            for item in box.specimens
            if item.species_id is not None
        )

    @property
    def level_cap_species_ids(self) -> frozenset[int]:
        return frozenset(
            item.species_id
            for box in self.boxes
            for item in box.specimens
            if item.species_id is not None and item.level == 100
        )


@dataclass(frozen=True, slots=True)
class CrystalOwnershipProgress:
    """Observable unique-species ownership across party and all PC boxes."""

    living: CompletionProgress
    level_cap: CompletionProgress
    boxed_specimens: int
    opaque_eggs: int
    free_storage_slots: int

    def __post_init__(self) -> None:
        if self.living.target != CRYSTAL_NON_EVENT_REGISTRATION_TARGET:
            raise CrystalObservationError("Crystal living target differs")
        if self.level_cap.target != CRYSTAL_NON_EVENT_REGISTRATION_TARGET:
            raise CrystalObservationError("Crystal level-cap target differs")
        if self.level_cap.completed > self.living.completed:
            raise CrystalObservationError("Crystal level-cap ownership exceeds living ownership")
        for name in ("boxed_specimens", "opaque_eggs", "free_storage_slots"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise CrystalObservationError(f"Crystal {name} is invalid")


def derive_crystal_ownership_progress(
    party: PartyObservation,
    storage: CrystalStorageObservation,
) -> CrystalOwnershipProgress:
    """Combine visible party and PC ownership without inferring egg species."""

    if not isinstance(party, PartyObservation):
        raise TypeError("party must be PartyObservation")
    if not isinstance(storage, CrystalStorageObservation):
        raise TypeError("storage must be CrystalStorageObservation")
    ordinary = frozenset(range(1, CRYSTAL_NON_EVENT_REGISTRATION_TARGET + 1))
    party_species = frozenset(party.species_ids()) & ordinary
    party_level_cap = frozenset(
        item.species_id for item in party.members if item.level == 100
    ) & ordinary
    living = (party_species | storage.living_species_ids) & ordinary
    level_cap = (party_level_cap | storage.level_cap_species_ids) & ordinary
    return CrystalOwnershipProgress(
        living=CompletionProgress(len(living), len(ordinary)),
        level_cap=CompletionProgress(len(level_cap), len(ordinary)),
        boxed_specimens=storage.occupied_slots,
        opaque_eggs=storage.egg_count,
        free_storage_slots=storage.free_slots,
    )


CRYSTAL_MAX_ITEM_STACK = 99
CRYSTAL_ITEMS_POCKET_CAPACITY = 20
CRYSTAL_BALLS_POCKET_CAPACITY = 12
CRYSTAL_ITEM_ID_MAX = 0xBE
CRYSTAL_BALL_ITEM_IDS = frozenset(
    {0x01, 0x02, 0x04, 0x05, 0x9D, 0x9F, 0xA0, 0xA1, 0xA4, 0xA5, 0xA6, 0xB1}
)
CRYSTAL_RECOVERY_ITEM_IDS = frozenset(
    {
        0x0E,  # Full Restore
        0x0F,  # Max Potion
        0x10,  # Hyper Potion
        0x11,  # Super Potion
        0x12,  # Potion
        0x27,  # Revive
        0x28,  # Max Revive
        0x2E,  # Fresh Water
        0x2F,  # Soda Pop
        0x30,  # Lemonade
        0x48,  # MooMoo Milk
        0x72,  # RageCandyBar
        0x79,  # EnergyPowder
        0x7A,  # Energy Root
        0x7C,  # Revival Herb
        0x8B,  # Berry Juice
        0x9C,  # Sacred Ash
        0xAD,  # Berry
        0xAE,  # Gold Berry
    }
)


@dataclass(frozen=True, slots=True)
class CrystalItemStack:
    pocket: CrystalPocket
    item_id: int
    quantity: int

    def __post_init__(self) -> None:
        if not isinstance(self.pocket, CrystalPocket):
            raise CrystalObservationError("Crystal item pocket is invalid")
        if type(self.item_id) is not int or not 1 <= self.item_id <= CRYSTAL_ITEM_ID_MAX:
            raise CrystalObservationError("Crystal item identity is invalid")
        if (
            type(self.quantity) is not int
            or not 1 <= self.quantity <= CRYSTAL_MAX_ITEM_STACK
        ):
            raise CrystalObservationError("Crystal item quantity is invalid")
        if (self.item_id in CRYSTAL_BALL_ITEM_IDS) is not (
            self.pocket is CrystalPocket.BALLS
        ):
            raise CrystalObservationError("Crystal item appears in the wrong pocket")


@dataclass(frozen=True, slots=True)
class CrystalInventoryObservation:
    items: tuple[CrystalItemStack, ...]
    balls: tuple[CrystalItemStack, ...]

    def __post_init__(self) -> None:
        if len(self.items) > CRYSTAL_ITEMS_POCKET_CAPACITY or any(
            item.pocket is not CrystalPocket.ITEMS for item in self.items
        ):
            raise CrystalObservationError("Crystal items pocket is invalid")
        if len(self.balls) > CRYSTAL_BALLS_POCKET_CAPACITY or any(
            item.pocket is not CrystalPocket.BALLS for item in self.balls
        ):
            raise CrystalObservationError("Crystal balls pocket is invalid")
        identities = tuple(item.item_id for item in (*self.items, *self.balls))
        if len(identities) != len(set(identities)):
            raise CrystalObservationError("Crystal inventory repeats an item stack")

    @property
    def capture_item_count(self) -> int:
        return sum(item.quantity for item in self.balls)

    @property
    def recovery_item_count(self) -> int:
        return sum(
            item.quantity for item in self.items if item.item_id in CRYSTAL_RECOVERY_ITEM_IDS
        )


def decode_crystal_party(
    *,
    count: int,
    species: bytes,
    structs: bytes,
) -> PartyObservation:
    """Decode the six Gen II party structs into the portable party contract."""

    if type(count) is not int or not 0 <= count <= CRYSTAL_PARTY_CAPACITY:  # noqa: E721
        raise CrystalObservationError("Crystal party count must be between zero and six")
    _require_bytes(
        species,
        CRYSTAL_PARTY_SPECIES_LIST_LENGTH,
        subject="Crystal party species",
    )
    _require_bytes(
        structs,
        CRYSTAL_PARTY_CAPACITY * CRYSTAL_PARTY_STRUCT_LENGTH,
        subject="Crystal party structs",
    )
    members: list[PartyMemberObservation] = []
    if species[count] != 0xFF:
        raise CrystalObservationError("Crystal party species list lacks its terminator")
    for index in range(count):
        start = index * CRYSTAL_PARTY_STRUCT_LENGTH
        payload = structs[start : start + CRYSTAL_PARTY_STRUCT_LENGTH]
        species_id = species[index]
        if species_id == CRYSTAL_EGG_SPECIES_ID:
            raise CrystalObservationError(
                "Crystal party egg requires the later egg-aware observation contract"
            )
        if not 1 <= species_id <= CRYSTAL_SPECIES_COUNT:
            raise CrystalObservationError("Crystal party species is outside the Pokédex")
        if payload[_MON_SPECIES] != species_id:
            raise CrystalObservationError("Crystal party list and struct species disagree")
        level = payload[_MON_LEVEL]
        hp = int.from_bytes(payload[_MON_HP : _MON_HP + 2], "big")
        max_hp = int.from_bytes(payload[_MON_MAX_HP : _MON_MAX_HP + 2], "big")
        moves = tuple(
            MoveObservation(
                move_id=payload[_MON_MOVES + move_slot],
                current_pp=payload[_MON_PP + move_slot] & 0x3F,
            )
            for move_slot in range(4)
        )
        held_item = payload[_MON_ITEM]
        members.append(
            PartyMemberObservation(
                slot=index + 1,
                species_id=species_id,
                level=level,
                hp=hp,
                max_hp=max_hp,
                status=_decode_crystal_status(payload[_MON_STATUS]),
                moves=moves,
                experience=int.from_bytes(payload[_MON_EXP : _MON_EXP + 3], "big"),
                held_item_ref=(
                    None if held_item == 0 else f"pokemon.crystal:item:{held_item:03d}"
                ),
            )
        )
    return PartyObservation(tuple(members))


def read_crystal_party(
    memory: CrystalBankedMemoryReader,
    *,
    maximum_attempts: int = 3,
) -> PartyObservation:
    """Take a bounded coherent party read from banked WRAM."""

    if type(maximum_attempts) is not int or maximum_attempts < 1:  # noqa: E721
        raise CrystalObservationError("Crystal party read needs a positive attempt bound")
    count_symbol = CRYSTAL_OBSERVATION_SYMBOLS["wPartyCount"]
    species_symbol = CRYSTAL_OBSERVATION_SYMBOLS["wPartySpecies"]
    structs_symbol = CRYSTAL_OBSERVATION_SYMBOLS["wPartyMon1"]
    last_error: CrystalObservationError | None = None
    for _ in range(maximum_attempts):
        count_before = _read_symbol(memory, count_symbol.name, 1)[0]
        species_before = _read_symbol(
            memory,
            species_symbol.name,
            CRYSTAL_PARTY_SPECIES_LIST_LENGTH,
        )
        structs_before = _read_symbol(
            memory,
            structs_symbol.name,
            CRYSTAL_PARTY_CAPACITY * CRYSTAL_PARTY_STRUCT_LENGTH,
        )
        count_after = _read_symbol(memory, count_symbol.name, 1)[0]
        species_after = _read_symbol(
            memory,
            species_symbol.name,
            CRYSTAL_PARTY_SPECIES_LIST_LENGTH,
        )
        structs_after = _read_symbol(
            memory,
            structs_symbol.name,
            CRYSTAL_PARTY_CAPACITY * CRYSTAL_PARTY_STRUCT_LENGTH,
        )
        if (
            count_before != count_after
            or species_before != species_after
            or structs_before != structs_after
        ):
            last_error = CrystalObservationError("Crystal party changed during observation")
            continue
        try:
            return decode_crystal_party(
                count=count_before,
                species=species_before,
                structs=structs_before,
            )
        except (CrystalObservationError, TypeError, ValueError) as error:
            last_error = CrystalObservationError(str(error))
    raise last_error or CrystalObservationError("Crystal party observation failed")


def decode_crystal_pokedex(
    *,
    caught: bytes,
    seen: bytes,
) -> CrystalPokedexProgress:
    """Count the 250 ordinary targets while excluding event-only Celebi."""

    _require_bytes(caught, CRYSTAL_POKEDEX_FLAG_BYTES, subject="Crystal caught flags")
    _require_bytes(seen, CRYSTAL_POKEDEX_FLAG_BYTES, subject="Crystal seen flags")
    caught_set = _flag_indices(caught)
    seen_set = _flag_indices(seen)
    if any(index > CRYSTAL_SPECIES_COUNT for index in caught_set | seen_set):
        raise CrystalObservationError("Crystal Pokédex padding bits must be clear")
    if not caught_set <= seen_set:
        raise CrystalObservationError("caught Crystal species must also be seen")
    ordinary = frozenset(range(1, CRYSTAL_NON_EVENT_REGISTRATION_TARGET + 1))
    return CrystalPokedexProgress(
        registered=CompletionProgress(len(caught_set & ordinary), len(ordinary)),
        seen=CompletionProgress(len(seen_set & ordinary), len(ordinary)),
    )


def read_crystal_pokedex(
    memory: CrystalBankedMemoryReader,
    *,
    maximum_attempts: int = 3,
) -> CrystalPokedexProgress:
    """Take a bounded coherent Pokédex read from banked WRAM."""

    if type(maximum_attempts) is not int or maximum_attempts < 1:  # noqa: E721
        raise CrystalObservationError("Crystal Pokédex read needs a positive attempt bound")
    last_error: CrystalObservationError | None = None
    for _ in range(maximum_attempts):
        caught_before = _read_symbol(memory, "wPokedexCaught", CRYSTAL_POKEDEX_FLAG_BYTES)
        seen_before = _read_symbol(memory, "wPokedexSeen", CRYSTAL_POKEDEX_FLAG_BYTES)
        caught_after = _read_symbol(memory, "wPokedexCaught", CRYSTAL_POKEDEX_FLAG_BYTES)
        seen_after = _read_symbol(memory, "wPokedexSeen", CRYSTAL_POKEDEX_FLAG_BYTES)
        if caught_before != caught_after or seen_before != seen_after:
            last_error = CrystalObservationError("Crystal Pokédex changed during observation")
            continue
        try:
            return decode_crystal_pokedex(caught=caught_before, seen=seen_before)
        except CrystalObservationError as error:
            last_error = error
    raise last_error or CrystalObservationError("Crystal Pokédex observation failed")


def decode_crystal_box(payload: bytes, *, box_number: int) -> CrystalBoxObservation:
    """Decode the observable prefix of one international Gen II PC box."""

    if type(box_number) is not int or not 1 <= box_number <= CRYSTAL_BOX_COUNT:
        raise CrystalObservationError("Crystal box number is invalid")
    _require_bytes(payload, CRYSTAL_BOX_OBSERVATION_BYTES, subject="Crystal box payload")
    count = payload[0]
    if count > CRYSTAL_BOX_CAPACITY:
        raise CrystalObservationError("Crystal box count exceeds capacity")
    species = payload[1 : 1 + CRYSTAL_BOX_SPECIES_LIST_LENGTH]
    if species[count] != 0xFF:
        raise CrystalObservationError("Crystal box species list lacks its terminator")
    structs_start = 1 + CRYSTAL_BOX_SPECIES_LIST_LENGTH
    specimens: list[CrystalStoredSpecimen] = []
    for index in range(count):
        visible_species = species[index]
        start = structs_start + index * CRYSTAL_BOX_STRUCT_LENGTH
        hidden_species = payload[start]
        level = payload[start + 0x1F]
        if visible_species == CRYSTAL_EGG_SPECIES_ID:
            if not 1 <= hidden_species <= CRYSTAL_SPECIES_COUNT:
                raise CrystalObservationError("Crystal egg has an invalid hidden species")
            specimens.append(
                CrystalStoredSpecimen(
                    box_number=box_number,
                    slot=index + 1,
                    species_id=None,
                    level=level,
                    is_egg=True,
                )
            )
            continue
        if not 1 <= visible_species <= CRYSTAL_SPECIES_COUNT:
            raise CrystalObservationError("Crystal box species is outside the Pokédex")
        if hidden_species != visible_species:
            raise CrystalObservationError("Crystal box list and struct species disagree")
        specimens.append(
            CrystalStoredSpecimen(
                box_number=box_number,
                slot=index + 1,
                species_id=visible_species,
                level=level,
            )
        )
    return CrystalBoxObservation(box_number=box_number, specimens=tuple(specimens))


def read_crystal_storage(
    memory: CrystalStorageMemoryReader,
    *,
    maximum_attempts: int = 3,
) -> CrystalStorageObservation:
    """Take one bounded coherent view of the live box plus 13 saved boxes."""

    if type(maximum_attempts) is not int or maximum_attempts < 1:  # noqa: E721
        raise CrystalObservationError("Crystal storage read needs a positive attempt bound")
    current_symbol = CRYSTAL_OBSERVATION_SYMBOLS["wCurBox"]
    last_error: CrystalObservationError | None = None
    for _ in range(maximum_attempts):
        current_before = _read_symbol(memory, current_symbol.name, 1)[0]
        if current_before >= CRYSTAL_BOX_COUNT:
            last_error = CrystalObservationError("Crystal current box is invalid")
            continue
        before = _read_all_crystal_boxes(memory, current_box_index=current_before)
        current_middle = _read_symbol(memory, current_symbol.name, 1)[0]
        if current_middle != current_before:
            last_error = CrystalObservationError("Crystal current box changed during observation")
            continue
        after = _read_all_crystal_boxes(memory, current_box_index=current_before)
        current_after = _read_symbol(memory, current_symbol.name, 1)[0]
        if current_after != current_before or after != before:
            last_error = CrystalObservationError("Crystal storage changed during observation")
            continue
        try:
            boxes = tuple(
                decode_crystal_box(payload, box_number=box_number)
                for box_number, payload in enumerate(before, start=1)
            )
            return CrystalStorageObservation(
                current_box_number=current_before + 1,
                boxes=boxes,
            )
        except CrystalObservationError as error:
            last_error = error
    raise last_error or CrystalObservationError("Crystal storage observation failed")


def decode_crystal_inventory(
    *,
    item_count: int,
    items: bytes,
    ball_count: int,
    balls: bytes,
) -> CrystalInventoryObservation:
    """Decode the two counted item/quantity pockets needed by goal state."""

    return CrystalInventoryObservation(
        items=_decode_crystal_pocket(
            count=item_count,
            payload=items,
            capacity=CRYSTAL_ITEMS_POCKET_CAPACITY,
            pocket=CrystalPocket.ITEMS,
        ),
        balls=_decode_crystal_pocket(
            count=ball_count,
            payload=balls,
            capacity=CRYSTAL_BALLS_POCKET_CAPACITY,
            pocket=CrystalPocket.BALLS,
        ),
    )


def read_crystal_inventory(
    memory: CrystalBankedMemoryReader,
    *,
    maximum_attempts: int = 3,
) -> CrystalInventoryObservation:
    """Take a bounded coherent inventory read from banked WRAM."""

    if type(maximum_attempts) is not int or maximum_attempts < 1:  # noqa: E721
        raise CrystalObservationError("Crystal inventory read needs a positive attempt bound")
    last_error: CrystalObservationError | None = None
    for _ in range(maximum_attempts):
        item_count_before = _read_symbol(memory, "wNumItems", 1)[0]
        items_before = _read_symbol(
            memory,
            "wItems",
            CRYSTAL_ITEMS_POCKET_CAPACITY * 2 + 1,
        )
        ball_count_before = _read_symbol(memory, "wNumBalls", 1)[0]
        balls_before = _read_symbol(
            memory,
            "wBalls",
            CRYSTAL_BALLS_POCKET_CAPACITY * 2 + 1,
        )
        item_count_after = _read_symbol(memory, "wNumItems", 1)[0]
        items_after = _read_symbol(
            memory,
            "wItems",
            CRYSTAL_ITEMS_POCKET_CAPACITY * 2 + 1,
        )
        ball_count_after = _read_symbol(memory, "wNumBalls", 1)[0]
        balls_after = _read_symbol(
            memory,
            "wBalls",
            CRYSTAL_BALLS_POCKET_CAPACITY * 2 + 1,
        )
        if (
            item_count_before != item_count_after
            or items_before != items_after
            or ball_count_before != ball_count_after
            or balls_before != balls_after
        ):
            last_error = CrystalObservationError(
                "Crystal inventory changed during observation"
            )
            continue
        try:
            return decode_crystal_inventory(
                item_count=item_count_before,
                items=items_before,
                ball_count=ball_count_before,
                balls=balls_before,
            )
        except CrystalObservationError as error:
            last_error = error
    raise last_error or CrystalObservationError("Crystal inventory observation failed")


def _decode_crystal_pocket(
    *,
    count: int,
    payload: bytes,
    capacity: int,
    pocket: CrystalPocket,
) -> tuple[CrystalItemStack, ...]:
    if type(count) is not int or not 0 <= count <= capacity:  # noqa: E721
        raise CrystalObservationError("Crystal pocket count exceeds capacity")
    _require_bytes(payload, capacity * 2 + 1, subject=f"Crystal {pocket.value} pocket")
    if payload[count * 2] != 0xFF:
        raise CrystalObservationError("Crystal pocket lacks its terminator")
    rows = tuple(
        CrystalItemStack(
            pocket=pocket,
            item_id=payload[index * 2],
            quantity=payload[index * 2 + 1],
        )
        for index in range(count)
    )
    if len({item.item_id for item in rows}) != len(rows):
        raise CrystalObservationError("Crystal pocket repeats an item stack")
    return rows


def _read_all_crystal_boxes(
    memory: CrystalStorageMemoryReader,
    *,
    current_box_index: int,
) -> tuple[bytes, ...]:
    rows: list[bytes] = []
    for box_number in range(1, CRYSTAL_BOX_COUNT + 1):
        symbol = (
            CRYSTAL_ACTIVE_BOX_SRAM_SYMBOL
            if box_number == current_box_index + 1
            else CRYSTAL_STORED_BOX_SRAM_SYMBOLS[box_number]
        )
        rows.append(_read_sram_symbol(memory, symbol, CRYSTAL_BOX_OBSERVATION_BYTES))
    return tuple(rows)


def _decode_crystal_status(value: int) -> StatusCondition:
    if type(value) is not int or not 0 <= value <= 0xFF:  # noqa: E721
        raise CrystalObservationError("Crystal status byte is invalid")
    sleep = value & 0x07
    persistent = value & 0x78
    unknown = value & 0x80
    if unknown or (sleep and persistent) or persistent.bit_count() > 1:
        raise CrystalObservationError("Crystal status byte has incompatible conditions")
    if sleep:
        return StatusCondition.SLEEP
    return {
        0x00: StatusCondition.HEALTHY,
        0x08: StatusCondition.POISON,
        0x10: StatusCondition.BURN,
        0x20: StatusCondition.FREEZE,
        0x40: StatusCondition.PARALYSIS,
    }[persistent]


def _flag_indices(payload: bytes) -> frozenset[int]:
    return frozenset(
        byte_index * 8 + bit_index + 1
        for byte_index, value in enumerate(payload)
        for bit_index in range(8)
        if value & (1 << bit_index)
    )


def _read_symbol(memory: CrystalBankedMemoryReader, name: str, length: int) -> bytes:
    symbol = CRYSTAL_OBSERVATION_SYMBOLS[name]
    try:
        payload = memory.read_wram(symbol.bank, symbol.address, length)
    except Exception as error:
        raise CrystalObservationError("Crystal banked WRAM read failed") from error
    _require_bytes(payload, length, subject=f"Crystal {name} read")
    return payload


def _read_sram_symbol(
    memory: CrystalStorageMemoryReader,
    symbol: CrystalSramSymbol,
    length: int,
) -> bytes:
    try:
        payload = memory.read_cartridge_ram(symbol.bank, symbol.address, length)
    except Exception as error:
        raise CrystalObservationError("Crystal banked SRAM read failed") from error
    _require_bytes(payload, length, subject=f"Crystal {symbol.name} read")
    return payload


def _require_bytes(value: object, length: int, *, subject: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != length:
        raise CrystalObservationError(f"{subject} must contain exactly {length} bytes")
    return value


__all__ = [
    "CRYSTAL_PARTY_CAPACITY",
    "CRYSTAL_PARTY_SPECIES_LIST_LENGTH",
    "CRYSTAL_PARTY_STRUCT_LENGTH",
    "CRYSTAL_POKEDEX_FLAG_BYTES",
    "CRYSTAL_NON_EVENT_REGISTRATION_TARGET",
    "CRYSTAL_SPECIES_COUNT",
    "CRYSTAL_BOX_CAPACITY",
    "CRYSTAL_BOX_COUNT",
    "CRYSTAL_BOX_OBSERVATION_BYTES",
    "CRYSTAL_BALL_ITEM_IDS",
    "CRYSTAL_BALLS_POCKET_CAPACITY",
    "CRYSTAL_ITEMS_POCKET_CAPACITY",
    "CRYSTAL_RECOVERY_ITEM_IDS",
    "CRYSTAL_TOTAL_STORAGE_CAPACITY",
    "CrystalBankedMemoryReader",
    "CrystalBattleMenuPhase",
    "CrystalBattleMenuState",
    "CrystalBattleStateReader",
    "CrystalBoxObservation",
    "CrystalInventoryObservation",
    "CrystalItemStack",
    "CrystalObservationError",
    "CrystalOwnershipProgress",
    "CrystalPocket",
    "CrystalPokedexProgress",
    "CrystalStorageMemoryReader",
    "CrystalStorageObservation",
    "CrystalStoredSpecimen",
    "decode_crystal_box",
    "decode_crystal_inventory",
    "decode_crystal_party",
    "decode_crystal_pokedex",
    "derive_crystal_ownership_progress",
    "read_crystal_party",
    "read_crystal_pokedex",
    "read_crystal_inventory",
    "read_crystal_storage",
]
