"""Package qualified TRAIN attack and switching heads without fitting weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.trainer-frozen-attack-composition.v1"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _head_digest(value: object) -> str:
    return _digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _qualified_source(directory: Path) -> tuple[TrainerPracticeThreeHeadModel, dict]:
    plan_bytes = (directory / "fit-plan.json").read_bytes()
    model_bytes = (directory / "fit" / "model.json").read_bytes()
    receipt_bytes = (directory / "fit" / "receipt.json").read_bytes()
    plan, receipt = json.loads(plan_bytes), json.loads(receipt_bytes)
    if (
        not isinstance(plan, dict)
        or not isinstance(receipt, dict)
        or receipt.get("qualification_tier") != "independent_root_train"
        or receipt.get("independent_train_supply_gate_passed") is not True
        or receipt.get("development_evaluations") != 0
        or receipt.get("authority_promotions") != 0
        or receipt.get("scenario_count") != len(plan.get("scenarios", []))
        or receipt.get("corpus_plan_sha256") != _digest(plan_bytes)
        or receipt.get("model_sha256") != _digest(model_bytes)
    ):
        raise ValueError("composition source lacks qualified TRAIN provenance")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(model_bytes))
    return model, {
        "model_sha256": _digest(model_bytes),
        "receipt_sha256": _digest(receipt_bytes),
        "plan_sha256": _digest(plan_bytes),
        "scenario_count": receipt["scenario_count"],
    }


def compose(
    old: TrainerPracticeThreeHeadModel,
    corrected: TrainerPracticeThreeHeadModel,
) -> TrainerPracticeThreeHeadModel:
    if (
        not set(old.train_capture_ids).issubset(corrected.train_capture_ids)
        or set(old.train_root_ids) != set(corrected.train_root_ids)
    ):
        raise ValueError("frozen attack lineage differs from corrected TRAIN corpus")
    result = TrainerPracticeThreeHeadModel(
        old.move, corrected.control, corrected.switch,
        corrected.train_capture_ids, corrected.train_root_ids,
    )
    restored = TrainerPracticeThreeHeadModel.from_dict(result.to_dict())
    if (
        restored.move.to_dict() != old.move.to_dict()
        or restored.control.to_dict() != corrected.control.to_dict()
        or restored.switch.to_dict() != corrected.switch.to_dict()
    ):
        raise ValueError("composition round-trip changed a head")
    RedTrainerPracticeOutcomePolicy("composition-preflight", "composition-preflight", restored)
    return restored


def run(old_dir: Path, corrected_dir: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise ValueError("composition output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit composition source before packaging")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    old, old_source = _qualified_source(old_dir)
    corrected, corrected_source = _qualified_source(corrected_dir)
    if old_source["scenario_count"] != 44 or corrected_source["scenario_count"] != 52:
        raise ValueError("composition source corpus size differs")
    composed = compose(old, corrected)
    model_bytes = (json.dumps(composed.to_dict(), sort_keys=True, indent=2) + "\n").encode()
    receipt = {
        "schema": SCHEMA,
        "source_commit": commit,
        "partition": "train",
        "status": "packaged_train_candidate_not_promoted",
        "attack_source": old_source,
        "control_switch_source": corrected_source,
        "head_sha256": {
            "move": _head_digest(composed.move.to_dict()),
            "control": _head_digest(composed.control.to_dict()),
            "switch": _head_digest(composed.switch.to_dict()),
        },
        "model_sha256": _digest(model_bytes),
        "train_capture_count": len(composed.train_capture_ids),
        "train_root_count": len(composed.train_root_ids),
        "optimizer_updates": 0,
        "gameplay_actions": 0,
        "authority_promotions": 0,
    }
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "model.json").write_bytes(model_bytes)
    (output / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--corrected", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.old, args.corrected, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
