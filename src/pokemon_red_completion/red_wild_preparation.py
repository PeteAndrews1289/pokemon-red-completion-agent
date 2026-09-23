"""Bounded DEVELOPMENT wild knockout excursion; capture controllers unchanged."""

from dataclasses import asdict, replace
from time import monotonic

from .actions import MacroAction, MacroActionKind
from .battle_runtime import BattleRuntimeTiming
from .party import StatusCondition
from .party_preparation import PreparationAttempt
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_goal_skills import _raw_party_fully_restored
from .red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256, FrozenTrainerBattler
from .red_party_preparation import observe_preparation_members, preparation_trainee
from .red_story_funding import restore_story_team
from .red_team_training import swap_field_party_slots
from .red_trainer_evolution import RedTrainerEvolutionGuard


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
    pp = sum(
        move.current_pp
        for move in trainee.usable_moves
        if RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move.move_id)).category != "status"
        and "self_destruct"
        not in RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move.move_id)).effect_flags
    )
    return "trainee_attack_pp_low" if pp < 5 else None


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
):
    """One knockout and free recovery; caller meters and retains every terminal."""
    if (
        not isinstance(battler, FrozenTrainerBattler)
        or battler.model_sha256 != FROZEN_K_SHA256
        or battler.qualification_sha256 != K_QUALIFICATION_SHA256
    ):
        raise ValueError("wild preparation requires exact K development actor")
    if type(maximum_battles) is not int or not 1 <= maximum_battles <= 8:
        raise ValueError("wild preparation battle count outside bound")
    if minimum_ready_members is not None and (
        type(minimum_ready_members) is not int
        or not 1 <= minimum_ready_members <= source_raw.party_count
    ):
        raise ValueError("invalid minimum battle-ready party count")
    if type(maximum_seek_steps) is not int or not 1 <= maximum_seek_steps <= 120:
        raise ValueError("wild preparation seek limit outside bound")
    if reader.read() != source_raw or emulator.pressed_buttons:
        raise ValueError("wild preparation source changed")
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
    stop_reason = "encounter_limit"
    nonwinning_exit = False
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
            "navigation_wild_policy": "bounded_existing_flee_support",
            "fit_allowed": False,
        },
    )
    try:
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
        replace(route, destination_map=corridor.map_id, destination_at=corridor.origin_at)(
            actions, reader, emulator
        )
        for battle_index in range(maximum_battles):
            live_members = observe_preparation_members(emulator, plan)
            if maximum_battles > 1:
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
            if reader.read().battle_state != 1:
                raise RuntimeError("wild preparation seek ended without a wild encounter")

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

            episode = battler.run_wild_training(
                reader,
                actions,
                expected_map=corridor.map_id,
                timing=BattleRuntimeTiming(),
                decision_guard=guard,
            )
            nonwinning_exit = (
                not episode.battle_won
                and episode.stop_reason == "battle_exited_without_win"
                and reader.read().battle_state == 0
            )
            if not episode.battle_won and not nonwinning_exit:
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
                raise RuntimeError("wild encounter produced no measured XP")
        after_battle = observe_preparation_members(emulator, plan)
        xp = sum(m.observation.experience for m in after_battle) - sum(
            m.observation.experience for m in members
        )
        if xp <= 0 and not nonwinning_exit:
            raise RuntimeError("wild knockout produced no measured XP")
        targets = dict(plan.targets)
        reserve_xp = sum(
            m.observation.experience for m in after_battle if m.specimen_ref in targets
        ) - sum(m.observation.experience for m in members if m.specimen_ref in targets)
        replace(route, destination_map=int(source_raw.map_id), destination_at=(7, 3))(
            actions, reader, emulator
        )
        heals += 1
        record("healing-started", {"home_map": int(source_raw.map_id)})
        restore_story_team(reader, actions, emulator, adapter)
        final = reader.read()
        if (
            not _raw_party_fully_restored(final)
            or not evolution.matches(bound, final)
            or final.player_money != source_raw.player_money
            or final.bag_items != source_raw.bag_items
            or final.map_id != source_raw.map_id
            or (final.player_y, final.player_x) != (3, 3)
            or final.battle_state
            or not reader.read_input_readiness().ready
            or emulator.pressed_buttons
        ):
            raise RuntimeError("wild preparation healed return did not verify")
        if reserve_xp <= 0 and not nonwinning_exit:
            raise RuntimeError("wild preparation produced no reserve XP; healed then stopped")
        completed = True
        return {
            "status": "complete" if reserve_xp > 0 else "no_progress",
            "battles": battles,
            "stop_reason": stop_reason,
            "xp_gained": xp,
            "battle_authority": "frozen_k_wild_training_development",
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
