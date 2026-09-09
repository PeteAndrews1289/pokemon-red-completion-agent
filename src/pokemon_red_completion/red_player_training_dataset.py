"""Admission of native player choices, separate from historical setup campaigns."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind, GoalSelectionMode
from pokemon_red_completion.goal_manager_trajectory import (
    GOAL_MANAGER_DECISION_TYPE,
    load_goal_manager_episode,
)
from pokemon_red_completion.living_dex_causal_journal import (
    restore_living_dex_observed_arm_example,
    restore_living_dex_observed_outcome,
)
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexCurriculumOutcomeExample,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionValueModel,
    LivingDexOutcomeStatus,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.living_dex_player_exploration import (
    LEGACY_RECOVERY_EXPLORATION_POLICY_ID,
    ExploringLivingDexGoalPolicy,
    exploration_policy_id,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot, PrivateEpisodeReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_adapter import (
    red_living_dex_outcome_from_observations,
)
from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id
from pokemon_red_completion.red_player_training import (
    CURRICULUM_EVENT,
    CURRICULUM_EVENT_SCHEMA,
    TRAINING_EVENT,
    TRAINING_EVENT_SCHEMA,
)
from pokemon_red_completion.red_player_training_plan import (
    COMPLETION_TRAINING_PLAN_SCHEMA,
    CONTINUATION_TRAINING_PLAN_SCHEMA,
    CURRICULUM_TRAINING_PLAN_SCHEMA,
    STORY_CURRICULUM_CONTRACT,
    RedPlayerTrainingPlan,
)


@dataclass(frozen=True, slots=True)
class RedPlayerTrainingDataset:
    examples: tuple[LivingDexObservedArmExample, ...]
    decisions: int
    excluded_nonexploratory: int
    excluded_zero_input: int
    episode_manifest_sha256: str
    plan_sha256: str
    curriculum_examples: tuple[LivingDexCurriculumOutcomeExample, ...] = ()


def load_red_player_training_episode(
    store: PrivateArtifactRoot,
    *,
    episode_id: str,
    expected_manifest_sha256: str,
    plan: RedPlayerTrainingPlan,
    behavior_model: LivingDexOptionValueModel,
) -> RedPlayerTrainingDataset:
    """Authenticate a complete episode, replay sampling, and reconstruct targets.

    This is known-training-root evidence, never an independent test. No emulator
    is opened here. Hashes establish recorded provenance, not ground-truth truth
    of an arbitrary external recording; only the trusted executor writes these.
    """
    _require_player_training_origin(store, episode_id, plan, behavior_model)
    return _audit_red_player_training_reader(
        store.open_episode(episode_id),
        episode_id=episode_id,
        expected_manifest_sha256=expected_manifest_sha256,
        plan=plan,
        behavior_model=behavior_model,
    )


def _require_player_training_origin(
    store: PrivateArtifactRoot,
    episode_id: str,
    plan: RedPlayerTrainingPlan,
    behavior_model: LivingDexOptionValueModel,
) -> None:
    """Keep declaration and parent checks before interpreting outcome streams."""
    legacy_restoration = (
        plan.document["behavior_policy_id"] == LEGACY_RECOVERY_EXPLORATION_POLICY_ID
    )
    if (
        plan.document["episode_id"] != episode_id
        or plan.document["model_sha256"] != behavior_model.model_sha256
        or plan.document["behavior_policy_id"]
        != exploration_policy_id(
            behavior_model.feature_version,
            legacy_restoration_preference=legacy_restoration,
        )
    ):
        raise ValueError("player training origin differs")
    sealed = store.find_sealed_record(
        f"rp-plan-{plan.plan_sha256}", expected_kind="red_player_training_plan"
    )
    if sealed is None or sealed.read() != dict(plan.document):
        raise ValueError("prospective player training declaration is missing")
    _require_continuation_origin(store, plan)


def _audit_red_player_training_reader(
    reader: PrivateEpisodeReader,
    *,
    episode_id: str,
    expected_manifest_sha256: str,
    plan: RedPlayerTrainingPlan,
    behavior_model: LivingDexOptionValueModel,
) -> RedPlayerTrainingDataset:
    """Shared recorded-choice checks; caller must authenticate origin and status.

    This private helper grants no fitting authority. The public loader requires
    a complete episode; failed-reader callers may expose diagnostics only.
    """
    legacy_restoration = (
        plan.document["behavior_policy_id"] == LEGACY_RECOVERY_EXPLORATION_POLICY_ID
    )
    if reader.manifest_sha256 != expected_manifest_sha256:
        raise ValueError("player training episode identity differs")
    metadata = cast(Mapping[str, object], reader.read_header()["metadata"])
    if (
        metadata.get("player_training_plan") != dict(plan.document)
        or metadata.get("player_training_plan_sha256") != plan.plan_sha256
        or metadata.get("teacher_queries") != 0
        or metadata.get("teacher_fallbacks") != 0
    ):
        raise ValueError("player training header differs")
    if any(
        metadata.get(key) != plan.document[key]
        for key in (
            "source_commit",
            "source_bundle_sha256",
            "state_sha256",
            "envelope_sha256",
            "profile_sha256",
            "model_sha256",
        )
    ):
        raise ValueError("player training inputs differ from its declaration")
    joined = load_goal_manager_episode(reader)
    if (
        joined.context_catalog_sha256 != plan.document["context_catalog_sha256"]
        or joined.context_id != plan.document["context_id"]
    ):
        raise ValueError("player training catalog origin differs")
    if len(joined.examples) > cast(int, plan.document["decision_limit"]):
        raise ValueError("player training decision bound differs")
    executions = (
        tuple(reader.iter_stream("executions")) if "executions" in reader.stream_names else ()
    )
    decision_steps = {
        item["decision_id"]: item["step_index"]
        for item in reader.iter_stream("decisions")
        if item.get("decision_type") == GOAL_MANAGER_DECISION_TYPE
    }
    outcome_steps: dict[str, object] = {}
    if any(
        item.partition != "train" or item.root_lineage_id != plan.document["root_lineage_id"]
        for item in joined.examples
    ):
        raise ValueError("player training partition differs")
    events: dict[str, Mapping[str, object]] = {}
    curriculum_events: dict[str, Mapping[str, object]] = {}
    for event in reader.iter_stream("events"):
        is_curriculum = event.get("kind") == CURRICULUM_EVENT
        if event.get("kind") not in {TRAINING_EVENT, CURRICULUM_EVENT}:
            continue
        if is_curriculum and plan.document["schema"] != CURRICULUM_TRAINING_PLAN_SCHEMA:
            raise ValueError("historical plan cannot admit curriculum outcomes")
        payload = _mapping(event.get("payload"))
        identity = payload.get("decision_id")
        if not isinstance(identity, str) or identity in events or identity in curriculum_events:
            raise ValueError("player training outcome is duplicated")
        if (
            payload.get("schema")
            != (CURRICULUM_EVENT_SCHEMA if is_curriculum else TRAINING_EVENT_SCHEMA)
            or payload.get("plan_sha256") != plan.plan_sha256
            or event.get("episode_id") != episode_id
        ):
            raise ValueError("player training outcome provenance differs")
        (curriculum_events if is_curriculum else events)[identity] = payload
        outcome_steps[identity] = event.get("step_index")
    policy = ExploringLivingDexGoalPolicy(
        behavior_model,
        seed=cast(int, plan.document["seed"]),
        legacy_restoration_preference=legacy_restoration,
    )
    examples = []
    curriculum_examples = []
    nonexploratory = zero_input = 0
    for decision in joined.examples:
        if plan.document["economic_contract"] == "known-spend-and-excess-reserve-v1" and any(
            option.resource_quote is not None
            and option.resource_quote.available_recovery_units is not None
            for option in decision.question.opportunities
        ):
            raise ValueError("historical economic contract cannot admit bounded consumption quotes")
        row: LivingDexObservedArmExample | LivingDexCurriculumOutcomeExample
        if decision.selection_mode is GoalSelectionMode.FORCED_SINGLETON:
            nonexploratory += 1
            eligible_story = (
                plan.document["schema"] == CURRICULUM_TRAINING_PLAN_SCHEMA
                and decision.question.opportunities[decision.selected_candidate_index].kind
                is GoalKind.ADVANCE_STORY
            )
            if not eligible_story:
                continue
            if (
                decision.question.available_indices != (decision.selected_candidate_index,)
                or decision.decision_id not in curriculum_events
            ):
                raise ValueError("curriculum story lacks its singleton observed outcome")
            payload = curriculum_events.pop(decision.decision_id)
            if (
                payload.get("curriculum_contract") != STORY_CURRICULUM_CONTRACT
                or type(payload.get("observation_failed")) is not bool
                or decision.behavior_policy_id is not None
                or decision.behavior_candidate_probabilities is not None
                or set(payload)
                != {
                    "schema",
                    "decision_id",
                    "plan_sha256",
                    "curriculum_contract",
                    "observation_failed",
                    "example",
                    "before",
                    "after",
                    "actions",
                    "frames",
                    "maximum_actions",
                    "maximum_frames",
                    "has_controller_input",
                    "start_step",
                    "end_step",
                }
            ):
                raise ValueError("curriculum contract differs")
            candidate = project_living_dex_goal_candidate(
                decision.question,
                decision.selected_candidate_index,
                feature_version=behavior_model.feature_version,
                binding_ref="curriculum-executed-option",
            )
            assert candidate is not None
            row = LivingDexCurriculumOutcomeExample(
                canonical_sha256(
                    {
                        "decision_id": decision.decision_id,
                        "plan_sha256": plan.plan_sha256,
                        "question_sha256": decision.question.ordered_policy_input_sha256,
                    }
                ),
                "train",
                behavior_model.feature_version,
                candidate.vector(
                    living_dex_option_context_from_goal_situation(decision.question.situation),
                    feature_version=behavior_model.feature_version,
                ),
                restore_living_dex_observed_outcome(
                    _mapping(_mapping(payload.get("example")).get("outcome"))
                ),
            )
            if canonical_sha256(row.public_dict()) != canonical_sha256(
                _mapping(payload.get("example"))
            ):
                raise ValueError("curriculum features or example differ from executed story")
        else:
            selection = policy.select(decision.question)
            expected_behavior = policy.selection_metadata()
            if (
                selection.selected_index != decision.selected_candidate_index
                or tuple(cast(list[float], expected_behavior["candidate_probabilities"]))
                != decision.behavior_candidate_probabilities
                or expected_behavior["behavior_policy_id"] != decision.behavior_policy_id
            ):
                raise ValueError("recorded choice does not replay from its declared behavior")
            if not policy.training_eligible:
                nonexploratory += 1
                continue
            if decision.decision_id not in events:
                raise ValueError("exploratory choice lacks its observed outcome")
            payload = events.pop(decision.decision_id)
            row = restore_living_dex_observed_arm_example(_mapping(payload.get("example")))
            if (
                row.menu != policy.last_menu
                or row.behavior_probabilities != policy.option_probabilities
                or payload.get("option_indices") != list(policy.last_menu_indices)
                or row.selected_candidate_index
                != policy.last_menu_indices.index(selection.selected_index)
                or row.partition != "train"
                or row.decision_sha256
                != canonical_sha256(
                    {
                        "decision_id": decision.decision_id,
                        "plan_sha256": plan.plan_sha256,
                        "question_sha256": decision.question.ordered_policy_input_sha256,
                    }
                )
            ):
                raise ValueError("player training menu or selected arm differs")
        actions, frames = payload.get("actions"), payload.get("frames")
        if (
            type(actions) is not int
            or type(frames) is not int
            or min(actions, frames) < 0
            or payload.get("has_controller_input") is not (actions > 0)
        ):
            raise ValueError("player training counters differ")
        if (
            payload.get("maximum_actions") != plan.maximum_actions
            or payload.get("maximum_frames") != plan.maximum_frames
        ):
            raise ValueError("player training dose differs")
        start, end = payload.get("start_step"), payload.get("end_step")
        if type(start) is not int or type(end) is not int or not 0 <= start <= end:
            raise ValueError("player training execution interval differs")
        if start != decision_steps.get(decision.decision_id) or end != outcome_steps.get(
            decision.decision_id
        ):
            raise ValueError("player training interval does not match its decision")
        trace = tuple(item for item in executions if start <= cast(int, item["step_index"]) < end)
        if len(trace) != actions or end - start != actions:
            raise ValueError("player training action count differs from its execution trace")
        recorded_frames = sum(cast(int, item["frames"]) for item in trace)
        if recorded_frames > frames or (
            all(item.get("status") == "success" for item in trace) and recorded_frames != frames
        ):
            raise ValueError("player training frames differ from its execution trace")
        if decision.outcome_status is GoalDecisionOutcome.INTERRUPTED:
            expected = LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
            )
            if payload.get("after") is not None or payload.get("observation_failed", False):
                raise ValueError("interrupted player choice has an invented after-state")
        elif isinstance(row, LivingDexCurriculumOutcomeExample) and payload["observation_failed"]:
            if payload.get("after") is not None:
                raise ValueError("unreadable curriculum has an invented after-state")
            expected = LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
            )
        else:
            expected = red_living_dex_outcome_from_observations(
                _mapping(payload.get("before")),
                _mapping(payload.get("after")),
                succeeded=decision.outcome_status is GoalDecisionOutcome.SUCCEEDED,
                actions=actions,
                frames=frames,
                maximum_actions=plan.maximum_actions,
                maximum_frames=plan.maximum_frames,
            )
        if row.outcome != expected:
            raise ValueError("player training target does not match observed evidence")
        if actions == 0:
            zero_input += 1
        elif isinstance(row, LivingDexCurriculumOutcomeExample):
            curriculum_examples.append(row)
        else:
            examples.append(row)
    if events or curriculum_events:
        raise ValueError("unselected or nonexploratory outcome was offered for training")
    return RedPlayerTrainingDataset(
        tuple(examples),
        len(joined.examples),
        nonexploratory,
        zero_input,
        reader.manifest_sha256,
        plan.plan_sha256,
        tuple(curriculum_examples),
    )


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("player training document must be a mapping")
    return value


def _require_continuation_origin(store: PrivateArtifactRoot, plan: RedPlayerTrainingPlan) -> None:
    """Join the new sampled episode to the completed saved parent, never its old choices."""
    if plan.document["schema"] not in {
        CONTINUATION_TRAINING_PLAN_SCHEMA,
        COMPLETION_TRAINING_PLAN_SCHEMA,
        CURRICULUM_TRAINING_PLAN_SCHEMA,
    }:
        return
    ancestor_id = cast(str, plan.document["continuation_episode_id"])
    record = store.find_sealed_record(
        checkpoint_record_id(ancestor_id),
        expected_kind=CHECKPOINT_KIND,
    )
    if (
        record is None
        or record.summary.record_sha256 != plan.document["continuation_checkpoint_sha256"]
    ):
        raise ValueError("continued training checkpoint differs")
    checkpoint = record.read()
    parent = store.open_episode(ancestor_id)
    metadata = _mapping(parent.read_header().get("metadata"))
    split = _mapping(metadata.get("split"))
    if (
        checkpoint.get("episode_id") != ancestor_id
        or checkpoint.get("trajectory_manifest_sha256") != parent.manifest_sha256
        or checkpoint.get("state_sha256") != plan.document["state_sha256"]
        or checkpoint.get("profile_sha256") != plan.document["restore_profile_sha256"]
        or split.get("partition") != "train"
        or split.get("root_lineage_id") != plan.document["root_lineage_id"]
    ):
        raise ValueError("continued training lineage or saved input differs")
