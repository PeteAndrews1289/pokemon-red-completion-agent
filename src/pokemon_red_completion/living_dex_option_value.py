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
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.goal_manager import GoalSituation
from pokemon_red_completion.goal_search_memory import GoalSearchHistory
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
    if type(version) is not int or version not in (1, 2, 3, 4):
        raise LivingDexOptionValueError("living-Dex feature version differs")
    return (
        LIVING_DEX_OPTION_FEATURE_NAMES
        + (LIVING_DEX_HISTORY_FEATURE_NAMES if version >= 2 else ())
        + (LIVING_DEX_RECOVERY_FEATURE_NAMES if version >= 3 else ())
        + (ECONOMY_FEATURE_NAMES if version >= 4 else ())
    )


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

    def __post_init__(self) -> None:
        if self.search_history is not None and not isinstance(
            self.search_history, GoalSearchHistory
        ):
            raise LivingDexOptionValueError("living-Dex search history differs")
        if self.economy_offer is not None and not isinstance(
            self.economy_offer, EconomyOffer
        ):
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
            _unit_interval(
                self.useful_liquidity_gain, subject="predicted useful_liquidity_gain"
            ),
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
        intercept = _validate_numeric_vector(
            self.intercept, targets, subject="intercept"
        )
        mean = _validate_numeric_vector(
            self.feature_mean, width, subject="feature_mean"
        )
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
            raise LivingDexOptionValueError(
                "cash_loss_weight must be 1.0 for this schema"
            )
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
            candidate.vector(context, feature_version=4), dtype=np.float64
        )
        normalized = (vector - self.feature_mean) / self.feature_scale
        raw = self.intercept + normalized @ self.coefficients
        clipped = np.clip(raw, 0.0, 1.0)
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
        intercept = _validate_numeric_vector(
            value.get("intercept"), targets, subject="intercept"
        )
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
        raise LivingDexOptionValueError(
            "useful_liquidity_gain_weight must be 1.0 for this schema"
        )
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
            row.menu.candidate_vector(row.selected_candidate_index, feature_version=4)
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

    def __post_init__(self) -> None:
        if self.objective not in {
            LIVING_DEX_OPTION_OBJECTIVE,
            "selected-arm-ips-plus-unit-curriculum-multioutcome-ridge-v1",
        }:
            raise LivingDexOptionValueError("living-Dex regression objective differs")
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
            if self.feature_version != 4:
                raise LivingDexOptionValueError(
                    "only feature_version 4 can carry an economy head"
                )
            if not isinstance(self.economy_head, LivingDexEconomyHead):
                raise LivingDexOptionValueError(
                    "economy_head must be a LivingDexEconomyHead"
                )
            if self.economy_head.qualified_examples > self.settled_examples:
                raise LivingDexOptionValueError(
                    "living-Dex economy head qualified examples exceed settled examples"
                )

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
        normalized = (vector - self.feature_mean) / self.feature_scale
        raw = self.intercept + normalized @ self.coefficients
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
        if self.economy_head is None or self.feature_version != 4:
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
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> LivingDexOptionValueModel:
        if not isinstance(value, Mapping):
            raise LivingDexOptionValueError("living-Dex model document differs")
        version = next(
            (
                v
                for v in (1, 2, 3, 4)
                if value.get("schema") == f"pokemon.core.living-dex-option-value-model.v{v}"
            ),
            1,
        )
        has_economy_head = "economy_head" in value
        if has_economy_head and version != 4:
            raise LivingDexOptionValueError("only feature_version 4 can carry an economy head")
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
            if economy_head.qualified_examples > cast(int, settled_examples):
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
            _validated_examples(examples, expected_partition="train"),
            key=lambda row: row.decision_sha256,
        )
    )
    curriculum = _validated_curriculum(curriculum_examples, rows)
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


def fit_living_dex_option_value(
    examples: Iterable[LivingDexObservedArmExample],
    *,
    ridge: float = DEFAULT_OPTION_VALUE_RIDGE,
    maximum_importance_weight: float = DEFAULT_MAX_IMPORTANCE_WEIGHT,
    feature_version: int = 1,
    curriculum_examples: Iterable[LivingDexCurriculumOutcomeExample] = (),
) -> LivingDexOptionValueFit:
    """Fit all outcome heads using only settled selected-arm train evidence."""

    ridge_value = _positive_finite(ridge, subject="ridge")
    cap = _positive_finite(
        maximum_importance_weight,
        subject="maximum importance weight",
    )
    if cap < 1.0:
        raise LivingDexOptionValueError("maximum importance weight must be at least one")
    rows = tuple(
        sorted(
            _validated_examples(examples, expected_partition="train"),
            key=lambda row: row.decision_sha256,
        )
    )
    curriculum = _validated_curriculum(curriculum_examples, rows)
    combined: tuple[LivingDexObservedArmExample | LivingDexCurriculumOutcomeExample, ...] = (
        *rows,
        *curriculum,
    )
    settled = tuple(row for row in combined if row.outcome.status is LivingDexOutcomeStatus.SETTLED)
    if len(settled) < 2:
        raise LivingDexOptionValueError(
            "living-Dex option fit needs two settled selected-arm examples"
        )
    dataset_sha256 = living_dex_option_train_dataset_sha256(rows, curriculum_examples=curriculum)
    option_feature_names(feature_version)
    if any(row.menu.feature_version > feature_version for row in rows):
        raise LivingDexOptionValueError("legacy fitter cannot ignore search history")
    if any(row.feature_version != feature_version for row in curriculum):
        raise LivingDexOptionValueError("curriculum feature version differs from fitter")
    features = np.asarray(
        [
            row.features
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
    if feature_version == 4 and len(qualified_econ_rows) >= 2:
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
            "selected-arm-ips-plus-unit-curriculum-multioutcome-ridge-v1"
            if curriculum
            else LIVING_DEX_OPTION_OBJECTIVE
        ),
        economy_head=economy_head,
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
        economy_qualified_examples=(
            len(qualified_econ_rows)
            if feature_version == 4 and len(qualified_econ_rows) > 0
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
        or any(row.feature_version != model.feature_version for row in curriculum)
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
                    model.intercept
                    + ((np.asarray(row.features) - model.feature_mean) / model.feature_scale)
                    @ model.coefficients,
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
) -> tuple[LivingDexObservedArmExample, ...]:
    if expected_partition not in _PARTITIONS:
        raise LivingDexOptionValueError("living-Dex expected partition differs")
    rows = tuple(examples)
    if not rows:
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
