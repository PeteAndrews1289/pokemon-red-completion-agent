"""Two bounded new encounters from earned natural saves, with in-place J authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_natural_team import MODEL_SHA

from pokemon_red_completion import cerulean as field
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
)
from pokemon_red_completion.gen1_party_menu import (
    promote_sole_living_party_member,
    swap_party_slots,
)
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
    game_mode,
    semantic_facts,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_collection import red_internal_species_number
from pokemon_red_completion.red_trainer_practice_episode import (
    run_live_red_trainer_practice_episode,
)
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.referee import CompletionReferee
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
BOOTS = (2900, 3100)
MAX_FRAMES = 160000


def authenticated_endpoint(directory: Path):
    report = json.loads((directory / "outcome.json").read_bytes())
    endpoint = json.loads((directory / "final-state.json").read_bytes())
    state = (directory / "final.state").read_bytes()
    verification = verify_trainer_practice_event_log(directory / "events")
    events = sorted((directory / "events").glob("event-*.json"))
    identity = json.loads(events[0].read_bytes())["payload"]["identity"]
    terminal = json.loads(events[-1].read_bytes())["payload"]["outcome"]
    if (
        verification["terminal_event"] != "run_finished"
        or verification["incomplete_decisions"] != 0
        or report["stop_reason"] != "battle_won"
        or not report["battle_won"]
        or report["outcome_model_sha256"] != MODEL_SHA["J"]
        or identity["outcome_model_sha256"] != MODEL_SHA["J"]
        or identity["capture_manifest_sha256"] != report["manifest_sha256"]
        or terminal["outcome_sha256"] != canonical_sha256(report)
        or endpoint["episode_returned"] is not True
        or endpoint["pressed_buttons"]
        or hashlib.sha256(state).hexdigest() != endpoint["state_sha256"]
        or endpoint["state_sha256"] != report["final_state_sha256"]
        or canonical_sha256(endpoint) != report["final_state_receipt_sha256"]
        or report["teacher_queries"] != 0
        or report["memory_write_actions"] != 0
    ):
        raise ValueError("earned endpoint authentication differs")
    return state, report


def completion_ledger(reader):
    """Fresh read-only facts, separate from the actor's battle inputs."""
    raw = reader.read()
    story = reader.read_cerulean_chapter_state(raw)
    completion = CompletionReferee().inspect(
        GameState(mode=game_mode(raw), facts=semantic_facts(raw))
    )
    return {
        "registered": sorted(reader.read_pokedex_state().owned_species),
        "party_national_ids": [red_internal_species_number(s) for s in raw.party_species_ids or ()],
        "party_hp": list(raw.party_hp or ()),
        "party_levels": list(raw.party_levels or ()),
        "battle_state": raw.battle_state,
        "input_ready": reader.read_input_readiness().ready,
        "cash": raw.player_money,
        "required_trainer_defeated": story.beat_required_rocket,
        "next_trainer_defeated": story.beat_super_nerd,
        "champion_event": completion.champion_event,
        "hall_of_fame_fact": completion.hall_of_fame_fact,
        "hall_of_fame_mode": completion.hall_of_fame_mode,
        "full_game_complete": completion.complete,
    }


def verify_story_outcome(before, after, episode):
    preserved = set(before["registered"]) <= set(after["registered"]) and Counter(
        before["party_national_ids"]
    ) == Counter(after["party_national_ids"])
    won = (
        episode is not None
        and episode.battle_won
        and not before["next_trainer_defeated"]
        and after["next_trainer_defeated"]
        and after["battle_state"] == 0
        and preserved
    )
    return {
        "goal_kind": GoalKind.ADVANCE_STORY.value,
        "selection_mode": "predeclared_development_objective_not_goal_model_selection",
        "status": GoalDecisionOutcome.SUCCEEDED.value if won else GoalDecisionOutcome.FAILED.value,
        "registrations_and_party_preserved": preserved,
        "outcome_verified_from_fresh_ledger": True,
    }


def has_actual_switch(episode):
    return any(
        d["kind"] in {"voluntary_switch", "forced_switch"}
        or (d["kind"] == "switch_prompt" and d.get("party_slot") is not None)
        for d in episode.decisions
    )


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("earned probe needs new output and committed source")
    if common._binding(args.rom)["sha256"] != common.ROM_SHA256:
        raise ValueError("ROM differs")
    if common._binding(args.model)["sha256"] != MODEL_SHA["J"]:
        raise ValueError("frozen J differs")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.model.read_bytes()))
    stats = RedPracticeCartridge(args.rom.read_bytes()).public_base_stats
    parents = [authenticated_endpoint(args.parents / f"boot{boot}-timing0-J") for boot in BOOTS]
    for boot, (_, report) in zip(BOOTS, parents, strict=True):
        if report["root_lineage_id"] != f"fresh-red-team-development-boot{boot}":
            raise ValueError("earned source lineage differs")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    _record(
        args.output / "plan.json",
        {
            "source_commit": commit,
            "model": common._binding(args.model),
            "parents": [
                common._binding(args.parents / f"boot{b}-timing0-J/outcome.json") for b in BOOTS
            ],
            "max_frames": MAX_FRAMES,
            "max_decisions": 80,
            "initial_loads_per_source": 1,
            "battle_resets": 0,
            "fits": 0,
        },
    )
    rows = []
    integrated = False
    for boot, (state, parent) in zip(BOOTS, parents, strict=True):
        directory = args.output / f"boot{boot}"
        directory.mkdir(mode=0o700)
        episode = None
        failure = None
        before = None
        log = None
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(state)
            session = FrameBudgetController(emulator, maximum_frames=MAX_FRAMES)
            reader = PokemonRedStateReader(session)
            actions = CountingExecutor(
                FrameSafeExecutor(session, DEFAULT_NEW_GAME_TIMING.controller_timing())
            )
            encoder = PokemonRedObservationEncoder.from_state_reader(
                reader, include_battle_stats=True, public_species_base_stats=stats
            )
            try:
                if (
                    canonical_sha256(encoder.snapshot().to_dict())
                    != parent["final_observation_sha256"]
                ):
                    raise ValueError("loaded earned state observation differs")
                before = completion_ledger(reader)
                _record(directory / "before-ledger.json", before)
                if before["next_trainer_defeated"] or not before["required_trainer_defeated"]:
                    raise ValueError("earned source is not before the new trainer")
                timing = field.DEFAULT_CERULEAN_TIMING
                for _ in range(timing.rocket_cleanup_pulses):
                    actions.execute(MacroAction(MacroActionKind.CANCEL))
                    actions.execute(
                        MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_wait_frames)
                    )
                field._move_mt_moon(
                    actions,
                    reader,
                    field.ROCKET_TO_SUPER_NERD_DIRECTIONS[:-1],
                    "earned new trainer approach",
                    expected_map_id=MapId.MT_MOON_B2F,
                    ledger=field._MtMoonTraversalLedger(),
                )
                swap_party_slots(
                    session,
                    actions,
                    reader,
                    source_index=1,
                    destination_index=0,
                    label="declared weaker-lead transfer setup",
                )
                field._trigger_trainer_through_wild_encounters(
                    actions,
                    reader,
                    timing,
                    direction=field.ROCKET_TO_SUPER_NERD_DIRECTIONS[-1],
                    origin=field.SUPER_NERD_TRIGGER_ORIGIN,
                    destination=field.SUPER_NERD_TRIGGER_DESTINATION,
                    expected_map=MapId.MT_MOON_B2F,
                    label="new earned-state trainer",
                )
                for _ in range(45):
                    raw = reader.read()
                    if (
                        raw.battle_state == 2
                        and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
                    ):
                        break
                    actions.execute(MacroAction(MacroActionKind.CONFIRM))
                    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
                else:
                    raise ValueError("new trainer did not reach MAIN")
                prepared = prepare_red_battle_scenario(encoder, raw, allow_no_attack=True)
                captured = session.save_state_bytes()
                manifest = build_battle_scenario_capture_payload(
                    capture_id=f"earned-natural-switch-boot{boot}",
                    root_lineage_id=parent["root_lineage_id"],
                    partition=ScenarioPartition.DEVELOPMENT,
                    state_bytes=captured,
                    source_state_sha256=hashlib.sha256(state).hexdigest(),
                    initial_observation_sha256=prepared.initial_observation_sha256,
                    source_commit=commit,
                    expected_map=int(MapId.MT_MOON_B2F),
                    expected_battle_state=2,
                    observation_schema=OBSERVATION_SCHEMA_V2,
                )
                _write(directory / "battle.state", captured)
                _write(directory / "battle.state.json", manifest)
                capture = open_battle_scenario_capture(
                    directory / "battle.state", directory / "battle.state.json"
                )
                log = TrainerPracticeEventLog(
                    directory / "events",
                    run_identity={
                        "source_commit": commit,
                        "capture_manifest_sha256": capture.manifest_sha256,
                        "model_sha256": MODEL_SHA["J"],
                        "parent_state_sha256": parent["final_state_sha256"],
                        "live_without_reset": True,
                    },
                )
                policy = RedTrainerPracticeOutcomePolicy(
                    policy_id="frozen-J-live-earned-trainer",
                    battle_plan_id=capture.manifest.capture_id,
                    model=model,
                )
                episode = run_live_red_trainer_practice_episode(
                    capture,
                    session=session,
                    policy=policy,
                    max_decisions=80,
                    event_sink=log.emit,
                    public_species_base_stats=stats,
                )
                battle_report = episode.public_dict()
                _record(directory / "battle-outcome.json", battle_report)
                _write(directory / "battle-final.state", session.save_state_bytes())
                log.finish({"outcome_sha256": canonical_sha256(battle_report)})
                if not integrated and episode.battle_won and has_actual_switch(episode):
                    raw = reader.read()
                    if raw.first_party_hp == 0:
                        promote_sole_living_party_member(
                            session, actions, reader, label="post-battle sole-survivor control"
                        )
                    field._settle_super_nerd_field_control(actions, reader, timing)
                    integrated = True
            except Exception as error:
                failure = {"error_type": type(error).__name__, "error": str(error)}
                if log is not None and not log.closed:
                    log.fail(error)
            finally:
                final_bytes = session.save_state_bytes()
                _write(directory / "final.state", final_bytes)
                try:
                    after = completion_ledger(reader)
                    _record(directory / "final-ledger.json", after)
                    outcome = verify_story_outcome(before, after, episode) if before else None
                except Exception as error:
                    after = None
                    outcome = None
                    failure = {
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "phase": "final_ledger",
                        "preceding_failure": failure,
                    }
                report = {
                    "boot": boot,
                    "model_sha256": MODEL_SHA["J"],
                    "parent_state_sha256": parent["final_state_sha256"],
                    "final_state_sha256": hashlib.sha256(final_bytes).hexdigest(),
                    "battle": episode.public_dict() if episode else None,
                    "actual_switch": has_actual_switch(episode) if episode else False,
                    "goal_outcome": outcome,
                    "final_ledger": after,
                    "failure": failure,
                    "field_actions": actions.actions_executed,
                    "total_frames": session.frame_count,
                    "initial_loads": 1,
                    "battle_resets": 0,
                    "memory_writes": 0,
                    "pressed_buttons": sorted(session.pressed_buttons),
                }
                _record(directory / "result.json", report)
                if log is not None:
                    _record(
                        directory / "log-verification.json",
                        verify_trainer_practice_event_log(log.directory),
                    )
                rows.append(report)
                print(
                    json.dumps(
                        {
                            k: report[k]
                            for k in (
                                "boot",
                                "actual_switch",
                                "goal_outcome",
                                "failure",
                                "total_frames",
                            )
                        }
                    ),
                    flush=True,
                )
    qualified = all(
        r["actual_switch"]
        and r["failure"] is None
        and not r["pressed_buttons"]
        and r["battle"]["stop_reason"] in {"battle_won", "party_defeated"}
        and r["goal_outcome"] is not None
        for r in rows
    ) and any(r["goal_outcome"]["status"] == "succeeded" for r in rows)
    result = {
        "small_party_probe_passed": qualified,
        "live_field_handoff_passed": qualified and integrated,
        "same_two_natural_origins": True,
        "new_independent_roots": 0,
        "fits": 0,
        "full_player_promotion": False,
        "episodes": rows,
    }
    _record(args.output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "model", "parents", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
