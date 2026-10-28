"""Explicit nonlearned diagnostic reference; never a campaign fallback or trainer."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from pathlib import Path

from run_red_development_worker import validate_spec
from run_red_trainer_practice_model import retained_session

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.emulation_batch import _record, file_digest, verify_pins
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import ControllerActionLimiter, FrameSafeExecutor
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_trainer_practice_episode import run_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_features import project_trainer_move_features
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trainer_proposed_control import estimated_finishing_features
from pokemon_red_completion.scenario_lab import ScenarioPartition


class PublicDamageReference:
    """Always attack; public approximate damage times accuracy, deterministic ties.

    This deliberately omits status tactics, voluntary switches and lookahead.
    It is a falsifiable simple reference, not an optimal battle oracle.
    """

    policy_id = "teacher-public-damage-decline-optional-healthiest-forced-v1"

    def __init__(self):
        self.last_decision_diagnostics = {}

    def choose_main(self, observation, prepared):
        projected = project_trainer_move_features(observation, prepared.features)
        accuracy_index = projected.feature_names.index("move.accuracy")
        candidates = []
        for slot, row, legal in zip(
            projected.candidate_slots,
            projected.candidate_vectors,
            prepared.supported_candidate_mask,
            strict=True,
        ):
            if legal:
                available, fraction, _ = estimated_finishing_features(observation, row)
                if not available:
                    raise ValueError("reference requires ordinary damaging move estimates")
                candidates.append((slot, fraction * row[accuracy_index]))
        if not candidates:
            raise ValueError("reference attack inventory exhausted")
        slot, _ = max(candidates, key=lambda item: (item[1], -item[0]))
        self.last_decision_diagnostics = dict(
            teacher=True, learned=False, rule="public_damage_times_accuracy",
            candidates=[list(item) for item in candidates], selected_slot=slot,
        )
        return BattleAction.move(slot)

    def choose_switch(self, observation, legal_party_slots, *, forced, may_decline):
        if forced is may_decline:
            raise ValueError("reference switch mode differs")
        if may_decline:
            self.last_decision_diagnostics = dict(
                teacher=True, learned=False, rule="decline_optional"
            )
            return None
        members = observation["features"]["party"]["members"]
        candidates = [
            (member["party_index"] + 1, member["hp"])
            for member in members
            if member["party_index"] + 1 in legal_party_slots and member["hp"] > 0
        ]
        if not candidates:
            raise ValueError("reference has no living legal replacement")
        slot, _ = max(candidates, key=lambda item: (item[1], -item[0]))
        self.last_decision_diagnostics = dict(
            teacher=True, learned=False, rule="highest_current_hp",
            candidates=[list(item) for item in candidates], selected_slot=slot,
        )
        return slot


def run(spec, output, spec_sha):
    validate_spec(spec)
    if (
        spec.get("reference_policy") != PublicDamageReference.policy_id
        or spec.get("allow_status_moves") is not False
    ):
        raise ValueError("reference scope differs")
    capture = open_battle_scenario_capture(Path(spec["capture"]), Path(spec["manifest"]))
    if capture.manifest.partition is not ScenarioPartition.TRAIN:
        raise ValueError("reference requires declared TRAIN fixture")
    cartridge = RedPracticeCartridge(Path(spec["rom"]).read_bytes())
    actor = PublicDamageReference()
    log = TrainerPracticeEventLog(output / "events", run_identity=dict(
        spec_sha256=spec_sha, policy_id=actor.policy_id, teacher=True,
        learned=False, model_queries=0, fit_allowed=False, copy_back=False,
        capture_sha256=capture.manifest.state_sha256,
        root=capture.manifest.root_lineage_id, partition="train", offset=spec["offset"],
    ))
    active = {}

    class Actions:
        def execute(self, action):
            return active["limiter"].execute(action)

    @contextmanager
    def session():
        with (
            PyBoyAdapter(Path(spec["rom"]), watch=False, speed=None) as em,
            retained_session(
                em, maximum_frames=160000, output=output,
                maximum_controller_actions=3000, maximum_wall_seconds=90,
                action_metadata=lambda: dict(
                    attempted_actions=active["limiter"].attempted_actions,
                    completed_actions=active["limiter"].completed_actions,
                ) if "limiter" in active else {},
            ) as port,
        ):
            active["limiter"] = ControllerActionLimiter(
                FrameSafeExecutor(port), maximum_actions=3000,
                admit_action=port.check_wall_time_budget,
            )
            yield port

    try:
        episode = run_red_trainer_practice_episode(
            capture, session_factory=session, policy=actor, max_decisions=80,
            opening_idle_frames=spec["offset"], action_executor=Actions(),
            event_sink=log.emit, public_species_base_stats=cartridge.public_base_stats,
            allow_stranded_accuracy_move=True, allow_status_moves=False,
            include_status_context=True,
        )
        payload = episode.public_dict()
        # The engine's intervention count refers to overrides of the supplied
        # policy, not its learned/nonlearned provenance. Keep that fact explicit.
        _record(output / "episode.json", payload)
        if not log.closed:
            log.finish(payload)
        return dict(
            valid=episode.stop_reason in ("battle_won", "party_defeated"),
            won=episode.battle_won, stop=episode.stop_reason,
            teacher_controlled_choices=len(episode.decisions), model_queries=0,
            learned_choices=0, policy_id=actor.policy_id, teacher=True,
            episode_sha256=file_digest(output / "episode.json"),
            log=verify_trainer_practice_event_log(output / "events"),
        )
    except BaseException as error:
        if not log.closed:
            log.fail(error)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("spec_sha256")
    args = parser.parse_args()
    if file_digest(args.spec) != args.spec_sha256:
        raise ValueError("reference spec hash differs")
    spec = json.loads(args.spec.read_bytes())
    output = Path.cwd() / "artifacts"
    output.mkdir(exist_ok=False)
    result = dict(spec_sha256=args.spec_sha256, valid=False, teacher=True, model_queries=0)
    try:
        result.update(run(spec, output, args.spec_sha256))
        verify_pins(spec["pins"])
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error), valid=False)
        raise
    finally:
        _record(output / "result.json", result)
        print(json.dumps(result), flush=True)
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
