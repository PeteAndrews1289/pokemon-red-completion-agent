"""Narrow Red incoming-turn bounds, not a general battle simulator.

Uses pinned core.asm GetDamageVarsForEnemyAttack/CalculateDamage semantics:
ordinary and critical stats separately, byte scaling, doubled critical level,
maximum random roll, STAB and type multipliers. Unsupported effects abstain.
The caller must re-observe before each action and verify the resulting state.
"""

from __future__ import annotations

from math import ceil

from .observation import TrainerDamageObservation
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref


class TrainerDamageError(ValueError):
    """The bounded ordinary-attack model cannot establish incoming damage."""


def ordinary_damage_upper(
    *,
    level: int,
    power: int,
    attack: int,
    defense: int,
    critical: bool,
    stab: bool,
    effectiveness: float,
) -> int:
    """Upper integer damage for one supported direct hit, including rounding.

    Ceil after combined type/STAB multiplication can overestimate integer
    cartridge rounding. No accuracy, AI preference, sleep or recharge discount.
    Stats above ten bits and zero divisors are unsupported, never assumed safe.
    """
    for value, upper in ((level, 100), (power, 250), (attack, 1023), (defense, 1023)):
        if type(value) is not int or not 1 <= value <= upper:
            raise TrainerDamageError("incoming damage numeric domain differs")
    if type(critical) is not bool or type(stab) is not bool:
        raise TrainerDamageError("incoming damage flags differ")
    if effectiveness not in (0.0, 0.25, 0.5, 1.0, 2.0, 4.0):
        raise TrainerDamageError("incoming type multiplier differs")
    if effectiveness == 0:
        return 0
    if attack > 255 or defense > 255:
        attack, defense = max(1, attack // 4), defense // 4
    if defense == 0:
        raise TrainerDamageError("cartridge damage divisor would be zero")
    effective_level = level * (2 if critical else 1)
    neutral = min(997, ((2 * effective_level // 5 + 2) * power * attack // defense) // 50) + 2
    return ceil(neutral * (1.5 if stab else 1.0) * effectiveness)


def incoming_damage_bounds(observation: TrainerDamageObservation) -> tuple[int, ...]:
    """Worst supported ordinary hit per member, including all multi-hit strikes.

    All multi-hit moves conservatively receive five critical hits. Damage-side
    status adds a full ceil(maxHP/16) residual allowance even for paralysis/freeze.
    Existing poison/burn also receive residual allowance; toxic/seeded/transformed
    states must already have been rejected by the observation adapter.
    Pure status and indirect damage effects abstain in this first recovery scope.
    """
    raw = observation.raw
    if (
        raw.battle_state != 2
        or raw.enemy_level is None
        or raw.party_max_hp is None
        or raw.party_status is None
        or raw.party_count is None
        or len(observation.defenses) != raw.party_count
        or len(observation.party_types) != raw.party_count
        or len(raw.party_max_hp) != raw.party_count
        or len(raw.party_status) != raw.party_count
    ):
        raise TrainerDamageError("incoming damage observation is incomplete")
    if len(observation.moves) != 4 or not any(observation.moves):
        raise TrainerDamageError("incoming damage move inventory is incomplete")
    result = [0] * raw.party_count
    for move_id in observation.moves:
        if not move_id:
            continue
        ref = pokemon_red_move_ref(move_id)
        move = RED_BATTLE_CATALOG.resolve_move(ref)
        attack_type = RED_BATTLE_CATALOG.switch_entry_attack_type(ref)
        if attack_type is None or "confusion" in move.effect_flags:
            raise TrainerDamageError("status/confusion incoming turns are not yet qualified")
        special = move.category == "special"
        attack = observation.enemy_special if special else observation.enemy_attack
        base_attack = observation.enemy_base_special if special else observation.enemy_base_attack
        for index, (defense, spec, base_defense, base_spec) in enumerate(observation.defenses):
            factor = RED_BATTLE_CATALOG.type_effectiveness(
                attack_type,
                observation.party_types[index],
            )
            worst = max(
                ordinary_damage_upper(
                    level=raw.enemy_level,
                    power=move.power,
                    attack=base_attack if critical else attack,
                    defense=(base_spec if special else base_defense)
                    if critical
                    else (spec if special else defense),
                    critical=critical,
                    stab=attack_type in observation.enemy_types,
                    effectiveness=factor,
                )
                for critical in (False, True)
            )
            worst *= 5 if "multi_hit" in move.effect_flags else 1
            if "status" in move.effect_flags or raw.party_status[index] & 0x18:
                worst += ceil(raw.party_max_hp[index] / 16)
            result[index] = max(result[index], worst)
    return tuple(result)
