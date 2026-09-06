"""Passive spectator updates from existing bounded-player observations and records.

This view never re-observes the cartridge, calls a policy, or executes a binding.
It publishes a selection only after its durable trajectory write. Party and
collection values describe the last semantic boundary, not every video frame.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field, replace

from pokemon_red_completion.bounded_player_episode import BoundedPlayerResult
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalManagerQuestion,
    GoalSelectionMode,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
    GoalManagerCompositionObservation,
)
from pokemon_red_completion.goal_manager_runtime import GoalDecisionAuthority
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryObserver,
    PendingGoalManagerDecision,
)
from pokemon_red_completion.living_dex_goal_policy import (
    LivingDexGoalDecisionMode,
    LivingDexGoalShadowPolicy,
)
from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardFrameObserver,
    DashboardGoalPressure,
    DashboardLearningComponent,
    DashboardModelState,
    DashboardPartyMember,
    DashboardSnapshot,
    DashboardState,
)
from pokemon_red_completion.red_collection import red_internal_species_number
from pokemon_red_completion.red_goal_manager import RedGoalObservation


class BoundedPlayerDashboard:
    """Best-effort read-only side channel; a view failure cannot choose an action."""

    def __init__(self, state: DashboardState, *, decision_limit: int) -> None:
        if type(decision_limit) is not int or not 1 <= decision_limit <= 4:
            raise ValueError("viewer requires a bounded one-to-four-goal episode")
        self.state = state
        self.decision_limit = decision_limit
        self.disabled = False
        self.failure_count = 0
        self._frames = DashboardFrameObserver(state, maximum_fps=12)
        self._snapshot = DashboardSnapshot(
            game="Pokémon Red",
            run_status="waiting",
            stage="Bounded player preparation",
            message="Waiting for the next authenticated game observation.",
            collection_target=151,
            collection_observed=False,
        )
        self._budget: Callable[[], CompositionBudgetCheckpoint] | None = None
        self._frame_offset = 0
        self._action_offset = 0
        self._started_at = time.monotonic()
        self._settled = 0
        self._committed = 0
        self._events: list[str] = []
        self.state.publish(self._snapshot)

    def safely(self, method: str, *args: object, **kwargs: object) -> None:
        if self.disabled:
            return
        try:
            getattr(self, method)(*args, **kwargs)
        except Exception:
            self.disabled = True
            self.failure_count += 1
            # No exception message, private object repr or traceback goes to HTTP.
            with suppress(Exception):
                self.state.publish(
                    replace(
                        self._snapshot,
                        run_status="blocked",
                        stage="Viewer unavailable",
                        message="Viewer stopped. The durable run remains authoritative.",
                    )
                )

    def start_arm(
        self,
        *,
        learned: bool,
        model_sha256: str,
        train_examples: int | None,
    ) -> None:
        self._frame_offset = self._snapshot.frame_count
        self._action_offset = self._snapshot.actions
        self._budget = None
        self._committed = self._settled = 0
        actor = "Learned challenger" if learned else "Deterministic comparison"
        self._events.append(f"{actor} starts from the same declared save")
        components = (
            ()
            if train_examples is None
            else (
                DashboardLearningComponent(
                    name="Living-Pokédex goal scorer",
                    scope="Bounded development, not production authority",
                    status="shadow",
                    authority="shadow_only",
                    train_examples=train_examples,
                    validation_examples=0,
                    validation_correct=0,
                    baseline_correct=None,
                    model_sha256=model_sha256,
                    independent_validation_units=0,
                ),
            )
        )
        self._snapshot = DashboardSnapshot(
            game="Pokémon Red",
            run_status="waiting",
            stage=actor,
            message="Preparing this arm. Any displayed frame belongs to the preceding arm.",
            frame_count=self._frame_offset,
            actions=self._action_offset,
            collection_target=151,
            collection_observed=False,
            model=DashboardModelState(mode="waiting", candidate=actor),
            learning_components=components,
            experiment=DashboardExperimentState(
                phase="live_evaluation",
                heading="Bounded Red development play",
                eyebrow="Model choice → deterministic skill → independent verification",
                zero_shot_total=self.decision_limit,
                adaptation_total=self.decision_limit,
                sealed_total=0,
                counter_labels=("Committed goals", "Settled goals", "Fits during play"),
            ),
        )
        self._publish()

    def bind_budget(self, checkpoint: Callable[[], CompositionBudgetCheckpoint]) -> None:
        self._budget = checkpoint

    def observed(
        self,
        live: RedGoalObservation,
        observation: GoalManagerCompositionObservation,
    ) -> None:
        if not isinstance(live, RedGoalObservation):
            raise TypeError("viewer requires an existing typed Red observation")
        collection = observation.collection
        self._snapshot = replace(
            self._snapshot,
            run_status="running",
            location=live.game_state.location,
            registered_species=collection.registered_species,
            living_species=collection.living_species,
            level_cap_species=live.evidence.level_collection.completed,
            collection_observed=True,
            capture_items=live.capture_item_count,
            free_storage_slots=live.free_storage_slots,
            party=tuple(
                DashboardPartyMember(
                    slot=member.slot,
                    label=f"Pokédex #{red_internal_species_number(member.species_id):03d}",
                    level=member.level,
                    hp=member.hp,
                    max_hp=member.max_hp,
                    status="fainted" if member.hp == 0 else member.status.value,
                )
                for member in live.party.members
            ),
            goals=tuple(
                DashboardGoalPressure(
                    goal=item.kind.value.replace("_", " "),
                    pressure=max(
                        observation.situation.pressure(need) for need in item.addressed_needs
                    ),
                    available=item.availability is GoalAvailability.AVAILABLE,
                )
                for item in observation.binding_set.opportunities
            ),
            message="Fresh boundary verified. Party and collection reflect this observation.",
        )
        self._events.append(
            f"Observed: {collection.living_species} living species; "
            f"{collection.required_specimens_remaining} required specimens remain"
        )
        self._publish()

    def committed(
        self,
        pending: PendingGoalManagerDecision,
        selection_mode: GoalSelectionMode,
        authority: GoalDecisionAuthority,
        *,
        learned: bool,
    ) -> None:
        selected = pending.question.opportunities[pending.selected_candidate_index]
        actor = "Model" if learned else "Deterministic comparison"
        model_choice = learned
        if selection_mode is GoalSelectionMode.FORCED_SINGLETON:
            actor, model_choice = "Forced single option", False
        elif isinstance(authority, LivingDexGoalShadowPolicy):
            decision = authority.last_decision
            if decision is None or decision.selected_kind != selected.kind:
                raise ValueError("viewer decision does not match the committed policy choice")
            model_choice = decision.mode is LivingDexGoalDecisionMode.MODEL_SHADOW
            actor = "Model" if model_choice else "Deterministic safety / unsupported"
            if model_choice:
                for score in sorted(decision.scores, key=lambda value: -value.utility):
                    self._events.append(
                        f"Score: {score.goal_kind.value.replace('_', ' ')} "
                        f"{score.utility:+.3f} utility (not a confidence probability)"
                    )
        self._committed += 1
        goal = selected.kind.value.replace("_", " ")
        self._events.append(f"Goal {self._committed}: {actor} chose {goal}; choice recorded")
        self._snapshot = replace(
            self._snapshot,
            stage=f"{actor} · {goal}",
            message="Choice recorded. Existing skills execute it; the verifier checks the result.",
            model=replace(
                self._snapshot.model,
                mode="model" if model_choice else "teacher",
                choice=f"{actor}: {goal}",
                decisions=self._snapshot.model.decisions + int(model_choice),
                fallbacks=self._snapshot.model.fallbacks + int(learned and not model_choice),
                teacher_queries=self._snapshot.model.teacher_queries
                + int(not learned and selection_mode is GoalSelectionMode.AUTHORITY),
            ),
            goals=tuple(replace(item, selected=item.goal == goal) for item in self._snapshot.goals),
        )
        self._publish()

    def settled(self, status: GoalDecisionOutcome, failure: GoalFailureReason | None) -> None:
        self._settled += 1
        reason = "" if failure is None else f" · {failure.value}"
        self._events.append(f"Goal {self._settled} outcome: {status.value}{reason}")
        self._publish()

    def finished(self, result: BoundedPlayerResult) -> None:
        self._events.append(f"Arm stopped: {result.stop_reason.value}")
        self._snapshot = replace(
            self._snapshot,
            run_status="paused",
            stage="Bounded arm finished",
            message="Saved final frame. An episode terminal does not prove game completion.",
        )
        self._publish()

    def failed(self) -> None:
        self._snapshot = replace(
            self._snapshot,
            run_status="failed",
            stage="Bounded arm failed",
            message="Execution stopped; details retained privately. No automatic retry.",
        )
        self._publish()

    def _publish(self) -> None:
        if self._budget is not None:
            budget = self._budget()
            self._snapshot = replace(
                self._snapshot,
                frame_count=self._frame_offset + budget.emulator_frames,
                actions=self._action_offset + budget.controller_actions,
            )
        self._snapshot = replace(
            self._snapshot,
            events=tuple(self._events[-24:]),
            stage_progress=min(1.0, self._settled / self.decision_limit),
            experiment=replace(
                self._snapshot.experiment,
                zero_shot_completed=self._committed,
                adaptation_completed=self._settled,
                predictions_committed=self._committed > 0,
            ),
        )
        self.state.publish(self._snapshot)

    def wants_frame(self, logical_frame: int) -> bool:
        return not self.disabled and self._frames.wants_frame(logical_frame)

    def publish_frame(self, width: int, height: int, rgb: bytes, logical_frame: int) -> None:
        self.safely("_publish_frame", width, height, rgb, logical_frame)

    def _publish_frame(self, width: int, height: int, rgb: bytes, logical_frame: int) -> None:
        frame = self._frame_offset + logical_frame
        budget = self._budget() if self._budget is not None else None
        self._snapshot = replace(
            self._snapshot,
            frame_count=frame,
            actions=self._action_offset + (0 if budget is None else budget.controller_actions),
            emulation_speed=frame / max(0.001, time.monotonic() - self._started_at) / 60.0,
        )
        self._frames.publish_frame(width, height, rgb, frame)
        self._publish()


@dataclass(slots=True)
class ViewerGoalTrajectory(GoalManagerTrajectoryObserver):
    """Notify only after the existing durable decision/outcome write succeeds."""

    viewer: BoundedPlayerDashboard | None = field(default=None, repr=False)
    displayed_authority: GoalDecisionAuthority | None = field(default=None, repr=False)
    learned_actor: bool = False

    def record_selection(
        self,
        question: GoalManagerQuestion,
        selected_candidate_index: int,
        *,
        behavior_policy: Mapping[str, object] | None = None,
        selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY,
    ) -> PendingGoalManagerDecision:
        pending = GoalManagerTrajectoryObserver.record_selection(
            self,
            question,
            selected_candidate_index,
            behavior_policy=behavior_policy,
            selection_mode=selection_mode,
        )
        if self.viewer is not None and self.pending_was_recorded:
            self.viewer.safely(
                "committed",
                pending,
                selection_mode,
                self.displayed_authority,
                learned=self.learned_actor,
            )
        return pending

    def record_outcome(
        self,
        pending: PendingGoalManagerDecision,
        *,
        status: GoalDecisionOutcome,
        failure_reason: GoalFailureReason | None = None,
    ) -> bool:
        recorded = GoalManagerTrajectoryObserver.record_outcome(
            self,
            pending,
            status=status,
            failure_reason=failure_reason,
        )
        if self.viewer is not None and recorded:
            self.viewer.safely("settled", status, failure_reason)
        return recorded
