"""One-shot fresh Safari setup qualification, never a fitting entry point.

No input save is accepted. The fixed claim is created before emulator startup;
failure consumes it. This diagnostic cannot create registered TRAIN examples.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerActionLimiter,
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from pokemon_red_completion.local_router import find_local_path
from pokemon_red_completion.observation import MapId, PokemonRedStateReader
from pokemon_red_completion.opening import run_opening_chapter
from pokemon_red_completion.red_live_safari import discover_reachable_red_safari_areas
from pokemon_red_completion.red_safari_training_setup import (
    RED_ROM_SHA256,
    redirect_fresh_lab_exit,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

ROOT = Path(__file__).resolve().parents[1]
CLAIM_ID = "safari-assisted-setup-train4100-20260920-v1"
BOOT_FRAMES = 4100
MAXIMUM_FRAMES = 60_000
MAXIMUM_WALL_SECONDS = 180
MAXIMUM_SETUP_ACTIONS = 40


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


class TracedController:
    """Retain every attempted input/frame advance, including failed calls."""

    def __init__(self, delegate, stream):
        self.delegate = delegate
        self.stream = stream
        self.ordinal = 0

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def _call(self, operation, value):
        self.ordinal += 1
        event = {"ordinal": self.ordinal, "operation": operation, "value": value,
                 "frame": self.frame_count}
        self.stream.write(json.dumps(dict(event, status="attempt")) + "\n")
        self.stream.flush()
        try:
            result = getattr(self.delegate, operation)(value)
        except Exception as error:
            self.stream.write(json.dumps(dict(event, status="failed", error=str(error))) + "\n")
            self.stream.flush()
            raise
        self.stream.write(json.dumps(dict(event, status="complete", end_frame=self.frame_count))
                          + "\n")
        self.stream.flush()
        return result

    def press(self, button):
        return self._call("press", button)

    def release(self, button):
        return self._call("release", button)

    def tick(self, frames):
        return self._call("tick", frames)


def finish_lab_exit(actions, reader, emulator) -> None:
    """Finish the lab's edge warp, not just the step onto its doorway.

    pokered's CheckWarpsNoCollision may leave BIT_STANDING_ON_WARP set
    after a released pulse. A subsequent outward collision dispatches
    CheckWarpsCollision. Permit that one exact observed boundary only.
    This correction is ROM-free tested; the first native claim stays failed.
    """
    before = reader.read()
    if (before.map_id != MapId.OAKS_LAB or (before.player_y, before.player_x) != (10, 4)
            or before.battle_state or emulator.pressed_buttons
            or not reader.read_input_readiness().ready):
        raise ValueError("lab exit requires released input at the verified approach")
    for ordinal in range(2):
        actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
        raw = reader.read()
        ready = not emulator.pressed_buttons and reader.read_input_readiness().ready
        if raw.map_id == MapId.SAFARI_ZONE_GATE and not raw.battle_state and ready:
            return
        if (ordinal == 0 and raw.map_id == MapId.OAKS_LAB
                and (raw.player_y, raw.player_x) == (11, 4) and not raw.battle_state and ready):
            continue
        raise ValueError("native exit did not reach a released ready Safari gate")


def run(rom_path: Path, private_root: Path) -> dict[str, object]:
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit setup qualification source before dispatch")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    rom = rom_path.read_bytes()
    if hashlib.sha256(rom).hexdigest() != RED_ROM_SHA256:
        raise ValueError("setup qualification ROM differs")
    # ROM-only route discovery is not gameplay or access to any retained save.
    world = StrategicScenarioRouteWorld.from_rom(rom)
    output = private_root / CLAIM_ID
    output.mkdir(mode=0o700, exist_ok=False)
    declaration = {
        "schema": "pokemon.red.safari-assisted-setup-claim.v1",
        "claim_id": CLAIM_ID, "source_commit": commit, "boot_frames": BOOT_FRAMES,
        "rom_sha256": RED_ROM_SHA256, "prospective_partition": "train",
        "maximum_frames": MAXIMUM_FRAMES, "maximum_wall_seconds": MAXIMUM_WALL_SECONDS,
        "maximum_post_opening_actions": MAXIMUM_SETUP_ACTIONS,
        "load_state_allowed": False, "retry_allowed": False,
        "learning_admission": "setup_only_not_registered_train",
        "allowed_intervention": "six_byte_lab_exit_redirect_before_any_model_query",
        "independence_claim": "one_new_power_on_only_no_split_or_transfer_claim",
        "model_queries": 0, "model_updates": 0,
    }
    write_json(output / "claim.json", declaration)
    result = dict(declaration, status="failed", stage="startup")
    started = time.monotonic()
    with (output / "inputs.jsonl").open("x", encoding="utf-8") as trace:  # noqa: SIM117
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            session = TracedController(MonotonicWallTimeBudgetController(
                FrameBudgetController(emulator, maximum_frames=MAXIMUM_FRAMES),
                maximum_wall_seconds=MAXIMUM_WALL_SECONDS,
            ), trace)
            reader = PokemonRedStateReader(session)
            actions = None
            try:
                result["stage"] = "fresh_opening"
                opening = run_opening_chapter(
                    rom_path, _emulator=session,
                    new_game_timing=replace(DEFAULT_NEW_GAME_TIMING, boot_frames=BOOT_FRAMES),
                )
                if not opening.passed:
                    raise ValueError("fresh opening did not verify its starter boundary")
                origin = emulator.save_state_bytes()
                (output / "origin.state").write_bytes(origin)
                result["origin_state_sha256"] = hashlib.sha256(origin).hexdigest()
                result["opening_frames"] = emulator.frame_count
                result["stage"] = "isolated_intervention"
                raw = reader.read()
                # Private adapter port is used only here, never passed to a policy.
                interventions = redirect_fresh_lab_exit(
                    emulator._require_backend().memory, rom_sha256=RED_ROM_SHA256,
                    isolated_training_setup=True, controller_released=not emulator.pressed_buttons,
                    battle_state=raw.battle_state,
                )
                write_json(output / "interventions.json", interventions)
                assisted = emulator.save_state_bytes()
                (output / "assisted.state").write_bytes(assisted)
                result["assisted_state_sha256"] = hashlib.sha256(assisted).hexdigest()
                result["stage"] = "native_lab_exit"
                actions = CountingExecutor(ControllerActionLimiter(
                    FrameSafeExecutor(session, DEFAULT_NEW_GAME_TIMING.controller_timing()),
                    maximum_actions=MAXIMUM_SETUP_ACTIONS,
                ))
                path = find_local_path(
                    world.local_graphs[int(MapId.OAKS_LAB)],
                    (raw.player_y, raw.player_x), (10, 4), start_mode="land",
                )
                write_json(output / "setup-route.json", {
                    "coordinates": path.coordinates, "directions": [e.action for e in path.edges],
                    "authority": "teacher_setup_not_model",
                })
                for edge in path.edges:
                    actions.execute(edge.macro_action)
                    current = reader.read()
                    if (current.map_id != MapId.OAKS_LAB or current.battle_state
                            or (current.player_y, current.player_x) != edge.target):
                        raise ValueError("native setup path missed coordinate postcondition")
                finish_lab_exit(actions, reader, emulator)
                raw = reader.read()
                if (raw.map_id != MapId.SAFARI_ZONE_GATE or raw.battle_state
                        or emulator.pressed_buttons or not reader.read_input_readiness().ready):
                    raise ValueError("native exit did not reach a released ready Safari gate")
                result["stage"] = "feasible_destination_inventory"
                areas = discover_reachable_red_safari_areas(
                    rom, reader.read_pokedex_state().owned_species,
                    free_storage_slots=6 - raw.party_count, world=world, reader=reader,
                )
                write_json(output / "areas.json", [a.public_dict() for a in areas])
                if len(areas) < 2:
                    raise ValueError("setup lacks two feasible Safari destinations")
                result.update(status="setup_qualified", candidate_count=len(areas),
                              post_opening_actions=actions.actions_executed)
            except Exception as error:
                result.update(error_type=type(error).__name__, error=str(error))
            finally:
                try:
                    terminal = emulator.save_state_bytes()
                    (output / "terminal.state").write_bytes(terminal)
                    result["terminal_state_sha256"] = hashlib.sha256(terminal).hexdigest()
                except Exception as retention_error:
                    result["state_retention_error"] = str(retention_error)
                    result["status"] = "failed"
                result["frames"] = emulator.frame_count
                result["wall_seconds"] = time.monotonic() - started
                result["pressed_buttons"] = sorted(emulator.pressed_buttons)
                result["post_opening_actions"] = 0 if actions is None else actions.actions_executed
                try:
                    raw = reader.read()
                    result["terminal"] = {
                        "map": raw.map_id, "x": raw.player_x, "y": raw.player_y,
                        "battle": raw.battle_state, "money": raw.player_money,
                    }
                except Exception as observation_error:
                    result["observation_retention_error"] = str(observation_error)
                    result["status"] = "failed"
                result["input_trace_sha256"] = hashlib.sha256(
                    (output / "inputs.jsonl").read_bytes()).hexdigest()
                result["new_fitted_examples"] = 0
                write_json(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.rom, args.private_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "setup_qualified" else 1)
