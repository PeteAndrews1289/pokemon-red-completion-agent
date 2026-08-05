"""Game-neutral action vocabulary for full battle-control learning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class BattleActionKind(StrEnum):
    """High-level decisions available at a main battle-menu boundary."""

    SELECT_MOVE = "select_move"
    USE_RECOVERY = "use_recovery"
    USE_BOOST = "use_boost"
    SWITCH = "switch"
    ATTEMPT_CAPTURE = "attempt_capture"
    FLEE = "flee"


class BattleBoostStat(StrEnum):
    """Transferable stat roles for consumable battle boosts."""

    ACCURACY = "accuracy"
    ATTACK = "attack"
    SPECIAL = "special"


@dataclass(frozen=True, slots=True)
class BattleAction:
    """One semantic action without cartridge-specific item or menu identifiers."""

    kind: BattleActionKind
    move_slot: int | None = None
    party_slot: int | None = None
    boost_stat: BattleBoostStat | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BattleActionKind):
            raise TypeError("kind must be a BattleActionKind")
        if self.kind is BattleActionKind.SELECT_MOVE:
            if type(self.move_slot) is not int or not 1 <= self.move_slot <= 4:  # noqa: E721
                raise ValueError("move actions require a one-based move slot")
            if self.party_slot is not None or self.boost_stat is not None:
                raise ValueError("move actions cannot name switch or boost parameters")
        elif self.kind is BattleActionKind.SWITCH:
            if self.party_slot is not None and (
                type(self.party_slot) is not int or not 1 <= self.party_slot <= 6  # noqa: E721
            ):
                raise ValueError("switch actions require a valid one-based party slot")
            if self.move_slot is not None or self.boost_stat is not None:
                raise ValueError("switch actions cannot name move or boost parameters")
        elif self.kind is BattleActionKind.USE_BOOST:
            if not isinstance(self.boost_stat, BattleBoostStat):
                raise ValueError("boost actions require a transferable stat role")
            if self.move_slot is not None or self.party_slot is not None:
                raise ValueError("boost actions cannot name move or switch parameters")
        elif any(value is not None for value in (self.move_slot, self.party_slot, self.boost_stat)):
            raise ValueError("recovery actions cannot name move, switch, or boost parameters")

    @classmethod
    def move(cls, slot: int) -> BattleAction:
        return cls(BattleActionKind.SELECT_MOVE, move_slot=slot)

    @classmethod
    def recovery(cls) -> BattleAction:
        return cls(BattleActionKind.USE_RECOVERY)

    @classmethod
    def boost(cls, stat: BattleBoostStat) -> BattleAction:
        return cls(BattleActionKind.USE_BOOST, boost_stat=stat)

    @classmethod
    def switch(cls, slot: int | None = None) -> BattleAction:
        return cls(BattleActionKind.SWITCH, party_slot=slot)

    @classmethod
    def capture(cls) -> BattleAction:
        return cls(BattleActionKind.ATTEMPT_CAPTURE)

    @classmethod
    def flee(cls) -> BattleAction:
        return cls(BattleActionKind.FLEE)

    @property
    def semantic_ref(self) -> str:
        if self.kind is BattleActionKind.SELECT_MOVE:
            return f"pokemon.core:battle:move:{self.move_slot}"
        if self.kind is BattleActionKind.SWITCH:
            target = "select" if self.party_slot is None else str(self.party_slot)
            return f"pokemon.core:battle:switch:{target}"
        if self.kind is BattleActionKind.USE_BOOST:
            assert self.boost_stat is not None
            return f"pokemon.core:battle:boost:{self.boost_stat.value}"
        if self.kind is BattleActionKind.ATTEMPT_CAPTURE:
            return "pokemon.core:battle:capture"
        if self.kind is BattleActionKind.FLEE:
            return "pokemon.core:battle:flee"
        return "pokemon.core:battle:recovery"

    def public_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "semantic_ref": self.semantic_ref,
            "move_slot": self.move_slot,
            "party_slot": self.party_slot,
            "boost_stat": self.boost_stat.value if self.boost_stat is not None else None,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> BattleAction:
        if not isinstance(value, Mapping):
            raise TypeError("battle action must be a mapping")
        try:
            kind = BattleActionKind(value.get("kind"))  # type: ignore[arg-type]
            boost_value = value.get("boost_stat")
            action = cls(
                kind=kind,
                move_slot=value.get("move_slot"),  # type: ignore[arg-type]
                party_slot=value.get("party_slot"),  # type: ignore[arg-type]
                boost_stat=(
                    BattleBoostStat(boost_value)  # type: ignore[arg-type]
                    if boost_value is not None
                    else None
                ),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("battle action payload is invalid") from error
        if value.get("semantic_ref") != action.semantic_ref or set(value) != {
            "kind",
            "semantic_ref",
            "move_slot",
            "party_slot",
            "boost_stat",
        }:
            raise ValueError("battle action payload is not canonical")
        return action


class BattleControlRequest(Exception):
    """Typed compatibility signal from a teacher policy to its menu executor."""

    default_action: BattleAction | None = None

    def __init__(self, action: BattleAction | None = None) -> None:
        resolved = action if action is not None else self.default_action
        if not isinstance(resolved, BattleAction):
            raise TypeError("battle control requests require a BattleAction")
        if resolved.kind is BattleActionKind.SELECT_MOVE:
            raise ValueError("move selection must return normally, not use a control request")
        self.action = resolved
        super().__init__(resolved.semantic_ref)


class LearnedBattleControlRequest(BattleControlRequest):
    """A complete semantic request emitted without consulting the teacher policy."""

    def __init__(
        self,
        action: BattleAction,
        *,
        party_slot: int | None = None,
        recovery_need: str | None = None,
        status: str | None = None,
    ) -> None:
        if party_slot is not None and not 1 <= party_slot <= 6:
            raise ValueError("learned request party slot must be one-based")
        if recovery_need not in {None, "hp", "status", "hp_and_status"}:
            raise ValueError("learned request recovery need is invalid")
        if action.kind is BattleActionKind.USE_RECOVERY:
            if party_slot is None or recovery_need is None:
                raise ValueError("learned recovery request requires a complete target")
            if recovery_need in {"status", "hp_and_status"} and not status:
                raise ValueError("learned status recovery requires the observed status")
            if recovery_need == "hp" and status is not None:
                raise ValueError("learned HP recovery cannot name a status")
        elif action.kind is BattleActionKind.SWITCH:
            if party_slot is None or recovery_need is not None or status is not None:
                raise ValueError("learned switch request requires only a party target")
        elif party_slot is not None or recovery_need is not None or status is not None:
            raise ValueError("learned target is incompatible with the action")
        self.party_slot = party_slot
        self.recovery_need = recovery_need
        self.status = status
        super().__init__(action)


def control_request_matches(
    cause: BaseException | None,
    expected: BattleAction,
) -> bool:
    """Match teacher-specific and learned requests by transferable action meaning."""

    if not isinstance(expected, BattleAction):
        raise TypeError("expected must be a BattleAction")
    if not isinstance(cause, BattleControlRequest):
        return False
    actual = cause.action
    if actual.kind is not expected.kind:
        return False
    if actual.kind is BattleActionKind.USE_BOOST:
        return actual.boost_stat is expected.boost_stat
    return actual.kind is not BattleActionKind.SELECT_MOVE


def recovery_request_matches(
    cause: BaseException | None,
    teacher_request_type: type[BattleControlRequest],
    *,
    accepted_needs: frozenset[str] = frozenset({"hp", "status", "hp_and_status"}),
    accepted_statuses: frozenset[str] | None = None,
) -> bool:
    """Match an exact teacher recovery or a compatible complete learned request."""
    if not issubclass(teacher_request_type, BattleControlRequest):
        raise TypeError("teacher_request_type must be a BattleControlRequest type")
    if isinstance(cause, teacher_request_type):
        return True
    return (
        isinstance(cause, LearnedBattleControlRequest)
        and cause.action.kind is BattleActionKind.USE_RECOVERY
        and cause.recovery_need in accepted_needs
        and (accepted_statuses is None or cause.status in accepted_statuses)
    )
