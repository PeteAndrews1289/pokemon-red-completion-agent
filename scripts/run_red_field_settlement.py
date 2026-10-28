"""Retain one bounded neutral-field recovery after a recorded frame-budget stop."""

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from run_red_autonomous_collection import ROOT, _verify_reserve_lineage

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_party import PokemonRedPartyReader


def settle(reader, actions, controller, resources):
    """Never press a direction or dismiss dialogue; retain any failed boundary."""
    before = resources()
    origin = reader.read()
    for attempt in range(65):
        raw = reader.read()
        readiness = reader.read_input_readiness()
        if (
            controller.pressed_buttons
            or raw.battle_state != 0
            or raw.map_id != origin.map_id
            or reader.read_bottom_dialogue_box_visible()
            or resources() != before
            or any(
                getattr(readiness, key) != 0
                for key in (
                    "joy_ignore",
                    "simulated_joypad_index",
                    "npc_movement_script_table",
                    "status_flags_5",
                    "movement_flags",
                )
            )
        ):
            raise ValueError("neutral field settlement crossed its safe boundary")
        if readiness.ready:
            return attempt
        if attempt < 64:
            actions.execute(MacroAction(MacroActionKind.WAIT))
    raise ValueError("neutral field settlement exhausted 64 frames")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    plan_path = parser.parse_args().plan
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    payloads = {}
    for key in ("rom", "state", "reserve_origin", "prior_plan", "prior_outcome", "prior_result"):
        if key not in plan:
            continue
        record = plan[key]
        payloads[key] = Path(record["path"]).read_bytes()
        if hashlib.sha256(payloads[key]).hexdigest() != record["sha256"]:
            raise ValueError("field settlement authentication failed")
    _verify_reserve_lineage(plan, payloads, field_settlement=True)
    if json.loads(payloads["prior_outcome"]).get("safe_terminal") is not False:
        raise ValueError("field settlement requires an incomplete field endpoint")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("field settlement requires committed source")
    output = Path(plan["output"])
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.field-settlement.v1",
            "provenance": {
                "parent_state_sha256": plan["state"]["sha256"],
                "reserve_origin_state_sha256": plan["reserve_origin"]["sha256"],
                "source_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "input_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
                "prior_outcome_sha256": plan["prior_outcome"]["sha256"],
            },
        },
    )
    with PyBoyAdapter(Path(plan["rom"]["path"]), watch=False, speed=None) as emulator:
        emulator.load_state_bytes(payloads["state"])
        controller = FrameBudgetController(emulator, maximum_frames=64)
        reader = PokemonRedStateReader(controller)
        actions = CountingExecutor(FrameSafeExecutor(controller))

        def resources():
            raw = reader.read()
            return (
                raw.player_money,
                raw.bag_items,
                raw.event_flags,
                reader.read_pokedex_state(),
                reader.read_all_box_states(),
                PokemonRedPartyReader(controller).read(),
            )

        original = resources()
        error = None
        releases = ()
        try:
            if plan.get("release_restored_inputs") is True:
                releases = FrameSafeExecutor(controller).release_restored_inputs()
            settle(reader, actions, controller, resources)
        except Exception as caught:
            error = {"type": type(caught).__name__, "message": str(caught)}
        terminal = emulator.save_state_bytes()
        _write(output / "terminal.state", terminal)
        _record(
            output / "outcome.json",
            {
                "before_state_sha256": plan["state"]["sha256"],
                "terminal_state_sha256": hashlib.sha256(terminal).hexdigest(),
                "safe_terminal": error is None,
                "verification": "field_ready" if error is None else None,
                "model_queries": 0,
                "neutral_frames": emulator.frame_count,
                "actions": actions.actions_executed,
                "released_inputs": releases,
                "preserved_resources": resources() == original,
                "readiness": asdict(reader.read_input_readiness()),
                "error": error,
            },
        )
        print(json.dumps({"output": str(output), "error": error, "frames": emulator.frame_count}))


if __name__ == "__main__":
    main()
