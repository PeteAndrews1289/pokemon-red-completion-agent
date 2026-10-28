"""Title-neutral observed-arm option-value learning for living-Pokedex planning.

This module is the replacement boundary for the retired binary dependency ranker.
Game adapters may bind concrete species, maps, items, routes, or puzzles behind a
``binding_ref``.  None of those identities enter the policy projection or model.

The learner consumes only the outcome of the action that was actually selected,
along with its logged behavior probability.  A failed action never creates a
target for an unexecuted alternative.  Interrupted or unreadable outcomes remain
censored evidence and are excluded from fitting.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import cast

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.goal_manager import GoalSituation
from pokemon_red_completion.goal_search_memory import GoalSearchHistory
from pokemon_red_completion.player_option_challenge import (
    OptionChallenge,
    challenge_feature_names,
    challenge_vector,
)
from pokemon_red_completion.player_option_preparation import OptionPreparation, preparation_vector
from pokemon_red_completion.player_option_level_workload import (
    OptionLevelWorkload, level_workload_feature_names, level_workload_vector,
)
from pokemon_red_completion.player_option_move_change import (
    OptionMoveChange, move_change_feature_names, move_change_vector,
    move_context_feature_names, move_context_from_v10,
)
from pokemon_red_completion.player_option_capture_invocation import (
    OptionCaptureInvocation, capture_invocation_feature_names, capture_invocation_vector,
    complete_paid_capture_feature_names, complete_paid_capture_vector,
    complete_paid_density_feature_names, complete_paid_density_vector,
)
from pokemon_red_completion.player_option_matchup import (
    OptionMatchup, MATCHUP_NAMES, matchup_feature_names, matchup_vector,
)
from pokemon_red_completion.player_readiness import PlayerReadiness, readiness_vector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.resource_economy_observation import (
    ECONOMY_FEATURE_NAMES,
    EconomyMode,
    EconomyOffer,
    EconomyOutcome,
    EconomySnapshot,
    economy_features,
)

LIVING_DEX_OPTION_CONTEXT_SCHEMA = "pokemon.core.living-dex-option-context.v1"
LIVING_DEX_OPTION_FEATURE_SCHEMA = "pokemon.core.living-dex-option-features.v1"
LIVING_DEX_OPTION_MENU_SCHEMA = "pokemon.core.living-dex-option-menu.v1"
LIVING_DEX_OPTION_OUTCOME_SCHEMA = "pokemon.core.living-dex-observed-outcome.v1"
LIVING_DEX_OPTION_EXAMPLE_SCHEMA = "pokemon.core.living-dex-observed-arm-example.v1"
LIVING_DEX_OPTION_MODEL_SCHEMA = "pokemon.core.living-dex-option-value-model.v1"
LIVING_DEX_OPTION_FIT_SCHEMA = "pokemon.core.living-dex-option-value-fit.v1"
LIVING_DEX_OPTION_EVALUATION_SCHEMA = "pokemon.core.living-dex-option-value-evaluation.v1"
LIVING_DEX_OPTION_OBJECTIVE = "selected-arm-capped-ips-multioutcome-ridge-v1"
LIVING_DEX_PARTY_COST_RESIDUAL_OBJECTIVE = "selected-arm-ips-unit-curriculum-party-cost-residual-ridge-v1"
LIVING_DEX_PARTY_COST_RETAINED_OUTPUT_OBJECTIVE = (
    "selected-arm-ips-unit-curriculum-party-cost-output-retained-residual-ridge-v1"
)
_PARTY_COST_RESIDUAL_OBJECTIVES = frozenset((
    LIVING_DEX_PARTY_COST_RESIDUAL_OBJECTIVE, LIVING_DEX_PARTY_COST_RETAINED_OUTPUT_OBJECTIVE,
))
_PARTY_COST_RETENTION_ABSOLUTE_TOLERANCE = 1e-10
LIVING_DEX_SUCCESS_RESIDUAL_OBJECTIVE = "selected-arm-ips-unit-curriculum-success-residual-ridge-v1"
LIVING_DEX_STORY_SUCCESS_RETAINED_OBJECTIVE = (
    "selected-arm-ips-unit-curriculum-story-context-success-retained-ridge-v1"
)
_STORY_SUCCESS_FEATURE_GROUP = "complete-story-context-v1"
LIVING_DEX_BOUNDED_STORY_SUCCESS_OBJECTIVE = (
    "selected-arm-ips-unit-curriculum-bounded-story-success-retained-ridge-v1"
)
LIVING_DEX_BOUNDED_STORY_SUCCESS_HEAD_SCHEMA = "pokemon.core.bounded-story-success-head.v1"
LIVING_DEX_BOUNDED_MATCHUP_STORY_SUCCESS_OBJECTIVE = (
    "selected-arm-ips-unit-curriculum-bounded-matchup-story-success-retained-ridge-v2"
)
LIVING_DEX_BOUNDED_MATCHUP_STORY_SUCCESS_HEAD_SCHEMA = "pokemon.core.bounded-story-success-head.v2"
_BOUNDED_MATCHUP_NORMALIZATION_SCHEMA = "pokemon.core.weighted-story-input-normalization.v1"
_BOUNDED_MATCHUP_SCALE_FLOOR = 1e-6
_BOUNDED_MATCHUP_CONSTANT_MULTIPLIER = 64.



class CompletePaidSuccessBasis(StrEnum):
    """Prespecified local residual basis, not a model-selection instruction."""

    CONSTANT = "constant"
    HORIZON = "horizon"
    DENSITY = "density"
    HORIZON_DENSITY = "horizon_density"


_COMPLETE_PAID_SUCCESS_OBJECTIVES = {
    basis: f"selected-arm-ips-unit-curriculum-complete-paid-{basis.value}-success-residual-ridge-v1"
    for basis in CompletePaidSuccessBasis
}
_RETAINED_SUCCESS_OBJECTIVES = frozenset((
    LIVING_DEX_SUCCESS_RESIDUAL_OBJECTIVE, LIVING_DEX_STORY_SUCCESS_RETAINED_OBJECTIVE,
    LIVING_DEX_BOUNDED_STORY_SUCCESS_OBJECTIVE,
    LIVING_DEX_BOUNDED_MATCHUP_STORY_SUCCESS_OBJECTIVE,
    *_COMPLETE_PAID_SUCCESS_OBJECTIVES.values(),
))

_RETAINED_HEAD_OBJECTIVES = frozenset((*_RETAINED_SUCCESS_OBJECTIVES, *_PARTY_COST_RESIDUAL_OBJECTIVES))

LIVING_DEX_OPTION_NORMALIZATION = "pokemon.core.living-dex-option-normalization.v1"
LIVING_DEX_ECONOMY_HEAD_SCHEMA = "pokemon.core.living-dex-economy-head.v1"
LIVING_DEX_ECONOMY_NORMALIZATION = "pokemon.core.living-dex-economy-normalization.v1"
LIVING_DEX_ECONOMY_OBJECTIVE = "selected-arm-capped-ips-economy-ridge-v1"
LIVING_DEX_ECONOMY_OUTCOME_NAMES = ("useful_liquidity_gain", "cash_loss")
LIVING_DEX_ECONOMY_EVIDENCE_SCHEMA = "pokemon.core.living-dex-economy-evidence.v1"

DEFAULT_OPTION_VALUE_RIDGE = 0.25
DEFAULT_MAX_IMPORTANCE_WEIGHT = 4.0

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PARTITIONS = frozenset({"train", "development", "validation", "adaptation", "test"})


class LivingDexOptionKind(StrEnum):
    """Portable collection-oriented intents shared by title adapters."""

    ACQUIRE = "acquire"
    EVOLVE = "evolve"
    TRADE = "trade"
    DEVELOP = "develop"
    MANAGE_STORAGE = "manage_storage"
    RESUPPLY = "resupply"
    UNLOCK_ACCESS = "unlock_access"
    EXPLORE = "explore"
    RESTORE = "restore"


class LivingDexOptionAvailability(StrEnum):
    """Hard availability mask supplied before the model scores a menu."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class LivingDexOptionUnavailableReason(StrEnum):
    """Identity-free reasons an option cannot receive model authority."""

    INVARIANT_VIOLATION = "invariant_violation"
    MISSING_CAPABILITY = "missing_capability"
    MISSING_RESOURCE = "missing_resource"
    NO_LEGAL_TARGET = "no_legal_target"
    STORY_GATE_CLOSED = "story_gate_closed"
    STORAGE_BLOCKED = "storage_blocked"
    TEMPORARILY_BLOCKED = "temporarily_blocked"
    WORLD_STATE_UNKNOWN = "world_state_unknown"


class LivingDexOutcomeStatus(StrEnum):
    """Whether an independently observed selected-arm outcome is trainable."""

    SETTLED = "settled"
    CENSORED = "censored"


class LivingDexCensorReason(StrEnum):
    """Why an attempted decision is evidence but not a learning target."""

    EXTERNAL_INTERRUPTION = "external_interruption"
    OBSERVATION_FAILED = "observation_failed"
    PROVENANCE_FAILED = "provenance_failed"


class LivingDexOptionValueError(ValueError):
    """The option-value contract, evidence, or model is invalid."""


# Frozen v1/v2 layout: extending the enum must never move historical coefficients.
LIVING_DEX_LEGACY_OPTION_KINDS = (
    LivingDexOptionKind.ACQUIRE,
    LivingDexOptionKind.EVOLVE,
    LivingDexOptionKind.TRADE,
    LivingDexOptionKind.DEVELOP,
    LivingDexOptionKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS,
    LivingDexOptionKind.EXPLORE,
)
_KIND_FEATURE_NAMES = tuple(f"kind.{kind.value}" for kind in LIVING_DEX_LEGACY_OPTION_KINDS)
LIVING_DEX_RECOVERY_FEATURE_NAMES = ("kind.restore", "party_pressure_x_restore")
_CANDIDATE_FEATURE_NAMES = (
    "completion_gain",
    "dependency_unlock_gain",
    "travel_effort",
    "execution_effort",
    "resource_cost",
    "storage_cost",
    "party_risk",
    "irreversibility_risk",
    "uncertainty",
)
_INTERACTION_FEATURE_NAMES = (
    "collection_pressure_x_completion_gain",
    "dependency_pressure_x_dependency_unlock_gain",
    "access_pressure_x_travel_effort",
    "resource_pressure_x_resource_cost",
    "storage_pressure_x_storage_cost",
    "party_pressure_x_party_risk",
    "knowledge_pressure_x_uncertainty",
)
LIVING_DEX_OPTION_FEATURE_NAMES = (
    *_KIND_FEATURE_NAMES,
    *_CANDIDATE_FEATURE_NAMES,
    *_INTERACTION_FEATURE_NAMES,
)

# Presence is separate from measured zero. Counts cover only tracking's lifetime;
# no feature claims that earlier, unrecorded searches did not happen.
LIVING_DEX_HISTORY_FEATURE_NAMES = (
    "search.tracked",
    "search.attempts",
    "search.exhausted",
    "search.actions",
    "search.frames",
)


def option_feature_names(version: int) -> tuple[str, ...]:
    from .player_option_preparation import preparation_feature_names
    from .player_readiness import readiness_feature_names

    if type(version) is not int or version not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
        raise LivingDexOptionValueError("living-Dex feature version differs")
    return (
        LIVING_DEX_OPTION_FEATURE_NAMES
        + (LIVING_DEX_HISTORY_FEATURE_NAMES if version >= 2 else ())
        + (LIVING_DEX_RECOVERY_FEATURE_NAMES if version >= 3 else ())
        + (ECONOMY_FEATURE_NAMES if version >= 4 else ())
        + (readiness_feature_names(LivingDexOptionKind) if version >= 5 else ())
        + (challenge_feature_names(LivingDexOptionKind) if version >= 6 else ())
        + (preparation_feature_names() if version >= 7 else ())
        + (kind_execution_effort_feature_names() if version >= 8 else ())
        + (level_workload_feature_names() if version >= 9 else ())
        + (move_change_feature_names() if version >= 10 else ())
        + (move_context_feature_names() if version >= 11 else ())
        + (capture_invocation_feature_names() if version >= 12 else ())
        + (complete_paid_capture_feature_names() if version >= 13 else ())
        + (complete_paid_density_feature_names() if version >= 14 else ())
        + (matchup_feature_names() if version >= 15 else ())
    )



def project_complete_paid_capture_features(prefix: Sequence[float]) -> tuple[float, ...]:
    """Derive V13 only from a prospectively authenticated V12 input vector."""
    values = tuple(prefix)
    if len(values) != len(option_feature_names(12)):
        raise LivingDexOptionValueError("complete-paid projection requires the V12 prefix")
    names = option_feature_names(12)
    acquire = values[names.index("kind.acquire")]
    descriptor = values[-len(capture_invocation_feature_names()):]
    if any(descriptor):
        kind_values = tuple(v for n, v in zip(names, values, strict=True)
                            if n.startswith("kind."))
        if acquire != 1. or any(v not in (0., 1.) for v in kind_values) or sum(kind_values) != 1.:
            raise LivingDexOptionValueError("capture invocation requires an acquisition input")
    try:
        suffix = complete_paid_capture_vector(descriptor, acquire=bool(acquire == 1.))
    except (TypeError, ValueError):
        raise LivingDexOptionValueError("complete-paid invocation projection differs") from None
    return (*values, *suffix)



def project_complete_paid_density_features(prefix: Sequence[float]) -> tuple[float, ...]:
    """Derive V14 from the exact V13 invocation and existing uncertainty input."""
    values = tuple(prefix)
    if len(values) != len(option_feature_names(13)):
        raise LivingDexOptionValueError("complete-paid density requires the V13 prefix")
    v12_width = len(option_feature_names(12))
    if values != project_complete_paid_capture_features(values[:v12_width]):
        raise LivingDexOptionValueError("complete-paid suffix differs from its V12 input")
    try:
        suffix = complete_paid_density_vector(
            values[v12_width:], uncertainty=values[option_feature_names(13).index("uncertainty")])
    except (TypeError, ValueError):
        raise LivingDexOptionValueError("complete-paid density projection differs") from None
    return (*values, *suffix)


def _matchup_from_vector(values: Sequence[float]) -> OptionMatchup | None:
    # Raw prediction arrays contain NumPy scalars; public descriptor parsing stays strict.
    values = tuple(v.item() if isinstance(v, np.generic) else v for v in values)
    if len(values) != len(MATCHUP_NAMES):
        raise LivingDexOptionValueError("matchup suffix width differs")
    if values[0] == 0.:
        if any(values):
            raise LivingDexOptionValueError("unobserved matchup suffix must be zero")
        return None
    if values[0] != 1.:
        raise LivingDexOptionValueError("matchup presence differs")
    try:
        return OptionMatchup(tuple(values[1:]))
    except (TypeError, ValueError):
        raise LivingDexOptionValueError("matchup suffix differs") from None


def project_matchup_features(
    prefix: Sequence[float], matchup: OptionMatchup | None = None,
) -> tuple[float, ...]:
    """Append only truthful current-combat observations to an exact V14 prefix."""
    values = tuple(prefix)
    if len(values) != len(option_feature_names(14)):
        raise LivingDexOptionValueError("matchup projection requires the V14 prefix")
    v13_width = len(option_feature_names(13))
    if values != project_complete_paid_density_features(values[:v13_width]):
        raise LivingDexOptionValueError("matchup V14 prefix differs")
    if matchup is not None:
        names = option_feature_names(14)
        kinds = tuple(v for n, v in zip(names, values, strict=True) if n.startswith("kind."))
        if (not isinstance(matchup, OptionMatchup)
                or values[names.index("kind.unlock_access")] != 1.
                or any(k not in (0., 1.) for k in kinds) or sum(kinds) != 1.
                or values[names.index("challenge.unlock_access_x_present")] != 1.
                or values[names.index("challenge.unlock_access_x_combat_required")] != 1.):
            raise LivingDexOptionValueError("matchup requires a current combat story option")
    if matchup is not None and matchup.values[2] == 1.:
        names = option_feature_names(14)
        known = values[names.index("challenge.unlock_access_x_opposition_known")] == 1.
        empty_own = matchup.values[0] == 1. and matchup.values[4] == matchup.values[5] == 0.
        if ((not known and not empty_own)
                or (known and values[names.index("challenge.unlock_access_x_opponent_fraction")] != matchup.values[6])):
            raise LivingDexOptionValueError("matchup roster differs from the current challenge")
    return (*values, *matchup_vector(matchup))


def complete_paid_success_columns(basis: CompletePaidSuccessBasis) -> tuple[int, ...]:
    """Indices within the explicit local suffix, never inferred from array tails."""
    if not isinstance(basis, CompletePaidSuccessBasis):
        raise LivingDexOptionValueError("complete-paid basis must be typed")
    return {
        CompletePaidSuccessBasis.CONSTANT: (0,),
        CompletePaidSuccessBasis.HORIZON: (0, 1),
        CompletePaidSuccessBasis.DENSITY: (0, 2),
        CompletePaidSuccessBasis.HORIZON_DENSITY: (0, 1, 2, 3),
    }[basis]


def complete_paid_success_version(basis: CompletePaidSuccessBasis) -> int:
    return 14 if max(complete_paid_success_columns(basis)) >= 2 else 13


def kind_execution_effort_feature_names() -> tuple[str, ...]:
    """Derived semantic products; no title, target or private identity."""
    return tuple(f"execution_effort_x_kind.{kind.value}" for kind in LivingDexOptionKind)


def _kind_execution_effort_from_original(
    features: tuple[float, ...], version: int,
) -> tuple[float, ...]:
    # Every product uses already observed columns. Missing recovery/readiness
    # fields stay absent/zero; original records and fingerprints are untouched.
    values = dict(zip(option_feature_names(version), features, strict=True))
    effort = values["execution_effort"]
    return tuple(effort * values.get(f"kind.{kind.value}", 0.0)
                 for kind in LivingDexOptionKind)


def _history_vector(history: GoalSearchHistory | None) -> tuple[float, ...]:
    if history is None:
        return (0.0,) * len(LIVING_DEX_HISTORY_FEATURE_NAMES)
    return (
        1.0,
        history.attempts / (history.attempts + 1),
        history.exhausted / (history.exhausted + 1),
        history.actions / (history.actions + 1000),
        history.frames / (history.frames + 60000),
    )


LIVING_DEX_OPTION_OUTCOME_NAMES = (
    "verified_success",
    "completion_gain",
    "dependency_unlock_gain",
    "action_cost",
    "frame_cost",
    "resource_cost",
    "party_cost",
    "storage_cost",
    "irreversible_loss",
)


def _unit_interval(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LivingDexOptionValueError(f"{subject} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise LivingDexOptionValueError(f"{subject} must be between zero and one")
    return result


def _positive_finite(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LivingDexOptionValueError(f"{subject} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise LivingDexOptionValueError(f"{subject} must be positive")
    return result


def _nonnegative_integer(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise LivingDexOptionValueError(f"{subject} must be a non-negative integer")
    return value


def _semantic_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0 if numerator <= 0 else 1.0
    return min(1.0, max(0.0, numerator / denominator))


@dataclass(frozen=True, slots=True)
class LivingDexOptionContext:
    """Normalized pressures that can change the value of the same option."""

    collection_pressure: float
    dependency_pressure: float
    access_pressure: float
    resource_pressure: float
    storage_pressure: float
    party_pressure: float
    knowledge_pressure: float
    economy_snapshot: EconomySnapshot | None = None
    target_cash: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "collection_pressure",
            "dependency_pressure",
            "access_pressure",
            "resource_pressure",
            "storage_pressure",
            "party_pressure",
            "knowledge_pressure",
        ):
            object.__setattr__(
                self,
                name,
                _unit_interval(getattr(self, name), subject=name),
            )
        if self.economy_snapshot is not None and not isinstance(
            self.economy_snapshot, EconomySnapshot
        ):
            raise LivingDexOptionValueError("living-Dex economy snapshot differs")
        if self.target_cash is not None and (
            type(self.target_cash) is not int or self.target_cash < 0
        ):
            raise LivingDexOptionValueError("living-Dex target cash must be non-negative integer")
        if (self.economy_snapshot is None) != (self.target_cash is None):
            raise LivingDexOptionValueError(
                "living-Dex economy context requires both snapshot and target cash"
            )

    def policy_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "access_pressure": self.access_pressure,
            "collection_pressure": self.collection_pressure,
            "dependency_pressure": self.dependency_pressure,
            "knowledge_pressure": self.knowledge_pressure,
            "party_pressure": self.party_pressure,
            "resource_pressure": self.resource_pressure,
            "schema": (
                LIVING_DEX_OPTION_CONTEXT_SCHEMA
                if self.economy_snapshot is None
                else "pokemon.core.living-dex-option-context.v2"
            ),
            "storage_pressure": self.storage_pressure,
        }
        if self.economy_snapshot is not None:
            assert self.target_cash is not None
            # Policy inputs need cash, not title-specific inventory identifiers.
            # Full before/after ledgers belong to independently recorded evidence.
            result["economy_cash"] = self.economy_snapshot.cash
            result["target_cash"] = self.target_cash
        return result


def living_dex_option_context_from_goal_situation(
    situation: GoalSituation,
    *,
    economy_snapshot: EconomySnapshot | None = None,
    target_cash: int | None = None,
) -> LivingDexOptionContext:
    """Project the shared nine-need state into the shared option-value state.

    This mapping is deliberately title-neutral.  Red and later-generation
    adapters may differ in how they measure story, collection, party,
    resources, storage, and world knowledge, but they must use the same
    pressure composition once those measurements reach ``GoalSituation``.
    """

    if not isinstance(situation, GoalSituation):
        raise TypeError("living-Dex option context needs a GoalSituation")
    return LivingDexOptionContext(
        collection_pressure=situation.collection_pressure,
        dependency_pressure=max(
            situation.story_pressure,
            situation.evolution_pressure,
        ),
        access_pressure=max(
            situation.story_pressure,
            situation.exploration_pressure,
        ),
        resource_pressure=situation.resource_pressure,
        storage_pressure=situation.storage_pressure,
        party_pressure=max(
            situation.team_pressure,
            situation.safety_pressure,
            situation.recovery_pressure,
        ),
        knowledge_pressure=situation.exploration_pressure,
        economy_snapshot=economy_snapshot,
        target_cash=target_cash,
    )


@dataclass(frozen=True, slots=True)
class LivingDexOptionFeatures:
    """One identity-free candidate description supplied before execution."""

    kind: LivingDexOptionKind
    completion_gain: float
    dependency_unlock_gain: float
    travel_effort: float
    execution_effort: float
    resource_cost: float
    storage_cost: float
    party_risk: float
    irreversibility_risk: float
    uncertainty: float

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LivingDexOptionKind):
            raise LivingDexOptionValueError("living-Dex option kind is unsupported")
        for name in _CANDIDATE_FEATURE_NAMES:
            object.__setattr__(
                self,
                name,
                _unit_interval(getattr(self, name), subject=name),
            )

    def vector(
        self, context: LivingDexOptionContext, *, feature_version: int = 1
    ) -> tuple[float, ...]:
        option_feature_names(feature_version)
        if self.kind is LivingDexOptionKind.RESTORE and feature_version < 3:
            raise LivingDexOptionValueError("legacy scorer cannot represent recovery")
        if not isinstance(context, LivingDexOptionContext):
            raise TypeError("context must be a LivingDexOptionContext")
        kinds = tuple(float(self.kind is kind) for kind in LIVING_DEX_LEGACY_OPTION_KINDS)
        candidates = tuple(float(getattr(self, name)) for name in _CANDIDATE_FEATURE_NAMES)
        interactions = (
            context.collection_pressure * self.completion_gain,
            context.dependency_pressure * self.dependency_unlock_gain,
            context.access_pressure * self.travel_effort,
            context.resource_pressure * self.resource_cost,
            context.storage_pressure * self.storage_cost,
            context.party_pressure * self.party_risk,
            context.knowledge_pressure * self.uncertainty,
        )
        result = (*kinds, *candidates, *interactions)
        if len(result) != len(LIVING_DEX_OPTION_FEATURE_NAMES):
            raise LivingDexOptionValueError("living-Dex option feature width differs")
        return result + (
            (
                float(self.kind is LivingDexOptionKind.RESTORE),
                context.party_pressure if self.kind is LivingDexOptionKind.RESTORE else 0.0,
            )
            if feature_version >= 3
            else ()
        )

    def policy_dict(self, context: LivingDexOptionContext) -> dict[str, object]:
        recovery = self.kind is LivingDexOptionKind.RESTORE
        return {
            "feature_names": list(
                LIVING_DEX_OPTION_FEATURE_NAMES
                + (LIVING_DEX_RECOVERY_FEATURE_NAMES if recovery else ())
            ),
            "kind": self.kind.value,
            "normalization": LIVING_DEX_OPTION_NORMALIZATION,
            "schema": (
                "pokemon.core.living-dex-option-features.v3"
                if recovery
                else LIVING_DEX_OPTION_FEATURE_SCHEMA
            ),
            "values": list(self.vector(context, feature_version=3 if recovery else 1)),
        }


def living_dex_option_features_from_semantic_facts(
    *,
    kind: LivingDexOptionKind,
    completion_units: int,
    maximum_completion_units: int,
    immediate_dependency_unlocks: int,
    incomplete_dependency_frontier: int,
    travel_action_estimate: int,
    execution_action_estimate: int,
    maximum_controller_actions: int,
    required_resource_units: int,
    available_resource_units: int,
    net_storage_slots: int,
    storage_headroom: int,
    party_risk: float,
    irreversible_constraints_exposed: int,
    irreversible_constraint_count: int,
    prerequisite_confidence: float,
) -> LivingDexOptionFeatures:
    """Normalize title-specific prospective counts through one shared contract."""

    if not isinstance(kind, LivingDexOptionKind):
        raise LivingDexOptionValueError("semantic option kind differs")
    values = {
        name: _nonnegative_integer(value, subject=name.replace("_", " "))
        for name, value in (
            ("completion_units", completion_units),
            ("maximum_completion_units", maximum_completion_units),
            ("immediate_dependency_unlocks", immediate_dependency_unlocks),
            ("incomplete_dependency_frontier", incomplete_dependency_frontier),
            ("travel_action_estimate", travel_action_estimate),
            ("execution_action_estimate", execution_action_estimate),
            ("maximum_controller_actions", maximum_controller_actions),
            ("required_resource_units", required_resource_units),
            ("available_resource_units", available_resource_units),
            ("storage_headroom", storage_headroom),
            (
                "irreversible_constraints_exposed",
                irreversible_constraints_exposed,
            ),
            ("irreversible_constraint_count", irreversible_constraint_count),
        )
    }
    if type(net_storage_slots) is not int:  # noqa: E721
        raise LivingDexOptionValueError("net storage slots must be an integer")
    if (
        values["maximum_completion_units"] <= 0
        or values["maximum_controller_actions"] <= 0
        or values["completion_units"] > values["maximum_completion_units"]
        or values["immediate_dependency_unlocks"] > values["incomplete_dependency_frontier"]
        or values["irreversible_constraints_exposed"] > values["irreversible_constraint_count"]
    ):
        raise LivingDexOptionValueError("semantic option count bounds differ")
    return LivingDexOptionFeatures(
        kind=kind,
        completion_gain=_semantic_ratio(
            values["completion_units"],
            values["maximum_completion_units"],
        ),
        dependency_unlock_gain=_semantic_ratio(
            values["immediate_dependency_unlocks"],
            values["incomplete_dependency_frontier"],
        ),
        travel_effort=_semantic_ratio(
            values["travel_action_estimate"],
            values["maximum_controller_actions"],
        ),
        execution_effort=_semantic_ratio(
            values["execution_action_estimate"],
            values["maximum_controller_actions"],
        ),
        resource_cost=_semantic_ratio(
            values["required_resource_units"],
            values["available_resource_units"],
        ),
        storage_cost=_semantic_ratio(
            max(0, net_storage_slots),
            values["storage_headroom"],
        ),
        party_risk=_unit_interval(party_risk, subject="party risk"),
        irreversibility_risk=_semantic_ratio(
            values["irreversible_constraints_exposed"],
            values["irreversible_constraint_count"],
        ),
        uncertainty=1.0
        - _unit_interval(
            prerequisite_confidence,
            subject="prerequisite confidence",
        ),
    )


@dataclass(frozen=True, slots=True)
class LivingDexOptionCandidate:
    """A policy-visible row plus a private execution binding."""

    binding_ref: str
    features: LivingDexOptionFeatures
    availability: LivingDexOptionAvailability
    unavailable_reason: LivingDexOptionUnavailableReason | None = None
    search_history: GoalSearchHistory | None = None
    economy_offer: EconomyOffer | None = None
    readiness: PlayerReadiness | None = None
    challenge: OptionChallenge | None = None
    preparation: OptionPreparation | None = None
    level_workload: OptionLevelWorkload | None = None
    move_change: OptionMoveChange | None = None
    capture_invocation: OptionCaptureInvocation | None = None
    matchup: OptionMatchup | None = None

    def __post_init__(self) -> None:
        if self.matchup is not None and (
            not isinstance(self.matchup, OptionMatchup)
            or not isinstance(self.features, LivingDexOptionFeatures)
            or self.features.kind is not LivingDexOptionKind.UNLOCK_ACCESS
            or not isinstance(self.challenge, OptionChallenge)
            or not self.challenge.combat_required
        ):
            raise LivingDexOptionValueError("matchup requires a current combat story option")
        if self.matchup is not None and self.matchup.values[2] == 1.:
            assert self.challenge is not None
            empty_own = (self.matchup.values[0] == 1.
                         and self.matchup.values[4] == self.matchup.values[5] == 0.)
            if ((not self.challenge.opposition_known and not empty_own)
                    or (self.challenge.opposition_known
                        and self.challenge.opponent_fraction != self.matchup.values[6])):
                raise LivingDexOptionValueError("matchup roster differs from the current challenge")
        if self.capture_invocation is not None and (
            not isinstance(self.capture_invocation, OptionCaptureInvocation)
            or self.features.kind is not LivingDexOptionKind.ACQUIRE
        ):
            raise LivingDexOptionValueError("capture invocation requires an acquisition option")
        if self.move_change is not None and (
            not isinstance(self.move_change, OptionMoveChange)
            or self.features.kind is not LivingDexOptionKind.DEVELOP
        ):
            raise LivingDexOptionValueError("move change requires a development option")
        if self.level_workload is not None and (
            not isinstance(self.level_workload, OptionLevelWorkload)
            or self.features.kind not in (LivingDexOptionKind.EVOLVE, LivingDexOptionKind.DEVELOP)
        ):
            raise LivingDexOptionValueError("level workload requires a level-training option")
        if self.preparation is not None and (
            not isinstance(self.preparation, OptionPreparation)
            or self.features.kind is not LivingDexOptionKind.DEVELOP
        ):
            raise LivingDexOptionValueError("preparation descriptor requires a development option")
        if self.challenge is not None and not isinstance(self.challenge, OptionChallenge):
            raise LivingDexOptionValueError("living-Dex challenge differs")
        if self.readiness is not None and not isinstance(self.readiness, PlayerReadiness):
            raise LivingDexOptionValueError("living-Dex readiness differs")
        if self.search_history is not None and not isinstance(
            self.search_history, GoalSearchHistory
        ):
            raise LivingDexOptionValueError("living-Dex search history differs")
        if self.economy_offer is not None and not isinstance(self.economy_offer, EconomyOffer):
            raise LivingDexOptionValueError("living-Dex economy offer differs")
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise LivingDexOptionValueError("living-Dex option needs a binding reference")
        if not isinstance(self.features, LivingDexOptionFeatures):
            raise LivingDexOptionValueError("living-Dex option features differ")
        if not isinstance(self.availability, LivingDexOptionAvailability):
            raise LivingDexOptionValueError("living-Dex option availability differs")
        if self.availability is LivingDexOptionAvailability.AVAILABLE:
            if self.unavailable_reason is not None:
                raise LivingDexOptionValueError(
                    "available living-Dex option has an unavailable reason"
                )
        elif not isinstance(self.unavailable_reason, LivingDexOptionUnavailableReason):
            raise LivingDexOptionValueError("masked living-Dex option needs an unavailable reason")

    def vector(
        self, context: LivingDexOptionContext, *, feature_version: int = 1
    ) -> tuple[float, ...]:
        option_feature_names(feature_version)
        if feature_version == 15:
            return project_matchup_features(
                replace(self, matchup=None).vector(context, feature_version=14), self.matchup)
        if self.matchup is not None:
            raise LivingDexOptionValueError("legacy scorer cannot ignore matchup")
        if feature_version == 14:
            return project_complete_paid_density_features(
                self.vector(context, feature_version=13))
        if feature_version == 13:
            return project_complete_paid_capture_features(
                self.vector(context, feature_version=12))
        if feature_version < 12 and self.capture_invocation is not None:
            raise LivingDexOptionValueError("legacy scorer cannot ignore capture invocation")
        if feature_version < 10 and self.move_change is not None:
            raise LivingDexOptionValueError("legacy scorer cannot ignore move change")
        if feature_version < 9 and self.level_workload is not None:
            raise LivingDexOptionValueError("legacy scorer cannot ignore level workload")
        if feature_version < 7 and self.preparation is not None:
            raise LivingDexOptionValueError("legacy scorer cannot ignore preparation")
        if feature_version < 6 and self.challenge is not None:
            raise LivingDexOptionValueError("legacy scorer cannot ignore challenge")
        if feature_version < 5 and self.readiness is not None:
            raise LivingDexOptionValueError("legacy scorer cannot ignore readiness")
        if feature_version == 1 and self.search_history is not None:
            raise LivingDexOptionValueError("legacy scorer cannot ignore search history")
        if feature_version < 4 and self.economy_offer is not None:
            raise LivingDexOptionValueError("legacy scorer cannot represent economy offer")
        features = self.features.vector(context, feature_version=min(3, feature_version))
        # v3 appends to the complete v2 layout, not between legacy columns.
        base = features[:-2] if feature_version >= 3 else features
        history_part = _history_vector(self.search_history) if feature_version >= 2 else ()
        recovery_part = features[-2:] if feature_version >= 3 else ()
        economy_part: tuple[float, ...] = ()
        if feature_version >= 4:
            if self.economy_offer is not None:
                if context.economy_snapshot is None or context.target_cash is None:
                    raise LivingDexOptionValueError(
                        "economy candidate requires an economy-bearing context"
                    )
                economy_part = economy_features(
                    context.economy_snapshot,
                    self.economy_offer,
                    target_cash=context.target_cash,
                )
            else:
                if context.economy_snapshot is not None and context.target_cash is not None:
                    economy_part = economy_features(
                        context.economy_snapshot,
                        EconomyOffer(mode=EconomyMode.OTHER),
                        target_cash=context.target_cash,
                    )
                else:
                    economy_part = (0.0,) * len(ECONOMY_FEATURE_NAMES)
        return (
            base
            + history_part
            + recovery_part
            + economy_part
            + (
                readiness_vector(self.readiness, self.features.kind, LivingDexOptionKind)
                if feature_version >= 5
                else ()
            )
            + (
                challenge_vector(self.challenge, self.features.kind, LivingDexOptionKind)
                if feature_version >= 6
                else ()
            )
            + (preparation_vector(self.preparation) if feature_version >= 7 else ())
            + (
                tuple(self.features.execution_effort * float(self.features.kind is kind)
                      for kind in LivingDexOptionKind)
                if feature_version >= 8 else ()
            )
            + (level_workload_vector(self.level_workload) if feature_version >= 9 else ())
            + (move_change_vector(self.move_change) if feature_version >= 10 else ())
            + (move_context_from_v10(move_change_vector(self.move_change)) if feature_version >= 11 else ())
            + (capture_invocation_vector(self.capture_invocation) if feature_version >= 12 else ())
        )

    def policy_dict(self, context: LivingDexOptionContext) -> dict[str, object]:
        result: dict[str, object] = {
            "availability": self.availability.value,
            "features": self.features.policy_dict(context),
            "unavailable_reason": (
                None if self.unavailable_reason is None else self.unavailable_reason.value
            ),
        }
        if self.search_history is not None:
            result["search_history"] = self.search_history.public_dict()
        if self.readiness is not None:
            result["readiness"] = self.readiness.public_dict()
        if self.challenge is not None:
            result["challenge"] = self.challenge.public_dict()
        if self.preparation is not None:
            result["preparation"] = self.preparation.public_dict()
        if self.level_workload is not None:
            result["level_workload"] = self.level_workload.public_dict()
        if self.move_change is not None:
            result["move_change"] = self.move_change.public_dict()
        if self.capture_invocation is not None:
            result["capture_invocation"] = self.capture_invocation.public_dict()
        if self.matchup is not None:
            result["matchup"] = self.matchup.public_dict()
        if self.economy_offer is not None:
            result["economy_offer"] = {
                "conditional_income": self.economy_offer.conditional_income,
                "mode": self.economy_offer.mode.value,
                "planned_spend": self.economy_offer.planned_spend,
            }
        return result


@dataclass(frozen=True, slots=True)
class LivingDexOptionMenu:
    """A variable-size complete menu with hard-masked unavailable candidates."""

    context: LivingDexOptionContext
    candidates: tuple[LivingDexOptionCandidate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.context, LivingDexOptionContext):
            raise LivingDexOptionValueError("living-Dex option context differs")
        if (
            not isinstance(self.candidates, tuple)
            or len(self.candidates) < 2
            or any(not isinstance(item, LivingDexOptionCandidate) for item in self.candidates)
        ):
            raise LivingDexOptionValueError("living-Dex option menu needs two candidates")
        if len(self.available_indices) < 2:
            raise LivingDexOptionValueError(
                "living-Dex option menu needs two executable candidates"
            )

    @property
    def available_indices(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, candidate in enumerate(self.candidates)
            if candidate.availability is LivingDexOptionAvailability.AVAILABLE
        )

    @property
    def policy_sha256(self) -> str:
        return canonical_sha256(self.policy_dict())

    def candidate_vector(
        self, index: int, *, feature_version: int | None = None
    ) -> tuple[float, ...]:
        if type(index) is not int or not 0 <= index < len(self.candidates):  # noqa: E721
            raise LivingDexOptionValueError("living-Dex candidate index is invalid")
        version = self.feature_version if feature_version is None else feature_version
        return self.candidates[index].vector(self.context, feature_version=version)

    @property
    def feature_version(self) -> int:
        if any(row.matchup is not None for row in self.candidates):
            return 15
        if any(row.capture_invocation is not None for row in self.candidates):
            return 12
        if any(row.move_change is not None for row in self.candidates):
            return 10
        if any(row.level_workload is not None for row in self.candidates):
            return 9
        if any(row.preparation is not None for row in self.candidates):
            return 7
        if any(row.challenge is not None for row in self.candidates):
            return 6
        if any(row.readiness is not None for row in self.candidates):
            return 5
        if (
            any(row.economy_offer is not None for row in self.candidates)
            or self.context.economy_snapshot is not None
        ):
            return 4
        if any(row.features.kind is LivingDexOptionKind.RESTORE for row in self.candidates):
            return 3
        return 2 if any(row.search_history is not None for row in self.candidates) else 1

    def policy_dict(self) -> dict[str, object]:
        return {
            "candidates": [candidate.policy_dict(self.context) for candidate in self.candidates],
            "context": self.context.policy_dict(),
            "schema": (
                LIVING_DEX_OPTION_MENU_SCHEMA
                if self.feature_version == 1
                else f"pokemon.core.living-dex-option-menu.v{self.feature_version}"
            ),
        }


@dataclass(frozen=True, slots=True)
class LivingDexObservedOutcome:
    """Independent post-attempt evidence for exactly one selected candidate."""

    status: LivingDexOutcomeStatus
    verified_success: bool | None = None
    completion_gain: float | None = None
    dependency_unlock_gain: float | None = None
    action_cost: float | None = None
    frame_cost: float | None = None
    resource_cost: float | None = None
    party_cost: float | None = None
    storage_cost: float | None = None
    irreversible_loss: float | None = None
    censor_reason: LivingDexCensorReason | None = None
    economy: EconomyOutcome | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LivingDexOutcomeStatus):
            raise LivingDexOptionValueError("living-Dex outcome status differs")
        if self.economy is not None and not isinstance(self.economy, EconomyOutcome):
            raise LivingDexOptionValueError("living-Dex economy outcome differs")
        target_names = LIVING_DEX_OPTION_OUTCOME_NAMES[1:]
        if self.status is LivingDexOutcomeStatus.SETTLED:
            if type(self.verified_success) is not bool:  # noqa: E721
                raise LivingDexOptionValueError("settled living-Dex outcome needs success")
            if self.censor_reason is not None:
                raise LivingDexOptionValueError("settled living-Dex outcome cannot be censored")
            for name in target_names:
                value = getattr(self, name)
                if value is None:
                    raise LivingDexOptionValueError(f"settled living-Dex outcome needs {name}")
                object.__setattr__(self, name, _unit_interval(value, subject=name))
        else:
            if not isinstance(self.censor_reason, LivingDexCensorReason):
                raise LivingDexOptionValueError("censored living-Dex outcome needs a reason")
            if self.verified_success is not None or any(
                getattr(self, name) is not None for name in target_names
            ):
                raise LivingDexOptionValueError(
                    "censored living-Dex outcome cannot become a target"
                )
            if self.economy is not None:
                raise LivingDexOptionValueError(
                    "censored living-Dex outcome cannot retain economy targets"
                )

    @property
    def target_vector(self) -> tuple[float, ...] | None:
        if self.status is LivingDexOutcomeStatus.CENSORED:
            return None
        assert self.verified_success is not None
        values = tuple(float(getattr(self, name)) for name in LIVING_DEX_OPTION_OUTCOME_NAMES[1:])
        return (float(self.verified_success), *values)

    def public_dict(self) -> dict[str, object]:
        target = self.target_vector
        result: dict[str, object] = {
            "censor_reason": (None if self.censor_reason is None else self.censor_reason.value),
            "schema": (
                LIVING_DEX_OPTION_OUTCOME_SCHEMA
                if self.economy is None
                else "pokemon.core.living-dex-observed-outcome.v2"
            ),
            "status": self.status.value,
            "target_names": list(LIVING_DEX_OPTION_OUTCOME_NAMES),
            "target_values": None if target is None else list(target),
        }
        if self.economy is not None:
            result["economy"] = self.economy.public_dict()
        return result


@dataclass(frozen=True, slots=True)
class LivingDexObservedArmExample:
    """One logged menu, selected arm, behavior distribution, and observed result."""

    decision_sha256: str
    partition: str
    menu: LivingDexOptionMenu
    selected_candidate_index: int
    behavior_probabilities: tuple[float, ...]
    outcome: LivingDexObservedOutcome

    def __post_init__(self) -> None:
        if (
            not isinstance(self.decision_sha256, str)
            or _SHA256.fullmatch(self.decision_sha256) is None
        ):
            raise LivingDexOptionValueError("living-Dex decision identity differs")
        if self.partition not in _PARTITIONS:
            raise LivingDexOptionValueError("living-Dex example partition differs")
        if not isinstance(self.menu, LivingDexOptionMenu):
            raise LivingDexOptionValueError("living-Dex example menu differs")
        if (
            type(self.selected_candidate_index) is not int  # noqa: E721
            or self.selected_candidate_index not in self.menu.available_indices
        ):
            raise LivingDexOptionValueError("living-Dex selected candidate is unavailable")
        if not isinstance(self.behavior_probabilities, tuple) or len(
            self.behavior_probabilities
        ) != len(self.menu.candidates):
            raise LivingDexOptionValueError("living-Dex behavior distribution differs")
        probabilities = tuple(
            _unit_interval(value, subject="behavior probability")
            for value in self.behavior_probabilities
        )
        if not math.isclose(sum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise LivingDexOptionValueError("living-Dex behavior probabilities do not sum to one")
        for index, probability in enumerate(probabilities):
            if index in self.menu.available_indices:
                if probability <= 0.0:
                    raise LivingDexOptionValueError("living-Dex behavior policy lacks full support")
            elif probability != 0.0:
                raise LivingDexOptionValueError(
                    "masked living-Dex option received behavior probability"
                )
        object.__setattr__(self, "behavior_probabilities", probabilities)
        if not isinstance(self.outcome, LivingDexObservedOutcome):
            raise LivingDexOptionValueError("living-Dex observed outcome differs")

    @property
    def selected_probability(self) -> float:
        return self.behavior_probabilities[self.selected_candidate_index]

    @property
    def selected_vector(self) -> tuple[float, ...]:
        return self.menu.candidate_vector(self.selected_candidate_index)

    def importance_weight(self, maximum: float = DEFAULT_MAX_IMPORTANCE_WEIGHT) -> float:
        cap = _positive_finite(maximum, subject="maximum importance weight")
        if cap < 1.0:
            raise LivingDexOptionValueError("maximum importance weight must be at least one")
        return min(cap, 1.0 / self.selected_probability)

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_probabilities": list(self.behavior_probabilities),
            "decision_sha256": self.decision_sha256,
            "menu": self.menu.policy_dict(),
            "menu_sha256": self.menu.policy_sha256,
            "outcome": self.outcome.public_dict(),
            "partition": self.partition,
            "schema": LIVING_DEX_OPTION_EXAMPLE_SCHEMA,
            "selected_candidate_index": self.selected_candidate_index,
            "selected_candidate_target_only": True,
            "unselected_action_targets": 0,
        }


@dataclass(frozen=True, slots=True)
class LivingDexCurriculumOutcomeExample:
    """One observed execution, not a choice or an importance-weighted arm.

    Features are the same portable candidate vector used at inference. Admission
    must reconstruct them from a prospectively recorded semantic question.
    """

    decision_sha256: str
    partition: str
    feature_version: int
    features: tuple[float, ...]
    outcome: LivingDexObservedOutcome

    def __post_init__(self) -> None:
        if (
            not isinstance(self.decision_sha256, str)
            or _SHA256.fullmatch(self.decision_sha256) is None
            or self.partition != "train"
            or type(self.feature_version) is not int
            or not isinstance(self.features, tuple)
            or len(self.features) != len(option_feature_names(self.feature_version))
            or any(
                type(value) not in (int, float) or not math.isfinite(value)
                for value in self.features
            )
            or not isinstance(self.outcome, LivingDexObservedOutcome)
        ):
            raise LivingDexOptionValueError("curriculum outcome example differs")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.living-dex-curriculum-outcome.v1",
            "decision_sha256": self.decision_sha256,
            "partition": self.partition,
            "feature_version": self.feature_version,
            "features": list(self.features),
            "outcome": self.outcome.public_dict(),
            "regression_weight": 1.0,
            "comparative_choice": False,
        }


@dataclass(frozen=True, slots=True)
class LivingDexPredictedOutcome:
    verified_success: float
    completion_gain: float
    dependency_unlock_gain: float
    action_cost: float
    frame_cost: float
    resource_cost: float
    party_cost: float
    storage_cost: float
    irreversible_loss: float

    def __post_init__(self) -> None:
        for name in LIVING_DEX_OPTION_OUTCOME_NAMES:
            object.__setattr__(
                self,
                name,
                _unit_interval(getattr(self, name), subject=f"predicted {name}"),
            )

    @classmethod
    def from_vector(cls, values: Sequence[float]) -> LivingDexPredictedOutcome:
        if len(values) != len(LIVING_DEX_OPTION_OUTCOME_NAMES):
            raise LivingDexOptionValueError("predicted living-Dex outcome width differs")
        return cls(*map(float, values))

    def vector(self) -> tuple[float, ...]:
        return tuple(float(getattr(self, name)) for name in LIVING_DEX_OPTION_OUTCOME_NAMES)


@dataclass(frozen=True, slots=True)
class LivingDexOptionUtility:
    """Declared planning utility over separately predicted outcome components."""

    success_weight: float
    completion_gain_weight: float
    dependency_unlock_weight: float
    action_cost_weight: float
    frame_cost_weight: float
    resource_cost_weight: float
    party_cost_weight: float
    storage_cost_weight: float
    irreversible_loss_weight: float

    def __post_init__(self) -> None:
        for name in (
            "success_weight",
            "completion_gain_weight",
            "dependency_unlock_weight",
            "action_cost_weight",
            "frame_cost_weight",
            "resource_cost_weight",
            "party_cost_weight",
            "storage_cost_weight",
            "irreversible_loss_weight",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise LivingDexOptionValueError(f"{name} must be numeric")
            result = float(value)
            if not math.isfinite(result) or result < 0.0:
                raise LivingDexOptionValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, result)
        if self.completion_gain_weight == 0.0 and self.dependency_unlock_weight == 0.0:
            raise LivingDexOptionValueError(
                "living-Dex utility must value completion or dependency progress"
            )

    def score(self, outcome: LivingDexPredictedOutcome) -> float:
        if not isinstance(outcome, LivingDexPredictedOutcome):
            raise TypeError("outcome must be a LivingDexPredictedOutcome")
        benefit = (
            self.success_weight * outcome.verified_success
            + self.completion_gain_weight * outcome.completion_gain
            + self.dependency_unlock_weight * outcome.dependency_unlock_gain
        )
        cost = (
            self.action_cost_weight * outcome.action_cost
            + self.frame_cost_weight * outcome.frame_cost
            + self.resource_cost_weight * outcome.resource_cost
            + self.party_cost_weight * outcome.party_cost
            + self.storage_cost_weight * outcome.storage_cost
            + self.irreversible_loss_weight * outcome.irreversible_loss
        )
        return benefit - cost


def _validate_numeric_vector(
    raw: object,
    expected_len: int,
    *,
    subject: str,
    positive_only: bool = False,
) -> NDArray[np.float64]:
    if isinstance(raw, np.ndarray):
        if raw.dtype.kind == "b" or raw.dtype.kind not in ("f", "i"):
            raise LivingDexOptionValueError(f"{subject} must be numeric")
        if raw.shape != (expected_len,):
            raise LivingDexOptionValueError(f"{subject} wrong shape")
        arr = raw.astype(np.float64, copy=False)
        if not np.all(np.isfinite(arr)):
            raise LivingDexOptionValueError(f"{subject} contains nonfinite values")
        if positive_only and np.any(arr <= 0.0):
            raise LivingDexOptionValueError(f"{subject} must be positive")
        return arr
    if not isinstance(raw, (list, tuple)) or len(raw) != expected_len:
        raise LivingDexOptionValueError(f"{subject} wrong shape")
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise LivingDexOptionValueError(f"{subject} contains nonnumeric cells")
        val = float(item)
        if not math.isfinite(val):
            raise LivingDexOptionValueError(f"{subject} contains nonfinite values")
        if positive_only and val <= 0.0:
            raise LivingDexOptionValueError(f"{subject} must be positive")
    return np.asarray(raw, dtype=np.float64)


def _validate_numeric_matrix(
    raw: object,
    expected_shape: tuple[int, int],
    *,
    subject: str,
) -> NDArray[np.float64]:
    rows, cols = expected_shape
    if isinstance(raw, np.ndarray):
        if raw.dtype.kind == "b" or raw.dtype.kind not in ("f", "i"):
            raise LivingDexOptionValueError(f"{subject} must be numeric")
        if raw.shape != (rows, cols):
            raise LivingDexOptionValueError(f"{subject} wrong shape")
        arr = raw.astype(np.float64, copy=False)
        if not np.all(np.isfinite(arr)):
            raise LivingDexOptionValueError(f"{subject} contains nonfinite values")
        return arr
    if not isinstance(raw, (list, tuple)) or len(raw) != rows:
        raise LivingDexOptionValueError(f"{subject} wrong shape")
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) != cols:
            raise LivingDexOptionValueError(f"{subject} wrong shape")
        for item in row:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise LivingDexOptionValueError(f"{subject} contains nonnumeric cells")
            if not math.isfinite(float(item)):
                raise LivingDexOptionValueError(f"{subject} contains nonfinite values")
    return np.asarray(raw, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class LivingDexPredictedEconomyOutcome:
    useful_liquidity_gain: float
    cash_loss: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "useful_liquidity_gain",
            _unit_interval(self.useful_liquidity_gain, subject="predicted useful_liquidity_gain"),
        )
        object.__setattr__(
            self,
            "cash_loss",
            _unit_interval(self.cash_loss, subject="predicted cash_loss"),
        )

    def vector(self) -> tuple[float, float]:
        return (self.useful_liquidity_gain, self.cash_loss)


@dataclass(frozen=True, slots=True)
class LivingDexEconomyHead:
    """Two-output linear value head for useful liquidity gain and cash loss."""

    coefficients: NDArray[np.float64]
    intercept: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    evidence_digest: str
    qualified_examples: int
    ridge: float
    maximum_importance_weight: float
    useful_liquidity_gain_weight: float = 1.0
    cash_loss_weight: float = 1.0
    schema: str = LIVING_DEX_ECONOMY_HEAD_SCHEMA
    normalization: str = LIVING_DEX_ECONOMY_NORMALIZATION
    objective: str = LIVING_DEX_ECONOMY_OBJECTIVE

    def __post_init__(self) -> None:
        if self.schema != LIVING_DEX_ECONOMY_HEAD_SCHEMA:
            raise LivingDexOptionValueError("living-Dex economy head schema differs")
        if self.normalization != LIVING_DEX_ECONOMY_NORMALIZATION:
            raise LivingDexOptionValueError("living-Dex economy head normalization differs")
        if self.objective != LIVING_DEX_ECONOMY_OBJECTIVE:
            raise LivingDexOptionValueError("living-Dex economy head objective differs")
        width = len(option_feature_names(4))
        targets = len(LIVING_DEX_ECONOMY_OUTCOME_NAMES)
        coefficients = _validate_numeric_matrix(
            self.coefficients, (width, targets), subject="coefficients"
        )
        intercept = _validate_numeric_vector(self.intercept, targets, subject="intercept")
        mean = _validate_numeric_vector(self.feature_mean, width, subject="feature_mean")
        scale = _validate_numeric_vector(
            self.feature_scale, width, subject="feature_scale", positive_only=True
        )
        if (
            not isinstance(self.evidence_digest, str)
            or _SHA256.fullmatch(self.evidence_digest) is None
        ):
            raise LivingDexOptionValueError("living-Dex economy head evidence digest differs")
        if type(self.qualified_examples) is not int or self.qualified_examples < 2:  # noqa: E721
            raise LivingDexOptionValueError(
                "living-Dex economy head qualified examples must be an integer >= 2"
            )
        object.__setattr__(self, "ridge", _positive_finite(self.ridge, subject="ridge"))
        cap = _positive_finite(
            self.maximum_importance_weight,
            subject="maximum importance weight",
        )
        if cap < 1.0:
            raise LivingDexOptionValueError("maximum importance weight must be at least one")
        object.__setattr__(self, "maximum_importance_weight", cap)
        if (
            isinstance(self.useful_liquidity_gain_weight, bool)
            or not isinstance(self.useful_liquidity_gain_weight, (int, float))
            or float(self.useful_liquidity_gain_weight) != 1.0
        ):
            raise LivingDexOptionValueError(
                "useful_liquidity_gain_weight must be 1.0 for this schema"
            )
        if (
            isinstance(self.cash_loss_weight, bool)
            or not isinstance(self.cash_loss_weight, (int, float))
            or float(self.cash_loss_weight) != 1.0
        ):
            raise LivingDexOptionValueError("cash_loss_weight must be 1.0 for this schema")
        object.__setattr__(self, "useful_liquidity_gain_weight", 1.0)
        object.__setattr__(self, "cash_loss_weight", 1.0)
        for name, value in (
            ("coefficients", coefficients),
            ("intercept", intercept),
            ("feature_mean", mean),
            ("feature_scale", scale),
        ):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)

    def predict_candidate(
        self,
        context: LivingDexOptionContext,
        candidate: LivingDexOptionCandidate,
    ) -> LivingDexPredictedEconomyOutcome:
        if not isinstance(context, LivingDexOptionContext):
            raise TypeError("context must be a LivingDexOptionContext")
        if not isinstance(candidate, LivingDexOptionCandidate):
            raise TypeError("candidate must be a LivingDexOptionCandidate")
        if context.economy_snapshot is None or context.target_cash is None:
            raise LivingDexOptionValueError(
                "living-Dex economy prediction requires economy context"
            )
        vector = np.asarray(
            replace(candidate, readiness=None, challenge=None, preparation=None, level_workload=None, move_change=None, capture_invocation=None, matchup=None).vector(
                context, feature_version=4
            ),
            dtype=np.float64,
        )
        normalized = (vector - self.feature_mean) / self.feature_scale
        raw = self.intercept + normalized @ self.coefficients
        # The label is capped by the pre-action shortfall and available cash.
        # Preserve the fitted estimate inside that analytically feasible range.
        scale = max(1, context.target_cash)
        cash = context.economy_snapshot.cash
        upper = np.asarray(
            (
                min(1.0, max(0, context.target_cash - cash) / scale),
                min(1.0, cash / scale),
            ),
            dtype=np.float64,
        )
        clipped = np.clip(raw, 0.0, upper)
        return LivingDexPredictedEconomyOutcome(
            useful_liquidity_gain=float(clipped[0]),
            cash_loss=float(clipped[1]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "cash_loss_weight": self.cash_loss_weight,
            "coefficients": self.coefficients.tolist(),
            "evidence_digest": self.evidence_digest,
            "feature_mean": self.feature_mean.tolist(),
            "feature_names": list(option_feature_names(4)),
            "feature_scale": self.feature_scale.tolist(),
            "intercept": self.intercept.tolist(),
            "maximum_importance_weight": self.maximum_importance_weight,
            "normalization": self.normalization,
            "objective": self.objective,
            "outcome_names": list(LIVING_DEX_ECONOMY_OUTCOME_NAMES),
            "qualified_examples": self.qualified_examples,
            "ridge": self.ridge,
            "schema": self.schema,
            "useful_liquidity_gain_weight": self.useful_liquidity_gain_weight,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> LivingDexEconomyHead:
        if not isinstance(value, Mapping):
            raise LivingDexOptionValueError("living-Dex economy head document differs")
        expected_keys = {
            "cash_loss_weight",
            "coefficients",
            "evidence_digest",
            "feature_mean",
            "feature_names",
            "feature_scale",
            "intercept",
            "maximum_importance_weight",
            "normalization",
            "objective",
            "outcome_names",
            "qualified_examples",
            "ridge",
            "schema",
            "useful_liquidity_gain_weight",
        }
        if set(value) != expected_keys:
            raise LivingDexOptionValueError("living-Dex economy head document differs")
        feature_names = value.get("feature_names")
        outcome_names = value.get("outcome_names")
        evidence_digest = value.get("evidence_digest")
        qualified_examples = value.get("qualified_examples")
        ridge = value.get("ridge")
        maximum_importance_weight = value.get("maximum_importance_weight")
        useful_weight = value.get("useful_liquidity_gain_weight")
        cash_weight = value.get("cash_loss_weight")

        if (
            value.get("schema") != LIVING_DEX_ECONOMY_HEAD_SCHEMA
            or value.get("normalization") != LIVING_DEX_ECONOMY_NORMALIZATION
            or value.get("objective") != LIVING_DEX_ECONOMY_OBJECTIVE
            or not isinstance(feature_names, list)
            or tuple(feature_names) != option_feature_names(4)
            or not isinstance(outcome_names, list)
            or tuple(outcome_names) != LIVING_DEX_ECONOMY_OUTCOME_NAMES
            or not isinstance(evidence_digest, str)
            or _SHA256.fullmatch(evidence_digest) is None
            or type(qualified_examples) is not int  # noqa: E721
            or qualified_examples < 2
            or isinstance(ridge, bool)
            or not isinstance(ridge, (int, float))
            or isinstance(maximum_importance_weight, bool)
            or not isinstance(maximum_importance_weight, (int, float))
            or isinstance(useful_weight, bool)
            or not isinstance(useful_weight, (int, float))
            or float(useful_weight) != 1.0
            or isinstance(cash_weight, bool)
            or not isinstance(cash_weight, (int, float))
            or float(cash_weight) != 1.0
        ):
            raise LivingDexOptionValueError("living-Dex economy head schema differs")
        width = len(option_feature_names(4))
        targets = len(LIVING_DEX_ECONOMY_OUTCOME_NAMES)
        coefficients = _validate_numeric_matrix(
            value.get("coefficients"), (width, targets), subject="coefficients"
        )
        intercept = _validate_numeric_vector(value.get("intercept"), targets, subject="intercept")
        feature_mean = _validate_numeric_vector(
            value.get("feature_mean"), width, subject="feature_mean"
        )
        feature_scale = _validate_numeric_vector(
            value.get("feature_scale"), width, subject="feature_scale", positive_only=True
        )
        return cls(
            coefficients=coefficients,
            intercept=intercept,
            feature_mean=feature_mean,
            feature_scale=feature_scale,
            evidence_digest=evidence_digest,
            qualified_examples=qualified_examples,
            ridge=float(ridge),
            maximum_importance_weight=float(maximum_importance_weight),
            useful_liquidity_gain_weight=1.0,
            cash_loss_weight=1.0,
        )


def qualified_economy_rows(
    rows: Iterable[object],
) -> tuple[LivingDexObservedArmExample, ...]:
    result: list[LivingDexObservedArmExample] = []
    for row in rows:
        if not isinstance(row, LivingDexObservedArmExample):
            continue
        if row.partition != "train":
            continue
        if row.outcome.status is not LivingDexOutcomeStatus.SETTLED:
            continue
        if row.outcome.economy is None or not isinstance(row.outcome.economy, EconomyOutcome):
            continue
        ctx = row.menu.context
        if ctx.economy_snapshot is None or ctx.target_cash is None:
            continue
        if len(row.menu.available_indices) < 2:
            continue
        result.append(row)
    return tuple(result)


def fit_living_dex_economy_head(
    examples: Iterable[LivingDexObservedArmExample],
    *,
    ridge: float = DEFAULT_OPTION_VALUE_RIDGE,
    maximum_importance_weight: float = DEFAULT_MAX_IMPORTANCE_WEIGHT,
    useful_liquidity_gain_weight: float = 1.0,
    cash_loss_weight: float = 1.0,
) -> LivingDexEconomyHead:
    ridge_value = _positive_finite(ridge, subject="ridge")
    cap = _positive_finite(
        maximum_importance_weight,
        subject="maximum importance weight",
    )
    if cap < 1.0:
        raise LivingDexOptionValueError("maximum importance weight must be at least one")
    if (
        isinstance(useful_liquidity_gain_weight, bool)
        or not isinstance(useful_liquidity_gain_weight, (int, float))
        or float(useful_liquidity_gain_weight) != 1.0
    ):
        raise LivingDexOptionValueError("useful_liquidity_gain_weight must be 1.0 for this schema")
    if (
        isinstance(cash_loss_weight, bool)
        or not isinstance(cash_loss_weight, (int, float))
        or float(cash_loss_weight) != 1.0
    ):
        raise LivingDexOptionValueError("cash_loss_weight must be 1.0 for this schema")
    validated = _validated_examples(examples, expected_partition="train")
    qualified = qualified_economy_rows(validated)
    if len(qualified) < 2:
        raise LivingDexOptionValueError(
            "living-Dex economy head fit needs at least two qualified examples"
        )
    sorted_rows = tuple(
        sorted(
            qualified,
            key=lambda row: row.decision_sha256,
        )
    )
    features = np.asarray(
        [
            replace(
                row.menu.candidates[row.selected_candidate_index],
                readiness=None,
                challenge=None,
                preparation=None,
                level_workload=None,
                move_change=None,
                capture_invocation=None,
                matchup=None,
            ).vector(row.menu.context, feature_version=4)
            for row in sorted_rows
        ],
        dtype=np.float64,
    )
    targets_list: list[tuple[float, float]] = []
    for row in sorted_rows:
        econ = row.outcome.economy
        if econ is None or not isinstance(econ, EconomyOutcome):
            raise LivingDexOptionValueError("qualified economy row missing EconomyOutcome")
        targets_list.append((econ.useful_liquidity_gain, econ.cash_loss))
    targets = np.asarray(targets_list, dtype=np.float64)

    weights = np.asarray(
        [row.importance_weight(cap) for row in sorted_rows],
        dtype=np.float64,
    )
    mean = np.average(features, axis=0, weights=weights)
    centered = features - mean
    scale = np.sqrt(np.average(centered**2, axis=0, weights=weights))
    scale[scale == 0.0] = 1.0
    normalized = (features - mean) / scale
    design = np.column_stack((np.ones(len(sorted_rows), dtype=np.float64), normalized))
    penalty = np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = 0.0
    weighted_design = design * weights[:, np.newaxis]
    left = design.T @ weighted_design + ridge_value * penalty
    right = design.T @ (weights[:, np.newaxis] * targets)
    try:
        parameters = cast(NDArray[np.float64], np.linalg.solve(left, right))
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError("living-Dex economy head fit is singular") from None
    intercept = parameters[0]
    coefficients = parameters[1:]
    evidence_digest = canonical_sha256(
        {
            "rows": [row.public_dict() for row in sorted_rows],
            "schema": LIVING_DEX_ECONOMY_EVIDENCE_SCHEMA,
        }
    )
    return LivingDexEconomyHead(
        coefficients=coefficients,
        intercept=intercept,
        feature_mean=mean,
        feature_scale=scale,
        evidence_digest=evidence_digest,
        qualified_examples=len(sorted_rows),
        ridge=ridge_value,
        maximum_importance_weight=cap,
        useful_liquidity_gain_weight=1.0,
        cash_loss_weight=1.0,
    )


@dataclass(frozen=True, slots=True)
class LivingDexBoundedStorySuccessHead:
    """Explicit learned correction to bounded parent success, gated to story options."""

    coefficients: NDArray[np.float64]
    intercept: float
    parent_model_sha256: str
    feature_version: int = 9

    def __post_init__(self):
        supplied = np.asarray(self.coefficients, dtype=object)
        if (supplied.shape != (len(option_feature_names(9)),)
                or any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.integer, np.floating))
                       for v in supplied)):
            raise LivingDexOptionValueError("bounded story head coefficients must be numeric")
        coefficients = np.asarray(self.coefficients, dtype=np.float64)
        if (type(self.feature_version) is not int or self.feature_version != 9
                or coefficients.shape != (len(option_feature_names(9)),)
                or not np.all(np.isfinite(coefficients))
                or isinstance(self.intercept, (bool, np.bool_))
                or not isinstance(self.intercept, (int, float, np.floating))
                or not math.isfinite(self.intercept)
                or type(self.parent_model_sha256) is not str
                or _SHA256.fullmatch(self.parent_model_sha256) is None):
            raise LivingDexOptionValueError("bounded story head parameters differ")
        coefficients = coefficients.copy()
        coefficients.setflags(write=False)
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(self, "intercept", float(self.intercept))

    def to_dict(self):
        return dict(schema=LIVING_DEX_BOUNDED_STORY_SUCCESS_HEAD_SCHEMA,
                    feature_version=9, feature_names=list(option_feature_names(9)),
                    kind="unlock_access", parent_model_sha256=self.parent_model_sha256,
                    coefficients=self.coefficients.tolist(), intercept=self.intercept)

    @classmethod
    def from_dict(cls, value):
        keys = {"schema", "feature_version", "feature_names", "kind",
                "parent_model_sha256", "coefficients", "intercept"}
        if (not isinstance(value, Mapping) or set(value) != keys
                or value.get("schema") != LIVING_DEX_BOUNDED_STORY_SUCCESS_HEAD_SCHEMA
                or value.get("kind") != "unlock_access"
                or value.get("feature_names") != list(option_feature_names(9))):
            raise LivingDexOptionValueError("bounded story head document differs")
        return cls(value["coefficients"], value["intercept"],
                   value["parent_model_sha256"], value["feature_version"])


def bounded_matchup_story_feature_indices() -> tuple[int, ...]:
    """Fixed semantic V15 basis; never select coordinates from labels or DEV."""
    names = option_feature_names(15)
    selected = tuple(i for i, name in enumerate(names)
                     if not (name.startswith("readiness.") and "_x_budget." in name))
    if len(names) != 506 or len(selected) != 461:
        raise LivingDexOptionValueError("declared V15 non-budget basis changed")
    return selected


@dataclass(frozen=True, slots=True)
class LivingDexBoundedMatchupStorySuccessHead:
    """V2 bounded correction with independent TRAIN-story normalization."""
    coefficients: NDArray[np.float64]
    intercept: float
    parent_model_sha256: str
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    constant_mask: NDArray[np.bool_]
    normalization_evidence_sha256: str
    feature_indices: tuple[int, ...] = field(default_factory=bounded_matchup_story_feature_indices)
    feature_version: int = 15

    def __post_init__(self):
        expected = bounded_matchup_story_feature_indices()
        if (type(self.feature_version) is not int or self.feature_version != 15
                or type(self.feature_indices) is not tuple or self.feature_indices != expected
                or any(type(i) is not int for i in self.feature_indices)):
            raise LivingDexOptionValueError("bounded matchup head requires its exact V15 semantic basis")
        width = len(expected)
        arrays = []
        for name in ("coefficients", "feature_mean", "feature_scale"):
            supplied = np.asarray(getattr(self, name), dtype=object)
            if (supplied.shape != (width,) or any(
                    isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.integer, np.floating))
                    for v in supplied)):
                raise LivingDexOptionValueError("bounded matchup head requires numeric arrays")
            value = np.asarray(getattr(self, name), dtype=np.float64)
            if not np.all(np.isfinite(value)):
                raise LivingDexOptionValueError("bounded matchup head contains nonfinite measurements")
            arrays.append(value)
        coefficients, mean, scale = arrays
        supplied_mask = np.asarray(self.constant_mask, dtype=object)
        if (supplied_mask.shape != (width,)
                or any(not isinstance(v, (bool, np.bool_)) for v in supplied_mask)):
            raise LivingDexOptionValueError("bounded matchup constant mask must be boolean")
        constant = np.asarray(self.constant_mask, dtype=bool)
        if (np.any(scale < _BOUNDED_MATCHUP_SCALE_FLOOR)
                or np.any(scale[constant] != 1.) or np.any(coefficients[constant] != 0.)
                or isinstance(self.intercept, (bool, np.bool_))
                or not isinstance(self.intercept, (int, float, np.floating))
                or not math.isfinite(self.intercept)):
            raise LivingDexOptionValueError("bounded matchup normalization or constant coefficients differ")
        for digest in (self.parent_model_sha256, self.normalization_evidence_sha256):
            if type(digest) is not str or _SHA256.fullmatch(digest) is None:
                raise LivingDexOptionValueError("bounded matchup head lacks immutable provenance")
        for name, value in zip(("coefficients", "feature_mean", "feature_scale", "constant_mask"),
                               (*arrays, constant), strict=True):
            detached = value.copy(); detached.setflags(write=False)
            object.__setattr__(self, name, detached)
        object.__setattr__(self, "intercept", float(self.intercept))

    @property
    def feature_names(self):
        names = option_feature_names(15)
        return tuple(names[i] for i in self.feature_indices)

    def to_dict(self):
        return dict(schema=LIVING_DEX_BOUNDED_MATCHUP_STORY_SUCCESS_HEAD_SCHEMA,
            feature_version=15, feature_names=list(self.feature_names), feature_indices=list(self.feature_indices),
            kind="unlock_access", parent_model_sha256=self.parent_model_sha256,
            coefficients=self.coefficients.tolist(), intercept=self.intercept,
            normalization=dict(schema=_BOUNDED_MATCHUP_NORMALIZATION_SCHEMA,
                feature_mean=self.feature_mean.tolist(), feature_scale=self.feature_scale.tolist(),
                constant_mask=self.constant_mask.tolist(), scale_floor=_BOUNDED_MATCHUP_SCALE_FLOOR,
                constant_threshold_multiplier=_BOUNDED_MATCHUP_CONSTANT_MULTIPLIER,
                training_input_sha256=self.normalization_evidence_sha256))

    @classmethod
    def from_dict(cls, value):
        keys = {"schema","feature_version","feature_names","feature_indices","kind",
                "parent_model_sha256","coefficients","intercept","normalization"}
        indices = bounded_matchup_story_feature_indices()
        if (not isinstance(value, Mapping) or set(value) != keys
                or value.get("schema") != LIVING_DEX_BOUNDED_MATCHUP_STORY_SUCCESS_HEAD_SCHEMA
                or value.get("kind") != "unlock_access" or value.get("feature_indices") != list(indices)
                or any(type(i) is not int for i in value["feature_indices"])
                or value.get("feature_names") != [option_feature_names(15)[i] for i in indices]):
            raise LivingDexOptionValueError("bounded matchup head document differs")
        norm = value["normalization"]
        if (not isinstance(norm, Mapping) or set(norm) != {"schema","feature_mean","feature_scale",
                "constant_mask","scale_floor","constant_threshold_multiplier","training_input_sha256"}
                or norm.get("schema") != _BOUNDED_MATCHUP_NORMALIZATION_SCHEMA
                or type(norm.get("scale_floor")) not in (int, float)
                or norm["scale_floor"] != _BOUNDED_MATCHUP_SCALE_FLOOR
                or type(norm.get("constant_threshold_multiplier")) not in (int, float)
                or norm["constant_threshold_multiplier"] != _BOUNDED_MATCHUP_CONSTANT_MULTIPLIER):
            raise LivingDexOptionValueError("bounded matchup normalization contract differs")
        return cls(value["coefficients"], value["intercept"], value["parent_model_sha256"],
            norm["feature_mean"], norm["feature_scale"], norm["constant_mask"], norm["training_input_sha256"],
            tuple(value["feature_indices"]), value["feature_version"])


def _restore_bounded_story_success_head(value):
    if isinstance(value, Mapping) and value.get("schema") == LIVING_DEX_BOUNDED_MATCHUP_STORY_SUCCESS_HEAD_SCHEMA:
        return LivingDexBoundedMatchupStorySuccessHead.from_dict(value)
    return LivingDexBoundedStorySuccessHead.from_dict(value)


def _bounded_story_mask(values):
    """Reject ambiguous public kind encodings before applying the runtime gate."""
    names = option_feature_names(9)
    kinds = [i for i, name in enumerate(names) if name.startswith("kind.")]
    columns = values[..., kinds]
    if np.any((columns != 0.) & (columns != 1.)) or np.any(columns.sum(axis=-1) != 1.):
        raise LivingDexOptionValueError("bounded story prediction requires an exact one-hot kind")
    return values[..., names.index("kind.unlock_access")] == 1.


@dataclass(frozen=True, slots=True)
class LivingDexOptionValueModel:
    """Multi-outcome linear value model fitted only on selected arms."""

    coefficients: NDArray[np.float64]
    intercept: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    train_dataset_sha256: str
    settled_examples: int
    censored_examples: int
    ridge: float
    maximum_importance_weight: float
    feature_version: int = 1
    objective: str = LIVING_DEX_OPTION_OBJECTIVE
    economy_head: LivingDexEconomyHead | None = None
    bounded_story_success_head: LivingDexBoundedStorySuccessHead | LivingDexBoundedMatchupStorySuccessHead | None = None

    def __post_init__(self) -> None:
        if self.objective not in {
            LIVING_DEX_OPTION_OBJECTIVE,
            "selected-arm-ips-plus-unit-curriculum-multioutcome-ridge-v1",
            *_RETAINED_HEAD_OBJECTIVES,
        }:
            raise LivingDexOptionValueError("living-Dex regression objective differs")
        if (self.objective in _PARTY_COST_RESIDUAL_OBJECTIVES
                and self.feature_version < 9):
            raise LivingDexOptionValueError("party cost retained models require feature version9 or a zero extension")
        if (self.objective == LIVING_DEX_STORY_SUCCESS_RETAINED_OBJECTIVE
                and self.feature_version < 9):
            raise LivingDexOptionValueError("story success retained models require V9 or a zero extension")
        headed_v1 = self.objective == LIVING_DEX_BOUNDED_STORY_SUCCESS_OBJECTIVE
        headed_v2 = self.objective == LIVING_DEX_BOUNDED_MATCHUP_STORY_SUCCESS_OBJECTIVE
        if ((headed_v1 or headed_v2) != (self.bounded_story_success_head is not None)
                or (headed_v1 and (not isinstance(self.bounded_story_success_head, LivingDexBoundedStorySuccessHead)
                                   or self.feature_version not in (9, 10)))
                or (headed_v2 and (not isinstance(self.bounded_story_success_head, LivingDexBoundedMatchupStorySuccessHead)
                                   or self.feature_version != 15))):
            raise LivingDexOptionValueError("bounded story objective, head or qualified prefix differs")
        width = len(option_feature_names(self.feature_version))
        targets = len(LIVING_DEX_OPTION_OUTCOME_NAMES)
        arrays = tuple(
            np.asarray(value, dtype=np.float64)
            for value in (
                self.coefficients,
                self.intercept,
                self.feature_mean,
                self.feature_scale,
            )
        )
        coefficients, intercept, mean, scale = arrays
        if (
            coefficients.shape != (width, targets)
            or intercept.shape != (targets,)
            or mean.shape != (width,)
            or scale.shape != (width,)
            or not all(np.all(np.isfinite(value)) for value in arrays)
            or np.any(scale <= 0.0)
        ):
            raise LivingDexOptionValueError("living-Dex option model parameters differ")
        if (
            not isinstance(self.train_dataset_sha256, str)
            or _SHA256.fullmatch(self.train_dataset_sha256) is None
        ):
            raise LivingDexOptionValueError("living-Dex train dataset identity differs")
        if (
            type(self.settled_examples) is not int  # noqa: E721
            or self.settled_examples < 2
            or type(self.censored_examples) is not int  # noqa: E721
            or self.censored_examples < 0
        ):
            raise LivingDexOptionValueError("living-Dex model example counts differ")
        object.__setattr__(self, "ridge", _positive_finite(self.ridge, subject="ridge"))
        cap = _positive_finite(
            self.maximum_importance_weight,
            subject="maximum importance weight",
        )
        if cap < 1.0:
            raise LivingDexOptionValueError("maximum importance weight must be at least one")
        object.__setattr__(self, "maximum_importance_weight", cap)
        for name, value in zip(
            ("coefficients", "intercept", "feature_mean", "feature_scale"),
            arrays,
            strict=True,
        ):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)
        if self.economy_head is not None:
            if self.feature_version not in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
                raise LivingDexOptionValueError(
                    "only feature_version 4 through 15 can carry an economy head"
                )
            if not isinstance(self.economy_head, LivingDexEconomyHead):
                raise LivingDexOptionValueError("economy_head must be a LivingDexEconomyHead")
            # A retained economy head describes its original dataset, while
            # settled_examples counts only this explicitly retained-head update.
            if (self.objective not in _RETAINED_HEAD_OBJECTIVES
                    and self.economy_head.qualified_examples > self.settled_examples):
                raise LivingDexOptionValueError(
                    "living-Dex economy head qualified examples exceed settled examples"
                )

        if self.objective in _COMPLETE_PAID_SUCCESS_OBJECTIVES.values():
            prefix = len(option_feature_names(12))
            success = LIVING_DEX_OPTION_OUTCOME_NAMES.index("verified_success")
            basis = next(b for b, objective in _COMPLETE_PAID_SUCCESS_OBJECTIVES.items()
                         if objective == self.objective)
            allowed = complete_paid_success_columns(basis)
            forbidden = tuple(i for i in range(len(self.coefficients) - prefix) if i not in allowed)
            if (self.feature_version not in (13, 14, 15)
                    or self.feature_version < complete_paid_success_version(basis)
                    or np.any(self.feature_mean[prefix:] != 0.)
                    or np.any(self.feature_scale[prefix:] != 1.)
                    or np.any(np.delete(self.coefficients[prefix:], success, axis=1) != 0.)
                    or any(np.any(self.coefficients[prefix + i] != 0.) for i in forbidden)):
                raise LivingDexOptionValueError("complete-paid residual model parameters differ")

    def story_success_components(self, vectors) -> dict[str, NDArray[np.float64]]:
        """Report actual bounded-head inputs and outputs; never fit or select."""
        head = self.bounded_story_success_head
        if head is None:
            raise LivingDexOptionValueError("model has no bounded story success head")
        values = np.asarray(vectors, dtype=np.float64)
        raw = self._base_raw_predictions(values)
        prefix = len(option_feature_names(9))
        story = _bounded_story_mask(values[..., :prefix])
        if isinstance(head, LivingDexBoundedMatchupStorySuccessHead):
            selected = values[..., head.feature_indices]
            normalized = (selected - head.feature_mean) / head.feature_scale
            normalized[..., head.constant_mask] = 0.
            contributions = np.zeros_like(values)
            contributions[..., head.feature_indices] = normalized * head.coefficients
        else:
            normalized = (values[..., :prefix] - self.feature_mean[:prefix]) / self.feature_scale[:prefix]
            contributions = normalized * head.coefficients
        delta = np.where(story, head.intercept + normalized @ head.coefficients, 0.)
        success = LIVING_DEX_OPTION_OUTCOME_NAMES.index("verified_success")
        base = raw[..., success]
        bounded = np.clip(base, 0., 1.)
        preclip = np.where(story, bounded + delta, base)
        return dict(base_raw=base, bounded_base=bounded, learned_delta=delta,
                    preclip=preclip, final=np.clip(preclip, 0., 1.), story_mask=story,
                    correction_feature_contributions=np.where(story[..., None], contributions, 0.),
                    correction_intercept=np.where(story, head.intercept, 0.))

    def raw_predictions(self, vectors) -> NDArray[np.float64]:
        raw = self._base_raw_predictions(vectors)
        if self.bounded_story_success_head is not None:
            components = self.story_success_components(vectors)
            raw[..., LIVING_DEX_OPTION_OUTCOME_NAMES.index("verified_success")] = components["preclip"]
        return raw

    def _base_raw_predictions(self, vectors) -> NDArray[np.float64]:
        """Use one raw calculation for scoring, fit diagnostics and evaluation.

        V13 computes the frozen V12 prefix with its original width. Adding zero
        suffix columns must not change its floating-point reduction order.
        """
        values = np.asarray(vectors, dtype=np.float64)
        if (values.ndim not in (1, 2)
                or values.shape[-1] != len(self.feature_mean)
                or not np.all(np.isfinite(values))):
            raise LivingDexOptionValueError("raw prediction input shape or values differ")
        if self.feature_version not in (13, 14, 15):
            return self.intercept + ((values - self.feature_mean) / self.feature_scale) @ self.coefficients
        prefix = len(option_feature_names(12))
        for row in values.reshape(-1, values.shape[-1]):
            expected = project_complete_paid_capture_features(row[:prefix])
            if self.feature_version >= 14:
                expected = project_complete_paid_density_features(expected)
            if self.feature_version == 15:
                expected = project_matchup_features(
                    expected, _matchup_from_vector(row[len(option_feature_names(14)):]))
            if tuple(row) != expected:
                raise LivingDexOptionValueError("complete-paid suffix differs from its V12 input")
        normalized_prefix = (values[..., :prefix] - self.feature_mean[:prefix]) / self.feature_scale[:prefix]
        raw = self.intercept + normalized_prefix @ np.ascontiguousarray(self.coefficients[:prefix])
        # Preserve V13's two-term reduction before adding new V14 density terms.
        prior_width = len(option_feature_names(14)) if self.feature_version == 15 else len(self.feature_mean)
        spans = ((prefix, prefix + 2), (prefix + 2, prior_width))
        if self.feature_version == 15:
            spans += ((prior_width, len(self.feature_mean)),)
        for start, stop in spans:
            if start == stop:
                continue
            delta = ((values[..., start:stop] - self.feature_mean[start:stop]) / self.feature_scale[start:stop]) @ np.ascontiguousarray(self.coefficients[start:stop])
            np.add(raw, delta, out=raw, where=delta != 0.)
        return raw

    @property
    def model_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def predict_candidate(
        self,
        context: LivingDexOptionContext,
        candidate: LivingDexOptionCandidate,
    ) -> LivingDexPredictedOutcome:
        if not isinstance(context, LivingDexOptionContext):
            raise TypeError("context must be a LivingDexOptionContext")
        if not isinstance(candidate, LivingDexOptionCandidate):
            raise TypeError("candidate must be a LivingDexOptionCandidate")
        vector = np.asarray(
            candidate.vector(context, feature_version=self.feature_version), dtype=np.float64
        )
        raw = self.raw_predictions(vector)
        return LivingDexPredictedOutcome.from_vector(np.clip(raw, 0.0, 1.0).tolist())

    def predict_economy_candidate(
        self,
        context: LivingDexOptionContext,
        candidate: LivingDexOptionCandidate,
    ) -> LivingDexPredictedEconomyOutcome | None:
        if not isinstance(context, LivingDexOptionContext):
            raise TypeError("context must be a LivingDexOptionContext")
        if not isinstance(candidate, LivingDexOptionCandidate):
            raise TypeError("candidate must be a LivingDexOptionCandidate")
        if self.economy_head is None or self.feature_version not in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
            return None
        if context.economy_snapshot is None or context.target_cash is None:
            return None
        return self.economy_head.predict_candidate(context, candidate)

    def scores(
        self,
        menu: LivingDexOptionMenu,
        utility: LivingDexOptionUtility,
    ) -> tuple[float | None, ...]:
        if not isinstance(menu, LivingDexOptionMenu):
            raise TypeError("menu must be a LivingDexOptionMenu")
        if not isinstance(utility, LivingDexOptionUtility):
            raise TypeError("utility must be a LivingDexOptionUtility")
        result: list[float | None] = []
        for index, candidate in enumerate(menu.candidates):
            if index not in menu.available_indices:
                result.append(None)
                continue
            base = utility.score(self.predict_candidate(menu.context, candidate))
            if self.economy_head is not None:
                econ = self.predict_economy_candidate(menu.context, candidate)
                if econ is not None:
                    base += (
                        self.economy_head.useful_liquidity_gain_weight * econ.useful_liquidity_gain
                        - self.economy_head.cash_loss_weight * econ.cash_loss
                    )
            result.append(base)
        return tuple(result)

    def select(self, menu: LivingDexOptionMenu, utility: LivingDexOptionUtility) -> int:
        values = self.scores(menu, utility)

        def key(index: int) -> tuple[float, int]:
            value = values[index]
            if value is None:
                raise LivingDexOptionValueError("masked living-Dex option reached selection")
            return value, -index

        return max(menu.available_indices, key=key)

    def diagnose_menu(
        self,
        menu: LivingDexOptionMenu,
        utility: LivingDexOptionUtility,
        *,
        selected_index: int | None = None,
    ) -> dict[str, object]:
        """Explain this frozen linear head without selecting, sampling or fitting.

        Outputs are regression estimates, not calibrated success probabilities.
        Contributions explain the raw regression before clipping; utility terms
        explain its bounded score. This receipt is not part of the policy menu.
        """
        if not isinstance(menu, LivingDexOptionMenu) or not isinstance(
            utility, LivingDexOptionUtility
        ):
            raise TypeError("diagnostics require a typed menu and utility")
        scores: dict[int, float] = {}
        if selected_index is not None and selected_index not in menu.available_indices:
            raise LivingDexOptionValueError("diagnostic selection is unavailable")
        names = option_feature_names(self.feature_version)
        weights = (
            utility.success_weight,
            utility.completion_gain_weight,
            utility.dependency_unlock_weight,
            -utility.action_cost_weight,
            -utility.frame_cost_weight,
            -utility.resource_cost_weight,
            -utility.party_cost_weight,
            -utility.storage_cost_weight,
            -utility.irreversible_loss_weight,
        )
        # Menus may be projected at an older feature version than this model.
        vectors = [
            c.vector(menu.context, feature_version=self.feature_version) for c in menu.candidates
        ]
        varying = [
            name for i, name in enumerate(names) if len({vector[i] for vector in vectors}) > 1
        ]
        rows = []
        for index, candidate in enumerate(menu.candidates):
            vector = np.asarray(vectors[index], dtype=np.float64)
            row: dict[str, object] = dict(
                candidate_index=index,
                kind=candidate.features.kind.value,
                available=index in menu.available_indices,
                input_vector=vector.tolist(),
            )
            if index not in menu.available_indices:
                row["score"] = None
                rows.append(row)
                continue
            normalized = (vector - self.feature_mean) / self.feature_scale
            contributions = normalized[:, None] * self.coefficients
            raw = self.raw_predictions(vector)
            bounded = np.clip(raw, 0.0, 1.0)
            scores[index] = utility.score(LivingDexPredictedOutcome.from_vector(bounded.tolist()))
            row.update(
                normalized_input_vector=normalized.tolist(),
                raw_predictions=dict(
                    zip(LIVING_DEX_OPTION_OUTCOME_NAMES, raw.tolist(), strict=True)
                ),
                bounded_predictions=dict(
                    zip(LIVING_DEX_OPTION_OUTCOME_NAMES, bounded.tolist(), strict=True)
                ),
                clipped_outputs=[
                    name
                    for name, value in zip(LIVING_DEX_OPTION_OUTCOME_NAMES, raw, strict=True)
                    if value < 0 or value > 1
                ],
                boundary_outputs=[
                    name
                    for name, value in zip(LIVING_DEX_OPTION_OUTCOME_NAMES, bounded, strict=True)
                    if value in (0, 1)
                ],
                utility_terms=dict(
                    zip(
                        LIVING_DEX_OPTION_OUTCOME_NAMES,
                        [float(v * w) for v, w in zip(bounded, weights, strict=True)],
                        strict=True,
                    )
                ),
                top_raw_contributions={
                    name: [
                        dict(feature=names[i], contribution=float(contributions[i, j]))
                        for i in sorted(
                            range(len(names)), key=lambda i: (-abs(contributions[i, j]), i)
                        )[:8]
                        if contributions[i, j] != 0
                    ]
                    for j, name in enumerate(LIVING_DEX_OPTION_OUTCOME_NAMES)
                },
                score=scores[index],
                economy=None,
            )
            if self.bounded_story_success_head is not None:
                components = self.story_success_components(vector)
                row["bounded_story_success"] = {
                    key: value.tolist() for key, value in components.items()
                }
                row["raw_contribution_scope"] = "base_linear_parameters_only"
                row["bounded_story_success"]["feature_names"] = list(option_feature_names(15 if isinstance(self.bounded_story_success_head, LivingDexBoundedMatchupStorySuccessHead) else 9))
            economy = self.predict_economy_candidate(menu.context, candidate)
            if economy is not None:
                head = self.economy_head
                assert head is not None
                econ_vector = np.asarray(
                    replace(
                        candidate,
                        readiness=None,
                        challenge=None,
                        preparation=None,
                        level_workload=None,
                        move_change=None,
                        capture_invocation=None,
                        matchup=None,
                    ).vector(menu.context, feature_version=4),
                    dtype=np.float64,
                )
                econ_raw = (
                    head.intercept
                    + ((econ_vector - head.feature_mean) / head.feature_scale) @ head.coefficients
                )
                row["economy"] = dict(
                    raw_predictions=dict(
                        zip(LIVING_DEX_ECONOMY_OUTCOME_NAMES, econ_raw.tolist(), strict=True)
                    ),
                    bounded_predictions=dict(
                        zip(LIVING_DEX_ECONOMY_OUTCOME_NAMES, economy.vector(), strict=True)
                    ),
                    score_adjustment=(
                        head.useful_liquidity_gain_weight * economy.useful_liquidity_gain
                        - head.cash_loss_weight * economy.cash_loss
                    ),
                    qualified_train_examples=head.qualified_examples,
                )
                scores[index] += (
                    head.useful_liquidity_gain_weight * economy.useful_liquidity_gain
                    - head.cash_loss_weight * economy.cash_loss
                )
                row["score"] = scores[index]
            rows.append(row)
        ranked = sorted(menu.available_indices, key=lambda i: (-scores[i], i))
        best = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else None
        comparison = runner_up if selected_index == best else best
        differences = (
            []
            if selected_index is None or comparison is None
            else [
                dict(
                    feature=name,
                    selected=vectors[selected_index][i],
                    compared=vectors[comparison][i],
                )
                for i, name in enumerate(names)
                if vectors[selected_index][i] != vectors[comparison][i]
            ]
        )
        diagnostic = dict(
            schema="pokemon.core.option-value-diagnostics.v1",
            diagnostic_only=True,
            prediction_is_calibrated_probability=False,
            model_sha256=self.model_sha256,
            feature_version=self.feature_version,
            feature_names=list(names),
            feature_mean=self.feature_mean.tolist(),
            feature_scale=self.feature_scale.tolist(),
            intercept=self.intercept.tolist(),
            settled_train_examples=self.settled_examples,
            weighted_feature_count=int(np.count_nonzero(np.any(self.coefficients != 0, axis=1))),
            varying_features=varying,
            candidates=rows,
            best_candidate_index=best,
            runner_up_candidate_index=runner_up,
            best_runner_up_score_margin=(
                None if runner_up is None else scores[best] - scores[runner_up]
            ),
            selected_candidate_index=selected_index,
            compared_candidate_index=comparison,
            selected_feature_differences=differences,
            score_margin_is_confidence=False,
        )
        if self.bounded_story_success_head is not None:
            diagnostic["weighted_feature_count_scope"] = "base_linear_parameters_only"
            diagnostic["bounded_head_weighted_feature_count"] = int(np.count_nonzero(self.bounded_story_success_head.coefficients))
        return diagnostic

    def diagnose_training_coverage(
        self,
        examples: Iterable[LivingDexObservedArmExample],
        *,
        curriculum_examples: Iterable[LivingDexCurriculumOutcomeExample] = (),
    ) -> dict[str, object]:
        """Inspect admitted TRAIN coverage and residuals; never produce a fit.

        Constant/nonzero features are not proof of independent coverage. Censored
        rows count as attempts, but do not become successful or failed targets.
        """
        rows = _validated_examples(examples, expected_partition="train")
        curriculum = _validated_curriculum(curriculum_examples, rows)
        dataset_sha256 = living_dex_option_train_dataset_sha256(
            rows,
            curriculum_examples=curriculum,
        )
        combined: list[LivingDexObservedArmExample | LivingDexCurriculumOutcomeExample] = [
            *rows,
            *curriculum,
        ]
        settled = [row for row in combined if row.outcome.status is LivingDexOutcomeStatus.SETTLED]
        if not settled:
            raise LivingDexOptionValueError("coverage requires settled TRAIN observations")
        feature_rows = [
            curriculum_features(row, self.feature_version)
            if isinstance(row, LivingDexCurriculumOutcomeExample)
            else row.menu.candidate_vector(
                row.selected_candidate_index, feature_version=self.feature_version
            )
            for row in settled
        ]
        vectors = np.asarray(feature_rows, dtype=np.float64)
        targets = np.asarray([row.outcome.target_vector for row in settled], dtype=np.float64)
        raw = self.raw_predictions(vectors)
        predicted = np.clip(raw, 0, 1)
        by_kind: dict[str, dict[str, int]] = {}
        for row in rows:
            kind = row.menu.candidates[row.selected_candidate_index].features.kind.value
            counts = by_kind.setdefault(kind, dict(attempts=0, successes=0, failures=0, censored=0))
            counts["attempts"] += 1
            if row.outcome.status is LivingDexOutcomeStatus.CENSORED:
                counts["censored"] += 1
            else:
                counts["successes" if row.outcome.verified_success else "failures"] += 1
        unit_by_kind: dict[str, dict[str, int]] = {}
        for unit in curriculum:
            kind_names = [
                name.removeprefix("kind.")
                for name, value in zip(
                    option_feature_names(unit.feature_version), unit.features, strict=True
                )
                if name.startswith("kind.") and value == 1
            ]
            kind = kind_names[0] if len(kind_names) == 1 else "unresolved"
            counts = unit_by_kind.setdefault(
                kind, dict(attempts=0, successes=0, failures=0, censored=0)
            )
            counts["attempts"] += 1
            if unit.outcome.status is LivingDexOutcomeStatus.CENSORED:
                counts["censored"] += 1
            else:
                counts["successes" if unit.outcome.verified_success else "failures"] += 1
        names = option_feature_names(self.feature_version)
        coverage = dict(
            schema="pokemon.core.option-train-coverage.v1",
            diagnostic_only=True,
            automatic_fit=False,
            independent_coverage_not_established=True,
            model_sha256=self.model_sha256,
            inspected_dataset_sha256=dataset_sha256,
            matches_model_train_dataset=dataset_sha256 == self.train_dataset_sha256,
            comparative_attempts=len(rows),
            unit_curriculum_attempts=len(curriculum),
            settled_examples=len(settled),
            censored_examples=len(rows) + len(curriculum) - len(settled),
            successful_examples=sum(row.outcome.verified_success is True for row in settled),
            unsuccessful_examples=sum(row.outcome.verified_success is False for row in settled),
            comparative_outcomes_by_kind=by_kind,
            unit_curriculum_outcomes_by_kind=unit_by_kind,
            features=[
                dict(
                    feature=name,
                    nonzero_examples=int(np.count_nonzero(vectors[:, i])),
                    minimum=float(vectors[:, i].min()),
                    maximum=float(vectors[:, i].max()),
                    variance=float(vectors[:, i].var()),
                    distinct_values=len(set(vectors[:, i].tolist())),
                    weighted=bool(np.any(self.coefficients[i] != 0)),
                )
                for i, name in enumerate(names)
            ],
            in_sample_mean_squared_error=dict(
                zip(
                    LIVING_DEX_OPTION_OUTCOME_NAMES,
                    ((predicted - targets) ** 2).mean(axis=0).tolist(),
                    strict=True,
                )
            ),
            clipped_example_counts=dict(
                zip(
                    LIVING_DEX_OPTION_OUTCOME_NAMES,
                    ((raw < 0) | (raw > 1)).sum(axis=0).tolist(),
                    strict=True,
                )
            ),
            in_sample_errors_are_not_unseen_performance=True,
        )
        if self.bounded_story_success_head is not None:
            coverage["weighted_feature_scope"] = "base_linear_parameters_only"
            head = self.bounded_story_success_head
            head_indices = (head.feature_indices if isinstance(head, LivingDexBoundedMatchupStorySuccessHead)
                            else tuple(range(len(head.coefficients))))
            weighted_head_indices = {i for i, coefficient in zip(head_indices, head.coefficients, strict=True) if coefficient != 0.}
            for i, feature in enumerate(coverage["features"]):
                feature["bounded_story_head_weighted"] = i in weighted_head_indices
        return coverage

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "censored_examples": self.censored_examples,
            "coefficients": self.coefficients.tolist(),
            "feature_mean": self.feature_mean.tolist(),
            "feature_names": list(option_feature_names(self.feature_version)),
            "feature_scale": self.feature_scale.tolist(),
            "intercept": self.intercept.tolist(),
            "maximum_importance_weight": self.maximum_importance_weight,
            "normalization": (
                LIVING_DEX_OPTION_NORMALIZATION
                if self.feature_version == 1
                else f"pokemon.core.living-dex-option-normalization.v{self.feature_version}"
            ),
            "objective": self.objective,
            "outcome_names": list(LIVING_DEX_OPTION_OUTCOME_NAMES),
            "ridge": self.ridge,
            "schema": (
                LIVING_DEX_OPTION_MODEL_SCHEMA
                if self.feature_version == 1
                else f"pokemon.core.living-dex-option-value-model.v{self.feature_version}"
            ),
            "settled_examples": self.settled_examples,
            "train_dataset_sha256": self.train_dataset_sha256,
        }
        if self.economy_head is not None:
            result["economy_head"] = self.economy_head.to_dict()
        if self.bounded_story_success_head is not None:
            result["bounded_story_success_head"] = self.bounded_story_success_head.to_dict()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> LivingDexOptionValueModel:
        if not isinstance(value, Mapping):
            raise LivingDexOptionValueError("living-Dex model document differs")
        version = next(
            (
                v
                for v in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
                if value.get("schema") == f"pokemon.core.living-dex-option-value-model.v{v}"
            ),
            1,
        )
        has_economy_head = "economy_head" in value
        if has_economy_head and version not in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
            raise LivingDexOptionValueError(
                "only feature_version 4 through 15 can carry an economy head"
            )
        expected_keys = {
            "censored_examples",
            "coefficients",
            "feature_mean",
            "feature_names",
            "feature_scale",
            "intercept",
            "maximum_importance_weight",
            "normalization",
            "objective",
            "outcome_names",
            "ridge",
            "schema",
            "settled_examples",
            "train_dataset_sha256",
        }
        if has_economy_head:
            expected_keys = expected_keys | {"economy_head"}
        if "bounded_story_success_head" in value:
            expected_keys = expected_keys | {"bounded_story_success_head"}
        if set(value) != expected_keys:
            raise LivingDexOptionValueError("living-Dex model document differs")
        feature_names = value.get("feature_names")
        outcome_names = value.get("outcome_names")
        train_dataset_sha256 = value.get("train_dataset_sha256")
        settled_examples = value.get("settled_examples")
        censored_examples = value.get("censored_examples")
        ridge = value.get("ridge")
        maximum_importance_weight = value.get("maximum_importance_weight")
        if (
            value.get("schema")
            != (
                LIVING_DEX_OPTION_MODEL_SCHEMA
                if version == 1
                else f"pokemon.core.living-dex-option-value-model.v{version}"
            )
            or value.get("objective")
            not in {
                LIVING_DEX_OPTION_OBJECTIVE,
                "selected-arm-ips-plus-unit-curriculum-multioutcome-ridge-v1",
                *_RETAINED_HEAD_OBJECTIVES,
            }
            or value.get("normalization")
            != (
                LIVING_DEX_OPTION_NORMALIZATION
                if version == 1
                else f"pokemon.core.living-dex-option-normalization.v{version}"
            )
            or not isinstance(feature_names, list)
            or tuple(feature_names) != option_feature_names(version)
            or not isinstance(outcome_names, list)
            or tuple(outcome_names) != LIVING_DEX_OPTION_OUTCOME_NAMES
            or not isinstance(train_dataset_sha256, str)
            or type(settled_examples) is not int  # noqa: E721
            or type(censored_examples) is not int  # noqa: E721
            or isinstance(ridge, bool)
            or not isinstance(ridge, (int, float))
            or isinstance(maximum_importance_weight, bool)
            or not isinstance(maximum_importance_weight, (int, float))
        ):
            raise LivingDexOptionValueError("living-Dex model schema differs")
        economy_head: LivingDexEconomyHead | None = None
        if has_economy_head:
            economy_head_val = value.get("economy_head")
            if not isinstance(economy_head_val, Mapping):
                raise LivingDexOptionValueError("living-Dex economy head document differs")
            economy_head = LivingDexEconomyHead.from_dict(economy_head_val)
            if (value.get("objective") not in _RETAINED_HEAD_OBJECTIVES
                    and economy_head.qualified_examples > cast(int, settled_examples)):
                raise LivingDexOptionValueError(
                    "living-Dex economy head qualified examples exceed settled examples"
                )
        try:
            return cls(
                coefficients=np.asarray(value["coefficients"], dtype=np.float64),
                intercept=np.asarray(value["intercept"], dtype=np.float64),
                feature_mean=np.asarray(value["feature_mean"], dtype=np.float64),
                feature_scale=np.asarray(value["feature_scale"], dtype=np.float64),
                train_dataset_sha256=train_dataset_sha256,
                settled_examples=settled_examples,
                censored_examples=censored_examples,
                ridge=float(ridge),
                maximum_importance_weight=float(maximum_importance_weight),
                feature_version=version,
                objective=str(value["objective"]),
                economy_head=economy_head,
                bounded_story_success_head=(_restore_bounded_story_success_head(value["bounded_story_success_head"])
                    if "bounded_story_success_head" in value else None),
            )
        except (KeyError, TypeError, ValueError):
            raise LivingDexOptionValueError("living-Dex model document is invalid") from None


@dataclass(frozen=True, slots=True)
class LivingDexOptionValueFitReport:
    train_dataset_sha256: str
    total_examples: int
    settled_examples: int
    censored_examples: int
    successful_examples: int
    distinct_selected_feature_rows: int
    weighted_mse_before: float
    weighted_mse_after: float
    feature_version: int = 1
    objective: str = LIVING_DEX_OPTION_OBJECTIVE
    economy_qualified_examples: int | None = None
    frozen_parent_model_sha256: str | None = None
    complete_paid_success_basis: CompletePaidSuccessBasis | None = None
    complete_paid_settled_examples: int | None = None
    complete_paid_distinct_horizons: int | None = None
    complete_paid_distinct_uncertainties: int | None = None
    complete_paid_design_rank: int | None = None
    party_cost_weighted_mse_before: float | None = None
    party_cost_weighted_mse_after: float | None = None
    party_cost_retention: Mapping[str, object] | None = None
    story_success_retention: Mapping[str, object] | None = None
    bounded_story_success_retention: Mapping[str, object] | None = None

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "censored_examples": self.censored_examples,
            "counterfactual_targets": 0,
            "distinct_selected_feature_rows": self.distinct_selected_feature_rows,
            "objective": self.objective,
            "outcome_balance_required": False,
            "schema": LIVING_DEX_OPTION_FIT_SCHEMA,
            "settled_examples": self.settled_examples,
            "successful_examples": self.successful_examples,
            "total_examples": self.total_examples,
            "train_dataset_sha256": self.train_dataset_sha256,
            "unselected_action_targets": 0,
            "weighted_mse_after": self.weighted_mse_after,
            "weighted_mse_before": self.weighted_mse_before,
        }
        if self.feature_version >= 2:
            result["feature_version"] = self.feature_version
            result["missing_history"] = "unknown_not_unattempted"
        if self.economy_qualified_examples is not None and self.economy_qualified_examples > 0:
            result["economy_qualified_examples"] = self.economy_qualified_examples
        if self.frozen_parent_model_sha256 is not None:
            party_only = self.objective in _PARTY_COST_RESIDUAL_OBJECTIVES
            result.update(frozen_parent_model_sha256=self.frozen_parent_model_sha256,
                          fitted_outcome_names=["party_cost" if party_only else "verified_success"],
                          normalization_retained=True, economy_head_retained=True,
                          outcome_balance_required=not party_only)
            if party_only:
                result.update(party_cost_weighted_mse_before=self.party_cost_weighted_mse_before,
                              party_cost_weighted_mse_after=self.party_cost_weighted_mse_after)
        if self.party_cost_retention is not None:
            result["party_cost_retention"] = dict(self.party_cost_retention)
        if self.story_success_retention is not None:
            result["story_success_retention"] = dict(self.story_success_retention)
        if self.bounded_story_success_retention is not None:
            result["bounded_story_success_retention"] = dict(self.bounded_story_success_retention)
        if self.complete_paid_success_basis is not None:
            result.update(
                complete_paid_success_basis=self.complete_paid_success_basis.value,
                complete_paid_settled_examples=self.complete_paid_settled_examples,
                complete_paid_distinct_horizons=self.complete_paid_distinct_horizons,
                global_intercept_retained=True, parent_feature_coefficients_retained=True,
                scope_gate="known-acquire-paid-finite-search-complete",
            )
        if self.complete_paid_distinct_uncertainties is not None:
            result.update(complete_paid_distinct_uncertainties=self.complete_paid_distinct_uncertainties,
                          complete_paid_design_rank=self.complete_paid_design_rank)
        return result


@dataclass(frozen=True, slots=True)
class LivingDexOptionValueFit:
    model: LivingDexOptionValueModel
    report: LivingDexOptionValueFitReport


@dataclass(frozen=True, slots=True)
class LivingDexOptionValueEvaluation:
    partition: str
    total_examples: int
    settled_examples: int
    censored_examples: int
    weighted_mse: float
    per_outcome_weighted_mse: tuple[float, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "censored_examples": self.censored_examples,
            "counterfactual_targets": 0,
            "outcome_names": list(LIVING_DEX_OPTION_OUTCOME_NAMES),
            "partition": self.partition,
            "per_outcome_weighted_mse": list(self.per_outcome_weighted_mse),
            "schema": LIVING_DEX_OPTION_EVALUATION_SCHEMA,
            "settled_examples": self.settled_examples,
            "total_examples": self.total_examples,
            "unselected_action_targets": 0,
            "weighted_mse": self.weighted_mse,
        }


def uniform_behavior_probabilities(menu: LivingDexOptionMenu) -> tuple[float, ...]:
    """Return a full-support uniform exploration distribution over legal options."""

    if not isinstance(menu, LivingDexOptionMenu):
        raise TypeError("menu must be a LivingDexOptionMenu")
    probability = 1.0 / len(menu.available_indices)
    return tuple(
        probability if index in menu.available_indices else 0.0
        for index in range(len(menu.candidates))
    )


def upgrade_option_value_model_for_search_history(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Zero-pad a retained model, without fitting or claiming learned history.

    This bootstrap permits prospective collection of history-bearing experience.
    All old predictions, training identity and counts remain unchanged. History
    effects become learned only through a subsequent observed-outcome fit.
    """
    if model.feature_version >= 2:
        return model
    width = len(LIVING_DEX_HISTORY_FEATURE_NAMES)
    return replace(
        model,
        feature_version=2,
        coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
        feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
        feature_scale=np.concatenate((model.feature_scale, np.ones(width))),
    )


def upgrade_option_value_model_for_optional_recovery(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Initialize recovery columns without new outcomes or claimed competence."""
    if model.feature_version >= 3:
        return model
    model = upgrade_option_value_model_for_search_history(model)
    return replace(
        model,
        feature_version=3,
        coefficients=np.vstack((model.coefficients, np.zeros((2, len(model.intercept))))),
        feature_mean=np.concatenate((model.feature_mean, np.zeros(2))),
        feature_scale=np.concatenate((model.feature_scale, np.ones(2))),
    )


def upgrade_option_value_model_for_economy(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Initialize economy columns without new outcomes or claimed competence.

    No historical predictions, targets, training identity, or counts change.
    """
    if model.feature_version >= 4:
        return model
    model = upgrade_option_value_model_for_optional_recovery(model)
    width = len(ECONOMY_FEATURE_NAMES)
    return replace(
        model,
        feature_version=4,
        coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
        feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
        feature_scale=np.concatenate((model.feature_scale, np.ones(width))),
    )


def upgrade_option_value_model_for_readiness(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Append unknown readiness with zero influence; retain every prior prediction."""
    model = upgrade_option_value_model_for_economy(model)
    if model.feature_version >= 5:
        return model
    width = len(option_feature_names(5)) - len(option_feature_names(4))
    return replace(
        model,
        feature_version=5,
        coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
        feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
        feature_scale=np.concatenate((model.feature_scale, np.ones(width))),
    )


def upgrade_option_value_model_for_challenge(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Zero-influence compatibility bridge, not trained challenge understanding."""
    model = upgrade_option_value_model_for_readiness(model)
    if model.feature_version >= 6:
        return model
    width = len(option_feature_names(6)) - len(option_feature_names(5))
    return replace(
        model,
        feature_version=6,
        coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
        feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
        feature_scale=np.concatenate((model.feature_scale, np.ones(width))),
    )


def upgrade_option_value_model_for_preparation(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Append zero-influence member facts, not trained preparation understanding."""
    model = upgrade_option_value_model_for_challenge(model)
    if model.feature_version >= 7:
        return model
    width = len(option_feature_names(7)) - len(option_feature_names(6))
    return replace(
        model,
        feature_version=7,
        coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
        feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
        feature_scale=np.concatenate((model.feature_scale, np.ones(width))),
    )



def upgrade_option_value_model_for_kind_effort(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Append zero influence; this compatibility bridge is not fitted learning."""
    model = upgrade_option_value_model_for_preparation(model)
    if model.feature_version >= 8:
        return model
    width = len(kind_execution_effort_feature_names())
    return replace(
        model,
        feature_version=8,
        coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
        feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
        feature_scale=np.concatenate((model.feature_scale, np.ones(width))),
    )


def upgrade_option_value_model_for_level_workload(model: LivingDexOptionValueModel) -> LivingDexOptionValueModel:
    """Append zero influence; compatibility is not fitted learning."""
    model = upgrade_option_value_model_for_kind_effort(model)
    if model.feature_version >= 9:
        return model
    width = len(level_workload_feature_names())
    return replace(model, feature_version=9,
                   coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
                   feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
                   feature_scale=np.concatenate((model.feature_scale, np.ones(width))))


def upgrade_option_value_model_for_move_change(model: LivingDexOptionValueModel) -> LivingDexOptionValueModel:
    """Append zero influence; preserve predictions, counts and all prior evidence."""
    model = upgrade_option_value_model_for_level_workload(model)
    if model.feature_version >= 10:
        return model
    width = len(move_change_feature_names())
    return replace(model, feature_version=10,
                   coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
                   feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
                   feature_scale=np.concatenate((model.feature_scale, np.ones(width))))


def project_move_context_features(features: tuple[float, ...]) -> tuple[float, ...]:
    """Append V11 products from a recorded V10 vector; preserve its exact prefix."""
    if len(features) != len(option_feature_names(10)):
        raise LivingDexOptionValueError("move context projection requires an exact V10 vector")
    return (*features, *move_context_from_v10(features[-len(move_change_feature_names()):]))


def upgrade_option_value_model_for_move_context(model: LivingDexOptionValueModel) -> LivingDexOptionValueModel:
    """Append zero influence without changing earlier predictions or evidence."""
    model = upgrade_option_value_model_for_move_change(model)
    if model.feature_version >= 11:
        return model
    width = len(move_context_feature_names())
    return replace(model, feature_version=11,
                   coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
                   feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
                   feature_scale=np.concatenate((model.feature_scale, np.ones(width))))


def upgrade_option_value_model_for_capture_invocation(model: LivingDexOptionValueModel) -> LivingDexOptionValueModel:
    """Explicit zero-influence projection; it does not fit or promote a model."""
    model = upgrade_option_value_model_for_move_context(model)
    if model.feature_version >= 12:
        return model
    width = len(capture_invocation_feature_names())
    return replace(model, feature_version=12,
                   coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
                   feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
                   feature_scale=np.concatenate((model.feature_scale, np.ones(width))))


def upgrade_option_value_model_for_complete_paid_capture(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Explicit derived-feature extension; no fitting or adoption."""
    model = upgrade_option_value_model_for_capture_invocation(model)
    if model.feature_version >= 13:
        return model
    width = len(complete_paid_capture_feature_names())
    return replace(model, feature_version=13,
                   coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
                   feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
                   feature_scale=np.concatenate((model.feature_scale, np.ones(width))))



def upgrade_option_value_model_for_complete_paid_density(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Append zero density influence while retaining every V13 parameter."""
    model = upgrade_option_value_model_for_complete_paid_capture(model)
    if model.feature_version >= 14:
        return model
    width = len(complete_paid_density_feature_names())
    return replace(model, feature_version=14,
                   coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
                   feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
                   feature_scale=np.concatenate((model.feature_scale, np.ones(width))))


def upgrade_option_value_model_for_matchup(
    model: LivingDexOptionValueModel,
) -> LivingDexOptionValueModel:
    """Append zero observation influence; never merge a bounded correction head."""
    if not isinstance(model, LivingDexOptionValueModel):
        raise TypeError("model must be a LivingDexOptionValueModel")
    if isinstance(model.bounded_story_success_head, LivingDexBoundedMatchupStorySuccessHead) and model.feature_version == 15:
        return model
    if model.bounded_story_success_head is not None:
        raise LivingDexOptionValueError("bounded story head has no V15 compatibility proof")
    model = upgrade_option_value_model_for_complete_paid_density(model)
    if model.feature_version == 15:
        return model
    width = len(matchup_feature_names())
    return replace(model, feature_version=15,
                   coefficients=np.vstack((model.coefficients, np.zeros((width, len(model.intercept))))),
                   feature_mean=np.concatenate((model.feature_mean, np.zeros(width))),
                   feature_scale=np.concatenate((model.feature_scale, np.ones(width))))


def curriculum_features(row: LivingDexCurriculumOutcomeExample, version: int) -> tuple[float, ...]:
    """Project old rows while preserving original evidence and unknown fields.

    V8 products derive only from original kind and execution-effort columns.
    Dataset fingerprints still hash the originals, never this explicit view.
    """
    option_feature_names(version)
    if version == 15:
        if row.feature_version > 15:
            raise LivingDexOptionValueError("curriculum feature version differs from fitter")
        if row.feature_version == 15:
            prefix = len(option_feature_names(14))
            return project_matchup_features(row.features[:prefix], _matchup_from_vector(row.features[prefix:]))
        # No old matchup observations are manufactured from outcomes or identities.
        return project_matchup_features(curriculum_features(row, 14), None)
    if version == 14:
        prefix = len(option_feature_names(13))
        if row.feature_version > 14:
            raise LivingDexOptionValueError("curriculum feature version differs from fitter")
        original = row.features[:prefix] if row.feature_version == 14 else curriculum_features(row, 13)
        projected = project_complete_paid_density_features(original)
        if row.feature_version == 14 and row.features != projected:
            raise LivingDexOptionValueError("complete-paid density suffix differs from its V13 input")
        return projected
    if version == 13:
        prefix = len(option_feature_names(12))
        if row.feature_version > 13:
            raise LivingDexOptionValueError("curriculum feature version differs from fitter")
        original = row.features[:prefix] if row.feature_version == 13 else curriculum_features(row, 12)
        projected = project_complete_paid_capture_features(original)
        if row.feature_version == 13 and row.features != projected:
            raise LivingDexOptionValueError("complete-paid suffix differs from its V12 input")
        return projected
    if row.feature_version == version:
        return row.features
    if version == 12 and row.feature_version < 12:
        # Historical invocation was not observed. Never reconstruct it from outcomes.
        return (*curriculum_features(row, 11), *capture_invocation_vector(None))
    if version == 11 and row.feature_version < 11:
        return project_move_context_features(curriculum_features(row, 10))
    if version == 10 and row.feature_version < 10:
        # No historical move facts are reconstructed from labels or identities.
        return (*curriculum_features(row, 9), *((0.0,) * len(move_change_feature_names())))
    if version == 9 and row.feature_version < 9:
        # Historical XP was not recorded. Keep it unknown, never reconstruct labels.
        return (*curriculum_features(row, 8), *((0.0,) * len(level_workload_feature_names())))
    if version == 8 and row.feature_version < 8:
        historical = (
            *row.features,
            *((0.0,) * (len(option_feature_names(7)) - len(row.features))),
        )
        return (*historical, *_kind_execution_effort_from_original(
            row.features, row.feature_version,
        ))
    if version in (5, 6, 7) and row.feature_version < version:
        return (*row.features, *((0.0,) * (len(option_feature_names(version)) - len(row.features))))
    raise LivingDexOptionValueError("curriculum feature version differs from fitter")


def living_dex_option_train_dataset_sha256(
    examples: Iterable[LivingDexObservedArmExample],
    *,
    curriculum_examples: Iterable[LivingDexCurriculumOutcomeExample] = (),
) -> str:
    """Return the order-independent identity used by the option-value fitter.

    The helper validates the same complete train denominator as the fitter.  It
    exists so a claim-before-fit publisher can bind the exact dataset before it
    invokes the learner without reimplementing the fit's identity contract.
    """

    rows = tuple(
        sorted(
            _validated_examples(examples, expected_partition="train", allow_empty=True),
            key=lambda row: row.decision_sha256,
        )
    )
    curriculum = _validated_curriculum(curriculum_examples, rows)
    if not rows and not curriculum:
        raise LivingDexOptionValueError("living-Dex option evidence is empty")
    if curriculum:
        return canonical_sha256(
            {
                "schema": "pokemon.core.living-dex-mixed-outcome-train-dataset.v1",
                "choices": [row.public_dict() for row in rows],
                "curriculum": [row.public_dict() for row in curriculum],
                "curriculum_regression_weight": 1.0,
            }
        )
    return canonical_sha256(
        {
            "rows": [row.public_dict() for row in rows],
            "schema": "pokemon.core.living-dex-option-train-dataset.v1",
        }
    )


def _fit_level_workload_cost_residuals(features, targets, weights, base, ridge):
    """Fit cost residuals while retaining the existing seven other heads.

    The residual design is zero for unknown workloads. A V9 warm start retains
    its learned costs and normalization; centered workload features receive an
    intercept correction so unknown-workload forecasts remain unchanged.
    """
    if not isinstance(base, LivingDexOptionValueModel) or base.feature_version > 9:
        raise LivingDexOptionValueError("workload cost retention requires a supported baseline")
    baseline = upgrade_option_value_model_for_level_workload(base)
    prefix = len(option_feature_names(8))
    new = features[:, prefix:]
    present = new[:, 0] == 1.
    if (np.count_nonzero(present) < 2
            or len({tuple(row) for row in new[present]}) < 2):
        raise LivingDexOptionValueError("workload cost fit needs distinct observed TRAIN workloads")
    if np.any(new[~present] != 0.):
        raise LivingDexOptionValueError("unknown workload rows must have no inferred measurements")
    mean = baseline.feature_mean.copy()
    scale = baseline.feature_scale.copy()
    if base.feature_version < 9:
        scale_new = np.sqrt(np.average(new[present] ** 2, axis=0, weights=weights[present]))
        scale_new[scale_new == 0.] = 1.
        mean[prefix:] = 0.
        scale[prefix:] = scale_new
    else:
        scale_new = scale[prefix:]
    design = new / scale_new
    raw_before = baseline.intercept + ((features - baseline.feature_mean) / baseline.feature_scale) @ baseline.coefficients
    cost_columns = tuple(LIVING_DEX_OPTION_OUTCOME_NAMES.index(name)
                         for name in ("action_cost", "frame_cost"))
    residual = targets[:, cost_columns] - raw_before[:, cost_columns]
    left = design.T @ (design * weights[:, np.newaxis]) + ridge * np.eye(design.shape[1])
    right = design.T @ (weights[:, np.newaxis] * residual)
    try:
        fitted = np.linalg.solve(left, right)
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError("workload cost Ridge fit is singular") from None
    coefficients = baseline.coefficients.copy()
    intercept = baseline.intercept.copy()
    for column, outcome in enumerate(cost_columns):
        coefficients[prefix:, outcome] += fitted[:, column]
        intercept[outcome] += (mean[prefix:] / scale_new) @ fitted[:, column]
    predictions = np.clip(intercept + ((features - mean) / scale) @ coefficients, 0., 1.)
    before = _weighted_mse(targets, np.clip(raw_before, 0., 1.), weights)
    after = _weighted_mse(targets, predictions, weights)
    return mean, scale, intercept, coefficients, before, after


def _fit_success_residuals(features, targets, weights, base, ridge):
    """Retain bounded success regression and its observed class-balance guard."""
    column = LIVING_DEX_OPTION_OUTCOME_NAMES.index("verified_success")
    if set(targets[:, column]) != {0., 1.}:
        raise LivingDexOptionValueError("success residual fit needs observed TRAIN successes and failures")
    return _fit_single_outcome_residuals(features, targets, weights, base, ridge, "verified_success")


def _fit_single_outcome_residuals(features, targets, weights, base, ridge, outcome_name):
    """Fit one measured outcome; every other learned coordinate stays exact."""
    column = LIVING_DEX_OPTION_OUTCOME_NAMES.index(outcome_name)
    mean, scale = base.feature_mean.copy(), base.feature_scale.copy()
    normalized = (features - mean) / scale
    design = np.column_stack((np.ones(len(features), dtype=np.float64), normalized))
    raw_before = base.intercept + normalized @ base.coefficients
    residual = targets[:, column] - raw_before[:, column]
    penalty = np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = 0.
    left = design.T @ (design * weights[:, np.newaxis]) + ridge * penalty
    right = design.T @ (weights * residual)
    try:
        fitted = np.linalg.solve(left, right)
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError(f"{outcome_name} residual Ridge fit is singular") from None
    coefficients, intercept = base.coefficients.copy(), base.intercept.copy()
    intercept[column] += fitted[0]
    coefficients[:, column] += fitted[1:]
    predictions = np.clip(intercept + normalized @ coefficients, 0., 1.)
    before = _weighted_mse(targets, np.clip(raw_before, 0., 1.), weights)
    after = _weighted_mse(targets, predictions, weights)
    return mean, scale, intercept, coefficients, before, after


def _fit_party_cost_with_retained_outputs(
    features, targets, weights, base, ridge, protected_indices, protected_ids,
):
    # Preserve the original unrestricted party solver and its report exactly.
    return _fit_outcome_with_retained_outputs(
        features, targets, weights, base, ridge, protected_indices, protected_ids)


def _story_success_feature_columns(features, version):
    """Fixed complete semantic group; reject forged raw curriculum gates."""
    names = option_feature_names(version)
    if (version != 9 or features.ndim != 2 or features.shape[1] != len(names)
            or not np.all(np.isfinite(features))):
        raise LivingDexOptionValueError("story success requires finite V9 inputs")
    kind_columns = tuple(names.index(f"kind.{kind.value}") for kind in LivingDexOptionKind)
    kinds = features[:, kind_columns]
    if np.any((kinds != 0.) & (kinds != 1.)) or np.any(kinds.sum(axis=1) != 1.):
        raise LivingDexOptionValueError("story success requires one-hot option kinds")
    for k, kind in enumerate(LivingDexOptionKind):
        off_kind = kinds[:, k] == 0.
        context = tuple(i for i, name in enumerate(names) if name.startswith((
            f"readiness.{kind.value}_x_", f"challenge.{kind.value}_x_")))
        if np.any(features[off_kind][:, context] != 0.):
            raise LivingDexOptionValueError("story success context escapes its option kind")
        effort = names.index(f"execution_effort_x_kind.{kind.value}")
        if not np.array_equal(features[:, effort], features[:, names.index("execution_effort")] * kinds[:, k]):
            raise LivingDexOptionValueError("story success effort interaction differs")
        known = features[:, names.index(f"readiness.{kind.value}_x_current.pp_known")]
        fraction = features[:, names.index(f"readiness.{kind.value}_x_current.pp_fraction")]
        if np.any((known != 0.) & (known != 1.)) or np.any((fraction < 0.) | (fraction > 1.)) or np.any(fraction[known == 0.] != 0.):
            raise LivingDexOptionValueError("story success cannot invent unknown PP")
    columns = tuple(i for i, name in enumerate(names) if name in (
        "kind.unlock_access", "execution_effort_x_kind.unlock_access") or name.startswith((
        "readiness.unlock_access_x_", "challenge.unlock_access_x_")))
    if len(columns) != 36:
        raise LivingDexOptionValueError("complete story feature group differs")
    return columns


def _fit_story_success_with_retained_outputs(
    features, targets, weights, base, ridge, protected_indices, protected_ids,
):
    columns = _story_success_feature_columns(features, base.feature_version)
    story = features[:, option_feature_names(9).index("kind.unlock_access")] == 1.
    if not np.all(story[np.asarray(protected_indices, dtype=int)]):
        raise LivingDexOptionValueError("story success anchors must be settled story rows")
    success = LIVING_DEX_OPTION_OUTCOME_NAMES.index("verified_success")
    if set(targets[story, success]) != {0., 1.}:
        raise LivingDexOptionValueError("story success needs observed TRAIN story successes and failures")
    result = _fit_outcome_with_retained_outputs(
        features, targets, weights, base, ridge, protected_indices, protected_ids,
        outcome_name="verified_success", feature_columns=columns)
    mean, scale, intercept, coefficients, before, after, metadata = result
    normalized = (features - mean) / scale
    old = base.intercept + normalized @ base.coefficients
    new = intercept + normalized @ coefficients
    error = float(np.max(np.abs(new[~story, success] - old[~story, success]))) if np.any(~story) else 0.
    if not math.isfinite(error) or error > _PARTY_COST_RETENTION_ABSOLUTE_TOLERANCE:
        raise LivingDexOptionValueError("story success nonstory raw-output tolerance exceeded")
    metadata.update(nonstory_rows=int(np.count_nonzero(~story)), story_rows=int(np.count_nonzero(story)),
        maximum_nonstory_raw_output_error=error, nonstory_raw_output_absolute_tolerance=_PARTY_COST_RETENTION_ABSOLUTE_TOLERANCE,
        all_other_outcomes_retained=True, nonstory_retention="algebraic plus numerical tolerance, not bitwise")
    return mean, scale, intercept, coefficients, before, after, metadata


def _fit_outcome_with_retained_outputs(
    features, targets, weights, base, ridge, protected_indices, protected_ids,
    *, outcome_name="party_cost", feature_columns=None,
):
    """Minimize the existing residual objective subject to retained raw outputs.

    SVD is used only to represent the nullspace of the protected input design.
    The original coefficient penalty is transformed into that basis; the global
    intercept remains unpenalized. No source identity enters a model feature.
    """
    column = LIVING_DEX_OPTION_OUTCOME_NAMES.index(outcome_name)
    subject = "party cost" if outcome_name == "party_cost" else "story success"
    mean, scale = base.feature_mean.copy(), base.feature_scale.copy()
    normalized = (features - mean) / scale
    design = np.column_stack((np.ones(len(features), dtype=np.float64), normalized))
    transform = None
    if feature_columns is not None:
        selected = np.asarray(feature_columns, dtype=int)
        transform = np.zeros((design.shape[1], len(selected)), dtype=np.float64)
        transform[0] = mean[selected] / scale[selected]
        transform[selected + 1, np.arange(len(selected))] = 1.
        # Raw gated inputs are exactly zero off-kind; never center them here.
        design = features[:, selected] / scale[selected]
    protected = design[np.asarray(protected_indices, dtype=int)]
    raw_before = base.intercept + normalized @ base.coefficients
    try:
        _, singular, right = np.linalg.svd(
            protected, full_matrices=protected.shape[0] < protected.shape[1])
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError(f"{subject} retention SVD did not converge") from None
    tolerance = float(max(protected.shape) * np.finfo(np.float64).eps * singular[0])
    rank = int(np.count_nonzero(singular > tolerance))
    basis = right[rank:].T
    projected = design @ basis
    projected_tolerance = float(
        max(design.shape) * np.finfo(np.float64).eps * max(1., np.linalg.norm(design)))
    try:
        projected_singular = np.linalg.svd(projected, compute_uv=False)
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError(f"{subject} projected SVD did not converge") from None
    projected_rank = int(np.count_nonzero(projected_singular > projected_tolerance))
    correction = np.zeros(design.shape[1], dtype=np.float64)
    if projected_rank:
        residual = targets[:, column] - raw_before[:, column]
        # P = diag(0, 1, ...): use Z.T @ P @ Z, never identity in reduced space.
        parameter_basis = basis if transform is None else transform @ basis
        penalty = parameter_basis[1:].T @ parameter_basis[1:]
        left = projected.T @ (projected * weights[:, None]) + ridge * penalty
        right_target = projected.T @ (weights * residual)
        try:
            correction = basis @ np.linalg.solve(left, right_target)
        except np.linalg.LinAlgError:
            raise LivingDexOptionValueError(f"retained {subject} Ridge fit is singular") from None
    if not np.all(np.isfinite(correction)):
        raise LivingDexOptionValueError(f"retained {subject} correction is nonfinite")
    coefficients, intercept = base.coefficients.copy(), base.intercept.copy()
    parameter_correction = correction if transform is None else transform @ correction
    intercept[column] += parameter_correction[0]
    coefficients[:, column] += parameter_correction[1:]
    raw_after = intercept + normalized @ coefficients
    maximum_error = float(np.max(np.abs(
        raw_after[np.asarray(protected_indices), column]
        - raw_before[np.asarray(protected_indices), column])))
    if not math.isfinite(maximum_error) or maximum_error > _PARTY_COST_RETENTION_ABSOLUTE_TOLERANCE:
        raise LivingDexOptionValueError(f"retained {subject} raw-output tolerance exceeded")
    metadata = {
        "protected_count": len(protected_ids),
        "protected_decision_sha256": canonical_sha256({
            "schema": ("pokemon.core.party-cost-retained-decisions.v1"
                       if outcome_name == "party_cost" else
                       "pokemon.core.story-success-retained-decisions.v1"),
            "decision_sha256s": sorted(protected_ids),
        }),
        "design_rank": rank,
        "design_columns": design.shape[1],
        "nullspace_dimension": basis.shape[1],
        "svd_absolute_tolerance": tolerance,
        "svd_tolerance_rule": "max(protected.shape) * float64_epsilon * largest_singular_value",
        "projected_design_rank": projected_rank,
        "projected_absolute_tolerance": projected_tolerance,
        "projected_tolerance_rule": "max(design.shape) * float64_epsilon * max(1, frobenius_norm(design))",
        "projected_largest_singular_value": float(projected_singular[0]) if len(projected_singular) else 0.,
        "projected_smallest_retained_singular_value": float(projected_singular[projected_rank - 1]) if projected_rank else None,
        "projected_condition_number": float(projected_singular[0] / projected_singular[projected_rank - 1]) if projected_rank else None,
        "maximum_raw_output_error": maximum_error,
        "raw_output_absolute_tolerance": _PARTY_COST_RETENTION_ABSOLUTE_TOLERANCE,
        "correction_l2_norm": float(np.linalg.norm(correction)),
        "intercept_penalized": False,
        "scope": "Retained TRAIN input outputs only; not a generalization or policy-quality guarantee.",
    }
    if feature_columns is not None:
        metadata.update(feature_group=_STORY_SUCCESS_FEATURE_GROUP,
            trainable_feature_indices=list(feature_columns),
            trainable_feature_names=[option_feature_names(base.feature_version)[i] for i in feature_columns],
            independent_global_intercept=False, intercept_compensation="sum(mean/scale * coefficient_delta)",
            parameter_correction_l2_norm=float(np.linalg.norm(parameter_correction)))
    return (mean, scale, intercept, coefficients,
            _weighted_mse(targets, np.clip(raw_before, 0., 1.), weights),
            _weighted_mse(targets, np.clip(raw_after, 0., 1.), weights), metadata)


def _fit_complete_paid_success_residuals(features, targets, weights, base, ridge, basis):
    """Fit only declared local success coordinates, anchored to raw V12 outputs."""
    version = complete_paid_success_version(basis)
    baseline = (upgrade_option_value_model_for_complete_paid_density(base) if version == 14
                else upgrade_option_value_model_for_complete_paid_capture(base))
    prefix = len(option_feature_names(12))
    column = LIVING_DEX_OPTION_OUTCOME_NAMES.index("verified_success")
    new = features[:, prefix:]
    # Also validates an already-V13 row; finite-width curriculum alone is not proof.
    raw_before = baseline.raw_predictions(features)
    active = new[:, 0] == 1.
    if np.count_nonzero(active) < 2 or set(targets[active, column]) != {0., 1.}:
        raise LivingDexOptionValueError(
            "complete-paid fit needs gate-positive TRAIN successes and failures")
    if (basis is CompletePaidSuccessBasis.HORIZON
            and len(set(new[active, 1])) < 2):
        raise LivingDexOptionValueError("complete-paid horizon fit needs distinct horizons")
    columns = complete_paid_success_columns(basis)
    design = new[active][:, columns]
    width = len(columns)
    if version == 14:
        if len(set(new[active, 2])) < 2:
            raise LivingDexOptionValueError("complete-paid density fit needs distinct uncertainty inputs")
        if np.linalg.matrix_rank(design) != width:
            raise LivingDexOptionValueError("complete-paid density design lacks full declared rank")
    weighted = weights[active]
    residual = targets[active, column] - raw_before[active, column]
    left = design.T @ (design * weighted[:, None]) + ridge * np.eye(width)
    right = design.T @ (weighted * residual)
    try:
        fitted = np.linalg.solve(left, right)
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError("complete-paid residual Ridge fit is singular") from None
    coefficients = baseline.coefficients.copy()
    coefficients[np.asarray(columns) + prefix, column] = fitted
    raw_after = raw_before.copy()
    for start, stop in ((0, 2), (2, new.shape[1])):
        if start == stop:
            continue
        delta = new[:, start:stop] @ coefficients[prefix + start:prefix + stop, column]
        np.add(raw_after[:, column], delta, out=raw_after[:, column], where=delta != 0.)
    return (
        baseline.feature_mean.copy(), baseline.feature_scale.copy(),
        baseline.intercept.copy(), coefficients,
        _weighted_mse(targets, np.clip(raw_before, 0., 1.), weights),
        _weighted_mse(targets, np.clip(raw_after, 0., 1.), weights),
    )


def _fit_bounded_story_success(features, targets, weights, base, ridge, indices, ids):
    """Fit a separate full-context head in the exact anchor nullspace."""
    _story_success_feature_columns(features, 9)  # Existing typed context/PP guards.
    story = _bounded_story_mask(features)
    if (not all(story[i] for i in indices)
            or set(targets[story, 0].tolist()) != {0., 1.}):
        raise LivingDexOptionValueError("bounded story anchors/classes differ")
    design = np.column_stack((np.ones(len(features)),
                              (features - base.feature_mean) / base.feature_scale))
    design[~story] = 0.
    constraint = design[list(indices)]
    _, singular, vt = np.linalg.svd(constraint, full_matrices=True)
    tolerance = max(constraint.shape) * np.finfo(np.float64).eps * (singular[0] if len(singular) else 0.)
    rank = int(np.count_nonzero(singular > tolerance))
    null = vt[rank:].T
    if not null.shape[1]:
        raise LivingDexOptionValueError("bounded story anchors leave no correction space")
    projected = design @ null
    penalty = null[1:].T @ null[1:]  # The explicit head bias is unpenalized.
    raw = base.raw_predictions(features)
    bounded_base = np.clip(raw[:, 0], 0., 1.)
    residual = targets[:, 0] - bounded_base
    left = projected.T @ (weights[:, None] * projected) + ridge * penalty
    right = projected.T @ (weights * residual)
    try:
        parameters = null @ np.linalg.solve(left, right)
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError("bounded story correction fit is singular") from None
    head = LivingDexBoundedStorySuccessHead(parameters[1:], float(parameters[0]), base.model_sha256)
    delta = design @ parameters
    anchor_error = float(np.max(np.abs(delta[list(indices)])))
    if not np.all(np.isfinite(parameters)) or anchor_error > 1e-10:
        raise LivingDexOptionValueError("bounded story correction violated retained forecasts")
    after_raw = raw.copy()
    after_raw[story, 0] = bounded_base[story] + delta[story]
    before = _weighted_mse(targets, np.clip(raw, 0., 1.), weights)
    after = _weighted_mse(targets, np.clip(after_raw, 0., 1.), weights)
    report = dict(schema="pokemon.core.bounded-story-success-retention.v1",
        protected_count=len(indices), protected_decision_sha256=canonical_sha256(dict(
            schema="pokemon.core.bounded-story-success-retained-decisions.v1", decision_sha256s=sorted(ids))),
        protected_decision_sha256s=sorted(ids), maximum_bounded_forecast_error=anchor_error,
        feature_group="complete-v9-prefix-plus-bias", trainable_feature_indices=list(range(features.shape[1])),
        trainable_feature_names=list(option_feature_names(9)), bias_unpenalized=True,
        protected_design_rank=rank, projected_design_rank=int(np.linalg.matrix_rank(projected)),
        story_rows=int(story.sum()), nonstory_rows=int((~story).sum()),
        parent_raw_success_mse=float(np.average((raw[:, 0]-targets[:, 0])**2, weights=weights)),
        corrected_preclip_success_mse=float(np.average((after_raw[:, 0]-targets[:, 0])**2, weights=weights)),
        base_parameters_retained=True, target="observed_success_minus_bounded_parent_success",
        normalizer_retained=True, parent_model_sha256=base.model_sha256)
    return head, before, after, report


def _fit_bounded_matchup_story_success(features, targets, weights, base, ridge, indices, ids, decision_ids):
    """V15 correction: TRAIN-input normalization, no budget features or target tuning."""
    _story_success_feature_columns(features[:, :len(option_feature_names(9))], 9)
    raw = base.raw_predictions(features)  # Also authenticates all V15 input contracts.
    story = _bounded_story_mask(features)
    if (not all(story[i] for i in indices) or set(targets[story, 0].tolist()) != {0., 1.}
            or len(decision_ids) != len(features) or len(set(decision_ids)) != len(decision_ids)
            or tuple(decision_ids) != tuple(sorted(decision_ids))
            or not np.all(np.isfinite(weights)) or np.any(weights <= 0.)):
        raise LivingDexOptionValueError("bounded matchup TRAIN anchors/classes/weights differ")
    selected = bounded_matchup_story_feature_indices()
    x = features[:, selected]
    story_x, story_weights = x[story], weights[story]
    mean = np.average(story_x, axis=0, weights=story_weights)
    centered = story_x - mean
    threshold = _BOUNDED_MATCHUP_CONSTANT_MULTIPLIER * np.finfo(np.float64).eps * np.maximum(1., np.max(np.abs(story_x), axis=0))
    constant = np.max(np.abs(centered), axis=0) <= threshold
    std = np.sqrt(np.average(centered ** 2, axis=0, weights=story_weights))
    scale = np.maximum(std, _BOUNDED_MATCHUP_SCALE_FLOOR)
    scale[constant] = 1.
    normalized = (x - mean) / scale
    normalized[:, constant] = 0.
    active = np.flatnonzero(~constant)
    design = np.column_stack((np.ones(len(features)), normalized[:, active]))
    design[~story] = 0.
    constraint = design[list(indices)]
    try:
        _, singular, vt = np.linalg.svd(constraint, full_matrices=True)
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError("bounded matchup anchor SVD did not converge") from None
    tolerance = max(constraint.shape) * np.finfo(np.float64).eps * (singular[0] if len(singular) else 0.)
    rank = int(np.count_nonzero(singular > tolerance)); null = vt[rank:].T
    if not null.shape[1]:
        raise LivingDexOptionValueError("bounded matchup anchors leave no nonconstant correction space")
    projected = design @ null
    penalty = null[1:].T @ null[1:]
    bounded_base = np.clip(raw[:, 0], 0., 1.)
    residual = targets[:, 0] - bounded_base
    left = projected.T @ (weights[:, None] * projected) + ridge * penalty
    right = projected.T @ (weights * residual)
    try:
        reduced = np.linalg.solve(left, right)
        parameters = null @ reduced
    except np.linalg.LinAlgError:
        raise LivingDexOptionValueError("bounded matchup correction fit is singular") from None
    coefficients = np.zeros(len(selected)); coefficients[active] = parameters[1:]
    evidence = canonical_sha256(dict(schema="pokemon.core.bounded-matchup-normalizer-inputs.v1",
        feature_indices=list(selected), rows=[dict(decision_sha256=decision_ids[i], features=x[i].tolist(), weight=float(weights[i]))
            for i in range(len(features)) if story[i]]))
    head = LivingDexBoundedMatchupStorySuccessHead(coefficients, float(parameters[0]), base.model_sha256,
        mean, scale, constant, evidence)
    delta = design @ parameters
    anchor_error = float(np.max(np.abs(delta[list(indices)])))
    if not np.all(np.isfinite(parameters)) or anchor_error > 1e-10:
        raise LivingDexOptionValueError("bounded matchup correction violated retained forecasts")
    after_raw = raw.copy(); after_raw[story, 0] = bounded_base[story] + delta[story]
    before = _weighted_mse(targets, np.clip(raw, 0., 1.), weights)
    after = _weighted_mse(targets, np.clip(after_raw, 0., 1.), weights)
    report = dict(schema="pokemon.core.bounded-story-success-retention.v2", protected_count=len(indices),
        protected_decision_sha256=canonical_sha256(dict(schema="pokemon.core.bounded-story-success-retained-decisions.v1", decision_sha256s=sorted(ids))),
        protected_decision_sha256s=sorted(ids), maximum_bounded_forecast_error=anchor_error,
        feature_group="complete-v15-excluding-readiness-budget-plus-bias",
        trainable_feature_indices=list(selected), trainable_feature_names=list(head.feature_names),
        excluded_feature_indices=[i for i in range(features.shape[1]) if i not in selected],
        bias_unpenalized=True, protected_design_rank=rank, projected_design_rank=int(np.linalg.matrix_rank(projected)),
        story_rows=int(story.sum()), nonstory_rows=int((~story).sum()),
        parent_raw_success_mse=float(np.average((raw[:, 0]-targets[:, 0])**2, weights=weights)),
        corrected_preclip_success_mse=float(np.average((after_raw[:, 0]-targets[:, 0])**2, weights=weights)),
        base_parameters_retained=True, target="observed_success_minus_bounded_parent_success",
        parent_normalizer_retained=True, correction_normalizer=head.to_dict()["normalization"],
        nonconstant_correction_columns=len(active), constant_coefficients_exact_zero=bool(np.all(coefficients[constant] == 0.)),
        reduced_normal_equation_max_abs_residual=float(np.max(np.abs(left @ reduced - right))),
        budget_invariance_scope="learned correction only; frozen parent budget dependence retained",
        parent_model_sha256=base.model_sha256)
    return head, before, after, report


def fit_living_dex_option_value(
    examples: Iterable[LivingDexObservedArmExample],
    *,
    ridge: float = DEFAULT_OPTION_VALUE_RIDGE,
    maximum_importance_weight: float = DEFAULT_MAX_IMPORTANCE_WEIGHT,
    feature_version: int = 1,
    curriculum_examples: Iterable[LivingDexCurriculumOutcomeExample] = (),
    frozen_level_workload_base: LivingDexOptionValueModel | None = None,
    frozen_success_base: LivingDexOptionValueModel | None = None,
    frozen_party_cost_base: LivingDexOptionValueModel | None = None,
    party_cost_retention_decision_sha256s: Sequence[str] | None = None,
    story_success_retention_decision_sha256s: Sequence[str] | None = None,
    complete_paid_success_basis: CompletePaidSuccessBasis | None = None,
    bounded_story_success_retention_decision_sha256s: Sequence[str] | None = None,
    bounded_matchup_story_success_retention_decision_sha256s: Sequence[str] | None = None,
) -> LivingDexOptionValueFit:
    """Fit settled TRAIN evidence; optional retention modes preserve other heads."""

    for parent in (frozen_success_base, frozen_party_cost_base, frozen_level_workload_base):
        if isinstance(parent, LivingDexOptionValueModel) and parent.bounded_story_success_head is not None:
            raise LivingDexOptionValueError("fitting an already corrected parent is unsupported")
    bounded_ids = None
    bounded_v2 = bounded_matchup_story_success_retention_decision_sha256s is not None
    if bounded_v2:
        supplied = bounded_matchup_story_success_retention_decision_sha256s
        if (not isinstance(frozen_success_base, LivingDexOptionValueModel)
                or type(feature_version) is not int or feature_version != 15
                or frozen_success_base.feature_version != 15
                or frozen_party_cost_base is not None or frozen_level_workload_base is not None
                or story_success_retention_decision_sha256s is not None
                or party_cost_retention_decision_sha256s is not None or complete_paid_success_basis is not None
                or bounded_story_success_retention_decision_sha256s is not None
                or isinstance(supplied, (str, bytes)) or not isinstance(supplied, Sequence)):
            raise LivingDexOptionValueError("bounded matchup fit requires an uncorrected V15 success parent and anchors")
        bounded_ids = tuple(supplied)
        if (not bounded_ids or any(type(v) is not str or _SHA256.fullmatch(v) is None for v in bounded_ids)
                or len(set(bounded_ids)) != len(bounded_ids)):
            raise LivingDexOptionValueError("bounded matchup anchors must be unique SHA256 decisions")
    if bounded_story_success_retention_decision_sha256s is not None:
        supplied = bounded_story_success_retention_decision_sha256s
        if (not isinstance(frozen_success_base, LivingDexOptionValueModel)
                or type(feature_version) is not int or feature_version != 9
                or frozen_success_base.feature_version != 9
                or frozen_party_cost_base is not None or frozen_level_workload_base is not None
                or story_success_retention_decision_sha256s is not None
                or party_cost_retention_decision_sha256s is not None
                or complete_paid_success_basis is not None
                or isinstance(supplied, (str, bytes)) or not isinstance(supplied, Sequence)):
            raise LivingDexOptionValueError("bounded story fit requires an uncorrected V9 success parent and anchors")
        bounded_ids = tuple(supplied)
        if (not bounded_ids or any(type(v) is not str or _SHA256.fullmatch(v) is None for v in bounded_ids)
                or len(set(bounded_ids)) != len(bounded_ids)):
            raise LivingDexOptionValueError("bounded story anchors must be unique SHA256 decisions")
    success_protected_ids = None
    if story_success_retention_decision_sha256s is not None:
        if (not isinstance(frozen_success_base, LivingDexOptionValueModel)
                or type(feature_version) is not int or feature_version != 9
                or frozen_success_base.feature_version != 9
                or frozen_party_cost_base is not None or frozen_level_workload_base is not None
                or complete_paid_success_basis is not None
                or isinstance(story_success_retention_decision_sha256s, (str, bytes))
                or not isinstance(story_success_retention_decision_sha256s, Sequence)):
            raise LivingDexOptionValueError("story success retention requires an exact V9 success parent and decision sequence")
        success_protected_ids = tuple(story_success_retention_decision_sha256s)
        if (not success_protected_ids
                or any(type(v) is not str or _SHA256.fullmatch(v) is None for v in success_protected_ids)
                or len(set(success_protected_ids)) != len(success_protected_ids)):
            raise LivingDexOptionValueError("story success retention decisions must be nonempty unique SHA256s")
    protected_ids = None
    if party_cost_retention_decision_sha256s is not None:
        if (frozen_party_cost_base is None
                or isinstance(party_cost_retention_decision_sha256s, (str, bytes))
                or not isinstance(party_cost_retention_decision_sha256s, Sequence)):
            raise LivingDexOptionValueError("party output retention requires a party baseline and decision sequence")
        protected_ids = tuple(party_cost_retention_decision_sha256s)
        if (not protected_ids
                or any(type(value) is not str or _SHA256.fullmatch(value) is None for value in protected_ids)
                or len(set(protected_ids)) != len(protected_ids)):
            raise LivingDexOptionValueError("party output retention decisions must be nonempty unique SHA256s")
    if frozen_party_cost_base is not None:
        if (frozen_level_workload_base is not None or frozen_success_base is not None
                or complete_paid_success_basis is not None):
            raise LivingDexOptionValueError("party cost and other retention modes are exclusive")
        if (not isinstance(frozen_party_cost_base, LivingDexOptionValueModel)
                or type(feature_version) is not int or feature_version != 9
                or frozen_party_cost_base.feature_version != 9):
            raise LivingDexOptionValueError("party cost retention requires an exact-version V9 baseline")
    if complete_paid_success_basis is not None:
        if (not isinstance(complete_paid_success_basis, CompletePaidSuccessBasis)
                or not isinstance(frozen_success_base, LivingDexOptionValueModel)
                or frozen_success_base.feature_version != 12
                or feature_version != complete_paid_success_version(complete_paid_success_basis)
                or frozen_level_workload_base is not None):
            raise LivingDexOptionValueError(
                "complete-paid fit requires a typed basis and frozen V12 parent with its exact declared projection")
    if frozen_success_base is not None:
        if frozen_level_workload_base is not None:
            raise LivingDexOptionValueError("success and workload retention modes are exclusive")
        if (not isinstance(frozen_success_base, LivingDexOptionValueModel)
                or (complete_paid_success_basis is None
                    and frozen_success_base.feature_version != feature_version)):
            raise LivingDexOptionValueError("success retention requires an exact-version baseline")

    ridge_value = _positive_finite(ridge, subject="ridge")
    cap = _positive_finite(
        maximum_importance_weight,
        subject="maximum importance weight",
    )
    if cap < 1.0:
        raise LivingDexOptionValueError("maximum importance weight must be at least one")
    rows = tuple(
        sorted(
            _validated_examples(
                examples, expected_partition="train",
                allow_empty=frozen_success_base is not None,
            ),
            key=lambda row: row.decision_sha256,
        )
    )
    curriculum = _validated_curriculum(curriculum_examples, rows)
    combined: tuple[LivingDexObservedArmExample | LivingDexCurriculumOutcomeExample, ...] = (
        *rows,
        *curriculum,
    )
    settled = tuple(row for row in combined if row.outcome.status is LivingDexOutcomeStatus.SETTLED)
    if bounded_v2:
        settled = tuple(sorted(settled, key=lambda row: row.decision_sha256))
    if len(settled) < 2:
        raise LivingDexOptionValueError(
            "living-Dex option fit needs two settled observed examples"
        )
    protected_indices = ()
    if protected_ids is not None:
        settled_ids = {row.decision_sha256 for row in settled}
        if not set(protected_ids).issubset(settled_ids):
            raise LivingDexOptionValueError("party output retention must identify settled TRAIN rows in this fit")
        protected_indices = tuple(i for i, row in enumerate(settled) if row.decision_sha256 in protected_ids)
    success_protected_indices = ()
    if success_protected_ids is not None:
        if not set(success_protected_ids).issubset({row.decision_sha256 for row in settled}):
            raise LivingDexOptionValueError("story success retention must identify settled TRAIN rows in this fit")
        success_protected_indices = tuple(i for i, row in enumerate(settled) if row.decision_sha256 in success_protected_ids)
    bounded_indices = ()
    if bounded_ids is not None:
        if not set(bounded_ids).issubset({row.decision_sha256 for row in settled}):
            raise LivingDexOptionValueError("bounded story anchors must identify settled TRAIN rows")
        bounded_indices = tuple(i for i, row in enumerate(settled) if row.decision_sha256 in bounded_ids)
    dataset_sha256 = living_dex_option_train_dataset_sha256(rows, curriculum_examples=curriculum)
    option_feature_names(feature_version)
    if any(row.menu.feature_version > feature_version for row in rows):
        raise LivingDexOptionValueError("legacy fitter cannot ignore search history")
    for row in curriculum:
        curriculum_features(row, feature_version)
    features = np.asarray(
        [
            curriculum_features(row, feature_version)
            if isinstance(row, LivingDexCurriculumOutcomeExample)
            else row.menu.candidate_vector(
                row.selected_candidate_index, feature_version=feature_version
            )
            for row in settled
        ],
        dtype=np.float64,
    )
    targets = np.asarray(
        [row.outcome.target_vector for row in settled],
        dtype=np.float64,
    )
    weights = np.asarray(
        [
            1.0
            if isinstance(row, LivingDexCurriculumOutcomeExample)
            else row.importance_weight(cap)
            for row in settled
        ],
        dtype=np.float64,
    )
    party_retention = None
    story_retention = None
    bounded_retention = None
    bounded_head = None
    if bounded_ids is not None:
        if bounded_v2:
            bounded_head, before, after, bounded_retention = _fit_bounded_matchup_story_success(
                features, targets, weights, frozen_success_base, ridge_value, bounded_indices, bounded_ids,
                tuple(row.decision_sha256 for row in settled))
        else:
            bounded_head, before, after, bounded_retention = _fit_bounded_story_success(
                features, targets, weights, frozen_success_base, ridge_value, bounded_indices, bounded_ids)
        mean, scale = frozen_success_base.feature_mean, frozen_success_base.feature_scale
        intercept, coefficients = frozen_success_base.intercept, frozen_success_base.coefficients
    elif success_protected_ids is not None:
        mean, scale, intercept, coefficients, before, after, story_retention = _fit_story_success_with_retained_outputs(
            features, targets, weights, frozen_success_base, ridge_value,
            success_protected_indices, success_protected_ids)
    elif complete_paid_success_basis is not None:
        mean, scale, intercept, coefficients, before, after = _fit_complete_paid_success_residuals(
            features, targets, weights, frozen_success_base, ridge_value, complete_paid_success_basis)
    elif frozen_success_base is not None:
        mean, scale, intercept, coefficients, before, after = _fit_success_residuals(
            features, targets, weights, frozen_success_base, ridge_value)
    elif frozen_party_cost_base is not None:
        if protected_ids is None:
            mean, scale, intercept, coefficients, before, after = _fit_single_outcome_residuals(
                features, targets, weights, frozen_party_cost_base, ridge_value, "party_cost")
        else:
            mean, scale, intercept, coefficients, before, after, party_retention = _fit_party_cost_with_retained_outputs(
                features, targets, weights, frozen_party_cost_base, ridge_value,
                protected_indices, protected_ids)
    elif frozen_level_workload_base is not None:
        if feature_version != 9:
            raise LivingDexOptionValueError("workload cost retention requires feature version9")
        mean, scale, intercept, coefficients, before, after = _fit_level_workload_cost_residuals(
            features, targets, weights, frozen_level_workload_base, ridge_value)
    else:
        mean = np.average(features, axis=0, weights=weights)
        centered = features - mean
        scale = np.sqrt(np.average(centered**2, axis=0, weights=weights))
        scale[scale == 0.0] = 1.0
        normalized = (features - mean) / scale
        design = np.column_stack((np.ones(len(settled), dtype=np.float64), normalized))
        penalty = np.eye(design.shape[1], dtype=np.float64)
        penalty[0, 0] = 0.0
        weighted_design = design * weights[:, np.newaxis]
        left = design.T @ weighted_design + ridge_value * penalty
        right = design.T @ (weights[:, np.newaxis] * targets)
        try:
            parameters = cast(NDArray[np.float64], np.linalg.solve(left, right))
        except np.linalg.LinAlgError:
            raise LivingDexOptionValueError("living-Dex option fit is singular") from None
        intercept = parameters[0]
        coefficients = parameters[1:]
        baseline = np.average(targets, axis=0, weights=weights)
        predictions = np.clip(intercept + normalized @ coefficients, 0.0, 1.0)
        before = _weighted_mse(targets, np.broadcast_to(baseline, targets.shape), weights)
        after = _weighted_mse(targets, predictions, weights)
    economy_head: LivingDexEconomyHead | None = None
    qualified_econ_rows = qualified_economy_rows(rows)
    if frozen_success_base is not None:
        economy_head = frozen_success_base.economy_head
    elif frozen_party_cost_base is not None:
        economy_head = frozen_party_cost_base.economy_head
    elif frozen_level_workload_base is not None:
        economy_head = frozen_level_workload_base.economy_head
    elif feature_version >= 4 and len(qualified_econ_rows) >= 2:
        economy_head = fit_living_dex_economy_head(
            rows,
            ridge=ridge_value,
            maximum_importance_weight=cap,
        )
    model = LivingDexOptionValueModel(
        coefficients=coefficients,
        intercept=intercept,
        feature_mean=mean,
        feature_scale=scale,
        train_dataset_sha256=dataset_sha256,
        settled_examples=len(settled),
        censored_examples=len(combined) - len(settled),
        ridge=ridge_value,
        maximum_importance_weight=cap,
        feature_version=feature_version,
        objective=(
            LIVING_DEX_BOUNDED_MATCHUP_STORY_SUCCESS_OBJECTIVE if bounded_v2 else
            LIVING_DEX_BOUNDED_STORY_SUCCESS_OBJECTIVE if bounded_ids is not None else
            LIVING_DEX_STORY_SUCCESS_RETAINED_OBJECTIVE if success_protected_ids is not None else
            _COMPLETE_PAID_SUCCESS_OBJECTIVES[complete_paid_success_basis]
            if complete_paid_success_basis is not None else
            LIVING_DEX_SUCCESS_RESIDUAL_OBJECTIVE if frozen_success_base is not None else
            LIVING_DEX_PARTY_COST_RETAINED_OUTPUT_OBJECTIVE if protected_ids is not None else
            LIVING_DEX_PARTY_COST_RESIDUAL_OBJECTIVE if frozen_party_cost_base is not None else
            "selected-arm-ips-plus-unit-curriculum-multioutcome-ridge-v1"
            if curriculum
            else LIVING_DEX_OPTION_OBJECTIVE
        ),
        economy_head=economy_head,
        bounded_story_success_head=bounded_head,
    )
    report = LivingDexOptionValueFitReport(
        train_dataset_sha256=dataset_sha256,
        total_examples=len(combined),
        settled_examples=len(settled),
        censored_examples=len(combined) - len(settled),
        successful_examples=sum(bool(row.outcome.verified_success) for row in settled),
        distinct_selected_feature_rows=len({tuple(row) for row in features}),
        weighted_mse_before=before,
        weighted_mse_after=after,
        feature_version=feature_version,
        objective=model.objective,
        frozen_parent_model_sha256=(
            frozen_success_base.model_sha256 if frozen_success_base is not None else
            frozen_party_cost_base.model_sha256 if frozen_party_cost_base is not None else None
        ),
        party_cost_weighted_mse_before=(
            _weighted_mse(targets[:, [LIVING_DEX_OPTION_OUTCOME_NAMES.index("party_cost")]],
                np.clip(frozen_party_cost_base.raw_predictions(features), 0., 1.)[:, [LIVING_DEX_OPTION_OUTCOME_NAMES.index("party_cost")]], weights)
            if frozen_party_cost_base is not None else None),
        party_cost_weighted_mse_after=(
            _weighted_mse(targets[:, [LIVING_DEX_OPTION_OUTCOME_NAMES.index("party_cost")]],
                np.clip(model.raw_predictions(features), 0., 1.)[:, [LIVING_DEX_OPTION_OUTCOME_NAMES.index("party_cost")]], weights)
            if frozen_party_cost_base is not None else None),
        party_cost_retention=party_retention,
        story_success_retention=story_retention,
        bounded_story_success_retention=bounded_retention,
        complete_paid_success_basis=complete_paid_success_basis,
        complete_paid_settled_examples=(
            int(np.count_nonzero(features[:, len(option_feature_names(12))] == 1.))
            if complete_paid_success_basis is not None else None),
        complete_paid_distinct_horizons=(
            len(set(features[features[:, len(option_feature_names(12))] == 1., len(option_feature_names(12)) + 1]))
            if complete_paid_success_basis is not None else None),
        complete_paid_distinct_uncertainties=(
            len(set(features[features[:, len(option_feature_names(12))] == 1., len(option_feature_names(12)) + 2]))
            if complete_paid_success_basis is not None and feature_version == 14 else None),
        complete_paid_design_rank=(
            int(np.linalg.matrix_rank(features[features[:, len(option_feature_names(12))] == 1.][:,
                np.asarray(complete_paid_success_columns(complete_paid_success_basis)) + len(option_feature_names(12))]))
            if complete_paid_success_basis is not None and feature_version == 14 else None),
        economy_qualified_examples=(
            len(qualified_econ_rows)
            if feature_version >= 4 and len(qualified_econ_rows) > 0
            else None
        ),
    )
    return LivingDexOptionValueFit(model, report)


def evaluate_living_dex_option_value(
    model: LivingDexOptionValueModel,
    examples: Iterable[LivingDexObservedArmExample],
    *,
    expected_partition: str = "development",
    curriculum_examples: Iterable[LivingDexCurriculumOutcomeExample] = (),
) -> LivingDexOptionValueEvaluation:
    """Measure selected-arm prediction error without producing policy-quality claims."""

    if not isinstance(model, LivingDexOptionValueModel):
        raise TypeError("model must be a LivingDexOptionValueModel")
    rows = _validated_examples(examples, expected_partition=expected_partition)
    curriculum = _validated_curriculum(curriculum_examples, rows)
    if curriculum and (
        expected_partition != "train"
        or any(
            row.feature_version != model.feature_version
            and not (
                model.feature_version in (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15) and row.feature_version < model.feature_version
            )
            for row in curriculum
        )
    ):
        raise LivingDexOptionValueError("curriculum is training-only with exact feature version")
    combined: tuple[LivingDexObservedArmExample | LivingDexCurriculumOutcomeExample, ...] = (
        *rows,
        *curriculum,
    )
    settled = tuple(row for row in combined if row.outcome.status is LivingDexOutcomeStatus.SETTLED)
    if not settled:
        raise LivingDexOptionValueError("living-Dex evaluation has no settled outcomes")
    targets = np.asarray(
        [row.outcome.target_vector for row in settled],
        dtype=np.float64,
    )
    predictions = np.asarray(
        [
            tuple(
                float(value)
                for value in np.clip(
                    model.raw_predictions(curriculum_features(row, model.feature_version)),
                    0.0,
                    1.0,
                )
            )
            if isinstance(row, LivingDexCurriculumOutcomeExample)
            else model.predict_candidate(
                row.menu.context,
                row.menu.candidates[row.selected_candidate_index],
            ).vector()
            for row in settled
        ],
        dtype=np.float64,
    )
    weights = np.asarray(
        [
            1.0
            if isinstance(row, LivingDexCurriculumOutcomeExample)
            else row.importance_weight(model.maximum_importance_weight)
            for row in settled
        ],
        dtype=np.float64,
    )
    squared = (targets - predictions) ** 2
    per_outcome = tuple(
        float(np.average(squared[:, index], weights=weights)) for index in range(squared.shape[1])
    )
    return LivingDexOptionValueEvaluation(
        partition=expected_partition,
        total_examples=len(combined),
        settled_examples=len(settled),
        censored_examples=len(combined) - len(settled),
        weighted_mse=sum(per_outcome) / len(per_outcome),
        per_outcome_weighted_mse=per_outcome,
    )


def _validated_curriculum(
    examples: Iterable[LivingDexCurriculumOutcomeExample],
    choices: tuple[LivingDexObservedArmExample, ...],
) -> tuple[LivingDexCurriculumOutcomeExample, ...]:
    rows = tuple(examples)
    if any(not isinstance(row, LivingDexCurriculumOutcomeExample) for row in rows):
        raise TypeError("curriculum evidence rows differ")
    identities = [row.decision_sha256 for row in choices] + [row.decision_sha256 for row in rows]
    if len(set(identities)) != len(identities):
        raise LivingDexOptionValueError("choice and curriculum decision identities repeat")
    return tuple(sorted(rows, key=lambda row: row.decision_sha256))


def _validated_examples(
    examples: Iterable[LivingDexObservedArmExample],
    *,
    expected_partition: str,
    allow_empty: bool = False,
) -> tuple[LivingDexObservedArmExample, ...]:
    if expected_partition not in _PARTITIONS:
        raise LivingDexOptionValueError("living-Dex expected partition differs")
    rows = tuple(examples)
    if not rows and not allow_empty:
        raise LivingDexOptionValueError("living-Dex option evidence is empty")
    if any(not isinstance(row, LivingDexObservedArmExample) for row in rows):
        raise TypeError("living-Dex option evidence rows differ")
    if any(row.partition != expected_partition for row in rows):
        raise LivingDexOptionValueError("living-Dex option evidence partition differs")
    if len({row.decision_sha256 for row in rows}) != len(rows):
        raise LivingDexOptionValueError("living-Dex decision identities repeat")
    return rows


def _weighted_mse(
    targets: NDArray[np.float64],
    predictions: NDArray[np.float64],
    weights: NDArray[np.float64],
) -> float:
    squared = np.mean((targets - predictions) ** 2, axis=1)
    return float(np.average(squared, weights=weights))


__all__ = [
    "CompletePaidSuccessBasis",
    "project_complete_paid_capture_features",
    "upgrade_option_value_model_for_complete_paid_capture",
    "DEFAULT_MAX_IMPORTANCE_WEIGHT",
    "DEFAULT_OPTION_VALUE_RIDGE",
    "LIVING_DEX_ECONOMY_EVIDENCE_SCHEMA",
    "LIVING_DEX_ECONOMY_HEAD_SCHEMA",
    "LIVING_DEX_ECONOMY_NORMALIZATION",
    "LIVING_DEX_ECONOMY_OBJECTIVE",
    "LIVING_DEX_ECONOMY_OUTCOME_NAMES",
    "LIVING_DEX_OPTION_FEATURE_NAMES",
    "LIVING_DEX_OPTION_NORMALIZATION",
    "LIVING_DEX_OPTION_OBJECTIVE",
    "LIVING_DEX_PARTY_COST_RESIDUAL_OBJECTIVE",
    "LIVING_DEX_PARTY_COST_RETAINED_OUTPUT_OBJECTIVE",
    "LIVING_DEX_OPTION_OUTCOME_NAMES",
    "LivingDexCensorReason",
    "LivingDexEconomyHead",
    "LivingDexObservedArmExample",
    "LivingDexObservedOutcome",
    "LivingDexOptionAvailability",
    "LivingDexOptionCandidate",
    "LivingDexOptionContext",
    "LivingDexOptionFeatures",
    "LivingDexOptionKind",
    "LivingDexOptionMenu",
    "LivingDexOptionUnavailableReason",
    "LivingDexOptionUtility",
    "LivingDexOptionValueError",
    "LivingDexOptionValueEvaluation",
    "LivingDexOptionValueFit",
    "LivingDexOptionValueFitReport",
    "LivingDexOptionValueModel",
    "LivingDexOutcomeStatus",
    "LivingDexPredictedEconomyOutcome",
    "LivingDexPredictedOutcome",
    "evaluate_living_dex_option_value",
    "fit_living_dex_economy_head",
    "fit_living_dex_option_value",
    "living_dex_option_train_dataset_sha256",
    "living_dex_option_features_from_semantic_facts",
    "living_dex_option_context_from_goal_situation",
    "qualified_economy_rows",
    "uniform_behavior_probabilities",
    "upgrade_option_value_model_for_economy",
]



