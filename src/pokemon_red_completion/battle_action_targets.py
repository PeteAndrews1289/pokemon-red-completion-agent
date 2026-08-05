"""Game-neutral target resolution for high-level battle actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind


class BattleActionTargetError(ValueError):
    """Raised when a semantic observation cannot supply a legal action target."""


class RecoveryNeed(StrEnum):
    """Transferable effect needed from a recovery action."""

    HP = "hp"
    STATUS = "status"
    HP_AND_STATUS = "hp_and_status"


@dataclass(frozen=True, slots=True)
class ResolvedBattleAction:
    """A high-level action plus its game-neutral party/effect target."""

    action: BattleAction
    party_slot: int | None = None
    recovery_need: RecoveryNeed | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, BattleAction):
            raise TypeError("action must be a BattleAction")
        if self.action.kind is BattleActionKind.USE_RECOVERY:
            if self.party_slot is None or self.recovery_need is None:
                raise ValueError("recovery actions require a party slot and recovery need")
        elif self.action.kind is BattleActionKind.SWITCH:
            if self.party_slot is None or self.recovery_need is not None:
                raise ValueError("switch actions require only a party slot")
        elif self.party_slot is not None or self.recovery_need is not None:
            raise ValueError("this action kind does not accept a target")
        if self.party_slot is not None and not 1 <= self.party_slot <= 6:
            raise ValueError("party_slot must be one-based and between one and six")

    def public_dict(self) -> dict[str, object]:
        return {
            "action": self.action.public_dict(),
            "party_slot": self.party_slot,
            "recovery_need": (self.recovery_need.value if self.recovery_need is not None else None),
        }


def resolve_battle_action_target(
    action: BattleAction,
    observation: Mapping[str, object],
) -> ResolvedBattleAction:
    """Resolve legal targets using only the portable semantic observation."""

    if not isinstance(action, BattleAction):
        raise TypeError("action must be a BattleAction")
    if not isinstance(observation, Mapping):
        raise TypeError("observation must be a mapping")
    if action.kind not in {BattleActionKind.USE_RECOVERY, BattleActionKind.SWITCH}:
        return ResolvedBattleAction(action)

    features = _mapping(observation.get("features"), "features")
    party = _mapping(features.get("party"), "party")
    members_value = party.get("members")
    members = (
        tuple(_mapping(value, "party member") for value in members_value)
        if isinstance(members_value, Sequence) and not isinstance(members_value, (str, bytes))
        else ()
    )
    active_index = _active_index(party, members)

    if action.kind is BattleActionKind.USE_RECOVERY:
        active = members[active_index] if members else _mapping(party.get("lead"), "party lead")
        hp = _nonnegative_int(active.get("hp"), "active hp")
        max_hp = _positive_int(active.get("max_hp"), "active max hp")
        if hp > max_hp:
            raise BattleActionTargetError("active hp exceeds maximum hp")
        has_status = active.get("status") is not None
        needs_hp = hp < max_hp
        if not needs_hp and not has_status:
            raise BattleActionTargetError("recovery has no observable effect target")
        need = (
            RecoveryNeed.HP_AND_STATUS
            if needs_hp and has_status
            else RecoveryNeed.HP
            if needs_hp
            else RecoveryNeed.STATUS
        )
        return ResolvedBattleAction(
            action,
            party_slot=active_index + 1,
            recovery_need=need,
        )

    if not members:
        raise BattleActionTargetError("party members are unavailable for switching")

    requested_index = action.party_slot - 1 if action.party_slot is not None else None
    if requested_index is not None:
        if requested_index >= len(members):
            raise BattleActionTargetError("requested switch target is absent")
        if requested_index == active_index:
            raise BattleActionTargetError("requested switch target is already active")
        if _nonnegative_int(members[requested_index].get("hp"), "target hp") == 0:
            raise BattleActionTargetError("requested switch target has fainted")
        return ResolvedBattleAction(action, party_slot=requested_index + 1)

    candidates: list[tuple[float, int, int, int]] = []
    for index, member in enumerate(members):
        if index == active_index:
            continue
        hp = _nonnegative_int(member.get("hp"), "party hp")
        max_hp = _positive_int(member.get("max_hp"), "party max hp")
        level = _positive_int(member.get("level"), "party level")
        if hp == 0:
            continue
        candidates.append((hp / max_hp, level, hp, -index))
    if not candidates:
        raise BattleActionTargetError("no living switch target is available")
    chosen_index = -max(candidates)[3]
    return ResolvedBattleAction(action, party_slot=chosen_index + 1)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BattleActionTargetError(f"{label} must be a mapping")
    return value


def _active_index(
    party: Mapping[str, object],
    members: tuple[Mapping[str, object], ...],
) -> int:
    value = party.get("active_index")
    if type(value) is int and value >= 0 and (not members or value < len(members)):  # noqa: E721
        return value
    lead = _mapping(party.get("lead"), "party lead")
    lead_species = lead.get("species_ref")
    if members:
        matches = [
            index
            for index, member in enumerate(members)
            if member.get("species_ref") == lead_species
            and member.get("hp") == lead.get("hp")
            and member.get("level") == lead.get("level")
        ]
        if len(matches) == 1:
            return matches[0]
    species = party.get("species_refs")
    if isinstance(species, Sequence) and not isinstance(species, (str, bytes)):
        matches = [index for index, item in enumerate(species) if item == lead_species]
        if len(matches) == 1:
            return matches[0]
    raise BattleActionTargetError("active party index is unavailable")


def _nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise BattleActionTargetError(f"{label} must be a non-negative integer")
    return value


def _positive_int(value: object, label: str) -> int:
    result = _nonnegative_int(value, label)
    if result == 0:
        raise BattleActionTargetError(f"{label} must be positive")
    return result
