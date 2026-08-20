from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_party_development_outcome_dataset import _frozen_input_catalog

from pokemon_red_completion.party_development_outcome_campaign import (
    RED_PARTY_DEVELOPMENT_OUTCOME_DOSE,
    RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT,
    RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT_SHA256,
    PartyDevelopmentOutcomeCampaignError,
    PartyDevelopmentOutcomeCampaignPlan,
    PartyDevelopmentOutcomeDose,
    PartyDevelopmentOutcomeTrialAssignment,
    PartyDevelopmentOutcomeTrialClaim,
    freeze_party_development_outcome_campaign,
)
from pokemon_red_completion.provenance import canonical_sha256

_WIDTHS = (6, 2, 6, 2, 6, 2, 6, 2, 5, 2, 6, 2, 6, 2)


def _plan() -> PartyDevelopmentOutcomeCampaignPlan:
    return freeze_party_development_outcome_campaign(
        _frozen_input_catalog(candidate_widths=_WIDTHS),
        source_commit="e" * 40,
        source_bundle_sha256="f" * 64,
        runner_source_sha256="0" * 64,
        exact_ci_run=31973374921,
        exact_ci_attempt=1,
        frozen_catalog_file_sha256="1" * 64,
        input_audit_receipt_file_sha256="2" * 64,
        input_audit_result_sha256="3" * 64,
    )


def test_campaign_expands_fourteen_questions_into_fifty_five_trials() -> None:
    plan = _plan()

    assert len(plan.assignments) == 55
    assert len({item.scenario_id for item in plan.assignments}) == 14
    assert len({item.trial_id for item in plan.assignments}) == 55
    assert tuple(item.ordinal for item in plan.assignments) == tuple(range(1, 56))
    assert sum(item.partition.value == "train" for item in plan.assignments) == 32
    assert sum(item.partition.value == "development" for item in plan.assignments) == 23

    summary = plan.public_summary()
    assert summary["question_partition_counts"] == {"development": 6, "train": 8}
    assert summary["trial_partition_counts"] == {"development": 23, "train": 32}
    assert summary["candidate_width_counts"] == {"2": 7, "5": 1, "6": 6}
    assert summary["candidate_trial_count"] == 55
    assert summary["complete_examples"] == 0
    assert summary["execution_authorized"] is False


def test_campaign_plan_round_trips_with_no_opened_outcomes() -> None:
    plan = _plan()
    document = plan.private_dict()
    restored = PartyDevelopmentOutcomeCampaignPlan.from_private_dict(document)

    assert restored == plan
    assert restored.plan_sha256 == plan.plan_sha256
    encoded = json.dumps(restored.public_summary(), sort_keys=True)
    assert "candidate.hp_ratio" not in encoded
    assert "source-profile" not in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert restored.public_summary()["teacher_queries"] == 0
    assert restored.public_summary()["model_predictions"] == 0


def test_campaign_plan_is_deterministic_for_the_same_catalog() -> None:
    first = _plan()
    second = _plan()

    assert first == second
    assert first.plan_sha256 == second.plan_sha256
    assert [item.trial_id for item in first.assignments] == [
        item.trial_id for item in second.assignments
    ]


def test_campaign_refuses_to_hide_a_smaller_candidate_denominator() -> None:
    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="55 ordered trials"):
        freeze_party_development_outcome_campaign(
            _frozen_input_catalog(),
            source_commit="e" * 40,
            source_bundle_sha256="f" * 64,
            runner_source_sha256="0" * 64,
            exact_ci_run=1,
            exact_ci_attempt=1,
            frozen_catalog_file_sha256="1" * 64,
            input_audit_receipt_file_sha256="2" * 64,
            input_audit_result_sha256="3" * 64,
        )


def test_assignment_round_trip_recomputes_both_hash_and_trial_identity() -> None:
    assignment = _plan().assignments[0]
    restored = PartyDevelopmentOutcomeTrialAssignment.from_private_dict(
        assignment.private_dict()
    )

    assert restored == assignment

    changed = assignment.private_dict()
    changed["candidate_index"] = 1
    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="digest differs"):
        PartyDevelopmentOutcomeTrialAssignment.from_private_dict(changed)


def test_rehashed_assignment_cannot_leave_its_frozen_question() -> None:
    plan = _plan()
    assignments = list(plan.assignments)
    original = assignments[1]
    forged = PartyDevelopmentOutcomeTrialAssignment.build(
        ordinal=original.ordinal,
        scenario_id=original.scenario_id,
        root_lineage_id="alien-root",
        initial_state_sha256=original.initial_state_sha256,
        partition=original.partition,
        kind=original.kind,
        goal=original.goal,
        binding_sha256=original.binding_sha256,
        candidate_index=original.candidate_index,
        candidate_sha256=original.candidate_sha256,
        candidate_feature_sha256=original.candidate_feature_sha256,
    )
    assignments[1] = forged

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="one frozen start"):
        replace(plan, assignments=tuple(assignments))


def test_campaign_rejects_duplicate_trial_id_even_when_count_stays_fifty_five() -> None:
    plan = _plan()
    assignments = list(plan.assignments)
    assignments[-1] = assignments[0]

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="ordered trials"):
        replace(plan, assignments=tuple(assignments))


def test_campaign_rejects_nonzero_or_rewritten_prospective_counters() -> None:
    document = _plan().private_dict()
    document["trial_claims"] = 1

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="document is invalid"):
        PartyDevelopmentOutcomeCampaignPlan.from_private_dict(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trial_claims", False),
        ("private_path_fields", False),
    ],
)
def test_campaign_rejects_boolean_zero_counter_substitutions(
    field: str,
    value: bool,
) -> None:
    document = _plan().private_dict()
    document[field] = value

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="document is invalid"):
        PartyDevelopmentOutcomeCampaignPlan.from_private_dict(document)


def test_campaign_rejects_ignored_fields_hidden_inside_its_dose() -> None:
    document = _plan().private_dict()
    dose = document["dose"]
    assert isinstance(dose, dict)
    dose["private_note"] = "ignored-field"

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="dose document"):
        PartyDevelopmentOutcomeCampaignPlan.from_private_dict(document)


def test_campaign_rejects_rehashed_plan_with_changed_execution_contract() -> None:
    document = _plan().private_dict()
    contract = document["execution_contract"]
    assert isinstance(contract, dict)
    contract["retry_after_any_controller_input"] = True
    document["execution_contract_sha256"] = canonical_sha256(contract)
    document.pop("plan_sha256")

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="document is invalid"):
        PartyDevelopmentOutcomeCampaignPlan.from_private_dict(
            {**document, "plan_sha256": "0" * 64}
        )


def test_trial_claim_binds_plan_assignment_ci_contract_and_dose() -> None:
    plan = _plan()
    assignment = plan.assignments[17]
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)

    assert claim.campaign_plan_sha256 == plan.plan_sha256
    assert claim.trial_id == assignment.trial_id
    assert claim.assignment_sha256 == assignment.assignment_sha256
    assert claim.exact_ci_run == plan.exact_ci_run
    assert claim.exact_ci_attempt == plan.exact_ci_attempt
    assert claim.execution_contract_sha256 == (
        RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT_SHA256
    )
    assert claim.dose_sha256 == RED_PARTY_DEVELOPMENT_OUTCOME_DOSE.dose_sha256
    assert claim.private_dict()["controller_actions_before_claim"] == 0
    assert claim.private_dict()["retry_after_controller_input"] is False

    restored = PartyDevelopmentOutcomeTrialClaim.from_private_dict(
        claim.private_dict()
    )
    assert restored == claim


def test_trial_claim_parser_rejects_a_rewritten_nonretry_guard() -> None:
    plan = _plan()
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, plan.assignments[0])
    document = claim.private_dict()
    document["retry_after_controller_input"] = True

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="document is invalid"):
        PartyDevelopmentOutcomeTrialClaim.from_private_dict(document)


def test_trial_claim_parser_rejects_boolean_zero_counter_substitution() -> None:
    plan = _plan()
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, plan.assignments[0])
    document = claim.private_dict()
    document["controller_actions_before_claim"] = False

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="document is invalid"):
        PartyDevelopmentOutcomeTrialClaim.from_private_dict(document)


def test_trial_claim_rejects_an_assignment_from_another_plan() -> None:
    plan = _plan()
    source = plan.assignments[0]
    foreign = PartyDevelopmentOutcomeTrialAssignment.build(
        ordinal=56,
        scenario_id=source.scenario_id,
        root_lineage_id=source.root_lineage_id,
        initial_state_sha256=source.initial_state_sha256,
        partition=source.partition,
        kind=source.kind,
        goal=source.goal,
        binding_sha256=source.binding_sha256,
        candidate_index=source.candidate_index,
        candidate_sha256=source.candidate_sha256,
        candidate_feature_sha256=source.candidate_feature_sha256,
    )

    with pytest.raises(PartyDevelopmentOutcomeCampaignError):
        PartyDevelopmentOutcomeTrialClaim.build(plan, foreign)


def test_trial_claim_detects_post_build_mutation() -> None:
    plan = _plan()
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, plan.assignments[0])

    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="claim differs"):
        replace(claim, exact_ci_run=claim.exact_ci_run + 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("completed_battles", 0),
        ("maximum_encounter_steps", 0),
        ("maximum_controller_actions", -1),
        ("maximum_frames", 0),
        ("maximum_healing_trips", 0),
        ("maximum_rotations", 0),
        ("maximum_faints", 1),
    ],
)
def test_outcome_dose_rejects_unbounded_or_faint_permitting_variants(
    field: str,
    value: int,
) -> None:
    values = {
        "completed_battles": 4,
        "maximum_encounter_steps": 2_500,
        "maximum_controller_actions": 100_000,
        "maximum_frames": 1_500_000,
        "maximum_healing_trips": 4,
        "maximum_rotations": 16,
        "maximum_faints": 0,
    }
    values[field] = value

    with pytest.raises(PartyDevelopmentOutcomeCampaignError):
        PartyDevelopmentOutcomeDose(**values)


def test_execution_contract_names_failure_interruption_and_nonretry_rules() -> None:
    contract = RED_PARTY_DEVELOPMENT_OUTCOME_EXECUTION_CONTRACT

    assert contract["retry_after_any_controller_input"] is False
    assert "invalid" in str(contract["failure_rule"])
    assert "censored" in str(contract["interruption_rule"])
    assert "never_previously_claimed" in str(contract["campaign_recovery_rule"])
    assert "every_available_candidate" in str(contract["preference_rule"])
    assert contract["partition_rule"] == "fit_train_only_and_never_tune_on_development"
