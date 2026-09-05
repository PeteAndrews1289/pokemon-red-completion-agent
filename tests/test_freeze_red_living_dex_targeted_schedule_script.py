# ruff: noqa: E402 -- standalone script is loaded after its local path setup.

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_red_living_dex_targeted_schedule.py"
FREEZER = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="freeze_red_living_dex_targeted_schedule_test",
)


def _args(tmp_path: Path) -> list[str]:
    return [
        "--expected-source-commit",
        "a" * 40,
        "--expected-source-bundle-sha256",
        "b" * 64,
        "--registry-source-commit",
        "c" * 40,
        "--expected-registry-sha256",
        "d" * 64,
        "--context-catalog",
        str(tmp_path / "catalog.json"),
        "--expected-context-catalog-sha256",
        "e" * 64,
        "--context-plan",
        str(tmp_path / "plan.json"),
        "--expected-context-plan-sha256",
        "f" * 64,
        "--private-root",
        str(tmp_path / "private"),
        "--rom",
        str(tmp_path / "red.gb"),
        "--expected-model-sha256",
        "1" * 64,
        "--expected-model-record-sha256",
        "2" * 64,
        "--capacity-result",
        str(tmp_path / "capacity.json"),
        "--expected-capacity-result-sha256",
        "3" * 64,
        "--schedule-out",
        str(tmp_path / "schedule.json"),
    ]


def _capacity_document() -> dict[str, object]:
    return {
        "capacity_sufficient": True,
        "controller_actions": 0,
        "development_maximum_matching": 8,
        "development_reuse_enabled": False,
        "emulator_frames": 0,
        "maximum_train_replays_per_context": 5,
        "model_fits": 0,
        "model_predictions": 0,
        "outcomes_opened": 0,
        "root_claims": 0,
        "schema": "pokemon.red.living-dex-repeatable-train-capacity-result.v1",
        "status": "repeatable_train_capacity_ready",
        "teacher_queries": 0,
        "train_maximum_matching": 10,
    }


def _write_capacity(path: Path, document: dict[str, object] | None = None) -> str:
    payload = json.dumps(
        _capacity_document() if document is None else document,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_parser_exposes_only_authentication_and_freeze_inputs(tmp_path: Path) -> None:
    parsed = FREEZER["_parser"]().parse_args(_args(tmp_path))

    assert parsed.schedule_out == tmp_path / "schedule.json"
    assert parsed.capacity_result == tmp_path / "capacity.json"
    for field in (
        "action",
        "candidate_index",
        "execute",
        "fit",
        "retry",
        "speed",
        "teacher",
        "watch",
    ):
        assert not hasattr(parsed, field)


def test_capacity_authentication_accepts_only_the_bounded_zero_effect_gate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "capacity.json"
    expected = _write_capacity(path)

    assert FREEZER["_authenticate_capacity_result"](path) == expected

    for key, value in (
        ("capacity_sufficient", False),
        ("maximum_train_replays_per_context", 6),
        ("development_reuse_enabled", True),
        ("train_maximum_matching", 9),
        ("development_maximum_matching", 7),
        ("controller_actions", 1),
        ("model_predictions", 1),
        ("outcomes_opened", 1),
    ):
        mutated = _capacity_document()
        mutated[key] = value
        _write_capacity(path, mutated)
        with pytest.raises(
            FREEZER["TargetedScheduleFreezeError"],
            match="capacity_authentication",
        ):
            FREEZER["_authenticate_capacity_result"](path)


def test_private_writer_is_create_only_and_rejects_repository_paths(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "private" / "schedule.json"
    document = {"schema": "private-test.v1", "secret": "identity"}

    digest = FREEZER["_write_new_private_json"](destination, document)
    payload = destination.read_bytes()
    assert digest == hashlib.sha256(payload).hexdigest()
    assert destination.stat().st_mode & 0o777 == 0o600
    with pytest.raises(
        FREEZER["TargetedScheduleFreezeError"],
        match="private_schedule_publication",
    ):
        FREEZER["_write_new_private_json"](destination, document)

    repository_destination = PROJECT_ROOT / ".forbidden-private" / "schedule.json"
    with pytest.raises(
        FREEZER["TargetedScheduleFreezeError"],
        match="private_schedule_publication",
    ):
        FREEZER["_write_new_private_json"](repository_destination, document)
    assert not repository_destination.parent.exists()


def test_script_has_no_gameplay_teacher_or_model_fit_imports() -> None:
    source = SCRIPT_PATH.read_text()

    for forbidden in (
        "controller_executor",
        "emulator.tick",
        "model.fit",
        "run_teacher",
        "teacher_policy",
    ):
        assert forbidden not in source
