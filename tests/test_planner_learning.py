from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy

import pytest

from pokemon_red_completion.planner_dataset import (
    PlannerDatasetError,
    PlannerDecisionProvenance,
    load_planner_episode,
)
from pokemon_red_completion.planner_model import ObjectiveRanker, planner_accuracy
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.planner_trajectory import SemanticObjectiveDecisionObserver
from pokemon_red_completion.play import QUALIFIED_OBJECTIVE_SEQUENCE
from pokemon_red_completion.red_trajectory import (
    POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
)
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
    canonical_sha256,
)


class _Provider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.test",
            mode="interactive",
            location="pokemon.test:area:start",
            features={
                "progress": {"badge_count": 0},
                "world": {"area_kind": "settlement"},
            },
        )


class _Executor:
    def execute(self, action: object) -> object:
        return action


class _Reader:
    manifest_sha256 = "a" * 64

    def __init__(self, streams: dict[str, list[dict[str, object]]]) -> None:
        self.streams = streams

    def read_header(self) -> dict[str, object]:
        return {
            "record_type": "episode",
            "trajectory_schema": "pokemon.trajectory.v1",
            "episode_id": "episode-1",
            "game_id": "pokemon.test",
            "metadata": {
                "policy": {
                    "actor": "deterministic_teacher",
                    "policy_id": POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
                },
                "split": {
                    "partition": "unassigned",
                    "root_lineage_id": "lineage-1",
                },
            },
        }

    def iter_stream(self, stream: str) -> Iterator[dict[str, object]]:
        yield from deepcopy(self.streams.get(stream, []))


def _reader() -> _Reader:
    sink = InMemoryTrajectorySink()
    provider = _Provider()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=provider,
        sink=sink,
        episode_id="episode-1",
    )
    observer = SemanticObjectiveDecisionObserver(
        graph=COMPLETION_QUEST,
        snapshot_provider=provider,
        recorder=recorder,
        policy_id=POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
    )
    for objective_id in QUALIFIED_OBJECTIVE_SEQUENCE:
        observer.select(objective_id)
        observer.complete(objective_id)

    decisions: list[dict[str, object]] = []
    snapshots: dict[str, dict[str, object]] = {}
    for record in sink.decisions:
        row = record.to_dict()
        snapshot = row.pop("snapshot")
        assert isinstance(snapshot, dict)
        decisions.append(row)
        snapshots[record.snapshot_sha256] = {
            "record_type": "snapshot",
            "snapshot_sha256": record.snapshot_sha256,
            "snapshot": snapshot,
        }
    return _Reader(
        {
            "decisions": decisions,
            "snapshots": list(snapshots.values()),
            "events": [
                {
                    "kind": "terminal",
                    "payload": {"status": "complete", "game_complete": True},
                }
            ],
        }
    )


def _load(reader: _Reader):  # type: ignore[no-untyped-def]
    return load_planner_episode(
        reader,
        COMPLETION_QUEST,
        ObjectiveFeatureProjector(),
        required_provenance=PlannerDecisionProvenance(
            actor="deterministic_teacher",
            policy_id=POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
        ),
    )


def test_planner_dataset_authenticates_complete_objective_sequence() -> None:
    dataset = _load(_reader())

    assert len(dataset.examples) == len(COMPLETION_QUEST) == 36
    assert dataset.partition == "unassigned"
    assert dataset.public_summary()["decisions"] == 36
    assert all(example.features.candidate_ids for example in dataset.examples)


def test_planner_dataset_rejects_teacher_label_leakage_into_features() -> None:
    reader = _reader()
    snapshot = reader.streams["snapshots"][0]["snapshot"]
    assert isinstance(snapshot, dict)
    features = snapshot["features"]
    assert isinstance(features, dict)
    features["objective_id"] = "power_on"
    old_digest = reader.streams["snapshots"][0]["snapshot_sha256"]
    new_digest = canonical_sha256(snapshot)
    reader.streams["snapshots"][0]["snapshot_sha256"] = new_digest
    for decision in reader.streams["decisions"]:
        if decision["snapshot_sha256"] == old_digest:
            decision["snapshot_sha256"] = new_digest

    with pytest.raises(PlannerDatasetError, match="label leaked"):
        _load(reader)


def test_first_semantic_objective_ranker_fits_the_demonstrated_route() -> None:
    dataset = _load(_reader())
    examples = tuple(
        (example.features.candidate_vectors, example.chosen_candidate_index)
        for example in dataset.examples
    )

    model = ObjectiveRanker.fit(
        feature_names=dataset.feature_names,
        examples=examples,
        seed=62001,
        epochs=800,
    )

    assert planner_accuracy(model, examples) >= 0.9
    assert model.to_dict()["model_id"] == (
        "pokemon.core.planning.masked-linear-ranker.v1"
    )
