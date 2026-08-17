from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_party_development_outcome_campaign import _WIDTHS, _plan
from test_party_development_outcome_dataset import _frozen_input_catalog

from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeCampaignError,
    PartyDevelopmentOutcomeCampaignPlan,
    PartyDevelopmentOutcomeInheritedTerminal,
    PartyDevelopmentOutcomeTrialAssignment,
    PartyDevelopmentOutcomeTrialClaim,
    freeze_party_development_outcome_campaign,
    party_development_outcome_record_ids,
)
from pokemon_red_completion.party_development_outcome_lineage import (
    PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND,
    PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND,
    PartyDevelopmentOutcomeLineageError,
    inspect_predecessor_campaign,
    open_inherited_campaign_results,
    validate_successor_campaign_lineage,
)
from pokemon_red_completion.party_development_outcome_results import (
    PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
    PartyDevelopmentOutcomeTrialResult,
    assemble_party_development_outcome_examples,
    build_party_development_trial_terminal,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    initialize_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_outcomes import OutcomeEvidenceStatus


def _store(tmp_path: Path) -> PrivateArtifactRoot:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()
    return initialize_private_root(
        private,
        repository_root=repository,
        allow_same_device=True,
        git_worktree_probe=lambda _path: False,
    )


def _publish_invalid(
    store: PrivateArtifactRoot,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> PartyDevelopmentOutcomeTrialResult:
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    claim_id, terminal_id = party_development_outcome_record_ids(plan, assignment)
    store.publish_sealed_record(
        claim_id,
        kind=PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND,
        record=claim.private_dict(),
    )
    evidence = {
        "schema": PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
        "campaign_plan_sha256": plan.plan_sha256,
        "trial_id": assignment.trial_id,
        "assignment_sha256": assignment.assignment_sha256,
        "claim_sha256": claim.claim_sha256,
        "candidate_index": assignment.candidate_index,
        "status": OutcomeEvidenceStatus.INVALID.value,
        "failure_code": "execution_error",
        "retry_after_controller_input": False,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    result = PartyDevelopmentOutcomeTrialResult.build(
        plan,
        assignment,
        claim,
        status=OutcomeEvidenceStatus.INVALID,
        evidence_sha256=canonical_sha256(evidence),
        failure_code="execution_error",
    )
    store.publish_sealed_record(
        terminal_id,
        kind=PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND,
        record=build_party_development_trial_terminal(result, evidence=evidence),
    )
    return result


def _successor(
    predecessor_plan: PartyDevelopmentOutcomeCampaignPlan,
    store: PrivateArtifactRoot,
) -> PartyDevelopmentOutcomeCampaignPlan:
    predecessor, inherited = inspect_predecessor_campaign(
        predecessor_plan,
        predecessor_plan_file_sha256="9" * 64,
        store=store,
    )
    return freeze_party_development_outcome_campaign(
        _frozen_input_catalog(candidate_widths=_WIDTHS),
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        runner_source_sha256="c" * 64,
        exact_ci_run=31978843671,
        exact_ci_attempt=1,
        frozen_catalog_file_sha256="1" * 64,
        input_audit_receipt_file_sha256="2" * 64,
        input_audit_result_sha256="3" * 64,
        predecessor=predecessor,
        inherited_terminals=inherited,
    )


def test_successor_round_trip_retires_the_consumed_trial_and_keeps_denominator(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    predecessor_plan = _plan()
    consumed = _publish_invalid(store, predecessor_plan, predecessor_plan.assignments[0])

    successor = _successor(predecessor_plan, store)
    restored = PartyDevelopmentOutcomeCampaignPlan.from_private_dict(
        successor.private_dict()
    )

    assert restored == successor
    assert len(successor.assignments) == 55
    assert len(successor.active_assignments) == 54
    assert successor.inherited_terminals[0].result_sha256 == consumed.result_sha256
    assert successor.public_summary()["trial_claims"] == 1
    assert successor.public_summary()["invalid_trials"] == 1
    assert successor.public_summary()["remaining_candidate_trials"] == 54
    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="already consumed"):
        PartyDevelopmentOutcomeTrialClaim.build(
            successor, successor.assignments[0]
        )
    assert party_development_outcome_record_ids(
        successor, successor.assignments[1]
    ) != party_development_outcome_record_ids(
        predecessor_plan, predecessor_plan.assignments[1]
    )

    boolean_counter = successor.private_dict()
    boolean_counter["trial_claims"] = True
    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="document"):
        PartyDevelopmentOutcomeCampaignPlan.from_private_dict(boolean_counter)


def test_successor_assembly_accepts_only_the_exact_inherited_result(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    predecessor_plan = _plan()
    result = _publish_invalid(store, predecessor_plan, predecessor_plan.assignments[0])
    successor = _successor(predecessor_plan, store)

    inherited = validate_successor_campaign_lineage(
        successor,
        predecessor_plan,
        predecessor_plan_file_sha256="9" * 64,
        store=store,
    )
    examples = assemble_party_development_outcome_examples(
        _frozen_input_catalog(candidate_widths=_WIDTHS),
        successor,
        inherited,
    )

    assert inherited == (result,)
    assert examples[0].outcomes[0] is not None
    assert examples[0].outcomes[0].status is OutcomeEvidenceStatus.INVALID
    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="lineage"):
        replace(successor, inherited_terminals=())


def test_successor_chain_carries_old_and_new_consumed_trials_without_retry(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    first = _plan()
    _publish_invalid(store, first, first.assignments[0])
    second = _successor(first, store)
    _publish_invalid(store, second, second.active_assignments[0])

    predecessor, inherited = inspect_predecessor_campaign(
        second,
        predecessor_plan_file_sha256="8" * 64,
        store=store,
    )

    assert predecessor.plan_sha256 == second.plan_sha256
    assert len(inherited) == 2
    assert {item.origin_campaign_plan_sha256 for item in inherited} == {
        first.plan_sha256,
        second.plan_sha256,
    }
    assert len({item.assignment_sha256 for item in inherited}) == 2
    third = freeze_party_development_outcome_campaign(
        _frozen_input_catalog(candidate_widths=_WIDTHS),
        source_commit="d" * 40,
        source_bundle_sha256="e" * 64,
        runner_source_sha256="f" * 64,
        exact_ci_run=31978843672,
        exact_ci_attempt=1,
        frozen_catalog_file_sha256="1" * 64,
        input_audit_receipt_file_sha256="2" * 64,
        input_audit_result_sha256="3" * 64,
        predecessor=predecessor,
        inherited_terminals=inherited,
    )
    still_active = third.active_assignments[0]
    assert party_development_outcome_record_ids(
        second, still_active
    ) != party_development_outcome_record_ids(third, still_active)
    with pytest.raises(PartyDevelopmentOutcomeCampaignError, match="already consumed"):
        PartyDevelopmentOutcomeTrialClaim.build(third, second.active_assignments[0])


def test_successor_refuses_an_open_claim_and_rehashed_lineage_mutation(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    assignment = plan.assignments[0]
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    claim_id, _ = party_development_outcome_record_ids(plan, assignment)
    store.publish_sealed_record(
        claim_id,
        kind=PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND,
        record=claim.private_dict(),
    )

    with pytest.raises(PartyDevelopmentOutcomeLineageError, match="open claim"):
        inspect_predecessor_campaign(
            plan,
            predecessor_plan_file_sha256="9" * 64,
            store=store,
        )

    terminal_result = _publish_invalid_after_existing_claim(store, plan, assignment)
    successor = _successor(plan, store)
    entry_document = successor.inherited_terminals[0].private_dict()
    entry_document["result_sha256"] = "f" * 64
    entry_document["inherited_terminal_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in entry_document.items()
            if key != "inherited_terminal_sha256"
        }
    )
    changed = PartyDevelopmentOutcomeInheritedTerminal.from_private_dict(
        entry_document
    )
    forged = replace(successor, inherited_terminals=(changed,))
    with pytest.raises(
        PartyDevelopmentOutcomeLineageError,
        match="immutable predecessor",
    ):
        validate_successor_campaign_lineage(
            forged,
            plan,
            predecessor_plan_file_sha256="9" * 64,
            store=store,
        )
    assert terminal_result.status is OutcomeEvidenceStatus.INVALID


def _publish_invalid_after_existing_claim(
    store: PrivateArtifactRoot,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> PartyDevelopmentOutcomeTrialResult:
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    _, terminal_id = party_development_outcome_record_ids(plan, assignment)
    evidence = {
        "schema": PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
        "campaign_plan_sha256": plan.plan_sha256,
        "trial_id": assignment.trial_id,
        "assignment_sha256": assignment.assignment_sha256,
        "claim_sha256": claim.claim_sha256,
        "candidate_index": assignment.candidate_index,
        "status": OutcomeEvidenceStatus.INVALID.value,
        "failure_code": "execution_error",
        "retry_after_controller_input": False,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    result = PartyDevelopmentOutcomeTrialResult.build(
        plan,
        assignment,
        claim,
        status=OutcomeEvidenceStatus.INVALID,
        evidence_sha256=canonical_sha256(evidence),
        failure_code="execution_error",
    )
    store.publish_sealed_record(
        terminal_id,
        kind=PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND,
        record=build_party_development_trial_terminal(result, evidence=evidence),
    )
    return result


def test_open_inherited_results_rejects_a_different_store(tmp_path: Path) -> None:
    store = _store(tmp_path / "first")
    plan = _plan()
    _publish_invalid(store, plan, plan.assignments[0])
    successor = _successor(plan, store)
    other = _store(tmp_path / "second")

    with pytest.raises(PartyDevelopmentOutcomeLineageError, match="missing"):
        open_inherited_campaign_results(successor, store=other)
