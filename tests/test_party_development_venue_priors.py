from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorError,
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorEvidence,
    VenuePriorUnitRatio,
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
