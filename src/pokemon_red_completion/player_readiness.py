"""Versioned bridge from existing post-battle observations to the option learner.

No prescribed choice, title identity, outcome label or private execution key.
Unknown historical readiness is distinct from an observed all-zero measurement.
"""

from dataclasses import dataclass
from math import isfinite

from .post_battle_strategy import PostBattleContext, current_party_measurements

READINESS_SCHEMA = "pokemon.core.player-readiness.v1"
NO_HISTORY_SCHEMA = "pokemon.core.player-readiness-no-history.v1"
CONTEXT_NAMES = (
    "recent.won",
    "recent.lost",
    "recent.unresolved",
    "recent.opposition_coverage",
    "recent.defeated_fraction",
    "recent.engaged_level_gap",
    "recent.fainted_fraction",
    "recent.hp_fraction",
    "recent.pp_spent_fraction",
    "recent.exhausted_move_fraction",
    "recent.voluntary_switch_fraction",
    "recent.suppressed_attack_fraction",
    "recent.last_opponent_hp_known",
    "recent.last_opponent_hp_fraction",
    "current.median_combat_level_gap",
    "current.lowest_combat_level_gap",
    "current.combat_level_spread",
    "current.hp_fraction",
    "current.fainted_fraction",
    "current.status_fraction",
    "current.pp_known",
    "current.pp_fraction",
)
BUDGET_NAMES = (
    "budget.attempts",
    "budget.actions",
    "budget.frames",
    "budget.seconds",
    "budget.heals",
)
READINESS_NAMES = ("observed", *CONTEXT_NAMES, *BUDGET_NAMES)


@dataclass(frozen=True)
class PlayerReadiness:
    values: tuple[float, ...]
    history_observed: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.values, tuple)
            or len(self.values) != len(READINESS_NAMES) - 1
            or any(type(v) not in (int, float) or not isfinite(v) for v in self.values)
        ):
            raise ValueError("readiness requires finite immutable measurements")
        for name, value in zip(READINESS_NAMES[1:], self.values, strict=True):
            if not (-1 if name.endswith("level_gap") else 0) <= value <= 1:
                raise ValueError("readiness measurement outside semantic bounds")
        features = dict(zip(READINESS_NAMES[1:], self.values, strict=True))
        if type(self.history_observed) is not bool:
            raise ValueError("readiness history presence must be explicit")
        if sum(features[f"recent.{r}"] for r in ("won", "lost", "unresolved")) != int(
            self.history_observed
        ):
            raise ValueError("readiness requires one observed battle result")
        if not self.history_observed and any(
            value for name, value in features.items()
            if name.startswith("recent.") or name.endswith("level_gap")
        ):
            raise ValueError("absent history cannot invent opposition or battle facts")
        for name in (
            "recent.won",
            "recent.lost",
            "recent.unresolved",
            "recent.last_opponent_hp_known",
            "current.pp_known",
        ):
            if features[name] not in (0, 1):
                raise ValueError("readiness indicator must be binary")
        for known, measured in (
            ("current.pp_known", "current.pp_fraction"),
            ("recent.last_opponent_hp_known", "recent.last_opponent_hp_fraction"),
        ):
            if not features[known] and features[measured]:
                raise ValueError("unknown readiness cannot claim a measurement")

    @classmethod
    def from_context(cls, context: PostBattleContext, remaining_budget: tuple[float, ...]):
        if not isinstance(context, PostBattleContext):
            raise TypeError("existing observed post-battle context required")
        values = context.features()
        if tuple(values) != CONTEXT_NAMES or not isinstance(remaining_budget, tuple):
            raise ValueError("post-battle feature contract changed")
        return cls((*values.values(), *remaining_budget))

    def public_dict(self):
        return dict(
            schema=READINESS_SCHEMA if self.history_observed else NO_HISTORY_SCHEMA,
            names=list(READINESS_NAMES[1:]), values=list(self.values),
        )

    @classmethod
    def without_battle_history(cls, members, remaining_budget):
        """Observe the current party without fabricating a prior encounter.

        All three result flags are zero, distinct from an unresolved battle.
        Opposition-dependent gaps are masked zero, not a claim of level parity.
        Existing feature dimensions and all historical observed rows stay exact.
        """
        levels, hp, fainted, status, pp = current_party_measurements(members)
        current = {
            "current.combat_level_spread": (max(levels) - min(levels)) / 100,
            "current.hp_fraction": hp,
            "current.fainted_fraction": fainted,
            "current.status_fraction": status,
            "current.pp_known": float(pp is not None),
            "current.pp_fraction": pp or 0.0,
        }
        if not isinstance(remaining_budget, tuple):
            raise ValueError("immutable remaining budget required")
        return cls(tuple(current.get(name, 0.0) for name in CONTEXT_NAMES) + remaining_budget,
                   history_observed=False)

    @classmethod
    def from_public(cls, document):
        if (
            not isinstance(document, dict)
            or set(document) != {"schema", "names", "values"}
            or document["schema"] not in {READINESS_SCHEMA, NO_HISTORY_SCHEMA}
            or document["names"] != list(READINESS_NAMES[1:])
            or not isinstance(document["values"], list)
        ):
            raise ValueError("readiness document contract differs")
        return cls(
            tuple(document["values"]), history_observed=document["schema"] == READINESS_SCHEMA,
        )


def readiness_feature_names(kinds):
    return tuple(f"readiness.{kind.value}_x_{name}" for kind in kinds for name in READINESS_NAMES)


def readiness_vector(readiness, kind, kinds):
    values = (0.0,) * len(READINESS_NAMES) if readiness is None else (1.0, *readiness.values)
    return tuple(v if candidate_kind is kind else 0.0 for candidate_kind in kinds for v in values)
