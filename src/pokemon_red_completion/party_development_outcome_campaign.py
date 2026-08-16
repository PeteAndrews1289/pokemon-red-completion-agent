"""Prospective contract for the first completion-aware Red outcome campaign.

The frozen input catalog contains fourteen *questions*, but a question becomes a
learner target only after every available candidate has been executed from an
independent clone of the same starting state.  For the official catalog that is
fifty-five one-shot trials.  This module makes that denominator explicit before
any controller input is authorized.

It deliberately contains no emulator, teacher, model, outcome, or filesystem
code.  A title adapter may later consume the plan, but it must durably claim one
trial identity before acting and may never replace or retry a consumed identity.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.party_development_frozen_catalog import (
    PartyDevelopmentFrozenCatalog,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
)
from pokemon_red_completion.party_development_rank import PartyDevelopmentGoal
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

RED_PARTY_DEVELOPMENT_OUTCOME_CAMPAIGN_SCHEMA = (
    "pokemon.red.party-development-outcome-campaign-plan.v1"
)
RED_PARTY_DEVELOPMENT_OUTCOME_ASSIGNMENT_SCHEMA = (
    "pokemon.red.party-development-outcome-trial-assignment.v1"
)
RED_PARTY_DEVELOPMENT_OUTCOME_CAMPAIGN_SUMMARY_SCHEMA = (
    "pokemon.red.party-development-outcome-campaign-summary.v1"
)
RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_CLAIM_SCHEMA = (
    "pokemon.red.party-development-outcome-trial-claim.v1"
)

RED_PARTY_DEVELOPMENT_OUTCOME_QUESTION_COUNT = 14
RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT = 55

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class PartyDevelopmentOutcomeCampaignError(ValueError):
    """Raised when a campaign could misstate or reuse a counterfactual."""


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeDose:
    """One comparable, bounded dose applied to every available candidate.

    Four completed battles is intentionally a small causal probe rather than a
    miniature playthrough.  It is long enough to expose experience yield,
    trainee participation, recovery pressure, and common level boundaries while
    keeping all fifty-five clones operationally tractable.  Hard limits remain
    independent so a flee loop or navigation defect cannot turn the dose into an
    unbounded run.
    """

    completed_battles: int = 4
    maximum_encounter_steps: int = 2_500
    maximum_controller_actions: int = 100_000
    maximum_frames: int = 1_500_000
    maximum_healing_trips: int = 4
    maximum_rotations: int = 16
    maximum_faints: int = 0

    def __post_init__(self) -> None:
        positive = (
            "completed_battles",
            "maximum_encounter_steps",
            "maximum_controller_actions",
            "maximum_frames",
            "maximum_healing_trips",
            "maximum_rotations",
        )
        if any(
            type(getattr(self, name)) is not int or getattr(self, name) <= 0  # noqa: E721
            for name in positive
        ) or type(self.maximum_faints) is not int:  # noqa: E721
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome dose bounds are invalid"
            )
        if self.maximum_faints != 0:
            raise PartyDevelopmentOutcomeCampaignError(
                "the first party-development outcome campaign requires zero faints"
            )

    @property
    def dose_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, int | str]:
        return {
            "schema": "pokemon.core.party-development-outcome-dose.v1",
            "completed_battles": self.completed_battles,
            "maximum_encounter_steps": self.maximum_encounter_steps,
            "maximum_controller_actions": self.maximum_controller_actions,
            "maximum_frames": self.maximum_frames,
            "maximum_healing_trips": self.maximum_healing_trips,
            "maximum_rotations": self.maximum_rotations,
            "maximum_faints": self.maximum_faints,
        }


RED_PARTY_DEVELOPMENT_OUTCOME_DOSE = PartyDevelopmentOutcomeDose()
RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT = {
    "schema": "pokemon.red.party-development-outcome-execution.v1",
    "purpose": "measure_completion_aware_party_candidate_preferences",
    "unit": "one_available_candidate_from_one_frozen_question",
    "campaign_shape": {
        "questions": RED_PARTY_DEVELOPMENT_OUTCOME_QUESTION_COUNT,
        "candidate_trials": RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT,
        "train_questions": 8,
        "development_questions": 6,
    },
    "clone_rule": "reload_the_exact_frozen_initial_state_for_every_candidate_trial",
    "selection_rule": (
        "bind_exactly_one_candidate_from_the_initial_frozen_menu_before_controller_input"
    ),
    "continuation_rule": (
        "hold_the_selected_private_trainee_and_venue_binding_fixed_for_the_complete_dose"
    ),
    "mechanics_rule": "one_shared_deterministic_safety_policy_for_every_candidate",
    "stop_rule": "four_completed_wild_battles_then_safe_cleanup",
    "measurement_rule": (
        "measure_completion_state_experience_safety_recovery_and_frames_at_stable_boundaries"
    ),
    "durability": (
        "one_exclusive_trial_artifact_and_durable_claim_before_any_controller_input"
    ),
    "retry_after_any_controller_input": False,
    "failure_rule": "retain_the_consumed_trial_as_invalid_never_replace_or_retry_it",
    "interruption_rule": "retain_the_consumed_trial_as_censored_never_replace_or_retry_it",
    "campaign_recovery_rule": (
        "after_power_loss_continue_only_with_trial_identities_never_previously_claimed"
    ),
    "preference_rule": "a_question_is_usable_only_when_every_available_candidate_is_measured",
    "partition_rule": "fit_train_only_and_never_tune_on_development",
    "forbidden_during_collection": [
        "candidate_replacement",
        "capture",
        "crystal_access",
        "direct_memory_edit",
        "full_game_replay",
        "model_fit",
        "model_prediction",
        "outcome_driven_retry",
        "sealed_red_access",
        "storage_access",
        "teacher_query",
    ],
    "dose": RED_PARTY_DEVELOPMENT_OUTCOME_DOSE.public_dict(),
    "outcome_objective_sha256": (
        PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256
    ),
}
RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT_SHA256 = canonical_sha256(
    RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT
)


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeTrialAssignment:
    """One immutable candidate counterfactual in deterministic campaign order."""

    ordinal: int
    trial_id: str
    scenario_id: str
    root_lineage_id: str
    initial_state_sha256: str
    partition: ScenarioPartition
    kind: TrainingChoiceKind
    goal: PartyDevelopmentGoal
    binding_sha256: str
    candidate_index: int
    candidate_sha256: str
    candidate_feature_sha256: str
    assignment_sha256: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 1:  # noqa: E721
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome trial ordinal is invalid"
            )
        for value, subject in (
            (self.trial_id, "trial"),
            (self.scenario_id, "scenario"),
            (self.root_lineage_id, "root lineage"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise PartyDevelopmentOutcomeCampaignError(
                    f"party-development outcome {subject} identity is invalid"
                )
        for value, subject in (
            (self.initial_state_sha256, "initial state"),
            (self.binding_sha256, "binding"),
            (self.candidate_sha256, "candidate"),
            (self.candidate_feature_sha256, "candidate feature"),
            (self.assignment_sha256, "assignment"),
        ):
            _require_digest(value, subject=subject)
        if not isinstance(self.partition, ScenarioPartition):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome trial partition is invalid"
            )
        if not isinstance(self.kind, TrainingChoiceKind) or not isinstance(
            self.goal, PartyDevelopmentGoal
        ):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome trial semantics are invalid"
            )
        if type(self.candidate_index) is not int or self.candidate_index < 0:  # noqa: E721
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome candidate index is invalid"
            )
        document = self._assignment_document()
        if self.assignment_sha256 != canonical_sha256(document):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome assignment digest differs"
            )
        expected_trial_id = _trial_id(self.assignment_sha256)
        if self.trial_id != expected_trial_id:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome trial identity differs"
            )

    @classmethod
    def build(
        cls,
        *,
        ordinal: int,
        scenario_id: str,
        root_lineage_id: str,
        initial_state_sha256: str,
        partition: ScenarioPartition,
        kind: TrainingChoiceKind,
        goal: PartyDevelopmentGoal,
        binding_sha256: str,
        candidate_index: int,
        candidate_sha256: str,
        candidate_feature_sha256: str,
    ) -> PartyDevelopmentOutcomeTrialAssignment:
        document = _assignment_document(
            ordinal=ordinal,
            scenario_id=scenario_id,
            root_lineage_id=root_lineage_id,
            initial_state_sha256=initial_state_sha256,
            partition=partition,
            kind=kind,
            goal=goal,
            binding_sha256=binding_sha256,
            candidate_index=candidate_index,
            candidate_sha256=candidate_sha256,
            candidate_feature_sha256=candidate_feature_sha256,
        )
        assignment_sha256 = canonical_sha256(document)
        return cls(
            ordinal=ordinal,
            trial_id=_trial_id(assignment_sha256),
            scenario_id=scenario_id,
            root_lineage_id=root_lineage_id,
            initial_state_sha256=initial_state_sha256,
            partition=partition,
            kind=kind,
            goal=goal,
            binding_sha256=binding_sha256,
            candidate_index=candidate_index,
            candidate_sha256=candidate_sha256,
            candidate_feature_sha256=candidate_feature_sha256,
            assignment_sha256=assignment_sha256,
        )

    def _assignment_document(self) -> dict[str, object]:
        return _assignment_document(
            ordinal=self.ordinal,
            scenario_id=self.scenario_id,
            root_lineage_id=self.root_lineage_id,
            initial_state_sha256=self.initial_state_sha256,
            partition=self.partition,
            kind=self.kind,
            goal=self.goal,
            binding_sha256=self.binding_sha256,
            candidate_index=self.candidate_index,
            candidate_sha256=self.candidate_sha256,
            candidate_feature_sha256=self.candidate_feature_sha256,
        )

    def private_dict(self) -> dict[str, object]:
        return {
            **self._assignment_document(),
            "trial_id": self.trial_id,
            "assignment_sha256": self.assignment_sha256,
        }

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> PartyDevelopmentOutcomeTrialAssignment:
        expected = {
            "assignment_sha256",
            "binding_sha256",
            "candidate_feature_sha256",
            "candidate_index",
            "candidate_sha256",
            "goal",
            "initial_state_sha256",
            "kind",
            "ordinal",
            "partition",
            "root_lineage_id",
            "scenario_id",
            "schema",
            "trial_id",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema")
            != RED_PARTY_DEVELOPMENT_OUTCOME_ASSIGNMENT_SCHEMA
        ):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome assignment document is invalid"
            )
        try:
            return cls(
                ordinal=cast(int, value["ordinal"]),
                trial_id=cast(str, value["trial_id"]),
                scenario_id=cast(str, value["scenario_id"]),
                root_lineage_id=cast(str, value["root_lineage_id"]),
                initial_state_sha256=cast(str, value["initial_state_sha256"]),
                partition=ScenarioPartition(cast(str, value["partition"])),
                kind=TrainingChoiceKind(cast(str, value["kind"])),
                goal=PartyDevelopmentGoal(cast(str, value["goal"])),
                binding_sha256=cast(str, value["binding_sha256"]),
                candidate_index=cast(int, value["candidate_index"]),
                candidate_sha256=cast(str, value["candidate_sha256"]),
                candidate_feature_sha256=cast(
                    str, value["candidate_feature_sha256"]
                ),
                assignment_sha256=cast(str, value["assignment_sha256"]),
            )
        except PartyDevelopmentOutcomeCampaignError:
            raise
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome assignment document is invalid"
            ) from error


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeCampaignPlan:
    """Exact 14-question / 55-trial plan, still unauthorized and unopened."""

    source_commit: str
    source_bundle_sha256: str
    runner_source_sha256: str
    exact_ci_run: int
    exact_ci_attempt: int
    frozen_catalog_file_sha256: str
    frozen_catalog_sha256: str
    prospective_catalog_sha256: str
    frozen_catalog_source_commit: str
    frozen_catalog_source_bundle_sha256: str
    rom_sha256: str
    input_audit_receipt_file_sha256: str
    input_audit_result_sha256: str
    assignments: tuple[PartyDevelopmentOutcomeTrialAssignment, ...]
    dose: PartyDevelopmentOutcomeDose = RED_PARTY_DEVELOPMENT_OUTCOME_DOSE
    execution_contract_sha256: str = (
        RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT_SHA256
    )

    def __post_init__(self) -> None:
        for value, subject in (
            (self.source_commit, "source commit"),
            (self.frozen_catalog_source_commit, "frozen catalog source commit"),
        ):
            if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
                raise PartyDevelopmentOutcomeCampaignError(
                    f"party-development outcome {subject} is invalid"
                )
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.runner_source_sha256, "runner source"),
            (self.frozen_catalog_file_sha256, "frozen catalog file"),
            (self.frozen_catalog_sha256, "frozen catalog"),
            (self.prospective_catalog_sha256, "prospective catalog"),
            (self.frozen_catalog_source_bundle_sha256, "frozen catalog source bundle"),
            (self.rom_sha256, "ROM"),
            (self.input_audit_receipt_file_sha256, "input-audit receipt file"),
            (self.input_audit_result_sha256, "input-audit result"),
            (self.execution_contract_sha256, "execution contract"),
        ):
            _require_digest(value, subject=subject)
        if (
            type(self.exact_ci_run) is not int  # noqa: E721
            or self.exact_ci_run <= 0
            or type(self.exact_ci_attempt) is not int  # noqa: E721
            or self.exact_ci_attempt <= 0
            or not isinstance(self.dose, PartyDevelopmentOutcomeDose)
            or self.dose != RED_PARTY_DEVELOPMENT_OUTCOME_DOSE
            or self.execution_contract_sha256
            != RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT_SHA256
        ):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome campaign execution identity is invalid"
            )
        if (
            not isinstance(self.assignments, tuple)
            or len(self.assignments) != RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT
            or any(
                not isinstance(item, PartyDevelopmentOutcomeTrialAssignment)
                for item in self.assignments
            )
            or tuple(item.ordinal for item in self.assignments)
            != tuple(range(1, RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT + 1))
        ):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome campaign needs exactly 55 ordered trials"
            )
        for attribute, subject in (
            ("trial_id", "trial"),
            ("assignment_sha256", "assignment"),
        ):
            values = tuple(getattr(item, attribute) for item in self.assignments)
            if len(values) != len(set(values)):
                raise PartyDevelopmentOutcomeCampaignError(
                    f"party-development outcome campaign repeats a {subject}"
                )
        by_scenario: dict[str, list[PartyDevelopmentOutcomeTrialAssignment]] = (
            defaultdict(list)
        )
        for assignment in self.assignments:
            by_scenario[assignment.scenario_id].append(assignment)
        if len(by_scenario) != RED_PARTY_DEVELOPMENT_OUTCOME_QUESTION_COUNT:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome campaign needs exactly fourteen questions"
            )
        for trials in by_scenario.values():
            first = trials[0]
            if (
                [item.candidate_index for item in trials]
                != list(range(len(trials)))
                or any(
                    (
                        item.root_lineage_id,
                        item.initial_state_sha256,
                        item.partition,
                        item.kind,
                        item.goal,
                        item.binding_sha256,
                    )
                    != (
                        first.root_lineage_id,
                        first.initial_state_sha256,
                        first.partition,
                        first.kind,
                        first.goal,
                        first.binding_sha256,
                    )
                    for item in trials[1:]
                )
            ):
                raise PartyDevelopmentOutcomeCampaignError(
                    "party-development outcome question trials do not share one frozen start"
                )
        question_partitions = Counter(
            trials[0].partition for trials in by_scenario.values()
        )
        if question_partitions != {
            ScenarioPartition.TRAIN: 8,
            ScenarioPartition.DEVELOPMENT: 6,
        }:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome campaign is not exact 8+6"
            )
        for partition in (
            ScenarioPartition.TRAIN,
            ScenarioPartition.DEVELOPMENT,
        ):
            kinds = {
                trials[0].kind
                for trials in by_scenario.values()
                if trials[0].partition is partition
            }
            if kinds != set(TrainingChoiceKind):
                raise PartyDevelopmentOutcomeCampaignError(
                    "party-development outcome partition lacks a choice kind"
                )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self._document())

    def _document(self) -> dict[str, object]:
        return {
            "schema": RED_PARTY_DEVELOPMENT_OUTCOME_CAMPAIGN_SCHEMA,
            "status": "prospective_unexecuted_authorization_required",
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "runner_source_sha256": self.runner_source_sha256,
            "exact_ci_run": self.exact_ci_run,
            "exact_ci_attempt": self.exact_ci_attempt,
            "frozen_catalog_file_sha256": self.frozen_catalog_file_sha256,
            "frozen_catalog_sha256": self.frozen_catalog_sha256,
            "prospective_catalog_sha256": self.prospective_catalog_sha256,
            "frozen_catalog_source_commit": self.frozen_catalog_source_commit,
            "frozen_catalog_source_bundle_sha256": (
                self.frozen_catalog_source_bundle_sha256
            ),
            "rom_sha256": self.rom_sha256,
            "input_audit_receipt_file_sha256": (
                self.input_audit_receipt_file_sha256
            ),
            "input_audit_result_sha256": self.input_audit_result_sha256,
            "execution_contract": deepcopy(
                RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT
            ),
            "execution_contract_sha256": self.execution_contract_sha256,
            "dose": self.dose.public_dict(),
            "assignments": [item.private_dict() for item in self.assignments],
            "execution_authorized": False,
            "trial_claims": 0,
            "measured_trials": 0,
            "invalid_trials": 0,
            "censored_trials": 0,
            "complete_examples": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "model_fits": 0,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }

    def private_dict(self) -> dict[str, object]:
        return {**self._document(), "plan_sha256": self.plan_sha256}

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> PartyDevelopmentOutcomeCampaignPlan:
        expected = {
            "assignments",
            "authority_promoted",
            "censored_trials",
            "complete_examples",
            "crystal_cases_opened",
            "dose",
            "exact_ci_attempt",
            "exact_ci_run",
            "execution_authorized",
            "execution_contract",
            "execution_contract_sha256",
            "frozen_catalog_file_sha256",
            "frozen_catalog_sha256",
            "frozen_catalog_source_bundle_sha256",
            "frozen_catalog_source_commit",
            "full_game_replays",
            "input_audit_receipt_file_sha256",
            "input_audit_result_sha256",
            "invalid_trials",
            "measured_trials",
            "model_fits",
            "model_predictions",
            "model_updates",
            "plan_sha256",
            "private_path_fields",
            "prospective_catalog_sha256",
            "rom_sha256",
            "runner_source_sha256",
            "schema",
            "sealed_red_cases_opened",
            "source_bundle_sha256",
            "source_commit",
            "status",
            "teacher_queries",
            "trial_claims",
        }
        zero_fields = (
            "censored_trials",
            "complete_examples",
            "crystal_cases_opened",
            "full_game_replays",
            "invalid_trials",
            "measured_trials",
            "model_fits",
            "model_predictions",
            "model_updates",
            "sealed_red_cases_opened",
            "teacher_queries",
            "trial_claims",
        )
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != RED_PARTY_DEVELOPMENT_OUTCOME_CAMPAIGN_SCHEMA
            or value.get("status")
            != "prospective_unexecuted_authorization_required"
            or value.get("execution_contract")
            != RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT
            or value.get("execution_authorized") is not False
            or value.get("authority_promoted") is not False
            or type(value.get("private_path_fields")) is not int  # noqa: E721
            or value.get("private_path_fields") != 0
            or any(
                type(value.get(name)) is not int or value.get(name) != 0  # noqa: E721
                for name in zero_fields
            )
            or not isinstance(value.get("assignments"), list)
            or not isinstance(value.get("dose"), Mapping)
        ):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome campaign document is invalid"
            )
        dose = cast(Mapping[str, object], value["dose"])
        if (
            set(dose) != set(RED_PARTY_DEVELOPMENT_OUTCOME_DOSE.public_dict())
            or dose.get("schema")
            != "pokemon.core.party-development-outcome-dose.v1"
        ):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome campaign dose document is invalid"
            )
        try:
            result = cls(
                source_commit=cast(str, value["source_commit"]),
                source_bundle_sha256=cast(str, value["source_bundle_sha256"]),
                runner_source_sha256=cast(str, value["runner_source_sha256"]),
                exact_ci_run=cast(int, value["exact_ci_run"]),
                exact_ci_attempt=cast(int, value["exact_ci_attempt"]),
                frozen_catalog_file_sha256=cast(
                    str, value["frozen_catalog_file_sha256"]
                ),
                frozen_catalog_sha256=cast(str, value["frozen_catalog_sha256"]),
                prospective_catalog_sha256=cast(
                    str, value["prospective_catalog_sha256"]
                ),
                frozen_catalog_source_commit=cast(
                    str, value["frozen_catalog_source_commit"]
                ),
                frozen_catalog_source_bundle_sha256=cast(
                    str, value["frozen_catalog_source_bundle_sha256"]
                ),
                rom_sha256=cast(str, value["rom_sha256"]),
                input_audit_receipt_file_sha256=cast(
                    str, value["input_audit_receipt_file_sha256"]
                ),
                input_audit_result_sha256=cast(
                    str, value["input_audit_result_sha256"]
                ),
                assignments=tuple(
                    PartyDevelopmentOutcomeTrialAssignment.from_private_dict(item)
                    for item in cast(list[object], value["assignments"])
                ),
                dose=PartyDevelopmentOutcomeDose(
                    completed_battles=cast(int, dose["completed_battles"]),
                    maximum_encounter_steps=cast(
                        int, dose["maximum_encounter_steps"]
                    ),
                    maximum_controller_actions=cast(
                        int, dose["maximum_controller_actions"]
                    ),
                    maximum_frames=cast(int, dose["maximum_frames"]),
                    maximum_healing_trips=cast(
                        int, dose["maximum_healing_trips"]
                    ),
                    maximum_rotations=cast(int, dose["maximum_rotations"]),
                    maximum_faints=cast(int, dose["maximum_faints"]),
                ),
                execution_contract_sha256=cast(
                    str, value["execution_contract_sha256"]
                ),
            )
        except PartyDevelopmentOutcomeCampaignError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome campaign document is invalid"
            ) from error
        if value.get("plan_sha256") != result.plan_sha256:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome campaign digest differs"
            )
        return result

    def public_summary(self) -> dict[str, object]:
        scenarios: dict[str, PartyDevelopmentOutcomeTrialAssignment] = {}
        for item in self.assignments:
            scenarios.setdefault(item.scenario_id, item)
        question_partitions = Counter(item.partition.value for item in scenarios.values())
        trial_partitions = Counter(item.partition.value for item in self.assignments)
        kinds = Counter(
            f"{item.partition.value}:{item.kind.value}" for item in scenarios.values()
        )
        goals = Counter(
            f"{item.partition.value}:{item.goal.value}" for item in scenarios.values()
        )
        widths = Counter(
            len([trial for trial in self.assignments if trial.scenario_id == scenario])
            for scenario in scenarios
        )
        return {
            "schema": RED_PARTY_DEVELOPMENT_OUTCOME_CAMPAIGN_SUMMARY_SCHEMA,
            "status": "collector_plan_frozen_controller_authorization_required",
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "runner_source_sha256": self.runner_source_sha256,
            "exact_ci_run": self.exact_ci_run,
            "exact_ci_attempt": self.exact_ci_attempt,
            "frozen_catalog_file_sha256": self.frozen_catalog_file_sha256,
            "frozen_catalog_sha256": self.frozen_catalog_sha256,
            "prospective_catalog_sha256": self.prospective_catalog_sha256,
            "rom_sha256": self.rom_sha256,
            "input_audit_receipt_file_sha256": (
                self.input_audit_receipt_file_sha256
            ),
            "input_audit_result_sha256": self.input_audit_result_sha256,
            "plan_sha256": self.plan_sha256,
            "execution_contract_sha256": self.execution_contract_sha256,
            "dose": self.dose.public_dict(),
            "question_count": len(scenarios),
            "candidate_trial_count": len(self.assignments),
            "question_partition_counts": dict(sorted(question_partitions.items())),
            "trial_partition_counts": dict(sorted(trial_partitions.items())),
            "question_kind_counts": dict(sorted(kinds.items())),
            "question_goal_counts": dict(sorted(goals.items())),
            "candidate_width_counts": {
                str(width): count for width, count in sorted(widths.items())
            },
            "unique_trial_id_count": len({item.trial_id for item in self.assignments}),
            "execution_authorized": False,
            "trial_claims": 0,
            "measured_trials": 0,
            "invalid_trials": 0,
            "censored_trials": 0,
            "complete_examples": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "model_fits": 0,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
            "authority_promoted": False,
            "trial_identity_values_public": False,
            "candidate_feature_values_public": False,
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeTrialClaim:
    """The record that must be synchronized before a trial can send input."""

    campaign_plan_sha256: str
    trial_id: str
    assignment_sha256: str
    source_commit: str
    exact_ci_run: int
    exact_ci_attempt: int
    execution_contract_sha256: str
    dose_sha256: str
    claim_sha256: str

    def __post_init__(self) -> None:
        for value, subject in (
            (self.campaign_plan_sha256, "campaign plan"),
            (self.assignment_sha256, "assignment"),
            (self.execution_contract_sha256, "execution contract"),
            (self.dose_sha256, "dose"),
            (self.claim_sha256, "claim"),
        ):
            _require_digest(value, subject=subject)
        if not isinstance(self.trial_id, str) or _SAFE_ID.fullmatch(self.trial_id) is None:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome claim trial identity is invalid"
            )
        if not isinstance(self.source_commit, str) or _COMMIT.fullmatch(self.source_commit) is None:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome claim source commit is invalid"
            )
        if (
            type(self.exact_ci_run) is not int  # noqa: E721
            or self.exact_ci_run <= 0
            or type(self.exact_ci_attempt) is not int  # noqa: E721
            or self.exact_ci_attempt <= 0
            or self.claim_sha256 != canonical_sha256(self._claim_document())
        ):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome claim differs"
            )

    @classmethod
    def build(
        cls,
        plan: PartyDevelopmentOutcomeCampaignPlan,
        assignment: PartyDevelopmentOutcomeTrialAssignment,
    ) -> PartyDevelopmentOutcomeTrialClaim:
        if not isinstance(plan, PartyDevelopmentOutcomeCampaignPlan):
            raise TypeError("plan must be a PartyDevelopmentOutcomeCampaignPlan")
        if not isinstance(assignment, PartyDevelopmentOutcomeTrialAssignment):
            raise TypeError("assignment must be a PartyDevelopmentOutcomeTrialAssignment")
        if assignment not in plan.assignments:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome claim assignment is outside its campaign"
            )
        document = _claim_document(
            campaign_plan_sha256=plan.plan_sha256,
            trial_id=assignment.trial_id,
            assignment_sha256=assignment.assignment_sha256,
            source_commit=plan.source_commit,
            exact_ci_run=plan.exact_ci_run,
            exact_ci_attempt=plan.exact_ci_attempt,
            execution_contract_sha256=plan.execution_contract_sha256,
            dose_sha256=plan.dose.dose_sha256,
        )
        return cls(
            campaign_plan_sha256=plan.plan_sha256,
            trial_id=assignment.trial_id,
            assignment_sha256=assignment.assignment_sha256,
            source_commit=plan.source_commit,
            exact_ci_run=plan.exact_ci_run,
            exact_ci_attempt=plan.exact_ci_attempt,
            execution_contract_sha256=plan.execution_contract_sha256,
            dose_sha256=plan.dose.dose_sha256,
            claim_sha256=canonical_sha256(document),
        )

    def _claim_document(self) -> dict[str, object]:
        return _claim_document(
            campaign_plan_sha256=self.campaign_plan_sha256,
            trial_id=self.trial_id,
            assignment_sha256=self.assignment_sha256,
            source_commit=self.source_commit,
            exact_ci_run=self.exact_ci_run,
            exact_ci_attempt=self.exact_ci_attempt,
            execution_contract_sha256=self.execution_contract_sha256,
            dose_sha256=self.dose_sha256,
        )

    def private_dict(self) -> dict[str, object]:
        return {**self._claim_document(), "claim_sha256": self.claim_sha256}

    @classmethod
    def from_private_dict(cls, value: object) -> PartyDevelopmentOutcomeTrialClaim:
        expected = {
            "assignment_sha256",
            "campaign_plan_sha256",
            "claim_sha256",
            "controller_actions_before_claim",
            "dose_sha256",
            "exact_ci_attempt",
            "exact_ci_run",
            "execution_contract_sha256",
            "model_predictions",
            "model_updates",
            "private_path_fields",
            "retry_after_controller_input",
            "schema",
            "source_commit",
            "teacher_queries",
            "trial_id",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema")
            != RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_CLAIM_SCHEMA
            or any(
                type(value.get(name)) is not int or value.get(name) != 0  # noqa: E721
                for name in (
                    "controller_actions_before_claim",
                    "teacher_queries",
                    "model_predictions",
                    "model_updates",
                    "private_path_fields",
                )
            )
            or value.get("retry_after_controller_input") is not False
        ):
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome claim document is invalid"
            )
        try:
            return cls(
                campaign_plan_sha256=cast(
                    str, value["campaign_plan_sha256"]
                ),
                trial_id=cast(str, value["trial_id"]),
                assignment_sha256=cast(str, value["assignment_sha256"]),
                source_commit=cast(str, value["source_commit"]),
                exact_ci_run=cast(int, value["exact_ci_run"]),
                exact_ci_attempt=cast(int, value["exact_ci_attempt"]),
                execution_contract_sha256=cast(
                    str, value["execution_contract_sha256"]
                ),
                dose_sha256=cast(str, value["dose_sha256"]),
                claim_sha256=cast(str, value["claim_sha256"]),
            )
        except PartyDevelopmentOutcomeCampaignError:
            raise
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentOutcomeCampaignError(
                "party-development outcome claim document is invalid"
            ) from error


def freeze_party_development_outcome_campaign(
    catalog: PartyDevelopmentFrozenCatalog,
    *,
    source_commit: str,
    source_bundle_sha256: str,
    runner_source_sha256: str,
    exact_ci_run: int,
    exact_ci_attempt: int,
    frozen_catalog_file_sha256: str,
    input_audit_receipt_file_sha256: str,
    input_audit_result_sha256: str,
) -> PartyDevelopmentOutcomeCampaignPlan:
    """Enumerate every available candidate without choosing or executing one."""

    if not isinstance(catalog, PartyDevelopmentFrozenCatalog):
        raise TypeError("catalog must be a PartyDevelopmentFrozenCatalog")
    if any(
        not available
        for question in catalog.questions
        for available in question.binding.candidate_available
    ):
        raise PartyDevelopmentOutcomeCampaignError(
            "the first Red outcome campaign requires all frozen candidates available"
        )
    assignments: list[PartyDevelopmentOutcomeTrialAssignment] = []
    for question in catalog.questions:
        for candidate in question.candidate_set.candidates:
            index = candidate.candidate_index
            assignments.append(
                PartyDevelopmentOutcomeTrialAssignment.build(
                    ordinal=len(assignments) + 1,
                    scenario_id=question.scenario_id,
                    root_lineage_id=question.binding.root_lineage_id,
                    initial_state_sha256=question.binding.initial_state_sha256,
                    partition=question.binding.partition,
                    kind=question.binding.kind,
                    goal=question.binding.goal,
                    binding_sha256=question.binding.binding_sha256,
                    candidate_index=index,
                    candidate_sha256=canonical_sha256(candidate.public_dict()),
                    candidate_feature_sha256=(
                        question.binding.candidate_feature_sha256[index]
                    ),
                )
            )
    return PartyDevelopmentOutcomeCampaignPlan(
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        runner_source_sha256=runner_source_sha256,
        exact_ci_run=exact_ci_run,
        exact_ci_attempt=exact_ci_attempt,
        frozen_catalog_file_sha256=frozen_catalog_file_sha256,
        frozen_catalog_sha256=catalog.catalog_sha256,
        prospective_catalog_sha256=catalog.prospective_catalog_sha256,
        frozen_catalog_source_commit=catalog.source_commit,
        frozen_catalog_source_bundle_sha256=catalog.source_bundle_sha256,
        rom_sha256=catalog.rom_sha256,
        input_audit_receipt_file_sha256=input_audit_receipt_file_sha256,
        input_audit_result_sha256=input_audit_result_sha256,
        assignments=tuple(assignments),
    )


def _assignment_document(
    *,
    ordinal: int,
    scenario_id: str,
    root_lineage_id: str,
    initial_state_sha256: str,
    partition: ScenarioPartition,
    kind: TrainingChoiceKind,
    goal: PartyDevelopmentGoal,
    binding_sha256: str,
    candidate_index: int,
    candidate_sha256: str,
    candidate_feature_sha256: str,
) -> dict[str, object]:
    return {
        "schema": RED_PARTY_DEVELOPMENT_OUTCOME_ASSIGNMENT_SCHEMA,
        "ordinal": ordinal,
        "scenario_id": scenario_id,
        "root_lineage_id": root_lineage_id,
        "initial_state_sha256": initial_state_sha256,
        "partition": partition.value,
        "kind": kind.value,
        "goal": goal.value,
        "binding_sha256": binding_sha256,
        "candidate_index": candidate_index,
        "candidate_sha256": candidate_sha256,
        "candidate_feature_sha256": candidate_feature_sha256,
    }


def _claim_document(
    *,
    campaign_plan_sha256: str,
    trial_id: str,
    assignment_sha256: str,
    source_commit: str,
    exact_ci_run: int,
    exact_ci_attempt: int,
    execution_contract_sha256: str,
    dose_sha256: str,
) -> dict[str, object]:
    return {
        "schema": RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_CLAIM_SCHEMA,
        "campaign_plan_sha256": campaign_plan_sha256,
        "trial_id": trial_id,
        "assignment_sha256": assignment_sha256,
        "source_commit": source_commit,
        "exact_ci_run": exact_ci_run,
        "exact_ci_attempt": exact_ci_attempt,
        "execution_contract_sha256": execution_contract_sha256,
        "dose_sha256": dose_sha256,
        "controller_actions_before_claim": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "retry_after_controller_input": False,
        "private_path_fields": 0,
    }


def _trial_id(assignment_sha256: str) -> str:
    return f"red-party-outcome-v1-{assignment_sha256[:40]}"


def _require_digest(value: object, *, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PartyDevelopmentOutcomeCampaignError(
            f"party-development outcome {subject} digest is invalid"
        )


__all__ = [
    "RED_PARTY_DEVELOPMENT_OUTCOME_ASSIGNMENT_SCHEMA",
    "RED_PARTY_DEVELOPMENT_OUTCOME_CAMPAIGN_SCHEMA",
    "RED_PARTY_DEVELOPMENT_OUTCOME_CAMPAIGN_SUMMARY_SCHEMA",
    "RED_PARTY_DEVELOPMENT_OUTCOME_DOSE",
    "RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT",
    "RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT_SHA256",
    "RED_PARTY_DEVELOPMENT_OUTCOME_QUESTION_COUNT",
    "RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_CLAIM_SCHEMA",
    "RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT",
    "PartyDevelopmentOutcomeCampaignError",
    "PartyDevelopmentOutcomeCampaignPlan",
    "PartyDevelopmentOutcomeDose",
    "PartyDevelopmentOutcomeTrialAssignment",
    "PartyDevelopmentOutcomeTrialClaim",
    "freeze_party_development_outcome_campaign",
]
