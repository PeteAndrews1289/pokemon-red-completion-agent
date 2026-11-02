"""Conservative native admission for helpers that must not evolve incidentally.

This is execution support, never a policy feature or an XP outcome prediction.
The default callers still exclude every level-evolving helper.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256

from .observation import ItemId
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_team_training import EvolutionTrainingPaused
from .red_trainer_evolution import level_evolution_edges

_CANONICAL_RED_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def ordinary_red_xp_upper_bound(base_experience: int, level: int) -> int:
    """Bound one award for every legal participant count and either OT equality.

    Canonical Gen I divides base XP by participants before multiplication/div7,
    then applies at most the traded and trainer floor1.5 boosts. Omitting the
    participant division and applying both boosts is conservative for wilds.
    EXP.ALL's separate distribution passes are deliberately outside this proof.
    See the existing red_party_development_adapter cartridge XP projection and
    https://github.com/pret/pokered/blob/master/engine/battle/experience.asm.
    """
    if (
        type(base_experience) is not int
        or not 1 <= base_experience <= 255
        or type(level) is not int
        or not 1 <= level <= 100
    ):
        raise ValueError("ordinary Red XP bound requires known cartridge facts")
    amount = base_experience * level // 7
    for _ in range(2):
        amount += amount // 2
    return amount


_MAXIMUM_SINGLE_AWARD = ordinary_red_xp_upper_bound(255, 100)
_QUALIFIED_ROM = object()


class EvolutionHelperXPExhausted(EvolutionTrainingPaused):
    """Productive safe pause at a known no-incidental-evolution boundary."""

    def __init__(self, battles, healing_trips, blocked_helpers):
        if (
            not isinstance(blocked_helpers, frozenset)
            or not blocked_helpers
            or any(type(s) is not int or not 1 <= s <= 255 for s in blocked_helpers)
        ):
            raise ValueError("headroom pause requires known blocked helper species")
        super().__init__(battles, healing_trips)
        self.blocked_helpers = blocked_helpers


@dataclass(frozen=True, slots=True)
class EvolutionHelperXPGuard:
    """Immutable pinned-cartridge floors; fresh native XP is checked every time."""

    # (internal species, next evolution level, XP floors for levels1..100)
    species_facts: tuple[tuple[int, int, tuple[int, ...]], ...]
    known_species: frozenset[int]
    excluded_species: frozenset[int]
    _qualification_token: object = field(default=None, repr=False, compare=False)

    def require_scope(self, excluded_species):
        if (
            self._qualification_token is not _QUALIFIED_ROM
            or self.excluded_species != excluded_species
        ):
            raise ValueError("helper XP guard lacks its exact cartridge exclusions")

    @classmethod
    @lru_cache(maxsize=1)
    def from_rom(cls, rom: bytes, excluded_species: frozenset[int]):
        if sha256(rom).hexdigest() != _CANONICAL_RED_SHA256:
            raise ValueError("certified helper XP requires the canonical Red engine")
        cartridge = RedPracticeCartridge(rom)
        edges = level_evolution_edges(rom)
        levels: dict[int, int] = {}
        for source, _target, level in edges:
            levels[source] = min(level, levels.get(source, level))
        if excluded_species != frozenset(levels):
            raise ValueError("certified helper exclusions differ from cartridge evolutions")
        return cls(
            tuple(
                (
                    species,
                    levels[species],
                    tuple(
                        cartridge.species(species).experience_at_level(level)
                        for level in range(1, 101)
                    ),
                )
                for species in sorted(levels)
            ),
            frozenset(cartridge.species_ids),
            excluded_species,
            _QUALIFIED_ROM,
        )

    def _environment_supported(self, raw) -> bool:
        """Unknown inventory or engine observations never get a headroom certificate."""
        bag = getattr(raw, "bag_items", None)
        battle = getattr(raw, "battle_state", None)
        if battle not in (0, 1) or type(battle) is not int or bag is None:
            return False
        try:
            if (
                any(
                    type(item) is not int
                    or type(quantity) is not int
                    or not 1 <= item <= 255
                    or not 1 <= quantity <= 99
                    for item, quantity in bag
                )
                or len(dict(bag)) != len(bag)
                or dict(bag).get(int(ItemId.EXP_ALL), 0)
            ):
                return False
        except (TypeError, ValueError):
            return False
        return not (
            battle == 1
            and (
                type(getattr(raw, "enemy_species_id", None)) is not int
                or raw.enemy_species_id not in self.known_species
                or type(getattr(raw, "enemy_level", None)) is not int
                or not 1 <= raw.enemy_level <= 100
            )
        )

    def _classification(self, party, raw):
        if not self._environment_supported(raw):
            return frozenset(), frozenset()
        facts = {species: (level, floors) for species, level, floors in self.species_facts}
        allowed, invalid, exhausted = set(), set(), set()
        for member in party.members:
            species, level, experience = (
                member.species_id,
                member.level,
                member.experience,
            )
            if species not in facts:
                continue
            if type(level) is not int or type(experience) is not int:
                invalid.add(species)
                continue
            evolution_level, floors = facts[species]
            if (
                not 1 <= level < evolution_level <= 100
                or not floors[level - 1] <= experience < floors[level]
            ):
                invalid.add(species)
                continue
            if experience + _MAXIMUM_SINGLE_AWARD < floors[evolution_level - 1]:
                allowed.add(species)
            else:
                exhausted.add(species)
        return (
            frozenset(allowed - invalid - exhausted),
            frozenset(exhausted - invalid),
        )

    def exclusions(self, party, raw) -> frozenset[int]:
        """Enforce the unchanged strict safety bound for actual execution."""
        allowed, _ = self._classification(party, raw)
        return self.excluded_species - allowed

    def headroom_exhausted_species(self, party, raw) -> frozenset[int]:
        """Diagnostic ONLY: known valid XP blocked solely by the headroom bound."""
        self.require_scope(self.excluded_species)
        _, exhausted = self._classification(party, raw)
        return exhausted
