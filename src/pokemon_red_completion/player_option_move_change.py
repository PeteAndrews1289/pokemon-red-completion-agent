"""Portable observed/proposed move-change facts, never a recommended choice.

The existing mechanics catalog resolves local IDs below this boundary. Unknown
PP, recipient stats and opposition remain explicitly masked. Power products
describe mechanics only; they are not damage estimates or outcome labels.
"""

from dataclasses import dataclass
from math import isfinite

from .battle_semantics import EFFECT_FLAGS, MOVE_CATEGORIES, POKEMON_TYPES, MoveMechanics

MOVE_CHANGE_SCHEMA = "pokemon.core.option-move-change.v1"
_MOVE_NAMES = (
    "known", "power", "accuracy", "base_pp", "priority",
    *("category." + name for name in MOVE_CATEGORIES),
    *("type." + name for name in POKEMON_TYPES),
    *("effect." + name for name in EFFECT_FLAGS),
    "pp_known", "current_pp", "maximum_pp", "pp_fraction", "stab",
)
_EXTRA_NAMES = (
    "present", "recipient_stats_known", "recipient_attack", "recipient_special_attack",
    "removed_matchup_known", "removed_effectiveness", "removed_matchup_power",
    "proposed_matchup_known", "proposed_effectiveness", "proposed_matchup_power",
)


def move_change_feature_names():
    return tuple("move_change." + name for name in (
        *(role + "." + name for role in ("removed", "proposed") for name in _MOVE_NAMES),
        *_EXTRA_NAMES,
    ))


def move_context_feature_names():
    """V11 products of already observed move and recipient mechanics."""
    return tuple(f"move_change.{role}.recipient_power_product"
                 for role in ("removed", "proposed"))


def move_context_from_v10(features):
    """Project the unchanged V10 move block, without labels or private IDs.

    This bounded mechanics product is not a damage forecast. Unknown recipient
    stats and absent moves remain masked; status moves contribute zero.
    """
    values = dict(zip(move_change_feature_names(), features, strict=True))
    if not values["move_change.present"] or not values["move_change.recipient_stats_known"]:
        return (0.0, 0.0)
    def product(role):
        prefix = f"move_change.{role}."
        if not values[prefix + "known"]:
            return 0.0
        stat = (values[prefix + "category.physical"] * values["move_change.recipient_attack"]
                + values[prefix + "category.special"] * values["move_change.recipient_special_attack"])
        return (values[prefix + "power"] * values[prefix + "accuracy"]
                * ((1.0 + .5 * values[prefix + "stab"]) / 1.5) * stat)
    return tuple(product(role) for role in ("removed", "proposed"))


def _pp(current, maximum):
    if current is None and maximum is None:
        return
    if (type(current) is not int or type(maximum) is not int
            or not 0 <= current <= maximum <= 63 or maximum < 1):
        raise ValueError("move change PP must be observed coherent integer charges")


def _mechanics_document(move):
    if move is None:
        return None
    return dict(type_name=move.type_name, category=move.category, power=move.power,
                accuracy=move.accuracy, max_pp=move.max_pp, priority=move.priority,
                effect_flags=sorted(move.effect_flags))


def _restore_mechanics(document):
    if document is None:
        return None
    names = set(MoveMechanics.__dataclass_fields__)
    if (not isinstance(document, dict) or set(document) != names
            or not isinstance(document["effect_flags"], list)
            or any(not isinstance(v, str) for v in document["effect_flags"])
            or document["effect_flags"] != sorted(set(document["effect_flags"]))):
        raise ValueError("move change mechanics contract differs")
    return MoveMechanics(**dict(document, effect_flags=frozenset(document["effect_flags"])))


@dataclass(frozen=True)
class OptionMoveChange:
    proposed: MoveMechanics
    removed: MoveMechanics | None
    proposed_current_pp: int
    proposed_maximum_pp: int
    removed_current_pp: int | None = None
    removed_maximum_pp: int | None = None
    removed_stab: bool = False
    proposed_stab: bool = False
    recipient_attack: int | None = None
    recipient_special_attack: int | None = None
    removed_effectiveness: float | None = None
    proposed_effectiveness: float | None = None

    def __post_init__(self):
        if not isinstance(self.proposed, MoveMechanics):
            raise TypeError("proposed move needs portable mechanics")
        if self.removed is not None and not isinstance(self.removed, MoveMechanics):
            raise TypeError("removed move needs portable mechanics or an observed empty slot")
        if any(type(v) is not bool for v in (self.removed_stab, self.proposed_stab)):
            raise ValueError("move change STAB must be explicit boolean facts")
        _pp(self.proposed_current_pp, self.proposed_maximum_pp)
        if self.proposed_current_pp is None:
            raise ValueError("proposed move PP must be specified by its mechanic")
        _pp(self.removed_current_pp, self.removed_maximum_pp)
        if self.removed is None and any(v is not None for v in (
            self.removed_current_pp, self.removed_maximum_pp, self.removed_effectiveness,
        )):
            raise ValueError("an empty removed slot cannot invent PP or matchup facts")
        if self.removed is None and self.removed_stab:
            raise ValueError("an empty removed slot has no STAB")
        stats = (self.recipient_attack, self.recipient_special_attack)
        if (stats[0] is None) != (stats[1] is None):
            raise ValueError("recipient attack and special attack must be jointly observed")
        if any(v is not None and (type(v) is not int or not 1 <= v <= 65535) for v in stats):
            raise ValueError("recipient stats must be observed positive integers")
        for value in (self.removed_effectiveness, self.proposed_effectiveness):
            if value is not None and (
                type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 4
            ):
                raise ValueError("known opposition effectiveness differs")

    def vector(self):
        def move_vector(move, current, maximum, stab):
            if move is None:
                return (0.0,) * len(_MOVE_NAMES)
            known = current is not None
            return (
                1.0, move.power / 255, move.accuracy, move.max_pp / 63, float(move.priority),
                *(float(move.category == name) for name in MOVE_CATEGORIES),
                *(float(move.type_name == name) for name in POKEMON_TYPES),
                *(float(name in move.effect_flags) for name in EFFECT_FLAGS),
                float(known), current / 63 if known else 0.0,
                maximum / 63 if known else 0.0, current / maximum if known else 0.0,
                float(stab),
            )
        def matchup(move, effectiveness, stab):
            if effectiveness is None:
                return (0.0, 0.0, 0.0)
            weighted_power = move.power * move.accuracy * (1.5 if stab else 1.0)
            return (1.0, effectiveness / 4, weighted_power * effectiveness / (255 * 1.5 * 4))
        stats_known = self.recipient_attack is not None
        return (
            *move_vector(self.removed, self.removed_current_pp, self.removed_maximum_pp, self.removed_stab),
            *move_vector(self.proposed, self.proposed_current_pp, self.proposed_maximum_pp, self.proposed_stab),
            1.0, float(stats_known),
            self.recipient_attack / (self.recipient_attack + 100) if stats_known else 0.0,
            self.recipient_special_attack / (self.recipient_special_attack + 100) if stats_known else 0.0,
            *matchup(self.removed, self.removed_effectiveness, self.removed_stab),
            *matchup(self.proposed, self.proposed_effectiveness, self.proposed_stab),
        )

    def public_dict(self):
        return dict(schema=MOVE_CHANGE_SCHEMA, **{
            name: _mechanics_document(value) if name in ("removed", "proposed") else value
            for name in self.__dataclass_fields__ for value in (getattr(self, name),)
        })

    @classmethod
    def from_public(cls, document):
        names = set(cls.__dataclass_fields__)
        if (not isinstance(document, dict) or set(document) != names | {"schema"}
                or document["schema"] != MOVE_CHANGE_SCHEMA):
            raise ValueError("move change document contract differs")
        values = {name: document[name] for name in names}
        for name in ("removed", "proposed"):
            values[name] = _restore_mechanics(values[name])
        result = cls(**values)
        if result.public_dict() != document:
            raise ValueError("move change document does not replay")
        return result


def move_change_vector(change):
    if change is None:
        return (0.0,) * len(move_change_feature_names())
    if not isinstance(change, OptionMoveChange):
        raise TypeError("move change descriptor differs")
    return change.vector()
