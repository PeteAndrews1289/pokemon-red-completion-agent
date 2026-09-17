"""Run a frozen attack-model baseline through one authenticated TRAIN trainer battle.

This baseline deliberately declines optional switches and takes the first living
forced replacement. It tests the model seam but does not claim learned switching.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController
from pokemon_red_completion.red_autonomous_player import _record
from pokemon_red_completion.red_trainer_practice_episode import (
    run_red_trainer_practice_episode,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.trainer-practice-baseline-plan.v1"
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


def _authenticate(plan: object):
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("trainer baseline plan differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit trainer baseline code before running it")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if plan.get("source_commit") != revision:
        raise ValueError("trainer baseline source commit differs")
    rom = _bound_file(plan.get("rom"), "ROM")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("trainer baseline Red ROM differs")
    model = MaskedMLPMoveRanker.from_dict(json.loads(_bound_file(plan.get("model"), "model")))
    state = plan.get("capture_state")
    manifest = plan.get("capture_manifest")
    _bound_file(state, "trainer state")
    _bound_file(manifest, "trainer manifest")
    assert isinstance(state, dict) and isinstance(manifest, dict)
    capture = open_battle_scenario_capture(Path(state["path"]), Path(manifest["path"]))
    if (
        capture.manifest.partition is not ScenarioPartition.TRAIN
        or capture.manifest.expected_battle_state != 2
        or plan.get("max_decisions") != 80
        or plan.get("maximum_frames") != 120000
    ):
        raise ValueError("trainer baseline scope differs")
    output = plan.get("output")
    if not isinstance(output, str) or Path(output).exists():
        raise ValueError("trainer baseline output must be new")
    return plan, capture, model


def run(plan_path: Path, *, check_only: bool = False) -> dict[str, object]:
    plan, capture, model = _authenticate(json.loads(plan_path.read_bytes()))

    class FrozenAttackBaseline:
        policy_id = "frozen-attack-model-decline-optional-first-legal-forced"

        def choose_main(self, _observation, prepared):
            index = model.predict(
                prepared.features.candidate_vectors,
                legal_mask=prepared.features.legal_mask,
                current_pp=prepared.features.current_pp,
            )
            return BattleAction.move(prepared.features.slot_indices[index] + 1)

        def choose_switch(self, _observation, legal_party_slots, *, forced, may_decline):
            if forced:
                return legal_party_slots[0]
            assert may_decline
            return None

    if check_only:
        return {
            "status": "action_free_trainer_baseline_preflight_passed",
            "capture_id": capture.manifest.capture_id,
            "controller_actions": 0,
            "emulator_frames": 0,
            "persistent_artifacts": 0,
        }

    rom_record = plan["rom"]
    assert isinstance(rom_record, dict) and isinstance(rom_record["path"], str)

    @contextmanager
    def session_factory():
        with PyBoyAdapter(Path(rom_record["path"]), watch=False, speed=None) as emulator:
            yield FrameBudgetController(emulator, maximum_frames=120000)

    output = Path(plan["output"])
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(
        output / "execution-started.json",
        {
            "capture_manifest_sha256": capture.manifest_sha256,
            "policy_id": FrozenAttackBaseline.policy_id,
            "source_commit": plan["source_commit"],
        },
    )
    try:
        result = run_red_trainer_practice_episode(
            capture,
            session_factory=session_factory,
            policy=FrozenAttackBaseline(),
            max_decisions=80,
        )
    except Exception as error:
        _record(output / "failure.json", {"type": type(error).__name__, "message": str(error)})
        raise
    report = result.public_dict()
    report.update(
        {
            "baseline_only": True,
            "learned_switch_authority": False,
            "source_commit": plan["source_commit"],
            "model_updates": 0,
            "full_game_replays": 0,
        }
    )
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
