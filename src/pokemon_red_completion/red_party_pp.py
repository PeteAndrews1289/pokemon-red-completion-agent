"""Exact Generation I party-PP arithmetic for Red scenario contracts.

The two high bits of a Red PP byte encode PP Up count while the lower six
encode remaining PP.  Keeping this decoder in the title adapter prevents the
inventory, preparation runner and later Crystal transfer adapter from each
inventing a subtly different resource threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.party_development_inventory import unit_bin
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
)
from pokemon_red_completion.red_party import PP_VALUE_MASK

_BATTLE_CATALOG = PokemonRedBattleCatalog()
_PP_UP_COUNT_SHIFT = 6
_PP_UP_BONUS_CAP = 7
_MOVE_SLOT_COUNT = 4
_UNSAFE_NATURAL_DEPLETION_FLAGS = frozenset(
    {
        "charge",
        "counter",
        "drain",
        "heal",
        "ohko",
        "recharge",
        "recoil",
        "self_destruct",
        "trapping",
    }
)


class RedPartyPpError(ValueError):
    """Raised when packed Red move/PP bytes are incoherent."""


@dataclass(frozen=True, slots=True)
class RedMovePp:
    """One one-based move slot's decoded PP state."""

    slot: int
    move_id: int
    current_pp: int
    maximum_pp: int

    def __post_init__(self) -> None:
        if type(self.slot) is not int or not 1 <= self.slot <= _MOVE_SLOT_COUNT:  # noqa: E721
            raise RedPartyPpError("Red move PP slot is invalid")
        if type(self.move_id) is not int or not 0 <= self.move_id <= 0xFF:  # noqa: E721
            raise RedPartyPpError("Red move PP identifier is invalid")
        for value, subject in (
            (self.current_pp, "current"),
            (self.maximum_pp, "maximum"),
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise RedPartyPpError(f"Red move {subject} PP is invalid")
        if self.current_pp > self.maximum_pp:
            raise RedPartyPpError("Red move reports PP above its own maximum")
        if (self.move_id == 0) != (self.maximum_pp == 0):
            raise RedPartyPpError("Red empty move and maximum PP disagree")


@dataclass(frozen=True, slots=True)
class RedPartyPpState:
    """Exact resource state for one four-slot Generation I moveset."""

    moves: tuple[RedMovePp, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.moves, tuple)
            or len(self.moves) != _MOVE_SLOT_COUNT
            or tuple(item.slot for item in self.moves)
            != tuple(range(1, _MOVE_SLOT_COUNT + 1))
        ):
            raise RedPartyPpError("Red move PP state must contain four ordered slots")

    @property
    def current_total(self) -> int:
        return sum(item.current_pp for item in self.moves)

    @property
    def maximum_total(self) -> int:
        return sum(item.maximum_pp for item in self.moves)

    @property
    def ratio(self) -> float:
        maximum = self.maximum_total
        return self.current_total / maximum if maximum else 0.0

    @property
    def resource_bin(self) -> str:
        return unit_bin(self.ratio)

    @property
    def middle_pp_ceiling(self) -> int:
        """Largest integer total that remains strictly below the high bin."""

        maximum = self.maximum_total
        return (67 * maximum - 1) // 100 if maximum else 0

    @property
    def minimum_consumption_to_middle(self) -> int:
        return max(0, self.current_total - self.middle_pp_ceiling)


def decode_red_party_pp(
    move_ids: tuple[int, ...],
    packed_pp: tuple[int, ...],
) -> RedPartyPpState:
    """Decode one exact four-slot moveset, including PP Up capacity."""

    if (
        not isinstance(move_ids, tuple)
        or not isinstance(packed_pp, tuple)
        or len(move_ids) != len(packed_pp)
        or len(move_ids) != _MOVE_SLOT_COUNT
        or any(
            type(value) is not int or not 0 <= value <= 0xFF  # noqa: E721
            for value in move_ids
        )
        or any(
            type(value) is not int or not 0 <= value <= 0xFF  # noqa: E721
            for value in packed_pp
        )
    ):
        raise RedPartyPpError("Red move and PP vectors are invalid")

    decoded: list[RedMovePp] = []
    for slot, (move_id, packed_value) in enumerate(
        zip(move_ids, packed_pp, strict=True),
        start=1,
    ):
        if move_id == 0:
            if packed_value:
                raise RedPartyPpError("empty Red move carries packed PP data")
            decoded.append(RedMovePp(slot, move_id, 0, 0))
            continue
        mechanics = _BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move_id))
        pp_up_count = packed_value >> _PP_UP_COUNT_SHIFT
        maximum_pp = mechanics.max_pp + pp_up_count * min(
            mechanics.max_pp // 5,
            _PP_UP_BONUS_CAP,
        )
        current_pp = packed_value & PP_VALUE_MASK
        if current_pp > maximum_pp:
            raise RedPartyPpError("Red move reports PP above its own maximum")
        decoded.append(RedMovePp(slot, move_id, current_pp, maximum_pp))
    return RedPartyPpState(tuple(decoded))


def natural_pp_depletion_slots(state: RedPartyPpState) -> tuple[int, ...]:
    """Return deterministic damaging slots safe for ordinary PP consumption."""

    if not isinstance(state, RedPartyPpState):
        raise TypeError("state must be a RedPartyPpState")
    slots = []
    for item in state.moves:
        if item.move_id == 0 or item.current_pp == 0:
            continue
        mechanics = _BATTLE_CATALOG.resolve_move(
            pokemon_red_move_ref(item.move_id)
        )
        if (
            mechanics.category == "status"
            or mechanics.power <= 0
            or mechanics.effect_flags & _UNSAFE_NATURAL_DEPLETION_FLAGS
        ):
            continue
        slots.append(item.slot)
    return tuple(slots)


__all__ = [
    "RedMovePp",
    "RedPartyPpError",
    "RedPartyPpState",
    "decode_red_party_pp",
    "natural_pp_depletion_slots",
]
