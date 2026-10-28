"""Compact observable effect/condition interactions for a learned status selector.

No action is chosen or masked here. Mechanics facts follow the pinned pokered
effects.asm and move_effects/{paralyze,heal}.asm. Availability indicators are
partial conditions, not promises of success (accuracy, Substitute, recharge and
other special mechanics can matter). No hidden duration, enemy stats or RNG.
"""

from collections.abc import Mapping

from .battle_semantics import BattleFeatureBatch
from .red_status_battle_features import STATUS_MOVE_NAMES, project_status_moves
from .red_trainer_practice_features import TrainerCandidateFeatures

BALANCED_STATUS_SCHEMA = "pokemon.core.battle.move-ranker.status.v2"
FAMILIES = ("sleep", "paralysis", "poison", "confusion", "accuracy", "disable", "heal", "rest")
COMPACT_STATUS_NAMES = (
    "choice.status",
    *(f"choice.effect.{family}" for family in FAMILIES),
    "choice.major_status_occupied",
    "choice.poison_type_immune",
    "choice.electric_paralysis_type_immune",
    "choice.already_confused",
    "choice.accuracy_floor",
    "choice.heal_full_hp",
    "choice.heal_missing_hp",
    "choice.rest_missing_hp",
    "choice.rest_existing_affliction",
    "choice.player_hp",
    "choice.opponent_hp",
    "choice.player_speed_margin",
    "choice.damage_alternative_fraction",
    "choice.damage_alternative_finishing_margin",
    "choice.accuracy",
    "choice.pp",
    "choice.confusion_self",
    "choice.player_asleep",
    "choice.accuracy_reduction_so_far",
)
BALANCED_STATUS_NAMES = (*STATUS_MOVE_NAMES, *COMPACT_STATUS_NAMES)


def project_balanced_status_moves(
    observation: Mapping[str, object], base: BattleFeatureBatch
) -> TrainerCandidateFeatures:
    # Local import avoids the proposal module's schema-dispatch dependency cycle.
    from .red_trainer_proposed_control import estimated_finishing_features

    previous = project_status_moves(observation, base)
    dictionaries = [dict(zip(STATUS_MOVE_NAMES, row, strict=True))
                    for row in previous.candidate_vectors]
    estimates = [estimated_finishing_features(observation, row)
                 for row, legal in zip(previous.candidate_vectors, base.legal_mask, strict=True)
                 if legal and not row[STATUS_MOVE_NAMES.index("move.category.status")]]
    damage = max(estimates, key=lambda estimate: estimate[1], default=(0., 0., 0.))
    rows = []
    for row, values in zip(previous.candidate_vectors, dictionaries, strict=True):
        if not values["move.category.status"]:
            rows.append((*row, *((0.,) * len(COMPACT_STATUS_NAMES))))
            continue
        sleep = values["effect.sleep"]
        paralyze = values["effect.paralysis"]
        poison = values["effect.poison"]
        confusion = values["effect.confusion"]
        accuracy = values["effect.down.accuracy"]
        disable = values["effect.disable"]
        rest = values["effect.rest"]
        heal = values["effect.heal"]
        missing = 1 - values["state.player_hp_ratio"]
        extras = (
            1., sleep, paralyze, poison, confusion, accuracy, disable, heal * (1-rest), rest,
            (sleep + paralyze + poison) * (1-values["observable.opponent.status.none"]),
            poison * values["state.opponent_type.poison"],
            paralyze * values["move.type.electric"] * values["state.opponent_type.ground"],
            confusion * values["status.opponent.confused"],
            accuracy * float(values["status.opponent.accuracy_stage"] == -1),
            heal * float(missing == 0), heal * missing, rest * missing,
            rest * (1-values["state.player_status.none"]),
            values["state.player_hp_ratio"], values["state.opponent_hp_ratio"],
            max(-1., min(1., values["interaction.player_speed_over_estimated_speed"] * 4 - 1)),
            damage[1], damage[2], values["move.accuracy"], values["move.pp_fraction"],
            values["status.player.confused"], values["state.player_status.sleep"],
            -accuracy * values["status.opponent.accuracy_stage"],
        )
        rows.append((*row, *extras))
    return TrainerCandidateFeatures(
        BALANCED_STATUS_SCHEMA, BALANCED_STATUS_NAMES, tuple(rows), previous.candidate_slots
    )
