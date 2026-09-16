"""One prospectively bounded natural encounter with frozen learned attack choice."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_runtime import advance_battle_to_policy_boundary
from pokemon_red_completion.blaine import ROUTE_11_TRAINING_VENUE
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.observation import MapId, PokemonRedStateReader
from pokemon_red_completion.red_autonomous_player import _record
from pokemon_red_completion.red_collection import red_collection_observation
from pokemon_red_completion.red_learned_battle import run_learned_battle
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_team_training import swap_field_party_slots
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder

ROOT = Path(__file__).resolve().parents[1]


def _authenticated_bytes(record: dict[str, str]) -> bytes:
    payload = Path(record["path"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != record["sha256"]:
        raise ValueError("prospective input hash differs")
    return payload


def run(plan_path: Path) -> dict[str, object]:
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    if plan["schema"] != "pokemon.red.learned-encounter-plan.v1":
        raise ValueError("unsupported learned encounter plan")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit the bounded implementation before gameplay")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if revision != plan["source_commit"]:
        raise ValueError("prospective source commit differs")
    payloads = {name: _authenticated_bytes(plan[name]) for name in ("rom", "state", "model")}
    model = MaskedMLPMoveRanker.from_dict(json.loads(payloads["model"]))
    lead = plan["one_based_lead_slot"]
    if type(lead) is not int or not 1 <= lead <= 6:  # noqa: E721
        raise ValueError("invalid prospective lead")
    # Small development envelope, not a general campaign/replay command.
    for key, ceiling in (
        ("maximum_decisions", 8),
        ("maximum_encounter_walks", 128),
        ("maximum_actions", 1600),
        ("maximum_frames", 150000),
    ):
        if type(plan[key]) is not int or not 1 <= plan[key] <= ceiling:  # noqa: E721
            raise ValueError(f"invalid bounded {key}")
    output = Path(plan["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    provenance = {
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "source_commit": revision,
        **{f"{name}_sha256": plan[name]["sha256"] for name in payloads},
        "partition": "correlated_development",
        "new_training_data": False,
        "teacher_setup": {"one_based_lead_slot": lead, "venue": "route_11"},
        "training_state_edits": [],
        "maximum_encounter_walks": plan["maximum_encounter_walks"],
        "maximum_actions": plan["maximum_actions"],
        "maximum_frames": plan["maximum_frames"],
    }
    with PyBoyAdapter(Path(plan["rom"]["path"]), watch=False, speed=None) as emulator:
        emulator.load_state_bytes(payloads["state"])
        initial_frame = emulator.frame_count
        budget = FrameBudgetController(emulator, maximum_frames=plan["maximum_frames"])
        reader = PokemonRedStateReader(budget)
        limiter = HardCompositionActionLimiter(
            FrameSafeExecutor(budget, DEFAULT_NEW_GAME_TIMING.controller_timing()),
            maximum_actions_per_decision=plan["maximum_actions"],
            maximum_episode_actions=plan["maximum_actions"],
        )
        actions = CountingExecutor(limiter)

        def collection():
            return red_collection_observation(
                reader.read_pokedex_state(),
                PokemonRedPartyReader(budget).read(),
                reader.read_all_box_states(),
            )

        initial_collection = collection()

        def setup() -> None:
            raw = reader.read()
            if raw.map_id != MapId.ROUTE_11 or raw.battle_state != 0:
                raise ValueError("source is not an earned Route 11 field state")
            if not reader.read_input_readiness().ready:
                raise ValueError("source field is not input-ready")
            swap_field_party_slots(
                actions,
                reader,
                budget,
                first_index=0,
                second_index=lead - 1,
                label="declared learned encounter lead setup",
                hideout_timing=DEFAULT_HIDEOUT_TIMING,
            )
            walk = ROUTE_11_TRAINING_VENUE.fresh_walk_to_grass()
            for _ in range(plan["maximum_encounter_walks"]):
                raw = reader.read()
                if raw.battle_state:
                    break
                if raw.map_id != MapId.ROUTE_11:
                    raise ValueError("encounter setup left the declared venue")
                walk(actions, reader, budget)
            if reader.read().battle_state != 1:
                raise RuntimeError("no natural encounter inside the setup bound")
            advance_battle_to_policy_boundary(
                reader,
                actions,
                expected_map=int(MapId.ROUTE_11),
                expected_battle_state=1,
                timing=ROUTE_11_TRAINING_VENUE.battle_timing,
                label="declared learned encounter introduction",
            )

        report = run_learned_battle(
            output=output,
            reader=reader,
            executor=actions,
            encoder=PokemonRedObservationEncoder.from_state_reader(reader),
            model=model,
            snapshot=emulator.save_state_bytes,
            costs=lambda: {
                "actions": actions.actions_executed,
                "attempted_actions": limiter.attempted_actions,
                "frames": emulator.frame_count - initial_frame,
            },
            setup=setup,
            provenance=provenance,
            expected_map=int(MapId.ROUTE_11),
            maximum_decisions=plan["maximum_decisions"],
            timing=ROUTE_11_TRAINING_VENUE.battle_timing,
        )
        final_collection = collection()
        source_unchanged = _authenticated_bytes(plan["state"]) == payloads["state"]
        ledger = {
            "before_owned": sorted(initial_collection.owned_species),
            "after_owned": sorted(final_collection.owned_species),
            "before_specimens": len(initial_collection.specimens),
            "after_specimens": len(final_collection.specimens),
            "source_unchanged": source_unchanged,
            "owned_flags_preserved": initial_collection.owned_species
            <= final_collection.owned_species,
            "input_ready": reader.read_input_readiness().ready,
        }
        _record(output / "collection-verification.json", ledger)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.plan)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["stop_reason"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
