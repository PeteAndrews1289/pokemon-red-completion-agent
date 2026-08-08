from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    objective_graph_document,
)
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.learned_planner_policy import (
    LearnedPlannerPolicyError,
    ModelObjectivePolicy,
)
from pokemon_red_completion.planner_dataset import (
    PlannerDatasetError,
    PlannerDecisionProvenance,
    load_planner_episode,
)
from pokemon_red_completion.planner_model import (
    ObjectiveRanker,
    PlannerModelError,
    load_objective_model_artifact,
    planner_accuracy,
)
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.planner_trajectory import SemanticObjectiveDecisionObserver
from pokemon_red_completion.play import QUALIFIED_OBJECTIVE_SEQUENCE
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist, quest_graph_payload
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
                "objective_graph_sha256": collection_document_sha256(
                    objective_graph_document(quest_graph_payload(COMPLETION_QUEST))
                ),
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
        ObjectiveFeatureProjector(COMPLETION_QUEST),
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
    assert model.to_dict()["model_id"] == ("pokemon.core.planning.masked-linear-ranker.v1")


def test_projector_matches_current_region_without_exposing_region_identity() -> None:
    snapshot = SemanticSnapshot(
        game_id="pokemon.test",
        mode="interactive",
        location="pokemon.test:area:fuchsia_pokecenter",
        features={
            "progress": {"badge_count": 4},
            "world": {"area_kind": "healing"},
        },
    ).to_dict()
    projector = ObjectiveFeatureProjector(COMPLETION_QUEST)
    batch = projector.project(
        snapshot,
        (
            COMPLETION_QUEST.objective("defeat_koga"),
            COMPLETION_QUEST.objective("defeat_erika"),
        ),
        objective_count=len(COMPLETION_QUEST),
    )
    match_index = batch.feature_names.index("candidate_target_region_matches_current")

    assert batch.candidate_vectors[:, match_index].tolist() == [1.0, 0.0]
    assert all("fuchsia" not in feature for feature in batch.feature_names)


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _model_artifact(tmp_path: Path) -> tuple[Path, ObjectiveRanker, str]:
    projector = ObjectiveFeatureProjector(COMPLETION_QUEST)
    model = ObjectiveRanker(
        feature_names=projector.feature_names,
        weights=[0.0] * len(projector.feature_names),
    )
    graph_sha256 = collection_document_sha256(
        objective_graph_document(quest_graph_payload(COMPLETION_QUEST))
    )
    streams = {
        "model.jsonl": _canonical_line(
            {
                "record_type": "planner_model",
                "model": model.to_dict(),
                "model_sha256": canonical_sha256(model.to_dict()),
                "objective_graph_sha256": graph_sha256,
            }
        ),
        "training.jsonl": _canonical_line({"record_type": "planner_training"}),
        "metrics.jsonl": _canonical_line({"record_type": "planner_metrics"}),
    }
    artifact = tmp_path / "planner-model"
    artifact.mkdir()
    files = []
    for filename, payload in streams.items():
        (artifact / filename).write_bytes(payload)
        files.append(
            {
                "filename": filename,
                "bytes": len(payload),
                "records": 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    (artifact / "manifest.json").write_text(
        json.dumps(
            {
                "format": "pokemon-red-completion-private-artifact-jsonl",
                "kind": "planner_model",
                "schema_version": 1,
                "status": "complete",
                "files": files,
            }
        ),
        encoding="ascii",
    )
    return artifact, model, graph_sha256


def test_objective_model_artifact_authenticates_model_and_graph(tmp_path: Path) -> None:
    artifact, expected, graph_sha256 = _model_artifact(tmp_path)

    loaded = load_objective_model_artifact(
        artifact,
        expected_feature_names=expected.feature_names,
        expected_objective_graph_sha256=graph_sha256,
    )

    assert loaded.to_dict() == expected.to_dict()
    with pytest.raises(PlannerModelError, match="graph-incompatible"):
        load_objective_model_artifact(
            artifact,
            expected_feature_names=expected.feature_names,
            expected_objective_graph_sha256="f" * 64,
        )


def test_live_policy_authorizes_model_choice_and_rejects_route_disagreement() -> None:
    provider = _Provider()
    projector = ObjectiveFeatureProjector(COMPLETION_QUEST)
    model = ObjectiveRanker(
        feature_names=projector.feature_names,
        weights=[0.0] * len(projector.feature_names),
    )
    policy = ModelObjectivePolicy(
        model=model,
        graph=COMPLETION_QUEST,
        snapshot_provider=provider,
    )
    prefix = QUALIFIED_OBJECTIVE_SEQUENCE[:8]
    for objective_id in prefix:
        assert policy.authorize(objective_id) == objective_id
        policy.complete(objective_id)

    with pytest.raises(LearnedPlannerPolicyError, match="different legal objective"):
        policy.authorize("defeat_misty")
    assert policy.public_dict()["teacher_fallbacks"] == 0


def test_live_policy_selects_among_legal_objectives_without_expected_route_label() -> None:
    graph = QuestGraph(
        (
            Objective(
                id="nearby",
                title="Nearby",
                completion_facts=frozenset({"done:nearby"}),
                specialist=Specialist.INTERACTION,
                priority=0,
            ),
            Objective(
                id="preferred",
                title="Preferred",
                completion_facts=frozenset({"done:preferred"}),
                specialist=Specialist.INTERACTION,
                priority=900,
            ),
        )
    )
    projector = ObjectiveFeatureProjector(graph)
    weights = [0.0] * len(projector.feature_names)
    weights[projector.feature_names.index("candidate_priority")] = 100.0
    policy = ModelObjectivePolicy(
        model=ObjectiveRanker(feature_names=projector.feature_names, weights=weights),
        graph=graph,
        snapshot_provider=_Provider(),
    )

    selected = policy.select(GameState(GameMode.OVERWORLD))

    assert selected == "preferred"
    policy.complete(selected)
    report = policy.public_dict()
    assert report["selected_decisions"] == 1
    assert report["authorized_decisions"] == 0
    assert report["route_dispatch_mode"] == "model_selected_specialists"


def test_live_policy_ranks_only_the_supplied_executable_candidates() -> None:
    graph = QuestGraph(
        (
            Objective(
                id="masked",
                title="Masked",
                completion_facts=frozenset({"done:masked"}),
                specialist=Specialist.INTERACTION,
                priority=900,
            ),
            Objective(
                id="executable",
                title="Executable",
                completion_facts=frozenset({"done:executable"}),
                specialist=Specialist.INTERACTION,
                priority=0,
            ),
        )
    )
    projector = ObjectiveFeatureProjector(graph)
    weights = [0.0] * len(projector.feature_names)
    weights[projector.feature_names.index("candidate_priority")] = 100.0
    policy = ModelObjectivePolicy(
        model=ObjectiveRanker(feature_names=projector.feature_names, weights=weights),
        graph=graph,
        snapshot_provider=_Provider(),
    )

    selected = policy.select(
        GameState(GameMode.OVERWORLD),
        (graph.objective("executable"),),
    )

    assert selected == "executable"
