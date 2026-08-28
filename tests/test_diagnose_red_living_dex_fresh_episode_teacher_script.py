from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from pokemon_red_completion.red_living_dex_episode_lineage import (
    derive_red_living_dex_initial_wait_frames,
)

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts/diagnose_red_living_dex_fresh_episode_teacher.py"
)
SPEC = importlib.util.spec_from_file_location("fresh_teacher_diagnostic", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_diagnostic_assignment_is_nonofficial_and_source_bound() -> None:
    assignment = MODULE._diagnostic_assignment(9_900_016)

    assert assignment.harness_seed == 9_900_016
    assert assignment.initial_wait_frames == derive_red_living_dex_initial_wait_frames(9_900_016)
    assert assignment.declared_runs == 1
    assert assignment.run_id == "red-fresh-teacher-diagnostic-9900016"
    assert assignment.target_template_ordinal == 2
    assert assignment.target_active_box_count == 17


def test_private_ledger_is_exclusive_and_durable(tmp_path: Path) -> None:
    ledger = MODULE._DurableLedger(tmp_path, 9_900_016)
    ledger.append({"event": "claimed", "harness_seed": 9_900_016})
    path = ledger.path
    ledger.close()

    row = json.loads(path.read_text(encoding="utf-8"))
    assert row == {
        "event": "claimed",
        "harness_seed": 9_900_016,
        "schema": "pokemon.red.private-fresh-teacher-diagnostic-ledger.v1",
    }
    with pytest.raises(MODULE.FreshTeacherDiagnosticError, match="already_claimed"):
        MODULE._DurableLedger(tmp_path, 9_900_016)


def test_private_ledger_rejects_repository_location() -> None:
    with pytest.raises(
        MODULE.FreshTeacherDiagnosticError,
        match="inside_repository",
    ):
        MODULE._DurableLedger(
            SCRIPT.parent / "private-diagnostic-ledger",
            9_900_016,
        )


def test_path_free_failure_retains_only_source_basenames_and_digest() -> None:
    try:
        raise RuntimeError("secret /private/location")
    except RuntimeError as error:
        result = MODULE._path_free_failure(error)

    assert result["exception_name"] == "RuntimeError"
    assert result["message_sha256"] != "secret /private/location"
    assert result["exception_chain"][0]["message_redacted"] is True
    assert result["exception_chain"][0]["message"] == ("[path-bearing-or-unbounded-message]")
    assert result["exception_chain"][0]["traceback_frames"]
    encoded = json.dumps(result, sort_keys=True)
    assert "/private/location" not in encoded
    assert str(Path(__file__).parent) not in encoded


def test_path_free_failure_retains_bounded_gameplay_message_and_cause() -> None:
    try:
        try:
            raise ValueError("Forest training missed its level-nine Bubble gate.")
        except ValueError as cause:
            raise RuntimeError(str(cause)) from cause
    except RuntimeError as error:
        result = MODULE._path_free_failure(error)

    assert len(result["exception_chain"]) == 2
    assert {row["exception_name"] for row in result["exception_chain"]} == {
        "RuntimeError",
        "ValueError",
    }
    assert all(
        row["message"] == "Forest training missed its level-nine Bubble gate."
        and row["message_redacted"] is False
        for row in result["exception_chain"]
    )


def test_gameplay_snapshot_is_path_free_and_json_serializable() -> None:
    class Memory:
        def read_u8(self, address: int) -> int:
            del address
            return 0

    snapshot = MODULE._gameplay_snapshot(Memory())

    assert snapshot["game_started"] is False
    assert snapshot["map_id"] is None
    encoded = json.dumps(snapshot, sort_keys=True)
    assert "/" not in encoded
    assert "\\" not in encoded
