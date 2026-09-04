from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from pokemon_red_completion.executor import GoalExecutionBudgetExhausted
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
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
from pokemon_red_completion.multi_goal_calibration_outcome import (
    FORCED_CALIBRATION_POLICY_ID,
    ForcedCalibrationPolicy,
    MultiGoalCalibrationOutcomeError,
    run_forced_calibration_outcome,
)
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.mainline:red:gb:us:rev0",
            mode="overworld",
            location="pokemon.red:forced-calibration-test",
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


def _collection() -> LivingCollectionCheckpoint:
    return LivingCollectionCheckpoint(
        registered_species=1,
        living_species=1,
        required_specimens_remaining=150,
        retained_captures=1,
        storage_headroom=10,
        undeclared_specimen_losses=0,
        completion_contract_sha256="1" * 64,
        specimen_ledger_sha256="2" * 64,
        required_specimens_sha256="3" * 64,
        specimen_counts=(("pokemon:national:001", 1),),
    )


def _trajectory(
    *,
    ordering_assignment_id: str,
) -> tuple[GoalManagerTrajectoryObserver, InMemoryTrajectorySink]:
    sink = InMemoryTrajectorySink()
    snapshot = _SnapshotProvider()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=snapshot,
        sink=sink,
        episode_id="forced-calibration-episode",
    )
    return (
        GoalManagerTrajectoryObserver(
            episode_id="forced-calibration-episode",
            root_lineage_id="red-goal-root-" + "4" * 64,
            partition="train",
            environment_id="pokemon.mainline:red:gb:us:rev0",
            actor="forced_calibration_arm",
            policy_id=FORCED_CALIBRATION_POLICY_ID,
            collection_id="5" * 64,
            assignment_id="6" * 64,
            source_commit="7" * 40,
            snapshot_provider=snapshot,
            recorder=recorder,
            sink=sink,
            ordering_assignment_id=ordering_assignment_id,
        ),
        sink,
    )


def _observe_factory(
    *,
    report_actions: int = 2,
    binding_failure: bool = False,
    binding_failure_actions: int = 0,
    budget_failure: bool = False,
) -> tuple[Callable[[], GoalManagerCompositionObservation], _Meter]:
    state = {"stage": 0, "actions": 0, "frames": 0}
    available = {GoalKind.ADVANCE_STORY, GoalKind.MANAGE_STORAGE}

    def observe() -> GoalManagerCompositionObservation:
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
                if budget_failure:
                    raise GoalExecutionBudgetExhausted("private budget detail")
                if binding_failure:
                    if binding_failure_actions:
                        state["stage"] += 1
                        state["actions"] += binding_failure_actions
                        state["frames"] += binding_failure_actions * 10
                    raise RuntimeError("private binding failure")
                state["stage"] += 1
                state["actions"] += 2
                state["frames"] += 20
                return GoalExecutionReport(report_actions, 20, {"bounded": True})

            return ExecutableGoalBinding(
                binding_ref=f"private:{kind.value}",
                kind=kind,
                estimated_effort=0.2,
                estimated_risk=0.1,
                execute=execute,
                verify=lambda _report: GoalVerification.succeeded(),
            )

        return GoalManagerCompositionObservation(
            semantic_state_sha256=f"{state['stage'] + 1:064x}",
            situation=GoalSituation(*([0.5] * 9)),
            binding_set=GoalBindingSet(
                opportunities,
                tuple(binding(kind) for kind in GoalKind if kind in available),
            ),
            collection=_collection(),
        )

    return observe, _Meter(state)


def _policy(
    observation: GoalManagerCompositionObservation,
    *,
    ordering_assignment_id: str,
    selected_kind: GoalKind = GoalKind.ADVANCE_STORY,
) -> ForcedCalibrationPolicy:
    question = ordered_goal_manager_question(
        assignment_id=ordering_assignment_id,
        decision_index=0,
        situation=observation.situation,
        opportunities=observation.binding_set.opportunities,
    )
    selected_available_ordinal = next(
        ordinal
        for ordinal, index in enumerate(question.available_indices)
        if question.opportunities[index].kind is selected_kind
    )
    return ForcedCalibrationPolicy(
        selected_available_ordinal=selected_available_ordinal,
        selected_goal_kind=selected_kind,
        expected_question_sha256=question.ordered_policy_input_sha256,
        expected_policy_context_sha256=question.policy_context_sha256,
        expected_available_menu_sha256=question.available_menu_sha256,
    )


def test_forced_arm_executes_exactly_one_preregistered_choice() -> None:
    ordering = "8" * 64
    observe, meter = _observe_factory()
    observation = observe()
    question = ordered_goal_manager_question(
        assignment_id=ordering,
        decision_index=0,
        situation=observation.situation,
        opportunities=observation.binding_set.opportunities,
    )
    expected_index = next(
        index
        for index in question.available_indices
        if question.opportunities[index].kind is GoalKind.ADVANCE_STORY
    )
    policy = _policy(observation, ordering_assignment_id=ordering)
    trajectory, sink = _trajectory(ordering_assignment_id=ordering)

    result = run_forced_calibration_outcome(
        observe=observe,
        policy=policy,
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert result.selected_goal_kind is GoalKind.ADVANCE_STORY
    assert result.selected_candidate_index == expected_index
    assert (
        sink.decisions[0].action["selected_candidate_index"]
        == result.selected_candidate_index
    )
    assert result.actions_executed == 2
    assert result.frames_executed == 20
    assert result.semantic_state_changed
    assert policy.decisions == 1
    assert len(sink.decisions) == 1
    assert len(sink.events) == 1
    behavior = sink.decisions[0].context.metadata["behavior_policy"]
    assert behavior["behavior_policy_id"] == FORCED_CALIBRATION_POLICY_ID
    assert behavior["selected_probability"] == 1.0
    assert sum(behavior["candidate_probabilities"]) == 1.0


def test_forced_arm_rejects_question_drift_before_binding_input() -> None:
    ordering = "8" * 64
    observe, meter = _observe_factory()
    policy = _policy(observe(), ordering_assignment_id=ordering)
    policy.expected_available_menu_sha256 = "9" * 64
    trajectory, sink = _trajectory(ordering_assignment_id=ordering)

    with pytest.raises(
        MultiGoalCalibrationOutcomeError,
        match="question differs",
    ):
        run_forced_calibration_outcome(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert meter.state["actions"] == 0
    assert sink.decisions == ()


def test_forced_arm_rejects_a_kind_substitution_before_binding_input() -> None:
    ordering = "8" * 64
    observe, meter = _observe_factory()
    policy = _policy(observe(), ordering_assignment_id=ordering)
    policy.selected_goal_kind = GoalKind.MANAGE_STORAGE
    trajectory, sink = _trajectory(ordering_assignment_id=ordering)

    with pytest.raises(
        MultiGoalCalibrationOutcomeError,
        match="question differs",
    ):
        run_forced_calibration_outcome(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert meter.state["actions"] == 0
    assert sink.decisions == ()


def test_forced_arm_resolves_available_ordinal_to_full_question_index() -> None:
    ordering = "8" * 64
    observe, meter = _observe_factory()
    observation = observe()
    question = ordered_goal_manager_question(
        assignment_id=ordering,
        decision_index=0,
        situation=observation.situation,
        opportunities=observation.binding_set.opportunities,
    )
    selected_kind = GoalKind.ADVANCE_STORY
    selected_full_index = next(
        index
        for index in question.available_indices
        if question.opportunities[index].kind is selected_kind
    )
    selected_available_ordinal = question.available_indices.index(selected_full_index)
    assert selected_available_ordinal != selected_full_index
    policy = _policy(
        observation,
        ordering_assignment_id=ordering,
        selected_kind=selected_kind,
    )
    trajectory, sink = _trajectory(ordering_assignment_id=ordering)

    result = run_forced_calibration_outcome(
        observe=observe,
        policy=policy,
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert result.selected_candidate_index == selected_full_index
    assert (
        sink.decisions[0].action["selected_candidate_index"]
        == selected_full_index
    )
    probabilities = sink.decisions[0].context.metadata["behavior_policy"][
        "candidate_probabilities"
    ]
    assert probabilities[selected_full_index] == 1.0


def test_forced_arm_rejects_self_reported_cost_drift() -> None:
    ordering = "8" * 64
    observe, meter = _observe_factory(report_actions=1)
    policy = _policy(observe(), ordering_assignment_id=ordering)
    trajectory, _sink = _trajectory(ordering_assignment_id=ordering)

    with pytest.raises(
        MultiGoalCalibrationOutcomeError,
        match="independent accounting",
    ):
        run_forced_calibration_outcome(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )


def test_forced_arm_retains_a_binding_failure_as_a_negative_outcome() -> None:
    ordering = "8" * 64
    observe, meter = _observe_factory(binding_failure=True)
    policy = _policy(observe(), ordering_assignment_id=ordering)
    trajectory, sink = _trajectory(ordering_assignment_id=ordering)

    result = run_forced_calibration_outcome(
        observe=observe,
        policy=policy,
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert result.status is GoalDecisionOutcome.FAILED
    assert result.actions_executed == 0
    assert result.frames_executed == 0
    assert result.semantic_state_changed is False
    assert len(sink.decisions) == len(sink.events) == 1
    assert sink.events[0].payload["failure_reason"] == "binding_failed"
    assert "private binding failure" not in json.dumps(result.public_dict())


def test_binding_failure_uses_independent_cost_and_state_accounting() -> None:
    ordering = "8" * 64
    observe, meter = _observe_factory(
        binding_failure=True,
        binding_failure_actions=3,
    )
    policy = _policy(observe(), ordering_assignment_id=ordering)
    trajectory, sink = _trajectory(ordering_assignment_id=ordering)

    result = run_forced_calibration_outcome(
        observe=observe,
        policy=policy,
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert result.status is GoalDecisionOutcome.FAILED
    assert result.actions_executed == 3
    assert result.frames_executed == 30
    assert result.semantic_state_changed is True
    assert sink.events[0].payload["failure_reason"] == "binding_failed"


def test_binding_adapter_preserves_the_typed_budget_failure() -> None:
    ordering = "8" * 64
    observe, meter = _observe_factory(budget_failure=True)
    policy = _policy(observe(), ordering_assignment_id=ordering)
    trajectory, sink = _trajectory(ordering_assignment_id=ordering)

    result = run_forced_calibration_outcome(
        observe=observe,
        policy=policy,
        trajectory=trajectory,
        budget_meter=meter,
    )

    assert result.status is GoalDecisionOutcome.FAILED
    assert result.actions_executed == 0
    assert result.frames_executed == 0
    assert result.semantic_state_changed is False
    assert len(sink.decisions) == len(sink.events) == 1
    assert sink.events[0].payload["failure_reason"] == "execution_budget_exhausted"


def test_forced_policy_cannot_be_reused() -> None:
    ordering = "8" * 64
    observe, _meter = _observe_factory()
    observation = observe()
    policy = _policy(observation, ordering_assignment_id=ordering)
    question = ordered_goal_manager_question(
        assignment_id=ordering,
        decision_index=0,
        situation=observation.situation,
        opportunities=observation.binding_set.opportunities,
    )

    policy.select(question)
    with pytest.raises(MultiGoalCalibrationOutcomeError, match="only once"):
        policy.select(question)
