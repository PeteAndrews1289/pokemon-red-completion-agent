"""Opt-in native nonlethal special-hit preparation for a declared wild target.

Existing critical-inclusive damage bounds supply an abstaining move selector.
Unknown incoming mechanics, volatile state, damaging residual status and missing
evidence mean no attack, not guessed safety. One explicitly enabled guarded
switch may propose a healthier weakener; no ball, Run or reset occurs here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .battle_recovery import switch_active_battler
from .battle_runtime import execute_bounded_battle_move_turn
from .observation import BattleMenuPhase, SemanticStateError
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_capture_weakening import safe_special_capture_move

_SUPPORTED_REPLIES = frozenset(
    {
        "NO_ADDITIONAL_EFFECT",
        "PARALYZE_SIDE_EFFECT1",
        "PARALYZE_SIDE_EFFECT2",
        "FREEZE_SIDE_EFFECT1",
        "FREEZE_SIDE_EFFECT2",
        "BURN_SIDE_EFFECT1",
        "BURN_SIDE_EFFECT2",
        "SPEED_UP2_EFFECT",
        "MIST_EFFECT",
        "HIGH_CRITICAL_EFFECT",
        "FLINCH_SIDE_EFFECT1",
        "FLINCH_SIDE_EFFECT2",
        "SPECIAL_UP2_EFFECT",
        "HEAL_EFFECT",
    }
)


@dataclass(frozen=True, slots=True)
class CaptureWeakeningResult:
    attempts: int
    damage: int
    stop_reason: str
    turns: tuple[dict[str, object], ...]
    setup: tuple[dict[str, object], ...] = ()


def living_capture_weakener(raw):
    """Lowest-level healthy member with a usable supported special attack.

    This is a mechanical proposal only. After switching, live critical-inclusive
    damage still decides whether ANY attack is allowed.
    """
    fields = (raw.party_moves, raw.party_pp, raw.party_hp, raw.party_max_hp,
              raw.party_levels, raw.party_status)
    if any(value is None for value in fields) or len({len(value) for value in fields}) != 1:
        return None
    candidates = []
    for index, (moves, pp, hp, maximum, level, status) in enumerate(zip(*fields, strict=True)):
        if index == raw.active_party_index or not maximum or hp <= maximum / 2 or status:
            continue
        for move_id, points in zip(moves, pp, strict=True):
            if not move_id or not points & 0x3F:
                continue
            ref = pokemon_red_move_ref(move_id)
            move = RED_BATTLE_CATALOG.resolve_move(ref)
            effect = RED_BATTLE_CATALOG.move_effect(ref)
            if move.category == "special" and move.power > 0 and (
                not move.effect_flags
                or effect in {"PARALYZE_SIDE_EFFECT1", "PARALYZE_SIDE_EFFECT2"}
            ):
                candidates.append((level, index))
                break
    return min(candidates)[1] if candidates else None


def prepare_nonlethal_capture(
    reader, actions, *, internal_species: int, level: int, maximum_attempts: int = 3,
    allow_weakener_switch: bool = False,
    emulator=None,
) -> CaptureWeakeningResult:
    from .observation import ItemId
    from .red_one_off_capture import OneOffCaptureRequest

    OneOffCaptureRequest(internal_species, level, ItemId.GREAT_BALL)
    if type(maximum_attempts) is not int or not 1 <= maximum_attempts <= 10:
        raise ValueError("capture weakening attempt limit differs")
    if type(allow_weakener_switch) is not bool:
        raise ValueError("capture weakener switching must be explicit")
    if allow_weakener_switch and emulator is None:
        raise ValueError("capture weakener switching requires the guarded emulator")
    start = reader.read()
    owned = reader.read_pokedex_state()
    boxes = reader.read_all_box_states()
    rows: list[dict[str, object]] = []
    setup: list[dict[str, object]] = []

    def result(reason):
        return CaptureWeakeningResult(
            len(rows), sum(int(row["damage"]) for row in rows), reason, tuple(rows), tuple(setup)
        )

    for _ in range(maximum_attempts):
        raw = reader.read()
        identity = reader.read_wild_capture_identity()
        if (
            raw.battle_state != 1
            or identity is None
            or identity.original_species_id != internal_species
            or raw.enemy_level != level
            or not raw.enemy_hp
            or not raw.battler_hp
            or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
        ):
            raise ValueError("capture weakening lacks its declared live MAIN boundary")
        if (
            raw.map_id != start.map_id
            or raw.player_money != start.player_money
            or raw.party_species_ids != start.party_species_ids
            or raw.bag_items != start.bag_items
            or reader.read_pokedex_state() != owned
            or reader.read_all_box_states() != boxes
        ):
            raise RuntimeError("capture weakening protected state drifted")
        status = reader.read_enemy_capture_status()
        if status is None or status & 0x18:
            return result("target_residual_damage_or_unknown_status")
        replies = reader.read_enemy_capture_moves()
        read_pp = getattr(reader, "read_enemy_capture_pp", None)
        reply_pp = read_pp() if callable(read_pp) else None
        if (
            replies is None or len(replies) != 4 or reply_pp is None or len(reply_pp) != 4
            or not any(move and points for move, points in zip(replies, reply_pp, strict=True))
        ):
            return result("unobserved_or_exhausted_enemy_reply_pp")
        reply_effects = tuple(
            RED_BATTLE_CATALOG.move_effect(pokemon_red_move_ref(move))
            for move in replies or ()
            if move
        )
        if not reply_effects or any(effect not in _SUPPORTED_REPLIES for effect in reply_effects):
            return result("unsupported_enemy_reply")
        healing_reply = "HEAL_EFFECT" in reply_effects
        if healing_reply and (
            type(raw.enemy_max_hp) is not int
            or not 0 < raw.enemy_hp <= raw.enemy_max_hp
        ):
            return result("unproven_enemy_healing_limit")
        try:
            inputs = reader.read_wild_special_damage_inputs(raw)
        except SemanticStateError:
            return result("unsupported_live_damage_state")
        selected = safe_special_capture_move(raw, inputs, allow_paralysis_side_effect=True)
        if selected is None and allow_weakener_switch and not setup:
            index = living_capture_weakener(raw)
            if index is not None:
                pp_before = raw.party_pp
                switch_active_battler(actions, reader, emulator, index,
                    expected_battle_state=1, label="bounded capture weakener",
                    allow_faint_outcome=True)
                changed = reader.read()
                changed_identity = reader.read_wild_capture_identity()
                if (
                    changed.battle_state != 1 or changed.active_party_index != index
                    or changed.party_pp != pp_before or changed.map_id != start.map_id
                    or changed.player_money != start.player_money
                    or changed.party_species_ids != start.party_species_ids
                    or changed.bag_items != start.bag_items
                    or reader.read_pokedex_state() != owned
                    or reader.read_all_box_states() != boxes
                    or changed_identity is None
                    or changed_identity.original_species_id != internal_species
                    or changed.enemy_level != level or not changed.enemy_hp
                ):
                    raise RuntimeError("capture weakener switch changed protected state")
                setup.append(dict(party_slot=index + 1, learned=False,
                    selection="lowest_level_healthy_supported_special", move_selected=False))
                if not changed.battler_hp:
                    return result("weakener_fainted")
                # Reobserve status, replies, stats and critical bounds after switching.
                raw = changed
                status = reader.read_enemy_capture_status()
                if status is None or status & 0x18:
                    return result("target_residual_damage_or_unknown_status")
                try:
                    inputs = reader.read_wild_special_damage_inputs(raw)
                except SemanticStateError:
                    return result("unsupported_live_damage_state")
                selected = safe_special_capture_move(raw, inputs, allow_paralysis_side_effect=True)
        if selected is None:
            return result("no_proven_nonlethal_move")
        slot, upper = selected
        if raw.party_pp is None or raw.active_party_index is None:
            raise ValueError("capture weakening lacks party PP evidence")
        turn = execute_bounded_battle_move_turn(
            reader,
            actions,
            expected_map=raw.map_id,
            selected_slot=slot,
            expected_battle_state=1,
            settle_to_next_decision=True,
            label="bounded nonlethal capture weakening",
        )
        after = reader.read()
        after_identity = reader.read_wild_capture_identity()
        if (
            after.battle_state != 1
            or after_identity is None
            or after_identity.original_species_id != internal_species
            or after.enemy_level != level
            or after.enemy_hp is None
            or after.enemy_hp <= 0
            or (after.enemy_hp > raw.enemy_hp and not healing_reply)
            or (healing_reply and (
                after.enemy_max_hp != raw.enemy_max_hp or after.enemy_hp > raw.enemy_max_hp
            ))
            or raw.enemy_hp - after.enemy_hp > upper
            or after.party_pp is None
            or after.active_party_index != raw.active_party_index
            or after.map_id != start.map_id
            or after.player_money != start.player_money
            or after.party_species_ids != start.party_species_ids
            or after.bag_items != start.bag_items
            or reader.read_pokedex_state() != owned
            or reader.read_all_box_states() != boxes
        ):
            raise RuntimeError("capture weakening exceeded its nonlethal/protected contract")
        expected = [list(p) for p in raw.party_pp]
        # PP Up bits remain untouched; a zero-PP move was never admitted.
        expected[raw.active_party_index][slot - 1] -= int(turn.move_executed)
        if after.party_pp != tuple(tuple(p) for p in expected):
            raise RuntimeError("capture weakening PP spend differs")
        rows.append(
            dict(
                move_slot=slot,
                move_id=raw.active_party_moves[slot - 1],
                upper_damage=upper,
                hp_before=raw.enemy_hp,
                hp_after=after.enemy_hp,
                damage=max(0, raw.enemy_hp - after.enemy_hp),
                hp_net_change=after.enemy_hp - raw.enemy_hp,
                enemy_hp_restored=after.enemy_hp > raw.enemy_hp,
                move_executed=turn.move_executed,
                critical_included=True,
                learned=False,
            )
        )
        if after.enemy_hp > raw.enemy_hp:
            return result("target_healed")
    return result("attempt_limit")
