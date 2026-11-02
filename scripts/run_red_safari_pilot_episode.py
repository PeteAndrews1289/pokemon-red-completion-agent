"""Record one prospectively assigned assisted Safari episode; never auto-fit/promote."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from qualify_red_safari_training_setup import write_json

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerActionLimiter,
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel
from pokemon_red_completion.observation import MapId, PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import (
    RED_SOLO_COLLECTION_CONTRACT,
    red_collection_observation,
)
from pokemon_red_completion.red_live_safari import (
    RedSafariEntryMode,
    _live_safari_binding,
    discover_reachable_red_safari_areas,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_player_model import load_player_goal_model_record
from pokemon_red_completion.red_safari_acquisition import select_red_safari_area
from pokemon_red_completion.red_safari_pilot_learning import (
    MAX_ACTIONS,
    MAX_FRAMES,
    SCHEMA,
    SCHEMA_V2,
    pilot_menu,
    pilot_outcome,
    reward_contract,
)
from pokemon_red_completion.red_safari_training_setup import RED_ROM_SHA256
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

ROOT = Path(__file__).resolve().parents[1]


def observe(reader, controller):
    raw = reader.read()
    collection = red_collection_observation(
        reader.read_pokedex_state(), PokemonRedPartyReader(controller).read(),
        reader.read_all_box_states(),
    )
    session = reader.read_safari_session_state()
    return {
        "registered": sorted(collection.owned_species),
        "target_registered": sorted(collection.owned_species &
                                    set(RED_SOLO_COLLECTION_CONTRACT.target_species)),
        "specimens": [list(row) for row in sorted(
            Counter(s.species_ref for s in collection.specimens).items())],
        "party_species": list(raw.party_species_ids), "party_hp": list(raw.party_hp),
        "free_party_slots": 6 - raw.party_count, "money": raw.player_money,
        "map": raw.map_id, "battle": raw.battle_state,
        "ready": reader.read_input_readiness().ready and not controller.pressed_buttons,
        "balls": session.safari_balls, "steps": session.safari_steps,
    }


class ActionRecorder:
    def __init__(self, delegate, controller, stream, selection_sha256):
        self.delegate, self.controller, self.stream = delegate, controller, stream
        self.selection_sha256 = selection_sha256
        self.count = 0

    def execute(self, action):
        self.count += 1
        row = dict(ordinal=self.count, action=asdict(action),
                   before_frame=self.controller.frame_count,
                   selection_sha256=self.selection_sha256, error=None)
        try:
            return self.delegate.execute(action)
        except Exception as error:
            row["error"] = str(error)
            raise
        finally:
            row["after_frame"] = self.controller.frame_count
            self.stream.write(json.dumps(row, sort_keys=True) + "\n")
            self.stream.flush()


def run(*, rom_path, source, source_sha256, source_receipt, receipt_sha256,
        model_path, model_sha256, output, partition, seed, origin_id, schema=SCHEMA):
    contract = reward_contract(schema)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit pilot source before native dispatch")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    rom, state, receipt = rom_path.read_bytes(), source.read_bytes(), source_receipt.read_bytes()
    if (hashlib.sha256(rom).hexdigest() != RED_ROM_SHA256
            or hashlib.sha256(state).hexdigest() != source_sha256
            or hashlib.sha256(receipt).hexdigest() != receipt_sha256):
        raise ValueError("pilot source authentication failed")
    origin = json.loads(receipt)
    if (origin.get("terminal_state_sha256") != source_sha256
            or origin.get("status") not in {"recovered", "setup_qualified"}
            or origin.get("partition", origin.get("prospective_partition")) != partition
            or origin.get("model_queries") != 0):
        raise ValueError("pilot requires partition-matched unqueried setup receipt")
    if schema == SCHEMA_V2 and origin.get("context_assistance") is not True:
        raise ValueError("v2 pilot requires an explicit isolated context receipt")
    model_document = json.loads(model_path.read_bytes())
    if model_document.get("schema") == "pokemon.red.assisted-safari-pilot-candidate.v1":
        if (partition != "development" or model_document.get("promotion_eligible") is not False
                or model_document.get("model_sha256") != model_sha256):
            raise ValueError("experimental Safari candidate is evaluation-only")
        model = LivingDexOptionValueModel.from_dict(model_document["model"])
        if model.model_sha256 != model_sha256:
            raise ValueError("experimental candidate digest differs")
    else:
        model = load_player_goal_model_record(model_path, expected_model_sha256=model_sha256).model
    world = StrategicScenarioRouteWorld.from_rom(rom)
    output.mkdir(mode=0o700, exist_ok=False)
    plan = dict(schema=schema, episode_id=output.name, partition=partition,
                source_state_sha256=source_sha256, source_receipt_sha256=receipt_sha256,
                origin_id=origin_id, behavior_model_sha256=model_sha256, seed=seed,
                teacher_assistance=("isolated_native_gate_source_only" if schema == SCHEMA
                                    else "isolated_native_gate_context_only"),
                promotion_eligible=False,
                maximum_actions=MAX_ACTIONS, maximum_frames=MAX_FRAMES,
                maximum_encounters=6, maximum_search_actions=128,
                maximum_wall_seconds=180, source_commit=commit,
                reward_contract=contract)
    write_json(output / "plan.json", plan)
    result = dict(schema=schema, plan_sha256=canonical_sha256(plan), status="censored",
                  economy_label_eligible=False, model_queries=0)
    started = time.monotonic()
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(state)
        controller = MonotonicWallTimeBudgetController(
            FrameBudgetController(emulator, maximum_frames=MAX_FRAMES), maximum_wall_seconds=180)
        reader = PokemonRedStateReader(controller)
        recorder = None
        try:
            before = observe(reader, controller)
            write_json(output / "before.json", before)
            if before["map"] != MapId.SAFARI_ZONE_GATE or not before["ready"]:
                raise ValueError("pilot source is not a ready gate")
            areas = discover_reachable_red_safari_areas(
                rom, reader.read_pokedex_state().owned_species,
                free_storage_slots=before["free_party_slots"], world=world, reader=reader,
            )
            offers, steps = tuple(a.offer for a in areas), tuple(a.route_steps for a in areas)
            menu = pilot_menu(before, offers, steps)
            inference_start = time.monotonic()
            choice = select_red_safari_area(model, menu, offers, seed=seed)
            result.update(model_queries=1, inference_seconds=time.monotonic() - inference_start)
            selection = dict(choice=choice.public_dict(), menu=menu.policy_dict(),
                             offers=[asdict(o) for o in offers], route_steps=list(steps),
                             controller_actions_before_commit=0)
            write_json(output / "selection.json", selection)
            result["selection_sha256"] = canonical_sha256(selection)
            with (output / "actions.jsonl").open("x") as stream:
                recorder = ActionRecorder(
                    ControllerActionLimiter(
                        FrameSafeExecutor(controller, DEFAULT_NEW_GAME_TIMING.controller_timing()),
                        maximum_actions=MAX_ACTIONS), controller, stream,
                    result["selection_sha256"],
                )
                actions = CountingExecutor(recorder)
                selected = areas[choice.selected_candidate_index]
                binding = _live_safari_binding(
                    area=selected, mode=RedSafariEntryMode.GATE,
                    free_storage_slots=before["free_party_slots"], controller=controller,
                    actions=actions, reader=reader, world=world, maximum_encounters=6,
                    maximum_search_actions=128,
                )
                execution = binding.execute()
                result["execution"] = dict(execution.evidence)
                after = observe(reader, controller)
                pilot_outcome(before, after, actions=recorder.count, frames=controller.frame_count,
                              captures=result["execution"]["captures"], schema=schema)
                result["status"] = "settled"
        except Exception as error:
            result.update(error_type=type(error).__name__, error=str(error))
        finally:
            state = emulator.save_state_bytes()
            (output / "terminal.state").write_bytes(state)
            try:
                write_json(output / "after.json", observe(reader, controller))
            except Exception as error:
                result.update(observation_error=str(error), status="censored")
            result.update(terminal_state_sha256=hashlib.sha256(state).hexdigest(),
                          actions=0 if recorder is None else recorder.count,
                          frames=controller.frame_count, wall_seconds=time.monotonic() - started)
            write_json(output / "result.json", result)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
    write_json(output / "manifest.json", dict(schema=schema, files=files))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "source", "source-receipt", "model", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    for name in ("source-sha256", "receipt-sha256", "model-sha256", "origin-id"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--partition", choices=("train", "development"), required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--schema", choices=(SCHEMA, SCHEMA_V2), default=SCHEMA)
    a = p.parse_args()
    result = run(rom_path=a.rom, source=a.source, source_sha256=a.source_sha256,
                 source_receipt=a.source_receipt, receipt_sha256=a.receipt_sha256,
                 model_path=a.model, model_sha256=a.model_sha256, output=a.output,
                 partition=a.partition, seed=a.seed, origin_id=a.origin_id, schema=a.schema)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "settled" else 1)
