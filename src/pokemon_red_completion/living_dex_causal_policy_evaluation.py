"""Exact paired realized-outcome gate for a living-Pokedex option policy.

Prediction error on logged arms is calibration, not playing competence.  This
module evaluates a frozen candidate and three preregistered controls from the
same reset and RNG condition.  Every branch is actually executed; no
unexecuted arm becomes a target.  The primary control is an envelope that is
successful when any random, cost-only, or myopic-completion branch succeeds.
That single conservative comparator avoids multiple-comparison claims.

The evaluator cannot fit, update, or select a model.  Candidate and control
choices must already be committed before any branch outcome is supplied.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.evaluation_design import paired_one_sided_exact_p
from pokemon_red_completion.living_dex_causal_curriculum import (
    LIVING_DEX_CAUSAL_EVALUATION_ENDPOINT,
    RED_DIRECT_CAUSAL_OPTION_KINDS,
    LivingDexCausalCurriculumDesign,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedOutcome,
    LivingDexOptionKind,
    LivingDexOutcomeStatus,
)

LIVING_DEX_CAUSAL_POLICY_CONTEXT_SCHEMA = (
    "pokemon.core.private-living-dex-causal-policy-context-result.v1"
)
LIVING_DEX_CAUSAL_POLICY_EVALUATION_SCHEMA = (
    "pokemon.core.living-dex-causal-policy-evaluation.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class LivingDexCausalBaseline(StrEnum):
    FROZEN_RANDOM = "frozen_random"
    COST_ONLY = "cost_only"
    MYOPIC_COMPLETION_GREEDY = "myopic_completion_greedy"


class LivingDexPairedDisposition(StrEnum):
    CANDIDATE_WIN = "candidate_win"
    CANDIDATE_LOSS = "candidate_loss"
    TIE = "tie"
    CENSORED = "censored"


class LivingDexCausalPolicyEvaluationError(ValueError):
    """A paired result lacks factual branches, independence, or frozen choices."""


@dataclass(frozen=True, slots=True)
class LivingDexCausalControlOutcome:
    """One preregistered control choice and its actually observed branch."""

    baseline: LivingDexCausalBaseline
    candidate_index: int
    outcome: LivingDexObservedOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, LivingDexCausalBaseline):
            raise LivingDexCausalPolicyEvaluationError("causal control differs")
        if type(self.candidate_index) is not int or not 0 <= self.candidate_index < 3:  # noqa: E721
            raise LivingDexCausalPolicyEvaluationError(
                "causal control candidate index differs"
            )
        if not isinstance(self.outcome, LivingDexObservedOutcome):
            raise TypeError("causal control needs an observed branch outcome")
        self.outcome.__post_init__()


@dataclass(frozen=True, slots=True)
class LivingDexCausalPolicyContextResult:
    """Candidate plus control branches from one untouched reset/RNG context."""

    context_identity_sha256: str
    physical_root_sha256: str
    independence_lineage_sha256: str
    same_reset_rng_sha256: str
    menu_policy_sha256: str
    model_choice_commitment_sha256: str
    control_choice_commitment_sha256: str
    focus_kind: LivingDexOptionKind
    candidate_index: int
    candidate_outcome: LivingDexObservedOutcome
    controls: tuple[LivingDexCausalControlOutcome, ...]
    choices_committed_before_outcomes: bool = True

    def __post_init__(self) -> None:
        for value, subject in (
            (self.context_identity_sha256, "policy context"),
            (self.physical_root_sha256, "policy physical root"),
            (self.independence_lineage_sha256, "policy lineage"),
            (self.same_reset_rng_sha256, "policy reset and RNG"),
            (self.menu_policy_sha256, "policy menu"),
            (self.model_choice_commitment_sha256, "model choice commitment"),
            (self.control_choice_commitment_sha256, "control choice commitment"),
        ):
            _require_sha256(value, subject=subject)
        if self.focus_kind not in RED_DIRECT_CAUSAL_OPTION_KINDS:
            raise LivingDexCausalPolicyEvaluationError(
                "policy evaluation focus kind differs"
            )
        if type(self.candidate_index) is not int or not 0 <= self.candidate_index < 3:  # noqa: E721
            raise LivingDexCausalPolicyEvaluationError(
                "policy candidate index differs"
            )
        if not isinstance(self.candidate_outcome, LivingDexObservedOutcome):
            raise TypeError("policy candidate needs an observed branch outcome")
        self.candidate_outcome.__post_init__()
        if (
            not isinstance(self.controls, tuple)
            or len(self.controls) != len(LivingDexCausalBaseline)
            or any(
                not isinstance(control, LivingDexCausalControlOutcome)
                for control in self.controls
            )
            or {control.baseline for control in self.controls}
            != set(LivingDexCausalBaseline)
        ):
            raise LivingDexCausalPolicyEvaluationError(
                "policy evaluation needs all three distinct controls"
            )
        for control in self.controls:
            control.__post_init__()
        if self.choices_committed_before_outcomes is not True:
            raise LivingDexCausalPolicyEvaluationError(
                "policy choices were not committed before outcomes"
            )
        outcomes_by_index: dict[int, LivingDexObservedOutcome] = {
            self.candidate_index: self.candidate_outcome
        }
        for control in self.controls:
            prior = outcomes_by_index.setdefault(
                control.candidate_index,
                control.outcome,
            )
            if prior != control.outcome:
                raise LivingDexCausalPolicyEvaluationError(
                    "same reset branch has contradictory outcomes"
                )

    @property
    def complete(self) -> bool:
        return self.candidate_outcome.status is LivingDexOutcomeStatus.SETTLED and all(
            control.outcome.status is LivingDexOutcomeStatus.SETTLED
            for control in self.controls
        )

    @property
    def unique_factual_branch_count(self) -> int:
        return len(
            {
                self.candidate_index,
                *(control.candidate_index for control in self.controls),
            }
        )

    @property
    def baseline_envelope_success(self) -> bool | None:
        if not self.complete:
            return None
        return any(bool(control.outcome.verified_success) for control in self.controls)

    @property
    def disposition(self) -> LivingDexPairedDisposition:
        """Return the factual complete-case disposition for diagnostics."""

        if not self.complete:
            return LivingDexPairedDisposition.CENSORED
        candidate = bool(self.candidate_outcome.verified_success)
        envelope = bool(self.baseline_envelope_success)
        if candidate and not envelope:
            return LivingDexPairedDisposition.CANDIDATE_WIN
        if envelope and not candidate:
            return LivingDexPairedDisposition.CANDIDATE_LOSS
        return LivingDexPairedDisposition.TIE

    @property
    def conservative_primary_disposition(self) -> LivingDexPairedDisposition:
        """Score every incomplete context against the candidate for inference."""

        if not self.complete:
            return LivingDexPairedDisposition.CANDIDATE_LOSS
        return self.disposition

    def disposition_against(
        self,
        baseline: LivingDexCausalBaseline,
    ) -> LivingDexPairedDisposition:
        if not isinstance(baseline, LivingDexCausalBaseline):
            raise TypeError("paired comparison needs a causal baseline")
        control = next(item for item in self.controls if item.baseline is baseline)
        if (
            self.candidate_outcome.status is LivingDexOutcomeStatus.CENSORED
            or control.outcome.status is LivingDexOutcomeStatus.CENSORED
        ):
            return LivingDexPairedDisposition.CENSORED
        candidate = bool(self.candidate_outcome.verified_success)
        comparator = bool(control.outcome.verified_success)
        if candidate and not comparator:
            return LivingDexPairedDisposition.CANDIDATE_WIN
        if comparator and not candidate:
            return LivingDexPairedDisposition.CANDIDATE_LOSS
        return LivingDexPairedDisposition.TIE


@dataclass(frozen=True, slots=True)
class LivingDexCausalPolicyEvaluation:
    """Path-free aggregate over the frozen 105-context paired endpoint."""

    design_sha256: str
    attempted_contexts: int
    complete_contexts: int
    censored_contexts: int
    candidate_wins: int
    candidate_losses: int
    complete_case_candidate_losses: int
    conservative_censored_losses: int
    ties: int
    candidate_successes: int
    baseline_envelope_successes: int
    exact_one_sided_p: float
    focus_kind_counts: tuple[tuple[str, int], ...]
    per_control: tuple[tuple[str, int, int, int], ...]
    factual_branch_executions: int
    distinct_physical_roots: int
    distinct_independence_lineages: int
    adequate_complete_contexts: bool
    candidate_success_floor_passed: bool
    promotion_gate_passed: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "adequate_complete_contexts": self.adequate_complete_contexts,
            "attempted_contexts": self.attempted_contexts,
            "baseline_envelope": [item.value for item in LivingDexCausalBaseline],
            "baseline_envelope_successes": self.baseline_envelope_successes,
            "candidate_losses": self.candidate_losses,
            "complete_case_candidate_losses": self.complete_case_candidate_losses,
            "conservative_censored_losses": self.conservative_censored_losses,
            "candidate_success_floor_passed": self.candidate_success_floor_passed,
            "candidate_successes": self.candidate_successes,
            "candidate_wins": self.candidate_wins,
            "censored_contexts": self.censored_contexts,
            "complete_contexts": self.complete_contexts,
            "design_sha256": self.design_sha256,
            "distinct_independence_lineages": (
                self.distinct_independence_lineages
            ),
            "distinct_physical_roots": self.distinct_physical_roots,
            "endpoint": LIVING_DEX_CAUSAL_EVALUATION_ENDPOINT,
            "exact_one_sided_p": self.exact_one_sided_p,
            "incomplete_context_inference_rule": (
                "every_incomplete_context_scored_as_candidate_loss"
            ),
            "factual_branch_executions": self.factual_branch_executions,
            "focus_kind_counts": dict(self.focus_kind_counts),
            "model_fits": 0,
            "per_control_descriptive": {
                baseline: {"losses": losses, "ties": ties, "wins": wins}
                for baseline, wins, losses, ties in self.per_control
            },
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "promotion_gate_passed": self.promotion_gate_passed,
            "schema": LIVING_DEX_CAUSAL_POLICY_EVALUATION_SCHEMA,
            "teacher_queries": 0,
            "ties": self.ties,
            "training_targets_emitted": 0,
            "unexecuted_action_targets": 0,
        }


def evaluate_living_dex_causal_policy(
    contexts: tuple[LivingDexCausalPolicyContextResult, ...],
    *,
    design: LivingDexCausalCurriculumDesign | None = None,
) -> LivingDexCausalPolicyEvaluation:
    """Evaluate the candidate only after all frozen branch outcomes exist."""

    active_design = LivingDexCausalCurriculumDesign() if design is None else design
    if not isinstance(active_design, LivingDexCausalCurriculumDesign):
        raise TypeError("causal policy evaluation needs its frozen design")
    active_design.__post_init__()
    if (
        not isinstance(contexts, tuple)
        or len(contexts) != active_design.prospective_development_contexts
        or any(
            not isinstance(context, LivingDexCausalPolicyContextResult)
            for context in contexts
        )
    ):
        raise LivingDexCausalPolicyEvaluationError(
            "causal policy evaluation needs the complete frozen denominator"
        )
    for context in contexts:
        context.__post_init__()
    for values, subject in (
        ((item.context_identity_sha256 for item in contexts), "context"),
        ((item.physical_root_sha256 for item in contexts), "physical root"),
        ((item.independence_lineage_sha256 for item in contexts), "lineage"),
    ):
        rows = tuple(values)
        if len(rows) != len(set(rows)):
            raise LivingDexCausalPolicyEvaluationError(
                f"causal policy evaluation repeats a {subject}"
            )
    focus_counts = Counter(item.focus_kind.value for item in contexts)
    if any(
        focus_counts[kind.value]
        != active_design.minimum_development_contexts_per_focus_kind
        for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
    ):
        raise LivingDexCausalPolicyEvaluationError(
            "causal policy evaluation focus schedule differs"
        )

    complete = tuple(item for item in contexts if item.complete)
    complete_case_dispositions = Counter(item.disposition for item in contexts)
    dispositions = Counter(item.conservative_primary_disposition for item in contexts)
    wins = dispositions[LivingDexPairedDisposition.CANDIDATE_WIN]
    losses = dispositions[LivingDexPairedDisposition.CANDIDATE_LOSS]
    ties = dispositions[LivingDexPairedDisposition.TIE]
    candidate_successes = sum(
        bool(item.candidate_outcome.verified_success) for item in complete
    )
    envelope_successes = sum(bool(item.baseline_envelope_success) for item in complete)
    p_value = paired_one_sided_exact_p(wins, losses)
    adequate = len(complete) >= active_design.minimum_complete_development_pairs
    success_floor = candidate_successes / len(contexts) >= 0.50
    passed = adequate and success_floor and wins > losses and p_value <= (
        active_design.paired_design.alpha
    )

    per_control: list[tuple[str, int, int, int]] = []
    for baseline in LivingDexCausalBaseline:
        counts = Counter(item.disposition_against(baseline) for item in contexts)
        per_control.append(
            (
                baseline.value,
                counts[LivingDexPairedDisposition.CANDIDATE_WIN],
                counts[LivingDexPairedDisposition.CANDIDATE_LOSS],
                counts[LivingDexPairedDisposition.TIE],
            )
        )
    return LivingDexCausalPolicyEvaluation(
        design_sha256=active_design.design_sha256,
        attempted_contexts=len(contexts),
        complete_contexts=len(complete),
        censored_contexts=len(contexts) - len(complete),
        candidate_wins=wins,
        candidate_losses=losses,
        complete_case_candidate_losses=complete_case_dispositions[
            LivingDexPairedDisposition.CANDIDATE_LOSS
        ],
        conservative_censored_losses=len(contexts) - len(complete),
        ties=ties,
        candidate_successes=candidate_successes,
        baseline_envelope_successes=envelope_successes,
        exact_one_sided_p=p_value,
        focus_kind_counts=tuple(sorted(focus_counts.items())),
        per_control=tuple(per_control),
        factual_branch_executions=sum(
            item.unique_factual_branch_count for item in contexts
        ),
        distinct_physical_roots=len(
            {item.physical_root_sha256 for item in contexts}
        ),
        distinct_independence_lineages=len(
            {item.independence_lineage_sha256 for item in contexts}
        ),
        adequate_complete_contexts=adequate,
        candidate_success_floor_passed=success_floor,
        promotion_gate_passed=passed,
    )


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexCausalPolicyEvaluationError(f"{subject} SHA-256 differs")
    return value


__all__ = [
    "LIVING_DEX_CAUSAL_POLICY_CONTEXT_SCHEMA",
    "LIVING_DEX_CAUSAL_POLICY_EVALUATION_SCHEMA",
    "LivingDexCausalBaseline",
    "LivingDexCausalControlOutcome",
    "LivingDexCausalPolicyContextResult",
    "LivingDexCausalPolicyEvaluation",
    "LivingDexCausalPolicyEvaluationError",
    "LivingDexPairedDisposition",
    "evaluate_living_dex_causal_policy",
]
