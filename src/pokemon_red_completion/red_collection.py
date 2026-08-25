"""Pokémon Red's explicit single-save, no-link living-Pokédex contract.

The supported lineage chooses Squirtle, the Helix Fossil, Hitmonlee, and
Jolteon.  The target therefore contains every National Pokédex species that can
coexist legitimately in that one Red save without a link cable, event
distribution, or MissingNo./item-duplication glitch.  Every omitted species is
named with one reason; nothing disappears into an unexplained denominator.
"""

from __future__ import annotations

from dataclasses import dataclass

from .collection import (
    CollectionContract,
    CollectionExclusion,
    CollectionExclusionReason,
    CollectionLocation,
    CollectionObservation,
    CollectionReport,
    LivingSpecimen,
    summarize_collection,
)
from .generation_one import GENERATION_ONE_SPECIES_COUNT, UNAVAILABLE_IN_RED
from .observation import RedBoxCollectionState, RedCurrentBoxState, RedPokedexState
from .party import PartyObservation

RED_COLLECTION_GAME_ID = "pokemon.mainline:red:gb:us:rev0"
NATIONAL_DEX_SIZE_GENERATION_ONE = GENERATION_ONE_SPECIES_COUNT
RED_SOLO_POKEDEX_TARGET_COUNT = 124
RED_SOLO_LIVING_TARGET_COUNT = 120

# National Pokédex number for each one-based internal species index. Zero is a
# MissingNo. hole. Derived from ``data/pokemon/dex_order.asm`` at the pinned
# pret/pokered commit documented by the observation adapter.
_RED_INTERNAL_TO_NATIONAL = (
    112,
    115,
    32,
    35,
    21,
    100,
    34,
    80,
    2,
    103,
    108,
    102,
    88,
    94,
    29,
    31,
    104,
    111,
    131,
    59,
    151,
    130,
    90,
    72,
    92,
    123,
    120,
    9,
    127,
    114,
    0,
    0,
    58,
    95,
    22,
    16,
    79,
    64,
    75,
    113,
    67,
    122,
    106,
    107,
    24,
    47,
    54,
    96,
    76,
    0,
    126,
    0,
    125,
    82,
    109,
    0,
    56,
    86,
    50,
    128,
    0,
    0,
    0,
    83,
    48,
    149,
    0,
    0,
    0,
    84,
    60,
    124,
    146,
    144,
    145,
    132,
    52,
    98,
    0,
    0,
    0,
    37,
    38,
    25,
    26,
    0,
    0,
    147,
    148,
    140,
    141,
    116,
    117,
    0,
    0,
    27,
    28,
    138,
    139,
    39,
    40,
    133,
    136,
    135,
    134,
    66,
    41,
    23,
    46,
    61,
    62,
    13,
    14,
    15,
    0,
    85,
    57,
    51,
    49,
    87,
    0,
    0,
    10,
    11,
    12,
    68,
    0,
    55,
    97,
    42,
    150,
    143,
    129,
    0,
    0,
    89,
    0,
    99,
    91,
    0,
    101,
    36,
    110,
    53,
    105,
    0,
    93,
    63,
    65,
    17,
    18,
    121,
    1,
    3,
    73,
    0,
    118,
    119,
    0,
    0,
    0,
    0,
    77,
    78,
    19,
    20,
    33,
    30,
    74,
    137,
    142,
    0,
    81,
    0,
    0,
    4,
    7,
    5,
    8,
    6,
    0,
    0,
    0,
    0,
    43,
    44,
    45,
    69,
    70,
    71,
)

if (
    len(_RED_INTERNAL_TO_NATIONAL) != 190
    or sum(number > 0 for number in _RED_INTERNAL_TO_NATIONAL) != NATIONAL_DEX_SIZE_GENERATION_ONE
):
    raise AssertionError("Red internal species order must cover all 151 real species")


def red_species_ref(national_dex_number: int) -> str:
    """Return the shared ontology reference for a Generation I species."""

    if (
        type(national_dex_number) is not int
        or not 1 <= national_dex_number <= NATIONAL_DEX_SIZE_GENERATION_ONE
    ):
        raise ValueError("national_dex_number must be between 1 and 151")
    return f"pokemon:national:{national_dex_number:03d}"


def red_species_number(species_ref: str) -> int:
    """Recover a National Pokédex number from a Red collection reference."""

    prefix = "pokemon:national:"
    if not isinstance(species_ref, str) or not species_ref.startswith(prefix):
        raise ValueError("species_ref is not a National Pokédex reference")
    suffix = species_ref.removeprefix(prefix)
    if len(suffix) != 3 or not suffix.isascii() or not suffix.isdigit():
        raise ValueError("species_ref must end in a three-digit National Pokédex number")
    number = int(suffix)
    if not 1 <= number <= NATIONAL_DEX_SIZE_GENERATION_ONE:
        raise ValueError("species_ref is outside the Generation I National Pokédex")
    return number


def red_internal_species_number(internal_species_id: int) -> int:
    """Translate Red's one-byte party/box identifier to a National Pokédex number."""

    if type(internal_species_id) is not int or not 1 <= internal_species_id <= len(
        _RED_INTERNAL_TO_NATIONAL
    ):
        raise ValueError("internal_species_id must be between 1 and 190")
    national_number = _RED_INTERNAL_TO_NATIONAL[internal_species_id - 1]
    if national_number == 0:
        raise ValueError("internal_species_id identifies MissingNo., not a real Pokémon")
    return national_number


def red_internal_species_id(national_dex_number: int) -> int:
    """Translate a National Pokédex number to Red's one-byte species identifier."""

    # Validate through the shared reference constructor so this inverse keeps
    # exactly the same 1..151 domain as every collection adapter.
    red_species_ref(national_dex_number)
    try:
        return _RED_INTERNAL_TO_NATIONAL.index(national_dex_number) + 1
    except ValueError:  # pragma: no cover - the module invariant covers all 151
        raise AssertionError("Red internal species order is incomplete") from None


def red_visible_living_specimens(
    party: PartyObservation,
    current_box: RedCurrentBoxState,
) -> tuple[LivingSpecimen, ...]:
    """Project the active party and currently loaded box into the shared contract.

    This deliberately says *visible*: the other eleven SRAM boxes are not
    inferred from Pokédex history. Full living-dex certification must enumerate
    each box through a later storage adapter before it can pass.
    """

    specimens = [
        LivingSpecimen(
            species_ref=red_species_ref(red_internal_species_number(member.species_id)),
            level=member.level,
            location=CollectionLocation.PARTY,
            slot_index=index,
        )
        for index, member in enumerate(party.members)
    ]
    specimens.extend(
        LivingSpecimen(
            species_ref=red_species_ref(red_internal_species_number(species_id)),
            level=level,
            location=CollectionLocation.BOX,
            container_index=current_box.box_index,
            slot_index=index,
        )
        for index, (species_id, level) in enumerate(
            zip(current_box.species_ids, current_box.levels, strict=True)
        )
    )
    return tuple(specimens)


def red_all_living_specimens(
    party: PartyObservation,
    collection: RedBoxCollectionState,
) -> tuple[LivingSpecimen, ...]:
    """Project the party and checksum-verified twelve-box census."""

    specimens = [
        LivingSpecimen(
            species_ref=red_species_ref(red_internal_species_number(member.species_id)),
            level=member.level,
            location=CollectionLocation.PARTY,
            slot_index=index,
        )
        for index, member in enumerate(party.members)
    ]
    for box in collection.boxes:
        specimens.extend(
            LivingSpecimen(
                species_ref=red_species_ref(red_internal_species_number(species_id)),
                level=level,
                location=CollectionLocation.BOX,
                container_index=box.box_index,
                slot_index=slot_index,
            )
            for slot_index, (species_id, level) in enumerate(
                zip(box.species_ids, box.levels, strict=True)
            )
        )
    return tuple(specimens)


def red_collection_observation(
    pokedex: RedPokedexState,
    party: PartyObservation,
    collection: RedBoxCollectionState,
) -> CollectionObservation:
    """Build the game-neutral global collection state from Red observations."""

    return CollectionObservation(
        owned_species=frozenset(red_species_ref(number) for number in pokedex.owned_species),
        specimens=red_all_living_specimens(party, collection),
        party_size=len(party.members),
        party_limit=6,
        box_counts=collection.counts,
        current_box_index=collection.current_box_index,
        box_capacity=20,
    )


def _exclusion(
    national_dex_number: int,
    reason: CollectionExclusionReason,
) -> CollectionExclusion:
    return CollectionExclusion(red_species_ref(national_dex_number), reason)


# Red-version absences shared with the lighter registration target.
_VERSION_EXCLUSIONS = tuple(sorted(UNAVAILABLE_IN_RED))
# These final evolutions require an external link trade in Generation I.
_LINK_EXCLUSIONS = (65, 68, 76, 94)
# The clean route's mutually exclusive choices. Earlier forms remain owned only
# when this save can actually retain a specimen alongside the chosen branch.
_ALTERNATE_STARTERS = (1, 2, 3, 4, 5, 6)
_ALTERNATE_FOSSIL = (140, 141)
_ALTERNATE_DOJO_GIFT = (107,)
_ALTERNATE_EEVEE_EVOLUTIONS = (134, 136)
_EVENT_ONLY = (151,)

RED_SOLO_EXCLUSIONS = tuple(
    sorted(
        (
            *(
                _exclusion(number, CollectionExclusionReason.VERSION_EXCLUSIVE)
                for number in _VERSION_EXCLUSIONS
            ),
            *(
                _exclusion(number, CollectionExclusionReason.LINK_TRADE_REQUIRED)
                for number in _LINK_EXCLUSIONS
            ),
            *(
                _exclusion(number, CollectionExclusionReason.ALTERNATE_STARTER)
                for number in _ALTERNATE_STARTERS
            ),
            *(
                _exclusion(number, CollectionExclusionReason.ALTERNATE_FOSSIL)
                for number in _ALTERNATE_FOSSIL
            ),
            *(
                _exclusion(number, CollectionExclusionReason.ALTERNATE_DOJO_GIFT)
                for number in _ALTERNATE_DOJO_GIFT
            ),
            *(
                _exclusion(number, CollectionExclusionReason.ALTERNATE_BRANCH_EVOLUTION)
                for number in _ALTERNATE_EEVEE_EVOLUTIONS
            ),
            *(_exclusion(number, CollectionExclusionReason.EVENT_ONLY) for number in _EVENT_ONLY),
        ),
        key=lambda item: red_species_number(item.species_ref),
    )
)

_EXCLUDED_REFS = frozenset(item.species_ref for item in RED_SOLO_EXCLUSIONS)
_CONSUMED_UNIQUE_FORM_NUMBERS = frozenset({7, 8, 133, 138})
RED_SOLO_COLLECTION_CONTRACT = CollectionContract(
    game_id=RED_COLLECTION_GAME_ID,
    species_universe=tuple(
        red_species_ref(number) for number in range(1, NATIONAL_DEX_SIZE_GENERATION_ONE + 1)
    ),
    target_species=tuple(
        red_species_ref(number)
        for number in range(1, NATIONAL_DEX_SIZE_GENERATION_ONE + 1)
        if red_species_ref(number) not in _EXCLUDED_REFS
    ),
    exclusions=RED_SOLO_EXCLUSIONS,
    living_target_species=tuple(
        red_species_ref(number)
        for number in range(1, NATIONAL_DEX_SIZE_GENERATION_ONE + 1)
        if red_species_ref(number) not in _EXCLUDED_REFS
        and number not in _CONSUMED_UNIQUE_FORM_NUMBERS
    ),
    target_level=100,
)

if len(RED_SOLO_COLLECTION_CONTRACT.target_species) != RED_SOLO_POKEDEX_TARGET_COUNT:
    raise AssertionError("Red solo Pokédex target must contain exactly 124 species")
if len(RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species) != RED_SOLO_LIVING_TARGET_COUNT:
    raise AssertionError("Red solo living target must contain exactly 120 coexisting species")


@dataclass(frozen=True, slots=True)
class RedPokedexProgress:
    """Pokédex-only progress toward the stricter living collection contract."""

    owned_target_numbers: tuple[int, ...]
    seen_target_numbers: tuple[int, ...]
    missing_target_numbers: tuple[int, ...]
    excluded_owned_numbers: tuple[int, ...]

    @property
    def target_count(self) -> int:
        return RED_SOLO_POKEDEX_TARGET_COUNT

    @property
    def owned_target_count(self) -> int:
        return len(self.owned_target_numbers)

    @property
    def pokedex_target_complete(self) -> bool:
        return not self.missing_target_numbers

    def public_dict(self) -> dict[str, object]:
        return {
            "contract": "red-solo-perfect-save-level-100-v2",
            "target": self.target_count,
            "owned": self.owned_target_count,
            "seen": len(self.seen_target_numbers),
            "missing": list(self.missing_target_numbers),
            "excluded_owned": list(self.excluded_owned_numbers),
            "pokedex_target_complete": self.pokedex_target_complete,
            "living_collection_verified": False,
            "level_100_collection_verified": False,
        }


@dataclass(frozen=True, slots=True)
class RedCollectionProgress:
    """Full Pokédex, living-storage, and level-cap progress for Red."""

    pokedex: RedPokedexProgress
    collection: CollectionReport
    box_counts: tuple[int, ...]
    current_box_index: int
    storage_initialized: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "contract": "red-solo-perfect-save-level-100-v2",
            "target": self.collection.target_count,
            "living_target": self.collection.living_target_count,
            "owned": self.collection.pokedex_owned_count,
            "seen": len(self.pokedex.seen_target_numbers),
            "living": self.collection.living_count,
            "level_100": self.collection.level_cap_count,
            "missing_owned": [
                red_species_number(species_ref) for species_ref in self.collection.missing_owned
            ],
            "missing_living": [
                red_species_number(species_ref) for species_ref in self.collection.missing_living
            ],
            "underleveled": [
                {
                    "national_dex_number": red_species_number(species_ref),
                    "level": level,
                }
                for species_ref, level in self.collection.underleveled
            ],
            "excluded_owned": list(self.pokedex.excluded_owned_numbers),
            "box_counts": list(self.box_counts),
            "current_box": self.current_box_index + 1,
            "storage_initialized": self.storage_initialized,
            "all_boxes_verified": True,
            "pokedex_target_complete": not self.collection.missing_owned,
            "living_collection_verified": not self.collection.missing_living,
            "level_100_collection_verified": self.collection.passed,
        }


def summarize_red_pokedex(state: RedPokedexState) -> RedPokedexProgress:
    """Project Red's flags onto the 124-species single-save target denominator."""

    target_numbers = tuple(
        red_species_number(species_ref)
        for species_ref in RED_SOLO_COLLECTION_CONTRACT.target_species
    )
    target_set = set(target_numbers)
    return RedPokedexProgress(
        owned_target_numbers=tuple(
            number for number in target_numbers if number in state.owned_species
        ),
        seen_target_numbers=tuple(
            number for number in target_numbers if number in state.seen_species
        ),
        missing_target_numbers=tuple(
            number for number in target_numbers if number not in state.owned_species
        ),
        excluded_owned_numbers=tuple(sorted(state.owned_species - target_set)),
    )


def summarize_red_collection(
    pokedex: RedPokedexState,
    party: PartyObservation,
    boxes: RedBoxCollectionState,
) -> RedCollectionProgress:
    """Evaluate all three Red completionist gates from one coherent census."""

    observation = red_collection_observation(pokedex, party, boxes)
    return RedCollectionProgress(
        pokedex=summarize_red_pokedex(pokedex),
        collection=summarize_collection(RED_SOLO_COLLECTION_CONTRACT, observation),
        box_counts=boxes.counts,
        current_box_index=boxes.current_box_index,
        storage_initialized=boxes.storage_initialized,
    )
