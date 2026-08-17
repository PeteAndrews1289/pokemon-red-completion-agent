"""Durable terminal records and dataset assembly for party counterfactuals."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.party_development_frozen_catalog import (
    PartyDevelopmentFrozenCatalog,
)
from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeCampaignPlan,
    PartyDevelopmentOutcomeTrialAssignment,
    PartyDevelopmentOutcomeTrialClaim,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_outcomes import (
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeEvidenceStatus,
    ScenarioOutcomeExample,
)

PARTY_DEVELOPMENT_OUTCOME_TRIAL_RESULT_SCHEMA = (
    "pokemon.red.party-development-outcome-trial-result.v1"
)
PARTY_DEVELOPMENT_OUTCOME_TRIAL_TERMINAL_SCHEMA = (
    "pokemon.red.party-development-outcome-trial-terminal.v1"
)
PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA = (
    "pokemon.red.party-development-outcome-private-evidence.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_REASON = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


class PartyDevelopmentOutcomeResultError(ValueError):
    """Raised when terminal evidence cannot preserve the one-shot campaign."""


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeTrialResult:
    """One measured, invalid, or recovered-censored campaign assignment."""

    campaign_plan_sha256: str
    trial_id: str
    assignment_sha256: str
    claim_sha256: str
    candidate_index: int
    status: OutcomeEvidenceStatus
    criterion_values: tuple[float, ...]
    semantic_actions: int | None
    controller_actions: int | None
    frames_executed: int | None
    battles_completed: int | None
    encounter_steps: int | None
    healing_trips: int | None
    rotations_executed: int | None
    faints: int | None
    evolution_completed: bool | None
    evidence_sha256: str
    failure_code: str | None
    result_sha256: str

    def __post_init__(self) -> None:
        for digest_value, subject in (
            (self.campaign_plan_sha256, "campaign plan"),
            (self.assignment_sha256, "assignment"),
            (self.claim_sha256, "claim"),
            (self.evidence_sha256, "evidence"),
            (self.result_sha256, "result"),
        ):
            _require_digest(digest_value, subject=subject)
        if (
            not isinstance(self.trial_id, str)
            or type(self.candidate_index) is not int  # noqa: E721
            or self.candidate_index < 0
            or not isinstance(self.status, OutcomeEvidenceStatus)
            or not isinstance(self.criterion_values, tuple)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in self.criterion_values
            )
        ):
            raise PartyDevelopmentOutcomeResultError(
                "party-development outcome result identity or values are invalid"
            )
        for metric_value, subject in (
            (self.semantic_actions, "semantic actions"),
            (self.controller_actions, "controller actions"),
            (self.frames_executed, "frames"),
            (self.battles_completed, "battles"),
            (self.encounter_steps, "encounter steps"),
            (self.healing_trips, "healing trips"),
            (self.rotations_executed, "rotations"),
            (self.faints, "faints"),
        ):
            if metric_value is not None and (  # noqa: E721
                type(metric_value) is not int or metric_value < 0
            ):
                raise PartyDevelopmentOutcomeResultError(
                    f"party-development outcome {subject} are invalid"
                )
        if self.evolution_completed is not None and not isinstance(
            self.evolution_completed, bool
        ):
            raise PartyDevelopmentOutcomeResultError(
                "party-development outcome evolution flag is invalid"
            )
        if self.failure_code is not None and (
            not isinstance(self.failure_code, str)
            or _SAFE_REASON.fullmatch(self.failure_code) is None
        ):
            raise PartyDevelopmentOutcomeResultError(
                "party-development outcome failure code is invalid"
            )
        if self.status is OutcomeEvidenceStatus.MEASURED:
            if (
                len(self.criterion_values)
                != len(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.criteria)
                or any(
                    value is None
                    for value in (
                        self.semantic_actions,
                        self.controller_actions,
                        self.frames_executed,
                        self.battles_completed,
                        self.encounter_steps,
                        self.healing_trips,
                        self.rotations_executed,
                        self.faints,
                        self.evolution_completed,
                    )
                )
                or self.failure_code is not None
            ):
                raise PartyDevelopmentOutcomeResultError(
                    "measured party-development result lacks exact terminal counters"
                )
        elif (
            self.criterion_values
            or self.failure_code is None
            or any(
                value is not None
                for value in (
                    self.semantic_actions,
                    self.controller_actions,
                    self.frames_executed,
                    self.battles_completed,
                    self.encounter_steps,
                    self.healing_trips,
                    self.rotations_executed,
                    self.faints,
                    self.evolution_completed,
                )
            )
        ):
            raise PartyDevelopmentOutcomeResultError(
                "unmeasured party-development result has measurements or no reason"
            )
        if self.result_sha256 != canonical_sha256(self._document()):
            raise PartyDevelopmentOutcomeResultError(
                "party-development outcome result digest differs"
            )

    @classmethod
    def build(
        cls,
        plan: PartyDevelopmentOutcomeCampaignPlan,
        assignment: PartyDevelopmentOutcomeTrialAssignment,
        claim: PartyDevelopmentOutcomeTrialClaim,
        *,
        status: OutcomeEvidenceStatus,
        evidence_sha256: str,
        criterion_values: tuple[float, ...] = (),
        semantic_actions: int | None = None,
        controller_actions: int | None = None,
        frames_executed: int | None = None,
        battles_completed: int | None = None,
        encounter_steps: int | None = None,
        healing_trips: int | None = None,
        rotations_executed: int | None = None,
        faints: int | None = None,
        evolution_completed: bool | None = None,
        failure_code: str | None = None,
    ) -> PartyDevelopmentOutcomeTrialResult:
        _require_plan_assignment_claim(plan, assignment, claim)
        document = _result_document(
            campaign_plan_sha256=plan.plan_sha256,
            trial_id=assignment.trial_id,
            assignment_sha256=assignment.assignment_sha256,
            claim_sha256=claim.claim_sha256,
            candidate_index=assignment.candidate_index,
            status=status,
            criterion_values=criterion_values,
            semantic_actions=semantic_actions,
            controller_actions=controller_actions,
            frames_executed=frames_executed,
            battles_completed=battles_completed,
            encounter_steps=encounter_steps,
            healing_trips=healing_trips,
            rotations_executed=rotations_executed,
            faints=faints,
            evolution_completed=evolution_completed,
            evidence_sha256=evidence_sha256,
            failure_code=failure_code,
        )
        result = cls(
            campaign_plan_sha256=plan.plan_sha256,
            trial_id=assignment.trial_id,
            assignment_sha256=assignment.assignment_sha256,
            claim_sha256=claim.claim_sha256,
            candidate_index=assignment.candidate_index,
            status=status,
            criterion_values=criterion_values,
            semantic_actions=semantic_actions,
            controller_actions=controller_actions,
            frames_executed=frames_executed,
            battles_completed=battles_completed,
            encounter_steps=encounter_steps,
            healing_trips=healing_trips,
            rotations_executed=rotations_executed,
            faints=faints,
            evolution_completed=evolution_completed,
            evidence_sha256=evidence_sha256,
            failure_code=failure_code,
            result_sha256=canonical_sha256(document),
        )
        result.require_within_plan(plan, assignment)
        return result

    def _document(self) -> dict[str, object]:
        return _result_document(
            campaign_plan_sha256=self.campaign_plan_sha256,
            trial_id=self.trial_id,
            assignment_sha256=self.assignment_sha256,
            claim_sha256=self.claim_sha256,
            candidate_index=self.candidate_index,
            status=self.status,
            criterion_values=self.criterion_values,
            semantic_actions=self.semantic_actions,
            controller_actions=self.controller_actions,
            frames_executed=self.frames_executed,
            battles_completed=self.battles_completed,
            encounter_steps=self.encounter_steps,
            healing_trips=self.healing_trips,
            rotations_executed=self.rotations_executed,
            faints=self.faints,
            evolution_completed=self.evolution_completed,
            evidence_sha256=self.evidence_sha256,
            failure_code=self.failure_code,
        )

    def private_dict(self) -> dict[str, object]:
        return {**self._document(), "result_sha256": self.result_sha256}

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> PartyDevelopmentOutcomeTrialResult:
        expected = {
            "assignment_sha256",
            "battles_completed",
            "campaign_plan_sha256",
            "candidate_index",
            "claim_sha256",
            "controller_actions",
            "criterion_values",
            "encounter_steps",
            "evidence_sha256",
            "evolution_completed",
            "faints",
            "failure_code",
            "frames_executed",
            "healing_trips",
            "result_sha256",
            "rotations_executed",
            "schema",
            "semantic_actions",
            "status",
            "trial_id",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != PARTY_DEVELOPMENT_OUTCOME_TRIAL_RESULT_SCHEMA
            or not isinstance(value.get("criterion_values"), list)
        ):
            raise PartyDevelopmentOutcomeResultError(
                "party-development outcome result document is invalid"
            )
        try:
            return cls(
                campaign_plan_sha256=cast(str, value["campaign_plan_sha256"]),
                trial_id=cast(str, value["trial_id"]),
                assignment_sha256=cast(str, value["assignment_sha256"]),
                claim_sha256=cast(str, value["claim_sha256"]),
                candidate_index=cast(int, value["candidate_index"]),
                status=OutcomeEvidenceStatus(cast(str, value["status"])),
                criterion_values=tuple(
                    cast(list[float], value["criterion_values"])
                ),
                semantic_actions=cast(int | None, value["semantic_actions"]),
                controller_actions=cast(int | None, value["controller_actions"]),
                frames_executed=cast(int | None, value["frames_executed"]),
                battles_completed=cast(int | None, value["battles_completed"]),
                encounter_steps=cast(int | None, value["encounter_steps"]),
                healing_trips=cast(int | None, value["healing_trips"]),
                rotations_executed=cast(int | None, value["rotations_executed"]),
                faints=cast(int | None, value["faints"]),
                evolution_completed=cast(bool | None, value["evolution_completed"]),
                evidence_sha256=cast(str, value["evidence_sha256"]),
                failure_code=cast(str | None, value["failure_code"]),
                result_sha256=cast(str, value["result_sha256"]),
            )
        except PartyDevelopmentOutcomeResultError:
            raise
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentOutcomeResultError(
                "party-development outcome result document is invalid"
            ) from error

    def require_within_plan(
        self,
        plan: PartyDevelopmentOutcomeCampaignPlan,
        assignment: PartyDevelopmentOutcomeTrialAssignment,
    ) -> None:
        if (
            assignment not in plan.assignments
            or self.campaign_plan_sha256 != plan.plan_sha256
            or self.trial_id != assignment.trial_id
            or self.assignment_sha256 != assignment.assignment_sha256
            or self.claim_sha256
            != PartyDevelopmentOutcomeTrialClaim.build(
                plan, assignment
            ).claim_sha256
            or self.candidate_index != assignment.candidate_index
        ):
            raise PartyDevelopmentOutcomeResultError(
                "party-development outcome result crosses its frozen assignment"
            )
        dose = plan.dose
        if self.status is OutcomeEvidenceStatus.MEASURED and (
            self.battles_completed != dose.completed_battles
            or self.encounter_steps is None
            or self.encounter_steps > dose.maximum_encounter_steps
            or self.controller_actions is None
            or not 1 <= self.controller_actions <= dose.maximum_controller_actions
            or self.frames_executed is None
            or not 1 <= self.frames_executed <= dose.maximum_frames
            or self.healing_trips is None
            or self.healing_trips > dose.maximum_healing_trips
            or self.rotations_executed is None
            or self.rotations_executed > dose.maximum_rotations
            or self.faints != dose.maximum_faints
        ):
            raise PartyDevelopmentOutcomeResultError(
                "measured party-development result exceeds or misses its fixed dose"
            )

    def require_within_campaign_lineage(
        self,
        plan: PartyDevelopmentOutcomeCampaignPlan,
        assignment: PartyDevelopmentOutcomeTrialAssignment,
    ) -> None:
        """Accept a current result or one exactly bound inherited terminal."""

        if self.campaign_plan_sha256 == plan.plan_sha256:
            self.require_within_plan(plan, assignment)
            return
        inherited = next(
            (
                item
                for item in plan.inherited_terminals
                if item.assignment_sha256 == assignment.assignment_sha256
            ),
            None,
        )
        if (
            inherited is None
            or assignment not in plan.assignments
            or inherited.origin_campaign_plan_sha256
            != self.campaign_plan_sha256
            or inherited.trial_id != self.trial_id
            or inherited.assignment_sha256 != self.assignment_sha256
            or inherited.candidate_index != self.candidate_index
            or inherited.status is not self.status
            or inherited.claim_sha256 != self.claim_sha256
            or inherited.result_sha256 != self.result_sha256
        ):
            raise PartyDevelopmentOutcomeResultError(
                "party-development outcome result is outside its campaign lineage"
            )

    def candidate_outcome(self) -> CandidateOutcome:
        return CandidateOutcome(
            status=self.status,
            criterion_values=self.criterion_values,
            actions_executed=self.semantic_actions,
            frames_executed=self.frames_executed,
            evidence_sha256=self.evidence_sha256,
        )


def build_party_development_trial_terminal(
    result: PartyDevelopmentOutcomeTrialResult,
    *,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    """Bind a terminal result to the detailed private verifier evidence."""

    if not isinstance(result, PartyDevelopmentOutcomeTrialResult):
        raise TypeError("result must be a PartyDevelopmentOutcomeTrialResult")
    if not isinstance(evidence, Mapping):
        raise PartyDevelopmentOutcomeResultError(
            "party-development terminal evidence differs from its result"
        )
    _require_evidence_matches_result(result, evidence)
    if canonical_sha256(evidence) != result.evidence_sha256:
        raise PartyDevelopmentOutcomeResultError(
            "party-development terminal evidence differs from its result"
        )
    document = {
        "schema": PARTY_DEVELOPMENT_OUTCOME_TRIAL_TERMINAL_SCHEMA,
        "result": result.private_dict(),
        "evidence": dict(evidence),
    }
    return {**document, "terminal_sha256": canonical_sha256(document)}


def parse_party_development_trial_terminal(
    value: object,
) -> PartyDevelopmentOutcomeTrialResult:
    expected = {"evidence", "result", "schema", "terminal_sha256"}
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("schema") != PARTY_DEVELOPMENT_OUTCOME_TRIAL_TERMINAL_SCHEMA
        or not isinstance(value.get("evidence"), Mapping)
        or canonical_sha256({key: value[key] for key in value if key != "terminal_sha256"})
        != value.get("terminal_sha256")
    ):
        raise PartyDevelopmentOutcomeResultError(
            "party-development terminal document is invalid"
        )
    result = PartyDevelopmentOutcomeTrialResult.from_private_dict(value.get("result"))
    evidence = cast(Mapping[str, object], value["evidence"])
    _require_evidence_matches_result(result, evidence)
    if canonical_sha256(evidence) != result.evidence_sha256:
        raise PartyDevelopmentOutcomeResultError(
            "party-development terminal evidence differs from its result"
        )
    return result


def _require_evidence_matches_result(
    result: PartyDevelopmentOutcomeTrialResult,
    evidence: Mapping[str, object],
) -> None:
    """Keep re-hashed detailed evidence from contradicting its terminal row."""

    common_fields = {
        "assignment_sha256",
        "campaign_plan_sha256",
        "candidate_index",
        "claim_sha256",
        "model_predictions",
        "model_updates",
        "private_path_fields",
        "schema",
        "status",
        "teacher_queries",
        "trial_id",
    }
    failure_fields = common_fields | {
        "failure_code",
        "retry_after_controller_input",
    }
    if result.status is OutcomeEvidenceStatus.CENSORED:
        expected_fields = failure_fields | {"measurements_recovered"}
    elif result.status is OutcomeEvidenceStatus.INVALID:
        expected_fields = failure_fields
    else:
        expected_fields = common_fields | {
            "after_completion",
            "after_party",
            "before_completion",
            "before_party",
            "controller_actions",
            "criterion_values",
            "evolution_completed",
            "execution",
            "frames_executed",
            "outcome_evidence_sha256",
            "semantic_actions",
        }
    if (
        set(evidence) != expected_fields
        or evidence.get("schema")
        != PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA
        or evidence.get("campaign_plan_sha256") != result.campaign_plan_sha256
        or evidence.get("trial_id") != result.trial_id
        or evidence.get("assignment_sha256") != result.assignment_sha256
        or evidence.get("claim_sha256") != result.claim_sha256
        or type(evidence.get("candidate_index")) is not int  # noqa: E721
        or evidence.get("candidate_index") != result.candidate_index
        or evidence.get("status") != result.status.value
        or any(
            type(evidence.get(name)) is not int or evidence.get(name) != 0  # noqa: E721
            for name in (
                "teacher_queries",
                "model_predictions",
                "model_updates",
                "private_path_fields",
            )
        )
    ):
        raise PartyDevelopmentOutcomeResultError(
            "party-development terminal evidence contradicts its result"
        )
    if result.status is not OutcomeEvidenceStatus.MEASURED:
        if (
            evidence.get("failure_code") != result.failure_code
            or evidence.get("retry_after_controller_input") is not False
            or (
                result.status is OutcomeEvidenceStatus.CENSORED
                and evidence.get("measurements_recovered") is not False
            )
        ):
            raise PartyDevelopmentOutcomeResultError(
                "party-development terminal failure evidence contradicts its result"
            )
        return
    execution = evidence.get("execution")
    criteria = evidence.get("criterion_values")
    if (
        not isinstance(execution, Mapping)
        or not isinstance(evidence.get("before_party"), Mapping)
        or not isinstance(evidence.get("after_party"), Mapping)
        or not isinstance(evidence.get("before_completion"), Mapping)
        or not isinstance(evidence.get("after_completion"), Mapping)
        or not isinstance(criteria, list)
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in criteria
        )
        or not isinstance(evidence.get("outcome_evidence_sha256"), str)
        or _SHA256.fullmatch(cast(str, evidence["outcome_evidence_sha256"]))
        is None
        or type(evidence.get("semantic_actions")) is not int  # noqa: E721
        or evidence.get("semantic_actions") != result.semantic_actions
        or type(evidence.get("controller_actions")) is not int  # noqa: E721
        or evidence.get("controller_actions") != result.controller_actions
        or type(evidence.get("frames_executed")) is not int  # noqa: E721
        or evidence.get("frames_executed") != result.frames_executed
        or criteria != list(result.criterion_values)
        or evidence.get("evolution_completed") is not result.evolution_completed
        or any(
            type(execution.get(name)) is not int  # noqa: E721
            or execution.get(name) != expected
            for name, expected in (
                ("battles_completed", result.battles_completed),
                ("steps_taken", result.encounter_steps),
                ("healing_trips", result.healing_trips),
                ("rotations_executed", result.rotations_executed),
                ("faints", result.faints),
            )
        )
    ):
        raise PartyDevelopmentOutcomeResultError(
            "party-development terminal measurements contradict their result"
        )


def assemble_party_development_outcome_examples(
    catalog: PartyDevelopmentFrozenCatalog,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    results: tuple[PartyDevelopmentOutcomeTrialResult, ...],
) -> tuple[ScenarioOutcomeExample, ...]:
    """Join immutable terminal rows back into the fourteen frozen menus."""

    if not isinstance(catalog, PartyDevelopmentFrozenCatalog):
        raise TypeError("catalog must be a PartyDevelopmentFrozenCatalog")
    if not isinstance(plan, PartyDevelopmentOutcomeCampaignPlan):
        raise TypeError("plan must be a PartyDevelopmentOutcomeCampaignPlan")
    if not isinstance(results, tuple) or any(
        not isinstance(item, PartyDevelopmentOutcomeTrialResult) for item in results
    ):
        raise TypeError("results must be an immutable typed tuple")
    if (
        catalog.catalog_sha256 != plan.frozen_catalog_sha256
        or catalog.prospective_catalog_sha256 != plan.prospective_catalog_sha256
    ):
        raise PartyDevelopmentOutcomeResultError(
            "party-development result assembly crosses frozen catalogs"
        )
    assignment_by_digest = {
        item.assignment_sha256: item for item in plan.assignments
    }
    by_assignment: dict[str, PartyDevelopmentOutcomeTrialResult] = {}
    for result in results:
        assignment = assignment_by_digest.get(result.assignment_sha256)
        if assignment is None:
            raise PartyDevelopmentOutcomeResultError(
                "party-development result is outside the campaign"
            )
        result.require_within_campaign_lineage(plan, assignment)
        if result.assignment_sha256 in by_assignment:
            raise PartyDevelopmentOutcomeResultError(
                "party-development results repeat an assignment"
            )
        by_assignment[result.assignment_sha256] = result

    assignments_by_scenario: dict[
        str, dict[int, PartyDevelopmentOutcomeTrialAssignment]
    ] = {}
    for assignment in plan.assignments:
        assignments_by_scenario.setdefault(assignment.scenario_id, {})[
            assignment.candidate_index
        ] = assignment
    examples: list[ScenarioOutcomeExample] = []
    for question in catalog.questions:
        assignments = assignments_by_scenario.get(question.scenario_id)
        if assignments is None or set(assignments) != set(
            range(len(question.candidate_set.candidates))
        ):
            raise PartyDevelopmentOutcomeResultError(
                "party-development campaign does not cover one frozen menu"
            )
        candidates = tuple(
            OutcomeCandidate(
                candidate.candidate_index,
                candidate.features,
                question.binding.candidate_available[candidate.candidate_index],
            )
            for candidate in question.candidate_set.candidates
        )
        candidate_outcomes: list[CandidateOutcome | None] = []
        for index in range(len(candidates)):
            terminal = by_assignment.get(assignments[index].assignment_sha256)
            candidate_outcomes.append(
                None if terminal is None else terminal.candidate_outcome()
            )
        outcomes = tuple(candidate_outcomes)
        example = ScenarioOutcomeExample(
            scenario_id=question.scenario_id,
            root_lineage_id=question.binding.root_lineage_id,
            initial_state_sha256=question.binding.initial_state_sha256,
            partition=question.binding.partition,
            objective=PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
            feature_schema_id=PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
            feature_names=PARTY_DEVELOPMENT_FEATURE_NAMES,
            candidates=candidates,
            outcomes=outcomes,
            prospective_binding_sha256=question.binding.binding_sha256,
        )
        question.binding.require_matches(example)
        examples.append(example)
    return tuple(examples)


def _result_document(
    *,
    campaign_plan_sha256: str,
    trial_id: str,
    assignment_sha256: str,
    claim_sha256: str,
    candidate_index: int,
    status: OutcomeEvidenceStatus,
    criterion_values: tuple[float, ...],
    semantic_actions: int | None,
    controller_actions: int | None,
    frames_executed: int | None,
    battles_completed: int | None,
    encounter_steps: int | None,
    healing_trips: int | None,
    rotations_executed: int | None,
    faints: int | None,
    evolution_completed: bool | None,
    evidence_sha256: str,
    failure_code: str | None,
) -> dict[str, object]:
    return {
        "schema": PARTY_DEVELOPMENT_OUTCOME_TRIAL_RESULT_SCHEMA,
        "campaign_plan_sha256": campaign_plan_sha256,
        "trial_id": trial_id,
        "assignment_sha256": assignment_sha256,
        "claim_sha256": claim_sha256,
        "candidate_index": candidate_index,
        "status": status.value,
        "criterion_values": list(criterion_values),
        "semantic_actions": semantic_actions,
        "controller_actions": controller_actions,
        "frames_executed": frames_executed,
        "battles_completed": battles_completed,
        "encounter_steps": encounter_steps,
        "healing_trips": healing_trips,
        "rotations_executed": rotations_executed,
        "faints": faints,
        "evolution_completed": evolution_completed,
        "evidence_sha256": evidence_sha256,
        "failure_code": failure_code,
    }


def _require_plan_assignment_claim(
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
    claim: PartyDevelopmentOutcomeTrialClaim,
) -> None:
    if (
        not isinstance(plan, PartyDevelopmentOutcomeCampaignPlan)
        or not isinstance(assignment, PartyDevelopmentOutcomeTrialAssignment)
        or not isinstance(claim, PartyDevelopmentOutcomeTrialClaim)
        or assignment not in plan.assignments
        or claim != PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    ):
        raise PartyDevelopmentOutcomeResultError(
            "party-development outcome result plan, assignment, and claim differ"
        )


def _require_digest(value: object, *, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PartyDevelopmentOutcomeResultError(
            f"party-development outcome {subject} digest is invalid"
        )


__all__ = [
    "PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA",
    "PARTY_DEVELOPMENT_OUTCOME_TRIAL_RESULT_SCHEMA",
    "PARTY_DEVELOPMENT_OUTCOME_TRIAL_TERMINAL_SCHEMA",
    "PartyDevelopmentOutcomeResultError",
    "PartyDevelopmentOutcomeTrialResult",
    "assemble_party_development_outcome_examples",
    "build_party_development_trial_terminal",
    "parse_party_development_trial_terminal",
]
