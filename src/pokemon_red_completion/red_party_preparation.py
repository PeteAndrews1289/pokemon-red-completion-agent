"""Explicit DEVELOPMENT preparation, separate from conservative cash funding.

Teacher selects the trainee/venue; exact qualified K owns all battle choices.
The caller enforces whole-excursion controller budgets and retains terminal state
even on an exception. No rewind, wild-policy fallback or artificial cash demand.
"""

from dataclasses import asdict, replace
from time import monotonic

from .party_preparation import PreparationAttempt, next_preparation_decision
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_goal_skills import _raw_party_fully_restored
from .red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
)
from .red_party import PokemonRedPartyReader
from .red_story_funding import _execute_admitted_trainer_excursion, center_trainer_candidates
from .red_team_training import swap_field_party_slots
from .red_trainer_evolution import RedTrainerEvolutionGuard
from .red_training_ground_route import RedVermilionGroundTransition
from .team_training import TeamTrainingDirective


def observe_preparation_members(emulator, plan):
    """Rebind current slots to the frozen roles using collision-checked fingerprints."""
    reader = PokemonRedPartyReader(emulator)
    party, refs = reader.read(), reader.preparation_specimen_refs()
    old = {m.specimen_ref: m for m in plan.roster}
    if set(refs) != set(old):
        raise ValueError("preparation roster changed")
    return tuple(
        replace(old[ref], observation=mon) for ref, mon in zip(refs, party.members, strict=True)
    )


def preparation_trainee(plan, members, attempts=()):
    decision = next_preparation_decision(plan, members, attempts)
    if decision.directive not in {
        TeamTrainingDirective.TRAIN_MEMBER,
        TeamTrainingDirective.SWITCH_TRAINEE,
    }:
        raise ValueError(f"preparation cannot start an excursion: {decision.reason}")
    return next(m for m in members if m.observation.slot == decision.target_slot)


def preparation_trainer_candidates(rom, reader, route, plan, members, attempts=()):
    """Risk-limited local opportunity, not a claim of learned venue selection."""
    trainee = preparation_trainee(plan, members, attempts).observation
    has_attack = any(
        RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(m.move_id)).category != "status"
        and "self_destruct"
        not in RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(m.move_id)).effect_flags
        for m in trainee.usable_moves
    )
    if not has_attack:
        return ()
    return tuple(
        c
        for c in center_trainer_candidates(rom, reader, route)
        if max(1, trainee.level - 8) <= max(m.level for m in c.quote.party) <= trainee.level
    )


def execute_preparation_excursion(
    *,
    rom,
    reader,
    actions,
    emulator,
    battler,
    adapter,
    target,
    source_raw,
    plan,
    attempts,
    record,
    cost_snapshot,
    hideout_timing,
):
    """One retained attempt; emit actual all-party costs even when execution fails."""
    if (
        not isinstance(battler, FrozenTrainerBattler)
        or battler.model_sha256 != FROZEN_K_SHA256
        or battler.qualification_sha256 != K_QUALIFICATION_SHA256
    ):
        raise ValueError("preparation requires exact qualified K")
    if reader.read() != source_raw or emulator.pressed_buttons:
        raise ValueError("preparation source changed before input")
    if not _raw_party_fully_restored(source_raw):
        raise ValueError("preparation requires full party HP, status and PP restoration")
    members = observe_preparation_members(emulator, plan)
    trainee = preparation_trainee(plan, members, attempts)
    route = replace(
        RedVermilionGroundTransition.from_rom(rom),
        full_event_offsets=True,
        observe_terrain=True,
        excluded_maps=frozenset({127, 203, 236}),
    )
    if target not in preparation_trainer_candidates(rom, reader, route, plan, members, attempts):
        raise ValueError("trainer is not in the preparation inventory")
    if any(m.observation.experience is None for m in members):
        raise ValueError("preparation requires measured experience")
    record(
        "preparation-choice",
        {
            "authority": "disclosed_teacher_preparation",
            "learned_preparation": False,
            "trainee_ref": trainee.specimen_ref,
            "initial_slot": trainee.observation.slot,
            "target_level": dict(plan.targets)[trainee.specimen_ref],
            "opposition_reference": plan.opposition_level,
            "trainer_map": target.trainer.map_id,
            "trainer_event": target.trainer.event_flag,
            "trainer_levels": [m.level for m in target.quote.party],
            "cash_before": source_raw.player_money,
            "battle_model_sha256": FROZEN_K_SHA256,
            "attempts_already_spent": len(attempts),
            "sales": 0,
            "fit_allowed": False,
        },
    )
    started = monotonic()
    start_actions, start_frames = cost_snapshot()
    result = None
    error = None
    heals = 0

    def excursion_record(name, value):
        nonlocal heals
        if name == "healing-started":
            heals += 1
        record(name, value)

    try:
        swap_field_party_slots(
            actions,
            reader,
            emulator,
            first_index=0,
            second_index=trainee.observation.slot - 1,
            label="declared combat preparation trainee",
            hideout_timing=hideout_timing,
        )
        current_members = observe_preparation_members(emulator, plan)
        if current_members[0].specimen_ref != trainee.specimen_ref:
            raise RuntimeError("preparation lead swap did not bind the selected specimen")
        current = reader.read()
        if target not in preparation_trainer_candidates(
            rom, reader, route, plan, current_members, attempts
        ):
            raise ValueError("preparation opportunity changed after party swap")
        result = _execute_admitted_trainer_excursion(
            rom=rom,
            reader=reader,
            actions=actions,
            emulator=emulator,
            battler=battler,
            adapter=adapter,
            target=target,
            source_raw=current,
            record=excursion_record,
            route=route,
            preparation_evolution_guard=RedTrainerEvolutionGuard.from_rom(rom, emulator),
        )
        result = {
            **result,
            "goal_authority": "disclosed_teacher_preparation",
            "learned_preparation": False,
        }
        return result
    except BaseException as caught:
        error = caught
        raise
    finally:
        end_actions, end_frames = cost_snapshot()
        # Preserve costs before reading optional instrumentation: if the latter
        # fails, the caller still has costs plus its immutable terminal save.
        record(
            "preparation-cost",
            {
                "actions": end_actions - start_actions,
                "frames": end_frames - start_frames,
                "seconds": monotonic() - started,
                "error": None if error is None else str(error),
                "completed_excursion": result is not None,
            },
        )
        after = {m.specimen_ref: m.observation for m in observe_preparation_members(emulator, plan)}
        rows = []
        for member in members:
            old, new = member.observation, after[member.specimen_ref]
            if new.experience is None or new.experience < old.experience:
                raise RuntimeError("preparation XP accounting regressed")
            rows.append(
                {
                    "specimen_ref": member.specimen_ref,
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
        receipt = PreparationAttempt(
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
                "attempt": asdict(receipt),
                "party": rows,
                "cash_delta": reader.read().player_money - source_raw.player_money,
                "authority": "teacher_trainee_and_venue_learned_battle",
                "fit_allowed": False,
            },
        )
