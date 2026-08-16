from __future__ import annotations

import ast
import hashlib
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "refresh_party_development_question_reservations.py"
)
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_refresh_loader_requires_exact_bytes_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    payload = b'{"schema":"test"}\n'
    path.write_bytes(payload)

    assert SCRIPT["_load_json"](
        path,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        subject="test input",
    ) == {"schema": "test"}
    with pytest.raises(RuntimeError, match="digest or size differs"):
        SCRIPT["_load_json"](
            path,
            expected_sha256="0" * 64,
            subject="test input",
        )


def test_refresh_writer_is_exclusive_and_canonical(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    payload = SCRIPT["_canonical_payload"]({"z": 2, "a": 1})

    digest = SCRIPT["_write_exclusive"](path, payload)

    assert path.read_bytes() == b'{"a":1,"z":2}\n'
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        SCRIPT["_write_exclusive"](path, payload)


def test_refresh_refuses_private_outputs_inside_the_repository() -> None:
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_require_external"](
            PROJECT_ROOT / "private-plan.json",
            subject="test output",
        )


def test_refresh_has_no_rom_emulator_controller_or_answer_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not any(
        token in module
        for module in imported_modules
        for token in (
            "emulator",
            "executor",
            "red_team_training",
            "rom",
            "teacher",
        )
    )
    assert called_attributes.isdisjoint(
        {
            "execute",
            "hold",
            "load_state",
            "press",
            "release",
            "save_state",
            "send_input",
            "tick",
        }
    )
    assert "refresh.public_summary()" in source
    assert "outcome_training_examples != 0" in source
