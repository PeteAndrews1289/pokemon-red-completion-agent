"""One-use, bounded outcome measurement for one assisted train capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController
from pokemon_red_completion.red_autonomous_player import _record
from pokemon_red_completion.red_battle_outcome_runtime import (
    collect_red_battle_outcome_example,
    prepare_red_battle_outcome_capture,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.teacher-battle-practice-measurement-plan.v1"
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def _bound_file(value: object, label: str) -> bytes:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError(f"{label} binding differs")
    path, digest = value["path"], value["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError(f"{label} identity differs")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{label} hash differs")
    return payload


def _authenticate(plan: object, plan_bytes: bytes):
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("assisted battle measurement plan differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit assisted battle measurement code first")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if plan.get("source_commit") != revision:
        raise ValueError("assisted measurement source commit differs")
    rom = _bound_file(plan.get("rom"), "ROM")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("assisted measurement Red ROM differs")
    model_bytes = _bound_file(plan.get("model"), "frozen model")
    materialization = json.loads(_bound_file(plan.get("materialization"), "materialization"))
    state_record = plan.get("capture_state")
    manifest_record = plan.get("capture_manifest")
    _bound_file(state_record, "assisted capture state")
    _bound_file(manifest_record, "assisted capture manifest")
    assert isinstance(state_record, dict) and isinstance(manifest_record, dict)
    capture = open_battle_scenario_capture(
        Path(state_record["path"]), Path(manifest_record["path"])
    )
    if (
        not isinstance(materialization, dict)
        or materialization.get("assistance") != "isolated_teacher_memory_intervention"
        or materialization.get("final_player_action") is not False
        or materialization.get("new_independent_upstream_roots") != 0
        or materialization.get("capture_manifest_sha256") != capture.manifest_sha256
        or materialization.get("assisted_state_sha256") != capture.manifest.state_sha256
        or materialization.get("configuration_sha256") != plan.get("configuration_sha256")
        or materialization.get("root_lineage_id") != capture.manifest.root_lineage_id
        or capture.manifest.partition is not ScenarioPartition.TRAIN
        or plan.get("candidate_indices") != [0, 1, 2, 3]
        or plan.get("minimum_pre_attack_frames") != 2048
        or plan.get("maximum_frames_per_candidate") != 4096
    ):
        raise ValueError("assisted capture or measurement scope differs")
    output = plan.get("output")
    if not isinstance(output, str) or Path(output).exists() or not plan_bytes:
        raise ValueError("assisted measurement output must be new")
    model = MaskedMLPMoveRanker.from_dict(json.loads(model_bytes))
    return plan, capture, model


def run(plan_path: Path, *, check_only: bool = False) -> dict[str, object]:
    plan_bytes = plan_path.read_bytes()
    plan, capture, model = _authenticate(json.loads(plan_bytes), plan_bytes)
    rom_record = plan["rom"]
    assert isinstance(rom_record, dict) and isinstance(rom_record["path"], str)
    rom_path = Path(rom_record["path"])

    @contextmanager
    def session_factory():
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            yield FrameBudgetController(emulator, maximum_frames=4096)

    prepared = prepare_red_battle_outcome_capture(capture, session_factory=session_factory)
    features = prepared.features
    if len(features.legal_mask) != 4 or not all(features.legal_mask):
        raise ValueError("assisted four-move menu differs")
    choice = model.predict(
        features.candidate_vectors,
        legal_mask=features.legal_mask,
        current_pp=features.current_pp,
    )
    if type(choice) is not int or not 0 <= choice < 4 or not features.legal_mask[choice]:  # noqa: E721
        raise ValueError("frozen model selected an illegal assisted candidate")
    if check_only:
        return {
            "status": "action_free_assisted_measurement_preflight_passed",
            "legal_move_count": 4,
            "controller_actions": 0,
            "emulator_frames": 0,
            "persistent_artifacts": 0,
        }

    output_path = plan["output"]
    assert isinstance(output_path, str)
    output = Path(output_path)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(
        output / "execution-started.json",
        {
            "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "capture_manifest_sha256": capture.manifest_sha256,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "model_choice_candidate_index": choice,
            "observation_sha256": prepared.initial_observation_sha256,
            "candidate_indices": [0, 1, 2, 3],
            "fit_allowed": False,
            "authority_promoted": False,
        },
    )

    def claim_candidate(index: int) -> None:
        _record(output / f"candidate-{index:02d}-started.json", {"candidate_index": index})

    def retain_candidate(index, outcome):  # type: ignore[no-untyped-def]
        _record(
            output / f"candidate-{index:02d}-outcome.json",
            {"candidate_index": index, "outcome": outcome.public_dict()},
        )

    try:
        collection = collect_red_battle_outcome_example(
            capture,
            session_factory=session_factory,
            candidate_claim_sink=claim_candidate,
            outcome_sink=retain_candidate,
        )
    except Exception as error:
        _record(output / "failure.json", {"type": type(error).__name__, "message": str(error)})
        raise
    report: dict[str, object] = {
        "schema": "pokemon.red.teacher-battle-practice-measurement-outcome.v1",
        "capture_manifest_sha256": collection.manifest_sha256,
        "root_lineage_id": capture.manifest.root_lineage_id,
        "configuration_sha256": plan["configuration_sha256"],
        "model_choice_candidate_index": choice,
        "collection": collection.public_dict(),
        "independent_upstream_roots_added": 0,
        "model_updates": 0,
        "authority_promotions": 0,
    }
    _record(output / "outcome.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, check_only=args.check_only), sort_keys=True))


if __name__ == "__main__":
    main()
