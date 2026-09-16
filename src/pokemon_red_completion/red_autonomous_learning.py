"""Admit durable autonomous choices as measured, training-only outcomes."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .goal_manager import GoalKind
from .living_dex_policy_codec import restore_living_dex_policy_menu
from .private_artifacts import PrivateArtifactRoot
from .provenance import canonical_sha256
from .red_development_measured_choice import (
    AUTONOMOUS_CHOICE_PARENT_KIND,
    AUTONOMOUS_CHOICE_PARENT_SCHEMA,
    DEVELOPMENT_MEASURED_CHOICE_KIND,
    DEVELOPMENT_MEASURED_MAXIMUM_ACTIONS,
    DEVELOPMENT_MEASURED_MAXIMUM_FRAMES,
    DEVELOPMENT_MEASURED_RESULT_SCHEMA,
    RedDevelopmentMeasuredChoice,
    RedDevelopmentMeasuredChoiceInput,
    RedDevelopmentMeasuredSegment,
    autonomous_choice_parent_record_id,
    publish_development_measured_choice,
)
from .red_economy_learning import red_registered_economy_outcome
from .red_live_option_menu import (
    RED_LIVE_AUTONOMOUS_EXECUTION_DECLARATION_SCHEMA,
    RED_LIVE_MIXED_OPTION_POLICY,
)
from .red_player_model import RedPlayerModelRecord
from .registered_collection import REGISTERED_OBJECTIVE
from .resource_economy_observation import EconomySnapshot

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"autonomous {subject} differs")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"autonomous {subject} differs")
    return value


def publish_autonomous_measured_choice(
    store: PrivateArtifactRoot,
    *,
    behavior: RedPlayerModelRecord,
    run_id: str,
    ordinal: int,
    intent: Mapping[str, object],
    decision: Mapping[str, object],
    outcome: Mapping[str, object],
    before_observation: Mapping[str, object],
    after_observation: Mapping[str, object],
    before_economy: EconomySnapshot,
    after_economy: EconomySnapshot,
    autonomous_plan_sha256: str,
    autonomous_result_sha256: str,
    intent_sha256: str,
    decision_sha256: str,
    outcome_sha256: str,
    source_commit: str,
    source_bundle_sha256: str,
    maximum_actions: int = DEVELOPMENT_MEASURED_MAXIMUM_ACTIONS,
    maximum_frames: int = DEVELOPMENT_MEASURED_MAXIMUM_FRAMES,
) -> tuple[RedDevelopmentMeasuredChoiceInput, dict[str, object]]:
    """Seal one already-played step without replaying or inventing an action trace."""
    if (
        not isinstance(behavior, RedPlayerModelRecord)
        or behavior.objective != REGISTERED_OBJECTIVE
        or not isinstance(run_id, str)
        or not run_id
        or type(ordinal) is not int
        or ordinal < 0
        or _COMMIT.fullmatch(source_commit) is None
        or maximum_actions != DEVELOPMENT_MEASURED_MAXIMUM_ACTIONS
        or maximum_frames != DEVELOPMENT_MEASURED_MAXIMUM_FRAMES
    ):
        raise ValueError("autonomous measured choice scope differs")
    for value, subject in (
        (autonomous_plan_sha256, "plan hash"),
        (autonomous_result_sha256, "result hash"),
        (intent_sha256, "intent hash"),
        (decision_sha256, "decision hash"),
        (outcome_sha256, "outcome hash"),
        (source_bundle_sha256, "source bundle"),
    ):
        _sha(value, subject)
    menu_outer = _mapping(intent.get("menu"), "menu")
    menu = restore_living_dex_policy_menu(_mapping(menu_outer.get("menu"), "policy menu"))
    selected_index = decision.get("selected_candidate_index")
    selection_seed = intent.get("selection_seed")
    probabilities = decision.get("probabilities")
    scores = decision.get("scores")
    if (
        type(selected_index) is not int
        or type(selection_seed) is not int
        or not isinstance(probabilities, list)
        or not isinstance(scores, list)
        or intent.get("state_sha256") != outcome.get("before_state_sha256")
        or intent.get("model_sha256") != behavior.model.model_sha256
        or decision.get("model_sha256") != behavior.model.model_sha256
        or decision.get("menu_sha256") != menu.policy_sha256
        or menu_outer.get("menu_sha256") != menu.policy_sha256
        or decision.get("mode") != "model_exploration"
        or decision.get("teacher_labels") != 0
        or decision.get("actions_executed") != 0
        or decision.get("emulator_frames") != 0
        or outcome.get("ordinal") != ordinal
        or outcome.get("choice") != decision
        or outcome.get("verification") != "succeeded"
        or outcome.get("error") is not None
        or outcome.get("error_type") is not None
        or outcome.get("safe_terminal") is not True
    ):
        raise ValueError("autonomous choice receipt differs")
    before = _mapping(outcome.get("before"), "before facts")
    after = _mapping(outcome.get("after"), "after facts")
    actions = after.get("actions")
    before_actions = before.get("actions")
    frames = after.get("frames")
    before_frames = before.get("frames")
    if (
        type(actions) is not int
        or type(before_actions) is not int
        or type(frames) is not int
        or type(before_frames) is not int
    ):
        raise ValueError("autonomous budget facts differ")
    actions -= before_actions
    frames -= before_frames
    if not 1 <= actions <= maximum_actions or not 0 <= frames <= maximum_frames:
        raise ValueError("autonomous choice exceeds measured budget")
    target_cash = menu.context.target_cash
    if type(target_cash) is not int:
        raise ValueError("autonomous choice target cash differs")
    selected_kind = GoalKind(str(outcome.get("selected_kind")))
    succeeded = True
    observed = red_registered_economy_outcome(
        before_observation,
        after_observation,
        selected_kind=selected_kind,
        succeeded=succeeded,
        actions=actions,
        frames=frames,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
        before_economy=before_economy,
        after_economy=after_economy,
        target_cash=target_cash,
    )
    choice_id = f"{run_id}:step-{ordinal:03d}"
    parent = {
        "schema": AUTONOMOUS_CHOICE_PARENT_SCHEMA,
        "choice_id": choice_id,
        "run_id": run_id,
        "ordinal": ordinal,
        "state_sha256": _sha(outcome.get("before_state_sha256"), "parent state"),
        "model_sha256": behavior.model.model_sha256,
        "collection": _mapping(before_observation.get("registration"), "registration"),
        "intent_sha256": intent_sha256,
        "autonomous_plan_sha256": autonomous_plan_sha256,
    }
    parent_record = store.publish_sealed_record(
        autonomous_choice_parent_record_id(choice_id),
        kind=AUTONOMOUS_CHOICE_PARENT_KIND,
        record=parent,
    )
    declaration = {
        "schema": RED_LIVE_AUTONOMOUS_EXECUTION_DECLARATION_SCHEMA,
        "run_id": run_id,
        "ordinal": ordinal,
        "autonomous_plan_sha256": autonomous_plan_sha256,
        "autonomous_result_sha256": autonomous_result_sha256,
        "intent_sha256": intent_sha256,
        "decision_sha256": decision_sha256,
        "outcome_sha256": outcome_sha256,
        "parent_checkpoint_sha256": parent_record.summary.record_sha256,
        "parent_state_sha256": parent["state_sha256"],
        "terminal_state_sha256": _sha(outcome.get("terminal_state_sha256"), "terminal state"),
        "menu_sha256": menu.policy_sha256,
        "model_sha256": behavior.model.model_sha256,
        "selected_candidate_index": selected_index,
        "selected_option_kind": decision.get("selected_option_kind"),
        "selection_seed": selection_seed,
        "behavior_probabilities": probabilities,
        "maximum_actions": maximum_actions,
        "maximum_frames": maximum_frames,
        "teacher_labels": 0,
        "retry_authorized": False,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle_sha256,
    }
    declaration_sha = canonical_sha256(declaration)
    segment = RedDevelopmentMeasuredSegment(
        pair_id=choice_id,
        declaration_sha256=declaration_sha,
        claim_sha256=intent_sha256,
        result_sha256=outcome_sha256,
        parent_state_sha256=str(parent["state_sha256"]),
        terminal_state_sha256=str(declaration["terminal_state_sha256"]),
        controller_actions=actions,
        emulator_frames=frames,
        status="retained_success",
    )
    choice = RedDevelopmentMeasuredChoice(
        choice_id=choice_id,
        parent_episode_id=run_id,
        parent_checkpoint_sha256=parent_record.summary.record_sha256,
        menu=menu,
        selected_candidate_index=selected_index,
        behavior_probabilities=tuple(float(value) for value in probabilities),
        scores=tuple(None if value is None else float(value) for value in scores),
        selection_seed=selection_seed,
        selection_declaration=declaration,
        selection_declaration_sha256=declaration_sha,
        model_sha256=behavior.model.model_sha256,
        before_observation=before_observation,
        after_observation=after_observation,
        before_observation_sha256=canonical_sha256(before_observation),
        after_observation_sha256=canonical_sha256(after_observation),
        parent_state_sha256=str(parent["state_sha256"]),
        terminal_state_sha256=str(declaration["terminal_state_sha256"]),
        segments=(segment,),
        segments_sha256=canonical_sha256([segment.public_dict()]),
        controller_actions=actions,
        emulator_frames=frames,
        resource_costs={
            "irreversible_loss": observed.irreversible_loss,
            "party_cost": observed.party_cost,
            "resource_cost": observed.resource_cost,
            "storage_cost": observed.storage_cost,
        },
        observer_source_commit=source_commit,
        observer_source_bundle_sha256=source_bundle_sha256,
        succeeded=True,
        selected_goal_kind=selected_kind,
        before_economy=before_economy,
        after_economy=after_economy,
        target_cash=target_cash,
        policy_id=RED_LIVE_MIXED_OPTION_POLICY,
    )
    measured = publish_development_measured_choice(store, choice, behavior)
    return measured, {
        "schema": DEVELOPMENT_MEASURED_RESULT_SCHEMA,
        "objective": REGISTERED_OBJECTIVE,
        "model_sha256": behavior.model.model_sha256,
        "choice_id": choice_id,
        "record_sha256": measured.record_sha256,
        "eligible_examples": 1,
        "action_trace_available": False,
        "authority_promotion_eligible": False,
        "teacher_labels": 0,
        "independent_evaluation": False,
        "choice_record_kind": DEVELOPMENT_MEASURED_CHOICE_KIND,
    }


__all__ = ["publish_autonomous_measured_choice"]
