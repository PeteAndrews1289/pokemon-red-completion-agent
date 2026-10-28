"""Owned-TM bundles through existing machine and mixed-menu ports.

The model chooses machine, recipient and replacement together. The disclosed
capacity proxy describes attack inventory, not damage or a predicted win.
It never removes a legal direct-attack tradeoff from the model's choice set.
"""

from dataclasses import asdict, replace
from hashlib import sha256

from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import GoalCashOutcome, ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
)
from .observation import Badge
from .player_option_challenge import OptionChallenge
from .player_option_move_change import OptionMoveChange
from .provenance import canonical_sha256
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref, pokemon_red_species_ref
from .red_live_option_menu import supplemental_live_option
from .red_machine_teaching import execute_machine_lesson, plan_machine_lesson
from .red_party import PokemonRedPartyReader
from .red_party_pp import decode_red_party_pp
from .red_player_field_goals import _field_ready


def direct_attack_capacity(species_id, moves, pp):
    """Current charges times power/accuracy/STAB, not damage or tactical value.

    Status/fixed/OHKO/self-destruct attacks are unexpressible by this proxy.
    This does not claim they lack value in the actual battler.
    """
    types = RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(species_id)).types
    total = 0.0
    for slot in decode_red_party_pp(moves, pp).moves:
        if not slot.move_id:
            continue
        move = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(slot.move_id))
        if move.power <= 0 or move.effect_flags & {"ohko", "self_destruct", "fixed_damage"}:
            continue
        stab = 1.5 if move.type_name in types else 1.0
        total += slot.current_pp * move.power * move.accuracy * stab
    return total


def owned_machine_options(runtime, actions, *, rom, include_fly_lesson=False,
                          include_attack_lessons=True, include_move_change_facts=False):
    """Read-only finite inventory; selection stays in the ordinary model port."""
    if any(type(v) is not bool for v in (include_fly_lesson, include_attack_lessons, include_move_change_facts)):
        raise ValueError("machine lesson permissions must be boolean")
    if not _field_ready(runtime):
        return ()
    raw = runtime.reader.read()
    if any(getattr(raw, field) is None for field in (
        "bag_items", "party_species_ids", "party_moves", "party_pp", "party_hp",
    )):
        return ()
    state = runtime.emulator.save_state_bytes()
    rows = []
    for item, quantity in sorted(raw.bag_items):
        field_lesson = (
            include_fly_lesson and item == 197
            and not any(19 in row for row in raw.party_moves)
            and bool(int(raw.badge_bits or 0) & int(Badge.THUNDER))
        )
        attack_lesson = include_attack_lessons and 201 <= item <= 250
        if (not attack_lesson and not field_lesson) or quantity <= 0:
            continue
        for party_slot, species in enumerate(raw.party_species_ids, 1):
            if raw.party_hp[party_slot - 1] <= 0:
                continue
            for replace_slot in range(1, 5):
                try:
                    lesson = plan_machine_lesson(rom, runtime.reader, item_id=item,
                        party_slot=party_slot, replace_slot=replace_slot)
                except ValueError:
                    continue  # incompatible, redundant, HM or a wrong empty slot
                move = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(lesson.move_id))
                if (not field_lesson and
                        (move.power <= 0 or move.effect_flags &
                         {"ohko", "self_destruct", "fixed_damage"})):
                    continue
                index = party_slot - 1
                moves, pp = list(raw.party_moves[index]), list(raw.party_pp[index])
                before = direct_attack_capacity(species, tuple(moves), tuple(pp))
                moves[replace_slot - 1], pp[replace_slot - 1] = lesson.move_id, move.max_pp
                after = direct_attack_capacity(species, tuple(moves), tuple(pp))
                change = None
                if include_move_change_facts:
                    old_id = raw.party_moves[index][replace_slot - 1]
                    removed = (RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(old_id))
                               if old_id else None)
                    charges = decode_red_party_pp(raw.party_moves[index], raw.party_pp[index]).moves[replace_slot - 1]
                    types = RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(species)).types
                    observed_stats = getattr(raw, "party_stats", None)
                    stats = observed_stats[index] if observed_stats is not None else None
                    change = OptionMoveChange(
                        proposed=move, removed=removed,
                        proposed_current_pp=move.max_pp, proposed_maximum_pp=move.max_pp,
                        removed_current_pp=charges.current_pp if removed is not None else None,
                        removed_maximum_pp=charges.maximum_pp if removed is not None else None,
                        removed_stab=removed is not None and removed.type_name in types,
                        proposed_stab=move.type_name in types,
                        recipient_attack=stats[0] if stats is not None else None,
                        recipient_special_attack=stats[3] if stats is not None else None,
                    )
                binding = _machine_binding(runtime, actions, rom, lesson, state, raw,
                                           tuple(moves), tuple(pp), before, after,
                                           field_lesson=field_lesson)
                candidate = LivingDexOptionCandidate(
                    binding_ref=binding.binding_ref,
                    availability=LivingDexOptionAvailability.AVAILABLE,
                    features=LivingDexOptionFeatures(
                        LivingDexOptionKind.DEVELOP, 0.0,
                        1.0 if field_lesson else max(0.0, after - before) / max(1.0, after),
                        0.0, 0.04, 0.05, 0.0, 0.0, 0.2, 0.5,
                    ),
                    challenge=OptionChallenge(False, False, 0.0, 0.0, 0.0),
                    move_change=change,
                )
                rows.append(supplemental_live_option(binding=binding, candidate=candidate))
    if runtime.emulator.save_state_bytes() != state:
        raise ValueError("owned-machine inventory changed native state")
    if len({row.binding.binding_ref for row in rows}) != len(rows):
        raise ValueError("owned-machine inventory repeats a lesson")
    return tuple(rows)


def connect_move_change_inventory(menu, *, rom):
    """Expose model-owned legal lessons with portable facts for a V10 assembly.

    Preserve all existing callbacks and bindings, including the Fly reward.
    Matching lessons gain facts; other legal owned attacks are additional model
    choices. Neither this connector nor its observer selects or executes one.
    """
    previous = menu.enumerate_owned_machines
    if getattr(previous, "move_change_inventory", False):
        return

    def observe(runtime, actions, observation):
        source = runtime.emulator.save_state_bytes()
        old = tuple(previous(runtime, actions, observation)) if previous is not None else ()
        richer = owned_machine_options(runtime, actions, rom=rom,
            include_fly_lesson=True, include_move_change_facts=True)
        additions = {row.binding.binding_ref: row for row in richer}
        if len({row.binding.binding_ref for row in old}) != len(old):
            raise ValueError("owned-machine callback repeats a private binding")
        rows = []
        for row in old:
            counterpart = additions.pop(row.binding.binding_ref, None)
            if counterpart is not None:
                if (row.binding.kind != counterpart.binding.kind
                        or row.candidate.features != counterpart.candidate.features):
                    raise ValueError("owned-machine callback contradicts its legal lesson")
                # Keep the exact original executor/custody closure.
                row = replace(row, candidate=counterpart.candidate)
            rows.append(row)
        rows.extend(additions.values())
        if runtime.emulator.save_state_bytes() != source:
            raise ValueError("move-change inventory changed native state")
        return tuple(rows)

    observe.move_change_inventory = True
    menu.enumerate_owned_machines = observe


def _machine_binding(runtime, actions, rom, lesson, source, before, moves, pp,
                     capacity_before, capacity_after, *, field_lesson=False):
    claimed, terminal, receipt = False, None, None
    party_reader = PokemonRedPartyReader(runtime.emulator)
    experience = tuple(m.experience for m in party_reader.read().members)
    dex, boxes, pc = (runtime.reader.read_pokedex_state(), runtime.reader.read_all_box_states(),
                      runtime.reader.read_pc_items())
    expected_moves = tuple(moves if i == lesson.party_slot - 1 else row
                           for i, row in enumerate(before.party_moves))
    expected_pp = tuple(pp if i == lesson.party_slot - 1 else row
                        for i, row in enumerate(before.party_pp))
    bag = dict(before.bag_items)
    consumed = int(lesson.item_id >= 201)
    bag[lesson.item_id] -= consumed
    expected_bag = {item: quantity for item, quantity in bag.items() if quantity}

    def protected():
        after = runtime.reader.read()
        fields = ("map_id", "player_x", "player_y", "player_money", "party_species_ids",
                  "party_levels", "party_hp", "party_status", "badge_bits", "event_flags",
                  "battle_state", "party_count")
        return (
            all(getattr(after, f) == getattr(before, f) for f in fields)
            and after.party_moves == expected_moves and after.party_pp == expected_pp
            and dict(after.bag_items or ()) == expected_bag
            and tuple(m.experience for m in party_reader.read().members) == experience
            and runtime.reader.read_pokedex_state() == dex
            and runtime.reader.read_all_box_states() == boxes
            and runtime.reader.read_pc_items() == pc
            and _field_ready(runtime)
        )

    def execute():
        nonlocal claimed, terminal, receipt
        if claimed or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("owned-machine lesson is stale or consumed")
        claimed = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        execute_machine_lesson(runtime.emulator, actions, runtime.reader, lesson, rom=rom)
        if not protected():
            raise RuntimeError("owned-machine lesson changed protected native state")
        terminal = runtime.emulator.save_state_bytes()
        receipt = GoalExecutionReport(actions.actions_executed - a,
            runtime.emulator.frame_count - f, dict(
                mechanic="owned_native_machine_lesson", lesson=asdict(lesson),
                selected_bundle_authority="model_or_disclosed_equivalent_choice",
                normal_controller_inputs=True, learned_menu_execution=False,
                capacity_proxy=("missing_Fly_dependency_not_attack_gain" if field_lesson
                    else "current_PP_times_power_accuracy_STAB_not_damage_or_win"),
                capacity_before=capacity_before, capacity_after=capacity_after,
                machine_consumed=consumed, cash_debit=0, xp_gained=0,
                field_move_unlocked=lesson.move_id if field_lesson else None,
                objective_completed=False, registrations_gained=0,
            ))
        return receipt

    def verify(report):
        return (GoalVerification.succeeded() if receipt is not None and report is receipt
                and terminal == runtime.emulator.save_state_bytes() and protected()
                else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))

    return ExecutableGoalBinding(
        "pokemon.red:owned-machine:" + sha256(source).hexdigest() + ":"
        + canonical_sha256(asdict(lesson)), GoalKind.DEVELOP_TEAM, 0.04, 0.0,
        execute, verify, maximum_cash_debit=0,
        cash_outcome=GoalCashOutcome(sha256(source).hexdigest(), "preserves_cash_approach"),
    )
