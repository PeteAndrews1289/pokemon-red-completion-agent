from __future__ import annotations

from pathlib import Path

import pytest
from test_red_living_dex_setup_recipe import (
    _ArmFactory,
    _identity,
    _Meter,
    _recipe,
    _root,
)

from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalDisposition,
    LivingDexControllerGate,
    materialize_living_dex_causal_example,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOutcomeStatus
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    initialize_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_causal_adapter import (
    build_red_living_dex_causal_scenario,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    validate_red_living_dex_setup_recipe,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _store_and_registry(tmp_path: Path) -> tuple[PrivateArtifactRoot, Path]:
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    registry = tmp_path / "claims"
    repository.mkdir()
    root.mkdir()
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return (
        initialize_private_root(
            root,
            repository_root=repository,
            device_id=device_id,
            git_worktree_probe=lambda _path: False,
        ),
        registry,
    )


def _red_scenario(tmp_path: Path):  # type: ignore[no-untyped-def]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    identity = _identity()
    factory = _ArmFactory(identity, meter)
    capture = validate_red_living_dex_setup_recipe(
        build_red_living_dex_prospective_capture_plan().slots[0],
        recipe,
        execution_identity=identity,
        root=_root(0),
        arm_factory=factory,
        meter=meter,
    )
    scenario = build_red_living_dex_causal_scenario(
        recipe,
        capture,
        setup_execution_identity=identity,
        arm_factory=factory,
        meter=meter,
        setup_terminal_sha256=_sha("setup-terminal"),
        setup_pair_claim_sha256=_sha("setup-pair-claim"),
        causal_source_commit="b" * 40,
        causal_runner_sha256=_sha("causal-runner"),
    )
    store, registry = _store_and_registry(tmp_path)
    return scenario, capture, factory, meter, store, registry


def test_validated_red_capture_emits_one_shared_causal_example(tmp_path: Path) -> None:
    scenario, capture, factory, meter, store, registry = _red_scenario(tmp_path)
    arms_before = len(factory.arms)
    actions_before = meter.controller_actions
    frames_before = meter.emulator_frames

    receipt = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert receipt.disposition in {
        LivingDexCausalDisposition.EXECUTED_SETTLED,
        LivingDexCausalDisposition.EXECUTED_CENSORED,
    }
    assert receipt.example is not None
    assert receipt.example.menu.policy_sha256 == capture.policy_projection.menu.policy_sha256
    assert len(factory.arms) == arms_before + 1
    assert meter.provider_executions == 1
    assert meter.controller_actions >= actions_before
    assert meter.emulator_frames >= frames_before
    assert receipt.public_dict()["unselected_runtimes_constructed"] == 0
    assert receipt.public_dict()["unselected_action_targets"] == 0

    recovered = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert recovered.example == receipt.example
    assert len(factory.arms) == arms_before + 1
    assert meter.provider_executions == 1


def test_reconstructed_provider_proof_drift_is_censored_not_a_failure_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, _capture, _factory, _meter, store, registry = _red_scenario(tmp_path)
    import pokemon_red_completion.red_living_dex_causal_adapter as adapter

    real_validate = adapter._validate_registry_offer

    def drifted(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        binding, fresh, _executable, offer, family = real_validate(*args, **kwargs)
        return binding, fresh, _sha("different-executable"), offer, family

    monkeypatch.setattr(adapter, "_validate_registry_offer", drifted)
    receipt = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert receipt.example is not None
    assert receipt.example.outcome.status is LivingDexOutcomeStatus.CENSORED
    assert receipt.public_dict()["causal_train_example_recorded"] is False


def test_red_runtime_restore_and_offer_construction_stay_behind_locked_gate(
    tmp_path: Path,
) -> None:
    scenario, _capture, factory, meter, _store, _registry = _red_scenario(tmp_path)
    actions_before = meter.controller_actions
    frames_before = meter.emulator_frames
    arms_before = len(factory.arms)
    gate = LivingDexControllerGate()

    with scenario.resolve_selected(0, gate) as arm:
        assert not gate.released
        assert meter.controller_actions == actions_before
        assert meter.emulator_frames == frames_before
        assert len(factory.arms) == arms_before + 1
        with pytest.raises(Exception, match="locked"):
            arm.execute(gate)

    assert meter.provider_executions == 0
