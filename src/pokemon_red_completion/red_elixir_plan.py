"""Pure, exact one-Elixir field plans; no inputs or learned target changes.

The caller must separately prove input readiness and released controls. A plan
chooses a party member by actual PP restored, not species, lead or battle value.
Field enemy-memory aliases are not meaningful protected overworld state.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import cast

from .observation import EVENT_FLAG_BYTES, RawGameState
from .red_party_pp import decode_red_party_pp

ELIXIR_ITEM_ID = 82


class RedElixirPlanError(ValueError):
    """An Elixir target, snapshot or observed effect does not qualify."""


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _same(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, tuple):
        assert isinstance(right, tuple)
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    return bool(left == right)


def _validate(raw: RawGameState) -> None:
    if (
        not isinstance(raw, RawGameState) or raw.game_started is not True
        or not _integer(raw.battle_state, 0, 0)
        or not _integer(raw.map_id, 0, 255)
        or not _integer(raw.player_x, 0, 255) or not _integer(raw.player_y, 0, 255)
        or not _integer(raw.party_count, 1, 6)
        or not _integer(raw.player_money, 0, 999999)
        or type(raw.event_flags) is not bytes or len(raw.event_flags) != EVENT_FLAG_BYTES
    ):
        raise RedElixirPlanError("Elixir requires a complete observed field boundary")
    count = cast(int, raw.party_count)
    for values, minimum, maximum in (
        (raw.party_species_ids, 1, 190), (raw.party_levels, 1, 100),
        (raw.party_hp, 1, 999), (raw.party_max_hp, 1, 999),
        (raw.party_status, 0, 255),
    ):
        if (type(values) is not tuple or len(values) != count
                or not all(_integer(value, minimum, maximum) for value in values)):
            raise RedElixirPlanError("Elixir requires complete, living party data")
    assert raw.party_hp is not None and raw.party_max_hp is not None
    if any(hp > maximum for hp, maximum in zip(raw.party_hp, raw.party_max_hp, strict=True)):
        raise RedElixirPlanError("Elixir party HP exceeds its maximum")
    if (type(raw.party_moves) is not tuple or type(raw.party_pp) is not tuple
            or len(raw.party_moves) != count or len(raw.party_pp) != count):
        raise RedElixirPlanError("Elixir party move/PP arrays differ")
    for moves, pp in zip(raw.party_moves, raw.party_pp, strict=True):
        try:
            decoded = decode_red_party_pp(moves, pp)
        except ValueError as error:
            raise RedElixirPlanError("Elixir move/PP bytes are invalid") from error
        if not decoded.maximum_total:
            raise RedElixirPlanError("Elixir party member has no occupied move")
    bag = raw.bag_items
    if (type(bag) is not tuple or len(bag) > 20 or any(
        type(row) is not tuple or len(row) != 2
        or not _integer(row[0], 1, 255) or not _integer(row[1], 1, 99)
        for row in bag
    )):
        raise RedElixirPlanError("Elixir bag is invalid")
    if len({item for item, _ in bag}) != len(bag):
        raise RedElixirPlanError("Elixir bag contains duplicate item stacks")
    if raw.bag_item_ids is not None and not _same(raw.bag_item_ids, tuple(i for i, _ in bag)):
        raise RedElixirPlanError("Elixir bag identity alias differs")
    for alias, alias_values in (
        (raw.first_party_level, raw.party_levels), (raw.first_party_hp, raw.party_hp),
        (raw.first_party_max_hp, raw.party_max_hp), (raw.first_party_status, raw.party_status),
        (raw.first_party_moves, raw.party_moves), (raw.first_party_pp, raw.party_pp),
    ):
        assert alias_values is not None
        if alias is not None and not _same(alias, alias_values[0]):
            raise RedElixirPlanError("Elixir first-party alias differs")
    if any(getattr(raw, field.name) is not None for field in fields(raw)
           if field.name.startswith("active_party_")):
        raise RedElixirPlanError("Elixir field state contains active battle-party data")
    for value in (raw.badge_bits, raw.status_flags_1, raw.repel_remaining_steps):
        if value is not None and not _integer(value, 0, 255):
            raise RedElixirPlanError("Elixir protected field byte is invalid")
    # Frozen RawGameState alone does not reject mutable or mistyped values in
    # its optional scratch fields. Keep the entire bound snapshot immutable.
    for name in (
        "battle_result", "enemy_species_id", "enemy_hp", "enemy_level", "enemy_max_hp",
        "player_attack_stage", "player_special_stage", "player_accuracy_stage",
        "enemy_defense_stage", "player_disabled_move_slot", "player_disable_turns",
    ):
        value = getattr(raw, name)
        if value is not None and not _integer(value, 0, 65535):
            raise RedElixirPlanError("Elixir optional raw field is invalid")
    if (raw.enemy_using_trapping_move is not None
            and type(raw.enemy_using_trapping_move) is not bool):
        raise RedElixirPlanError("Elixir optional raw flag is invalid")


def _selection(raw: RawGameState) -> tuple[int, tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    _validate(raw)
    assert raw.bag_items is not None and raw.party_moves is not None and raw.party_pp is not None
    if dict(raw.bag_items).get(ELIXIR_ITEM_ID, 0) < 1:
        raise RedElixirPlanError("Elixir is not owned")
    candidates = []
    for index, (moves, pp) in enumerate(zip(raw.party_moves, raw.party_pp, strict=True)):
        decoded = decode_red_party_pp(moves, pp)
        gains = tuple(min(10, move.maximum_pp - move.current_pp) for move in decoded.moves)
        after = tuple(packed + gain for packed, gain in zip(pp, gains, strict=True))
        candidates.append((index, pp, after, gains))
    selected = max(candidates, key=lambda row: (sum(row[3]), -row[0]))
    if not sum(selected[3]):
        raise RedElixirPlanError("Elixir has no positive PP benefit")
    return selected


@dataclass(frozen=True, slots=True)
class RedElixirPlan:
    before: RawGameState
    party_index: int
    before_pp: tuple[int, ...]
    after_pp: tuple[int, ...]
    slot_gains: tuple[int, ...]

    def __post_init__(self) -> None:
        expected = _selection(self.before)
        if not _same((self.party_index, self.before_pp, self.after_pp, self.slot_gains), expected):
            raise RedElixirPlanError("Elixir plan differs from its bound observed benefit")

    @property
    def total_pp_restored(self) -> int:
        return sum(self.slot_gains)

    @property
    def expected_bag(self) -> tuple[tuple[int, int], ...]:
        assert self.before.bag_items is not None
        return tuple(
            (item, quantity - int(item == ELIXIR_ITEM_ID))
            for item, quantity in self.before.bag_items
            if item != ELIXIR_ITEM_ID or quantity > 1
        )


def plan_field_elixir(raw: RawGameState) -> RedElixirPlan:
    """Maximize actual restored PP among living targets; ties use party order."""
    return RedElixirPlan(raw, *_selection(raw))


def verify_field_elixir(plan: RedElixirPlan, before: RawGameState, after: RawGameState) -> None:
    """Verify exactly one application, not input readiness or completion authority."""
    if not isinstance(plan, RedElixirPlan):
        raise RedElixirPlanError("Elixir plan is unavailable")
    _validate(before)
    _validate(after)
    if not all(
        _same(getattr(before, f.name), getattr(plan.before, f.name)) for f in fields(before)
    ):
        raise RedElixirPlanError("Elixir before-state differs from its bound snapshot")
    plan.__post_init__()
    assert before.party_pp is not None
    expected_pp = tuple(
        plan.after_pp if index == plan.party_index else pp
        for index, pp in enumerate(before.party_pp)
    )
    if not _same(after.party_pp, expected_pp) or not _same(after.bag_items, plan.expected_bag):
        raise RedElixirPlanError("Elixir exact PP effect or one-item consumption differs")
    if before.bag_item_ids is None:
        expected_ids = None
    else:
        expected_ids = tuple(item for item, _ in plan.expected_bag)
    expected_first_pp = expected_pp[0] if before.first_party_pp is not None else None
    if (not _same(after.bag_item_ids, expected_ids)
            or not _same(after.first_party_pp, expected_first_pp)):
        raise RedElixirPlanError("Elixir updated bag/PP aliases differ")
    for name in (
        "game_started", "battle_state", "map_id", "player_x", "player_y", "player_money",
        "event_flags", "badge_bits", "status_flags_1", "repel_remaining_steps",
        "party_count", "party_species_ids", "party_levels", "party_moves",
        "party_hp", "party_max_hp", "party_status", "first_party_level",
        "first_party_hp", "first_party_max_hp", "first_party_status", "first_party_moves",
    ):
        if not _same(getattr(before, name), getattr(after, name)):
            raise RedElixirPlanError(f"Elixir changed protected {name}")
