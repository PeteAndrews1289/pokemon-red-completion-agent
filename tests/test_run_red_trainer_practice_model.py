from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.battle_control_features import CONTROL_CLASS_REFS, CONTROL_FEATURE_NAMES
from pokemon_red_completion.battle_control_model import BattleControlMLP
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import FEATURE_NAMES
from pokemon_red_completion.battle_switch_target import SWITCH_TARGET_FEATURE_NAMES
from pokemon_red_completion.battle_switch_target_model import BattleSwitchTargetMLP
from pokemon_red_completion.scenario_lab import ScenarioPartition

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_red_trainer_practice_model as runner  # noqa: E402


def test_model_runner_requires_exact_bound_bytes(tmp_path):
    path = tmp_path / "private-model.json"
    path.write_bytes(b"{}")
    binding = {"path": str(path), "sha256": hashlib.sha256(b"{}").hexdigest()}
    assert runner._bound_file(binding, "model") == b"{}"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="model hash differs"):
        runner._bound_file(binding, "model")


def test_model_runner_rejects_wrong_plan_before_cartridge_access():
    with pytest.raises(ValueError, match="plan differs"):
        runner._authenticate({"schema": "not-a-trainer-model-plan"})


def test_model_runner_loads_all_three_heads_and_rejects_test_partition(
    tmp_path, monkeypatch
):
    move = MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        input_weights=np.zeros((2, len(FEATURE_NAMES))),
        hidden_bias=np.zeros(2), output_weights=np.zeros(2), output_bias=0.0,
    )
    control = BattleControlMLP(
        feature_names=CONTROL_FEATURE_NAMES,
        class_refs=(CONTROL_CLASS_REFS[0], CONTROL_CLASS_REFS[5]),
        input_weights=np.zeros((2, len(CONTROL_FEATURE_NAMES))),
        hidden_bias=np.zeros(2), output_weights=np.zeros((2, 2)), output_bias=np.array([1, 0]),
    )
    switch = BattleSwitchTargetMLP(
        weights1=np.zeros((len(SWITCH_TARGET_FEATURE_NAMES), 2)),
        bias1=np.zeros(2), weights2=np.zeros(2),
        feature_mean=np.zeros(len(SWITCH_TARGET_FEATURE_NAMES)),
        feature_scale=np.ones(len(SWITCH_TARGET_FEATURE_NAMES)), training_seed=0,
    )
    payloads = {
        "ROM": b"rom",
        "move model": json.dumps(move.to_dict()).encode(),
        "control model": json.dumps(control.to_dict()).encode(),
        "switch model": json.dumps(switch.to_dict()).encode(),
        "capture state": b"state", "capture manifest": b"manifest",
    }
    monkeypatch.setattr(runner, "_bound_file", lambda _value, label: payloads[label])
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"rom").hexdigest())
    monkeypatch.setattr(
        runner.subprocess, "check_output",
        lambda args, **_kwargs: b"" if "status" in args else b"commit\n",
    )
    capture = SimpleNamespace(manifest=SimpleNamespace(partition=ScenarioPartition.TRAIN))
    monkeypatch.setattr(runner, "open_battle_scenario_capture", lambda *_args: capture)
    plan = {
        "schema": runner.SCHEMA, "source_commit": "commit", "rom": {},
        "move_model": {}, "control_model": {}, "switch_model": {},
        "capture_state": {"path": "state"}, "capture_manifest": {"path": "manifest"},
        "max_decisions": 2, "maximum_frames": 1000,
        "output": str(tmp_path / "new-output"),
    }
    _plan, _capture, loaded_move, loaded_control, loaded_switch = runner._authenticate(plan)
    assert loaded_move.feature_names == FEATURE_NAMES
    assert loaded_control.class_refs == (CONTROL_CLASS_REFS[0], CONTROL_CLASS_REFS[5])
    assert loaded_switch.training_seed == 0
    capture.manifest.partition = ScenarioPartition.TEST
    with pytest.raises(ValueError, match="partition is unavailable"):
        runner._authenticate(plan)
