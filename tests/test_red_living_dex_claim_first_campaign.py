from __future__ import annotations

import copy
import os
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_red_living_dex_setup_recipe import _identity, _recipes, _root, _store

from pokemon_red_completion import claim_first_admission as admission
from pokemon_red_completion import red_living_dex_claim_first_campaign as campaign
from pokemon_red_completion.claim_first_admission import (
    ClaimFirstExecutionIdentity,
    ClaimFirstRootPair,
    read_root_pair_claim,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureSetupStatus,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    RedLivingDexClaimFirstCampaignError,
    RedLivingDexClaimFirstDisposition,
    RedLivingDexResolvedSetupSlot,
    run_red_living_dex_claim_first_setup_slot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
    build_red_living_dex_setup_recipe_plan,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _registry(tmp_path: Path) -> Path:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)
    return registry


def _fixture(ordinal: int = 0):  # type: ignore[no-untyped-def]
    plan = build_red_living_dex_setup_recipe_plan(
        _recipes(),
        execution_identity=_identity(),
    )
    root = _root(ordinal)
    document = plan.private_dict()
    recipe = plan.recipes[ordinal]
    outer = ClaimFirstExecutionIdentity(
        source_commit="c" * 40,
        source_bundle_sha256=_sha("current-source"),
        exact_ci_run=777,
        exact_ci_attempt=1,
        producer_execution_identity_sha256=plan.execution_identity.identity_sha256,
        producer_plan_sha256=plan.plan_sha256,
        producer_private_plan_sha256=_sha("private-plan"),
        producer_manifest_sha256=_sha("manifest"),
        slot_sha256=recipe.slot_sha256,
        recipe_sha256=recipe.recipe_sha256,
        logical_root_sha256=root.root_consumption_sha256,
        physical_root_sha256=root.physical_root_sha256,
        title_adapter_sha256=_sha("red-adapter"),
        runtime_factory_sha256=_sha("runtime-factory"),
        runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    )
    return plan, root, document, outer


@dataclass
class _FakeCapture:
    recipe_sha256: str
    execution_identity_sha256: str
    attestation: Any

    def private_dict(self) -> dict[str, object]:
        return {
            "attestation_sha256": self.attestation.attestation_sha256,
            "execution_identity_sha256": self.execution_identity_sha256,
            "recipe_sha256": self.recipe_sha256,
            "schema": "test.red.claim-first-capture.v1",
        }


class _ResolvedScope(AbstractContextManager[RedLivingDexResolvedSetupSlot]):
    def __init__(self, resolved: RedLivingDexResolvedSetupSlot, events: list[str]) -> None:
        self._resolved = resolved
        self._events = events

    def __enter__(self) -> RedLivingDexResolvedSetupSlot:
        self._events.append("scope_enter")
        return self._resolved

    def __exit__(self, *_args: object) -> None:
        self._events.append("scope_exit")


class _Resolver:
    def __init__(
        self,
        plan: Any,
        outer: ClaimFirstExecutionIdentity,
        events: list[str],
        *,
        recipe_override: Any | None = None,
    ) -> None:
        self._plan = plan
        self._outer = outer
        self._events = events
        self._recipe_override = recipe_override

    def __call__(
        self,
        frozen: Any,
        root: Any,
        pair_claim: ClaimFirstRootPair,
        *,
        meter: RedLivingDexSetupEffectMeter,
    ) -> AbstractContextManager[RedLivingDexResolvedSetupSlot]:
        del root, meter
        self._events.append("resolver_call")
        assert pair_claim.claim_sha256 == self._outer.root_pair(
            stage="setup-capture"
        ).claim_sha256
        recipe = (
            self._plan.recipes[frozen.ordinal]
            if self._recipe_override is None
            else self._recipe_override
        )
        return _ResolvedScope(
            RedLivingDexResolvedSetupSlot(
                recipe=recipe,
                producer_execution_identity=self._plan.execution_identity,
                arm_factory=lambda *_args: None,
                title_adapter_sha256=self._outer.title_adapter_sha256,
                runtime_factory_sha256=self._outer.runtime_factory_sha256,
            ),
            self._events,
        )


class _ForbiddenResolver:
    def __call__(self, *_args: object, **_kwargs: object) -> Any:
        raise AssertionError("recovery invoked the resolver")


def _install_fake_validator(
    monkeypatch: pytest.MonkeyPatch,
    plan: Any,
    events: list[str],
) -> _FakeCapture:
    capture = _FakeCapture(
        plan.recipes[0].recipe_sha256,
        plan.execution_identity.identity_sha256,
        SimpleNamespace(
            setup_controller_actions=0,
            setup_emulator_frames=0,
            attestation_sha256=_sha("attestation"),
        ),
    )

    def validate(*_args: object, **_kwargs: object) -> _FakeCapture:
        events.append("validator")
        return capture

    monkeypatch.setattr(campaign, "validate_red_living_dex_setup_recipe", validate)
    monkeypatch.setattr(
        campaign,
        "restore_red_living_dex_validated_setup_capture",
        lambda _document: capture,
    )
    return capture


def test_claims_both_roots_and_local_episode_before_cold_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, root, document, outer = _fixture()
    events: list[str] = []
    loads = 0

    def load() -> dict[str, object]:
        nonlocal loads
        loads += 1
        events.append(f"plan_load_{loads}")
        return copy.deepcopy(document)

    _install_fake_validator(monkeypatch, plan, events)
    registry = _registry(tmp_path)
    meter = RedLivingDexSetupEffectMeter()

    receipt = run_red_living_dex_claim_first_setup_slot(
        _store(tmp_path),
        plan_loader=load,
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_Resolver(plan, outer, events),
        meter=meter,
        claim_registry=registry,
        failpoint=lambda stage, _frozen: events.append(stage),
    )

    pair = outer.root_pair(stage="setup-capture")
    assert read_root_pair_claim(registry, pair.claim_sha256) == pair
    assert receipt.disposition is RedLivingDexClaimFirstDisposition.EXECUTED_COMPLETE
    assert receipt.terminal.status is LivingDexCaptureSetupStatus.COMPLETE
    assert meter.checkpoint().root_claims == 1
    assert events.index("after_local_claim") < events.index("plan_load_2")
    assert events.index("plan_load_2") < events.index("resolver_call")
    assert events.index("scope_enter") < events.index("validator") < events.index("scope_exit")


def test_completed_recovery_never_reauthenticates_or_constructs_a_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, root, document, outer = _fixture()
    events: list[str] = []
    _install_fake_validator(monkeypatch, plan, events)
    registry = _registry(tmp_path)
    store = _store(tmp_path)
    first = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=lambda: copy.deepcopy(document),
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_Resolver(plan, outer, events),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
    )
    assert first.newly_executed

    recovered = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=lambda: copy.deepcopy(document),
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_ForbiddenResolver(),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
    )

    assert recovered.disposition is RedLivingDexClaimFirstDisposition.RECOVERED_COMPLETE
    assert not recovered.newly_executed


@pytest.mark.parametrize("cutpoint", ("after_pair_claim", "after_local_claim"))
def test_crash_cutpoints_recover_without_runtime_or_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cutpoint: str,
) -> None:
    plan, root, document, outer = _fixture()
    _install_fake_validator(monkeypatch, plan, [])
    registry = _registry(tmp_path)
    store = _store(tmp_path)

    def crash(stage: str, _frozen: object) -> None:
        if stage == cutpoint:
            raise RuntimeError("synthetic power loss")

    with pytest.raises(RuntimeError, match="power loss"):
        run_red_living_dex_claim_first_setup_slot(
            store,
            plan_loader=lambda: copy.deepcopy(document),
            expected_producer_plan_sha256=plan.plan_sha256,
            ordinal=0,
            root=root,
            outer_execution_identity=outer,
            resolver=_ForbiddenResolver(),
            meter=RedLivingDexSetupEffectMeter(),
            claim_registry=registry,
            failpoint=crash,
        )

    recovered = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=lambda: copy.deepcopy(document),
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_ForbiddenResolver(),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
    )
    assert recovered.disposition is RedLivingDexClaimFirstDisposition.RECOVERED_INTERRUPTED
    assert recovered.terminal.retry_allowed is False
    assert not recovered.newly_executed


def test_uncertain_pair_directory_fsync_recovers_without_runtime_or_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, root, document, outer = _fixture()
    registry = _registry(tmp_path)
    store = _store(tmp_path)
    real_fsync = os.fsync
    calls = 0

    def fail_after_pair_rename(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic uncertain directory durability")
        real_fsync(descriptor)

    monkeypatch.setattr(admission.os, "fsync", fail_after_pair_rename)
    with pytest.raises(RedLivingDexClaimFirstCampaignError, match="could not be retained"):
        run_red_living_dex_claim_first_setup_slot(
            store,
            plan_loader=lambda: copy.deepcopy(document),
            expected_producer_plan_sha256=plan.plan_sha256,
            ordinal=0,
            root=root,
            outer_execution_identity=outer,
            resolver=_ForbiddenResolver(),
            meter=RedLivingDexSetupEffectMeter(),
            claim_registry=registry,
        )

    pair = outer.root_pair(stage="setup-capture")
    assert read_root_pair_claim(registry, pair.claim_sha256) == pair
    monkeypatch.setattr(admission.os, "fsync", real_fsync)

    recovered = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=lambda: copy.deepcopy(document),
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_ForbiddenResolver(),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
    )
    assert recovered.disposition is RedLivingDexClaimFirstDisposition.RECOVERED_INTERRUPTED
    assert recovered.terminal.status is LivingDexCaptureSetupStatus.INTERRUPTED
    assert recovered.terminal.retry_allowed is False
    assert not recovered.newly_executed


@pytest.mark.parametrize(
    "cutpoint",
    (
        "after_plan_reauthentication",
        "after_runtime_scope_open",
        "after_capture_append",
    ),
)
def test_postlocal_cutpoints_settle_once_and_recovery_never_reopens_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cutpoint: str,
) -> None:
    plan, root, document, outer = _fixture()
    events: list[str] = []
    _install_fake_validator(monkeypatch, plan, events)
    registry = _registry(tmp_path)
    store = _store(tmp_path)

    def crash(stage: str, _frozen: object) -> None:
        if stage == cutpoint:
            raise RuntimeError("synthetic postlocal power loss")

    failed = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=lambda: copy.deepcopy(document),
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_Resolver(plan, outer, events),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
        failpoint=crash,
    )
    assert failed.disposition is RedLivingDexClaimFirstDisposition.EXECUTED_FAILED
    assert failed.terminal.retry_allowed is False
    if cutpoint == "after_runtime_scope_open":
        assert "scope_exit" in events

    recovered = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=lambda: copy.deepcopy(document),
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_ForbiddenResolver(),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
    )
    assert recovered.disposition is RedLivingDexClaimFirstDisposition.RECOVERED_FAILED
    assert not recovered.newly_executed


def test_base_exception_closes_runtime_and_remains_permanently_interrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, root, document, outer = _fixture()
    events: list[str] = []
    _install_fake_validator(monkeypatch, plan, events)
    registry = _registry(tmp_path)
    store = _store(tmp_path)

    def interrupt(stage: str, _frozen: object) -> None:
        if stage == "after_runtime_scope_open":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_red_living_dex_claim_first_setup_slot(
            store,
            plan_loader=lambda: copy.deepcopy(document),
            expected_producer_plan_sha256=plan.plan_sha256,
            ordinal=0,
            root=root,
            outer_execution_identity=outer,
            resolver=_Resolver(plan, outer, events),
            meter=RedLivingDexSetupEffectMeter(),
            claim_registry=registry,
            failpoint=interrupt,
        )
    assert "scope_exit" in events

    recovered = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=lambda: copy.deepcopy(document),
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_ForbiddenResolver(),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
    )
    assert recovered.terminal.status is LivingDexCaptureSetupStatus.INTERRUPTED
    assert recovered.terminal.retry_allowed is False


def test_deep_plan_drift_after_local_claim_fails_without_opening_runtime(
    tmp_path: Path,
) -> None:
    plan, root, document, outer = _fixture()
    loads = 0

    def load() -> dict[str, object]:
        nonlocal loads
        loads += 1
        current = copy.deepcopy(document)
        if loads == 2:
            current["learner_effects"] = 1
        return current

    receipt = run_red_living_dex_claim_first_setup_slot(
        _store(tmp_path),
        plan_loader=load,
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_ForbiddenResolver(),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=_registry(tmp_path),
    )

    assert receipt.disposition is RedLivingDexClaimFirstDisposition.EXECUTED_FAILED
    assert receipt.terminal.status is LivingDexCaptureSetupStatus.FAILED
    assert receipt.terminal.setup_controller_actions == 0
    assert receipt.terminal.setup_emulator_frames == 0


def test_resolver_substitution_fails_before_validator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, root, document, outer = _fixture()
    called = False

    def forbidden_validator(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("substituted recipe reached validator")

    monkeypatch.setattr(
        campaign,
        "validate_red_living_dex_setup_recipe",
        forbidden_validator,
    )
    changed = replace(
        plan.recipes[0],
        root_consumption_sha256="f" * 64,
    )
    receipt = run_red_living_dex_claim_first_setup_slot(
        _store(tmp_path),
        plan_loader=lambda: copy.deepcopy(document),
        expected_producer_plan_sha256=plan.plan_sha256,
        ordinal=0,
        root=root,
        outer_execution_identity=outer,
        resolver=_Resolver(plan, outer, [], recipe_override=changed),
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=_registry(tmp_path),
    )

    assert receipt.disposition is RedLivingDexClaimFirstDisposition.EXECUTED_FAILED
    assert not called


def test_outer_identity_must_bind_exact_runner_and_frozen_slot(tmp_path: Path) -> None:
    plan, root, document, outer = _fixture()
    with pytest.raises(RedLivingDexClaimFirstCampaignError, match="outer execution"):
        run_red_living_dex_claim_first_setup_slot(
            _store(tmp_path),
            plan_loader=lambda: copy.deepcopy(document),
            expected_producer_plan_sha256=plan.plan_sha256,
            ordinal=0,
            root=root,
            outer_execution_identity=replace(outer, runner_sha256=_sha("other-runner")),
            resolver=_ForbiddenResolver(),
            meter=RedLivingDexSetupEffectMeter(),
            claim_registry=_registry(tmp_path),
        )
