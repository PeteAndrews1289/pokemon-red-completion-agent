"""Continue one retained model-selected wild battle without replaying its route."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import committed_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_autonomous_capture_recovery import (
    validate_autonomous_capture_recovery_source,
)
from pokemon_red_completion.red_autonomous_player import _exception_chain
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref
from pokemon_red_completion.surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _record(path: Path, document: Mapping[str, object]) -> None:
    _write(path, (json.dumps(document, sort_keys=True, indent=2) + "\n").encode())


def _authenticated(plan: Mapping[str, object], key: str) -> bytes:
    item = plan.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"recovery plan lacks {key}")
    path = Path(item["path"])
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != item.get("sha256"):
        raise ValueError(f"recovery {key} authentication failed")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get("schema") != "pokemon.red.autonomous-capture-recovery-plan.v1":
        raise ValueError("recovery plan schema differs")
    payloads = {
        key: _authenticated(plan, key)
        for key in (
            "rom",
            "failed_result",
            "failed_outcome",
            "failed_decision",
            "failed_execution",
            "failed_terminal",
        )
    }
    source = validate_autonomous_capture_recovery_source(
        result=json.loads(payloads["failed_result"]),
        outcome=json.loads(payloads["failed_outcome"]),
        decision=json.loads(payloads["failed_decision"]),
        execution_started=json.loads(payloads["failed_execution"]),
        terminal_state=payloads["failed_terminal"],
    )
    maximum_actions = plan.get("maximum_actions")
    maximum_frames = plan.get("maximum_frames")
    if type(maximum_actions) is not int or not 1 <= maximum_actions <= 1_000:
        raise ValueError("recovery action bound differs")
    if type(maximum_frames) is not int or not 1 <= maximum_frames <= 240_000:
        raise ValueError("recovery frame bound differs")
    output = Path(plan["output"])
    if output.exists():
        raise FileExistsError("autonomous capture recovery is already claimed")
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status:
        raise ValueError("commit the reviewed source before autonomous recovery")

    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.autonomous-capture-recovery-execution.v1",
            "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "source_bundle_sha256": committed_source_bundle_sha256(ROOT),
            "model_sha256": source.model_sha256,
            "parent_state_sha256": source.terminal_state_sha256,
            "selected_binding_ref": source.selected_binding_ref,
            "maximum_actions": maximum_actions,
            "maximum_frames": maximum_frames,
            "route_replayed": False,
            "model_queried": False,
            "learning_eligible": False,
        },
    )

    with PyBoyAdapter(Path(plan["rom"]["path"]), watch=False, speed=None) as emulator:
        emulator.load_state_bytes(payloads["failed_terminal"])
        if emulator.save_state_bytes() != payloads["failed_terminal"] or emulator.pressed_buttons:
            raise ValueError("exact retained terminal roundtrip differs")
        initial_frame = emulator.frame_count
        frames = WindowedFrameBudgetController(
            emulator,
            maximum_frames_per_window=maximum_frames,
            maximum_total_frames=maximum_frames,
        )
        hard = HardCompositionActionLimiter(
            FrameSafeExecutor(frames, DEFAULT_NEW_GAME_TIMING.controller_timing()),
            maximum_actions_per_decision=maximum_actions,
            maximum_episode_actions=maximum_actions,
        )
        actions = CountingExecutor(hard)
        reader = PokemonRedStateReader(frames)
        raw = reader.read()
        if raw.battle_state != 1 or raw.enemy_species_id is None:
            raise ValueError("retained acquisition terminal is not a wild battle")
        target = red_species_ref(red_internal_species_number(raw.enemy_species_id))
        capture = LiveWildEncounterExecutor(
            frames,
            actions,
            reader,
            DEFAULT_SURGE_TIMING,
            label="autonomous capture exact-state recovery",
            capture_status_support=True,
        )
        before = capture.read_collection()
        if target in before.owned_species:
            raise ValueError("retained encounter target is already registered")
        _write(output / "before.state", payloads["failed_terminal"])
        _record(
            output / "intent.json",
            {
                "schema": "pokemon.red.autonomous-capture-recovery-intent.v1",
                "parent_state_sha256": source.terminal_state_sha256,
                "selected_binding_ref": source.selected_binding_ref,
                "target_species_ref": target,
                "model_sha256": source.model_sha256,
                "model_queried": False,
                "teacher_actions": 0,
                "route_replayed": False,
                "learning_eligible": False,
            },
        )
        caught = False
        error: BaseException | None = None
        try:
            caught = capture.capture_encounter(target)
        except BaseException as caught_error:
            error = caught_error
        terminal = emulator.save_state_bytes()
        _write(output / "terminal.state", terminal)
        final = reader.read()
        after = capture.read_collection()
        safe = (
            final.battle_state == 0
            and reader.read_input_readiness().ready
            and not emulator.pressed_buttons
        )
        gained = target in after.owned_species and target not in before.owned_species
        specimen_delta = len(after.specimens) - len(before.specimens)
        success = error is None and caught is True and safe and gained and specimen_delta == 1
        result = {
            "schema": "pokemon.red.autonomous-capture-recovery-result.v1",
            "status": "succeeded" if success else "failed",
            "model_sha256": source.model_sha256,
            "selected_binding_ref": source.selected_binding_ref,
            "target_species_ref": target,
            "parent_state_sha256": source.terminal_state_sha256,
            "terminal_state_sha256": hashlib.sha256(terminal).hexdigest(),
            "caught": caught,
            "safe_terminal": safe,
            "registration_gain": int(gained),
            "specimen_delta": specimen_delta,
            "registered_species_before": len(before.owned_species),
            "registered_species_after": len(after.owned_species),
            "actions": hard.attempted_actions,
            "completed_actions": actions.actions_executed,
            "frames": emulator.frame_count - initial_frame,
            "battle_state": final.battle_state,
            "map_id": final.map_id,
            "position_yx": [final.player_y, final.player_x],
            "status_reports": capture.capture_status_reports,
            "throw_preparations": capture.capture_throw_preparations,
            "model_queries": 0,
            "teacher_actions": 0,
            "route_replayed": False,
            "learning_eligible": False,
            "authority_promotions": 0,
            "error_chain": _exception_chain(error),
        }
        _record(output / "result.json", result)
        print(json.dumps(result, sort_keys=True, indent=2))
        if not success:
            raise RuntimeError("autonomous capture recovery did not reach its verified terminal")


if __name__ == "__main__":
    main()
