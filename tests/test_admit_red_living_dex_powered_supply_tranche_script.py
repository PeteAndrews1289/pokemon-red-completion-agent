from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    build_red_living_dex_powered_supply_plan,
    compose_red_living_dex_powered_supply_generator_sha256,
    compose_red_living_dex_powered_supply_teacher_sha256,
    encode_red_living_dex_powered_supply_plan,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/admit_red_living_dex_powered_supply_tranche.py"),
    run_name="admit_red_living_dex_powered_supply_tranche_test",
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):  # type: ignore[no-untyped-def]
    generator_path = tmp_path / "generator.py"
    conditioner_path = tmp_path / "conditioner.py"
    generator_path.write_bytes(b"generator-v2\n")
    conditioner_path.write_bytes(b"conditioner-v2\n")
    source_bundle = _sha(b"source-bundle")
    runner_sha256 = _sha(generator_path.read_bytes())
    conditioner_sha256 = _sha(conditioner_path.read_bytes())
    generator_execution = compose_red_living_dex_powered_supply_generator_sha256(
        source_bundle_sha256=source_bundle,
        generator_runner_sha256=runner_sha256,
        conditioner_runner_sha256=conditioner_sha256,
    )
    plan = build_red_living_dex_powered_supply_plan(
        source_commit="a" * 40,
        source_bundle_sha256=source_bundle,
        teacher_execution_sha256=(
            compose_red_living_dex_powered_supply_teacher_sha256(
                source_bundle_sha256=source_bundle,
                generator_execution_sha256=generator_execution,
            )
        ),
        generator_execution_sha256=generator_execution,
        generator_runner_sha256=runner_sha256,
        conditioner_runner_sha256=conditioner_sha256,
        runtime_identity_sha256=_sha(b"runtime-identity"),
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(encode_red_living_dex_powered_supply_plan(plan))
    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "GENERATOR_PATH", generator_path)
    monkeypatch.setitem(globals_, "CONDITIONER_PATH", conditioner_path)
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
    return plan, plan_path, generator_execution, conditioner_path


def _args(plan, plan_path: Path, generator_execution: str):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        plan=plan_path,
        expected_plan_sha256=_sha(plan_path.read_bytes()),
        expected_source_commit=plan.source_commit,
        expected_source_bundle_sha256=plan.source_bundle_sha256,
        expected_generator_execution_sha256=generator_execution,
        private_root=Path("/private/store"),
    )


def test_admission_command_authenticates_and_seals_without_gameplay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, plan_path, generator_execution, _conditioner = _fixture(
        tmp_path, monkeypatch
    )
    published: list[tuple[str, str, object]] = []

    class _Store:
        def publish_sealed_record(
            self,
            record_id: str,
            *,
            kind: str,
            record: object,
        ) -> object:
            published.append((record_id, kind, record))
            return SimpleNamespace(
                summary=SimpleNamespace(
                    manifest_sha256=_sha(b"manifest"),
                    record_sha256=_sha(b"record"),
                )
            )

    bundle = SimpleNamespace(
        record_id=f"pwr-admit-{plan.plan_sha256}",
        private_dict=lambda: {"schema": "private-admission"},
        public_dict=lambda: {
            "authenticated_success_roots": 12,
            "controller_actions": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "population_scale_authorized": False,
        },
    )
    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: _Store())
    monkeypatch.setitem(
        globals_,
        "open_fixed_account_claim_registry",
        lambda: Path("claims"),
    )

    def authenticate(
        observed_plan,  # type: ignore[no-untyped-def]
        *,
        private_store: object,
        claim_registry: Path,
        recover_interrupted: bool,
    ) -> object:
        assert observed_plan == plan
        assert isinstance(private_store, _Store)
        assert claim_registry == Path("claims")
        assert recover_interrupted is True
        return bundle

    monkeypatch.setitem(
        globals_,
        "authenticate_red_living_dex_powered_supply_private_tranche",
        authenticate,
    )

    result = SCRIPT["_run"](_args(plan, plan_path, generator_execution))

    assert result["authenticated_success_roots"] == 12
    assert result["controller_actions"] == 0
    assert result["emulator_frames"] == 0
    assert result["model_fits"] == 0
    assert result["population_scale_authorized"] is False
    assert result["admission_manifest_sha256"] == _sha(b"manifest")
    assert len(published) == 1
    assert published[0][0] == bundle.record_id
    assert "/private" not in str(result)


def test_admission_rejects_conditioner_drift_before_private_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, plan_path, generator_execution, conditioner = _fixture(
        tmp_path, monkeypatch
    )
    private_opens = 0

    def open_store(*_args: object, **_kwargs: object) -> object:
        nonlocal private_opens
        private_opens += 1
        raise AssertionError("private store must stay closed")

    monkeypatch.setitem(SCRIPT["_run"].__globals__, "open_private_root", open_store)
    conditioner.write_bytes(b"conditioner-v3\n")

    with pytest.raises(
        SCRIPT["PoweredSupplyAdmissionCommandError"],
        match="plan_authentication",
    ):
        SCRIPT["_run"](_args(plan, plan_path, generator_execution))
    assert private_opens == 0


def test_admission_cli_has_no_rom_controller_retry_or_learning_surface() -> None:
    parsed = SCRIPT["_parser"]().parse_args(
        [
            "--plan",
            "/private/plan.json",
            "--expected-plan-sha256",
            "a" * 64,
            "--expected-source-commit",
            "b" * 40,
            "--expected-source-bundle-sha256",
            "c" * 64,
            "--expected-generator-execution-sha256",
            "d" * 64,
            "--private-root",
            "/private/store",
        ]
    )

    assert parsed.plan == Path("/private/plan.json")
    for forbidden in (
        "rom",
        "watch",
        "speed",
        "controller",
        "retry",
        "model",
        "fit",
        "outcome",
        "teacher",
        "seed",
    ):
        assert not hasattr(parsed, forbidden)


def test_main_failure_is_path_free_and_truthfully_zero_effect(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_run",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["PoweredSupplyAdmissionCommandError"]("plan_authentication")
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda _argv: object()),
    )

    assert SCRIPT["main"]([]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["stage"] == "plan_authentication"
    assert result["controller_actions"] == 0
    assert result["emulator_frames"] == 0
    assert result["model_fits"] == 0
    assert result["root_state_restores"] == 0
    assert result["population_scale_authorized"] is False
    assert "/private" not in str(result)
