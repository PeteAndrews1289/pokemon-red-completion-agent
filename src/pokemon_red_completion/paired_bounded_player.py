"""Outcome comparison for two independently restored bounded-player arms."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerResult,
    BoundedPlayerStopReason,
)
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import (
    GoalManagerCompositionError,
    LivingCollectionCheckpoint,
    require_living_collection_transition,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PUBLIC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class PairedBoundedPlayerError(RuntimeError):
    """Raised when two bounded arms are not a trustworthy pair."""


class PairedBoundedPlayerVerdict(StrEnum):
    """Outcome-only paired comparison without an arbitrary scalar reward."""

    LEARNED_ADVANTAGE = "learned_advantage"
    BASELINE_ADVANTAGE = "baseline_advantage"
    EQUIVALENT = "equivalent"
    INCOMPARABLE = "incomparable"


@dataclass(frozen=True, slots=True)
class BoundedPlayerProgress:
    """Verified progress and cost projected from one bounded episode."""

    completion_satisfied: bool
    required_specimens_reduced: int
    registered_species_gained: int
    living_species_gained: int
    retained_captures_gained: int
    storage_headroom_gained: int
    successful_decisions: int
    successful_goal_counts: tuple[tuple[GoalKind, int], ...]
    controller_actions: int
    emulator_frames: int
    recovery_attempts: int

    @property
    def progress_vector(self) -> tuple[int, ...]:
        return (
            int(self.completion_satisfied),
            self.required_specimens_reduced,
            self.registered_species_gained,
            self.living_species_gained,
            self.retained_captures_gained,
            self.storage_headroom_gained,
            self.successful_decisions,
            *(count for _kind, count in self.successful_goal_counts),
        )

    @property
    def cost_vector(self) -> tuple[int, ...]:
        return (
            self.controller_actions,
            self.emulator_frames,
            self.recovery_attempts,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "completion_satisfied": self.completion_satisfied,
            "controller_actions": self.controller_actions,
            "emulator_frames": self.emulator_frames,
            "living_species_gained": self.living_species_gained,
            "recovery_attempts": self.recovery_attempts,
            "registered_species_gained": self.registered_species_gained,
            "required_specimens_reduced": self.required_specimens_reduced,
            "retained_captures_gained": self.retained_captures_gained,
            "storage_headroom_gained": self.storage_headroom_gained,
            "successful_decisions": self.successful_decisions,
            "successful_goal_counts": {
                kind.value: count for kind, count in self.successful_goal_counts
            },
        }


@dataclass(frozen=True, slots=True)
class PairedBoundedPlayerArm:
    """One durable episode plus its independently authenticated starting state."""

    arm_id: str
    starting_state_sha256: str
    starting_semantic_state_sha256: str
    starting_collection: LivingCollectionCheckpoint
    trajectory_manifest_sha256: str
    episode: BoundedPlayerResult

    def __post_init__(self) -> None:
        if not isinstance(self.arm_id, str) or _PUBLIC_ID.fullmatch(self.arm_id) is None:
            raise PairedBoundedPlayerError("paired arm id must be path-free")
        for name in (
            "starting_state_sha256",
            "starting_semantic_state_sha256",
            "trajectory_manifest_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise PairedBoundedPlayerError(f"paired arm {name} is invalid")
        if not isinstance(self.starting_collection, LivingCollectionCheckpoint):
            raise TypeError("starting_collection must be a LivingCollectionCheckpoint")
        if not isinstance(self.episode, BoundedPlayerResult):
            raise TypeError("episode must be a BoundedPlayerResult")
        if self.episode.authority_id != self.arm_id:
            raise PairedBoundedPlayerError("paired arm authority identity differs")
        if self.episode.completion_satisfied != (
            self.episode.stop_reason is BoundedPlayerStopReason.COMPLETION_REACHED
        ):
            raise PairedBoundedPlayerError("paired arm terminal state is inconsistent")
        previous = self.starting_collection
        for ordinal, step in enumerate(self.episode.steps, start=1):
            if step.decision_ordinal != ordinal or step.collection_before != previous:
                raise PairedBoundedPlayerError("paired arm collection chain is invalid")
            if step.actions_executed < 0 or step.frames_executed < 0:
                raise PairedBoundedPlayerError("paired arm cost counters are invalid")
            succeeded = step.status is GoalDecisionOutcome.SUCCEEDED
            if succeeded and not step.semantic_state_changed:
                raise PairedBoundedPlayerError("paired arm success retained stale semantic state")
            try:
                require_living_collection_transition(
                    step.collection_before,
                    step.collection_after,
                    selected_kind=step.selected_kind,
                    require_selected_goal_progress=succeeded,
                )
            except GoalManagerCompositionError as error:
                raise PairedBoundedPlayerError(
                    "paired arm collection transition is invalid"
                ) from error
            previous = step.collection_after

    @property
    def ending_collection(self) -> LivingCollectionCheckpoint:
        if not self.episode.steps:
            return self.starting_collection
        return self.episode.steps[-1].collection_after

    @property
    def progress(self) -> BoundedPlayerProgress:
        final = self.ending_collection
        initial = self.starting_collection
        successful_goal_counts = tuple(
            (
                kind,
                sum(
                    step.status is GoalDecisionOutcome.SUCCEEDED
                    and step.selected_kind is kind
                    for step in self.episode.steps
                ),
            )
            for kind in GoalKind
        )
        return BoundedPlayerProgress(
            completion_satisfied=self.episode.completion_satisfied,
            required_specimens_reduced=(
                initial.required_specimens_remaining - final.required_specimens_remaining
            ),
            registered_species_gained=(
                final.registered_species - initial.registered_species
            ),
            living_species_gained=final.living_species - initial.living_species,
            retained_captures_gained=(
                final.retained_captures - initial.retained_captures
            ),
            storage_headroom_gained=final.storage_headroom - initial.storage_headroom,
            successful_decisions=sum(
                step.status is GoalDecisionOutcome.SUCCEEDED
                for step in self.episode.steps
            ),
            successful_goal_counts=successful_goal_counts,
            controller_actions=sum(step.actions_executed for step in self.episode.steps),
            emulator_frames=sum(step.frames_executed for step in self.episode.steps),
            recovery_attempts=self.episode.recovery_attempts,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "arm_id": self.arm_id,
            "episode": self.episode.public_dict(),
            "progress": self.progress.public_dict(),
            "starting_collection": self.starting_collection.public_dict(),
            "starting_semantic_state_sha256": self.starting_semantic_state_sha256,
            "starting_state_sha256": self.starting_state_sha256,
            "trajectory_manifest_sha256": self.trajectory_manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class PairedBoundedPlayerComparison:
    """A same-reset comparison between learned and deterministic authorities."""

    pair_id: str
    learned: PairedBoundedPlayerArm
    baseline: PairedBoundedPlayerArm
    verdict: PairedBoundedPlayerVerdict
    decision_basis: str

    def public_dict(self) -> dict[str, object]:
        return {
            "baseline": self.baseline.public_dict(),
            "decision_basis": self.decision_basis,
            "learned": self.learned.public_dict(),
            "pair_id": self.pair_id,
            "private_binding_fields": 0,
            "private_path_fields": 0,
            "schema": "pokemon.core.paired-bounded-player-result.v1",
            "status": "complete",
            "verdict": self.verdict.value,
        }


def compare_paired_bounded_player_arms(
    *,
    pair_id: str,
    learned: PairedBoundedPlayerArm,
    baseline: PairedBoundedPlayerArm,
) -> PairedBoundedPlayerComparison:
    """Compare verified progress first and cost only when progress is equal."""

    if not isinstance(pair_id, str) or _PUBLIC_ID.fullmatch(pair_id) is None:
        raise PairedBoundedPlayerError("pair id must be path-free")
    if not isinstance(learned, PairedBoundedPlayerArm) or not isinstance(
        baseline, PairedBoundedPlayerArm
    ):
        raise TypeError("paired comparison needs two bounded-player arms")
    if learned.arm_id == baseline.arm_id:
        raise PairedBoundedPlayerError("paired authorities must be distinct")
    if (
        learned.starting_state_sha256 != baseline.starting_state_sha256
        or learned.starting_semantic_state_sha256
        != baseline.starting_semantic_state_sha256
        or learned.starting_collection != baseline.starting_collection
    ):
        raise PairedBoundedPlayerError("paired arms did not start from the same state")

    learned_progress = learned.progress
    baseline_progress = baseline.progress
    progress_relation = _dominance(
        learned_progress.progress_vector,
        baseline_progress.progress_vector,
        lower_is_better=False,
    )
    if progress_relation > 0:
        verdict = PairedBoundedPlayerVerdict.LEARNED_ADVANTAGE
        basis = "verified_progress_dominance"
    elif progress_relation < 0:
        verdict = PairedBoundedPlayerVerdict.BASELINE_ADVANTAGE
        basis = "verified_progress_dominance"
    elif learned_progress.progress_vector != baseline_progress.progress_vector:
        verdict = PairedBoundedPlayerVerdict.INCOMPARABLE
        basis = "mixed_verified_progress_tradeoff"
    else:
        cost_relation = _dominance(
            learned_progress.cost_vector,
            baseline_progress.cost_vector,
            lower_is_better=True,
        )
        if cost_relation > 0:
            verdict = PairedBoundedPlayerVerdict.LEARNED_ADVANTAGE
            basis = "equal_progress_lower_cost"
        elif cost_relation < 0:
            verdict = PairedBoundedPlayerVerdict.BASELINE_ADVANTAGE
            basis = "equal_progress_lower_cost"
        elif learned_progress.cost_vector == baseline_progress.cost_vector:
            verdict = PairedBoundedPlayerVerdict.EQUIVALENT
            basis = "equal_progress_and_cost"
        else:
            verdict = PairedBoundedPlayerVerdict.INCOMPARABLE
            basis = "equal_progress_mixed_cost_tradeoff"
    return PairedBoundedPlayerComparison(
        pair_id=pair_id,
        learned=learned,
        baseline=baseline,
        verdict=verdict,
        decision_basis=basis,
    )


def _dominance(
    left: tuple[int, ...],
    right: tuple[int, ...],
    *,
    lower_is_better: bool,
) -> int:
    if len(left) != len(right):  # pragma: no cover - internal fixed-width vectors
        raise AssertionError("paired vectors have different widths")
    left_no_worse = all(
        lvalue <= rvalue if lower_is_better else lvalue >= rvalue
        for lvalue, rvalue in zip(left, right, strict=True)
    )
    right_no_worse = all(
        rvalue <= lvalue if lower_is_better else rvalue >= lvalue
        for lvalue, rvalue in zip(left, right, strict=True)
    )
    if left_no_worse and left != right:
        return 1
    if right_no_worse and left != right:
        return -1
    return 0
