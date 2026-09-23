"""Bounded, recorded recovery-versus-next-goal choices at a field boundary.

Only the chosen recovery executes here. A selected next-goal binding is returned
to its caller, which retains ownership of that goal's execution and accounting.
No teacher fallback, purchasing, model update or automatic loss retry exists.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from .goal_manager import GoalDecisionOutcome, GoalKind, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from .living_dex_option_value import LivingDexOptionValueModel
from .provenance import canonical_sha256
from .red_autonomous_player import _record, _write
from .red_faint_recovery import RedFaintAwareFieldRestoreGoalProvider, plan_faint_aware_recovery
from .red_goal_manager import RedGoalObservation
from .red_live_option_menu import build_red_live_option_set, select_red_live_option


class RecoveryIntermissionError(ValueError):
    """No safe, authenticated continuation within the declared recovery budget."""


def run_recovery_intermission(
    *,
    model: LivingDexOptionValueModel,
    model_sha256: str,
    output: Path,
    recovery: RedFaintAwareFieldRestoreGoalProvider,
    next_goal: Callable[[RedGoalObservation], ExecutableGoalBinding | None],
    snapshot: Callable[[], bytes],
    seed: int,
    maximum_items: int,
    target_cash: int,
    on_verified_recovery: Callable[[object], None] | None = None,
) -> ExecutableGoalBinding:
    """Rebuild actual alternatives after every single-item outcome.

    Existing safety-mode choices are logged as such, never called model choices.
    Exhausted budget stops with the retained state; it cannot force the next fight.
    Both alternatives must be genuinely executable to query the learner.
    """
    if (
        not isinstance(model, LivingDexOptionValueModel)
        or model.model_sha256 != model_sha256
        or type(seed) is not int
        or seed < 0
        or type(maximum_items) is not int
        or not 0 <= maximum_items <= 12
        or type(target_cash) is not int
        or not 0 <= target_cash <= 999999
    ):
        raise RecoveryIntermissionError("recovery model identity or budget differs")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.recovery-intermission.v1",
            "model_sha256": model_sha256,
            "seed": seed,
            "maximum_items": maximum_items,
            "target_cash": target_cash,
            "model_updates": 0,
            "next_goal_execution_owned_by_caller": True,
        },
    )
    spent = 0
    selections = 0
    model_queries = 0
    try:
        while True:
            state = snapshot()
            observation = recovery.adapter.observe()
            if (
                not observation.input_ready
                or observation.raw.battle_state
                or recovery.emulator.pressed_buttons
            ):
                raise RecoveryIntermissionError("intermission is not a released field boundary")
            following = next_goal(observation)
            if following is not None and (
                not isinstance(following, ExecutableGoalBinding)
                or following.kind in {GoalKind.RESTORE_TEAM, GoalKind.RECOVER_CONTROL}
            ):
                raise RecoveryIntermissionError(
                    "next goal is not a distinct executable alternative"
                )
            offer = recovery.offer(observation)
            if snapshot() != state:
                raise RecoveryIntermissionError("intermission enumeration changed the game")
            step = output / f"step-{spent:02d}"
            step.mkdir(mode=0o700)
            _write(step / "before.state", state)
            if offer.binding is None:
                if offer.unavailable_reason not in {
                    GoalUnavailableReason.NO_LEGAL_TARGET,
                    GoalUnavailableReason.MISSING_RESOURCE,
                }:
                    raise RecoveryIntermissionError("recovery boundary is unavailable")
                if following is None:
                    raise RecoveryIntermissionError("no executable recovery or continuation")
                _record(
                    step / "selection.json",
                    {
                        "mode": "forced_singleton",
                        "selected_binding_ref": following.binding_ref,
                        "model_queries": 0,
                        "recovery_unavailable": str(offer.unavailable_reason),
                    },
                )
                return following
            if spent >= maximum_items:
                raise RecoveryIntermissionError("recovery item budget exhausted")
            if following is None:
                # No fictitious next battle is added to manufacture model authority.
                raise RecoveryIntermissionError("recovery has no executable competing goal")
            bindings = (offer.binding, following)
            economy = observation.economy_snapshot()
            if economy is None:
                raise RecoveryIntermissionError("recovery choice lacks observed cash or inventory")
            options = build_red_live_option_set(
                situation=observation.situation,
                binding_set=GoalBindingSet(tuple(b.opportunity for b in bindings), bindings),
                supplements=(),
                model_feature_version=model.feature_version,
                ordering_seed_sha256=canonical_sha256({"seed": seed, "step": spent}),
                economy_snapshot=economy,
                target_cash=target_cash,
            )
            selected = select_red_live_option(
                model, options, seed=seed + spent, exploration_mix=0.0
            )
            selections += 1
            choice_record = selected.public_dict()
            model_queries += int(choice_record["mode"] == "model_exploration")
            binding = options.binding(selected.selected_candidate_index)
            item_plan = plan_faint_aware_recovery(observation.raw)
            assert item_plan is not None
            _record(
                step / "selection.json",
                {
                    **choice_record,
                    "selected_binding_ref": binding.binding_ref,
                    "selected_goal_kind": binding.kind.value,
                    "menu": options.public_dict(),
                    "before_state_sha256": hashlib.sha256(state).hexdigest(),
                    "recovery_mechanic": asdict(item_plan),
                    "owned_item_consumption": 1,
                    "item_target_authority": "deterministic_skill",
                    "replacement_cost_qualified": False,
                },
            )
            if snapshot() != state:
                raise RecoveryIntermissionError("intermission selection changed the game")
            if binding is following:
                return following
            report = binding.execute()
            verdict = binding.verify(report)
            _record(
                step / "outcome.json",
                {
                    "report": {
                        "actions_executed": report.actions_executed,
                        "frames_executed": report.frames_executed,
                        "evidence": dict(report.evidence),
                    },
                    "verification": asdict(verdict),
                },
            )
            _write(step / "after.state", snapshot())
            if verdict.status is not GoalDecisionOutcome.SUCCEEDED:
                raise RecoveryIntermissionError("selected recovery failed verification")
            spent += 1
            if on_verified_recovery is not None:
                on_verified_recovery(report)
    except BaseException as error:
        _record(
            output / "failure.json",
            {"error_type": type(error).__name__, "error": str(error), "verified_items": spent},
        )
        raise
    finally:
        _write(output / "terminal.state", snapshot())
        _record(
            output / "terminal.json",
            {
                "verified_items": spent,
                "model_updates": 0,
                "selections": selections,
                "model_queries": model_queries,
                "next_goal_executed": False,
            },
        )
