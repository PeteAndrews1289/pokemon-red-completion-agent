from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_living_dex_policy_development import _model
from test_red_living_dex_development_setup_journal import _fixture

from pokemon_red_completion import red_living_dex_clustered_development_execution as execution
from pokemon_red_completion.living_dex_goal_model_record import (
    LivingDexGoalModelRecord,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_invocation import (
    bind_red_living_dex_authenticated_consumer,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RedLivingDexCurrentConsumerBinding,
)
from pokemon_red_completion.red_living_dex_clustered_development_execution import (
    RedLivingDexClusteredDevelopmentExecutionError,
    execute_red_living_dex_development_assignment,
    preflight_red_living_dex_clustered_development_assignment,
    preflight_red_living_dex_development_assignment,
    run_red_living_dex_clustered_development_assignment,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _model_record() -> LivingDexGoalModelRecord:
    return LivingDexGoalModelRecord(
        model=_model(),
        file_sha256=_sha("model-record"),
        source_commit="e" * 40,
        source_bundle_sha256=_sha("model-source"),
        exact_ci_run=23456,
        exact_ci_attempt=1,
    )


def _consumer() -> Any:
    current = RedLivingDexCurrentConsumerBinding(
        source_commit="d" * 40,
        source_bundle_sha256=_sha("development-current-source"),
        exact_ci_run=12345,
        exact_ci_attempt=1,
    )
    return bind_red_living_dex_authenticated_consumer(
        current,
        bootstrap_identity=(
            current.source_commit,
            current.source_bundle_sha256,
            current.exact_ci_run,
            current.exact_ci_attempt,
        ),
    )


def _patch_production_join(
    monkeypatch: pytest.MonkeyPatch,
    *,
    plan: Any,
    selection: Any,
    identity: Any,
    registry: Path,
) -> list[object]:
    records: list[object] = []

    def reopen(*_args: object, **_kwargs: object) -> tuple[Any, object, dict[str, object]]:
        record = object()
        records.append(record)
        return selection, record, plan.private_dict()

    monkeypatch.setattr(execution, "reopen_red_living_dex_development_selection", reopen)
    monkeypatch.setattr(
        execution,
        "authenticate_red_living_dex_execution_runtime",
        lambda *_args, **_kwargs: SimpleNamespace(
            sha256=plan.bindings.runtime_identity_sha256
        ),
    )
    monkeypatch.setattr(
        execution,
        "compose_red_living_dex_setup_execution_identity",
        lambda **_kwargs: identity,
    )
    monkeypatch.setattr(execution, "fixed_account_claim_registry_root", lambda: registry)
    monkeypatch.setattr(
        execution,
        "observe_claim_first_pair_availability",
        lambda *_args, **_kwargs: True,
    )
    return records


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


def test_production_preflight_authenticates_source_plan_root_and_model_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, capability, frozen, _outer, meter, resolver, store, registry = _fixture(
        tmp_path
    )
    record = _model_record()
    records = _patch_production_join(
        monkeypatch,
        plan=plan,
        selection=frozen.selection,
        identity=frozen.producer_execution_identity(),
        registry=registry,
    )
    roots_loaded = 0

    def load_root(selection: Any) -> Any:
        nonlocal roots_loaded
        roots_loaded += 1
        assert selection == frozen.selection
        return capability.root.root

    before = meter.checkpoint()
    receipt = preflight_red_living_dex_development_assignment(
        tmp_path,
        store,
        consumer=_consumer(),
        ordinal=frozen.selection.ordinal,
        root_loader=load_root,
        meter=meter,
        model_record=record,
        expected_model_sha256=record.model.model_sha256,
        expected_model_record_sha256=record.file_sha256,
        binding=frozen.binding,
    )

    assert receipt.public_dict()["model_predictions"] == 0
    assert receipt.public_dict()["controller_actions"] == 0
    assert roots_loaded == 1
    assert len(records) == 2
    assert records[0] is not records[1]
    assert resolver.calls == 0
    assert meter.checkpoint() == before
    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()


def test_production_preflight_rejects_model_record_before_plan_or_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _plan, _capability, frozen, _outer, meter, _resolver, store, _registry = (
        _fixture(tmp_path)
    )
    record = _model_record()
    plan_loads = 0
    root_loads = 0

    def forbidden_plan(*_args: object, **_kwargs: object) -> object:
        nonlocal plan_loads
        plan_loads += 1
        raise AssertionError("wrong model record opened the plan")

    def forbidden_root(_selection: object) -> object:
        nonlocal root_loads
        root_loads += 1
        raise AssertionError("wrong model record opened the root")

    monkeypatch.setattr(
        execution,
        "reopen_red_living_dex_development_selection",
        forbidden_plan,
    )

    with pytest.raises(
        RedLivingDexClusteredDevelopmentExecutionError,
        match="model identity",
    ):
        preflight_red_living_dex_development_assignment(
            tmp_path,
            store,
            consumer=_consumer(),
            ordinal=frozen.selection.ordinal,
            root_loader=forbidden_root,
            meter=meter,
            model_record=record,
            expected_model_sha256=record.model.model_sha256,
            expected_model_record_sha256="f" * 64,
            binding=frozen.binding,
        )

    assert plan_loads == 0
    assert root_loads == 0


def test_production_preflight_requires_a_fresh_plan_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, capability, frozen, _outer, meter, _resolver, store, registry = _fixture(
        tmp_path
    )
    record = _model_record()
    sealed_record = object()
    monkeypatch.setattr(
        execution,
        "reopen_red_living_dex_development_selection",
        lambda *_args, **_kwargs: (
            frozen.selection,
            sealed_record,
            plan.private_dict(),
        ),
    )
    monkeypatch.setattr(
        execution,
        "authenticate_red_living_dex_execution_runtime",
        lambda *_args, **_kwargs: SimpleNamespace(
            sha256=plan.bindings.runtime_identity_sha256
        ),
    )
    monkeypatch.setattr(
        execution,
        "compose_red_living_dex_setup_execution_identity",
        lambda **_kwargs: frozen.producer_execution_identity(),
    )
    monkeypatch.setattr(execution, "fixed_account_claim_registry_root", lambda: registry)

    with pytest.raises(
        RedLivingDexClusteredDevelopmentExecutionError,
        match="reauthentication differs",
    ):
        preflight_red_living_dex_development_assignment(
            tmp_path,
            store,
            consumer=_consumer(),
            ordinal=frozen.selection.ordinal,
            root_loader=lambda _selection: capability.root.root,
            meter=meter,
            model_record=record,
            expected_model_sha256=record.model.model_sha256,
            expected_model_record_sha256=record.file_sha256,
            binding=frozen.binding,
        )

    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()


def test_production_execution_constructs_rom_resolver_only_after_full_join(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, capability, frozen, _outer, meter, _resolver, store, registry = _fixture(
        tmp_path
    )
    record = _model_record()
    _patch_production_join(
        monkeypatch,
        plan=plan,
        selection=frozen.selection,
        identity=frozen.producer_execution_identity(),
        registry=registry,
    )
    rom_path = tmp_path / "red.gb"
    constructed: list[tuple[Path, object]] = []
    sentinel_resolver = object()
    sentinel_receipt = object()

    def build_resolver(*, rom_path: Path, producer_execution_identity: object) -> object:
        constructed.append((rom_path, producer_execution_identity))
        return sentinel_resolver

    def run_assignment(**kwargs: object) -> object:
        assert kwargs["selection"] == frozen.selection
        assert kwargs["root"] == capability.root.root
        assert kwargs["resolver"] is sentinel_resolver
        assert kwargs["model"] == record.model
        assert kwargs["claim_registry"] == registry
        return sentinel_receipt

    monkeypatch.setattr(execution, "RedLivingDexLateProductionResolver", build_resolver)
    monkeypatch.setattr(
        execution,
        "run_red_living_dex_clustered_development_assignment",
        run_assignment,
    )

    receipt = execute_red_living_dex_development_assignment(
        tmp_path,
        store,
        consumer=_consumer(),
        ordinal=frozen.selection.ordinal,
        root_loader=lambda _selection: capability.root.root,
        rom_path=rom_path,
        meter=meter,
        model_record=record,
        expected_model_sha256=record.model.model_sha256,
        expected_model_record_sha256=record.file_sha256,
        binding=frozen.binding,
    )

    assert receipt is sentinel_receipt
    assert constructed == [(rom_path, frozen.producer_execution_identity())]


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
