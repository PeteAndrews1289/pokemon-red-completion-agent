from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

import pokemon_red_completion.red_cave_venue_prior as cave_prior_module
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorEvidence,
    VenuePriorMeasurementContract,
    VenuePriorOperationalContract,
    VenuePriorSourceCompatibilityAttestation,
    VenuePriorUnitRatio,
)
from pokemon_red_completion.red_cave_venue_prior import (
    RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256,
    RED_CAVE_MEASUREMENT_SOURCE_COMMIT,
    RED_CAVE_VENUE_MEASUREMENT_PUBLIC_PLAN_SHA256,
    RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256,
    RedCaveVenuePriorError,
    attest_red_cave_source_compatibility,
    compose_red_cave_venue_prior,
)
from pokemon_red_completion.team_training import GrindingArea

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-venue-measurement-plan-v2-2026-08-15.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-venue-measurement-result-v2-2026-08-16.json"
)
COMPOSITION_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-venue-prior-composition-v2-2026-08-16.json"
)


def _receipts() -> tuple[dict[str, object], dict[str, object]]:
    return (
        json.loads(PLAN_PATH.read_text(encoding="ascii")),
        json.loads(RESULT_PATH.read_text(encoding="ascii")),
    )


def _compatibility() -> VenuePriorSourceCompatibilityAttestation:
    return VenuePriorSourceCompatibilityAttestation(
        attestation_id="test-cave-source-compatibility",
        observed_commit=RED_CAVE_MEASUREMENT_SOURCE_COMMIT,
        observed_source_bundle_sha256=RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256,
        current_commit="c" * 40,
        current_source_bundle_sha256="d" * 64,
        unchanged_elements_sha256="e" * 64,
        current_elements_sha256="f" * 64,
        waived_elements=("publication-and-composition-only",),
        waiver_allowlist_sha256="1" * 64,
    )


def _operational_contract(
    compatibility: VenuePriorSourceCompatibilityAttestation,
) -> VenuePriorOperationalContract:
    return VenuePriorOperationalContract(
        contract_id="test-cave-operational-contract",
        policy_sha256="2" * 64,
        encounter_execution_sha256="3" * 64,
        recovery_execution_sha256="4" * 64,
        battle_timing_sha256="5" * 64,
        accounting_sha256="6" * 64,
        source_compatibility_sha256=compatibility.source_compatibility_sha256,
    )


def _existing_registry() -> PartyDevelopmentVenuePriorRegistry:
    evidence = VenuePriorEvidence(
        evidence_id="test-route-prior",
        venue=GrindingArea(
            area_id="test_route",
            minimum_encounter_level=1,
            maximum_encounter_level=2,
            has_nearby_healer=True,
            measured_samples=20,
        ),
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        measurement_contract_sha256=(
            VenuePriorMeasurementContract().measurement_contract_sha256
        ),
        operational_contract_sha256="7" * 64,
        source_compatibility_sha256="8" * 64,
        support_root_lineage_ids=("test-route-root",),
        support_state_sha256=("9" * 64,),
        outcome_receipt_sha256=("a" * 64,),
        reliability=VenuePriorUnitRatio(1, 1),
        expected_yield=VenuePriorUnitRatio(1, 1),
        matchup_safety=VenuePriorUnitRatio(1, 1),
        travel_cost=VenuePriorUnitRatio(0, 1),
        recovery_cost=VenuePriorUnitRatio(0, 1),
    )
    return PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        entries=(evidence,),
    )


def test_public_cave_receipts_have_the_exact_frozen_digests() -> None:
    assert hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() == (
        RED_CAVE_VENUE_MEASUREMENT_PUBLIC_PLAN_SHA256
    )
    assert hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest() == (
        RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256
    )


def test_cave_receipt_validator_reconciles_the_accepted_measurement() -> None:
    plan, result = _receipts()

    cave_prior_module._require_public_receipts(
        plan,
        result,
        public_plan_sha256=RED_CAVE_VENUE_MEASUREMENT_PUBLIC_PLAN_SHA256,
        public_result_sha256=RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256,
    )

    mutated = copy.deepcopy(result)
    measurement = mutated["measurement"]
    assert isinstance(measurement, dict)
    measurement["candidate_decisions"] = 1
    with pytest.raises(RedCaveVenuePriorError, match="prospective arithmetic"):
        cave_prior_module._require_public_receipts(
            plan,
            mutated,
            public_plan_sha256=RED_CAVE_VENUE_MEASUREMENT_PUBLIC_PLAN_SHA256,
            public_result_sha256=RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256,
        )


def test_source_compatibility_accepts_only_identical_runtime_and_two_additions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = tuple(
        {"path": path, "sha256": hashlib.sha256(path.encode()).hexdigest()}
        for path in cave_prior_module._CRITICAL_RUNTIME_PATHS
    )
    monkeypatch.setattr(
        cave_prior_module,
        "committed_source_bundle_sha256",
        lambda _root, *, revision: (
            RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256
            if revision == RED_CAVE_MEASUREMENT_SOURCE_COMMIT
            else "d" * 64
        ),
    )
    monkeypatch.setattr(
        cave_prior_module,
        "_committed_runtime_rows",
        lambda _root, *, revision: rows,
    )
    monkeypatch.setattr(
        cave_prior_module,
        "_changed_paths_between",
        lambda *_args: tuple(sorted(cave_prior_module._COMPATIBILITY_SOURCE_ADDITIONS)),
    )

    attestation = attest_red_cave_source_compatibility(
        PROJECT_ROOT,
        current_commit="c" * 40,
        current_source_bundle_sha256="d" * 64,
    )

    assert attestation.waived_elements == ("publication-and-composition-only",)
    assert attestation.observed_commit == RED_CAVE_MEASUREMENT_SOURCE_COMMIT
    assert attestation.current_commit == "c" * 40

    changed_rows = (*rows[:-1], {"path": rows[-1]["path"], "sha256": "0" * 64})
    calls = iter((rows, changed_rows))
    monkeypatch.setattr(
        cave_prior_module,
        "_committed_runtime_rows",
        lambda _root, *, revision: next(calls),
    )
    with pytest.raises(RedCaveVenuePriorError, match="execution-bearing"):
        attest_red_cave_source_compatibility(
            PROJECT_ROOT,
            current_commit="c" * 40,
            current_source_bundle_sha256="d" * 64,
        )


def test_source_compatibility_rejects_an_extra_source_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = tuple(
        {"path": path, "sha256": hashlib.sha256(path.encode()).hexdigest()}
        for path in cave_prior_module._CRITICAL_RUNTIME_PATHS
    )
    monkeypatch.setattr(
        cave_prior_module,
        "committed_source_bundle_sha256",
        lambda _root, *, revision: (
            RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256
            if revision == RED_CAVE_MEASUREMENT_SOURCE_COMMIT
            else "d" * 64
        ),
    )
    monkeypatch.setattr(
        cave_prior_module,
        "_committed_runtime_rows",
        lambda _root, *, revision: rows,
    )
    monkeypatch.setattr(
        cave_prior_module,
        "_changed_paths_between",
        lambda *_args: (
            *sorted(cave_prior_module._COMPATIBILITY_SOURCE_ADDITIONS),
            "src/pokemon_red_completion/red_team_training.py",
        ),
    )

    with pytest.raises(RedCaveVenuePriorError, match="exceeds publication"):
        attest_red_cave_source_compatibility(
            PROJECT_ROOT,
            current_commit="c" * 40,
            current_source_bundle_sha256="d" * 64,
        )


def test_composition_adds_exactly_one_cave_prior_without_a_training_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, result = _receipts()
    existing_registry = _existing_registry()
    compatibility = _compatibility()
    operational = _operational_contract(compatibility)
    monkeypatch.setattr(
        cave_prior_module,
        "RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256",
        existing_registry.registry_sha256,
    )
    monkeypatch.setattr(
        cave_prior_module,
        "RED_CAVE_ROUTE_PRIOR_OPERATIONAL_CONTRACT_SHA256",
        existing_registry.entries[0].operational_contract_sha256,
    )
    monkeypatch.setattr(
        cave_prior_module,
        "red_cave_operational_contract",
        lambda *_args, **_kwargs: operational,
    )

    composition = compose_red_cave_venue_prior(
        existing_registry=existing_registry,
        plan=plan,
        result=result,
        public_plan_sha256=RED_CAVE_VENUE_MEASUREMENT_PUBLIC_PLAN_SHA256,
        public_result_sha256=RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256,
        registry_source_commit=compatibility.current_commit,
        registry_source_bundle_sha256=(
            compatibility.current_source_bundle_sha256
        ),
        source_compatibility=compatibility,
        repository_root=PROJECT_ROOT,
    )

    assert len(composition.registry.entries) == 2
    assert composition.cave_evidence.support_count == 1
    assert composition.cave_evidence.reliability == VenuePriorUnitRatio(1, 1)
    assert composition.cave_evidence.expected_yield == VenuePriorUnitRatio(4, 4)
    assert composition.cave_evidence.matchup_safety == VenuePriorUnitRatio(67, 67)
    assert composition.cave_evidence.travel_cost == VenuePriorUnitRatio(1, 68)
    assert composition.cave_evidence.recovery_cost == VenuePriorUnitRatio(7, 74)
    public = composition.public_dict()
    assert public["venue_prior_entries_added"] == 1
    assert public["resulting_venue_prior_count"] == 2
    assert public["training_examples_created"] == 0
    assert public["composition_controller_actions"] == 0
    assert public["authority_promoted"] is False
    encoded = json.dumps(public, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "species_id" not in encoded


def test_working_runtime_drift_cannot_masquerade_as_measured_cave_source() -> None:
    rows = cave_prior_module._committed_runtime_rows(
        PROJECT_ROOT,
        revision=RED_CAVE_MEASUREMENT_SOURCE_COMMIT,
    )

    drifted = tuple(
        row["path"]
        for row in rows
        if isinstance(row["path"], str)
        and hashlib.sha256((PROJECT_ROOT / row["path"]).read_bytes()).hexdigest()
        != row["sha256"]
    )

    # The consumed Cave run remains valid historical evidence at its measured
    # source.  Completion-aware fixed-dose execution intentionally changes the
    # current runtime, so the old byte-identity attestation must no longer be
    # treated as current-source authority.  Any further drift requires an
    # explicit review here rather than silently inheriting the old result.
    assert drifted == (
        "src/pokemon_red_completion/blaine.py",
        "src/pokemon_red_completion/emulator.py",
        "src/pokemon_red_completion/executor.py",
        "src/pokemon_red_completion/hideout.py",
        "src/pokemon_red_completion/observation.py",
        "src/pokemon_red_completion/red_battle_catalog.py",
        "src/pokemon_red_completion/red_party_development_venue_priors.py",
        "src/pokemon_red_completion/red_team_training.py",
    )


def test_tracked_composition_receipt_is_exact_path_free_and_non_executing() -> None:
    payload = COMPOSITION_PATH.read_bytes()
    receipt = json.loads(payload.decode("ascii"))

    assert hashlib.sha256(payload).hexdigest() == (
        "015d2d256d8722d8f874f1219235c2f8ff35b3e401e645e99cf8990cda79d0d6"
    )
    assert receipt["status"] == "source_only_prior_composed"
    assert receipt["previous_venue_prior_count"] == 1
    assert receipt["venue_prior_entries_added"] == 1
    assert receipt["resulting_venue_prior_count"] == 2
    assert receipt["registry"]["entry_count"] == 2
    assert receipt["registry"]["registry_sha256"] == (
        "4379309d1e87eaa896254ac945897353ede418472ea011bc3c03675c9b4542eb"
    )
    assert receipt["private_registry_file_sha256"] == (
        "da32ef5ba736348a5abc3c93c6c9a3c9217cc958b2905b65cd11c45347a42bfc"
    )
    assert receipt["source_compatibility"]["current_commit"] == (
        "107e0343d128a9cd0c1a1aea6b33a5b1ee9be5c3"
    )
    for counter in (
        "composition_rom_reads",
        "composition_emulator_starts",
        "composition_controller_actions",
        "teacher_queries",
        "model_predictions",
        "model_updates",
        "outcomes_executed",
        "sealed_test_cases_opened",
        "crystal_contexts_opened",
        "training_examples_created",
    ):
        assert receipt[counter] == 0
    assert receipt["authority_promoted"] is False
    assert receipt["private_path_fields"] == 0
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    configured_rom = os.environ.get("POKEMON_RED_ROM")
    if configured_rom is not None:
        assert configured_rom not in encoded
    assert "species_id" not in encoded
