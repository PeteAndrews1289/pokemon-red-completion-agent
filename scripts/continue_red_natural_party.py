"""One no-rewind, natural-resource DEVELOPMENT continuation into frozen K.

Preparation is disclosed teacher scaffolding; every trainer decision belongs to K.
The earned party, including a smaller party when balls run out, is never fabricated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from dataclasses import asdict
from pathlib import Path

from red_natural_six_preparation import select_patrol, verify_catch
from run_red_trainer_earned_switch import completion_ledger

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2, build_battle_scenario_capture_payload, open_battle_scenario_capture,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerActionLimiter, CountingExecutor, FrameBudgetController, FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from pokemon_red_completion.field_recovery import use_field_recovery_item
from pokemon_red_completion.gen1_indoor_encounters import indoor_land_encounter_mask
from pokemon_red_completion.gen1_party_menu import swap_party_slots
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from pokemon_red_completion.gen1_trainer_sight import (
    Gen1TrainerSightProjector, trainer_headers, trainer_sight_zones,
)
from pokemon_red_completion.gen1_traversal import map_object_events
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.observation import BattleMenuPhase, ItemId, PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_routed_trainer_funding import _face_trainer_boundary
from pokemon_red_completion.red_trainer_funding import local_trainer_funding_candidates
from pokemon_red_completion.red_trainer_practice_episode import run_live_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.red_trainer_practice_outcome_policy import RedTrainerPracticeOutcomePolicy
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.route_executor import execute_route
from pokemon_red_completion.route_plan import RoutePlanningError, plan_route
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
from pokemon_red_completion.surge import (
    DEFAULT_SURGE_TIMING, LiveWildCorridorSurveyExecutor, _try_catch_wild,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "a0af2a39b75bdbbe3ed775360c790ed4cdbde06437ca3b4f3ea050d727b7363d"
MODEL_SHA = "e626e3435d1aa75654593535acf0e5e52a7eb7430481217a80aff3a53c191472"
ROM_SHA = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
LINEAGE = "fresh-red-six-development-boot3700"
CAPTURE_ID = "natural-continuation-3700-k"


def bound(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("continuation input hash differs")
    return data


def capture_capacity(raw, encounters):
    """The smaller-party fallback is fixed before any capture/model outcome."""
    if not 2 <= raw.party_count <= 6:
        raise ValueError("natural party is outside the declared continuation scope")
    return (raw.party_count < 6 and encounters < 12
            and dict(raw.bag_items or ()).get(int(ItemId.POKE_BALL), 0) >= 6 - raw.party_count
            and all(hp > 0 for hp in raw.party_hp or ())
            and not any(raw.party_status or ()))


def recover_hp(session, actions, reader, record):
    for _ in range(18):
        raw = reader.read()
        if raw.battle_state or not reader.read_input_readiness().ready:
            raise ValueError("Potion recovery needs a ready field boundary")
        target = next((i for i, (hp, maximum) in enumerate(
            zip(raw.party_hp, raw.party_max_hp, strict=True))
            if hp > 0 and (maximum - hp >= 20 or hp * 2 < maximum)), None)
        if target is None or not dict(raw.bag_items or ()).get(int(ItemId.POTION), 0):
            return
        use_field_recovery_item(actions, reader, session, target, ItemId.POTION)
        record({"kind": "ordinary_potion", "party_slot": target + 1,
                "before_hp": raw.party_hp, "after_hp": reader.read().party_hp})
    raise ValueError("ordinary potion recovery bound exhausted")


def prepare_party(session, actions, reader, world, record):
    encounters = 0

    def capture():
        nonlocal encounters
        raw = reader.read()
        if raw.battle_state != 1:
            raise ValueError("capture preparation encountered a non-wild battle")
        encounters += 1
        caught = _try_catch_wild(session, actions, reader, raw.enemy_species_id,
                                 "natural continuation", max_throws=5)
        after = reader.read()
        spent = verify_catch(raw, after, caught)
        record({"kind": "wild_capture", "encounter": encounters,
                "enemy_species": raw.enemy_species_id, "caught": caught,
                "balls_spent": spent, "party_count": after.party_count,
                "party_hp": after.party_hp, "cash": after.player_money,
                "method": "ordinary_ball_only_no_stat_edits"})
        recover_hp(session, actions, reader, record)

    if reader.read().battle_state == 1:
        capture()
    raw = reader.read()
    if raw.battle_state or not reader.read_input_readiness().ready:
        raise ValueError("retained wild encounter did not restore field control")
    if capture_capacity(raw, encounters):
        map_id = raw.map_id
        hazards = Gen1TrainerSightProjector(world.rom, reader, full_event_offsets=True)
        blocked = (world.object_blockers[map_id] | reader.read_current_object_coordinates()
                   | frozenset(world.macro_graph.warp_locations.get(map_id, ()))
                   | frozenset(h.at for h in hazards.observe_hazards(raw)))
        direction = select_patrol(world.local_graphs[map_id],
            indoor_land_encounter_mask(world.rom, world.terrain[map_id]),
            (raw.player_y, raw.player_x), blocked)
        walker = LiveWildCorridorSurveyExecutor(session, actions, reader, DEFAULT_SURGE_TIMING,
            label="natural continuation patrol", forward_directions=(direction,),
            starting_endpoint="south", max_legs=322)
        for _ in range(320):
            if not capture_capacity(reader.read(), encounters):
                break
            walker.seek_encounter()
            if reader.read().battle_state:
                capture()
        # No rewind or unnecessary return trip: routing starts at actual endpoint.
    recover_hp(session, actions, reader, record)
    raw = reader.read()
    if raw.battle_state or raw.party_count < 2 or not raw.party_hp or max(raw.party_hp) <= 0:
        raise ValueError("earned party cannot enter the declared model diagnostic")
    if raw.party_hp[0] <= 0 or raw.party_hp[-1] <= 0 or any(raw.party_status or ()):
        raise ValueError("party needs recovery outside the held-Potion protocol")
    swap_party_slots(session, actions, reader, source_index=0,
                     destination_index=raw.party_count - 1, label="earned late-slot model test")
    return {"party_count": raw.party_count, "six_members": raw.party_count == 6,
            "encounters": encounters, "ordinary_slot_swap": [1, raw.party_count]}


class WalkingOnlyWorld:
    """Constrain candidate construction, not just its post-hoc validation."""

    def __init__(self, world):
        self.world = world

    def plan_feasible_to_map(self, start, goal_map, *, goal_at):
        if start.map_id != goal_map or start.mode != "land":
            raise RoutePlanningError("natural trainer approach is local land walking only")
        graph = LocalGraph({at: tuple(edge for edge in edges
            if edge.kind == "walk" and not edge.requirements and edge.transient is None
            and edge.action_kind is MacroActionKind.MOVE
            and edge.required_mode in (None, "land") and edge.result_mode in (None, "land"))
            for at, edges in self.world.local_graphs[start.map_id].edges.items()})
        blocked = (start.occupied | self.world.object_blockers[start.map_id]
                   | (frozenset(self.world.macro_graph.warp_locations.get(start.map_id, ()))
                      - {start.at}))
        return plan_route(MacroGraph({start.map_id: ()}), {start.map_id: graph},
            start.map_id, start.at, goal_map, goal_at=goal_at, start_mode="land",
            blocked={start.map_id: blocked})


def approach_trainer(session, actions, reader, world, record):
    observer = Gen1TraversalObserver(reader,
        hazard_projector=Gen1TrainerSightProjector(world.rom, reader, full_event_offsets=True))
    raw = reader.read()
    zones = trainer_sight_zones(trainer_headers(world.rom, {raw.map_id}, full_event_offsets=True),
        map_object_events(world.rom, {raw.map_id}), raw, reader.read_current_map_objects())
    candidates = local_trainer_funding_candidates(world.rom, WalkingOnlyWorld(world), observer.observe(), zones,
                                                  maximum_steps=128)
    if not candidates:
        raise ValueError("no ordinary trainer reachable through the declared safe walking scope")
    target = min(candidates, key=lambda c: (len(c.approach.steps), c.trainer.sprite_index))
    record({"kind": "trainer_selected_before_queries", "trainer": asdict(target.trainer),
            "walk_steps": len(target.approach.steps), "quote": asdict(target.quote)})
    route = execute_route(target.approach, actions, observer,
        interruption_handler=Gen1WildFleeHandler(actions, reader, maximum_flees=8,
            stabilization_frames=180, route_name="natural frozen-K approach"))
    record({"kind": "trainer_approach", "passed": route.passed,
            "executed_steps": len(route.executed_steps), "interruptions": len(route.interruptions),
            "terminal_map": route.terminal.map_id, "terminal_at": route.terminal.at})
    _face_trainer_boundary(actions, reader, target.interaction_facing.value)
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    for _ in range(45):
        raw = reader.read()
        if raw.battle_state == 2 and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN:
            break
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
    else:
        raise ValueError("selected trainer did not reach a model-ready battle")
    if reader.read_active_trainer_identity() != (
        target.trainer.trainer_class, target.trainer.trainer_class - 200, target.trainer.trainer_set
    ):
        raise ValueError("engaged trainer differs from the preselected identity")
    return target


def continuation_parent(args):
    """Only a retained, pre-model descendant can resume this preparation runner."""
    parent = None
    source_sha = SOURCE_SHA
    used = {"frames": 0, "macros": 0, "seconds": 0, "stage": 0}
    if args.parent_result is not None:
        parent = json.loads(bound(args.parent_result, args.parent_result_sha256))
        if (args.state.resolve() != (args.parent_result.parent / "final.state").resolve()
                or parent.get("root_source_sha256", parent.get("source_sha256")) != SOURCE_SHA
                or parent["model_sha256"] != MODEL_SHA or parent["battle"] is not None
                or (args.parent_result.parent / "events").exists()
                or parent["pressed_buttons"] or parent["memory_writes"] or parent["fits"]):
            raise ValueError("parent is not an unused retained preparation descendant")
        source_sha = parent["final_state_sha256"]
        used = parent.get("cumulative", {"frames": parent["frames"],
            "macros": parent["macros_attempted"], "seconds": parent["elapsed_seconds"], "stage": 1})
        if (used["stage"] >= 4 or used["frames"] >= 500000 or used["macros"] >= 20000
                or used["seconds"] >= 899):
            raise ValueError("continuation chain exhausted its aggregate budget")
    elif args.parent_result_sha256 is not None:
        raise ValueError("parent hash has no result")
    return source_sha, used


def run(args):
    source_sha, used = continuation_parent(args)
    state, rom, model_bytes = (bound(args.state, source_sha), bound(args.rom, ROM_SHA),
                               bound(args.model, MODEL_SHA))
    if args.output.exists() or args.claim.exists():
        raise ValueError("this continuation is already claimed")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("continuation requires committed executable source")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    world = StrategicScenarioRouteWorld.from_rom(rom)
    stats = RedPracticeCartridge(rom).public_base_stats
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(model_bytes))
    args.output.mkdir(mode=0o700)
    plan = {"source_commit": commit, "source_sha256": source_sha, "model_sha256": MODEL_SHA,
            "root_source_sha256": SOURCE_SHA, "prior_cost": used,
            "parent_result_sha256": args.parent_result_sha256,
            "resume_trainer_identity": args.resume_trainer_identity,
            "root_lineage_id": LINEAGE, "partition": "DEVELOPMENT", "maximum_frames": 500000,
            "maximum_macros": 20000, "maximum_seconds": 900, "maximum_encounters": 12,
            "maximum_patrol_steps": 320, "ball_method": "direct_throws_no_weakening",
            "fallback": "one natural trainer with the actually earned party, minimum two",
            "maximum_battle_decisions": 160, "maximum_battle_frames": 240000,
            "maximum_battle_macros": 5000, "maximum_battle_seconds": 45,
            "initial_loads": 1, "rewinds": 0, "fits": 0, "memory_writes": 0}
    if args.parent_result is not None:
        _record(args.parent_result.parent / "continuation-claimed.json", plan)
    _record(args.claim, plan)
    _record(args.output / "plan.json", plan)
    events = []

    def record(row):
        events.append(row)
        _record(args.output / f"preparation-{len(events):03}.json", row)
        print(json.dumps(row, default=str), flush=True)

    error = None
    episode = None
    log = None
    battle_actions = None
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(state)
        framed = FrameBudgetController(emulator, maximum_frames=500000 - used["frames"])
        session = MonotonicWallTimeBudgetController(framed,
            maximum_wall_seconds=math.floor(900 - used["seconds"]))
        limiter = ControllerActionLimiter(FrameSafeExecutor(session,
            DEFAULT_NEW_GAME_TIMING.controller_timing()), maximum_actions=20000 - used["macros"])
        actions = CountingExecutor(limiter)
        reader = PokemonRedStateReader(session)
        start_frames = session.frame_count
        before = completion_ledger(reader)
        _record(args.output / "before-ledger.json", before)
        try:
            if args.resume_trainer_identity is not None:
                if (args.parent_result is None or reader.read().battle_state != 2
                        or reader.read_battle_menu_state(reader.read()).phase is not BattleMenuPhase.MAIN
                        or reader.read_active_trainer_identity() != tuple(args.resume_trainer_identity)):
                    raise ValueError("pre-query trainer resumption boundary differs")
                record({"kind": "resume_exact_prequery_trainer_boundary",
                        "identity": args.resume_trainer_identity})
            else:
                preparation = prepare_party(session, actions, reader, world, record)
                _record(args.output / "prepared-party.json", preparation)
                approach_trainer(session, actions, reader, world, record)
            raw = reader.read()
            encoder = PokemonRedObservationEncoder.from_state_reader(reader,
                include_battle_stats=True, public_species_base_stats=stats)
            prepared = prepare_red_battle_scenario(encoder, raw, allow_no_attack=True)
            captured = session.save_state_bytes()
            manifest = build_battle_scenario_capture_payload(
                capture_id=CAPTURE_ID, root_lineage_id=LINEAGE,
                partition=ScenarioPartition.DEVELOPMENT, state_bytes=captured,
                source_state_sha256=source_sha,
                initial_observation_sha256=prepared.initial_observation_sha256,
                source_commit=commit, expected_map=raw.map_id, expected_battle_state=2,
                observation_schema=OBSERVATION_SCHEMA_V2)
            _write(args.output / "battle.state", captured)
            _write(args.output / "battle.state.json", manifest)
            capture = open_battle_scenario_capture(args.output / "battle.state",
                                                   args.output / "battle.state.json")
            log = TrainerPracticeEventLog(args.output / "events", run_identity={
                "source_commit": commit, "capture_manifest_sha256": capture.manifest_sha256,
                "model_sha256": MODEL_SHA, "parent_state_sha256": source_sha,
                "live_without_reset": True})
            battle_session = MonotonicWallTimeBudgetController(
                FrameBudgetController(session, maximum_frames=240000), maximum_wall_seconds=45)
            # Preparation cannot use any of the battle's reserved macro allowance.
            # Settlement below is admitted against the remaining aggregate allowance.
            battle_actions = ControllerActionLimiter(FrameSafeExecutor(battle_session),
                maximum_actions=min(5000, 20000 - used["macros"] - limiter.attempted_actions),
                admit_action=battle_session.check_wall_time_budget)
            episode = run_live_red_trainer_practice_episode(capture, session=battle_session,
                policy=RedTrainerPracticeOutcomePolicy(policy_id="frozen-K-natural-continuation",
                    battle_plan_id=capture.manifest.capture_id, model=model),
                max_decisions=160, event_sink=log.emit, public_species_base_stats=stats,
                action_executor=battle_actions,
                decision_guard=lambda _: battle_session.check_wall_time_budget())
            report = episode.public_dict()
            _record(args.output / "battle-outcome.json", report)
            _write(args.output / "battle-final.state", session.save_state_bytes())
            log.finish({"outcome_sha256": canonical_sha256(report)})
            # Bounded dialogue cleanup, not a substitute battle action or new encounter.
            if episode.battle_won:
                for _ in range(30):
                    if reader.read().battle_state == 0 and reader.read_input_readiness().ready:
                        break
                    if used["macros"] + limiter.attempted_actions + battle_actions.attempted_actions + 2 > 20000:
                        raise RuntimeError("aggregate continuation macro budget exhausted")
                    actions.execute(MacroAction(MacroActionKind.CANCEL))
                    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            if log is not None and not log.closed:
                log.fail(exc)
        finally:
            for button in tuple(session.pressed_buttons):
                session.release(button)
            final = session.save_state_bytes()
            _write(args.output / "final.state", final)
            result = {"error": error, "source_commit": commit, "source_sha256": source_sha,
                "root_source_sha256": SOURCE_SHA, "parent_result_sha256": args.parent_result_sha256,
                "final_state_sha256": hashlib.sha256(final).hexdigest(), "before": before,
                "after": completion_ledger(reader), "pressed_buttons": sorted(session.pressed_buttons),
                "frames": session.frame_count - start_frames,
                "macros_attempted": limiter.attempted_actions + (
                    battle_actions.attempted_actions if battle_actions else 0),
                "macros_completed": limiter.completed_actions + (
                    battle_actions.completed_actions if battle_actions else 0),
                "elapsed_seconds": session.elapsed_seconds, "model_sha256": MODEL_SHA,
                "battle": episode.public_dict() if episode else None,
                "fits": 0, "memory_writes": 0, "main_save_changed": False}
            result["cumulative"] = {"frames": used["frames"] + result["frames"],
                "macros": used["macros"] + result["macros_attempted"],
                "seconds": used["seconds"] + result["elapsed_seconds"], "stage": used["stage"] + 1}
            _record(args.output / "result.json", result)
            print(json.dumps({key: value for key, value in result.items() if key != "battle"}
                | {"battle_summary": ({key: report[key] for key in
                    ("battle_won", "stop_reason", "decision_count", "action_counts", "metrics")}
                    if episode else None)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "rom", "model", "output", "claim"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--parent-result", type=Path)
    parser.add_argument("--parent-result-sha256")
    parser.add_argument("--resume-trainer-identity", nargs=3, type=int)
    run(parser.parse_args())
