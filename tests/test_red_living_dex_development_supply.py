from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_living_dex_goal_model_record import _model, _record
from test_red_living_dex_causal_campaign import _registry
from test_red_living_dex_clustered_train_runner import _successor_clustered_fixture
from test_red_living_dex_setup_recipe import _store

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstRootPair,
    claim_first_pair_registry,
)
from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.living_dex_development_supplement import (
    LivingDexDevelopmentSupplementPolicy,
    select_living_dex_development_supplement,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    RedLivingDexClusteredTrainPlanBinding,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    RedLivingDexDevelopmentSupplyError,
    audit_red_living_dex_development_supply,
    build_red_living_dex_development_supplement_capabilities,
    inventory_red_living_dex_development_supply,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _bindings_for_same_plan(store):  # type: ignore[no-untyped-def]
    plan, _binding = _successor_clustered_fixture()
    bindings = []
    for ordinal in range(2):
        record = store.publish_sealed_record(
            f"development-plan-{ordinal}",
            kind=f"development-plan-{ordinal}",
            record=plan.private_dict(),
        )
        bindings.append(
            RedLivingDexClusteredTrainPlanBinding(
                private_plan_sha256=plan.private_plan_sha256,
                plan_manifest_sha256=record.summary.manifest_sha256,
                plan_record_sha256=record.summary.record_sha256,
                schedule_sha256=plan.schedule.schedule_sha256,
                policy_sha256=plan.schedule.policy.policy_sha256,
                record_id=record.summary.record_id,
                record_kind=record.summary.kind,
                train_scenarios=16,
                development_scenarios=4,
            )
        )
    return tuple(bindings), plan.private_dict()


def _train_rows(count: int = 18) -> tuple[SimpleNamespace, ...]:
    return tuple(
        SimpleNamespace(
            identity=SimpleNamespace(
                partition="train",
                lineage_sha256=_sha(("train-lineage", ordinal)),
                state_sha256=_sha(("train-state", ordinal)),
                envelope_sha256=_sha(("train-envelope", ordinal)),
            ),
            example=object(),
        )
        for ordinal in range(count)
    )


def _publish_model(store, dataset_sha256: str):  # type: ignore[no-untyped-def]
    model = replace(
        _model(),
        train_dataset_sha256=dataset_sha256,
        settled_examples=18,
    )
    record = store.publish_sealed_record(
        f"lc-update-model-{dataset_sha256}",
        kind="living_dex_causal_integration_model",
        record=_record(model),
    )
    return model, record


def _consume_root(registry, row: dict[str, object], ordinal: int) -> None:  # type: ignore[no-untyped-def]
    claim = ClaimFirstRootPair(
        logical_root_sha256=row["root_consumption_sha256"],  # type: ignore[arg-type]
        physical_root_sha256=row["physical_root_sha256"],  # type: ignore[arg-type]
        stage="test-development-supply",
        execution_identity_sha256=_sha(("execution", ordinal)),
        plan_sha256=_sha(("plan", ordinal)),
        slot_sha256=row["template_sha256"],  # type: ignore[arg-type]
        runner_sha256=_sha(("runner", ordinal)),
        source_commit="a" * 40,
    )
    with claim_first_pair_registry(registry) as transaction:
        transaction.claim(claim)


def test_audit_deduplicates_schedules_and_reports_only_the_true_shortfall(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    bindings, document = _bindings_for_same_plan(store)
    dataset_sha256 = _sha("train-dataset")
    model, model_record = _publish_model(store, dataset_sha256)
    rows = _train_rows()
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "load_living_dex_authenticated_causal_examples",
        lambda _store: rows,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "living_dex_option_train_dataset_sha256",
        lambda _rows: dataset_sha256,
    )
    development = [
        row for row in document["assignments"] if row["partition"] == "development"
    ]
    _consume_root(registry, development[0], 0)
    _consume_root(registry, development[1], 1)

    result = audit_red_living_dex_development_supply(
        store,
        claim_registry=registry,
        expected_model_sha256=model.model_sha256,
        expected_model_record_sha256=model_record.summary.record_sha256,
        bindings=bindings,
    )

    assert result.authenticated_train_examples == 18
    assert result.scheduled_development_assignments == 8
    assert result.unique_development_roots == 4
    assert result.duplicate_schedule_assignments == 4
    assert result.available_development_roots == 2
    assert result.unavailable_development_roots == 2
    assert result.development_root_shortfall == 2
    assert result.minimum_new_roots_to_freeze == 3
    assert result.missing_option_kinds
    assert "trade" not in result.missing_option_kinds
    assert result.supply_ready is False
    public = result.public_dict()
    encoded = json.dumps(public, sort_keys=True)
    assert public["development_outcomes_opened"] == 0
    assert public["model_predictions"] == 0
    assert all(
        row["lineage_sha256"] not in encoded
        and row["root_consumption_sha256"] not in encoded
        and row["physical_root_sha256"] not in encoded
        for row in development
    )


def test_audit_reports_ready_when_four_independent_roots_remain(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    bindings, _document = _bindings_for_same_plan(store)
    dataset_sha256 = _sha("train-dataset")
    model, model_record = _publish_model(store, dataset_sha256)
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "load_living_dex_authenticated_causal_examples",
        lambda _store: _train_rows(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "living_dex_option_train_dataset_sha256",
        lambda _rows: dataset_sha256,
    )

    result = audit_red_living_dex_development_supply(
        store,
        claim_registry=registry,
        expected_model_sha256=model.model_sha256,
        expected_model_record_sha256=model_record.summary.record_sha256,
        bindings=bindings,
    )

    assert result.available_development_roots == 4
    assert result.available_development_lineages == 4
    assert result.supply_ready is True
    assert result.minimum_new_roots_to_freeze == 0
    assert result.public_dict()["status"] == "development_supply_ready"


def test_private_inventory_reproduces_public_counts_without_serializing_ids(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    bindings, document = _bindings_for_same_plan(store)
    dataset_sha256 = _sha("train-dataset")
    model, model_record = _publish_model(store, dataset_sha256)
    rows = _train_rows()
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "load_living_dex_authenticated_causal_examples",
        lambda _store: rows,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "living_dex_option_train_dataset_sha256",
        lambda _rows: dataset_sha256,
    )
    development = [
        row for row in document["assignments"] if row["partition"] == "development"
    ]
    _consume_root(registry, development[0], 0)
    _consume_root(registry, development[1], 1)

    inventory = inventory_red_living_dex_development_supply(
        store,
        claim_registry=registry,
        expected_model_sha256=model.model_sha256,
        expected_model_record_sha256=model_record.summary.record_sha256,
        bindings=bindings,
    )

    assert len(inventory.train_lineages) == 18
    assert len(inventory.train_states) == 18
    assert len(inventory.historical_roots) == 4
    assert len(inventory.available_roots) == 2
    assert inventory.result.minimum_new_roots_to_freeze == 3
    assert not hasattr(inventory, "public_dict")


def test_audit_fails_closed_on_model_record_or_duplicate_semantic_drift(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    bindings, _document = _bindings_for_same_plan(store)
    dataset_sha256 = _sha("train-dataset")
    model, model_record = _publish_model(store, dataset_sha256)
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "load_living_dex_authenticated_causal_examples",
        lambda _store: _train_rows(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "living_dex_option_train_dataset_sha256",
        lambda _rows: dataset_sha256,
    )

    with pytest.raises(RedLivingDexDevelopmentSupplyError, match="model record"):
        audit_red_living_dex_development_supply(
            store,
            claim_registry=registry,
            expected_model_sha256=model.model_sha256,
            expected_model_record_sha256=_sha("wrong-record"),
            bindings=bindings,
        )

    mutated = replace(bindings[1], policy_sha256=_sha("wrong-policy"))
    with pytest.raises(
        RedLivingDexDevelopmentSupplyError,
        match="authentication failed",
    ):
        audit_red_living_dex_development_supply(
            store,
            claim_registry=registry,
            expected_model_sha256=model.model_sha256,
            expected_model_record_sha256=model_record.summary.record_sha256,
            bindings=(bindings[0], mutated),
        )


def test_red_adapter_projects_only_authenticated_development_capabilities() -> None:
    frozen, _binding = _successor_clustered_fixture()
    capabilities = tuple(item.capability for item in frozen.assignments)

    projected = build_red_living_dex_development_supplement_capabilities(
        capabilities
    )
    policy = LivingDexDevelopmentSupplementPolicy(
        new_roots=3,
        minimum_surviving_roots=2,
        minimum_new_families=3,
        minimum_new_locations=3,
        held_root_count=2,
        required_total_roots=4,
        held_option_kinds=(
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.EVOLVE,
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.RESUPPLY,
            LivingDexOptionKind.UNLOCK_ACCESS,
            LivingDexOptionKind.EXPLORE,
        ),
        required_option_kinds=RED_DIRECT_CAUSAL_OPTION_KINDS,
    )
    plan = select_living_dex_development_supplement(
        projected,
        policy=policy,
    )

    assert len(projected) == 4
    assert len(plan.assignments) == 3
    assert all(
        item.family_scope_id.startswith("development-family")
        and item.location_scope_id.startswith("development-location")
        for item in plan.assignments
    )
    assert sum(
        LivingDexOptionKind.MANAGE_STORAGE in item.available_option_kinds
        for item in plan.assignments
    ) >= 2
