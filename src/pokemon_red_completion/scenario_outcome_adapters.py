"""Thin domain adapters for the shared bounded-outcome contract.

Each adapter keeps its existing identity-free feature projection and converts
independently verified execution evidence into a prospectively ordered outcome.
The shared layer sees no map, species, move, party-slot, or teacher identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pokemon_red_completion.battle_outcome_learning import BattleOutcomeExample
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
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
from pokemon_red_completion.strategic_navigation import (
    DestinationAvailability,
    NavigationOutcomeStatus,
    StrategicNavigationDecision,
    StrategicNavigationError,
    StrategicNavigationOutcome,
    StrategicNavigationRecord,
)
from pokemon_red_completion.strategic_navigation_dataset import (
    StrategicNavigationInferenceInput,
)
from pokemon_red_completion.strategic_navigation_model import (
    STRATEGIC_NAVIGATION_FEATURE_NAMES,
    STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID,
    strategic_navigation_feature_matrix,
)
from pokemon_red_completion.team_training import TeamTrainingProgress
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TrainingCandidate,
    TrainingCandidateSet,
)

BATTLE_TURN_OBJECTIVE = OutcomeObjective(
    objective_id="battle.turn.health-terminal-utility.v1",
    family=ScenarioFamily.BATTLE,
    criteria=(
        OutcomeCriterion(
            "battle.turn.utility",
            OutcomeDirection.MAXIMIZE,
            9,
        ),
    ),
)

NAVIGATION_ROUTE_OBJECTIVE = OutcomeObjective(
    objective_id="navigation.route.arrival-efficiency.v1",
    family=ScenarioFamily.NAVIGATION,
    criteria=(
        OutcomeCriterion("navigation.terminal-reached", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("navigation.route-progress", OutcomeDirection.MAXIMIZE, 6),
        OutcomeCriterion("navigation.request-efficiency", OutcomeDirection.MAXIMIZE, 6),
        OutcomeCriterion("navigation.replans", OutcomeDirection.MINIMIZE, 0),
        OutcomeCriterion("navigation.interruptions", OutcomeDirection.MINIMIZE, 0),
        OutcomeCriterion("navigation.movement-requests", OutcomeDirection.MINIMIZE, 0),
    ),
)

PARTY_DEVELOPMENT_OBJECTIVE = OutcomeObjective(
    objective_id="party-development.progress-efficiency.v1",
    family=ScenarioFamily.PARTY_DEVELOPMENT,
    criteria=(
        OutcomeCriterion("party.no-blackout", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.objective-progress", OutcomeDirection.MAXIMIZE, 0),
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
class NavigationOutcomeTrial:
    """A full decision/outcome binding for one cloned route execution."""

    decision: StrategicNavigationDecision
    outcome: StrategicNavigationOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.decision, StrategicNavigationDecision):
            raise ScenarioOutcomeError("navigation trial decision is invalid")
        if not isinstance(self.outcome, StrategicNavigationOutcome):
            raise ScenarioOutcomeError("navigation trial outcome is invalid")
        try:
            StrategicNavigationRecord(self.decision, self.outcome)
        except StrategicNavigationError as error:
            raise ScenarioOutcomeError(
                "navigation trial decision/outcome binding is invalid"
            ) from error

    @property
    def candidate_index(self) -> int:
        return self.decision.selected_index


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeTrial:
    """Before/after evidence for one trainee or venue counterfactual."""

    candidate: TrainingCandidate
    target_slot: int
    before_party: PartyObservation
    after_party: PartyObservation
    progress_before: TeamTrainingProgress
    progress_after: TeamTrainingProgress
    frames_executed: int
    rotations_executed: int = 0
    evolution_completed: bool = False
    censored: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, TrainingCandidate):
            raise ScenarioOutcomeError("party outcome candidate is invalid")
        if type(self.target_slot) is not int or self.target_slot < 1:  # noqa: E721
            raise ScenarioOutcomeError("party outcome target slot is invalid")
        if not isinstance(self.before_party, PartyObservation) or not isinstance(
            self.after_party, PartyObservation
        ):
            raise ScenarioOutcomeError("party outcome needs typed before/after observations")
        if not isinstance(self.progress_before, TeamTrainingProgress) or not isinstance(
            self.progress_after, TeamTrainingProgress
        ):
            raise ScenarioOutcomeError("party outcome needs typed progress counters")
        if type(self.frames_executed) is not int or self.frames_executed < 0:  # noqa: E721
            raise ScenarioOutcomeError("party outcome frame count is invalid")
        if type(self.rotations_executed) is not int or self.rotations_executed < 0:  # noqa: E721
            raise ScenarioOutcomeError("party outcome rotation count is invalid")
        if not isinstance(self.evolution_completed, bool) or not isinstance(
            self.censored, bool
        ):
            raise ScenarioOutcomeError("party outcome flags must be boolean")
        for name in (
            "battles_completed",
            "steps_taken",
            "healing_trips",
            "faints",
        ):
            if getattr(self.progress_after, name) < getattr(self.progress_before, name):
                raise ScenarioOutcomeError("party outcome progress counters moved backwards")
        if not self.censored and self.frames_executed < 1:
            raise ScenarioOutcomeError("a measured party outcome needs positive execution time")
        if self.before_party.member_in_slot(self.target_slot) is None or (
            self.after_party.member_in_slot(self.target_slot) is None
        ):
            raise ScenarioOutcomeError("party outcome target is absent from before/after evidence")

    @property
    def candidate_index(self) -> int:
        return self.candidate.candidate_index


_Trial = TypeVar(
    "_Trial",
    NavigationOutcomeTrial,
    PartyDevelopmentOutcomeTrial,
)


def adapt_battle_outcome_example(
    example: BattleOutcomeExample,
    *,
    scenario_id: str,
) -> ScenarioOutcomeExample:
    """Project the proven Red battle counterfactual into the shared boundary."""

    if not isinstance(example, BattleOutcomeExample):
        raise TypeError("example must be BattleOutcomeExample")
    candidates = tuple(
        OutcomeCandidate(index, tuple(vector), bool(example.usable_mask[index]))
        for index, vector in enumerate(example.features.candidate_vectors)
    )
    outcomes = tuple(
        None
        if outcome is None
        else CandidateOutcome(
            status=OutcomeEvidenceStatus.MEASURED,
            criterion_values=(outcome.utility,),
            actions_executed=outcome.actions_executed,
            frames_executed=outcome.frames_executed,
            evidence_sha256=canonical_sha256(outcome.public_dict()),
        )
        for outcome in example.outcomes
    )
    return ScenarioOutcomeExample(
        scenario_id=scenario_id,
        root_lineage_id=example.root_lineage_id,
        initial_state_sha256=example.initial_state_sha256,
        partition=example.partition,
        objective=BATTLE_TURN_OBJECTIVE,
        feature_schema_id=example.features.schema_id,
        feature_names=example.features.feature_names,
        candidates=candidates,
        outcomes=outcomes,
    )


def adapt_navigation_outcomes(
    inference: StrategicNavigationInferenceInput,
    trials: tuple[NavigationOutcomeTrial, ...],
    *,
    scenario_id: str,
    root_lineage_id: str,
    initial_state_sha256: str,
    partition: ScenarioPartition,
) -> ScenarioOutcomeExample:
    """Join cloned route results to the existing destination feature projection."""

    if not isinstance(inference, StrategicNavigationInferenceInput):
        raise TypeError("inference must be StrategicNavigationInferenceInput")
    if not isinstance(trials, tuple) or any(
        not isinstance(item, NavigationOutcomeTrial) for item in trials
    ):
        raise ScenarioOutcomeError("navigation trials must be an immutable typed tuple")
    by_candidate = _unique_trials(trials, candidate_count=len(inference.candidates))
    decision_ids = {trial.decision.decision_id for trial in trials}
    if len(decision_ids) > 1:
        raise ScenarioOutcomeError(
            "navigation counterfactuals do not share one decision identity"
        )
    expected_partition = (
        "validation"
        if partition is ScenarioPartition.DEVELOPMENT
        else partition.value
    )
    if any(
        trial.decision.root_lineage_id != root_lineage_id
        or trial.decision.partition != expected_partition
        or StrategicNavigationInferenceInput(
            trial.decision.policy_input()
        ).ordered_policy_input_sha256
        != inference.ordered_policy_input_sha256
        for trial in trials
    ):
        raise ScenarioOutcomeError(
            "navigation trial provenance differs from its shared policy question"
        )
    matrix = strategic_navigation_feature_matrix(inference)
    candidates = tuple(
        OutcomeCandidate(
            candidate_index=index,
            features=tuple(float(value) for value in matrix[index]),
            available=(
                row.get("availability") == DestinationAvailability.AVAILABLE.value
            ),
        )
        for index, row in enumerate(inference.candidates)
    )
    outcomes: list[CandidateOutcome | None] = []
    for index, (candidate, row) in enumerate(
        zip(candidates, inference.candidates, strict=True)
    ):
        trial = by_candidate.get(index)
        if not candidate.available:
            if trial is not None:
                raise ScenarioOutcomeError(
                    "an unavailable navigation candidate cannot have an execution trial"
                )
            outcomes.append(None)
            continue
        if trial is None:
            outcomes.append(None)
            continue
        outcome = trial.outcome
        evidence_sha256 = canonical_sha256(outcome.public_dict())
        actions = outcome.movement_requests + outcome.wait_actions
        if outcome.status is NavigationOutcomeStatus.INTERRUPTED:
            outcomes.append(
                CandidateOutcome(
                    status=OutcomeEvidenceStatus.CENSORED,
                    actions_executed=actions,
                    evidence_sha256=evidence_sha256,
                )
            )
            continue
        route_steps = row.get("route_steps")
        if type(route_steps) is not int or route_steps < 0:  # noqa: E721
            raise ScenarioOutcomeError("navigation candidate route length is invalid")
        progress = (
            1.0
            if outcome.terminal_reached
            else min(1.0, outcome.acknowledged_steps / max(1, route_steps))
        )
        request_efficiency = (
            1.0
            if outcome.terminal_reached and outcome.movement_requests == 0
            else outcome.acknowledged_steps / max(1, outcome.movement_requests)
        )
        outcomes.append(
            CandidateOutcome(
                status=OutcomeEvidenceStatus.MEASURED,
                criterion_values=(
                    float(outcome.terminal_reached),
                    progress,
                    request_efficiency,
                    float(len(outcome.replans)),
                    float(len(outcome.interruptions)),
                    float(outcome.movement_requests),
                ),
                actions_executed=actions,
                evidence_sha256=evidence_sha256,
            )
        )
    return ScenarioOutcomeExample(
        scenario_id=scenario_id,
        root_lineage_id=root_lineage_id,
        initial_state_sha256=initial_state_sha256,
        partition=partition,
        objective=NAVIGATION_ROUTE_OBJECTIVE,
        feature_schema_id=STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID,
        feature_names=STRATEGIC_NAVIGATION_FEATURE_NAMES,
        candidates=candidates,
        outcomes=tuple(outcomes),
    )


def adapt_party_development_outcomes(
    candidate_set: TrainingCandidateSet,
    trials: tuple[PartyDevelopmentOutcomeTrial, ...],
    *,
    scenario_id: str,
    root_lineage_id: str,
    initial_state_sha256: str,
    partition: ScenarioPartition,
) -> ScenarioOutcomeExample:
    """Join bounded before/after training evidence to trainee or venue candidates."""

    if not isinstance(candidate_set, TrainingCandidateSet):
        raise TypeError("candidate_set must be TrainingCandidateSet")
    if not isinstance(trials, tuple) or any(
        not isinstance(item, PartyDevelopmentOutcomeTrial) for item in trials
    ):
        raise ScenarioOutcomeError("party trials must be an immutable typed tuple")
    by_candidate = _unique_trials(trials, candidate_count=len(candidate_set.candidates))
    if any(
        trial.candidate != candidate_set.candidates[trial.candidate_index]
        for trial in trials
    ):
        raise ScenarioOutcomeError(
            "party trial candidate differs from its identity-free candidate set"
        )
    if trials:
        first = trials[0]
        if any(
            trial.before_party != first.before_party
            or trial.progress_before != first.progress_before
            for trial in trials[1:]
        ):
            raise ScenarioOutcomeError(
                "party counterfactuals do not share one starting observation"
            )
        target_slots = tuple(trial.target_slot for trial in trials)
        if candidate_set.kind.value == "venue" and len(set(target_slots)) != 1:
            raise ScenarioOutcomeError(
                "venue counterfactuals do not share one trainee binding"
            )
        if candidate_set.kind.value == "trainee" and len(target_slots) != len(
            set(target_slots)
        ):
            raise ScenarioOutcomeError(
                "trainee counterfactuals repeat a target-party binding"
            )
    candidates = tuple(
        OutcomeCandidate(
            candidate_index=item.candidate_index,
            features=item.features,
            available=True,
        )
        for item in candidate_set.candidates
    )
    outcomes: list[CandidateOutcome | None] = []
    for index in range(len(candidates)):
        trial = by_candidate.get(index)
        if trial is None:
            outcomes.append(None)
            continue
        evidence = _party_trial_evidence(trial)
        if trial.censored:
            outcomes.append(
                CandidateOutcome(
                    status=OutcomeEvidenceStatus.CENSORED,
                    actions_executed=_party_semantic_actions(trial),
                    frames_executed=trial.frames_executed,
                    evidence_sha256=canonical_sha256(evidence),
                )
            )
            continue
        total_experience_gained = _experience_gained(
            trial.before_party,
            trial.after_party,
        )
        target_experience_gained = _target_experience_gained(trial)
        battles = (
            trial.progress_after.battles_completed
            - trial.progress_before.battles_completed
        )
        center_visits = (
            trial.progress_after.healing_trips
            - trial.progress_before.healing_trips
        )
        faints = trial.progress_after.faints - trial.progress_before.faints
        objective_progress = target_experience_gained > 0 or trial.evolution_completed
        outcomes.append(
            CandidateOutcome(
                status=OutcomeEvidenceStatus.MEASURED,
                criterion_values=(
                    float(not trial.after_party.is_wiped_out),
                    float(objective_progress),
                    float(trial.evolution_completed),
                    1_000.0 * target_experience_gained / trial.frames_executed,
                    float(target_experience_gained),
                    1_000.0 * total_experience_gained / trial.frames_executed,
                    battles / max(1, center_visits),
                    float(faints),
                    float(trial.frames_executed),
                ),
                actions_executed=_party_semantic_actions(trial),
                frames_executed=trial.frames_executed,
                evidence_sha256=canonical_sha256(evidence),
            )
        )
    feature_schema_id = candidate_set.candidates[0].feature_schema_id
    return ScenarioOutcomeExample(
        scenario_id=scenario_id,
        root_lineage_id=root_lineage_id,
        initial_state_sha256=initial_state_sha256,
        partition=partition,
        objective=PARTY_DEVELOPMENT_OBJECTIVE,
        feature_schema_id=feature_schema_id,
        feature_names=TRAINING_CANDIDATE_FEATURE_NAMES,
        candidates=candidates,
        outcomes=tuple(outcomes),
    )


def _unique_trials(
    trials: tuple[_Trial, ...],
    *,
    candidate_count: int,
) -> dict[int, _Trial]:
    result: dict[int, _Trial] = {}
    for trial in trials:
        if trial.candidate_index not in range(candidate_count):
            raise ScenarioOutcomeError("outcome trial candidate index is outside its menu")
        if trial.candidate_index in result:
            raise ScenarioOutcomeError("outcome trials repeat a candidate")
        result[trial.candidate_index] = trial
    return result


def _experience_gained(before: PartyObservation, after: PartyObservation) -> int:
    if before.size != after.size:
        raise ScenarioOutcomeError("party size changed inside a development comparison")
    gained = _total_experience(after) - _total_experience(before)
    if gained < 0:
        raise ScenarioOutcomeError("party experience moved backwards")
    return gained


def _total_experience(party: PartyObservation) -> int:
    total = 0
    for member in party.members:
        if member.experience is None:
            raise ScenarioOutcomeError(
                "party development outcomes require exact experience observations"
            )
        total += member.experience
    return total


def _target_experience_gained(trial: PartyDevelopmentOutcomeTrial) -> int:
    before = trial.before_party.member_in_slot(trial.target_slot)
    after = trial.after_party.member_in_slot(trial.target_slot)
    if before is None or after is None:  # pragma: no cover - dataclass invariant
        raise AssertionError("party outcome target binding disappeared")
    if before.experience is None or after.experience is None:
        raise ScenarioOutcomeError(
            "party development outcomes require exact target experience"
        )
    gained = after.experience - before.experience
    if gained < 0:
        raise ScenarioOutcomeError("target-party experience moved backwards")
    return gained


def _party_semantic_actions(trial: PartyDevelopmentOutcomeTrial) -> int:
    return (
        trial.progress_after.battles_completed
        - trial.progress_before.battles_completed
        + trial.progress_after.healing_trips
        - trial.progress_before.healing_trips
        + trial.rotations_executed
    )


def _party_trial_evidence(trial: PartyDevelopmentOutcomeTrial) -> dict[str, object]:
    return {
        "schema": "pokemon.core.party-development-outcome-evidence.v1",
        "candidate_sha256": canonical_sha256(trial.candidate.public_dict()),
        "target_binding_sha256": canonical_sha256(
            {
                "before_slot": trial.target_slot,
                "before_member": _party_member_evidence(
                    trial.before_party.member_in_slot(trial.target_slot)
                ),
                "after_member": _party_member_evidence(
                    trial.after_party.member_in_slot(trial.target_slot)
                ),
            }
        ),
        "before_experience": [member.experience for member in trial.before_party.members],
        "after_experience": [member.experience for member in trial.after_party.members],
        "before_levels": list(trial.before_party.levels),
        "after_levels": list(trial.after_party.levels),
        "before_progress": {
            "battles": trial.progress_before.battles_completed,
            "heals": trial.progress_before.healing_trips,
            "faints": trial.progress_before.faints,
        },
        "after_progress": {
            "battles": trial.progress_after.battles_completed,
            "heals": trial.progress_after.healing_trips,
            "faints": trial.progress_after.faints,
        },
        "frames_executed": trial.frames_executed,
        "rotations_executed": trial.rotations_executed,
        "evolution_completed": trial.evolution_completed,
        "censored": trial.censored,
    }


def _party_member_evidence(
    member: PartyMemberObservation | None,
) -> dict[str, object]:
    if member is None:
        raise ScenarioOutcomeError("party outcome target evidence is absent")
    return {
        "slot": member.slot,
        "species_id": member.species_id,
        "level": member.level,
        "hp": member.hp,
        "max_hp": member.max_hp,
        "status": member.status.value,
        "experience": member.experience,
    }


__all__ = [
    "BATTLE_TURN_OBJECTIVE",
    "NAVIGATION_ROUTE_OBJECTIVE",
    "PARTY_DEVELOPMENT_OBJECTIVE",
    "NavigationOutcomeTrial",
    "PartyDevelopmentOutcomeTrial",
    "adapt_battle_outcome_example",
    "adapt_navigation_outcomes",
    "adapt_party_development_outcomes",
]
