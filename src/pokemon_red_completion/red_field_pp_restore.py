"""One prospectively profiled, observed Elixir use; no new item supply or healing."""
from __future__ import annotations

from dataclasses import dataclass

from .actions import MacroActionKind
from .executor import CountingExecutor
from .field_recovery import EmulatorState
from .goal_manager import GoalFailureReason, GoalKind, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .lavender import (
    DEFAULT_LAVENDER_TIMING,
    _close_menus,
    _open_bag,
    _select_bag_item,
    _select_cursor,
)
from .observation import ItemId, PokemonRedStateReader
from .red_elixir_plan import RedElixirPlanError, plan_field_elixir, verify_field_elixir
from .red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalBindingOffer,
    RedGoalBindingProvider,
    RedGoalObservation,
)
from .victory_road import _pulse


class RedFieldPpRestoreError(RuntimeError):
    """A one-shot owned-item restoration failed without replay or replenishment."""


@dataclass(frozen=True, slots=True)
class RedCombinedFieldRestoreGoalProvider:
    """Prospective HP-then-PP offer composition, never execution-error fallback.

    The model chooses RESTORE_TEAM versus other goals; item/target selection is
    deterministic. Each offer preserves the selected provider's exact verifier.
    """

    hp_provider: RedGoalBindingProvider
    pp_provider: RedGoalBindingProvider
    kind: GoalKind = GoalKind.RESTORE_TEAM

    def __post_init__(self) -> None:
        if self.hp_provider.kind is not self.kind or self.pp_provider.kind is not self.kind:
            raise RedFieldPpRestoreError("combined recovery provider kinds differ")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        hp = self.hp_provider.offer(observation)
        if hp.binding is not None or hp.unavailable_reason not in {
            GoalUnavailableReason.NO_LEGAL_TARGET, GoalUnavailableReason.MISSING_RESOURCE,
        }:
            return hp
        return self.pp_provider.offer(observation)


@dataclass(slots=True)
class RedFieldPpRestoreGoalProvider:
    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: EmulatorState
    adapter: PokemonRedGoalStateAdapter
    kind: GoalKind = GoalKind.RESTORE_TEAM

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        if (
            observation.pp_restoration is None or not observation.input_ready
            or self.reader.read_bottom_dialogue_box_visible() or self.emulator.pressed_buttons
        ):
            return RedGoalBindingOffer.unavailable(
                self.kind, GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        try:
            plan = plan_field_elixir(observation.raw)
        except RedElixirPlanError:
            return RedGoalBindingOffer.unavailable(self.kind, GoalUnavailableReason.NO_LEGAL_TARGET)
        claimed = False
        receipt = {
            "schema": "pokemon.red.field-pp-restoration-receipt.v1",
            "bounded": True,
            "owned_items_consumed": 1,
            "party_index": plan.party_index,
            "before_pp": plan.before_pp,
            "after_pp": plan.after_pp,
            "slot_gains": plan.slot_gains,
            "restored_pp": plan.total_pp_restored,
            "target_selection": "deterministic_maximum_actual_pp_gain",
            "pp_gain_is_learned_target": False,
            "learned_authority": "goal_choice_only",
        }

        def execute() -> GoalExecutionReport:
            nonlocal claimed
            if claimed:
                raise RedFieldPpRestoreError("Elixir offer already consumed")
            claimed = True  # a stale/failed binding is never silently retried
            if (
                self.adapter.observe() != observation or self.emulator.pressed_buttons
                or self.reader.read_bottom_dialogue_box_visible()
                or not self.reader.read_input_readiness().ready
            ):
                raise RedFieldPpRestoreError("Elixir origin changed before controller input")
            start_actions = self.actions.actions_executed
            start_frames = self.emulator.frame_count
            timing = DEFAULT_LAVENDER_TIMING
            _open_bag(self.actions, self.emulator, timing)
            _select_bag_item(self.actions, self.emulator, ItemId.ELIXIR, timing)
            _pulse(self.actions, MacroActionKind.CONFIRM)
            _pulse(self.actions, MacroActionKind.CONFIRM, frames=240)
            _select_cursor(self.actions, self.emulator, plan.party_index, timing)
            _pulse(self.actions, MacroActionKind.CONFIRM)
            before_stock = dict(observation.raw.bag_items or ()).get(int(ItemId.ELIXIR), 0)
            for _ in range(24):
                current = self.reader.read()
                stock = dict(current.bag_items or ()).get(int(ItemId.ELIXIR), 0)
                if stock != before_stock:
                    # Never confirm again after ANY consumption or inventory anomaly.
                    verify_field_elixir(plan, observation.raw, current)
                    _close_menus(self.actions, self.reader, timing)
                    after = self.adapter.observe()
                    verify_field_elixir(plan, observation.raw, after.raw)
                    if not after.input_ready or self.emulator.pressed_buttons:
                        raise RedFieldPpRestoreError("Elixir did not settle with released controls")
                    return GoalExecutionReport(
                        actions_executed=self.actions.actions_executed - start_actions,
                        frames_executed=self.emulator.frame_count - start_frames,
                        evidence=dict(receipt),
                    )
                _pulse(self.actions, MacroActionKind.CONFIRM)
            raise RedFieldPpRestoreError("Elixir was not consumed within its bounded interaction")

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            try:
                verify_field_elixir(plan, observation.raw, after.raw)
            except RedElixirPlanError:
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if (
                not claimed or report.actions_executed <= 0 or not after.input_ready
                or report.evidence != receipt
                or self.emulator.pressed_buttons
                or after.collection_observation != observation.collection_observation
                or self.adapter.graph.completed_ids(after.game_state)
                != self.adapter.graph.completed_ids(observation.game_state)
            ):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(ExecutableGoalBinding(
            binding_ref="pokemon.red:recovery:one-owned-elixir",
            kind=self.kind, estimated_effort=0.08, estimated_risk=0.03,
            execute=execute, verify=verify,
        ))
