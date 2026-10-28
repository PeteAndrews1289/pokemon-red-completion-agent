"""Settle observed in-flight native movement, never supply a walking route."""

from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_forced_motion import SPINNER_MAP_IDS, spinner_sequences
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot


def interrupted_pewter_escort_binding(runtime, actions, *, maximum_waits=32, settle_frames=120):
    """Finish only the already running east-exit guide, not a Brock approach.

    Pinned Red Pewter scripts4/5/6 finish an NPC escort, its final text and
    native reset. No directional input, new interaction or yes/no choice is
    allowed. This is mandatory controller settlement, not learned strategy.
    """
    if any(type(v) is not int or v <= 0 for v in (maximum_waits, settle_frames)):
        raise ValueError("escort settlement bounds must be positive integers")
    raw = runtime.reader.read()
    if raw.map_id != 2 or raw.battle_state or runtime.emulator.pressed_buttons:
        return None
    chapter = runtime.reader.read_pewter_chapter_state(raw)
    controls = chapter.controls
    if (
        chapter.beat_brock
        or chapter.local_script not in {4, 5, 6}
        or controls.joy_ignore != 240
        or _field_ready(runtime)
        or (chapter.local_script == 4 and controls.npc_movement_script_table not in {0, 3})
    ):
        return None
    source = runtime.emulator.save_state_bytes()
    _, lesson = capture_player_lesson_snapshot(runtime)
    used, terminal, retained = False, None, None

    def execute():
        nonlocal used, terminal, retained
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("escort settlement is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        boxes, dex, pc = (runtime.reader.read_all_box_states(),
            runtime.reader.read_pokedex_state(), runtime.reader.read_pc_items())
        confirms = 0
        for _ in range(maximum_waits):
            current = runtime.reader.read()
            phase = runtime.reader.read_pewter_chapter_state(current)
            if (current.map_id != raw.map_id or current.battle_state
                or phase.local_script not in {0, 4, 5, 6}):
                raise RuntimeError("escort settlement left its native script")
            if phase.local_script == 0 and _field_ready(runtime):
                break
            # Script4 shows its final text only after the native walk finishes.
            # Never send buttons while the escort still owns simulated input.
            if (phase.local_script == 4 and not phase.controls.npc_movement_script_table
                and not phase.controls.simulated_joypad_index
                and runtime.reader.read_bottom_dialogue_box_visible()):
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
                confirms += 1
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=settle_frames))
        else:
            raise RuntimeError("escort settlement exhausted its wait bound")
        after = runtime.reader.read()
        _, after_lesson = capture_player_lesson_snapshot(runtime)
        if (after_lesson != lesson or any(getattr(after, name) != getattr(raw, name)
            for name in ("player_money", "bag_items", "badge_bits", "event_flags", "party_hp",
                "party_max_hp", "party_pp", "party_status", "party_species_ids", "party_levels",
                "party_moves", "party_stats"))
            or runtime.reader.read_all_box_states() != boxes
            or runtime.reader.read_pokedex_state() != dex or runtime.reader.read_pc_items() != pc):
            raise RuntimeError("escort settlement changed protected resources")
        terminal = runtime.emulator.save_state_bytes()
        retained = GoalExecutionReport(actions.actions_executed-a, runtime.emulator.frame_count-f,
            dict(mechanic="native_pewter_escort_settlement", learned_recovery=False,
                model_queries=0, directional_inputs=0, dialogue_confirms=confirms,
                endpoint=(after.player_y, after.player_x), verified=True))
        return retained

    def verify(report):
        if (terminal is None or report != retained or not _field_ready(runtime)
            or runtime.emulator.save_state_bytes() != terminal):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding("pokemon.red:retained-pewter-escort:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL, 0.04, 0.02, execute, verify, maximum_cash_debit=0)


def _purified_message_custody(runtime):
    from .red_party import PokemonRedPartyReader

    party = PokemonRedPartyReader(runtime.emulator)
    return (party.preparation_specimen_refs(),
            tuple((m.species_id, m.level, m.experience) for m in party.read().members),
            runtime.reader.read_all_box_states(), runtime.reader.read_pokedex_state(),
            runtime.reader.read_pc_items())


def _interrupted_purified_message_binding(runtime, actions, *, settle_frames):
    """Dismiss an already healed native Tower message, without granting healing."""
    from .observation import EventFlag, MapId, event_flag_is_set
    from .red_party_pp import decode_red_party_pp

    raw = runtime.reader.read()
    if raw.map_id != int(MapId.POKEMON_TOWER_5F):
        return None
    if (raw.battle_state or (raw.player_y, raw.player_x) not in
            {(8, 10), (8, 11), (9, 10), (9, 11)}
        or runtime.emulator.pressed_buttons or _field_ready(runtime)
        or runtime.reader.trainer_engagement_active()
        or not runtime.reader.read_bottom_dialogue_box_visible()
        or raw.event_flags is None
        or len(raw.event_flags) * 8 <= int(EventFlag.IN_PURIFIED_ZONE)
        or not event_flag_is_set(raw.event_flags, int(EventFlag.IN_PURIFIED_ZONE))):
        return None
    try:
        count = len(raw.party_hp)
        if (not 1 <= count <= 6 or raw.party_count != count
            or len(raw.party_max_hp) != count or raw.party_hp != raw.party_max_hp
            or any(hp <= 0 for hp in raw.party_hp)
            or raw.party_status != (0,) * count
            or len(raw.party_moves) != count or len(raw.party_pp) != count):
            return None
        pp = tuple(decode_red_party_pp(m, p) for m, p in
                   zip(raw.party_moves, raw.party_pp, strict=True))
        if any(p.maximum_total <= 0 or p.current_total != p.maximum_total for p in pp):
            return None
    except (AttributeError, TypeError, ValueError):
        return None
    source = runtime.emulator.save_state_bytes()
    _, lesson = capture_player_lesson_snapshot(runtime)
    used, terminal, retained = False, None, None

    def execute():
        nonlocal used, terminal, retained
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("purified message settlement is stale or consumed")
        used = True
        from copy import deepcopy
        from .gen1_route_runtime import Gen1WildFleeHandler
        from .route_executor import TraversalSnapshot

        custody = deepcopy(_purified_message_custody(runtime))
        a, f = actions.actions_executed, runtime.emulator.frame_count
        handler = Gen1WildFleeHandler(actions, runtime.reader, maximum_flees=0,
            stabilization_frames=settle_frames, allow_party_faints=True,
            allow_field_faint_dialogue=True)
        receipt = handler.handle(TraversalSnapshot(raw.map_id,
            (raw.player_y, raw.player_x), False, "scripted_dialogue"))
        after = runtime.reader.read()
        _, after_lesson = capture_player_lesson_snapshot(runtime)
        if (not _field_ready(runtime) or runtime.emulator.pressed_buttons
            or (after.map_id, after.player_y, after.player_x, after.battle_state)
            != (raw.map_id, raw.player_y, raw.player_x, 0)
            or after_lesson != lesson or _purified_message_custody(runtime) != custody
            or any(getattr(after, name) != getattr(raw, name) for name in (
                "player_money", "bag_items", "badge_bits", "event_flags", "party_count",
                "party_species_ids", "party_levels", "party_hp", "party_max_hp",
                "party_pp", "party_status", "party_moves", "party_stats"))):
            raise RuntimeError("purified message settlement changed protected state")
        terminal = runtime.emulator.save_state_bytes()
        retained = GoalExecutionReport(actions.actions_executed-a,
            runtime.emulator.frame_count-f,
            dict(mechanic="native_purified_message_settlement", learned_recovery=False,
                model_queries=0, directional_inputs=0, healing_performed_by_handler=False,
                individual_xp_box_dex_custody_verified=True, verified=True,
                endpoint=(after.player_y, after.player_x), route_details=receipt.details))
        return retained

    def verify(report):
        if (terminal is None or report != retained or not _field_ready(runtime)
            or runtime.emulator.pressed_buttons
            or runtime.emulator.save_state_bytes() != terminal):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding("pokemon.red:retained-motion:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL, 0.04, 0.02, execute, verify, maximum_cash_debit=0)


def interrupted_motion_binding(runtime, actions, *, rom, maximum_waits=16, settle_frames=120):
    """Observe one unambiguous native chain endpoint before offering recovery."""
    if any(type(v) is not int or v <= 0 for v in (maximum_waits, settle_frames)):
        raise ValueError("motion settlement bounds must be positive integers")
    purified = _interrupted_purified_message_binding(runtime, actions, settle_frames=settle_frames)
    if purified is not None:
        return purified
    raw = runtime.reader.read()
    ready = runtime.reader.read_input_readiness()
    if (
        raw.map_id not in SPINNER_MAP_IDS
        or raw.battle_state
        or _field_ready(runtime)
        or ready.joy_ignore != 255
        or not ready.simulated_joypad_index
        or not ready.movement_flags & 128
        or runtime.reader.read_bottom_dialogue_box_visible()
    ):
        return None
    at = (raw.player_y, raw.player_x)
    chains = tuple(
        (trigger, *path)
        for trigger, path in spinner_sequences(rom, raw.map_id).items()
        if at in (trigger, *path)
    )
    endpoints = {path[-1] for path in chains}
    if len(endpoints) != 1:
        return None
    (endpoint,) = endpoints
    allowed = frozenset(p for path in chains for p in path)
    source = runtime.emulator.save_state_bytes()
    _, lesson = capture_player_lesson_snapshot(runtime)
    used, terminal, retained = False, None, None

    def execute():
        nonlocal used, terminal, retained
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("motion settlement is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        boxes, dex, pc = (
            runtime.reader.read_all_box_states(),
            runtime.reader.read_pokedex_state(),
            runtime.reader.read_pc_items(),
        )
        for _ in range(maximum_waits):
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=settle_frames))
            after = runtime.reader.read()
            if (
                after.map_id != raw.map_id
                or after.battle_state
                or (after.player_y, after.player_x) not in allowed
                or runtime.reader.read_bottom_dialogue_box_visible()
            ):
                raise RuntimeError("motion settlement left its declared native path")
            if _field_ready(runtime):
                if (after.player_y, after.player_x) != endpoint:
                    raise RuntimeError("motion settled at an unexpected endpoint")
                break
        else:
            raise RuntimeError("motion settlement exhausted its wait bound")
        _, after_lesson = capture_player_lesson_snapshot(runtime)
        if (
            after_lesson != lesson
            or any(
                getattr(after, name) != getattr(raw, name)
                for name in (
                    "player_money",
                    "bag_items",
                    "badge_bits",
                    "event_flags",
                    "party_hp",
                    "party_pp",
                    "party_status",
                    "party_species_ids",
                    "party_levels",
                    "party_moves",
                )
            )
            or runtime.reader.read_all_box_states() != boxes
            or runtime.reader.read_pokedex_state() != dex
            or runtime.reader.read_pc_items() != pc
        ):
            raise RuntimeError("motion settlement changed protected resources")
        terminal = runtime.emulator.save_state_bytes()
        retained = GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                mechanic="native_forced_motion_settlement",
                learned_recovery=False,
                model_queries=0,
                directional_inputs=0,
                endpoint=endpoint,
                verified=True,
            ),
        )
        return retained

    def verify(report):
        if (
            terminal is None
            or report != retained
            or not _field_ready(runtime)
            or runtime.emulator.save_state_bytes() != terminal
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:retained-motion:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL,
        0.04,
        0.02,
        execute,
        verify,
        maximum_cash_debit=0,
    )



def _prior_poison_boundary(raw, proof):
    """Use a closed native battle boundary, never a guessed pre-faint status.

    The configured parent authenticates the files and their chunk/tail linkage.
    This adapter independently checks the episode hashes, field control, whole
    roster, PP/stats, money and badges before exposing only recorded HP/status.
    No saved state from the prior boundary is loaded or copied into the game.
    """
    from .provenance import canonical_sha256

    try:
        if (type(proof) is not dict or proof.get("schema") != "pokemon.red.retained-native-field-boundary.v1"):
            return None
        episode, endpoint, capture = proof["episode"], proof["endpoint"], proof["capture"]
        observation = episode["final_observation"]
        if (canonical_sha256(episode) != endpoint["outcome_sha256"]
                or canonical_sha256(observation) != episode["final_observation_sha256"]
                or proof["native_final_state_sha256"] != endpoint["final_state_sha256"]
                or endpoint["actor_returned_win"] is not True
                or capture["source_state_sha256"] != proof["source_chunk_state_sha256"]
                or capture["partition"] != "development"
                or capture["capture_id"] != episode["capture_id"]
                or capture["expected_map"] != raw.map_id
                or episode["battle_won"] is not True or episode["final_battle_state"] != 0
                or episode["stop_reason"] != "battle_won"
                or episode["teacher_queries"] != 0 or episode["memory_write_actions"] != 0
                or episode["failed_move_executions"] != 0):
            return None
        features = observation["features"]
        party = features["party"]
        members = party["members"]
        if (features["control"]["input_ready"] is not True
                or features["battle"] is not None or features["menu"] is not None
                or party["count"] != raw.party_count or len(members) != raw.party_count
                or features["resources"]["money"] != raw.player_money
                or features["progress"]["badge_count"] != int(raw.badge_bits).bit_count()):
            return None
        old_hp, old_status = [], []
        for index, member in enumerate(members):
            stats = member["stats"]
            status = member["status"]
            if status not in (None, "poison"):
                return None  # Sleep counters or other statuses are not reconstructed.
            if (int(member["species_ref"].rsplit(":",1)[1]) != raw.party_species_ids[index]
                    or member["level"] != raw.party_levels[index]
                    or member["max_hp"] != raw.party_max_hp[index]
                    or (stats["attack"],stats["defense"],stats["speed"],stats["special"]) != raw.party_stats[index]
                    or tuple(int(m["move_ref"].rsplit(":",1)[1]) for m in member["moves"]) != raw.party_moves[index]
                    or tuple(m["pp"] for m in member["moves"]) != tuple(v & 63 for v in raw.party_pp[index])
                    or type(member["hp"]) is not int or not 0 <= member["hp"] <= member["max_hp"]):
                return None
            hp, encoded = member["hp"], 8 if status == "poison" else 0
            now_hp, now_status = raw.party_hp[index], raw.party_status[index]
            if (now_hp,now_status) != (hp,encoded) and not (hp > 0 and encoded == 8 and now_hp == now_status == 0):
                return None
            old_hp.append(hp);old_status.append(encoded)
        if not any(hp > 0 and status == 8 and now == 0 for hp,status,now in zip(old_hp,old_status,raw.party_hp,strict=True)):
            return None
        return tuple(old_hp), tuple(old_status)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def retained_field_faint_binding(runtime, actions, *, outcome, settle_frames=120, prior_native_boundary=None):
    """Reconnect an exact failed native poison-faint observation after a load.

    The configured parent authenticates the retained result and state. Its prior
    semantic observation supplies only the already recorded HP/status transition;
    it never changes emulator memory or authorizes an arbitrary text dismissal.
    """
    from dataclasses import replace
    from .gen1_route_runtime import Gen1WildFleeHandler
    from .route_executor import TraversalSnapshot

    if type(settle_frames) is not int or settle_frames <= 0:
        raise ValueError("faint settlement requires a positive frame bound")
    raw = runtime.reader.read()
    readiness = runtime.reader.read_input_readiness()
    if (not raw.game_started or raw.battle_state or runtime.emulator.pressed_buttons
        or _field_ready(runtime) or readiness.joy_ignore
        or readiness.simulated_joypad_index or readiness.npc_movement_script_table
        or runtime.reader.trainer_engagement_active()
        or runtime.reader.read_overworld_start_menu_visible()
        or not runtime.reader.read_bottom_dialogue_box_visible()):
        return None
    source = runtime.emulator.save_state_bytes()

    def normalized(value):
        return tuple(normalized(v) for v in value) if isinstance(value, (tuple, list)) else value

    try:
        before, after = outcome["before"], outcome["after"]
        old, current = before["diagnostics"], after["diagnostics"]
        count = raw.party_count
        old_hp, old_status = tuple(old["party_hp"]), tuple(old["party_status"])
        if outcome["error"] == "field dialogue lacks a newly poisoned member faint":
            boundary = _prior_poison_boundary(raw, prior_native_boundary)
            if boundary is None:
                return None
            old_hp, old_status = boundary
        if (outcome["error_type"] != "RouteExecutionError"
            or outcome["error"] not in {"Gen I route cannot dismiss 'scripted_dialogue'", "field dialogue lacks a newly poisoned member faint"}
            or outcome["failure_phase"] != "execution"
            or outcome["safe_terminal"] is not True
            or outcome["terminal_state_sha256"] != sha256(source).hexdigest()
            or before["input_ready"] is not True or after["input_ready"] is not False
            or before["buttons_released"] is not True or after["buttons_released"] is not True
            or before["battle_state"] != 0 or after["battle_state"] != 0
            or type(count) is not int or not 1 <= count <= 6
            or len(old_hp) != count or len(old_status) != count
            or raw.party_hp is None or raw.party_status is None
            or len(raw.party_hp) != count or len(raw.party_status) != count
            or not any(hp > 0 for hp in raw.party_hp)
            or any(type(v) is not int or v < 0 for v in (*old_hp, *old_status))
            or normalized(old["party_species_ids"]) != raw.party_species_ids
            or any(normalized(current[name]) != getattr(raw, name) for name in (
                "map_id", "player_x", "player_y", "battle_state", "player_money",
                "party_count", "party_hp", "party_max_hp", "party_status",
                "party_species_ids", "party_levels", "party_moves", "party_stats",
                "bag_items", "badge_bits"))
            or normalized(current["party_pp_encoded"]) != raw.party_pp):
            return None
        slots = tuple(i + 1 for i, (hp, status, now, now_status) in enumerate(
            zip(old_hp, old_status, raw.party_hp, raw.party_status, strict=True))
            if hp > 0 and status == 8 and now == 0 and now_status == 0)
        if not slots:
            return None
    except (KeyError, TypeError, ValueError):
        return None

    used, terminal, retained = False, None, None

    def execute():
        nonlocal used, terminal, retained
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("retained faint settlement is stale or consumed")
        used = True
        from copy import deepcopy

        custody = deepcopy(_purified_message_custody(runtime))
        a, f = actions.actions_executed, runtime.emulator.frame_count
        handler = Gen1WildFleeHandler(actions, runtime.reader, maximum_flees=0,
            stabilization_frames=settle_frames, allow_party_faints=True,
            allow_field_faint_dialogue=True, emulator=runtime.emulator)
        # Restore only the observer's recorded transition evidence. The native
        # state stays at the failed tail, including its fainted party member.
        handler._field_boundary = replace(raw, party_hp=old_hp, party_status=old_status)
        receipt = handler.handle(TraversalSnapshot(raw.map_id,
            (raw.player_y, raw.player_x), False, "scripted_dialogue"))
        after_raw = runtime.reader.read()
        if (not receipt.details.get("native_field_faint")
            or tuple(receipt.details.get("new_fainted_slots", ())) != slots
            or not _field_ready(runtime) or runtime.emulator.pressed_buttons
            or (after_raw.map_id, after_raw.player_y, after_raw.player_x)
            != (raw.map_id, raw.player_y, raw.player_x)
            or _purified_message_custody(runtime) != custody):
            raise RuntimeError("retained faint settlement changed protected state")
        terminal = runtime.emulator.save_state_bytes()
        retained = GoalExecutionReport(actions.actions_executed-a,
            runtime.emulator.frame_count-f,
            dict(mechanic="native_retained_field_faint_settlement", learned_recovery=False,
                model_queries=0, directional_inputs=0, healing_performed_by_handler=False,
                prior_native_outcome_authenticated=True, verified=True,
                individual_xp_box_dex_custody_verified=True, route_details=receipt.details))
        return retained

    def verify(report):
        if (terminal is None or report != retained or not _field_ready(runtime)
            or runtime.emulator.pressed_buttons
            or runtime.emulator.save_state_bytes() != terminal):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding("pokemon.red:retained-motion:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL, 0.04, 0.02, execute, verify, maximum_cash_debit=0)
