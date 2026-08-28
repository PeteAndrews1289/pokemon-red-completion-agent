from __future__ import annotations

import hashlib
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_episode_lineage import (
    build_red_living_dex_fresh_episode_plan,
    compose_red_living_dex_fresh_episode_generator_execution_sha256,
    compose_red_living_dex_fresh_episode_teacher_execution_sha256,
    encode_red_living_dex_fresh_episode_plan,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "scripts/preflight_red_living_dex_episode_lineage_generator.py"
)
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="preflight_red_living_dex_episode_lineage_generator_test",
)


def _digest(label: str) -> str:
    return canonical_sha256({"label": label})


def _artifacts(tmp_path: Path):  # type: ignore[no-untyped-def]
    evidence_payload = b'{"status":"capacity_insufficient"}\n'
    evidence = tmp_path / "capacity.json"
    evidence.write_bytes(evidence_payload)
    source_bundle = _digest("source")
    generator_runner = tmp_path / "generator.py"
    conditioner_runner = tmp_path / "conditioner.py"
    generator_runner.write_bytes(b"# generator\n")
    conditioner_runner.write_bytes(b"# conditioner\n")
    generator = compose_red_living_dex_fresh_episode_generator_execution_sha256(
        source_bundle_sha256=source_bundle,
        generator_runner_sha256=hashlib.sha256(
            generator_runner.read_bytes()
        ).hexdigest(),
        conditioner_runner_sha256=hashlib.sha256(
            conditioner_runner.read_bytes()
        ).hexdigest(),
    )
    plan = build_red_living_dex_fresh_episode_plan(
        source_commit="a" * 40,
        source_bundle_sha256=source_bundle,
        teacher_execution_sha256=(
            compose_red_living_dex_fresh_episode_teacher_execution_sha256(
                source_bundle_sha256=source_bundle,
                generator_execution_sha256=generator,
            )
        ),
        generator_execution_sha256=generator,
        capacity_evidence_sha256=hashlib.sha256(evidence_payload).hexdigest(),
    )
    plan_payload = encode_red_living_dex_fresh_episode_plan(plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(plan_payload)
    return (
        evidence,
        plan_path,
        plan_payload,
        source_bundle,
        generator_runner,
        conditioner_runner,
    )


def test_cli_has_no_rom_runtime_generation_or_output_surface() -> None:
    parser = SCRIPT["_parser"]()
    parsed = parser.parse_args(
        [
            "--plan",
            "/public/plan.json",
            "--expected-plan-sha256",
            "a" * 64,
        ]
    )

    assert parsed.expected_plan_sha256 == "a" * 64
    for field in (
        "rom",
        "state",
        "private_root",
        "out",
        "watch",
        "speed",
        "execute",
        "retry",
    ):
        assert not hasattr(parsed, field)


def test_script_has_no_emulator_controller_teacher_or_fit_import() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "PyBoyAdapter",
        "FrameSafeExecutor",
        "run_qualified_play",
        "DeterministicTeacher",
        "load_state",
        "save_state",
        "fit_living_dex",
        "write_root_claim",
    ):
        assert forbidden not in source


def test_run_authenticates_public_plan_and_emits_zero_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        evidence,
        plan_path,
        plan_payload,
        source_bundle,
        generator_runner,
        conditioner_runner,
    ) = _artifacts(tmp_path)
    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "CAPACITY_EVIDENCE_PATH", evidence)
    monkeypatch.setitem(globals_, "GENERATOR_RUNNER_PATH", generator_runner)
    monkeypatch.setitem(globals_, "CONDITIONER_RUNNER_PATH", conditioner_runner)
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
    args = SimpleNamespace(
        plan=plan_path,
        expected_plan_sha256=hashlib.sha256(plan_payload).hexdigest(),
    )

    result = SCRIPT["_run"](args)

    assert result["status"] == (
        "fresh_train_episode_generator_plan_preflight_passed"
    )
    assert result["assignments"] == 13
    assert result["target_template_counts"] == {"2": 6, "3": 6, "5": 1}
    assert result["storage_pressure_values_millionths"] == [
        625_000,
        750_000,
        875_000,
    ]
    assert result["root_generation_executions"] == 0
    assert result["controller_actions"] == 0
    assert result["emulator_frames"] == 0
    assert result["learner_outcomes"] == 0
    assert result["model_fits"] == 0
    assert "/private/" not in str(result)


def test_run_rejects_plan_or_capacity_digest_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        evidence,
        plan_path,
        plan_payload,
        source_bundle,
        generator_runner,
        conditioner_runner,
    ) = _artifacts(tmp_path)
    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "CAPACITY_EVIDENCE_PATH", evidence)
    monkeypatch.setitem(globals_, "GENERATOR_RUNNER_PATH", generator_runner)
    monkeypatch.setitem(globals_, "CONDITIONER_RUNNER_PATH", conditioner_runner)
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

    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorPreflightError"],
        match="plan_authentication",
    ):
        SCRIPT["_run"](
            SimpleNamespace(plan=plan_path, expected_plan_sha256="f" * 64)
        )

    evidence.write_bytes(b'{"status":"changed"}\n')
    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorPreflightError"],
        match="capacity_authentication",
    ):
        SCRIPT["_run"](
            SimpleNamespace(
                plan=plan_path,
                expected_plan_sha256=hashlib.sha256(plan_payload).hexdigest(),
            )
        )


def test_run_rejects_generator_or_conditioner_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        evidence,
        plan_path,
        plan_payload,
        source_bundle,
        generator_runner,
        conditioner_runner,
    ) = _artifacts(tmp_path)
    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "CAPACITY_EVIDENCE_PATH", evidence)
    monkeypatch.setitem(globals_, "GENERATOR_RUNNER_PATH", generator_runner)
    monkeypatch.setitem(globals_, "CONDITIONER_RUNNER_PATH", conditioner_runner)
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
    conditioner_runner.write_bytes(b"# changed conditioner\n")

    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorPreflightError"],
        match="source_authentication",
    ):
        SCRIPT["_run"](
            SimpleNamespace(
                plan=plan_path,
                expected_plan_sha256=hashlib.sha256(plan_payload).hexdigest(),
            )
        )
