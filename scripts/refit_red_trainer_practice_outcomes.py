"""Refit an admitted TRAIN trainer corpus with a declared optimizer schedule.

The retained branches are authenticated anew. No emulator battle is replayed,
and no DEVELOPMENT material can enter the fit adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import fit_red_trainer_practice_outcomes as fitter

ROOT = Path(__file__).resolve().parents[1]


def build_refit_plan(
    previous: dict[str, object], *, commit: str, epochs: int, output: Path,
    warm_start_move_model: Path | None = None,
    warm_start_move_receipt: Path | None = None,
    warm_start_move_epochs: int | None = None,
) -> dict[str, object]:
    scenarios = previous.get("scenarios")
    if (
        previous.get("schema") != fitter.SCHEMA
        or not isinstance(scenarios, list)
        or len(scenarios) < 16
        or type(epochs) is not int  # noqa: E721
        or not 100 <= epochs <= 3000
        or not isinstance(commit, str)
        or len(commit) != 40
    ):
        raise ValueError("refit needs an admitted TRAIN corpus and declared optimizer")
    if (warm_start_move_model is None) != (warm_start_move_receipt is None):
        raise ValueError("warm-start model and receipt must be paired")
    if warm_start_move_model is None and warm_start_move_epochs is not None:
        raise ValueError("warm-start schedule lacks a model")
    if warm_start_move_model is not None and (
        type(warm_start_move_epochs) is not int  # noqa: E721
        or not 100 <= warm_start_move_epochs <= epochs
    ):
        raise ValueError("warm-start schedule differs")
    plan = {
        **previous,
        "source_commit": commit,
        "epochs": epochs,
        "output": str(output),
    }
    if warm_start_move_model is not None and warm_start_move_receipt is not None:
        plan.update(
            {
                "warm_start_move_model": _binding(warm_start_move_model),
                "warm_start_move_receipt": _binding(warm_start_move_receipt),
                "warm_start_move_epochs": warm_start_move_epochs,
            }
        )
    return plan


def _binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run(
    previous_dir: Path, output_dir: Path, *, epochs: int,
    warm_start_move_dir: Path | None = None,
    warm_start_move_epochs: int | None = None,
) -> dict[str, object]:
    if output_dir.exists():
        raise ValueError("trainer refit output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit optimizer before trainer refit")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    previous_plan_path = previous_dir / "fit-plan.json"
    previous_receipt_path = previous_dir / "fit" / "receipt.json"
    previous_model_path = previous_dir / "fit" / "model.json"
    old_plan = json.loads(previous_plan_path.read_bytes())
    old_receipt = json.loads(previous_receipt_path.read_bytes())
    if (
        old_receipt.get("qualification_tier") != "independent_root_train"
        or old_receipt.get("independent_train_supply_gate_passed") is not True
        or old_receipt.get("scenario_count") != len(old_plan.get("scenarios", []))
        or old_receipt.get("corpus_plan_sha256")
        != hashlib.sha256(previous_plan_path.read_bytes()).hexdigest()
        or old_receipt.get("model_sha256")
        != hashlib.sha256(previous_model_path.read_bytes()).hexdigest()
    ):
        raise ValueError("previous admitted trainer fit receipt differs")
    output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    plan = build_refit_plan(
        old_plan,
        commit=commit,
        epochs=epochs,
        output=output_dir / "fit",
        warm_start_move_model=(
            warm_start_move_dir / "fit" / "model.json" if warm_start_move_dir else None
        ),
        warm_start_move_receipt=(
            warm_start_move_dir / "fit" / "receipt.json" if warm_start_move_dir else None
        ),
        warm_start_move_epochs=warm_start_move_epochs,
    )
    plan_path = output_dir / "fit-plan.json"
    plan_path.write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n")
    checked = fitter.run(plan_path, check_only=True)
    fitted = fitter.run(plan_path)
    result = {
        "schema": "pokemon.red.trainer-refit-result.v1",
        "status": "train_refit_completed",
        "source_commit": commit,
        "previous_model_sha256": old_receipt["model_sha256"],
        "model_sha256": fitted["model_sha256"],
        "scenario_count": fitted["scenario_count"],
        "optimizer_epochs": fitted["optimizer_epochs"],
        "warm_start_move_model_sha256": fitted["warm_start_move_model_sha256"],
        "warm_start_move_epochs": fitted["warm_start_move_epochs"],
        "training_diagnostics": fitted["training_diagnostics"],
        "admission": checked,
        "gameplay_actions": 0,
        "development_evaluations": 0,
        "authority_promotions": 0,
    }
    (output_dir / "summary.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--warm-start-move", type=Path)
    parser.add_argument("--warm-start-move-epochs", type=int)
    args = parser.parse_args()
    print(json.dumps(run(
        args.previous,
        args.output,
        epochs=args.epochs,
        warm_start_move_dir=args.warm_start_move,
        warm_start_move_epochs=args.warm_start_move_epochs,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
