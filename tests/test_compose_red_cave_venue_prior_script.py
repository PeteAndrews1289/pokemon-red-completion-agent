from __future__ import annotations

import argparse
import ast
import hashlib
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "compose_red_cave_venue_prior.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_composition_rejects_a_registry_digest_outside_the_plan(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="differs from the prospective plan"):
        SCRIPT["_run"](
            argparse.Namespace(
                existing_registry_file_sha256="0" * 64,
                existing_registry=tmp_path / "existing.json",
                out_registry=tmp_path / "next.json",
                out_summary=tmp_path / "summary.json",
            )
        )


def test_composition_outputs_must_remain_external(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_run"](
            argparse.Namespace(
                existing_registry_file_sha256=(
                    SCRIPT["RED_CAVE_VENUE_PRIOR_REGISTRY_FILE_SHA256"]
                ),
                existing_registry=tmp_path / "existing.json",
                out_registry=PROJECT_ROOT / "private-registry.json",
                out_summary=tmp_path / "summary.json",
            )
        )


def test_composition_writer_is_exclusive_and_exact(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    payload = b'{"schema":"test"}\n'

    assert SCRIPT["_write_exclusive"](path, payload) == hashlib.sha256(
        payload
    ).hexdigest()
    assert path.read_bytes() == payload
    with pytest.raises(FileExistsError):
        SCRIPT["_write_exclusive"](path, payload)


def test_composition_script_has_no_live_game_or_learning_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "pokemon_red_completion.emulator" not in imported_modules
    assert "pokemon_red_completion.rom" not in imported_modules
    assert "pokemon_red_completion.teacher" not in imported_modules
    assert "--execute" not in source
    assert "model.predict" not in source
    assert "teacher" not in source.lower()
