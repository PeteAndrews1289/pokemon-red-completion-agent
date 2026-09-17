"""Pinned Red cartridge facts for teacher-only battle construction.

The 150 ordinary base-stat rows and Mew's separate row are read from the ROM,
not copied into the model or a hand-maintained species table.  Starting moves,
level-up rows and TM/HM compatibility are different sources of availability;
evolution-inherited and event-only moves are not claimed by this catalog.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .battle_practice_factory import BattlePracticeError, PracticeStats
from .gen1_cartridge import internal_to_dex, level_up_learnsets
from .observation import GEN1_TYPE_NAMES_BY_CODE
from .red_battle_catalog import PokemonRedBattleCatalog, pokemon_red_species_ref

_BASE_STATS_OFFSET = 0x383DE
_MEW_BASE_STATS_OFFSET = 0x425B
_BASE_ROW_SIZE = 28
_INTERNAL_NAMES_OFFSET = 0x1C21E
_INTERNAL_NAME_SIZE = 10
_TMHM_MOVES = (
    5,
    13,
    14,
    18,
    25,
    92,
    32,
    34,
    36,
    38,
    61,
    55,
    58,
    59,
    63,
    6,
    66,
    68,
    69,
    99,
    72,
    76,
    82,
    85,
    87,
    89,
    90,
    91,
    94,
    100,
    102,
    104,
    115,
    117,
    118,
    120,
    121,
    126,
    129,
    130,
    135,
    138,
    143,
    156,
    86,
    149,
    153,
    157,
    161,
    164,
    15,
    19,
    57,
    70,
    148,
)


@dataclass(frozen=True, slots=True)
class RedPracticeSpecies:
    internal_id: int
    national_number: int
    types: tuple[int, int]
    base_stats: tuple[int, int, int, int, int]
    catch_rate: int
    base_experience: int
    growth_code: int
    starting_moves: tuple[int, ...]
    level_up_moves: tuple[tuple[int, int], ...]
    tmhm_moves: tuple[int, ...]
    nickname_bytes: bytes

    def intrinsic_moves_at_level(self, level: int) -> tuple[int, ...]:
        """Starting plus own level-up moves, not evolution-inherited or TM moves."""

        if type(level) is not int or not 1 <= level <= 100:  # noqa: E721
            raise BattlePracticeError("practice species level must be 1..100")
        return tuple(
            dict.fromkeys(
                (*self.starting_moves, *(move for at, move in self.level_up_moves if at <= level))
            )
        )

    def teachable_moves_at_level(self, level: int) -> tuple[int, ...]:
        """Own intrinsic moves plus compatible TMs/HMs; availability is not ownership."""

        return tuple(dict.fromkeys((*self.intrinsic_moves_at_level(level), *self.tmhm_moves)))

    def neutral_stats(self, level: int, *, dv: int = 8) -> PracticeStats:
        """Deterministic zero-stat-exp starter for a species and level.

        This is a training convenience, not a claim about a wild specimen's DVs.
        Explicit stat overrides remain available for adversarial scenarios.
        """

        if type(level) is not int or not 1 <= level <= 100:  # noqa: E721
            raise BattlePracticeError("practice species level must be 1..100")
        if type(dv) is not int or not 0 <= dv <= 15:  # noqa: E721
            raise BattlePracticeError("practice DV must be 0..15")
        return self.stats_with_dvs(level, (dv, dv, dv, dv))

    def trainer_stats(self, level: int) -> PracticeStats:
        """Native Red trainer DVs: $98 attack/defense, $88 speed/special."""

        return self.stats_with_dvs(level, (9, 8, 8, 8))

    def stats_with_dvs(self, level: int, dvs: tuple[int, int, int, int]) -> PracticeStats:
        """Gen I's zero-stat-exp formula, including the derived HP DV."""

        if type(level) is not int or not 1 <= level <= 100:  # noqa: E721
            raise BattlePracticeError("practice species level must be 1..100")
        if len(dvs) != 4 or any(type(dv) is not int or not 0 <= dv <= 15 for dv in dvs):
            raise BattlePracticeError("practice DVs must be four nibbles")
        hp, attack, defense, speed, special = self.base_stats
        hp_dv = sum((dv & 1) << shift for dv, shift in zip(dvs, (3, 2, 1, 0), strict=True))
        return PracticeStats(
            max_hp=((2 * (hp + hp_dv)) * level) // 100 + level + 10,
            attack=((2 * (attack + dvs[0])) * level) // 100 + 5,
            defense=((2 * (defense + dvs[1])) * level) // 100 + 5,
            speed=((2 * (speed + dvs[2])) * level) // 100 + 5,
            special=((2 * (special + dvs[3])) * level) // 100 + 5,
        )

    def experience_at_level(self, level: int) -> int:
        """Experience floor from Red's six pinned growth-rate polynomials."""

        if type(level) is not int or not 1 <= level <= 100:  # noqa: E721
            raise BattlePracticeError("practice species level must be 1..100")
        cubic = level**3
        quadratic = level**2
        formulas = (
            cubic,
            3 * cubic // 4 + 10 * quadratic - 30,
            3 * cubic // 4 + 20 * quadratic - 70,
            6 * cubic // 5 - 15 * quadratic + 100 * level - 140,
            4 * cubic // 5,
            5 * cubic // 4,
        )
        if not 0 <= self.growth_code < len(formulas):
            raise BattlePracticeError("Red practice growth code differs")
        return max(0, formulas[self.growth_code])


class RedPracticeCartridge:
    """All 151 Red species and their cartridge-backed move sources."""

    def __init__(self, rom: bytes) -> None:
        if not isinstance(rom, bytes) or len(rom) < 0x40000:
            raise BattlePracticeError("Red practice cartridge differs")
        mapping = internal_to_dex(rom)
        learnsets = level_up_learnsets(rom)
        catalog = PokemonRedBattleCatalog()
        if set(mapping) != set(catalog.species_ids):
            raise BattlePracticeError("Red practice species catalog differs")
        species: dict[int, RedPracticeSpecies] = {}
        for internal_id, national_number in mapping.items():
            offset = (
                _MEW_BASE_STATS_OFFSET
                if national_number == 151
                else _BASE_STATS_OFFSET + (national_number - 1) * _BASE_ROW_SIZE
            )
            row = rom[offset : offset + _BASE_ROW_SIZE]
            if len(row) != _BASE_ROW_SIZE or row[0] != national_number:
                raise BattlePracticeError("Red practice base-stat table differs")
            types = (row[6], row[7])
            try:
                type_names = tuple(dict.fromkeys(GEN1_TYPE_NAMES_BY_CODE[code] for code in types))
            except KeyError as error:
                raise BattlePracticeError("Red practice type byte differs") from error
            if type_names != catalog.resolve_species(pokemon_red_species_ref(internal_id)).types:
                raise BattlePracticeError("Red practice species types differ from pinned catalog")
            starting = tuple(move for move in row[15:19] if move)
            if any(move not in catalog.move_ids for move in starting):
                raise BattlePracticeError("Red practice starting move differs")
            if row[19] > 5:
                raise BattlePracticeError("Red practice growth code differs")
            tmhm = tuple(
                move
                for index, move in enumerate(_TMHM_MOVES)
                if row[20 + index // 8] & (1 << (index % 8))
            )
            name_at = _INTERNAL_NAMES_OFFSET + (internal_id - 1) * _INTERNAL_NAME_SIZE
            name = rom[name_at : name_at + _INTERNAL_NAME_SIZE]
            if len(name) != _INTERNAL_NAME_SIZE or not name or name[0] in {0, 0x50}:
                raise BattlePracticeError("Red practice species name table differs")
            species[internal_id] = RedPracticeSpecies(
                internal_id=internal_id,
                national_number=national_number,
                types=types,
                base_stats=(row[1], row[2], row[3], row[4], row[5]),
                catch_rate=row[8],
                base_experience=row[9],
                growth_code=row[19],
                starting_moves=starting,
                level_up_moves=learnsets[national_number],
                tmhm_moves=tmhm,
                nickname_bytes=name + b"\x50",
            )
        if len(species) != 151:
            raise BattlePracticeError("Red practice cartridge lacks 151 species")
        self._species = species

    @property
    def species_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._species))

    @property
    def public_base_stats(self) -> Mapping[int, tuple[int, int, int, int, int]]:
        """Public species mechanics, not specimen DVs or trainer reserve state."""

        return MappingProxyType(
            {identifier: species.base_stats for identifier, species in self._species.items()}
        )

    def species(self, internal_id: int) -> RedPracticeSpecies:
        try:
            return self._species[internal_id]
        except KeyError as error:
            raise BattlePracticeError("unknown Red practice species") from error
