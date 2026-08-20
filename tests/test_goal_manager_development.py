from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

import numpy as np
import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
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
    GoalManagerDevelopmentError,
    GoalManagerDevelopmentResult,
    load_repeatable_goal_manager_development_episode,
    run_repeatable_goal_manager_development_episode,
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
    GoalManagerTrajectoryObserver,
    ordered_goal_manager_question,
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


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id=RED_COLLECTION_GAME_ID,
            mode="overworld",
            location="pokemon.red:development-test",
            features={},
        )


class _Executor:
    def execute(self, action: object) -> object:
        return action


def _collection_checkpoint_for_test() -> LivingCollectionCheckpoint:
    specimens = {"pokemon:national:007": 1}
    required = RED_ACQUISITION_CATALOG.required_root_acquisitions()
    remaining = {
        species: count - specimens.get(species, 0)
        for species, count in required.items()
        if count > specimens.get(species, 0)
    }
    return LivingCollectionCheckpoint(
        registered_species=1,
        living_species=0,
        required_specimens_remaining=sum(remaining.values()),
        retained_captures=1,
        storage_headroom=2,
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
                "specimens": specimens,
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


@dataclass
class _Meter:
    state: dict[str, int]

    def checkpoint(self) -> CompositionBudgetCheckpoint:
        return CompositionBudgetCheckpoint(
            controller_actions=self.state["actions"],
            emulator_frames=self.state["frames"],
        )


def _model() -> GoalManagerLinearModel:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    return GoalManagerLinearModel(
        weights=np.zeros(width, dtype=np.float64),
        feature_mean=np.zeros(width, dtype=np.float64),
        feature_scale=np.ones(width, dtype=np.float64),
        l2=0.0,
        training_epochs=1,
    )


def _different_model() -> GoalManagerLinearModel:
    model = _model()
    weights = model.weights.copy()
    weights[0] = 1.0
    return GoalManagerLinearModel(
        weights=weights,
        feature_mean=model.feature_mean,
        feature_scale=model.feature_scale,
        l2=model.l2,
        training_epochs=model.training_epochs,
    )


def _trajectory(
    *,
    assignment_id: str = "b" * 64,
    ordering_assignment_id: str | None = None,
    partition: str = "development",
) -> tuple[GoalManagerTrajectoryObserver, InMemoryTrajectorySink]:
    sink = InMemoryTrajectorySink()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id="development-episode",
    )
    observer = GoalManagerTrajectoryObserver(
        episode_id="development-episode",
        root_lineage_id="red-goal-root-" + "4" * 64,
        partition=partition,
        environment_id=RED_COLLECTION_GAME_ID,
        actor="exploratory_goal_manager",
        policy_id="red-goal-manager-outcome-development-v1",
        collection_id="a" * 64,
        assignment_id=assignment_id,
        source_commit="1" * 40,
        snapshot_provider=_SnapshotProvider(),
        recorder=recorder,
        sink=sink,
        ordering_assignment_id=ordering_assignment_id,
    )
    return observer, sink


def _observe_factory(
    *,
    fail: bool = False,
    include_evolution: bool = False,
) -> tuple[Callable[[], GoalManagerCompositionObservation], _Meter]:
    state = {"stage": 0, "actions": 0, "frames": 0}

    def observe() -> GoalManagerCompositionObservation:
        stage = state["stage"]
        available = {
            GoalKind.ADVANCE_STORY,
            GoalKind.MANAGE_STORAGE,
            GoalKind.RESTORE_TEAM,
        }
        if include_evolution:
            available.add(GoalKind.EVOLVE_SPECIES)
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
                state["stage"] += 1
                state["actions"] += 2
                state["frames"] += 20
                return GoalExecutionReport(2, 20, {"bounded": True})

            def verify(_report: GoalExecutionReport) -> GoalVerification:
                if fail:
                    return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                return GoalVerification.succeeded()

            return ExecutableGoalBinding(
                binding_ref=f"private:{kind.value}",
                kind=kind,
                estimated_effort=0.2,
                estimated_risk=0.1,
                execute=execute,
                verify=verify,
            )

        collection = _collection_checkpoint_for_test()
        return GoalManagerCompositionObservation(
            semantic_state_sha256=f"{stage + 1:064x}",
            situation=GoalSituation(
                story_pressure=min(1.0, 0.3 + 0.2 * stage),
                collection_pressure=0.5,
                team_pressure=0.5,
                evolution_pressure=0.5,
                safety_pressure=0.5,
                resource_pressure=0.5,
                storage_pressure=0.5,
                recovery_pressure=0.5,
                exploration_pressure=0.5,
            ),
            binding_set=GoalBindingSet(
                opportunities,
                tuple(binding(kind) for kind in GoalKind if kind in available),
            ),
            collection=collection,
        )

    return observe, _Meter(state)


def test_exploratory_policy_is_seeded_and_records_exact_propensity() -> None:
    from pokemon_red_completion.goal_manager import GoalManagerQuestion

    opportunities = tuple(
        GoalOpportunity(
            binding_ref=f"candidate:{kind.value}",
            kind=kind,
            availability=GoalAvailability.AVAILABLE,
            estimated_effort=0.2,
            estimated_risk=0.1,
        )
        for kind in (GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM)
    )
    question = GoalManagerQuestion(
        situation=GoalSituation(*([0.5] * 9)),
        opportunities=opportunities,
    )
    first = ExploratoryGoalManagerPolicy(_model(), seed=7)
    second = ExploratoryGoalManagerPolicy(_model(), seed=7)

    assert first.select(question) == second.select(question)
    metadata = first.selection_metadata()
    assert metadata["behavior_policy_id"] == (
        "pokemon.core.goal-manager.exploratory-softmax.v1"
    )
    probabilities = cast(Sequence[float], metadata["candidate_probabilities"])
    assert abs(sum(probabilities) - 1.0) < 1e-12
    selected_probability = cast(float, metadata["selected_probability"])
    assert 0.0 < selected_probability <= 1.0


def test_repeatable_development_records_three_model_led_outcomes() -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory()
    policy = ExploratoryGoalManagerPolicy(_model(), seed=11)

    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=policy,
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert result.verified_outcomes == 3
    assert result.is_composition
    assert policy.decisions == 3
    assert len(sink.decisions) == 3
    assert len(sink.events) == 3
    assert all(
        "behavior_policy" in decision.context.metadata for decision in sink.decisions
    )


def test_trial_provenance_does_not_change_frozen_question_order() -> None:
    frozen_assignment = "c" * 64
    trajectory, _sink = _trajectory(
        assignment_id="d" * 64,
        ordering_assignment_id=frozen_assignment,
    )
    observe, _meter = _observe_factory()
    observation = observe()

    question = trajectory.ordered_question(
        observation.situation,
        observation.binding_set.opportunities,
    )
    expected = ordered_goal_manager_question(
        assignment_id=frozen_assignment,
        decision_index=0,
        situation=observation.situation,
        opportunities=observation.binding_set.opportunities,
    )

    assert question == expected


def test_repeatable_development_retains_verified_failure_and_stops() -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory(fail=True)
    policy = ExploratoryGoalManagerPolicy(_model(), seed=5)

    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=policy,
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert result.verified_outcomes == 1
    assert not result.is_composition
    assert result.stopped_reason == "verified_failure"
    assert len(sink.decisions) == 1
    assert len(sink.events) == 1
    assert sink.events[0].payload["status"] == "failed"


def test_repeatable_development_rejects_evolution_before_prediction() -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory(include_evolution=True)
    policy = ExploratoryGoalManagerPolicy(_model(), seed=5)

    with pytest.raises(
        GoalManagerDevelopmentError,
        match="evolution requires retained lineage evidence",
    ):
        run_repeatable_goal_manager_development_episode(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert policy.decisions == 0
    assert not sink.decisions
    assert not sink.events


class _DevelopmentReader:
    manifest_sha256 = "c" * 64

    def __init__(
        self,
        sink: InMemoryTrajectorySink,
        result: GoalManagerDevelopmentResult,
        *,
        tamper_selected_probability: bool = False,
        tamper_specimen_counts: bool = False,
        tamper_environment: bool = False,
        tamper_decision_identity: bool = False,
        tamper_terminal_identity: bool = False,
        partition: str = "development",
        maximum_decisions: int = 3,
    ) -> None:
        self._sink = sink
        self._result = result
        self._tamper_selected_probability = tamper_selected_probability
        self._tamper_specimen_counts = tamper_specimen_counts
        self._tamper_environment = tamper_environment
        self._tamper_decision_identity = tamper_decision_identity
        self._tamper_terminal_identity = tamper_terminal_identity
        self._partition = partition
        self._maximum_decisions = maximum_decisions

    def read_header(self) -> Mapping[str, object]:
        return {
            "record_type": "episode",
            "trajectory_schema": "pokemon.trajectory.v1",
            "episode_id": "development-episode",
            "game_id": RED_COLLECTION_GAME_ID,
            "metadata": {
                "policy": {
                    "actor": "exploratory_goal_manager",
                    "policy_id": "red-goal-manager-outcome-development-v1",
                },
                "split": {
                    "partition": self._partition,
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
                "development": {
                    "exploration_mix": 0.15,
                    "maximum_importance_weight": 4.0,
                    "maximum_decisions": self._maximum_decisions,
                    "outcome_objective_id": (
                        "pokemon.core.goal-manager.selected-outcome-objective.v1"
                    ),
                    "repeatable_capture": True,
                    "temperature": 1.0,
                    "teacher_fallbacks": 0,
                    "teacher_queries": 0,
                },
            },
        }

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]:
        if stream == "decisions":
            for decision in self._sink.decisions:
                payload = deepcopy(decision.to_dict())
                if self._tamper_selected_probability:
                    context = cast(dict[str, object], payload["context"])
                    metadata = cast(dict[str, object], context["metadata"])
                    behavior = cast(dict[str, object], metadata["behavior_policy"])
                    behavior["selected_probability"] = 0.25
                if self._tamper_environment:
                    context = cast(dict[str, object], payload["context"])
                    metadata = cast(dict[str, object], context["metadata"])
                    metadata["environment_id"] = "pokemon.mainline:crystal:gbc:us:rev1"
                if self._tamper_decision_identity:
                    payload["decision_id"] = str(payload["decision_id"]).replace(
                        ":goal-manager:", ":renamed:"
                    )
                yield payload
        elif stream == "events":
            for event in self._sink.events:
                payload = event.to_dict()
                if self._tamper_decision_identity:
                    outcome = cast(dict[str, object], payload["payload"])
                    outcome["decision_id"] = str(outcome["decision_id"]).replace(
                        ":goal-manager:", ":renamed:"
                    )
                yield payload
            development = deepcopy(self._result.public_dict())
            if self._tamper_specimen_counts:
                steps = cast(list[dict[str, object]], development["steps"])
                after = cast(dict[str, object], steps[0]["collection_after"])
                after["specimen_counts"] = [["pokemon:national:010", 1]]
            yield {
                "event_id": (
                    "development-episode:wrong-terminal"
                    if self._tamper_terminal_identity
                    else "development-episode:terminal"
                ),
                "episode_id": "development-episode",
                "step_index": sum(step.actions_executed for step in self._result.steps),
                "kind": "terminal",
                "payload": {
                    "status": "complete",
                    "development": development,
                },
            }
        elif stream == "executions":
            for step in self._result.steps:
                frames_per_action = step.frames_executed // step.actions_executed
                for _ in range(step.actions_executed):
                    yield {
                        "episode_id": "development-episode",
                        "frames": frames_per_action,
                        "status": "success",
                    }


def _first_question(sink: InMemoryTrajectorySink) -> GoalManagerQuestion:
    policy_input = sink.decisions[0].context.metadata["policy_input"]
    assert isinstance(policy_input, Mapping)
    return GoalManagerQuestion.from_policy_input(policy_input)


def test_strict_development_admission_builds_outcome_targets() -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory()
    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=ExploratoryGoalManagerPolicy(_model(), seed=11),
        trajectory=trajectory,
        budget_meter=meter,
    )

    admitted = load_repeatable_goal_manager_development_episode(
        _DevelopmentReader(sink, result),
        expected_campaign_id="a" * 64,
        expected_trial_claim_sha256="b" * 64,
        expected_episode_id="development-episode",
        expected_root_lineage_id="red-goal-root-" + "4" * 64,
        expected_seed=11,
        expected_execution_identity_sha256="8" * 64,
        expected_context_catalog_sha256="e" * 64,
        expected_context_id="f" * 64,
        expected_binding_manifest_sha256="d" * 64,
        expected_state_sha256="2" * 64,
        expected_envelope_sha256="1" * 64,
        expected_first_question_sha256=_first_question(sink).ordered_policy_input_sha256,
        expected_first_policy_context_sha256=_first_question(sink).policy_context_sha256,
        expected_first_available_menu_sha256=_first_question(sink).available_menu_sha256,
        expected_model=_model(),
        expected_source_commit="1" * 40,
    )

    assert admitted.verified_outcomes == 3
    assert admitted.composition
    assert len(admitted.targets) == 3
    assert {target.reward for target in admitted.targets} == {1.0}
    assert all(0.0 < target.behavior_probability <= 1.0 for target in admitted.targets)
    assert all(1.0 <= target.importance_weight <= 4.0 for target in admitted.targets)


def test_strict_one_decision_train_admission_is_explicit() -> None:
    trajectory, sink = _trajectory(partition="train")
    observe, meter = _observe_factory()
    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=ExploratoryGoalManagerPolicy(_model(), seed=17),
        trajectory=trajectory,
        budget_meter=meter,
        maximum_decisions=1,
    )
    reader = _DevelopmentReader(
        sink,
        result,
        partition="train",
        maximum_decisions=1,
    )

    admitted = load_repeatable_goal_manager_development_episode(
        reader,
        expected_campaign_id="a" * 64,
        expected_trial_claim_sha256="b" * 64,
        expected_episode_id="development-episode",
        expected_root_lineage_id="red-goal-root-" + "4" * 64,
        expected_seed=17,
        expected_execution_identity_sha256="8" * 64,
        expected_context_catalog_sha256="e" * 64,
        expected_context_id="f" * 64,
        expected_binding_manifest_sha256="d" * 64,
        expected_state_sha256="2" * 64,
        expected_envelope_sha256="1" * 64,
        expected_first_question_sha256=_first_question(sink).ordered_policy_input_sha256,
        expected_first_policy_context_sha256=_first_question(sink).policy_context_sha256,
        expected_first_available_menu_sha256=_first_question(sink).available_menu_sha256,
        expected_model=_model(),
        expected_source_commit="1" * 40,
        expected_partition="train",
        expected_maximum_decisions=1,
    )

    assert admitted.dataset.partition == "train"
    assert len(admitted.targets) == 1


def test_strict_development_admission_rejects_wrong_model() -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory()
    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=ExploratoryGoalManagerPolicy(_model(), seed=11),
        trajectory=trajectory,
        budget_meter=meter,
    )

    with pytest.raises(GoalManagerDevelopmentError, match="terminal result differs"):
        load_repeatable_goal_manager_development_episode(
            _DevelopmentReader(sink, result),
            expected_campaign_id="a" * 64,
            expected_trial_claim_sha256="b" * 64,
            expected_episode_id="development-episode",
            expected_root_lineage_id="red-goal-root-" + "4" * 64,
            expected_seed=11,
            expected_execution_identity_sha256="8" * 64,
            expected_context_catalog_sha256="e" * 64,
            expected_context_id="f" * 64,
            expected_binding_manifest_sha256="d" * 64,
            expected_state_sha256="2" * 64,
            expected_envelope_sha256="1" * 64,
            expected_first_question_sha256=_first_question(sink).ordered_policy_input_sha256,
            expected_first_policy_context_sha256=_first_question(sink).policy_context_sha256,
            expected_first_available_menu_sha256=_first_question(sink).available_menu_sha256,
            expected_model=_different_model(),
            expected_source_commit="1" * 40,
        )


def test_strict_development_admission_binds_selected_propensity_to_vector() -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory()
    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=ExploratoryGoalManagerPolicy(_model(), seed=11),
        trajectory=trajectory,
        budget_meter=meter,
    )

    with pytest.raises(
        GoalManagerDevelopmentError,
        match="selected behavior probability differs",
    ):
        load_repeatable_goal_manager_development_episode(
            _DevelopmentReader(sink, result, tamper_selected_probability=True),
            expected_campaign_id="a" * 64,
            expected_trial_claim_sha256="b" * 64,
            expected_episode_id="development-episode",
            expected_root_lineage_id="red-goal-root-" + "4" * 64,
            expected_seed=11,
            expected_execution_identity_sha256="8" * 64,
            expected_context_catalog_sha256="e" * 64,
            expected_context_id="f" * 64,
            expected_binding_manifest_sha256="d" * 64,
            expected_state_sha256="2" * 64,
            expected_envelope_sha256="1" * 64,
            expected_first_question_sha256=_first_question(sink).ordered_policy_input_sha256,
            expected_first_policy_context_sha256=_first_question(sink).policy_context_sha256,
            expected_first_available_menu_sha256=_first_question(sink).available_menu_sha256,
            expected_model=_model(),
            expected_source_commit="1" * 40,
        )


def test_strict_development_admission_rejects_same_total_species_replacement() -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory()
    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=ExploratoryGoalManagerPolicy(_model(), seed=11),
        trajectory=trajectory,
        budget_meter=meter,
    )

    with pytest.raises(GoalManagerDevelopmentError, match="derived evidence differs"):
        load_repeatable_goal_manager_development_episode(
            _DevelopmentReader(sink, result, tamper_specimen_counts=True),
            expected_campaign_id="a" * 64,
            expected_trial_claim_sha256="b" * 64,
            expected_episode_id="development-episode",
            expected_root_lineage_id="red-goal-root-" + "4" * 64,
            expected_seed=11,
            expected_execution_identity_sha256="8" * 64,
            expected_context_catalog_sha256="e" * 64,
            expected_context_id="f" * 64,
            expected_binding_manifest_sha256="d" * 64,
            expected_state_sha256="2" * 64,
            expected_envelope_sha256="1" * 64,
            expected_first_question_sha256=(
                _first_question(sink).ordered_policy_input_sha256
            ),
            expected_first_policy_context_sha256=(
                _first_question(sink).policy_context_sha256
            ),
            expected_first_available_menu_sha256=(
                _first_question(sink).available_menu_sha256
            ),
            expected_model=_model(),
            expected_source_commit="1" * 40,
        )


def test_strict_development_admission_rejects_non_red_environment() -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory()
    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=ExploratoryGoalManagerPolicy(_model(), seed=11),
        trajectory=trajectory,
        budget_meter=meter,
    )

    with pytest.raises(GoalManagerDevelopmentError, match="provenance differs"):
        load_repeatable_goal_manager_development_episode(
            _DevelopmentReader(sink, result, tamper_environment=True),
            expected_campaign_id="a" * 64,
            expected_trial_claim_sha256="b" * 64,
            expected_episode_id="development-episode",
            expected_root_lineage_id="red-goal-root-" + "4" * 64,
            expected_seed=11,
            expected_execution_identity_sha256="8" * 64,
            expected_context_catalog_sha256="e" * 64,
            expected_context_id="f" * 64,
            expected_binding_manifest_sha256="d" * 64,
            expected_state_sha256="2" * 64,
            expected_envelope_sha256="1" * 64,
            expected_first_question_sha256=(
                _first_question(sink).ordered_policy_input_sha256
            ),
            expected_first_policy_context_sha256=(
                _first_question(sink).policy_context_sha256
            ),
            expected_first_available_menu_sha256=(
                _first_question(sink).available_menu_sha256
            ),
            expected_model=_model(),
            expected_source_commit="1" * 40,
        )


@pytest.mark.parametrize(
    ("reader_kwargs", "message"),
    [
        ({"tamper_decision_identity": True}, "decision identity differs"),
        ({"tamper_terminal_identity": True}, "terminal identity differs"),
    ],
)
def test_strict_development_admission_rejects_renamed_identity(
    reader_kwargs: Mapping[str, bool],
    message: str,
) -> None:
    trajectory, sink = _trajectory()
    observe, meter = _observe_factory()
    result = run_repeatable_goal_manager_development_episode(
        observe=observe,
        policy=ExploratoryGoalManagerPolicy(_model(), seed=11),
        trajectory=trajectory,
        budget_meter=meter,
    )

    with pytest.raises(GoalManagerDevelopmentError, match=message):
        load_repeatable_goal_manager_development_episode(
            _DevelopmentReader(sink, result, **reader_kwargs),
            expected_campaign_id="a" * 64,
            expected_trial_claim_sha256="b" * 64,
            expected_episode_id="development-episode",
            expected_root_lineage_id="red-goal-root-" + "4" * 64,
            expected_seed=11,
            expected_execution_identity_sha256="8" * 64,
            expected_context_catalog_sha256="e" * 64,
            expected_context_id="f" * 64,
            expected_binding_manifest_sha256="d" * 64,
            expected_state_sha256="2" * 64,
            expected_envelope_sha256="1" * 64,
            expected_first_question_sha256=(
                _first_question(sink).ordered_policy_input_sha256
            ),
            expected_first_policy_context_sha256=(
                _first_question(sink).policy_context_sha256
            ),
            expected_first_available_menu_sha256=(
                _first_question(sink).available_menu_sha256
            ),
            expected_model=_model(),
            expected_source_commit="1" * 40,
        )
