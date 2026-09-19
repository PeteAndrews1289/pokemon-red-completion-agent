"""ROM-free admission checks for the four clean-power trainer sources."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.scenario_lab import ScenarioPartition

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_fresh_red_trainer_curriculum as curriculum  # noqa: E402


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    frames = (2000, 2100, 2200, 2300)
    ids = [f"fresh-red-lab-rival-train-boot{frame}" for frame in frames]
    manifests = {}
    for index, (source_id, boot_frames) in enumerate(zip(ids, frames, strict=True)):
        source = tmp_path / source_id
        source.mkdir()
        origin = f"origin-{index}".encode()
        state = f"battle-{index}".encode()
        (source / "origin.state").write_bytes(origin)
        (source / "source.state").write_bytes(state)
        (source / "source.state.json").write_bytes(b"{}")
        origin_hash = hashlib.sha256(origin).hexdigest()
        state_hash = hashlib.sha256(state).hexdigest()
        (source / "outcome.json").write_text(json.dumps({
            "schema": "pokemon.red.fresh-trainer-train-source.v1",
            "source_id": source_id,
            "root_lineage_id": source_id,
            "partition": "train",
            "fresh_power_on": True,
            "origin_state_sha256": origin_hash,
            "battle_state_sha256": state_hash,
            "first_party_ot_id": 100 + index,
            "boot_frames": boot_frames,
            "source_commit": "c" * 40,
            "model_queries": 0,
            "model_updates": 0,
            "full_game_runs": 0,
        }))
        manifests[source_id] = SimpleNamespace(
            state_sha256=state_hash,
            source_state_sha256=origin_hash,
            root_lineage_id=source_id,
            observation_schema=OBSERVATION_SCHEMA_V2,
            partition=ScenarioPartition.TRAIN,
            source_commit="c" * 40,
        )
    (tmp_path / "batch-outcome.json").write_text(json.dumps({
        "schema": "pokemon.red.fresh-trainer-train-batch.v1",
        "status": "captured",
        "source_commit": "c" * 40,
        "fresh_power_on_sources": 4,
        "distinct_origin_state_hashes": 4,
        "distinct_player_trainer_ids": 4,
        "boot_frames": list(frames),
        "source_ids": ids,
    }))
    monkeypatch.setattr(
        curriculum,
        "open_battle_scenario_capture",
        lambda state, _manifest: SimpleNamespace(manifest=manifests[state.parent.name]),
    )
    return tmp_path


def test_source_rows_rechecks_physical_distinctness_not_just_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch = _fixture(tmp_path, monkeypatch)
    assert len(curriculum._source_rows(batch)) == 4
    second = batch / "fresh-red-lab-rival-train-boot2100" / "outcome.json"
    value = json.loads(second.read_text())
    value["first_party_ot_id"] = 100
    second.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="repeated physical starts"):
        curriculum._source_rows(batch)


def test_source_rows_rejects_broken_origin_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch = _fixture(tmp_path, monkeypatch)
    second = batch / "fresh-red-lab-rival-train-boot2100" / "origin.state"
    second.write_bytes(b"changed-origin")
    with pytest.raises(ValueError, match="ancestry or capture differs"):
        curriculum._source_rows(batch)
