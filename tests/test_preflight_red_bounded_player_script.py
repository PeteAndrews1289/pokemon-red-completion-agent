from __future__ import annotations

import ast
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "preflight_red_bounded_player.py"


def _call_names() -> tuple[str, ...]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    result: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            result.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            result.append(node.func.attr)
    return tuple(result)


def test_player_preflight_binds_authentication_and_blocks_controller_input() -> None:
    calls = _call_names()

    for required in (
        "require_clean_source",
        "require_published_source",
        "verify_rom",
        "open_goal_manager_context_capture",
        "load_red_goal_context_profile",
        "load_goal_manager_model",
        "ReadOnlyController",
        "preflight_red_bounded_player",
        "_write_exclusive",
    ):
        assert required in calls
    assert "run_bounded_player_episode" not in calls
    assert "save_state" not in calls
    assert "save_state_bytes" not in calls


def test_player_preflight_command_imports_without_private_inputs() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--assignment-id" in result.stdout
    assert "--state" in result.stdout
    assert "--model" in result.stdout
    assert "--out" in result.stdout


def test_player_preflight_receipt_must_be_new_external_and_not_rom_adjacent(
    tmp_path: Path,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    receipt = module["_new_external_receipt"]
    rom_dir = tmp_path / "roms"
    output_dir = tmp_path / "receipts"
    rom_dir.mkdir()
    output_dir.mkdir()
    rom = rom_dir / "red.gb"
    rom.write_bytes(b"rom")

    assert receipt(output_dir / "ready.json", rom_path=rom) == (
        output_dir / "ready.json"
    ).resolve()
    with pytest.raises(RuntimeError, match="new JSON file"):
        receipt(rom_dir / "ready.json", rom_path=rom)
    existing = output_dir / "existing.json"
    existing.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="new JSON file"):
        receipt(existing, rom_path=rom)


def test_player_preflight_budget_meter_counts_actions_and_frames() -> None:
    module = runpy.run_path(str(SCRIPT))
    meter_type = module["_ReadOnlyBudgetMeter"]
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=40)
    meter = meter_type(actions=actions, emulator=emulator, initial_frame_count=40)

    assert meter.checkpoint() == CompositionBudgetCheckpoint(0, 0)
    actions.actions_executed = 1
    emulator.frame_count = 43
    assert meter.checkpoint() == CompositionBudgetCheckpoint(1, 3)
    emulator.frame_count = 39
    with pytest.raises(RuntimeError, match="moved backwards"):
        meter.checkpoint()
