from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/audit_living_dex_causal_public_capacity_bound.py"
EVIDENCE_PATH = (
    PROJECT_ROOT / "docs/evidence/living-dex-causal-public-capacity-bound-v1-2026-08-27.json"
)


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("public_capacity_bound", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_capacity_bound_replays_exactly_from_checked_in_receipts() -> None:
    module = _script()
    payload = module.canonical_bytes()
    document = json.loads(payload)

    assert EVIDENCE_PATH.read_bytes() == payload
    assert document["capacity"] == {
        "combined_new_root_minimum": 128,
        "combined_required_contexts": 195,
        "development_required_contexts": 105,
        "historical_eligible_root_pool": 69,
        "later_claimed_roots": 1,
        "later_retired_root_exclusions": 1,
        "remaining_root_upper_bound": 67,
        "train_new_root_minimum_if_all_remaining_qualify": 23,
        "train_required_contexts": 90,
    }
    assert document["interpretation"]["capacity_ready"] is False
    assert document["interpretation"]["root_reuse_allowed"] is False


def test_public_capacity_check_mode_and_projection_are_effect_free() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(EVIDENCE_PATH.read_text())
    encoded = EVIDENCE_PATH.read_text()

    assert "current" in result.stdout
    assert document["counter_deltas"] == {
        "causal_train_examples": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "root_claims": 0,
        "teacher_queries": 0,
    }
    for forbidden in ("/Users/", "/Volumes/", "private_root"):
        assert forbidden not in encoded
    configured_rom = os.environ.get("POKEMON_RED_ROM")
    if configured_rom is not None:
        assert configured_rom not in encoded
