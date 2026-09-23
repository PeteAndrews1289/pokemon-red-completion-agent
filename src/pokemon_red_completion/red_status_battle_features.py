"""Experimental status-aware move view; no hidden duration, roster or identity inputs.

The legacy view remains an exact prefix, so zero-padding a frozen head preserves
its scores. Effect metadata tells the learner what a move *does*, not when to use
it. Long-horizon cartridge returns, not this projector, supply preferences.
"""

from collections.abc import Mapping

import numpy as np

from .battle_semantics import BattleFeatureBatch
from .red_battle_catalog import PokemonRedBattleCatalog
from .red_trainer_practice_features import (
    MOVE_FEATURE_NAMES,
    MOVE_SCHEMA_ID,
    TrainerCandidateFeatures,
    _integer,
    _mapping,
    project_trainer_move_features,
)
from .red_trainer_practice_head import TrainerHeadModel

STATUS_MOVE_SCHEMA = "pokemon.core.battle.move-ranker.status.v1"
STATS = ("attack", "defense", "speed", "special", "accuracy", "evasion")
EFFECTS = ("sleep", "poison", "paralysis", "confusion", "disable", "heal", "rest")
STATUS_MOVE_NAMES = (
    *MOVE_FEATURE_NAMES,
    "status.player.confused",
    "status.opponent.confused",
    *(f"status.{side}.{stat}_stage" for side in ("player", "opponent") for stat in STATS),
    *(f"effect.{effect}" for effect in EFFECTS),
    *(f"effect.{direction}.{stat}" for direction in ("up", "down") for stat in STATS),
)


def project_status_moves(
    observation: Mapping[str, object], base: BattleFeatureBatch
) -> TrainerCandidateFeatures:
    legacy = project_trainer_move_features(observation, base)
    features = _mapping(observation.get("features"), "features")
    battle = _mapping(features.get("battle"), "battle")
    context = _mapping(battle.get("status_context"), "status context")
    if context.get("schema") != "pokemon.core.battle.status-context.v1":
        raise ValueError("status context schema differs")
    confused = (context.get("player_confused"), context.get("opponent_confused"))
    if any(type(x) is not bool for x in confused):
        raise ValueError("confusion state must be observed")
    stages: list[float] = []
    for side in ("player", "opponent"):
        values = context.get(f"{side}_stages")
        if not isinstance(values, list) or len(values) != 6:
            raise ValueError("six observed stat stages required")
        stages.extend(_integer(x, -6, 6, "stage") / 6 for x in values)
    lead = _mapping(_mapping(features.get("party"), "party").get("lead"), "lead")
    moves = lead.get("moves")
    if not isinstance(moves, list):
        raise ValueError("visible moves missing")
    catalog = PokemonRedBattleCatalog()
    by_slot = {_mapping(m, "move").get("slot_index"): m for m in moves}
    rows = []
    for slot, row in zip(base.slot_indices, legacy.candidate_vectors, strict=True):
        move = _mapping(by_slot.get(slot), "move")
        ref = move.get("move_ref")
        if not isinstance(ref, str):
            raise ValueError("move reference missing")
        effect = catalog.move_effect(ref)
        # Rest shares HEAL_EFFECT with Recover/Softboiled in Red, but induces sleep.
        labels = (
            effect == "SLEEP_EFFECT",
            effect == "POISON_EFFECT",
            effect == "PARALYZE_EFFECT",
            effect == "CONFUSION_EFFECT",
            effect == "DISABLE_EFFECT",
            effect == "HEAL_EFFECT",
            ref.endswith(":156"),
        )
        stage_effects = tuple(
            float(effect in {f"{stat.upper()}_{direction.upper()}{n}_EFFECT" for n in (1, 2)})
            for direction in ("up", "down")
            for stat in STATS
        )
        rows.append(
            (
                *row,
                *(float(x is True) for x in confused),
                *stages,
                *(float(x) for x in labels),
                *stage_effects,
            )
        )
    return TrainerCandidateFeatures(
        STATUS_MOVE_SCHEMA, STATUS_MOVE_NAMES, tuple(rows), legacy.candidate_slots
    )


def move_schema(schema: object) -> tuple[str, tuple[str, ...]]:
    from .red_balanced_status_features import BALANCED_STATUS_NAMES, BALANCED_STATUS_SCHEMA

    if schema == MOVE_SCHEMA_ID:
        return MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES
    if schema == STATUS_MOVE_SCHEMA:
        return STATUS_MOVE_SCHEMA, STATUS_MOVE_NAMES
    if schema == BALANCED_STATUS_SCHEMA:
        return BALANCED_STATUS_SCHEMA, BALANCED_STATUS_NAMES
    raise ValueError("unsupported move-head schema")


def project_for_head(observation, base, head: TrainerHeadModel) -> TrainerCandidateFeatures:
    from .red_balanced_status_features import (
        BALANCED_STATUS_SCHEMA,
        project_balanced_status_moves,
    )

    move_schema(head.schema_id)
    if head.schema_id == BALANCED_STATUS_SCHEMA:
        return project_balanced_status_moves(observation, base)
    return (
        project_status_moves(observation, base)
        if head.schema_id == STATUS_MOVE_SCHEMA
        else project_trainer_move_features(observation, base)
    )


def expand_frozen_move(head: TrainerHeadModel) -> TrainerHeadModel:
    if head.schema_id != MOVE_SCHEMA_ID or head.feature_names != MOVE_FEATURE_NAMES:
        raise ValueError("expected frozen legacy move head")
    weights = np.zeros((len(STATUS_MOVE_NAMES), head.weights1.shape[1]))
    weights[: len(MOVE_FEATURE_NAMES)] = head.weights1
    return TrainerHeadModel(
        STATUS_MOVE_SCHEMA,
        STATUS_MOVE_NAMES,
        weights,
        head.bias1,
        head.weights2,
        head.training_seed,
        head.training_objective,
    )


def status_choice_slots(
    projected: TrainerCandidateFeatures, legal_slots: tuple[int, ...], damage_head: TrainerHeadModel
) -> tuple[int, ...]:
    """The selector may choose status, but cannot silently replace K's damage ranking."""
    status_at = MOVE_FEATURE_NAMES.index("move.category.status")
    damage_slots = tuple(
        s
        for s in legal_slots
        if projected.candidate_vectors[projected.candidate_slots.index(s)][status_at] == 0
    )
    best = None
    if damage_slots:
        rows = tuple(
            projected.candidate_vectors[projected.candidate_slots.index(s)][
                : len(MOVE_FEATURE_NAMES)
            ]
            for s in damage_slots
        )
        best = damage_slots[damage_head.predict_index(rows)]
    return tuple(s for s in legal_slots if s == best or s not in damage_slots)
