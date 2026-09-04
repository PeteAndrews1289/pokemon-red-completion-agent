from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import replace

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalSelectionMode,
    GoalSituation,
)
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryError,
    GoalManagerTrajectoryObserver,
    load_goal_manager_episode,
    ordered_goal_manager_question,
)
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)


class _Provider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.red",
            mode="overworld",
            location="pokemon.red:area:portable-test",
            features={},
        )


class _Executor:
    def execute(self, action: object) -> object:
        return action


class _Reader:
    manifest_sha256 = "a" * 64

    def __init__(
        self,
        decisions: list[dict[str, object]],
        events: list[dict[str, object]],
    ) -> None:
        self._streams = {"decisions": decisions, "events": events}

    def read_header(self) -> Mapping[str, object]:
        return {
            "record_type": "episode",
            "trajectory_schema": "pokemon.trajectory.v1",
            "episode_id": "goal-episode-1",
            "game_id": "pokemon.red",
            "metadata": {
                "policy": {
                    "actor": "deterministic_teacher",
                    "policy_id": "portable-goal-teacher-v1",
                },
                "split": {
                    "partition": "train",
                    "root_lineage_id": "goal-root-1",
                },
                "goal_manager": {
                    "collection_id": "portable-goal-curriculum-v1",
                    "assignment_id": "goal-assignment-1",
                    "source_commit": "1" * 40,
                    "context_catalog_sha256": "2" * 64,
                    "context_id": "3" * 64,
                    "binding_manifest_sha256": "6" * 64,
                    "state_sha256": "4" * 64,
                    "envelope_sha256": "5" * 64,
                },
            },
        }

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]:
        yield from deepcopy(self._streams.get(stream, []))


def _situation() -> GoalSituation:
    return GoalSituation(
        story_pressure=0.40,
        collection_pressure=0.80,
        team_pressure=0.20,
        evolution_pressure=0.10,
        safety_pressure=0.15,
        resource_pressure=0.10,
        storage_pressure=0.05,
        recovery_pressure=0.0,
        exploration_pressure=0.30,
    )


def _opportunities() -> tuple[GoalOpportunity, ...]:
    return (
        GoalOpportunity(
            "private:red:story-objective",
            GoalKind.ADVANCE_STORY,
            GoalAvailability.AVAILABLE,
            estimated_effort=0.25,
            estimated_risk=0.20,
        ),
        GoalOpportunity(
            "private:red:species-source",
            GoalKind.ACQUIRE_SPECIES,
            GoalAvailability.AVAILABLE,
            estimated_effort=0.40,
            estimated_risk=0.10,
        ),
        GoalOpportunity(
            "private:red:center-route",
            GoalKind.RESTORE_TEAM,
            GoalAvailability.AVAILABLE,
            estimated_effort=0.10,
            estimated_risk=0.01,
        ),
    )


def _observer():  # type: ignore[no-untyped-def]
    sink = InMemoryTrajectorySink()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_Provider(),
        sink=sink,
        episode_id="goal-episode-1",
    )
    observer = GoalManagerTrajectoryObserver(
        episode_id="goal-episode-1",
        root_lineage_id="goal-root-1",
        partition="train",
        environment_id="pokemon.red",
        actor="deterministic_teacher",
        policy_id="portable-goal-teacher-v1",
        collection_id="portable-goal-curriculum-v1",
        assignment_id="goal-assignment-1",
        source_commit="1" * 40,
        snapshot_provider=_Provider(),
        recorder=recorder,
        sink=sink,
    )
    return observer, recorder, sink


def _reader_from_sink(sink: InMemoryTrajectorySink) -> _Reader:
    return _Reader(
        [record.to_dict() for record in sink.decisions],
        [record.to_dict() for record in sink.events],
    )


def test_choice_is_written_before_execution_and_strictly_reloads() -> None:
    observer, recorder, sink = _observer()
    question = observer.ordered_question(_situation(), _opportunities())
    selected = next(
        index
        for index, opportunity in enumerate(question.opportunities)
        if opportunity.kind is GoalKind.ACQUIRE_SPECIES
    )

    pending = observer.record_selection(question, selected)

    assert len(sink.decisions) == 1
    assert not sink.events
    encoded = json.dumps(sink.decisions[0].to_dict(), sort_keys=True)
    assert "private:red" not in encoded
    recorder.execute({"kind": "bounded-specialist-work"})
    assert observer.record_outcome(
        pending,
        status=GoalDecisionOutcome.SUCCEEDED,
    )
    observer.require_settled()

    dataset = load_goal_manager_episode(_reader_from_sink(sink))

    assert len(dataset.examples) == 1
    assert dataset.context_catalog_sha256 == "2" * 64
    assert dataset.binding_manifest_sha256 == "6" * 64
    assert dataset.examples[0].selected_kind is GoalKind.ACQUIRE_SPECIES
    assert dataset.examples[0].teacher_choice_target == selected
    assert dataset.examples[0].question.policy_input == question.policy_input
    assert dataset.public_summary()["private_binding_fields"] == 0


@pytest.mark.parametrize(
    ("status", "reason"),
    (
        (
            GoalDecisionOutcome.FAILED,
            GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED,
        ),
        (
            GoalDecisionOutcome.INTERRUPTED,
            GoalFailureReason.EXTERNAL_INTERRUPTION,
        ),
    ),
)
def test_failure_and_interruption_are_retained_without_imitation_labels(
    status: GoalDecisionOutcome,
    reason: GoalFailureReason,
) -> None:
    observer, _recorder, sink = _observer()
    question = observer.ordered_question(_situation(), _opportunities())
    pending = observer.record_selection(question, 0)
    observer.record_outcome(pending, status=status, failure_reason=reason)

    example = load_goal_manager_episode(_reader_from_sink(sink)).examples[0]

    assert example.outcome_status is status
    assert example.failure_reason is reason
    assert example.teacher_choice_target is None


def test_forced_singleton_is_never_an_imitation_target() -> None:
    observer, _recorder, sink = _observer()
    question = observer.ordered_question(_situation(), _opportunities())
    pending = observer.record_selection(
        question,
        0,
        selection_mode=GoalSelectionMode.FORCED_SINGLETON,
    )
    observer.record_outcome(pending, status=GoalDecisionOutcome.SUCCEEDED)

    example = load_goal_manager_episode(_reader_from_sink(sink)).examples[0]

    assert example.selection_mode is GoalSelectionMode.FORCED_SINGLETON
    assert example.teacher_choice_target is None


def test_outcome_must_consume_the_exact_pending_choice() -> None:
    observer, _recorder, _sink = _observer()
    question = observer.ordered_question(_situation(), _opportunities())
    pending = observer.record_selection(question, 0)

    with pytest.raises(GoalManagerTrajectoryError, match="does not match"):
        observer.record_outcome(
            replace(pending, decision_id="different"),
            status=GoalDecisionOutcome.SUCCEEDED,
        )
    with pytest.raises(GoalManagerTrajectoryError, match="no consumed outcome"):
        observer.require_settled()


def test_candidate_order_depends_on_assignment_not_teacher_label() -> None:
    first = ordered_goal_manager_question(
        assignment_id="assignment-a",
        decision_index=0,
        situation=_situation(),
        opportunities=_opportunities(),
    )
    repeated = ordered_goal_manager_question(
        assignment_id="assignment-a",
        decision_index=0,
        situation=_situation(),
        opportunities=_opportunities(),
    )
    other = ordered_goal_manager_question(
        assignment_id="assignment-c",
        decision_index=0,
        situation=_situation(),
        opportunities=_opportunities(),
    )

    assert first == repeated
    assert {item.kind for item in first.opportunities} == {
        item.kind for item in other.opportunities
    }
    assert tuple(item.kind for item in first.opportunities) != tuple(
        item.kind for item in other.opportunities
    )
    assert first.policy_context_sha256 == other.policy_context_sha256


def test_test_partition_is_closed_by_default() -> None:
    _observer_value, recorder, sink = _observer()
    with pytest.raises(GoalManagerTrajectoryError, match="test partition"):
        GoalManagerTrajectoryObserver(
            episode_id="goal-episode-1",
            root_lineage_id="goal-root-test",
            partition="test",
            environment_id="pokemon.red",
            actor="deterministic_teacher",
            policy_id="portable-goal-teacher-v1",
            collection_id="portable-goal-curriculum-v1",
            assignment_id="goal-assignment-test",
            source_commit="1" * 40,
            snapshot_provider=_Provider(),
            recorder=recorder,
            sink=sink,
        )
