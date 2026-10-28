"""Native object-to-capture lifecycle for a declared limited-opportunity source."""

from __future__ import annotations

from dataclasses import dataclass

from .actions import MacroActionKind
from .battle_runtime import advance_battle_to_policy_boundary
from .observation import event_flag_is_set
from .red_one_off_capture import OneOffCaptureBudget, OneOffCaptureRequest, run_one_off_capture
from .red_static_capture import (
    RedStaticCaptureTarget,
    red_static_capture_targets,
    require_static_capture_admission,
)


@dataclass(frozen=True, slots=True)
class RedStaticCaptureResult:
    species_number: int
    captured: bool
    consumed_event: bool
    throws_committed: int
    source_removed: bool


def execute_static_capture(
    emulator,
    actions,
    reader,
    target: RedStaticCaptureTarget,
    request: OneOffCaptureRequest,
    *,
    rom: bytes,
    budget: OneOffCaptureBudget,
    before_throw=None,
    select_replacement=None,
    record_decision=None,
    commit_throw=None,
    prepare_encounter=None,
    allow_snorlax=False,
) -> RedStaticCaptureResult:
    """Interact once, retain any failure, and verify the native source lifecycle.

    A fresh interaction cannot reuse a partially spent budget. Continuations
    inside a retained battle use the one-off runtime, not another object press.
    No route or ball selection is owned by this deterministic executor.
    """
    from .surge import _pulse

    if type(allow_snorlax) is not bool:
        raise ValueError("Snorlax capture opt-in must be explicit")
    snorlax = False
    if allow_snorlax and target.species_number == 143:
        from .red_snorlax_capture import route12_snorlax_target

        snorlax = target == route12_snorlax_target(rom)
    if not snorlax and target not in red_static_capture_targets(rom):
        raise ValueError("static capture target differs from cartridge")
    budget.validate()
    if budget.request != request or budget.throws_committed:
        raise ValueError("static interaction requires its fresh declared allocation")
    require_static_capture_admission(
        reader,
        target,
        internal_species=request.internal_species,
        level=request.level,
        ball_id=int(request.ball),
        minimum_balls=budget.max_throws,
    )
    initial = reader.read()
    if dict(initial.bag_items or ()).get(int(request.ball), 0) != budget.initial_ball_count:
        raise ValueError("static capture allocation differs from bag")
    initial_boxes = reader.read_all_box_states()
    initial_dex = reader.read_pokedex_state()
    if snorlax:
        from .red_snorlax_capture import activate_snorlax

        activate_snorlax(actions, reader, emulator)
    else:
        _pulse(actions, MacroActionKind.INTERACT, frames=120)
    for _ in range(64):
        raw = reader.read()
        if (
            raw.map_id != initial.map_id
            or raw.player_money != initial.player_money
            or raw.bag_items != initial.bag_items
            or raw.party_species_ids != initial.party_species_ids
            or reader.read_all_box_states() != initial_boxes
            or reader.read_pokedex_state().owned_species != initial_dex.owned_species
            or reader.read_pokedex_state().seen_species
            not in (
                initial_dex.seen_species,
                initial_dex.seen_species | {target.species_number},
            )
            or raw.party_hp != initial.party_hp
            or raw.party_pp != initial.party_pp
            or raw.party_moves != initial.party_moves
            or raw.party_levels != initial.party_levels
            or raw.party_status != initial.party_status
            or (raw.player_y, raw.player_x) != (initial.player_y, initial.player_x)
        ):
            raise RuntimeError("static capture introduction changed protected state")
        if raw.battle_state == 1:
            break
        if raw.battle_state != 0:
            raise RuntimeError("static capture opened a non-wild battle")
        _pulse(actions, MacroActionKind.CONFIRM, frames=120)
    else:
        raise RuntimeError("static capture did not open its native battle")
    advance_battle_to_policy_boundary(
        reader,
        actions,
        expected_map=target.map_id,
        expected_battle_state=1,
        label="static capture introduction",
    )
    if prepare_encounter is not None and request.ball.value != 1:
        # This declared one-time preparation may reduce HP, unlike the repeated
        # nondamaging before_throw callback. Its executor owns damage bounds.
        # Protect source, target, inventory and collection again at this seam.
        prepared_from = reader.read()
        prepare_encounter()
        prepared = reader.read()
        identity = reader.read_wild_capture_identity()
        if (
            prepared.battle_state != 1
            or identity is None
            or identity.original_species_id != request.internal_species
            or prepared.enemy_level != request.level
            or prepared.enemy_hp is None
            or prepared_from.enemy_hp is None
            or not 0 < prepared.enemy_hp <= prepared_from.enemy_hp
            or prepared.map_id != initial.map_id
            or prepared.player_money != initial.player_money
            or prepared.bag_items != initial.bag_items
            or prepared.party_species_ids != initial.party_species_ids
            or reader.read_all_box_states() != initial_boxes
            or reader.read_pokedex_state().owned_species != initial_dex.owned_species
            or budget.throws_committed != 0
        ):
            raise RuntimeError("static capture initial preparation changed protected state")
    captured = run_one_off_capture(
        emulator,
        actions,
        reader,
        request,
        max_throws=budget.max_throws,
        budget=budget,
        before_throw=before_throw,
        select_replacement=select_replacement,
        record_decision=record_decision,
        commit_throw=commit_throw,
    )
    return settle_static_capture(
        actions,
        reader,
        target,
        captured=captured,
        budget=budget,
        initial_money=initial.player_money,
        initial_owned=initial_dex.owned_species,
    )


def settle_static_capture(
    actions,
    reader,
    target: RedStaticCaptureTarget,
    *,
    captured: bool,
    budget: OneOffCaptureBudget,
    initial_money: int | None,
    initial_owned: frozenset[int],
) -> RedStaticCaptureResult:
    """Finish a retained native encounter without pressing its object again.

    This is settlement only, not admission or authentication of a continuation.
    The caller must retain and authenticate its original source/allocation.
    """
    from .surge import _pulse

    terminal = reader.read()
    terminal_boxes = reader.read_all_box_states()
    terminal_pc = reader.read_pc_items()
    expected_dex = initial_owned | ({target.species_number} if captured else set())
    for _ in range(48):
        raw = reader.read()
        if (
            raw.map_id != target.map_id
            or raw.battle_state != 0
            or raw.player_money != initial_money
            or raw.bag_items != terminal.bag_items
            or raw.party_species_ids != terminal.party_species_ids
            or raw.party_hp != terminal.party_hp
            or raw.party_pp != terminal.party_pp
            or raw.party_moves != terminal.party_moves
            or raw.party_levels != terminal.party_levels
            or raw.party_status != terminal.party_status
            or reader.read_all_box_states() != terminal_boxes
            or reader.read_pc_items() != terminal_pc
            or reader.read_pokedex_state().owned_species != expected_dex
        ):
            raise RuntimeError("static capture field settlement changed protected state")
        if raw.event_flags is None:
            raise RuntimeError("static capture lacks final event evidence")
        consumed = event_flag_is_set(raw.event_flags, target.event_flag)
        removed = not any(
            o.sprite_index == target.object_index and o.visible
            for o in reader.read_current_map_objects()
        )
        if (
            consumed
            and removed
            and reader.read_input_readiness().ready
            and not reader.read_bottom_dialogue_box_visible()
        ):
            return RedStaticCaptureResult(
                target.species_number, captured, True, budget.throws_committed, True
            )
        _pulse(actions, MacroActionKind.CANCEL, frames=120)
    raise RuntimeError("static capture result lacks settled consumed-event/object proof")
