"""Conservative pure-special weakening, not a trainer knockout policy."""

from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_trainer_damage import ordinary_damage_upper


def safe_special_capture_move(raw, inputs):
    """Return (one-based move slot, critical-inclusive upper damage), or None.

    Abstain on secondary effects, physical/special mechanics and moves that
    could knock out the target. A caller may throw a ball instead of attacking.
    The adapter supplies conservative live/unmodified stats. No species recipe.
    """
    attack, defense, own_types, enemy_types = inputs
    if (
        raw.battle_state != 1
        or raw.active_party_level is None
        or raw.enemy_hp is None
        or not raw.active_party_moves
        or raw.active_party_pp is None
        or len(raw.active_party_moves) != len(raw.active_party_pp)
    ):
        raise ValueError("capture weakening requires complete live moves and HP")
    candidates = []
    for slot, (move_id, pp) in enumerate(
        zip(raw.active_party_moves, raw.active_party_pp, strict=True), 1
    ):
        if (
            not move_id
            or not pp & 0x3F
            or (raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0)
        ):
            continue
        move = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move_id))
        if move.category != "special" or move.power <= 0 or move.effect_flags:
            continue
        upper = ordinary_damage_upper(
            level=raw.active_party_level,
            power=move.power,
            attack=attack,
            defense=defense,
            critical=True,
            stab=move.type_name in own_types,
            effectiveness=RED_BATTLE_CATALOG.type_effectiveness(move.type_name, enemy_types),
        )
        if 0 < upper < raw.enemy_hp:
            candidates.append((upper, slot))
    if not candidates:
        return None
    upper, slot = min(candidates)
    return slot, upper
