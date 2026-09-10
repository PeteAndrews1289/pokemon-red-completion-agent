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

from pokemon_red_completion.battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    BattleIntent,
    BattleRuntimeTiming,
    BattleSwitchCapability,
)
from pokemon_red_completion.blaine import MANSION_TEAM_POLICY, MANSION_TRAINING_FLEE_TIMING
from pokemon_red_completion.celadon import _flee
from pokemon_red_completion.gen1_trainer_dialogue import (
    bind_scripted_trainer_dialogue,
    retained_scripted_trainer_candidate,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalDecisionOutcome
from pokemon_red_completion.observation import BattleMenuPhase, EventFlag, MapId
from pokemon_red_completion.red_capture_preparation import prepare_capture_escort
from pokemon_red_completion.red_failed_regional_profile import committed_failed_source_profile
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
from pokemon_red_completion.red_routed_recovery import (
    RecoveryRouteInterruptionHandler,
    bind_routed_center_recovery,
)
from pokemon_red_completion.red_routed_trainer_funding import active_trainer_funding_candidate
from pokemon_red_completion.red_team_training import (
    collection_escape_escort,
    escape_collection_battle,
)
from pokemon_red_completion.red_trainer_control import RedTrainerPartyController
from pokemon_red_completion.red_trainer_funding_battle import run_prepared_trainer_funding
from pokemon_red_completion.red_trainer_healing import trainer_bag_within_budget
from pokemon_red_completion.red_trainer_risk import RedTrainerRiskController
from pokemon_red_completion.red_trainer_survival import RedTrainerSurvivalController


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
        chosen_profile = committed_failed_source_profile(ready.private_root, failed_id)
        if chosen_profile is not None:
            ready = replace(ready, profile=chosen_profile)
            break
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


def require_registered_recovery_binding(ready):
    """Reject incomplete ledger wiring before opening or controlling the game."""
    if getattr(ready, "registration_policy", None) is None:
        return
    sequence = getattr(ready, "registration_sequence", None)
    if (type(sequence) is not int or sequence < 1
            or getattr(ready, "registration_ledger", None) is None
            or not getattr(ready, "registration_session_record_id", None)):
        raise ValueError("registered recovery requires its ledger, sequence and session binding")


def observed_failed_trainer_switches(store, episode_id, depth=0):
    """Reconstruct consumed switches from recorded active-party transitions."""
    if depth >= 8:
        raise ValueError("trainer switch ancestry exceeds its bound")
    episode = store.open_failed_episode(episode_id)
    metadata = episode.read_header()["metadata"]
    previous = ()
    if metadata.get("schema") == "pokemon.red.forced-recovery-header.v1":
        previous = observed_failed_trainer_switches(
            store,
            metadata["recovery"]["failure_episode_id"],
            depth + 1,
        )
    snapshots = {
        row["snapshot_sha256"]: row["snapshot"]["features"]
        for row in episode.iter_stream("snapshots")
    }
    observed = []
    for execution in episode.iter_stream("executions"):
        before = snapshots[execution["before_sha256"]]
        after = snapshots[execution["after_sha256"]]
        before_slot = (before.get("party") or {}).get("active_index")
        after_slot = (after.get("party") or {}).get("active_index")
        if (
            all((view.get("battle") or {}).get("kind") == "trainer" for view in (before, after))
            and type(before_slot) is int
            and type(after_slot) is int
            and before_slot != after_slot
        ):
            observed.append(after_slot + 1)
    return previous + tuple(observed)


def observed_failed_trainer_heal_claims(store, episode_id, depth=0):
    """Carry durable item claims across failed recoveries; never refund ambiguity."""
    if depth >= 8:
        raise ValueError("trainer healing ancestry exceeds its bound")
    episode = store.open_failed_episode(episode_id)
    metadata = episode.read_header()["metadata"]
    count = 0
    if metadata.get("schema") == "pokemon.red.forced-recovery-header.v1":
        count = observed_failed_trainer_heal_claims(
            store,
            metadata["recovery"]["failure_episode_id"],
            depth + 1,
        )
    if "trainer_recovery_decisions" in episode.stream_names:
        count += sum(
            row.get("kind") == "heal" for row in episode.iter_stream("trainer_recovery_decisions")
        )
    return count


def remaining_trainer_heal_budget(store, episode_id, requested):
    claimed = observed_failed_trainer_heal_claims(store, episode_id)
    if type(requested) is not int or not 0 <= requested <= max(0, 2 - claimed):
        raise ValueError("recovery would refresh already claimed Full Restores")
    return claimed


def observed_failed_trainer_risk_claims(store, episode_id, depth=0):
    """Count durable critical-exposure intents, including interrupted/no-PP turns."""
    if depth >= 8:
        raise ValueError("trainer risk ancestry exceeds its bound")
    episode = store.open_failed_episode(episode_id)
    metadata = episode.read_header()["metadata"]
    count = 0
    if metadata.get("schema") == "pokemon.red.forced-recovery-header.v1":
        count = observed_failed_trainer_risk_claims(
            store, metadata["recovery"]["failure_episode_id"], depth + 1,
        )
    if "trainer_recovery_decisions" in episode.stream_names:
        count += sum(
            row.get("kind") == "risk_attack"
            for row in episode.iter_stream("trainer_recovery_decisions")
        )
    return count


def run(args):
    settled_admission = getattr(args, "admit_settled_field", False)
    if type(settled_admission) is not bool or (settled_admission and any((
        getattr(args, "finish_trainer_funding", False),
        getattr(args, "finish_scripted_trainer", None),
        getattr(args, "maximum_full_restores", 0),
        getattr(args, "zero_item_survival", False),
        getattr(args, "maximum_critical_exposures", 0),
        getattr(args, "prior_switches", ()),
    ))):
        raise ValueError("settled admission is an exclusive zero-controller mode")
    healing_budget = getattr(args, "maximum_full_restores", 0)
    prior_switches = tuple(getattr(args, "prior_switches", ()))
    scripted_trainer = getattr(args, "finish_scripted_trainer", None)
    zero_item_survival = getattr(args, "zero_item_survival", False)
    risk_budget = getattr(args, "maximum_critical_exposures", 0)
    if type(risk_budget) is not int or not 0 <= risk_budget <= 2 or (
        risk_budget and (not getattr(args, "finish_trainer_funding", False)
                         or healing_budget or zero_item_survival or scripted_trainer)
    ):
        raise ValueError("critical exposure requires its explicit active zero-item mode")
    if type(zero_item_survival) is not bool or (
        zero_item_survival and (not getattr(args, "finish_trainer_funding", False)
                               or healing_budget or scripted_trainer)
    ):
        raise ValueError("zero-item survival requires its explicit active-trainer mode")
    survival_control = bool(healing_budget) or zero_item_survival or bool(risk_budget)
    if scripted_trainer not in {None, "lance"} or (
        scripted_trainer
        and (getattr(args, "finish_trainer_funding", False) or healing_budget or prior_switches)
    ):
        raise ValueError("scripted trainer recovery is a separate zero-item introduction mode")
    if (
        type(healing_budget) is not int
        or not 0 <= healing_budget <= 2
        or (healing_budget and not getattr(args, "finish_trainer_funding", False))
        or (prior_switches and not survival_control)
    ):
        raise ValueError("healing budget requires the explicit active-trainer recovery mode")
    ready, failed = prepare(args)
    require_registered_recovery_binding(ready)
    prior_risk_claims = (
        observed_failed_trainer_risk_claims(ready.private_root, args.failed_episode)
        if risk_budget else 0
    )
    if prior_risk_claims + risk_budget > 2:
        raise ValueError("recovery would refresh already claimed critical exposures")
    prior_heal_claims = (
        remaining_trainer_heal_budget(
            ready.private_root,
            args.failed_episode,
            healing_budget,
        )
        if getattr(args, "finish_trainer_funding", False)
        else 0
    )
    if (
        survival_control
        and observed_failed_trainer_switches(
            ready.private_root,
            args.failed_episode,
        )
        != prior_switches
    ):
        raise ValueError("declared prior switches differ from the retained failed execution")

    def survival_actor(reader, emulator, decision_sink=None):
        if risk_budget:
            return RedTrainerRiskController(
                reader, emulator, prior_switches, 0, decision_sink=decision_sink,
                maximum_critical_exposures=risk_budget,
                previous_critical_exposures=prior_risk_claims,
            )
        return RedTrainerSurvivalController(
            reader, emulator, prior_switches, healing_budget, decision_sink=decision_sink,
        )

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
        runtime = base._registered_runtime(ready, runtime)
        before = runtime.adapter.observe()
        trainer_recovery = getattr(args, "finish_trainer_funding", False) or bool(scripted_trainer)
        trainer_target = None
        if trainer_recovery:
            if not ready.trainer_funding or before.party.fainted_count:
                raise ValueError("trainer recovery requires the funding mode and preserved party")
            trainer_target = (
                retained_scripted_trainer_candidate(
                    world.rom,
                    reader,
                    map_id=int(MapId.LANCES_ROOM),
                    trainer_event_flag=int(EventFlag.BEAT_LANCES_ROOM_TRAINER),
                    final_event_flag=int(EventFlag.BEAT_LANCE),
                )
                if scripted_trainer
                else active_trainer_funding_candidate(world.rom, reader)
            )
            if (
                not scripted_trainer
                and reader.read_battle_menu_state(before.raw).phase is not BattleMenuPhase.MAIN
            ):
                raise ValueError("trainer recovery must begin at the MAIN battle menu")
            if survival_control:
                controller = survival_actor(reader, base.ReadOnlyController(emulator))
                first_survival_decision = controller.decide(before.raw)
        if settled_admission and not (
            before.raw.battle_state == 0 and before.input_ready
            and not before.party.fainted_count and _raw_party_restored(before.raw)
        ):
            raise ValueError("settled admission requires a healthy input-ready field")
        if before.party.fainted_count or not (
            settled_admission
            or
            (trainer_recovery and before.raw.battle_state == 2)
            or (scripted_trainer and before.raw.battle_state == 0)
            or before.raw.battle_state == 1
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
            "maximum_actions": 0 if settled_admission else 6000,
            "maximum_frames": 0 if settled_admission else 600000,
            "settled_admission": settled_admission,
            "model_queries": 0,
            "training_examples": 0,
            "original_choice_retried": False,
            "finish_trainer_funding": trainer_recovery,
            "finish_scripted_trainer": scripted_trainer,
            "maximum_full_restores": healing_budget,
            "zero_item_survival": zero_item_survival,
            "maximum_critical_exposures": risk_budget,
            "prior_critical_exposure_claims": prior_risk_claims,
            "prior_full_restore_claims": prior_heal_claims,
            "prior_switches": list(prior_switches),
            "first_survival_action": (
                first_survival_decision.kind if trainer_recovery and survival_control else None
            ),
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
                    **(
                        {"registration_session_record_id": ready.registration_session_record_id}
                        if getattr(ready, "registration_session_record_id", None) is not None
                        else {}
                    ),
                    "routed_recovery": ready.routed_recovery,
                    "trainer_funding": ready.trainer_funding,
                    "trainer_pending_recovery": ready.trainer_pending_recovery,
                    "regional_trainer_funding": ready.regional_trainer_funding,
                    "observed_trainer_funding": ready.observed_trainer_funding,
                    "remaining_acquisition_demand": ready.remaining_acquisition_demand,
                    "level_evolution_acquisitions": ready.level_evolution_acquisitions,
                    "recovery": preflight,
                }
            )
            frames = base.WindowedFrameBudgetController(
                base.ReadOnlyController(emulator) if settled_admission else emulator,
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
            runtime = base._registered_runtime(ready, runtime)
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
                trainer_receipt = None
                if trainer_target is not None:
                    story_controller = (
                        RedTrainerPartyController(reader, frames) if scripted_trainer else None
                    )

                    def validate_trainer():
                        current_target = (
                            retained_scripted_trainer_candidate(
                                world.rom,
                                reader,
                                map_id=int(MapId.LANCES_ROOM),
                                trainer_event_flag=int(EventFlag.BEAT_LANCES_ROOM_TRAINER),
                                final_event_flag=int(EventFlag.BEAT_LANCE),
                            )
                            if scripted_trainer
                            else active_trainer_funding_candidate(world.rom, reader)
                        )
                        if current_target != trainer_target:
                            raise ValueError("active trainer recovery target changed before input")

                    guard = RecoveryRouteInterruptionHandler(
                        actions,
                        reader,
                        tuple(before.raw.party_species_ids or ()),
                        tuple(range(before.party.size)),
                        maximum_trainer_battles=0,
                    )
                    trainer_receipt = run_prepared_trainer_funding(
                        reader,
                        actions,
                        target=trainer_target,
                        validate_target=validate_trainer,
                        move_slot_policy=guard._safe_trainer_move,
                        timing=(
                            BattleRuntimeTiming(max_runtime_pulses=1600)
                            if scripted_trainer
                            else DEFAULT_BATTLE_RUNTIME_TIMING
                        ),
                        resume_active_battle=not scripted_trainer,
                        validate_scripted_dialogue=(
                            bind_scripted_trainer_dialogue(
                                world.rom,
                                reader,
                                trainer_target,
                                before.raw,
                                final_event_flag=int(EventFlag.BEAT_LANCE),
                            )
                            if scripted_trainer
                            else None
                        ),
                        intent=(
                            BattleIntent(
                                "defeat_lance",
                                battle_plan_id="cartridge-trainer-story-recovery",
                                switch_capabilities=frozenset(
                                    {BattleSwitchCapability.TEMPORARY_ROLE_PIVOT}
                                ),
                                switch_limit=story_controller.maximum_switches,
                                require_move_between_switches=True,
                            )
                            if story_controller is not None
                            else None
                        ),
                        maximum_full_restores=healing_budget,
                        battle_runner_override=(
                            survival_actor(
                                reader,
                                frames,
                                decision_sink=lambda report: writer.append(
                                    "trainer_recovery_decisions",
                                    report,
                                    durable=True,
                                ),
                            ).run
                            if survival_control
                            else story_controller.run
                            if story_controller is not None
                            else None
                        ),
                    )
                    writer.append(
                        "trainer_funding",
                        {
                            "event_flag": trainer_target.trainer.event_flag,
                            "opponent": trainer_target.trainer.trainer_class,
                            "trainer_set": trainer_target.trainer.trainer_set,
                            "initial_money": trainer_receipt.initial_money,
                            "final_money": trainer_receipt.final_money,
                            "payout": trainer_receipt.payout,
                            "training_examples": 0,
                        },
                        durable=True,
                    )
                elif before.raw.battle_state == 1:
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
                bindings = (
                    None
                    if trainer_recovery or settled_admission
                    else bind_routed_center_recovery(
                        router,
                        runtime.enumerator(actions).enumerate(runtime.adapter.observe()),
                        runtime.adapter.observe(),
                        prepare_escort=lambda: prepare_capture_escort(runtime, actions),
                        require_pp_restore=True,
                    )
                )
                if bindings is not None:
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
                    "living_specimens_preserved": (
                        Counter(s.species_ref for s in before.collection_observation.specimens)
                        == Counter(s.species_ref for s in after.collection_observation.specimens)
                    ),
                    "pokedex_preserved": before.collection_observation.owned_species
                    == after.collection_observation.owned_species,
                }
                if trainer_recovery:
                    checks["trainer_income_verified"] = (
                        trainer_receipt is not None
                        and after.raw.player_money == trainer_receipt.final_money
                        and trainer_bag_within_budget(before.raw, after.raw, healing_budget)
                    )
                    if scripted_trainer:
                        checks["lance_story_event_verified"] = (
                            "league:lance_defeated" in after.game_state.facts
                        )
                else:
                    checks["hp_status_pp_restored"] = _raw_party_restored(after.raw)
                writer.append("recovery_verification", checks, durable=True)
                if not all(checks.values()):
                    raise ValueError(f"recovery verification failed: {checks!r}")
                if recorder.recording_failures:
                    raise ValueError("recovery trajectory lost evidence")
                costs = meter.checkpoint()
                if settled_admission and (
                    costs.controller_actions != 0 or costs.emulator_frames != 0
                    or emulator.save_state_bytes() != payload
                ):
                    raise ValueError("settled admission changed state or consumed controller input")
                result = RedFailureRecoveryResult(
                    args.failed_episode,
                    args.failed_manifest,
                    args.failed_state,
                    failed["actions"],
                    failed["frames"],
                    costs.controller_actions,
                    costs.emulator_frames,
                    settled_admission=settled_admission,
                )
                observer = base._player_observer(
                    runtime,
                    actions,
                    world,
                    ready.quote_resource_costs,
                    completion_dose=ready.completion_dose,
                    routed_recovery=ready.routed_recovery,
                    trainer_funding=ready.trainer_funding,
                    trainer_pending_recovery=ready.trainer_pending_recovery,
                    regional_trainer_funding=ready.regional_trainer_funding,
                    observed_trainer_funding=ready.observed_trainer_funding,
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
                if getattr(ready, "registration_policy", None) is not None:
                    from pokemon_red_completion.red_registration_session import (
                        observe_registration,
                        read_registration_state,
                        validate_terminal_registration,
                    )

                    registration_state, seen = read_registration_state(emulator, runtime)
                    captured["registration_observation"] = observe_registration(
                        registration_state,
                        seen=seen,
                        run_id=ready.registration_policy.run_id,
                        rom_sha256=ready.rom_sha256,
                        snapshot_sha256=str(captured["state_sha256"]),
                        sequence=ready.registration_sequence,
                    ).document()
                    validate_terminal_registration(
                        captured,
                        ready.registration_policy,
                        sequence=ready.registration_sequence,
                        rom_sha256=ready.rom_sha256,
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
            if getattr(ready, "registration_policy", None) is not None:
                from pokemon_red_completion.red_registration_session import registration_row
                from pokemon_red_completion.registration_memory import RegistrationMemory

                RegistrationMemory(ready.registration_ledger).record(
                    registration_row(captured["registration_observation"]),
                )
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
    parser.add_argument("--admit-settled-field", action="store_true")
    parser.add_argument("--finish-trainer-funding", action="store_true")
    parser.add_argument("--finish-scripted-trainer", choices=("lance",))
    parser.add_argument("--maximum-full-restores", type=int, default=0)
    parser.add_argument("--zero-item-survival", action="store_true")
    parser.add_argument("--maximum-critical-exposures", type=int, default=0)
    parser.add_argument("--prior-switches", type=int, nargs="*", default=[])
    run(parser.parse_args())
