from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorError,
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorEvidence,
    VenuePriorMeasurementContract,
    VenuePriorObservation,
    VenuePriorOperationalContract,
    VenuePriorSourceCompatibilityAttestation,
    VenuePriorUnitRatio,
    compose_venue_prior_evidence,
)
from pokemon_red_completion.team_training import GrindingArea


def _area(name: str, minimum: int, maximum: int) -> GrindingArea:
    return GrindingArea(
        area_id=name,
        minimum_encounter_level=minimum,
        maximum_encounter_level=maximum,
        rare_maximum_encounter_level=maximum + 2,
        measured_samples=50,
    )


def _evidence(
    venue: GrindingArea,
    *,
    evidence_id: str,
    root: str,
    state: str,
    receipt: str,
) -> VenuePriorEvidence:
    return VenuePriorEvidence(
        evidence_id=evidence_id,
        venue=venue,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        measurement_contract_sha256="0" * 64,
        operational_contract_sha256="6" * 64,
        source_compatibility_sha256="5" * 64,
        support_root_lineage_ids=(root,),
        support_state_sha256=(state * 64,),
        outcome_receipt_sha256=(receipt * 64,),
        reliability=VenuePriorUnitRatio(9, 10),
        expected_yield=VenuePriorUnitRatio(7, 10),
        matchup_safety=VenuePriorUnitRatio(19, 20),
        travel_cost=VenuePriorUnitRatio(1, 4),
        recovery_cost=VenuePriorUnitRatio(1, 5),
    )


def _registry() -> PartyDevelopmentVenuePriorRegistry:
    first = _evidence(
        _area("private-route-a", 12, 18),
        evidence_id="prior-a",
        root="support-root-a",
        state="c",
        receipt="d",
    )
    second = _evidence(
        _area("private-cave-b", 18, 24),
        evidence_id="prior-b",
        root="support-root-b",
        state="e",
        receipt="f",
    )
    return PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit="1" * 40,
        source_bundle_sha256="2" * 64,
        entries=(first, second),
    )


def _operational_contract() -> VenuePriorOperationalContract:
    source_compatibility = _source_compatibility()
    return VenuePriorOperationalContract(
        contract_id="bounded-training-v1",
        policy_sha256="1" * 64,
        encounter_execution_sha256="2" * 64,
        recovery_execution_sha256="3" * 64,
        battle_timing_sha256="4" * 64,
        accounting_sha256="5" * 64,
        source_compatibility_sha256=(
            source_compatibility.source_compatibility_sha256
        ),
    )


def _source_compatibility() -> VenuePriorSourceCompatibilityAttestation:
    return VenuePriorSourceCompatibilityAttestation(
        attestation_id="bounded-training-source-v1",
        observed_commit="a" * 40,
        observed_source_bundle_sha256="b" * 64,
        current_commit="c" * 40,
        current_source_bundle_sha256="d" * 64,
        unchanged_elements_sha256="e" * 64,
        current_elements_sha256="f" * 64,
        waived_elements=("runtime-change-a",),
        waiver_allowlist_sha256="0" * 64,
    )


def _observation(
    *,
    root: str = "prior-root-a",
    state: str = "8",
    completed: bool = True,
    gained: int = 4,
    required: int = 4,
    battles: int = 10,
    faints: int = 0,
    travel: int = 1,
    recovery: int = 2,
    optional: int = 0,
    cleanup: int = 1,
) -> VenuePriorObservation:
    return VenuePriorObservation(
        root_lineage_id=root,
        initial_state_sha256=state * 64,
        outcome_receipt_sha256=("9" * 64,),
        objective_completed=completed,
        progress_units_gained=gained,
        progress_units_required=required,
        battles_completed=battles,
        faints=faints,
        venue_transition_trips=travel,
        required_recovery_trips=recovery,
        optional_recovery_trips=optional,
        cleanup_trips=cleanup,
        total_counted_center_routes=travel + recovery + optional + cleanup,
    )


def test_registry_round_trip_preserves_exact_priors_without_public_identity() -> None:
    registry = _registry()
    encoded = json.dumps(registry.public_dict(), sort_keys=True)

    assert "private-route-a" not in encoded
    assert "private-cave-b" not in encoded
    assert "support-root" not in encoded
    assert registry.public_dict()["entry_count"] == 2
    assert registry.public_dict()["outcomes_opened"] == 0

    restored = PartyDevelopmentVenuePriorRegistry.from_private_dict(registry.private_dict())
    assert restored == registry
    prior = restored.prior_for(
        _area("private-route-a", 12, 18),
        operational_contract_sha256="6" * 64,
    )
    assert prior.available
    assert prior.reliability == 0.9
    assert prior.expected_yield == 0.7
    assert prior.matchup_safety == 0.95
    assert prior.travel_cost == 0.25
    assert prior.recovery_cost == 0.2
    assert prior.support_count == 1


def test_prior_is_bound_to_the_complete_venue_band_not_only_its_name() -> None:
    registry = _registry()
    changed_band = replace(
        _area("private-route-a", 12, 18),
        maximum_encounter_level=19,
        rare_maximum_encounter_level=20,
    )

    assert (
        registry.prior_for(
            changed_band,
            operational_contract_sha256="6" * 64,
        ).available
        is False
    )
    assert registry.evidence_for(changed_band) is None


def test_prior_is_unavailable_after_its_operational_contract_changes() -> None:
    registry = _registry()

    assert (
        registry.prior_for(
            _area("private-route-a", 12, 18),
            operational_contract_sha256="7" * 64,
        ).available
        is False
    )


@pytest.mark.parametrize(
    ("root", "state", "match"),
    (
        ("support-root-a", "9" * 64, "root already supports"),
        ("fresh-root", "c" * 64, "state already supports"),
    ),
)
def test_candidate_context_cannot_reuse_prior_support(root: str, state: str, match: str) -> None:
    with pytest.raises(PartyDevelopmentVenuePriorError, match=match):
        _registry().require_scenario_is_independent(
            root_lineage_id=root,
            initial_state_sha256=state,
        )


def test_mutated_private_registry_digest_fails_closed() -> None:
    document = deepcopy(_registry().private_dict())
    entries = document["entries"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    measurements = first["measurements"]
    assert isinstance(measurements, dict)
    reliability = measurements["reliability"]
    assert isinstance(reliability, dict)
    reliability["numerator"] = 8

    with pytest.raises(PartyDevelopmentVenuePriorError, match="evidence digest"):
        PartyDevelopmentVenuePriorRegistry.from_private_dict(document)


def test_registry_rejects_duplicate_venue_and_evidence_bindings() -> None:
    first = _registry().entries[0]
    duplicate_venue = replace(
        first,
        evidence_id="different-id",
        support_root_lineage_ids=("different-root",),
        support_state_sha256=("8" * 64,),
        outcome_receipt_sha256=("7" * 64,),
    )

    with pytest.raises(PartyDevelopmentVenuePriorError, match="venue binding"):
        PartyDevelopmentVenuePriorRegistry.freeze(
            source_commit="1" * 40,
            source_bundle_sha256="2" * 64,
            entries=(first, duplicate_venue),
        )


def test_empty_registry_reports_absence_instead_of_inventing_a_prior() -> None:
    registry = PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit="1" * 40,
        source_bundle_sha256="2" * 64,
        entries=(),
    )

    assert (
        registry.prior_for(
            _area("unknown", 5, 8),
            operational_contract_sha256="6" * 64,
        ).available
        is False
    )
    assert registry.public_dict()["entry_count"] == 0


def test_typed_measurement_composes_exact_auditable_ratios() -> None:
    evidence = compose_venue_prior_evidence(
        evidence_id="composed-prior-a",
        venue=_area("private-route-a", 12, 18),
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        measurement_contract=VenuePriorMeasurementContract(),
        operational_contract=_operational_contract(),
        source_compatibility=_source_compatibility(),
        observations=(
            _observation(),
            _observation(
                root="prior-root-b",
                state="7",
                completed=False,
                gained=2,
                battles=5,
                faints=1,
                travel=0,
                recovery=1,
                optional=1,
                cleanup=2,
            ),
        ),
    )

    assert evidence.reliability == VenuePriorUnitRatio(1, 2)
    assert evidence.expected_yield == VenuePriorUnitRatio(6, 8)
    assert evidence.matchup_safety == VenuePriorUnitRatio(15, 16)
    assert evidence.travel_cost == VenuePriorUnitRatio(1, 16)
    assert evidence.recovery_cost == VenuePriorUnitRatio(4, 19)
    assert evidence.support_root_lineage_ids == ("prior-root-a", "prior-root-b")
    assert evidence.measurement_contract_sha256 == (
        VenuePriorMeasurementContract().measurement_contract_sha256
    )
    assert evidence.operational_contract_sha256 == (
        _operational_contract().operational_contract_sha256
    )


def test_cleanup_route_is_accounted_but_not_relabelled_as_recurring_recovery() -> None:
    evidence = compose_venue_prior_evidence(
        evidence_id="cleanup-prior",
        venue=_area("private-route-a", 12, 18),
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        measurement_contract=VenuePriorMeasurementContract(),
        operational_contract=_operational_contract(),
        source_compatibility=_source_compatibility(),
        observations=(_observation(recovery=0, optional=0, cleanup=5),),
    )

    assert evidence.recovery_cost == VenuePriorUnitRatio(0, 10)
    assert evidence.recovery_cost.value == 0.0


@pytest.mark.parametrize(
    ("field", "match"),
    (
        ("incomplete_progress", "must deliver its bounded progress"),
        ("incomplete_center_accounting", "accounting is incomplete"),
    ),
)
def test_observation_rejects_semantic_accounting_drift(field: str, match: str) -> None:
    values = {
        "root_lineage_id": "prior-root-a",
        "initial_state_sha256": "8" * 64,
        "outcome_receipt_sha256": ("9" * 64,),
        "objective_completed": True,
        "progress_units_gained": 4,
        "progress_units_required": 4,
        "battles_completed": 10,
        "faints": 0,
        "venue_transition_trips": 1,
        "required_recovery_trips": 2,
        "optional_recovery_trips": 0,
        "cleanup_trips": 1,
        "total_counted_center_routes": 4,
    }
    if field == "incomplete_progress":
        values["progress_units_gained"] = 3
    else:
        values["total_counted_center_routes"] = 3

    with pytest.raises(PartyDevelopmentVenuePriorError, match=match):
        VenuePriorObservation(**values)  # type: ignore[arg-type]


def test_composition_rejects_reused_root_or_state_support() -> None:
    first = _observation()

    with pytest.raises(PartyDevelopmentVenuePriorError, match="independent roots and states"):
        compose_venue_prior_evidence(
            evidence_id="dependent-prior",
            venue=_area("private-route-a", 12, 18),
            source_commit="a" * 40,
            source_bundle_sha256="b" * 64,
            measurement_contract=VenuePriorMeasurementContract(),
            operational_contract=_operational_contract(),
            source_compatibility=_source_compatibility(),
            observations=(
                first,
                _observation(root="prior-root-b", state="8"),
            ),
        )


def test_composition_rejects_source_compatibility_contract_mismatch() -> None:
    compatibility = _source_compatibility()
    contract = replace(
        _operational_contract(),
        source_compatibility_sha256="f" * 64,
    )

    with pytest.raises(
        PartyDevelopmentVenuePriorError,
        match="source compatibility differs",
    ):
        compose_venue_prior_evidence(
            evidence_id="incompatible-prior",
            venue=_area("private-route-a", 12, 18),
            source_commit="a" * 40,
            source_bundle_sha256="b" * 64,
            measurement_contract=VenuePriorMeasurementContract(),
            operational_contract=contract,
            source_compatibility=compatibility,
            observations=(_observation(),),
        )


def test_evidence_identity_commits_the_source_compatibility_attestation() -> None:
    evidence = compose_venue_prior_evidence(
        evidence_id="compatibility-bound-prior",
        venue=_area("private-route-a", 12, 18),
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        measurement_contract=VenuePriorMeasurementContract(),
        operational_contract=_operational_contract(),
        source_compatibility=_source_compatibility(),
        observations=(_observation(),),
    )

    assert replace(
        evidence,
        source_compatibility_sha256="f" * 64,
    ).evidence_sha256 != evidence.evidence_sha256


@pytest.mark.parametrize(
    "field",
    (
        "policy_sha256",
        "encounter_execution_sha256",
        "recovery_execution_sha256",
        "battle_timing_sha256",
        "accounting_sha256",
        "source_compatibility_sha256",
    ),
)
def test_operational_digest_commits_every_execution_layer(field: str) -> None:
    contract = _operational_contract()
    changed = replace(contract, **{field: "f" * 64})

    assert changed.operational_contract_sha256 != contract.operational_contract_sha256
