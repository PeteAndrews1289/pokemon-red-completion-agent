"""Bounded DEVELOPMENT wild knockout excursion; capture controllers unchanged."""

from dataclasses import asdict, replace
from time import monotonic

from .actions import MacroAction, MacroActionKind
from .battle_runtime import BattleRuntimeTiming
from .observation import MapId
from .party import StatusCondition
from .party_preparation import PreparationAttempt
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_goal_skills import _POKEMON_CENTER_MAPS, _raw_party_fully_restored
from .red_learned_trainer import FrozenTrainerBattler
from .red_party_preparation import observe_preparation_members, preparation_trainee
from .red_scoped_training_battlers import validate_scoped_wild_battler
from .red_story_funding import restore_story_team
from .red_team_training import swap_field_party_slots
from .red_trainer_evolution import RedTrainerEvolutionGuard
from .wild_training_objective import WildTrainingObjective


class WildPreparationDefeat(RuntimeError):
    """Observed all-party defeat; callers may settle it, never erase it."""


HEALTH_LIMITED_RETURNS = frozenset(
    {
        "party_hp_below_half",
        "party_status",
        "party_fainted",
        "insufficient_battle_ready_members",
        "trainee_attack_pp_low",
        "attack_support_pp_low",
    }
)


def preparation_transport_slot(raw, *, allow_statused=False):
    """Fastest healthy living escort from observed stats, not a species rule.

    This is disclosed navigation support, not a guarantee of escape or a
    replacement for the learned wild actor. Slow trainees lead only at the
    training venue; unnecessary transit hits should not consume their outing.
    """
    if type(allow_statused) is not bool:
        raise ValueError("statused transport opt-in must be boolean")
    size = raw.party_count
    if (
        type(size) is not int
        or not 1 <= size <= 6
        or any(
            values is None or len(values) != size
            for values in (raw.party_hp, raw.party_status, raw.party_stats)
        )
    ):
        raise ValueError("transport escort lacks observed party stats")
    if any(
        len(stats) != 4 or any(type(v) is not int or v <= 0 for v in stats)
        for stats in raw.party_stats
    ):
        raise ValueError("transport escort stats are incomplete")
    candidates = [i for i in range(size) if raw.party_hp[i] > 0 and raw.party_status[i] == 0]
    # A depleted outing still needs to reach its nurse. Prefer a healthy escort,
    # but allow an observed living member on that return leg when none is healthy.
    # This does not authorize starting training with a statused party.
    if not candidates and allow_statused:
        candidates = [i for i in range(size) if raw.party_hp[i] > 0]
    if not candidates:
        required = "living" if allow_statused else "healthy living"
        raise ValueError(f"transport escort requires a {required} member")
    return max(candidates, key=lambda i: (raw.party_stats[i][2], raw.party_hp[i], -i))


def prepare_training_transport(actions, reader, emulator, timing, *, allow_statused=False):
    index = preparation_transport_slot(reader.read(), allow_statused=allow_statused)
    swap_field_party_slots(
        actions,
        reader,
        emulator,
        first_index=0,
        second_index=index,
        label="observed-speed training transport escort",
        hideout_timing=timing,
    )
    return index


def wild_training_attack_moves(member):
    """Known eligible attacks, independent of their current PP.

    A status-only recipient can earn participation XP when the existing local
    battler switches to a reserve. Healing does not teach that recipient a move.
    This is capacity evidence, not a fighter selection or a forced switch.
    """
    return tuple(
        move
        for move in member.known_moves
        if RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move.move_id)).category != "status"
        and "self_destruct"
        not in RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move.move_id)).effect_flags
    )


def wild_training_has_attack_capacity(members):
    """Structural admission only; runtime separately verifies HP/status/PP."""
    return any(wild_training_attack_moves(member.observation) for member in members)


def wild_training_return_reason(members, trainee_ref, target_level, *, minimum_ready_members=None):
    """Disclosed resource rule, not a learned recovery prediction."""
    trainee = next(m.observation for m in members if m.specimen_ref == trainee_ref)
    if trainee.level >= target_level:
        return "trainee_target_reached"
    for member in members:
        mon = member.observation
        if mon.hp <= 0:
            return "party_fainted"
        if mon.status is not StatusCondition.HEALTHY:
            return "party_status"
        if minimum_ready_members is None and mon.hp * 2 < mon.max_hp:
            return "party_hp_below_half"
    if minimum_ready_members is not None:
        if type(minimum_ready_members) is not int or not 1 <= minimum_ready_members <= len(members):
            raise ValueError("invalid minimum battle-ready party count")
        ready = sum(
            member.observation.hp * 2 >= member.observation.max_hp
            and member.observation.can_battle
            and any(
                move.current_pp >= 5
                and RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move.move_id)).category
                != "status"
                and "self_destruct"
                not in RED_BATTLE_CATALOG.resolve_move(
                    pokemon_red_move_ref(move.move_id)
                ).effect_flags
                for move in member.observation.usable_moves
            )
            for member in members
        )
        if ready < minimum_ready_members:
            return "insufficient_battle_ready_members"
        # Healthy reserves can escort a retreat, but do not make an injured
        # trainee safe to keep leading fresh encounters.
        if trainee.hp * 2 < trainee.max_hp:
            return "party_hp_below_half"
    attacks = wild_training_attack_moves(trainee)
    if attacks:
        # Preserve the existing depletion retreat for a direct-fighting trainee.
        return "trainee_attack_pp_low" if sum(move.current_pp for move in attacks) < 5 else None
    reserves = tuple(
        wild_training_attack_moves(member.observation)
        for member in members
        if member.specimen_ref != trainee_ref
    )
    if any(sum(move.current_pp for move in moves) >= 5 for moves in reserves):
        return None  # The existing learned battler still owns whether/where to switch.
    if any(reserves):
        return "attack_support_pp_low"
    return "trainee_no_attack_support"  # Structural inability, not a reason for more nursing.


def transport_to_observed_preparation_corridor(
    actions, reader, emulator, *, route, corridor, record, recovery_map, recovery_at,
):
    """Materialize the same venue's physical lane after ordinary map arrival.

    Off-map terrain is only a prospective cartridge quote. Keep a still-legal
    pair, otherwise rederive within the observed component without changing the
    selected source, trainee, level dose or original encounter/search bounds.
    All travel uses the same guarded route/action ports; errors are not retried.
    """
    from .gen1_route_runtime import Gen1TraversalObserver
    from .gen1_trainer_sight import Gen1TrainerSightProjector
    from .red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from .red_living_dex_wild_corridor import derive_red_living_dex_wild_corridor
    from .red_training_ground_route import ground_route_capability_projector
    from .route_plan import RoutePlanningError

    if not route.observe_terrain:
        replace(route, destination_map=corridor.map_id, destination_at=corridor.origin_at)(
            actions, reader, emulator
        )
        return corridor
    if corridor.map_id in route.excluded_maps:
        raise ValueError("preparation destination excluded")
    observer = Gen1TraversalObserver(
        reader,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, reader, full_event_offsets=route.full_event_offsets,
        ),
        capability_projector=ground_route_capability_projector(route, emulator),
    )

    def observed_world():
        snapshot = observer.observe()
        if (not snapshot.ready or snapshot.interruption is not None
                or snapshot.mode != "land" or emulator.pressed_buttons):
            raise ValueError("preparation corridor requires a settled land boundary")
        world = route.route_world.with_current_observation(reader)
        if route.excluded_maps:
            world = replace(world, macro_graph=replace(
                world.macro_graph,
                edges={
                    m: tuple(e for e in edges if e.target_map not in route.excluded_maps)
                    for m, edges in world.macro_graph.edges.items()
                    if m not in route.excluded_maps
                },
            ))
        raw = reader.read()
        if (raw.battle_state != 0 or raw.map_id != snapshot.map_id
                or (raw.player_y, raw.player_x) != snapshot.at):
            raise ValueError("preparation corridor observation changed")
        return snapshot, world

    def quote(world, snapshot, goal_map, goal_at):
        # Match the ordinary ground route's existing complete-Cut opt-in and
        # learned-trainer hazard policy; this is not a second planner.
        try:
            return world.plan_feasible_to_map(snapshot, goal_map, goal_at=goal_at)
        except RoutePlanningError:
            if not route.allow_complete_cut_search:
                raise
            return world._plan_candidate(
                snapshot, goal_map, goal_at=goal_at,
                blocked={snapshot.map_id: snapshot.occupied | frozenset(
                    h.at for h in snapshot.hazards
                    if h.kind != "trainer_sight" or route.trainer_binding_factory is None
                )},
            )

    snapshot, world = observed_world()
    entry = None
    if snapshot.map_id != corridor.map_id:
        # No inferred waypoint: the ordinary composed route supplies its own
        # last native passage arrival for the already selected venue map.
        entry = quote(world, snapshot, corridor.map_id, None)
        if entry.terminal_map != corridor.map_id:
            raise ValueError("preparation map-entry quote differs from venue")
        replace(route, route_world=world, destination_map=corridor.map_id,
                destination_at=entry.terminal_at)(actions, reader, emulator)
        snapshot, world = observed_world()
    if snapshot.map_id != corridor.map_id:
        raise ValueError("preparation did not reach its selected venue")
    excluded = snapshot.occupied | frozenset(h.at for h in snapshot.hazards)
    live = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget(corridor.source_id),
        world.terrain[corridor.map_id], world.local_graphs[corridor.map_id],
        cartridge=route.rom, excluded=excluded, reachable_from=snapshot.at,
        preferred_corridor=corridor,
    )
    live = replace(
        live, maximum_legs=corridor.maximum_legs,
        maximum_seek_steps=corridor.maximum_seek_steps,
        maximum_encounters=corridor.maximum_encounters,
    )
    if live.source_id != corridor.source_id or live.map_id != corridor.map_id:
        raise ValueError("observed preparation corridor changed source")
    quoted = quote(world, snapshot, live.map_id, live.origin_at)
    projected = replace(snapshot, at=quoted.terminal_at, mode=quoted.terminal_mode)
    returned = quote(world, projected, recovery_map, recovery_at)
    if returned.terminal_map != recovery_map or returned.terminal_at != recovery_at:
        raise ValueError("observed preparation return quote differs from recovery")
    record("preparation-corridor-observed", {
        "authority": "same_selected_venue_observed_local_geometry",
        "planned_corridor": corridor.private_dict(),
        "observed_corridor": live.private_dict(),
        "corridor_rebound": live != corridor,
        "native_map_entry_used": entry is not None,
        "entry_quote_steps": 0 if entry is None else len(entry.steps),
        "local_quote_steps": len(quoted.steps),
        "return_quote_steps": len(returned.steps),
        "recovery_map": recovery_map,
        "recovery_at": recovery_at,
        "source_id_unchanged": True,
        "encounter_search_and_leg_caps_unchanged": True,
        "fit_allowed": False,
    })
    replace(route, route_world=world, destination_map=live.map_id,
            destination_at=live.origin_at)(actions, reader, emulator)
    return live


def execute_wild_preparation(
    *,
    rom,
    reader,
    actions,
    emulator,
    battler,
    adapter,
    source_raw,
    plan,
    attempts,
    record,
    cost_snapshot,
    hideout_timing,
    route,
    corridor,
    maximum_seek_steps=120,
    maximum_battles=1,
    minimum_ready_members=None,
    recovery_home_map=None,
    prepare_transport_escort=False,
    restore_on_return=True,
    allow_health_retreat=False,
    continue_after_nonwinning_exit=False,
):
    """One knockout and free recovery; caller meters and retains every terminal."""
    if not isinstance(battler, FrozenTrainerBattler):
        raise ValueError("wild preparation requires exact K development actor")
    battle_authority = battler.wild_authority(corridor.map_id)
    validate_scoped_wild_battler(battler)
    objective_version = getattr(battler, "wild_training_objective_version", None)
    if objective_version is not None and (type(objective_version) is not int or objective_version != 1):
        raise ValueError("unsupported wild training objective capability")
    if type(maximum_battles) is not int or not 1 <= maximum_battles <= 128:
        raise ValueError("wild preparation battle count outside bound")
    if type(prepare_transport_escort) is not bool:
        raise ValueError("transport escort opt-in must be boolean")
    if type(restore_on_return) is not bool:
        raise ValueError("automatic restoration opt-in must be boolean")
    if type(allow_health_retreat) is not bool:
        raise ValueError("health retreat opt-in must be boolean")
    if type(continue_after_nonwinning_exit) is not bool:
        raise ValueError("nonwinning continuation opt-in must be boolean")
    if minimum_ready_members is not None and (
        type(minimum_ready_members) is not int
        or not 1 <= minimum_ready_members <= source_raw.party_count
    ):
        raise ValueError("invalid minimum battle-ready party count")
    if type(maximum_seek_steps) is not int or not 1 <= maximum_seek_steps <= 120:
        raise ValueError("wild preparation seek limit outside bound")
    if reader.read() != source_raw or emulator.pressed_buttons:
        raise ValueError("wild preparation source changed")
    home = source_raw.map_id if recovery_home_map is None else recovery_home_map
    if (
        isinstance(home, bool)
        or not isinstance(home, int)
        or home not in _POKEMON_CENTER_MAPS | {MapId.INDIGO_PLATEAU_LOBBY}
    ):
        raise ValueError("wild preparation requires a supported recovery Center")
    indigo = home == MapId.INDIGO_PLATEAU_LOBBY
    destination = (
        ((11, 7) if indigo else (7, 3)) if restore_on_return else ((7, 7) if indigo else (3, 3))
    )
    if not _raw_party_fully_restored(source_raw) or source_raw.battle_state:
        raise ValueError("wild preparation requires restored field party")
    members = observe_preparation_members(emulator, plan)
    trainee = preparation_trainee(plan, members, attempts)
    if any(m.observation.experience is None for m in members):
        raise ValueError("wild preparation requires XP observations")
    started = monotonic()
    start_actions, start_frames = cost_snapshot()
    error = None
    completed = False
    heals = 0
    battles = 0
    encounters = 0
    nonwinning_exits = 0
    stop_reason = "encounter_limit"
    nonwinning_exit = False
    search_exhausted = False
    record(
        "preparation-choice",
        {
            "authority": "teacher_trainee_venue_and_navigation_learned_wild_knockout",
            "trainee_ref": trainee.specimen_ref,
            "attempts_already_spent": len(attempts),
            "target_level": dict(plan.targets)[trainee.specimen_ref],
            "corridor": corridor.private_dict(),
            "maximum_seek_steps": maximum_seek_steps,
            "maximum_battles": maximum_battles,
            "minimum_ready_members": minimum_ready_members,
            "recovery_home_map": int(home),
            "navigation_wild_policy": "bounded_existing_flee_support",
            "transport_escort": "observed_speed" if prepare_transport_escort else "trainee_lead",
            "fit_allowed": False,
            "restore_on_return": restore_on_return,
            "allow_health_retreat": allow_health_retreat,
            "continue_after_nonwinning_exit": continue_after_nonwinning_exit,
        },
    )
    try:
        if prepare_transport_escort:
            prepare_training_transport(actions, reader, emulator, hideout_timing)
            corridor = transport_to_observed_preparation_corridor(
                actions, reader, emulator, route=route, corridor=corridor, record=record,
                recovery_map=int(home), recovery_at=destination,
            )
            trainee = next(
                m
                for m in observe_preparation_members(emulator, plan)
                if m.specimen_ref == trainee.specimen_ref
            )
        swap_field_party_slots(
            actions,
            reader,
            emulator,
            first_index=0,
            second_index=trainee.observation.slot - 1,
            label="wild preparation trainee",
            hideout_timing=hideout_timing,
        )
        bound = reader.read()
        evolution = RedTrainerEvolutionGuard.from_rom(rom, emulator)
        if observe_preparation_members(emulator, plan)[0].specimen_ref != trainee.specimen_ref:
            raise RuntimeError("wild preparation lead binding changed")
        if not prepare_transport_escort:
            corridor = transport_to_observed_preparation_corridor(
                actions, reader, emulator, route=route, corridor=corridor, record=record,
                recovery_map=int(home), recovery_at=destination,
            )
        for battle_index in range(maximum_battles):
            live_members = observe_preparation_members(emulator, plan)
            if maximum_battles > 1 or allow_health_retreat or continue_after_nonwinning_exit:
                reason = wild_training_return_reason(
                    live_members,
                    trainee.specimen_ref,
                    dict(plan.targets)[trainee.specimen_ref],
                    minimum_ready_members=minimum_ready_members,
                )
                if reason is not None:
                    stop_reason = reason
                    break
            battle_bound = reader.read()
            before_xp = sum(m.observation.experience for m in live_members)
            encounter_actions, encounter_frames = cost_snapshot()
            for _ in range(maximum_seek_steps):
                raw = reader.read()
                if raw.battle_state:
                    break
                at = (raw.player_y, raw.player_x)
                if raw.map_id != corridor.map_id or at not in {
                    corridor.origin_at,
                    corridor.terminal_at,
                }:
                    raise RuntimeError("wild preparation left its verified encounter pair")
                direction = "up" if at == corridor.origin_at else "down"
                actions.execute(MacroAction(MacroActionKind.MOVE, direction))
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
            sought = reader.read()
            if sought.battle_state != 1:
                if (
                    sought.battle_state != 0
                    or sought.map_id != corridor.map_id
                    or (sought.player_y, sought.player_x)
                    not in {
                        corridor.origin_at,
                        corridor.terminal_at,
                    }
                    or not reader.read_input_readiness().ready
                    or reader.read_bottom_dialogue_box_visible()
                    or emulator.pressed_buttons
                ):
                    raise RuntimeError("wild preparation search ended at an unsafe boundary")
                # Finite random search is allowed to find nothing. Keep prior
                # wins/XP and all search costs, return for healing, and let the
                # preparation budget decide whether another outing is useful.
                search_exhausted = True
                stop_reason = "encounter_search_exhausted"
                record(
                    "search-exhausted",
                    {
                        "maximum_seek_steps": maximum_seek_steps,
                        "battles_completed": battles,
                        "actions": cost_snapshot()[0] - encounter_actions,
                        "frames": cost_snapshot()[1] - encounter_frames,
                    },
                )
                break

            def guard(raw, battle_bound=battle_bound):
                if (
                    raw.battle_state != 1
                    or raw.map_id != corridor.map_id
                    or raw.party_species_ids != battle_bound.party_species_ids
                    or raw.party_count != battle_bound.party_count
                    or raw.bag_items != battle_bound.bag_items
                    or raw.player_money != battle_bound.player_money
                ):
                    raise RuntimeError("wild preparation battle preservation failed")

            objective_kwargs = {}
            if objective_version == 1:
                # Rebind after the selected trainee lead swap using current semantic facts.
                objective = WildTrainingObjective.from_members(
                    source_state_sha256=battler.source_state_sha256,
                    trainee_ref=trainee.specimen_ref,
                    target_level=dict(plan.targets)[trainee.specimen_ref],
                    members=observe_preparation_members(emulator, plan),
                )
                if objective.trainee_slot != 1:
                    raise ValueError("wild training objective lost the selected lead binding")
                objective_kwargs["training_objective"] = objective
            encounters += 1
            episode = battler.run_wild_training(
                reader,
                actions,
                expected_map=corridor.map_id,
                timing=BattleRuntimeTiming(),
                decision_guard=guard,
                **objective_kwargs,
            )
            nonwinning_exit = (
                not episode.battle_won
                and episode.stop_reason == "battle_exited_without_win"
                and reader.read().battle_state == 0
            )
            if not episode.battle_won and not nonwinning_exit:
                lost = reader.read()
                if (
                    episode.stop_reason == "party_defeated"
                    and lost.battle_state == 1
                    and lost.party_hp
                    and not any(lost.party_hp)
                ):
                    raise WildPreparationDefeat("wild preparation stopped: party_defeated")
                raise RuntimeError(f"wild preparation stopped: {episode.stop_reason}")
            for _ in range(40):
                raw = reader.read()
                if raw.battle_state or raw.map_id != corridor.map_id:
                    raise RuntimeError("wild preparation settlement left field")
                if (
                    reader.read_input_readiness().ready
                    and not reader.read_bottom_dialogue_box_visible()
                ):
                    break
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
            else:
                raise RuntimeError("wild preparation settlement budget")
            raw = reader.read()
            if not evolution.matches(bound, raw):
                raise RuntimeError("wild preparation specimen preservation failed")
            if raw.player_money != bound.player_money or raw.bag_items != bound.bag_items:
                raise RuntimeError("wild preparation field resources changed")
            if nonwinning_exit:
                nonwinning_exits += 1
                stop_reason = "battle_exited_without_win"
                record(
                    f"wild-encounter-{battle_index + 1:03d}",
                    {
                        "battle_won": False,
                        "stop_reason": stop_reason,
                        "battle_result": raw.battle_result,
                        "actions": cost_snapshot()[0] - encounter_actions,
                        "frames": cost_snapshot()[1] - encounter_frames,
                    },
                )
                if continue_after_nonwinning_exit:
                    stop_reason = "encounter_limit"
                    continue
                break
            battles += 1
            current_xp = sum(
                m.observation.experience for m in observe_preparation_members(emulator, plan)
            )
            record(
                f"wild-encounter-{battle_index + 1:03d}",
                {
                    "battle_won": True,
                    "xp_gained": current_xp - before_xp,
                    "actions": cost_snapshot()[0] - encounter_actions,
                    "frames": cost_snapshot()[1] - encounter_frames,
                    "party_hp": list(raw.party_hp),
                    "party_status": list(raw.party_status),
                    "party_pp": [list(p) for p in raw.party_pp],
                },
            )
            if current_xp <= before_xp:
                reason = wild_training_return_reason(
                    observe_preparation_members(emulator, plan),
                    trainee.specimen_ref,
                    dict(plan.targets)[trainee.specimen_ref],
                    minimum_ready_members=minimum_ready_members,
                )
                # A native simultaneous knockout may legitimately award no XP
                # when every participant fainted. Keep that zero and retreat;
                # unknown/non-increasing XP with a ready party is still an error.
                if (
                    current_xp == before_xp
                    and allow_health_retreat
                    and reason in HEALTH_LIMITED_RETURNS
                ):
                    stop_reason = reason
                    break
                raise RuntimeError("wild encounter produced no measured XP")
        after_battle = observe_preparation_members(emulator, plan)
        xp = sum(m.observation.experience for m in after_battle) - sum(
            m.observation.experience for m in members
        )
        health_retreat = allow_health_retreat and stop_reason in HEALTH_LIMITED_RETURNS
        if xp <= 0 and not (nonwinning_exits or search_exhausted or health_retreat):
            raise RuntimeError("wild knockout produced no measured XP")
        targets = dict(plan.targets)
        reserve_xp = sum(
            m.observation.experience for m in after_battle if m.specimen_ref in targets
        ) - sum(m.observation.experience for m in members if m.specimen_ref in targets)
        if not evolution.matches(bound, reader.read()):
            raise RuntimeError("wild preparation pre-return specimen preservation failed")
        if prepare_transport_escort:
            return_raw = reader.read()
            escort = prepare_training_transport(
                actions, reader, emulator, hideout_timing, allow_statused=True
            )
            record(
                "return-transport",
                {
                    "selected_initial_slot": escort + 1,
                    "selected_status": return_raw.party_status[escort],
                    "statused_fallback_allowed": True,
                    "authority": "observed_living_escort_to_native_recovery",
                },
            )
        recovery_bound = reader.read()
        # Training can change levels, and the verified escort swap changes order.
        # Bind recovery to that verified boundary, not the pre-training roster.
        recovery_evolution = RedTrainerEvolutionGuard.from_rom(rom, emulator)
        replace(route, destination_map=int(home), destination_at=destination)(
            actions, reader, emulator
        )
        if restore_on_return:
            heals += 1
            record("healing-started", {"home_map": int(home)})
            restore_story_team(reader, actions, emulator, adapter)
        final = reader.read()
        if (
            (restore_on_return and not _raw_party_fully_restored(final))
            or not recovery_evolution.matches(recovery_bound, final)
            or final.player_money != source_raw.player_money
            or final.bag_items != source_raw.bag_items
            or final.map_id != home
            or (final.player_y, final.player_x) != ((7, 7) if indigo else (3, 3))
            or final.battle_state
            or not reader.read_input_readiness().ready
            or emulator.pressed_buttons
        ):
            raise RuntimeError("wild preparation healed return did not verify")
        if reserve_xp < 0:
            raise RuntimeError("wild preparation reserve XP decreased")
        if reserve_xp == 0 and xp > 0:
            # The escort may win after the trainee faints. Its genuine XP is
            # not target progress, but a verified return is an ordinary setback.
            stop_reason = "trainee_received_no_xp"
        elif reserve_xp == 0 and not (nonwinning_exits or search_exhausted or health_retreat):
            raise RuntimeError("wild preparation produced no reserve XP; healed then stopped")
        completed = True
        return {
            "status": "complete" if reserve_xp > 0 else "no_progress",
            "battles": battles,
            "encounters": encounters,
            "nonwinning_exits": nonwinning_exits,
            "stop_reason": stop_reason,
            "health_limited_return": health_retreat,
            "xp_gained": xp,
            "battle_authority": battle_authority,
            "learned_preparation": False,
            "sales": 0,
            "purchases": 0,
        }
    except BaseException as caught:
        error = caught
        raise
    finally:
        end_actions, end_frames = cost_snapshot()
        record(
            "preparation-cost",
            {
                "actions": end_actions - start_actions,
                "frames": end_frames - start_frames,
                "seconds": monotonic() - started,
                "completed_excursion": completed,
                "battles_completed": battles,
                "encounters": encounters,
                "nonwinning_exits": nonwinning_exits,
                "stop_reason": stop_reason if error is None else "error",
                "error": None if error is None else str(error),
            },
        )
        after = {m.specimen_ref: m.observation for m in observe_preparation_members(emulator, plan)}
        rows = []
        for m in members:
            old, new = m.observation, after[m.specimen_ref]
            if new.experience is None or new.experience < old.experience:
                raise RuntimeError("wild preparation XP accounting regressed")
            rows.append(
                {
                    "specimen_ref": m.specimen_ref,
                    "initial_slot": old.slot,
                    "final_slot": new.slot,
                    "level_before": old.level,
                    "level_after": new.level,
                    "species_before": old.species_id,
                    "species_after": new.species_id,
                    "xp_before": old.experience,
                    "xp_after": new.experience,
                    "xp_gained": new.experience - old.experience,
                    "hp_after": new.hp,
                }
            )
        selected = after[trainee.specimen_ref]
        attempt = PreparationAttempt(
            trainee.specimen_ref,
            trainee.observation.level,
            selected.level,
            selected.experience - trainee.observation.experience,
            end_actions - start_actions,
            end_frames - start_frames,
            monotonic() - started,
            heals=heals,
            failed=error is not None,
        )
        record(
            "preparation-attempt",
            {
                "attempt": asdict(attempt),
                "party": rows,
                "cash_delta": reader.read().player_money - source_raw.player_money,
                "authority": "teacher_preparation_learned_wild_battle",
                "fit_allowed": False,
            },
        )
