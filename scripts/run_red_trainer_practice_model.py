"""Run one hash-bound three-head battle policy with durable decision telemetry.

TRAIN runs are curriculum evidence. DEVELOPMENT runs are comparisons only; this
script never fits, promotes, relabels, or opens TEST captures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from pokemon_red_completion.battle_control_model import BattleControlMLP
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    open_battle_scenario_capture,
)
from pokemon_red_completion.battle_switch_target_model import BattleSwitchTargetMLP
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_player import _record
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_trainer_practice_ancestry import trainer_origin_cluster
from pokemon_red_completion.red_trainer_practice_episode import run_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)
from pokemon_red_completion.red_trainer_practice_policy import RedTrainerPracticeModelPolicy
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.trainer-practice-model-plan.v1"
OUTCOME_SCHEMA = "pokemon.red.trainer-practice-outcome-model-plan.v1"
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
    if not isinstance(plan, dict) or plan.get("schema") not in {SCHEMA, OUTCOME_SCHEMA}:
        raise ValueError("trainer model plan differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit trainer model code before running it")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if plan.get("source_commit") != revision:
        raise ValueError("trainer model source commit differs")
    rom = _bound_file(plan.get("rom"), "ROM")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("trainer model Red ROM differs")
    model: TrainerPracticeThreeHeadModel | tuple[
        MaskedMLPMoveRanker, BattleControlMLP, BattleSwitchTargetMLP
    ]
    if plan["schema"] == OUTCOME_SCHEMA:
        model = TrainerPracticeThreeHeadModel.from_dict(
            json.loads(_bound_file(plan.get("outcome_model"), "outcome model"))
        )
    else:
        model = (
            MaskedMLPMoveRanker.from_dict(
                json.loads(_bound_file(plan.get("move_model"), "move model"))
            ),
            BattleControlMLP.from_dict(
                json.loads(_bound_file(plan.get("control_model"), "control model"))
            ),
            BattleSwitchTargetMLP.from_dict(
                json.loads(_bound_file(plan.get("switch_model"), "switch model"))
            ),
        )
    state, manifest = plan.get("capture_state"), plan.get("capture_manifest")
    _bound_file(state, "capture state")
    _bound_file(manifest, "capture manifest")
    assert isinstance(state, dict) and isinstance(manifest, dict)
    capture = open_battle_scenario_capture(Path(state["path"]), Path(manifest["path"]))
    if capture.manifest.partition not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}:
        raise ValueError("trainer model capture partition is unavailable")
    if (
        plan["schema"] == OUTCOME_SCHEMA
        and capture.manifest.observation_schema != OBSERVATION_SCHEMA_V2
    ):
        raise ValueError("outcome model requires actor-visible battle stats")
    if (
        isinstance(model, TrainerPracticeThreeHeadModel)
        and capture.manifest.partition is ScenarioPartition.DEVELOPMENT
        and trainer_origin_cluster(capture.manifest.root_lineage_id) in {
            trainer_origin_cluster(root) for root in model.train_root_ids
        }
    ):
        raise ValueError("DEVELOPMENT root overlaps outcome-model training lineage")
    max_decisions, maximum_frames = plan.get("max_decisions"), plan.get("maximum_frames")
    opening_idle_frames = plan.get("opening_idle_frames", 0)
    if (
        type(max_decisions) is not int or not 1 <= max_decisions <= 80
        or type(maximum_frames) is not int or not 1 <= maximum_frames <= 120000
        or type(opening_idle_frames) is not int
        or not 0 <= opening_idle_frames <= 12
    ):
        raise ValueError("trainer model budget differs")
    output = plan.get("output")
    if not isinstance(output, str) or Path(output).exists():
        raise ValueError("trainer model output must be new")
    return plan, capture, model


def run(plan_path: Path, *, check_only: bool = False) -> dict[str, object]:
    plan, capture, model = _authenticate(
        json.loads(plan_path.read_bytes())
    )
    if check_only:
        return {
            "status": "action_free_trainer_model_preflight_passed",
            "capture_id": capture.manifest.capture_id,
            "partition": capture.manifest.partition.value,
            "controller_actions": 0,
            "emulator_frames": 0,
            "persistent_artifacts": 0,
        }
    rom = plan["rom"]
    assert isinstance(rom, dict) and isinstance(rom["path"], str)
    maximum_frames = plan["maximum_frames"]
    max_decisions = plan["max_decisions"]
    opening_idle_frames = plan.get("opening_idle_frames", 0)
    assert isinstance(maximum_frames, int) and isinstance(max_decisions, int)
    assert isinstance(opening_idle_frames, int)

    @contextmanager
    def session_factory():
        with PyBoyAdapter(Path(rom["path"]), watch=False, speed=None) as emulator:
            yield FrameBudgetController(emulator, maximum_frames=maximum_frames)

    policy: RedTrainerPracticeOutcomePolicy | RedTrainerPracticeModelPolicy
    if isinstance(model, TrainerPracticeThreeHeadModel):
        policy = RedTrainerPracticeOutcomePolicy(
            policy_id="three-head-whole-party-outcome-model",
            battle_plan_id=capture.manifest.capture_id,
            model=model,
        )
        model_identity = {"outcome_model_sha256": plan["outcome_model"]["sha256"]}
        public_stats = RedPracticeCartridge(_bound_file(plan["rom"], "ROM")).public_base_stats
    else:
        move_model, control_model, switch_model = model
        policy = RedTrainerPracticeModelPolicy(
            policy_id="three-head-attack-switch-model",
            battle_plan_id=capture.manifest.capture_id,
            move_model=move_model,
            control_model=control_model,
            switch_model=switch_model,
        )
        model_identity = {
            "move_model_sha256": plan["move_model"]["sha256"],
            "control_model_sha256": plan["control_model"]["sha256"],
            "switch_model_sha256": plan["switch_model"]["sha256"],
        }
        public_stats = None
    output_path = plan["output"]
    assert isinstance(output_path, str)
    output = Path(output_path)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(output / "execution-started.json", {
        "source_commit": plan["source_commit"],
        "capture_manifest_sha256": capture.manifest_sha256,
        "policy_id": policy.policy_id,
        "partition": capture.manifest.partition.value,
        "opening_idle_frames": opening_idle_frames,
    })
    log = TrainerPracticeEventLog(output / "events", run_identity={
        "source_commit": plan["source_commit"],
        "capture_id": capture.manifest.capture_id,
        "root_lineage_id": capture.manifest.root_lineage_id,
        "partition": capture.manifest.partition.value,
        "capture_manifest_sha256": capture.manifest_sha256,
        "policy_id": policy.policy_id,
        **model_identity,
        "max_decisions": max_decisions,
        "maximum_frames": maximum_frames,
        "opening_idle_frames": opening_idle_frames,
    })
    try:
        episode = run_red_trainer_practice_episode(
            capture,
            session_factory=session_factory,
            policy=policy,
            max_decisions=max_decisions,
            opening_idle_frames=opening_idle_frames,
            event_sink=log.emit,
            public_species_base_stats=public_stats,
        )
    except Exception as error:
        log.fail(error)
        _record(output / "failure.json", {
            "schema": "pokemon.red.trainer-practice-model-failure.v1",
            "error_type": type(error).__name__,
            "partition": capture.manifest.partition.value,
        })
        _record(
            output / "event-log-verification.json",
            verify_trainer_practice_event_log(log.directory),
        )
        raise
    report = episode.public_dict()
    report.update({
        "partition": capture.manifest.partition.value,
        "root_lineage_id": capture.manifest.root_lineage_id,
        "source_commit": plan["source_commit"],
        "opening_idle_frames": opening_idle_frames,
        "model_updates": 0,
        "authority_promotions": 0,
    })
    _record(output / "outcome.json", report)
    log.finish({
        "battle_won": episode.battle_won,
        "stop_reason": episode.stop_reason,
        "decision_count": len(episode.decisions),
        "elapsed_ns": episode.elapsed_ns,
        "outcome_sha256": canonical_sha256(report),
    })
    _record(
        output / "event-log-verification.json",
        verify_trainer_practice_event_log(log.directory),
    )
    return {
        "status": "trainer_model_episode_recorded",
        "partition": capture.manifest.partition.value,
        "capture_id": capture.manifest.capture_id,
        "battle_won": episode.battle_won,
        "stop_reason": episode.stop_reason,
        "decision_count": len(episode.decisions),
        "metrics": report["metrics"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, check_only=args.check_only), sort_keys=True))


if __name__ == "__main__":
    main()
