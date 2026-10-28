"""Current-party paid Safari rewards; navigation/lesson are mechanics, not policy."""

from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_traversal import map_object_events
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .red_field_item import collect_visible_field_item, red_field_items
from .red_machine_teaching import execute_machine_lesson, plan_machine_lesson
from .red_npc_approach import approach_npc
from .red_paid_safari_departure import exit_paid_search, plan_paid_safari_departure
from .red_pc_storage import face_pc_boundary
from .red_player_field_goals import _field_ready
from .red_player_story_travel import story_travel_binding
from .red_safari_acquisition import enter_red_safari_area, red_safari_zone_offers
from .red_safari_objective_route import (
    OBJECTIVE_MAPS,
    require_objective_route,
    route_safari_objective,
)
from .route_plan import RoutePlanningError

PROTECTED = (
    "player_money",
    "party_species_ids",
    "party_levels",
    "party_moves",
    "party_pp",
    "party_hp",
    "party_status",
    "badge_bits",
)


def safari_registrations_preserved(before, after):
    """Fleeing may add seen entries, but cannot acquire or lose owned species."""
    return before.owned_species == after.owned_species and before.seen_species <= after.seen_species


def reward_bag(before, *, item, consumed=None):
    expected = dict(before)
    if expected.get(item, 0) or (consumed is not None and expected.get(consumed) != 1):
        raise ValueError("reward is already owned or exchange item is absent")
    if consumed is not None:
        del expected[consumed]
    if len(expected) >= 20:
        raise ValueError("reward has no inventory capacity")
    expected[item] = 1
    return expected


def collect_hm_reward(runtime, actions, *, item, events, consumed=None):
    """Caller owns approach/facing. Native events AND exact bag delta prove receipt."""
    before = runtime.reader.read()
    expected = reward_bag(before.bag_items, item=item, consumed=consumed)
    if not _field_ready(runtime) or any(event_flag_is_set(before.event_flags, e) for e in events):
        raise ValueError("HM reward requires an unclaimed ready boundary")
    for _ in range(128):
        current = runtime.reader.read()
        if current.map_id != before.map_id or current.battle_state:
            raise RuntimeError("HM reward left its interaction boundary")
        for key in PROTECTED:
            if getattr(current, key) != getattr(before, key):
                raise RuntimeError("HM reward changed protected " + key)
        received = all(event_flag_is_set(current.event_flags, e) for e in events)
        if received and _field_ready(runtime):
            if dict(current.bag_items) != expected:
                raise RuntimeError("HM reward inventory differs from native receipt")
            return {"item": item, "consumed": consumed, "events": list(events)}
        kind = MacroActionKind.INTERACT if _field_ready(runtime) else MacroActionKind.CONFIRM
        actions.execute(MacroAction(kind))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
    raise RuntimeError("HM reward dialogue did not settle")


def safari_approach(runtime, actions, world, *, map_id, target_at, face_target=True):
    """Choose a feasible adjacent stance from cartridge terrain and paid timer."""
    reader = runtime.reader
    start = Gen1TraversalObserver(reader).observe()
    world = world.with_current_observation(reader)
    candidates = []
    for dy, dx, facing in ((1, 0, "up"), (0, -1, "right"), (0, 1, "left"), (-1, 0, "down")):
        at = target_at[0] + dy, target_at[1] + dx
        if min(at) < 0:
            continue
        try:
            plan = world.plan_feasible_to_map(start, map_id, goal_at=at)
            require_objective_route(plan, reader.read_safari_session_state())
        except (RoutePlanningError, ValueError):
            continue
        candidates.append((len(plan.steps), at, facing))
    if not candidates:
        raise ValueError("Safari reward has no step-safe interaction stance")
    _, at, facing = min(candidates)
    evidence = route_safari_objective(
        runtime.emulator, reader, actions, world, map_id=map_id, at=at
    )
    if face_target:
        face_pc_boundary(actions, reader, facing)
    return evidence


def expire_paid_safari(runtime, actions, world):
    """Reuse native time-up when a pre-Surf player has no walkable park exit."""
    from .safari import DEFAULT_SAFARI_TIMING, _move, _pulse

    reader, em = runtime.reader, runtime.emulator
    before, session = reader.read(), reader.read_safari_session_state()
    if (
        not _field_ready(runtime)
        or not session.in_safari_zone
        or session.safari_game_over
        or not 0 <= session.safari_steps <= 500
        or session.safari_balls != 30
    ):
        raise ValueError("Safari time-up requires an intact active paid session")
    world = world.with_current_observation(reader)
    graph, terrain = world.local_graphs[before.map_id], world.terrain[before.map_id]
    at = (before.player_y, before.player_x)
    pairs = []
    for edge in graph.neighbors(at):
        target = edge.target
        if (
            edge.action_kind is not MacroActionKind.MOVE
            or edge.requirements
            or not edge.permits_mode("land")
            or edge.next_mode("land") != "land"
            or terrain.grass[target[0]][target[1]]
        ):
            continue
        for back in graph.neighbors(target):
            if (
                back.target == at
                and back.action_kind is MacroActionKind.MOVE
                and not back.requirements
                and back.permits_mode("land")
                and back.next_mode("land") == "land"
            ):
                pairs.append((edge.action, back.action, target))
    if not pairs or terrain.grass[at[0]][at[1]]:
        raise ValueError("Safari time-up lacks a safe reversible nongrass pair")
    outward, inward, target = min(pairs)
    timing = DEFAULT_SAFARI_TIMING
    steps = 0
    for _ in range(session.safari_steps + 1):
        if reader.read_safari_session_state().safari_steps == 0:
            break
        raw = reader.read()
        here = (raw.player_y, raw.player_x)
        if raw.map_id != before.map_id or here not in {at, target}:
            raise RuntimeError("Safari time-up left its reversible pair")
        _move(
            actions,
            reader,
            em,
            (outward if here == at else inward,),
            timing,
            "observed Safari time-up",
            expected_party_species_ids=before.party_species_ids,
        )
        steps += 1
    # Red tests time-up on the next attempted walking step, not on Confirm.
    raw = reader.read()
    here = (raw.player_y, raw.player_x)
    if raw.map_id != before.map_id or here not in {at, target}:
        raise RuntimeError("Safari time-up lost its final walking stance")
    _pulse(
        actions,
        MacroActionKind.MOVE,
        outward if here == at else inward,
        frames=timing.movement_frames,
    )
    for _ in range(timing.cleanup_pulses):
        raw, final = reader.read(), reader.read_safari_session_state()
        if (
            raw.map_id == MapId.SAFARI_ZONE_GATE
            and _field_ready(runtime)
            and not final.in_safari_zone
            and not final.safari_game_over
            and final.safari_steps == final.safari_balls == 0
        ):
            for key in (*PROTECTED, "bag_items"):
                if getattr(raw, key) != getattr(before, key):
                    raise RuntimeError("Safari time-up changed protected " + key)
            return {"method": "native_time_up", "steps": steps, "additional_fee": 0}
        kind = (
            MacroActionKind.CANCEL
            if raw.map_id == MapId.SAFARI_ZONE_GATE
            else MacroActionKind.CONFIRM
        )
        _pulse(actions, kind, frames=timing.wait_frames)
    raise RuntimeError("Safari time-up did not return inactive gate control")


def safari_rewards_binding(
    runtime, actions, *, route, party_slot, replace_slot, record, complete_center_approach=False
):
    """One resumable mechanics option; never captures or changes the chosen party."""
    if type(complete_center_approach) is not bool:
        raise TypeError("Safari center approach must be an explicit boolean")
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    if (
        type(party_slot) is not int
        or type(replace_slot) is not int
        or not raw.party_moves
        or not 1 <= party_slot <= len(raw.party_moves)
        or not 1 <= replace_slot <= 4
    ):
        raise ValueError("Safari Surf lesson needs an actual party/move slot")
    bag = dict(raw.bag_items or ())
    surf, teeth = int(ItemId.HM03_SURF), int(ItemId.GOLD_TEETH)
    if bag.get(int(ItemId.HM04_STRENGTH)) or event_flag_is_set(
        raw.event_flags, int(EventFlag.GAVE_GOLD_TEETH)
    ):
        return None
    inside = raw.map_id in OBJECTIVE_MAPS
    approach = None
    if not inside:
        if raw.map_id != MapId.FUCHSIA_POKECENTER:
            return None
        if (raw.player_y, raw.player_x) != (3, 3):
            if not complete_center_approach:
                return None
            approach = story_travel_binding(
                runtime, actions, objective_id="obtain_surf", route=route, destination_at=(3, 3)
            )
            if approach is None:
                return None
    if bag.get(surf) and bag.get(teeth) and 57 in raw.party_moves[party_slot - 1] and not inside:
        return None
    if len(bag) + int(not bag.get(surf)) + int(not bag.get(teeth)) > 20 or (
        not inside and raw.player_money < 500
    ):
        return None
    source = runtime.emulator.save_state_bytes()
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Safari rewards option is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        reader, em = runtime.reader, runtime.emulator
        expected_moves = [list(row) for row in raw.party_moves]
        expected_pp = [list(row) for row in raw.party_pp]
        if 57 not in expected_moves[party_slot - 1]:
            expected_moves[party_slot - 1][replace_slot - 1] = 57
            expected_pp[party_slot - 1][replace_slot - 1] = 15
        boxes, dex, pc = (
            reader.read_all_box_states(),
            reader.read_pokedex_state(),
            reader.read_pc_items(),
        )
        stages = []

        def retain(name, evidence):
            stages.append(dict(stage=name, evidence=evidence))
            record(name, evidence)

        if approach is not None:
            report = approach.execute()
            if approach.verify(report).status.value != "succeeded":
                raise RuntimeError("Safari center approach did not verify its native stance")
            retain("center_stance_approach", dict(report.evidence))
        if not inside:
            offer = next(
                o
                for o in red_safari_zone_offers(route.rom, ())
                if o.map_id == MapId.SAFARI_ZONE_CENTER
            )
            receipt = enter_red_safari_area(em, actions, reader, offer)
            retain(
                "paid_admission",
                dict(
                    receipt.public_dict(),
                    money_before=receipt.money_before,
                    money_after=receipt.money_after,
                ),
            )
        if not dict(reader.read().bag_items).get(teeth):
            (target,) = red_field_items(route.rom, teeth)
            retain(
                "teeth_approach",
                safari_approach(
                    runtime, actions, route.route_world, map_id=target.map_id, target_at=target.at
                ),
            )
            collect_visible_field_item(actions, reader, target)
            retain("gold_teeth", {"item": teeth, "verified": True})
        # Preserve an actual West field stance as the house departure destination.
        (target,) = red_field_items(route.rom, teeth)
        if not dict(reader.read().bag_items).get(surf):
            house = int(MapId.SAFARI_ZONE_SECRET_HOUSE)
            (guru,) = [o for o in map_object_events(route.rom, {house}) if o.object_index == 1]
            retain(
                "guru_approach",
                safari_approach(
                    runtime, actions, route.route_world, map_id=house, target_at=(guru.y, guru.x)
                ),
            )
            live = [o for o in reader.read_current_map_objects() if o.sprite_index == 1]
            if len(live) != 1 or (live[0].picture_id, live[0].at) != (
                guru.sprite_id,
                (guru.y, guru.x),
            ):
                raise ValueError("Surf guru differs from cartridge object")
            retain(
                "surf_reward",
                collect_hm_reward(runtime, actions, item=surf, events=(int(EventFlag.GOT_HM03),)),
            )
        if 57 not in reader.read().party_moves[party_slot - 1]:
            lesson = plan_machine_lesson(
                route.rom, reader, item_id=surf, party_slot=party_slot, replace_slot=replace_slot
            )
            execute_machine_lesson(em, actions, reader, lesson, rom=route.rom)
            retain(
                "surf_lesson",
                {
                    "party_slot": party_slot,
                    "replace_slot": replace_slot,
                    "move": 57,
                    "learned_selection": False,
                },
            )
        if reader.read().map_id == MapId.SAFARI_ZONE_SECRET_HOUSE:
            retain(
                "house_departure",
                safari_approach(
                    runtime,
                    actions,
                    route.route_world,
                    map_id=target.map_id,
                    target_at=target.at,
                    face_target=False,
                ),
            )
        try:
            plan_paid_safari_departure(
                Gen1TraversalObserver(reader).observe(), route.route_world, reader
            )
        except (RoutePlanningError, ValueError):
            retain("paid_departure", expire_paid_safari(runtime, actions, route.route_world))
        else:
            retain("paid_departure", exit_paid_search(em, actions, reader, route.route_world))
        replace(route, destination_map=int(MapId.FUCHSIA_POKECENTER), destination_at=(3, 3))(
            actions, reader, em
        )
        after = reader.read()
        expected_bag = dict(raw.bag_items)
        expected_bag.update({surf: 1, teeth: 1})
        if (
            not _field_ready(runtime)
            or dict(after.bag_items) != expected_bag
            or after.player_money != raw.player_money - (0 if inside else 500)
            or reader.read_all_box_states() != boxes
            or not safari_registrations_preserved(dex, reader.read_pokedex_state())
            or reader.read_pc_items() != pc
        ):
            raise RuntimeError("Safari rewards did not preserve earned resources")
        if after.party_moves != tuple(
            tuple(row) for row in expected_moves
        ) or after.party_pp != tuple(tuple(row) for row in expected_pp):
            raise RuntimeError("Safari lesson changed unexpected moves or PP")
        for key in ("party_species_ids", "party_levels", "party_hp", "party_status", "badge_bits"):
            if getattr(after, key) != getattr(raw, key):
                raise RuntimeError("Safari rewards changed protected " + key)
        runtime.observer.latch_verified_facts(
            runtime.adapter.graph.objective("obtain_surf").completion_facts
        )
        terminal = em.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            em.frame_count - f,
            dict(
                objective="obtain_surf",
                objective_completed=True,
                stages=stages,
                support="paid_safari_rewards_and_explicit_surf_lesson",
                captures=0,
            ),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and _field_ready(runtime)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:safari-rewards:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, 0.2 + (0.0 if approach is None else approach.estimated_effort)),
        0.02,
        execute,
        verify,
        maximum_cash_debit=0 if inside else 500,
        story_objective_ref="obtain_surf",
    )


def strength_reward_binding(runtime, actions, *, route):
    """Exchange earned teeth for HM04; teaching Strength is a separate lesson."""
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    strength, teeth = int(ItemId.HM04_STRENGTH), int(ItemId.GOLD_TEETH)
    if (
        raw.map_id != MapId.FUCHSIA_POKECENTER
        or not raw.bag_items
        or dict(raw.bag_items).get(teeth) != 1
        or dict(raw.bag_items).get(strength)
        or not dict(raw.bag_items).get(int(ItemId.HM03_SURF))
    ):
        return None
    source = runtime.emulator.save_state_bytes()
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Strength exchange is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        reader, em = runtime.reader, runtime.emulator
        boxes, dex, pc = (
            reader.read_all_box_states(),
            reader.read_pokedex_state(),
            reader.read_pc_items(),
        )
        approach_npc(
            em,
            reader,
            actions,
            rom=route.rom,
            map_id=int(MapId.WARDENS_HOUSE),
            object_index=1,
            maximum_readiness_waits=100,
        )
        evidence = collect_hm_reward(
            runtime,
            actions,
            item=strength,
            consumed=teeth,
            events=(int(EventFlag.GAVE_GOLD_TEETH), int(EventFlag.GOT_HM04)),
        )
        replace(route, destination_map=int(MapId.FUCHSIA_POKECENTER), destination_at=(3, 3))(
            actions, reader, em
        )
        after = reader.read()
        if (
            not _field_ready(runtime)
            or dict(after.bag_items) != reward_bag(raw.bag_items, item=strength, consumed=teeth)
            or reader.read_all_box_states() != boxes
            or reader.read_pokedex_state() != dex
            or reader.read_pc_items() != pc
        ):
            raise RuntimeError("Strength exchange did not preserve earned resources")
        for key in PROTECTED:
            if getattr(after, key) != getattr(raw, key):
                raise RuntimeError("Strength exchange changed protected " + key)
        runtime.observer.latch_verified_facts(
            runtime.adapter.graph.objective("obtain_strength").completion_facts
        )
        terminal = em.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            em.frame_count - f,
            dict(
                objective="obtain_strength",
                objective_completed=True,
                support="gold_teeth_exchange",
                strength_taught=False,
                reward=evidence,
            ),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and _field_ready(runtime)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:strength-reward:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        0.05,
        0.01,
        execute,
        verify,
        maximum_cash_debit=0,
        story_objective_ref="obtain_strength",
    )


def strength_lesson_binding(runtime, actions, *, rom, party_slot, replace_slot):
    """Expose an explicit legal HM04 lesson; recipient selection is not learned."""
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    if not dict(raw.bag_items or ()).get(int(ItemId.HM04_STRENGTH)):
        return None
    if any(70 in moves for moves in raw.party_moves or ()):
        return None
    lesson = plan_machine_lesson(
        rom,
        runtime.reader,
        item_id=int(ItemId.HM04_STRENGTH),
        party_slot=party_slot,
        replace_slot=replace_slot,
    )
    source = runtime.emulator.save_state_bytes()
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Strength lesson is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        execute_machine_lesson(runtime.emulator, actions, runtime.reader, lesson, rom=rom)
        if not _field_ready(runtime):
            raise RuntimeError("Strength lesson did not restore field control")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="explicit_strength_lesson",
                learned_selection=False,
                party_slot=party_slot,
                replace_slot=replace_slot,
                move=70,
            ),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and _field_ready(runtime)
            and 70 in runtime.reader.read().party_moves[party_slot - 1]
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:strength-lesson:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        0.04,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def safari_reward_story_option(
    runtime,
    actions,
    *,
    objective_id,
    route,
    party_slot=None,
    replace_slot=None,
    record=None,
    complete_center_approach=False,
):
    """Offer an earned HM or its actual approach without choosing story order.

    The paid Safari executor needs its verified center stance. Travel only
    approaches that boundary; it never grants an HM, heals or chooses Koga.
    Surf recipient/move replacement are explicit caller-supplied mechanics.
    Strength cannot be offered before the real Gold Teeth have been earned.
    """
    if objective_id not in {"obtain_surf", "obtain_strength"}:
        raise ValueError("undeclared Safari reward objective")
    if type(complete_center_approach) is not bool:
        raise TypeError("Safari center approach must be an explicit boolean")
    if objective_id == "obtain_surf" and not callable(record):
        raise TypeError("Surf rewards require an explicit stage recorder")
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    bag = dict(raw.bag_items or ())
    if objective_id == "obtain_surf":
        if bag.get(int(ItemId.HM04_STRENGTH)):
            return None
        binding = safari_rewards_binding(
            runtime,
            actions,
            route=route,
            party_slot=party_slot,
            replace_slot=replace_slot,
            record=record,
            complete_center_approach=complete_center_approach,
        )
        if binding is None and (
            raw.map_id in OBJECTIVE_MAPS
            or raw.player_money < 500
            or len(bag)
            + int(not bag.get(int(ItemId.HM03_SURF)))
            + int(not bag.get(int(ItemId.GOLD_TEETH)))
            > 20
        ):
            return None
    else:
        if (
            bag.get(int(ItemId.GOLD_TEETH)) != 1
            or not bag.get(int(ItemId.HM03_SURF))
            or bag.get(int(ItemId.HM04_STRENGTH))
        ):
            return None
        binding = strength_reward_binding(runtime, actions, route=route)
    if binding is None:
        local = raw.map_id == int(MapId.FUCHSIA_POKECENTER)
        if local and (raw.player_y, raw.player_x) == (3, 3):
            return None
        binding = story_travel_binding(
            runtime,
            actions,
            objective_id=objective_id,
            route=route,
            frontier=not local,
            stop_at_map_boundary=not local,
            destination_at=(3, 3) if local else None,
        )
    return None if binding is None else (binding, OptionChallenge(False, False, 0.0, 0.0, 0.0))
