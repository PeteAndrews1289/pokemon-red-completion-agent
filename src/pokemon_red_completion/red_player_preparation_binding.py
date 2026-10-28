"""Bind existing role-aware preparation, with recovery left to the next goal.

The caller declares the trainee/venue plan as support. The player owns whether
to execute this offer, never an invented alternative or a memory-edit action.
"""

from dataclasses import asdict
from hashlib import sha256

from .gen1_route_runtime import Gen1FieldBlackoutPending, Gen1TraversalObserver
from .gen1_traversal import cut_capabilities
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .provenance import canonical_sha256
from .red_blackout_recovery import settle_red_blackout
from .red_goal_skills import (
    _POKEMON_CENTER_MAPS,
    RedCenterRestoreGoalProvider,
    _raw_party_fully_restored,
)
from .red_party_preparation import observe_preparation_members, preparation_trainee
from .red_training_ground_route import ground_route_capability_projector
from .red_player_lesson import capture_player_lesson_snapshot
from .red_trainer_evolution import level_evolution_edges, level_evolution_matches
from .red_wild_preparation import (
    HEALTH_LIMITED_RETURNS,
    WildPreparationDefeat,
    execute_wild_preparation,
    wild_training_has_attack_capacity,
)


def settle_preparation_loss(
    runtime, actions, *, record, maximum_pulses=128, allow_field_loss=False
):
    """Mandatory native loss settlement, not a selected goal or successful dose.

    Used both at the typed defeat seam and for an authenticated retained loss.
    The caller's guarded port owns all input/time caps. No load, edit or fit.
    """
    if type(allow_field_loss) is not bool:
        raise TypeError("preparation field loss scope requires an explicit boolean")
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    admitted_origin = (
        raw.battle_state == 0
        and not runtime.reader.read_input_readiness().ready
        and runtime.reader.read_bottom_dialogue_box_visible()
        if allow_field_loss else raw.battle_state == 1
    )
    if (
        not admitted_origin
        or not raw.party_hp
        or any(raw.party_hp)
        or runtime.emulator.pressed_buttons
    ):
        raise ValueError("preparation settlement requires an observed released wild defeat")
    record(
        "blackout-started",
        dict(source_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(), before=lesson),
    )
    evidence = settle_red_blackout(
        actions, runtime.reader, runtime.emulator, maximum_pulses=maximum_pulses,
        **({"allow_field_loss": True} if allow_field_loss else {}),
    )
    after, terminal = capture_player_lesson_snapshot(runtime)

    def preserved(document):
        return tuple(
            (
                m["specimen_ref"],
                m["species_id"],
                m["level"],
                m["experience"],
                tuple(move[0] for move in m["moves"]),
            )
            for m in document["party"]
        )

    if (
        preserved(lesson) != preserved(terminal)
        or lesson["completed_objectives"] != terminal["completed_objectives"]
        or lesson["objective_catalog"] != terminal["objective_catalog"]
        or terminal["in_battle"]
        or not after.input_ready
        or runtime.reader.read_bottom_dialogue_box_visible()
        or not _raw_party_fully_restored(after.raw)
        or runtime.emulator.pressed_buttons
    ):
        raise ValueError("preparation blackout did not preserve XP/party/progress or settle")
    result = dict(
        status="settled_loss",
        stop_reason="party_defeated",
        successful_preparation=False,
        learned_recovery=False,
        blackout=evidence,
        before=lesson,
        after=terminal,
        terminal_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
    )
    record("blackout-settled", result)
    return result


def preparation_encounter_limits(quantum=None):
    """Bound one selected dose before returning control to the goal model.

    None preserves the existing 64-encounter behavior. A shorter explicit quantum
    changes no target or battle choice, and renews no outer player allowance.
    """
    if quantum is not None and (type(quantum) is not int or not 1 <= quantum <= 64):
        raise ValueError("preparation encounter quantum must be an integer in 1..64")
    battles = 64 if quantum is None else quantum
    return battles, battles - 1


def preparation_estimated_effort(travel_cost, maximum_battles, *, approach_cost=0):
    """Compose the existing child heuristic with only a route-to-home surcharge.

    Costs come from feasible route plans; callers validate the battle allowance.
    This preserves the legacy bounded estimate, not an expected action count.
    """
    return min(1.0, (approach_cost + travel_cost + 120 * maximum_battles) / 3000)


def preparation_binding(
    runtime,
    actions,
    *,
    battler,
    plan,
    route,
    corridor,
    record,
    hideout_timing,
    maximum_battles=3,
    maximum_recoveries=0,
    repeat_health_limited_zero_progress=False,
    minimum_ready_members=None,
    prepare_transport_escort=False,
    include_indigo_lobby=False,
    restore_completed_target=False,
    restore_exhausted_partial=False,
):
    """Fresh, single-use offer for any supported healthy combat roster.

    XP and the declared target level are independently checked after execution.
    Opt-in recovery retains each incomplete dose and its original target/budget.
    A separate opt-in permits verified zero-XP health retreats only within the
    plan's original consecutive no-progress limit; no encounter budget is reset.
    Default callers still leave restoration to the next goal.
    An explicit completed-target endpoint includes one final metered nurse
    restoration after earned target attainment. A separate explicit opt-in restores
    a productive exhausted partial dose once, without changing its failed target
    or renewing its encounters. All restoration uses the shared metered port.
    The shared outer controller owns aggregate action/frame/wall limits.
    """
    if type(maximum_battles) is not int or not 1 <= maximum_battles <= 128:
        raise ValueError("preparation battle allowance must be1..128")
    # One recovery between each of at most128 encounters is sufficient. This
    # opt-in never replenishes the encounter budget.
    if type(maximum_recoveries) is not int or not 0 <= maximum_recoveries <= 127:
        raise ValueError("preparation recovery allowance must be0..127")
    if type(repeat_health_limited_zero_progress) is not bool:
        raise ValueError("zero-progress health recovery must be explicit boolean")
    no_progress_limit = None
    if repeat_health_limited_zero_progress:
        no_progress_limit = getattr(getattr(plan, "budget", None), "max_no_progress", None)
        if not maximum_recoveries or type(no_progress_limit) is not int or no_progress_limit < 1:
            raise ValueError(
                "zero-progress recovery requires a declared no-progress/recovery limit"
            )
    if minimum_ready_members is not None and (
        type(minimum_ready_members) is not int or not 1 <= minimum_ready_members <= 6
    ):
        raise ValueError("invalid minimum battle-ready party count")
    if type(prepare_transport_escort) is not bool:
        raise ValueError("training transport escort must be explicit boolean")
    if type(include_indigo_lobby) is not bool:
        raise ValueError("Indigo preparation opt-in must be boolean")
    if type(restore_completed_target) is not bool:
        raise ValueError("completed preparation restoration must be explicit boolean")
    if type(restore_exhausted_partial) is not bool:
        raise ValueError("partial preparation restoration must be explicit boolean")
    restore = getattr(actions, "execute_restoration", None)
    if (maximum_recoveries or restore_completed_target or restore_exhausted_partial) and not callable(restore):
        raise ValueError("preparation recovery requires the shared metered restoration port")
    if battler.session is not runtime.emulator:
        raise ValueError("preparation battler bypasses the guarded controller")
    raw = runtime.reader.read()
    from .observation import MapId

    indigo = include_indigo_lobby and raw.map_id == MapId.INDIGO_PLATEAU_LOBBY
    nurse_at = (7, 7) if indigo else (3, 3)
    if (
        (raw.map_id not in _POKEMON_CENTER_MAPS and not indigo)
        or raw.battle_state
        or (raw.player_y, raw.player_x) != nurse_at
        or not _raw_party_fully_restored(raw)
        or not runtime.reader.read_input_readiness().ready
        or runtime.reader.read_bottom_dialogue_box_visible()
        or runtime.emulator.pressed_buttons
    ):
        return None
    members = observe_preparation_members(runtime.emulator, plan)
    if not wild_training_has_attack_capacity(members):
        return None  # Nursing cannot make an entirely status-only roster attack.
    if minimum_ready_members is not None and minimum_ready_members > len(members):
        raise ValueError("invalid minimum battle-ready party count")
    try:
        trainee = preparation_trainee(plan, members)
    except ValueError:
        return None  # The declared dose is already met; do not grind indefinitely.
    origin = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=ground_route_capability_projector(route, runtime.emulator),
    ).observe()
    from .route_plan import RoutePlanningError

    try:
        travel = route.route_world.plan_feasible_to_map(
            origin, corridor.map_id, goal_at=corridor.origin_at
        )
    except RoutePlanningError:
        return None
    target = dict(plan.targets)[trainee.specimen_ref]
    used = False
    loss = None
    recoverable_return = False
    bounded_progress_return = False
    partial_report_digest = None
    completed_report_digest = None
    completed_state_sha256 = None
    before_actions, before_frames = actions.actions_executed, runtime.emulator.frame_count
    before_objectives = runtime.adapter.graph.completed_ids(runtime.adapter.observe().game_state)

    def same_or_earned(old, new):
        return new.species_id == old.species_id or level_evolution_matches(
            old, new, level_evolution_edges(route.rom)
        )

    def retained_boundary(previous):
        after = runtime.reader.read()
        current = observe_preparation_members(runtime.emulator, plan)
        old = {m.specimen_ref: m.observation for m in previous}
        new = {m.specimen_ref: m.observation for m in current}
        valid = (
            old.keys() == new.keys()
            and all(
                same_or_earned(old[k], new[k])
                and new[k].level >= old[k].level
                and new[k].experience >= old[k].experience
                for k in old
            )
            and after.map_id == raw.map_id
            and not after.battle_state
            and (after.player_y, after.player_x) == nurse_at
            and runtime.reader.read_input_readiness().ready
            and not runtime.reader.read_bottom_dialogue_box_visible()
            and not runtime.emulator.pressed_buttons
            and after.player_money == raw.player_money
            and after.bag_items == raw.bag_items
            and runtime.adapter.graph.completed_ids(runtime.adapter.observe().game_state)
            == before_objectives
        )
        return valid, current

    def execute():
        nonlocal used, loss, recoverable_return, bounded_progress_return, partial_report_digest
        nonlocal completed_report_digest, completed_state_sha256
        if (
            used
            or runtime.reader.read() != raw
            or not runtime.reader.read_input_readiness().ready
            or runtime.reader.read_bottom_dialogue_box_visible()
            or runtime.emulator.pressed_buttons
        ):
            raise ValueError("preparation offer is consumed or stale")
        used = True
        remaining = maximum_battles
        consecutive_no_progress = 0
        doses = []
        dose_members = members
        source_raw = raw
        for dose in range(maximum_recoveries + 1):
            try:
                result = execute_wild_preparation(
                    rom=route.rom,
                    reader=runtime.reader,
                    actions=actions,
                    emulator=runtime.emulator,
                    battler=battler,
                    adapter=runtime.adapter,
                    source_raw=source_raw,
                    plan=plan,
                    attempts=(),
                    record=record,
                    cost_snapshot=lambda: (actions.actions_executed, runtime.emulator.frame_count),
                    hideout_timing=hideout_timing,
                    route=route,
                    corridor=corridor,
                    maximum_battles=remaining,
                    restore_on_return=False,
                    # A verified retreat remains a failed recoverable goal
                    # when restoration is left to the next model selection.
                    allow_health_retreat=True,
                    continue_after_nonwinning_exit=True,
                    minimum_ready_members=minimum_ready_members,
                    prepare_transport_escort=prepare_transport_escort,
                )
            except (WildPreparationDefeat, Gen1FieldBlackoutPending) as defeat:
                field_loss = isinstance(defeat, Gen1FieldBlackoutPending)
                if field_loss:
                    record("field-blackout-handoff", dict(
                        source_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                        reason=str(defeat),
                        route_failure=None if defeat.failure is None else dict(
                            reason=defeat.failure.reason.value,
                            acknowledged_steps=[asdict(r.step)
                                                for r in defeat.failure.executed_steps],
                            movement_requests=defeat.failure.movement_requests,
                            wait_actions=defeat.failure.wait_actions,
                        ),
                        model_queries=0, learned_recovery=False,
                    ))
                loss = result = settle_preparation_loss(
                    runtime, actions, record=record,
                    **({"allow_field_loss": True} if field_loss else {}),
                )
                break
            recoverable_return = result.get("health_limited_return") is True
            bounded_progress_return = (
                not maximum_recoveries
                and result.get("stop_reason") == "encounter_limit"
                and result.get("encounters", result.get("battles")) == maximum_battles
            )
            if not maximum_recoveries:
                break
            valid, current = retained_boundary(dose_members)
            old = {m.specimen_ref: m.observation for m in dose_members}
            new = {m.specimen_ref: m.observation for m in current}
            spent = result.get("encounters", result.get("battles"))
            if not valid or type(spent) is not int or not 0 <= spent <= remaining:
                raise ValueError("preparation dose boundary or battle accounting differs")
            remaining -= spent
            # A final retained dose can consume the shared encounter allowance
            # before reaching its level target. Treat its independently verified
            # earned XP like the existing single-dose bounded return, not an
            # unknown outcome. This never converts the incomplete target to a win.
            bounded_progress_return = (
                result.get("stop_reason") == "encounter_limit" and remaining == 0 and spent > 0
            )
            reached = new[trainee.specimen_ref].level >= target
            earned_xp = new[trainee.specimen_ref].experience > old[trainee.specimen_ref].experience
            consecutive_no_progress = 0 if earned_xp else consecutive_no_progress + 1
            retry_zero_progress = (
                repeat_health_limited_zero_progress
                and recoverable_return
                and consecutive_no_progress < no_progress_limit
            )
            dose_result = dict(
                ordinal=dose,
                trainee_ref=trainee.specimen_ref,
                target_level=target,
                target_reached=reached,
                verification="succeeded" if reached else "failed",
                failure_reason=None if reached else "target_not_met",
                terminal_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                remaining_battles=remaining,
                result=dict(result),
                model_queries=0,
                **(
                    dict(
                        consecutive_no_progress=consecutive_no_progress,
                        no_progress_limit=no_progress_limit,
                    )
                    if repeat_health_limited_zero_progress
                    else {}
                ),
            )
            # Persist the unfinished dose before any healing or further input.
            record("retained-dose", dose_result)
            doses.append(dose_result)
            if (
                reached
                or dose == maximum_recoveries
                or remaining == 0
                or result.get("stop_reason") not in HEALTH_LIMITED_RETURNS
                or spent == 0
                or (not earned_xp and not retry_zero_progress)
                or _raw_party_fully_restored(runtime.reader.read())
            ):
                break
            offer = RedCenterRestoreGoalProvider(
                actions,
                runtime.reader,
                runtime.emulator,
                runtime.adapter,
                require_full_pp_restore=True,
                **({"include_indigo_lobby": True} if indigo else {}),
            ).offer(runtime.adapter.observe())
            if offer.binding is None:
                raise RuntimeError("retained preparation restoration unavailable")
            record(
                "retained-recovery-intent",
                dict(
                    dose=dose,
                    trainee_ref=trainee.specimen_ref,
                    target_level=target,
                    remaining_battles=remaining,
                    model_queries=0,
                    **(
                        dict(
                            consecutive_no_progress=consecutive_no_progress,
                            no_progress_limit=no_progress_limit,
                        )
                        if repeat_health_limited_zero_progress
                        else {}
                    ),
                ),
            )
            restore(offer.binding)
            restored, healed_members = retained_boundary(current)
            healed = {m.specimen_ref: m.observation for m in healed_members}
            if (
                not restored
                or not _raw_party_fully_restored(runtime.reader.read())
                or any(
                    healed[k].level != new[k].level or healed[k].experience != new[k].experience
                    for k in new
                )
                or preparation_trainee(plan, healed_members).specimen_ref != trainee.specimen_ref
            ):
                raise ValueError("retained preparation restoration changed target or progress")
            dose_members = healed_members
            source_raw = runtime.reader.read()
        if doses:
            result = dict(
                result,
                retained_doses=doses,
                original_target=dict(specimen_ref=trainee.specimen_ref, level=target),
                total_battle_allowance=maximum_battles,
                maximum_recoveries=maximum_recoveries,
                **(
                    dict(
                        repeat_health_limited_zero_progress=True,
                        no_progress_limit=no_progress_limit,
                    )
                    if repeat_health_limited_zero_progress
                    else {}
                ),
                encounters_across_doses=maximum_battles - remaining,
                completed_battles_across_doses=sum(d["result"]["battles"] for d in doses),
                xp_gained_across_doses=sum(
                    m.observation.experience
                    for m in observe_preparation_members(runtime.emulator, plan)
                )
                - sum(m.observation.experience for m in members),
            )
        if loss is None:
            valid, current = retained_boundary(members)
            if valid:
                old = {m.specimen_ref: m.observation for m in members}
                new = {m.specimen_ref: m.observation for m in current}
                party_xp = sum(new[k].experience - old[k].experience for k in old)
                trainee_xp = new[trainee.specimen_ref].experience - old[trainee.specimen_ref].experience
                result = dict(result, party_xp_gained_across_doses=party_xp,
                              trainee_xp_gained_across_doses=trainee_xp)
        if loss is None and restore_completed_target:
            valid, current = retained_boundary(members)
            old = {m.specimen_ref: m.observation for m in members}
            before_heal = {m.specimen_ref: m.observation for m in current}
            ref = trainee.specimen_ref
            reached = (valid and before_heal[ref].level >= target
                       and before_heal[ref].experience > old[ref].experience)
            if reached:
                restoration = None
                if not _raw_party_fully_restored(runtime.reader.read()):
                    record("completed-target-recovery-intent", dict(
                        trainee_ref=ref, target_level=target, model_queries=0,
                        terminal_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                    ))
                    offer = RedCenterRestoreGoalProvider(
                        actions, runtime.reader, runtime.emulator, runtime.adapter,
                        require_full_pp_restore=True,
                        **({"include_indigo_lobby": True} if indigo else {}),
                    ).offer(runtime.adapter.observe())
                    if offer.binding is None:
                        raise RuntimeError("completed preparation restoration unavailable")
                    restored = restore(offer.binding)
                    restoration = dict(actions=restored.actions_executed,
                                       frames=restored.frames_executed,
                                       evidence=dict(restored.evidence))
                valid, healed_members = retained_boundary(current)
                healed = {m.specimen_ref: m.observation for m in healed_members}
                if (not valid or not _raw_party_fully_restored(runtime.reader.read())
                    or any((healed[k].species_id, healed[k].level, healed[k].experience,
                            tuple(m.move_id for m in healed[k].known_moves))
                           != (before_heal[k].species_id, before_heal[k].level,
                               before_heal[k].experience,
                               tuple(m.move_id for m in before_heal[k].known_moves))
                           for k in before_heal)):
                    raise ValueError("completed preparation restoration changed progress or readiness")
                completed_state_sha256 = sha256(runtime.emulator.save_state_bytes()).hexdigest()
                result = dict(result, completed_target_endpoint=dict(
                    schema="pokemon.red.preparation-ready-endpoint.v1",
                    trainee_ref=ref, target_level=target, target_reached=True,
                    fully_restored=True, terminal_sha256=completed_state_sha256,
                    restoration=restoration, model_queries=0,
                ))
                completed_report_digest = canonical_sha256(result)
                record("completed-target-ready-endpoint", result["completed_target_endpoint"])
        if loss is None and bounded_progress_return:
            valid, current = retained_boundary(members)
            old = {m.specimen_ref: m.observation for m in members}
            new = {m.specimen_ref: m.observation for m in current}
            ref = trainee.specimen_ref
            eligible = (
                valid
                and new[ref].experience > old[ref].experience
                and new[ref].level < target
                and type(result.get("encounters", result.get("battles"))) is int
                and (no_progress_limit is None or consecutive_no_progress < no_progress_limit)
            )
            restoration = None
            if (eligible and restore_exhausted_partial
                    and not _raw_party_fully_restored(runtime.reader.read())):
                record("bounded-partial-recovery-intent", dict(
                    trainee_ref=ref, target_level=target, model_queries=0,
                    authority="selected_preparation_final_restoration",
                    target_reached=False, encounters_exhausted=True,
                    terminal_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                ))
                offer = RedCenterRestoreGoalProvider(
                    actions, runtime.reader, runtime.emulator, runtime.adapter,
                    require_full_pp_restore=True,
                    **({"include_indigo_lobby": True} if indigo else {}),
                ).offer(runtime.adapter.observe())
                if offer.binding is not None:
                    # The shared port charges one attempt before input and raises
                    # its typed budget stop before input when no allowance remains.
                    restored = restore(offer.binding)
                    valid, healed_members = retained_boundary(current)
                    healed = {m.specimen_ref: m.observation for m in healed_members}
                    if (not valid or not _raw_party_fully_restored(runtime.reader.read())
                        or any((healed[k].species_id, healed[k].level, healed[k].experience,
                                tuple(m.move_id for m in healed[k].known_moves))
                               != (new[k].species_id, new[k].level, new[k].experience,
                                   tuple(m.move_id for m in new[k].known_moves))
                               for k in new)):
                        raise ValueError("partial preparation restoration changed progress or readiness")
                    restoration = dict(actions=restored.actions_executed,
                                       frames=restored.frames_executed,
                                       evidence=dict(restored.evidence))
            # A fully healed final nonwinning encounter may already be ready.
            # Both paths remain failed doses requiring a fresh model choice.
            if eligible and _raw_party_fully_restored(runtime.reader.read()):
                result = dict(result, bounded_partial_preparation=dict(
                    schema="pokemon.red.preparation-partial.v1",
                    trainee_ref=ref,
                    target_level=target,
                    initial_level=old[ref].level,
                    terminal_level=new[ref].level,
                    initial_xp=old[ref].experience,
                    terminal_xp=new[ref].experience,
                    encounter_allowance=maximum_battles,
                    encounters=maximum_battles,
                    target_reached=False,
                    fully_restored=True,
                    stop_reason="encounter_limit",
                    **(dict(restoration=restoration,
                            support_authority="selected_preparation_final_restoration",
                            model_queries=0) if restoration is not None else {}),
                    terminal_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                ))
                partial_report_digest = canonical_sha256(result)
        return GoalExecutionReport(
            actions.actions_executed - before_actions,
            runtime.emulator.frame_count - before_frames,
            result,
        )

    def verify(report):
        after = runtime.adapter.observe()
        current = observe_preparation_members(runtime.emulator, plan)
        old = {m.specimen_ref: m.observation for m in members}
        new = {m.specimen_ref: m.observation for m in current}
        preserved = old.keys() == new.keys() and all(
            same_or_earned(old[k], new[k])
            and new[k].experience >= old[k].experience
            and new[k].level >= old[k].level
            for k in old
        )
        if loss is not None:
            if (
                used
                and preserved
                and report.actions_executed > 0
                and sha256(runtime.emulator.save_state_bytes()).hexdigest()
                == loss["terminal_sha256"]
                and runtime.adapter.graph.completed_ids(after.game_state) == before_objectives
            ):
                return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        ref = trainee.specimen_ref
        if (
            used
            and report.actions_executed > 0
            and preserved
            and after.raw.map_id == raw.map_id
            and (after.raw.player_y, after.raw.player_x) == nurse_at
            and not after.raw.battle_state
            and after.input_ready
            and not runtime.reader.read_bottom_dialogue_box_visible()
            and not runtime.emulator.pressed_buttons
            and after.raw.player_money == raw.player_money
            and after.raw.bag_items == raw.bag_items
            and runtime.adapter.graph.completed_ids(after.game_state) == before_objectives
        ):
            if new[ref].level >= target and new[ref].experience > old[ref].experience:
                if restore_completed_target and (
                    not _raw_party_fully_restored(after.raw)
                    or completed_report_digest is None
                    or canonical_sha256(dict(report.evidence)) != completed_report_digest
                    or sha256(runtime.emulator.save_state_bytes()).hexdigest() != completed_state_sha256
                    or report.actions_executed != actions.actions_executed - before_actions
                    or report.frames_executed != runtime.emulator.frame_count - before_frames
                ):
                    return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                return GoalVerification.succeeded()
            if (
                (
                    recoverable_return
                    or (bounded_progress_return and new[ref].experience > old[ref].experience)
                )
                and new[ref].level < target
                and not _raw_party_fully_restored(after.raw)
            ):
                return GoalVerification.failed(GoalFailureReason.RECOVERY_REQUIRED)
            if (
                partial_report_digest is not None
                and canonical_sha256(dict(report.evidence)) == partial_report_digest
                and report.actions_executed == actions.actions_executed - before_actions
                and report.frames_executed == runtime.emulator.frame_count - before_frames
                and sha256(runtime.emulator.save_state_bytes()).hexdigest()
                == report.evidence["bounded_partial_preparation"]["terminal_sha256"]
                and new[ref].level < target
                and new[ref].experience > old[ref].experience
                and _raw_party_fully_restored(after.raw)
            ):
                return GoalVerification.failed(GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED)
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    return ExecutableGoalBinding(
        "pokemon.red:bounded-preparation:"
        + canonical_sha256(
            dict(
                trainee=trainee.specimen_ref,
                target=target,
                corridor=corridor.private_dict(),
                maximum_battles=maximum_battles,
                maximum_recoveries=maximum_recoveries,
                **(
                    dict(
                        repeat_health_limited_zero_progress=True,
                        no_progress_limit=no_progress_limit,
                    )
                    if repeat_health_limited_zero_progress
                    else {}
                ),
                **(
                    {"minimum_ready_members": minimum_ready_members}
                    if minimum_ready_members is not None
                    else {}
                ),
                **({"prepare_transport_escort": True} if prepare_transport_escort else {}),
                **({"include_indigo_lobby": True} if indigo else {}),
                **({"restore_completed_target": True} if restore_completed_target else {}),
                **({"restore_exhausted_partial": True} if restore_exhausted_partial else {}),
            )
        ),
        GoalKind.DEVELOP_TEAM,
        preparation_estimated_effort(travel.cost, maximum_battles),
        0.20,
        execute,
        verify,
    )
