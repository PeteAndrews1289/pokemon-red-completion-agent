"""Model-selected, separately declared story combat using the frozen battler.

The adapter plans an adjacent approach; the goal policy selects the challenge,
and the battle policy selects every combat action. Losses remain paid setbacks.
"""

from dataclasses import asdict, replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import (
    Gen1TrainerSightProjector,
    TrainerFacing,
    TrainerSightZone,
    static_trainer_sight_zones,
    trainer_headers,
    trainer_sight_zones,
)
from .gen1_traversal import cut_capabilities, map_object_events
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import GoalCashOutcome, ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import event_flag_is_set
from .provenance import canonical_sha256
from .red_gym_reward import GymReward
from .red_player_cash_exposure import (
    certified_cash_safe_transition,
    single_blackout_cash_bound,
)
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .red_routed_trainer_funding import _face_trainer_boundary as face_trainer_boundary
from .red_scoped_training_battlers import resolve_story_battler
from .red_story_battle import FrozenStoryBattleController, StoryTrainerContract
from .red_story_sight_entry import enter_story_sight, planned_sight_approaches, sight_entry_edge
from .route_plan import RoutePlanningError


class StoryBattleDecisionBudgetReached(RuntimeError):
    """Retain an authenticated unfinished battle after its local decision bound."""

    reason_code = "story_battle_decision_budget"


def story_battle_binding(
    runtime,
    actions,
    *,
    contract,
    route,
    battler,
    completes_objective=True,
    reward=None,
    scripted_fossil_guard=False,
    scripted_hideout=False,
    before_challenge=None,
):
    if before_challenge is not None and not callable(before_challenge):
        raise TypeError("story challenge admission must be callable")
    if type(completes_objective) is not bool:
        raise TypeError("explicit story completion scope required")
    if type(scripted_fossil_guard) is not bool or (
        scripted_fossil_guard and (reward is not None or completes_objective)
    ):
        raise ValueError("scripted fossil guard is an intermediate, nonreward battle")
    if type(scripted_hideout) is not bool or (
        scripted_hideout and (reward is not None or scripted_fossil_guard)
    ):
        raise ValueError("scripted Hideout scope differs")
    if not isinstance(contract, StoryTrainerContract):
        raise TypeError("cartridge-bound story contract required")
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    objective = runtime.adapter.graph.objective(contract.objective_id)
    if (
        contract.objective_id
        not in {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
        or not before.raw.party_hp
        or not any(before.raw.party_hp)
    ):
        return None
    if contract.defeated_event is not None and event_flag_is_set(
        before.raw.event_flags, contract.defeated_event
    ):
        return None
    headers = trainer_headers(route.rom, {contract.map_id}, full_event_offsets=True)
    objects = map_object_events(route.rom, {contract.map_id})
    leader = None
    if scripted_hideout:
        from .red_scripted_story_trainer import hideout_scripted_contract, hideout_scripted_object

        if contract != hideout_scripted_contract(route.rom, before.raw):
            raise ValueError("scripted Hideout contract changed")
        leader = hideout_scripted_object(route.rom, before.raw.map_id)
        if not any(
            o.sprite_index == leader.object_index
            and o.picture_id == leader.sprite_id
            and o.at == leader.at
            for o in runtime.reader.read_current_map_objects()
        ):
            return None
        if completes_objective and contract.defeated_event is None:
            raise ValueError("poster guard cannot complete Hideout objective")
    if scripted_fossil_guard:
        from .red_scripted_story_trainer import fossil_guard_contract, fossil_guard_object

        if contract != fossil_guard_contract(route.rom, before.raw):
            raise ValueError("scripted fossil guard contract changed")
        leader = fossil_guard_object(route.rom)
    if reward is not None:
        if not isinstance(reward, GymReward) or reward.contract(route.rom, before.raw) != contract:
            raise ValueError("leader reward and cartridge contract differ")
        leaders = [o for o in objects if o.object_index == 1 and o.movement == 255]
        if len(leaders) != 1:
            raise ValueError("leader needs one stationary cartridge object")
        leader = leaders[0]
    targets = [
        t
        for t in static_trainer_sight_zones(headers, objects, before.raw.event_flags)
        if t.event_flag == contract.defeated_event and not t.defeated
    ]
    if leader is not None:
        targets = [
            TrainerSightZone(
                contract.map_id,
                leader.object_index,
                leader.trainer_class,
                leader.trainer_set,
                leader.at,
                TrainerFacing.DOWN,
                0,
                contract.defeated_event,
                False,
                False,
            )
        ]
    if len(targets) != 1:
        raise ValueError("story target not unique in cartridge")
    target = targets[0]
    if (
        target.trainer_class,
        target.trainer_class - 200,
        target.trainer_set,
    ) != contract.trainer_identity:
        raise ValueError("story target differs from contract")
    start = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    approaches = []
    for facing in TrainerFacing:
        dy, dx = facing.delta
        at = (target.at[0] - dy, target.at[1] - dx)
        if min(at) < 0 or at in target.lane:
            continue
        try:
            plan = route.route_world.plan_feasible_to_map(start, contract.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        approaches.append((plan, facing))
    sight = None
    if not approaches:
        if leader is not None:
            return None
        zones = trainer_sight_zones(
            headers, objects, before.raw, runtime.reader.read_current_map_objects()
        )
        sights = planned_sight_approaches(route.route_world, start, zones, contract)
        if not sights:
            return None
        plan, sight = min(sights, key=lambda pair: pair[0].cost)
        facing = None
    else:
        plan, facing = min(approaches, key=lambda pair: pair[0].cost)
    actor = resolve_story_battler(battler, contract)
    cash_route = certified_cash_safe_transition(route, before.raw, plan)
    loss_debit = single_blackout_cash_bound(before.raw, cash_route)
    controller = FrozenStoryBattleController(actor, (contract,), evolution_rom=route.rom)
    source = runtime.emulator.save_state_bytes()
    used, terminal, result = False, None, None

    def observe_target():
        raw = runtime.reader.read()
        if raw.map_id != contract.map_id or (raw.player_y, raw.player_x) != plan.terminal_at:
            raise ValueError("story interaction boundary changed")
        zones = trainer_sight_zones(
            headers, objects, raw, runtime.reader.read_current_map_objects()
        )
        matched = any(
            not t.defeated
            and all(
                getattr(t, k) == getattr(target, k)
                for k in (
                    "map_id",
                    "sprite_index",
                    "event_flag",
                    "trainer_class",
                    "trainer_set",
                    "at",
                )
            )
            for t in zones
        )
        if leader is not None:
            matched = any(
                o.sprite_index == leader.object_index
                and o.at == leader.at
                and o.picture_id == leader.sprite_id
                for o in runtime.reader.read_current_map_objects()
            )
        if not matched:
            raise ValueError("story target moved or changed before interaction")
        return zones

    def execute():
        nonlocal used, terminal, result
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("story battle is stale or consumed")
        if resolve_story_battler(battler, contract) is not actor:
            raise ValueError("story battle actor changed before execution")
        used = True
        if before_challenge is not None:
            before_challenge(contract)
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(
            cash_route or route,
            destination_map=contract.map_id,
            destination_at=plan.terminal_at,
        )(actions, runtime.reader, runtime.emulator)
        zones = observe_target()
        facing_interruption = None
        if facing is not None:
            # A blocked turn on encounter terrain may start a wild battle after
            # navigation has finished. Reuse the income route's bounded escape;
            # it must restore the same square and facing before any interaction.
            facing_interruption = face_trainer_boundary(
                actions, runtime.reader, facing.value, route_name="story trainer facing"
            )
            zones = observe_target()
        raw = runtime.reader.read()
        if raw.map_id != contract.map_id or (raw.player_y, raw.player_x) != plan.terminal_at:
            raise ValueError("story interaction boundary changed")
        entry = raw
        if sight is not None:
            live = Gen1TraversalObserver(
                runtime.reader,
                hazard_projector=Gen1TrainerSightProjector(
                    route.rom, runtime.reader, full_event_offsets=True
                ),
            ).observe()
            edge = sight_entry_edge(
                live,
                route.route_world.local_graphs[live.map_id].neighbors(live.at),
                zones,
                contract,
            )
            if edge != sight:
                raise ValueError("story sight boundary changed before engagement")
            enter_story_sight(runtime.reader, actions, edge=edge, contract=contract, rom=route.rom)
        else:
            actions.execute(MacroAction(MacroActionKind.INTERACT))
        for _ in range(32):
            raw = runtime.reader.read()
            if raw.battle_state == 2:
                break
            if raw.battle_state or raw.map_id != contract.map_id:
                raise ValueError("unexpected story introduction state")
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=144))
            if runtime.reader.read().battle_state == 0:
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
        else:
            raise RuntimeError("story battle introduction exceeded bound")
        result = controller.run(
            runtime.reader,
            actions,
            objective_id=contract.objective_id,
            battle_plan_id=contract.battle_plan_id,
            expected_map=contract.map_id,
        )
        reward_evidence = None
        if reward is not None and result.outcome == "won" and result.field_ready:
            reward_evidence = reward.settle(
                runtime.reader, actions, before=entry, victory_money=result.money_delta
            )
        if (
            result.outcome not in {"won", "lost"}
            or not result.field_ready
            or not _field_ready(runtime)
        ):
            episode = getattr(result, "episode", None)
            current = runtime.reader.read()
            if (
                result.outcome == "unresolved"
                and result.field_ready is False
                and episode is not None
                and episode.stop_reason == "decision_budget"
                and not episode.battle_won
                and len(episode.decisions) == controller.maximum_decisions
                and episode.final_battle_state == current.battle_state == 2
                and current.map_id == contract.map_id
                and runtime.reader.read_active_trainer_identity() == contract.trainer_identity
                and current.party_hp is not None
                and any(current.party_hp)
            ):
                record = getattr(actions, "record_diagnostic_event", None)
                if callable(record):
                    record("story_battle_decision_budget", dict(
                        stop_reason=episode.stop_reason,
                        decisions_consumed=len(episode.decisions),
                        maximum_decisions=controller.maximum_decisions,
                        battle_won=False, field_ready=False,
                        terminal_state_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                        outcome_and_costs_retained=True,
                        new_controller_inputs=0,
                    ))
                raise StoryBattleDecisionBudgetReached(
                    "story battle reached its bounded decision limit"
                )
            raise RuntimeError("story battle did not settle to a supported field boundary")
        raw = runtime.reader.read()
        if result.outcome == "won":
            if not victory_proved() or (
                raw.badge_bits & contract.victory_badge_bits != contract.victory_badge_bits
            ):
                raise RuntimeError("story victory lacks event or badge proof")
            if completes_objective:
                runtime.observer.latch_verified_facts(objective.completion_facts)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                objective=contract.objective_id,
                objective_completed=completes_objective and result.outcome == "won",
                battle=result.public_dict(),
                reward=reward_evidence,
                support="cartridge_route_and_dialogue",
                facing_interruption=(
                    None if facing_interruption is None else asdict(facing_interruption)
                ),
                automatic_preparation=False,
                source_sha256=sha256(source).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
            ),
        )

    def victory_proved():
        if contract.defeated_event is not None:
            return event_flag_is_set(runtime.reader.read().event_flags, contract.defeated_event)
        from .red_eventless_trainer import eventless_battle_finished

        return eventless_battle_finished(runtime.reader, contract.trainer_identity, won=True)

    def verify(report):
        after, snapshot = capture_player_lesson_snapshot(runtime)
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if not set(lesson["completed_objectives"]) <= set(snapshot["completed_objectives"]):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if result.outcome == "lost":
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        if (
            not victory_proved()
            or after.raw.badge_bits & contract.victory_badge_bits != contract.victory_badge_bits
            or (
                completes_objective
                and contract.objective_id not in snapshot["completed_objectives"]
            )
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:story-battle:"
        + canonical_sha256(
            dict(objective=contract.objective_id, source=sha256(source).hexdigest())
        ),
        GoalKind.ADVANCE_STORY,
        min(1.0, 0.2 + plan.cost / 3000),
        0.4,
        execute,
        verify,
        maximum_cash_debit=loss_debit,
        story_objective_ref=contract.objective_id,
        cash_outcome=(None if loss_debit is None else GoalCashOutcome(
            sha256(source).hexdigest(), "single_trainer", loss_debit)),
    )
