from __future__ import annotations

from pathlib import Path

import pytest
from test_red_living_dex_claim_first_campaign import _registry
from test_red_living_dex_clustered_train_runner import (
    _ArmFactory,
    _identity,
    _Resolver,
    _successor_clustered_fixture,
)
from test_red_living_dex_setup_recipe import _store

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstExecutionIdentity,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureSetupStatus,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    authenticate_red_living_dex_clustered_development_selection,
)
from pokemon_red_completion.red_living_dex_development_setup_admission import (
    authenticate_frozen_red_living_dex_development_setup_slot,
)
from pokemon_red_completion.red_living_dex_development_setup_journal import (
    RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256,
    RedLivingDexDevelopmentSetupDisposition,
    run_red_living_dex_development_setup,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    plan, binding = _successor_clustered_fixture()
    selection = authenticate_red_living_dex_clustered_development_selection(
        plan.private_dict(),
        16,
        binding=binding,
    )
    capability = plan.assignments[selection.ordinal].capability
    identity = _identity()
    frozen = authenticate_frozen_red_living_dex_development_setup_slot(
        plan.private_dict(),
        selection=selection,
        binding=binding,
        root=capability.root.root,
        producer_execution_identity=identity,
        expected_runtime_identity_sha256=plan.bindings.runtime_identity_sha256,
    )
    outer = ClaimFirstExecutionIdentity(
        source_commit="d" * 40,
        source_bundle_sha256=_sha("development-current-source"),
        exact_ci_run=12345,
        exact_ci_attempt=1,
        producer_execution_identity_sha256=identity.identity_sha256,
        producer_plan_sha256=selection.private_plan_sha256,
        producer_private_plan_sha256=selection.private_plan_sha256,
        producer_manifest_sha256=binding.plan_manifest_sha256,
        slot_sha256=selection.slot_sha256,
        recipe_sha256=selection.recipe_sha256,
        logical_root_sha256=selection.logical_root_sha256,
        physical_root_sha256=selection.physical_root_sha256,
        title_adapter_sha256=RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
        runtime_factory_sha256=RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
        runner_sha256=RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256,
    )
    meter = RedLivingDexSetupEffectMeter()
    resolver = _Resolver(
        capability.recipe,
        identity,
        _ArmFactory(identity, meter),
    )
    return (
        plan,
        capability,
        frozen,
        outer,
        meter,
        resolver,
        _store(tmp_path),
        _registry(tmp_path),
    )


class _ForbiddenResolver:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise AssertionError("recovery reopened the Red runtime")


def test_development_setup_executes_once_and_recovers_terminal(
    tmp_path: Path,
) -> None:
    plan, capability, frozen, outer, meter, resolver, store, registry = _fixture(
        tmp_path
    )

    receipt = run_red_living_dex_development_setup(
        frozen,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=capability.root.root,
        outer_execution_identity=outer,
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
    )

    assert receipt.terminal.status in {
        LivingDexCaptureSetupStatus.COMPLETE,
        LivingDexCaptureSetupStatus.FAILED,
    }
    assert resolver.calls == 1
    assert receipt.public_dict()["development_outcomes_opened"] == 0
    assert receipt.public_dict()["training_targets_emitted"] == 0

    forbidden = _ForbiddenResolver()
    recovered = run_red_living_dex_development_setup(
        frozen,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=capability.root.root,
        outer_execution_identity=outer,
        resolver=forbidden,
        meter=meter,
        claim_registry=registry,
    )
    assert recovered.terminal == receipt.terminal
    assert recovered.disposition in {
        RedLivingDexDevelopmentSetupDisposition.RECOVERED_COMPLETE,
        RedLivingDexDevelopmentSetupDisposition.RECOVERED_FAILED,
    }
    assert forbidden.calls == 0


def test_interruption_after_pair_claim_is_terminal_without_runtime(
    tmp_path: Path,
) -> None:
    plan, capability, frozen, outer, meter, resolver, store, registry = _fixture(
        tmp_path
    )

    def failpoint(stage: str, _frozen: object) -> None:
        if stage == "after_pair_claim":
            raise RuntimeError("power loss")

    with pytest.raises(RuntimeError, match="power loss"):
        run_red_living_dex_development_setup(
            frozen,
            store=store,
            plan_loader=lambda: plan.private_dict(),
            root=capability.root.root,
            outer_execution_identity=outer,
            resolver=resolver,
            meter=meter,
            claim_registry=registry,
            failpoint=failpoint,
        )
    assert resolver.calls == 0

    recovered = run_red_living_dex_development_setup(
        frozen,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=capability.root.root,
        outer_execution_identity=outer,
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
    )
    assert recovered.disposition is (
        RedLivingDexDevelopmentSetupDisposition.RECOVERED_INTERRUPTED
    )
    assert recovered.terminal.status is LivingDexCaptureSetupStatus.INTERRUPTED
    assert recovered.terminal.retry_allowed is False
    assert resolver.calls == 0


def test_interruption_after_controller_release_never_reopens_runtime(
    tmp_path: Path,
) -> None:
    plan, capability, frozen, outer, meter, resolver, store, registry = _fixture(
        tmp_path
    )

    def failpoint(stage: str, _frozen: object) -> None:
        if stage == "after_controller_release":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_red_living_dex_development_setup(
            frozen,
            store=store,
            plan_loader=lambda: plan.private_dict(),
            root=capability.root.root,
            outer_execution_identity=outer,
            resolver=resolver,
            meter=meter,
            claim_registry=registry,
            failpoint=failpoint,
        )

    forbidden = _ForbiddenResolver()
    recovered = run_red_living_dex_development_setup(
        frozen,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=capability.root.root,
        outer_execution_identity=outer,
        resolver=forbidden,
        meter=meter,
        claim_registry=registry,
    )
    assert recovered.disposition is (
        RedLivingDexDevelopmentSetupDisposition.RECOVERED_INTERRUPTED
    )
    assert forbidden.calls == 0
