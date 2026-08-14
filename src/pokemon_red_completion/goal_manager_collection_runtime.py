"""One-shot authenticated collection of a Red goal-manager microcontext."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalKind,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    GoalManagerContextCatalog,
    goal_manager_catalog_episode_metadata,
)
from pokemon_red_completion.goal_manager_dataset import (
    GoalManagerDatasetError,
    load_assigned_goal_manager_episode,
)
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_ACTOR,
    GOAL_MANAGER_GAME_ID,
    GOAL_MANAGER_POLICY_ID,
    GoalManagerAssignment,
)
from pokemon_red_completion.goal_manager_runtime import (
    CompletionFirstGoalTeacher,
    GoalBindingSet,
    GoalDecisionAuthority,
    GoalManagerExecutionResult,
    execute_goal_manager_decision,
)
from pokemon_red_completion.goal_manager_trajectory import (
    CollectedGoalManagerDataset,
    GoalManagerTrajectoryObserver,
    ordered_goal_manager_question,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalOpportunityEnumerator,
)
from pokemon_red_completion.trajectory import (
    RecordingExecutor,
    SnapshotProvider,
    SparseEvent,
)
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink


class GoalManagerCollectionRuntimeError(RuntimeError):
    """Raised before a microcontext can become counted training evidence."""


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")


class GoalActionPort(Protocol):
    def execute(self, action: MacroAction) -> object: ...


GoalEnumeratorFactory = Callable[
    [CountingExecutor],
    RedGoalOpportunityEnumerator,
]


@dataclass(frozen=True, slots=True)
class GoalManagerContextPreflight:
    """Path-free proof that one frozen state has a useful manager decision."""

    assignment_id: str
    slot_id: str
    capture_id: str
    state_sha256: str
    envelope_sha256: str
    focus_kind: GoalKind
    selected_kind: GoalKind
    available_goal_count: int
    available_goal_kinds: tuple[GoalKind, ...]
    focus_pressure: float
    question_sha256: str
    binding_manifest_sha256: str

    def __post_init__(self) -> None:
        for value, subject in (
            (self.slot_id, "slot identity"),
            (self.capture_id, "capture identity"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise GoalManagerCollectionRuntimeError(f"preflight {subject} is invalid")
        for value, subject in (
            (self.assignment_id, "assignment digest"),
            (self.state_sha256, "state digest"),
            (self.envelope_sha256, "envelope digest"),
            (self.question_sha256, "question digest"),
            (self.binding_manifest_sha256, "binding manifest digest"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise GoalManagerCollectionRuntimeError(f"preflight {subject} is invalid")
        if not isinstance(self.focus_kind, GoalKind) or not isinstance(
            self.selected_kind, GoalKind
        ):
            raise GoalManagerCollectionRuntimeError("preflight goal kind is invalid")
        if (
            type(self.available_goal_count) is not int  # noqa: E721
            or self.available_goal_count < 1
            or len(self.available_goal_kinds) != self.available_goal_count
            or len(set(self.available_goal_kinds)) != len(self.available_goal_kinds)
            or any(not isinstance(kind, GoalKind) for kind in self.available_goal_kinds)
            or self.available_goal_kinds
            != tuple(kind for kind in GoalKind if kind in set(self.available_goal_kinds))
        ):
            raise GoalManagerCollectionRuntimeError(
                "preflight available goal menu is invalid"
            )
        if self.selected_kind not in self.available_goal_kinds:
            raise GoalManagerCollectionRuntimeError(
                "preflight selected goal is not available"
            )
        if isinstance(self.focus_pressure, bool) or not isinstance(
            self.focus_pressure, (int, float)
        ):
            raise GoalManagerCollectionRuntimeError("preflight focus pressure is invalid")
        if not 0.0 <= float(self.focus_pressure) <= 1.0:
            raise GoalManagerCollectionRuntimeError("preflight focus pressure is invalid")

    @property
    def passed(self) -> bool:
        return (
            self.focus_kind is self.selected_kind
            and self.available_goal_count >= 1
            and len(self.available_goal_kinds) == self.available_goal_count
            and self.focus_pressure >= 0.5
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-goal-manager-context-preflight-v1",
            "assignment_id": self.assignment_id,
            "slot_id": self.slot_id,
            "capture_id": self.capture_id,
            "state_sha256": self.state_sha256,
            "envelope_sha256": self.envelope_sha256,
            "focus_kind": self.focus_kind.value,
            "selected_kind": self.selected_kind.value,
            "available_goal_count": self.available_goal_count,
            "available_goal_kinds": [kind.value for kind in self.available_goal_kinds],
            "focus_pressure": self.focus_pressure,
            "question_sha256": self.question_sha256,
            "binding_manifest_sha256": self.binding_manifest_sha256,
            "passed": self.passed,
            "private_binding_fields": 0,
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class RecordedGoalManagerContext:
    """Strictly reloaded result of one completed one-decision episode."""

    preflight: GoalManagerContextPreflight
    execution: GoalManagerExecutionResult
    dataset: CollectedGoalManagerDataset
    episode_summary: Mapping[str, object]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-recorded-goal-manager-context-v1",
            "preflight": self.preflight.public_dict(),
            "execution": self.execution.public_dict(),
            "dataset": self.dataset.public_summary(),
            "episode": dict(self.episode_summary),
            "private_path_fields": 0,
        }


def goal_binding_manifest_sha256(binding_set: GoalBindingSet) -> str:
    """Bind the private executable behind every model-facing candidate.

    Binding identities stay out of model input and recorded decisions, but the
    private context catalog must still prevent a curator from freezing one
    question and executing a different same-shaped skill later.
    """

    if not isinstance(binding_set, GoalBindingSet):
        raise TypeError("binding_set must be a GoalBindingSet")
    return canonical_sha256(
        {
            "schema": "pokemon-red-goal-manager-binding-manifest-v1",
            "opportunities": [
                {
                    "binding_ref": opportunity.binding_ref,
                    "policy": opportunity.policy_dict(),
                }
                for opportunity in binding_set.opportunities
            ],
        }
    )


def preflight_goal_manager_context(
    *,
    assignment: GoalManagerAssignment,
    capture: GoalManagerContextCapture,
    adapter: PokemonRedGoalStateAdapter,
    enumerator: RedGoalOpportunityEnumerator,
    authority: GoalDecisionAuthority | None = None,
) -> GoalManagerContextPreflight:
    """Inspect a state without acting or opening its one-shot episode namespace."""

    _require_committed_assignment(assignment)
    if not isinstance(capture, GoalManagerContextCapture):
        raise TypeError("capture must be a verified goal-manager context capture")
    observation = adapter.observe()
    binding_set = enumerator.enumerate(observation)
    question = ordered_goal_manager_question(
        assignment_id=assignment.assignment_id,
        decision_index=0,
        situation=observation.situation,
        opportunities=binding_set.opportunities,
    )
    selected = (authority or CompletionFirstGoalTeacher()).select(question)
    bound = _bound_selection(question, selected)
    preflight = GoalManagerContextPreflight(
        assignment_id=assignment.assignment_id,
        slot_id=assignment.slot_id,
        capture_id=capture.capture_id,
        state_sha256=capture.state_sha256,
        envelope_sha256=capture.envelope_sha256,
        focus_kind=assignment.focus_kind,
        selected_kind=bound.kind,
        available_goal_count=len(question.available_indices),
        available_goal_kinds=tuple(
            kind
            for kind in GoalKind
            if any(
                opportunity.kind is kind
                for opportunity in question.opportunities
                if opportunity.availability.value == "available"
            )
        ),
        focus_pressure=question.situation.pressure(assignment.focus_need),
        question_sha256=question.ordered_policy_input_sha256,
        binding_manifest_sha256=goal_binding_manifest_sha256(binding_set),
    )
    if not preflight.passed:
        reasons = []
        if preflight.available_goal_count < 1:
            reasons.append("no_available_goal")
        if preflight.focus_pressure < 0.5:
            reasons.append("focus_pressure_below_threshold")
        if preflight.selected_kind is not preflight.focus_kind:
            reasons.append("teacher_did_not_select_focus_kind")
        raise GoalManagerCollectionRuntimeError(
            "goal-manager context preflight failed: " + ", ".join(reasons)
        )
    return preflight


def record_goal_manager_context(
    *,
    private_root: PrivateArtifactRoot,
    assignment: GoalManagerAssignment,
    capture: GoalManagerContextCapture,
    context_catalog: GoalManagerContextCatalog,
    metadata: Mapping[str, object],
    adapter: PokemonRedGoalStateAdapter,
    snapshot_provider: SnapshotProvider,
    action_delegate: GoalActionPort,
    enumerator_factory: GoalEnumeratorFactory,
    authority: GoalDecisionAuthority | None = None,
) -> RecordedGoalManagerContext:
    """Preflight, durably record, execute, verify, and strictly reload one slot."""

    if not isinstance(private_root, PrivateArtifactRoot):
        raise TypeError("private_root must be a PrivateArtifactRoot")
    _require_committed_assignment(assignment)
    if not isinstance(capture, GoalManagerContextCapture):
        raise TypeError("capture must be a verified goal-manager context capture")
    _require_assignment_metadata(assignment, context_catalog, metadata)
    selected_authority = authority or CompletionFirstGoalTeacher()

    # This phase performs no action and creates no private output.  A bad state
    # therefore cannot consume the one permitted episode identity.
    preflight_actions = CountingExecutor(action_delegate)
    preflight = preflight_goal_manager_context(
        assignment=assignment,
        capture=capture,
        adapter=adapter,
        enumerator=enumerator_factory(preflight_actions),
        authority=selected_authority,
    )
    context = context_catalog.entry(assignment.slot_id)
    if (
        context.assignment_id != assignment.assignment_id
        or context.capture_id != capture.capture_id
        or context.state_sha256 != capture.state_sha256
        or context.envelope_sha256 != capture.envelope_sha256
        or context.question_sha256 != preflight.question_sha256
        or context.binding_manifest_sha256 != preflight.binding_manifest_sha256
        or context.selected_kind is not preflight.selected_kind
        or context.available_goal_kinds != preflight.available_goal_kinds
        or context.focus_pressure != preflight.focus_pressure
    ):
        raise GoalManagerCollectionRuntimeError(
            "live preflight differs from the frozen context catalog"
        )

    writer = private_root.begin_episode(assignment.episode_id)
    with writer:
        sink = EpisodeTrajectorySink(
            writer,
            episode_id=assignment.episode_id,
            game_id=GOAL_MANAGER_GAME_ID,
        )
        sink.write_episode_header(metadata=metadata)
        recorder: RecordingExecutor[MacroAction, object] = RecordingExecutor(
            delegate=action_delegate,
            snapshot_provider=snapshot_provider,
            sink=sink,
            episode_id=assignment.episode_id,
        )
        actions = CountingExecutor(recorder)
        observation = adapter.observe()
        binding_set = enumerator_factory(actions).enumerate(observation)
        live_question = ordered_goal_manager_question(
            assignment_id=assignment.assignment_id,
            decision_index=0,
            situation=observation.situation,
            opportunities=binding_set.opportunities,
        )
        if live_question.ordered_policy_input_sha256 != preflight.question_sha256:
            raise GoalManagerCollectionRuntimeError(
                "goal-manager state changed after preflight and before durable choice"
            )
        if goal_binding_manifest_sha256(binding_set) != preflight.binding_manifest_sha256:
            raise GoalManagerCollectionRuntimeError(
                "goal-manager executable bindings changed after preflight"
            )
        trajectory = GoalManagerTrajectoryObserver(
            episode_id=assignment.episode_id,
            root_lineage_id=assignment.root_lineage_id,
            partition=assignment.partition,
            environment_id=GOAL_MANAGER_GAME_ID,
            actor=GOAL_MANAGER_ACTOR,
            policy_id=GOAL_MANAGER_POLICY_ID,
            collection_id=assignment.collection_id,
            assignment_id=assignment.assignment_id,
            source_commit=assignment.source_commit or "",
            snapshot_provider=snapshot_provider,
            recorder=recorder,
            sink=sink,
        )
        execution = execute_goal_manager_decision(
            situation=observation.situation,
            binding_set=binding_set,
            authority=selected_authority,
            trajectory=trajectory,
        )
        if execution.selected_kind is not assignment.focus_kind:
            raise GoalManagerCollectionRuntimeError(
                "live teacher selection differs from the preflight focus"
            )
        if not execution.passed:
            raise GoalManagerCollectionRuntimeError(
                "goal-manager selected skill failed independent verification"
            )
        if not execution.decision_recorded or not execution.outcome_recorded:
            raise GoalManagerCollectionRuntimeError(
                "goal-manager decision instrumentation did not persist"
            )
        trajectory.require_settled()
        if recorder.recording_failures:
            raise GoalManagerCollectionRuntimeError(
                "goal-manager trajectory instrumentation failed"
            )
        sink.record_event(
            SparseEvent(
                event_id=f"{assignment.episode_id}:terminal",
                episode_id=assignment.episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "goal_manager_decisions": 1,
                    "goal_manager_outcomes": 1,
                },
            )
        )
        sink.finalize()

    try:
        dataset = load_assigned_goal_manager_episode(
            private_root.open_episode(assignment.episode_id),
            assignment,
            context_catalog=context_catalog,
        )
    except GoalManagerDatasetError as error:
        raise GoalManagerCollectionRuntimeError(str(error)) from error
    example = dataset.examples[0]
    if example.teacher_choice_target is None or example.selected_kind is not assignment.focus_kind:
        raise GoalManagerCollectionRuntimeError(
            "completed goal-manager episode is not an admissible focused teacher choice"
        )
    return RecordedGoalManagerContext(
        preflight=preflight,
        execution=execution,
        dataset=dataset,
        episode_summary=writer.summary.public_dict(),
    )


def _bound_selection(question, selected: object) -> BoundGoalSelection:  # type: ignore[no-untyped-def]
    if isinstance(selected, BoundGoalSelection):
        rebound = bind_goal_selection(question, selected.selected_index)
        if rebound != selected:
            raise GoalManagerCollectionRuntimeError(
                "goal authority returned a selection for a different question"
            )
        return rebound
    if type(selected) is int:  # noqa: E721
        return bind_goal_selection(question, selected)
    raise GoalManagerCollectionRuntimeError("goal authority returned an invalid selection")


def _require_committed_assignment(assignment: GoalManagerAssignment) -> None:
    if not isinstance(assignment, GoalManagerAssignment):
        raise TypeError("assignment must be a GoalManagerAssignment")
    if assignment.source_commit is None:
        raise GoalManagerCollectionRuntimeError(
            "goal-manager collection requires one exact committed source"
        )


def _require_assignment_metadata(
    assignment: GoalManagerAssignment,
    context_catalog: GoalManagerContextCatalog,
    metadata: Mapping[str, object],
) -> None:
    if not isinstance(metadata, Mapping):
        raise TypeError("goal-manager episode metadata must be a mapping")
    expected = goal_manager_catalog_episode_metadata(assignment, context_catalog)
    for key in ("goal_manager", "policy", "source", "source_bundle_sha256", "split"):
        if metadata.get(key) != expected[key]:
            raise GoalManagerCollectionRuntimeError(
                "goal-manager episode metadata differs from its assignment"
            )
