from __future__ import annotations

import ast
import hashlib
import runpy
import stat
from pathlib import Path

import pytest

from pokemon_red_completion.party_development_inventory import unit_bin

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INITIALIZER_PATH = PROJECT_ROOT / "scripts" / "initialize_party_development_prior.py"
INVENTORY_PATH = PROJECT_ROOT / "scripts" / "inventory_party_development_checkpoints.py"
INITIALIZER = runpy.run_path(str(INITIALIZER_PATH))
INVENTORY = runpy.run_path(str(INVENTORY_PATH))


@pytest.mark.parametrize(
    ("script", "value", "payload"),
    (
        (INITIALIZER, b'{"private":true}\n', b'{"private":true}\n'),
        (
            INVENTORY,
            {"private": True},
            b'{"private":true}\n',
        ),
    ),
)
def test_party_development_private_writers_are_exclusive_and_owner_only(
    script: dict[str, object], value: object, payload: bytes, tmp_path: Path
) -> None:
    writer = script["_write_exclusive"]
    target = tmp_path / "private.json"

    digest = writer(target, value)  # type: ignore[operator]

    assert digest == hashlib.sha256(payload).hexdigest()
    assert target.read_bytes() == payload
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        writer(target, value)  # type: ignore[operator]


def test_inventory_pp_bin_matches_the_model_feature_scale() -> None:
    pp_bin = INVENTORY["_pp_bin"]

    for total_pp in (0, 32, 86, 128, 171, 255, 256):
        assert pp_bin(total_pp) == unit_bin(total_pp / 256)  # type: ignore[operator]


def test_inventory_script_has_no_controller_or_input_execution_surface() -> None:
    source = INVENTORY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not any("controller" in module or "teacher" in module for module in imported_modules)
    assert called_attributes.isdisjoint(
        {"tick", "press", "hold", "release", "send_input", "execute"}
    )
    assert 'glob("red-goal-v1-*.state")' in source
    assert "sealed" not in source.lower()
    assert "crystal" not in source.lower()
