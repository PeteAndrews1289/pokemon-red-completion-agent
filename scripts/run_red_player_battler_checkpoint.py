"""One new earned-state goal through the main player's prepared trainer seam.

Development integration probe, not goal-model selection or another H/J trial.
The source and next trainer are predeclared; failures are never replayed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

from run_red_trainer_earned_switch import completion_ledger

from pokemon_red_completion.battle_runtime import DEFAULT_BATTLE_RUNTIME_TIMING
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
)
from pokemon_red_completion.field_recovery import use_field_recovery_item
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from pokemon_red_completion.gen1_trainer_sight import (
    Gen1TrainerSightProjector,
    trainer_headers,
    trainer_sight_zones,
)
from pokemon_red_completion.gen1_traversal import map_object_events
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.observation import ItemId, PokemonRedStateReader, event_flag_is_set
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_J_SHA256,
    FrozenTrainerBattler,
    load_frozen_trainer_model,
)
from pokemon_red_completion.red_resource_goal_router import _ROUTE_LIMITS
from pokemon_red_completion.red_routed_trainer_funding import _face_trainer_boundary
from pokemon_red_completion.red_trainer_funding import local_trainer_funding_candidates
from pokemon_red_completion.red_trainer_funding_battle import run_prepared_trainer_funding
from pokemon_red_completion.route_executor import execute_route
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "bcfb5c9df52a3c21527cc31df449a42dcf4fee3ebf4df6b4312768828f815f88"
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def run(args):
    source = args.state.read_bytes()
    rom = args.rom.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("earned boot3100 endpoint differs")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("cartridge differs")
    model = load_frozen_trainer_model(args.model.read_bytes(), FROZEN_J_SHA256)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit source before execution")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    args.output.mkdir(mode=0o700, exist_ok=False)
    _record(args.output / "plan.json", {
        "source_commit": commit, "source_state_sha256": SOURCE_SHA256,
        "model_sha256": FROZEN_J_SHA256, "root_lineage_id": "fresh-red-team-development-boot3100",
        "goal_kind": "resupply", "selection": "predeclared_integration_not_goal_model",
        "target_map": 61, "target_sprite": 5, "target_event": 1405,
        "maximum_frames": 160000, "maximum_actions": 2000, "maximum_battle_decisions": 80,
        "maximum_potions": 3, "maximum_wild_flees": 8, "maximum_route_steps": 100,
        "resets_after_start": 0, "teacher_battle_fallback": False, "retries": 0,
    })
    failure = None
    receipt = None
    before = None
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(source)
        session = FrameBudgetController(emulator, maximum_frames=160000)
        reader = PokemonRedStateReader(session)
        actions = CountingExecutor(HardCompositionActionLimiter(
            FrameSafeExecutor(session, DEFAULT_NEW_GAME_TIMING.controller_timing()),
            maximum_actions_per_decision=2000, maximum_episode_actions=2000,
        ))
        battler = FrozenTrainerBattler(
            session, model, args.output / "trainer-battles", commit,
            "fresh-red-team-development-boot3100", SOURCE_SHA256,
            RedPracticeCartridge(rom).public_base_stats,
        )
        try:
            before = completion_ledger(reader)
            _record(args.output / "before-ledger.json", before)
            if reader.read().map_id != 61 or event_flag_is_set(reader.read().event_flags, 1405):
                raise ValueError("new undefeated trainer boundary differs")
            # A normal-menu preparation, using existing earned stock only.
            for _ in range(3):
                raw = reader.read()
                damaged = [i for i, (hp, maximum) in enumerate(zip(
                    raw.party_hp, raw.party_max_hp, strict=True,
                )) if hp < maximum]
                if not damaged:
                    break
                use_field_recovery_item(actions, reader, session, damaged[0], ItemId.POTION)
            raw = reader.read()
            if raw.party_hp != raw.party_max_hp or any(raw.party_status):
                raise ValueError("declared recovery budget did not restore the party")
            _record(args.output / "recovered-ledger.json", completion_ledger(reader))
            observer = Gen1TraversalObserver(
                reader, Gen1TrainerSightProjector(rom, reader, full_event_offsets=True),
            )
            start = observer.observe()
            world = StrategicScenarioRouteWorld.from_rom(rom).with_current_blocks(
                reader.read_current_map_blocks(),
            )
            zones = trainer_sight_zones(
                trainer_headers(rom, {61}, full_event_offsets=True),
                map_object_events(rom, {61}), raw, reader.read_current_map_objects(),
            )
            blocked = start.occupied.union(t.at for t in zones)
            for trainer in zones:
                if trainer.active:
                    blocked = blocked.union(trainer.lane)
            blocked = blocked.union(h.at for h in start.hazards)
            candidates = local_trainer_funding_candidates(
                rom, world, replace(start, occupied=blocked),
                tuple(t for t in zones if t.sprite_index == 5), maximum_steps=100,
            )
            if len(candidates) != 1:
                raise ValueError("declared trainer has no single bounded approach")
            target = candidates[0]
            _record(args.output / "target.json", {
                "event_flag": target.trainer.event_flag, "route_steps": len(target.approach.steps),
                "payout": target.quote.expected_victory_money,
                "opponent_levels": [m.level for m in target.quote.party],
            })
            route = execute_route(
                target.approach, actions, observer, limits=_ROUTE_LIMITS,
                interruption_handler=Gen1WildFleeHandler(actions, reader, 8, 180),
            )
            if not route.passed:
                raise RuntimeError("prepared trainer approach failed")
            _face_trainer_boundary(actions, reader, target.interaction_facing.value)

            def validate():
                current = reader.read()
                actual = trainer_sight_zones(
                    trainer_headers(rom, {61}, full_event_offsets=True),
                    map_object_events(rom, {61}), current, reader.read_current_map_objects(),
                )
                match = next(t for t in actual if t.sprite_index == 5)
                if (
                    not match.visible or match.defeated or match.at != target.trainer.at
                    or match.trainer_class != target.trainer.trainer_class
                    or match.trainer_set != target.trainer.trainer_set
                    or match.event_flag != 1405
                ):
                    raise ValueError("live target differs")

            def no_teacher(_raw):
                raise AssertionError("old battle policy must never be queried")

            receipt = run_prepared_trainer_funding(
                reader, actions, target=target, validate_target=validate,
                move_slot_policy=no_teacher, timing=DEFAULT_BATTLE_RUNTIME_TIMING,
                battle_runner_override=battler.run,
            )
        except Exception as error:
            failure = {"error_type": type(error).__name__, "error": str(error)}
        finally:
            final = session.save_state_bytes()
            _write(args.output / "final.state", final)
            after = completion_ledger(reader)
            _record(args.output / "final-ledger.json", after)
            won = (
                failure is None and receipt is not None and before is not None
                and after["registered"] == before["registered"]
                and after["party_national_ids"] == before["party_national_ids"]
                and after["cash"] == before["cash"] + receipt.payout
                and after["input_ready"] and after["battle_state"] == 0
                and event_flag_is_set(reader.read().event_flags, 1405)
            )
            report = {
                "goal_kind": "resupply", "status": "succeeded" if won else "failed",
                "selection": "predeclared_integration_not_goal_model",
                "source_commit": commit, "source_state_sha256": SOURCE_SHA256,
                "final_state_sha256": hashlib.sha256(final).hexdigest(),
                "model_sha256": FROZEN_J_SHA256, "failure": failure,
                "learned_battle_calls": battler.calls, "actions": actions.actions_executed,
                "frames": session.frame_count, "final_ledger": after,
                "payout": receipt.payout if receipt is not None else None,
                "resets_after_start": 0, "fits": 0, "memory_writes": 0,
                "pressed_buttons": sorted(session.pressed_buttons),
            }
            _record(args.output / "result.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "state", "model", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
