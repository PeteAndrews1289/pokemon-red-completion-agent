"""Action-free checks of the player's real inputs before curriculum collection.

No source access, model query, teacher preference or outcome label. A changed
contrast shows representational capacity, not a learned or correct decision.
Indices join existing executable options privately; identities are not features.
"""

import math
from dataclasses import dataclass

from .goal_manager import GoalKind, GoalManagerQuestion
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .living_dex_option_value import (
    living_dex_option_context_from_goal_situation,
    option_feature_names,
)
from .player_readiness import PlayerReadiness
from .resource_economy_observation import EconomySnapshot


@dataclass(frozen=True)
class PlayerDecisionProbe:
    feature_version: int
    indices: tuple[int, ...]
    kinds: tuple[GoalKind, ...]
    vectors: tuple[tuple[float, ...], ...]

    def __post_init__(self):
        if (type(self.feature_version) is not int
                or not isinstance(self.indices, tuple)
                or not isinstance(self.kinds, tuple)
                or not isinstance(self.vectors, tuple)
                or any(not isinstance(v, tuple) for v in self.vectors)):
            raise ValueError("player probe requires immutable versioned inputs")
        width = len(option_feature_names(self.feature_version))
        if (len(self.indices) < 2 or len(set(self.indices)) != len(self.indices)
                or any(type(i) is not int or i < 0 for i in self.indices)
                or len(self.kinds) != len(self.indices)
                or len(self.vectors) != len(self.indices)
                or any(not isinstance(k, GoalKind) for k in self.kinds)
                or any(len(v) != width or any(type(x) not in (int, float)
                       or not math.isfinite(x) for x in v) for v in self.vectors)):
            raise ValueError("player probe needs aligned finite multi-option inputs")


def probe_player_decision(
    question: GoalManagerQuestion, *, economy_snapshot: EconomySnapshot,
    target_cash: int, feature_version: int = 4, readiness: PlayerReadiness | None = None,
) -> PlayerDecisionProbe:
    """Project every available option, rejecting silently omitted capabilities.

    Singleton lessons remain valid teacher data elsewhere, but cannot establish
    model-directed choice. Availability is supplied by the runtime; this helper
    does not prove that a provider is correctly bound to an executable action.
    """
    context = living_dex_option_context_from_goal_situation(
        question.situation, economy_snapshot=economy_snapshot, target_cash=target_cash,
    )
    indices, kinds, vectors = [], [], []
    for index in question.available_indices:
        candidate = project_living_dex_goal_candidate(
            question, index, feature_version=feature_version,
            binding_ref="private-probe-not-an-execution",
            readiness=readiness,
        )
        if candidate is None:
            raise ValueError("player probe contains an unsupported available goal")
        indices.append(index)
        kinds.append(question.opportunities[index].kind)
        vectors.append(candidate.vector(context, feature_version=feature_version))
    return PlayerDecisionProbe(feature_version, tuple(indices), tuple(kinds), tuple(vectors))


def compare_player_decision_pair(
    before: PlayerDecisionProbe, after: PlayerDecisionProbe, *,
    before_pair: tuple[int, int], after_pair: tuple[int, int],
) -> dict:
    """Compare a declared ordered pair across situations without choosing a winner.

    Pair elements are original question indices, not positions in the masked
    menu. Explicit joins support reordered menus without using private bindings
    as policy features. The caller is responsible for matching semantic roles.
    Equal contrasts concern the linear predictor only; clipping/safety logic can
    still change final decisions. Equal full inputs are the stronger collision.
    """
    if before.feature_version != after.feature_version:
        raise ValueError("player probe feature versions differ")

    def rows(probe, pair):
        if (not isinstance(pair, tuple) or len(pair) != 2
                or any(type(i) is not int or i not in probe.indices for i in pair)
                or pair[0] == pair[1]):
            raise ValueError("player probe pair must name two available indices")
        positions = tuple(probe.indices.index(i) for i in pair)
        return tuple(probe.kinds[i] for i in positions), tuple(probe.vectors[i] for i in positions)

    old_kinds, old = rows(before, before_pair)
    new_kinds, new = rows(after, after_pair)
    if old_kinds != new_kinds:
        raise ValueError("player probe pair goal roles differ")
    names = option_feature_names(before.feature_version)
    changed = [name for i, name in enumerate(names)
               if any(a[i] != b[i] for a, b in zip(old, new, strict=True))]
    contrasts = [name for i, name in enumerate(names)
                 if old[0][i] - old[1][i] != new[0][i] - new[1][i]]
    return dict(
        schema="pokemon.core.player-decision-contrast.v1",
        feature_version=before.feature_version,
        goal_kinds=[k.value for k in old_kinds],
        changed_input_features=changed,
        changed_linear_contrast_features=contrasts,
        identical_pair_inputs=not changed,
        identical_linear_contrast=not contrasts,
        learned_advantage_demonstrated=False,
    )
