import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import measure_retained_train_battle_alternatives as runner  # noqa: E402


def _bound(path: Path, payload: bytes) -> dict[str, str]:
    path.write_bytes(payload)
    return {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest()}


def _plan(tmp_path: Path) -> dict[str, object]:
    before = b"retained battle state"
    root = "red-goal-root-c1d575483e311b3a9854b0e85237f725c3da1412ed62ab142dcd82050c666435"
    query = {
        "state_sha256": hashlib.sha256(before).hexdigest(),
        "observation_sha256": "a" * 64,
        "model_sha256": "b" * 64,
        "facts": {"moves": [56, 70, 58, 57]},
    }
    source = {
        "schema": "pokemon.red.model-battle-train-episode-outcome.v1",
        "stop_reason": "encounter_limit",
        "root_lineage_id": root,
    }
    return {
        "schema": runner.SCHEMA,
        "source_commit": "c" * 40,
        "rom": _bound(tmp_path / "red.gb", b"ROM"),
        "source_outcome": _bound(tmp_path / "outcome.json", json.dumps(source).encode()),
        "query": _bound(tmp_path / "query.json", json.dumps(query).encode()),
        "before_state": _bound(tmp_path / "before.state", before),
        "root_lineage_id": root,
        "observation_sha256": "a" * 64,
        "model_sha256": "b" * 64,
        "encounter_index": 0,
        "candidate_indices": [0, 1, 2, 3],
        "minimum_pre_attack_frames": 2048,
        "maximum_actions_per_branch": 32,
        "maximum_frames_per_branch": 4096,
        "output": str(tmp_path / "new-output"),
    }


def test_branch_plan_requires_clean_exact_source(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"ROM").hexdigest())
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"dirty" if args[1] == "status" else b"c" * 40,
    )
    with pytest.raises(ValueError, match="commit bounded branch code"):
        runner._validated_plan(plan, b"prospective")
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"" if args[1] == "status" else b"d" * 40,
    )
    with pytest.raises(ValueError, match="source commit differs"):
        runner._validated_plan(plan, b"prospective")


def test_branch_plan_rejects_scope_hash_and_output_reuse(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"ROM").hexdigest())
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"" if args[1] == "status" else b"c" * 40,
    )
    assert runner._validated_plan(plan, b"prospective")[1] == b"retained battle state"
    with pytest.raises(ValueError, match="scope or provenance"):
        runner._validated_plan({**plan, "minimum_pre_attack_frames": 128}, b"prospective")
    Path(plan["before_state"]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash differs"):
        runner._validated_plan(plan, b"prospective")


def test_action_free_preflight_does_not_create_output(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(
        runner,
        "_validated_plan",
        lambda _plan, _bytes: ({"facts": {"moves": [56, 70, 58, 57]}}, b"state", b"ROM"),
    )

    class Emulator:
        frame_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())
    monkeypatch.setattr(
        runner,
        "_prepared_boundary",
        lambda *_args: SimpleNamespace(features=SimpleNamespace(legal_mask=(True,) * 4)),
    )
    assert runner.run(plan_path, check_only=True)["controller_actions"] == 0
    assert not Path(plan["output"]).exists()
