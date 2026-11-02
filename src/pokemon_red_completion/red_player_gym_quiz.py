"""Quote one reachable native quiz interaction without a scripted gym route.

Correct answers and panel coordinates are disclosed cartridge mechanics, not
learned puzzle knowledge. This binding opens one gate and never awards a badge.
"""

from dataclasses import replace
from hashlib import sha256

from .blaine import GYM_GATE_EVENTS, QUIZ_CORRECT_ANSWERS, QUIZ_TEXT_PULSES, _answer_quiz
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .rom import verify_rom_bytes
from .route_plan import RoutePlanningError

OBJECTIVE = "defeat_blaine"
# Exact-revision hidden-event panel coordinates, approached from below.
# pret/pokered data/events/hidden_events.asm, CINNABAR_GYM entries1..6.
QUIZ_APPROACHES = ((8, 15), (2, 10), (8, 9), (14, 9), (14, 1), (8, 1))


def cinnabar_quiz_option(runtime, actions, *, route):
    """Offer the cheapest actually reachable closed panel, with no inputs."""
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    if (
        raw.map_id != int(MapId.CINNABAR_GYM)
        or raw.event_flags is None
        or raw.bag_items is None
        or raw.player_money is None
        or not raw.party_hp
        or not any(raw.party_hp)
        or OBJECTIVE
        not in {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
    ):
        return None
    verify_rom_bytes(route.rom)
    world = route.route_world.with_current_observation(runtime.reader)
    route = replace(route, route_world=world)
    start = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    candidates = []
    for index, at in enumerate(QUIZ_APPROACHES, 1):
        if event_flag_is_set(raw.event_flags, int(GYM_GATE_EVENTS[index])):
            continue
        try:
            plan = world.plan_feasible_to_map(start, int(MapId.CINNABAR_GYM), goal_at=at)
        except RoutePlanningError:
            continue
        candidates.append((plan.cost, index, at))
    if not candidates:
        return None
    cost, index, at = min(candidates)
    gate = int(GYM_GATE_EVENTS[index])
    source = runtime.emulator.save_state_bytes()
    used, terminal, retained_report = False, None, None

    def execute():
        nonlocal used, terminal, retained_report
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("quiz interaction is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        reader, em = runtime.reader, runtime.emulator
        boxes, dex, pc = (
            reader.read_all_box_states(),
            reader.read_pokedex_state(),
            reader.read_pc_items(),
        )
        replace(route, destination_map=int(MapId.CINNABAR_GYM), destination_at=at)(
            actions, reader, em
        )
        arrival = reader.read()
        if (
            not _field_ready(runtime)
            or arrival.map_id != raw.map_id
            or (arrival.player_y, arrival.player_x) != at
            or arrival.event_flags != raw.event_flags
        ):
            raise RuntimeError("quiz approach changed its native boundary")
        _answer_quiz(
            actions,
            reader,
            em,
            index,
            QUIZ_CORRECT_ANSWERS[index - 1],
            QUIZ_TEXT_PULSES[index - 1],
            correct_only=True,
        )
        after, after_lesson = capture_player_lesson_snapshot(runtime)
        expected_events = bytearray(raw.event_flags)
        expected_events[gate // 8] |= 1 << (gate % 8)
        if (
            not _field_ready(runtime)
            or after.raw.map_id != raw.map_id
            or (after.raw.player_y, after.raw.player_x) != at
            or after.raw.event_flags != bytes(expected_events)
            or after_lesson != lesson
            or any(
                getattr(after.raw, name) != getattr(raw, name)
                for name in (
                    "bag_items",
                    "player_money",
                    "badge_bits",
                    "party_hp",
                    "party_status",
                    "party_species_ids",
                    "party_levels",
                    "party_moves",
                    "party_pp",
                )
            )
            or reader.read_all_box_states() != boxes
            or reader.read_pokedex_state() != dex
            or reader.read_pc_items() != pc
        ):
            raise RuntimeError("quiz did not open only its gate while preserving resources")
        terminal = em.save_state_bytes()
        retained_report = GoalExecutionReport(
            actions.actions_executed - a,
            em.frame_count - f,
            dict(
                support="observed_correct_quiz_interaction",
                objective=OBJECTIVE,
                objective_completed=False,
                quiz_index=index,
                native_gate_opened=True,
                learned_puzzle=False,
                trainer_battles=0,
                purchases=0,
                sales=0,
            ),
        )
        return retained_report

    def verify(report):
        if (
            not used
            or terminal is None
            or report != retained_report
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    binding = ExecutableGoalBinding(
        f"pokemon.red:quiz-gate:{index}:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, (cost + 40) / 3000),
        0.05,
        execute,
        verify,
        maximum_cash_debit=0,
        story_objective_ref=OBJECTIVE,
    )
    return binding, OptionChallenge(False, False, 0.0, 0.0, 0.0)
