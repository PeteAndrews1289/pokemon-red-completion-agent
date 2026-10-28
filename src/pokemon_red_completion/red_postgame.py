"""Recognize the native Continue menu without ever selecting New Game."""

from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, MapId, event_flag_is_set
from .red_player_field_goals import _field_ready

LEAGUE_EVENTS = (
    EventFlag.BEAT_LORELEI, EventFlag.BEAT_BRUNO, EventFlag.BEAT_AGATHA,
    EventFlag.BEAT_LANCES_ROOM_TRAINER, EventFlag.BEAT_LANCE, EventFlag.BEAT_CHAMPION_RIVAL,
)
PRESERVED_PARTY = (
    "party_count", "party_species_ids", "party_levels", "party_max_hp",
    "party_moves", "badge_bits", "player_money", "bag_items",
)


def continue_menu_visible(rows: tuple[str, ...]) -> bool:
    return (len(rows) == 18 and rows[2][2:10] == "CONTINUE"
            and rows[4][2:10] == "NEW GAME" and rows[6][2:8] == "OPTION")


def require_continue_selection(rows, cursor):
    if (not continue_menu_visible(rows) or cursor.selected_visible_index != 0
            or cursor.maximum_visible_index != 2 or cursor.top_x != 1 or cursor.top_y != 2):
        raise ValueError("native Continue is not the verified selected menu entry")


def continue_action(phase, rows, raw, scene, cursor, *, dialogue, saw_reset):
    """Reuse the qualified Hall/title/summary selector, not a new-game policy."""
    if phase == "hall" and any("NEW GAME" in row for row in rows):
        if not saw_reset:
            raise ValueError("native League event reset was not observed")
        phase = "title"
    if phase == "hall":
        if raw.map_id != int(MapId.HALL_OF_FAME):
            if not saw_reset:
                raise ValueError("native League event reset was not observed")
            return "title", None
        if not scene.queued_movement and (scene.script_stage != 1 or dialogue):
            return phase, MacroAction(MacroActionKind.CONFIRM)
    elif phase == "title":
        if continue_menu_visible(rows):
            require_continue_selection(rows, cursor)
            return "summary", MacroAction(MacroActionKind.CONFIRM)
        if any("NEW GAME" in row for row in rows):
            raise ValueError("Continue unavailable; New Game forbidden")
        return phase, MacroAction(MacroActionKind.OPEN_MENU)
    elif phase == "summary":
        require_continue_selection(rows, cursor)
        if not any("PLAYER" in row for row in rows) or not any("BADGES" in row for row in rows):
            raise ValueError("native Continue summary is unverified")
        return "field", MacroAction(MacroActionKind.CONFIRM)
    return phase, None


def postgame_return_binding(runtime, actions):
    """Mandatory native credits settlement, stopping at the actual Pallet field.

    No nurse, route, capture target, additional story credit or strategic query
    is supplied. Native credits reset temporary League events and may restore
    HP/PP; party identity, levels, moves, stock and earned resources must survive.
    """
    before = runtime.reader.read()
    rows = runtime.reader.read_screen_text_rows()
    completed = set(runtime.adapter.graph.completed_ids(runtime.adapter.observe().game_state))
    native_hall = (
        before.map_id == int(MapId.HALL_OF_FAME)
        and event_flag_is_set(before.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
    )
    resumable = "enter_hall_of_fame" in completed and (
        before.map_id == int(MapId.HALL_OF_FAME)
        or not before.game_started or continue_menu_visible(rows)
    )
    if (
        not (native_hall or resumable) or before.battle_state != 0
        or not before.party_count or before.player_money is None or before.bag_items is None
        or runtime.emulator.pressed_buttons
    ):
        return None
    source = runtime.emulator.save_state_bytes()
    protected = {name: getattr(before, name) for name in PRESERVED_PARTY}
    boxes = runtime.reader.read_all_box_states()
    dex = runtime.reader.read_pokedex_state()
    pc = runtime.reader.read_pc_items()
    used, terminal = False, None

    def terminal_valid():
        raw = runtime.reader.read()
        return (
            raw.map_id == int(MapId.PALLET_TOWN) and _field_ready(runtime)
            and not any(event_flag_is_set(raw.event_flags, e) for e in LEAGUE_EVENTS)
            and all(getattr(raw, name) == value for name, value in protected.items())
            and runtime.reader.read_all_box_states() == boxes
            and runtime.reader.read_pokedex_state() == dex
            and runtime.reader.read_pc_items() == pc
        )

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("postgame return is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        phase = "hall" if before.map_id == int(MapId.HALL_OF_FAME) else "title"
        saw_reset, phases = not native_hall, []
        for pulse in range(900):
            raw = runtime.reader.read()
            saw_reset |= not event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
            if phase == "field" and raw.map_id == int(MapId.PALLET_TOWN) and _field_ready(runtime):
                if not terminal_valid():
                    raise RuntimeError("native Continue terminal did not preserve earned state")
                break
            scene = (runtime.reader.read_final_league_scene()
                     if raw.map_id == int(MapId.HALL_OF_FAME) else None)
            next_phase, action = continue_action(
                phase, runtime.reader.read_screen_text_rows(), raw, scene,
                runtime.reader.read_menu_cursor_state(),
                dialogue=runtime.reader.read_bottom_dialogue_box_visible(), saw_reset=saw_reset)
            if next_phase != phase:
                phases.append(dict(pulse=pulse, before=phase, after=next_phase))
            phase = next_phase
            if action is not None:
                actions.execute(action)
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
        else:
            raise RuntimeError("existing native Continue exhausted its pulse guard")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a, runtime.emulator.frame_count - f,
            dict(native_postgame_return_verified=True, phases=phases,
                 saw_native_reset=saw_reset, new_game_selected=False,
                 cash_bag_party_dex_boxes_pc_preserved=True, field_ready=True,
                 learned_return=False, model_queries=0, story_credit=False,
                 source_sha256=sha256(source).hexdigest(),
                 terminal_sha256=sha256(terminal).hexdigest()),
        )

    def verify(report):
        if (
            terminal is None or runtime.emulator.save_state_bytes() != terminal
            or not terminal_valid()
            or report.evidence.get("source_sha256") != sha256(source).hexdigest()
            or report.evidence.get("terminal_sha256") != sha256(terminal).hexdigest()
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:postgame-return:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL, 0.1, 0.0, execute, verify, maximum_cash_debit=0,
    )
