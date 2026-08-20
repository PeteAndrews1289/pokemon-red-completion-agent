"""Train-only ranker for the rootless living-Dex dependency curriculum.

This deliberately separate head learns one small state-by-action interaction.  It
does not update the gameplay goal manager and does not import development opening
types or comparison code.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyCandidateFeatures,
    RootlessDependencyOutcome,
    RootlessDependencyScenario,
    RootlessLivingDexDependencyDesign,
)
from pokemon_red_completion.provenance import canonical_sha256

DEPENDENCY_RANKER_MODEL_SCHEMA = "pokemon.core.rootless-dependency-ranker-model.v1"
DEPENDENCY_RANKER_FIT_SCHEMA = "pokemon.core.rootless-dependency-ranker-fit.v1"
DEPENDENCY_TRAIN_DATASET_SCHEMA = "pokemon.core.rootless-dependency-train-dataset.v1"
DEPENDENCY_RANKER_OBJECTIVE = "pairwise-logistic-ridge-fixed-v1"
DEPENDENCY_RANKER_FEATURE_NAMES = (
    "adds_precursor",
    "consumes_precursor",
    "has_precursor_surplus_x_adds_precursor",
    "has_precursor_surplus_x_consumes_precursor",
)
DEPENDENCY_RANKER_ITERATIONS = 512
DEPENDENCY_RANKER_LEARNING_RATE = 0.08
DEPENDENCY_RANKER_RIDGE = 0.05


class LivingDexDependencyRankerError(ValueError):
    """The train-only dependency ranker or its frozen input is invalid."""


@dataclass(frozen=True, slots=True)
class DependencyTrainExample:
    scenario_id: str
    assigned_action: GoalKind
    preferred_action: GoalKind
    reward: int
    acquire_minus_evolve: tuple[float, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scenario_id, str)
            or self.assigned_action not in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
            or self.preferred_action
            not in {
                GoalKind.ACQUIRE_SPECIES,
                GoalKind.EVOLVE_SPECIES,
            }
            or self.reward not in {-1, 1}
            or len(self.acquire_minus_evolve) != len(DEPENDENCY_RANKER_FEATURE_NAMES)
            or any(not math.isfinite(value) for value in self.acquire_minus_evolve)
        ):
            raise LivingDexDependencyRankerError("dependency train example differs")
        expected_preferred = (
            self.assigned_action if self.reward == 1 else _other_action(self.assigned_action)
        )
        if self.preferred_action is not expected_preferred:
            raise LivingDexDependencyRankerError("dependency preference target differs")

    def public_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "assigned_action": self.assigned_action.value,
            "preferred_action": self.preferred_action.value,
            "reward": self.reward,
            "acquire_minus_evolve": list(self.acquire_minus_evolve),
        }


@dataclass(frozen=True, slots=True)
class DependencyRankerModel:
    feature_names: tuple[str, ...]
    weights: tuple[float, ...]
    train_dataset_sha256: str

    def __post_init__(self) -> None:
        if self.feature_names != DEPENDENCY_RANKER_FEATURE_NAMES:
            raise LivingDexDependencyRankerError("dependency ranker features differ")
        if len(self.weights) != len(self.feature_names) or any(
            type(value) is not float or not math.isfinite(value) for value in self.weights
        ):
            raise LivingDexDependencyRankerError("dependency ranker weights differ")
        if not _is_sha256(self.train_dataset_sha256):
            raise LivingDexDependencyRankerError("dependency train dataset identity differs")

    @property
    def model_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def score(self, candidate: DependencyCandidateFeatures) -> float:
        values = _candidate_vector(candidate)
        return sum(weight * value for weight, value in zip(self.weights, values, strict=True))

    def acquire_probability(self, scenario: RootlessDependencyScenario) -> float:
        if not isinstance(scenario, RootlessDependencyScenario):
            raise TypeError("scenario must be a RootlessDependencyScenario")
        acquire = self.score(scenario.candidate_features(GoalKind.ACQUIRE_SPECIES))
        evolve = self.score(scenario.candidate_features(GoalKind.EVOLVE_SPECIES))
        return _sigmoid(acquire - evolve)

    def preferred_action(self, scenario: RootlessDependencyScenario) -> GoalKind:
        return (
            GoalKind.ACQUIRE_SPECIES
            if self.acquire_probability(scenario) >= 0.5
            else GoalKind.EVOLVE_SPECIES
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": DEPENDENCY_RANKER_MODEL_SCHEMA,
            "feature_names": list(self.feature_names),
            "weights": list(self.weights),
            "train_dataset_sha256": self.train_dataset_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DependencyRankerModel:
        if not isinstance(value, Mapping) or set(value) != {
            "schema",
            "feature_names",
            "weights",
            "train_dataset_sha256",
        }:
            raise LivingDexDependencyRankerError("dependency ranker document differs")
        names = value.get("feature_names")
        weights = value.get("weights")
        train_dataset_sha256 = value.get("train_dataset_sha256")
        if (
            value.get("schema") != DEPENDENCY_RANKER_MODEL_SCHEMA
            or not isinstance(names, list)
            or any(not isinstance(item, str) for item in names)
            or not isinstance(weights, list)
            or any(type(item) is not float for item in weights)  # noqa: E721
            or not isinstance(train_dataset_sha256, str)
        ):
            raise LivingDexDependencyRankerError("dependency ranker document differs")
        return cls(tuple(names), tuple(weights), train_dataset_sha256)


@dataclass(frozen=True, slots=True)
class DependencyRankerFit:
    design_sha256: str
    train_dataset_sha256: str
    model: DependencyRankerModel
    baseline_cross_entropy: float
    fitted_cross_entropy: float
    train_accuracy: float

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.design_sha256)
            or self.train_dataset_sha256 != self.model.train_dataset_sha256
            or not all(
                type(value) is float and math.isfinite(value)
                for value in (
                    self.baseline_cross_entropy,
                    self.fitted_cross_entropy,
                    self.train_accuracy,
                )
            )
            or not 0.0 <= self.train_accuracy <= 1.0
            or self.fitted_cross_entropy >= self.baseline_cross_entropy
        ):
            raise LivingDexDependencyRankerError("dependency fit metrics differ")

    @property
    def fit_sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": DEPENDENCY_RANKER_FIT_SCHEMA,
            "design_sha256": self.design_sha256,
            "train_dataset_sha256": self.train_dataset_sha256,
            "model": self.model.to_dict(),
            "model_sha256": self.model.model_sha256,
            "objective": DEPENDENCY_RANKER_OBJECTIVE,
            "ridge": DEPENDENCY_RANKER_RIDGE,
            "learning_rate": DEPENDENCY_RANKER_LEARNING_RATE,
            "iterations": DEPENDENCY_RANKER_ITERATIONS,
            "baseline_cross_entropy": self.baseline_cross_entropy,
            "fitted_cross_entropy": self.fitted_cross_entropy,
            "train_accuracy": self.train_accuracy,
            "train_examples": 8,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DependencyRankerFit:
        expected_fields = {
            "schema",
            "design_sha256",
            "train_dataset_sha256",
            "model",
            "model_sha256",
            "objective",
            "ridge",
            "learning_rate",
            "iterations",
            "baseline_cross_entropy",
            "fitted_cross_entropy",
            "train_accuracy",
            "train_examples",
        }
        if not isinstance(value, Mapping) or set(value) != expected_fields:
            raise LivingDexDependencyRankerError("dependency fit document differs")
        model_value = value.get("model")
        if not isinstance(model_value, Mapping):
            raise LivingDexDependencyRankerError("dependency fit document differs")
        model = DependencyRankerModel.from_dict(model_value)
        design_sha256 = value.get("design_sha256")
        train_dataset_sha256 = value.get("train_dataset_sha256")
        baseline_cross_entropy = value.get("baseline_cross_entropy")
        fitted_cross_entropy = value.get("fitted_cross_entropy")
        train_accuracy = value.get("train_accuracy")
        if (
            value.get("schema") != DEPENDENCY_RANKER_FIT_SCHEMA
            or not isinstance(design_sha256, str)
            or not isinstance(train_dataset_sha256, str)
            or value.get("model_sha256") != model.model_sha256
            or value.get("objective") != DEPENDENCY_RANKER_OBJECTIVE
            or type(value.get("ridge")) is not float  # noqa: E721
            or value.get("ridge") != DEPENDENCY_RANKER_RIDGE
            or type(value.get("learning_rate")) is not float  # noqa: E721
            or value.get("learning_rate") != DEPENDENCY_RANKER_LEARNING_RATE
            or type(value.get("iterations")) is not int  # noqa: E721
            or value.get("iterations") != DEPENDENCY_RANKER_ITERATIONS
            or type(baseline_cross_entropy) is not float  # noqa: E721
            or type(fitted_cross_entropy) is not float  # noqa: E721
            or type(train_accuracy) is not float  # noqa: E721
            or type(value.get("train_examples")) is not int  # noqa: E721
            or value.get("train_examples") != 8
        ):
            raise LivingDexDependencyRankerError("dependency fit document differs")
        fit = cls(
            design_sha256=design_sha256,
            train_dataset_sha256=train_dataset_sha256,
            model=model,
            baseline_cross_entropy=baseline_cross_entropy,
            fitted_cross_entropy=fitted_cross_entropy,
            train_accuracy=train_accuracy,
        )
        if fit.to_dict() != dict(value):
            raise LivingDexDependencyRankerError("dependency fit document differs")
        return fit


def fit_dependency_ranker(
    design: RootlessLivingDexDependencyDesign,
    outcomes: Sequence[RootlessDependencyOutcome],
) -> DependencyRankerFit:
    """Fit one frozen interaction head from exactly eight canonical train outcomes."""

    examples = dependency_train_examples(design, outcomes)
    dataset_document = {
        "schema": DEPENDENCY_TRAIN_DATASET_SCHEMA,
        "design_sha256": design.design_sha256,
        "rows": [example.public_dict() for example in examples],
    }
    dataset_sha = canonical_sha256(dataset_document)
    weights = [0.0] * len(DEPENDENCY_RANKER_FEATURE_NAMES)
    for _ in range(DEPENDENCY_RANKER_ITERATIONS):
        gradient = [DEPENDENCY_RANKER_RIDGE * weight for weight in weights]
        for example in examples:
            target = 1.0 if example.preferred_action is GoalKind.ACQUIRE_SPECIES else 0.0
            prediction = _sigmoid(_dot(weights, example.acquire_minus_evolve))
            for index, value in enumerate(example.acquire_minus_evolve):
                gradient[index] += (prediction - target) * value / len(examples)
        for index, value in enumerate(gradient):
            weights[index] -= DEPENDENCY_RANKER_LEARNING_RATE * value
    model = DependencyRankerModel(
        DEPENDENCY_RANKER_FEATURE_NAMES,
        tuple(float(value) for value in weights),
        dataset_sha,
    )
    probabilities = [model.acquire_probability(scenario) for scenario in design.train_scenarios]
    targets = [
        1.0 if example.preferred_action is GoalKind.ACQUIRE_SPECIES else 0.0 for example in examples
    ]
    fitted_loss = _cross_entropy(targets, probabilities)
    accuracy = sum(
        (probability >= 0.5) == bool(target)
        for probability, target in zip(probabilities, targets, strict=True)
    ) / len(targets)
    fit = DependencyRankerFit(
        design_sha256=design.design_sha256,
        train_dataset_sha256=dataset_sha,
        model=model,
        baseline_cross_entropy=math.log(2.0),
        fitted_cross_entropy=fitted_loss,
        train_accuracy=float(accuracy),
    )
    if fit.train_accuracy != 1.0 or DependencyRankerModel.from_dict(model.to_dict()) != model:
        raise LivingDexDependencyRankerError("dependency fit failed its frozen train gate")
    return fit


def dependency_train_examples(
    design: RootlessLivingDexDependencyDesign,
    outcomes: Sequence[RootlessDependencyOutcome],
) -> tuple[DependencyTrainExample, ...]:
    if not isinstance(design, RootlessLivingDexDependencyDesign):
        raise TypeError("design must be a RootlessLivingDexDependencyDesign")
    if not isinstance(outcomes, Sequence) or len(outcomes) != 8:
        raise LivingDexDependencyRankerError("fit requires exactly eight outcomes")
    by_id: dict[str, RootlessDependencyOutcome] = {}
    for outcome in outcomes:
        if not isinstance(outcome, RootlessDependencyOutcome):
            raise LivingDexDependencyRankerError("dependency outcome type differs")
        if outcome.scenario_id in by_id or outcome.status != "settled" or outcome.reward is None:
            raise LivingDexDependencyRankerError("dependency outcome roster differs")
        by_id[outcome.scenario_id] = outcome
    if set(by_id) != {scenario.scenario_id for scenario in design.train_scenarios}:
        raise LivingDexDependencyRankerError("dependency outcome roster differs")
    examples: list[DependencyTrainExample] = []
    for scenario in design.train_scenarios:
        outcome = by_id[scenario.scenario_id]
        reward = outcome.reward
        if (
            reward is None
            or outcome.action is not scenario.assigned_action
            or outcome.structure != scenario.structure
            or outcome.before != scenario.before
        ):
            raise LivingDexDependencyRankerError("dependency outcome binding differs")
        acquire = _candidate_vector(scenario.candidate_features(GoalKind.ACQUIRE_SPECIES))
        evolve = _candidate_vector(scenario.candidate_features(GoalKind.EVOLVE_SPECIES))
        preferred = (
            scenario.assigned_action if reward == 1 else _other_action(scenario.assigned_action)
        )
        examples.append(
            DependencyTrainExample(
                scenario.scenario_id,
                scenario.assigned_action,
                preferred,
                reward,
                tuple(left - right for left, right in zip(acquire, evolve, strict=True)),
            )
        )
    if (
        Counter(example.assigned_action for example in examples)
        != {GoalKind.ACQUIRE_SPECIES: 4, GoalKind.EVOLVE_SPECIES: 4}
        or Counter(example.reward for example in examples) != {-1: 4, 1: 4}
        or Counter(example.preferred_action for example in examples)
        != {GoalKind.ACQUIRE_SPECIES: 4, GoalKind.EVOLVE_SPECIES: 4}
    ):
        raise LivingDexDependencyRankerError("dependency train balance differs")
    return tuple(examples)


def _candidate_vector(candidate: DependencyCandidateFeatures) -> tuple[float, ...]:
    if not isinstance(candidate, DependencyCandidateFeatures):
        raise TypeError("candidate must be DependencyCandidateFeatures")
    has_surplus = 1.0 if candidate.state.precursor_surplus > 0 else 0.0
    return (
        float(candidate.adds_precursor),
        float(candidate.consumes_precursor),
        has_surplus * candidate.adds_precursor,
        has_surplus * candidate.consumes_precursor,
    )


def _other_action(action: GoalKind) -> GoalKind:
    if action is GoalKind.ACQUIRE_SPECIES:
        return GoalKind.EVOLVE_SPECIES
    if action is GoalKind.EVOLVE_SPECIES:
        return GoalKind.ACQUIRE_SPECIES
    raise LivingDexDependencyRankerError("dependency action differs")


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _cross_entropy(targets: Sequence[float], probabilities: Sequence[float]) -> float:
    if len(targets) != len(probabilities) or not targets:
        raise LivingDexDependencyRankerError("dependency loss inputs differ")
    epsilon = 1e-12
    return -sum(
        target * math.log(min(1.0 - epsilon, max(epsilon, probability)))
        + (1.0 - target) * math.log(min(1.0 - epsilon, max(epsilon, 1.0 - probability)))
        for target, probability in zip(targets, probabilities, strict=True)
    ) / len(targets)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
