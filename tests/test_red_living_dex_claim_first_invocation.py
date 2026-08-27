from __future__ import annotations

import copy
import inspect
from pathlib import Path
from typing import Any

import pytest
from test_red_living_dex_setup_recipe import _identity, _recipes, _root, _store

from pokemon_red_completion import red_living_dex_claim_first_invocation as invocation
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    SourceIdentity,
    canonical_sha256,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RED_LIVING_DEX_CLAIM_FIRST_INVOCATION_PREFLIGHT_SCHEMA,
    RedLivingDexClaimFirstInvocationError,
    RedLivingDexCurrentConsumerBinding,
    RedLivingDexFrozenProducerBinding,
    RedLivingDexLoadedProducerSlot,
    execute_red_living_dex_claim_first_invocation,
    preflight_red_living_dex_claim_first_invocation,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
    build_red_living_dex_setup_recipe_plan,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _registry(tmp_path: Path) -> Path:
    registry = tmp_path / "account-claims"
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)
    marker = registry / ".coordination.lock"
    marker.touch(mode=0o600)
    marker.chmod(0o600)
    return registry


def _consumer() -> RedLivingDexCurrentConsumerBinding:
    return RedLivingDexCurrentConsumerBinding(
        source_commit="c" * 40,
        source_bundle_sha256=_sha("current-source"),
        exact_ci_run=1234,
        exact_ci_attempt=1,
    )


def _producer_document(plan: Any) -> tuple[dict[str, object], str]:
    execution = plan.execution_identity.private_dict()
    freeze = {
        "recipe_plan_sha256": plan.plan_sha256,
        "schema": "test.red.living-dex-provider-freeze.v1",
    }
    payload: dict[str, object] = {
        "context_catalog_sha256": _sha("catalog"),
        "context_plan_sha256": _sha("context-plan"),
        "controller_actions": 0,
        "emulator_frames": 0,
        "execution_identity": execution,
        "execution_identity_sha256": plan.execution_identity.identity_sha256,
        "freeze": freeze,
        "freeze_sha256": canonical_sha256(freeze),
        "goal_registry_sha256": _sha("goal-registry"),
        "model_fits": 0,
        "model_predictions": 0,
        "outcomes": 0,
        "provider_executions": 0,
        "recipe_plan": plan.private_dict(),
        "recipe_plan_sha256": plan.plan_sha256,
        "root_claims": 0,
        "route_registry_sha256": _sha("route-registry"),
        "rom_sha256": POKEMON_RED_US_REV_0.sha256,
        "runtime_identity_sha256": _sha("runtime"),
        "schema": invocation.RED_LIVING_DEX_PROVIDER_PLAN_SCHEMA,
        "source_catalog_partition_reused_as_prospective_label": False,
        "source_bundle_sha256": plan.execution_identity.source_bundle_sha256,
        "source_commit": plan.execution_identity.source_commit,
        "status": "frozen_before_claim_controller_input_outcome_or_fit",
        "teacher_queries": 0,
    }
    private_plan_sha256 = canonical_sha256(payload)
    return {**payload, "private_plan_sha256": private_plan_sha256}, private_plan_sha256


def _fixture(tmp_path: Path, ordinal: int = 3):  # type: ignore[no-untyped-def]
    plan = build_red_living_dex_setup_recipe_plan(
        _recipes(),
        execution_identity=_identity(),
    )
    document, private_plan_sha256 = _producer_document(plan)
    store = _store(tmp_path)
    record = store.publish_sealed_record(
        "red-living-dex-provider-plan-v1",
        kind="red-living-dex-provider-plan-v1",
        record=document,
    )
    producer = RedLivingDexFrozenProducerBinding(
        producer_plan_sha256=plan.plan_sha256,
        producer_private_plan_sha256=private_plan_sha256,
        producer_manifest_sha256=record.summary.manifest_sha256,
        ordinal=ordinal,
    )
    return plan, store, record, producer, _root(ordinal)


def _fresh_loader(
    store: Any,
    root: Any,
    calls: list[int],
):  # type: ignore[no-untyped-def]
    def load(ordinal: int) -> RedLivingDexLoadedProducerSlot:
        calls.append(ordinal)
        record = store.find_sealed_record(
            "red-living-dex-provider-plan-v1",
            expected_kind="red-living-dex-provider-plan-v1",
        )
        assert record is not None
        return RedLivingDexLoadedProducerSlot(record, root)

    return load


def test_preflight_reads_one_selected_root_and_has_zero_protected_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _plan, store, _record, producer, root = _fixture(tmp_path)
    registry = _registry(tmp_path)
    source_checks: list[object] = []
    ordinals: list[int] = []
    monkeypatch.setattr(
        invocation,
        "_require_current_consumer",
        lambda project_root, consumer: source_checks.append((project_root, consumer)),
    )
    monkeypatch.setattr(
        invocation,
        "_build_production_resolver",
        lambda **_kwargs: pytest.fail("preflight constructed a production resolver"),
    )
    monkeypatch.setattr(
        invocation,
        "run_red_living_dex_claim_first_setup_slot",
        lambda *_args, **_kwargs: pytest.fail("preflight called the campaign"),
    )

    receipt = preflight_red_living_dex_claim_first_invocation(
        Path("/public/repository"),
        consumer=_consumer(),
        producer=producer,
        producer_slot_loader=_fresh_loader(store, root, ordinals),
        claim_registry=registry,
    )

    assert ordinals == [producer.ordinal]
    assert len(source_checks) == 2
    assert receipt.public_dict() == {
        "behavior_draws": 0,
        "claim_registry_observations": 1,
        "controller_actions": 0,
        "current_consumer_bound": True,
        "emulator_frames": 0,
        "exact_ci_bound": True,
        "learner_labels": 0,
        "learner_outcomes": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "producer_executions": 0,
        "producer_record_reads": 1,
        "resolver_constructions": 0,
        "root_claims": 0,
        "schema": RED_LIVING_DEX_CLAIM_FIRST_INVOCATION_PREFLIGHT_SCHEMA,
        "selected_root_reads": 1,
        "selected_slots": 1,
        "setup_campaign_calls": 0,
        "sibling_root_reads": 0,
        "status": "one_slot_ready_before_claim_or_runtime",
        "teacher_queries": 0,
    }
    encoded = repr(receipt.public_dict())
    assert str(tmp_path) not in encoded
    assert producer.producer_private_plan_sha256 not in encoded
    assert producer.producer_manifest_sha256 not in encoded
    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("producer_plan_sha256", _sha("another-plan")),
        ("producer_private_plan_sha256", _sha("another-private-plan")),
        ("producer_manifest_sha256", _sha("another-manifest")),
    ),
)
def test_preflight_rejects_every_immutable_producer_binding_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    _plan, store, _record, producer, root = _fixture(tmp_path)
    changed = copy.copy(producer)
    object.__setattr__(changed, field, value)
    monkeypatch.setattr(invocation, "_require_current_consumer", lambda *_args: None)

    with pytest.raises(
        RedLivingDexClaimFirstInvocationError,
        match="immutable_producer_authentication",
    ):
        preflight_red_living_dex_claim_first_invocation(
            Path("/public/repository"),
            consumer=_consumer(),
            producer=changed,
            producer_slot_loader=_fresh_loader(store, root, []),
            claim_registry=_registry(tmp_path),
        )


def test_hash_bound_but_internally_cross_joined_producer_record_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(
        _recipes(),
        execution_identity=_identity(),
    )
    document, _private_plan_sha256 = _producer_document(plan)
    document["source_commit"] = "e" * 40
    payload = dict(document)
    payload.pop("private_plan_sha256")
    private_plan_sha256 = canonical_sha256(payload)
    document["private_plan_sha256"] = private_plan_sha256
    store = _store(tmp_path)
    record = store.publish_sealed_record(
        "red-living-dex-provider-plan-v1",
        kind="red-living-dex-provider-plan-v1",
        record=document,
    )
    producer = RedLivingDexFrozenProducerBinding(
        producer_plan_sha256=plan.plan_sha256,
        producer_private_plan_sha256=private_plan_sha256,
        producer_manifest_sha256=record.summary.manifest_sha256,
        ordinal=0,
    )
    monkeypatch.setattr(invocation, "_require_current_consumer", lambda *_args: None)

    with pytest.raises(
        RedLivingDexClaimFirstInvocationError,
        match="immutable_producer_authentication",
    ):
        preflight_red_living_dex_claim_first_invocation(
            Path("/public/repository"),
            consumer=_consumer(),
            producer=producer,
            producer_slot_loader=_fresh_loader(store, _root(0), []),
            claim_registry=_registry(tmp_path),
        )


def test_preflight_rejects_a_claimed_selected_root_without_reading_siblings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _plan, store, _record, producer, root = _fixture(tmp_path)
    registry = _registry(tmp_path)
    marker = registry / f"{root.root_consumption_sha256}.json"
    marker.write_text("consumed\n", encoding="ascii")
    marker.chmod(0o600)
    ordinals: list[int] = []
    monkeypatch.setattr(invocation, "_require_current_consumer", lambda *_args: None)

    with pytest.raises(
        RedLivingDexClaimFirstInvocationError,
        match="selected_root_unavailable",
    ):
        preflight_red_living_dex_claim_first_invocation(
            Path("/public/repository"),
            consumer=_consumer(),
            producer=producer,
            producer_slot_loader=_fresh_loader(store, root, ordinals),
            claim_registry=registry,
        )
    assert ordinals == [producer.ordinal]


def test_execution_owns_the_only_resolver_and_reopens_the_record_for_each_join(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, store, _record, producer, root = _fixture(tmp_path)
    events: list[str] = []
    ordinals: list[int] = []
    resolver = object()
    result = object()
    monkeypatch.setattr(
        invocation,
        "_require_current_consumer",
        lambda *_args: events.append("source"),
    )

    def build_resolver(**kwargs: object) -> object:
        events.append("resolver")
        assert kwargs["producer_execution_identity"] == plan.execution_identity
        return resolver

    def run_campaign(_store: object, **kwargs: object) -> object:
        events.append("campaign")
        assert kwargs["resolver"] is resolver
        assert kwargs["outer_execution_identity"].title_adapter_sha256 == (
            RED_LIVING_DEX_TITLE_ADAPTER_SHA256
        )
        assert kwargs["outer_execution_identity"].runtime_factory_sha256 == (
            RED_LIVING_DEX_RUNTIME_FACTORY_SHA256
        )
        assert kwargs["outer_execution_identity"].runner_sha256 == (
            RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256
        )
        assert canonical_sha256(dict(kwargs["plan_loader"]())) == plan.plan_sha256
        assert canonical_sha256(dict(kwargs["plan_loader"]())) == plan.plan_sha256
        return result

    monkeypatch.setattr(invocation, "_build_production_resolver", build_resolver)
    monkeypatch.setattr(
        invocation,
        "run_red_living_dex_claim_first_setup_slot",
        run_campaign,
    )

    actual = execute_red_living_dex_claim_first_invocation(
        Path("/public/repository"),
        store,
        consumer=_consumer(),
        producer=producer,
        producer_slot_loader=_fresh_loader(store, root, ordinals),
        claim_registry=_registry(tmp_path),
        rom_path=Path("/private/red.gb"),
        rom_bytes=b"authenticated-red-bytes",
        meter=RedLivingDexSetupEffectMeter(),
    )

    assert actual is result
    assert events == ["source", "source", "resolver", "campaign"]
    assert ordinals == [producer.ordinal] * 3
    parameters = inspect.signature(execute_red_living_dex_claim_first_invocation).parameters
    assert "resolver" not in parameters
    assert "resolver_factory" not in parameters


def test_execution_rejects_a_cached_record_at_the_postclaim_reauthentication_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _plan, store, first, producer, root = _fixture(tmp_path)
    second = store.find_sealed_record(
        "red-living-dex-provider-plan-v1",
        expected_kind="red-living-dex-provider-plan-v1",
    )
    assert second is not None and second is not first
    records = iter((first, second, second))

    def loader(_ordinal: int) -> RedLivingDexLoadedProducerSlot:
        return RedLivingDexLoadedProducerSlot(next(records), root)

    monkeypatch.setattr(invocation, "_require_current_consumer", lambda *_args: None)
    monkeypatch.setattr(
        invocation,
        "_build_production_resolver",
        lambda **_kwargs: object(),
    )

    def run_campaign(_store: object, **kwargs: object) -> object:
        kwargs["plan_loader"]()
        with pytest.raises(
            RedLivingDexClaimFirstInvocationError,
            match="postclaim_producer_reauthentication",
        ):
            kwargs["plan_loader"]()
        return object()

    monkeypatch.setattr(
        invocation,
        "run_red_living_dex_claim_first_setup_slot",
        run_campaign,
    )
    execute_red_living_dex_claim_first_invocation(
        Path("/public/repository"),
        store,
        consumer=_consumer(),
        producer=producer,
        producer_slot_loader=loader,
        claim_registry=_registry(tmp_path),
        rom_path=Path("/private/red.gb"),
        rom_bytes=b"authenticated-red-bytes",
        meter=RedLivingDexSetupEffectMeter(),
    )


def _ci_document(binding: RedLivingDexCurrentConsumerBinding) -> dict[str, object]:
    return {
        "conclusion": "success",
        "event": "push",
        "head_sha": binding.source_commit,
        "html_url": (
            "https://github.com/PeteAndrews1289/pokemon-red-completion-agent/"
            f"actions/runs/{binding.exact_ci_run}"
        ),
        "id": binding.exact_ci_run,
        "name": "CI",
        "path": ".github/workflows/ci.yml",
        "repository": {"full_name": "PeteAndrews1289/pokemon-red-completion-agent"},
        "run_attempt": binding.exact_ci_attempt,
        "status": "completed",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("head_sha", "d" * 40),
        ("id", 9999),
        ("run_attempt", 2),
        ("status", "queued"),
        ("conclusion", "failure"),
        ("event", "pull_request"),
        ("name", "Other"),
        ("path", ".github/workflows/other.yml"),
        ("html_url", "https://example.invalid/run"),
        ("repository", {"full_name": "other/repository"}),
    ),
)
def test_exact_ci_document_rejects_every_material_binding_swap(
    field: str,
    value: object,
) -> None:
    binding = _consumer()
    document = _ci_document(binding)
    document[field] = value
    with pytest.raises(
        RedLivingDexClaimFirstInvocationError,
        match="current_ci_authentication",
    ):
        invocation._require_exact_green_ci_document(binding, document)


@pytest.mark.parametrize("failure", ("dirty", "unpublished", "bundle"))
def test_current_consumer_rejects_dirty_unpublished_or_wrong_bundle(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    binding = _consumer()
    monkeypatch.setattr(
        invocation,
        "detect_source_identity",
        lambda _root: SourceIdentity(binding.source_commit, failure == "dirty"),
    )
    if failure == "unpublished":
        monkeypatch.setattr(
            invocation,
            "require_published_source",
            lambda *_args: (_ for _ in ()).throw(EvaluationIdentityError("not published")),
        )
    else:
        monkeypatch.setattr(invocation, "require_published_source", lambda *_args: None)
    monkeypatch.setattr(
        invocation,
        "working_source_bundle_sha256",
        lambda _root: _sha("wrong") if failure == "bundle" else binding.source_bundle_sha256,
    )
    monkeypatch.setattr(
        invocation,
        "_require_exact_green_ci",
        lambda _binding: pytest.fail("invalid source reached CI authentication"),
    )

    with pytest.raises(
        RedLivingDexClaimFirstInvocationError,
        match="current_source_authentication",
    ):
        invocation._require_current_consumer(Path("/public/repository"), binding)


def test_public_preflight_signature_cannot_receive_execution_capabilities() -> None:
    parameters = inspect.signature(
        preflight_red_living_dex_claim_first_invocation
    ).parameters
    for forbidden in (
        "store",
        "rom",
        "rom_path",
        "rom_bytes",
        "meter",
        "resolver",
        "resolver_factory",
        "runner",
    ):
        assert forbidden not in parameters

    source = Path(invocation.__file__).read_text(encoding="utf-8")
    assert "teacher_choice" not in source
    assert "model.fit(" not in source
    assert "sealed Red" not in source
