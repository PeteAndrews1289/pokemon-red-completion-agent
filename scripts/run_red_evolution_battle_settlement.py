"""One authenticated defensive escape from a budget-interrupted evolution battle."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from pokemon_red_completion import red_goal_context as context
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_capture
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_goal_context_profile import parse_red_goal_context_profile
from pokemon_red_completion.red_team_training import escape_collection_battle

ROOT = Path(__file__).resolve().parents[1]


def validate_source(result, outcome, decision, started, state):
    """Bind the latest failed execution, not an earlier convenient snapshot."""
    if (
        result.get("schema") != "pokemon.red.autonomous-option-result.v1"
        or result.get("stop_reason") != "execution_failed"
        or not result.get("outcomes")
        or result["outcomes"][-1] != outcome
        or outcome.get("choice") != decision
        or outcome.get("selected_kind") != "evolve_species"
        or outcome.get("safe_terminal") is not False
        or outcome.get("error_type")
        not in {
            "CompositionActionBudgetExhausted",
            "ControllerFrameBudgetExhausted",
        }
        or outcome.get("after", {}).get("battle_state") != 1
        or outcome.get("terminal_state_sha256") != hashlib.sha256(state).hexdigest()
        or decision.get("schema") != "pokemon.red.live-mixed-option-choice.v1"
        or decision.get("mode") != "model_exploration"
        or decision.get("selected_option_kind") != "evolve"
        or decision.get("model_sha256") != result.get("model_sha256")
        or started.get("selected_kind") != "evolve_species"
        or started.get("state_sha256") != outcome.get("before_state_sha256")
        or started.get("menu_sha256") != decision.get("menu_sha256")
        or not isinstance(started.get("selected_binding_ref"), str)
        or not started["selected_binding_ref"]
    ):
        raise ValueError("settlement does not match the retained model evolution")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    plan_bytes = parser.parse_args().plan.read_bytes()
    plan = json.loads(plan_bytes)
    for key, ceiling in (("maximum_actions", 1000), ("maximum_frames", 120000)):
        if type(plan.get(key)) is not int or not 0 < plan[key] <= ceiling:
            raise ValueError("settlement budget exceeds its bounded scope")
    payloads = {}
    for key in (
        "rom",
        "state",
        "checkpoint",
        "profile",
        "result",
        "outcome",
        "decision",
        "started",
    ):
        payloads[key] = Path(plan[key]["path"]).read_bytes()
        if hashlib.sha256(payloads[key]).hexdigest() != plan[key]["sha256"]:
            raise ValueError("settlement input authentication failed")
    documents = {
        key: json.loads(payloads[key]) for key in ("result", "outcome", "decision", "started")
    }
    validate_source(**documents, state=payloads["state"])
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("settlement requires committed source")
    envelope = json.loads(payloads["checkpoint"])["envelope"]
    envelope.update(state_sha256=plan["state"]["sha256"], checkpoint_id=plan["run_id"])
    capture = parse_goal_manager_context_capture(
        payloads["state"],
        (json.dumps(envelope) + "\n").encode(),
    )
    profile = parse_red_goal_context_profile(payloads["profile"])
    output = Path(plan["output"])
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.evolution-battle-settlement.v1",
            "input_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "parent_state_sha256": plan["state"]["sha256"],
            "prior_outcome_sha256": plan["outcome"]["sha256"],
            "prior_binding_ref": documents["started"]["selected_binding_ref"],
            "maximum_actions": plan["maximum_actions"],
            "maximum_frames": plan["maximum_frames"],
            "model_queries": 0,
            "authority": "operator-authorized deterministic defensive escape",
        },
    )
    with PyBoyAdapter(Path(plan["rom"]["path"]), watch=False, speed=None) as emulator:
        emulator.load_state_bytes(payloads["state"])
        controller = WindowedFrameBudgetController(
            emulator,
            maximum_frames_per_window=plan["maximum_frames"],
            maximum_total_frames=plan["maximum_frames"],
        )
        reader = PokemonRedStateReader(controller)
        limiter = HardCompositionActionLimiter(
            FrameSafeExecutor(controller, DEFAULT_NEW_GAME_TIMING.controller_timing()),
            maximum_actions_per_decision=plan["maximum_actions"],
            maximum_episode_actions=plan["maximum_actions"],
        )
        actions = CountingExecutor(limiter)
        runtime = context.build_red_goal_context_runtime(
            profile=profile,
            capture=capture,
            emulator=controller,
            reader=reader,
        )

        def facts():
            observed = runtime.adapter.observe()
            collection = observed.collection_observation
            return {
                "owned_species": sorted(collection.owned_species),
                "specimen_counts": dict(Counter(s.species_ref for s in collection.specimens)),
                "cash": observed.raw.player_money,
                "bag_items": list(map(list, observed.raw.bag_items)),
                "battle_state": observed.raw.battle_state,
                "input_ready": observed.input_ready,
                "map_id": int(observed.raw.map_id),
                "party_levels": list(observed.raw.party_levels or ()),
                "party_hp": list(observed.raw.party_hp or ()),
            }

        before = facts()
        _record(output / "before.json", before)
        error = None
        try:
            if controller.pressed_buttons or before["battle_state"] != 1:
                raise ValueError("settlement requires an input-neutral wild battle")
            for key in ("owned_species", "specimen_counts", "cash", "bag_items", "map_id"):
                if before[key] != documents["outcome"]["after"][key]:
                    raise ValueError("settlement native origin differs from its receipt")
            escape_collection_battle(
                actions,
                reader,
                controller,
                recipient_species_id=None,
                policy=context.MANSION_TEAM_POLICY,
                flee_func=context._flee,
                flee_timing=context.MANSION_TRAINING_FLEE_TIMING,
            )
            after = facts()
            for key in ("owned_species", "specimen_counts", "cash", "bag_items", "map_id"):
                if after[key] != before[key]:
                    raise ValueError("settlement changed protected collection resources")
        except Exception as caught:
            error = {"type": type(caught).__name__, "message": str(caught)}
        finally:
            terminal = emulator.save_state_bytes()
            _write(output / "terminal.state", terminal)
            after = facts()
            safe = (
                not after["battle_state"]
                and after["input_ready"]
                and not controller.pressed_buttons
            )
            _record(
                output / "outcome.json",
                {
                    "before_state_sha256": plan["state"]["sha256"],
                    "terminal_state_sha256": hashlib.sha256(terminal).hexdigest(),
                    "before": before,
                    "after": after,
                    "safe_terminal": bool(safe),
                    "verification": "defensive_escape" if safe and error is None else None,
                    "error": error,
                    "actions": limiter.attempted_actions,
                    "completed_actions": actions.actions_executed,
                    "frames": controller.frames_executed,
                    "model_queries": 0,
                    "learning_eligible": False,
                },
            )
        print(json.dumps({"safe_terminal": bool(safe), "error": error, "after": after}))


if __name__ == "__main__":
    main()
