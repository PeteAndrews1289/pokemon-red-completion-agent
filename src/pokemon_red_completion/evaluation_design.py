"""Exact, dependency-free design checks for paired promotion experiments.

The project's learned heads are usually compared on the same independent
contexts.  A paired win means the candidate succeeds while its frozen
comparator fails; a paired loss means the reverse; ties carry no direction.
The exact sign test conditions on the number of discordant pairs, so it does
not need an assumed tie rate to control false positives.  Power does need a
declared win/loss/tie alternative and is computed prospectively.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache


class EvaluationDesignError(ValueError):
    """Raised when a proposed promotion design is incomplete or invalid."""


@dataclass(frozen=True, slots=True)
class PairedExactDesign:
    """A fully specified one-sided exact paired-comparison design."""

    independent_contexts: int
    alpha: float
    smallest_useful_win_probability: float
    smallest_useful_loss_probability: float
    target_power: float

    def __post_init__(self) -> None:
        _positive_count(self.independent_contexts, subject="independent contexts")
        _open_unit(self.alpha, subject="alpha")
        _closed_unit(
            self.smallest_useful_win_probability,
            subject="smallest useful win probability",
        )
        _closed_unit(
            self.smallest_useful_loss_probability,
            subject="smallest useful loss probability",
        )
        if (
            self.smallest_useful_win_probability
            + self.smallest_useful_loss_probability
            > 1.0
        ):
            raise EvaluationDesignError("paired alternative probabilities exceed one")
        if (
            self.smallest_useful_win_probability
            <= self.smallest_useful_loss_probability
        ):
            raise EvaluationDesignError(
                "paired alternative must favor the candidate"
            )
        _open_unit(self.target_power, subject="target power")

    @property
    def achieved_power(self) -> float:
        return paired_one_sided_exact_power(
            self.independent_contexts,
            win_probability=self.smallest_useful_win_probability,
            loss_probability=self.smallest_useful_loss_probability,
            alpha=self.alpha,
        )

    @property
    def minimum_contexts(self) -> int:
        return minimum_paired_contexts(
            win_probability=self.smallest_useful_win_probability,
            loss_probability=self.smallest_useful_loss_probability,
            alpha=self.alpha,
            target_power=self.target_power,
        )

    @property
    def adequately_powered(self) -> bool:
        return self.achieved_power + 1e-15 >= self.target_power

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.paired-exact-design.v1",
            "independent_contexts": self.independent_contexts,
            "statistic": "discordant_candidate_wins_and_losses",
            "comparator": "same_context_frozen_control",
            "test": "one_sided_exact_sign_test_conditional_on_discordance",
            "decision_rule": (
                "promote only when candidate wins exceed losses and the one-sided "
                "exact p-value is at most alpha"
            ),
            "alpha": self.alpha,
            "smallest_useful_effect": {
                "win_probability": self.smallest_useful_win_probability,
                "loss_probability": self.smallest_useful_loss_probability,
                "tie_probability": 1.0
                - self.smallest_useful_win_probability
                - self.smallest_useful_loss_probability,
            },
            "target_power": self.target_power,
            "achieved_power": self.achieved_power,
            "minimum_contexts_for_target_power": self.minimum_contexts,
            "adequately_powered": self.adequately_powered,
        }


@lru_cache(maxsize=None, typed=True)
def paired_one_sided_exact_p(wins: int, losses: int) -> float:
    """Return P(Binomial(wins + losses, 0.5) >= wins)."""

    _count(wins, subject="paired wins")
    _count(losses, subject="paired losses")
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    return math.fsum(
        math.comb(discordant, successes) * 0.5**discordant
        for successes in range(wins, discordant + 1)
    )


@lru_cache(maxsize=None, typed=True)
def paired_one_sided_exact_power(
    independent_contexts: int,
    *,
    win_probability: float,
    loss_probability: float,
    alpha: float = 0.05,
) -> float:
    """Return prospective power under a declared win/loss/tie alternative."""

    _positive_count(independent_contexts, subject="independent contexts")
    _closed_unit(win_probability, subject="win probability")
    _closed_unit(loss_probability, subject="loss probability")
    _open_unit(alpha, subject="alpha")
    discordance_probability = win_probability + loss_probability
    if discordance_probability > 1.0:
        raise EvaluationDesignError("paired alternative probabilities exceed one")
    if discordance_probability == 0.0:
        return 0.0
    conditional_win_probability = win_probability / discordance_probability
    probability = 0.0
    for discordant in range(1, independent_contexts + 1):
        discordant_probability = _binomial_probability(
            independent_contexts,
            discordant,
            discordance_probability,
        )
        rejecting_probability = math.fsum(
            _binomial_probability(
                discordant,
                wins,
                conditional_win_probability,
            )
            for wins in range(discordant + 1)
            if wins > discordant - wins
            and paired_one_sided_exact_p(wins, discordant - wins) <= alpha
        )
        probability += discordant_probability * rejecting_probability
    return min(max(probability, 0.0), 1.0)


@lru_cache(maxsize=None, typed=True)
def paired_one_sided_exact_power_with_forced_losses(
    independent_contexts: int,
    *,
    forced_losses: int,
    win_probability: float,
    loss_probability: float,
    alpha: float = 0.05,
) -> float:
    """Return power when up to ``forced_losses`` are scored against the candidate.

    An incomplete paired context cannot be removed without an ignorability
    assumption.  The promotion endpoint instead treats every allowed incomplete
    context as a candidate loss.  This prospective calculation sizes the full
    denominator under that least-favorable censoring rule.
    """

    _positive_count(independent_contexts, subject="independent contexts")
    _count(forced_losses, subject="forced losses")
    if forced_losses > independent_contexts:
        raise EvaluationDesignError("forced losses exceed independent contexts")
    _closed_unit(win_probability, subject="win probability")
    _closed_unit(loss_probability, subject="loss probability")
    _open_unit(alpha, subject="alpha")
    discordance_probability = win_probability + loss_probability
    if discordance_probability > 1.0:
        raise EvaluationDesignError("paired alternative probabilities exceed one")
    remaining = independent_contexts - forced_losses
    if remaining == 0 or discordance_probability == 0.0:
        return 0.0
    conditional_win_probability = win_probability / discordance_probability
    probability = 0.0
    for discordant in range(remaining + 1):
        discordant_probability = _binomial_probability(
            remaining,
            discordant,
            discordance_probability,
        )
        rejecting_probability = math.fsum(
            _binomial_probability(
                discordant,
                wins,
                conditional_win_probability,
            )
            for wins in range(discordant + 1)
            if wins > discordant - wins + forced_losses
            and paired_one_sided_exact_p(
                wins,
                discordant - wins + forced_losses,
            )
            <= alpha
        )
        probability += discordant_probability * rejecting_probability
    return min(max(probability, 0.0), 1.0)


@lru_cache(maxsize=None, typed=True)
def minimum_paired_contexts(
    *,
    win_probability: float,
    loss_probability: float,
    alpha: float = 0.05,
    target_power: float = 0.8,
    maximum_contexts: int = 10_000,
) -> int:
    """Find the first n meeting a prospective paired exact-test power target."""

    _closed_unit(win_probability, subject="win probability")
    _closed_unit(loss_probability, subject="loss probability")
    _open_unit(alpha, subject="alpha")
    _open_unit(target_power, subject="target power")
    _positive_count(maximum_contexts, subject="maximum contexts")
    if win_probability + loss_probability > 1.0:
        raise EvaluationDesignError("paired alternative probabilities exceed one")
    if win_probability <= loss_probability:
        raise EvaluationDesignError(
            "a favorable alternative is required to size a one-sided design"
        )
    for contexts in range(1, maximum_contexts + 1):
        power = paired_one_sided_exact_power(
            contexts,
            win_probability=win_probability,
            loss_probability=loss_probability,
            alpha=alpha,
        )
        if power + 1e-15 >= target_power:
            return contexts
    raise EvaluationDesignError("target power exceeds the maximum context budget")


@lru_cache(maxsize=None, typed=True)
def minimum_paired_contexts_with_forced_losses(
    *,
    forced_losses: int,
    win_probability: float,
    loss_probability: float,
    alpha: float = 0.05,
    target_power: float = 0.8,
    maximum_contexts: int = 10_000,
) -> int:
    """Find the first full denominator powered after worst-case incompleteness.

    ``forced_losses`` is fixed prospectively rather than estimated from opened
    outcomes.  Every such context remains in the denominator and is scored as
    a candidate loss.  The returned sample size is therefore the first one
    that survives the declared attrition budget without an ignorability claim.
    """

    _count(forced_losses, subject="forced losses")
    _closed_unit(win_probability, subject="win probability")
    _closed_unit(loss_probability, subject="loss probability")
    _open_unit(alpha, subject="alpha")
    _open_unit(target_power, subject="target power")
    _positive_count(maximum_contexts, subject="maximum contexts")
    if win_probability + loss_probability > 1.0:
        raise EvaluationDesignError("paired alternative probabilities exceed one")
    if win_probability <= loss_probability:
        raise EvaluationDesignError(
            "a favorable alternative is required to size a one-sided design"
        )
    if forced_losses >= maximum_contexts:
        raise EvaluationDesignError("forced losses exhaust the maximum context budget")
    for contexts in range(forced_losses + 1, maximum_contexts + 1):
        power = paired_one_sided_exact_power_with_forced_losses(
            contexts,
            forced_losses=forced_losses,
            win_probability=win_probability,
            loss_probability=loss_probability,
            alpha=alpha,
        )
        if power + 1e-15 >= target_power:
            return contexts
    raise EvaluationDesignError("target power exceeds the maximum context budget")


@lru_cache(maxsize=None, typed=True)
def zero_loss_conjunction_power(
    independent_contexts: int,
    *,
    minimum_wins: int,
    win_probability: float,
    loss_probability: float,
) -> float:
    """Audit the old `wins >= k and losses == 0` rule without endorsing it."""

    _positive_count(independent_contexts, subject="independent contexts")
    _positive_count(minimum_wins, subject="minimum wins")
    if minimum_wins > independent_contexts:
        raise EvaluationDesignError("minimum wins exceed independent contexts")
    _closed_unit(win_probability, subject="win probability")
    _closed_unit(loss_probability, subject="loss probability")
    if win_probability + loss_probability > 1.0:
        raise EvaluationDesignError("paired alternative probabilities exceed one")
    tie_probability = 1.0 - win_probability - loss_probability
    return math.fsum(
        math.comb(independent_contexts, wins)
        * win_probability**wins
        * tie_probability ** (independent_contexts - wins)
        for wins in range(minimum_wins, independent_contexts + 1)
    )


def _binomial_probability(trials: int, successes: int, probability: float) -> float:
    if probability == 0.0:
        return 1.0 if successes == 0 else 0.0
    if probability == 1.0:
        return 1.0 if successes == trials else 0.0
    return (
        math.comb(trials, successes)
        * probability**successes
        * (1.0 - probability) ** (trials - successes)
    )


def _count(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise EvaluationDesignError(f"{subject} must be a non-negative integer")
    return value


def _positive_count(value: object, *, subject: str) -> int:
    result = _count(value, subject=subject)
    if result == 0:
        raise EvaluationDesignError(f"{subject} must be positive")
    return result


def _closed_unit(value: object, *, subject: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise EvaluationDesignError(f"{subject} must be between zero and one")
    return float(value)


def _open_unit(value: object, *, subject: str) -> float:
    result = _closed_unit(value, subject=subject)
    if result in {0.0, 1.0}:
        raise EvaluationDesignError(f"{subject} must be strictly between zero and one")
    return result


__all__ = [
    "EvaluationDesignError",
    "PairedExactDesign",
    "minimum_paired_contexts",
    "minimum_paired_contexts_with_forced_losses",
    "paired_one_sided_exact_p",
    "paired_one_sided_exact_power",
    "paired_one_sided_exact_power_with_forced_losses",
    "zero_loss_conjunction_power",
]
