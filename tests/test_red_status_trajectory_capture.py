from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    open_battle_scenario_capture,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_status_trajectory_capture import (
    TrajectoryCaptureSink,
    validate_capture_indices,
)
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def parent():
    return SimpleNamespace(manifest=SimpleNamespace(
        partition=ScenarioPartition.TRAIN, observation_schema=OBSERVATION_SCHEMA_V2,
        expected_map=120, root_lineage_id="training-origin", capture_id="training-parent",
        state_sha256="a" * 64), manifest_sha256="b" * 64)


def fixture(tmp_path, *, different=False):
    obs = {"features": {"status": "confused"}}
    log = TrainerPracticeEventLog(tmp_path / "events", run_identity={"partition": "train"})
    calls = []

    def snapshot():
        calls.append(1)
        return {"policy_observation": {} if different else obs, "map_id": 120,
                "battle_state": 2, "state_bytes": b"native-state",
                "initial_observation_sha256": "c" * 64}

    sink = TrajectoryCaptureSink(parent=parent(), directory=tmp_path / "snapshots",
                                  indices=(2, 3, 5, 8), source_commit="d" * 40,
                                  log=log, snapshot=snapshot)
    event = {"event": "decision_started", "decision_index": 2, "mode": "main",
             "observation_sha256": canonical_sha256(obs)}
    return sink, event, calls, log


def test_passive_sink_only_snapshots_declared_prechoice_boundaries(tmp_path):
    sink, event, calls, log = fixture(tmp_path)
    sink({**event, "decision_index": 1})
    sink({"event": "decision_completed", "decision_index": 1})
    assert calls == []
    sink(event)
    assert calls == [1]
    folder = tmp_path / "snapshots/decision-002"
    capture = open_battle_scenario_capture(folder / "capture.state", folder / "capture.state.json")
    assert capture.state_bytes == b"native-state"
    assert capture.manifest.root_lineage_id == "training-origin"
    assert capture.manifest.source_state_sha256 == "a" * 64
    log.finish({"retained": True})
    assert verify_trainer_practice_event_log(tmp_path / "events")["complete"]


def test_mismatch_fails_before_snapshot_files_and_duplicate_never_overwrites(tmp_path):
    sink, event, _, _ = fixture(tmp_path / "mismatch", different=True)
    with pytest.raises(ValueError, match="differs from actor"):
        sink(event)
    assert not (tmp_path / "mismatch/snapshots").exists()
    sink, event, calls, _ = fixture(tmp_path / "duplicate")
    sink(event)
    with pytest.raises(ValueError, match="duplicate"):
        sink(event)
    assert calls == [1]


def test_non_main_boundary_is_censored_without_reading_state(tmp_path):
    sink, event, calls, log = fixture(tmp_path)
    sink({**event, "mode": "forced_switch"})
    assert calls == []
    assert log.last_event == "trajectory_capture_censored"


@pytest.mark.parametrize("indices", [(), (1,), (2, 2), (41,), (True,), tuple(range(2, 11))])
def test_capture_plan_is_bounded_and_unique(indices):
    with pytest.raises(ValueError):
        validate_capture_indices(indices, parent())


def test_capture_cannot_relabel_development_as_training():
    p = parent()
    p.manifest.partition = ScenarioPartition.DEVELOPMENT
    with pytest.raises(ValueError, match="TRAIN"):
        validate_capture_indices((2,), p)


def test_diagnostics_keep_conflicting_compact_inputs_and_timing_uncertainty():
    import sys
    from pathlib import Path

    from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_red_status_trajectory_coverage import target_diagnostics

    damage = [0.] * len(BALANCED_STATUS_NAMES)
    status = damage.copy()
    status[BALANCED_STATUS_NAMES.index("choice.status")] = 1.
    base = {"capture_id": "one", "vectors": [damage, status], "slots": [1, 2],
            "returns": [0., -1.], "timing_returns": {"1": [0., 0., 0.], "2": [-3., 1., -1.]}}
    contrary = {**base, "capture_id": "two", "returns": [0., 2.]}
    actor = SimpleNamespace(move=SimpleNamespace(predict_index=lambda rows: 1))
    out = target_diagnostics([base, contrary], actor)
    assert out["unique_compact_inputs"] == 1
    assert len(out["conflicting_exact_input_groups"]) == 1
    assert out["status_worse"] == out["status_better"] == 1
    assert out["high_cost_errors"] == 1
    assert out["timing_sign_changes"] == 2
