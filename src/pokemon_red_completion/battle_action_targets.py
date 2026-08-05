"""Game-neutral target resolution for high-level battle actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_runtime import (
    BattleRecoveryCapability,
    BattleSwitchCapability,
)


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
    status: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, BattleAction):
            raise TypeError("action must be a BattleAction")
        if self.action.kind is BattleActionKind.USE_RECOVERY:
            if self.party_slot is None or self.recovery_need is None:
                raise ValueError("recovery actions require a party slot and recovery need")
            if self.recovery_need in {RecoveryNeed.STATUS, RecoveryNeed.HP_AND_STATUS}:
                if not self.status:
                    raise ValueError("status recovery requires the observed status")
            elif self.status is not None:
                raise ValueError("HP-only recovery cannot name a status")
        elif self.action.kind is BattleActionKind.SWITCH:
            if self.party_slot is None or self.recovery_need is not None or self.status is not None:
                raise ValueError("switch actions require only a party slot")
        elif (
            self.party_slot is not None
            or self.recovery_need is not None
            or self.status is not None
        ):
            raise ValueError("this action kind does not accept a target")
        if self.party_slot is not None and not 1 <= self.party_slot <= 6:
            raise ValueError("party_slot must be one-based and between one and six")

    def public_dict(self) -> dict[str, object]:
        return {
            "action": self.action.public_dict(),
            "party_slot": self.party_slot,
            "recovery_need": (self.recovery_need.value if self.recovery_need is not None else None),
            "status": self.status,
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
        status = active.get("status")
        if status is not None and (not isinstance(status, str) or not status):
            raise BattleActionTargetError("active status must be a semantic string")
        has_status = status is not None
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
            status=status,
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


def authorize_recovery_target(
    resolved: ResolvedBattleAction,
    capabilities: frozenset[BattleRecoveryCapability],
) -> ResolvedBattleAction:
    """Select one declared recovery effect without consulting a teacher policy."""
    if resolved.action.kind is not BattleActionKind.USE_RECOVERY:
        raise BattleActionTargetError("only recovery actions use recovery capabilities")
    if not isinstance(capabilities, frozenset) or any(
        not isinstance(value, BattleRecoveryCapability) for value in capabilities
    ):
        raise TypeError("capabilities must contain recovery capabilities")
    need = resolved.recovery_need
    assert need is not None
    status_capability = {
        "sleep": BattleRecoveryCapability.CURE_SLEEP,
        "paralysis": BattleRecoveryCapability.CURE_PARALYSIS,
        "poison": BattleRecoveryCapability.CURE_POISON,
        "burn": BattleRecoveryCapability.CURE_BURN,
        "freeze": BattleRecoveryCapability.CURE_FREEZE,
    }.get(resolved.status)
    status_allowed = resolved.status is not None and (
        BattleRecoveryCapability.CURE_ANY_STATUS in capabilities
        or status_capability in capabilities
    )
    hp_allowed = (
        need in {RecoveryNeed.HP, RecoveryNeed.HP_AND_STATUS}
        and BattleRecoveryCapability.RESTORE_HP in capabilities
    )
    if status_allowed and BattleRecoveryCapability.CURE_ANY_STATUS in capabilities:
        return replace(
            resolved,
            recovery_need=(RecoveryNeed.HP_AND_STATUS if hp_allowed else RecoveryNeed.STATUS),
        )
    if status_allowed:
        return replace(resolved, recovery_need=RecoveryNeed.STATUS)
    if hp_allowed:
        return replace(resolved, recovery_need=RecoveryNeed.HP, status=None)
    raise BattleActionTargetError("recovery effect is not declared by the executor")


def authorize_switch_target(
    resolved: ResolvedBattleAction,
    capabilities: frozenset[BattleSwitchCapability],
    *,
    observation: Mapping[str, object] | None = None,
) -> ResolvedBattleAction:
    """Authorize a complete living-party target for a declared switch executor."""
    if resolved.action.kind is not BattleActionKind.SWITCH:
        raise BattleActionTargetError("only switch actions use switch capabilities")
    if not isinstance(capabilities, frozenset) or any(
        not isinstance(value, BattleSwitchCapability) for value in capabilities
    ):
        raise TypeError("capabilities must contain switch capabilities")
    if not capabilities:
        raise BattleActionTargetError("switch effect is not declared by the executor")
    if resolved.party_slot is None:
        raise BattleActionTargetError("switch action lacks a complete party target")
    if observation is not None and capabilities & {
        BattleSwitchCapability.RESET_STAT_STAGES,
        BattleSwitchCapability.TEMPORARY_ROLE_PIVOT,
        BattleSwitchCapability.PROTECTED_RECOVERY,
    }:
        features = _mapping(observation.get("features"), "features")
        party = _mapping(features.get("party"), "party")
        members_value = party.get("members")
        if not isinstance(members_value, Sequence) or isinstance(
            members_value, (str, bytes)
        ):
            raise BattleActionTargetError("party members are unavailable for switching")
        members = tuple(_mapping(value, "party member") for value in members_value)
        active_index = _active_index(party, members)
        candidates = [
            (index, member)
            for index, member in enumerate(members)
            if index != active_index
            and _nonnegative_int(member.get("hp"), "party hp") > 0
        ]
        if not candidates:
            raise BattleActionTargetError("no living switch target is available")
        if BattleSwitchCapability.TEMPORARY_ROLE_PIVOT in capabilities:
            active_level = _positive_int(
                members[active_index].get("level"), "active party level"
            )
            strongest_level = max(
                _positive_int(member.get("level"), "party level")
                for _index, member in candidates
            )
            if active_level < strongest_level:
                chosen_index = max(
                    candidates,
                    key=lambda candidate: (
                        _positive_int(candidate[1].get("level"), "party level"),
                        _nonnegative_int(candidate[1].get("hp"), "party hp")
                        / _positive_int(
                            candidate[1].get("max_hp"), "party max hp"
                        ),
                        -candidate[0],
                    ),
                )[0]
            else:
                chosen_index = min(index for index, _member in candidates)
        else:
            chosen_index = min(index for index, _member in candidates)
        return replace(resolved, party_slot=chosen_index + 1)
    return resolved


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
