"""Title-neutral contract for learning acquisition followed by replanning.

The curriculum is intentionally separate from execution.  It freezes a repeatable,
fixed-denominator experiment that can later collect causal goal-manager outcomes without
turning one successful Red capture into a claim of full-game or cross-title competence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerQuestion,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetMeter,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
    require_living_collection_transition,
)
from pokemon_red_completion.goal_manager_development import (
    DEVELOPMENT_BEHAVIOR_POLICY_ID,
    DEVELOPMENT_EXPLORATION_MIX,
    DEVELOPMENT_MAX_IMPORTANCE_WEIGHT,
    DEVELOPMENT_TEMPERATURE,
    ExploratoryGoalManagerPolicy,
    GoalManagerDevelopmentResult,
    GoalManagerDevelopmentTarget,
    _collection_checkpoint,
    _integer_field,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerScorer,
    canonical_goal_manager_model_record_sha256,
)
from pokemon_red_completion.goal_manager_runtime import execute_goal_manager_decision
from pokemon_red_completion.goal_manager_trajectory import (
    CollectedGoalManagerDataset,
    GoalEpisodeReader,
    GoalManagerTrajectoryError,
    GoalManagerTrajectoryObserver,
    load_goal_manager_episode,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID

ACQUISITION_REPLANNING_SCHEMA = (
    "pokemon.core.acquisition-replanning-curriculum.v1"
)
ACQUISITION_REPLANNING_ROOTS = 4
ACQUISITION_REPLANNING_TRIALS_PER_ROOT = 4
ACQUISITION_REPLANNING_EPISODES = (
    ACQUISITION_REPLANNING_ROOTS * ACQUISITION_REPLANNING_TRIALS_PER_ROOT
)
ACQUISITION_REPLANNING_MAX_DECISIONS = 2
ACQUISITION_REPLANNING_MIN_POST_CHOICES = 2
ACQUISITION_REPLANNING_MIN_ADMITTED_ACQUISITIONS = 4
ACQUISITION_REPLANNING_MIN_REPLANS = 4
ACQUISITION_REPLANNING_MIN_REPLAN_ROOTS = 3


class AcquisitionReplanningCurriculumError(ValueError):
    """Raised when a proposed curriculum weakens the frozen learning question."""


@dataclass(frozen=True, slots=True)
class AssignedGoalIntervention:
    """Select one frozen semantic intervention without consulting a model."""

    kind: GoalKind

    def __post_init__(self) -> None:
        if self.kind not in {
            GoalKind.ACQUIRE_SPECIES,
            GoalKind.DEVELOP_TEAM,
            GoalKind.EXPLORE,
        }:
            raise AcquisitionReplanningCurriculumError(
                "assigned intervention kind is outside the frozen schedule"
            )

    def select(self, question: GoalManagerQuestion) -> BoundGoalSelection:
        if not isinstance(question, GoalManagerQuestion):
            raise TypeError("question must be a GoalManagerQuestion")
        matches = tuple(
            index
            for index in question.available_indices
            if question.opportunities[index].kind is self.kind
        )
        if len(matches) != 1:
            raise AcquisitionReplanningCurriculumError(
                "assigned intervention is not uniquely executable"
            )
        return bind_goal_selection(question, matches[0])


@dataclass(frozen=True, slots=True)
class AcquisitionReplanningStep:
    """One independently verified step with an explicit learning-role boundary."""

    decision_ordinal: int
    selected_kind: GoalKind
    status: GoalDecisionOutcome
    learner_target_eligible: bool
    behavior_probability: float | None
    base_probability: float | None
    available_goal_count: int
    actions_executed: int
    frames_executed: int
    semantic_state_changed: bool
    policy_context_sha256: str
    available_menu_sha256: str
    collection_before: LivingCollectionCheckpoint
    collection_after: LivingCollectionCheckpoint

    def public_dict(self) -> dict[str, object]:
        collection_before = self.collection_before.public_dict()
        collection_before["specimen_counts"] = [
            list(item) for item in self.collection_before.specimen_counts
        ]
        collection_after = self.collection_after.public_dict()
        collection_after["specimen_counts"] = [
            list(item) for item in self.collection_after.specimen_counts
        ]
        return {
            "actions_executed": self.actions_executed,
            "available_goal_count": self.available_goal_count,
            "available_menu_sha256": self.available_menu_sha256,
            "base_probability": self.base_probability,
            "behavior_probability": self.behavior_probability,
            "collection_after": collection_after,
            "collection_before": collection_before,
            "decision_ordinal": self.decision_ordinal,
            "frames_executed": self.frames_executed,
            "learner_target_eligible": self.learner_target_eligible,
            "policy_context_sha256": self.policy_context_sha256,
            "selected_kind": self.selected_kind.value,
            "semantic_state_changed": self.semantic_state_changed,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class AcquisitionReplanningRunResult:
    """Settled intervention plus at most one model-led changed-state decision."""

    model_sha256: str
    seed: int
    assigned_intervention: GoalKind
    steps: tuple[AcquisitionReplanningStep, ...]
    stopped_reason: str

    @property
    def learner_targets(self) -> int:
        return sum(step.learner_target_eligible for step in self.steps)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.acquisition-replanning-result.v1",
            "status": "durable_terminal",
            "model_sha256": self.model_sha256,
            "seed": self.seed,
            "assigned_intervention": self.assigned_intervention.value,
            "decisions": len(self.steps),
            "assigned_dispatches": min(1, len(self.steps)),
            "learner_targets": self.learner_targets,
            "selected_goal_kinds": [step.selected_kind.value for step in self.steps],
            "steps": [step.public_dict() for step in self.steps],
            "stopped_reason": self.stopped_reason,
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
        }


@dataclass(frozen=True, slots=True)
class AdmittedAcquisitionReplanningEpisode:
    """Strict durable admission with only the model-led second choice as a target."""

    dataset: CollectedGoalManagerDataset
    assigned_intervention: GoalKind
    stopped_reason: str
    targets: tuple[GoalManagerDevelopmentTarget, ...]


def load_acquisition_replanning_episode(
    reader: GoalEpisodeReader,
    *,
    expected_campaign_id: str,
    expected_trial_claim_sha256: str,
    expected_episode_id: str,
    expected_root_lineage_id: str,
    expected_seed: int,
    expected_execution_identity_sha256: str,
    expected_context_catalog_sha256: str,
    expected_context_id: str,
    expected_binding_manifest_sha256: str,
    expected_state_sha256: str,
    expected_envelope_sha256: str,
    expected_first_question_sha256: str,
    expected_first_policy_context_sha256: str,
    expected_first_available_menu_sha256: str,
    expected_assigned_intervention: GoalKind,
    expected_model: GoalManagerScorer,
    expected_source_commit: str,
) -> AdmittedAcquisitionReplanningEpisode:
    """Authenticate one retained episode without teaching the assigned first action."""

    try:
        dataset = load_goal_manager_episode(reader)
    except GoalManagerTrajectoryError as error:
        raise AcquisitionReplanningCurriculumError(str(error)) from error
    if (
        dataset.partition != "development"
        or dataset.actor != "acquisition_replanning_mixed_policy"
        or dataset.policy_id != "red-acquisition-replanning-development-v1"
        or dataset.environment_id != RED_COLLECTION_GAME_ID
        or dataset.collection_id != expected_campaign_id
        or dataset.assignment_id != expected_trial_claim_sha256
        or dataset.episode_id != expected_episode_id
        or dataset.root_lineage_id != expected_root_lineage_id
        or dataset.context_catalog_sha256 != expected_context_catalog_sha256
        or dataset.context_id != expected_context_id
        or dataset.binding_manifest_sha256 != expected_binding_manifest_sha256
        or dataset.capture_state_sha256 != expected_state_sha256
        or dataset.capture_envelope_sha256 != expected_envelope_sha256
        or dataset.source_commit != expected_source_commit
        or not 1 <= len(dataset.examples) <= 2
    ):
        raise AcquisitionReplanningCurriculumError("episode provenance differs")
    first = dataset.examples[0]
    if (
        first.decision_index != 0
        or first.selected_kind is not expected_assigned_intervention
        or first.question.ordered_policy_input_sha256
        != expected_first_question_sha256
        or first.question.policy_context_sha256
        != expected_first_policy_context_sha256
        or first.question.available_menu_sha256
        != expected_first_available_menu_sha256
        or first.behavior_policy_id is not None
        or first.behavior_probability is not None
        or first.behavior_candidate_probabilities is not None
        or first.behavior_base_probability is not None
        or first.behavior_exploration_mix is not None
        or first.behavior_temperature is not None
    ):
        raise AcquisitionReplanningCurriculumError(
            "assigned intervention evidence differs"
        )
    first_succeeded = first.outcome_status is GoalDecisionOutcome.SUCCEEDED
    if (first_succeeded and len(dataset.examples) != 2) or (
        not first_succeeded and len(dataset.examples) != 1
    ):
        raise AcquisitionReplanningCurriculumError(
            "episode decision count differs from the runtime branch"
        )
    if any(
        example.decision_id
        != f"{expected_episode_id}:goal-manager:{example.decision_index}"
        for example in dataset.examples
    ):
        raise AcquisitionReplanningCurriculumError("decision identity differs")
    expected_model_sha256 = canonical_goal_manager_model_record_sha256(
        expected_model.to_dict()
    )
    targets: list[GoalManagerDevelopmentTarget] = []
    if len(dataset.examples) == 2:
        second = dataset.examples[1]
        if (
            second.decision_index != 1
            or len(second.question.available_indices)
            < ACQUISITION_REPLANNING_MIN_POST_CHOICES
            or any(
                second.question.opportunities[index].kind
                is GoalKind.EVOLVE_SPECIES
                for index in second.question.available_indices
            )
            or second.behavior_policy_id != DEVELOPMENT_BEHAVIOR_POLICY_ID
            or second.behavior_probability is None
            or second.behavior_candidate_probabilities is None
            or second.behavior_base_probability is None
            or second.behavior_exploration_mix != DEVELOPMENT_EXPLORATION_MIX
            or second.behavior_temperature != DEVELOPMENT_TEMPERATURE
        ):
            raise AcquisitionReplanningCurriculumError(
                "model-led replan propensity differs"
            )
        replay = ExploratoryGoalManagerPolicy(expected_model, seed=expected_seed)
        selected = replay.select(second.question)
        metadata = replay.selection_metadata()
        if (
            selected.selected_index != second.selected_candidate_index
            or metadata.get("behavior_policy_id") != second.behavior_policy_id
            or metadata.get("selected_probability") != second.behavior_probability
            or tuple(cast(list[float], metadata.get("candidate_probabilities")))
            != second.behavior_candidate_probabilities
            or metadata.get("base_selected_probability")
            != second.behavior_base_probability
            or metadata.get("exploration_mix") != second.behavior_exploration_mix
            or metadata.get("temperature") != second.behavior_temperature
        ):
            raise AcquisitionReplanningCurriculumError(
                "model-led replan does not replay exactly"
            )
        if second.outcome_status is not GoalDecisionOutcome.INTERRUPTED:
            probability = float(second.behavior_probability)
            targets.append(
                GoalManagerDevelopmentTarget(
                    decision_id=second.decision_id,
                    selected_candidate_index=second.selected_candidate_index,
                    reward=(
                        1.0
                        if second.outcome_status is GoalDecisionOutcome.SUCCEEDED
                        else -1.0
                    ),
                    behavior_probability=probability,
                    importance_weight=min(
                        DEVELOPMENT_MAX_IMPORTANCE_WEIGHT,
                        1.0 / probability,
                    ),
                )
            )
    header = _mapping(reader.read_header(), "episode header")
    metadata = _mapping(header.get("metadata"), "episode metadata")
    goal_metadata = _mapping(metadata.get("goal_manager"), "goal metadata")
    contract = _mapping(
        metadata.get("acquisition_replanning"),
        "acquisition-replanning contract",
    )
    if (
        goal_metadata.get("execution_identity_sha256")
        != expected_execution_identity_sha256
        or contract.get("assigned_intervention")
        != expected_assigned_intervention.value
        or contract.get("behavior_contract")
        != acquisition_replanning_behavior_contract()
        or contract.get("first_decision_is_model_prediction") is not False
        or contract.get("learner_target_decision_indices") != [1]
        or contract.get("maximum_decisions") != 2
    ):
        raise AcquisitionReplanningCurriculumError("episode contract differs")
    terminals = [
        _mapping(row, "episode terminal")
        for row in reader.iter_stream("events")
        if row.get("kind") == "terminal"
    ]
    if len(terminals) != 1:
        raise AcquisitionReplanningCurriculumError(
            "episode needs exactly one durable terminal"
        )
    terminal = terminals[0]
    if (
        terminal.get("event_id") != f"{expected_episode_id}:terminal"
        or terminal.get("episode_id") != expected_episode_id
    ):
        raise AcquisitionReplanningCurriculumError("terminal identity differs")
    payload = _mapping(terminal.get("payload"), "terminal payload")
    if payload.get("status") != "complete":
        raise AcquisitionReplanningCurriculumError("episode terminal is not complete")
    result = _mapping(
        payload.get("acquisition_replanning"),
        "terminal result",
    )
    steps = result.get("steps")
    if (
        result.get("schema") != "pokemon.red.acquisition-replanning-result.v1"
        or result.get("status") != "durable_terminal"
        or result.get("model_sha256") != expected_model_sha256
        or result.get("seed") != expected_seed
        or result.get("assigned_intervention")
        != expected_assigned_intervention.value
        or result.get("decisions") != len(dataset.examples)
        or result.get("assigned_dispatches") != 1
        or result.get("learner_targets") != len(targets)
        or result.get("selected_goal_kinds")
        != [example.selected_kind.value for example in dataset.examples]
        or not isinstance(steps, list)
        or len(steps) != len(dataset.examples)
        or result.get("teacher_queries") != 0
        or result.get("teacher_fallbacks") != 0
    ):
        raise AcquisitionReplanningCurriculumError("terminal result differs")
    transitions: list[tuple[LivingCollectionCheckpoint, LivingCollectionCheckpoint]] = []
    for index, (example, raw_step) in enumerate(
        zip(dataset.examples, steps, strict=True)
    ):
        step = _mapping(raw_step, "terminal step")
        expected_behavior = None if index == 0 else example.behavior_probability
        expected_base = None if index == 0 else example.behavior_base_probability
        if (
            step.get("decision_ordinal") != index + 1
            or step.get("selected_kind") != example.selected_kind.value
            or step.get("status") != example.outcome_status.value
            or step.get("learner_target_eligible") is not (index == 1)
            or step.get("behavior_probability") != expected_behavior
            or step.get("base_probability") != expected_base
            or (
                example.outcome_status is GoalDecisionOutcome.SUCCEEDED
                and step.get("semantic_state_changed") is not True
            )
        ):
            raise AcquisitionReplanningCurriculumError("terminal step differs")
        before = _collection_checkpoint(
            step.get("collection_before"),
            subject="acquisition-replanning collection before",
        )
        after = _collection_checkpoint(
            step.get("collection_after"),
            subject="acquisition-replanning collection after",
        )
        require_living_collection_transition(
            before,
            after,
            selected_kind=example.selected_kind,
            require_selected_goal_progress=(
                example.outcome_status is GoalDecisionOutcome.SUCCEEDED
            ),
        )
        if transitions and transitions[-1][1] != before:
            raise AcquisitionReplanningCurriculumError(
                "collection continuity differs"
            )
        transitions.append((before, after))
    if len(dataset.examples) == 2 and (
        dataset.examples[0].question.policy_context_sha256
        == dataset.examples[1].question.policy_context_sha256
        or dataset.examples[0].question.available_menu_sha256
        == dataset.examples[1].question.available_menu_sha256
    ):
        raise AcquisitionReplanningCurriculumError(
            "changed-state replanning evidence differs"
        )
    execution_rows = [
        _mapping(row, "execution row") for row in reader.iter_stream("executions")
    ]
    actions = [
        _integer_field(step, "actions_executed", subject="terminal step")
        for step in cast(list[Mapping[str, object]], steps)
    ]
    frames = [
        _integer_field(step, "frames_executed", subject="terminal step")
        for step in cast(list[Mapping[str, object]], steps)
    ]
    execution_frames = [
        _integer_field(row, "frames", subject="execution row")
        for row in execution_rows
    ]
    if (
        any(value > 6_000 for value in actions)
        or any(value > 600_000 for value in frames)
        or sum(actions) > 12_000
        or sum(frames) > 1_200_000
        or sum(actions) != len(execution_rows)
        or sum(frames) != sum(execution_frames)
    ):
        raise AcquisitionReplanningCurriculumError("budget evidence differs")
    stopped_reason = result.get("stopped_reason")
    expected_stop = (
        "assigned_intervention_failed"
        if first.outcome_status is not GoalDecisionOutcome.SUCCEEDED
        else "verified_failure"
        if len(dataset.examples) == 2
        and dataset.examples[1].outcome_status is not GoalDecisionOutcome.SUCCEEDED
        else "decision_limit"
    )
    if stopped_reason != expected_stop:
        raise AcquisitionReplanningCurriculumError("stop reason differs")
    return AdmittedAcquisitionReplanningEpisode(
        dataset=dataset,
        assigned_intervention=expected_assigned_intervention,
        stopped_reason=expected_stop,
        targets=tuple(targets),
    )


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AcquisitionReplanningCurriculumError(f"{subject} is invalid")
    return value


def run_acquisition_replanning_episode(
    *,
    observe: Callable[[], GoalManagerCompositionObservation],
    assigned_intervention: GoalKind,
    policy: ExploratoryGoalManagerPolicy,
    trajectory: GoalManagerTrajectoryObserver,
    budget_meter: CompositionBudgetMeter,
) -> AcquisitionReplanningRunResult:
    """Execute one frozen intervention and one later model-led semantic choice."""

    if not callable(observe):
        raise TypeError("observe must be callable")
    if not isinstance(policy, ExploratoryGoalManagerPolicy):
        raise TypeError("policy must be an ExploratoryGoalManagerPolicy")
    if not isinstance(trajectory, GoalManagerTrajectoryObserver):
        raise TypeError("trajectory must be a GoalManagerTrajectoryObserver")
    if not isinstance(budget_meter, CompositionBudgetMeter):
        raise TypeError("budget_meter must be a CompositionBudgetMeter")
    if policy.decisions != 0 or trajectory.next_decision_index != 0:
        raise AcquisitionReplanningCurriculumError("episode must start unused")
    intervention = AssignedGoalIntervention(assigned_intervention)
    initial_budget = budget_meter.checkpoint()
    current = _composition_observation(observe())
    if budget_meter.checkpoint() != initial_budget:
        raise AcquisitionReplanningCurriculumError(
            "initial observation attempted emulator work"
        )
    initial_question = trajectory.ordered_question(
        current.situation,
        current.binding_set.opportunities,
    )
    required = {
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.DEVELOP_TEAM,
        GoalKind.EXPLORE,
    }
    initial_kinds = {
        initial_question.opportunities[index].kind
        for index in initial_question.available_indices
    }
    if len(initial_question.available_indices) < 3 or not required.issubset(
        initial_kinds
    ):
        raise AcquisitionReplanningCurriculumError(
            "initial intervention menu differs from the frozen contract"
        )
    first = execute_goal_manager_decision(
        situation=current.situation,
        binding_set=current.binding_set,
        authority=intervention,
        trajectory=trajectory,
        require_durable_decision=True,
    )
    if not first.decision_recorded or not first.outcome_recorded or first.execution is None:
        raise AcquisitionReplanningCurriculumError(
            "assigned intervention was not durably settled"
        )
    after_first = _composition_observation(observe())
    first_budget = budget_meter.checkpoint()
    first_actions = first_budget.controller_actions - initial_budget.controller_actions
    first_frames = first_budget.emulator_frames - initial_budget.emulator_frames
    if (
        first_actions != first.execution.actions_executed
        or first_frames != first.execution.frames_executed
    ):
        raise AcquisitionReplanningCurriculumError(
            "assigned intervention budget evidence differs"
        )
    require_living_collection_transition(
        current.collection,
        after_first.collection,
        selected_kind=first.selected_kind,
        require_selected_goal_progress=first.passed,
    )
    first_changed = after_first.semantic_state_sha256 != current.semantic_state_sha256
    steps = [
        AcquisitionReplanningStep(
            decision_ordinal=1,
            selected_kind=first.selected_kind,
            status=first.verification.status,
            learner_target_eligible=False,
            behavior_probability=None,
            base_probability=None,
            available_goal_count=len(initial_question.available_indices),
            actions_executed=first_actions,
            frames_executed=first_frames,
            semantic_state_changed=first_changed,
            policy_context_sha256=initial_question.policy_context_sha256,
            available_menu_sha256=initial_question.available_menu_sha256,
            collection_before=current.collection,
            collection_after=after_first.collection,
        )
    ]
    if not first.passed:
        trajectory.require_settled()
        return AcquisitionReplanningRunResult(
            model_sha256=policy.model_sha256,
            seed=policy.seed,
            assigned_intervention=assigned_intervention,
            steps=tuple(steps),
            stopped_reason="assigned_intervention_failed",
        )
    if not first_changed:
        raise AcquisitionReplanningCurriculumError(
            "successful assigned intervention did not change semantic state"
        )

    second_question = trajectory.ordered_question(
        after_first.situation,
        after_first.binding_set.opportunities,
    )
    if (
        len(second_question.available_indices) < ACQUISITION_REPLANNING_MIN_POST_CHOICES
        or second_question.policy_context_sha256
        == initial_question.policy_context_sha256
        or second_question.available_menu_sha256
        == initial_question.available_menu_sha256
    ):
        raise AcquisitionReplanningCurriculumError(
            "changed-state replanning menu differs from the frozen contract"
        )
    if any(
        second_question.opportunities[index].kind is GoalKind.EVOLVE_SPECIES
        for index in second_question.available_indices
    ):
        raise AcquisitionReplanningCurriculumError(
            "replanning evolution requires a separate retained-lineage contract"
        )
    second = execute_goal_manager_decision(
        situation=after_first.situation,
        binding_set=after_first.binding_set,
        authority=policy,
        trajectory=trajectory,
        require_durable_decision=True,
    )
    if (
        not second.decision_recorded
        or not second.outcome_recorded
        or second.execution is None
    ):
        raise AcquisitionReplanningCurriculumError(
            "model-led replan was not durably settled"
        )
    after_second = _composition_observation(observe())
    second_budget = budget_meter.checkpoint()
    second_actions = second_budget.controller_actions - first_budget.controller_actions
    second_frames = second_budget.emulator_frames - first_budget.emulator_frames
    if (
        second_actions != second.execution.actions_executed
        or second_frames != second.execution.frames_executed
    ):
        raise AcquisitionReplanningCurriculumError(
            "model-led replan budget evidence differs"
        )
    require_living_collection_transition(
        after_first.collection,
        after_second.collection,
        selected_kind=second.selected_kind,
        require_selected_goal_progress=second.passed,
    )
    second_changed = (
        after_second.semantic_state_sha256 != after_first.semantic_state_sha256
    )
    if second.passed and not second_changed:
        raise AcquisitionReplanningCurriculumError(
            "successful model-led replan did not change semantic state"
        )
    metadata = policy.selection_metadata()
    behavior_probability = _probability(
        metadata.get("selected_probability"),
        subject="behavior probability",
        positive=True,
    )
    base_probability = _probability(
        metadata.get("base_selected_probability"),
        subject="base probability",
        positive=False,
    )
    steps.append(
        AcquisitionReplanningStep(
            decision_ordinal=2,
            selected_kind=second.selected_kind,
            status=second.verification.status,
            learner_target_eligible=True,
            behavior_probability=behavior_probability,
            base_probability=base_probability,
            available_goal_count=len(second_question.available_indices),
            actions_executed=second_actions,
            frames_executed=second_frames,
            semantic_state_changed=second_changed,
            policy_context_sha256=second_question.policy_context_sha256,
            available_menu_sha256=second_question.available_menu_sha256,
            collection_before=after_first.collection,
            collection_after=after_second.collection,
        )
    )
    trajectory.require_settled()
    return AcquisitionReplanningRunResult(
        model_sha256=policy.model_sha256,
        seed=policy.seed,
        assigned_intervention=assigned_intervention,
        steps=tuple(steps),
        stopped_reason=("decision_limit" if second.passed else "verified_failure"),
    )


def _composition_observation(value: object) -> GoalManagerCompositionObservation:
    if not isinstance(value, GoalManagerCompositionObservation):
        raise AcquisitionReplanningCurriculumError(
            "observer returned an invalid composition observation"
        )
    return value


def _probability(value: object, *, subject: str, positive: bool) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.0 <= float(value) <= 1.0
        or (positive and float(value) == 0.0)
    ):
        raise AcquisitionReplanningCurriculumError(f"{subject} is invalid")
    return float(value)


@dataclass(frozen=True, slots=True)
class AcquisitionReplanningInventory:
    """Path-free summary of the evidence available before curriculum execution."""

    acquisition_train_roots: int
    previously_used_roots: int
    unused_roots: int
    unused_roots_with_multiple_initial_choices: int
    authenticated_post_acquisition_captures: int
    prior_durable_post_acquisition_choice_count: int

    def __post_init__(self) -> None:
        values = (
            self.acquisition_train_roots,
            self.previously_used_roots,
            self.unused_roots,
            self.unused_roots_with_multiple_initial_choices,
            self.authenticated_post_acquisition_captures,
            self.prior_durable_post_acquisition_choice_count,
        )
        if any(type(value) is not int or value < 0 for value in values):  # noqa: E721
            raise AcquisitionReplanningCurriculumError(
                "curriculum inventory counts must be non-negative integers"
            )
        if self.previously_used_roots + self.unused_roots != self.acquisition_train_roots:
            raise AcquisitionReplanningCurriculumError(
                "curriculum inventory does not preserve the root denominator"
            )
        if self.unused_roots_with_multiple_initial_choices > self.unused_roots:
            raise AcquisitionReplanningCurriculumError(
                "curriculum initial-choice count exceeds unused roots"
            )
        if self.authenticated_post_acquisition_captures > self.unused_roots:
            raise AcquisitionReplanningCurriculumError(
                "curriculum post-acquisition captures exceed unused roots"
            )

    @property
    def existing_contexts_support_execution(self) -> bool:
        return (
            self.unused_roots >= ACQUISITION_REPLANNING_ROOTS
            and self.unused_roots_with_multiple_initial_choices
            >= ACQUISITION_REPLANNING_ROOTS
            and self.authenticated_post_acquisition_captures
            >= ACQUISITION_REPLANNING_ROOTS
            and self.prior_durable_post_acquisition_choice_count
            >= ACQUISITION_REPLANNING_MIN_POST_CHOICES
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.acquisition-replanning-inventory.v1",
            "status": (
                "existing_contexts_support_execution"
                if self.existing_contexts_support_execution
                else "existing_contexts_insufficient"
            ),
            "acquisition_train_roots": self.acquisition_train_roots,
            "previously_used_roots": self.previously_used_roots,
            "unused_roots": self.unused_roots,
            "unused_roots_with_multiple_initial_choices": (
                self.unused_roots_with_multiple_initial_choices
            ),
            "authenticated_post_acquisition_captures": (
                self.authenticated_post_acquisition_captures
            ),
            "prior_durable_post_acquisition_choice_count": (
                self.prior_durable_post_acquisition_choice_count
            ),
            "model_predictions": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "outcomes_added": 0,
        }


@dataclass(frozen=True, slots=True)
class AcquisitionReplanningEpisodeAssessment:
    """Strict, title-neutral eligibility result for one later collected episode."""

    qualifies: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.acquisition-replanning-episode-assessment.v1",
            "qualifies": self.qualifies,
            "reasons": list(self.reasons),
        }


def assess_acquisition_replanning_episode(
    result: GoalManagerDevelopmentResult,
) -> AcquisitionReplanningEpisodeAssessment:
    """Check one settled outcome without inventing success from infrastructure facts."""

    if not isinstance(result, GoalManagerDevelopmentResult):
        raise TypeError("result must be a GoalManagerDevelopmentResult")
    reasons: list[str] = []
    if len(result.steps) != ACQUISITION_REPLANNING_MAX_DECISIONS:
        reasons.append("not_exactly_two_settled_decisions")
        return AcquisitionReplanningEpisodeAssessment(False, tuple(reasons))

    acquisition, replan = result.steps
    if acquisition.selected_kind is not GoalKind.ACQUIRE_SPECIES:
        reasons.append("first_goal_not_acquire_species")
    if acquisition.status is not GoalDecisionOutcome.SUCCEEDED:
        reasons.append("acquisition_not_verified")
    if not acquisition.semantic_state_changed:
        reasons.append("acquisition_semantic_state_unchanged")
    if (
        acquisition.collection_after.required_specimens_remaining
        >= acquisition.collection_before.required_specimens_remaining
        or acquisition.collection_after.retained_captures
        <= acquisition.collection_before.retained_captures
        or sum(count for _species, count in acquisition.collection_after.specimen_counts)
        < sum(count for _species, count in acquisition.collection_before.specimen_counts)
    ):
        reasons.append("acquisition_did_not_advance_living_collection")
    if replan.available_goal_count < ACQUISITION_REPLANNING_MIN_POST_CHOICES:
        reasons.append("post_acquisition_menu_has_fewer_than_two_choices")
    if replan.selected_kind is GoalKind.ACQUIRE_SPECIES:
        reasons.append("second_goal_did_not_change")
    if replan.status is not GoalDecisionOutcome.SUCCEEDED:
        reasons.append("second_outcome_not_verified")
    if not replan.semantic_state_changed:
        reasons.append("second_semantic_state_unchanged")
    if (
        acquisition.policy_context_sha256 == replan.policy_context_sha256
        or result.policy_context_changes < 1
    ):
        reasons.append("policy_context_did_not_change")
    if (
        acquisition.available_menu_sha256 == replan.available_menu_sha256
        or result.available_menu_changes < 1
    ):
        reasons.append("available_menu_did_not_change")
    return AcquisitionReplanningEpisodeAssessment(not reasons, tuple(reasons))


def acquisition_replanning_behavior_contract() -> dict[str, object]:
    """Return the fixed-denominator intervention and stopping contract."""

    return {
        "schema": "pokemon.core.acquisition-replanning-behavior.v1",
        "root_lineages": ACQUISITION_REPLANNING_ROOTS,
        "trials_per_root": ACQUISITION_REPLANNING_TRIALS_PER_ROOT,
        "planned_episodes": ACQUISITION_REPLANNING_EPISODES,
        "maximum_controller_started_decisions_per_episode": (
            ACQUISITION_REPLANNING_MAX_DECISIONS
        ),
        "learned_choice_decisions_after_intervention": 1,
        "first_decision_schedule_per_root": [
            GoalKind.ACQUIRE_SPECIES.value,
            GoalKind.ACQUIRE_SPECIES.value,
            GoalKind.DEVELOP_TEAM.value,
            GoalKind.EXPLORE.value,
        ],
        "first_decision_schedule_scope": "per_trial_within_each_root",
        "first_decision_assignment": "frozen_intervention_before_outcomes",
        "first_decision_is_model_prediction": False,
        "second_decision_authority": "exploratory_goal_manager",
        "minimum_initial_executable_choices": 3,
        "minimum_post_acquisition_executable_choices": 2,
        "require_action_free_reobservation_after_first_outcome": True,
        "require_changed_policy_context_before_second_decision": True,
        "require_changed_available_menu_before_second_decision": True,
        "require_distinct_second_goal_kind_after_acquisition": True,
        "retain_all_claimed_failures": True,
        "replacement_or_retry_allowed": False,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
    }


def acquisition_replanning_evidence_contract() -> dict[str, object]:
    """Return the minimum evidence needed before this curriculum may fit a model."""

    return {
        "schema": "pokemon.core.acquisition-replanning-evidence-gate.v1",
        "minimum_admitted_acquisition_first_episodes": (
            ACQUISITION_REPLANNING_MIN_ADMITTED_ACQUISITIONS
        ),
        "minimum_verified_distinct_goal_replans": ACQUISITION_REPLANNING_MIN_REPLANS,
        "minimum_root_lineages_with_verified_replan": (
            ACQUISITION_REPLANNING_MIN_REPLAN_ROOTS
        ),
        "threshold_basis": (
            "provisional feasibility gate: four verified replans across at least three "
            "of four roots; all sixteen outcomes remain retained regardless of gate"
        ),
        "acquisition_requirements": [
            "independent_success_verification",
            "required_specimen_count_decreased",
            "living_collection_nonregression",
        ],
        "replanning_requirements": [
            "post_acquisition_menu_has_at_least_two_executable_choices",
            "policy_context_changed",
            "available_menu_changed",
            "second_selected_goal_differs_from_acquire_species",
            "second_outcome_independently_verified",
        ],
        "fit_partition": "train_only",
        "descriptive_development_result_only": True,
        "unseen_comparison": False,
        "authority_promotion": False,
        "transfer_claim": False,
    }


def acquisition_replanning_capability_gap() -> dict[str, object]:
    """Describe the smallest reusable capability missing from the current Red roots."""

    return {
        "schema": "pokemon.core.acquisition-replanning-capability-gap.v1",
        "status": "reusable_same_area_second_goal_required",
        "required_capability": (
            "Expose at least one title-neutral, independently verified non-acquisition "
            "choice at an encounter source after one retained acquisition."
        ),
        "preferred_candidate": GoalKind.DEVELOP_TEAM.value,
        "acceptable_goal_kinds": [
            GoalKind.DEVELOP_TEAM.value,
            GoalKind.RESTORE_TEAM.value,
            GoalKind.EXPLORE.value,
        ],
        "why_generic": (
            "The preferred team-development capability must consume an encounter-source "
            "adapter rather than a Pokemon Red map script so later titles can bind the "
            "same semantic skill. An existing alternative is acceptable only when it "
            "remains executable after acquisition and is not added merely to inflate "
            "menu cardinality."
        ),
        "must_not_add": [
            "fixed_route_walkthrough",
            "teacher_choice",
            "root_specific_rescue",
            "silent_singleton_dispatch_as_learned_choice",
        ],
        "execution_authorized": False,
    }


def acquisition_replanning_design_record(
    inventory: AcquisitionReplanningInventory,
) -> dict[str, object]:
    """Build the canonical path-free design record from an action-free inventory."""

    if not isinstance(inventory, AcquisitionReplanningInventory):
        raise TypeError("inventory must be an AcquisitionReplanningInventory")
    record = {
        "schema": ACQUISITION_REPLANNING_SCHEMA,
        "inventory": inventory.public_dict(),
        "behavior": acquisition_replanning_behavior_contract(),
        "evidence_gate": acquisition_replanning_evidence_contract(),
        "capability_gap": acquisition_replanning_capability_gap(),
        "claim_boundary": {
            "supported": (
                "The current Red inventory can seed a four-root acquisition curriculum, "
                "but it cannot yet expose a genuine multi-choice post-acquisition replan."
            ),
            "unsupported": (
                "This design is not gameplay, training evidence, learned replanning, Red "
                "completion, living-Pokedex completion, or cross-title transfer."
            ),
        },
        "zero_effects": {
            "model_predictions": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "episode_attempts": 0,
            "verified_outcomes": 0,
            "model_fits": 0,
            "unseen_comparisons": 0,
            "authority_promotions": 0,
            "transfer_results": 0,
        },
    }
    return {**record, "design_sha256": canonical_sha256(record)}


__all__ = (
    "ACQUISITION_REPLANNING_EPISODES",
    "ACQUISITION_REPLANNING_MAX_DECISIONS",
    "ACQUISITION_REPLANNING_MIN_ADMITTED_ACQUISITIONS",
    "ACQUISITION_REPLANNING_MIN_REPLAN_ROOTS",
    "ACQUISITION_REPLANNING_MIN_REPLANS",
    "ACQUISITION_REPLANNING_ROOTS",
    "ACQUISITION_REPLANNING_SCHEMA",
    "ACQUISITION_REPLANNING_TRIALS_PER_ROOT",
    "AdmittedAcquisitionReplanningEpisode",
    "AcquisitionReplanningRunResult",
    "AcquisitionReplanningStep",
    "AcquisitionReplanningCurriculumError",
    "AcquisitionReplanningEpisodeAssessment",
    "AcquisitionReplanningInventory",
    "AssignedGoalIntervention",
    "assess_acquisition_replanning_episode",
    "acquisition_replanning_behavior_contract",
    "acquisition_replanning_capability_gap",
    "acquisition_replanning_design_record",
    "acquisition_replanning_evidence_contract",
    "load_acquisition_replanning_episode",
    "run_acquisition_replanning_episode",
)
