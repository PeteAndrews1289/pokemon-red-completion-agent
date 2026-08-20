"""Integrity-checked movement-control traces for navigation diagnostics.

The teacher trajectory records every executed macro action, but movement is only
useful supervision when it is tied to the active semantic objective and proves a
world-state transition.  This module performs that join without exposing ROM
addresses or treating menu cursor movement as overworld navigation.

These examples are deliberately *not* strategic destination labels and are not
promotion-eligible.  They may diagnose control or support low-level pretraining,
but the transferable policy boundary ranks semantic destinations while the
deterministic route planner owns exact directions.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    objective_graph_document,
)
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.planner_trajectory import (
    POKEMON_OBJECTIVE_SELECTION_SKILL_ID,
)
from pokemon_red_completion.quest import QuestGraph, quest_graph_payload
from pokemon_red_completion.trajectory import canonical_sha256

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DIRECTIONS = frozenset({"up", "down", "left", "right"})
_PARTITIONS = frozenset({"train", "validation", "test", "unassigned"})


class NavigationDatasetError(RuntimeError):
    """Raised when an episode cannot prove trustworthy navigation labels."""


class EpisodeReader(Protocol):
    @property
    def manifest_sha256(self) -> str: ...

    def read_header(self) -> Mapping[str, object]: ...

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class NavigationDecisionProvenance:
    actor: str
    policy_id: str
    skill_id: str = POKEMON_OBJECTIVE_SELECTION_SKILL_ID

    def __post_init__(self) -> None:
        for name in ("actor", "policy_id", "skill_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise NavigationDatasetError(
                    "navigation provenance fields must be non-empty strings"
                )


@dataclass(frozen=True, slots=True)
class NavigationDecisionExample:
    execution_id: str
    step_index: int
    before_snapshot_sha256: str
    after_snapshot_sha256: str
    objective_id: str
    target_checkpoint_id: str
    goal_specialist: str
    goal_target_region: str | None
    direction: str
    before_area_ref: str
    after_area_ref: str
    before_position: tuple[int, int]
    after_position: tuple[int, int]
    area_transition: bool
    group_id: str

    def __post_init__(self) -> None:
        if not self.execution_id:
            raise NavigationDatasetError("navigation execution identity is empty")
        if type(self.step_index) is not int or self.step_index < 0:  # noqa: E721
            raise NavigationDatasetError("navigation step index is invalid")
        _digest(self.before_snapshot_sha256, subject="before snapshot digest")
        _digest(self.after_snapshot_sha256, subject="after snapshot digest")
        _digest(self.group_id, subject="navigation group digest")
        if self.direction not in _DIRECTIONS:
            raise NavigationDatasetError("navigation direction is invalid")
        if not self.objective_id or not self.target_checkpoint_id or not self.goal_specialist:
            raise NavigationDatasetError("navigation goal identity is incomplete")
        if not self.before_area_ref or not self.after_area_ref:
            raise NavigationDatasetError("navigation area identity is incomplete")
        if self.area_transition is not (self.before_area_ref != self.after_area_ref):
            raise NavigationDatasetError("navigation area transition evidence is inconsistent")


@dataclass(frozen=True, slots=True)
class NavigationEpisodeDataset:
    episode_id: str
    game_id: str
    manifest_sha256: str
    root_lineage_id: str
    partition: str
    objective_graph_sha256: str
    examples: tuple[NavigationDecisionExample, ...]
    excluded_nonprogress_moves: int

    def public_summary(self) -> dict[str, object]:
        directions = Counter(example.direction for example in self.examples)
        return {
            "schema": "navigation-episode-dataset-summary-v1",
            "intended_use": "movement_control_diagnostics_only",
            "label_granularity": "individual_direction",
            "examples": len(self.examples),
            "strategic_destination_decisions": 0,
            "objective_count": len({example.objective_id for example in self.examples}),
            "checkpoint_count": len(
                {example.target_checkpoint_id for example in self.examples}
            ),
            "area_count": len({example.before_area_ref for example in self.examples}),
            "area_transitions": sum(example.area_transition for example in self.examples),
            "direction_counts": dict(sorted(directions.items())),
            "excluded_nonprogress_moves": self.excluded_nonprogress_moves,
            "manifest_sha256": self.manifest_sha256,
            "partition": self.partition,
            "objective_graph_sha256": self.objective_graph_sha256,
            "promotion_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class _ObjectiveSpan:
    step_index: int
    objective_id: str
    specialist: str
    target_region: str | None


@dataclass(frozen=True, slots=True)
class _CheckpointBoundary:
    step_index: int
    checkpoint_id: str


def load_navigation_episode(
    reader: EpisodeReader,
    graph: QuestGraph,
    *,
    required_provenance: NavigationDecisionProvenance,
) -> NavigationEpisodeDataset:
    """Join successful world movement to the active verified teacher objective."""

    if not isinstance(graph, QuestGraph):
        raise TypeError("graph must be a QuestGraph")
    if not isinstance(required_provenance, NavigationDecisionProvenance):
        raise TypeError("required_provenance must be NavigationDecisionProvenance")
    header = _mapping(reader.read_header(), subject="episode header")
    if header.get("record_type") != "episode" or header.get("trajectory_schema") != (
        "pokemon.trajectory.v1"
    ):
        raise NavigationDatasetError("private episode has an unsupported header")
    episode_id = _string(header.get("episode_id"), subject="episode identity")
    game_id = _string(header.get("game_id"), subject="game identity")
    metadata = _mapping(header.get("metadata"), subject="episode metadata")
    objective_graph_sha256 = collection_document_sha256(
        objective_graph_document(quest_graph_payload(graph))
    )
    if metadata.get("objective_graph_sha256") != objective_graph_sha256:
        raise NavigationDatasetError("episode objective graph does not match")
    policy = _mapping(metadata.get("policy"), subject="episode policy")
    if (
        policy.get("actor") != required_provenance.actor
        or policy.get("policy_id") != required_provenance.policy_id
    ):
        raise NavigationDatasetError("episode provenance does not match the teacher")
    split = _mapping(metadata.get("split"), subject="episode split")
    partition = _string(split.get("partition"), subject="partition")
    if partition not in _PARTITIONS:
        raise NavigationDatasetError("episode partition is unsupported")
    root_lineage_id = _string(split.get("root_lineage_id"), subject="root lineage")

    objective_spans = _read_objective_spans(
        reader,
        graph,
        episode_id=episode_id,
        provenance=required_provenance,
    )
    checkpoints = _read_checkpoint_boundaries(reader)
    executions = _read_move_executions(reader, episode_id=episode_id)
    needed_hashes = {
        digest
        for row in executions
        for digest in (
            _digest(row.get("before_sha256"), subject="before snapshot digest"),
            _digest(row.get("after_sha256"), subject="after snapshot digest"),
        )
    }
    snapshots = _read_snapshots(reader, game_id=game_id, needed_hashes=needed_hashes)

    span_steps = tuple(span.step_index for span in objective_spans)
    checkpoint_steps = tuple(item.step_index for item in checkpoints)
    examples: list[NavigationDecisionExample] = []
    excluded_nonprogress = 0
    for row in executions:
        step_index = _integer(row.get("step_index"), subject="execution step")
        span_index = bisect_right(span_steps, step_index) - 1
        if span_index < 0:
            raise NavigationDatasetError("movement precedes the first objective selection")
        span = objective_spans[span_index]
        checkpoint_index = bisect_right(checkpoint_steps, step_index - 1)
        if checkpoint_index >= len(checkpoints):
            raise NavigationDatasetError("movement occurs after the final checkpoint")
        target_checkpoint_id = checkpoints[checkpoint_index].checkpoint_id
        before_digest = _digest(row.get("before_sha256"), subject="before snapshot digest")
        after_digest = _digest(row.get("after_sha256"), subject="after snapshot digest")
        before = snapshots[before_digest]
        after = snapshots[after_digest]
        transition = _world_transition(before, after)
        if transition is None:
            excluded_nonprogress += 1
            continue
        before_area, after_area, before_position, after_position = transition
        action = _mapping(row.get("action"), subject="movement action")
        direction = _string(action.get("value"), subject="movement direction")
        group_id = canonical_sha256(
            {
                "episode_id": episode_id,
                "target_checkpoint_id": target_checkpoint_id,
                "starting_area_ref": before_area,
            }
        )
        examples.append(
            NavigationDecisionExample(
                execution_id=_string(row.get("execution_id"), subject="execution identity"),
                step_index=step_index,
                before_snapshot_sha256=before_digest,
                after_snapshot_sha256=after_digest,
                objective_id=span.objective_id,
                target_checkpoint_id=target_checkpoint_id,
                goal_specialist=span.specialist,
                goal_target_region=span.target_region,
                direction=direction,
                before_area_ref=before_area,
                after_area_ref=after_area,
                before_position=before_position,
                after_position=after_position,
                area_transition=before_area != after_area,
                group_id=group_id,
            )
        )
    if not examples:
        raise NavigationDatasetError("episode contains no progressing world movement")
    _require_complete_terminal(reader)
    return NavigationEpisodeDataset(
        episode_id=episode_id,
        game_id=game_id,
        manifest_sha256=_digest(reader.manifest_sha256, subject="manifest digest"),
        root_lineage_id=root_lineage_id,
        partition=partition,
        objective_graph_sha256=objective_graph_sha256,
        examples=tuple(examples),
        excluded_nonprogress_moves=excluded_nonprogress,
    )


def _read_objective_spans(
    reader: EpisodeReader,
    graph: QuestGraph,
    *,
    episode_id: str,
    provenance: NavigationDecisionProvenance,
) -> tuple[_ObjectiveSpan, ...]:
    rows = [
        row
        for row in reader.iter_stream("decisions")
        if row.get("decision_type") == "objective_selection"
    ]
    if len(rows) != len(graph):
        raise NavigationDatasetError("navigation dataset requires every objective label")
    completed_facts: set[str] = set()
    spans: list[_ObjectiveSpan] = []
    previous_step = -1
    seen: set[str] = set()
    for row in rows:
        if row.get("episode_id") != episode_id:
            raise NavigationDatasetError("objective decision belongs to another episode")
        step = _integer(row.get("step_index"), subject="objective step")
        if step < previous_step:
            raise NavigationDatasetError("objective decision steps move backwards")
        previous_step = step
        action = _mapping(row.get("action"), subject="objective action")
        if action.get("kind") != "select_objective":
            raise NavigationDatasetError("objective decision action is unsupported")
        objective_id = _string(action.get("objective_id"), subject="objective identity")
        if objective_id in seen:
            raise NavigationDatasetError("objective decision is duplicated")
        context = _mapping(row.get("context"), subject="objective context")
        context_metadata = _mapping(context.get("metadata"), subject="objective metadata")
        if (
            context.get("actor") != provenance.actor
            or context.get("policy_id") != provenance.policy_id
            or context_metadata.get("skill_id") != provenance.skill_id
            or context.get("objective_id") != objective_id
        ):
            raise NavigationDatasetError("objective decision provenance is not approved")
        state = GameState(mode=GameMode.OVERWORLD, facts=frozenset(completed_facts))
        legal_ids = tuple(item.id for item in graph.available_objectives(state))
        if objective_id not in legal_ids:
            raise NavigationDatasetError("objective sequence contradicts the quest graph")
        objective = graph.objective(objective_id)
        spans.append(
            _ObjectiveSpan(
                step_index=step,
                objective_id=objective.id,
                specialist=objective.specialist.value,
                target_region=objective.target_region,
            )
        )
        seen.add(objective_id)
        completed_facts.update(objective.completion_facts)
    return tuple(spans)


def _read_move_executions(
    reader: EpisodeReader,
    *,
    episode_id: str,
) -> tuple[Mapping[str, object], ...]:
    result: list[Mapping[str, object]] = []
    previous_step = -1
    seen_ids: set[str] = set()
    for row in reader.iter_stream("executions"):
        action_value = row.get("action")
        if not isinstance(action_value, Mapping) or action_value.get("kind") != "move":
            continue
        if row.get("status") != "success" or action_value.get("value") not in _DIRECTIONS:
            continue
        if action_value.get("repeat") != 1:
            continue
        if row.get("episode_id") != episode_id:
            raise NavigationDatasetError("movement execution belongs to another episode")
        execution_id = _string(row.get("execution_id"), subject="execution identity")
        if execution_id in seen_ids:
            raise NavigationDatasetError("movement execution identity is duplicated")
        seen_ids.add(execution_id)
        step = _integer(row.get("step_index"), subject="execution step")
        if step <= previous_step:
            raise NavigationDatasetError("movement execution steps are not increasing")
        previous_step = step
        result.append(row)
    if not result:
        raise NavigationDatasetError("episode contains no successful movement executions")
    return tuple(result)


def _read_checkpoint_boundaries(
    reader: EpisodeReader,
) -> tuple[_CheckpointBoundary, ...]:
    rows = [row for row in reader.iter_stream("events") if row.get("kind") == "checkpoint"]
    if not rows:
        raise NavigationDatasetError("navigation dataset requires checkpoint boundaries")
    result: list[_CheckpointBoundary] = []
    previous_step = -1
    expected_total: int | None = None
    for ordinal, row in enumerate(rows, start=1):
        step = _integer(row.get("step_index"), subject="checkpoint step")
        if step < previous_step:
            raise NavigationDatasetError("checkpoint steps move backwards")
        previous_step = step
        payload = _mapping(row.get("payload"), subject="checkpoint payload")
        local_checkpoint_id = _string(
            payload.get("checkpoint_id"), subject="checkpoint identity"
        )
        checkpoint_id = f"{ordinal:03d}:{local_checkpoint_id}"
        completed = _integer(payload.get("completed"), subject="checkpoint ordinal")
        total = _integer(payload.get("total"), subject="checkpoint total")
        if completed != ordinal:
            raise NavigationDatasetError("checkpoint ordinals are not contiguous")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise NavigationDatasetError("checkpoint total changes within the episode")
        result.append(_CheckpointBoundary(step, checkpoint_id))
    if expected_total != len(result):
        raise NavigationDatasetError("checkpoint stream is incomplete")
    return tuple(result)


def _read_snapshots(
    reader: EpisodeReader,
    *,
    game_id: str,
    needed_hashes: set[str],
) -> dict[str, Mapping[str, object]]:
    snapshots: dict[str, Mapping[str, object]] = {}
    for row in reader.iter_stream("snapshots"):
        digest = _digest(row.get("snapshot_sha256"), subject="snapshot digest")
        if digest not in needed_hashes:
            continue
        snapshot = _mapping(row.get("snapshot"), subject="snapshot")
        if canonical_sha256(snapshot) != digest:
            raise NavigationDatasetError("snapshot content does not match its digest")
        if snapshot.get("game_id") != game_id:
            raise NavigationDatasetError("navigation snapshot belongs to another game")
        snapshots[digest] = snapshot
    if snapshots.keys() != needed_hashes:
        raise NavigationDatasetError("movement execution references a missing snapshot")
    return snapshots


def _world_transition(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> tuple[str, str, tuple[int, int], tuple[int, int]] | None:
    if before.get("mode") != "interactive" or after.get("mode") != "interactive":
        return None
    before_features = _mapping(before.get("features"), subject="before features")
    after_features = _mapping(after.get("features"), subject="after features")
    before_control = _mapping(before_features.get("control"), subject="before control")
    if before_control.get("input_ready") is not True or before_features.get("battle") is not None:
        return None
    before_world = _mapping(before_features.get("world"), subject="before world")
    after_world = _mapping(after_features.get("world"), subject="after world")
    before_area = _string(before_world.get("area_ref"), subject="before area")
    after_area = _string(after_world.get("area_ref"), subject="after area")
    before_position = _position(before_world.get("position"), subject="before position")
    after_position = _position(after_world.get("position"), subject="after position")
    if before_area == after_area and before_position == after_position:
        return None
    return before_area, after_area, before_position, after_position


def _require_complete_terminal(reader: EpisodeReader) -> None:
    rows = [row for row in reader.iter_stream("events") if row.get("kind") == "terminal"]
    if len(rows) != 1:
        raise NavigationDatasetError("navigation episode requires one terminal event")
    payload = _mapping(rows[0].get("payload"), subject="terminal payload")
    if payload.get("status") != "complete" or payload.get("game_complete") is not True:
        raise NavigationDatasetError("navigation episode is not a completed game")


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise NavigationDatasetError(f"{subject} must be a mapping")
    return value


def _string(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise NavigationDatasetError(f"{subject} must be a non-empty string")
    return value


def _integer(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise NavigationDatasetError(f"{subject} must be a non-negative integer")
    return value


def _position(value: object, *, subject: str) -> tuple[int, int]:
    position = _mapping(value, subject=subject)
    x = _integer(position.get("x"), subject=f"{subject} x")
    y = _integer(position.get("y"), subject=f"{subject} y")
    return x, y


def _digest(value: object, *, subject: str) -> str:
    digest = _string(value, subject=subject)
    if _SHA256.fullmatch(digest) is None:
        raise NavigationDatasetError(f"{subject} must be a SHA-256 digest")
    return digest
