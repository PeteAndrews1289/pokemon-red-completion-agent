#!/usr/bin/env python3
"""One separately logged escape-and-heal from an authenticated failed Red state.

This does not run the failed goal, query a policy, fit a model or rewrite the
failed episode. The terminal is support-only, with exact predecessor costs.
"""

from __future__ import annotations

import argparse
import base64
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import run_paired_red_bounded_player as base

from pokemon_red_completion.blaine import MANSION_TEAM_POLICY, MANSION_TRAINING_FLEE_TIMING
from pokemon_red_completion.celadon import _flee
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalDecisionOutcome
from pokemon_red_completion.red_capture_preparation import prepare_capture_escort
from pokemon_red_completion.red_failure_recovery import (
    RedFailureRecoveryResult,
    authenticated_failure_state,
)
from pokemon_red_completion.red_goal_context_profile import (
    _canonical_line,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_skills import _raw_party_restored
from pokemon_red_completion.red_player_checkpoint import (
    capture_red_failure_state,
    capture_red_player_terminal,
    publish_red_player_checkpoint,
)
from pokemon_red_completion.red_regional_goal_proposal import (
    REGIONAL_PROPOSAL_KIND,
    regional_proposal_record_id,
)
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter
from pokemon_red_completion.red_routed_recovery import bind_routed_center_recovery
from pokemon_red_completion.red_team_training import (
    collection_escape_escort,
    escape_collection_battle,
)


def restored_proposal_profile(document):
    profile = parse_red_goal_context_profile(_canonical_line(document["profile"]))
    if profile.profile_sha256 != document["profile_sha256"]:
        raise ValueError("failed proposal profile identity differs")
    return profile


def prepare(args):
    declaration = json.loads(args.parent_arguments.read_text())
    original = list(declaration["args"])
    original[original.index("--pair-id") + 1] = args.episode_id
    original[original.index("--out") + 1] = str(args.out)
    ready = base._prepare(base._parser().parse_args(original))
    if ready.context_origin != "training" or ready.continuation is None:
        raise ValueError("recovery requires an authenticated training predecessor")
    # A native regional attempt may have changed profile before the failed
    # choice. Read its existing proposal; never select a destination again.
    failed_id = args.failed_episode
    proposal = None
    for _ in range(8):
        proposal = ready.private_root.find_sealed_record(
            regional_proposal_record_id(failed_id),
            expected_kind=REGIONAL_PROPOSAL_KIND,
        )
        if proposal is not None:
            break
        metadata = ready.private_root.open_failed_episode(failed_id).read_header()["metadata"]
        if metadata.get("schema") != "pokemon.red.forced-recovery-header.v1":
            break
        failed_id = metadata["recovery"]["failure_episode_id"]
    if proposal is not None:
        document = proposal.read()
        profile = restored_proposal_profile(document)
        ready = replace(ready, profile=profile)
    state = authenticated_failure_state(
        ready.private_root,
        episode_id=args.failed_episode,
        manifest_sha256=args.failed_manifest,
        state_sha256=args.failed_state,
        parent_state_sha256=ready.capture.state_sha256,
        parent_envelope_sha256=ready.capture.envelope_sha256,
        profile_sha256=ready.profile.profile_sha256,
        rom_sha256=ready.rom_sha256,
    )
    return ready, state


def run(args):
    ready, failed = prepare(args)
    payload = base64.urlsafe_b64decode(failed["state_base64"])
    world = base._route_world(ready)
    if world is None:
        raise ValueError("recovery requires cartridge-derived routes")
    writer = sink = recorder = None
    finalized = False
    with base.PyBoyAdapter(ready.rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(payload)
        if emulator.save_state_bytes() != payload or emulator.pressed_buttons:
            raise ValueError("exact failed state roundtrip differs")
        reader = base.PokemonRedStateReader(base.ReadOnlyController(emulator))
        runtime = base.build_red_goal_context_runtime(
            profile=ready.profile,
            capture=ready.capture,
            emulator=base.ReadOnlyController(emulator),
            reader=reader,
        )
        before = runtime.adapter.observe()
        if before.party.fainted_count or not (
            before.raw.battle_state == 1
            or (
                before.raw.battle_state == 0
                and before.input_ready
                and not _raw_party_restored(before.raw)
            )
        ):
            raise ValueError("recovery entry is neither a preserved wild battle nor a needy field")
        recipient = before.party.lead.species_id
        escort = collection_escape_escort(
            before.party,
            recipient,
            MANSION_TEAM_POLICY,
            enemy_level=before.raw.enemy_level,
            enemy_species=before.raw.enemy_species_id,
        )
        if escort is None and before.raw.battle_state == 1:
            raise ValueError("failed battle has no qualified defensive escape escort")
        preflight = {
            "source_commit": ready.source_commit,
            "source_bundle_sha256": ready.source_bundle_sha256,
            "episode_id": args.episode_id,
            "failure_episode_id": args.failed_episode,
            "failure_manifest_sha256": args.failed_manifest,
            "failure_state_sha256": args.failed_state,
            "profile_sha256": ready.profile.profile_sha256,
            "model_sha256": ready.model_sha256,
            "escape_escort_species": escort.species_id if escort is not None else None,
            "maximum_actions": 6000,
            "maximum_frames": 600000,
            "model_queries": 0,
            "training_examples": 0,
            "original_choice_retried": False,
        }
        if not args.execute:
            base._write_exclusive(args.out, {**preflight, "status": "ready_read_only"})
            return
        try:
            writer = ready.private_root.begin_episode(args.episode_id)
            sink = base.EpisodeTrajectorySink(
                writer,
                episode_id=args.episode_id,
                game_id=base.GAME_ID,
                durable_writes=True,
            )
            sink.write_episode_header(
                metadata={
                    **base._context_scope(ready),
                    **base._continuation_header(ready),
                    "schema": "pokemon.red.forced-recovery-header.v1",
                    "source_commit": ready.source_commit,
                    "source_bundle_sha256": ready.source_bundle_sha256,
                    "state_sha256": ready.capture.state_sha256,
                    "envelope_sha256": ready.capture.envelope_sha256,
                    "profile_sha256": ready.profile.profile_sha256,
                    "rom_sha256": ready.rom_sha256,
                    "model_sha256": ready.model_sha256,
                    "context_origin": "training",
                    "training_eligible": False,
                    "completion_dose": ready.completion_dose,
                    "routed_recovery": ready.routed_recovery,
                    "remaining_acquisition_demand": ready.remaining_acquisition_demand,
                    "level_evolution_acquisitions": ready.level_evolution_acquisitions,
                    "recovery": preflight,
                }
            )
            frames = base.WindowedFrameBudgetController(
                emulator,
                maximum_frames_per_window=600000,
                maximum_total_frames=600000,
            )
            reader = base.PokemonRedStateReader(frames)
            runtime = base.build_red_goal_context_runtime(
                profile=ready.profile,
                capture=ready.capture,
                emulator=frames,
                reader=reader,
            )
            recorder = base.RecordingExecutor(
                delegate=base.FrameSafeExecutor(
                    frames, base.DEFAULT_NEW_GAME_TIMING.controller_timing()
                ),
                snapshot_provider=base.PokemonRedObservationEncoder.from_state_reader(reader),
                sink=sink,
                episode_id=args.episode_id,
            )
            hard = base.HardCompositionActionLimiter(
                recorder,
                maximum_actions_per_decision=6000,
                maximum_episode_actions=6000,
            )
            actions = base.CountingExecutor(hard)
            meter = base.CompositionIndependentBudgetMeter(hard, frames)
            try:
                if before.raw.battle_state == 1:
                    escape_collection_battle(
                        actions,
                        reader,
                        frames,
                        recipient_species_id=recipient,
                        policy=MANSION_TEAM_POLICY,
                        flee_func=_flee,
                        flee_timing=MANSION_TRAINING_FLEE_TIMING,
                    )
                router = RedResourceGoalRouter(runtime, actions, world, routed_recovery=True)
                # An available FIELD_RESTORE spends items and does not restore
                # PP. This support operation explicitly requires the Center
                # mechanic, not whichever same-kind local goal is offered.
                bindings = bind_routed_center_recovery(
                    router,
                    runtime.enumerator(actions).enumerate(runtime.adapter.observe()),
                    runtime.adapter.observe(),
                    prepare_escort=lambda: prepare_capture_escort(runtime, actions),
                    require_pp_restore=True,
                )
                heals = [b for b in bindings.bindings if b.kind is GoalKind.RESTORE_TEAM]
                if len(heals) != 1:
                    raise ValueError("recovery lacks one executable Center restore")
                report = heals[0].execute()
                if heals[0].verify(report).status is not GoalDecisionOutcome.SUCCEEDED:
                    raise ValueError("recovery did not verify its healing result")
                after = runtime.adapter.observe()
                checks = {
                    "field_ready": after.input_ready and after.raw.battle_state == 0,
                    "zero_faints": after.party.fainted_count == 0,
                    "hp_status_pp_restored": _raw_party_restored(after.raw),
                    "living_specimens_preserved": (
                        Counter(s.species_ref for s in before.collection_observation.specimens)
                        == Counter(s.species_ref for s in after.collection_observation.specimens)
                    ),
                    "pokedex_preserved": before.collection_observation.owned_species
                    == after.collection_observation.owned_species,
                }
                writer.append("recovery_verification", checks, durable=True)
                if not all(checks.values()):
                    raise ValueError(f"recovery verification failed: {checks!r}")
                if recorder.recording_failures:
                    raise ValueError("recovery trajectory lost evidence")
                costs = meter.checkpoint()
                result = RedFailureRecoveryResult(
                    args.failed_episode,
                    args.failed_manifest,
                    args.failed_state,
                    failed["actions"],
                    failed["frames"],
                    costs.controller_actions,
                    costs.emulator_frames,
                )
                observer = base._player_observer(
                    runtime,
                    actions,
                    world,
                    ready.quote_resource_costs,
                    completion_dose=ready.completion_dose,
                    routed_recovery=ready.routed_recovery,
                    remaining_acquisition_demand=ready.remaining_acquisition_demand,
                    level_evolution_acquisitions=ready.level_evolution_acquisitions,
                )
                memory = base._execution_search_memory(ready)
                observer.search_memory = memory
                captured = capture_red_player_terminal(
                    emulator=emulator,
                    meter=meter,
                    observe=observer,
                    parent=ready.capture,
                    result=result,
                    episode_id=args.episode_id,
                    profile_sha256=ready.profile.profile_sha256,
                    rom_sha256=ready.rom_sha256,
                    model_sha256=ready.model_sha256,
                    source_commit=ready.source_commit,
                    source_bundle_sha256=ready.source_bundle_sha256,
                    context_origin="training",
                    search_memory=memory,
                )
                writer.append("checkpoint", captured, durable=True)
            except BaseException:
                writer.append(
                    "failure_state",
                    capture_red_failure_state(emulator=emulator, meter=meter),
                    durable=True,
                )
                raise
            sink.record_event(
                base.SparseEvent(
                    event_id=f"{args.episode_id}:terminal",
                    episode_id=args.episode_id,
                    step_index=recorder.next_step_index,
                    kind="terminal",
                    payload={"status": "complete", "bounded_player": result.public_dict()},
                )
            )
            sink.finalize()
            writer.complete()
            finalized = True
            checkpoint = publish_red_player_checkpoint(ready.private_root, captured)
            base._write_exclusive(
                args.out,
                {
                    **preflight,
                    "status": "recovered",
                    "checkpoint": checkpoint,
                    "recovery": result.public_dict(),
                    "before": before.public_dict(),
                    "after": after.public_dict(),
                },
            )
            print(
                json.dumps(
                    {
                        "status": "recovered",
                        "checkpoint": checkpoint,
                        "recovery": result.public_dict(),
                    }
                ),
                flush=True,
            )
        except BaseException as error:
            if writer is not None and not finalized:
                base._retain_failure(
                    writer, sink=sink, recorder=recorder, episode_id=args.episode_id, error=error
                )
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-arguments", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--failed-episode", required=True)
    parser.add_argument("--failed-manifest", required=True)
    parser.add_argument("--failed-state", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    run(parser.parse_args())
