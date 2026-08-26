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
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.provenance import canonical_sha256

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


_KIND_FEATURE_NAMES = tuple(f"kind.{kind.value}" for kind in LivingDexOptionKind)
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

    def policy_dict(self) -> dict[str, object]:
        return {
            "access_pressure": self.access_pressure,
            "collection_pressure": self.collection_pressure,
            "dependency_pressure": self.dependency_pressure,
            "knowledge_pressure": self.knowledge_pressure,
            "party_pressure": self.party_pressure,
            "resource_pressure": self.resource_pressure,
            "schema": LIVING_DEX_OPTION_CONTEXT_SCHEMA,
            "storage_pressure": self.storage_pressure,
        }


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

    def vector(self, context: LivingDexOptionContext) -> tuple[float, ...]:
        if not isinstance(context, LivingDexOptionContext):
            raise TypeError("context must be a LivingDexOptionContext")
        kinds = tuple(float(self.kind is kind) for kind in LivingDexOptionKind)
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
        return result

    def policy_dict(self, context: LivingDexOptionContext) -> dict[str, object]:
        return {
            "feature_names": list(LIVING_DEX_OPTION_FEATURE_NAMES),
            "kind": self.kind.value,
            "normalization": LIVING_DEX_OPTION_NORMALIZATION,
            "schema": LIVING_DEX_OPTION_FEATURE_SCHEMA,
            "values": list(self.vector(context)),
        }


@dataclass(frozen=True, slots=True)
class LivingDexOptionCandidate:
    """A policy-visible row plus a private execution binding."""

    binding_ref: str
    features: LivingDexOptionFeatures
    availability: LivingDexOptionAvailability
    unavailable_reason: LivingDexOptionUnavailableReason | None = None

    def __post_init__(self) -> None:
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
            raise LivingDexOptionValueError(
                "masked living-Dex option needs an unavailable reason"
            )

    def policy_dict(self, context: LivingDexOptionContext) -> dict[str, object]:
        return {
            "availability": self.availability.value,
            "features": self.features.policy_dict(context),
            "unavailable_reason": (
                None if self.unavailable_reason is None else self.unavailable_reason.value
            ),
        }


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

    def candidate_vector(self, index: int) -> tuple[float, ...]:
        if type(index) is not int or not 0 <= index < len(self.candidates):  # noqa: E721
            raise LivingDexOptionValueError("living-Dex candidate index is invalid")
        return self.candidates[index].features.vector(self.context)

    def policy_dict(self) -> dict[str, object]:
        return {
            "candidates": [candidate.policy_dict(self.context) for candidate in self.candidates],
            "context": self.context.policy_dict(),
            "schema": LIVING_DEX_OPTION_MENU_SCHEMA,
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

    def __post_init__(self) -> None:
        if not isinstance(self.status, LivingDexOutcomeStatus):
            raise LivingDexOptionValueError("living-Dex outcome status differs")
        target_names = LIVING_DEX_OPTION_OUTCOME_NAMES[1:]
        if self.status is LivingDexOutcomeStatus.SETTLED:
            if type(self.verified_success) is not bool:  # noqa: E721
                raise LivingDexOptionValueError("settled living-Dex outcome needs success")
            if self.censor_reason is not None:
                raise LivingDexOptionValueError("settled living-Dex outcome cannot be censored")
            for name in target_names:
                value = getattr(self, name)
                if value is None:
                    raise LivingDexOptionValueError(
                        f"settled living-Dex outcome needs {name}"
                    )
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

    @property
    def target_vector(self) -> tuple[float, ...] | None:
        if self.status is LivingDexOutcomeStatus.CENSORED:
            return None
        assert self.verified_success is not None
        values = tuple(float(getattr(self, name)) for name in LIVING_DEX_OPTION_OUTCOME_NAMES[1:])
        return (float(self.verified_success), *values)

    def public_dict(self) -> dict[str, object]:
        target = self.target_vector
        return {
            "censor_reason": (
                None if self.censor_reason is None else self.censor_reason.value
            ),
            "schema": LIVING_DEX_OPTION_OUTCOME_SCHEMA,
            "status": self.status.value,
            "target_names": list(LIVING_DEX_OPTION_OUTCOME_NAMES),
            "target_values": None if target is None else list(target),
        }


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
        if not isinstance(self.decision_sha256, str) or _SHA256.fullmatch(
            self.decision_sha256
        ) is None:
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
        if (
            not isinstance(self.behavior_probabilities, tuple)
            or len(self.behavior_probabilities) != len(self.menu.candidates)
        ):
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
                    raise LivingDexOptionValueError(
                        "living-Dex behavior policy lacks full support"
                    )
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

    def __post_init__(self) -> None:
        width = len(LIVING_DEX_OPTION_FEATURE_NAMES)
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
        if not isinstance(self.train_dataset_sha256, str) or _SHA256.fullmatch(
            self.train_dataset_sha256
        ) is None:
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
        vector = np.asarray(candidate.features.vector(context), dtype=np.float64)
        normalized = (vector - self.feature_mean) / self.feature_scale
        raw = self.intercept + normalized @ self.coefficients
        return LivingDexPredictedOutcome.from_vector(np.clip(raw, 0.0, 1.0).tolist())

    def scores(
        self,
        menu: LivingDexOptionMenu,
        utility: LivingDexOptionUtility,
    ) -> tuple[float | None, ...]:
        if not isinstance(menu, LivingDexOptionMenu):
            raise TypeError("menu must be a LivingDexOptionMenu")
        if not isinstance(utility, LivingDexOptionUtility):
            raise TypeError("utility must be a LivingDexOptionUtility")
        return tuple(
            utility.score(self.predict_candidate(menu.context, candidate))
            if index in menu.available_indices
            else None
            for index, candidate in enumerate(menu.candidates)
        )

    def select(self, menu: LivingDexOptionMenu, utility: LivingDexOptionUtility) -> int:
        values = self.scores(menu, utility)

        def key(index: int) -> tuple[float, int]:
            value = values[index]
            if value is None:
                raise LivingDexOptionValueError("masked living-Dex option reached selection")
            return value, -index

        return max(menu.available_indices, key=key)

    def to_dict(self) -> dict[str, object]:
        return {
            "censored_examples": self.censored_examples,
            "coefficients": self.coefficients.tolist(),
            "feature_mean": self.feature_mean.tolist(),
            "feature_names": list(LIVING_DEX_OPTION_FEATURE_NAMES),
            "feature_scale": self.feature_scale.tolist(),
            "intercept": self.intercept.tolist(),
            "maximum_importance_weight": self.maximum_importance_weight,
            "normalization": LIVING_DEX_OPTION_NORMALIZATION,
            "objective": LIVING_DEX_OPTION_OBJECTIVE,
            "outcome_names": list(LIVING_DEX_OPTION_OUTCOME_NAMES),
            "ridge": self.ridge,
            "schema": LIVING_DEX_OPTION_MODEL_SCHEMA,
            "settled_examples": self.settled_examples,
            "train_dataset_sha256": self.train_dataset_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> LivingDexOptionValueModel:
        if not isinstance(value, Mapping) or set(value) != {
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
        }:
            raise LivingDexOptionValueError("living-Dex model document differs")
        feature_names = value.get("feature_names")
        outcome_names = value.get("outcome_names")
        train_dataset_sha256 = value.get("train_dataset_sha256")
        settled_examples = value.get("settled_examples")
        censored_examples = value.get("censored_examples")
        ridge = value.get("ridge")
        maximum_importance_weight = value.get("maximum_importance_weight")
        if (
            value.get("schema") != LIVING_DEX_OPTION_MODEL_SCHEMA
            or value.get("objective") != LIVING_DEX_OPTION_OBJECTIVE
            or value.get("normalization") != LIVING_DEX_OPTION_NORMALIZATION
            or not isinstance(feature_names, list)
            or tuple(feature_names) != LIVING_DEX_OPTION_FEATURE_NAMES
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

    def public_dict(self) -> dict[str, object]:
        return {
            "censored_examples": self.censored_examples,
            "counterfactual_targets": 0,
            "distinct_selected_feature_rows": self.distinct_selected_feature_rows,
            "objective": LIVING_DEX_OPTION_OBJECTIVE,
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


def fit_living_dex_option_value(
    examples: Iterable[LivingDexObservedArmExample],
    *,
    ridge: float = DEFAULT_OPTION_VALUE_RIDGE,
    maximum_importance_weight: float = DEFAULT_MAX_IMPORTANCE_WEIGHT,
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
    settled = tuple(
        row for row in rows if row.outcome.status is LivingDexOutcomeStatus.SETTLED
    )
    if len(settled) < 2:
        raise LivingDexOptionValueError(
            "living-Dex option fit needs two settled selected-arm examples"
        )
    dataset_sha256 = canonical_sha256(
        {
            "rows": [row.public_dict() for row in rows],
            "schema": "pokemon.core.living-dex-option-train-dataset.v1",
        }
    )
    features = np.asarray([row.selected_vector for row in settled], dtype=np.float64)
    targets = np.asarray(
        [row.outcome.target_vector for row in settled],
        dtype=np.float64,
    )
    weights = np.asarray(
        [row.importance_weight(cap) for row in settled],
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
    model = LivingDexOptionValueModel(
        coefficients=coefficients,
        intercept=intercept,
        feature_mean=mean,
        feature_scale=scale,
        train_dataset_sha256=dataset_sha256,
        settled_examples=len(settled),
        censored_examples=len(rows) - len(settled),
        ridge=ridge_value,
        maximum_importance_weight=cap,
    )
    report = LivingDexOptionValueFitReport(
        train_dataset_sha256=dataset_sha256,
        total_examples=len(rows),
        settled_examples=len(settled),
        censored_examples=len(rows) - len(settled),
        successful_examples=sum(bool(row.outcome.verified_success) for row in settled),
        distinct_selected_feature_rows=len({row.selected_vector for row in settled}),
        weighted_mse_before=before,
        weighted_mse_after=after,
    )
    return LivingDexOptionValueFit(model, report)


def evaluate_living_dex_option_value(
    model: LivingDexOptionValueModel,
    examples: Iterable[LivingDexObservedArmExample],
    *,
    expected_partition: str = "development",
) -> LivingDexOptionValueEvaluation:
    """Measure selected-arm prediction error without producing policy-quality claims."""

    if not isinstance(model, LivingDexOptionValueModel):
        raise TypeError("model must be a LivingDexOptionValueModel")
    rows = _validated_examples(examples, expected_partition=expected_partition)
    settled = tuple(
        row for row in rows if row.outcome.status is LivingDexOutcomeStatus.SETTLED
    )
    if not settled:
        raise LivingDexOptionValueError("living-Dex evaluation has no settled outcomes")
    targets = np.asarray(
        [row.outcome.target_vector for row in settled],
        dtype=np.float64,
    )
    predictions = np.asarray(
        [
            model.predict_candidate(
                row.menu.context,
                row.menu.candidates[row.selected_candidate_index],
            ).vector()
            for row in settled
        ],
        dtype=np.float64,
    )
    weights = np.asarray(
        [row.importance_weight(model.maximum_importance_weight) for row in settled],
        dtype=np.float64,
    )
    squared = (targets - predictions) ** 2
    per_outcome = tuple(
        float(np.average(squared[:, index], weights=weights))
        for index in range(squared.shape[1])
    )
    return LivingDexOptionValueEvaluation(
        partition=expected_partition,
        total_examples=len(rows),
        settled_examples=len(settled),
        censored_examples=len(rows) - len(settled),
        weighted_mse=sum(per_outcome) / len(per_outcome),
        per_outcome_weighted_mse=per_outcome,
    )


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
    "LIVING_DEX_OPTION_FEATURE_NAMES",
    "LIVING_DEX_OPTION_NORMALIZATION",
    "LIVING_DEX_OPTION_OBJECTIVE",
    "LIVING_DEX_OPTION_OUTCOME_NAMES",
    "LivingDexCensorReason",
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
    "LivingDexPredictedOutcome",
    "evaluate_living_dex_option_value",
    "fit_living_dex_option_value",
    "uniform_behavior_probabilities",
]
