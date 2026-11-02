"""Independently rederive collection artifacts; no ROM input or TRAIN admission."""

import json
from hashlib import sha256

import pytest
from test_player_sequence_collector import collect
from test_red_sequence_receipts import read

from pokemon_red_completion.player_sequence_reconstruction import reconstruct_sequence_candidates
from pokemon_red_completion.provenance import canonical_sha256


def args(root, partition="development"):
    return dict(
        source_sha256=sha256(b"0").hexdigest(), partition=partition,
        expected_plan_sha256=canonical_sha256(read(root / "plan.json")),
        expected_result_sha256=canonical_sha256(read(root / "result.json")),
        expected_declaration_sha256=canonical_sha256(read(root / "sequence/declaration.json")),
    )


@pytest.mark.parametrize("horizon", [1, 2, 4])
@pytest.mark.parametrize("partition", ["train", "development"])
def test_reconstruct_actual_mocked_choices_and_recovery_without_admission(
    tmp_path, monkeypatch, horizon, partition,
):
    root, _ = collect(tmp_path, monkeypatch, horizon=horizon, partition=partition)
    rows = reconstruct_sequence_candidates(root, **args(root, partition))
    assert sum(row.measurement.actions for row in rows) == 3
    assert sum(row.measurement.cash_debits for row in rows) == 60
    assert all(not row.training_eligible and not any(row.targets.known) for row in rows)
    assert all(len(row.features) == 351 and row.behavior_probability > 0 for row in rows)
    assert rows[0].features[-8:] == (0.0,) * 8
    if horizon == 1:
        assert rows[0].measurement.actions == 2  # includes intervening recovery
        assert rows[1].features[-8] == 0.5
    if horizon == 4:
        assert not rows[0].measurement.complete_window


@pytest.mark.parametrize("file,field,value,error", [
    ("anchor-000.json", "features", [0.0] * 351, "anchor"),
    ("anchor-001.json", "previous_outcome_sha256", [], "anchor"),
    ("anchor-000.json", "behavior_probability", 1, "anchor"),
    ("anchor-000.json", "training_eligible", 0, "anchor"),
    ("window-000.json", "complete_window", False, "window"),
    ("window-000.json", "training_eligible", True, "window"),
    ("window-000.json", "first_model_choice", True, "window"),
    ("window-000.json", "prefix_outcome_sha256", [], "window"),
    ("receipt-001.json", "observed_cost", {}, "receipt"),
    ("result.json", "projection_error", {"message": "hidden failure"}, "result"),
    ("result.json", "windows", 5, "result"),
])
def test_mutated_candidate_is_rejected_without_repair(
    tmp_path, monkeypatch, file, field, value, error,
):
    root, _ = collect(tmp_path, monkeypatch)
    path = root / "sequence" / file
    document = read(path)
    document[field] = value
    path.write_text(json.dumps(document))
    original = path.read_bytes()
    with pytest.raises(ValueError, match=error):
        reconstruct_sequence_candidates(root, **args(root))
    assert path.read_bytes() == original


@pytest.mark.parametrize("field,value", [
    ("partition", "train"), ("horizon", 3), ("source_sha256", "b" * 64),
])
def test_changed_prospective_declaration_rejected(tmp_path, monkeypatch, field, value):
    root, _ = collect(tmp_path, monkeypatch)
    pinned = args(root)
    path = root / "sequence/declaration.json"
    document = read(path)
    document[field] = value
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="declaration"):
        reconstruct_sequence_candidates(root, **pinned)


def test_duplicate_or_extra_window_is_not_another_training_sample(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch)
    (root / "sequence/window-001.json").write_bytes(
        (root / "sequence/window-000.json").read_bytes(),
    )
    with pytest.raises(ValueError, match="census"):
        reconstruct_sequence_candidates(root, **args(root))


def test_missing_anchor_is_not_silently_skipped(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch)
    (root / "sequence/anchor-001.json").unlink()
    with pytest.raises(FileNotFoundError):
        reconstruct_sequence_candidates(root, **args(root))


def test_partial_native_execution_cannot_be_recast_as_complete_window(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch, fault="partial")
    with pytest.raises(ValueError):
        reconstruct_sequence_candidates(root, **args(root))
    assert read(root / "sequence/result.json")["unprojected_observed_costs"][0]["actions"] == 1
