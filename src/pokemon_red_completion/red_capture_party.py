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
from pokemon_red_completion.party import PartyObservation, StatusCondition
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from pokemon_red_completion.red_capture_support import red_capture_status_options
from pokemon_red_completion.red_pc_storage import (
    deposit_party_member,
    face_pc_boundary,
    open_bills_pc,
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
    box_species_ids: tuple[int, ...]


def capture_party_ready(party: PartyObservation) -> bool:
    return choose_capture_status(
        party, red_capture_status_options(party),
        target_status=StatusCondition.HEALTHY, attempts_used=0,
    ) is not None


def plan_capture_party(
    party: PartyObservation, box: tuple[RedBoxMoveMember, ...], *, box_index: int,
) -> RedCapturePartyPlan | None:
    """Choose capabilities, not species; preserve every last field-move carrier."""
    if type(box_index) is not int or not 0 <= box_index < 12:
        raise ValueError("capture support current box differs")
    if tuple(row.box_slot for row in box) != tuple(range(1, len(box) + 1)):
        raise ValueError("capture support box slots are not contiguous")
    if capture_party_ready(party):
        return None
    if not any(member.hp > 0 for member in party.members):
        raise RedCapturePartyError("capture preparation needs a living escort")
    helpers = []
    for boxed in box:
        accuracy = [
            RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move)).accuracy
            for move, pp in zip(boxed.moves, boxed.pp, strict=True)
            if move and pp and RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(move))
        ]
        if accuracy:
            helpers.append((max(accuracy), boxed.level, -boxed.box_slot, boxed))
    if not helpers:
        raise RedCapturePartyError("no usable sleep/paralysis move in party or current box")
    helper = max(helpers, key=lambda row: row[:3])[3]
    deposit = None
    if len(party.members) == 6:
        if len(box) >= 20:
            raise RedCapturePartyError("capture helper substitution needs one free box slot")
        strongest = max(
            (member for member in party.members if member.hp > 0),
            key=lambda member: (member.level, member.hp), default=None,
        )
        if strongest is None:
            raise RedCapturePartyError("capture preparation needs a living escort")
        candidates = []
        for member in party.members:
            if member.slot == strongest.slot:
                continue
            known = {move.move_id for move in member.moves} & _FIELD_MOVES
            others = {move.move_id for other in party.members if other.slot != member.slot
                      for move in other.moves}
            if known - others:
                continue
            candidates.append(member)
        if not candidates:
            raise RedCapturePartyError("every party member is protected capture support")
        deposit = min(candidates, key=lambda member: (member.level, -member.slot)).slot
    return RedCapturePartyPlan(
        helper, deposit, tuple(member.species_id for member in party.members),
        tuple(tuple(move.move_id for move in member.moves) for member in party.members),
        box_index, tuple(member.species_id for member in box),
    )


def execute_capture_party_at_pc(
    plan: RedCapturePartyPlan, actions: CountingExecutor, reader: PokemonRedStateReader,
    *, pc_map_id: int, read_party: Callable[[], PartyObservation],
) -> dict[str, object]:
    """Execute only at a settled standard-center PC; no routing or hidden heal."""
    raw = reader.read()
    box = reader.read_current_box_state()
    moves = reader.read_current_box_move_members()
    if (
        (raw.map_id, raw.player_y, raw.player_x) != (pc_map_id, 4, 13)
        or raw.battle_state != 0 or not reader.read_input_readiness().ready
        or raw.party_species_ids != plan.party_species_ids
        or raw.party_moves != plan.party_moves
        or box.box_index != plan.current_box_index
        or box.species_ids != plan.box_species_ids
        or moves[plan.helper.box_slot - 1] != plan.helper
    ):
        raise RedCapturePartyError("capture helper plan differs before PC input")
    before = Counter((*plan.party_species_ids, *plan.box_species_ids))
    bag, money = raw.bag_items, raw.player_money
    face_pc_boundary(actions, reader, "up")
    open_bills_pc(actions, reader)
    if plan.deposit_party_slot is not None:
        report = deposit_party_member(
            actions, reader, party_slot=plan.deposit_party_slot,
            expected_species_id=plan.party_species_ids[plan.deposit_party_slot - 1],
        )
        if not report.passed:
            raise RedCapturePartyError("capture helper deposit failed")
    report_withdraw = withdraw_box_member(
        actions, reader, box_slot=plan.helper.box_slot,
        expected_species_id=plan.helper.species_id,
    )
    if not report_withdraw.passed:
        raise RedCapturePartyError("capture helper withdrawal failed")
    close_menu(actions, reader)
    after = reader.read()
    stored = reader.read_current_box_state()
    if (
        Counter((*(after.party_species_ids or ()), *stored.species_ids)) != before
        or stored.box_index != plan.current_box_index
        or after.bag_items != bag or after.player_money != money
        or after.battle_state != 0 or not reader.read_input_readiness().ready
    ):
        raise RedCapturePartyError("capture preparation changed protected collection/resources")
    party = read_party()
    if not capture_party_ready(party):
        raise RedCapturePartyError("withdrawn capture helper is not actually ready")
    return {"capture_party_prepared": True, "specimens_preserved": sum(before.values()),
            "setup_training_rows": 0, "new_acquisitions": 0}
