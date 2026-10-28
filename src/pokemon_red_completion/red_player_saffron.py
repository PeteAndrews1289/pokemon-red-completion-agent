"""Current-party access adapter; model selects the goal, mechanics open the gate."""

from dataclasses import replace
from hashlib import sha256

from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .lavender import DEFAULT_LAVENDER_TIMING, _close_menus
from .observation import SAFFRON_GUARD_ACCESS_MASK, ItemId, MapId
from .red_goal_skills import _raw_party_fully_restored
from .red_player_field_goals import _field_ready
from .red_player_tower import _origin
from .route_plan import RoutePlanningError
from .saffron import FRESH_WATER_PRICE, run_saffron_access_chapter


def saffron_access_ready(raw):
    """Admit any healthy actual party, never the old Eevee preparation chapter."""
    bag = dict(raw.bag_items or ())
    return bool(
        not raw.battle_state
        and _raw_party_fully_restored(raw)
        and raw.status_flags_1 is not None
        and not raw.status_flags_1 & SAFFRON_GUARD_ACCESS_MASK
        and raw.player_money is not None
        and raw.player_money >= FRESH_WATER_PRICE
        and raw.bag_items is not None
        and len(bag) < 20
        and not any(bag.get(i) for i in (ItemId.FRESH_WATER, ItemId.SODA_POP, ItemId.LEMONADE))
    )


def saffron_access_binding(runtime, actions, *, route):
    raw = runtime.reader.read()
    objective = runtime.adapter.graph.objective("reach_saffron")
    if (
        not _field_ready(runtime)
        or not saffron_access_ready(raw)
        or objective.id
        not in {
            o.id
            for o in runtime.adapter.graph.available_objectives(
                runtime.adapter.observe().game_state
            )
        }
    ):
        return None
    try:
        plan = route.route_world.plan_feasible_to_map(
            _origin(runtime, route), int(MapId.CELADON_POKECENTER), goal_at=(3, 3)
        )
    except RoutePlanningError:
        return None
    source = runtime.emulator.save_state_bytes()
    used = False
    terminal = None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Saffron access stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=int(MapId.CELADON_POKECENTER), destination_at=(3, 3))(
            actions, runtime.reader, runtime.emulator
        )
        arrival = runtime.reader.read()
        if not saffron_access_ready(arrival) or any(
            getattr(arrival, key) != getattr(raw, key)
            for key in (
                "player_money",
                "bag_items",
                "party_species_ids",
                "badge_bits",
                "event_flags",
            )
        ):
            raise ValueError("Saffron approach needs recovery or changed protected resources")
        report = run_saffron_access_chapter(runtime.emulator, runtime.reader, actions)
        if not _field_ready(runtime):
            _close_menus(actions, runtime.reader, DEFAULT_LAVENDER_TIMING)
        final = runtime.reader.read()
        if (
            not report.passed
            or not _field_ready(runtime)
            or not _raw_party_fully_restored(final)
            or final.map_id != int(MapId.SAFFRON_POKECENTER)
            or not final.status_flags_1 & SAFFRON_GUARD_ACCESS_MASK
            or final.player_money != raw.player_money - FRESH_WATER_PRICE
            or any(
                getattr(final, key) != getattr(raw, key)
                for key in ("bag_items", "party_species_ids", "badge_bits", "event_flags")
            )
        ):
            raise ValueError("Saffron native access or protected resources not verified")
        runtime.observer.latch_verified_facts(objective.completion_facts)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                objective=objective.id,
                objective_completed=True,
                support="existing_current_party_vending_guard_navigation",
                purchases=1,
                purchase_cost=FRESH_WATER_PRICE,
                trainer_battles=0,
                chapter=report.public_dict(),
                automatic_objectives=[],
            ),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None and runtime.emulator.save_state_bytes() == terminal
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:saffron-access:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, (plan.cost + 400) / 3000),
        0.05,
        execute,
        verify,
        story_objective_ref=objective.id,
        maximum_cash_debit=FRESH_WATER_PRICE,
    )


def saffron_settlement_binding(runtime, actions):
    """Close retained nurse dialogue; native guard and location must already exist."""
    raw = runtime.reader.read()
    if (
        raw.map_id != int(MapId.SAFFRON_POKECENTER)
        or raw.battle_state
        or raw.status_flags_1 is None
        or not raw.status_flags_1 & SAFFRON_GUARD_ACCESS_MASK
        or not _raw_party_fully_restored(raw)
        or not runtime.reader.read_input_readiness().ready
        or not runtime.reader.read_bottom_dialogue_box_visible()
    ):
        return None
    source = runtime.emulator.save_state_bytes()
    terminal = None
    used = False

    def execute():
        nonlocal terminal, used
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("Saffron settlement stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        _close_menus(actions, runtime.reader, DEFAULT_LAVENDER_TIMING)
        if not _field_ready(runtime) or runtime.reader.read() != raw:
            raise ValueError("Saffron settlement changed semantic state or left dialogue")
        objective = runtime.adapter.graph.objective("reach_saffron")
        runtime.observer.latch_verified_facts(objective.completion_facts)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(support="close_earned_saffron_nurse_dialogue", purchases=0, heals=0),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None and runtime.emulator.save_state_bytes() == terminal
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:saffron-settlement:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL,
        0.01,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )
