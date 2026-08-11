from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.strategic_navigation import (
    DestinationAvailability,
    NavigationDestinationCandidate,
    NavigationFailureReason,
    NavigationOutcomeStatus,
    StrategicInterruptionKind,
    StrategicInterruptionOutcome,
    StrategicInterruptionResolution,
    StrategicNavigationDecision,
    StrategicNavigationOutcome,
    StrategicNavigationRecord,
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_audit import (
    audit_strategic_navigation_collection,
)
from pokemon_red_completion.strategic_navigation_dataset import (
    StrategicNavigationDataset,
    StrategicNavigationDatasetError,
    audit_strategic_navigation_partitions,
    load_assigned_strategic_navigation_episode,
    load_strategic_navigation_episode,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    STRATEGIC_NAVIGATION_DECISION_TYPE,
    STRATEGIC_NAVIGATION_OUTCOME_KIND,
    strategic_navigation_decision_record,
    strategic_navigation_outcome_event,
)
from pokemon_red_completion.trajectory import InMemoryTrajectorySink, SemanticSnapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _Reader:
    manifest_sha256 = "a" * 64

    def __init__(
        self,
        streams: dict[str, list[dict[str, object]]],
        *,
        episode_id: str = "episode-root-train-001",
        root_lineage_id: str = "root-train-001",
        partition: str = "train",
        policy_id: str = "strategic-teacher-v1",
        assigned_metadata: dict[str, object] | None = None,
    ) -> None:
        self.streams = streams
        self.episode_id = episode_id
        self.root_lineage_id = root_lineage_id
        self.partition = partition
        self.policy_id = policy_id
        self.assigned_metadata = assigned_metadata

    def read_header(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "policy": {
                "actor": "deterministic_teacher",
                "policy_id": self.policy_id,
            },
            "split": {
                "root_lineage_id": self.root_lineage_id,
                "partition": self.partition,
            },
        }
        if self.assigned_metadata is not None:
            metadata.update(deepcopy(self.assigned_metadata))
        return {
            "record_type": "episode",
            "trajectory_schema": "pokemon.trajectory.v1",
            "episode_id": self.episode_id,
            "metadata": metadata,
        }

    def iter_stream(self, stream: str) -> Iterator[dict[str, object]]:
        yield from deepcopy(self.streams.get(stream, []))


def _record(
    index: int,
    status: NavigationOutcomeStatus,
    *,
    root: str = "root-train-001",
    partition: str = "train",
    actor: str = "deterministic_teacher",
    policy_id: str = "strategic-teacher-v1",
    episode_id: str | None = None,
    need_tags: tuple[StrategicNavigationTag, ...] = (
        StrategicNavigationTag.ADVANCE_STORY,
    ),
) -> StrategicNavigationRecord:
    decision = StrategicNavigationDecision(
        episode_id=episode_id or f"episode-{root}",
        decision_index=index,
        root_lineage_id=root,
        partition=partition,
        actor=actor,
        policy_id=policy_id,
        semantic_need_tags=need_tags,
        origin_semantic_tags=(StrategicNavigationTag.OVERWORLD,),
        origin_region_ref=f"pokemon.test:region:{root}",
        candidates=(
            NavigationDestinationCandidate(
                destination_ref=f"pokemon.test:destination:{root}:{index}:a",
                semantic_tags=(StrategicNavigationTag.STORY_PROGRESS,),
                availability=DestinationAvailability.AVAILABLE,
                route_cost=12,
                route_steps=10,
                map_transitions=2,
                field_actions=0,
                mode_changes=0,
            ),
            NavigationDestinationCandidate(
                destination_ref=f"pokemon.test:destination:{root}:{index}:b",
                semantic_tags=(StrategicNavigationTag.SAFE_HUB,),
                availability=DestinationAvailability.AVAILABLE,
                route_cost=7,
                route_steps=6,
                map_transitions=1,
                field_actions=0,
                mode_changes=0,
            ),
        ),
        selected_destination_ref=f"pokemon.test:destination:{root}:{index}:a",
    )
    failure_reason = (
        None
        if status is NavigationOutcomeStatus.SUCCEEDED
        else (
            NavigationFailureReason.EXTERNAL_POWER_LOSS
            if status is NavigationOutcomeStatus.INTERRUPTED
            else NavigationFailureReason.REPLAN_BUDGET_EXHAUSTED
        )
    )
    interruptions = (
        (
            StrategicInterruptionOutcome(
                StrategicInterruptionKind.EXTERNAL_POWER_LOSS,
                StrategicInterruptionResolution.CENSORED,
            ),
        )
        if status is NavigationOutcomeStatus.INTERRUPTED
        else ()
    )
    outcome = StrategicNavigationOutcome(
        decision_id=decision.decision_id,
        selected_destination_ref=decision.selected_destination_ref,
        status=status,
        terminal_reached=status is NavigationOutcomeStatus.SUCCEEDED,
        movement_requests=10,
        acknowledged_steps=9,
        wait_actions=1,
        interruptions=interruptions,
        failure_reason=failure_reason,
    )
    return StrategicNavigationRecord(decision, outcome)


def _reader(
    *,
    root: str = "root-train-001",
    partition: str = "train",
    episode_id: str | None = None,
    policy_id: str = "strategic-teacher-v1",
    assigned_metadata: dict[str, object] | None = None,
    statuses: tuple[NavigationOutcomeStatus, ...] = (
        NavigationOutcomeStatus.SUCCEEDED,
        NavigationOutcomeStatus.FAILED,
        NavigationOutcomeStatus.INTERRUPTED,
    ),
) -> _Reader:
    snapshot = SemanticSnapshot(
        game_id="pokemon.test",
        mode="overworld",
        location="pokemon.test:area:origin",
    )
    records = tuple(
        _record(
            index,
            status,
            root=root,
            partition=partition,
            episode_id=episode_id,
            policy_id=policy_id,
        )
        for index, status in enumerate(statuses)
    )
    return _Reader(
        {
            "decisions": [
                strategic_navigation_decision_record(
                    record,
                    snapshot,
                    step_index=index * 10,
                ).to_dict()
                for index, record in enumerate(records)
            ],
            "events": [
                strategic_navigation_outcome_event(
                    record,
                    step_index=index * 10 + 5,
                ).to_dict()
                for index, record in enumerate(records)
            ],
        },
        episode_id=episode_id or f"episode-{root}",
        root_lineage_id=root,
        partition=partition,
        policy_id=policy_id,
        assigned_metadata=assigned_metadata,
    )


def test_dataset_separates_successful_imitation_failure_and_censoring() -> None:
    dataset = StrategicNavigationDataset.from_records(
        (
            _record(0, NavigationOutcomeStatus.SUCCEEDED),
            _record(1, NavigationOutcomeStatus.FAILED),
            _record(2, NavigationOutcomeStatus.INTERRUPTED),
        )
    )

    assert tuple(item.teacher_choice_target for item in dataset.examples) == (0, None, None)
    assert tuple(item.outcome_target for item in dataset.examples) == (True, False, None)
    with pytest.raises(TypeError):
        dataset.examples[0].policy_input["schema"] = "tampered"  # type: ignore[index]
    frozen_candidates = dataset.examples[0].policy_input["candidates"]
    assert isinstance(frozen_candidates, tuple)
    with pytest.raises(TypeError):
        frozen_candidates[0]["route_cost"] = 999  # type: ignore[index]
    assert dataset.public_summary() == {
        "schema": "strategic-navigation-dataset-summary-v1",
        "root_lineage_id": "root-train-001",
        "partition": "train",
        "provenance": {
            "actor": "deterministic_teacher",
            "policy_id": "strategic-teacher-v1",
        },
        "records": 3,
        "outcomes": {"failed": 1, "interrupted": 1, "succeeded": 1},
        "candidate_count_counts": {"2": 3},
        "semantic_need_tag_counts": {"advance_story": 3},
        "teacher_choice_examples": 1,
        "outcome_examples": 2,
        "censored_examples": 1,
        "replan_reason_counts": {},
        "interruption_kind_counts": {"external_power_loss": 1},
        "movement_action_labels": 0,
        "numeric_feature_schema_frozen": False,
        "promotion_eligible": False,
    }


def test_successful_learned_choice_is_outcome_evidence_not_teacher_imitation() -> None:
    dataset = StrategicNavigationDataset.from_records(
        (
            _record(
                0,
                NavigationOutcomeStatus.SUCCEEDED,
                actor="learned_policy",
            ),
        )
    )

    assert dataset.examples[0].teacher_choice_target is None
    assert dataset.examples[0].outcome_target is True
    assert dataset.public_summary()["teacher_choice_examples"] == 0


def test_dataset_rejects_mixed_provenance_and_out_of_order_episode_indexes() -> None:
    first = _record(1, NavigationOutcomeStatus.SUCCEEDED)
    second = _record(0, NavigationOutcomeStatus.SUCCEEDED)

    with pytest.raises(StrategicNavigationDatasetError, match="unique and increasing"):
        StrategicNavigationDataset.from_records((first, second))
    with pytest.raises(StrategicNavigationDatasetError, match="do not share"):
        StrategicNavigationDataset.from_records(
            (
                _record(0, NavigationOutcomeStatus.SUCCEEDED),
                _record(1, NavigationOutcomeStatus.SUCCEEDED, policy_id="other-policy"),
            )
        )


def test_partition_audit_accepts_distinct_train_and_validation_lineages() -> None:
    training = StrategicNavigationDataset.from_records(
        (_record(0, NavigationOutcomeStatus.SUCCEEDED),)
    )
    validation = StrategicNavigationDataset.from_records(
        (
            _record(
                0,
                NavigationOutcomeStatus.SUCCEEDED,
                root="root-validation-001",
                partition="validation",
            ),
        )
    )

    audit = audit_strategic_navigation_partitions((training, validation))

    assert audit.public_dict() == {
        "schema": "strategic-navigation-partition-audit-v1",
        "lineage_count": 2,
        "partition_counts": {"train": 1, "validation": 1},
        "decision_overlap_count": 0,
        "validation_need_tags_missing_from_training": [],
        "ready_for_model_development": True,
        "reasons": [],
    }


def test_partition_audit_fails_closed_on_coverage_and_provenance_gaps() -> None:
    training = StrategicNavigationDataset.from_records(
        (_record(0, NavigationOutcomeStatus.FAILED),)
    )
    validation = StrategicNavigationDataset.from_records(
        (
            _record(
                0,
                NavigationOutcomeStatus.INTERRUPTED,
                root="root-validation-001",
                partition="validation",
                actor="learned_policy",
                need_tags=(StrategicNavigationTag.COMPLETE_COLLECTION,),
            ),
        )
    )

    audit = audit_strategic_navigation_partitions((training, validation))

    assert audit.ready_for_model_development is False
    assert set(audit.reasons) == {
        "mixed_actor",
        "validation_need_tag_absent_from_training",
        "train_has_no_successful_teacher_choice",
        "validation_has_no_successful_teacher_choice",
    }
    assert audit.validation_need_tags_missing_from_training == ("complete_collection",)


def test_duplicate_decision_cannot_cross_lineage_audit() -> None:
    original = _record(0, NavigationOutcomeStatus.SUCCEEDED)
    duplicate_root = StrategicNavigationDataset.from_records((original,))
    second = StrategicNavigationDataset(
        root_lineage_id=original.decision.root_lineage_id,
        partition=original.decision.partition,
        actor=original.decision.actor,
        policy_id=original.decision.policy_id,
        records=(replace(original),),
    )

    audit = audit_strategic_navigation_partitions((duplicate_root, second))

    assert "duplicate_root_lineage" in audit.reasons
    assert "decision_overlap_across_lineages" in audit.reasons
    assert audit.decision_overlap_count == 1


def test_trajectory_projection_persists_identity_free_choice_and_outcome() -> None:
    record = _record(0, NavigationOutcomeStatus.SUCCEEDED)
    snapshot = SemanticSnapshot(
        game_id="pokemon.test",
        mode="overworld",
        location="pokemon.test:area:origin",
        facts=("story:ready",),
        features={"party": {"fainted": 0}},
    )

    decision = strategic_navigation_decision_record(record, snapshot, step_index=20)
    outcome = strategic_navigation_outcome_event(record, step_index=30)
    sink = InMemoryTrajectorySink()
    sink.record_decision(decision)
    sink.record_event(outcome)

    assert decision.decision_type == STRATEGIC_NAVIGATION_DECISION_TYPE
    assert decision.action == {
        "kind": "select_destination",
        "selected_candidate_index": 0,
    }
    assert outcome.kind == STRATEGIC_NAVIGATION_OUTCOME_KIND
    assert outcome.payload["decision_id"] == decision.decision_id
    encoded_choice = json.dumps(
        {
            "context": decision.context.to_dict(),
            "action": decision.to_dict()["action"],
        },
        sort_keys=True,
    )
    encoded_outcome = json.dumps(outcome.to_dict(), sort_keys=True)
    for forbidden in (
        "destination_ref",
        "origin_region_ref",
        "pokemon.test",
        '"direction"',
        '"coordinate"',
        '"map_id"',
    ):
        assert forbidden not in encoded_choice
        assert forbidden not in encoded_outcome
    assert sink.decisions == (decision,)
    assert sink.events == (outcome,)


def test_authenticated_episode_reader_joins_decisions_to_consumed_outcomes() -> None:
    dataset = load_strategic_navigation_episode(_reader())

    assert tuple(item.teacher_choice_target for item in dataset.examples) == (0, None, None)
    assert tuple(item.outcome_target for item in dataset.examples) == (True, False, None)
    assert dataset.public_summary() == {
        "schema": "collected-strategic-navigation-dataset-summary-v1",
        "episode_id": "episode-root-train-001",
        "manifest_sha256": "a" * 64,
        "root_lineage_id": "root-train-001",
        "partition": "train",
        "provenance": {
            "actor": "deterministic_teacher",
            "policy_id": "strategic-teacher-v1",
        },
        "examples": 3,
        "outcomes": {"failed": 1, "interrupted": 1, "succeeded": 1},
        "candidate_count_counts": {"2": 3},
        "semantic_need_tag_counts": {"advance_story": 3},
        "teacher_choice_examples": 1,
        "outcome_examples": 2,
        "censored_examples": 1,
        "replan_reason_counts": {},
        "interruption_kind_counts": {"external_power_loss": 1},
        "movement_action_labels": 0,
        "numeric_feature_schema_frozen": False,
        "promotion_eligible": False,
    }


def test_assigned_reader_requires_committed_metadata_and_seals_test() -> None:
    registry = parse_strategic_navigation_registry(
        (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    local_assignment = registry.learning_assignment("red-strategic-v1-01-train")
    with pytest.raises(StrategicNavigationDatasetError, match="committed source"):
        load_assigned_strategic_navigation_episode(
            _reader(),
            assignment=local_assignment,
        )

    assignment = replace(local_assignment, source_commit="a" * 40)
    reader = _reader(
        root=assignment.root_lineage_id,
        partition=assignment.partition,
        episode_id=assignment.episode_id,
        policy_id="qualified-completion-order-v1",
        assigned_metadata=assignment.episode_metadata(),
        statuses=(NavigationOutcomeStatus.SUCCEEDED,),
    )

    dataset = load_assigned_strategic_navigation_episode(
        reader,
        assignment=assignment,
    )

    assert dataset.episode_id == assignment.episode_id
    assert dataset.root_lineage_id == assignment.root_lineage_id
    assert dataset.partition == "train"

    test_assignment = replace(
        registry.assignment("red-strategic-v1-08-test"),
        source_commit="b" * 40,
    )
    with pytest.raises(StrategicNavigationDatasetError, match="must remain unopened"):
        load_assigned_strategic_navigation_episode(
            reader,
            assignment=test_assignment,
        )


@pytest.mark.parametrize(
    "drifted_block",
    ("collection", "policy", "source", "source_bundle_sha256", "split"),
)
def test_assigned_reader_rejects_each_drifted_identity_block(
    drifted_block: str,
) -> None:
    registry = parse_strategic_navigation_registry(
        (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    assignment = replace(
        registry.learning_assignment("red-strategic-v1-01-train"),
        source_commit="a" * 40,
    )
    metadata = assignment.episode_metadata()
    if drifted_block == "collection":
        collection = metadata["collection"]
        assert isinstance(collection, dict)
        collection["run_id"] = "red-strategic-v1-02-train"
    elif drifted_block == "policy":
        policy = metadata["policy"]
        assert isinstance(policy, dict)
        policy["policy_id"] = "spoofed-policy-v1"
    elif drifted_block == "source":
        metadata["source"] = {"git_commit": "b" * 40}
    elif drifted_block == "source_bundle_sha256":
        metadata["source_bundle_sha256"] = "b" * 64
    else:
        split = metadata["split"]
        assert isinstance(split, dict)
        split["partition"] = "validation"
    reader = _reader(
        root=assignment.root_lineage_id,
        partition=assignment.partition,
        episode_id=assignment.episode_id,
        policy_id="qualified-completion-order-v1",
        assigned_metadata=metadata,
        statuses=(NavigationOutcomeStatus.SUCCEEDED,),
    )

    with pytest.raises(StrategicNavigationDatasetError, match="differs"):
        load_assigned_strategic_navigation_episode(
            reader,
            assignment=assignment,
        )


def test_authenticated_lineages_feed_partition_coverage_and_baseline_audit() -> None:
    training = load_strategic_navigation_episode(_reader())
    validation = load_strategic_navigation_episode(
        _reader(
            root="root-validation-001",
            partition="validation",
            statuses=(NavigationOutcomeStatus.SUCCEEDED,),
        )
    )

    audit = audit_strategic_navigation_collection((training, validation))

    assert audit.public_dict() == {
        "schema": "strategic-navigation-collection-audit-v1",
        "partition_audit": {
            "schema": "strategic-navigation-partition-audit-v1",
            "lineage_count": 2,
            "partition_counts": {"train": 1, "validation": 1},
            "decision_overlap_count": 0,
            "validation_need_tags_missing_from_training": [],
            "ready_for_model_development": True,
            "reasons": [],
        },
        "example_count": 4,
        "partition_example_counts": {"train": 3, "validation": 1},
        "outcomes": {"failed": 1, "interrupted": 1, "succeeded": 2},
        "candidate_count_counts": {"2": 4},
        "candidate_availability_counts": {"available": 8},
        "semantic_need_tag_counts": {"advance_story": 4},
        "selected_index_counts": {"0": 4},
        "replan_reason_counts": {},
        "interruption_kind_counts": {"external_power_loss": 1},
        "resource_renewal_counts": {},
        "failure_reason_counts": {
            "external_power_loss": 1,
            "replan_budget_exhausted": 1,
        },
        "available_route_cost": {"count": 8, "min": 7, "max": 12},
        "route_cost_only_baseline": {
            "unique_minimum_cases": 2,
            "matches": 0,
            "ties_excluded": 0,
        },
        "candidate_shape_baseline": {
            "training_selected_indexes": {"advance_story/2": 0},
            "validation_cases": 1,
            "matches": 1,
        },
        "numeric_feature_schema_frozen": False,
        "model_development_admitted": True,
    }


def test_episode_reader_rejects_identity_leakage_and_outcome_join_tampering() -> None:
    leaked = _reader()
    metadata = leaked.streams["decisions"][0]["context"]
    assert isinstance(metadata, dict)
    metadata = metadata["metadata"]
    assert isinstance(metadata, dict)
    policy_input = metadata["policy_input"]
    assert isinstance(policy_input, dict)
    candidates = policy_input["candidates"]
    assert isinstance(candidates, list)
    candidate = candidates[0]
    assert isinstance(candidate, dict)
    candidate["destination_ref"] = "pokemon.test:map:13"

    with pytest.raises(StrategicNavigationDatasetError, match="candidate schema"):
        load_strategic_navigation_episode(leaked)

    named = _reader()
    context = named.streams["decisions"][0]["context"]
    assert isinstance(context, dict)
    named_metadata = context["metadata"]
    assert isinstance(named_metadata, dict)
    named_input = named_metadata["policy_input"]
    assert isinstance(named_input, dict)
    named_candidates = named_input["candidates"]
    assert isinstance(named_candidates, list)
    named_candidate = named_candidates[0]
    assert isinstance(named_candidate, dict)
    named_candidate["semantic_tags"] = ["viridian_city"]

    with pytest.raises(StrategicNavigationDatasetError, match="title-specific"):
        load_strategic_navigation_episode(named)

    rebound = _reader()
    payload = rebound.streams["events"][0]["payload"]
    assert isinstance(payload, dict)
    payload["selected_candidate_index"] = 1

    with pytest.raises(StrategicNavigationDatasetError, match="binding differs"):
        load_strategic_navigation_episode(rebound)


def test_episode_reader_requires_exactly_one_outcome_per_decision() -> None:
    missing = _reader()
    missing.streams["events"].pop(0)
    with pytest.raises(StrategicNavigationDatasetError, match="no consumed outcome"):
        load_strategic_navigation_episode(missing)

    duplicated = _reader()
    duplicated.streams["events"].append(deepcopy(duplicated.streams["events"][0]))
    with pytest.raises(StrategicNavigationDatasetError, match="more than one outcome"):
        load_strategic_navigation_episode(duplicated)
