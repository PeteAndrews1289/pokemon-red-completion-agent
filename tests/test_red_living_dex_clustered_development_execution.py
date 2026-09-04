from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_living_dex_policy_development import _model
from test_red_living_dex_development_setup_journal import _fixture

from pokemon_red_completion.red_living_dex_clustered_development_execution import (
    RedLivingDexClusteredDevelopmentExecutionError,
    preflight_red_living_dex_clustered_development_assignment,
    run_red_living_dex_clustered_development_assignment,
)


def test_preflight_authenticates_join_without_prediction_or_effect(
    tmp_path: Path,
) -> None:
    plan, capability, frozen, outer, meter, resolver, _store_value, registry = (
        _fixture(tmp_path)
    )
    model = _model()
    before = meter.checkpoint()

    receipt = preflight_red_living_dex_clustered_development_assignment(
        selection=frozen.selection,
        binding=frozen.binding,
        plan_document=plan.private_dict(),
        root=capability.root.root,
        producer_execution_identity=frozen.producer_execution_identity(),
        outer_execution_identity=outer,
        meter=meter,
        claim_registry=registry,
        model=model,
        expected_model_sha256=model.model_sha256,
    )

    assert receipt.public_dict()["claim_available"] is True
    assert receipt.public_dict()["model_predictions"] == 0
    assert receipt.public_dict()["controller_actions"] == 0
    assert meter.checkpoint() == before
    assert resolver.calls == 0
    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()


def test_preflight_rejects_outer_identity_before_claim(tmp_path: Path) -> None:
    plan, capability, frozen, outer, meter, _resolver, _store_value, registry = (
        _fixture(tmp_path)
    )
    model = _model()

    with pytest.raises(
        RedLivingDexClusteredDevelopmentExecutionError,
        match="outer identity",
    ):
        preflight_red_living_dex_clustered_development_assignment(
            selection=frozen.selection,
            binding=frozen.binding,
            plan_document=plan.private_dict(),
            root=capability.root.root,
            producer_execution_identity=frozen.producer_execution_identity(),
            outer_execution_identity=replace(
                outer,
                producer_manifest_sha256="f" * 64,
            ),
            meter=meter,
            claim_registry=registry,
            model=model,
            expected_model_sha256=model.model_sha256,
        )

    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()


def test_failed_setup_never_opens_model_outcome_or_training_target(
    tmp_path: Path,
) -> None:
    plan, capability, frozen, outer, meter, resolver, store, registry = _fixture(
        tmp_path
    )
    model = _model()

    receipt = run_red_living_dex_clustered_development_assignment(
        selection=frozen.selection,
        binding=frozen.binding,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=capability.root.root,
        producer_execution_identity=frozen.producer_execution_identity(),
        outer_execution_identity=outer,
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
        model=model,
        expected_model_sha256=model.model_sha256,
    )

    assert receipt.development is None
    assert receipt.public_dict()["development_outcomes_opened"] == 0
    assert receipt.public_dict()["model_predictions"] == 0
    assert receipt.public_dict()["teacher_queries"] == 0
    assert receipt.public_dict()["training_targets_emitted"] == 0
    assert resolver.calls == 1


def test_wrong_model_fails_before_plan_or_root_claim(tmp_path: Path) -> None:
    plan, capability, frozen, outer, meter, resolver, store, registry = _fixture(
        tmp_path
    )
    model = _model()
    plan_loads = 0

    def load_plan():  # type: ignore[no-untyped-def]
        nonlocal plan_loads
        plan_loads += 1
        return plan.private_dict()

    with pytest.raises(
        RedLivingDexClusteredDevelopmentExecutionError,
        match="model identity",
    ):
        run_red_living_dex_clustered_development_assignment(
            selection=frozen.selection,
            binding=frozen.binding,
            store=store,
            plan_loader=load_plan,
            root=capability.root.root,
            producer_execution_identity=frozen.producer_execution_identity(),
            outer_execution_identity=outer,
            resolver=resolver,
            meter=meter,
            claim_registry=registry,
            model=model,
            expected_model_sha256="f" * 64,
        )

    assert plan_loads == 0
    assert resolver.calls == 0
    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()


def test_root_substitution_fails_before_model_or_runtime(tmp_path: Path) -> None:
    plan, _capability, frozen, outer, meter, resolver, store, registry = _fixture(
        tmp_path
    )
    wrong = plan.assignments[17].capability.root.root
    model = _model()

    with pytest.raises(
        RedLivingDexClusteredDevelopmentExecutionError,
        match="root differs",
    ):
        run_red_living_dex_clustered_development_assignment(
            selection=frozen.selection,
            binding=frozen.binding,
            store=store,
            plan_loader=lambda: plan.private_dict(),
            root=wrong,
            producer_execution_identity=frozen.producer_execution_identity(),
            outer_execution_identity=outer,
            resolver=resolver,
            meter=meter,
            claim_registry=registry,
            model=model,
            expected_model_sha256=model.model_sha256,
        )

    assert resolver.calls == 0
    assert tuple(registry.iterdir()) == ()
