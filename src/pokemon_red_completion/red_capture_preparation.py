"""Execute an observed escort swap without choosing a goal or fabricating a heal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_party_menu import swap_party_slots
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.red_capture_lead import RedCaptureLeadError, plan_capture_lead
from pokemon_red_completion.red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer, RedGoalObservation
from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider
from pokemon_red_completion.red_team_training import close_menu

if TYPE_CHECKING:
    from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


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


def require_capture_party(observation: RedGoalObservation) -> None:
    """Ordinary acquisition never inherits a fainted recovery passenger."""
    if (observation.raw.battle_state or not observation.input_ready
            or not observation.party.members or observation.party.fainted_count):
        raise RedCaptureLeadError("capture needs settled, living party before preparation")


def _prepared_binding(
    original: ExecutableGoalBinding, runtime: RedGoalContextRuntime,
    actions: CountingExecutor, observation: RedGoalObservation,
    rebind: Callable[[RedGoalObservation], ExecutableGoalBinding | None],
) -> ExecutableGoalBinding:
    executed: list[tuple[ExecutableGoalBinding, GoalExecutionReport]] = []
    claimed = False

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedCaptureLeadError("prepared capture binding already consumed")
        claimed = True
        before = runtime.adapter.observe()
        if before != observation:
            raise RedCaptureLeadError("capture preparation observation changed before input")
        require_capture_party(before)
        action_start, frame_start = actions.actions_executed, runtime.emulator.frame_count
        swapped = prepare_capture_escort(runtime, actions)
        fresh = runtime.adapter.observe()
        require_capture_party(fresh)
        selected = rebind(fresh)
        if selected is None or selected.kind is not original.kind:
            raise RedCaptureLeadError("prepared capture lost its selected goal")
        report = selected.execute()
        executed.append((selected, report))
        return GoalExecutionReport(
            actions.actions_executed - action_start,
            runtime.emulator.frame_count - frame_start,
            {**report.evidence, "escort_preparation": {
                "qualified": True, "swapped": swapped, "setup_training_rows": 0,
            }},
        )

    def verify(_report: GoalExecutionReport) -> GoalVerification:
        if len(executed) != 1:
            raise RedCaptureLeadError("prepared capture has no underlying execution")
        selected, report = executed[0]
        return selected.verify(report)

    return replace(original, execute=execute, verify=verify)


def bind_capture_escort(
    router: RedResourceGoalRouter, bindings: GoalBindingSet, observation: RedGoalObservation,
) -> GoalBindingSet:
    """Prepare before any capture/helper/storage travel, then rebind the same source."""
    original = next((b for b in bindings.bindings if b.kind is GoalKind.ACQUIRE_SPECIES), None)
    if original is None:
        return bindings
    from pokemon_red_completion.red_routed_capture_support import _without_capture
    try:
        require_capture_party(observation)
        plan_capture_lead(observation.party)
    except RedCaptureLeadError:
        return _without_capture(bindings, original)
    source = next(s for s in router.runtime.profile.providers if s.kind is original.kind)
    source_ref = f"pokemon.red:acquisition:{source.parameters['source_id']}"

    def rebind(fresh: RedGoalObservation) -> ExecutableGoalBinding | None:
        rebound = replace(router, prepare_capture_escort=False).enumerate(fresh)
        selected = next((b for b in rebound.bindings if b.kind is original.kind), None)
        if selected is not None and not (
            selected.search_source_ref == source_ref or selected.binding_ref == source_ref
            or selected.binding_ref.startswith(f"{source_ref}:profile-")
        ):
            raise RedCaptureLeadError("escort preparation changed selected source")
        return selected

    supported = _prepared_binding(original, router.runtime, router.actions, observation, rebind)
    return GoalBindingSet(bindings.opportunities, tuple(
        supported if b.binding_ref == original.binding_ref else b for b in bindings.bindings
    ))


@dataclass(frozen=True, slots=True)
class EscortPreparedCaptureProvider:
    """Requalify on arrival, after transport may have changed health or party state."""

    provider: RedAreaSurveyGoalProvider
    runtime: RedGoalContextRuntime
    actions: CountingExecutor
    kind: GoalKind = GoalKind.ACQUIRE_SPECIES

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        offer = self.provider.offer(observation)
        if offer.binding is None:
            return offer

        def rebind(fresh: RedGoalObservation) -> ExecutableGoalBinding | None:
            return self.provider.offer(fresh).binding

        return RedGoalBindingOffer.available(_prepared_binding(
            offer.binding, self.runtime, self.actions, observation, rebind,
        ))
