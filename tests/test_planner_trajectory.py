from __future__ import annotations

import json

import pytest

from pokemon_red_completion.planner_trajectory import (
    POKEMON_OBJECTIVE_SELECTION_SKILL_ID,
    SemanticObjectiveDecisionObserver,
)
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.test",
            mode="interactive",
            location="pokemon.test:area:start",
            facts=("pokemon.core:party:available",),
            features={
                "world": {"area_kind": "settlement"},
                "progress": {"badge_count": 0},
            },
        )


class _Executor:
    def execute(self, action: object) -> object:
        return action


def _observer() -> tuple[SemanticObjectiveDecisionObserver, InMemoryTrajectorySink]:
    sink = InMemoryTrajectorySink()
    provider = _SnapshotProvider()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=provider,
        sink=sink,
        episode_id="episode-1",
    )
    return (
        SemanticObjectiveDecisionObserver(
            graph=COMPLETION_QUEST,
            snapshot_provider=provider,
            recorder=recorder,
            policy_id="teacher-v1",
        ),
        sink,
    )


def test_objective_selection_separates_policy_facts_from_teacher_annotations() -> None:
    observer, sink = _observer()

    assert observer.select("power_on")
    observer.complete("power_on")
    assert observer.select("begin_adventure")

    first, second = sink.decisions
    assert first.decision_type == "objective_selection"
    assert first.action == {
        "kind": "select_objective",
        "objective_id": "power_on",
        "specialist": "bootstrap",
    }
    assert first.context.metadata == {
        "skill_id": POKEMON_OBJECTIVE_SELECTION_SKILL_ID,
        "legal_objective_ids": ("power_on",),
    }
    assert "system:clean_power_on" not in first.snapshot.facts
    assert "system:clean_power_on" in second.snapshot.facts
    assert second.action is not None
    assert second.action["objective_id"] == "begin_adventure"

    # Labels and legal candidates are targets/annotations, never model inputs.
    serialized_features = json.dumps(second.snapshot.to_dict()["features"], sort_keys=True)
    assert "begin_adventure" not in serialized_features
    assert "legal_objective_ids" not in serialized_features


def test_objective_selection_rejects_illegal_or_overlapping_teacher_labels() -> None:
    observer, _ = _observer()

    with pytest.raises(ValueError, match="not currently legal"):
        observer.select("defeat_brock")

    observer.select("power_on")
    with pytest.raises(ValueError, match="already active"):
        observer.select("begin_adventure")
    with pytest.raises(ValueError, match="does not match active"):
        observer.complete("begin_adventure")


def test_objective_branches_preserve_multiple_legal_candidates() -> None:
    observer, sink = _observer()
    prefix = (
        "power_on",
        "begin_adventure",
        "choose_starter",
        "receive_pokedex",
        "reach_pewter",
        "defeat_brock",
        "reach_cerulean",
        "help_bill",
        "defeat_misty",
        "reach_vermilion",
        "obtain_cut",
        "defeat_surge",
        "reach_lavender",
        "reach_celadon",
    )
    for objective_id in prefix:
        observer.select(objective_id)
        observer.complete(objective_id)

    observer.select("clear_rocket_hideout")
    decision = sink.decisions[-1]
    assert decision.context.metadata["legal_objective_ids"] == (
        "clear_rocket_hideout",
        "defeat_erika",
        "reach_saffron",
    )
