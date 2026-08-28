"""Outcome-blind gate between causal collection and option-model fitting.

The prospective schedule may attempt ninety Red contexts, yet controller
interruptions or unexpectedly uniform outcomes can still leave a dataset that
cannot support a useful fit.  This module audits the *complete attempted
denominator* before a fitter may consume any row.  It therefore cannot improve
its verdict by silently dropping failures, censored rows, awkward option kinds,
or the one immutable development-rigor prefix example.

The audit performs no fit, prediction, policy choice, gameplay, or teacher
query.  It returns only aggregate, path-free diagnostics.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
    LivingDexCausalCurriculumDesign,
    red_setup_policy_feature_row_supported,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexObservedArmExample,
    LivingDexOptionValueFit,
    LivingDexOutcomeStatus,
    fit_living_dex_option_value,
)

LIVING_DEX_CAUSAL_FIT_READINESS_SCHEMA = "pokemon.core.living-dex-causal-fit-readiness.v1"


class LivingDexCausalFitReadinessError(ValueError):
    """A fit-readiness input violates the frozen prospective denominator."""


@dataclass(frozen=True, slots=True)
class LivingDexCausalFitReadiness:
    """Aggregate proof that the selected-arm dataset is informative enough."""

    design_sha256: str
    prospective_examples: int
    prospective_settled_examples: int
    prospective_censored_examples: int
    prefix_examples: int
    prefix_settled_examples: int
    distinct_decision_identities: int
    distinct_selected_feature_rows: int
    selected_feature_rank: int
    selected_kind_counts: tuple[tuple[str, int], ...]
    settled_kind_counts: tuple[tuple[str, int], ...]
    selected_candidate_index_counts: tuple[tuple[str, int], ...]
    censored_kind_counts: tuple[tuple[str, int], ...]
    censored_candidate_index_counts: tuple[tuple[str, int], ...]
    censor_reason_counts: tuple[tuple[str, int], ...]
    successful_examples: int
    unsuccessful_examples: int
    variable_outcome_heads: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.reasons

    def public_dict(self) -> dict[str, object]:
        return {
            "design_sha256": self.design_sha256,
            "distinct_decision_identities": self.distinct_decision_identities,
            "distinct_selected_feature_rows": self.distinct_selected_feature_rows,
            "fit_executions": 0,
            "model_predictions": 0,
            "prefix_examples": self.prefix_examples,
            "prefix_settled_examples": self.prefix_settled_examples,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "prospective_censored_examples": self.prospective_censored_examples,
            "prospective_examples": self.prospective_examples,
            "prospective_settled_examples": self.prospective_settled_examples,
            "ready": self.ready,
            "reasons": list(self.reasons),
            "schema": LIVING_DEX_CAUSAL_FIT_READINESS_SCHEMA,
            "selected_candidate_index_counts": dict(self.selected_candidate_index_counts),
            "censored_candidate_index_counts": dict(
                self.censored_candidate_index_counts
            ),
            "censored_kind_counts": dict(self.censored_kind_counts),
            "censor_reason_counts": dict(self.censor_reason_counts),
            "selected_feature_rank": self.selected_feature_rank,
            "selected_kind_counts": dict(self.selected_kind_counts),
            "settled_kind_counts": dict(self.settled_kind_counts),
            "successful_examples": self.successful_examples,
            "teacher_queries": 0,
            "unexecuted_action_targets": 0,
            "unsuccessful_examples": self.unsuccessful_examples,
            "variable_outcome_heads": list(self.variable_outcome_heads),
        }


@dataclass(frozen=True, slots=True)
class LivingDexCausalPoweredFit:
    """A fit that could only begin after the powered train gate passed."""

    readiness: LivingDexCausalFitReadiness
    fit: LivingDexOptionValueFit

    def __post_init__(self) -> None:
        if not isinstance(self.readiness, LivingDexCausalFitReadiness) or not isinstance(
            self.fit, LivingDexOptionValueFit
        ):
            raise TypeError("causal powered fit components differ")
        if not self.readiness.ready:
            raise LivingDexCausalFitReadinessError(
                "causal powered fit lacks a passing readiness proof"
            )
        if self.fit.report.total_examples != (
            self.readiness.prospective_examples + self.readiness.prefix_examples
        ):
            raise LivingDexCausalFitReadinessError(
                "causal powered fit omitted part of the frozen denominator"
            )


def audit_living_dex_causal_fit_readiness(
    prospective_examples: Iterable[LivingDexObservedArmExample],
    *,
    prefix_examples: Iterable[LivingDexObservedArmExample],
    design: LivingDexCausalCurriculumDesign | None = None,
) -> LivingDexCausalFitReadiness:
    """Audit all attempted rows without fitting or outcome-dependent selection."""

    active_design = LivingDexCausalCurriculumDesign() if design is None else design
    if not isinstance(active_design, LivingDexCausalCurriculumDesign):
        raise TypeError("causal fit readiness needs its frozen design")
    active_design.__post_init__()
    prospective = tuple(prospective_examples)
    prefix = tuple(prefix_examples)
    combined = (*prospective, *prefix)
    if any(not isinstance(row, LivingDexObservedArmExample) for row in combined):
        raise TypeError("causal fit readiness rows differ")
    for row in combined:
        row.__post_init__()

    settled = tuple(
        row for row in prospective if row.outcome.status is LivingDexOutcomeStatus.SETTLED
    )
    censored = tuple(
        row for row in prospective if row.outcome.status is LivingDexOutcomeStatus.CENSORED
    )
    settled_prefix = tuple(
        row for row in prefix if row.outcome.status is LivingDexOutcomeStatus.SETTLED
    )
    selected_kind_counts = Counter(
        row.menu.candidates[row.selected_candidate_index].features.kind.value for row in prospective
    )
    settled_kind_counts = Counter(
        row.menu.candidates[row.selected_candidate_index].features.kind.value for row in settled
    )
    candidate_index_counts = Counter(str(row.selected_candidate_index) for row in prospective)
    censored_kind_counts = Counter(
        row.menu.candidates[row.selected_candidate_index].features.kind.value
        for row in censored
    )
    censored_candidate_index_counts = Counter(
        str(row.selected_candidate_index) for row in censored
    )
    censor_reason_counts = Counter(
        row.outcome.censor_reason.value
        for row in censored
        if row.outcome.censor_reason is not None
    )
    selected_vectors = tuple(row.selected_vector for row in settled)
    feature_rank = (
        0
        if not selected_vectors
        else int(np.linalg.matrix_rank(np.asarray(selected_vectors, dtype=np.float64)))
    )
    targets = tuple(row.outcome.target_vector for row in settled)
    if any(target is None for target in targets):
        raise LivingDexCausalFitReadinessError("settled causal row lacks its selected-arm target")
    numeric_targets = tuple(target for target in targets if target is not None)
    variable_heads = tuple(
        name
        for index, name in enumerate(LIVING_DEX_OPTION_OUTCOME_NAMES)
        if numeric_targets
        and max(row[index] for row in numeric_targets) - min(row[index] for row in numeric_targets)
        >= active_design.minimum_variable_outcome_range
    )
    successful = sum(bool(row.outcome.verified_success) for row in settled)
    unsuccessful = len(settled) - successful

    reasons: list[str] = []
    if len(prospective) != active_design.prospective_train_contexts:
        reasons.append("prospective_denominator_differs")
    if len(prefix) != active_design.existing_development_rigor_prefix_examples:
        reasons.append("immutable_prefix_denominator_differs")
    if len(settled_prefix) != len(prefix):
        reasons.append("immutable_prefix_not_settled")
    if any(row.partition != "train" for row in combined):
        reasons.append("non_train_row_present")
    decision_ids = tuple(row.decision_sha256 for row in combined)
    if len(decision_ids) != len(set(decision_ids)):
        reasons.append("duplicate_decision_identity")
    if any(
        len(row.menu.candidates) != 3
        or row.menu.available_indices != (0, 1, 2)
        or len(row.behavior_probabilities) != 3
        or any(
            not math.isclose(value, 1.0 / 3.0, rel_tol=0.0, abs_tol=1e-12)
            for value in row.behavior_probabilities
        )
        for row in prospective
    ):
        reasons.append("prospective_behavior_policy_differs")
    if any(
        not red_setup_policy_feature_row_supported(candidate.features)
        for row in combined
        for candidate in row.menu.candidates
    ):
        reasons.append("red_setup_feature_projection_differs")
    expected_kind_counts = active_design.prospective_selected_kind_counts
    if any(
        selected_kind_counts[kind.value] != expected_kind_counts[kind.value]
        for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
    ) or set(selected_kind_counts) != set(expected_kind_counts):
        reasons.append("prospective_selected_kind_schedule_differs")
    if any(candidate_index_counts[str(index)] != 30 for index in range(3)):
        reasons.append("prospective_candidate_position_schedule_differs")
    if len(settled) < active_design.minimum_settled_train_examples:
        reasons.append("insufficient_settled_train_examples")
    if any(
        settled_kind_counts[kind.value] < active_design.minimum_settled_train_examples_per_kind
        for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
    ):
        reasons.append("insufficient_settled_examples_per_kind")
    if len(set(selected_vectors)) < active_design.minimum_distinct_train_feature_rows:
        reasons.append("insufficient_distinct_selected_feature_rows")
    if feature_rank < active_design.minimum_train_feature_rank:
        reasons.append("insufficient_selected_feature_rank")
    if successful < active_design.minimum_successful_train_examples:
        reasons.append("insufficient_successful_train_examples")
    if unsuccessful < active_design.minimum_unsuccessful_train_examples:
        reasons.append("insufficient_unsuccessful_train_examples")
    if len(variable_heads) < active_design.minimum_variable_outcome_heads:
        reasons.append("insufficient_variable_outcome_heads")
    if "verified_success" not in variable_heads:
        reasons.append("verified_success_head_is_constant")

    return LivingDexCausalFitReadiness(
        design_sha256=active_design.design_sha256,
        prospective_examples=len(prospective),
        prospective_settled_examples=len(settled),
        prospective_censored_examples=len(prospective) - len(settled),
        prefix_examples=len(prefix),
        prefix_settled_examples=len(settled_prefix),
        distinct_decision_identities=len(set(decision_ids)),
        distinct_selected_feature_rows=len(set(selected_vectors)),
        selected_feature_rank=feature_rank,
        selected_kind_counts=tuple(sorted(selected_kind_counts.items())),
        settled_kind_counts=tuple(sorted(settled_kind_counts.items())),
        selected_candidate_index_counts=tuple(sorted(candidate_index_counts.items())),
        censored_kind_counts=tuple(sorted(censored_kind_counts.items())),
        censored_candidate_index_counts=tuple(
            sorted(censored_candidate_index_counts.items())
        ),
        censor_reason_counts=tuple(sorted(censor_reason_counts.items())),
        successful_examples=successful,
        unsuccessful_examples=unsuccessful,
        variable_outcome_heads=variable_heads,
        reasons=tuple(sorted(set(reasons))),
    )


def require_living_dex_causal_fit_ready(
    prospective_examples: Iterable[LivingDexObservedArmExample],
    *,
    prefix_examples: Iterable[LivingDexObservedArmExample],
    design: LivingDexCausalCurriculumDesign | None = None,
) -> LivingDexCausalFitReadiness:
    """Return the audit or stop before a low-information fit can begin."""

    audit = audit_living_dex_causal_fit_readiness(
        prospective_examples,
        prefix_examples=prefix_examples,
        design=design,
    )
    if not audit.ready:
        raise LivingDexCausalFitReadinessError(
            "causal fit readiness failed: " + ", ".join(audit.reasons)
        )
    return audit


def fit_powered_living_dex_causal_model(
    prospective_examples: Iterable[LivingDexObservedArmExample],
    *,
    prefix_examples: Iterable[LivingDexObservedArmExample],
    design: LivingDexCausalCurriculumDesign | None = None,
) -> LivingDexCausalPoweredFit:
    """Fit once only after the complete prospective readiness gate passes."""

    prospective = tuple(prospective_examples)
    prefix = tuple(prefix_examples)
    readiness = require_living_dex_causal_fit_ready(
        prospective,
        prefix_examples=prefix,
        design=design,
    )
    fit = fit_living_dex_option_value((*prospective, *prefix))
    return LivingDexCausalPoweredFit(readiness=readiness, fit=fit)


__all__ = [
    "LIVING_DEX_CAUSAL_FIT_READINESS_SCHEMA",
    "LivingDexCausalFitReadiness",
    "LivingDexCausalFitReadinessError",
    "LivingDexCausalPoweredFit",
    "audit_living_dex_causal_fit_readiness",
    "fit_powered_living_dex_causal_model",
    "require_living_dex_causal_fit_ready",
]
