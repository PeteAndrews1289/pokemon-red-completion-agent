from __future__ import annotations

import ast
import hashlib
import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.red_party_development_pp_materialization import (
    RedPpStartAdapter,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "preflight_red_party_development_pp_materializations.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_pp_preflight_loader_requires_exact_bytes_and_digest(
    tmp_path: Path,
) -> None:
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


def test_pp_preflight_writer_is_exclusive_canonical_and_owner_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / "output.json"
    payload = SCRIPT["_canonical_payload"]({"z": 2, "a": 1})

    digest = SCRIPT["_write_exclusive"](path, payload)

    assert path.read_bytes() == b'{"a":1,"z":2}\n'
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        SCRIPT["_write_exclusive"](path, payload)


def test_pp_preflight_refuses_private_outputs_inside_the_repository() -> None:
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_require_external"](
            PROJECT_ROOT / "private-plan.json",
            subject="test output",
        )


@pytest.mark.parametrize(
    ("map_id", "x", "y", "expected"),
    (
        (
            int(MapId.CINNABAR_POKECENTER),
            13,
            4,
            RedPpStartAdapter.CINNABAR_CENTER_PC_TO_ROUTE_11,
        ),
        (
            int(MapId.CINNABAR_MART),
            2,
            5,
            RedPpStartAdapter.CINNABAR_MART_CLERK_TO_ROUTE_11,
        ),
    ),
)
def test_pp_preflight_supports_only_the_two_exact_source_boundaries(
    map_id: int,
    x: int,
    y: int,
    expected: RedPpStartAdapter,
) -> None:
    raw = RawGameState(True, map_id, x, y, 6, 0)

    assert SCRIPT["_start_adapter"](raw) is expected
    with pytest.raises(RuntimeError, match="not at a supported exact"):
        SCRIPT["_start_adapter"](RawGameState(True, map_id, x + 1, y, 6, 0))


def test_pp_preflight_has_no_controller_teacher_or_write_state_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
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
            "controller",
            "executor",
            "red_team_training",
            "teacher",
        )
    )
    assert called_attributes.isdisjoint(
        {
            "execute",
            "hold",
            "press",
            "release",
            "save_state",
            "send_input",
            "tick",
        }
    )
    assert "load_state_bytes" in called_attributes
    assert '"controller_actions": 0' not in source
    assert "plan.public_summary()" in source
    assert "ItemId.EXP_ALL" in source
    assert "reservation_plan.excluded_root_lineage_ids" in source
    assert "rom_path," in source
