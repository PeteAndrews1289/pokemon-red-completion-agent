from __future__ import annotations

import ast
import hashlib
import runpy
import stat
from pathlib import Path

import pytest

from pokemon_red_completion.scenario_lab import ScenarioPartition

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


def test_inventory_pp_bin_uses_each_movesets_actual_capacity() -> None:
    pp_bin = INVENTORY["_pp_bin"]
    pp_ratio = INVENTORY["_pp_ratio"]

    moves = (1, 2, 0, 0)  # base PP 35 + 25
    assert pp_bin(moves, (35, 25, 0, 0)) == "high"  # type: ignore[operator]
    assert pp_bin(moves, (17, 12, 0, 0)) == "middle"  # type: ignore[operator]
    assert pp_bin(moves, (3, 2, 0, 0)) == "low"  # type: ignore[operator]
    assert pp_ratio((45, 0, 0, 0), (0xFD, 0, 0, 0)) == 1.0  # type: ignore[operator]


@pytest.mark.parametrize(
    ("checkpoint_id", "partition"),
    (
        ("red-goal-v1-001-example-train-01", ScenarioPartition.TRAIN),
        ("red-goal-v1-002-example-validation-01", ScenarioPartition.DEVELOPMENT),
        ("red-party-pp-v1-train-01", ScenarioPartition.TRAIN),
        ("red-party-pp-v1-development-01", ScenarioPartition.DEVELOPMENT),
    ),
)
def test_inventory_assigns_prepared_pp_captures_to_their_open_partition(
    checkpoint_id: str,
    partition: ScenarioPartition,
) -> None:
    assert INVENTORY["_partition"](checkpoint_id) is partition  # type: ignore[operator]


def test_inventory_scans_only_historical_and_prepared_pp_capture_names(
    tmp_path: Path,
) -> None:
    expected = {
        tmp_path / "red-goal-v1-001-example-train-01.state",
        tmp_path / "red-party-pp-v1-train-01.state",
        tmp_path / "red-party-pp-v1-development-01.state",
    }
    for path in (*expected, tmp_path / "unrelated.state"):
        path.touch()

    assert set(INVENTORY["_capture_states"](tmp_path)) == expected  # type: ignore[operator]


@pytest.mark.parametrize(
    ("moves", "pp", "match"),
    (
        ((1, 2, 0), (35, 25, 0), "vectors are invalid"),
        ((0, 0, 0, 0), (1, 0, 0, 0), "empty checkpoint move"),
        ((1, 0, 0, 0), (63, 0, 0, 0), "above its own maximum"),
    ),
)
def test_inventory_pp_ratio_rejects_incoherent_vectors(
    moves: tuple[int, ...], pp: tuple[int, ...], match: str
) -> None:
    pp_ratio = INVENTORY["_pp_ratio"]

    with pytest.raises(RuntimeError, match=match):
        pp_ratio(moves, pp)  # type: ignore[operator]


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
    assert '"red-goal-v1-*.state"' in source
    assert '"red-party-pp-v1-train-*.state"' in source
    assert '"red-party-pp-v1-development-*.state"' in source
    assert "sealed" not in source.lower()
    assert "crystal" not in source.lower()
