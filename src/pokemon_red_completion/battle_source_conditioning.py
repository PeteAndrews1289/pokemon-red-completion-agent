"""Title-neutral contract for conditioning a battle source without changing identity.

Conditioning is not teaching and does not create a learning example.  It may
restore expendable battle resources so that a later authenticated scenario has
more than one real action, while the party facts that define the upstream
decision context remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass


class BattleSourceConditioningError(ValueError):
    """Raised when resource restoration changes the source's semantic identity."""


@dataclass(frozen=True, slots=True)
class BattlePartyMemberIdentity:
    """Portable party facts a resource-only operation may not change."""

    species_ref: str
    level: int
    move_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.species_ref or not isinstance(self.species_ref, str):
            raise BattleSourceConditioningError("party identity needs a species reference")
        if type(self.level) is not int or not 1 <= self.level <= 100:  # noqa: E721
            raise BattleSourceConditioningError("party identity has an invalid level")
        if (
            not isinstance(self.move_refs, tuple)
            or not self.move_refs
            or any(not isinstance(ref, str) or not ref for ref in self.move_refs)
        ):
            raise BattleSourceConditioningError("party identity needs learned move references")


@dataclass(frozen=True, slots=True)
class BattlePartyIdentity:
    """Ordered party identity shared by title adapters."""

    members: tuple[BattlePartyMemberIdentity, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.members, tuple) or not 1 <= len(self.members) <= 6:
            raise BattleSourceConditioningError("party identity needs one to six members")


@dataclass(frozen=True, slots=True)
class BattleSourceConditioningContract:
    """One bounded operation that may restore resources but not teach choices."""

    operation: str = "restore_battle_resources"
    minimum_supported_actions: int = 2
    preserves_party_order: bool = True
    preserves_species: bool = True
    preserves_levels: bool = True
    preserves_moves: bool = True
    permits_hp_restoration: bool = True
    permits_status_cure: bool = True
    permits_pp_restoration: bool = True

    def __post_init__(self) -> None:
        if self.operation != "restore_battle_resources":
            raise BattleSourceConditioningError("unsupported battle source conditioning operation")
        if self.minimum_supported_actions < 2:
            raise BattleSourceConditioningError(
                "conditioning cannot turn a forced singleton into a learning decision"
            )
        if not all(
            (
                self.preserves_party_order,
                self.preserves_species,
                self.preserves_levels,
                self.preserves_moves,
                self.permits_hp_restoration,
                self.permits_status_cure,
                self.permits_pp_restoration,
            )
        ):
            raise BattleSourceConditioningError(
                "battle resource conditioning contract cannot weaken its identity boundary"
            )

    def require_identity_preserved(
        self,
        before: BattlePartyIdentity,
        after: BattlePartyIdentity,
    ) -> None:
        """Reject any restoration that changed party order, species, level, or moves."""

        if before != after:
            raise BattleSourceConditioningError(
                "battle resource restoration changed the upstream party identity"
            )


BATTLE_RESOURCE_CONDITIONING_V1 = BattleSourceConditioningContract()


__all__ = [
    "BATTLE_RESOURCE_CONDITIONING_V1",
    "BattlePartyIdentity",
    "BattlePartyMemberIdentity",
    "BattleSourceConditioningContract",
    "BattleSourceConditioningError",
]
