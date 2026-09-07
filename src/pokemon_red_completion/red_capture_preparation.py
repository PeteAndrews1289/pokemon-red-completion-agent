"""Execute an observed escort swap without choosing a goal or fabricating a heal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_party_menu import swap_party_slots
from pokemon_red_completion.red_capture_lead import RedCaptureLeadError, plan_capture_lead
from pokemon_red_completion.red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from pokemon_red_completion.red_team_training import close_menu

if TYPE_CHECKING:
    from pokemon_red_completion.red_goal_context import RedGoalContextRuntime


def prepare_capture_escort(runtime: RedGoalContextRuntime, actions: CountingExecutor) -> bool:
    """Prepare a capable lead for guarded recovery/transit, preserving all specimens.

    A returned False means the existing lead qualified, not refusal. This does
    not authorize capture with fainted teammates or choose the battle policy.
    """
    before = runtime.adapter.observe()
    if before.raw.battle_state or not before.input_ready:
        raise RedCaptureLeadError("escort preparation requires settled field control")
    plan = plan_capture_lead(before.party)
    ledger = dependency_specimen_ledger(before.collection_observation)
    if plan.requires_swap:
        close_menu(actions, runtime.reader)
        current = runtime.adapter.observe()
        plan.require_current(current.party)
        if (
            current.raw.battle_state or not current.input_ready
            or (current.raw.map_id, current.raw.player_x, current.raw.player_y)
            != (before.raw.map_id, before.raw.player_x, before.raw.player_y)
            or current.raw.bag_items != before.raw.bag_items
            or current.raw.player_money != before.raw.player_money
            or dependency_specimen_ledger(current.collection_observation) != ledger
        ):
            raise RedCaptureLeadError("escort state changed before swap")
        swap_party_slots(
            runtime.emulator, actions, runtime.reader,
            source_index=plan.target_index, destination_index=0,
            label="capability-derived recovery escort",
        )
    after = runtime.adapter.observe()
    plan.require_result(after.party)
    if (
        after.raw.battle_state or not after.input_ready
        or (after.raw.map_id, after.raw.player_x, after.raw.player_y)
        != (before.raw.map_id, before.raw.player_x, before.raw.player_y)
        or after.raw.bag_items != before.raw.bag_items
        or after.raw.player_money != before.raw.player_money
        or dependency_specimen_ledger(after.collection_observation) != ledger
    ):
        raise RedCaptureLeadError("escort swap changed protected state or field control")
    return plan.requires_swap
