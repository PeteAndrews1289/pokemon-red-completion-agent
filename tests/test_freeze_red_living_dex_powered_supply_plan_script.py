from __future__ import annotations

import hashlib
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256,
    compose_red_living_dex_powered_supply_generator_sha256,
    parse_red_living_dex_powered_supply_plan,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/freeze_red_living_dex_powered_supply_plan.py"),
    run_name="freeze_red_living_dex_powered_supply_plan_test",
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):  # type: ignore[no-untyped-def]
    capacity = tmp_path / "capacity-result.json"
    generator = tmp_path / "generator.py"
    conditioner = tmp_path / "conditioner.py"
    capacity.write_bytes(b'{"status":"powered-capacity-insufficient"}\n')
    generator.write_bytes(b"generator-v2\n")
    conditioner.write_bytes(b"conditioner-v2\n")
    source_bundle = _digest(b"published-source")
    capacity_sha256 = _digest(capacity.read_bytes())
    generator_execution = compose_red_living_dex_powered_supply_generator_sha256(
        source_bundle_sha256=source_bundle,
        generator_runner_sha256=_digest(generator.read_bytes()),
        conditioner_runner_sha256=_digest(conditioner.read_bytes()),
    )
    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "CAPACITY_RESULT_PATH", capacity)
    monkeypatch.setitem(globals_, "GENERATOR_PATH", generator)
    monkeypatch.setitem(globals_, "CONDITIONER_PATH", conditioner)
    monkeypatch.setitem(
        globals_,
        "RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256",
        capacity_sha256,
    )
    monkeypatch.setitem(
        globals_,
        "detect_source_identity",
        lambda *_args, **_kwargs: SimpleNamespace(git_commit="a" * 40),
    )
    monkeypatch.setitem(globals_, "require_clean_source", lambda _source: None)
    monkeypatch.setitem(
        globals_,
        "require_published_source",
        lambda _root, _source: None,
    )
    monkeypatch.setitem(
        globals_,
        "working_source_bundle_sha256",
        lambda _root: source_bundle,
    )
    runtime_identity = _digest(b"runtime-identity")
    monkeypatch.setitem(
        globals_,
        "build_runtime_identity",
        lambda: SimpleNamespace(sha256=runtime_identity),
    )
    return capacity, generator, conditioner, source_bundle, generator_execution


def _args(
    *,
    output: Path,
    capacity: Path,
    source_bundle: str,
    generator_execution: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        out=output,
        expected_source_commit="a" * 40,
        expected_source_bundle_sha256=source_bundle,
        expected_generator_execution_sha256=generator_execution,
        expected_runtime_identity_sha256=_digest(b"runtime-identity"),
        expected_capacity_result_sha256=_digest(capacity.read_bytes()),
        expected_powered_design_sha256=RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256,
    )


def test_freezer_writes_one_canonical_v2_plan_without_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capacity, _generator, _conditioner, source_bundle, generator_execution = _fixture(
        tmp_path, monkeypatch
    )
    output = tmp_path / "powered-supply-plan.json"

    result = SCRIPT["_run"](
        _args(
            output=output,
            capacity=capacity,
            source_bundle=source_bundle,
            generator_execution=generator_execution,
        )
    )
    payload = output.read_bytes()
    plan = parse_red_living_dex_powered_supply_plan(payload)

    assert len(plan.assignments) == 12
    assert result["plan_file_sha256"] == _digest(payload)
    assert result["status"] == (
        "bounded_powered_lineage_supply_plan_frozen_without_execution"
    )
    assert result["generator_runner_sha256"] == plan.generator_runner_sha256
    assert result["conditioner_runner_sha256"] == (
        plan.conditioner_runner_sha256
    )
    assert result["runtime_identity_sha256"] == plan.runtime_identity_sha256
    for field in (
        "behavior_draws",
        "controller_actions",
        "emulator_frames",
        "learner_labels",
        "learner_outcomes",
        "model_fits",
        "model_predictions",
        "provider_executions",
        "root_claims",
        "root_generation_executions",
        "teacher_queries",
    ):
        assert result[field] == 0


def test_freezer_is_create_only_and_rejects_source_or_evidence_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capacity, _generator, _conditioner, source_bundle, generator_execution = _fixture(
        tmp_path, monkeypatch
    )
    output = tmp_path / "powered-supply-plan.json"
    args = _args(
        output=output,
        capacity=capacity,
        source_bundle=source_bundle,
        generator_execution=generator_execution,
    )
    SCRIPT["_run"](args)

    with pytest.raises(
        SCRIPT["PoweredSupplyFreezeError"],
        match="exclusive_plan_publication",
    ):
        SCRIPT["_run"](args)

    second_output = tmp_path / "drifted-plan.json"
    with pytest.raises(
        SCRIPT["PoweredSupplyFreezeError"],
        match="source_authentication",
    ):
        SCRIPT["_run"](
            SimpleNamespace(
                **{
                    **vars(args),
                    "out": second_output,
                    "expected_source_bundle_sha256": "f" * 64,
                }
            )
        )
    assert not second_output.exists()


def test_freezer_rejects_runtime_drift_before_publishing_a_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capacity, _generator, _conditioner, source_bundle, generator_execution = _fixture(
        tmp_path, monkeypatch
    )
    output = tmp_path / "runtime-drifted-plan.json"
    args = _args(
        output=output,
        capacity=capacity,
        source_bundle=source_bundle,
        generator_execution=generator_execution,
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "build_runtime_identity",
        lambda: SimpleNamespace(sha256=_digest(b"different-runtime")),
    )

    with pytest.raises(
        SCRIPT["PoweredSupplyFreezeError"],
        match="runtime_authentication",
    ):
        SCRIPT["_run"](args)

    assert not output.exists()


def test_generator_execution_binding_detects_runner_or_conditioner_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capacity, generator, conditioner, source_bundle, expected = _fixture(
        tmp_path, monkeypatch
    )

    assert SCRIPT["_generator_execution"](source_bundle) == expected
    generator.write_bytes(b"generator-v3\n")
    assert SCRIPT["_generator_execution"](source_bundle) != expected
    generator.write_bytes(b"generator-v2\n")
    conditioner.write_bytes(b"conditioner-v3\n")
    assert SCRIPT["_generator_execution"](source_bundle) != expected


def test_freezer_cli_has_no_rom_execution_retry_or_learning_surface() -> None:
    parser = SCRIPT["_parser"]()
    parsed = parser.parse_args(
        [
            "--expected-source-commit",
            "a" * 40,
            "--expected-source-bundle-sha256",
            "b" * 64,
            "--expected-generator-execution-sha256",
            "c" * 64,
            "--expected-runtime-identity-sha256",
            "f" * 64,
            "--expected-capacity-result-sha256",
            "d" * 64,
            "--expected-powered-design-sha256",
            "e" * 64,
            "--out",
            "/private/plan.json",
        ]
    )

    assert parsed.out == Path("/private/plan.json")
    for forbidden in (
        "rom",
        "watch",
        "teacher",
        "model",
        "fit",
        "outcome",
        "seed",
        "retry",
        "assignment",
        "private_root",
    ):
        assert not hasattr(parsed, forbidden)
