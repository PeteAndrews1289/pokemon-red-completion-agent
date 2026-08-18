from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import cast

import numpy as np
import pytest

import pokemon_red_completion.acquisition_replanning_curriculum as curriculum_module
from pokemon_red_completion.acquisition_replanning_curriculum import (
    ACQUISITION_REPLANNING_EPISODES,
    AcquisitionReplanningCurriculumError,
    AcquisitionReplanningInventory,
    AcquisitionReplanningRunResult,
    AssignedGoalIntervention,
    acquisition_replanning_behavior_contract,
    acquisition_replanning_design_record,
    acquisition_replanning_evidence_contract,
    assess_acquisition_replanning_episode,
    load_acquisition_replanning_episode,
    run_acquisition_replanning_episode,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_development import (
    ExploratoryGoalManagerPolicy,
    GoalManagerDevelopmentResult,
    GoalManagerDevelopmentStep,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryError,
    GoalManagerTrajectoryObserver,
    load_goal_manager_episode,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_collection import (
    RED_COLLECTION_GAME_ID,
    RED_SOLO_COLLECTION_CONTRACT,
)
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)


def _collection(*, remaining: int, captures: int, specimens: int) -> LivingCollectionCheckpoint:
    return LivingCollectionCheckpoint(
        registered_species=specimens,
        living_species=specimens,
        required_specimens_remaining=remaining,
        retained_captures=captures,
        storage_headroom=10,
        undeclared_specimen_losses=0,
        completion_contract_sha256="a" * 64,
        specimen_ledger_sha256=f"{specimens:064x}",
        required_specimens_sha256=f"{remaining:064x}",
        specimen_counts=((f"pokemon:national:{specimens:03d}", specimens),),
    )


def _step(
    ordinal: int,
    kind: GoalKind,
    before: LivingCollectionCheckpoint,
    after: LivingCollectionCheckpoint,
    *,
    menu: str,
) -> GoalManagerDevelopmentStep:
    return GoalManagerDevelopmentStep(
        decision_ordinal=ordinal,
        selected_kind=kind,
        status=GoalDecisionOutcome.SUCCEEDED,
        behavior_probability=0.5,
        base_probability=0.5,
        available_goal_count=3,
        actions_executed=10,
        frames_executed=100,
        semantic_state_changed=True,
        policy_context_sha256=("b" if ordinal == 1 else "c") * 64,
        available_menu_sha256=menu * 64,
        collection_before=before,
        collection_after=after,
    )


def _current_inventory() -> AcquisitionReplanningInventory:
    return AcquisitionReplanningInventory(
        acquisition_train_roots=6,
        previously_used_roots=2,
        unused_roots=4,
        unused_roots_with_multiple_initial_choices=4,
        authenticated_post_acquisition_captures=0,
        prior_durable_post_acquisition_choice_count=1,
    )


def test_current_inventory_fails_only_the_post_acquisition_boundary() -> None:
    inventory = _current_inventory()

    assert inventory.existing_contexts_support_execution is False
    assert inventory.public_dict() == {
        "schema": "pokemon.core.acquisition-replanning-inventory.v1",
        "status": "existing_contexts_insufficient",
        "acquisition_train_roots": 6,
        "previously_used_roots": 2,
        "unused_roots": 4,
        "unused_roots_with_multiple_initial_choices": 4,
        "authenticated_post_acquisition_captures": 0,
        "prior_durable_post_acquisition_choice_count": 1,
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_added": 0,
    }


def test_inventory_requires_an_exact_root_denominator() -> None:
    with pytest.raises(AcquisitionReplanningCurriculumError, match="denominator"):
        AcquisitionReplanningInventory(
            acquisition_train_roots=6,
            previously_used_roots=1,
            unused_roots=4,
            unused_roots_with_multiple_initial_choices=4,
            authenticated_post_acquisition_captures=0,
            prior_durable_post_acquisition_choice_count=1,
        )


def test_behavior_is_balanced_repeatable_and_teacher_free() -> None:
    behavior = acquisition_replanning_behavior_contract()

    assert behavior["planned_episodes"] == ACQUISITION_REPLANNING_EPISODES == 16
    assert behavior["first_decision_schedule_per_root"] == [
        "acquire_species",
        "acquire_species",
        "develop_team",
        "explore",
    ]
    assert behavior["first_decision_schedule_scope"] == "per_trial_within_each_root"
    acquisition_trials_per_root = behavior["first_decision_schedule_per_root"].count(
        "acquire_species"
    )
    acquisition_first_roots = (
        behavior["root_lineages"] if acquisition_trials_per_root else 0
    )
    assert acquisition_first_roots >= 3
    assert behavior["maximum_controller_started_decisions_per_episode"] == 2
    assert behavior["learned_choice_decisions_after_intervention"] == 1
    assert behavior["first_decision_is_model_prediction"] is False
    assert behavior["minimum_initial_executable_choices"] == 3
    assert behavior["minimum_post_acquisition_executable_choices"] == 2
    assert behavior["retain_all_claimed_failures"] is True
    assert behavior["replacement_or_retry_allowed"] is False
    assert behavior["teacher_queries"] == 0


def test_evidence_gate_is_descriptive_and_requires_cross_root_replanning() -> None:
    gate = acquisition_replanning_evidence_contract()

    assert gate["minimum_admitted_acquisition_first_episodes"] == 4
    assert gate["minimum_verified_distinct_goal_replans"] == 4
    assert gate["minimum_root_lineages_with_verified_replan"] == 3
    assert gate["fit_partition"] == "train_only"
    assert gate["unseen_comparison"] is False
    assert gate["authority_promotion"] is False
    assert gate["transfer_claim"] is False


def test_design_record_is_path_free_and_execution_closed() -> None:
    record = acquisition_replanning_design_record(_current_inventory())
    encoded = str(record)

    assert len(record["design_sha256"]) == 64
    assert record["capability_gap"]["execution_authorized"] is False
    assert record["zero_effects"] == {
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "episode_attempts": 0,
        "verified_outcomes": 0,
        "model_fits": 0,
        "unseen_comparisons": 0,
        "authority_promotions": 0,
        "transfer_results": 0,
    }
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_episode_assessment_requires_real_acquisition_then_distinct_replan() -> None:
    before = _collection(remaining=10, captures=2, specimens=2)
    acquired = _collection(remaining=9, captures=3, specimens=3)
    result = GoalManagerDevelopmentResult(
        model_sha256="d" * 64,
        seed=1,
        steps=(
            _step(1, GoalKind.ACQUIRE_SPECIES, before, acquired, menu="1"),
            _step(2, GoalKind.DEVELOP_TEAM, acquired, acquired, menu="2"),
        ),
        policy_context_changes=1,
        available_menu_changes=1,
        stopped_reason="decision_limit",
    )

    assessment = assess_acquisition_replanning_episode(result)

    assert assessment.qualifies is True
    assert assessment.reasons == ()


def test_episode_assessment_rejects_repeated_acquisition_without_replanning() -> None:
    before = _collection(remaining=10, captures=2, specimens=2)
    acquired = _collection(remaining=9, captures=3, specimens=3)
    result = GoalManagerDevelopmentResult(
        model_sha256="d" * 64,
        seed=1,
        steps=(
            _step(1, GoalKind.ACQUIRE_SPECIES, before, acquired, menu="1"),
            _step(2, GoalKind.ACQUIRE_SPECIES, acquired, acquired, menu="2"),
        ),
        policy_context_changes=1,
        available_menu_changes=1,
        stopped_reason="decision_limit",
    )

    assessment = assess_acquisition_replanning_episode(result)

    assert assessment.qualifies is False
    assert assessment.reasons == ("second_goal_did_not_change",)


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id=RED_COLLECTION_GAME_ID,
            mode="overworld",
            location="pokemon.red:acquisition-replanning-test",
            features={},
        )


class _Executor:
    def execute(self, action: object) -> object:
        return action


@dataclass
class _Meter:
    state: dict[str, int]

    def checkpoint(self) -> CompositionBudgetCheckpoint:
        return CompositionBudgetCheckpoint(
            controller_actions=self.state["actions"],
            emulator_frames=self.state["frames"],
        )


def _linear_model() -> GoalManagerLinearModel:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    return GoalManagerLinearModel(
        weights=np.zeros(width, dtype=np.float64),
        feature_mean=np.zeros(width, dtype=np.float64),
        feature_scale=np.ones(width, dtype=np.float64),
        l2=0.0,
        training_epochs=1,
    )


def _living(specimens: dict[str, int]) -> LivingCollectionCheckpoint:
    required = RED_ACQUISITION_CATALOG.required_root_acquisitions()
    remaining = {
        species: count - specimens.get(species, 0)
        for species, count in required.items()
        if count > specimens.get(species, 0)
    }
    return LivingCollectionCheckpoint(
        registered_species=len(specimens),
        living_species=sum(
            species in RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
            for species in specimens
        ),
        required_specimens_remaining=sum(remaining.values()),
        retained_captures=sum(
            min(count, specimens.get(species, 0))
            for species, count in required.items()
        ),
        storage_headroom=10,
        undeclared_specimen_losses=0,
        completion_contract_sha256=canonical_sha256(
            {
                "schema": "pokemon.core.living-collection-contract.v1",
                "game_id": RED_COLLECTION_GAME_ID,
                "registered_target": sorted(
                    RED_SOLO_COLLECTION_CONTRACT.target_species
                ),
                "living_target": sorted(
                    RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
                ),
                "required_root_acquisitions": dict(sorted(required.items())),
            }
        ),
        specimen_ledger_sha256=canonical_sha256(
            {
                "schema": "pokemon.core.living-specimen-ledger.v1",
                "specimens": dict(sorted(specimens.items())),
            }
        ),
        required_specimens_sha256=canonical_sha256(
            {
                "schema": "pokemon.core.remaining-required-specimens.v1",
                "remaining": dict(sorted(remaining.items())),
            }
        ),
        specimen_counts=tuple(sorted(specimens.items())),
    )


def _replanning_fixture(*, fail_first: bool = False) -> tuple[
    Callable[[], GoalManagerCompositionObservation],
    _Meter,
    GoalManagerTrajectoryObserver,
    InMemoryTrajectorySink,
]:
    state: dict[str, object] = {
        "stage": 0,
        "actions": 0,
        "frames": 0,
        "last_kind": None,
        "acquired": False,
    }

    def observe() -> GoalManagerCompositionObservation:
        stage = int(state["stage"])
        available = {
            GoalKind.DEVELOP_TEAM,
            GoalKind.EXPLORE,
        }
        if stage == 0:
            available.add(GoalKind.ACQUIRE_SPECIES)
        opportunities = tuple(
            GoalOpportunity(
                binding_ref=f"private:{kind.value}",
                kind=kind,
                availability=(
                    GoalAvailability.AVAILABLE
                    if kind in available
                    else GoalAvailability.UNAVAILABLE
                ),
                estimated_effort=0.2 if kind in available else None,
                estimated_risk=0.1 if kind in available else None,
                unavailable_reason=(
                    None
                    if kind in available
                    else GoalUnavailableReason.NO_LEGAL_TARGET
                ),
            )
            for kind in GoalKind
        )

        def binding(kind: GoalKind) -> ExecutableGoalBinding:
            def execute() -> GoalExecutionReport:
                state["stage"] = int(state["stage"]) + 1
                state["actions"] = int(state["actions"]) + 2
                state["frames"] = int(state["frames"]) + 20
                state["last_kind"] = kind
                if kind is GoalKind.ACQUIRE_SPECIES:
                    state["acquired"] = True
                return GoalExecutionReport(2, 20, {"bounded": True})

            return ExecutableGoalBinding(
                binding_ref=f"private:{kind.value}",
                kind=kind,
                estimated_effort=0.2,
                estimated_risk=0.1,
                execute=execute,
                verify=lambda _report: (
                    GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                    if fail_first and state["stage"] == 1
                    else GoalVerification.succeeded()
                ),
            )

        specimens = {"pokemon:national:007": 1}
        if state["acquired"]:
            specimens["pokemon:national:010"] = 1
        return GoalManagerCompositionObservation(
            semantic_state_sha256=f"{stage + 1:064x}",
            situation=GoalSituation(
                story_pressure=0.2 + stage * 0.1,
                collection_pressure=0.8 - stage * 0.1,
                team_pressure=0.5 + stage * 0.1,
                evolution_pressure=0.2,
                safety_pressure=0.2,
                resource_pressure=0.2,
                storage_pressure=0.2,
                recovery_pressure=0.2,
                exploration_pressure=0.4 + stage * 0.1,
            ),
            binding_set=GoalBindingSet(
                opportunities,
                tuple(binding(kind) for kind in GoalKind if kind in available),
            ),
            collection=_living(specimens),
        )

    sink = InMemoryTrajectorySink()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id="acquisition-replanning-episode",
    )
    trajectory = GoalManagerTrajectoryObserver(
        episode_id="acquisition-replanning-episode",
        root_lineage_id="red-goal-root-" + "4" * 64,
        partition="development",
        environment_id=RED_COLLECTION_GAME_ID,
        actor="acquisition_replanning_mixed_policy",
        policy_id="red-acquisition-replanning-development-v1",
        collection_id="a" * 64,
        assignment_id="b" * 64,
        source_commit="1" * 40,
        snapshot_provider=_SnapshotProvider(),
        recorder=recorder,
        sink=sink,
        ordering_assignment_id="c" * 64,
    )
    return observe, _Meter(cast(dict[str, int], state)), trajectory, sink


def test_run_uses_assigned_first_step_and_only_second_step_is_a_target() -> None:
    observe, meter, trajectory, sink = _replanning_fixture()

    result = run_acquisition_replanning_episode(
        observe=observe,
        assigned_intervention=GoalKind.ACQUIRE_SPECIES,
        policy=ExploratoryGoalManagerPolicy(_linear_model(), seed=2),
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert len(result.steps) == 2
    assert result.steps[0].selected_kind is GoalKind.ACQUIRE_SPECIES
    assert result.steps[0].learner_target_eligible is False
    assert result.steps[0].behavior_probability is None
    assert result.steps[1].learner_target_eligible is True
    assert result.steps[1].behavior_probability is not None
    assert result.learner_targets == 1
    assert "behavior_policy" not in sink.decisions[0].context.metadata
    assert "behavior_policy" in sink.decisions[1].context.metadata


def test_assigned_intervention_rejects_missing_or_duplicate_semantic_kind() -> None:
    observation, _meter, _trajectory, _sink = _replanning_fixture()
    question = GoalManagerQuestion(
        situation=observation().situation,
        opportunities=observation().binding_set.opportunities,
    )

    selected = AssignedGoalIntervention(GoalKind.DEVELOP_TEAM).select(question)

    assert selected.kind is GoalKind.DEVELOP_TEAM


def test_assigned_failure_never_becomes_a_learner_target() -> None:
    observe, meter, trajectory, _sink = _replanning_fixture(fail_first=True)
    result = run_acquisition_replanning_episode(
        observe=observe,
        assigned_intervention=GoalKind.DEVELOP_TEAM,
        policy=ExploratoryGoalManagerPolicy(_linear_model(), seed=2),
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert result.learner_targets == 0
    assert result.stopped_reason == "assigned_intervention_failed"


class _AcquisitionReader:
    manifest_sha256 = "9" * 64

    def __init__(
        self,
        sink: InMemoryTrajectorySink,
        result: AcquisitionReplanningRunResult,
        *,
        inject_first_behavior: bool = False,
    ) -> None:
        self._sink = sink
        self._result = result
        self._inject_first_behavior = inject_first_behavior

    def read_header(self) -> Mapping[str, object]:
        return {
            "record_type": "episode",
            "trajectory_schema": "pokemon.trajectory.v1",
            "episode_id": "acquisition-replanning-episode",
            "game_id": RED_COLLECTION_GAME_ID,
            "metadata": {
                "policy": {
                    "actor": "acquisition_replanning_mixed_policy",
                    "policy_id": "red-acquisition-replanning-development-v1",
                },
                "split": {
                    "partition": "development",
                    "root_lineage_id": "red-goal-root-" + "4" * 64,
                },
                "goal_manager": {
                    "assignment_id": "b" * 64,
                    "binding_manifest_sha256": "d" * 64,
                    "collection_id": "a" * 64,
                    "context_catalog_sha256": "e" * 64,
                    "context_id": "f" * 64,
                    "envelope_sha256": "1" * 64,
                    "execution_identity_sha256": "8" * 64,
                    "source_commit": "1" * 40,
                    "state_sha256": "2" * 64,
                },
                "acquisition_replanning": {
                    "assigned_intervention": "acquire_species",
                    "behavior_contract": acquisition_replanning_behavior_contract(),
                    "first_decision_is_model_prediction": False,
                    "learner_target_decision_indices": [1],
                    "maximum_decisions": 2,
                },
            },
        }

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]:
        if stream == "decisions":
            for index, decision in enumerate(self._sink.decisions):
                payload = deepcopy(decision.to_dict())
                if index == 0 and self._inject_first_behavior:
                    context = cast(dict[str, object], payload["context"])
                    metadata = cast(dict[str, object], context["metadata"])
                    metadata["behavior_policy"] = {
                        "behavior_policy_id": "forged",
                        "candidate_probabilities": [1.0],
                        "selected_probability": 1.0,
                        "base_selected_probability": 1.0,
                        "exploration_mix": 0.0,
                        "temperature": 1.0,
                    }
                yield payload
        elif stream == "events":
            for event in self._sink.events:
                yield event.to_dict()
            yield {
                "event_id": "acquisition-replanning-episode:terminal",
                "episode_id": "acquisition-replanning-episode",
                "step_index": sum(
                    step.actions_executed for step in self._result.steps
                ),
                "kind": "terminal",
                "payload": {
                    "status": "complete",
                    "acquisition_replanning": self._result.public_dict(),
                },
            }
        elif stream == "executions":
            for step in self._result.steps:
                frames_per_action = step.frames_executed // step.actions_executed
                for _ in range(step.actions_executed):
                    yield {
                        "episode_id": "acquisition-replanning-episode",
                        "frames": frames_per_action,
                        "status": "success",
                    }


def _admit_test_episode(*, inject_first_behavior: bool = False):
    observe, meter, trajectory, sink = _replanning_fixture()
    model = _linear_model()
    result = run_acquisition_replanning_episode(
        observe=observe,
        assigned_intervention=GoalKind.ACQUIRE_SPECIES,
        policy=ExploratoryGoalManagerPolicy(model, seed=2),
        trajectory=trajectory,
        budget_meter=meter,
    )
    first_question = GoalManagerQuestion.from_policy_input(
        cast(Mapping[str, object], sink.decisions[0].context.metadata["policy_input"])
    )
    return load_acquisition_replanning_episode(
        _AcquisitionReader(
            sink,
            result,
            inject_first_behavior=inject_first_behavior,
        ),
        expected_campaign_id="a" * 64,
        expected_trial_claim_sha256="b" * 64,
        expected_episode_id="acquisition-replanning-episode",
        expected_root_lineage_id="red-goal-root-" + "4" * 64,
        expected_seed=2,
        expected_execution_identity_sha256="8" * 64,
        expected_context_catalog_sha256="e" * 64,
        expected_context_id="f" * 64,
        expected_binding_manifest_sha256="d" * 64,
        expected_state_sha256="2" * 64,
        expected_envelope_sha256="1" * 64,
        expected_first_question_sha256=first_question.ordered_policy_input_sha256,
        expected_first_policy_context_sha256=first_question.policy_context_sha256,
        expected_first_available_menu_sha256=first_question.available_menu_sha256,
        expected_assigned_intervention=GoalKind.ACQUIRE_SPECIES,
        expected_model=model,
        expected_source_commit="1" * 40,
    )


def test_strict_admission_builds_only_the_second_decision_target() -> None:
    admitted = _admit_test_episode()

    assert admitted.assigned_intervention is GoalKind.ACQUIRE_SPECIES
    assert len(admitted.dataset.examples) == 2
    assert len(admitted.targets) == 1
    assert admitted.targets[0].decision_id.endswith(":goal-manager:1")


def test_strict_admission_rejects_behavior_metadata_on_assigned_intervention() -> None:
    with pytest.raises(
        (AcquisitionReplanningCurriculumError, GoalManagerTrajectoryError),
    ):
        _admit_test_episode(inject_first_behavior=True)


def _strict_admission_call(
    reader: _AcquisitionReader,
    *,
    model: GoalManagerLinearModel,
    first_question: GoalManagerQuestion,
):
    return load_acquisition_replanning_episode(
        reader,
        expected_campaign_id="a" * 64,
        expected_trial_claim_sha256="b" * 64,
        expected_episode_id="acquisition-replanning-episode",
        expected_root_lineage_id="red-goal-root-" + "4" * 64,
        expected_seed=2,
        expected_execution_identity_sha256="8" * 64,
        expected_context_catalog_sha256="e" * 64,
        expected_context_id="f" * 64,
        expected_binding_manifest_sha256="d" * 64,
        expected_state_sha256="2" * 64,
        expected_envelope_sha256="1" * 64,
        expected_first_question_sha256=first_question.ordered_policy_input_sha256,
        expected_first_policy_context_sha256=first_question.policy_context_sha256,
        expected_first_available_menu_sha256=first_question.available_menu_sha256,
        expected_assigned_intervention=GoalKind.ACQUIRE_SPECIES,
        expected_model=model,
        expected_source_commit="1" * 40,
    )


def _strict_dataset_fixture():
    observe, meter, trajectory, sink = _replanning_fixture()
    model = _linear_model()
    result = run_acquisition_replanning_episode(
        observe=observe,
        assigned_intervention=GoalKind.ACQUIRE_SPECIES,
        policy=ExploratoryGoalManagerPolicy(model, seed=2),
        trajectory=trajectory,
        budget_meter=meter,
    )
    reader = _AcquisitionReader(sink, result)
    first_question = GoalManagerQuestion.from_policy_input(
        cast(Mapping[str, object], sink.decisions[0].context.metadata["policy_input"])
    )
    return reader, load_goal_manager_episode(reader), model, first_question


def test_strict_admission_rejects_successful_first_step_without_replan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, dataset, model, first_question = _strict_dataset_fixture()
    impossible = replace(dataset, examples=dataset.examples[:1])
    monkeypatch.setattr(
        curriculum_module,
        "load_goal_manager_episode",
        lambda _reader: impossible,
    )

    with pytest.raises(
        AcquisitionReplanningCurriculumError,
        match="runtime branch",
    ):
        _strict_admission_call(reader, model=model, first_question=first_question)


def test_strict_admission_rejects_second_step_after_failed_intervention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, dataset, model, first_question = _strict_dataset_fixture()
    failed_first = replace(
        dataset.examples[0],
        outcome_status=GoalDecisionOutcome.FAILED,
        failure_reason=GoalFailureReason.OUTCOME_NOT_VERIFIED,
    )
    impossible = replace(
        dataset,
        examples=(failed_first, dataset.examples[1]),
    )
    monkeypatch.setattr(
        curriculum_module,
        "load_goal_manager_episode",
        lambda _reader: impossible,
    )

    with pytest.raises(
        AcquisitionReplanningCurriculumError,
        match="runtime branch",
    ):
        _strict_admission_call(reader, model=model, first_question=first_question)


@pytest.mark.parametrize("invalid_menu", ("singleton", "evolution"))
def test_strict_admission_rejects_impossible_replan_menu(
    monkeypatch: pytest.MonkeyPatch,
    invalid_menu: str,
) -> None:
    reader, dataset, model, first_question = _strict_dataset_fixture()
    second = dataset.examples[1]
    opportunities = list(second.question.opportunities)
    if invalid_menu == "singleton":
        selected = second.selected_candidate_index
        for index in second.question.available_indices:
            if index != selected:
                opportunities[index] = replace(
                    opportunities[index],
                    availability=GoalAvailability.UNAVAILABLE,
                    estimated_effort=None,
                    estimated_risk=None,
                    unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
                )
    else:
        evolution = next(
            index
            for index, opportunity in enumerate(opportunities)
            if opportunity.kind is GoalKind.EVOLVE_SPECIES
        )
        opportunities[evolution] = replace(
            opportunities[evolution],
            availability=GoalAvailability.AVAILABLE,
            estimated_effort=0.5,
            estimated_risk=0.1,
            unavailable_reason=None,
        )
    invalid_question = GoalManagerQuestion(
        situation=second.question.situation,
        opportunities=tuple(opportunities),
    )
    replacement_fields: dict[str, object] = {"question": invalid_question}
    if invalid_menu == "singleton":
        replacement_fields.update(
            {
                "behavior_probability": 1.0,
                "behavior_candidate_probabilities": tuple(
                    1.0 if index == second.selected_candidate_index else 0.0
                    for index in range(len(opportunities))
                ),
                "behavior_base_probability": 1.0,
            }
        )
    impossible = replace(
        dataset,
        examples=(dataset.examples[0], replace(second, **replacement_fields)),
    )
    monkeypatch.setattr(
        curriculum_module,
        "load_goal_manager_episode",
        lambda _reader: impossible,
    )

    with pytest.raises(
        AcquisitionReplanningCurriculumError,
        match="model-led replan propensity differs",
    ):
        _strict_admission_call(reader, model=model, first_question=first_question)
