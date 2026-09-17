from __future__ import annotations

import json

import pytest

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_analysis import (
    summarize_trainer_practice_runs,
)
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog


def _run(tmp_path, name, *, root="train-root", won=False):
    directory = tmp_path / name
    directory.mkdir()
    log = TrainerPracticeEventLog(directory / "events", run_identity={
        "partition": "train", "capture_id": name, "root_lineage_id": root,
        "policy_id": "model-a",
    })
    log.emit({"event": "decision_started", "decision_index": 1})
    log.emit({"event": "decision_completed", "decision": {"kind": "attack"}})
    outcome = {
        "capture_id": name, "policy_id": "model-a", "battle_won": won,
        "stop_reason": "battle_won" if won else "party_defeated",
        "decision_count": 1, "player_turn_count": 1, "elapsed_ns": 1000,
        "policy_elapsed_ns": 100, "frames_executed": 500,
        "action_counts": {"attack": 1}, "metrics": {"opponent_faints": int(won)},
    }
    (directory / "outcome.json").write_text(json.dumps(outcome))
    log.finish({"outcome_sha256": canonical_sha256(outcome)})
    return directory


def test_cohort_counts_one_root_for_two_variants(tmp_path):
    first = _run(tmp_path, "variant-a", won=True)
    second = _run(tmp_path, "variant-b", won=False)
    summary = summarize_trainer_practice_runs((first, second))
    group = summary["groups"][0]
    assert group["runs"] == 2
    assert group["upstream_roots"] == 1
    assert group["repeat_or_variant_runs"] == 1
    assert group["battle_wins"] == 1
    assert group["battle_losses"] == 1
    assert group["frames_executed"] == 1000


def test_cohort_rejects_tampered_outcome(tmp_path):
    directory = _run(tmp_path, "tampered")
    outcome_path = directory / "outcome.json"
    outcome = json.loads(outcome_path.read_bytes())
    outcome["battle_won"] = True
    outcome_path.write_text(json.dumps(outcome))
    with pytest.raises(ValueError, match="differs from terminal"):
        summarize_trainer_practice_runs((directory,))
