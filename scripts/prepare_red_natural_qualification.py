"""Metered ordinary recovery, shopping and capture for natural battle qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from continue_red_natural_party import ROM_SHA, approach_trainer, bound, recover_hp
from red_natural_six_preparation import select_patrol, verify_catch
from run_red_trainer_earned_switch import completion_ledger

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerActionLimiter, CountingExecutor, FrameBudgetController, FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from pokemon_red_completion.gen1_indoor_encounters import indoor_land_encounter_mask
from pokemon_red_completion.gen1_party_menu import swap_party_slots
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from pokemon_red_completion.gen1_trainer_sight import (
    Gen1TrainerSightProjector, static_trainer_sight_zones, trainer_headers,
)
from pokemon_red_completion.gen1_traversal import map_object_events
from pokemon_red_completion.lavender import DEFAULT_LAVENDER_TIMING, _buy_mart_item, _close_menus
from pokemon_red_completion.observation import BattleMenuPhase, ItemId, PokemonRedStateReader
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG, pokemon_red_move_ref, pokemon_red_species_ref,
)
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_goal_skills import _raw_party_restored, finish_center_dialogue
from pokemon_red_completion.red_pc_storage import face_pc_boundary
from pokemon_red_completion.red_trainer_damage import ordinary_damage_upper
from pokemon_red_completion.route_executor import RouteExecutionLimits, execute_route
from pokemon_red_completion.route_plan import RoutePlanningError, plan_route
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
from pokemon_red_completion.surge import (
    DEFAULT_SURGE_TIMING, LiveWildCorridorSurveyExecutor, SurgeChapterError, _navigate_main,
    _try_catch_wild, _weaken_wild_capture_once,
)

ROOT = Path(__file__).resolve().parents[1]
MAPS = frozenset({61, 60, 59, 68, 15, 14, 2, 58, 56})


def field_executor(session):
    # Field menus need the established held-input timing, not battle's one-frame
    # pulses. Keep WAIT one frame so every caller's explicit wait stays literal.
    return FrameSafeExecutor(session, DEFAULT_NEW_GAME_TIMING.controller_timing())


def retained_uncaught_field(before, after):
    """Accept lost wild opportunity, never a reset, purchase, catch or blackout."""
    return (before.battle_state == 1 and after.battle_state == 0
        and before.map_id == after.map_id and before.player_money == after.player_money
        and before.party_species_ids == after.party_species_ids
        and before.bag_items == after.bag_items and max(after.party_hp) > 0)


def open_buy_list(actions, reader):
    # Field cursor bytes can be stale or invalid; they are not an open menu.
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
    for _ in range(8):
        menu = reader.read_menu_cursor_state()
        if (menu.top_x, menu.top_y) == (5, 4):
            return
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
    raise ValueError("ordinary Mart buy list did not open")


def safe_weakening(raw, stats):
    """Disclosed teacher: only ordinary physical single hits with a critical bound.

    Use the minimum possible wild defense; do not assume the hidden enemy DV.
    Unsupported stages/status/effects abstain, not a species-specific preference.
    """
    if (raw.battle_state != 1 or not raw.enemy_hp or not raw.enemy_max_hp
            or raw.enemy_hp * 2 <= raw.enemy_max_hp or raw.enemy_defense_stage < 7):
        return None
    base_defense = stats[raw.enemy_species_id][2]
    minimum_defense = (2 * base_defense * raw.enemy_level) // 100 + 5
    enemy_types = RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(raw.enemy_species_id)).types
    choices = []
    for i, species in enumerate(raw.party_species_ids):
        if (i == raw.active_party_index or raw.party_hp[i] * 2 < raw.party_max_hp[i]
                or raw.party_status[i]):
            continue
        own_types = RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(species)).types
        for slot, move_id in enumerate(raw.party_moves[i]):
            if not move_id or not (raw.party_pp[i][slot] & 63):
                continue
            move = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move_id))
            if (move.category != "physical" or not move.power
                    or not move.effect_flags <= {"drain"}):
                continue
            effectiveness = RED_BATTLE_CATALOG.type_effectiveness(move.type_name, enemy_types)
            # One badge's attack boost is rounded up conservatively. Only this
            # early-game no-stack preparation context is admitted by the runner.
            attack = math.ceil(raw.party_stats[i][0] * 9 / 8)
            upper = ordinary_damage_upper(level=raw.party_levels[i], power=move.power,
                attack=attack, defense=minimum_defense, critical=True,
                stab=move.type_name in own_types, effectiveness=effectiveness)
            if 0 < upper < raw.enemy_hp:
                choices.append((upper, i, slot))
    return max(choices, default=None)


class Preparation:
    def __init__(self, session, actions, reader, world, record, capture_usage=None, weakening=True):
        self.session, self.actions, self.reader, self.world, self.record = session, actions, reader, world, record
        self.observer = Gen1TraversalObserver(reader,
            hazard_projector=Gen1TrainerSightProjector(world.rom, reader, full_event_offsets=True))
        self.capture_usage = dict(capture_usage or {"encounters": 0, "patrol_attempts": 0})
        self.weakening = weakening

    def plan(self, target, at, extra=None):
        start, raw = self.observer.observe(), self.reader.read()
        zones = static_trainer_sight_zones(
            trainer_headers(self.world.rom, MAPS, full_event_offsets=True),
            map_object_events(self.world.rom, MAPS), raw.event_flags)
        blocked = {m: self.world.object_blockers[m] | frozenset(
            cell for z in zones if z.map_id == m for cell in z.lane) for m in MAPS}
        blocked[start.map_id] |= start.occupied | frozenset(h.at for h in start.hazards)
        for m, cells in (extra or {}).items():
            blocked[m] = blocked.get(m, frozenset()) | cells
        route = plan_route(self.world.macro_graph, self.world.local_graphs, start.map_id,
            start.at, target, goal_at=at, start_mode=start.mode,
            last_outside=start.last_outside_map, blocked=blocked, capabilities=start.capabilities)
        if not set(route.macro_path.maps) <= MAPS or len(route.steps) > 600:
            raise ValueError("ordinary supply route exceeds the declared region or steps")
        return route

    def travel(self, target, at):
        route = self.plan(target, at)
        self.record({"kind": "route_plan", "maps": route.macro_path.maps, "steps": len(route.steps),
                     "destination": target, "at": at})
        receipt = execute_route(route, self.actions, self.observer,
            interruption_handler=Gen1WildFleeHandler(self.actions, self.reader, maximum_flees=24,
                stabilization_frames=180, route_name="natural qualification supply"),
            replanner=lambda request: self.plan(request.goal_map, request.goal_at, request.blocked),
            limits=RouteExecutionLimits(max_interruptions=24, max_replans=8))
        self.record({"kind": "route_complete", "steps": len(receipt.executed_steps),
                     "interruptions": len(receipt.interruptions), "replans": len(receipt.replans)})

    def recover(self):
        raw = self.reader.read()
        if raw.party_hp[0] <= 0:
            best = max(range(raw.party_count), key=lambda i: (raw.party_hp[i], raw.party_levels[i]))
            swap_party_slots(self.session, self.actions, self.reader, source_index=best,
                             destination_index=0, label="ordinary living-lead recovery")
        self.travel(68, (3, 3))
        face_pc_boundary(self.actions, self.reader, "up")
        before = self.reader.read()
        for _ in range(40):
            if _raw_party_restored(self.reader.read()):
                break
            self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
            self.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
        else:
            raise ValueError("ordinary nurse did not restore every member")
        finish_center_dialogue(self.actions, self.reader)
        after = self.reader.read()
        if (before.party_species_ids != after.party_species_ids or before.bag_items != after.bag_items
                or before.player_money != after.player_money or not _raw_party_restored(after)):
            raise ValueError("Center recovery changed protected resources")
        self.record({"kind": "ordinary_center_heal", "before_hp": before.party_hp,
            "after_hp": after.party_hp, "pp_restored": True, "cash": after.player_money})

    def supply(self):
        self.travel(56, (5, 2))
        face_pc_boundary(self.actions, self.reader, "left")
        raw = self.reader.read()
        stock = dict(raw.bag_items or ()).get(4, 0)
        quantity = min(max(0, 8 - stock), raw.player_money // 200)
        if quantity <= 0:
            raise ValueError("no real-money ball purchase is available")
        open_buy_list(self.actions, self.reader)
        _buy_mart_item(self.actions, self.session, DEFAULT_LAVENDER_TIMING,
            absolute_index=0, item=4, quantity=quantity, target_bag_quantity=stock + quantity)
        _close_menus(self.actions, self.reader, DEFAULT_LAVENDER_TIMING)
        after = self.reader.read()
        expected = dict(raw.bag_items)
        expected[4] = stock + quantity
        if (dict(after.bag_items) != expected or after.player_money != raw.player_money - 200 * quantity
                or after.party_hp != raw.party_hp or after.party_species_ids != raw.party_species_ids):
            raise ValueError("ordinary shopping accounting differs")
        self.record({"kind": "ordinary_ball_purchase", "quantity": quantity, "cost": 200 * quantity,
            "cash_before": raw.player_money, "cash_after": after.player_money, "balls": stock + quantity})

    def capture(self):
        self.travel(59, None)
        raw = self.reader.read()
        mask = indoor_land_encounter_mask(self.world.rom, self.world.terrain[59])
        origin = (raw.player_y, raw.player_x)
        candidates = sorted((at for at in self.world.local_graphs[59].edges if mask[at[0]][at[1]]),
                            key=lambda at: (abs(at[0]-origin[0])+abs(at[1]-origin[1]), at))
        for at in candidates[:80]:
            try:
                route = self.plan(59, at)
                hazards = Gen1TrainerSightProjector(self.world.rom, self.reader, full_event_offsets=True)
                blocked = (self.world.object_blockers[59] | frozenset(self.world.macro_graph.warp_locations[59])
                           | frozenset(h.at for h in hazards.observe_hazards(raw)))
                direction = select_patrol(self.world.local_graphs[59], mask, at, blocked)
                break
            except (ValueError, RoutePlanningError):
                continue
        else:
            raise ValueError("no safely reachable natural encounter pair")
        self.travel(59, at)
        walker = LiveWildCorridorSurveyExecutor(self.session, self.actions, self.reader, DEFAULT_SURGE_TIMING,
            label="ordinary natural qualification capture", forward_directions=(direction,),
            starting_endpoint="south", max_legs=642)
        stats = RedPracticeCartridge(self.world.rom).public_base_stats
        for _ in range(max(0, 640 - self.capture_usage["patrol_attempts"])):
            raw = self.reader.read()
            if raw.party_count == 6:
                return
            if self.capture_usage["encounters"] >= 24 or dict(raw.bag_items or ()).get(4, 0) < 6 - raw.party_count:
                raise ValueError("natural six-member preparation exhausted actual capture resources")
            recover_hp(self.session, self.actions, self.reader, self.record)
            self.capture_usage["patrol_attempts"] += 1
            walker.seek_encounter()
            if not self.reader.read().battle_state:
                continue
            _navigate_main(self.actions, self.reader, 0)
            before = self.reader.read()
            if before.battle_state != 1:
                raise ValueError("unexpected trainer during natural capture")
            self.capture_usage["encounters"] += 1
            encounters = self.capture_usage["encounters"]
            for _ in range(4 if self.weakening else 0):
                choice = safe_weakening(self.reader.read(), stats)
                if choice is None:
                    break
                upper, member, move = choice
                self.record({"kind": "teacher_capture_weakening", "member": member + 1,
                    "move": move + 1, "critical_upper": upper, "enemy_hp": self.reader.read().enemy_hp})
                try:
                    if not _weaken_wild_capture_once(self.session, self.actions, self.reader, member, move,
                                                    "ordinary critical-bounded weakening"):
                        break
                except SurgeChapterError as exc:
                    if not retained_uncaught_field(before, self.reader.read()):
                        raise
                    self.record({"kind": "retained_uncaught_field_recovery", "encounter": encounters,
                        "error": str(exc), "hp": self.reader.read().party_hp,
                        "pp": self.reader.read().party_pp, "replay": False})
                    break
            if self.reader.read().battle_state != 1:
                self.record({"kind": "wild_encounter_ended_without_catch", "encounter": encounters})
                continue
            caught = _try_catch_wild(self.session, self.actions, self.reader, before.enemy_species_id,
                                     "ordinary six-member catch", max_throws=5)
            after = self.reader.read()
            spent = verify_catch(before, after, caught)
            self.record({"kind": "ordinary_catch", "encounter": encounters, "caught": caught,
                         "balls_spent": spent, "party_count": after.party_count, "hp": after.party_hp})
        raise ValueError("natural capture patrol step budget exhausted")


def run(args):
    state = bound(args.state, args.state_sha256)
    rom = bound(args.rom, ROM_SHA)
    prior = json.loads(bound(args.parent, args.parent_sha256)) if args.parent else None
    if prior is not None and prior["final_state_sha256"] != args.state_sha256:
        raise ValueError("retained parent and input state disagree")
    used = prior.get("preparation_cumulative", {"frames": 0, "macros": 0, "seconds": 0}) if prior else {
        "frames": 0, "macros": 0, "seconds": 0}
    capture_usage = prior.get("capture_usage") if prior else None
    if capture_usage is None and prior and prior.get("phase") == "capture":
        # Migrate the retained pre-counter failure conservatively, without
        # rewriting its receipt or granting a fresh encounter/step allowance.
        events = [json.loads(p.read_bytes()) for p in sorted(args.parent.parent.glob("event-*.json"))]
        capture_usage = {"encounters": sum(e.get("kind") in {
            "ordinary_catch", "wild_encounter_ended_without_catch"} for e in events)
            + int(prior.get("error") is not None),
            "patrol_attempts": min(640, prior["costs"]["macros"])}
    if args.output.exists() or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("preparation requires committed source and new output")
    if used["frames"] >= 600000 or used["macros"] >= 16000 or used["seconds"] >= 599:
        raise ValueError("preparation cumulative budget exhausted")
    world = StrategicScenarioRouteWorld.from_rom(rom)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    plan = {"source_commit": commit, "phase": args.phase, "root_lineage_id": args.lineage,
        "parent_sha256": args.parent_sha256, "state_sha256": args.state_sha256, "prior_cost": used,
        "maximum_frames": 600000, "maximum_macros": 16000, "maximum_seconds": 600,
        "model_queries": 0, "memory_writes": 0, "item_sales": 0}
    plan["capture_weakening_enabled"] = weakening_enabled(prior)
    _record(args.state.parent / (args.state.name + ".qualification-next-claim.json"), plan)
    _record(args.output / "plan.json", plan)
    rows = []
    def record(row):
        rows.append(row)
        _record(args.output / f"event-{len(rows):03}.json", row)
        print(json.dumps(row), flush=True)
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(state)
        session = MonotonicWallTimeBudgetController(
            FrameBudgetController(emulator, maximum_frames=600000-used["frames"]),
            maximum_wall_seconds=math.floor(600-used["seconds"]))
        limiter = ControllerActionLimiter(field_executor(session), maximum_actions=16000-used["macros"])
        actions, reader = CountingExecutor(limiter), PokemonRedStateReader(session)
        start_frames = session.frame_count
        before, error = completion_ledger(reader), None
        preparation = Preparation(session, actions, reader, world, record,
            capture_usage, plan["capture_weakening_enabled"])
        try:
            if reader.read().badge_bits != 1:
                raise ValueError("natural preparation currently admits exactly the first-badge context")
            if reader.read().battle_state != 0:
                raise ValueError("ordinary preparation requires a retained field endpoint")
            # A failed menu attempt may leave a submenu open despite field-ready
            # movement flags. Exit structurally without choosing a field action.
            for _ in range(3):
                actions.execute(MacroAction(MacroActionKind.CANCEL))
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
            if args.phase == "trainer":
                raw = reader.read()
                if raw.party_count != 6 or min(raw.party_hp) <= 0 or any(raw.party_status):
                    raise ValueError("six healthy natural members required before qualification")
                preparation.travel(59, None)
                raw = reader.read()
                strongest = late_slot_source(raw)
                if strongest != 5:
                    swap_party_slots(session, actions, reader, source_index=strongest, destination_index=5,
                                     label="natural full-party late-slot setup")
                approach_trainer(session, actions, reader, world, record)
            else:
                getattr(preparation, args.phase)()
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            for button in tuple(session.pressed_buttons):
                session.release(button)
            final = session.save_state_bytes()
            _write(args.output / "final.state", final)
            costs = {"frames": session.frame_count - start_frames, "macros": limiter.attempted_actions,
                     "seconds": session.elapsed_seconds}
            result = {**plan, "error": error, "before": before, "after": completion_ledger(reader),
                "capture_usage": preparation.capture_usage,
                "final_state_sha256": hashlib.sha256(final).hexdigest(), "costs": costs,
                "preparation_cumulative": {k: used[k]+costs[k] for k in costs},
                "held_buttons": sorted(session.pressed_buttons)}
            _record(args.output / "result.json", result)
            print(json.dumps(result), flush=True)


def late_slot_source(raw):
    """Stable ordinary setup across exact-state continuations; do not swap twice."""
    return max(range(raw.party_count), key=lambda i: (raw.party_levels[i], raw.party_max_hp[i], i))


def weakening_enabled(prior):
    """Do not keep invoking an unreliable teacher helper on its descendant."""
    if not prior:
        return True
    return bool(prior.get("capture_weakening_enabled", True) and
                "weakening" not in str((prior.get("error") or {}).get("message", "")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("state", "rom", "output"):
        parser.add_argument("--"+field, type=Path, required=True)
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--parent-sha256")
    parser.add_argument("--state-sha256", required=True)
    parser.add_argument("--lineage", required=True)
    parser.add_argument("--phase", choices=("recover", "supply", "capture", "trainer"), required=True)
    run(parser.parse_args())
