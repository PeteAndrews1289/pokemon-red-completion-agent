"""Opt-in PP resource evidence, separate from historical HP/resource features."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .observation import ItemId, RawGameState
from .red_party_pp import decode_red_party_pp

PP_RESOURCE_SCHEMA = "pokemon.red.pp-resource-observation.v1"


@dataclass(frozen=True, slots=True)
class RedPpResourceObservation:
    item_count: int
    party_slots: tuple[tuple[tuple[int, int], ...], ...]

    def __post_init__(self) -> None:
        if type(self.item_count) is not int or not 0 <= self.item_count <= 99:
            raise ValueError("PP restorative count is invalid")
        if type(self.party_slots) is not tuple or not 1 <= len(self.party_slots) <= 6:
            raise ValueError("PP observation needs one to six party members")
        for member in self.party_slots:
            if type(member) is not tuple or len(member) != 4:
                raise ValueError("PP observation needs four ordered move slots")
            for slot in member:
                if (
                    type(slot) is not tuple or len(slot) != 2
                    or any(type(value) is not int for value in slot)
                    or not 0 <= slot[0] <= slot[1] <= 63
                ):
                    raise ValueError("PP observation slot is invalid")

    def public_dict(self) -> dict[str, object]:
        # Slot quantities, not species/move identifiers, addresses or bindings.
        return {
            "schema": PP_RESOURCE_SCHEMA,
            "item_count": self.item_count,
            "party_slots": [[list(slot) for slot in member] for member in self.party_slots],
        }

    @classmethod
    def from_public(cls, value: object) -> RedPpResourceObservation:
        if not isinstance(value, Mapping) or set(value) != {
            "schema", "item_count", "party_slots",
        } or value["schema"] != PP_RESOURCE_SCHEMA:
            raise ValueError("PP resource observation schema differs")
        members = value["party_slots"]
        count = value["item_count"]
        if type(count) is not int or not isinstance(members, list):
            raise ValueError("PP resource observation types differ")
        parsed = []
        for member in members:
            if not isinstance(member, list):
                raise ValueError("PP resource member differs")
            slots = []
            for slot in member:
                if not isinstance(slot, list) or len(slot) != 2:
                    raise ValueError("PP resource slot differs")
                current, maximum = slot
                if type(current) is not int or type(maximum) is not int:
                    raise ValueError("PP resource quantities differ")
                slots.append((current, maximum))
            parsed.append(tuple(slots))
        return cls(count, tuple(parsed))


def observe_pp_resources(raw: RawGameState) -> RedPpResourceObservation:
    if (
        type(raw.party_count) is not int or not 1 <= raw.party_count <= 6
        or raw.party_moves is None or raw.party_pp is None
        or len(raw.party_moves) != raw.party_count or len(raw.party_pp) != raw.party_count
        or raw.bag_items is None
    ):
        raise ValueError("PP resource observation needs complete party and inventory")
    inventory: dict[int, int] = {}
    for item, quantity in raw.bag_items:
        if (
            type(item) is not int or not 1 <= item <= 255 or item in inventory
            or type(quantity) is not int or not 1 <= quantity <= 99
        ):
            raise ValueError("PP resource observation inventory differs")
        inventory[item] = quantity
    party = tuple(
        tuple((slot.current_pp, slot.maximum_pp) for slot in decode_red_party_pp(moves, pp).moves)
        for moves, pp in zip(raw.party_moves, raw.party_pp, strict=True)
    )
    return RedPpResourceObservation(inventory.get(int(ItemId.ELIXIR), 0), party)
