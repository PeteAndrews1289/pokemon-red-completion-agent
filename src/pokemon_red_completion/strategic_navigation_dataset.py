"""Lineage-safe datasets for strategic navigation supervision.

Successful teacher choices may supervise destination ranking. Failed choices
are retained as negative outcome evidence but are never relabelled as correct
imitation targets. Externally interrupted choices remain censored examples, so
a power loss cannot quietly become either success or failure.

The dataset carries the identity-free policy projection from
``strategic_navigation``. It does not freeze a numeric feature vocabulary or
infer collection status from the schema itself; those are later admission gates.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.strategic_navigation import (
    DestinationAvailability,
    DestinationUnavailableReason,
    NavigationDestinationCandidate,
    NavigationFailureReason,
    NavigationOutcomeStatus,
    StrategicInterruptionKind,
    StrategicInterruptionOutcome,
    StrategicInterruptionResolution,
    StrategicNavigationError,
    StrategicNavigationOutcome,
    StrategicNavigationRecord,
    StrategicNavigationTag,
    StrategicReplanOutcome,
    StrategicReplanReason,
    StrategicResourceKind,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_ACTOR,
    STRATEGIC_NAVIGATION_POLICY_ID,
    StrategicNavigationAssignment,
    StrategicNavigationEpisodeAssignment,
    StrategicNavigationRehearsalAssignment,
    StrategicNavigationScenarioRehearsalAssignment,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    STRATEGIC_NAVIGATION_DECISION_TYPE,
    STRATEGIC_NAVIGATION_OUTCOME_KIND,
    STRATEGIC_NAVIGATION_SKILL_ID,
)

_PARTITIONS = frozenset({"train", "validation", "test", "unassigned"})
STRATEGIC_MINIMUM_TRAIN_CONTEXTS = 24
STRATEGIC_MINIMUM_VALIDATION_CONTEXTS = 12


class EpisodeReader(Protocol):
    @property
    def manifest_sha256(self) -> str: ...

    def read_header(self) -> Mapping[str, object]: ...

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]: ...


class StrategicNavigationDatasetError(RuntimeError):
    """Raised when records cannot form a truthful training lineage."""


@dataclass(frozen=True, slots=True)
class StrategicNavigationExample:
    """One strategic choice with separate imitation and outcome targets."""

    decision_id: str
    episode_id: str
    decision_index: int
    root_lineage_id: str
    partition: str
    actor: str
    policy_id: str
    policy_input: Mapping[str, object]
    selected_candidate_index: int
    outcome_status: NavigationOutcomeStatus
    replan_reasons: tuple[StrategicReplanReason, ...] = ()
    interruption_kinds: tuple[StrategicInterruptionKind, ...] = ()
    resource_renewals: tuple[StrategicResourceKind, ...] = ()
    failure_reason: NavigationFailureReason | None = None

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "episode_id",
            "root_lineage_id",
            "partition",
            "actor",
            "policy_id",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise StrategicNavigationDatasetError(f"{name} must be non-empty")
        if type(self.decision_index) is not int or self.decision_index < 0:  # noqa: E721
            raise StrategicNavigationDatasetError("decision index is invalid")
        if not isinstance(self.outcome_status, NavigationOutcomeStatus):
            raise StrategicNavigationDatasetError("example outcome status is invalid")
        for name, expected_type in (
            ("replan_reasons", StrategicReplanReason),
            ("interruption_kinds", StrategicInterruptionKind),
            ("resource_renewals", StrategicResourceKind),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(value, expected_type) for value in values
            ):
                raise StrategicNavigationDatasetError(
                    f"example {name} must use an immutable semantic vocabulary"
                )
        if self.outcome_status is NavigationOutcomeStatus.SUCCEEDED:
            if self.failure_reason is not None:
                raise StrategicNavigationDatasetError(
                    "a successful example cannot carry a failure reason"
                )
        elif not isinstance(self.failure_reason, NavigationFailureReason):
            raise StrategicNavigationDatasetError(
                "a failed or interrupted example needs a semantic failure reason"
            )
        canonical = _policy_input(
            _thaw_policy_input(self.policy_input),
            subject="strategic example policy input",
        )
        candidates = canonical["candidates"]
        assert isinstance(candidates, list)
        if self.selected_candidate_index not in range(len(candidates)):
            raise StrategicNavigationDatasetError("example selected index is invalid")
        object.__setattr__(self, "policy_input", _freeze_policy_input(canonical))

    @property
    def teacher_choice_target(self) -> int | None:
        """Return a label only for a successfully executed deterministic-teacher choice."""

        if (
            self.outcome_status is NavigationOutcomeStatus.SUCCEEDED
            and self.actor == "deterministic_teacher"
        ):
            return self.selected_candidate_index
        return None

    @property
    def outcome_target(self) -> bool | None:
        """Return success/failure while preserving external censoring."""

        if self.outcome_status is NavigationOutcomeStatus.SUCCEEDED:
            return True
        if self.outcome_status is NavigationOutcomeStatus.FAILED:
            return False
        return None

    @property
    def candidates(self) -> tuple[Mapping[str, object], ...]:
        """Return the validated immutable identity-free candidate rows."""

        return _candidate_rows(self)

    @property
    def semantic_need_tags(self) -> tuple[str, ...]:
        """Return the validated portable need vocabulary for this decision."""

        return _need_tags(self)

    @property
    def ordered_policy_input_sha256(self) -> str:
        """Hash the exact model-facing candidate order for diagnostics."""

        return strategic_ordered_policy_input_sha256(self.policy_input)

    @property
    def policy_context_sha256(self) -> str:
        """Hash the model-facing question independently of candidate order."""

        return strategic_policy_context_sha256(self.policy_input)

    @property
    def selected_candidate_sha256(self) -> str:
        """Hash the selected identity-free candidate independently of its slot."""

        return strategic_selected_candidate_sha256(self)


@dataclass(frozen=True, slots=True)
class StrategicNavigationDataset:
    """One root lineage of genuine destination choices and consumed outcomes."""

    root_lineage_id: str
    partition: str
    actor: str
    policy_id: str
    records: tuple[StrategicNavigationRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or not self.records:
            raise StrategicNavigationDatasetError(
                "a strategic navigation dataset needs an immutable non-empty record tuple"
            )
        expected = (
            self.root_lineage_id,
            self.partition,
            self.actor,
            self.policy_id,
        )
        if any(
            (
                record.decision.root_lineage_id,
                record.decision.partition,
                record.decision.actor,
                record.decision.policy_id,
            )
            != expected
            for record in self.records
        ):
            raise StrategicNavigationDatasetError(
                "dataset records do not share lineage, partition and policy provenance"
            )
        decision_ids = tuple(record.decision.decision_id for record in self.records)
        if len(set(decision_ids)) != len(decision_ids):
            raise StrategicNavigationDatasetError("dataset repeats a strategic decision")
        by_episode: defaultdict[str, list[int]] = defaultdict(list)
        for record in self.records:
            by_episode[record.decision.episode_id].append(record.decision.decision_index)
        if any(indexes != sorted(set(indexes)) for indexes in by_episode.values()):
            raise StrategicNavigationDatasetError(
                "episode decision indexes must be unique and increasing"
            )

    @classmethod
    def from_records(
        cls,
        records: Iterable[StrategicNavigationRecord],
    ) -> StrategicNavigationDataset:
        rows = tuple(records)
        if not rows:
            raise StrategicNavigationDatasetError(
                "a strategic navigation dataset needs at least one record"
            )
        first = rows[0].decision
        return cls(
            root_lineage_id=first.root_lineage_id,
            partition=first.partition,
            actor=first.actor,
            policy_id=first.policy_id,
            records=rows,
        )

    @property
    def examples(self) -> tuple[StrategicNavigationExample, ...]:
        return tuple(
            StrategicNavigationExample(
                decision_id=record.decision.decision_id,
                episode_id=record.decision.episode_id,
                decision_index=record.decision.decision_index,
                root_lineage_id=record.decision.root_lineage_id,
                partition=record.decision.partition,
                actor=record.decision.actor,
                policy_id=record.decision.policy_id,
                policy_input=record.decision.policy_input(),
                selected_candidate_index=record.decision.selected_index,
                outcome_status=record.outcome.status,
                replan_reasons=tuple(item.reason for item in record.outcome.replans),
                interruption_kinds=tuple(
                    item.kind for item in record.outcome.interruptions
                ),
                resource_renewals=record.outcome.resource_renewals,
                failure_reason=record.outcome.failure_reason,
            )
            for record in self.records
        )

    @property
    def semantic_need_tags(self) -> frozenset[str]:
        return frozenset(
            tag.value
            for record in self.records
            for tag in record.decision.semantic_need_tags
        )

    def public_summary(self) -> dict[str, object]:
        outcomes = Counter(record.outcome.status.value for record in self.records)
        candidate_counts = Counter(
            len(record.decision.candidates) for record in self.records
        )
        need_tags = Counter(
            tag.value
            for record in self.records
            for tag in record.decision.semantic_need_tags
        )
        replan_reasons = Counter(
            replan.reason.value
            for record in self.records
            for replan in record.outcome.replans
        )
        interruption_kinds = Counter(
            interruption.kind.value
            for record in self.records
            for interruption in record.outcome.interruptions
        )
        examples = self.examples
        return {
            "schema": "strategic-navigation-dataset-summary-v1",
            "root_lineage_id": self.root_lineage_id,
            "partition": self.partition,
            "provenance": {"actor": self.actor, "policy_id": self.policy_id},
            "records": len(self.records),
            "outcomes": dict(sorted(outcomes.items())),
            "candidate_count_counts": {
                str(count): total for count, total in sorted(candidate_counts.items())
            },
            "semantic_need_tag_counts": dict(sorted(need_tags.items())),
            "teacher_choice_examples": sum(
                item.teacher_choice_target is not None for item in examples
            ),
            "unique_teacher_choice_contexts": len(
                {
                    item.policy_context_sha256
                    for item in examples
                    if item.teacher_choice_target is not None
                }
            ),
            "outcome_examples": sum(item.outcome_target is not None for item in examples),
            "censored_examples": sum(item.outcome_target is None for item in examples),
            "replan_reason_counts": dict(sorted(replan_reasons.items())),
            "interruption_kind_counts": dict(sorted(interruption_kinds.items())),
            "movement_action_labels": 0,
            "numeric_feature_schema_frozen": False,
            "promotion_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class CollectedStrategicNavigationDataset:
    """Identity-free examples joined from one authenticated private episode."""

    episode_id: str
    manifest_sha256: str
    root_lineage_id: str
    partition: str
    actor: str
    policy_id: str
    examples: tuple[StrategicNavigationExample, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.examples, tuple) or not self.examples:
            raise StrategicNavigationDatasetError(
                "a collected navigation dataset needs an immutable non-empty example tuple"
            )
        if any(
            (
                item.episode_id,
                item.root_lineage_id,
                item.partition,
                item.actor,
                item.policy_id,
            )
            != (
                self.episode_id,
                self.root_lineage_id,
                self.partition,
                self.actor,
                self.policy_id,
            )
            for item in self.examples
        ):
            raise StrategicNavigationDatasetError(
                "collected navigation examples contradict their episode provenance"
            )

    def public_summary(self) -> dict[str, object]:
        outcomes = Counter(item.outcome_status.value for item in self.examples)
        candidate_counts = Counter(
            len(_candidate_rows(item)) for item in self.examples
        )
        need_tags = Counter(
            tag for item in self.examples for tag in _need_tags(item)
        )
        replan_reasons = Counter(
            reason.value for item in self.examples for reason in item.replan_reasons
        )
        interruption_kinds = Counter(
            kind.value for item in self.examples for kind in item.interruption_kinds
        )
        return {
            "schema": "collected-strategic-navigation-dataset-summary-v1",
            "episode_id": self.episode_id,
            "manifest_sha256": self.manifest_sha256,
            "root_lineage_id": self.root_lineage_id,
            "partition": self.partition,
            "provenance": {"actor": self.actor, "policy_id": self.policy_id},
            "examples": len(self.examples),
            "outcomes": dict(sorted(outcomes.items())),
            "candidate_count_counts": {
                str(count): total for count, total in sorted(candidate_counts.items())
            },
            "semantic_need_tag_counts": dict(sorted(need_tags.items())),
            "teacher_choice_examples": sum(
                item.teacher_choice_target is not None for item in self.examples
            ),
            "unique_teacher_choice_contexts": len(
                {
                    item.policy_context_sha256
                    for item in self.examples
                    if item.teacher_choice_target is not None
                }
            ),
            "outcome_examples": sum(
                item.outcome_target is not None for item in self.examples
            ),
            "censored_examples": sum(
                item.outcome_target is None for item in self.examples
            ),
            "replan_reason_counts": dict(sorted(replan_reasons.items())),
            "interruption_kind_counts": dict(sorted(interruption_kinds.items())),
            "movement_action_labels": 0,
            "numeric_feature_schema_frozen": False,
            "promotion_eligible": False,
        }

    @property
    def semantic_need_tags(self) -> frozenset[str]:
        return frozenset(
            tag for example in self.examples for tag in _need_tags(example)
        )


def load_strategic_navigation_episode(
    reader: EpisodeReader,
) -> CollectedStrategicNavigationDataset:
    """Join strategic decisions to one consumed semantic outcome each."""

    header = _mapping(reader.read_header(), subject="episode header")
    if header.get("record_type") != "episode" or header.get("trajectory_schema") != (
        "pokemon.trajectory.v1"
    ):
        raise StrategicNavigationDatasetError("episode header schema is incompatible")
    episode_id = _string(header.get("episode_id"), subject="episode identity")
    metadata = _mapping(header.get("metadata"), subject="episode metadata")
    policy = _mapping(metadata.get("policy"), subject="episode policy")
    actor = _string(policy.get("actor"), subject="episode actor")
    policy_id = _string(policy.get("policy_id"), subject="episode policy identity")
    split = _mapping(metadata.get("split"), subject="episode split")
    root_lineage_id = _string(
        split.get("root_lineage_id"), subject="root lineage identity"
    )
    partition = _string(split.get("partition"), subject="episode partition")
    if partition not in _PARTITIONS:
        raise StrategicNavigationDatasetError("episode partition is unsupported")

    raw_decisions = [
        _mapping(row, subject="strategic decision")
        for row in reader.iter_stream("decisions")
        if row.get("decision_type") == STRATEGIC_NAVIGATION_DECISION_TYPE
    ]
    raw_events = [
        _mapping(row, subject="strategic outcome")
        for row in reader.iter_stream("events")
        if row.get("kind") == STRATEGIC_NAVIGATION_OUTCOME_KIND
    ]
    if not raw_decisions:
        raise StrategicNavigationDatasetError("episode has no strategic navigation decisions")
    events_by_decision: dict[str, Mapping[str, object]] = {}
    for event in raw_events:
        payload = _mapping(event.get("payload"), subject="strategic outcome payload")
        decision_id = _string(
            payload.get("decision_id"), subject="outcome decision identity"
        )
        if decision_id in events_by_decision:
            raise StrategicNavigationDatasetError(
                "strategic decision has more than one outcome"
            )
        events_by_decision[decision_id] = payload

    examples: list[StrategicNavigationExample] = []
    seen: set[str] = set()
    previous_index = -1
    for row in raw_decisions:
        decision_id = _string(row.get("decision_id"), subject="decision identity")
        if decision_id in seen:
            raise StrategicNavigationDatasetError("strategic decision is duplicated")
        seen.add(decision_id)
        row_episode = _string(row.get("episode_id"), subject="decision episode")
        if row_episode != episode_id:
            raise StrategicNavigationDatasetError("strategic decision episode differs")
        context = _mapping(row.get("context"), subject="strategic decision context")
        if context.get("actor") != actor or context.get("policy_id") != policy_id:
            raise StrategicNavigationDatasetError("strategic decision policy differs")
        decision_metadata = _mapping(
            context.get("metadata"), subject="strategic decision metadata"
        )
        if decision_metadata.get("skill_id") != STRATEGIC_NAVIGATION_SKILL_ID:
            raise StrategicNavigationDatasetError("strategic decision skill differs")
        if (
            decision_metadata.get("root_lineage_id") != root_lineage_id
            or decision_metadata.get("partition") != partition
        ):
            raise StrategicNavigationDatasetError("strategic decision split differs")
        strategic_index = _integer(
            decision_metadata.get("strategic_decision_index"),
            subject="strategic decision index",
        )
        if strategic_index <= previous_index:
            raise StrategicNavigationDatasetError(
                "strategic decision indexes must be strictly increasing"
            )
        previous_index = strategic_index
        policy_input = _policy_input(
            decision_metadata.get("policy_input"),
            subject="strategic policy input",
        )
        action = _mapping(row.get("action"), subject="strategic decision action")
        if set(action) != {"kind", "selected_candidate_index"} or action.get(
            "kind"
        ) != "select_destination":
            raise StrategicNavigationDatasetError("strategic decision action is invalid")
        selected_index = _integer(
            action.get("selected_candidate_index"), subject="selected candidate index"
        )
        candidates = policy_input["candidates"]
        assert isinstance(candidates, list)
        if selected_index not in range(len(candidates)):
            raise StrategicNavigationDatasetError("selected candidate index is invalid")
        selected_candidate = candidates[selected_index]
        assert isinstance(selected_candidate, dict)
        if selected_candidate.get("availability") != DestinationAvailability.AVAILABLE.value:
            raise StrategicNavigationDatasetError("selected candidate is not available")
        try:
            outcome_payload = events_by_decision.pop(decision_id)
        except KeyError as error:
            raise StrategicNavigationDatasetError(
                "strategic decision has no consumed outcome"
            ) from error
        outcome = _validated_outcome(
            outcome_payload,
            decision_id=decision_id,
            selected_index=selected_index,
        )
        examples.append(
            StrategicNavigationExample(
                decision_id=decision_id,
                episode_id=episode_id,
                decision_index=strategic_index,
                root_lineage_id=root_lineage_id,
                partition=partition,
                actor=actor,
                policy_id=policy_id,
                policy_input=policy_input,
                selected_candidate_index=selected_index,
                outcome_status=outcome.status,
                replan_reasons=tuple(item.reason for item in outcome.replans),
                interruption_kinds=tuple(
                    item.kind for item in outcome.interruptions
                ),
                resource_renewals=outcome.resource_renewals,
                failure_reason=outcome.failure_reason,
            )
        )
    if events_by_decision:
        raise StrategicNavigationDatasetError("outcome has no strategic decision")
    return CollectedStrategicNavigationDataset(
        episode_id=episode_id,
        manifest_sha256=_digest(reader.manifest_sha256, subject="episode manifest"),
        root_lineage_id=root_lineage_id,
        partition=partition,
        actor=actor,
        policy_id=policy_id,
        examples=tuple(examples),
    )


def load_assigned_strategic_navigation_episode(
    reader: EpisodeReader,
    *,
    assignment: StrategicNavigationEpisodeAssignment,
    allow_test: bool = False,
) -> CollectedStrategicNavigationDataset:
    """Load one episode only when its header matches a committed root assignment."""

    if not isinstance(
        assignment,
        (
            StrategicNavigationAssignment,
            StrategicNavigationRehearsalAssignment,
            StrategicNavigationScenarioRehearsalAssignment,
        ),
    ):
        raise TypeError("assignment must be a strategic episode assignment")
    if assignment.source_commit is None:
        raise StrategicNavigationDatasetError(
            "assigned strategic episode requires committed source identity"
        )
    if assignment.partition == "test" and not allow_test:
        raise StrategicNavigationDatasetError(
            "the strategic navigation test partition must remain unopened"
        )
    header = _mapping(reader.read_header(), subject="episode header")
    metadata = _mapping(header.get("metadata"), subject="episode metadata")
    expected = assignment.episode_metadata()
    for key in ("policy", "source", "source_bundle_sha256", "split"):
        if metadata.get(key) != expected[key]:
            raise StrategicNavigationDatasetError(
                f"assigned strategic episode {key} differs"
            )
    collection = _mapping(
        metadata.get("collection"),
        subject="strategic episode collection metadata",
    )
    expected_collection = _mapping(
        expected["collection"],
        subject="expected strategic collection metadata",
    )
    if collection != expected_collection:
        raise StrategicNavigationDatasetError(
            "assigned strategic episode collection identity differs"
        )
    dataset = load_strategic_navigation_episode(reader)
    if (
        dataset.episode_id,
        dataset.root_lineage_id,
        dataset.partition,
        dataset.actor,
        dataset.policy_id,
    ) != (
        assignment.episode_id,
        assignment.root_lineage_id,
        assignment.partition,
        STRATEGIC_NAVIGATION_ACTOR,
        STRATEGIC_NAVIGATION_POLICY_ID,
    ):
        raise StrategicNavigationDatasetError(
            "assigned strategic episode provenance differs"
        )
    if isinstance(assignment, StrategicNavigationScenarioRehearsalAssignment) and (
        len(dataset.examples) != 1 or dataset.examples[0].decision_index != 0
    ):
        raise StrategicNavigationDatasetError(
            "strategic scenario rehearsal must contain exactly one decision"
        )
    return dataset


def _policy_input(value: object, *, subject: str) -> dict[str, object]:
    raw = _mapping(value, subject=subject)
    if set(raw) != {
        "schema",
        "semantic_need_tags",
        "origin_semantic_tags",
        "candidates",
    } or raw.get("schema") != "strategic-navigation-policy-input-v1":
        raise StrategicNavigationDatasetError("strategic policy input schema is invalid")
    need_tags = _tags(raw.get("semantic_need_tags"), subject="semantic need tags")
    origin_tags = _tags(
        raw.get("origin_semantic_tags"), subject="origin semantic tags"
    )
    candidate_rows = raw.get("candidates")
    if not isinstance(candidate_rows, list) or len(candidate_rows) < 2:
        raise StrategicNavigationDatasetError(
            "strategic policy input needs at least two candidates"
        )
    candidates: list[dict[str, object]] = []
    for index, value_candidate in enumerate(candidate_rows):
        candidate = _mapping(value_candidate, subject="strategic candidate")
        if set(candidate) != {
            "binding_index",
            "semantic_tags",
            "availability",
            "route_cost",
            "route_steps",
            "map_transitions",
            "field_actions",
            "mode_changes",
            "unavailability_reason",
        } or candidate.get("binding_index") != index:
            raise StrategicNavigationDatasetError("strategic candidate schema is invalid")
        tags = _tags(candidate.get("semantic_tags"), subject="candidate semantic tags")
        try:
            availability = DestinationAvailability(
                _string(candidate.get("availability"), subject="candidate availability")
            )
        except (TypeError, ValueError) as error:
            raise StrategicNavigationDatasetError(
                "strategic candidate availability is invalid"
            ) from error
        if availability is DestinationAvailability.AVAILABLE:
            projected = NavigationDestinationCandidate(
                destination_ref=f"binding:{index}",
                semantic_tags=tags,
                availability=availability,
                route_cost=_integer(candidate.get("route_cost"), subject="route cost"),
                route_steps=_integer(candidate.get("route_steps"), subject="route steps"),
                map_transitions=_integer(
                    candidate.get("map_transitions"), subject="map transitions"
                ),
                field_actions=_integer(
                    candidate.get("field_actions"), subject="field actions"
                ),
                mode_changes=_integer(
                    candidate.get("mode_changes"), subject="mode changes"
                ),
            )
        else:
            if any(
                candidate.get(name) is not None
                for name in (
                    "route_cost",
                    "route_steps",
                    "map_transitions",
                    "field_actions",
                    "mode_changes",
                )
            ):
                raise StrategicNavigationDatasetError(
                    "unavailable strategic candidate advertises route metrics"
                )
            try:
                unavailable_reason = DestinationUnavailableReason(
                    _string(
                        candidate.get("unavailability_reason"),
                        subject="candidate unavailability reason",
                    )
                )
            except (TypeError, ValueError) as error:
                raise StrategicNavigationDatasetError(
                    "strategic unavailability reason is invalid"
                ) from error
            projected = NavigationDestinationCandidate(
                destination_ref=f"binding:{index}",
                semantic_tags=tags,
                availability=availability,
                unavailability_reason=unavailable_reason,
            )
        canonical = projected.policy_features(binding_index=index)
        if dict(candidate) != canonical:
            raise StrategicNavigationDatasetError(
                "strategic candidate is not in canonical identity-free form"
            )
        candidates.append(canonical)
    return {
        "schema": "strategic-navigation-policy-input-v1",
        "semantic_need_tags": [item.value for item in need_tags],
        "origin_semantic_tags": [item.value for item in origin_tags],
        "candidates": candidates,
    }


def _thaw_policy_input(value: object) -> dict[str, object]:
    """Copy either fresh JSON or an already-frozen example into parser form."""

    raw = _mapping(value, subject="strategic example policy input")
    candidate_values = raw.get("candidates")
    if not isinstance(candidate_values, (list, tuple)):
        raise StrategicNavigationDatasetError("strategic candidate collection is invalid")
    candidates: list[dict[str, object]] = []
    for value_candidate in candidate_values:
        candidate = dict(_mapping(value_candidate, subject="strategic candidate"))
        semantic_tags = candidate.get("semantic_tags")
        if isinstance(semantic_tags, tuple):
            candidate["semantic_tags"] = list(semantic_tags)
        candidates.append(candidate)
    need_tags = raw.get("semantic_need_tags")
    origin_tags = raw.get("origin_semantic_tags")
    return {
        "schema": raw.get("schema"),
        "semantic_need_tags": list(need_tags) if isinstance(need_tags, tuple) else need_tags,
        "origin_semantic_tags": (
            list(origin_tags) if isinstance(origin_tags, tuple) else origin_tags
        ),
        "candidates": candidates,
    }


def _freeze_policy_input(value: dict[str, object]) -> Mapping[str, object]:
    """Make model input recursively immutable after canonical validation."""

    candidates = value["candidates"]
    need_tags = value["semantic_need_tags"]
    origin_tags = value["origin_semantic_tags"]
    assert isinstance(candidates, list)
    assert isinstance(need_tags, list)
    assert isinstance(origin_tags, list)
    frozen_candidates = []
    for candidate_value in candidates:
        assert isinstance(candidate_value, dict)
        candidate = dict(candidate_value)
        tags = candidate["semantic_tags"]
        assert isinstance(tags, list)
        candidate["semantic_tags"] = tuple(tags)
        frozen_candidates.append(MappingProxyType(candidate))
    return MappingProxyType(
        {
            "schema": value["schema"],
            "semantic_need_tags": tuple(need_tags),
            "origin_semantic_tags": tuple(origin_tags),
            "candidates": tuple(frozen_candidates),
        }
    )


def _candidate_rows(
    example: StrategicNavigationExample,
) -> tuple[Mapping[str, object], ...]:
    rows = example.policy_input.get("candidates")
    if not isinstance(rows, tuple) or any(not isinstance(row, Mapping) for row in rows):
        raise StrategicNavigationDatasetError(
            "validated strategic example lost its immutable candidate rows"
        )
    return rows


def _need_tags(example: StrategicNavigationExample) -> tuple[str, ...]:
    tags = example.policy_input.get("semantic_need_tags")
    if not isinstance(tags, tuple) or any(not isinstance(tag, str) for tag in tags):
        raise StrategicNavigationDatasetError(
            "validated strategic example lost its semantic need tags"
        )
    return tags


def strategic_ordered_policy_input_sha256(value: Mapping[str, object]) -> str:
    """Hash one validated policy input while retaining candidate order."""

    return canonical_sha256(
        _policy_input(
            _thaw_policy_input(value),
            subject="strategic ordered policy input",
        )
    )


def strategic_policy_context_sha256(value: Mapping[str, object]) -> str:
    """Hash the portable strategic question without assignment order.

    ``binding_index`` exists only to connect a selected public row back to its
    private route plan.  Candidate order is assignment-permuted to prevent a
    slot shortcut.  Neither property creates a new strategic context, so both
    are removed before canonical hashing.
    """

    canonical = _policy_input(
        _thaw_policy_input(value),
        subject="strategic policy context",
    )
    raw_candidates = canonical["candidates"]
    assert isinstance(raw_candidates, list)
    candidates: list[dict[str, object]] = []
    for raw_candidate in raw_candidates:
        assert isinstance(raw_candidate, dict)
        candidate = dict(raw_candidate)
        candidate.pop("binding_index")
        candidates.append(candidate)
    candidates.sort(key=canonical_sha256)
    return canonical_sha256(
        {
            "candidates": candidates,
            "origin_semantic_tags": canonical["origin_semantic_tags"],
            "schema": "strategic-navigation-policy-context-v1",
            "semantic_need_tags": canonical["semantic_need_tags"],
        }
    )


def strategic_selected_candidate_sha256(
    example: StrategicNavigationExample,
) -> str:
    """Hash the selected portable candidate without its permuted slot."""

    canonical = _policy_input(
        _thaw_policy_input(example.policy_input),
        subject="strategic selected candidate",
    )
    raw_candidates = canonical["candidates"]
    assert isinstance(raw_candidates, list)
    candidate = dict(raw_candidates[example.selected_candidate_index])
    candidate.pop("binding_index")
    return canonical_sha256(
        {
            "candidate": candidate,
            "schema": "strategic-navigation-selected-candidate-v1",
        }
    )


def _validated_outcome(
    payload: Mapping[str, object],
    *,
    decision_id: str,
    selected_index: int,
) -> StrategicNavigationOutcome:
    if set(payload) != {
        "decision_id",
        "selected_candidate_index",
        "status",
        "terminal_reached",
        "movement_requests",
        "acknowledged_steps",
        "wait_actions",
        "replans",
        "interruptions",
        "resource_renewals",
        "failure_reason",
    }:
        raise StrategicNavigationDatasetError("strategic outcome schema is invalid")
    if (
        payload.get("decision_id") != decision_id
        or payload.get("selected_candidate_index") != selected_index
    ):
        raise StrategicNavigationDatasetError("strategic outcome binding differs")
    try:
        status = NavigationOutcomeStatus(
            _string(payload.get("status"), subject="outcome status")
        )
    except (TypeError, ValueError) as error:
        raise StrategicNavigationDatasetError("strategic outcome status is invalid") from error
    terminal_reached = payload.get("terminal_reached")
    if type(terminal_reached) is not bool:  # noqa: E721
        raise StrategicNavigationDatasetError("strategic terminal flag is invalid")
    raw_replans = payload.get("replans")
    raw_interruptions = payload.get("interruptions")
    raw_resources = payload.get("resource_renewals")
    if (
        not isinstance(raw_replans, list)
        or not isinstance(raw_interruptions, list)
        or not isinstance(raw_resources, list)
    ):
        raise StrategicNavigationDatasetError("strategic outcome collections are invalid")
    replans = tuple(_replan(value) for value in raw_replans)
    interruptions = tuple(_interruption(value) for value in raw_interruptions)
    try:
        resources = tuple(StrategicResourceKind(value) for value in raw_resources)
    except (TypeError, ValueError) as error:
        raise StrategicNavigationDatasetError(
            "strategic resource renewal is invalid"
        ) from error
    raw_failure = payload.get("failure_reason")
    try:
        failure = (
            None
            if raw_failure is None
            else NavigationFailureReason(
                _string(raw_failure, subject="failure reason")
            )
        )
    except (TypeError, ValueError) as error:
        raise StrategicNavigationDatasetError("strategic failure reason is invalid") from error
    try:
        outcome = StrategicNavigationOutcome(
            decision_id=decision_id,
            selected_destination_ref=f"binding:{selected_index}",
            status=status,
            terminal_reached=terminal_reached,
            movement_requests=_integer(
                payload.get("movement_requests"), subject="movement requests"
            ),
            acknowledged_steps=_integer(
                payload.get("acknowledged_steps"), subject="acknowledged steps"
            ),
            wait_actions=_integer(payload.get("wait_actions"), subject="wait actions"),
            replans=replans,
            interruptions=interruptions,
            resource_renewals=resources,
            failure_reason=failure,
        )
    except StrategicNavigationError as error:
        raise StrategicNavigationDatasetError(str(error)) from error
    return outcome


def _replan(value: object) -> StrategicReplanOutcome:
    row = _mapping(value, subject="strategic replan")
    if set(row) != {"ordinal", "reason", "replacement_route_steps"}:
        raise StrategicNavigationDatasetError("strategic replan schema is invalid")
    try:
        reason = StrategicReplanReason(
            _string(row.get("reason"), subject="replan reason")
        )
    except (TypeError, ValueError) as error:
        raise StrategicNavigationDatasetError("strategic replan reason is invalid") from error
    return StrategicReplanOutcome(
        _integer(row.get("ordinal"), subject="replan ordinal"),
        reason,
        _integer(row.get("replacement_route_steps"), subject="replacement route steps"),
    )


def _interruption(value: object) -> StrategicInterruptionOutcome:
    row = _mapping(value, subject="strategic interruption")
    if set(row) != {"kind", "outcome"}:
        raise StrategicNavigationDatasetError("strategic interruption schema is invalid")
    try:
        kind = StrategicInterruptionKind(
            _string(row.get("kind"), subject="interruption kind")
        )
        outcome = StrategicInterruptionResolution(
            _string(row.get("outcome"), subject="interruption outcome")
        )
    except (TypeError, ValueError) as error:
        raise StrategicNavigationDatasetError(
            "strategic interruption vocabulary is invalid"
        ) from error
    return StrategicInterruptionOutcome(kind, outcome)


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise StrategicNavigationDatasetError(f"{subject} must be a string-keyed mapping")
    return value


def _string(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise StrategicNavigationDatasetError(f"{subject} must be a non-empty string")
    return value


def _integer(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise StrategicNavigationDatasetError(
            f"{subject} must be a non-negative integer"
        )
    return value


def _tags(value: object, *, subject: str) -> tuple[StrategicNavigationTag, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(set(value))
    ):
        raise StrategicNavigationDatasetError(
            f"{subject} must be non-empty, unique and sorted"
        )
    try:
        return tuple(StrategicNavigationTag(item) for item in value)
    except ValueError as error:
        raise StrategicNavigationDatasetError(
            f"{subject} contains a title-specific or unsupported tag"
        ) from error


def _digest(value: object, *, subject: str) -> str:
    result = _string(value, subject=subject)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise StrategicNavigationDatasetError(
            f"{subject} must be a lowercase SHA-256 digest"
        )
    return result


@dataclass(frozen=True, slots=True)
class StrategicNavigationPartitionAudit:
    """Leakage and coverage audit before a numeric model may be developed."""

    lineage_count: int
    partition_counts: tuple[tuple[str, int], ...]
    decision_overlap_count: int
    teacher_choice_example_count: int
    unique_teacher_choice_context_count: int
    replicated_teacher_choice_example_count: int
    partition_unique_teacher_choice_context_counts: tuple[tuple[str, int], ...]
    train_validation_context_overlap_count: int
    context_target_conflict_count: int
    validation_need_tags_missing_from_training: tuple[str, ...]
    ready_for_model_development: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "strategic-navigation-partition-audit-v2",
            "lineage_count": self.lineage_count,
            "partition_counts": dict(self.partition_counts),
            "decision_overlap_count": self.decision_overlap_count,
            "teacher_choice_example_count": self.teacher_choice_example_count,
            "unique_teacher_choice_context_count": (
                self.unique_teacher_choice_context_count
            ),
            "replicated_teacher_choice_example_count": (
                self.replicated_teacher_choice_example_count
            ),
            "partition_unique_teacher_choice_context_counts": dict(
                self.partition_unique_teacher_choice_context_counts
            ),
            "train_validation_context_overlap_count": (
                self.train_validation_context_overlap_count
            ),
            "context_target_conflict_count": self.context_target_conflict_count,
            "validation_need_tags_missing_from_training": list(
                self.validation_need_tags_missing_from_training
            ),
            "ready_for_model_development": self.ready_for_model_development,
            "reasons": list(self.reasons),
        }


def audit_strategic_navigation_partitions(
    datasets: Iterable[
        StrategicNavigationDataset | CollectedStrategicNavigationDataset
    ],
) -> StrategicNavigationPartitionAudit:
    """Audit in-memory or authenticated whole-lineage splits."""

    rows = tuple(datasets)
    reasons: list[str] = []
    roots = [dataset.root_lineage_id for dataset in rows]
    if len(set(roots)) != len(roots):
        reasons.append("duplicate_root_lineage")
    if any(dataset.partition == "unassigned" for dataset in rows):
        reasons.append("unassigned_lineage")
    partitions = Counter(dataset.partition for dataset in rows)
    if not partitions.get("train") or not partitions.get("validation"):
        reasons.append("missing_train_or_validation_partition")
    if len({dataset.actor for dataset in rows}) > 1:
        reasons.append("mixed_actor")
    if len({dataset.policy_id for dataset in rows}) > 1:
        reasons.append("mixed_policy")

    decision_ids = [
        example.decision_id for dataset in rows for example in dataset.examples
    ]
    overlap = len(decision_ids) - len(set(decision_ids))
    if overlap:
        reasons.append("decision_overlap_across_lineages")
    teacher_examples = tuple(
        example
        for dataset in rows
        for example in dataset.examples
        if example.teacher_choice_target is not None
    )
    partition_contexts: defaultdict[str, set[str]] = defaultdict(set)
    context_targets: defaultdict[str, set[str]] = defaultdict(set)
    for example in teacher_examples:
        context = example.policy_context_sha256
        partition_contexts[example.partition].add(context)
        context_targets[context].add(example.selected_candidate_sha256)
    unique_contexts = set(context_targets)
    train_validation_overlap = len(
        partition_contexts["train"] & partition_contexts["validation"]
    )
    if train_validation_overlap:
        reasons.append("train_validation_policy_context_overlap")
    target_conflicts = sum(len(targets) > 1 for targets in context_targets.values())
    if target_conflicts:
        reasons.append("policy_context_has_conflicting_teacher_target")
    training_tags = {
        tag
        for dataset in rows
        if dataset.partition == "train"
        for tag in dataset.semantic_need_tags
    }
    validation_tags = {
        tag
        for dataset in rows
        if dataset.partition == "validation"
        for tag in dataset.semantic_need_tags
    }
    missing = tuple(sorted(validation_tags - training_tags))
    if missing:
        reasons.append("validation_need_tag_absent_from_training")
    for partition in ("train", "validation"):
        partition_examples = [
            example
            for dataset in rows
            if dataset.partition == partition
            for example in dataset.examples
        ]
        if not any(item.teacher_choice_target is not None for item in partition_examples):
            reasons.append(f"{partition}_has_no_successful_teacher_choice")
    if len(partition_contexts["train"]) < STRATEGIC_MINIMUM_TRAIN_CONTEXTS:
        reasons.append("insufficient_unique_train_contexts")
    if (
        len(partition_contexts["validation"])
        < STRATEGIC_MINIMUM_VALIDATION_CONTEXTS
    ):
        reasons.append("insufficient_unique_validation_contexts")
    return StrategicNavigationPartitionAudit(
        lineage_count=len(rows),
        partition_counts=tuple(sorted(partitions.items())),
        decision_overlap_count=overlap,
        teacher_choice_example_count=len(teacher_examples),
        unique_teacher_choice_context_count=len(unique_contexts),
        replicated_teacher_choice_example_count=(
            len(teacher_examples) - len(unique_contexts)
        ),
        partition_unique_teacher_choice_context_counts=tuple(
            sorted(
                (partition, len(contexts))
                for partition, contexts in partition_contexts.items()
            )
        ),
        train_validation_context_overlap_count=train_validation_overlap,
        context_target_conflict_count=target_conflicts,
        validation_need_tags_missing_from_training=missing,
        ready_for_model_development=not reasons,
        reasons=tuple(reasons),
    )
