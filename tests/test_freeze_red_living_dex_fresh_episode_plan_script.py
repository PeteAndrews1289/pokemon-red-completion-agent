from __future__ import annotations

import hashlib
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.red_living_dex_episode_lineage import (
    RED_LIVING_DEX_FRESH_EPISODE_FIRST_HARNESS_SEED,
    compose_red_living_dex_fresh_episode_generator_execution_sha256,
    parse_red_living_dex_fresh_episode_plan,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/freeze_red_living_dex_fresh_episode_plan.py"),
    run_name="freeze_red_living_dex_fresh_episode_plan_test",
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):  # type: ignore[no-untyped-def]
    evidence = tmp_path / "capacity.json"
    generator = tmp_path / "generator.py"
    conditioner = tmp_path / "conditioner.py"
    evidence.write_bytes(b'{"status":"capacity-insufficient"}\n')
    generator.write_bytes(b"generator\n")
    conditioner.write_bytes(b"conditioner\n")
    source_bundle = _digest(b"source")
    generator_execution = (
        compose_red_living_dex_fresh_episode_generator_execution_sha256(
            source_bundle_sha256=source_bundle,
            generator_runner_sha256=_digest(generator.read_bytes()),
            conditioner_runner_sha256=_digest(conditioner.read_bytes()),
        )
    )
    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "CAPACITY_EVIDENCE_PATH", evidence)
    monkeypatch.setitem(globals_, "GENERATOR_RUNNER_PATH", generator)
    monkeypatch.setitem(globals_, "CONDITIONER_RUNNER_PATH", conditioner)
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
    return evidence, source_bundle, generator_execution


def test_freeze_writes_one_external_canonical_plan_without_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, source_bundle, generator_execution = _fixture(
        tmp_path,
        monkeypatch,
    )
    output = tmp_path / "frozen-plan.json"
    result = SCRIPT["_run"](
        SimpleNamespace(
            out=output,
            expected_source_commit="a" * 40,
            expected_source_bundle_sha256=source_bundle,
            expected_generator_execution_sha256=generator_execution,
            expected_capacity_evidence_sha256=_digest(evidence.read_bytes()),
        )
    )
    payload = output.read_bytes()
    plan = parse_red_living_dex_fresh_episode_plan(payload)

    assert len(plan.assignments) == 13
    assert plan.assignments[0].harness_seed == (
        RED_LIVING_DEX_FRESH_EPISODE_FIRST_HARNESS_SEED
    )
    assert result["plan_file_sha256"] == _digest(payload)
    assert result["controller_actions"] == 0
    assert result["root_generation_executions"] == 0
    assert result["model_fits"] == 0

    with pytest.raises(
        SCRIPT["FreshEpisodePlanFreezeError"],
        match="output_authentication",
    ):
        SCRIPT["_run"](
            SimpleNamespace(
                out=output,
                expected_source_commit="a" * 40,
                expected_source_bundle_sha256=source_bundle,
                expected_generator_execution_sha256=generator_execution,
                expected_capacity_evidence_sha256=(
                    _digest(evidence.read_bytes())
                ),
            )
        )


def test_freeze_rejects_source_or_capacity_drift_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, source_bundle, generator_execution = _fixture(
        tmp_path,
        monkeypatch,
    )
    output = tmp_path / "frozen-plan.json"
    with pytest.raises(
        SCRIPT["FreshEpisodePlanFreezeError"],
        match="source_authentication",
    ):
        SCRIPT["_run"](
            SimpleNamespace(
                out=output,
                expected_source_commit="a" * 40,
                expected_source_bundle_sha256=source_bundle,
                expected_generator_execution_sha256=generator_execution,
                expected_capacity_evidence_sha256="f" * 64,
            )
        )

    assert not output.exists()


def test_freeze_cli_has_no_rom_teacher_model_or_seed_choice() -> None:
    parser = SCRIPT["_parser"]()
    parsed = parser.parse_args(
        [
            "--out",
            "/private/plan.json",
            "--expected-source-commit",
            "a" * 40,
            "--expected-source-bundle-sha256",
            "b" * 64,
            "--expected-generator-execution-sha256",
            "c" * 64,
            "--expected-capacity-evidence-sha256",
            "d" * 64,
        ]
    )

    for forbidden in (
        "rom",
        "watch",
        "teacher",
        "model",
        "outcome",
        "seed",
        "retry",
    ):
        assert not hasattr(parsed, forbidden)
