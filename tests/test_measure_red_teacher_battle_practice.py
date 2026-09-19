import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_scenario_capture import build_battle_scenario_capture_payload
from pokemon_red_completion.scenario_lab import ScenarioPartition

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import measure_red_teacher_battle_practice as runner  # noqa: E402


def _bound(path, payload):
    path.write_bytes(payload)
    return {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest()}


def _plan(tmp_path):
    state = b"isolated assisted state"
    manifest = build_battle_scenario_capture_payload(
        capture_id="assisted-train-test",
        root_lineage_id="red-goal-root-test",
        partition=ScenarioPartition.TRAIN,
        state_bytes=state,
        initial_observation_sha256="b" * 64,
        source_commit="c" * 40,
        expected_map=165,
        expected_battle_state=1,
        source_state_sha256="d" * 64,
    )
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    receipt = {
        "assistance": "isolated_teacher_memory_intervention",
        "final_player_action": False,
        "new_independent_upstream_roots": 0,
        "capture_manifest_sha256": manifest_sha,
        "assisted_state_sha256": hashlib.sha256(state).hexdigest(),
        "configuration_sha256": "e" * 64,
        "root_lineage_id": "red-goal-root-test",
    }
    return {
        "schema": runner.SCHEMA,
        "source_commit": "a" * 40,
        "rom": _bound(tmp_path / "red.gb", b"ROM"),
        "model": _bound(tmp_path / "model.json", b"{}"),
        "materialization": _bound(tmp_path / "receipt.json", json.dumps(receipt).encode()),
        "capture_state": _bound(tmp_path / "assisted.state", state),
        "capture_manifest": _bound(tmp_path / "assisted.state.json", manifest),
        "configuration_sha256": "e" * 64,
        "candidate_indices": [0, 1, 2, 3],
        "minimum_pre_attack_frames": 2048,
        "maximum_frames_per_candidate": 4096,
        "output": str(tmp_path / "new-output"),
    }


def _authenticate_ready(monkeypatch):
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"ROM").hexdigest())
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"" if args[1] == "status" else b"a" * 40,
    )
    monkeypatch.setattr(
        runner.MaskedMLPMoveRanker,
        "from_dict",
        lambda _value: SimpleNamespace(),
    )


def test_assisted_measurement_rejects_dirty_source(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"dirty" if args[1] == "status" else b"a" * 40,
    )
    with pytest.raises(ValueError, match="commit assisted battle measurement"):
        runner._authenticate(plan, b"plan")


def test_assisted_measurement_binds_capture_and_scope(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    _authenticate_ready(monkeypatch)
    assert runner._authenticate(plan, b"plan")[1].manifest.partition is ScenarioPartition.TRAIN
    with pytest.raises(ValueError, match="scope differs"):
        runner._authenticate({**plan, "minimum_pre_attack_frames": 500}, b"plan")
    Path(plan["output"]).mkdir()
    with pytest.raises(ValueError, match="must be new"):
        runner._authenticate(plan, b"plan")


def test_assisted_measurement_preflight_is_action_free(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    _authenticate_ready(monkeypatch)
    features = SimpleNamespace(
        legal_mask=(True, True, True, True),
        candidate_vectors=((0.0,),) * 4,
        current_pp=(5.0,) * 4,
    )
    monkeypatch.setattr(
        runner,
        "prepare_red_battle_outcome_capture",
        lambda *_args, **_kwargs: SimpleNamespace(features=features),
    )
    monkeypatch.setattr(
        runner.MaskedMLPMoveRanker,
        "from_dict",
        lambda _value: SimpleNamespace(predict=lambda *_args, **_kwargs: 1),
    )
    result = runner.run(plan_path, check_only=True)
    assert result["controller_actions"] == result["emulator_frames"] == 0
    assert not Path(plan["output"]).exists()
