"""Outcome-bearing adaptation for the shared semantic battle move ranker.

Teacher choices remain useful coverage diagnostics, but they are not rewards.
This module updates only the final layer of an existing nonlinear move ranker
from cartridge-measured counterfactual outcomes.  The frozen hidden layer is a
prior learned from the Red curriculum; the last-layer update is small,
deterministic, and explicitly anchored to that prior.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.battle_model import BattleModelValidationError
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import BattleFeatureBatch
from pokemon_red_completion.scenario_lab import ScenarioPartition

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UTILITY_TOLERANCE = 1e-9


class BattleOutcomeLearningError(ValueError):
    """Raised when outcome evidence crosses an experimental boundary."""


@dataclass(frozen=True, slots=True)
class BattleTurnOutcome:
    """Title-neutral health and terminal effects of one selected move turn.

    ``move_executed`` remains diagnostic.  A policy choice can be mechanically
    suppressed by the cartridge after the controller has proved the selected
    turn boundary (sleep, paralysis, Disable, trapping, or an opponent's
    terminal move).  That is still an observed consequence of choosing the
    candidate, not a teacher label or a controller failure.
    """

    move_executed: bool
    opponent_damage_fraction: float
    player_damage_fraction: float
    opponent_fainted: bool
    player_fainted: bool
    battle_exited: bool
    actions_executed: int
    frames_executed: int
    pre_attack_frames: int = 0

    def __post_init__(self) -> None:
        for name in ("move_executed", "opponent_fainted", "player_fainted", "battle_exited"):
            if not isinstance(getattr(self, name), bool):
                raise BattleOutcomeLearningError(f"{name} must be a bool")
        for name in ("opponent_damage_fraction", "player_damage_fraction"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise BattleOutcomeLearningError(f"{name} must be a finite unit fraction")
        for name in ("actions_executed", "frames_executed"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:  # noqa: E721
                raise BattleOutcomeLearningError(f"{name} must be a positive integer")
        if (
            type(self.pre_attack_frames) is not int  # noqa: E721
            or not 0 <= self.pre_attack_frames <= self.frames_executed
        ):
            raise BattleOutcomeLearningError(
                "pre_attack_frames must fit inside the execution frame count"
            )

    @property
    def learner_update_eligible(self) -> bool:
        """A returned turn is selection-proven even when the move is suppressed."""

        return True

    @property
    def utility(self) -> float:
        """Fixed health/terminal utility; controller timing is diagnostic only."""

        return (
            2.0 * float(self.opponent_fainted)
            - 2.0 * float(self.player_fainted)
            + float(self.opponent_damage_fraction)
            - float(self.player_damage_fraction)
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.battle.selected-turn-outcome.v2",
            "move_executed": self.move_executed,
            "opponent_damage_fraction": self.opponent_damage_fraction,
            "player_damage_fraction": self.player_damage_fraction,
            "opponent_fainted": self.opponent_fainted,
            "player_fainted": self.player_fainted,
            "battle_exited": self.battle_exited,
            "actions_executed": self.actions_executed,
            "frames_executed": self.frames_executed,
            "pre_attack_frames": self.pre_attack_frames,
            "utility": self.utility,
        }


@dataclass(frozen=True, slots=True)
class BattleOutcomeExample:
    """All usable move outcomes replayed from one exact starting state."""

    root_lineage_id: str
    initial_state_sha256: str
    partition: ScenarioPartition
    features: BattleFeatureBatch
    outcomes: tuple[BattleTurnOutcome | None, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.root_lineage_id, str) or _SAFE_ID.fullmatch(
            self.root_lineage_id
        ) is None:
            raise BattleOutcomeLearningError("root lineage identity is invalid")
        if not isinstance(self.initial_state_sha256, str) or _SHA256.fullmatch(
            self.initial_state_sha256
        ) is None:
            raise BattleOutcomeLearningError("initial state digest is invalid")
        if not isinstance(self.partition, ScenarioPartition):
            raise BattleOutcomeLearningError("scenario partition is invalid")
        if not isinstance(self.features, BattleFeatureBatch):
            raise BattleOutcomeLearningError("battle feature batch is invalid")
        if not isinstance(self.outcomes, tuple) or len(self.outcomes) != len(
            self.features.candidate_vectors
        ):
            raise BattleOutcomeLearningError("candidate outcomes do not match features")
        usable = self.features.legal_mask
        for index, (is_legal, pp, outcome) in enumerate(
            zip(usable, self.features.current_pp, self.outcomes, strict=True)
        ):
            expected = is_legal and pp > 0
            if expected and not isinstance(outcome, BattleTurnOutcome):
                raise BattleOutcomeLearningError(
                    f"usable candidate {index} lacks a measured outcome"
                )
            if not expected and outcome is not None:
                raise BattleOutcomeLearningError(
                    f"unusable candidate {index} cannot carry an outcome"
                )

    @property
    def best_candidate_indices(self) -> tuple[int, ...]:
        utilities = tuple(
            None if outcome is None else outcome.utility for outcome in self.outcomes
        )
        best = max(value for value in utilities if value is not None)
        return tuple(
            index
            for index, value in enumerate(utilities)
            if value is not None and math.isclose(value, best, abs_tol=_UTILITY_TOLERANCE)
        )

    @property
    def usable_mask(self) -> NDArray[np.bool_]:
        return np.asarray(
            tuple(
                legal and pp > 0
                for legal, pp in zip(
                    self.features.legal_mask,
                    self.features.current_pp,
                    strict=True,
                )
            ),
            dtype=np.bool_,
        )

    @property
    def target_distribution(self) -> NDArray[np.float64]:
        target = np.zeros(len(self.outcomes), dtype=np.float64)
        winners = self.best_candidate_indices
        target[list(winners)] = 1.0 / len(winners)
        return target

    @property
    def learner_update_eligible(self) -> bool:
        """Whether cartridge outcomes distinguish at least one usable action."""

        usable_count = int(np.sum(self.usable_mask))
        return len(self.best_candidate_indices) < usable_count


@dataclass(frozen=True, slots=True)
class BattleOutcomeUpdateReport:
    base_model_sha256: str
    updated_model_sha256: str
    training_example_count: int
    training_root_lineage_ids: tuple[str, ...]
    training_state_sha256: tuple[str, ...]
    loss_before: float
    loss_after: float
    epochs: int
    learning_rate: float
    prior_l2: float

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.battle.outcome-update.v1",
            "base_model_sha256": self.base_model_sha256,
            "updated_model_sha256": self.updated_model_sha256,
            "training_example_count": self.training_example_count,
            "training_root_lineage_ids": list(self.training_root_lineage_ids),
            "training_state_sha256": list(self.training_state_sha256),
            "loss_before": self.loss_before,
            "loss_after": self.loss_after,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "prior_l2": self.prior_l2,
            "authority_promoted": False,
            "teacher_choice_targets": 0,
        }


@dataclass(frozen=True, slots=True)
class BattleOutcomeUpdate:
    model: MaskedMLPMoveRanker
    report: BattleOutcomeUpdateReport


@dataclass(frozen=True, slots=True)
class BattleOutcomeEvaluation:
    model_sha256: str
    example_count: int
    correct_preferences: int
    mean_selected_utility: float
    root_lineage_ids: tuple[str, ...]

    @property
    def preference_accuracy(self) -> float:
        return self.correct_preferences / self.example_count

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.battle.outcome-evaluation.v1",
            "model_sha256": self.model_sha256,
            "partition": ScenarioPartition.DEVELOPMENT.value,
            "example_count": self.example_count,
            "correct_preferences": self.correct_preferences,
            "preference_accuracy": self.preference_accuracy,
            "mean_selected_utility": self.mean_selected_utility,
            "root_lineage_ids": list(self.root_lineage_ids),
            "learner_updates": 0,
            "authority_promoted": False,
        }


@dataclass(frozen=True, slots=True)
class BattleOutcomeLearningCycle:
    update: BattleOutcomeUpdate
    base_development: BattleOutcomeEvaluation
    updated_development: BattleOutcomeEvaluation

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.battle.outcome-learning-cycle.v1",
            "update": self.update.report.public_dict(),
            "base_development": self.base_development.public_dict(),
            "updated_development": self.updated_development.public_dict(),
            "lineage_partition_overlap": 0,
            "initial_state_partition_overlap": 0,
            "sealed_test_cases_opened": 0,
            "authority_promoted": False,
        }


@dataclass(frozen=True, slots=True)
class BattleOutcomePairedEvaluation:
    """Same-state utility comparison between a frozen prior and one update."""

    base_model_sha256: str
    updated_model_sha256: str
    example_count: int
    updated_wins: int
    base_wins: int
    equivalent_choices: int
    base_correct_preferences: int
    updated_correct_preferences: int
    root_lineage_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            _SHA256.fullmatch(self.base_model_sha256) is None
            or _SHA256.fullmatch(self.updated_model_sha256) is None
        ):
            raise BattleOutcomeLearningError("paired evaluation model identity is invalid")
        if type(self.example_count) is not int or self.example_count < 1:  # noqa: E721
            raise BattleOutcomeLearningError("paired evaluation example count is invalid")
        for value, name in (
            (self.updated_wins, "updated win count"),
            (self.base_wins, "base win count"),
            (self.equivalent_choices, "equivalent choice count"),
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise BattleOutcomeLearningError(f"paired evaluation {name} is invalid")
        if (
            self.updated_wins + self.base_wins + self.equivalent_choices
            != self.example_count
        ):
            raise BattleOutcomeLearningError("paired evaluation accounting is invalid")
        for value, name in (
            (self.base_correct_preferences, "base preference count"),
            (self.updated_correct_preferences, "updated preference count"),
        ):
            if type(value) is not int or not 0 <= value <= self.example_count:  # noqa: E721
                raise BattleOutcomeLearningError(f"{name} is invalid")
        if (
            not isinstance(self.root_lineage_ids, tuple)
            or not self.root_lineage_ids
            or len(self.root_lineage_ids) > self.example_count
            or len(self.root_lineage_ids) != len(set(self.root_lineage_ids))
            or any(_SAFE_ID.fullmatch(value) is None for value in self.root_lineage_ids)
        ):
            raise BattleOutcomeLearningError("paired evaluation root lineages are invalid")

    @property
    def discordant_examples(self) -> int:
        return self.updated_wins + self.base_wins

    @property
    def updated_better_one_sided_exact_p(self) -> float:
        """Exact paired sign-test tail; descriptive until a powered gate is frozen."""

        total = self.discordant_examples
        if total == 0:
            return 1.0
        return sum(
            math.comb(total, successes) for successes in range(self.updated_wins, total + 1)
        ) / (2**total)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.battle.outcome-paired-evaluation.v1",
            "partition": ScenarioPartition.DEVELOPMENT.value,
            "base_model_sha256": self.base_model_sha256,
            "updated_model_sha256": self.updated_model_sha256,
            "example_count": self.example_count,
            "updated_wins": self.updated_wins,
            "base_wins": self.base_wins,
            "equivalent_choices": self.equivalent_choices,
            "discordant_examples": self.discordant_examples,
            "updated_better_one_sided_exact_p": self.updated_better_one_sided_exact_p,
            "base_correct_preferences": self.base_correct_preferences,
            "updated_correct_preferences": self.updated_correct_preferences,
            "root_lineage_ids": list(self.root_lineage_ids),
            "inferential_claim": False,
            "learner_updates": 0,
            "authority_promoted": False,
        }


@dataclass(frozen=True, slots=True)
class BattleOutcomeLearningCurvePoint:
    """One from-scratch prior-preserving update at a frozen prefix size."""

    training_size: int
    training_root_lineage_ids: tuple[str, ...]
    training_state_sha256: tuple[str, ...]
    update: BattleOutcomeUpdate | None
    base_development: BattleOutcomeEvaluation
    updated_development: BattleOutcomeEvaluation
    paired_development: BattleOutcomePairedEvaluation

    def __post_init__(self) -> None:
        if type(self.training_size) is not int or self.training_size < 1:  # noqa: E721
            raise BattleOutcomeLearningError("learning-curve training size is invalid")
        if (
            len(self.training_root_lineage_ids) != self.training_size
            or len(self.training_root_lineage_ids)
            != len(set(self.training_root_lineage_ids))
            or any(
                _SAFE_ID.fullmatch(value) is None
                for value in self.training_root_lineage_ids
            )
        ):
            raise BattleOutcomeLearningError("learning-curve training roots are invalid")
        if (
            len(self.training_state_sha256) != self.training_size
            or len(self.training_state_sha256) != len(set(self.training_state_sha256))
            or any(_SHA256.fullmatch(value) is None for value in self.training_state_sha256)
        ):
            raise BattleOutcomeLearningError("learning-curve training states are invalid")
        if not isinstance(self.base_development, BattleOutcomeEvaluation) or not isinstance(
            self.updated_development, BattleOutcomeEvaluation
        ):
            raise BattleOutcomeLearningError("learning-curve development evaluation is invalid")
        if not isinstance(self.paired_development, BattleOutcomePairedEvaluation):
            raise BattleOutcomeLearningError("learning-curve paired evaluation is invalid")
        if (
            self.base_development.example_count
            != self.updated_development.example_count
            or self.base_development.example_count
            != self.paired_development.example_count
            or self.base_development.model_sha256
            != self.paired_development.base_model_sha256
            or self.updated_development.model_sha256
            != self.paired_development.updated_model_sha256
        ):
            raise BattleOutcomeLearningError(
                "learning-curve development evidence does not share one comparison"
            )
        if self.update is None:
            if self.base_development.model_sha256 != self.updated_development.model_sha256:
                raise BattleOutcomeLearningError("a no-update curve point changed the model")
        elif (
            not isinstance(self.update, BattleOutcomeUpdate)
            or self.update.report.training_example_count != self.training_size
            or self.update.report.base_model_sha256
            != self.base_development.model_sha256
            or self.update.report.updated_model_sha256
            != self.updated_development.model_sha256
        ):
            raise BattleOutcomeLearningError("learning-curve update binding is invalid")

    @property
    def status(self) -> str:
        return "updated" if self.update is not None else "insufficient_preference_signal"

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.battle.outcome-learning-curve-point.v1",
            "training_size": self.training_size,
            "training_root_lineage_ids": list(self.training_root_lineage_ids),
            "training_state_sha256": list(self.training_state_sha256),
            "status": self.status,
            "update": None if self.update is None else self.update.report.public_dict(),
            "base_development": self.base_development.public_dict(),
            "updated_development": self.updated_development.public_dict(),
            "paired_development": self.paired_development.public_dict(),
            "authority_promoted": False,
        }


@dataclass(frozen=True, slots=True)
class BattleOutcomeLearningCurve:
    """Descriptive prefix curve over independent roots and one untouched dev set."""

    points: tuple[BattleOutcomeLearningCurvePoint, ...]
    training_order_state_sha256: tuple[str, ...]
    development_root_lineage_ids: tuple[str, ...]
    development_state_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.points, tuple)
            or len(self.points) < 3
            or any(
                not isinstance(point, BattleOutcomeLearningCurvePoint)
                for point in self.points
            )
        ):
            raise BattleOutcomeLearningError("an initial learning curve needs three points")
        sizes = tuple(point.training_size for point in self.points)
        if sizes != tuple(sorted(set(sizes))):
            raise BattleOutcomeLearningError("learning-curve sizes must strictly increase")
        if sizes[-1] != len(self.training_order_state_sha256):
            raise BattleOutcomeLearningError(
                "the final learning-curve point must use every training state"
            )
        if (
            len(self.training_order_state_sha256)
            != len(set(self.training_order_state_sha256))
            or any(
                _SHA256.fullmatch(value) is None
                for value in self.training_order_state_sha256
            )
            or any(
                point.training_state_sha256
                != self.training_order_state_sha256[: point.training_size]
                for point in self.points
            )
        ):
            raise BattleOutcomeLearningError("learning-curve training order is invalid")
        if (
            not self.development_root_lineage_ids
            or len(self.development_root_lineage_ids)
            != len(self.development_state_sha256)
            or len(self.development_root_lineage_ids)
            != len(set(self.development_root_lineage_ids))
            or len(self.development_state_sha256)
            != len(set(self.development_state_sha256))
            or any(
                _SAFE_ID.fullmatch(value) is None
                for value in self.development_root_lineage_ids
            )
            or any(
                _SHA256.fullmatch(value) is None
                for value in self.development_state_sha256
            )
        ):
            raise BattleOutcomeLearningError("learning-curve development catalog is invalid")
        expected_roots = set(self.development_root_lineage_ids)
        if any(
            set(point.base_development.root_lineage_ids) != expected_roots
            or set(point.updated_development.root_lineage_ids) != expected_roots
            or set(point.paired_development.root_lineage_ids) != expected_roots
            for point in self.points
        ):
            raise BattleOutcomeLearningError(
                "learning-curve points do not share the frozen development roots"
            )

    @property
    def training_sizes(self) -> tuple[int, ...]:
        return tuple(point.training_size for point in self.points)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.battle.outcome-learning-curve.v1",
            "training_sizes": list(self.training_sizes),
            "training_order_state_sha256": list(self.training_order_state_sha256),
            "development_root_lineage_ids": list(self.development_root_lineage_ids),
            "development_state_sha256": list(self.development_state_sha256),
            "points": [point.public_dict() for point in self.points],
            "development_reused_for_fitting": False,
            "descriptive_initial_curve": True,
            "inferential_claim": False,
            "sealed_test_cases_opened": 0,
            "teacher_choice_targets": 0,
            "authority_promoted": False,
        }


def adapt_mlp_last_layer_from_outcomes(
    base_model: MaskedMLPMoveRanker,
    examples: Iterable[BattleOutcomeExample],
    *,
    epochs: int = 100,
    learning_rate: float = 0.01,
    prior_l2: float = 0.1,
) -> BattleOutcomeUpdate:
    """Fit the MLP output layer while retaining its learned hidden prior."""

    choices = tuple(examples)
    _require_examples(choices, partition=ScenarioPartition.TRAIN)
    if not any(choice.learner_update_eligible for choice in choices):
        raise BattleOutcomeLearningError(
            "training outcome examples contain no preference signal"
        )
    _require_hyperparameters(epochs, learning_rate, prior_l2)
    if any(example.features.feature_names != base_model.feature_names for example in choices):
        raise BattleOutcomeLearningError("outcome feature schema differs from the base model")

    payload = base_model.to_dict()
    input_weights = np.asarray(payload["input_weights"], dtype=np.float64)
    hidden_bias = np.asarray(payload["hidden_bias"], dtype=np.float64)
    prior_output = np.asarray(payload["output_weights"], dtype=np.float64)
    output = prior_output.copy()
    first_moment = np.zeros_like(output)
    second_moment = np.zeros_like(output)
    beta_one, beta_two, epsilon = 0.9, 0.999, 1e-8
    loss_before = _outcome_loss(base_model, choices)

    for step in range(1, epochs + 1):
        gradient = np.zeros_like(output)
        for example in choices:
            features = np.asarray(example.features.candidate_vectors, dtype=np.float64)
            hidden = np.tanh(features @ input_weights.T + hidden_bias)
            scores = hidden @ output
            usable = example.usable_mask
            probabilities = np.zeros(scores.shape[0], dtype=np.float64)
            shifted = scores[usable] - np.max(scores[usable])
            exponentials = np.exp(shifted)
            probabilities[usable] = exponentials / np.sum(exponentials)
            gradient += hidden.T @ (probabilities - example.target_distribution)
        gradient /= len(choices)
        gradient += prior_l2 * (output - prior_output)
        first_moment = beta_one * first_moment + (1.0 - beta_one) * gradient
        second_moment = beta_two * second_moment + (1.0 - beta_two) * gradient**2
        corrected_first = first_moment / (1.0 - beta_one**step)
        corrected_second = second_moment / (1.0 - beta_two**step)
        output -= learning_rate * corrected_first / (np.sqrt(corrected_second) + epsilon)

    updated = MaskedMLPMoveRanker(
        feature_names=base_model.feature_names,
        feature_schema_id=base_model.feature_schema_id,
        input_weights=input_weights,
        hidden_bias=hidden_bias,
        output_weights=output,
        output_bias=float(payload["output_bias"]),
        training_seed=base_model.training_seed,
    )
    loss_after = _outcome_loss(updated, choices)
    if not loss_after < loss_before:
        raise BattleOutcomeLearningError("bounded outcome update did not reduce training loss")
    base_sha256 = _model_sha256(base_model)
    updated_sha256 = _model_sha256(updated)
    if updated_sha256 == base_sha256:
        raise BattleOutcomeLearningError("bounded outcome update did not change the model")
    return BattleOutcomeUpdate(
        model=updated,
        report=BattleOutcomeUpdateReport(
            base_model_sha256=base_sha256,
            updated_model_sha256=updated_sha256,
            training_example_count=len(choices),
            training_root_lineage_ids=tuple(
                sorted({example.root_lineage_id for example in choices})
            ),
            training_state_sha256=tuple(
                sorted(example.initial_state_sha256 for example in choices)
            ),
            loss_before=loss_before,
            loss_after=loss_after,
            epochs=epochs,
            learning_rate=float(learning_rate),
            prior_l2=float(prior_l2),
        ),
    )


def evaluate_battle_outcome_preferences(
    model: MaskedMLPMoveRanker,
    examples: Iterable[BattleOutcomeExample],
) -> BattleOutcomeEvaluation:
    """Measure preference quality on development examples without fitting."""

    choices = tuple(examples)
    _require_examples(choices, partition=ScenarioPartition.DEVELOPMENT)
    if any(example.features.feature_names != model.feature_names for example in choices):
        raise BattleOutcomeLearningError("development features differ from the model schema")
    model_sha256 = _model_sha256(model)
    correct = 0
    selected_utilities: list[float] = []
    for example in choices:
        selected = model.predict(
            example.features.candidate_vectors,
            legal_mask=example.features.legal_mask,
            current_pp=example.features.current_pp,
        )
        correct += int(selected in example.best_candidate_indices)
        outcome = example.outcomes[selected]
        if outcome is None:  # pragma: no cover - masked prediction invariant
            raise AssertionError("masked model selected an unusable candidate")
        selected_utilities.append(outcome.utility)
    if _model_sha256(model) != model_sha256:
        raise BattleOutcomeLearningError("development evaluation mutated the model")
    return BattleOutcomeEvaluation(
        model_sha256=model_sha256,
        example_count=len(choices),
        correct_preferences=correct,
        mean_selected_utility=float(np.mean(selected_utilities)),
        root_lineage_ids=tuple(sorted({example.root_lineage_id for example in choices})),
    )


def run_battle_outcome_learning_cycle(
    base_model: MaskedMLPMoveRanker,
    *,
    training_examples: Iterable[BattleOutcomeExample],
    development_examples: Iterable[BattleOutcomeExample],
    epochs: int = 100,
    learning_rate: float = 0.01,
    prior_l2: float = 0.1,
) -> BattleOutcomeLearningCycle:
    """Update on train roots and evaluate both models on untouched roots."""

    training = tuple(training_examples)
    development = tuple(development_examples)
    _require_examples(training, partition=ScenarioPartition.TRAIN)
    _require_examples(development, partition=ScenarioPartition.DEVELOPMENT)
    training_roots = {example.root_lineage_id for example in training}
    development_roots = {example.root_lineage_id for example in development}
    if training_roots & development_roots:
        raise BattleOutcomeLearningError("root lineage crosses train and development")
    training_states = {example.initial_state_sha256 for example in training}
    development_states = {example.initial_state_sha256 for example in development}
    if training_states & development_states:
        raise BattleOutcomeLearningError("initial state crosses train and development")

    update = adapt_mlp_last_layer_from_outcomes(
        base_model,
        training,
        epochs=epochs,
        learning_rate=learning_rate,
        prior_l2=prior_l2,
    )
    return BattleOutcomeLearningCycle(
        update=update,
        base_development=evaluate_battle_outcome_preferences(base_model, development),
        updated_development=evaluate_battle_outcome_preferences(update.model, development),
    )


def compare_battle_outcome_preferences(
    base_model: MaskedMLPMoveRanker,
    updated_model: MaskedMLPMoveRanker,
    examples: Iterable[BattleOutcomeExample],
) -> BattleOutcomePairedEvaluation:
    """Compare selected utilities on the exact same untouched examples."""

    choices = tuple(examples)
    _require_examples(choices, partition=ScenarioPartition.DEVELOPMENT)
    if any(
        example.features.feature_names != base_model.feature_names
        or example.features.feature_names != updated_model.feature_names
        for example in choices
    ):
        raise BattleOutcomeLearningError("paired development features differ from a model schema")
    base_sha256 = _model_sha256(base_model)
    updated_sha256 = _model_sha256(updated_model)
    updated_wins = base_wins = equivalent = 0
    base_correct = updated_correct = 0
    for example in choices:
        base_index = _selected_candidate(base_model, example)
        updated_index = _selected_candidate(updated_model, example)
        base_correct += int(base_index in example.best_candidate_indices)
        updated_correct += int(updated_index in example.best_candidate_indices)
        base_outcome = example.outcomes[base_index]
        updated_outcome = example.outcomes[updated_index]
        if base_outcome is None or updated_outcome is None:  # pragma: no cover - mask invariant
            raise AssertionError("masked model selected an unusable candidate")
        difference = updated_outcome.utility - base_outcome.utility
        if math.isclose(difference, 0.0, abs_tol=_UTILITY_TOLERANCE):
            equivalent += 1
        elif difference > 0:
            updated_wins += 1
        else:
            base_wins += 1
    if _model_sha256(base_model) != base_sha256 or _model_sha256(updated_model) != updated_sha256:
        raise BattleOutcomeLearningError("paired development evaluation mutated a model")
    return BattleOutcomePairedEvaluation(
        base_model_sha256=base_sha256,
        updated_model_sha256=updated_sha256,
        example_count=len(choices),
        updated_wins=updated_wins,
        base_wins=base_wins,
        equivalent_choices=equivalent,
        base_correct_preferences=base_correct,
        updated_correct_preferences=updated_correct,
        root_lineage_ids=tuple(sorted({example.root_lineage_id for example in choices})),
    )


def run_battle_outcome_learning_curve(
    base_model: MaskedMLPMoveRanker,
    *,
    training_examples: Iterable[BattleOutcomeExample],
    development_examples: Iterable[BattleOutcomeExample],
    training_sizes: tuple[int, ...],
    epochs: int = 100,
    learning_rate: float = 0.01,
    prior_l2: float = 0.1,
) -> BattleOutcomeLearningCurve:
    """Fit frozen prefixes from the same prior and score one untouched dev set.

    The caller-provided training order is part of the prospective design.  Flat
    prefixes remain in the curve as typed no-update points; they are never
    replaced after observing their outcomes.
    """

    training = tuple(training_examples)
    development = tuple(development_examples)
    _require_examples(training, partition=ScenarioPartition.TRAIN)
    _require_examples(development, partition=ScenarioPartition.DEVELOPMENT)
    _require_independent_curve_roots(training, subject="training")
    _require_independent_curve_roots(development, subject="development")
    _require_disjoint_partitions(training, development)
    _require_curve_sizes(training_sizes, training_count=len(training))
    _require_hyperparameters(epochs, learning_rate, prior_l2)

    base_development = evaluate_battle_outcome_preferences(base_model, development)
    points: list[BattleOutcomeLearningCurvePoint] = []
    for size in training_sizes:
        prefix = training[:size]
        update = (
            adapt_mlp_last_layer_from_outcomes(
                base_model,
                prefix,
                epochs=epochs,
                learning_rate=learning_rate,
                prior_l2=prior_l2,
            )
            if any(example.learner_update_eligible for example in prefix)
            else None
        )
        updated_model = base_model if update is None else update.model
        updated_development = evaluate_battle_outcome_preferences(
            updated_model,
            development,
        )
        points.append(
            BattleOutcomeLearningCurvePoint(
                training_size=size,
                training_root_lineage_ids=tuple(
                    example.root_lineage_id for example in prefix
                ),
                training_state_sha256=tuple(
                    example.initial_state_sha256 for example in prefix
                ),
                update=update,
                base_development=base_development,
                updated_development=updated_development,
                paired_development=compare_battle_outcome_preferences(
                    base_model,
                    updated_model,
                    development,
                ),
            )
        )
    return BattleOutcomeLearningCurve(
        points=tuple(points),
        training_order_state_sha256=tuple(
            example.initial_state_sha256 for example in training
        ),
        development_root_lineage_ids=tuple(
            example.root_lineage_id for example in development
        ),
        development_state_sha256=tuple(
            example.initial_state_sha256 for example in development
        ),
    )


def _require_examples(
    examples: tuple[BattleOutcomeExample, ...],
    *,
    partition: ScenarioPartition,
) -> None:
    if not examples or any(not isinstance(value, BattleOutcomeExample) for value in examples):
        raise BattleOutcomeLearningError("outcome examples are invalid")
    if any(value.partition is not partition for value in examples):
        raise BattleOutcomeLearningError(
            f"outcome examples must belong to the {partition.value} partition"
        )
    states = [value.initial_state_sha256 for value in examples]
    if len(states) != len(set(states)):
        raise BattleOutcomeLearningError("outcome examples duplicate an initial state")


def _require_hyperparameters(epochs: int, learning_rate: float, prior_l2: float) -> None:
    if type(epochs) is not int or epochs < 1:  # noqa: E721
        raise BattleOutcomeLearningError("epochs must be a positive integer")
    for value, name, positive in (
        (learning_rate, "learning_rate", True),
        (prior_l2, "prior_l2", False),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (float(value) <= 0 if positive else float(value) < 0)
        ):
            raise BattleOutcomeLearningError(f"{name} is invalid")


def _require_independent_curve_roots(
    examples: tuple[BattleOutcomeExample, ...],
    *,
    subject: str,
) -> None:
    roots = tuple(example.root_lineage_id for example in examples)
    if len(roots) != len(set(roots)):
        raise BattleOutcomeLearningError(
            f"battle learning curve requires one independent {subject} root per example"
        )


def _require_disjoint_partitions(
    training: tuple[BattleOutcomeExample, ...],
    development: tuple[BattleOutcomeExample, ...],
) -> None:
    if {example.root_lineage_id for example in training} & {
        example.root_lineage_id for example in development
    }:
        raise BattleOutcomeLearningError("root lineage crosses train and development")
    if {example.initial_state_sha256 for example in training} & {
        example.initial_state_sha256 for example in development
    }:
        raise BattleOutcomeLearningError("initial state crosses train and development")


def _require_curve_sizes(
    sizes: tuple[int, ...],
    *,
    training_count: int,
) -> None:
    if (
        not isinstance(sizes, tuple)
        or len(sizes) < 3
        or any(type(value) is not int or value < 1 for value in sizes)  # noqa: E721
        or sizes != tuple(sorted(set(sizes)))
    ):
        raise BattleOutcomeLearningError(
            "battle learning curve needs at least three strictly increasing positive sizes"
        )
    if sizes[-1] != training_count:
        raise BattleOutcomeLearningError(
            "battle learning curve final size must consume the complete training catalog"
        )


def _selected_candidate(
    model: MaskedMLPMoveRanker,
    example: BattleOutcomeExample,
) -> int:
    return model.predict(
        example.features.candidate_vectors,
        legal_mask=example.features.legal_mask,
        current_pp=example.features.current_pp,
    )


def _outcome_loss(
    model: MaskedMLPMoveRanker,
    examples: tuple[BattleOutcomeExample, ...],
) -> float:
    losses = []
    for example in examples:
        try:
            probabilities = model.predict_proba(
                example.features.candidate_vectors,
                legal_mask=example.features.legal_mask,
                current_pp=example.features.current_pp,
            )
        except BattleModelValidationError as error:
            raise BattleOutcomeLearningError("model rejected outcome features") from error
        target = example.target_distribution
        selected = target > 0
        losses.append(float(-np.sum(target[selected] * np.log(probabilities[selected]))))
    return float(np.mean(losses))


def _model_sha256(model: MaskedMLPMoveRanker) -> str:
    return hashlib.sha256(model.to_json().encode("ascii")).hexdigest()
