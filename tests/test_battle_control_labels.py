from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_control_labels import (
    BattleControlLabelError,
    load_battle_control_artifact,
)


def _line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _artifact(tmp_path: Path) -> Path:
    root = tmp_path / "red-battle-control-test"
    root.mkdir()
    streams = {
        "metadata.jsonl": _line(
            {
                "record_type": "battle_control_run",
                "schema_version": 1,
                "model_id": "pokemon.core.battle.masked-mlp-ranker.v1",
                "model_sha256": "a" * 64,
                "action_schema": "pokemon.core.battle.action.v1",
            }
        ),
        "labels.jsonl": _line(
            {
                "record_type": "battle_control_label",
                "schema_version": 1,
                "label_index": 1,
                "decision_index": 12,
                "battle_plan_id": "battle-059-league-lorelei",
                "objective_id": "defeat_lorelei",
                "observation": {
                    "schema_version": 1,
                    "game_id": "pokemon.mainline:red:gb:us:rev0",
                    "mode": "battle",
                    "location": "pokemon.red.gb.us.rev0:area:loreleis_room",
                    "facts": ["pokemon.core:battle:active"],
                    "features": {},
                },
                "teacher_action": BattleAction.recovery().public_dict(),
            }
        ),
        "summary.jsonl": _line(
            {
                "record_type": "battle_control_summary",
                "schema_version": 1,
                "battle_policy": {"control_records": 1},
                "game_complete": True,
            }
        ),
    }
    entries = []
    for filename, payload in streams.items():
        (root / filename).write_bytes(payload)
        entries.append(
            {
                "filename": filename,
                "bytes": len(payload),
                "records": 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "artifact_id": root.name,
        "files": entries,
        "format": "pokemon-red-completion-private-artifact-jsonl",
        "kind": "battle_control_labels",
        "schema_version": 1,
        "status": "complete",
        "totals": {
            "bytes": sum(len(payload) for payload in streams.values()),
            "files": 3,
            "records": 3,
        },
    }
    (root / "manifest.json").write_bytes(_line(manifest))
    return root


def test_control_loader_authenticates_typed_action_labels(tmp_path: Path) -> None:
    dataset = load_battle_control_artifact(_artifact(tmp_path))

    assert dataset.game_complete
    assert dataset.source_model_sha256 == "a" * 64
    assert dataset.labels[0].teacher_action == BattleAction.recovery()
    assert dataset.public_summary()["action_counts"] == {
        "pokemon.core:battle:recovery": 1
    }


def test_control_loader_rejects_stream_tampering(tmp_path: Path) -> None:
    root = _artifact(tmp_path)
    with (root / "labels.jsonl").open("ab") as stream:
        stream.write(b" ")

    with pytest.raises(BattleControlLabelError, match="authentication"):
        load_battle_control_artifact(root)
