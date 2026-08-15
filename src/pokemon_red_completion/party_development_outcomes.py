"""Completion-aware outcome labels for party-development counterfactuals.

This is the v2 companion to the historical progress/efficiency adapter.  It
retains safety and efficiency, but it also measures whether a choice advances
the declared balance, evolution, living-collection, or role-coverage goal
without sacrificing completion state elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentCatalogError,
    PartyDevelopmentProspectiveBinding,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    PartyDevelopmentCandidate,
    PartyDevelopmentCandidateSet,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioFamily, ScenarioPartition
from pokemon_red_completion.scenario_outcomes import (
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeCriterion,
    OutcomeDirection,
    OutcomeEvidenceStatus,
    OutcomeObjective,
    ScenarioOutcomeError,
    ScenarioOutcomeExample,
)
from pokemon_red_completion.team_training import TeamTrainingProgress
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE = OutcomeObjective(
    objective_id="party-development.completion-progress-efficiency.v2",
    family=ScenarioFamily.PARTY_DEVELOPMENT,
    criteria=(
        OutcomeCriterion("party.no-blackout", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.completion-no-regression", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.primary-goal-progress", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.living-targets-gained", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.registrations-gained", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.roles-gained", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.evolution-steps-reduced", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.level-deficit-reduced", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.evolution-completed", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion(
            "party.target-experience-per-1000-frames",
            OutcomeDirection.MAXIMIZE,
            6,
        ),
        OutcomeCriterion("party.target-experience-gained", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion(
            "party.total-experience-per-1000-frames",
            OutcomeDirection.MAXIMIZE,
            6,
        ),
        OutcomeCriterion("party.battles-per-center-visit", OutcomeDirection.MAXIMIZE, 6),
        OutcomeCriterion("party.faints", OutcomeDirection.MINIMIZE, 0),
        OutcomeCriterion("party.frames", OutcomeDirection.MINIMIZE, 0),
    ),
)


@dataclass(frozen=True, slots=True)
class PartyCompletionSnapshot:
    """Title-neutral completion counters at one bounded execution boundary."""

    registered_target_count: int
    registration_target_total: int
    living_target_count: int
    living_target_total: int
    role_coverage_count: int
    role_target_total: int
    evolution_steps_remaining: int
    level_floor_deficit: int

    def __post_init__(self) -> None:
        for count_name, total_name in (
            ("registered_target_count", "registration_target_total"),
            ("living_target_count", "living_target_total"),
            ("role_coverage_count", "role_target_total"),
        ):
            count = getattr(self, count_name)
            total = getattr(self, total_name)
            if (
                type(count) is not int  # noqa: E721
                or type(total) is not int  # noqa: E721
                or total < 1
                or not 0 <= count <= total
            ):
                raise ScenarioOutcomeError(
                    f"party completion {count_name.replace('_', ' ')} is invalid"
                )
        for name in ("evolution_steps_remaining", "level_floor_deficit"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise ScenarioOutcomeError(f"party completion {name.replace('_', ' ')} is invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "registered_target_count": self.registered_target_count,
            "registration_target_total": self.registration_target_total,
            "living_target_count": self.living_target_count,
            "living_target_total": self.living_target_total,
            "role_coverage_count": self.role_coverage_count,
            "role_target_total": self.role_target_total,
            "evolution_steps_remaining": self.evolution_steps_remaining,
            "level_floor_deficit": self.level_floor_deficit,
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeTrialV2:
    """Before/after completion evidence for one v2 candidate execution."""

    candidate: PartyDevelopmentCandidate
    target_slot: int
    before_party: PartyObservation
    after_party: PartyObservation
    progress_before: TeamTrainingProgress
    progress_after: TeamTrainingProgress
    completion_before: PartyCompletionSnapshot
    completion_after: PartyCompletionSnapshot
    frames_executed: int
    rotations_executed: int = 0
    evolution_completed: bool = False
    censored: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, PartyDevelopmentCandidate):
            raise ScenarioOutcomeError("v2 party outcome candidate is invalid")
        if type(self.target_slot) is not int or self.target_slot < 1:  # noqa: E721
            raise ScenarioOutcomeError("v2 party outcome target slot is invalid")
        if not isinstance(self.before_party, PartyObservation) or not isinstance(
            self.after_party, PartyObservation
        ):
            raise ScenarioOutcomeError("v2 party outcome needs typed before/after observations")
        if not isinstance(self.progress_before, TeamTrainingProgress) or not isinstance(
            self.progress_after, TeamTrainingProgress
        ):
            raise ScenarioOutcomeError("v2 party outcome needs typed progress counters")
        if not isinstance(self.completion_before, PartyCompletionSnapshot) or not isinstance(
            self.completion_after, PartyCompletionSnapshot
        ):
            raise ScenarioOutcomeError("v2 party outcome needs completion snapshots")
        _require_same_completion_targets(self.completion_before, self.completion_after)
        if type(self.frames_executed) is not int or self.frames_executed < 0:  # noqa: E721
            raise ScenarioOutcomeError("v2 party outcome frame count is invalid")
        if type(self.rotations_executed) is not int or self.rotations_executed < 0:  # noqa: E721
            raise ScenarioOutcomeError("v2 party outcome rotation count is invalid")
        if not isinstance(self.evolution_completed, bool) or not isinstance(self.censored, bool):
            raise ScenarioOutcomeError("v2 party outcome flags must be boolean")
        for name in ("battles_completed", "steps_taken", "healing_trips", "faints"):
            if getattr(self.progress_after, name) < getattr(self.progress_before, name):
                raise ScenarioOutcomeError("v2 party outcome progress moved backwards")
        if not self.censored and self.frames_executed < 1:
            raise ScenarioOutcomeError("a measured v2 party outcome needs positive execution time")
        if self.before_party.member_in_slot(self.target_slot) is None or (
            self.after_party.member_in_slot(self.target_slot) is None
        ):
            raise ScenarioOutcomeError(
                "v2 party outcome target is absent from before/after evidence"
            )

    @property
    def candidate_index(self) -> int:
        return self.candidate.candidate_index


def adapt_party_development_outcomes_v2(
    candidate_set: PartyDevelopmentCandidateSet,
    trials: tuple[PartyDevelopmentOutcomeTrialV2, ...],
    *,
    scenario_id: str,
    root_lineage_id: str,
    initial_state_sha256: str,
    partition: ScenarioPartition,
    prospective_binding: PartyDevelopmentProspectiveBinding,
) -> ScenarioOutcomeExample:
    """Join cloned v2 candidate executions to completion-aware preferences."""

    if not isinstance(candidate_set, PartyDevelopmentCandidateSet):
        raise TypeError("candidate_set must be a PartyDevelopmentCandidateSet")
    if not isinstance(prospective_binding, PartyDevelopmentProspectiveBinding):
        raise TypeError("prospective_binding must be a PartyDevelopmentProspectiveBinding")
    if len(prospective_binding.candidate_available) != len(candidate_set.candidates):
        raise PartyDevelopmentCatalogError(
            "party-development outcome differs from its prospective candidate menu"
        )
    if not isinstance(trials, tuple) or any(
        not isinstance(item, PartyDevelopmentOutcomeTrialV2) for item in trials
    ):
        raise ScenarioOutcomeError("v2 party trials must be an immutable typed tuple")
    by_candidate: dict[int, PartyDevelopmentOutcomeTrialV2] = {}
    for bound_trial in trials:
        if bound_trial.candidate_index not in range(len(candidate_set.candidates)):
            raise ScenarioOutcomeError("v2 party trial candidate is outside its menu")
        if bound_trial.candidate_index in by_candidate:
            raise ScenarioOutcomeError("v2 party trials repeat a candidate")
        if bound_trial.candidate != candidate_set.candidates[bound_trial.candidate_index]:
            raise ScenarioOutcomeError(
                "v2 party trial differs from its identity-free candidate set"
            )
        by_candidate[bound_trial.candidate_index] = bound_trial
    _require_shared_start(candidate_set, trials)

    candidates = tuple(
        OutcomeCandidate(
            item.candidate_index,
            item.features,
            prospective_binding.candidate_available[item.candidate_index],
        )
        for item in candidate_set.candidates
    )
    outcomes: list[CandidateOutcome | None] = []
    for index in range(len(candidates)):
        trial = by_candidate.get(index)
        if trial is None:
            outcomes.append(None)
            continue
        evidence_sha256 = canonical_sha256(_trial_evidence(trial))
        if trial.censored:
            outcomes.append(
                CandidateOutcome(
                    status=OutcomeEvidenceStatus.CENSORED,
                    actions_executed=_semantic_actions(trial),
                    frames_executed=trial.frames_executed,
                    evidence_sha256=evidence_sha256,
                )
            )
            continue
        outcomes.append(
            CandidateOutcome(
                status=OutcomeEvidenceStatus.MEASURED,
                criterion_values=_criterion_values(candidate_set.goal, trial),
                actions_executed=_semantic_actions(trial),
                frames_executed=trial.frames_executed,
                evidence_sha256=evidence_sha256,
            )
        )
    example = ScenarioOutcomeExample(
        scenario_id=scenario_id,
        root_lineage_id=root_lineage_id,
        initial_state_sha256=initial_state_sha256,
        partition=partition,
        objective=PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
        feature_schema_id=PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
        feature_names=PARTY_DEVELOPMENT_FEATURE_NAMES,
        candidates=candidates,
        outcomes=tuple(outcomes),
        prospective_binding_sha256=prospective_binding.binding_sha256,
    )
    prospective_binding.require_matches(example)
    return example


def _require_shared_start(
    candidate_set: PartyDevelopmentCandidateSet,
    trials: tuple[PartyDevelopmentOutcomeTrialV2, ...],
) -> None:
    if not trials:
        return
    first = trials[0]
    if any(
        trial.before_party != first.before_party
        or trial.progress_before != first.progress_before
        or trial.completion_before != first.completion_before
        for trial in trials[1:]
    ):
        raise ScenarioOutcomeError("v2 party counterfactuals do not share one starting observation")
    target_slots = tuple(trial.target_slot for trial in trials)
    if candidate_set.kind is TrainingChoiceKind.VENUE and len(set(target_slots)) != 1:
        raise ScenarioOutcomeError("v2 venue counterfactuals do not share one trainee binding")
    if candidate_set.kind is TrainingChoiceKind.TRAINEE and len(target_slots) != len(
        set(target_slots)
    ):
        raise ScenarioOutcomeError("v2 trainee counterfactuals repeat a target-party binding")


def _criterion_values(
    goal: PartyDevelopmentGoal,
    trial: PartyDevelopmentOutcomeTrialV2,
) -> tuple[float, ...]:
    before = trial.completion_before
    after = trial.completion_after
    registration_gain = after.registered_target_count - before.registered_target_count
    living_gain = after.living_target_count - before.living_target_count
    role_gain = after.role_coverage_count - before.role_coverage_count
    evolution_reduction = before.evolution_steps_remaining - after.evolution_steps_remaining
    level_reduction = before.level_floor_deficit - after.level_floor_deficit
    no_regression = (
        registration_gain >= 0
        and living_gain >= 0
        and role_gain >= 0
        and evolution_reduction >= 0
        and level_reduction >= 0
    )
    primary_progress = {
        PartyDevelopmentGoal.BALANCE: max(0, level_reduction),
        PartyDevelopmentGoal.EVOLUTION: max(0, evolution_reduction),
        PartyDevelopmentGoal.COLLECTION: max(0, registration_gain) + max(0, living_gain),
        PartyDevelopmentGoal.ROLE_COVERAGE: max(0, role_gain),
    }[goal]
    target_experience = _target_experience_gained(trial)
    total_experience = _experience_gained(trial.before_party, trial.after_party)
    battles = trial.progress_after.battles_completed - trial.progress_before.battles_completed
    center_visits = trial.progress_after.healing_trips - trial.progress_before.healing_trips
    faints = trial.progress_after.faints - trial.progress_before.faints
    return (
        float(not trial.after_party.is_wiped_out),
        float(no_regression),
        float(primary_progress),
        float(living_gain),
        float(registration_gain),
        float(role_gain),
        float(evolution_reduction),
        float(level_reduction),
        float(trial.evolution_completed),
        1_000.0 * target_experience / trial.frames_executed,
        float(target_experience),
        1_000.0 * total_experience / trial.frames_executed,
        battles / max(1, center_visits),
        float(faints),
        float(trial.frames_executed),
    )


def _experience_gained(before: PartyObservation, after: PartyObservation) -> int:
    if before.size != after.size:
        raise ScenarioOutcomeError("party size changed inside a v2 outcome")
    gained = _total_experience(after) - _total_experience(before)
    if gained < 0:
        raise ScenarioOutcomeError("party experience moved backwards in a v2 outcome")
    return gained


def _total_experience(party: PartyObservation) -> int:
    total = 0
    for member in party.members:
        if member.experience is None:
            raise ScenarioOutcomeError("v2 party outcomes require exact experience")
        total += member.experience
    return total


def _target_experience_gained(trial: PartyDevelopmentOutcomeTrialV2) -> int:
    before = trial.before_party.member_in_slot(trial.target_slot)
    after = trial.after_party.member_in_slot(trial.target_slot)
    if before is None or after is None:  # pragma: no cover - dataclass invariant
        raise AssertionError("v2 party target binding disappeared")
    if before.experience is None or after.experience is None:
        raise ScenarioOutcomeError("v2 party outcomes require target experience")
    gained = after.experience - before.experience
    if gained < 0:
        raise ScenarioOutcomeError("v2 target experience moved backwards")
    return gained


def _semantic_actions(trial: PartyDevelopmentOutcomeTrialV2) -> int:
    return (
        trial.progress_after.battles_completed
        - trial.progress_before.battles_completed
        + trial.progress_after.healing_trips
        - trial.progress_before.healing_trips
        + trial.rotations_executed
    )


def _trial_evidence(trial: PartyDevelopmentOutcomeTrialV2) -> dict[str, object]:
    return {
        "schema": "pokemon.core.party-development-completion-outcome-evidence.v2",
        "candidate_sha256": canonical_sha256(trial.candidate.public_dict()),
        "target_binding_sha256": canonical_sha256(
            {
                "before_slot": trial.target_slot,
                "before_member": _member_evidence(
                    trial.before_party.member_in_slot(trial.target_slot)
                ),
                "after_member": _member_evidence(
                    trial.after_party.member_in_slot(trial.target_slot)
                ),
            }
        ),
        "completion_before": trial.completion_before.public_dict(),
        "completion_after": trial.completion_after.public_dict(),
        "before_experience": [member.experience for member in trial.before_party.members],
        "after_experience": [member.experience for member in trial.after_party.members],
        "before_levels": list(trial.before_party.levels),
        "after_levels": list(trial.after_party.levels),
        "before_progress": _progress_evidence(trial.progress_before),
        "after_progress": _progress_evidence(trial.progress_after),
        "frames_executed": trial.frames_executed,
        "rotations_executed": trial.rotations_executed,
        "evolution_completed": trial.evolution_completed,
        "censored": trial.censored,
    }


def _member_evidence(member: PartyMemberObservation | None) -> dict[str, object]:
    if member is None:
        raise ScenarioOutcomeError("v2 party target evidence is absent")
    return {
        "slot": member.slot,
        "species_id": member.species_id,
        "level": member.level,
        "hp": member.hp,
        "max_hp": member.max_hp,
        "status": member.status.value,
        "experience": member.experience,
    }


def _progress_evidence(progress: TeamTrainingProgress) -> dict[str, object]:
    return {
        "battles": progress.battles_completed,
        "heals": progress.healing_trips,
        "faints": progress.faints,
    }


def _require_same_completion_targets(
    before: PartyCompletionSnapshot,
    after: PartyCompletionSnapshot,
) -> None:
    if (
        before.registration_target_total != after.registration_target_total
        or before.living_target_total != after.living_target_total
        or before.role_target_total != after.role_target_total
    ):
        raise ScenarioOutcomeError("v2 party completion target changed during execution")


__all__ = [
    "PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE",
    "PartyCompletionSnapshot",
    "PartyDevelopmentOutcomeTrialV2",
    "adapt_party_development_outcomes_v2",
]
