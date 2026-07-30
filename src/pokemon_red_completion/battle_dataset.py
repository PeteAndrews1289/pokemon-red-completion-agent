"""Integrity-checked joins and leakage-resistant grouping for battle decisions.

This module deliberately keeps private identifiers in memory only.  Public summaries
contain aggregate counts and qualification reasons, never trajectory rows, local game
references, filesystem locations, or feature values.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.battle_semantics import (
    BattleFeatureBatch,
    BattleFeatureProjector,
    BattleMovePolicyContext,
)
from pokemon_red_completion.trajectory import canonical_sha256

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,159}\Z")
_PARTITIONS = frozenset({"train", "validation", "test", "unassigned"})


class BattleDatasetError(RuntimeError):
    """Raised when a private episode cannot produce a trustworthy battle dataset."""


class EpisodeReader(Protocol):
    """Path-free subset of :class:`PrivateEpisodeReader` used by this module."""

    @property
    def manifest_sha256(self) -> str: ...

    def read_header(self) -> Mapping[str, object]: ...

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class BattleDecisionProvenance:
    """Disclosed decision source required for one imitation dataset."""

    actor: str
    policy_id: str
    skill_id: str

    def __post_init__(self) -> None:
        for field_name in ("actor", "policy_id", "skill_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise BattleDatasetError(
                    "battle decision provenance fields must be non-empty strings"
                )


@dataclass(frozen=True, slots=True)
class BattleDecisionExample:
    """One private teacher choice joined to its exact policy observation."""

    decision_id: str
    snapshot_sha256: str
    step_index: int
    group_id: str
    group_source: str
    features: BattleFeatureBatch
    chosen_candidate_index: int
    policy_goal_observed: bool
    policy_context: BattleMovePolicyContext | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision_id, str) or not self.decision_id:
            raise BattleDatasetError("battle example has an invalid decision identity")
        _require_sha256(self.snapshot_sha256, subject="snapshot digest")
        if type(self.step_index) is not int or self.step_index < 0:  # noqa: E721
            raise BattleDatasetError("battle example has an invalid step index")
        _require_sha256(self.group_id, subject="battle group digest")
        if self.group_source not in {"explicit_battle_instance", "diagnostic_area_position"}:
            raise BattleDatasetError("battle example has an invalid grouping source")
        if (
            type(self.chosen_candidate_index) is not int  # noqa: E721
            or not 0 <= self.chosen_candidate_index < len(self.features.candidate_vectors)
        ):
            raise BattleDatasetError("battle example has an invalid chosen candidate")
        if not self.features.legal_mask[self.chosen_candidate_index]:
            raise BattleDatasetError("teacher selected an illegal battle candidate")
        if self.policy_goal_observed is not (self.policy_context is not None):
            raise BattleDatasetError(
                "battle policy context presence must match its observation status"
            )


@dataclass(frozen=True, slots=True)
class BattleEpisodeDataset:
    """Battle examples and immutable split provenance from one root episode."""

    episode_id: str
    game_id: str
    manifest_sha256: str
    root_lineage_id: str
    partition: str
    regime: str
    examples: tuple[BattleDecisionExample, ...]
    feature_names: tuple[str, ...]
    diagnostic_reasons: tuple[str, ...]

    @property
    def episode_qualified(self) -> bool:
        """Whether this episode is structurally usable in its declared data lane."""

        return not self.diagnostic_reasons

    @property
    def promotion_eligible(self) -> bool:
        """A single episode can never establish held-out specialist promotion."""

        return False

    @property
    def snapshot_hashes(self) -> frozenset[str]:
        return frozenset(example.snapshot_sha256 for example in self.examples)

    @property
    def group_ids(self) -> frozenset[str]:
        return frozenset(example.group_id for example in self.examples)

    def public_summary(self) -> dict[str, object]:
        slot_counts = [0, 0, 0, 0]
        forced_choice_decisions = 0
        free_choice_decisions = 0
        unobserved_context_decisions = 0
        for example in self.examples:
            slot = example.features.slot_indices[example.chosen_candidate_index]
            if 0 <= slot < len(slot_counts):
                slot_counts[slot] += 1
            if example.policy_context is not None and example.policy_context.forced_choice:
                forced_choice_decisions += 1
            elif example.policy_context is not None:
                free_choice_decisions += 1
            else:
                unobserved_context_decisions += 1
        return {
            "schema": "battle-episode-dataset-summary-v1",
            "decisions": len(self.examples),
            "groups": len(self.group_ids),
            "manifest_sha256": self.manifest_sha256,
            "partition": self.partition,
            "episode_qualified": self.episode_qualified,
            "promotion_eligible": self.promotion_eligible,
            "diagnostic_reasons": list(self.diagnostic_reasons),
            "forced_choice_decisions": forced_choice_decisions,
            "free_choice_decisions": free_choice_decisions,
            "unobserved_context_decisions": unobserved_context_decisions,
            "slot_counts": slot_counts,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticFold:
    """Indices for one deterministic, whole-group diagnostic fold."""

    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    train_groups: int
    test_groups: int


@dataclass(frozen=True, slots=True)
class PartitionAudit:
    """Aggregate-only structural check that cannot establish promotion."""

    episode_count: int
    root_lineage_count: int
    partition_counts: tuple[tuple[str, int], ...]
    snapshot_overlap_count: int
    promotion_eligible: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "battle-partition-audit-v1",
            "episode_count": self.episode_count,
            "root_lineage_count": self.root_lineage_count,
            "partition_counts": dict(self.partition_counts),
            "snapshot_overlap_count": self.snapshot_overlap_count,
            "promotion_eligible": self.promotion_eligible,
            "reasons": list(self.reasons),
        }


def load_battle_episode(
    reader: EpisodeReader,
    projector: BattleFeatureProjector,
    *,
    required_provenance: BattleDecisionProvenance,
) -> BattleEpisodeDataset:
    """Join battle decisions to snapshots after the reader verifies the entire episode."""

    if not hasattr(reader, "read_header") or not hasattr(reader, "iter_stream"):
        raise TypeError("reader must provide the private episode reader interface")
    if not hasattr(projector, "project"):
        raise TypeError("projector must provide the battle feature projector interface")
    if not isinstance(required_provenance, BattleDecisionProvenance):
        raise TypeError("required_provenance must be a BattleDecisionProvenance")

    header = _mapping(reader.read_header(), subject="episode header")
    if header.get("record_type") != "episode":
        raise BattleDatasetError("private episode has an invalid header record type")
    if header.get("trajectory_schema") != "pokemon.trajectory.v1":
        raise BattleDatasetError("private episode uses an unsupported trajectory schema")
    episode_id = _non_empty_string(header.get("episode_id"), subject="episode identity")
    game_id = _non_empty_string(header.get("game_id"), subject="game identity")
    metadata = _mapping(header.get("metadata"), subject="episode metadata")
    policy = _mapping(metadata.get("policy"), subject="episode policy metadata")
    if (
        policy.get("actor") != required_provenance.actor
        or policy.get("policy_id") != required_provenance.policy_id
    ):
        raise BattleDatasetError("episode provenance does not match the required imitation teacher")
    split = _mapping(metadata.get("split"), subject="episode split metadata")
    partition = _non_empty_string(split.get("partition"), subject="episode partition")
    if partition not in _PARTITIONS:
        raise BattleDatasetError("private episode uses an unsupported partition")
    regime = _non_empty_string(split.get("regime"), subject="episode split regime")
    root_lineage_id = _non_empty_string(
        split.get("root_lineage_id"),
        subject="root lineage identity",
    )
    if _SAFE_ID.fullmatch(root_lineage_id) is None:
        raise BattleDatasetError("private episode has an invalid root lineage identity")

    decisions = _read_decisions(
        reader,
        episode_id=episode_id,
        required_provenance=required_provenance,
    )
    needed_hashes = {decision["snapshot_sha256"] for decision in decisions}
    snapshots = _read_referenced_snapshots(
        reader,
        game_id=game_id,
        needed_hashes=needed_hashes,
    )

    examples: list[BattleDecisionExample] = []
    feature_names: tuple[str, ...] | None = None
    previous_step = -1
    seen_decision_ids: set[str] = set()
    inferred_grouping = False
    missing_policy_goal = False

    for decision in decisions:
        decision_id = _non_empty_string(
            decision.get("decision_id"),
            subject="decision identity",
        )
        if decision_id in seen_decision_ids:
            raise BattleDatasetError("private episode contains duplicate decision identities")
        seen_decision_ids.add(decision_id)
        if decision.get("episode_id") != episode_id:
            raise BattleDatasetError("battle decision belongs to a different episode")
        step_index = _non_negative_int(decision.get("step_index"), subject="decision step")
        if step_index <= previous_step:
            raise BattleDatasetError("battle decision steps are not strictly increasing")
        previous_step = step_index

        snapshot_sha256 = _require_sha256(
            decision.get("snapshot_sha256"),
            subject="decision snapshot digest",
        )
        snapshot = snapshots[snapshot_sha256]
        action = _mapping(decision.get("action"), subject="battle decision action")
        if action.get("kind") != "select_move":
            raise BattleDatasetError("battle decision has an unsupported action")
        selected_slot = _non_negative_int(
            action.get("slot_index"),
            subject="selected move slot",
        )

        context = _mapping(decision.get("context"), subject="decision context")
        context_schema_version = context.get("schema_version")
        if type(context_schema_version) is not int or context_schema_version != 1:  # noqa: E721
            raise BattleDatasetError("decision context uses an unsupported schema")
        context_metadata = _mapping(
            context.get("metadata"),
            subject="decision context metadata",
        )
        policy_context = _observed_policy_context(
            context=context,
            context_metadata=context_metadata,
            snapshot=snapshot,
            selected_slot=selected_slot,
        )
        policy_goal_observed = policy_context is not None
        missing_policy_goal = missing_policy_goal or not policy_goal_observed
        batch = projector.project(
            snapshot,
            policy_context=policy_context,
        )
        if feature_names is None:
            feature_names = tuple(batch.feature_names)
        elif tuple(batch.feature_names) != feature_names:
            raise BattleDatasetError("battle feature schema changed within one episode")
        candidate_matches = [
            index
            for index, slot_index in enumerate(batch.slot_indices)
            if slot_index == selected_slot
        ]
        if len(candidate_matches) != 1:
            raise BattleDatasetError("selected move is absent from the projected candidates")
        chosen_candidate_index = candidate_matches[0]
        group_id, group_source = _battle_group(
            context_metadata=context_metadata,
            snapshot=snapshot,
        )
        inferred_grouping = inferred_grouping or group_source != "explicit_battle_instance"
        examples.append(
            BattleDecisionExample(
                decision_id=decision_id,
                snapshot_sha256=snapshot_sha256,
                step_index=step_index,
                group_id=group_id,
                group_source=group_source,
                features=batch,
                chosen_candidate_index=chosen_candidate_index,
                policy_goal_observed=policy_goal_observed,
                policy_context=policy_context,
            )
        )

    if not examples:
        raise BattleDatasetError("private episode contains no battle decisions")

    reasons: set[str] = set()
    if partition == "unassigned":
        reasons.add("unassigned_root_lineage")
    if inferred_grouping:
        reasons.add("inferred_battle_groups")
    if missing_policy_goal:
        reasons.add("policy_goal_not_fully_observed")
    return BattleEpisodeDataset(
        episode_id=episode_id,
        game_id=game_id,
        manifest_sha256=_require_sha256(
            reader.manifest_sha256,
            subject="episode manifest digest",
        ),
        root_lineage_id=root_lineage_id,
        partition=partition,
        regime=regime,
        examples=tuple(examples),
        feature_names=feature_names or (),
        diagnostic_reasons=tuple(sorted(reasons)),
    )


def grouped_diagnostic_folds(
    dataset: BattleEpisodeDataset,
    *,
    fold_count: int = 5,
) -> tuple[DiagnosticFold, ...]:
    """Build deterministic size-balanced folds without ever splitting a battle group."""

    if type(fold_count) is not int or fold_count < 2:  # noqa: E721
        raise BattleDatasetError("diagnostic fold count must be at least two")
    groups: dict[str, list[int]] = defaultdict(list)
    for index, example in enumerate(dataset.examples):
        groups[example.group_id].append(index)
    if len(groups) < fold_count:
        raise BattleDatasetError("not enough battle groups for the requested folds")

    fold_groups: list[list[str]] = [[] for _ in range(fold_count)]
    fold_sizes = [0] * fold_count
    ordered_groups = sorted(groups, key=lambda item: (-len(groups[item]), item))
    for group_id in ordered_groups:
        destination = min(
            range(fold_count),
            key=lambda index: (fold_sizes[index], len(fold_groups[index]), index),
        )
        fold_groups[destination].append(group_id)
        fold_sizes[destination] += len(groups[group_id])

    all_indices = frozenset(range(len(dataset.examples)))
    result: list[DiagnosticFold] = []
    for test_group_ids in fold_groups:
        test_indices = tuple(
            sorted(index for group_id in test_group_ids for index in groups[group_id])
        )
        test_set = frozenset(test_indices)
        train_indices = tuple(sorted(all_indices - test_set))
        result.append(
            DiagnosticFold(
                train_indices=train_indices,
                test_indices=test_indices,
                train_groups=len(groups) - len(test_group_ids),
                test_groups=len(test_group_ids),
            )
        )
    return tuple(result)


def audit_preassigned_partitions(
    datasets: Sequence[BattleEpisodeDataset],
) -> PartitionAudit:
    """Check structural partition leakage without authenticating collection assignments."""

    if not datasets:
        raise BattleDatasetError("partition audit requires at least one episode")
    roots: dict[str, str] = {}
    snapshots_by_partition: dict[str, set[str]] = defaultdict(set)
    partition_counts: dict[str, int] = defaultdict(int)
    reasons: set[str] = {"promotion_protocol_not_authenticated"}
    episode_ids: set[str] = set()
    manifest_ids: set[str] = set()

    expected_game = datasets[0].game_id
    expected_features = datasets[0].feature_names
    for dataset in datasets:
        if dataset.episode_id in episode_ids:
            reasons.add("duplicate_episode_identity")
        episode_ids.add(dataset.episode_id)
        if dataset.manifest_sha256 in manifest_ids:
            reasons.add("duplicate_episode_manifest")
        manifest_ids.add(dataset.manifest_sha256)
        if dataset.game_id != expected_game:
            reasons.add("mixed_game_ids")
        if dataset.feature_names != expected_features:
            reasons.add("mixed_feature_schemas")
        if dataset.partition == "unassigned":
            reasons.add("unassigned_root_lineage")
        previous_partition = roots.setdefault(dataset.root_lineage_id, dataset.partition)
        if previous_partition != dataset.partition:
            reasons.add("root_lineage_partition_overlap")
        snapshots_by_partition[dataset.partition].update(dataset.snapshot_hashes)
        partition_counts[dataset.partition] += 1
        reasons.update(dataset.diagnostic_reasons)

    assigned = ("train", "validation", "test")
    for partition in assigned:
        if partition_counts.get(partition, 0) == 0:
            reasons.add(f"missing_{partition}_partition")
    snapshot_overlap: set[str] = set()
    for left_index, left in enumerate(assigned):
        for right in assigned[left_index + 1 :]:
            snapshot_overlap.update(
                snapshots_by_partition[left].intersection(snapshots_by_partition[right])
            )
    return PartitionAudit(
        episode_count=len(datasets),
        root_lineage_count=len(roots),
        partition_counts=tuple(sorted(partition_counts.items())),
        snapshot_overlap_count=len(snapshot_overlap),
        promotion_eligible=False,
        reasons=tuple(sorted(reasons)),
    )


def _read_decisions(
    reader: EpisodeReader,
    *,
    episode_id: str,
    required_provenance: BattleDecisionProvenance,
) -> list[dict[str, object]]:
    decisions: list[dict[str, object]] = []
    for row in reader.iter_stream("decisions"):
        decision = dict(_mapping(row, subject="decision record"))
        if decision.get("record_type") != "decision":
            raise BattleDatasetError("decision stream contains an invalid record type")
        decision_schema_version = decision.get("schema_version")
        if type(decision_schema_version) is not int or decision_schema_version != 1:  # noqa: E721
            raise BattleDatasetError("decision stream uses an unsupported schema")
        if decision.get("decision_type") != "battle_move_selection":
            continue
        if decision.get("episode_id") != episode_id:
            raise BattleDatasetError("decision stream mixes episode identities")
        context = _mapping(decision.get("context"), subject="decision context")
        metadata = _mapping(context.get("metadata"), subject="decision context metadata")
        if (
            context.get("actor") != required_provenance.actor
            or context.get("policy_id") != required_provenance.policy_id
            or metadata.get("skill_id") != required_provenance.skill_id
        ):
            raise BattleDatasetError(
                "battle decision provenance does not match the required imitation teacher"
            )
        decisions.append(decision)
    return decisions


def _read_referenced_snapshots(
    reader: EpisodeReader,
    *,
    game_id: str,
    needed_hashes: set[object],
) -> dict[str, Mapping[str, object]]:
    normalized_needed = {
        _require_sha256(value, subject="decision snapshot digest") for value in needed_hashes
    }
    snapshots: dict[str, Mapping[str, object]] = {}
    seen_hashes: set[str] = set()
    for row in reader.iter_stream("snapshots"):
        record = _mapping(row, subject="snapshot record")
        if record.get("record_type") != "snapshot":
            raise BattleDatasetError("snapshot stream contains an invalid record type")
        digest = _require_sha256(
            record.get("snapshot_sha256"),
            subject="snapshot content digest",
        )
        if digest in seen_hashes:
            raise BattleDatasetError("snapshot stream contains a duplicate content digest")
        seen_hashes.add(digest)
        snapshot = _mapping(record.get("snapshot"), subject="semantic snapshot")
        if canonical_sha256(snapshot) != digest:
            raise BattleDatasetError("semantic snapshot content digest failed validation")
        if snapshot.get("game_id") != game_id:
            raise BattleDatasetError("snapshot stream mixes game identities")
        if digest in normalized_needed:
            snapshots[digest] = snapshot
    if set(snapshots) != normalized_needed:
        raise BattleDatasetError("battle decision references an absent semantic snapshot")
    return snapshots


def _battle_group(
    *,
    context_metadata: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> tuple[str, str]:
    battle_instance = context_metadata.get("battle_instance_id")
    if isinstance(battle_instance, str) and _SAFE_ID.fullmatch(battle_instance):
        return _opaque_digest({"battle_instance_id": battle_instance}), "explicit_battle_instance"

    location = snapshot.get("location")
    features = _mapping(snapshot.get("features"), subject="snapshot features")
    world = _mapping(features.get("world"), subject="snapshot world features")
    position = _mapping(world.get("position"), subject="snapshot position")
    x = position.get("x")
    y = position.get("y")
    if not isinstance(location, str) or type(x) is not int or type(y) is not int:  # noqa: E721
        raise BattleDatasetError("battle decision lacks a safe diagnostic group proxy")
    return (
        _opaque_digest({"location": location, "x": x, "y": y}),
        "diagnostic_area_position",
    )


def _observed_policy_context(
    *,
    context: Mapping[str, object],
    context_metadata: Mapping[str, object],
    snapshot: Mapping[str, object],
    selected_slot: int,
) -> BattleMovePolicyContext | None:
    objective_id = context.get("objective_id")
    battle_plan_id = context_metadata.get("battle_plan_id")
    if (
        not isinstance(objective_id, str)
        or _SAFE_ID.fullmatch(objective_id) is None
        or not isinstance(battle_plan_id, str)
        or _SAFE_ID.fullmatch(battle_plan_id) is None
        or context_metadata.get("battle_goal") != "win"
    ):
        return None
    policy = context_metadata.get("battle_policy_context")
    if not isinstance(policy, Mapping) or set(policy) != {
        "goal",
        "move_policy",
        "required_move_ref",
    }:
        return None
    recovery_marker = context_metadata.get("teacher_recovery_marker")
    if recovery_marker not in {"none", "bounded_recovery"}:
        return None
    goal = policy.get("goal")
    move_policy = policy.get("move_policy")
    required_move_ref = policy.get("required_move_ref")
    if goal != "win" or move_policy not in {"any_usable", "exact_required"}:
        return None
    if move_policy == "any_usable":
        if required_move_ref is not None:
            return None
        return BattleMovePolicyContext(
            goal="win",
            move_policy="any_usable",
            required_move_ref=None,
        )
    if not isinstance(required_move_ref, str) or not required_move_ref:
        return None

    features = snapshot.get("features")
    if not isinstance(features, Mapping):
        return None
    party = features.get("party")
    if not isinstance(party, Mapping):
        return None
    lead = party.get("lead")
    if not isinstance(lead, Mapping):
        return None
    moves = lead.get("moves")
    if not isinstance(moves, list):
        return None
    selected = [
        move
        for move in moves
        if isinstance(move, Mapping) and move.get("slot_index") == selected_slot
    ]
    if len(selected) != 1 or selected[0].get("move_ref") != required_move_ref:
        return None
    try:
        return BattleMovePolicyContext(
            goal="win",
            move_policy="exact_required",
            required_move_ref=required_move_ref,
        )
    except ValueError:
        return None


def _opaque_digest(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BattleDatasetError(f"{subject} must be a JSON object")
    if not all(isinstance(key, str) for key in value):
        raise BattleDatasetError(f"{subject} contains a non-string key")
    return value


def _non_empty_string(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BattleDatasetError(f"{subject} must be a non-empty string")
    return value


def _non_negative_int(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise BattleDatasetError(f"{subject} must be a non-negative integer")
    return value


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleDatasetError(f"{subject} must be a lowercase SHA-256 digest")
    return value
