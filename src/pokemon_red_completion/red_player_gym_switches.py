"""Observable trash-can search; never read the randomly chosen lock indices.

The search is deterministic mechanic support, not a learned puzzle policy.
Only visible attempts and opened-lock events inform its next interaction.
"""

from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector, TrainerFacing
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import MapId, event_flag_is_set
from .red_pc_storage import face_pc_boundary
from .red_player_field_goals import _field_ready
from .route_plan import RoutePlanningError

# Visible room geometry, in cartridge text/sign order. No hidden solution state.
CANS = tuple((y, x) for x in (1, 3, 5, 7, 9) for y in (7, 9, 11))


def visible_locks(raw):
    if raw.event_flags is None:
        raise ValueError("Gym lock observation is unavailable")
    return (event_flag_is_set(raw.event_flags, 0x161), event_flag_is_set(raw.event_flags, 0x160))


def next_can(history, locks):
    if all(locks):
        return None
    if locks[0]:
        first = next(
            (r["can"] for r in reversed(history) if not r["before"][0] and r["after"][0]), None
        )
        if first is None:
            raise ValueError("open first lock lacks observed interaction history")
        y, x = CANS[first]
        adjacent = [i for i, (yy, xx) in enumerate(CANS) if abs(yy - y) + abs(xx - x) == 2]
        # Gen I can select the top-left can after ANY first switch. This is a legal retry,
        # not a read of the game's randomly selected answer.
        if 0 not in adjacent:
            adjacent.append(0)
        tries = sum(r["before"][0] and r.get("first_can") == first for r in history)
        return adjacent[tries % len(adjacent)]
    searched = [r["can"] for r in history if not r["before"][0]]
    return (searched[-1] + 1) % len(CANS) if searched else 0


def can_stances(index):
    y, x = CANS[index]
    return tuple(((y - f.delta[0], x - f.delta[1]), f) for f in TrainerFacing)


def gym_switch_binding(runtime, actions, *, route, history, record):
    if not _field_ready(runtime) or runtime.reader.read().map_id != int(MapId.VERMILION_GYM):
        return None
    raw = runtime.reader.read()
    locks = visible_locks(raw)
    index = next_can(history, locks)
    if index is None:
        return None
    start = Gen1TraversalObserver(
        runtime.reader,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    plans = []
    for at, facing in can_stances(index):
        try:
            plan = route.route_world.plan_feasible_to_map(start, raw.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        plans.append((plan, facing))
    if not plans:
        return None
    plan, facing = min(plans, key=lambda r: r[0].cost)
    source = runtime.emulator.save_state_bytes()
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Gym switch interaction is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=raw.map_id, destination_at=plan.terminal_at)(
            actions, runtime.reader, runtime.emulator
        )
        face_pc_boundary(actions, runtime.reader, facing.value)
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
        for _ in range(32):
            if _field_ready(runtime):
                break
            actions.execute(MacroAction(MacroActionKind.CANCEL))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=60))
        after = runtime.reader.read()
        for key in (
            "map_id",
            "party_species_ids",
            "party_moves",
            "party_hp",
            "party_pp",
            "party_status",
            "player_money",
            "bag_items",
            "badge_bits",
            "battle_state",
        ):
            if getattr(after, key) != getattr(raw, key):
                raise RuntimeError("Gym search changed protected " + key)
        if not _field_ready(runtime):
            raise RuntimeError("Gym search failed to settle")
        row = dict(can=index, before=list(locks), after=list(visible_locks(after)))
        if locks[0]:
            row["first_can"] = next(
                r["can"] for r in reversed(history) if not r["before"][0] and r["after"][0]
            )
        record(row)
        history.append(row)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="visible_trash_can_search",
                attempt=row,
                objective_completed=False,
                hidden_lock_indices_read=False,
            ),
        )

    def verify(report):
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:gym-can:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, 0.02 + plan.cost / 3000),
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )
