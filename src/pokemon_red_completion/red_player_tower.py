"""Current-party Tower boundaries; combat learned, rewards and transport mechanical."""

from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .battle_runtime import (
    BattleRuntimeTiming,
    advance_battle_to_policy_boundary,
    note_observed_battle_exit,
)
from .gen1_cartridge import wild_tables
from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from .gen1_trainer_sight import Gen1TrainerSightProjector, TrainerFacing
from .gen1_traversal import cut_capabilities, map_object_events
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .local_router import without_coordinates
from .observation import event_flag_is_set
from .red_blackout_recovery import settle_red_blackout
from .red_goal_skills import _raw_party_fully_restored
from .red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256
from .red_pc_storage import face_pc_boundary
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .red_trainer_evolution import RedTrainerEvolutionGuard
from .rom import verify_rom_bytes
from .route_executor import TraversalSnapshot
from .route_plan import RoutePlanningError
from .wild_party_flee import validate_flee_party


def marowak_pending(raw):
    return bool(
        raw.map_id == 147
        and raw.event_flags is not None
        and len(raw.event_flags) * 8 > 271
        and not event_flag_is_set(raw.event_flags, 271)
        and dict(raw.bag_items or ()).get(72) == 1
    )


def _origin(runtime, route):
    return Gen1TraversalObserver(
        runtime.reader,
        capability_projector=cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()


class _MarowakEscapeHandoff(Exception):
    """The incidental escape ends in the exact new ghost, not free field control."""


class _MarowakEscapeExecutor:
    """Stop the ordinary RUN handler before it can act in the one-off battle."""

    def __init__(self, delegate, reader):
        self.delegate, self.reader = delegate, reader
        self.encounter = reader.read()
        self.escaped = None
        if (
            not marowak_pending(self.encounter)
            or self.encounter.battle_state != 1
            or (self.encounter.player_y, self.encounter.player_x) != (16, 10)
            or (self.encounter.enemy_species_id, self.encounter.enemy_level) == (145, 30)
        ):
            raise ValueError("ordinary Tower escape lacks its exact pending gate encounter")

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def _observe(self):
        raw = self.reader.read()
        same_tile = (raw.map_id, raw.player_y, raw.player_x) == (147, 16, 10)
        same_enemy = (raw.enemy_species_id, raw.enemy_level) == (
            self.encounter.enemy_species_id, self.encounter.enemy_level
        )
        if raw.battle_state == 0 and same_tile and same_enemy and raw.battle_result == 2:
            validate_flee_party(
                self.encounter, raw, allow_new_faints=True, allow_status_changes=True
            )
            if not self.reader.read_input_readiness().ready:
                self.escaped = raw
        if raw.battle_state == 1 and not same_enemy:
            if (
                self.escaped is None
                or not same_tile
                or not marowak_pending(raw)
                or (raw.enemy_species_id, raw.enemy_level) != (145, 30)
                or raw.battle_result != 0
                or type(raw.enemy_hp) is not int or raw.enemy_hp <= 0
                or type(raw.enemy_max_hp) is not int or raw.enemy_hp > raw.enemy_max_hp
                or self.encounter.party_stats is None
                or raw.party_stats != self.encounter.party_stats
            ):
                raise ValueError("ordinary Tower escape has an unverified new battle")
            validate_flee_party(
                self.encounter, raw, allow_new_faints=True, allow_status_changes=True
            )
            note_observed_battle_exit()
            raise _MarowakEscapeHandoff

    def execute(self, action):
        self._observe()
        result = self.delegate.execute(action)
        self._observe()
        return result


def marowak_binding(runtime, actions, *, route, battler, before_challenge=None):
    """Explicit opt-in of the existing K wild-knockout actor to the unique ghost."""
    raw = runtime.reader.read()
    if not marowak_pending(raw):
        return None
    engaged = raw.battle_state == 1 and (raw.player_y, raw.player_x) == (16, 10)
    if not engaged and not _field_ready(runtime):
        return None
    if (battler.model_sha256, battler.qualification_sha256) != (
        FROZEN_K_SHA256,
        K_QUALIFICATION_SHA256,
    ):
        raise ValueError("Marowak requires exact qualified K wild actor")
    verify_rom_bytes(route.rom)
    # Do not let ordinary route execution enter/flee the one-off script.
    world = route.route_world
    safe = replace(
        world,
        # Live terrain rebuilds regenerate local graphs from these blockers.
        # Keep the one-off trigger excluded during execution/replanning too.
        object_blockers={**world.object_blockers,
            147: world.object_blockers[147] | {(16, 10)}},
        local_graphs={
            **world.local_graphs,
            147: without_coordinates(world.local_graphs[147], {(16, 10)}),
        },
    )
    approach = replace(route, route_world=safe, destination_map=147, destination_at=(16, 11))
    if not engaged:
        try:
            safe.plan_feasible_to_map(_origin(runtime, approach), 147, goal_at=(16, 11))
        except RoutePlanningError:
            return None
    source = runtime.emulator.save_state_bytes()
    used, terminal, won = False, None, False

    def execute():
        nonlocal used, terminal, won
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("Marowak boundary is stale or consumed")
        used = True
        if before_challenge is not None:
            before_challenge()
        a, f = actions.actions_executed, runtime.emulator.frame_count
        if not engaged:
            approach(actions, runtime.reader, runtime.emulator)
            if not _field_ready(runtime) or (
                runtime.reader.read().player_y,
                runtime.reader.read().player_x,
            ) != (16, 11):
                raise ValueError("Marowak approach differs")
            actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
        ordinary_flee = None
        approach_step_pending = not engaged
        for _ in range(32):
            current = runtime.reader.read()
            if (
                approach_step_pending
                and marowak_pending(current)
                and (current.player_y, current.player_x) == (16, 11)
                and current.battle_state == 1
            ):
                # Encounter arbitration may interrupt LEFT before leaving the
                # verified adjacent stance. This is not the one-off ghost.
                advance_battle_to_policy_boundary(
                    runtime.reader, actions, expected_map=147, expected_battle_state=1,
                    timing=BattleRuntimeTiming(), label="ordinary Marowak approach encounter",
                )
                current = runtime.reader.read()
                if (current.enemy_species_id, current.enemy_level) == (145, 30) or (
                    current.enemy_level, current.enemy_species_id
                ) not in wild_tables(route.rom).get(147, ()):
                    raise ValueError("Marowak approach has an unlisted ordinary opponent")
                if ordinary_flee is None:
                    ordinary_flee = Gen1WildFleeHandler(
                        actions, runtime.reader, maximum_flees=2, stabilization_frames=120,
                        route_name="ordinary encounter before Marowak",
                        allow_party_faints=True, emulator=runtime.emulator,
                    )
                else:
                    ordinary_flee.executor = actions
                ordinary_flee.handle(TraversalSnapshot(147, (16, 11), False, "wild_battle"))
                returned = runtime.reader.read()
                if (
                    not _field_ready(runtime)
                    or not marowak_pending(returned)
                    or (returned.player_y, returned.player_x) != (16, 11)
                ):
                    raise ValueError("Marowak approach escape lost its settled boundary")
                record = getattr(actions, "record_diagnostic_event", None)
                if callable(record):
                    record("ordinary_wild_before_marowak", dict(
                        actor="rule_based_support", species=current.enemy_species_id,
                        level=current.enemy_level, ghost_completed=False, model_queries=0,
                        boundary="adjacent_approach", pending_exact_marowak_handoff=False,
                        free_field_escape_verified=True,
                    ))
                actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
                continue
            if not marowak_pending(current) or (current.player_y, current.player_x) != (16, 10):
                raise ValueError("Marowak introduction left its scope")
            approach_step_pending = False
            if current.battle_state == 1:
                advance_battle_to_policy_boundary(
                    runtime.reader, actions, expected_map=147, expected_battle_state=1,
                    timing=BattleRuntimeTiming(), label="Tower gate encounter",
                )
                current = runtime.reader.read()
                if (current.enemy_species_id, current.enemy_level) == (145, 30):
                    break
                # A random encounter can win the native arbitration on the
                # same trigger tile. Never call that Gastly the scripted ghost,
                # nor relax the ghost identity check. Only ROM-listed ordinary
                # encounters may use the existing bounded transport escape.
                if (current.enemy_level, current.enemy_species_id) not in wild_tables(
                    route.rom
                ).get(147, ()):
                    raise ValueError(
                        "Tower trigger has an unlisted opponent: "
                        f"species={current.enemy_species_id}, level={current.enemy_level}"
                    )
                if ordinary_flee is None:
                    ordinary_flee = Gen1WildFleeHandler(
                        _MarowakEscapeExecutor(actions, runtime.reader), runtime.reader,
                        maximum_flees=2, stabilization_frames=120,
                        route_name="ordinary encounter before Marowak",
                        allow_party_faints=True, emulator=runtime.emulator,
                    )
                else:
                    # Each ordinary encounter has its own observed identity;
                    # keep the handler's accumulated flee budget, not an old
                    # encounter's exit certificate.
                    ordinary_flee.executor = _MarowakEscapeExecutor(actions, runtime.reader)
                handed_off = False
                try:
                    ordinary_flee.handle(
                        TraversalSnapshot(147, (16, 10), False, "wild_battle")
                    )
                except _MarowakEscapeHandoff:
                    handed_off = True
                record = getattr(actions, "record_diagnostic_event", None)
                if callable(record):
                    record("ordinary_wild_before_marowak", dict(
                        actor="rule_based_support", species=current.enemy_species_id,
                        level=current.enemy_level, ghost_completed=False, model_queries=0,
                        pending_exact_marowak_handoff=handed_off,
                        free_field_escape_verified=not handed_off,
                    ))
                if handed_off:
                    break
                continue
            if current.battle_state:
                raise ValueError("Marowak introduction left its wild scope")
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=144))
            if runtime.reader.read().battle_state == 0:
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
        else:
            raise RuntimeError("Marowak introduction budget")
        advance_battle_to_policy_boundary(
            runtime.reader,
            actions,
            expected_map=147,
            expected_battle_state=1,
            timing=BattleRuntimeTiming(),
            label="revealed Marowak",
        )
        entry = runtime.reader.read()
        if (
            not marowak_pending(entry)
            or entry.enemy_species_id != 145
            or entry.enemy_level != 30
            or (entry.player_y, entry.player_x) != (16, 10)
        ):
            raise ValueError(
                "Scope did not reveal the exact level30 Marowak: "
                f"species={entry.enemy_species_id}, level={entry.enemy_level}, "
                f"at={(entry.player_y, entry.player_x)}"
            )
        evolution = RedTrainerEvolutionGuard.from_rom(route.rom, runtime.emulator)

        def guard(current):
            if (
                current.battle_state != 1
                or current.map_id != 147
                or current.enemy_species_id != 145
                or current.enemy_level != 30
                or current.bag_items != entry.bag_items
                or current.player_money != entry.player_money
                or current.party_species_ids != entry.party_species_ids
            ):
                raise ValueError("Marowak battle identity/resources changed")

        episode = battler.run_wild_training(
            runtime.reader,
            actions,
            expected_map=147,
            timing=BattleRuntimeTiming(),
            decision_guard=guard,
        )
        lost = episode.stop_reason == "party_defeated"
        if lost:
            settle_red_blackout(actions, runtime.reader, runtime.emulator)
        else:
            if not episode.battle_won:
                raise RuntimeError("Marowak learned battle stopped: " + episode.stop_reason)
            for _ in range(64):
                current = runtime.reader.read()
                if _field_ready(runtime) and event_flag_is_set(current.event_flags, 271):
                    break
                if current.map_id != 147 or current.battle_state:
                    raise ValueError("Marowak victory settlement left field")
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
        final = runtime.reader.read()
        won = event_flag_is_set(final.event_flags, 271)
        if (
            not _field_ready(runtime)
            or won == lost
            or not evolution.matches(entry, final)
            or final.bag_items != entry.bag_items
            or (not lost and final.player_money != entry.player_money)
        ):
            raise ValueError("Marowak outcome lacks native event or specimen preservation")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="ghost_trigger_and_settlement",
                learned_combat=True,
                battler_interface="frozen_k_wild_training_development",
                fit=False,
                native_ghost_event=won,
                lost=lost,
                objective_completed=False,
            ),
        )

    def verify(report):
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return (
            GoalVerification.succeeded()
            if won
            else GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        )

    return ExecutableGoalBinding(
        "pokemon.red:ghost-marowak:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL if engaged else GoalKind.ADVANCE_STORY,
        0.2,
        0.4,
        execute,
        verify,
        maximum_cash_debit=(raw.player_money + 1) // 2,
    )


def fuji_phase(raw):
    if raw.battle_state or raw.event_flags is None or raw.bag_items is None:
        return None
    if (
        raw.map_id == 148
        and all(event_flag_is_set(raw.event_flags, e) for e in (271, 273, 274, 275))
        and not event_flag_is_set(raw.event_flags, 279)
    ):
        return "rescue", 4, 149
    if (
        raw.map_id == 149
        and all(event_flag_is_set(raw.event_flags, e) for e in (279, 1231))
        and not dict(raw.bag_items).get(73)
        and not event_flag_is_set(raw.event_flags, 296)
        and len(raw.bag_items) < 20
    ):
        return "flute", 5, 149
    return None


def fuji_binding(runtime, actions, *, route):
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    spec = fuji_phase(raw)
    if spec is None:
        return None
    phase, index, destination = spec
    verify_rom_bytes(route.rom)
    target = next(o for o in map_object_events(route.rom, {raw.map_id}) if o.object_index == index)

    def present():
        return any(
            o.sprite_index == index and o.picture_id == 22 and o.at == target.at
            for o in runtime.reader.read_current_map_objects()
        )

    if target.sprite_id != 22 or not present():
        raise ValueError("Fuji cartridge/live object differs")
    candidates = []
    for facing in TrainerFacing:
        at = (target.y - facing.delta[0], target.x - facing.delta[1])
        if min(at) < 0:
            continue
        try:
            plan = route.route_world.plan_feasible_to_map(
                _origin(runtime, route), raw.map_id, goal_at=at
            )
        except RoutePlanningError:
            continue
        candidates.append((plan, facing))
    if not candidates:
        return None
    plan, facing = min(candidates, key=lambda p: p[0].cost)
    source = runtime.emulator.save_state_bytes()
    used = False
    terminal = None

    def achieved(current):
        return (
            current.map_id == destination
            and all(event_flag_is_set(current.event_flags, e) for e in (279, 1231))
            and (
                phase == "rescue"
                or (
                    event_flag_is_set(current.event_flags, 296)
                    and dict(current.bag_items or ()).get(73) == 1
                )
            )
        )

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Fuji interaction is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=raw.map_id, destination_at=plan.terminal_at)(
            actions, runtime.reader, runtime.emulator
        )
        if not present() or fuji_phase(runtime.reader.read()) != spec:
            raise ValueError("Fuji prerequisite changed")
        face_pc_boundary(actions, runtime.reader, facing.value)
        for _ in range(128):
            current = runtime.reader.read()
            if current.battle_state or current.map_id not in {raw.map_id, destination}:
                raise ValueError("Fuji unexpected state")
            if achieved(current) and _field_ready(runtime):
                break
            actions.execute(
                MacroAction(
                    MacroActionKind.INTERACT if _field_ready(runtime) else MacroActionKind.CONFIRM
                )
            )
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=144))
        final = runtime.reader.read()
        bag = dict(raw.bag_items)
        if phase == "flute":
            bag[73] = 1
        if (
            not achieved(final)
            or not _field_ready(runtime)
            or dict(final.bag_items or ()) != bag
            or any(
                getattr(final, k) != getattr(raw, k)
                for k in (
                    "party_species_ids",
                    "party_hp",
                    "party_pp",
                    "party_status",
                    "player_money",
                    "badge_bits",
                )
            )
        ):
            raise ValueError("Fuji native outcome or protected resources differ")
        capture_player_lesson_snapshot(runtime)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="native_fuji_interaction",
                phase=phase,
                learned=False,
                objective_completed=phase == "flute",
            ),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and _field_ready(runtime)
            and achieved(runtime.reader.read())
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:fuji:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        0.05,
        0.02,
        execute,
        verify,
    )


def healthy_lavender_return(runtime, actions, *, route):
    raw = runtime.reader.read()
    if (
        not _field_ready(runtime)
        or not dict(raw.bag_items or ()).get(73)
        or not _raw_party_fully_restored(raw)
        or raw.map_id == 141
    ):
        return None
    try:
        route.route_world.plan_feasible_to_map(_origin(runtime, route), 141, goal_at=(3, 3))
    except RoutePlanningError:
        return None
    source = runtime.emulator.save_state_bytes()
    used = False
    terminal = None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("healthy return stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=141, destination_at=(3, 3))(
            actions, runtime.reader, runtime.emulator
        )
        final = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or not _raw_party_fully_restored(final)
            or final.map_id != 141
            or any(
                getattr(raw, k) != getattr(final, k)
                for k in (
                    "bag_items",
                    "player_money",
                    "party_species_ids",
                    "badge_bits",
                    "event_flags",
                )
            )
        ):
            raise ValueError("healthy Lavender return did not preserve resources")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(support="healthy_lavender_return", heals=0, learned=False),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None and runtime.emulator.save_state_bytes() == terminal
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:tower-center:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        0.05,
        0.02,
        execute,
        verify,
    )
