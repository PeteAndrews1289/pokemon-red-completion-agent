"""Capability-derived storage substitution, using the existing verified PC operator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from pokemon_red_completion.gen1_field_moves import GEN1_FIELD_MOVE_IDS
from pokemon_red_completion.observation import (
    PokemonRedStateReader,
    RedBoxCollectionState,
    RedBoxMoveMember,
)
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from pokemon_red_completion.red_capture_lead import plan_capture_lead
from pokemon_red_completion.red_pc_storage import (
    ActionExecutor,
    close_generic_pc_session,
    deposit_party_member,
    face_pc_boundary,
    open_bills_pc,
    switch_box,
    withdraw_box_member,
)


class RedFieldPartyError(RuntimeError):
    """A field specialist cannot be retrieved with its declared protections."""


@dataclass(frozen=True)
class RedFieldPartyPlan:
    move_id: int
    party: PartyObservation
    boxes: RedBoxCollectionState
    target_box: int
    helper: RedBoxMoveMember
    deposit_slot: int | None


def plan_field_party(
    party: PartyObservation,
    boxes: RedBoxCollectionState,
    inventories: tuple[tuple[RedBoxMoveMember, ...], ...],
    *,
    move_id: int,
) -> RedFieldPartyPlan | None:
    """Preserve field/status support and an escort; no species-specific selection."""
    if move_id not in GEN1_FIELD_MOVE_IDS or type(move_id) is not int:
        raise ValueError("unsupported field move")
    if len(inventories) != len(boxes.boxes):
        raise RedFieldPartyError("complete box inventory required")
    for box, inventory in zip(boxes.boxes, inventories, strict=True):
        if (
            tuple(m.box_slot for m in inventory) != tuple(range(1, len(inventory) + 1))
            or tuple(m.species_id for m in inventory) != box.species_ids
            or tuple(m.level for m in inventory) != box.levels
        ):
            raise RedFieldPartyError("box move inventory differs")
    if any(m.hp > 0 and any(v.move_id == move_id for v in m.moves) for m in party.members):
        return None
    escort = plan_capture_lead(party).target_member.slot
    helpers = [(i, m) for i, rows in enumerate(inventories) for m in rows if move_id in m.moves]
    if not helpers:
        raise RedFieldPartyError("no owned field move holder")
    if party.size == 6 and len(boxes.boxes[boxes.current_box_index].species_ids) >= 20:
        # Deposit in the existing box before switching. Do not search for hidden capacity.
        raise RedFieldPartyError("current box has no substitution capacity")
    deposit = None
    if party.size == 6:
        candidates = []
        for member in party.members:
            if member.slot == escort:
                continue
            others = [m for m in party.members if m.slot != member.slot]
            fields = {v.move_id for v in member.moves} & GEN1_FIELD_MOVE_IDS
            retained = {v.move_id for m in others if m.hp > 0 for v in m.moves}
            if fields - retained:
                continue

            def statuses(members: list[PartyMemberObservation]) -> set[str]:
                return {
                    effect
                    for m in members
                    if m.hp > 0
                    for v in m.moves
                    if v.is_usable
                    if (
                        effect := RED_BATTLE_CATALOG.capture_status_effect(
                            pokemon_red_move_ref(v.move_id)
                        )
                    )
                    is not None
                }

            if statuses([member]) - statuses(others):
                continue
            capacity = max(
                (
                    spec.power
                    for v in member.moves
                    if v.is_usable
                    if (
                        spec := RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(v.move_id))
                    ).category
                    != "status"
                    and "self_destruct" not in spec.effect_flags
                ),
                default=0,
            )
            candidates.append((capacity, member.level, member.slot))
        if not candidates:
            raise RedFieldPartyError("all party members are protected")
        deposit = min(candidates)[2]
    target, helper = min(
        helpers, key=lambda row: (row[0] != boxes.current_box_index, row[0], row[1].box_slot)
    )
    return RedFieldPartyPlan(move_id, party, boxes, target, helper, deposit)


def retrieve_field_party_at_pc(
    plan: RedFieldPartyPlan,
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    *,
    pc_map: int,
    read_party: Callable[[], PartyObservation],
) -> dict[str, object]:
    """No routing, healing, release or rollback. Exceptions retain partial PC state."""
    from pokemon_red_completion.red_goal_skills import _POKEMON_CENTER_MAPS

    before = reader.read()
    if (
        pc_map not in _POKEMON_CENTER_MAPS
        or (before.map_id, before.player_y, before.player_x) != (pc_map, 4, 13)
        or before.battle_state != 0
        or not reader.read_input_readiness().ready
        or reader.read_generic_pc_session_active()
        or before.bag_items is None
        or before.player_money is None
        or before.event_flags is None
        or read_party() != plan.party
        or reader.read_all_box_states() != plan.boxes
        or reader.read_box_move_members(plan.target_box)[plan.helper.box_slot - 1] != plan.helper
    ):
        raise RedFieldPartyError("field retrieval boundary changed before input")
    # Recompute admissibility: even a caller-constructed plan cannot bypass protections.
    inventories = tuple(reader.read_box_move_members(i) for i in range(12))
    if plan_field_party(plan.party, plan.boxes, inventories, move_id=plan.move_id) != plan:
        raise RedFieldPartyError("field retrieval plan is not the current safe substitution")
    expected_boxes = list(plan.boxes.boxes)
    expected_party = list(plan.party.members)
    face_pc_boundary(actions, reader, "up")
    open_bills_pc(actions, reader)
    if plan.deposit_slot is not None:
        member = expected_party.pop(plan.deposit_slot - 1)
        report = deposit_party_member(
            actions, reader, party_slot=plan.deposit_slot, expected_species_id=member.species_id
        )
        if not report.passed:
            raise RedFieldPartyError("field specialist deposit failed")
        index = plan.boxes.current_box_index
        box = expected_boxes[index]
        expected_boxes[index] = replace(
            box,
            species_ids=(*box.species_ids, member.species_id),
            levels=(*box.levels, member.level),
        )
    if (
        plan.target_box != plan.boxes.current_box_index
        and not switch_box(actions, reader, target_box_index=plan.target_box).passed
    ):
        raise RedFieldPartyError("field specialist box switch failed")
    if reader.read_box_move_members(plan.target_box)[plan.helper.box_slot - 1] != plan.helper:
        raise RedFieldPartyError("stored field specialist changed before withdrawal")
    if not withdraw_box_member(
        actions, reader, box_slot=plan.helper.box_slot, expected_species_id=plan.helper.species_id
    ).passed:
        raise RedFieldPartyError("field specialist withdrawal failed")
    close_generic_pc_session(actions, reader)
    raw, party = reader.read(), read_party()
    target = expected_boxes[plan.target_box]
    index = plan.helper.box_slot - 1
    expected_boxes[plan.target_box] = replace(
        target,
        species_ids=target.species_ids[:index] + target.species_ids[index + 1 :],
        levels=target.levels[:index] + target.levels[index + 1 :],
    )
    boxes = reader.read_all_box_states()
    if (
        boxes.boxes != tuple(expected_boxes)
        or boxes.current_box_index != plan.target_box
        or party.size != len(expected_party) + 1
        or party.members[:-1] != tuple(replace(m, slot=i + 1) for i, m in enumerate(expected_party))
        or any(
            getattr(raw, key) != getattr(before, key)
            for key in (
                "map_id",
                "player_x",
                "player_y",
                "bag_items",
                "player_money",
                "badge_bits",
                "event_flags",
            )
        )
        or raw.battle_state != 0
        or not reader.read_input_readiness().ready
        or reader.read_generic_pc_session_active()
    ):
        raise RedFieldPartyError("field retrieval changed protected state")
    member = party.members[-1]
    if (
        member.species_id != plan.helper.species_id
        or member.level != plan.helper.level
        or tuple(v.move_id for v in member.moves) != plan.helper.moves
        or tuple(v.current_pp for v in member.moves) != plan.helper.pp
        or member.hp <= 0
    ):
        raise RedFieldPartyError("withdrawn field specialist is not the usable observed holder")
    return {
        "field_specialist_retrieved": True,
        "collection_preserved": True,
        "setup_training_rows": 0,
        "new_acquisitions": 0,
        "deposit_party_slot": plan.deposit_slot,
        "target_box": plan.target_box,
    }
