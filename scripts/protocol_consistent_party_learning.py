"""Train-only party utility learning with a frozen, title-neutral protocol.

The earlier shared MLP could reduce training loss while becoming less calibrated
on every newly completed development question.  This module deliberately makes
the next falsifier smaller:

* the historical teacher-derived prior is frozen and must have zero outcome
  updates;
* trainee and venue choices receive separate residual heads;
* only a frozen hidden representation and compact title-neutral semantic groups
  are exposed to those heads, including explicit goal-conditioned venue terms;
* every fully measured candidate ordering contributes menu-normalized pairwise
  targets; and
* evaluation is deterministic leave-one-root-out over train roots only.

No species, map, route, title, candidate position, or teacher choice enters the
representation or target.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeModel,
    canonical_party_development_outcome_model_sha256,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.scenario_lab import ScenarioFamily, ScenarioPartition
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeExample
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PROTOCOL_PARTY_RANKER_ID = "pokemon.core.party-development.protocol-residual.v2"
PROTOCOL_DESIGN_ID = "pokemon.red.party-development.train-only-architecture-selection.v2"
PROTOCOL_PAIRWISE_RIDGE = 4.0
PROTOCOL_NEWTON_STEPS = 64
PROTOCOL_OPTIMIZER_TOLERANCE = 1e-10
PROTOCOL_TOLERANCE = 1e-12
_PORTABLE_BASE_GROUP_NAMES = (
    "portable.goal_alignment",
    "portable.safety_resource",
    "portable.escort_feasibility",
    "portable.venue_quality",
    "portable.venue_safety",
    "portable.venue_cost",
)
_VENUE_INTERACTION_COMPONENTS = ("quality", "safety", "cost")
VENUE_INTERACTION_GROUP_NAMES = tuple(
    f"portable.goal_{goal.value}.venue_{component}"
    for goal in PartyDevelopmentGoal
    for component in _VENUE_INTERACTION_COMPONENTS
)
PORTABLE_GROUP_NAMES = (*_PORTABLE_BASE_GROUP_NAMES, *VENUE_INTERACTION_GROUP_NAMES)


class ProtocolPartyLearningError(ValueError):
    """Raised when the train-only protocol or representation is crossed."""


@dataclass(frozen=True, slots=True)
class ProtocolPartyRanker:
    """Two residual heads over one frozen prior representation."""

    base_model_sha256: str
    representation_names: tuple[str, ...]
    trainee_weights: NDArray[np.float64]
    venue_weights: NDArray[np.float64]
    training_lineages: tuple[tuple[str, str], ...]
    ridge: float = PROTOCOL_PAIRWISE_RIDGE
    model_id: str = PROTOCOL_PARTY_RANKER_ID

    def __post_init__(self) -> None:
        if (
            self.model_id != PROTOCOL_PARTY_RANKER_ID
            or not _is_sha256(self.base_model_sha256)
            or not self.representation_names
            or len(self.representation_names) != len(set(self.representation_names))
        ):
            raise ProtocolPartyLearningError("protocol ranker identity is invalid")
        if (
            not isinstance(self.training_lineages, tuple)
            or not self.training_lineages
            or tuple(sorted(self.training_lineages)) != self.training_lineages
            or len({root for root, _state in self.training_lineages}) != len(self.training_lineages)
            or len({state for _root, state in self.training_lineages})
            != len(self.training_lineages)
            or any(not root or not _is_sha256(state) for root, state in self.training_lineages)
        ):
            raise ProtocolPartyLearningError("protocol training lineages are invalid")
        if self.ridge != PROTOCOL_PAIRWISE_RIDGE:
            raise ProtocolPartyLearningError("protocol ridge differs from the frozen value")
        for value, subject in (
            (self.trainee_weights, "trainee"),
            (self.venue_weights, "venue"),
        ):
            weights = np.asarray(value, dtype=np.float64)
            if weights.shape != (len(self.representation_names),) or not np.all(
                np.isfinite(weights)
            ):
                raise ProtocolPartyLearningError(f"protocol {subject} weights are invalid")
            detached = weights.copy()
            detached.setflags(write=False)
            object.__setattr__(self, f"{subject}_weights", detached)

    def scores(
        self,
        base_model: PartyDevelopmentOutcomeModel,
        example: ScenarioOutcomeExample,
    ) -> NDArray[np.float64]:
        """Score one identity-free menu without mutating the frozen prior."""

        _require_base_model(base_model)
        if canonical_party_development_outcome_model_sha256(base_model) != self.base_model_sha256:
            raise ProtocolPartyLearningError("protocol prior identity differs")
        if self.representation_names != _representation_names(base_model):
            raise ProtocolPartyLearningError("protocol representation names differ")
        _require_example(example)
        kind = _choice_kind(example)
        base_scores, representation = _representation(base_model, example)
        weights = self.trainee_weights if kind is TrainingChoiceKind.TRAINEE else self.venue_weights
        scores = base_scores + representation @ weights
        if scores.shape != (len(example.candidates),) or not np.all(np.isfinite(scores)):
            raise ProtocolPartyLearningError("protocol candidate scores are invalid")
        return scores

    def to_dict(self) -> dict[str, object]:
        return {
            "base_model_sha256": self.base_model_sha256,
            "feature_schema_id": PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
            "model_id": self.model_id,
            "pairwise_menu_normalized": True,
            "representation_names": list(self.representation_names),
            "ridge": self.ridge,
            "separate_action_heads": True,
            "trainee_weights": self.trainee_weights.tolist(),
            "training_lineages": [
                {"root_lineage_id": root, "state_sha256": state}
                for root, state in self.training_lineages
            ],
            "venue_weights": self.venue_weights.tolist(),
        }

    @classmethod
    def from_dict(cls, value: object) -> ProtocolPartyRanker:
        """Load one strictly typed model and reject lossy or widened schemas."""

        expected_keys = {
            "base_model_sha256",
            "feature_schema_id",
            "model_id",
            "pairwise_menu_normalized",
            "representation_names",
            "ridge",
            "separate_action_heads",
            "trainee_weights",
            "training_lineages",
            "venue_weights",
        }
        if not isinstance(value, Mapping) or set(value) != expected_keys:
            raise ProtocolPartyLearningError("protocol model schema is invalid")
        names = value.get("representation_names")
        lineages = value.get("training_lineages")
        base_model_sha256 = value.get("base_model_sha256")
        expected_names = (
            (
                "frozen_prior.score_adjustment",
                *(
                    f"frozen_hidden.{index}"
                    for index in range(len(names) - len(PORTABLE_GROUP_NAMES) - 1)
                ),
                *PORTABLE_GROUP_NAMES,
            )
            if isinstance(names, list)
            else ()
        )
        if (
            not _is_sha256(base_model_sha256)
            or not isinstance(base_model_sha256, str)
            or value.get("feature_schema_id") != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
            or value.get("model_id") != PROTOCOL_PARTY_RANKER_ID
            or value.get("pairwise_menu_normalized") is not True
            or value.get("separate_action_heads") is not True
            or type(value.get("ridge")) is not float  # noqa: E721
            or value.get("ridge") != PROTOCOL_PAIRWISE_RIDGE
            or not isinstance(names, list)
            or not names
            or any(not isinstance(item, str) or not item for item in names)
            or tuple(names) != expected_names
            or not isinstance(lineages, list)
            or not lineages
        ):
            raise ProtocolPartyLearningError("protocol model identity is invalid")
        parsed_lineages: list[tuple[str, str]] = []
        for item in lineages:
            if not isinstance(item, Mapping) or set(item) != {
                "root_lineage_id",
                "state_sha256",
            }:
                raise ProtocolPartyLearningError("protocol model lineage is invalid")
            root = item.get("root_lineage_id")
            state = item.get("state_sha256")
            if (
                not isinstance(root, str)
                or not root
                or not isinstance(state, str)
                or not _is_sha256(state)
            ):
                raise ProtocolPartyLearningError("protocol model lineage is invalid")
            parsed_lineages.append((root, state))

        def weights(subject: str) -> NDArray[np.float64]:
            raw = value.get(subject)
            if (
                not isinstance(raw, list)
                or len(raw) != len(names)
                or any(
                    isinstance(item, bool)
                    or type(item) is not float  # noqa: E721
                    or not math.isfinite(float(item))
                    for item in raw
                )
            ):
                raise ProtocolPartyLearningError(f"protocol model {subject} are invalid")
            return np.asarray(raw, dtype=np.float64)

        model = cls(
            base_model_sha256=base_model_sha256,
            representation_names=tuple(names),
            trainee_weights=weights("trainee_weights"),
            venue_weights=weights("venue_weights"),
            training_lineages=tuple(parsed_lineages),
        )
        if model.to_dict() != dict(value):
            raise ProtocolPartyLearningError("protocol model does not round-trip exactly")
        return model


@dataclass(frozen=True, slots=True)
class ProtocolMetrics:
    example_count: int
    correct_preferences: int
    cross_entropy: float
    mean_winner_probability: float

    @property
    def accuracy(self) -> float:
        return self.correct_preferences / self.example_count

    def public_dict(self) -> dict[str, object]:
        return {
            "accuracy": self.accuracy,
            "correct_preferences": self.correct_preferences,
            "cross_entropy": self.cross_entropy,
            "example_count": self.example_count,
            "mean_winner_probability": self.mean_winner_probability,
        }


@dataclass(frozen=True, slots=True)
class ProtocolMetricPair:
    base: ProtocolMetrics
    updated: ProtocolMetrics

    def public_dict(self) -> dict[str, object]:
        return {"base": self.base.public_dict(), "updated": self.updated.public_dict()}


@dataclass(frozen=True, slots=True)
class ProtocolRepresentationAudit:
    """Deterministic pre-fit falsifier for the fixed representation."""

    action_goal_counts: Mapping[str, int]
    pairwise_rows_by_action: Mapping[str, int]
    effective_rank_by_action: Mapping[str, int]
    required_rank_by_action: Mapping[str, int]
    nonzero_design_by_action_goal: Mapping[str, bool]
    venue_interaction_variance: Mapping[str, bool]
    contradictory_pairwise_rows: int
    passed: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "action_goal_counts": dict(sorted(self.action_goal_counts.items())),
            "contradictory_pairwise_rows": self.contradictory_pairwise_rows,
            "effective_rank_by_action": dict(sorted(self.effective_rank_by_action.items())),
            "nonzero_design_by_action_goal": dict(
                sorted(self.nonzero_design_by_action_goal.items())
            ),
            "pairwise_rows_by_action": dict(sorted(self.pairwise_rows_by_action.items())),
            "passed": self.passed,
            "required_rank_by_action": dict(sorted(self.required_rank_by_action.items())),
            "schema": "pokemon.red.protocol-party-representation-audit.v1",
            "venue_interaction_variance": dict(sorted(self.venue_interaction_variance.items())),
        }


@dataclass(frozen=True, slots=True)
class ProtocolLeaveOneRootOutEvaluation:
    """Train-root architecture-selection result for one frozen design."""

    overall: ProtocolMetricPair
    by_action: Mapping[str, ProtocolMetricPair]
    by_goal: Mapping[str, ProtocolMetricPair]
    updated_wins: int
    base_wins: int
    correctness_ties: int
    winner_probability_improvements: int
    winner_probability_regressions: int
    winner_probability_ties: int
    passed: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "base_wins": self.base_wins,
            "by_action": {
                key: value.public_dict() for key, value in sorted(self.by_action.items())
            },
            "by_goal": {key: value.public_dict() for key, value in sorted(self.by_goal.items())},
            "correctness_ties": self.correctness_ties,
            "evidence_class": "train_only_architecture_selection_not_independent_generalization",
            "evaluation": "deterministic_leave_one_root_out_train_roots_only",
            "overall": self.overall.public_dict(),
            "pass_rule": {
                "every_action_slice_must_not_regress": True,
                "every_goal_slice_must_not_regress": True,
                "cross_entropy_must_decrease": True,
                "mean_winner_probability_must_increase": True,
                "overall_accuracy_must_increase": True,
                "updated_paired_wins_must_exceed_base_wins": True,
            },
            "passed": self.passed,
            "updated_wins": self.updated_wins,
            "winner_probability_improvements": self.winner_probability_improvements,
            "winner_probability_regressions": self.winner_probability_regressions,
            "winner_probability_ties": self.winner_probability_ties,
        }


@dataclass(frozen=True, slots=True)
class ProtocolPartyLearningResult:
    model: ProtocolPartyRanker
    evaluation: ProtocolLeaveOneRootOutEvaluation
    representation_audit: ProtocolRepresentationAudit


def run_protocol_party_leave_one_root_out(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
) -> ProtocolPartyLearningResult:
    """Fit one frozen design and evaluate it on held-out train roots only."""

    choices = tuple(examples)
    _require_base_model(base_model)
    _require_training_examples(base_model, choices)
    representation_audit = audit_protocol_party_representation(base_model, choices)
    if not representation_audit.passed:
        raise ProtocolPartyLearningError("protocol representation audit did not pass")
    ordered = tuple(sorted(choices, key=lambda item: item.root_lineage_id))
    base_probabilities: list[NDArray[np.float64]] = []
    updated_probabilities: list[NDArray[np.float64]] = []
    for held_out in ordered:
        fold_training = tuple(
            item for item in ordered if item.root_lineage_id != held_out.root_lineage_id
        )
        fold_model = _fit_protocol_ranker(base_model, fold_training)
        base_scores, _features = _representation(base_model, held_out)
        base_probabilities.append(_masked_probabilities(base_scores, held_out))
        updated_probabilities.append(
            _masked_probabilities(fold_model.scores(base_model, held_out), held_out)
        )
    metric_pair = _metric_pair(ordered, base_probabilities, updated_probabilities)
    by_action = {
        kind.value: _metric_pair_for_indices(
            ordered,
            base_probabilities,
            updated_probabilities,
            tuple(index for index, example in enumerate(ordered) if _choice_kind(example) is kind),
        )
        for kind in TrainingChoiceKind
    }
    goals = tuple(sorted({_goal(item) for item in ordered}, key=lambda item: item.value))
    if not {
        PartyDevelopmentGoal.COLLECTION,
        PartyDevelopmentGoal.EVOLUTION,
    }.issubset(goals):
        raise ProtocolPartyLearningError("protocol training set lacks living-Pokedex goals")
    by_goal = {
        goal.value: _metric_pair_for_indices(
            ordered,
            base_probabilities,
            updated_probabilities,
            tuple(index for index, example in enumerate(ordered) if _goal(example) is goal),
        )
        for goal in goals
    }
    paired = _paired_counts(ordered, base_probabilities, updated_probabilities)
    passed = _evaluation_passed(metric_pair, by_action, by_goal, paired)
    evaluation = ProtocolLeaveOneRootOutEvaluation(
        overall=metric_pair,
        by_action=by_action,
        by_goal=by_goal,
        updated_wins=paired[0],
        base_wins=paired[1],
        correctness_ties=paired[2],
        winner_probability_improvements=paired[3],
        winner_probability_regressions=paired[4],
        winner_probability_ties=paired[5],
        passed=passed,
    )
    return ProtocolPartyLearningResult(
        model=_fit_protocol_ranker(base_model, ordered),
        evaluation=evaluation,
        representation_audit=representation_audit,
    )


def audit_protocol_party_representation(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
) -> ProtocolRepresentationAudit:
    """Falsify unusable or contradictory train designs before any fit begins."""

    choices = tuple(examples)
    _require_base_model(base_model)
    _require_training_examples(base_model, choices)
    action_goal_counts: Counter[str] = Counter()
    nonzero_design: dict[str, bool] = {}
    venue_variance: dict[str, bool] = {}
    pairwise_rows_by_action: dict[str, int] = {}
    rank_by_action: dict[str, int] = {}
    required_rank_by_action: dict[str, int] = {}
    contradiction_rows: list[tuple[str, NDArray[np.float64], float]] = []
    representation_names = _representation_names(base_model)

    for example in choices:
        action_goal_counts[f"{_choice_kind(example).value}:{_goal(example).value}"] += 1

    for kind in TrainingChoiceKind:
        action_examples = tuple(item for item in choices if _choice_kind(item) is kind)
        rows, offsets, targets, _weights = _pairwise_rows(base_model, action_examples)
        pairwise_rows_by_action[kind.value] = rows.shape[0]
        rank_by_action[kind.value] = int(
            np.linalg.matrix_rank(rows, tol=PROTOCOL_OPTIMIZER_TOLERANCE)
        )
        goals = tuple(
            sorted({_goal(item) for item in action_examples}, key=lambda item: item.value)
        )
        required_rank_by_action[kind.value] = len(goals)
        for goal in goals:
            key = f"{kind.value}:{goal.value}"
            stratum = tuple(item for item in action_examples if _goal(item) is goal)
            stratum_rows, _offsets, _targets, _sample_weights = _pairwise_rows(
                base_model,
                stratum,
            )
            nonzero_design[key] = bool(np.any(np.abs(stratum_rows) > PROTOCOL_OPTIMIZER_TOLERANCE))
            if kind is TrainingChoiceKind.VENUE:
                for component in _VENUE_INTERACTION_COMPONENTS:
                    name = f"portable.goal_{goal.value}.venue_{component}"
                    index = representation_names.index(name)
                    venue_variance[f"{key}:{component}"] = any(
                        float(
                            np.ptp(
                                _representation(base_model, item)[1][
                                    list(item.available_candidate_indices), index
                                ]
                            )
                        )
                        > PROTOCOL_OPTIMIZER_TOLERANCE
                        for item in stratum
                    )
        for row, offset, target in zip(rows, offsets, targets, strict=True):
            vector, canonical_target = _canonical_pairwise_direction(
                np.concatenate((np.asarray([offset], dtype=np.float64), row)),
                float(target),
            )
            contradiction_rows.append((kind.value, vector, canonical_target))

    contradictions = 0
    for index, (kind, vector, target) in enumerate(contradiction_rows):
        for other_kind, other_vector, other_target in contradiction_rows[index + 1 :]:
            if (
                kind == other_kind
                and np.allclose(
                    vector,
                    other_vector,
                    rtol=1e-9,
                    atol=PROTOCOL_OPTIMIZER_TOLERANCE,
                )
                and abs(target - other_target) > PROTOCOL_TOLERANCE
            ):
                contradictions += 1
    passed = (
        all(nonzero_design.values())
        and all(venue_variance.values())
        and all(
            rank_by_action[action] >= required_rank_by_action[action] for action in rank_by_action
        )
        and contradictions == 0
    )
    return ProtocolRepresentationAudit(
        action_goal_counts=dict(sorted(action_goal_counts.items())),
        pairwise_rows_by_action=pairwise_rows_by_action,
        effective_rank_by_action=rank_by_action,
        required_rank_by_action=required_rank_by_action,
        nonzero_design_by_action_goal=nonzero_design,
        venue_interaction_variance=venue_variance,
        contradictory_pairwise_rows=contradictions,
        passed=passed,
    )


def _canonical_pairwise_direction(
    vector: NDArray[np.float64],
    target: float,
) -> tuple[NDArray[np.float64], float]:
    nonzero = np.flatnonzero(np.abs(vector) > PROTOCOL_OPTIMIZER_TOLERANCE)
    if nonzero.size and vector[int(nonzero[0])] < 0:
        return -vector, 1.0 - target
    return vector, target


def _evaluation_passed(
    overall: ProtocolMetricPair,
    by_action: Mapping[str, ProtocolMetricPair],
    by_goal: Mapping[str, ProtocolMetricPair],
    paired: tuple[int, int, int, int, int, int],
) -> bool:
    return (
        _strictly_greater(overall.updated.accuracy, overall.base.accuracy)
        and _strictly_less(overall.updated.cross_entropy, overall.base.cross_entropy)
        and _strictly_greater(
            overall.updated.mean_winner_probability,
            overall.base.mean_winner_probability,
        )
        and paired[0] > paired[1]
        and all(_slice_did_not_regress(pair) for pair in by_action.values())
        and all(_slice_did_not_regress(pair) for pair in by_goal.values())
    )


def canonical_protocol_party_ranker_sha256(model: ProtocolPartyRanker) -> str:
    payload = json.dumps(
        model.to_dict(),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _fit_protocol_ranker(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Sequence[ScenarioOutcomeExample],
) -> ProtocolPartyRanker:
    names = _representation_names(base_model)
    weights: dict[TrainingChoiceKind, NDArray[np.float64]] = {}
    for kind in TrainingChoiceKind:
        kind_examples = tuple(item for item in examples if _choice_kind(item) is kind)
        if not kind_examples:
            raise ProtocolPartyLearningError(f"protocol fold lacks {kind.value} training evidence")
        rows, offsets, targets, sample_weights = _pairwise_rows(
            base_model,
            kind_examples,
        )
        weights[kind] = _fit_pairwise_residual(
            rows,
            offsets,
            targets,
            sample_weights,
        )
    lineages = tuple(sorted((item.root_lineage_id, item.initial_state_sha256) for item in examples))
    return ProtocolPartyRanker(
        base_model_sha256=canonical_party_development_outcome_model_sha256(base_model),
        representation_names=names,
        trainee_weights=weights[TrainingChoiceKind.TRAINEE],
        venue_weights=weights[TrainingChoiceKind.VENUE],
        training_lineages=lineages,
    )


def _pairwise_rows(
    base_model: PartyDevelopmentOutcomeModel,
    examples: tuple[ScenarioOutcomeExample, ...],
) -> tuple[
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
]:
    rows: list[NDArray[np.float64]] = []
    offsets: list[float] = []
    targets: list[float] = []
    sample_weights: list[float] = []
    menu_weight = 1.0 / len(examples)
    for example in examples:
        base_scores, representation = _representation(base_model, example)
        available = example.available_candidate_indices
        pairs = tuple(
            (left, right)
            for position, left in enumerate(available)
            for right in available[position + 1 :]
        )
        if not pairs:
            raise ProtocolPartyLearningError("protocol menu has no candidate pairs")
        pair_weight = menu_weight / len(pairs)
        for left, right in pairs:
            left_outcome = example.outcomes[left]
            right_outcome = example.outcomes[right]
            if left_outcome is None or right_outcome is None:
                raise ProtocolPartyLearningError("protocol pairwise target is not fully measured")
            left_key = example.objective.preference_key(left_outcome.criterion_values)
            right_key = example.objective.preference_key(right_outcome.criterion_values)
            target = 0.5 if left_key == right_key else float(left_key > right_key)
            rows.append(representation[left] - representation[right])
            offsets.append(float(base_scores[left] - base_scores[right]))
            targets.append(target)
            sample_weights.append(pair_weight)
    return (
        np.asarray(rows, dtype=np.float64),
        np.asarray(offsets, dtype=np.float64),
        np.asarray(targets, dtype=np.float64),
        np.asarray(sample_weights, dtype=np.float64),
    )


def _fit_pairwise_residual(
    rows: NDArray[np.float64],
    offsets: NDArray[np.float64],
    targets: NDArray[np.float64],
    sample_weights: NDArray[np.float64],
    *,
    maximum_steps: int = PROTOCOL_NEWTON_STEPS,
) -> NDArray[np.float64]:
    if (
        rows.ndim != 2
        or offsets.shape != (rows.shape[0],)
        or targets.shape != offsets.shape
        or sample_weights.shape != offsets.shape
        or not np.all(np.isfinite(rows))
        or not np.all(np.isfinite(offsets))
        or not np.all(np.isfinite(targets))
        or not np.all(sample_weights > 0)
        or not math.isclose(float(np.sum(sample_weights)), 1.0)
        or type(maximum_steps) is not int  # noqa: E721
        or maximum_steps < 1
    ):
        raise ProtocolPartyLearningError("protocol pairwise design is invalid")
    weights = np.zeros(rows.shape[1], dtype=np.float64)
    converged = False
    for _step in range(maximum_steps):
        logits = offsets + rows @ weights
        probabilities = _sigmoid(logits)
        gradient = rows.T @ (sample_weights * (probabilities - targets))
        gradient += PROTOCOL_PAIRWISE_RIDGE * weights
        curvature = sample_weights * probabilities * (1.0 - probabilities)
        hessian = (rows.T * curvature) @ rows
        hessian += PROTOCOL_PAIRWISE_RIDGE * np.eye(rows.shape[1])
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError as error:
            raise ProtocolPartyLearningError("protocol pairwise optimizer is singular") from error
        weights -= step
        if float(np.linalg.norm(step, ord=np.inf)) <= PROTOCOL_OPTIMIZER_TOLERANCE:
            converged = True
            break
    if not np.all(np.isfinite(weights)) or not converged:
        raise ProtocolPartyLearningError("protocol pairwise optimizer did not converge")
    return weights


def _representation(
    base_model: PartyDevelopmentOutcomeModel,
    example: ScenarioOutcomeExample,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    features = np.asarray(
        [candidate.features for candidate in example.candidates],
        dtype=np.float64,
    )
    normalized = (features - base_model.feature_mean) / base_model.feature_scale
    hidden = np.tanh(normalized @ base_model.weights1 + base_model.bias1)
    base_scores = hidden @ base_model.weights2
    portable = np.asarray(
        [_portable_groups(row, goal=_goal(example)) for row in features],
        dtype=np.float64,
    )
    representation = np.column_stack((base_scores, hidden, portable))
    if representation.shape != (
        len(example.candidates),
        len(_representation_names(base_model)),
    ) or not np.all(np.isfinite(representation)):
        raise ProtocolPartyLearningError("protocol representation is invalid")
    return base_scores, representation


def _representation_names(
    base_model: PartyDevelopmentOutcomeModel,
) -> tuple[str, ...]:
    return (
        "frozen_prior.score_adjustment",
        *(f"frozen_hidden.{index}" for index in range(base_model.weights2.shape[0])),
        *PORTABLE_GROUP_NAMES,
    )


def _portable_groups(
    features: NDArray[np.float64],
    *,
    goal: PartyDevelopmentGoal,
) -> tuple[float, ...]:
    value = {
        name: float(features[index]) for index, name in enumerate(PARTY_DEVELOPMENT_FEATURE_NAMES)
    }
    if goal is PartyDevelopmentGoal.BALANCE:
        goal_alignment = value["candidate.level_floor_deficit"]
    elif goal is PartyDevelopmentGoal.EVOLUTION:
        proximity = value["candidate.evolution_level_distance_known"] * (
            1.0 - value["candidate.evolution_level_distance"]
        )
        goal_alignment = float(
            np.mean(
                (
                    value["candidate.evolution_required"],
                    value["candidate.evolution_stages_remaining"],
                    value["candidate.evolution_feasible_now"],
                    proximity,
                )
            )
        )
    elif goal is PartyDevelopmentGoal.COLLECTION:
        goal_alignment = float(
            np.mean(
                (
                    value["candidate.registration_needed"],
                    value["candidate.living_target_needed"],
                    -value["candidate.living_retention_risk"],
                )
            )
        )
    else:
        goal_alignment = 0.5 * (value["candidate.role_needed"] - value["candidate.role_complete"])
    safety_resource = float(
        np.mean(
            (
                value["candidate.hp_ratio"],
                value["candidate.status_healthy"],
                value["candidate.can_battle"],
                value["candidate.attack_pp"],
                value["candidate.projected_survival_margin"],
            )
        )
    )
    escort_feasibility = 0.5 * (
        value["candidate.projected_survival_margin"] - value["candidate.emergency_escort_required"]
    )
    venue_quality = float(
        np.mean(
            (
                value["venue.fightable_share"],
                value["venue.has_nearby_healer"],
                value["venue.prior_reliability"],
                value["venue.prior_expected_yield"],
                value["venue.prior_matchup_safety"],
            )
        )
    )
    venue_safety = float(
        np.mean(
            (
                value["venue.fightable_share"],
                value["venue.has_nearby_healer"],
                value["venue.prior_matchup_safety"],
            )
        )
    )
    venue_cost = -0.5 * (value["venue.prior_travel_cost"] + value["venue.prior_recovery_cost"])
    interactions = tuple(
        component_value if interaction_goal is goal else 0.0
        for interaction_goal in PartyDevelopmentGoal
        for component_value in (venue_quality, venue_safety, venue_cost)
    )
    return (
        goal_alignment,
        safety_resource,
        escort_feasibility,
        venue_quality,
        venue_safety,
        venue_cost,
        *interactions,
    )


def _metric_pair(
    examples: Sequence[ScenarioOutcomeExample],
    base_probabilities: Sequence[NDArray[np.float64]],
    updated_probabilities: Sequence[NDArray[np.float64]],
) -> ProtocolMetricPair:
    indices = tuple(range(len(examples)))
    return _metric_pair_for_indices(
        examples,
        base_probabilities,
        updated_probabilities,
        indices,
    )


def _metric_pair_for_indices(
    examples: Sequence[ScenarioOutcomeExample],
    base_probabilities: Sequence[NDArray[np.float64]],
    updated_probabilities: Sequence[NDArray[np.float64]],
    indices: tuple[int, ...],
) -> ProtocolMetricPair:
    if not indices:
        raise ProtocolPartyLearningError("protocol metric slice is empty")
    selected = tuple(examples[index] for index in indices)
    base = tuple(base_probabilities[index] for index in indices)
    updated = tuple(updated_probabilities[index] for index in indices)
    return ProtocolMetricPair(
        base=_metrics(selected, base),
        updated=_metrics(selected, updated),
    )


def _metrics(
    examples: Sequence[ScenarioOutcomeExample],
    probabilities: Sequence[NDArray[np.float64]],
) -> ProtocolMetrics:
    correct = 0
    losses: list[float] = []
    winner_probabilities: list[float] = []
    for example, menu_probabilities in zip(examples, probabilities, strict=True):
        winners = example.best_candidate_indices
        correct += int(int(np.argmax(menu_probabilities)) in winners)
        target = example.target_distribution
        positive = target > 0
        losses.append(
            float(
                -np.sum(target[positive] * np.log(np.maximum(menu_probabilities[positive], 1e-300)))
            )
        )
        winner_probabilities.append(float(np.sum(menu_probabilities[list(winners)])))
    return ProtocolMetrics(
        example_count=len(examples),
        correct_preferences=correct,
        cross_entropy=float(np.mean(losses)),
        mean_winner_probability=float(np.mean(winner_probabilities)),
    )


def _paired_counts(
    examples: Sequence[ScenarioOutcomeExample],
    base_probabilities: Sequence[NDArray[np.float64]],
    updated_probabilities: Sequence[NDArray[np.float64]],
) -> tuple[int, int, int, int, int, int]:
    updated_wins = base_wins = correctness_ties = 0
    improvements = regressions = probability_ties = 0
    for example, base, updated in zip(
        examples,
        base_probabilities,
        updated_probabilities,
        strict=True,
    ):
        winners = example.best_candidate_indices
        base_correct = int(np.argmax(base)) in winners
        updated_correct = int(np.argmax(updated)) in winners
        if updated_correct and not base_correct:
            updated_wins += 1
        elif base_correct and not updated_correct:
            base_wins += 1
        else:
            correctness_ties += 1
        delta = float(np.sum(updated[list(winners)]) - np.sum(base[list(winners)]))
        if delta > PROTOCOL_TOLERANCE:
            improvements += 1
        elif delta < -PROTOCOL_TOLERANCE:
            regressions += 1
        else:
            probability_ties += 1
    return (
        updated_wins,
        base_wins,
        correctness_ties,
        improvements,
        regressions,
        probability_ties,
    )


def _slice_did_not_regress(pair: ProtocolMetricPair) -> bool:
    return (
        pair.updated.accuracy + PROTOCOL_TOLERANCE >= pair.base.accuracy
        and pair.updated.cross_entropy <= pair.base.cross_entropy + PROTOCOL_TOLERANCE
        and pair.updated.mean_winner_probability + PROTOCOL_TOLERANCE
        >= pair.base.mean_winner_probability
    )


def _strictly_greater(left: float, right: float) -> bool:
    return left > right + PROTOCOL_TOLERANCE


def _strictly_less(left: float, right: float) -> bool:
    return left < right - PROTOCOL_TOLERANCE


def _masked_probabilities(
    scores: NDArray[np.float64],
    example: ScenarioOutcomeExample,
) -> NDArray[np.float64]:
    available = np.zeros(len(example.candidates), dtype=np.bool_)
    available[list(example.available_candidate_indices)] = True
    probabilities = np.zeros(len(example.candidates), dtype=np.float64)
    shifted = scores[available] - np.max(scores[available])
    exponentials = np.exp(shifted)
    probabilities[available] = exponentials / np.sum(exponentials)
    return probabilities


def _sigmoid(values: NDArray[np.float64]) -> NDArray[np.float64]:
    result = np.empty_like(values)
    positive = values >= 0
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    negative_exp = np.exp(values[~positive])
    result[~positive] = negative_exp / (1.0 + negative_exp)
    return result


def _choice_kind(example: ScenarioOutcomeExample) -> TrainingChoiceKind:
    index = PARTY_DEVELOPMENT_FEATURE_NAMES.index("choice.trainee")
    values = {candidate.features[index] for candidate in example.candidates}
    if values == {1.0}:
        return TrainingChoiceKind.TRAINEE
    if values == {0.0}:
        return TrainingChoiceKind.VENUE
    raise ProtocolPartyLearningError("protocol menu contradicts one action kind")


def _goal(example: ScenarioOutcomeExample) -> PartyDevelopmentGoal:
    selected: list[PartyDevelopmentGoal] = []
    for goal in PartyDevelopmentGoal:
        index = PARTY_DEVELOPMENT_FEATURE_NAMES.index(f"context.goal.{goal.value}")
        values = {candidate.features[index] for candidate in example.candidates}
        if values == {1.0}:
            selected.append(goal)
        elif values != {0.0}:
            raise ProtocolPartyLearningError("protocol menu has an invalid goal mask")
    if len(selected) != 1:
        raise ProtocolPartyLearningError("protocol menu does not declare one goal")
    return selected[0]


def _require_base_model(model: PartyDevelopmentOutcomeModel) -> None:
    if not isinstance(model, PartyDevelopmentOutcomeModel):
        raise TypeError("base_model must be a PartyDevelopmentOutcomeModel")
    if model.outcome_training_examples != 0:
        raise ProtocolPartyLearningError(
            "protocol prior must exclude every earlier outcome-trained update"
        )


def _require_training_examples(
    base_model: PartyDevelopmentOutcomeModel,
    examples: tuple[ScenarioOutcomeExample, ...],
) -> None:
    if len(examples) < 4:
        raise ProtocolPartyLearningError("protocol requires multiple train roots")
    for example in examples:
        _require_example(example)
        if example.partition is not ScenarioPartition.TRAIN:
            raise ProtocolPartyLearningError("protocol cannot open or reuse development labels")
        if not example.learner_update_eligible:
            raise ProtocolPartyLearningError(
                "protocol requires a complete measured candidate ordering"
            )
    for attribute, subject in (
        ("scenario_id", "scenario"),
        ("root_lineage_id", "root"),
        ("initial_state_sha256", "state"),
    ):
        values = tuple(getattr(item, attribute) for item in examples)
        if len(values) != len(set(values)):
            raise ProtocolPartyLearningError(f"protocol repeats a {subject}")
    roots = {item.root_lineage_id for item in examples}
    states = {item.initial_state_sha256 for item in examples}
    if roots & base_model.teacher_prior.consumed_root_lineage_ids:
        raise ProtocolPartyLearningError("protocol root overlaps teacher-prior evidence")
    if states & base_model.teacher_prior.consumed_state_sha256:
        raise ProtocolPartyLearningError("protocol state overlaps teacher-prior evidence")
    kinds = {_choice_kind(item) for item in examples}
    if kinds != set(TrainingChoiceKind):
        raise ProtocolPartyLearningError("protocol requires both action heads")


def _require_example(example: ScenarioOutcomeExample) -> None:
    if (
        not isinstance(example, ScenarioOutcomeExample)
        or example.family is not ScenarioFamily.PARTY_DEVELOPMENT
        or example.feature_schema_id != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
        or example.feature_names != PARTY_DEVELOPMENT_FEATURE_NAMES
    ):
        raise ProtocolPartyLearningError("protocol outcome example is incompatible")
    _choice_kind(example)
    _goal(example)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "PORTABLE_GROUP_NAMES",
    "PROTOCOL_DESIGN_ID",
    "PROTOCOL_NEWTON_STEPS",
    "PROTOCOL_OPTIMIZER_TOLERANCE",
    "PROTOCOL_PAIRWISE_RIDGE",
    "PROTOCOL_PARTY_RANKER_ID",
    "ProtocolLeaveOneRootOutEvaluation",
    "ProtocolMetricPair",
    "ProtocolMetrics",
    "ProtocolPartyLearningError",
    "ProtocolPartyLearningResult",
    "ProtocolPartyRanker",
    "ProtocolRepresentationAudit",
    "VENUE_INTERACTION_GROUP_NAMES",
    "audit_protocol_party_representation",
    "canonical_protocol_party_ranker_sha256",
    "run_protocol_party_leave_one_root_out",
]
