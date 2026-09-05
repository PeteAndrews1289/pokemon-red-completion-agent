from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_living_dex_causal_campaign import (
    _ForbiddenResolver,
    _Resolver,
    _sha,
)
from test_red_living_dex_claim_first_invocation import (
    _consumer,
    _fixture,
    _fresh_loader,
    _registry,
)
from test_red_living_dex_setup_recipe import _ArmFactory

from pokemon_red_completion import red_living_dex_causal_invocation as invocation
from pokemon_red_completion.claim_first_admission import ClaimFirstExecutionIdentity
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalDisposition,
)
from pokemon_red_completion.red_living_dex_causal_campaign import (
    RedLivingDexFrozenCausalCampaign,
    freeze_red_living_dex_causal_campaign,
)
from pokemon_red_completion.red_living_dex_causal_invocation import (
    RedLivingDexCausalInvocationError,
    authenticate_red_living_dex_current_consumer,
    bind_red_living_dex_authenticated_consumer,
    execute_red_living_dex_causal_campaign,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_admission import (
    authenticate_frozen_red_living_dex_setup_slot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
)


def _frozen_fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    recipe_plan, store, _record, producer, root = _fixture(tmp_path, ordinal=0)
    frozen = authenticate_frozen_red_living_dex_setup_slot(
        recipe_plan.private_dict(),
        expected_plan_sha256=recipe_plan.plan_sha256,
        ordinal=producer.ordinal,
        root=root,
    )
    frozen_outer = ClaimFirstExecutionIdentity(
        source_commit="a" * 40,
        source_bundle_sha256=_sha("freeze-source"),
        exact_ci_run=111,
        exact_ci_attempt=1,
        producer_execution_identity_sha256=(frozen.producer_execution_identity_sha256),
        producer_plan_sha256=producer.producer_plan_sha256,
        producer_private_plan_sha256=producer.producer_private_plan_sha256,
        producer_manifest_sha256=producer.producer_manifest_sha256,
        slot_sha256=frozen.slot_sha256,
        recipe_sha256=frozen.recipe_sha256,
        logical_root_sha256=frozen.logical_root_sha256,
        physical_root_sha256=frozen.physical_root_sha256,
        title_adapter_sha256=RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
        runtime_factory_sha256=RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
        runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    )
    registry = _registry(tmp_path)
    campaign = freeze_red_living_dex_causal_campaign(
        store,
        frozen=frozen,
        outer_execution_identity=frozen_outer,
        retired_physical_root_sha256s=(_sha("retired-physical-root"),),
        claim_registry=registry,
    )
    return recipe_plan, store, producer, root, frozen_outer, registry, campaign


def _authenticated_consumer():  # type: ignore[no-untyped-def]
    binding = _consumer()
    return bind_red_living_dex_authenticated_consumer(
        binding,
        bootstrap_identity=(
            binding.source_commit,
            binding.source_bundle_sha256,
            binding.exact_ci_run,
            binding.exact_ci_attempt,
        ),
    )


def test_repeatable_consumer_requires_clean_published_source_and_green_ci(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _consumer()
    calls: list[tuple[Path, object]] = []
    monkeypatch.setattr(
        invocation,
        "require_red_living_dex_current_consumer",
        lambda root, expected: calls.append((root, expected)),
    )

    consumer = authenticate_red_living_dex_current_consumer(tmp_path, binding)

    assert calls == [(tmp_path, binding)]
    assert consumer.binding == binding
    consumer.__post_init__()


def test_direct_invocation_surface_has_no_plan_identity_resolver_or_registry_injection() -> None:
    parameters = inspect.signature(execute_red_living_dex_causal_campaign).parameters
    assert "claim_registry" not in parameters
    assert "producer" not in parameters
    assert "resolver" not in parameters
    assert "runtime_factory" not in parameters
    assert "campaign" not in parameters
    assert "selected_candidate_index" not in parameters
    assert "behavior_seed" not in parameters


def test_freeze_at_a_executes_under_b_and_terminal_recovery_stays_runtime_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        recipe_plan,
        store,
        producer,
        root,
        frozen_outer,
        registry,
        campaign,
    ) = _frozen_fixture(tmp_path)
    ordinals: list[int] = []
    meter = RedLivingDexSetupEffectMeter()
    factory = _ArmFactory(recipe_plan.execution_identity, meter)
    resolver = _Resolver(recipe_plan, frozen_outer, factory)
    monkeypatch.setattr(
        invocation,
        "_authenticate_current_execution_runtime",
        lambda *_args: _sha("runtime"),
    )
    monkeypatch.setattr(
        invocation,
        "fixed_account_claim_registry_root",
        lambda: registry,
    )
    monkeypatch.setattr(
        invocation,
        "_LateProductionResolver",
        lambda **_kwargs: resolver,
    )

    receipt = execute_red_living_dex_causal_campaign(
        Path("/public/repository"),
        store,
        consumer=_authenticated_consumer(),
        producer_slot_loader=_fresh_loader(store, root, ordinals),
        rom_path=tmp_path / "must-not-open.gb",
        meter=meter,
    )

    assert isinstance(receipt.plan, RedLivingDexFrozenCausalCampaign)
    assert receipt.plan == campaign
    assert receipt.plan.causal_source_commit == "a" * 40
    assert receipt.execution_identity.setup_execution_identity.source_commit == (
        _consumer().source_commit
    )
    assert receipt.causal is not None
    assert receipt.causal.scenario.identity.source_commit == _consumer().source_commit
    assert receipt.causal.disposition is LivingDexCausalDisposition.EXECUTED_SETTLED
    assert receipt.public_dict()["causal_train_example_recorded"] is True
    assert ordinals == [producer.ordinal] * 4
    assert resolver.calls == 2

    forbidden = _ForbiddenResolver()
    recovery_ordinals: list[int] = []
    monkeypatch.setattr(
        invocation,
        "_LateProductionResolver",
        lambda **_kwargs: forbidden,
    )
    recovered = execute_red_living_dex_causal_campaign(
        Path("/public/repository"),
        store,
        consumer=_authenticated_consumer(),
        producer_slot_loader=_fresh_loader(store, root, recovery_ordinals),
        rom_path=tmp_path / "still-must-not-open.gb",
        meter=RedLivingDexSetupEffectMeter(),
    )

    assert recovered.causal is not None
    assert recovered.causal.example == receipt.causal.example
    assert forbidden.calls == 0
    assert recovery_ordinals == [producer.ordinal] * 2


def test_late_resolver_does_not_read_rom_until_postclaim_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe_plan, _store, _producer, _root, _outer, _registry_path, _campaign = _frozen_fixture(
        tmp_path
    )
    reads: list[Path] = []
    constructed: list[bytes] = []
    rom_path = tmp_path / "late.gb"

    class Delegate:
        def __init__(self, *, rom_path: Path, rom_bytes: bytes, **_kwargs: object) -> None:
            assert rom_path == tmp_path / "late.gb"
            constructed.append(rom_bytes)

        def __call__(self, *_args: object, **_kwargs: object) -> object:
            return object()

    monkeypatch.setattr(
        invocation,
        "_read_stable_red_rom",
        lambda path: reads.append(path) or b"red-rom",
    )
    monkeypatch.setattr(invocation, "RedLivingDexProductionSetupResolver", Delegate)
    late = invocation._LateProductionResolver(
        rom_path=rom_path,
        producer_execution_identity=recipe_plan.execution_identity,
    )

    assert reads == []
    assert constructed == []
    late(object(), object(), object(), meter=RedLivingDexSetupEffectMeter())
    assert reads == [rom_path]
    assert constructed == [b"red-rom"]


def test_runtime_identity_failure_precedes_resolver_construction_and_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _recipe_plan, store, producer, root, _outer, registry, _campaign = (
        _frozen_fixture(tmp_path)
    )
    ordinals: list[int] = []
    before = tuple(sorted(path.relative_to(registry) for path in registry.rglob("*")))
    monkeypatch.setattr(
        invocation,
        "fixed_account_claim_registry_root",
        lambda: registry,
    )
    monkeypatch.setattr(
        invocation,
        "_authenticate_current_execution_runtime",
        lambda *_args: (_ for _ in ()).throw(
            RedLivingDexCausalInvocationError("runtime_identity_authentication")
        ),
    )
    monkeypatch.setattr(
        invocation,
        "_LateProductionResolver",
        lambda **_kwargs: pytest.fail("resolver constructed before runtime identity"),
    )

    with pytest.raises(
        RedLivingDexCausalInvocationError,
        match="runtime_identity_authentication",
    ):
        execute_red_living_dex_causal_campaign(
            Path("/public/repository"),
            store,
            consumer=_authenticated_consumer(),
            producer_slot_loader=_fresh_loader(store, root, ordinals),
            rom_path=tmp_path / "must-not-open.gb",
            meter=RedLivingDexSetupEffectMeter(),
        )

    assert ordinals == [producer.ordinal]
    assert tuple(sorted(path.relative_to(registry) for path in registry.rglob("*"))) == before


def test_runtime_authentication_checks_stage_origins_and_sealed_pyboy_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    original = project_root / ".venv/lib/python3.14/site-packages"
    staged = tmp_path / "stage/venv/lib/python3.14/site-packages"
    original.mkdir(parents=True)
    (staged / "pyboy-2.7.0.dist-info").mkdir(parents=True)
    expected = _sha("sealed-runtime")
    closure = object()
    calls: list[str] = []
    monkeypatch.setattr(invocation.sys, "path", [str(staged)])
    monkeypatch.setattr(
        invocation,
        "authenticate_execution_runtime_closure",
        lambda path: calls.append(f"closure:{path}") or closure,
    )
    monkeypatch.setattr(
        invocation,
        "require_authenticated_runtime_finder",
        lambda value: calls.append("finder") if value is closure else pytest.fail(),
    )
    monkeypatch.setattr(
        invocation,
        "require_loaded_runtime_origins",
        lambda value: calls.append("origins") if value is closure else pytest.fail(),
    )
    monkeypatch.setattr(
        invocation.metadata,
        "PathDistribution",
        lambda path: calls.append(f"distribution:{path}") or object(),
    )
    monkeypatch.setattr(
        invocation,
        "build_runtime_identity_from",
        lambda **_kwargs: calls.append("identity")
        or SimpleNamespace(sha256=expected),
    )
    record = SimpleNamespace(read=lambda: {"runtime_identity_sha256": expected})

    assert invocation._authenticate_current_execution_runtime(  # type: ignore[arg-type]
        project_root,
        record,
    ) == expected
    assert calls[1:3] == ["finder", "origins"]

    monkeypatch.setattr(
        invocation,
        "build_runtime_identity_from",
        lambda **_kwargs: SimpleNamespace(sha256=_sha("substituted-runtime")),
    )
    with pytest.raises(
        RedLivingDexCausalInvocationError,
        match="runtime_identity_authentication",
    ):
        invocation._authenticate_current_execution_runtime(  # type: ignore[arg-type]
            project_root,
            record,
        )
