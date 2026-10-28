"""Control features for concrete child proposals, never teacher action selection.

Damage is a deliberately approximate public-stat estimate, not hidden opponent
HP/stats or a cartridge oracle. It is an input to a learned choice, not a rule.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.battle_semantics import BattleFeatureBatch, BattleMechanicsCatalog
from pokemon_red_completion.red_status_battle_features import project_for_head
from pokemon_red_completion.red_trainer_practice_features import (
    CONTROL_FEATURE_NAMES_V2,
    MOVE_FEATURE_NAMES,
    SWITCH_FEATURE_NAMES_V2,
    _integer,
    _mapping,
    _visible_stats,
    project_trainer_control_features,
    project_trainer_switch_features,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel

SELECTED_MOVE_NAMES = (
    "move.category.physical",
    "move.category.special",
    "move.category.status",
    "move.accuracy",
    "move.priority",
    "move.pp_fraction",
    "move.effective_power_fraction",
    "move.type_effectiveness_fraction",
    "interaction.physical_attack_over_estimated_defense",
    "interaction.special_over_estimated_special",
)
SELECTED_SWITCH_NAMES = tuple(
    name for name in SWITCH_FEATURE_NAMES_V2 if name.startswith("candidate.")
)
PROPOSED_STATE_NAMES = (
    *CONTROL_FEATURE_NAMES_V2,
    "proposal.is_decline",
    "proposal.damage_estimate_available",
    "proposal.estimated_damage_over_remaining_hp",
    "proposal.estimated_finishing_margin",
    *(f"proposal.{name}" for name in SELECTED_MOVE_NAMES),
    *(f"proposal.{name}" for name in SELECTED_SWITCH_NAMES),
)
PROPOSED_CONTROL_SCHEMA = "pokemon.core.battle.control.proposed-components.v1"
PROPOSED_CONTROL_NAMES = (
    "action.attack_or_decline",
    "action.switch",
    *(f"attack_or_decline.{name}" for name in PROPOSED_STATE_NAMES),
    *(f"switch.{name}" for name in PROPOSED_STATE_NAMES),
)


@dataclass(frozen=True, slots=True)
class ProposedControl:
    move_slot: int | None
    switch_slot: int
    candidate_vectors: tuple[tuple[float, ...], tuple[float, ...]]


def proposed_control(
    observation: Mapping[str, object],
    *,
    catalog: BattleMechanicsCatalog,
    move_head: TrainerHeadModel,
    switch_head: TrainerHeadModel,
    move_batch: BattleFeatureBatch | None,
    move_slots: tuple[int, ...],
    switch_slots: tuple[int, ...],
) -> ProposedControl:
    """Use exactly the supplied legal child inventories at fit and play time."""
    switches = project_trainer_switch_features(observation, catalog)
    if not switch_slots or len(set(switch_slots)) != len(switch_slots):
        raise ValueError("proposed control needs unique legal reserves")
    switch_rows = tuple(
        switches.candidate_vectors[switches.candidate_slots.index(slot)] for slot in switch_slots
    )
    switch_index = switch_head.predict_index(switch_rows)
    move_slot = None
    move_row = None
    if move_slots:
        if move_batch is None or len(set(move_slots)) != len(move_slots):
            raise ValueError("proposed control move inventory differs")
        moves = project_for_head(observation, move_batch, move_head)
        rows = tuple(
            moves.candidate_vectors[moves.candidate_slots.index(slot)] for slot in move_slots
        )
        index = move_head.predict_index(rows)
        move_slot, move_row = move_slots[index], rows[index]
    common = tuple(
        project_trainer_control_features(
            observation,
            catalog=catalog,
            move_batch=move_batch,
        ).tolist()
    )
    move_values = (
        tuple(move_row[MOVE_FEATURE_NAMES.index(name)] for name in SELECTED_MOVE_NAMES)
        if move_row is not None
        else (0.0,) * len(SELECTED_MOVE_NAMES)
    )
    switch_values = tuple(
        switch_rows[switch_index][SWITCH_FEATURE_NAMES_V2.index(name)]
        for name in SELECTED_SWITCH_NAMES
    )
    damage = estimated_finishing_features(observation, move_row)
    state = (*common, float(move_slot is None), *damage, *move_values, *switch_values)
    if len(state) != len(PROPOSED_STATE_NAMES) or any(
        not math.isfinite(x) or not -1 <= x <= 1 for x in state
    ):
        raise ValueError("proposed control feature range differs")
    zeros = (0.0,) * len(state)
    return ProposedControl(
        move_slot,
        switch_slots[switch_index],
        (
            (1.0, 0.0, *state, *zeros),
            (0.0, 1.0, *zeros, *state),
        ),
    )


def estimated_finishing_features(
    observation: Mapping[str, object],
    move_row: tuple[float, ...] | None,
) -> tuple[float, float, float]:
    """Approximate neutral-stat noncritical damage; unusual effects stay unknown."""
    if move_row is None:
        return (0.0, 0.0, 0.0)
    values = dict(zip(MOVE_FEATURE_NAMES, move_row[:len(MOVE_FEATURE_NAMES)], strict=True))
    if values["move.category.status"] or any(
        values[f"move.effect.{flag}"]
        for flag in (
            "fixed_damage",
            "ohko",
            "counter",
            "multi_hit",
            "charge",
            "self_destruct",
        )
    ):
        return (0.0, 0.0, 0.0)
    _, player, opponent, _ = _visible_stats(observation)
    features = _mapping(observation.get("features"), "features")
    battle = _mapping(features.get("battle"), "battle")
    party = _mapping(features.get("party"), "party")
    lead = _mapping(party.get("lead"), "lead")
    level = _integer(lead.get("level"), 1, 100, "player level")
    foe_level = _integer(battle.get("opponent_level"), 1, 100, "opponent level")
    bases = _mapping(battle.get("opponent_public_base_stats"), "public opponent")
    hp_base = _integer(bases.get("hp"), 1, 255, "base HP")
    ratio = battle.get("opponent_hp_ratio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
        raise ValueError("opponent public HP ratio differs")
    remaining = max(1.0, ((2 * (hp_base + 8) * foe_level) // 100 + foe_level + 10) * ratio)
    physical = bool(values["move.category.physical"])
    stage_key = "player_attack_stage" if physical else "player_special_stage"
    attack_stage = _integer(battle.get(stage_key), -6, 6, "player stage")
    defense_stage = (
        _integer(battle.get("opponent_defense_stage"), -6, 6, "defense stage") if physical else 0
    )

    def stage(value: int) -> float:
        return (2 + value) / 2 if value >= 0 else 2 / (2 - value)

    attack = player[0 if physical else 3] * stage(attack_stage)
    if physical and lead.get("status") == "burn":
        attack *= 0.5
    defense = opponent[1 if physical else 3] * stage(defense_stage)
    power = values["move.power_fraction"] * 255
    effectiveness = values["move.type_effectiveness_fraction"] * 4
    stab = 1.5 if values["move.stab"] else 1.0
    damage = (
        (((2 * level / 5 + 2) * power * attack / max(1, defense)) / 50 + 2)
        * stab
        * effectiveness
        * 0.925
    )
    multiple = damage / remaining
    return (1.0, min(multiple, 4.0) / 4.0, max(-1.0, min(1.0, multiple - 1.0)))
