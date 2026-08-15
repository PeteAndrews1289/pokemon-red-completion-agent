from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

import pokemon_red_completion.red_party_development_venue_priors as venue_prior_module
from pokemon_red_completion.blaine import ROUTE_11_TRAINING_VENUE
from pokemon_red_completion.collection_protocol import (
    committed_source_bundle_sha256,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorUnitRatio,
)
from pokemon_red_completion.provenance import detect_source_identity
from pokemon_red_completion.red_party_development_venue_priors import (
    RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
    RedPartyDevelopmentVenuePriorError,
    attest_red_route_11_source_compatibility,
    compose_red_route_11_venue_prior,
    red_route_11_operational_contract,
)
from pokemon_red_completion.training_venue import TrainingVenue

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-outcome-plan-v2-2026-08-14.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-outcome-result-v2-2026-08-14.json"
)


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    return (
        json.loads(PLAN_PATH.read_text(encoding="ascii")),
        json.loads(RESULT_PATH.read_text(encoding="ascii")),
    )


@lru_cache(maxsize=1)
def _source_compatibility():
    identity = detect_source_identity(PROJECT_ROOT)
    assert identity.git_commit is not None
    current_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=identity.git_commit,
    )
    return attest_red_route_11_source_compatibility(
        PROJECT_ROOT,
        current_commit=identity.git_commit,
        current_source_bundle_sha256=current_bundle,
    )


def _composition(
    plan: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
    *,
    result_sha256: str | None = None,
):
    default_plan, default_result = _documents()
    compatibility = _source_compatibility()
    return compose_red_route_11_venue_prior(
        plan=default_plan if plan is None else plan,
        result=default_result if result is None else result,
        public_plan_sha256=hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest(),
        public_result_sha256=(
            hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest()
            if result_sha256 is None
            else result_sha256
        ),
        registry_source_commit=compatibility.current_commit,
        registry_source_bundle_sha256=(
            compatibility.current_source_bundle_sha256
        ),
        source_compatibility=compatibility,
    )


def test_route_11_receipts_compose_the_exact_observed_unit_ratios() -> None:
    composition = _composition()
    evidence = composition.evidence

    assert evidence.source_commit == "00499bc68b099ffcd0125a6777bc3b836a84ff0b"
    assert evidence.source_bundle_sha256 == (
        "969f6ae2f60282848d26d4097fcefe6e9881f3739d78b560bdf0f186482f6294"
    )
    assert evidence.venue == ROUTE_11_TRAINING_VENUE.band
    assert evidence.support_count == 1
    assert evidence.reliability == VenuePriorUnitRatio(1, 1)
    assert evidence.expected_yield == VenuePriorUnitRatio(4, 4)
    assert evidence.matchup_safety == VenuePriorUnitRatio(108, 108)
    assert evidence.travel_cost == VenuePriorUnitRatio(0, 108)
    assert evidence.recovery_cost == VenuePriorUnitRatio(10, 118)
    assert composition.registry.source_commit == (
        composition.source_compatibility.current_commit
    )
    assert composition.registry.source_bundle_sha256 == (
        composition.source_compatibility.current_source_bundle_sha256
    )


def test_composed_registry_round_trips_but_public_projection_hides_support() -> None:
    composition = _composition()
    restored = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        composition.registry.private_dict()
    )
    public = composition.public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert restored == composition.registry
    assert public["accepted_venue_evidence_count"] == 1
    assert public["rejected_stale_sibling_venue_count"] == 1
    assert public["outcomes_executed"] == 0
    assert public["teacher_queries"] == 0
    assert public["sealed_test_cases_opened"] == 0
    assert public["crystal_contexts_opened"] == 0
    assert public["private_path_fields"] == 0
    assert "red-goal-v1-029" not in encoded
    assert "24b848eeb9d0d7b1" not in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("retreat_hp_ratio", 0.44),
        ("reserve_total_pp", 3),
        ("maximum_battles", 199),
        ("maximum_budgeted_center_calls", 49),
        ("mandatory_heal_only_when_health_status_or_pp_is_unsafe", False),
    ),
)
def test_composition_rejects_published_policy_drift(
    field: str, replacement: object
) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(plan)
    training_policy = drifted["training_policy"]
    assert isinstance(training_policy, dict)
    training_policy[field] = replacement

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="training policy differs",
    ):
        _composition(drifted, result)


def test_composition_rejects_a_result_bound_to_another_plan() -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    bindings = drifted["prospective_bindings"]
    assert isinstance(bindings, dict)
    bindings["public_plan_sha256"] = "f" * 64

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="identity"):
        _composition(plan, drifted)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("candidate_kind", "higher_encounter_band_15_21"),
        ("evolution_completed", False),
        ("final_target_level", 25),
        ("faints", 1),
    ),
)
def test_composition_rejects_nonqualifying_route_trial(
    field: str, replacement: object
) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    collection = drifted["outcome_collection"]
    assert isinstance(collection, dict)
    trials = collection["trials"]
    assert isinstance(trials, list) and isinstance(trials[0], dict)
    trials[0][field] = replacement

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="bounded evolution"):
        _composition(plan, drifted)


def test_composition_rejects_incomplete_center_phase_accounting() -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    collection = drifted["outcome_collection"]
    assert isinstance(collection, dict)
    trials = collection["trials"]
    assert isinstance(trials, list) and isinstance(trials[0], dict)
    trials[0]["required_recovery_trips"] = 9

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="accounting"):
        _composition(plan, drifted)


def test_composition_rejects_sealed_or_cross_title_support() -> None:
    plan, result = _documents()
    for field in ("sealed_test", "crystal"):
        drifted = copy.deepcopy(plan)
        root = drifted["authenticated_root"]
        assert isinstance(root, dict)
        root[field] = True
        with pytest.raises(RedPartyDevelopmentVenuePriorError, match="open independent Red"):
            _composition(drifted, result)


def test_composition_rejects_the_stale_sibling_as_candidate_zero() -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(plan)
    construction = drifted["candidate_construction"]
    assert isinstance(construction, dict)
    construction["ordered_minimum_encounter_levels"] = [15, 9]
    construction["ordered_maximum_encounter_levels"] = [21, 15]

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="candidate zero"):
        _composition(drifted, result)


def test_operational_contract_changes_when_policy_changes() -> None:
    compatibility = _source_compatibility()
    baseline = red_route_11_operational_contract(
        source_compatibility=compatibility
    )
    changed = red_route_11_operational_contract(
        source_compatibility=compatibility,
        policy=replace(
            RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
            retreat_hp_ratio=0.44,
        )
    )

    assert changed.policy_sha256 != baseline.policy_sha256
    assert changed.encounter_execution_sha256 == baseline.encounter_execution_sha256
    assert changed.recovery_execution_sha256 == baseline.recovery_execution_sha256
    assert changed.battle_timing_sha256 == baseline.battle_timing_sha256
    assert changed.accounting_sha256 == baseline.accounting_sha256
    assert changed.operational_contract_sha256 != baseline.operational_contract_sha256


def test_operational_contract_rejects_a_stateful_route_11_walker() -> None:
    drifted = replace(
        ROUTE_11_TRAINING_VENUE,
        walk_to_grass_factory=lambda: ROUTE_11_TRAINING_VENUE.walk_to_grass,
    )

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="operating seam"):
        red_route_11_operational_contract(
            source_compatibility=_source_compatibility(),
            venue=drifted,
        )


def test_source_compatibility_recomputes_exact_bundles_and_three_waivers() -> None:
    attestation = _source_compatibility()

    assert attestation.observed_commit == (
        "00499bc68b099ffcd0125a6777bc3b836a84ff0b"
    )
    assert attestation.observed_source_bundle_sha256 == (
        "969f6ae2f60282848d26d4097fcefe6e9881f3739d78b560bdf0f186482f6294"
    )
    assert attestation.waived_elements == (
        "red.run-team-balancing",
        "red.team-training-execution-summary",
        "training-venue.fresh-walk-to-grass",
    )
    assert attestation.unchanged_elements_sha256 == (
        "5731efecb1ae36800b4e98dcbfc980af587f7960e28a6f2535478ec7f5b283e9"
    )
    assert attestation.current_elements_sha256 == (
        "e5f9319505ee1fbecff6d0149cfae6c9939bd8efe88d04e630a40b225dab6eb2"
    )
    assert attestation.waiver_allowlist_sha256 == (
        "d0dcd598ad4b5c434ea9b3ff3cd686226501aa00752520b908dd32019866b01b"
    )


def test_source_compatibility_rejects_a_false_current_bundle_claim() -> None:
    attestation = _source_compatibility()

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="current Route 11 source bundle differs",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256="f" * 64,
        )


def test_source_compatibility_rejects_unlisted_historical_element_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attestation = _source_compatibility()
    original = venue_prior_module.committed_executable_source_blob

    def changed_blob(
        repository_root: str | Path,
        *,
        revision: str,
        relative_path: str,
    ) -> bytes:
        payload = original(
            repository_root,
            revision=revision,
            relative_path=relative_path,
        )
        if (
            revision == attestation.observed_commit
            and relative_path.endswith("/team_training.py")
        ):
            return payload.replace(
                b"class TeamTrainingProgress",
                b"class HistoricalTeamTrainingProgress",
                1,
            )
        return payload

    monkeypatch.setattr(
        venue_prior_module,
        "committed_executable_source_blob",
        changed_blob,
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="unreviewed Route 11 source drift",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256=(
                attestation.current_source_bundle_sha256
            ),
        )


def test_source_compatibility_rejects_a_stale_waiver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attestation = _source_compatibility()
    existing = venue_prior_module._ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS
    monkeypatch.setattr(
        venue_prior_module,
        "_ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS",
        (
            *existing,
            replace(existing[0], element_id="unused.runtime-change"),
        ),
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="stale exception",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256=(
                attestation.current_source_bundle_sha256
            ),
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("git_commit", "d" * 40),
        ("source_bundle_sha256", "e" * 64),
    ),
)
def test_composition_rejects_a_false_historical_source_claim(
    field: str,
    replacement: str,
) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    source = drifted["source"]
    assert isinstance(source, dict)
    source[field] = replacement

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="successful published source|required compatibility proof",
    ):
        _composition(plan, drifted)


def test_composition_pins_the_result_receipt_digest() -> None:
    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="identity"):
        _composition(result_sha256="f" * 64)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("candidate_kind", "lower_encounter_band_9_15"),
        ("evolution_completed", False),
        ("faints", 99),
        ("battles_completed", 0),
    ),
)
def test_composition_computes_and_validates_the_rejected_stale_sibling(
    field: str,
    replacement: object,
) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    collection = drifted["outcome_collection"]
    assert isinstance(collection, dict)
    trials = collection["trials"]
    assert isinstance(trials, list) and isinstance(trials[1], dict)
    trials[1][field] = replacement

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="stale Cave"):
        _composition(plan, drifted)


def test_operational_contract_has_independent_golden_coverage() -> None:
    contract = red_route_11_operational_contract(
        source_compatibility=_source_compatibility()
    )

    assert contract.policy_sha256 == (
        "bb1ff8c7b449b359f01c7c1c9474c1a660ea604f629cbc0c9130e20030a7cd8c"
    )
    assert contract.encounter_execution_sha256 == (
        "d8ee44e07f28f8b5d7190639af14a1142da6657d8ca7e3d803fe578c73e41c98"
    )
    assert contract.recovery_execution_sha256 == (
        "5c7d34e09f1e0b363661d4f09ff47e0d9e3437e3a7958b82ecba9e23d05982bd"
    )
    assert contract.battle_timing_sha256 == (
        "20accd493cf01c759b1d5d6f9550e1e31dc7b88ccaeba3b67e3d0f075566bae9"
    )
    assert contract.accounting_sha256 == (
        "4032c0c58e570fdb282aa15a2aa987b835f614a3c0deeef1ba6cacfd979e3bab"
    )


@pytest.mark.parametrize(
    "venue",
    (
        replace(
            ROUTE_11_TRAINING_VENUE,
            band=replace(
                ROUTE_11_TRAINING_VENUE.band,
                measured_samples=80,
            ),
        ),
        replace(
            ROUTE_11_TRAINING_VENUE,
            walk_to_grass=lambda *_args: 1,
        ),
    ),
)
def test_operational_contract_rejects_measured_band_or_walker_identity_drift(
    venue: TrainingVenue,
) -> None:
    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="operating seam"):
        red_route_11_operational_contract(
            source_compatibility=_source_compatibility(),
            venue=venue,
        )


def test_operational_contract_rejects_drift_in_the_global_measured_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drifted = replace(
        ROUTE_11_TRAINING_VENUE,
        band=replace(
            ROUTE_11_TRAINING_VENUE.band,
            measured_samples=80,
        ),
    )
    monkeypatch.setattr(
        venue_prior_module,
        "ROUTE_11_TRAINING_VENUE",
        drifted,
    )

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="operating seam"):
        red_route_11_operational_contract(
            source_compatibility=_source_compatibility(),
            venue=drifted,
        )
