from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pytest

import pokemon_red_completion.goal_manager_composition_runtime as composition
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    FRESH_COMPOSITION_CONFIDENCE_FLOOR,
    CompositionBudgetCheckpoint,
    GoalManagerCompositionError,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
    require_living_collection_transition,
    run_goal_manager_composition_episode,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
    LearnedGoalManagerPolicy,
    canonical_goal_manager_model_record_sha256,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_trajectory import GoalManagerTrajectoryObserver
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.red",
            mode="overworld",
            location="pokemon.red:area:composition-test",
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


def _model() -> GoalManagerLinearModel:
    weights = np.zeros(len(GOAL_MANAGER_FEATURE_NAMES), dtype=np.float64)
    weights[GOAL_MANAGER_FEATURE_NAMES.index("candidate.addressed_pressure_max")] = 20.0
    return GoalManagerLinearModel(
        weights=weights,
        feature_mean=np.zeros_like(weights),
        feature_scale=np.ones_like(weights),
        l2=0.0,
        training_epochs=1,
    )


def _policy(monkeypatch: pytest.MonkeyPatch) -> LearnedGoalManagerPolicy:
    model = _model()
    monkeypatch.setattr(
        composition,
        "FROZEN_RED_GOAL_MANAGER_SHA256",
        canonical_goal_manager_model_record_sha256(model.to_dict()),
    )
    return LearnedGoalManagerPolicy(
        model,
        confidence_threshold=FRESH_COMPOSITION_CONFIDENCE_FLOOR,
    )


def _trajectory():  # type: ignore[no-untyped-def]
    sink = InMemoryTrajectorySink()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id="composition-episode",
    )
    observer = GoalManagerTrajectoryObserver(
        episode_id="composition-episode",
        root_lineage_id="composition-root",
        partition="validation",
        environment_id="pokemon.red",
        actor="learned_goal_manager",
        policy_id="red-goal-manager-af29d7e7",
        collection_id="fresh-composition-v1",
        assignment_id="composition-assignment",
        source_commit="1" * 40,
        snapshot_provider=_SnapshotProvider(),
        recorder=recorder,
        sink=sink,
    )
    return observer, sink


def _situation(stage: int) -> GoalSituation:
    return GoalSituation(
        story_pressure=0.9 if stage >= 2 else 0.1,
        collection_pressure=0.2,
        team_pressure=0.1,
        evolution_pressure=0.1,
        safety_pressure=0.9 if stage == 0 else 0.1,
        resource_pressure=0.1,
        storage_pressure=0.9 if stage == 1 else 0.1,
        recovery_pressure=0.0,
        exploration_pressure=0.1,
    )


def _observation_factory(
    *,
    failed_verifier: bool = False,
    singleton: bool = False,
    drift_required_digest: bool = False,
    swap_specimen_on_storage: bool = False,
    block_storage_headroom_gain: bool = False,
):
    state = {"stage": 0, "actions": 0, "frames": 0}

    def observe() -> GoalManagerCompositionObservation:
        stage = state["stage"]
        desired = (
            GoalKind.RESTORE_TEAM
            if stage == 0
            else GoalKind.MANAGE_STORAGE
            if stage == 1
            else GoalKind.ADVANCE_STORY
        )
        if singleton:
            available = {desired}
        elif stage in {0, 1}:
            available = {
                GoalKind.ADVANCE_STORY,
                GoalKind.MANAGE_STORAGE,
                GoalKind.RESTORE_TEAM,
            }
        else:
            available = {GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM}
        opportunities = tuple(
            GoalOpportunity(
                binding_ref=f"private:red:{kind.value}",
                kind=kind,
                availability=(
                    GoalAvailability.AVAILABLE
                    if kind in available
                    else GoalAvailability.UNAVAILABLE
                ),
                estimated_effort=0.2 if kind in available else None,
                estimated_risk=0.1 if kind in available else None,
                unavailable_reason=(
                    None if kind in available else GoalUnavailableReason.NO_LEGAL_TARGET
                ),
            )
            for kind in GoalKind
        )

        def binding(kind: GoalKind) -> ExecutableGoalBinding:
            def execute() -> GoalExecutionReport:
                state["stage"] += 1
                state["actions"] += 100
                state["frames"] += 10_000
                return GoalExecutionReport(100, 10_000, {"bounded": True})

            def verify(_report: GoalExecutionReport) -> GoalVerification:
                if failed_verifier:
                    return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                return GoalVerification.succeeded()

            return ExecutableGoalBinding(
                binding_ref=f"private:red:{kind.value}",
                kind=kind,
                estimated_effort=0.2,
                estimated_risk=0.1,
                execute=execute,
                verify=verify,
            )

        bindings = tuple(binding(kind) for kind in GoalKind if kind in available)
        storage_managed = stage >= 2
        specimen_counts = (
            (
                ("pokemon:red:living:replacement", 10),
            )
            if storage_managed and swap_specimen_on_storage
            else (("pokemon:red:living:starter", 10),)
        )
        return GoalManagerCompositionObservation(
            semantic_state_sha256=f"{stage + 1:064x}",
            situation=_situation(stage),
            binding_set=GoalBindingSet(opportunities, bindings),
            collection=LivingCollectionCheckpoint(
                registered_species=10,
                living_species=10,
                required_specimens_remaining=5,
                retained_captures=0,
                storage_headroom=(1 if block_storage_headroom_gain else 9)
                if storage_managed
                else 1,
                undeclared_specimen_losses=0,
                completion_contract_sha256=f"{301:064x}",
                specimen_ledger_sha256=(
                    f"{102 if storage_managed and swap_specimen_on_storage else 101:064x}"
                ),
                required_specimens_sha256=f"{201:064x}"
                if not (drift_required_digest and stage == 1)
                else f"{203:064x}",
                specimen_counts=specimen_counts,
            ),
        )

    return observe, _Meter(state)


def test_composition_runs_three_distinct_learned_choices_and_gains_storage_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    policy = _policy(monkeypatch)
    observe, meter = _observation_factory()

    result = run_goal_manager_composition_episode(
        observe=observe,
        policy=policy,
        trajectory=trajectory,
        budget_meter=meter,
    )
    public = result.public_dict()

    assert [step.selected_kind for step in result.steps] == [
        GoalKind.RESTORE_TEAM,
        GoalKind.MANAGE_STORAGE,
        GoalKind.ADVANCE_STORY,
    ]
    assert result.policy_context_changes == 2
    assert result.available_menu_changes == 1
    assert public["status"] == "core_composition_contract_satisfied"
    assert public["minimum_confidence"] >= 0.8
    assert public["fixed_dispatches"] == 0
    assert public["core_contract_only"] is True
    assert public["execution_receipt_required"] is True
    assert "teacher_queries" not in public
    assert "teacher_fallbacks" not in public
    assert len(sink.decisions) == 3
    assert len(sink.events) == 3
    encoded = json.dumps(public, sort_keys=True)
    assert "private:red" not in encoded
    assert "composition-root" not in encoded


def test_failed_acquisition_requires_nonregression_but_not_false_progress() -> None:
    checkpoint = LivingCollectionCheckpoint(
        registered_species=10,
        living_species=10,
        required_specimens_remaining=5,
        retained_captures=0,
        storage_headroom=1,
        undeclared_specimen_losses=0,
        completion_contract_sha256="1" * 64,
        specimen_ledger_sha256="2" * 64,
        required_specimens_sha256="3" * 64,
        specimen_counts=(("pokemon:red:living:starter", 10),),
    )

    require_living_collection_transition(
        checkpoint,
        checkpoint,
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        require_selected_goal_progress=False,
    )
    with pytest.raises(GoalManagerCompositionError, match="did not change"):
        require_living_collection_transition(
            checkpoint,
            checkpoint,
            selected_kind=GoalKind.ACQUIRE_SPECIES,
        )
def test_composition_rejects_a_singleton_menu_before_prediction_or_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    policy = _policy(monkeypatch)
    observe, meter = _observation_factory(singleton=True)

    with pytest.raises(GoalManagerCompositionError, match="field-composition"):
        run_goal_manager_composition_episode(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert policy.decisions == 0
    assert not sink.decisions
    assert not sink.events


def test_composition_retains_the_first_failed_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    policy = _policy(monkeypatch)
    observe, meter = _observation_factory(failed_verifier=True)

    with pytest.raises(GoalManagerCompositionError, match="verified durable success"):
        run_goal_manager_composition_episode(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert len(sink.decisions) == 1
    assert len(sink.events) == 1
    assert sink.events[0].payload["status"] == "failed"
    assert sink.events[0].payload["failure_reason"] == "outcome_not_verified"


def test_composition_rejects_wrong_model_before_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    policy = LearnedGoalManagerPolicy(
        _model(),
        confidence_threshold=FRESH_COMPOSITION_CONFIDENCE_FLOOR,
    )
    observe, meter = _observation_factory()
    observations = 0

    def counted_observe() -> GoalManagerCompositionObservation:
        nonlocal observations
        observations += 1
        return observe()

    monkeypatch.setattr(composition, "FROZEN_RED_GOAL_MANAGER_SHA256", "f" * 64)
    with pytest.raises(GoalManagerCompositionError, match="frozen design"):
        run_goal_manager_composition_episode(
            observe=counted_observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert observations == 0
    assert policy.decisions == 0
    assert not sink.decisions
    assert not sink.events


def test_composition_rejects_self_report_that_differs_from_independent_meter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    policy = _policy(monkeypatch)
    observe, meter = _observation_factory()
    original_checkpoint = meter.checkpoint
    calls = 0

    def mismatched_checkpoint() -> CompositionBudgetCheckpoint:
        nonlocal calls
        calls += 1
        value = original_checkpoint()
        if calls >= 3:
            return CompositionBudgetCheckpoint(
                controller_actions=value.controller_actions + 1,
                emulator_frames=value.emulator_frames,
            )
        return value

    monkeypatch.setattr(meter, "checkpoint", mismatched_checkpoint)
    with pytest.raises(GoalManagerCompositionError, match="independent budget"):
        run_goal_manager_composition_episode(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert len(sink.decisions) == 1
    assert len(sink.events) == 1


def test_composition_rejects_required_target_drift_after_the_first_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    policy = _policy(monkeypatch)
    observe, meter = _observation_factory(drift_required_digest=True)

    with pytest.raises(GoalManagerCompositionError, match="required-specimen ledger"):
        run_goal_manager_composition_episode(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert len(sink.decisions) == 1
    assert len(sink.events) == 1


def test_composition_rejects_storage_that_replaces_an_existing_specimen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    policy = _policy(monkeypatch)
    observe, meter = _observation_factory(swap_specimen_on_storage=True)

    with pytest.raises(GoalManagerCompositionError, match="collection state regressed"):
        run_goal_manager_composition_episode(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert len(sink.decisions) == 2
    assert len(sink.events) == 2


def test_composition_rejects_storage_without_more_capture_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    policy = _policy(monkeypatch)
    observe, meter = _observation_factory(block_storage_headroom_gain=True)

    with pytest.raises(GoalManagerCompositionError, match="gain headroom"):
        run_goal_manager_composition_episode(
            observe=observe,
            policy=policy,
            trajectory=trajectory,
            budget_meter=meter,
        )

    assert len(sink.decisions) == 2
    assert len(sink.events) == 2
