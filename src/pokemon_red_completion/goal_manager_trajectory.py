"""Record and reload high-level goal choices without private title bindings.

The decision is durably written before its selected specialist executes.  One
later outcome event must consume it.  Successful deterministic-teacher choices
can become imitation targets, failures remain outcome evidence, and external
interruptions remain censored rather than being silently dropped or relabelled.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Protocol, cast

from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalManagerError,
    GoalManagerExample,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSelectionMode,
    GoalSituation,
    bind_goal_selection,
)
from pokemon_red_completion.trajectory import (
    DecisionContext,
    DecisionRecord,
    JSONValue,
    SemanticSnapshot,
    SnapshotProvider,
    SparseEvent,
    TrajectorySink,
)

GOAL_MANAGER_SKILL_ID = "pokemon.core.goal-manager.v1"
GOAL_MANAGER_DECISION_TYPE = "goal_manager_selection"
GOAL_MANAGER_OUTCOME_KIND = "goal_manager_outcome"


class GoalManagerTrajectoryError(RuntimeError):
    """Raised when goal-manager trajectory provenance or joins are invalid."""


class GoalDecisionRecorder(Protocol):
    episode_id: str
    sink: TrajectorySink

    @property
    def next_step_index(self) -> int: ...

    def record_standalone_decision(self, decision: DecisionRecord) -> bool: ...

    def note_instrumentation_failure(self) -> None: ...


class GoalEpisodeReader(Protocol):
    @property
    def manifest_sha256(self) -> str: ...

    def read_header(self) -> Mapping[str, object]: ...

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class PendingGoalManagerDecision:
    """A written choice awaiting one semantic outcome."""

    decision_id: str
    decision_index: int
    question: GoalManagerQuestion
    selected_candidate_index: int


def ordered_goal_manager_question(
    *,
    assignment_id: str,
    decision_index: int,
    situation: GoalSituation,
    opportunities: tuple[GoalOpportunity, ...],
) -> GoalManagerQuestion:
    """Order candidates from a source assignment nonce, never from a label."""

    if not isinstance(assignment_id, str) or not assignment_id:
        raise GoalManagerTrajectoryError("goal-manager assignment identity is absent")
    if type(decision_index) is not int or decision_index < 0:  # noqa: E721
        raise GoalManagerTrajectoryError("goal-manager decision index is invalid")

    def order_key(item: GoalOpportunity) -> bytes:
        return hashlib.sha256(
            f"{assignment_id}:{decision_index}:{item.binding_ref}".encode()
        ).digest()

    return GoalManagerQuestion(
        situation=situation,
        opportunities=tuple(sorted(opportunities, key=order_key)),
    )


def goal_manager_decision_record(
    pending: PendingGoalManagerDecision,
    snapshot: SemanticSnapshot,
    *,
    step_index: int,
    episode_id: str,
    root_lineage_id: str,
    partition: str,
    environment_id: str,
    actor: str,
    policy_id: str,
    collection_id: str,
    assignment_id: str,
    source_commit: str,
    behavior_policy: Mapping[str, object] | None = None,
    selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY,
) -> DecisionRecord:
    """Encode an identity-free choice before its selected goal executes."""

    if not isinstance(pending, PendingGoalManagerDecision):
        raise TypeError("pending must be a PendingGoalManagerDecision")
    if not isinstance(snapshot, SemanticSnapshot):
        raise TypeError("snapshot must be a SemanticSnapshot")
    if snapshot.game_id != environment_id:
        raise GoalManagerTrajectoryError(
            "goal-manager snapshot environment differs from its assignment"
        )
    bind_goal_selection(pending.question, pending.selected_candidate_index)
    if not isinstance(selection_mode, GoalSelectionMode):
        raise GoalManagerTrajectoryError("goal-manager selection mode is invalid")
    metadata: dict[str, object] = {
        "assignment_id": assignment_id,
        "collection_id": collection_id,
        "environment_id": environment_id,
        "goal_decision_index": pending.decision_index,
        "partition": partition,
        "policy_input": pending.question.policy_input,
        "root_lineage_id": root_lineage_id,
        "skill_id": GOAL_MANAGER_SKILL_ID,
        "selection_mode": selection_mode.value,
        "source_commit": source_commit,
    }
    if behavior_policy is not None:
        metadata["behavior_policy"] = behavior_policy
    return DecisionRecord(
        decision_id=pending.decision_id,
        episode_id=episode_id,
        step_index=step_index,
        snapshot=snapshot,
        context=DecisionContext(
            policy_id=policy_id,
            actor=actor,
            metadata=_json_mapping(metadata),
        ),
        decision_type=GOAL_MANAGER_DECISION_TYPE,
        action={
            "kind": "select_goal",
            "selected_candidate_index": pending.selected_candidate_index,
        },
    )


def goal_manager_outcome_event(
    pending: PendingGoalManagerDecision,
    *,
    episode_id: str,
    step_index: int,
    status: GoalDecisionOutcome,
    failure_reason: GoalFailureReason | None,
) -> SparseEvent:
    """Encode exactly one consumed outcome without binding or exception text."""

    _validate_outcome(status, failure_reason)
    return SparseEvent(
        event_id=f"{pending.decision_id}:outcome",
        episode_id=episode_id,
        step_index=step_index,
        kind=GOAL_MANAGER_OUTCOME_KIND,
        payload=_json_mapping(
            {
                "decision_id": pending.decision_id,
                "failure_reason": (None if failure_reason is None else failure_reason.value),
                "selected_candidate_index": pending.selected_candidate_index,
                "status": status.value,
            }
        ),
    )


@dataclass(slots=True)
class GoalManagerTrajectoryObserver:
    """Record one choice before execution and join one outcome afterward."""

    episode_id: str
    root_lineage_id: str
    partition: str
    environment_id: str
    actor: str
    policy_id: str
    collection_id: str
    assignment_id: str
    source_commit: str
    snapshot_provider: SnapshotProvider
    recorder: GoalDecisionRecorder
    sink: TrajectorySink
    ordering_assignment_id: str | None = None
    allow_test: bool = False
    _next_decision_index: int = field(default=0, init=False)
    _pending: PendingGoalManagerDecision | None = field(default=None, init=False)
    _pending_was_recorded: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for name in (
            "episode_id",
            "root_lineage_id",
            "partition",
            "environment_id",
            "actor",
            "policy_id",
            "collection_id",
            "assignment_id",
            "source_commit",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise GoalManagerTrajectoryError(f"{name} must be non-empty")
        if self.ordering_assignment_id is None:
            self.ordering_assignment_id = self.assignment_id
        elif not isinstance(self.ordering_assignment_id, str) or not self.ordering_assignment_id:
            raise GoalManagerTrajectoryError(
                "ordering_assignment_id must be non-empty"
            )
        if self.partition == "test" and not self.allow_test:
            raise GoalManagerTrajectoryError("the goal-manager test partition must remain unopened")
        if self.partition not in {
            "train",
            "development",
            "validation",
            "test",
            "unassigned",
        }:
            raise GoalManagerTrajectoryError("goal-manager partition is unsupported")
        if self.recorder.episode_id != self.episode_id:
            raise GoalManagerTrajectoryError(
                "goal-manager recorder episode differs from its assignment"
            )
        if self.recorder.sink is not self.sink:
            raise GoalManagerTrajectoryError("goal-manager decision and outcome sinks differ")

    @property
    def next_decision_index(self) -> int:
        return self._next_decision_index

    @property
    def pending_decision(self) -> PendingGoalManagerDecision | None:
        return self._pending

    @property
    def pending_was_recorded(self) -> bool:
        """Whether the durable decision write for the pending choice succeeded."""

        return self._pending is not None and self._pending_was_recorded

    @property
    def question_ordering_assignment_id(self) -> str:
        """Return the frozen ordering nonce after constructor validation."""

        if self.ordering_assignment_id is None:  # Defensive; __post_init__ fills it.
            raise GoalManagerTrajectoryError("ordering assignment is absent")
        return self.ordering_assignment_id

    def ordered_question(
        self,
        situation: GoalSituation,
        opportunities: tuple[GoalOpportunity, ...],
    ) -> GoalManagerQuestion:
        """Expose the exact candidate order before either teacher or model acts."""

        if self._pending is not None:
            raise GoalManagerTrajectoryError("a goal-manager decision still awaits its outcome")
        return ordered_goal_manager_question(
            assignment_id=self.question_ordering_assignment_id,
            decision_index=self._next_decision_index,
            situation=situation,
            opportunities=opportunities,
        )

    def record_selection(
        self,
        question: GoalManagerQuestion,
        selected_candidate_index: int,
        *,
        behavior_policy: Mapping[str, object] | None = None,
        selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY,
    ) -> PendingGoalManagerDecision:
        """Write the choice before returning execution authority to its caller."""

        if self._pending is not None:
            raise GoalManagerTrajectoryError("a goal-manager decision still awaits its outcome")
        expected = ordered_goal_manager_question(
            assignment_id=self.question_ordering_assignment_id,
            decision_index=self._next_decision_index,
            situation=question.situation,
            opportunities=question.opportunities,
        )
        if expected.opportunities != question.opportunities:
            raise GoalManagerTrajectoryError(
                "goal-manager candidates do not use the assignment order"
            )
        bind_goal_selection(question, selected_candidate_index)
        pending = PendingGoalManagerDecision(
            decision_id=(f"{self.episode_id}:goal-manager:{self._next_decision_index}"),
            decision_index=self._next_decision_index,
            question=question,
            selected_candidate_index=selected_candidate_index,
        )
        snapshot = self.snapshot_provider.snapshot()
        recorded = self.recorder.record_standalone_decision(
            goal_manager_decision_record(
                pending,
                snapshot,
                step_index=self.recorder.next_step_index,
                episode_id=self.episode_id,
                root_lineage_id=self.root_lineage_id,
                partition=self.partition,
                environment_id=self.environment_id,
                actor=self.actor,
                policy_id=self.policy_id,
                collection_id=self.collection_id,
                assignment_id=self.assignment_id,
                source_commit=self.source_commit,
                behavior_policy=behavior_policy,
                selection_mode=selection_mode,
            )
        )
        self._next_decision_index += 1
        self._pending = pending
        self._pending_was_recorded = recorded
        return pending

    def record_outcome(
        self,
        pending: PendingGoalManagerDecision,
        *,
        status: GoalDecisionOutcome,
        failure_reason: GoalFailureReason | None = None,
    ) -> bool:
        """Consume the pending choice with one success, failure, or interruption."""

        if self._pending is None:
            raise GoalManagerTrajectoryError("goal-manager outcome has no pending decision")
        if pending != self._pending:
            raise GoalManagerTrajectoryError(
                "goal-manager outcome does not match the pending decision"
            )
        _validate_outcome(status, failure_reason)
        decision_was_recorded = self._pending_was_recorded
        if not decision_was_recorded:
            self._pending = None
            self._pending_was_recorded = False
            return False
        try:
            self.sink.record_event(
                goal_manager_outcome_event(
                    pending,
                    episode_id=self.episode_id,
                    step_index=self.recorder.next_step_index,
                    status=status,
                    failure_reason=failure_reason,
                )
            )
        except Exception:
            self.recorder.note_instrumentation_failure()
            return False
        self._pending = None
        self._pending_was_recorded = False
        return True

    def abandon_unrecorded_selection(
        self,
        pending: PendingGoalManagerDecision,
    ) -> None:
        """Settle a choice whose decision write failed before any skill could act."""

        if self._pending is None or pending != self._pending:
            raise GoalManagerTrajectoryError(
                "unrecorded goal-manager selection does not match the pending decision"
            )
        if self._pending_was_recorded:
            raise GoalManagerTrajectoryError(
                "a durably recorded goal-manager selection cannot be abandoned"
            )
        self._pending = None
        self._pending_was_recorded = False

    def require_settled(self) -> None:
        if self._pending is not None:
            raise GoalManagerTrajectoryError("goal-manager decision has no consumed outcome")


@dataclass(frozen=True, slots=True)
class CollectedGoalManagerDataset:
    """Strictly joined choices from one authenticated episode container."""

    episode_id: str
    manifest_sha256: str
    root_lineage_id: str
    partition: str
    environment_id: str
    actor: str
    policy_id: str
    collection_id: str
    assignment_id: str
    source_commit: str
    context_catalog_sha256: str
    context_id: str
    binding_manifest_sha256: str
    capture_state_sha256: str
    capture_envelope_sha256: str
    examples: tuple[GoalManagerExample, ...]

    def __post_init__(self) -> None:
        if not self.examples:
            raise GoalManagerTrajectoryError("a collected goal-manager dataset needs examples")

    def public_summary(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.collected-goal-manager-summary.v1",
            "episode_id": self.episode_id,
            "manifest_sha256": self.manifest_sha256,
            "root_lineage_id": self.root_lineage_id,
            "partition": self.partition,
            "environment_id": self.environment_id,
            "provenance": {
                "actor": self.actor,
                "policy_id": self.policy_id,
                "collection_id": self.collection_id,
                "assignment_id": self.assignment_id,
                "source_commit": self.source_commit,
                "context_catalog_sha256": self.context_catalog_sha256,
                "context_id": self.context_id,
                "binding_manifest_sha256": self.binding_manifest_sha256,
            },
            "examples": len(self.examples),
            "outcomes": dict(
                sorted(Counter(item.outcome_status.value for item in self.examples).items())
            ),
            "teacher_choice_examples": sum(
                item.teacher_choice_target is not None for item in self.examples
            ),
            "private_binding_fields": 0,
            "movement_action_labels": 0,
        }


def load_goal_manager_episode(reader: GoalEpisodeReader) -> CollectedGoalManagerDataset:
    """Strictly join every recorded manager choice to one consumed outcome."""

    header = _mapping(reader.read_header(), subject="episode header")
    if (
        header.get("record_type") != "episode"
        or header.get("trajectory_schema") != "pokemon.trajectory.v1"
    ):
        raise GoalManagerTrajectoryError("episode header schema is incompatible")
    episode_id = _string(header.get("episode_id"), subject="episode identity")
    environment_id = _string(header.get("game_id"), subject="environment identity")
    metadata = _mapping(header.get("metadata"), subject="episode metadata")
    policy = _mapping(metadata.get("policy"), subject="episode policy")
    actor = _string(policy.get("actor"), subject="episode actor")
    policy_id = _string(policy.get("policy_id"), subject="episode policy identity")
    split = _mapping(metadata.get("split"), subject="episode split")
    root_lineage_id = _string(split.get("root_lineage_id"), subject="root lineage identity")
    partition = _string(split.get("partition"), subject="episode partition")
    goal_metadata = _mapping(
        metadata.get("goal_manager"), subject="goal-manager collection metadata"
    )
    collection_id = _string(
        goal_metadata.get("collection_id"), subject="goal-manager collection identity"
    )
    assignment_id = _string(
        goal_metadata.get("assignment_id"), subject="goal-manager assignment identity"
    )
    source_commit = _string(
        goal_metadata.get("source_commit"), subject="goal-manager source commit"
    )
    context_catalog_sha256 = _digest(
        goal_metadata.get("context_catalog_sha256"), subject="context catalog digest"
    )
    context_id = _digest(goal_metadata.get("context_id"), subject="context identity")
    binding_manifest_sha256 = _digest(
        goal_metadata.get("binding_manifest_sha256"),
        subject="binding manifest digest",
    )
    capture_state_sha256 = _digest(
        goal_metadata.get("state_sha256"), subject="captured state digest"
    )
    capture_envelope_sha256 = _digest(
        goal_metadata.get("envelope_sha256"), subject="capture envelope digest"
    )

    decisions = [
        _mapping(row, subject="goal-manager decision")
        for row in reader.iter_stream("decisions")
        if row.get("decision_type") == GOAL_MANAGER_DECISION_TYPE
    ]
    events_by_decision: dict[str, Mapping[str, object]] = {}
    for row in reader.iter_stream("events"):
        if row.get("kind") != GOAL_MANAGER_OUTCOME_KIND:
            continue
        event = _mapping(row, subject="goal-manager outcome")
        payload = _mapping(event.get("payload"), subject="goal-manager outcome payload")
        decision_id = _string(payload.get("decision_id"), subject="outcome decision identity")
        if decision_id in events_by_decision:
            raise GoalManagerTrajectoryError("goal-manager decision has more than one outcome")
        events_by_decision[decision_id] = payload
    if not decisions:
        raise GoalManagerTrajectoryError("episode has no goal-manager decisions")

    examples: list[GoalManagerExample] = []
    seen: set[str] = set()
    previous_index = -1
    for row in decisions:
        decision_id = _string(row.get("decision_id"), subject="decision identity")
        if decision_id in seen:
            raise GoalManagerTrajectoryError("goal-manager decision is duplicated")
        seen.add(decision_id)
        if row.get("episode_id") != episode_id:
            raise GoalManagerTrajectoryError("goal-manager decision episode differs")
        context = _mapping(row.get("context"), subject="goal-manager decision context")
        if context.get("actor") != actor or context.get("policy_id") != policy_id:
            raise GoalManagerTrajectoryError("goal-manager decision policy differs")
        decision_metadata = _mapping(
            context.get("metadata"), subject="goal-manager decision metadata"
        )
        expected_metadata = {
            "assignment_id": assignment_id,
            "collection_id": collection_id,
            "environment_id": environment_id,
            "partition": partition,
            "root_lineage_id": root_lineage_id,
            "skill_id": GOAL_MANAGER_SKILL_ID,
            "source_commit": source_commit,
        }
        if any(decision_metadata.get(key) != value for key, value in expected_metadata.items()):
            raise GoalManagerTrajectoryError(
                "goal-manager decision provenance differs from its episode"
            )
        decision_index = _integer(
            decision_metadata.get("goal_decision_index"),
            subject="goal-manager decision index",
        )
        if decision_index != len(examples) or decision_index <= previous_index:
            raise GoalManagerTrajectoryError(
                "goal-manager decision indexes must be contiguous from zero"
            )
        previous_index = decision_index
        policy_input = _mapping(
            decision_metadata.get("policy_input"), subject="goal-manager policy input"
        )
        try:
            question = GoalManagerQuestion.from_policy_input(policy_input)
        except GoalManagerError as error:
            raise GoalManagerTrajectoryError(str(error)) from error
        try:
            selection_mode = GoalSelectionMode(
                _string(
                    decision_metadata.get(
                        "selection_mode",
                        GoalSelectionMode.AUTHORITY.value,
                    ),
                    subject="goal-manager selection mode",
                )
            )
        except (TypeError, ValueError) as error:
            raise GoalManagerTrajectoryError(
                "goal-manager selection mode is invalid"
            ) from error
        (
            behavior_policy_id,
            behavior_probability,
            behavior_candidate_probabilities,
            behavior_base_probability,
            behavior_exploration_mix,
            behavior_temperature,
        ) = _parse_behavior_policy(
            decision_metadata.get("behavior_policy"),
            question=question,
        )
        action = _mapping(row.get("action"), subject="goal-manager action")
        if (
            set(action) != {"kind", "selected_candidate_index"}
            or action.get("kind") != "select_goal"
        ):
            raise GoalManagerTrajectoryError("goal-manager action is invalid")
        selected = _integer(
            action.get("selected_candidate_index"), subject="selected candidate index"
        )
        try:
            bind_goal_selection(question, selected)
        except GoalManagerError as error:
            raise GoalManagerTrajectoryError(str(error)) from error
        if (
            behavior_candidate_probabilities is not None
            and behavior_probability
            != behavior_candidate_probabilities[selected]
        ):
            raise GoalManagerTrajectoryError(
                "selected behavior probability differs from its candidate probability"
            )
        try:
            outcome = events_by_decision.pop(decision_id)
        except KeyError as error:
            raise GoalManagerTrajectoryError(
                "goal-manager decision has no consumed outcome"
            ) from error
        if outcome.get("selected_candidate_index") != selected:
            raise GoalManagerTrajectoryError("goal-manager outcome selected index differs")
        try:
            status = GoalDecisionOutcome(
                _string(outcome.get("status"), subject="goal-manager outcome status")
            )
            raw_reason = outcome.get("failure_reason")
            failure_reason = (
                None
                if raw_reason is None
                else GoalFailureReason(_string(raw_reason, subject="goal-manager failure reason"))
            )
            _validate_outcome(status, failure_reason)
        except (TypeError, ValueError) as error:
            raise GoalManagerTrajectoryError(
                "goal-manager outcome vocabulary is invalid"
            ) from error
        examples.append(
            GoalManagerExample(
                decision_id=decision_id,
                episode_id=episode_id,
                decision_index=decision_index,
                root_lineage_id=root_lineage_id,
                partition=partition,
                environment_id=environment_id,
                actor=actor,
                policy_id=policy_id,
                question=question,
                selected_candidate_index=selected,
                outcome_status=status,
                failure_reason=failure_reason,
                behavior_policy_id=behavior_policy_id,
                behavior_probability=behavior_probability,
                behavior_candidate_probabilities=behavior_candidate_probabilities,
                behavior_base_probability=behavior_base_probability,
                behavior_exploration_mix=behavior_exploration_mix,
                behavior_temperature=behavior_temperature,
                selection_mode=selection_mode,
            )
        )
    if events_by_decision:
        raise GoalManagerTrajectoryError("goal-manager outcome has no decision")
    return CollectedGoalManagerDataset(
        episode_id=episode_id,
        manifest_sha256=_digest(reader.manifest_sha256, subject="episode manifest"),
        root_lineage_id=root_lineage_id,
        partition=partition,
        environment_id=environment_id,
        actor=actor,
        policy_id=policy_id,
        collection_id=collection_id,
        assignment_id=assignment_id,
        source_commit=source_commit,
        context_catalog_sha256=context_catalog_sha256,
        context_id=context_id,
        binding_manifest_sha256=binding_manifest_sha256,
        capture_state_sha256=capture_state_sha256,
        capture_envelope_sha256=capture_envelope_sha256,
        examples=tuple(examples),
    )


def _validate_outcome(
    status: GoalDecisionOutcome,
    failure_reason: GoalFailureReason | None,
) -> None:
    if not isinstance(status, GoalDecisionOutcome):
        raise GoalManagerTrajectoryError("goal-manager outcome is invalid")
    if status is GoalDecisionOutcome.SUCCEEDED:
        if failure_reason is not None:
            raise GoalManagerTrajectoryError(
                "a successful goal-manager outcome cannot have a failure reason"
            )
    elif not isinstance(failure_reason, GoalFailureReason):
        raise GoalManagerTrajectoryError(
            "a failed or interrupted goal-manager outcome needs a reason"
        )


def _json_mapping(value: Mapping[str, object]) -> Mapping[str, JSONValue]:
    return cast(Mapping[str, JSONValue], _json_value(value))


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GoalManagerTrajectoryError(f"{subject} must be an object")
    return value


def _string(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise GoalManagerTrajectoryError(f"{subject} must be non-empty")
    return value


def _integer(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise GoalManagerTrajectoryError(f"{subject} must be a non-negative integer")
    return value


def _number(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoalManagerTrajectoryError(f"{subject} must be numeric")
    return float(value)


def _probability(value: object, *, subject: str, positive: bool) -> float:
    result = _number(value, subject=subject)
    if not 0.0 <= result <= 1.0 or (positive and result == 0.0):
        raise GoalManagerTrajectoryError(f"{subject} must be a valid probability")
    return result


def _positive_number(value: object, *, subject: str) -> float:
    result = _number(value, subject=subject)
    if result <= 0.0:
        raise GoalManagerTrajectoryError(f"{subject} must be positive")
    return result


def _parse_behavior_policy(
    value: object,
    *,
    question: GoalManagerQuestion,
) -> tuple[
    str | None,
    float | None,
    tuple[float, ...] | None,
    float | None,
    float | None,
    float | None,
]:
    if value is None:
        return None, None, None, None, None, None
    behavior = _mapping(value, subject="goal-manager behavior policy")
    if set(behavior) != {
        "base_selected_probability",
        "behavior_policy_id",
        "candidate_probabilities",
        "exploration_mix",
        "schema",
        "selected_probability",
        "temperature",
    } or behavior.get("schema") != "pokemon.core.goal-manager-behavior-policy.v1":
        raise GoalManagerTrajectoryError("goal-manager behavior policy schema is invalid")
    policy_id = _string(
        behavior.get("behavior_policy_id"),
        subject="goal-manager behavior policy identity",
    )
    selected_probability = _probability(
        behavior.get("selected_probability"),
        subject="goal-manager selected behavior probability",
        positive=True,
    )
    base_probability = _probability(
        behavior.get("base_selected_probability"),
        subject="goal-manager selected base probability",
        positive=False,
    )
    exploration_mix = _probability(
        behavior.get("exploration_mix"),
        subject="goal-manager exploration mix",
        positive=False,
    )
    temperature = _positive_number(
        behavior.get("temperature"),
        subject="goal-manager behavior temperature",
    )
    candidate_probabilities = behavior.get("candidate_probabilities")
    if (
        not isinstance(candidate_probabilities, (list, tuple))
        or len(candidate_probabilities) != len(question.opportunities)
        or any(
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not 0.0 <= float(item) <= 1.0
            for item in candidate_probabilities
        )
        or abs(sum(float(item) for item in candidate_probabilities) - 1.0) > 1e-9
    ):
        raise GoalManagerTrajectoryError(
            "goal-manager behavior probabilities are invalid"
        )
    return (
        policy_id,
        selected_probability,
        tuple(float(item) for item in candidate_probabilities),
        base_probability,
        exploration_mix,
        temperature,
    )


def _digest(value: object, *, subject: str) -> str:
    result = _string(value, subject=subject)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise GoalManagerTrajectoryError(f"{subject} must be a lowercase SHA-256 digest")
    return result
