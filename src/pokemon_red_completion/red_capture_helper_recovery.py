"""Explicit, metered Center restoration within a selected capture preparation.

Box storage is not healing. The caller must have actually withdrawn the helper;
this reuses the existing verified restore skill without querying a policy or
creating an extra training label.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.red_capture_party import RedCapturePartyError, capture_party_ready
from pokemon_red_completion.red_capture_preparation import prepare_capture_escort
from pokemon_red_completion.red_goal_skills import _POKEMON_CENTER_MAPS
from pokemon_red_completion.red_routed_recovery import bind_routed_center_recovery

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


def restore_capture_helper(router: RedResourceGoalRouter) -> dict[str, object]:
    """Heal once, visibly, at a Center; reject an unverified or still-unready result."""
    runtime = router.runtime
    observed = runtime.adapter.observe()
    if (
        not router.routed_recovery
        or not observed.input_ready
        or observed.raw.battle_state
        or observed.raw.map_id not in _POKEMON_CENTER_MAPS
    ):
        raise RedCapturePartyError("capture helper restoration needs settled Center control")
    before = router.actions.actions_executed, runtime.emulator.frame_count
    if capture_party_ready(observed.party):
        raise RedCapturePartyError("capture helper restoration was requested without need")

    def prepare_escort() -> None:
        prepare_capture_escort(runtime, router.actions)

    local = runtime.enumerator(router.actions).enumerate(observed)
    offers = bind_routed_center_recovery(
        router,
        local,
        observed,
        prepare_escort=prepare_escort,
        require_pp_restore=True,
    )
    restore = [binding for binding in offers.bindings if binding.kind is GoalKind.RESTORE_TEAM]
    if len(restore) != 1:
        raise RedCapturePartyError("capture helper has no executable Center restoration")
    report = restore[0].execute()
    verification = restore[0].verify(report)
    fresh = runtime.adapter.observe()
    if verification.status is not GoalDecisionOutcome.SUCCEEDED or not capture_party_ready(
        fresh.party
    ):
        raise RedCapturePartyError("capture helper Center restoration did not verify readiness")
    return {
        "capture_helper_restoration": {
            "verified": True,
            "actions": router.actions.actions_executed - before[0],
            "frames": runtime.emulator.frame_count - before[1],
            "setup_training_rows": 0,
        }
    }
