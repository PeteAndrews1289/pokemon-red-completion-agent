"""Separate shadow learner for prospective finite-goal returns.

Two heads estimate completion within the declared budget and total attempt cost
under one frozen continuation. These are regression estimates, not calibrated
probabilities or optimal Q values. No legacy outcome, coefficient or actor is
modified. The pure selector abstains unless its caller supplies independently
qualified support and explicit error/equivalence bounds; there are no live defaults.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from .forward_goal import ForwardGoalOutcome, ForwardGoalPlan, _digest, _positive, _vector
from .provenance import canonical_sha256


def forward_goal_features(
    plan: ForwardGoalPlan,
    context: tuple[float, ...],
    candidate: tuple[float, ...],
) -> tuple[float, ...]:
    """Observed start-state × candidate interactions, including declared budgets.

    Shared additive context alone cancels between options in a linear model.
    Fixed budget scales encode known resource envelopes, not outcome denominators
    chosen after seeing a trajectory. IDs, selected index and future events are
    deliberately absent from this projection.
    """
    if not isinstance(plan, ForwardGoalPlan):
        raise ValueError("forward-goal projection needs a declaration")
    _vector(context)
    _vector(candidate)
    budgets = (
        plan.max_actions / (plan.max_actions + 1000),
        plan.max_frames / (plan.max_frames + 60000),
        plan.max_resources / (plan.max_resources + 10),
        plan.max_macros / (plan.max_macros + 2),
    )
    state = (*context, *budgets)
    vector = (*state, *candidate, *(s * c for s in state for c in candidate))
    _vector(vector)
    return vector


@dataclass(frozen=True, slots=True)
class ForwardGoalPrediction:
    completion: float
    cost: float

    def __post_init__(self) -> None:
        if (
            any(
                type(v) not in (int, float) or not math.isfinite(v)
                for v in (self.completion, self.cost)
            )
            or not 0 <= self.completion <= 1
            or self.cost < 0
        ):
            raise ValueError("forward-goal prediction is invalid")


@dataclass(frozen=True, slots=True)
class ForwardGoalModel:
    contract: tuple[str, str, str]
    context_names: tuple[str, ...]
    candidate_names: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[tuple[float, float], ...]
    intercept: tuple[float, float]
    dataset_sha256: str
    settled_examples: int
    censored_examples: int
    ridge: float
    importance_cap: float

    def __post_init__(self) -> None:
        if not isinstance(self.contract, tuple) or len(self.contract) != 3:
            raise ValueError("forward-goal model contract differs")
        ForwardGoalPlan(*self.contract, 1, 1, 0)
        _digest(self.dataset_sha256)
        _positive(self.settled_examples, "settled examples")
        _positive(self.censored_examples, "censored examples", zero=True)
        if any(
            not isinstance(names, tuple)
            or not names
            or len(set(names)) != len(names)
            or any(not isinstance(name, str) or not name for name in names)
            for names in (self.context_names, self.candidate_names)
        ):
            raise ValueError("forward-goal model feature names differ")
        if (
            any(
                type(v) not in (int, float) or not math.isfinite(v)
                for v in (self.ridge, self.importance_cap)
            )
            or self.ridge <= 0
            or self.importance_cap < 1
        ):
            raise ValueError("forward-goal model fit parameters differ")
        _vector(self.mean)
        _vector(self.scale)
        _vector(self.intercept)
        width = ((len(self.context_names) + 4 + 1) * (len(self.candidate_names) + 1)) - 1
        if len(self.mean) != width or len(self.scale) != width or any(s <= 0 for s in self.scale):
            raise ValueError("forward-goal normalization dimensions differ")
        if (
            not isinstance(self.coefficients, tuple)
            or len(self.coefficients) != width
            or len(self.intercept) != 2
        ):
            raise ValueError("forward-goal model head dimensions differ")
        for row in self.coefficients:
            _vector(row)
            if len(row) != 2:
                raise ValueError("forward-goal coefficient dimensions differ")

    def predict(
        self,
        *,
        plan: ForwardGoalPlan,
        context_names: tuple[str, ...],
        context: tuple[float, ...],
        candidate_names: tuple[str, ...],
        candidates: tuple[tuple[float, ...], ...],
    ) -> tuple[ForwardGoalPrediction, ...]:
        if plan.contract != self.contract:
            raise ValueError("forward-goal goal/verifier/continuation contract differs")
        if context_names != self.context_names or candidate_names != self.candidate_names:
            raise ValueError("forward-goal input feature schema differs")
        if (
            len(context) != len(context_names)
            or not isinstance(candidates, tuple)
            or not candidates
        ):
            raise ValueError("forward-goal input dimensions differ")
        predictions = []
        for candidate in candidates:
            if len(candidate) != len(candidate_names):
                raise ValueError("forward-goal candidate dimensions differ")
            features = forward_goal_features(plan, context, candidate)
            normalized = [
                (x - m) / s for x, m, s in zip(features, self.mean, self.scale, strict=True)
            ]
            output = tuple(
                self.intercept[head]
                + math.fsum(
                    x * weight[head]
                    for x, weight in zip(normalized, self.coefficients, strict=True)
                )
                for head in range(2)
            )
            if not all(math.isfinite(value) for value in output):
                raise ValueError("forward-goal inference produced a nonfinite estimate")
            predictions.append(
                ForwardGoalPrediction(
                    max(0.0, min(1.0, output[0])),
                    max(0.0, output[1]),
                )
            )
        return tuple(predictions)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.forward-goal-model.v1",
            "authority": "unqualified-shadow",
            "goal_family": self.contract[0],
            "verifier_sha256": self.contract[1],
            "continuation_sha256": self.contract[2],
            "context_names": list(self.context_names),
            "candidate_names": list(self.candidate_names),
            "projection": "observed-context-and-fixed-budget-cross-candidate.v1",
            "target_names": ["completion_within_budget", "cumulative_attempt_cost"],
            "mean": list(self.mean),
            "scale": list(self.scale),
            "coefficients": [list(row) for row in self.coefficients],
            "intercept": list(self.intercept),
            "dataset_sha256": self.dataset_sha256,
            "settled_examples": self.settled_examples,
            "censored_examples": self.censored_examples,
            "ridge": self.ridge,
            "importance_cap": self.importance_cap,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.public_dict())


@dataclass(frozen=True, slots=True)
class ForwardGoalFit:
    model: ForwardGoalModel
    recorded_roots: int
    settled_roots: int
    distinct_inputs: int
    mse_before: tuple[float, float]
    mse_after: tuple[float, float]


def fit_forward_goal(
    outcomes: Iterable[ForwardGoalOutcome],
    *,
    ridge: float = 1.0,
    importance_cap: float = 10.0,
) -> ForwardGoalFit:
    """Fit only prospective selected-first-option train returns, including failures.

    Clipped first-choice inverse propensities balance a uniform target over the
    same supported initial menus. They do not correct a changed continuation or
    make dependent starts independent. Censored prefixes are retained in the
    dataset fingerprint/count, never given a complete cost or failure label.
    """
    if any(
        type(v) not in (int, float) or not math.isfinite(v) for v in (ridge, importance_cap)
    ) or (ridge <= 0 or importance_cap < 1):
        raise ValueError("forward-goal fit regularization/importance cap is invalid")
    rows = tuple(outcomes)
    if not rows or any(not isinstance(row, ForwardGoalOutcome) for row in rows):
        raise ValueError("forward-goal fit requires declared prospective outcomes")
    rows = tuple(sorted(rows, key=lambda r: r.choice.decision_sha256))
    if len({r.choice.decision_sha256 for r in rows}) != len(rows):
        raise ValueError("forward-goal decision identities repeat")
    if any(r.choice.partition != "train" for r in rows):
        raise ValueError("forward-goal fitting is train-only")
    first = rows[0]
    if any(
        (r.plan.contract, r.choice.context_names, r.choice.candidate_names)
        != (
            first.plan.contract,
            first.choice.context_names,
            first.choice.candidate_names,
        )
        for r in rows
    ):
        raise ValueError("forward-goal fitting cannot mix goal/continuation/input contracts")
    settled = tuple(row for row in rows if row.target is not None)
    if len(settled) < 2:
        raise ValueError("forward-goal fit needs at least two settled selected choices")
    features = np.asarray(
        [
            forward_goal_features(
                r.plan, r.choice.context, r.choice.candidates[r.choice.selected_index]
            )
            for r in settled
        ],
        dtype=np.float64,
    )
    targets = np.asarray([r.target for r in settled], dtype=np.float64)
    weights = np.asarray(
        [
            min(
                importance_cap,
                1 / (len(r.choice.candidates) * r.choice.probabilities[r.choice.selected_index]),
            )
            for r in settled
        ],
        dtype=np.float64,
    )
    mean = np.average(features, axis=0, weights=weights)
    scale = np.sqrt(np.average((features - mean) ** 2, axis=0, weights=weights))
    scale[scale == 0] = 1.0
    normalized = (features - mean) / scale
    design = np.column_stack((np.ones(len(settled)), normalized))
    penalty = np.eye(design.shape[1]) * ridge
    penalty[0, 0] = 0
    weighted = design * weights[:, np.newaxis]
    try:
        parameters = np.linalg.solve(
            design.T @ weighted + penalty, design.T @ (targets * weights[:, np.newaxis])
        )
    except np.linalg.LinAlgError:
        raise ValueError("forward-goal fit is singular") from None
    if not np.isfinite(parameters).all():
        raise ValueError("forward-goal fit produced nonfinite parameters")
    predictions = design @ parameters
    predictions[:, 0] = np.clip(predictions[:, 0], 0, 1)
    predictions[:, 1] = np.maximum(predictions[:, 1], 0)
    baseline = np.average(targets, axis=0, weights=weights)
    before = np.average((targets - baseline) ** 2, axis=0, weights=weights)
    after = np.average((targets - predictions) ** 2, axis=0, weights=weights)
    model = ForwardGoalModel(
        first.plan.contract,
        first.choice.context_names,
        first.choice.candidate_names,
        tuple(float(v) for v in mean),
        tuple(float(v) for v in scale),
        tuple((float(row[0]), float(row[1])) for row in parameters[1:]),
        (float(parameters[0, 0]), float(parameters[0, 1])),
        canonical_sha256(
            {
                "schema": "pokemon.core.forward-goal-dataset.v1",
                "outcomes": [r.public_dict() for r in rows],
            }
        ),
        len(settled),
        len(rows) - len(settled),
        float(ridge),
        float(importance_cap),
    )
    return ForwardGoalFit(
        model,
        len({r.choice.root_sha256 for r in rows}),
        len({r.choice.root_sha256 for r in settled}),
        len({tuple(row) for row in features}),
        (float(before[0]), float(before[1])),
        (float(after[0]), float(after[1])),
    )


@dataclass(frozen=True, slots=True)
class ForwardGoalSelectionBounds:
    """Explicit qualification inputs, not inferred confidence from a ridge score."""

    completion_error: float
    cost_error: float
    equivalence_margin: float
    minimum_completion: float

    def __post_init__(self) -> None:
        values = (
            self.completion_error,
            self.cost_error,
            self.equivalence_margin,
            self.minimum_completion,
        )
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("forward-goal selection bounds must be finite and nonnegative")
        if any(
            v > 1 for v in (self.completion_error, self.equivalence_margin, self.minimum_completion)
        ):
            raise ValueError("forward-goal completion bounds exceed one")


def select_forward_goal(
    predictions: tuple[ForwardGoalPrediction, ...],
    *,
    supported: tuple[bool, ...],
    bounds: ForwardGoalSelectionBounds | None = None,
) -> int | None:
    """Prefer credible completion, or credibly cheaper equivalent completion.

    No support or explicit qualification means abstention. All offered options
    need support: an unmeasured alternative cannot silently be discarded. Ties,
    unresolved differences and universally poor completion also abstain.
    """
    if (
        not isinstance(predictions, tuple)
        or len(predictions) < 2
        or any(not isinstance(p, ForwardGoalPrediction) for p in predictions)
        or not isinstance(supported, tuple)
        or len(supported) != len(predictions)
        or any(type(s) is not bool for s in supported)
    ):
        raise ValueError("forward-goal selection inputs differ")
    if bounds is None or not all(supported):
        return None
    if not isinstance(bounds, ForwardGoalSelectionBounds):
        raise ValueError("forward-goal selection needs explicit qualified bounds")
    e, c, margin = bounds.completion_error, bounds.cost_error, bounds.equivalence_margin
    winners = []
    for index, prediction in enumerate(predictions):
        if max(0.0, prediction.completion - e) < bounds.minimum_completion:
            continue
        dominates = True
        for other_index, other in enumerate(predictions):
            if index == other_index:
                continue
            better_completion = (
                max(0.0, prediction.completion - e) > min(1.0, other.completion + e) + margin
            )
            equivalent_completion = abs(prediction.completion - other.completion) + 2 * e <= margin
            cheaper = prediction.cost + c < max(0.0, other.cost - c)
            if not (better_completion or (equivalent_completion and cheaper)):
                dominates = False
                break
        if dominates:
            winners.append(index)
    return winners[0] if len(winners) == 1 else None
