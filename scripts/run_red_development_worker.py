"""One isolated diagnostic job, never a campaign or a model-promotion command.

The parent pins this script, package, job declaration and private inputs before launch.
Battle specifications consume pre-existing captures without editing them. Fresh smoke
jobs reuse the deterministic opening/rival teacher and explicitly make no learned claim.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

from run_red_trainer_practice_model import retained_session

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulation_batch import file_digest, verify_pins
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import ControllerActionLimiter, FrameSafeExecutor
from pokemon_red_completion.observation import MapId, OpeningPhase, PokemonRedStateReader
from pokemon_red_completion.opening import run_opening_chapter
from pokemon_red_completion.play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    LAB_RIVAL_TRIGGER_DIRECTIONS,
    _expect_position,
    _move,
    _resolve_lab_rival,
    _wait,
    is_rival_resolution_verified,
    is_rival_victory_verified,
)
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_player_origins import _NoLoadController, _OpeningActions
from pokemon_red_completion.red_safari_training_setup import RED_ROM_SHA256
from pokemon_red_completion.red_trainer_practice_episode import run_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def validate_spec(spec):
    """Reject wrong roles, undeclared inputs and unbounded or broadened jobs before input."""
    if spec.get("mode") not in ("battle", "fresh_smoke"):
        raise ValueError("undeclared diagnostic mode")
    if type(spec.get("allow_status_moves", False)) is not bool:
        raise ValueError("status action scope must be an explicit boolean")
    if spec.get("fit_allowed") is not False or spec.get("copy_back") is not False:
        raise ValueError("diagnostics cannot fit or copy back")
    required = [spec["rom"]]
    if spec["mode"] == "battle":
        required += [spec["model"], spec["capture"], spec["manifest"]]
        if spec.get("offset") not in (0, 4, 8):
            raise ValueError("undeclared battle offset")
    elif spec.get("boot_offset") not in (257, 293):
        raise ValueError("undeclared fresh smoke offset")
    if any(path not in spec["pins"] for path in required):
        raise ValueError("all native inputs must be pinned")
    if spec["pins"][spec["rom"]] != RED_ROM_SHA256:
        raise ValueError("wrong cartridge")
    verify_pins(spec["pins"])


def battle(spec, output, spec_sha):
    capture = open_battle_scenario_capture(Path(spec["capture"]), Path(spec["manifest"]))
    if capture.manifest.partition is ScenarioPartition.TEST:
        raise ValueError("diagnostic cannot consume TEST captures")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(Path(spec["model"]).read_bytes()))
    allow_status = spec.get("allow_status_moves", False)
    if allow_status and model.damage_reference is None:
        raise ValueError("status scope requires an existing composed status model")
    cartridge = RedPracticeCartridge(Path(spec["rom"]).read_bytes())
    log = TrainerPracticeEventLog(
        output / "events",
        run_identity=dict(
            spec_sha256=spec_sha,
            partition=capture.manifest.partition.value,
            root=capture.manifest.root_lineage_id,
            model_sha256=file_digest(Path(spec["model"])),
            capture_sha256=capture.manifest.state_sha256,
            fit_allowed=False,
            assisted=True,
            allow_status_moves=allow_status,
            include_status_context=True,
            offset=spec["offset"],
        ),
    )
    active = {}

    class Actions:
        def execute(self, action):
            return active["limiter"].execute(action)

    @contextmanager
    def session():
        with (
            PyBoyAdapter(Path(spec["rom"]), watch=False, speed=None) as em,
            retained_session(
                em,
                maximum_frames=160000,
                output=output,
                maximum_controller_actions=3000,
                maximum_wall_seconds=90,
                action_metadata=lambda: (
                    dict(
                        attempted_actions=active["limiter"].attempted_actions,
                        completed_actions=active["limiter"].completed_actions,
                    )
                    if "limiter" in active
                    else {}
                ),
            ) as port,
        ):
            active["limiter"] = ControllerActionLimiter(
                FrameSafeExecutor(port),
                maximum_actions=3000,
                admit_action=port.check_wall_time_budget,
            )
            yield port

    try:
        actor = RedTrainerPracticeOutcomePolicy(
            "misty-feasibility-risk",
            capture.manifest.capture_id,
            model,
        )
        episode = run_red_trainer_practice_episode(
            capture,
            session_factory=session,
            policy=actor,
            max_decisions=80,
            opening_idle_frames=spec["offset"],
            action_executor=Actions(),
            event_sink=log.emit,
            public_species_base_stats=cartridge.public_base_stats,
            allow_stranded_accuracy_move=True,
            allow_status_moves=allow_status,
            include_status_context=True,
        )
        payload = episode.public_dict()
        _record(output / "episode.json", payload)
        if not log.closed:
            log.finish(payload)
        return dict(
            valid=episode.stop_reason in ("battle_won", "party_defeated"),
            won=episode.battle_won,
            stop=episode.stop_reason,
            decisions=len(episode.decisions),
            episode_sha256=file_digest(output / "episode.json"),
            log=verify_trainer_practice_event_log(output / "events"),
        )
    except BaseException as error:
        if not log.closed:
            log.fail(error)
        raise


def fresh_smoke(spec, output):
    """New power-on, zero loads/edits/model calls; native teacher through rival resolution."""
    active = {}
    with PyBoyAdapter(Path(spec["rom"]), watch=False, speed=None) as em:
        if em.frame_count != 0 or em.pressed_buttons:
            raise ValueError("fresh emulator is not at untouched power-on")
        _write(output / "power-on.state", em.save_state_bytes())
        with retained_session(
            em,
            maximum_frames=80000,
            output=output,
            maximum_controller_actions=450,
            maximum_wall_seconds=180,
            action_metadata=lambda: (
                dict(
                    attempted_actions=active["actions"].delegate.attempted_actions,
                    completed_actions=active["actions"].delegate.completed_actions,
                )
                if "actions" in active
                else {}
            ),
        ) as port:
            controller = _NoLoadController(port, maximum_frames=80000)
            actions = _OpeningActions(controller, output)
            active["actions"] = actions
            timing = replace(
                DEFAULT_NEW_GAME_TIMING,
                boot_frames=DEFAULT_NEW_GAME_TIMING.boot_frames + spec["boot_offset"],
            )
            opening = run_opening_chapter(
                Path(spec["rom"]),
                new_game_timing=timing,
                _emulator=controller,
                _executor=actions,
            )
            _record(output / "opening.json", opening.public_dict())
            reader = PokemonRedStateReader(controller)
            if not opening.passed or reader.read_opening_control_state(reader.read()).phase != (
                OpeningPhase.STARTER_OBTAINED
            ):
                raise ValueError("opening did not reach starter boundary")
            _write(output / "starter.state", em.save_state_bytes())
            _move(actions, reader, LAB_RIVAL_TRIGGER_DIRECTIONS, "fresh smoke native rival")
            _expect_position(reader.read(), MapId.OAKS_LAB, 4, 6, "fresh smoke rival trigger")
            _wait(actions, DEFAULT_QUALIFIED_PLAY_TIMING.rival_trigger_wait_frames)
            raw, native, saw = _resolve_lab_rival(actions, reader, DEFAULT_QUALIFIED_PLAY_TIMING)
            resolved = is_rival_resolution_verified(native, saw_trainer_battle=saw)
            valid = (
                resolved
                and raw.battle_state == 0
                and reader.read_input_readiness().ready
                and not reader.read_bottom_dialogue_box_visible()
            )
            return dict(
                valid=valid,
                stop="rival_resolved" if valid else "rival_unresolved",
                rival_won=is_rival_victory_verified(native, saw_trainer_battle=saw),
                native=asdict(native),
                partition="development",
                state_loads=0,
                model_queries=0,
                memory_edits=0,
                teacher="existing opening and native rival",
                actions=len(actions.receipts),
                power_on_sha256=file_digest(output / "power-on.state"),
                starter_sha256=file_digest(output / "starter.state"),
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("spec_sha256")
    args = parser.parse_args()
    if file_digest(args.spec) != args.spec_sha256:
        raise ValueError("job declaration changed")
    spec = json.loads(args.spec.read_bytes())
    validate_spec(spec)
    output = Path.cwd() / "artifacts"
    output.mkdir(mode=0o700, exist_ok=False)
    result = dict(valid=False, spec_sha256=args.spec_sha256, fit_allowed=False, copy_back=False)
    try:
        result.update(
            battle(spec, output, args.spec_sha256)
            if spec["mode"] == "battle"
            else fresh_smoke(spec, output)
        )
        verify_pins(spec["pins"])
    except BaseException as error:
        result.update(valid=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        _record(output / "result.json", result)
        print(json.dumps(result), flush=True)
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
