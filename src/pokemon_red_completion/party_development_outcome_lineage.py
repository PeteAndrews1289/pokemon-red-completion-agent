"""Fail-closed lineage recovery for one-shot party outcome campaigns.

A changed executable can never resume an old frozen plan.  Instead, a successor
binds the exact predecessor plan plus every immutable claim/terminal pair that
predecessor (or an earlier ancestor) consumed.  Only assignments absent from
that lineage remain claimable.
"""

from __future__ import annotations

from collections.abc import Mapping

from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeCampaignPlan,
    PartyDevelopmentOutcomeCampaignPredecessor,
    PartyDevelopmentOutcomeInheritedTerminal,
    PartyDevelopmentOutcomeTrialAssignment,
    PartyDevelopmentOutcomeTrialClaim,
    party_development_outcome_record_ids,
)
from pokemon_red_completion.party_development_outcome_results import (
    PartyDevelopmentOutcomeTrialResult,
    parse_party_development_trial_terminal,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
)

PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND = "party_development_outcome_claim"
PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND = "party_development_outcome_terminal"


class PartyDevelopmentOutcomeLineageError(RuntimeError):
    """Raised before a successor can omit, alter, or rerun consumed evidence."""


def inspect_predecessor_campaign(
    predecessor_plan: PartyDevelopmentOutcomeCampaignPlan,
    *,
    predecessor_plan_file_sha256: str,
    store: PrivateArtifactRoot,
) -> tuple[
    PartyDevelopmentOutcomeCampaignPredecessor,
    tuple[PartyDevelopmentOutcomeInheritedTerminal, ...],
]:
    """Reconstruct the complete consumed lineage from immutable private records."""

    if not isinstance(predecessor_plan, PartyDevelopmentOutcomeCampaignPlan):
        raise TypeError("predecessor_plan must be a campaign plan")
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("store must be a PrivateArtifactRoot")
    predecessor = PartyDevelopmentOutcomeCampaignPredecessor.build(
        predecessor_plan,
        plan_file_sha256=predecessor_plan_file_sha256,
    )
    inherited: list[PartyDevelopmentOutcomeInheritedTerminal] = []
    for entry in predecessor_plan.inherited_terminals:
        _open_inherited_terminal(entry, store=store)
        inherited.append(entry)

    newly_consumed = 0
    for assignment in predecessor_plan.active_assignments:
        claim_id, terminal_id = party_development_outcome_record_ids(
            predecessor_plan, assignment
        )
        claim_record = store.find_sealed_record(
            claim_id,
            expected_kind=PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND,
        )
        terminal_record = store.find_sealed_record(
            terminal_id,
            expected_kind=PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND,
        )
        if terminal_record is not None and claim_record is None:
            raise PartyDevelopmentOutcomeLineageError(
                "predecessor terminal exists without its durable claim"
            )
        if claim_record is not None and terminal_record is None:
            raise PartyDevelopmentOutcomeLineageError(
                "predecessor has an open claim; retain a censored terminal before succession"
            )
        if claim_record is None:
            continue
        assert terminal_record is not None
        inherited.append(
            _inherit_direct_terminal(
                predecessor_plan,
                assignment,
                claim_record=claim_record,
                terminal_record=terminal_record,
            )
        )
        newly_consumed += 1
    if newly_consumed == 0:
        raise PartyDevelopmentOutcomeLineageError(
            "successor requires at least one newly consumed predecessor trial"
        )
    ordinal_by_assignment = {
        item.assignment_sha256: item.ordinal for item in predecessor_plan.assignments
    }
    inherited.sort(key=lambda item: ordinal_by_assignment[item.assignment_sha256])
    if len({item.assignment_sha256 for item in inherited}) != len(inherited):
        raise PartyDevelopmentOutcomeLineageError(
            "predecessor lineage repeats a consumed assignment"
        )
    return predecessor, tuple(inherited)


def validate_successor_campaign_lineage(
    plan: PartyDevelopmentOutcomeCampaignPlan,
    predecessor_plan: PartyDevelopmentOutcomeCampaignPlan,
    *,
    predecessor_plan_file_sha256: str,
    store: PrivateArtifactRoot,
) -> tuple[PartyDevelopmentOutcomeTrialResult, ...]:
    """Rebuild a successor's lineage and return its authenticated old results."""

    if not plan.is_successor or plan.predecessor is None:
        raise PartyDevelopmentOutcomeLineageError(
            "campaign is not a provenance-bound successor"
        )
    if (
        plan.assignments != predecessor_plan.assignments
        or plan.frozen_catalog_file_sha256
        != predecessor_plan.frozen_catalog_file_sha256
        or plan.frozen_catalog_sha256 != predecessor_plan.frozen_catalog_sha256
        or plan.prospective_catalog_sha256
        != predecessor_plan.prospective_catalog_sha256
        or plan.frozen_catalog_source_commit
        != predecessor_plan.frozen_catalog_source_commit
        or plan.frozen_catalog_source_bundle_sha256
        != predecessor_plan.frozen_catalog_source_bundle_sha256
        or plan.rom_sha256 != predecessor_plan.rom_sha256
        or plan.input_audit_receipt_file_sha256
        != predecessor_plan.input_audit_receipt_file_sha256
        or plan.input_audit_result_sha256
        != predecessor_plan.input_audit_result_sha256
        or plan.dose != predecessor_plan.dose
        or plan.execution_contract_sha256
        != predecessor_plan.execution_contract_sha256
    ):
        raise PartyDevelopmentOutcomeLineageError(
            "successor changes the predecessor campaign denominator or dose"
        )
    expected_predecessor, expected_inherited = inspect_predecessor_campaign(
        predecessor_plan,
        predecessor_plan_file_sha256=predecessor_plan_file_sha256,
        store=store,
    )
    if (
        plan.predecessor != expected_predecessor
        or plan.inherited_terminals != expected_inherited
    ):
        raise PartyDevelopmentOutcomeLineageError(
            "successor lineage differs from immutable predecessor records"
        )
    return open_inherited_campaign_results(plan, store=store)


def open_inherited_campaign_results(
    plan: PartyDevelopmentOutcomeCampaignPlan,
    *,
    store: PrivateArtifactRoot,
) -> tuple[PartyDevelopmentOutcomeTrialResult, ...]:
    """Open every exact inherited terminal without consulting actor logic."""

    assignment_by_digest = {
        item.assignment_sha256: item for item in plan.assignments
    }
    results: list[PartyDevelopmentOutcomeTrialResult] = []
    for entry in plan.inherited_terminals:
        result = _open_inherited_terminal(entry, store=store)
        assignment = assignment_by_digest.get(entry.assignment_sha256)
        if assignment is None:
            raise PartyDevelopmentOutcomeLineageError(
                "inherited terminal is outside the successor assignments"
            )
        result.require_within_campaign_lineage(plan, assignment)
        results.append(result)
    return tuple(results)


def _inherit_direct_terminal(
    predecessor_plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
    *,
    claim_record: PrivateSealedRecord,
    terminal_record: PrivateSealedRecord,
) -> PartyDevelopmentOutcomeInheritedTerminal:
    claim = PartyDevelopmentOutcomeTrialClaim.from_private_dict(claim_record.read())
    if claim != PartyDevelopmentOutcomeTrialClaim.build(predecessor_plan, assignment):
        raise PartyDevelopmentOutcomeLineageError(
            "predecessor claim differs from its frozen assignment"
        )
    terminal_document = terminal_record.read()
    result = parse_party_development_trial_terminal(terminal_document)
    result.require_within_plan(predecessor_plan, assignment)
    terminal_sha256 = terminal_document.get("terminal_sha256")
    if not isinstance(terminal_sha256, str):
        raise PartyDevelopmentOutcomeLineageError(
            "predecessor terminal lacks its typed digest"
        )
    return PartyDevelopmentOutcomeInheritedTerminal.build(
        origin_campaign_plan_sha256=predecessor_plan.plan_sha256,
        trial_id=assignment.trial_id,
        assignment_sha256=assignment.assignment_sha256,
        candidate_index=assignment.candidate_index,
        status=result.status,
        claim_sha256=claim.claim_sha256,
        result_sha256=result.result_sha256,
        terminal_sha256=terminal_sha256,
        claim_record_id=claim_record.summary.record_id,
        claim_record_sha256=claim_record.summary.record_sha256,
        claim_manifest_sha256=claim_record.summary.manifest_sha256,
        terminal_record_id=terminal_record.summary.record_id,
        terminal_record_sha256=terminal_record.summary.record_sha256,
        terminal_manifest_sha256=terminal_record.summary.manifest_sha256,
    )


def _open_inherited_terminal(
    entry: PartyDevelopmentOutcomeInheritedTerminal,
    *,
    store: PrivateArtifactRoot,
) -> PartyDevelopmentOutcomeTrialResult:
    claim_record = store.find_sealed_record(
        entry.claim_record_id,
        expected_kind=PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND,
    )
    terminal_record = store.find_sealed_record(
        entry.terminal_record_id,
        expected_kind=PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND,
    )
    if claim_record is None or terminal_record is None:
        raise PartyDevelopmentOutcomeLineageError(
            "inherited campaign record is missing"
        )
    if (
        claim_record.summary.record_sha256 != entry.claim_record_sha256
        or claim_record.summary.manifest_sha256 != entry.claim_manifest_sha256
        or terminal_record.summary.record_sha256 != entry.terminal_record_sha256
        or terminal_record.summary.manifest_sha256
        != entry.terminal_manifest_sha256
    ):
        raise PartyDevelopmentOutcomeLineageError(
            "inherited sealed-record digest differs"
        )
    claim = PartyDevelopmentOutcomeTrialClaim.from_private_dict(claim_record.read())
    terminal_document = terminal_record.read()
    result = parse_party_development_trial_terminal(terminal_document)
    if not _entry_matches_records(entry, claim, result, terminal_document):
        raise PartyDevelopmentOutcomeLineageError(
            "inherited typed terminal differs from its lineage binding"
        )
    return result


def _entry_matches_records(
    entry: PartyDevelopmentOutcomeInheritedTerminal,
    claim: PartyDevelopmentOutcomeTrialClaim,
    result: PartyDevelopmentOutcomeTrialResult,
    terminal_document: Mapping[str, object],
) -> bool:
    return (
        claim.campaign_plan_sha256 == entry.origin_campaign_plan_sha256
        and claim.trial_id == entry.trial_id
        and claim.assignment_sha256 == entry.assignment_sha256
        and claim.claim_sha256 == entry.claim_sha256
        and result.campaign_plan_sha256 == entry.origin_campaign_plan_sha256
        and result.trial_id == entry.trial_id
        and result.assignment_sha256 == entry.assignment_sha256
        and result.candidate_index == entry.candidate_index
        and result.status is entry.status
        and result.claim_sha256 == entry.claim_sha256
        and result.result_sha256 == entry.result_sha256
        and terminal_document.get("terminal_sha256") == entry.terminal_sha256
    )


__all__ = [
    "PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND",
    "PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND",
    "PartyDevelopmentOutcomeLineageError",
    "inspect_predecessor_campaign",
    "open_inherited_campaign_results",
    "validate_successor_campaign_lineage",
]
