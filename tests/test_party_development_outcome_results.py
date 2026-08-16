from __future__ import annotations

from dataclasses import replace

import pytest
from test_party_development_outcome_campaign import _WIDTHS, _plan
from test_party_development_outcome_dataset import _frozen_input_catalog

from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeTrialClaim,
)
from pokemon_red_completion.party_development_outcome_results import (
    PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
    PartyDevelopmentOutcomeResultError,
    PartyDevelopmentOutcomeTrialResult,
    assemble_party_development_outcome_examples,
    build_party_development_trial_terminal,
    parse_party_development_trial_terminal,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_outcomes import OutcomeEvidenceStatus


def _result(
    ordinal: int = 1,
    *,
    status: OutcomeEvidenceStatus = OutcomeEvidenceStatus.MEASURED,
) -> tuple[PartyDevelopmentOutcomeTrialResult, dict[str, object]]:
    plan = _plan()
    assignment = plan.assignments[ordinal - 1]
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    measured = status is OutcomeEvidenceStatus.MEASURED
    evidence = {
        "schema": PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
        "campaign_plan_sha256": plan.plan_sha256,
        "trial_id": assignment.trial_id,
        "assignment_sha256": assignment.assignment_sha256,
        "claim_sha256": claim.claim_sha256,
        "candidate_index": assignment.candidate_index,
        "status": status.value,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    if measured:
        evidence.update(
            {
                "semantic_actions": 6,
                "controller_actions": 400,
                "frames_executed": 40_000,
                "criterion_values": [float(index) for index in range(15)],
                "evolution_completed": False,
                "before_party": {},
                "after_party": {},
                "before_completion": {},
                "after_completion": {},
                "outcome_evidence_sha256": "2" * 64,
                "execution": {
                    "battles_completed": 4,
                    "steps_taken": 24,
                    "healing_trips": 1,
                    "rotations_executed": 1,
                    "faints": 0,
                },
            }
        )
    else:
        evidence.update(
            {
                "failure_code": "process_interrupted",
                "retry_after_controller_input": False,
            }
        )
        if status is OutcomeEvidenceStatus.CENSORED:
            evidence["measurements_recovered"] = False
    result = PartyDevelopmentOutcomeTrialResult.build(
        plan,
        assignment,
        claim,
        status=status,
        evidence_sha256=canonical_sha256(evidence),
        criterion_values=(tuple(float(index) for index in range(15)) if measured else ()),
        semantic_actions=6 if measured else None,
        controller_actions=400 if measured else None,
        frames_executed=40_000 if measured else None,
        battles_completed=4 if measured else None,
        encounter_steps=24 if measured else None,
        healing_trips=1 if measured else None,
        rotations_executed=1 if measured else None,
        faints=0 if measured else None,
        evolution_completed=False if measured else None,
        failure_code=None if measured else "process_interrupted",
    )
    return result, evidence


def test_measured_result_round_trips_and_terminal_binds_private_evidence() -> None:
    result, evidence = _result()
    restored = PartyDevelopmentOutcomeTrialResult.from_private_dict(
        result.private_dict()
    )
    terminal = build_party_development_trial_terminal(result, evidence=evidence)

    assert restored == result
    assert parse_party_development_trial_terminal(terminal) == result
    assert result.candidate_outcome().status is OutcomeEvidenceStatus.MEASURED
    assert result.battles_completed == 4


def test_terminal_rejects_different_evidence_even_when_result_is_valid() -> None:
    result, _evidence = _result()

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="evidence"):
        build_party_development_trial_terminal(
            result,
            evidence={"schema": "different"},
        )


def test_result_digest_detects_post_build_counter_mutation() -> None:
    result, _evidence = _result()

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="digest differs"):
        replace(result, controller_actions=401)


def test_unmeasured_result_rejects_recovered_measurements() -> None:
    plan = _plan()
    assignment = plan.assignments[0]
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="has measurements"):
        PartyDevelopmentOutcomeTrialResult.build(
            plan,
            assignment,
            claim,
            status=OutcomeEvidenceStatus.INVALID,
            evidence_sha256="1" * 64,
            controller_actions=1,
            failure_code="execution_error",
        )


def test_result_rejects_a_rehashed_wrong_claim_for_the_frozen_plan() -> None:
    result, _evidence = _result()
    plan = _plan()
    assignment = plan.assignments[0]
    document = result.private_dict()
    document["claim_sha256"] = "1" * 64
    document["result_sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "result_sha256"}
    )
    tampered = PartyDevelopmentOutcomeTrialResult.from_private_dict(document)

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="crosses"):
        tampered.require_within_plan(plan, assignment)


def test_result_builder_rejects_a_self_consistent_but_wrong_claim() -> None:
    plan = _plan()
    assignment = plan.assignments[0]
    expected = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    forged = replace(
        expected,
        source_commit="1" * 40,
        claim_sha256=canonical_sha256(
            {
                **expected._claim_document(),
                "source_commit": "1" * 40,
            }
        ),
    )

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="claim differ"):
        PartyDevelopmentOutcomeTrialResult.build(
            plan,
            assignment,
            forged,
            status=OutcomeEvidenceStatus.INVALID,
            evidence_sha256="1" * 64,
            failure_code="execution_error",
        )


def test_terminal_rejects_rehashed_evidence_that_contradicts_its_result() -> None:
    result, evidence = _result()
    changed = dict(evidence)
    changed["candidate_index"] = result.candidate_index + 1
    rebound = replace(
        result,
        evidence_sha256=canonical_sha256(changed),
        result_sha256=canonical_sha256(
            {
                **result._document(),
                "evidence_sha256": canonical_sha256(changed),
            }
        ),
    )

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="contradict"):
        build_party_development_trial_terminal(rebound, evidence=changed)


@pytest.mark.parametrize(
    ("mutation",),
    [
        ("boolean_candidate",),
        ("boolean_zero_counter",),
        ("boolean_execution_counter",),
        ("hidden_top_level_field",),
    ],
)
def test_terminal_rejects_rehashed_ambiguous_or_extra_evidence(
    mutation: str,
) -> None:
    result, evidence = _result()
    changed = dict(evidence)
    if mutation == "boolean_candidate":
        changed["candidate_index"] = False
    elif mutation == "boolean_zero_counter":
        changed["teacher_queries"] = False
    elif mutation == "boolean_execution_counter":
        execution = dict(changed["execution"])
        execution["faints"] = False
        changed["execution"] = execution
    else:
        changed["unexpected_field"] = "not allowed"
    evidence_sha256 = canonical_sha256(changed)
    rebound = replace(
        result,
        evidence_sha256=evidence_sha256,
        result_sha256=canonical_sha256(
            {
                **result._document(),
                "evidence_sha256": evidence_sha256,
            }
        ),
    )

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="contradict"):
        build_party_development_trial_terminal(rebound, evidence=changed)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("battles_completed", 3),
        ("encounter_steps", 2_501),
        ("controller_actions", 100_001),
        ("frames_executed", 1_500_001),
        ("healing_trips", 5),
        ("rotations_executed", 17),
        ("faints", 1),
    ],
)
def test_measured_result_rejects_every_fixed_dose_violation(
    field: str,
    value: int,
) -> None:
    plan = _plan()
    assignment = plan.assignments[0]
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    evidence = {"schema": "test.evidence.v1", "field": field}
    values = {
        "semantic_actions": 6,
        "controller_actions": 400,
        "frames_executed": 40_000,
        "battles_completed": 4,
        "encounter_steps": 24,
        "healing_trips": 1,
        "rotations_executed": 1,
        "faints": 0,
    }
    values[field] = value

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="fixed dose"):
        PartyDevelopmentOutcomeTrialResult.build(
            plan,
            assignment,
            claim,
            status=OutcomeEvidenceStatus.MEASURED,
            evidence_sha256=canonical_sha256(evidence),
            criterion_values=tuple(float(index) for index in range(15)),
            evolution_completed=False,
            **values,
        )


def test_recovered_interruption_has_no_measurements_and_never_becomes_a_target() -> None:
    result, evidence = _result(status=OutcomeEvidenceStatus.CENSORED)

    terminal = build_party_development_trial_terminal(result, evidence=evidence)
    restored = parse_party_development_trial_terminal(terminal)

    assert restored.status is OutcomeEvidenceStatus.CENSORED
    assert restored.criterion_values == ()
    assert restored.controller_actions is None
    assert not restored.candidate_outcome().measured


def test_assembler_keeps_partial_question_incomplete() -> None:
    plan = _plan()
    catalog = _frozen_input_catalog(candidate_widths=_WIDTHS)
    first, _evidence = _result(1)

    examples = assemble_party_development_outcome_examples(
        catalog,
        plan,
        (first,),
    )

    assert len(examples) == 14
    first_question = next(
        item for item in examples if item.scenario_id == plan.assignments[0].scenario_id
    )
    assert not first_question.fully_measured
    assert not first_question.learner_update_eligible


def test_assembler_reconstructs_all_fourteen_complete_examples_from_fifty_five_rows() -> None:
    plan = _plan()
    catalog = _frozen_input_catalog(candidate_widths=_WIDTHS)
    results = tuple(_result(ordinal)[0] for ordinal in range(1, 56))

    examples = assemble_party_development_outcome_examples(catalog, plan, results)

    assert len(examples) == 14
    assert all(item.fully_measured for item in examples)
    assert sum(len(item.available_candidate_indices) for item in examples) == 55


def test_assembler_rejects_duplicate_terminal_for_one_assignment() -> None:
    plan = _plan()
    catalog = _frozen_input_catalog(candidate_widths=_WIDTHS)
    first, _evidence = _result(1)

    with pytest.raises(PartyDevelopmentOutcomeResultError, match="repeat"):
        assemble_party_development_outcome_examples(
            catalog,
            plan,
            (first, first),
        )
