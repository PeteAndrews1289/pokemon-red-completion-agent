from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy

import pytest

from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    objective_graph_document,
)
from pokemon_red_completion.navigation_dataset import (
    NavigationDatasetError,
    NavigationDecisionProvenance,
    load_navigation_episode,
)
from pokemon_red_completion.planner_trajectory import (
    POKEMON_OBJECTIVE_SELECTION_SKILL_ID,
)
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist, quest_graph_payload
from pokemon_red_completion.trajectory import canonical_sha256

GRAPH = QuestGraph(
    (
        Objective(
            id="leave_home",
            title="Leave home",
            completion_facts=frozenset({"story:left_home"}),
            specialist=Specialist.NAVIGATION,
            target_region="town",
            priority=1,
        ),
        Objective(
            id="reach_lab",
            title="Reach lab",
            completion_facts=frozenset({"location:lab"}),
            specialist=Specialist.INTERACTION,
            prerequisites=frozenset({"leave_home"}),
            target_region="lab",
            priority=2,
        ),
    )
)


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
                "objective_graph_sha256": collection_document_sha256(
                    objective_graph_document(quest_graph_payload(GRAPH))
                ),
                "policy": {
                    "actor": "deterministic_teacher",
                    "policy_id": "teacher-v1",
                },
                "split": {
                    "partition": "unassigned",
                    "root_lineage_id": "root-1",
                },
            },
        }

    def iter_stream(self, stream: str) -> Iterator[dict[str, object]]:
        yield from deepcopy(self.streams.get(stream, []))


def _snapshot(area: str, x: int, y: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "game_id": "pokemon.test",
        "mode": "interactive",
        "location": area,
        "facts": [],
        "features": {
            "battle": None,
            "control": {"input_ready": True},
            "world": {"area_ref": area, "area_kind": "interior", "position": {"x": x, "y": y}},
        },
    }


def _reader() -> _Reader:
    snapshots = [
        _snapshot("pokemon.test:area:home", 1, 1),
        _snapshot("pokemon.test:area:home", 2, 1),
        _snapshot("pokemon.test:area:town", 2, 2),
    ]
    digests = [canonical_sha256(snapshot) for snapshot in snapshots]
    decisions = []
    for step, objective_id in ((0, "leave_home"), (5, "reach_lab")):
        decisions.append(
            {
                "decision_type": "objective_selection",
                "episode_id": "episode-1",
                "step_index": step,
                "action": {"kind": "select_objective", "objective_id": objective_id},
                "context": {
                    "actor": "deterministic_teacher",
                    "policy_id": "teacher-v1",
                    "objective_id": objective_id,
                    "metadata": {"skill_id": POKEMON_OBJECTIVE_SELECTION_SKILL_ID},
                },
            }
        )
    executions = [
        {
            "execution_id": "execution-1",
            "episode_id": "episode-1",
            "step_index": 1,
            "status": "success",
            "action": {"kind": "move", "value": "right", "repeat": 1},
            "before_sha256": digests[0],
            "after_sha256": digests[1],
        },
        {
            "execution_id": "execution-2",
            "episode_id": "episode-1",
            "step_index": 2,
            "status": "success",
            "action": {"kind": "move", "value": "up", "repeat": 1},
            "before_sha256": digests[1],
            "after_sha256": digests[1],
        },
        {
            "execution_id": "execution-3",
            "episode_id": "episode-1",
            "step_index": 6,
            "status": "success",
            "action": {"kind": "move", "value": "down", "repeat": 1},
            "before_sha256": digests[1],
            "after_sha256": digests[2],
        },
    ]
    return _Reader(
        {
            "decisions": decisions,
            "executions": executions,
            "snapshots": [
                {"snapshot_sha256": digest, "snapshot": snapshot}
                for digest, snapshot in zip(digests, snapshots, strict=True)
            ],
            "events": [
                {
                    "step_index": 3,
                    "kind": "checkpoint",
                    "payload": {
                        "checkpoint_id": "outside_home",
                        "completed": 1,
                        "total": 2,
                    },
                },
                {
                    "step_index": 7,
                    "kind": "checkpoint",
                    "payload": {
                        "checkpoint_id": "lab_door",
                        "completed": 2,
                        "total": 2,
                    },
                },
                {
                    "kind": "terminal",
                    "payload": {"status": "complete", "game_complete": True},
                }
            ],
        }
    )


def _load(reader: _Reader):  # type: ignore[no-untyped-def]
    return load_navigation_episode(
        reader,
        GRAPH,
        required_provenance=NavigationDecisionProvenance(
            actor="deterministic_teacher",
            policy_id="teacher-v1",
        ),
    )


def test_navigation_dataset_joins_progressing_moves_to_active_objectives() -> None:
    dataset = _load(_reader())

    assert [example.direction for example in dataset.examples] == ["right", "down"]
    assert [example.objective_id for example in dataset.examples] == [
        "leave_home",
        "reach_lab",
    ]
    assert [example.target_checkpoint_id for example in dataset.examples] == [
        "001:outside_home",
        "002:lab_door",
    ]
    assert dataset.examples[1].area_transition is True
    assert dataset.excluded_nonprogress_moves == 1
    assert dataset.public_summary() == {
        "schema": "navigation-episode-dataset-summary-v1",
        "examples": 2,
        "objective_count": 2,
        "checkpoint_count": 2,
        "area_count": 1,
        "area_transitions": 1,
        "direction_counts": {"down": 1, "right": 1},
        "excluded_nonprogress_moves": 1,
        "manifest_sha256": "a" * 64,
        "partition": "unassigned",
        "objective_graph_sha256": collection_document_sha256(
            objective_graph_document(quest_graph_payload(GRAPH))
        ),
        "promotion_eligible": False,
    }


def test_navigation_dataset_rejects_tampered_snapshot_content() -> None:
    reader = _reader()
    snapshot = reader.streams["snapshots"][0]["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["location"] = "pokemon.test:area:tampered"

    with pytest.raises(NavigationDatasetError, match="does not match its digest"):
        _load(reader)


def test_navigation_dataset_requires_completed_game_evidence() -> None:
    reader = _reader()
    payload = reader.streams["events"][-1]["payload"]
    assert isinstance(payload, dict)
    payload["game_complete"] = False

    with pytest.raises(NavigationDatasetError, match="not a completed game"):
        _load(reader)
