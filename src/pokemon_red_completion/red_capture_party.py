"""One bounded PC substitution chosen from actual stored move capabilities.

The selected capture goal owns this preparation. It is deterministic support,
not a second policy decision, acquisition, evolution or fitted outcome.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from pokemon_red_completion.capture_support import choose_capture_status
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import PokemonRedStateReader, RedBoxMoveMember
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation, StatusCondition
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from pokemon_red_completion.red_capture_support import red_capture_status_options
from pokemon_red_completion.red_pc_storage import (
    deposit_party_member,
    face_pc_boundary,
    open_bills_pc,
    switch_box,
    withdraw_box_member,
)
from pokemon_red_completion.red_team_training import close_menu

# Revision-specific HM move identities stay in the Red adapter, never model inputs.
_FIELD_MOVES = frozenset({15, 19, 57, 70, 148})


class RedCapturePartyError(RuntimeError):
    """Capture support is absent, changed or unsafe to retrieve."""


@dataclass(frozen=True, slots=True)
class RedCapturePartyPlan:
    helper: RedBoxMoveMember
    deposit_party_slot: int | None
    party_species_ids: tuple[int, ...]
    party_moves: tuple[tuple[int, ...], ...]
    current_box_index: int
    helper_box_index: int
    box_species_ids: tuple[int, ...]
    observed_box_species: tuple[tuple[int, tuple[int, ...]], ...]


def capture_party_ready(party: PartyObservation) -> bool:
    return (
        choose_capture_status(
            party,
            red_capture_status_options(party),
            target_status=StatusCondition.HEALTHY,
            attempts_used=0,
        )
        is not None
    )


def explain_capture_party_unready(
    party: PartyObservation,
    expected_helper: RedBoxMoveMember | None = None,
) -> str:
    """Format path-free semantic diagnostics explaining why party capture support is unready.

    Examines living status, HP ratio vs the 50% threshold, status condition, and move PP
    without exposing private paths or raw memory.
    """
    if not party.members:
        return "party has no members"
    reasons: list[str] = []
    if expected_helper is not None:
        candidate: PartyMemberObservation | None = party.members[-1]
        assert candidate is not None
        if candidate.species_id != expected_helper.species_id:
            matching = [m for m in party.members if m.species_id == expected_helper.species_id]
            if matching:
                candidate = matching[0]
            else:
                reasons.append(
                    f"expected helper species {expected_helper.species_id} not found in party "
                    f"(last slot {candidate.slot} is species {candidate.species_id})"
                )
                candidate = None
        if candidate is not None:
            c_reasons: list[str] = []
            if candidate.hp == 0:
                c_reasons.append(f"fainted (hp 0/{candidate.max_hp})")
            elif candidate.hp_ratio <= 0.5:
                c_reasons.append(
                    f"low HP ({candidate.hp}/{candidate.max_hp} = {candidate.hp_ratio:.1%}, "
                    f"requires > 50.0%)"
                )
            if candidate.status is not StatusCondition.HEALTHY:
                c_reasons.append(f"status condition '{candidate.status.value}'")
            status_moves: list[tuple[int, int, str]] = []
            for move in candidate.moves:
                if not move.is_known:
                    continue
                ref = pokemon_red_move_ref(move.move_id)
                effect = RED_BATTLE_CATALOG.capture_status_effect(ref)
                if effect is not None:
                    status_moves.append((move.move_id, move.current_pp, effect))
            if not status_moves:
                c_reasons.append("unsuitable moves (no sleep/paralysis move)")
            elif all(pp == 0 for _, pp, _ in status_moves):
                exhausted_ids = ", ".join(str(mid) for mid, _, _ in status_moves)
                c_reasons.append(f"status moves out of PP (move {exhausted_ids})")
            if c_reasons:
                reasons.append(
                    f"withdrawn helper slot {candidate.slot} (species {candidate.species_id}, "
                    f"level {candidate.level}): {'; '.join(c_reasons)}"
                )

    options = red_capture_status_options(party)
    if not options:
        reasons.append("party has no usable sleep/paralysis moves")
    else:
        disqualified: list[str] = []
        for opt in options:
            m = party.members[opt.party_slot - 1]
            flaws: list[str] = []
            if m.hp == 0:
                flaws.append("fainted")
            elif m.hp_ratio <= 0.5:
                flaws.append(f"HP {m.hp_ratio:.1%} <= 50%")
            if m.status is not StatusCondition.HEALTHY:
                flaws.append(f"status '{m.status.value}'")
            disqualified.append(f"slot {m.slot} ({', '.join(flaws)})")
        reasons.append(
            f"{len(options)} move option(s) available but disqualified: {'; '.join(disqualified)}"
        )
    return "; ".join(reasons) if reasons else "no member satisfies capture readiness"


def plan_capture_party(
    party: PartyObservation,
    box: tuple[RedBoxMoveMember, ...],
    *,
    box_index: int,
) -> RedCapturePartyPlan | None:
    """Choose a helper from one observed box (the compatibility entry point)."""
    return plan_capture_party_across_boxes(
        party,
        ((box_index, box),),
        current_box_index=box_index,
    )


def plan_capture_party_across_boxes(
    party: PartyObservation,
    boxes: tuple[tuple[int, tuple[RedBoxMoveMember, ...]], ...],
    *,
    current_box_index: int,
) -> RedCapturePartyPlan | None:
    """Choose capabilities across observed boxes and preserve field-move carriers.

    ``boxes`` is deliberately keyed by box index instead of species identity.  The
    caller may pass all twelve verified boxes; the one-box entry point above keeps
    older callers honest without pretending unobserved storage is empty.
    """
    if type(current_box_index) is not int or not 0 <= current_box_index < 12:
        raise ValueError("capture support current box differs")
    indices = tuple(index for index, _members in boxes)
    if (
        not boxes
        or len(set(indices)) != len(indices)
        or any(type(index) is not int or not 0 <= index < 12 for index in indices)
        or tuple(sorted(indices)) != indices
        or current_box_index not in indices
    ):
        raise ValueError("capture support observed boxes differ")
    for _index, members in boxes:
        if tuple(row.box_slot for row in members) != tuple(range(1, len(members) + 1)):
            raise ValueError("capture support box slots are not contiguous")
    if capture_party_ready(party):
        return None
    if not any(member.hp > 0 for member in party.members):
        raise RedCapturePartyError("capture preparation needs a living escort")
    helpers = []
    blocked_capability = False
    for candidate_box_index, members in boxes:
        # A full party must first deposit into the helper's box.  Do not choose a
        # technically capable helper whose container cannot accept that deposit.
        if len(party.members) == 6 and len(members) >= 20:
            blocked_capability = blocked_capability or any(
                move and pp
                and RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(move))
                for boxed in members
                for move, pp in zip(boxed.moves, boxed.pp, strict=True)
            )
            continue
        for boxed in members:
            accuracy = [
                RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move)).accuracy
                for move, pp in zip(boxed.moves, boxed.pp, strict=True)
                if move and pp
                and RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(move))
            ]
            if accuracy:
                helpers.append(
                    (
                        max(accuracy),
                        boxed.level,
                        candidate_box_index == current_box_index,
                        -candidate_box_index,
                        -boxed.box_slot,
                        candidate_box_index,
                        boxed,
                    )
                )
    if not helpers:
        if blocked_capability:
            raise RedCapturePartyError("capture helper substitution needs one free box slot")
        raise RedCapturePartyError("no usable retrievable sleep/paralysis helper in observed boxes")
    selected = max(helpers, key=lambda row: row[:5])
    helper_box_index, helper = selected[5], selected[6]
    helper_box = dict(boxes)[helper_box_index]
    deposit = None
    if len(party.members) == 6:
        strongest = max(
            (member for member in party.members if member.hp > 0),
            key=lambda member: (member.level, member.hp),
            default=None,
        )
        if strongest is None:
            raise RedCapturePartyError("capture preparation needs a living escort")
        candidates = []
        for member in party.members:
            if member.slot == strongest.slot:
                continue
            known = {move.move_id for move in member.moves} & _FIELD_MOVES
            others = {
                move.move_id
                for other in party.members
                if other.slot != member.slot
                for move in other.moves
            }
            if known - others:
                continue
            candidates.append(member)
        if not candidates:
            raise RedCapturePartyError("every party member is protected capture support")
        deposit = min(candidates, key=lambda member: (member.level, -member.slot)).slot
    return RedCapturePartyPlan(
        helper,
        deposit,
        tuple(member.species_id for member in party.members),
        tuple(tuple(move.move_id for move in member.moves) for member in party.members),
        current_box_index,
        helper_box_index,
        tuple(member.species_id for member in helper_box),
        tuple(
            (index, tuple(member.species_id for member in members))
            for index, members in boxes
        ),
    )


def _read_observed_box_species(
    plan: RedCapturePartyPlan, reader: PokemonRedStateReader,
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    if len(plan.observed_box_species) == 1:
        box = reader.read_current_box_state()
        return ((box.box_index, box.species_ids),)
    collection = reader.read_all_box_states()
    return tuple((box.box_index, box.species_ids) for box in collection.boxes)


def execute_capture_party_at_pc(
    plan: RedCapturePartyPlan,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    *,
    pc_map_id: int,
    read_party: Callable[[], PartyObservation],
    restore_helper: Callable[[], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Withdraw at a settled PC; any optional restoration is explicit and reported."""
    raw = reader.read()
    box = reader.read_current_box_state()
    observed_boxes = _read_observed_box_species(plan, reader)
    moves = (
        reader.read_current_box_move_members()
        if plan.helper_box_index == plan.current_box_index
        else reader.read_box_move_members(plan.helper_box_index)
    )
    if (
        (raw.map_id, raw.player_y, raw.player_x) != (pc_map_id, 4, 13)
        or raw.battle_state != 0
        or not reader.read_input_readiness().ready
        or raw.party_species_ids != plan.party_species_ids
        or raw.party_moves != plan.party_moves
        or box.box_index != plan.current_box_index
        or observed_boxes != plan.observed_box_species
        or dict(observed_boxes).get(plan.helper_box_index) != plan.box_species_ids
        or moves[plan.helper.box_slot - 1] != plan.helper
    ):
        raise RedCapturePartyError("capture helper plan differs before PC input")
    before = Counter(
        (*plan.party_species_ids, *(species for _, rows in observed_boxes for species in rows))
    )
    bag, money = raw.bag_items, raw.player_money
    face_pc_boundary(actions, reader, "up")
    open_bills_pc(actions, reader)
    rotations = 0
    if plan.helper_box_index != plan.current_box_index:
        report_switch = switch_box(
            actions, reader, target_box_index=plan.helper_box_index,
        )
        if not report_switch.passed:
            raise RedCapturePartyError("capture helper box switch failed")
        rotations = 1
    if plan.deposit_party_slot is not None:
        report = deposit_party_member(
            actions,
            reader,
            party_slot=plan.deposit_party_slot,
            expected_species_id=plan.party_species_ids[plan.deposit_party_slot - 1],
        )
        if not report.passed:
            raise RedCapturePartyError("capture helper deposit failed")
    report_withdraw = withdraw_box_member(
        actions,
        reader,
        box_slot=plan.helper.box_slot,
        expected_species_id=plan.helper.species_id,
    )
    if not report_withdraw.passed:
        raise RedCapturePartyError("capture helper withdrawal failed")
    close_menu(actions, reader)
    after = reader.read()
    stored = reader.read_current_box_state()
    stored_all = _read_observed_box_species(plan, reader)
    if (
        Counter(
            (*(after.party_species_ids or ()), *(s for _, rows in stored_all for s in rows))
        ) != before
        or stored.box_index != plan.helper_box_index
        or after.bag_items != bag
        or after.player_money != money
        or after.battle_state != 0
        or not reader.read_input_readiness().ready
    ):
        raise RedCapturePartyError("capture preparation changed protected collection/resources")
    party = read_party()
    restoration: dict[str, object] = {}
    if not capture_party_ready(party) and restore_helper is not None:
        restoration = restore_helper()
        after = reader.read()
        stored = reader.read_current_box_state()
        stored_all = _read_observed_box_species(plan, reader)
        if (
            Counter(
                (*(after.party_species_ids or ()), *(s for _, rows in stored_all for s in rows))
            ) != before
            or stored.box_index != plan.helper_box_index
            or after.bag_items != bag
            or after.player_money != money
            or after.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise RedCapturePartyError("helper restoration changed protected collection/resources")
        party = read_party()
    if not capture_party_ready(party):
        diagnostic = explain_capture_party_unready(party, plan.helper)
        raise RedCapturePartyError(f"withdrawn capture helper is not actually ready: {diagnostic}")
    return {
        **restoration,
        "capture_party_prepared": True,
        "specimens_preserved": sum(before.values()),
        "box_rotations": rotations,
        "setup_training_rows": 0,
        "new_acquisitions": 0,
    }
