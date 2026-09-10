"""Audit retained failed forward attempts without granting fitting or replay authority.

The same sampled-choice, goal and cost validators serve complete and failed
records. Only the complete public loaders admit training outcomes. This module
returns an intentionally different diagnostic type: an observed failure of a
frozen controller is not evidence of a blackout or of optimal strategy.
"""

from dataclasses import dataclass
from typing import cast

from .forward_goal import ForwardGoalOutcome, ForwardGoalPlan, ForwardGoalTerminal
from .living_dex_option_value import LivingDexOptionValueModel
from .private_artifacts import PrivateArtifactRoot
from .red_failure_recovery import authenticated_failure_state
from .red_forward_dataset import _audit_red_forward_reader, _require_red_forward_scope
from .red_player_training_dataset import (
    _audit_red_player_training_reader,
    _require_player_training_origin,
)
from .red_player_training_plan import RedPlayerTrainingPlan


@dataclass(frozen=True, slots=True)
class RedForwardQuarantineDiagnostic:
    """Recorded evidence only; deliberately not a fit-compatible outcome."""

    manifest_sha256: str
    failure_state_sha256: str
    plan_sha256: str
    terminal: str
    observed_goal: bool | None
    recorded_return: tuple[float, float] | None
    prefix_cost: float
    actions: int
    frames: int
    resources: int
    macros: int
    sampled_training_rows: int
    excluded_nonexploratory_steps: int

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.forward-quarantine-diagnostic.v1",
            "episode_status": "failed",
            "admission": "quarantined-not-for-fitting",
            "manifest_sha256": self.manifest_sha256,
            "failure_state_sha256": self.failure_state_sha256,
            "plan_sha256": self.plan_sha256,
            "terminal": self.terminal,
            "observed_goal": self.observed_goal,
            "recorded_return": (
                list(self.recorded_return) if self.recorded_return is not None else None
            ),
            "prefix_cost": self.prefix_cost,
            "actions": self.actions,
            "frames": self.frames,
            "resources": self.resources,
            "macros": self.macros,
            "sampled_training_rows": self.sampled_training_rows,
            "excluded_nonexploratory_steps": self.excluded_nonexploratory_steps,
            "fitting_authorized": False,
            "checkpoint_authorized": False,
            "retry_authorized": False,
            "in_game_loss_inferred": False,
        }


def audit_failed_red_forward_episode(
    store: PrivateArtifactRoot,
    *,
    episode_id: str,
    expected_manifest_sha256: str,
    expected_failure_state_sha256: str,
    expected_rom_sha256: str,
    training_plan: RedPlayerTrainingPlan,
    behavior_model: LivingDexOptionValueModel,
    forward_plan: ForwardGoalPlan,
    objective_id: str,
) -> RedForwardQuarantineDiagnostic:
    """Authenticate a released failed capture and the entire recorded prefix.

    No emulator, input, prediction for future play, fitting, or artifact mutation
    occurs. Replaying the recorded sampler validates past choice probabilities.
    A missing/malformed terminal rejects rather than fabricating a negative row.
    An explicitly censored terminal remains unknown. A later checkpoint failure
    does not overwrite an already durable, authenticated forward observation.
    """
    diagnostic, _ = _audit_failed_forward(
        store,
        episode_id=episode_id,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_failure_state_sha256=expected_failure_state_sha256,
        expected_rom_sha256=expected_rom_sha256,
        training_plan=training_plan,
        behavior_model=behavior_model,
        forward_plan=forward_plan,
        objective_id=objective_id,
    )
    return diagnostic


def load_failed_red_forward_controller_return(
    store: PrivateArtifactRoot,
    *,
    episode_id: str,
    expected_manifest_sha256: str,
    expected_failure_state_sha256: str,
    expected_rom_sha256: str,
    training_plan: RedPlayerTrainingPlan,
    behavior_model: LivingDexOptionValueModel,
    forward_plan: ForwardGoalPlan,
    objective_id: str,
    return_contract: str,
) -> ForwardGoalOutcome:
    """Explicit forward-only admission of a known finite frozen-controller stop.

    This does not admit a failed episode to immediate/native training or make its
    save resumable. Callers must include the entire declared attempted batch.
    A censored/interrupted return cannot enter through this narrowly named path.
    """
    if return_contract != "finite-goal-under-frozen-controller.v1":
        raise ValueError("failed forward return requires the explicit controller contract")
    _, outcome = _audit_failed_forward(
        store,
        episode_id=episode_id,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_failure_state_sha256=expected_failure_state_sha256,
        expected_rom_sha256=expected_rom_sha256,
        training_plan=training_plan,
        behavior_model=behavior_model,
        forward_plan=forward_plan,
        objective_id=objective_id,
    )
    if outcome.terminal is not ForwardGoalTerminal.STOPPED or outcome.observed_goal is not False:
        raise ValueError("failed controller return must be a known finite goal stop")
    return outcome


def _audit_failed_forward(
    store: PrivateArtifactRoot,
    *,
    episode_id: str,
    expected_manifest_sha256: str,
    expected_failure_state_sha256: str,
    expected_rom_sha256: str,
    training_plan: RedPlayerTrainingPlan,
    behavior_model: LivingDexOptionValueModel,
    forward_plan: ForwardGoalPlan,
    objective_id: str,
) -> tuple[RedForwardQuarantineDiagnostic, ForwardGoalOutcome]:
    _require_red_forward_scope(training_plan, forward_plan, objective_id)
    _require_player_training_origin(store, episode_id, training_plan, behavior_model)
    reader = store.open_failed_episode(episode_id)
    immediate = _audit_red_player_training_reader(
        reader,
        episode_id=episode_id,
        expected_manifest_sha256=expected_manifest_sha256,
        plan=training_plan,
        behavior_model=behavior_model,
    )
    outcome = _audit_red_forward_reader(
        reader,
        immediate=immediate,
        training_plan=training_plan,
        forward_plan=forward_plan,
        objective_id=objective_id,
    )
    # The existing failure reader pins the same immutable manifest again and
    # authenticates the latest retained bytes and all no-resume flags.
    state = authenticated_failure_state(
        store,
        episode_id=episode_id,
        manifest_sha256=expected_manifest_sha256,
        state_sha256=expected_failure_state_sha256,
        parent_state_sha256=cast(str, training_plan.document["state_sha256"]),
        parent_envelope_sha256=cast(str, training_plan.document["envelope_sha256"]),
        profile_sha256=cast(str, training_plan.document["profile_sha256"]),
        rom_sha256=expected_rom_sha256,
    )
    if (
        type(state.get("actions")) is not int
        or type(state.get("frames")) is not int
        or any(
            state.get(flag) is not False
            for flag in ("safe_checkpoint", "admitted_continuation", "training_target")
        )
        or state["actions"] != outcome.counters.actions
        or state["frames"] != outcome.counters.frames
    ):
        raise ValueError("failed Red forward capture differs from its terminal prefix")
    diagnostic = RedForwardQuarantineDiagnostic(
        reader.manifest_sha256,
        expected_failure_state_sha256,
        forward_plan.sha256,
        outcome.terminal.value,
        outcome.observed_goal,
        outcome.target,
        outcome.counters.cost(outcome.plan),
        outcome.counters.actions,
        outcome.counters.frames,
        outcome.counters.resources,
        outcome.counters.macros,
        len(immediate.examples),
        immediate.excluded_nonexploratory,
    )
    return diagnostic, outcome
