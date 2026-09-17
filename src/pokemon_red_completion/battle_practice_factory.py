"""Title-neutral request for teacher-assisted, isolated battle practice.

This describes initial conditions, never a player action. Title adapters may
support only a subset of possible conditions and must reject unsupported keys.
All variants from one source retain that source's upstream lineage identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .provenance import canonical_sha256
from .scenario_lab import ScenarioPartition

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")


class BattlePracticeError(ValueError):
    """An assisted condition is unsupported or cannot be authenticated."""


@dataclass(frozen=True, slots=True)
class PracticeMove:
    move_ref: str
    pp: int

    def __post_init__(self) -> None:
        if not isinstance(self.move_ref, str) or not self.move_ref:
            raise BattlePracticeError("practice move needs a nonempty semantic reference")
        if type(self.pp) is not int or not 1 <= self.pp <= 63:  # noqa: E721
            raise BattlePracticeError("practice move PP must be 1..63")


@dataclass(frozen=True, slots=True)
class PracticeStats:
    max_hp: int
    attack: int
    defense: int
    speed: int
    special: int

    def __post_init__(self) -> None:
        for name in ("max_hp", "attack", "defense", "speed", "special"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 999:  # noqa: E721
                raise BattlePracticeError(f"practice {name} must be 1..999")

    @classmethod
    def from_dict(cls, value: object) -> PracticeStats:
        fields = {"max_hp", "attack", "defense", "speed", "special"}
        if not isinstance(value, dict) or set(value) != fields:
            raise BattlePracticeError("practice stats need all five declared fields")
        return cls(**value)

    def public_dict(self) -> dict[str, int]:
        return {
            name: getattr(self, name)
            for name in ("max_hp", "attack", "defense", "speed", "special")
        }


@dataclass(frozen=True, slots=True)
class PracticeReserve:
    party_slot: int  # one-based, matching the in-game party display
    species_ref: str
    level: int
    moves: tuple[PracticeMove, ...]
    hp: int | None = None
    stats: PracticeStats | None = None

    def __post_init__(self) -> None:
        if type(self.party_slot) is not int or not 1 <= self.party_slot <= 6:  # noqa: E721
            raise BattlePracticeError("reserve party slot must be 1..6")
        if not isinstance(self.species_ref, str) or not self.species_ref:
            raise BattlePracticeError("reserve species reference differs")
        if type(self.level) is not int or not 1 <= self.level <= 100:  # noqa: E721
            raise BattlePracticeError("reserve level must be 1..100")
        if (
            not isinstance(self.moves, tuple)
            or not 1 <= len(self.moves) <= 4
            or any(not isinstance(move, PracticeMove) for move in self.moves)
            or len({move.move_ref for move in self.moves}) != len(self.moves)
        ):
            raise BattlePracticeError("reserve moves must be one to four distinct moves")
        if self.hp is not None and (type(self.hp) is not int or self.hp <= 0):  # noqa: E721
            raise BattlePracticeError("reserve HP must be positive")
        if self.stats is not None and not isinstance(self.stats, PracticeStats):
            raise BattlePracticeError("reserve stats differ")
        if self.hp is not None and self.stats is not None and self.hp > self.stats.max_hp:
            raise BattlePracticeError("reserve HP exceeds declared maximum")

    @classmethod
    def from_dict(cls, value: object) -> PracticeReserve:
        required = {"party_slot", "species_ref", "level", "moves"}
        if (
            not isinstance(value, dict)
            or not required <= set(value)
            or set(value) - required - {"hp", "stats"}
        ):
            raise BattlePracticeError("reserve record differs")
        moves = value["moves"]
        if not isinstance(moves, list) or any(
            not isinstance(move, dict) or set(move) != {"move_ref", "pp"} for move in moves
        ):
            raise BattlePracticeError("reserve move records differ")
        return cls(
            party_slot=value["party_slot"],
            species_ref=value["species_ref"],
            level=value["level"],
            moves=tuple(PracticeMove(**move) for move in moves),
            hp=value.get("hp"),
            stats=PracticeStats.from_dict(value["stats"])
            if value.get("stats") is not None
            else None,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "party_slot": self.party_slot,
            "species_ref": self.species_ref,
            "level": self.level,
            "moves": [{"move_ref": move.move_ref, "pp": move.pp} for move in self.moves],
            "hp": self.hp,
            "stats": self.stats.public_dict() if self.stats else None,
        }


@dataclass(frozen=True, slots=True)
class BattlePracticeSpec:
    source_state_sha256: str
    root_lineage_id: str
    partition: ScenarioPartition
    actor_moves: tuple[PracticeMove, ...]
    opponent_hp: int
    actor_level: int | None = None
    opponent_level: int | None = None
    actor_stats: PracticeStats | None = None
    opponent_stats: PracticeStats | None = None
    actor_hp: int | None = None
    actor_species_ref: str | None = None
    opponent_species_ref: str | None = None
    opponent_moves: tuple[PracticeMove, ...] | None = None
    party_reserves: tuple[PracticeReserve, ...] | None = None
    battle_kind: str = "wild"
    opponent_party_count: int | None = None
    opponent_reserves: tuple[PracticeReserve, ...] | None = None

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.source_state_sha256) is None:
            raise BattlePracticeError("practice source state hash differs")
        if _SAFE_ID.fullmatch(self.root_lineage_id) is None:
            raise BattlePracticeError("practice root lineage differs")
        if self.partition is not ScenarioPartition.TRAIN:
            raise BattlePracticeError("first practice factory is train-only")
        if (
            not isinstance(self.actor_moves, tuple)
            or not 2 <= len(self.actor_moves) <= 4
            or any(not isinstance(move, PracticeMove) for move in self.actor_moves)
        ):
            raise BattlePracticeError("practice needs two to four declared moves")
        if len({move.move_ref for move in self.actor_moves}) != len(self.actor_moves):
            raise BattlePracticeError("practice moves must be distinct alternatives")
        if type(self.opponent_hp) is not int or self.opponent_hp <= 0:  # noqa: E721
            raise BattlePracticeError("practice opponent HP must be positive")
        for name in ("actor_level", "opponent_level"):
            level = getattr(self, name)
            if level is not None and (type(level) is not int or not 1 <= level <= 100):  # noqa: E721
                raise BattlePracticeError(f"practice {name} must be 1..100")
        for name in ("actor_stats", "opponent_stats"):
            stats = getattr(self, name)
            if stats is not None and not isinstance(stats, PracticeStats):
                raise BattlePracticeError(f"practice {name} differs")
        if self.actor_hp is not None and (type(self.actor_hp) is not int or self.actor_hp <= 0):  # noqa: E721
            raise BattlePracticeError("practice actor HP must be positive")
        if (
            self.actor_stats is not None
            and self.actor_hp is not None
            and self.actor_hp > self.actor_stats.max_hp
        ):
            raise BattlePracticeError("practice actor HP exceeds declared maximum")
        if self.opponent_stats is not None and self.opponent_hp > self.opponent_stats.max_hp:
            raise BattlePracticeError("practice opponent HP exceeds declared maximum")
        for name in ("actor_species_ref", "opponent_species_ref"):
            ref = getattr(self, name)
            if ref is not None and (not isinstance(ref, str) or not ref):
                raise BattlePracticeError(f"practice {name} differs")
        if self.opponent_moves is not None and (
            not isinstance(self.opponent_moves, tuple)
            or not 1 <= len(self.opponent_moves) <= 4
            or any(not isinstance(move, PracticeMove) for move in self.opponent_moves)
            or len({move.move_ref for move in self.opponent_moves}) != len(self.opponent_moves)
        ):
            raise BattlePracticeError("practice opponent moves must be one to four distinct moves")
        if self.party_reserves is not None and (
            not isinstance(self.party_reserves, tuple)
            or not 1 <= len(self.party_reserves) <= 5
            or any(not isinstance(reserve, PracticeReserve) for reserve in self.party_reserves)
            or len({reserve.party_slot for reserve in self.party_reserves})
            != len(self.party_reserves)
        ):
            raise BattlePracticeError("practice reserves must occupy one to five distinct slots")
        if self.battle_kind not in {"wild", "trainer"}:
            raise BattlePracticeError("practice battle kind must be wild or trainer")
        if self.battle_kind == "wild":
            if self.opponent_party_count is not None or self.opponent_reserves is not None:
                raise BattlePracticeError("wild practice cannot declare an opponent party")
        else:
            if (
                type(self.opponent_party_count) is not int  # noqa: E721
                or not 1 <= self.opponent_party_count <= 6
            ):
                raise BattlePracticeError("trainer practice party count must be 1..6")
            if (
                self.opponent_species_ref is None
                or self.opponent_level is None
                or self.opponent_moves is None
            ):
                raise BattlePracticeError("trainer practice needs an explicit active opponent")
            if self.opponent_reserves is not None and (
                not isinstance(self.opponent_reserves, tuple)
                or not 1 <= len(self.opponent_reserves) <= 5
                or any(not isinstance(item, PracticeReserve) for item in self.opponent_reserves)
                or len({item.party_slot for item in self.opponent_reserves})
                != len(self.opponent_reserves)
                or any(
                    item.party_slot > self.opponent_party_count for item in self.opponent_reserves
                )
            ):
                raise BattlePracticeError("trainer practice opponent reserves differ")

    @classmethod
    def from_dict(cls, value: object) -> BattlePracticeSpec:
        """Fail closed when a caller requests an axis this adapter cannot set."""

        required = {
            "source_state_sha256",
            "root_lineage_id",
            "partition",
            "actor_moves",
            "opponent_hp",
        }
        optional = {
            "actor_level",
            "opponent_level",
            "actor_stats",
            "opponent_stats",
            "actor_hp",
            "actor_species_ref",
            "opponent_species_ref",
            "opponent_moves",
            "party_reserves",
            "battle_kind",
            "opponent_party_count",
            "opponent_reserves",
        }
        if (
            not isinstance(value, dict)
            or not required <= set(value)
            or set(value) - required - optional
        ):
            raise BattlePracticeError("unsupported or missing practice condition")
        moves = value["actor_moves"]
        if not isinstance(moves, list) or any(
            not isinstance(move, dict) or set(move) != {"move_ref", "pp"} for move in moves
        ):
            raise BattlePracticeError("practice move records differ")
        opponent_moves = value.get("opponent_moves")
        if opponent_moves is not None and (
            not isinstance(opponent_moves, list)
            or any(
                not isinstance(move, dict) or set(move) != {"move_ref", "pp"}
                for move in opponent_moves
            )
        ):
            raise BattlePracticeError("practice opponent move records differ")
        party_reserves = value.get("party_reserves")
        if party_reserves is not None and not isinstance(party_reserves, list):
            raise BattlePracticeError("practice reserve records differ")
        opponent_reserves = value.get("opponent_reserves")
        if opponent_reserves is not None and not isinstance(opponent_reserves, list):
            raise BattlePracticeError("practice opponent reserve records differ")
        try:
            partition = ScenarioPartition(value["partition"])
            return cls(
                source_state_sha256=value["source_state_sha256"],
                root_lineage_id=value["root_lineage_id"],
                partition=partition,
                actor_moves=tuple(
                    PracticeMove(move_ref=move["move_ref"], pp=move["pp"]) for move in moves
                ),
                opponent_hp=value["opponent_hp"],
                actor_level=value.get("actor_level"),
                opponent_level=value.get("opponent_level"),
                actor_stats=(
                    PracticeStats.from_dict(value["actor_stats"])
                    if value.get("actor_stats") is not None
                    else None
                ),
                opponent_stats=(
                    PracticeStats.from_dict(value["opponent_stats"])
                    if value.get("opponent_stats") is not None
                    else None
                ),
                actor_hp=value.get("actor_hp"),
                actor_species_ref=value.get("actor_species_ref"),
                opponent_species_ref=value.get("opponent_species_ref"),
                opponent_moves=(
                    tuple(
                        PracticeMove(move_ref=move["move_ref"], pp=move["pp"])
                        for move in opponent_moves
                    )
                    if opponent_moves is not None
                    else None
                ),
                party_reserves=(
                    tuple(PracticeReserve.from_dict(reserve) for reserve in party_reserves)
                    if party_reserves is not None
                    else None
                ),
                battle_kind=value.get("battle_kind", "wild"),
                opponent_party_count=value.get("opponent_party_count"),
                opponent_reserves=(
                    tuple(PracticeReserve.from_dict(reserve) for reserve in opponent_reserves)
                    if opponent_reserves is not None
                    else None
                ),
            )
        except (TypeError, ValueError, KeyError) as error:
            raise BattlePracticeError(f"invalid practice condition: {error}") from error

    @property
    def configuration_sha256(self) -> str:
        configuration: dict[str, object] = {
            "schema": "pokemon.core.battle-practice-configuration.v1",
            "source_state_sha256": self.source_state_sha256,
            "root_lineage_id": self.root_lineage_id,
            "partition": self.partition.value,
            "actor_moves": [
                {"move_ref": move.move_ref, "pp": move.pp} for move in self.actor_moves
            ],
            "opponent_hp": self.opponent_hp,
        }
        if any(
            value is not None
            for value in (
                self.actor_level,
                self.opponent_level,
                self.actor_stats,
                self.opponent_stats,
                self.actor_hp,
            )
        ):
            configuration["schema"] = "pokemon.core.battle-practice-configuration.v2"
            configuration.update(
                actor_level=self.actor_level,
                opponent_level=self.opponent_level,
                actor_stats=self.actor_stats.public_dict() if self.actor_stats else None,
                opponent_stats=self.opponent_stats.public_dict() if self.opponent_stats else None,
                actor_hp=self.actor_hp,
            )
        if any(
            value is not None
            for value in (
                self.actor_species_ref,
                self.opponent_species_ref,
                self.opponent_moves,
            )
        ):
            configuration["schema"] = "pokemon.core.battle-practice-configuration.v3"
            configuration.update(
                actor_species_ref=self.actor_species_ref,
                opponent_species_ref=self.opponent_species_ref,
                opponent_moves=(
                    [{"move_ref": move.move_ref, "pp": move.pp} for move in self.opponent_moves]
                    if self.opponent_moves is not None
                    else None
                ),
            )
        if self.party_reserves is not None:
            configuration["schema"] = "pokemon.core.battle-practice-configuration.v4"
            configuration["party_reserves"] = [
                reserve.public_dict() for reserve in self.party_reserves
            ]
        if self.battle_kind == "trainer":
            configuration["schema"] = "pokemon.core.battle-practice-configuration.v5"
            configuration.update(
                battle_kind=self.battle_kind,
                opponent_party_count=self.opponent_party_count,
                opponent_reserves=(
                    [reserve.public_dict() for reserve in self.opponent_reserves]
                    if self.opponent_reserves is not None
                    else None
                ),
            )
        return canonical_sha256(configuration)
