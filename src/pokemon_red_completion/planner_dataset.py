"""Authenticated joins for semantic whole-game objective demonstrations."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.planner_semantics import (
    ObjectiveFeatureBatch,
    ObjectiveFeatureProjector,
)
from pokemon_red_completion.planner_trajectory import (
    POKEMON_OBJECTIVE_SELECTION_SKILL_ID,
)
from pokemon_red_completion.quest import QuestGraph
from pokemon_red_completion.trajectory import canonical_sha256

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PARTITIONS = frozenset({"train", "validation", "test", "unassigned"})
_FORBIDDEN_INPUT_KEYS = frozenset(
    {"objective_id", "legal_objective_ids", "selected_objective_id"}
)


class PlannerDatasetError(RuntimeError):
    """Raised when a trajectory cannot prove a trustworthy planner dataset."""


class EpisodeReader(Protocol):
    @property
    def manifest_sha256(self) -> str: ...

    def read_header(self) -> Mapping[str, object]: ...

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class PlannerDecisionProvenance:
    actor: str
    policy_id: str
    skill_id: str = POKEMON_OBJECTIVE_SELECTION_SKILL_ID


@dataclass(frozen=True, slots=True)
class PlannerDecisionExample:
    decision_id: str
    snapshot_sha256: str
    step_index: int
    features: ObjectiveFeatureBatch
    chosen_candidate_index: int


@dataclass(frozen=True, slots=True)
class PlannerEpisodeDataset:
    episode_id: str
    game_id: str
    manifest_sha256: str
    root_lineage_id: str
    partition: str
    examples: tuple[PlannerDecisionExample, ...]
    feature_names: tuple[str, ...]

    def public_summary(self) -> dict[str, object]:
        return {
            "schema": "planner-episode-dataset-summary-v1",
            "decisions": len(self.examples),
            "game_id": self.game_id,
            "manifest_sha256": self.manifest_sha256,
            "partition": self.partition,
        }


def load_planner_episode(
    reader: EpisodeReader,
    graph: QuestGraph,
    projector: ObjectiveFeatureProjector,
    *,
    required_provenance: PlannerDecisionProvenance,
) -> PlannerEpisodeDataset:
    """Verify and project every objective choice in one complete episode."""

    header = _mapping(reader.read_header(), subject="episode header")
    if header.get("record_type") != "episode" or header.get("trajectory_schema") != (
        "pokemon.trajectory.v1"
    ):
        raise PlannerDatasetError("private episode has an unsupported header")
    episode_id = _string(header.get("episode_id"), subject="episode identity")
    game_id = _string(header.get("game_id"), subject="game identity")
    metadata = _mapping(header.get("metadata"), subject="episode metadata")
    policy = _mapping(metadata.get("policy"), subject="episode policy metadata")
    if policy.get("actor") != required_provenance.actor or policy.get("policy_id") != (
        required_provenance.policy_id
    ):
        raise PlannerDatasetError("episode provenance does not match the required teacher")
    split = _mapping(metadata.get("split"), subject="episode split metadata")
    partition = _string(split.get("partition"), subject="partition")
    if partition not in _PARTITIONS:
        raise PlannerDatasetError("episode has an unsupported partition")
    root_lineage_id = _string(split.get("root_lineage_id"), subject="root lineage")

    decisions = [
        row
        for row in reader.iter_stream("decisions")
        if row.get("decision_type") == "objective_selection"
    ]
    if len(decisions) != len(graph):
        raise PlannerDatasetError(
            f"planner episode has {len(decisions)} objective labels; expected {len(graph)}"
        )
    needed = {
        _digest(row.get("snapshot_sha256"), subject="decision snapshot digest")
        for row in decisions
    }
    snapshots: dict[str, Mapping[str, object]] = {}
    for row in reader.iter_stream("snapshots"):
        digest = _digest(row.get("snapshot_sha256"), subject="snapshot digest")
        if digest not in needed:
            continue
        snapshot = _mapping(row.get("snapshot"), subject="snapshot")
        if canonical_sha256(snapshot) != digest:
            raise PlannerDatasetError("snapshot content does not match its digest")
        if snapshot.get("game_id") != game_id:
            raise PlannerDatasetError("planner snapshot belongs to another game")
        _reject_label_leakage(snapshot.get("features"))
        snapshots[digest] = snapshot
    if snapshots.keys() != needed:
        raise PlannerDatasetError("planner decision references a missing snapshot")

    examples: list[PlannerDecisionExample] = []
    seen_ids: set[str] = set()
    previous_step = -1
    feature_names: tuple[str, ...] | None = None
    for row in decisions:
        decision_id = _string(row.get("decision_id"), subject="decision identity")
        if decision_id in seen_ids:
            raise PlannerDatasetError("duplicate planner decision identity")
        seen_ids.add(decision_id)
        if row.get("episode_id") != episode_id:
            raise PlannerDatasetError("planner decision belongs to another episode")
        step_index = _integer(row.get("step_index"), subject="decision step")
        if step_index < previous_step:
            raise PlannerDatasetError("planner decision steps move backwards")
        previous_step = step_index
        context = _mapping(row.get("context"), subject="decision context")
        context_metadata = _mapping(context.get("metadata"), subject="context metadata")
        if (
            context.get("actor") != required_provenance.actor
            or context.get("policy_id") != required_provenance.policy_id
            or context_metadata.get("skill_id") != required_provenance.skill_id
        ):
            raise PlannerDatasetError("planner decision provenance is not approved")
        action = _mapping(row.get("action"), subject="planner action")
        if action.get("kind") != "select_objective":
            raise PlannerDatasetError("planner decision has an unsupported action")
        selected_id = _string(action.get("objective_id"), subject="selected objective")
        if context.get("objective_id") != selected_id:
            raise PlannerDatasetError("planner action and context objectives disagree")
        digest = _digest(row.get("snapshot_sha256"), subject="decision snapshot digest")
        snapshot = snapshots[digest]
        facts = frozenset(_strings(snapshot.get("facts"), subject="snapshot facts"))
        legal = graph.available_objectives(GameState(mode=GameMode.OVERWORLD, facts=facts))
        legal_ids = tuple(objective.id for objective in legal)
        declared_legal = tuple(
            _strings(context_metadata.get("legal_objective_ids"), subject="legal objectives")
        )
        if declared_legal != legal_ids:
            raise PlannerDatasetError("declared legal objectives contradict the quest graph")
        if selected_id not in legal_ids:
            raise PlannerDatasetError("teacher selected an illegal objective")
        batch = projector.project(snapshot, legal, objective_count=len(graph))
        if feature_names is None:
            feature_names = batch.feature_names
        elif feature_names != batch.feature_names:
            raise PlannerDatasetError("planner feature schema changed within the episode")
        examples.append(
            PlannerDecisionExample(
                decision_id=decision_id,
                snapshot_sha256=digest,
                step_index=step_index,
                features=batch,
                chosen_candidate_index=legal_ids.index(selected_id),
            )
        )

    terminal = [row for row in reader.iter_stream("events") if row.get("kind") == "terminal"]
    if len(terminal) != 1:
        raise PlannerDatasetError("planner episode requires exactly one terminal event")
    payload = _mapping(terminal[0].get("payload"), subject="terminal payload")
    if payload.get("status") != "complete" or payload.get("game_complete") is not True:
        raise PlannerDatasetError("planner episode is not a completed game")
    return PlannerEpisodeDataset(
        episode_id=episode_id,
        game_id=game_id,
        manifest_sha256=_digest(reader.manifest_sha256, subject="episode manifest digest"),
        root_lineage_id=root_lineage_id,
        partition=partition,
        examples=tuple(examples),
        feature_names=feature_names or (),
    )


def _reject_label_leakage(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in _FORBIDDEN_INPUT_KEYS:
                raise PlannerDatasetError("planner label leaked into policy features")
            _reject_label_leakage(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_label_leakage(nested)


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PlannerDatasetError(f"{subject} must be a mapping")
    return value


def _string(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlannerDatasetError(f"{subject} must be a non-empty string")
    return value


def _strings(value: object, *, subject: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise PlannerDatasetError(f"{subject} must be a sequence")
    return tuple(_string(item, subject=subject) for item in value)


def _integer(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise PlannerDatasetError(f"{subject} must be a non-negative integer")
    return value


def _digest(value: object, *, subject: str) -> str:
    digest = _string(value, subject=subject)
    if _SHA256.fullmatch(digest) is None:
        raise PlannerDatasetError(f"{subject} must be a SHA-256 digest")
    return digest
