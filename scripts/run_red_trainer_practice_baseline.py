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
from dataclasses import replace
from pathlib import Path

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController, FrameSafeExecutor
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_trainer_practice_counterfactual import (
    TrainerPracticeFirstChoice,
    collect_trainer_practice_counterfactuals,
)
from pokemon_red_completion.red_trainer_practice_episode import (
    run_red_trainer_practice_episode,
)
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
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
        or plan.get("matched_choices") not in {None, "opening_attack_vs_five_switches"}
        or plan.get("matched_prompt_choices") not in {None, True}
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

        def __init__(self):
            self.last_decision_diagnostics: dict[str, object] = {}

        def choose_main(self, _observation, prepared):
            probabilities = model.predict_proba(
                prepared.features.candidate_vectors,
                legal_mask=prepared.features.legal_mask,
                current_pp=prepared.features.current_pp,
            )
            index = int(probabilities.argmax())
            self.last_decision_diagnostics = {
                "move_probabilities": probabilities.tolist(),
                "move_candidate_slots": [slot + 1 for slot in prepared.features.slot_indices],
                "control_rule": "always_attack",
            }
            return BattleAction.move(prepared.features.slot_indices[index] + 1)

        def choose_switch(self, _observation, legal_party_slots, *, forced, may_decline):
            if forced:
                self.last_decision_diagnostics = {"control_rule": "first_legal_forced"}
                return legal_party_slots[0]
            assert may_decline
            self.last_decision_diagnostics = {"control_rule": "decline_optional"}
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
    model_binding = plan["model"]
    assert isinstance(model_binding, dict)
    log = TrainerPracticeEventLog(
        output / "events",
        run_identity={
            "source_commit": plan["source_commit"],
            "capture_id": capture.manifest.capture_id,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "partition": capture.manifest.partition.value,
            "capture_manifest_sha256": capture.manifest_sha256,
            "model_sha256": model_binding["sha256"],
            "policy_id": FrozenAttackBaseline.policy_id,
            "maximum_frames": plan["maximum_frames"],
            "max_decisions": plan["max_decisions"],
        },
    )
    try:
        result = run_red_trainer_practice_episode(
            capture,
            session_factory=session_factory,
            policy=FrozenAttackBaseline(),
            max_decisions=80,
            event_sink=log.emit,
        )

        def retain_branch(index, choice, episode):  # type: ignore[no-untyped-def]
            _record(
                output / f"matched-branch-{index:02d}.json",
                {"first_choice_ref": choice.semantic_ref, "episode": episode.public_dict()},
            )

        matched = (
            collect_trainer_practice_counterfactuals(
                capture,
                session_factory=session_factory,
                continuation_policy_factory=FrozenAttackBaseline,
                first_choices=(
                    TrainerPracticeFirstChoice(BattleAction.move(1)),
                    *(
                        TrainerPracticeFirstChoice(BattleAction.switch(slot))
                        for slot in range(2, 7)
                    ),
                ),
                max_decisions=8,
                player_turn_horizon=2,
                branch_sink=retain_branch,
            )
            if plan.get("matched_choices") == "opening_attack_vs_five_switches"
            else None
        )
        matched_prompt = None
        if plan.get("matched_prompt_choices") is True:
            with PyBoyAdapter(Path(rom_record["path"]), watch=False, speed=None) as emulator:
                emulator.load_state_bytes(capture.state_bytes)
                reader = PokemonRedStateReader(emulator)
                actions = FrameSafeExecutor(
                    FrameBudgetController(emulator, maximum_frames=10000)
                )
                execute_bounded_battle_move_turn(
                    reader,
                    actions,
                    expected_map=capture.manifest.expected_map,
                    selected_slot=1,
                    expected_battle_state=2,
                    settle_to_next_decision=True,
                    timing=replace(
                        DEFAULT_BATTLE_RUNTIME_TIMING,
                        max_post_attack_transition_pulses=40,
                    ),
                    label="trainer practice prompt capture",
                )
                raw = reader.read()
                if not reader.trainer_switch_prompt_visible(raw):
                    raise ValueError("trainer practice opening attack missed replacement prompt")
                observation = PokemonRedObservationEncoder.from_state_reader(
                    reader
                ).snapshot_from_raw(raw).to_dict()
                prompt_state = emulator.save_state_bytes()
            prompt_manifest = build_battle_scenario_capture_payload(
                capture_id=f"{capture.manifest.capture_id}-replacement-prompt",
                root_lineage_id=capture.manifest.root_lineage_id,
                partition=ScenarioPartition.TRAIN,
                state_bytes=prompt_state,
                initial_observation_sha256=canonical_sha256(observation),
                source_commit=plan["source_commit"],
                expected_map=capture.manifest.expected_map,
                expected_battle_state=2,
                source_state_sha256=capture.manifest.state_sha256,
            )
            _write(output / "prompt.state", prompt_state)
            _write(output / "prompt.state.json", prompt_manifest)
            prompt_capture = open_battle_scenario_capture(
                output / "prompt.state", output / "prompt.state.json"
            )

            def retain_prompt_branch(index, choice, episode):  # type: ignore[no-untyped-def]
                _record(
                    output / f"prompt-branch-{index:02d}.json",
                    {"first_choice_ref": choice.semantic_ref, "episode": episode.public_dict()},
                )

            matched_prompt = collect_trainer_practice_counterfactuals(
                prompt_capture,
                session_factory=session_factory,
                continuation_policy_factory=FrozenAttackBaseline,
                first_choices=(
                    TrainerPracticeFirstChoice(None),
                    *(
                        TrainerPracticeFirstChoice(BattleAction.switch(slot))
                        for slot in range(2, 7)
                    ),
                ),
                max_decisions=5,
                player_turn_horizon=1,
                branch_sink=retain_prompt_branch,
            )
    except Exception as error:
        log.fail(error)
        _record(
            output / "event-log-verification.json",
            verify_trainer_practice_event_log(log.directory),
        )
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
    if matched is not None:
        _record(output / "matched-choices.json", matched.public_dict())
    if matched_prompt is not None:
        _record(output / "matched-prompt-choices.json", matched_prompt.public_dict())
    log.finish({
        "battle_won": result.battle_won,
        "stop_reason": result.stop_reason,
        "decision_count": len(result.decisions),
        "elapsed_ns": result.elapsed_ns,
        "outcome_sha256": canonical_sha256(report),
    })
    _record(
        output / "event-log-verification.json",
        verify_trainer_practice_event_log(log.directory),
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, check_only=args.check_only), sort_keys=True))


if __name__ == "__main__":
    main()
