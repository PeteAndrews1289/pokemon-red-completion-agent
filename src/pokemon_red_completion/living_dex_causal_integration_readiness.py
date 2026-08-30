"""Eight-row train-only plumbing gate for causal living-Pokedex learning.

This is deliberately smaller than the powered 60/90-row fit-readiness gate.
It asks only whether the complete first authentic corpus can exercise one
explicitly non-authoritative integration fit without hiding an awkward row.
It never fits, predicts, executes gameplay, queries a teacher, or reads a
development schedule.  Passing this gate proves wiring and minimal information
contrast, not policy quality, gameplay authority, or cross-title transfer.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pokemon_red_completion.living_dex_causal_curriculum import (
    red_setup_policy_feature_row_supported,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexAuthenticatedCausalExample,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOutcomeStatus,
)

LIVING_DEX_CAUSAL_INTEGRATION_READINESS_SCHEMA = (
    "pokemon.core.living-dex-causal-integration-readiness.v1"
)
INTEGRATION_EXPECTED_AUTHENTIC_EXAMPLES = 8
INTEGRATION_MINIMUM_TRAIN_LINEAGES = 4
INTEGRATION_MINIMUM_SELECTED_OPTION_KINDS = 4
INTEGRATION_MAXIMUM_EXAMPLES_PER_LINEAGE = 2
INTEGRATION_MINIMUM_DISTINCT_SELECTED_FEATURE_ROWS = 4
INTEGRATION_MINIMUM_VARIABLE_TARGET_HEADS = 1


class LivingDexCausalIntegrationReadinessError(ValueError):
    """The first authentic causal corpus cannot open the plumbing fit."""


@dataclass(frozen=True, slots=True)
class LivingDexCausalIntegrationReadiness:
    """Path-free aggregate result over every authenticated causal example."""

    authentic_examples: int
    train_examples: int
    development_examples: int
    settled_examples: int
    censored_examples: int
    distinct_causal_identities: int
    distinct_decision_identities: int
    distinct_lineages: int
    maximum_lineage_multiplicity: int
    distinct_selected_option_kinds: int
    candidate_feature_rows: int
    supported_candidate_feature_rows: int
    distinct_selected_feature_rows: int
    variable_target_heads: int
    verified_success_varies: bool
    full_support_examples: int
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.reasons

    def public_dict(self) -> dict[str, object]:
        return {
            "audit_scope": "complete-authenticated-causal-example-family",
            "authentic_examples": self.authentic_examples,
            "candidate_feature_rows": self.candidate_feature_rows,
            "censored_examples": self.censored_examples,
            "complete_denominator_included": True,
            "controller_actions": 0,
            "counterfactual_targets": 0,
            "development_examples": self.development_examples,
            "development_schedule_reads": 0,
            "distinct_causal_identities": self.distinct_causal_identities,
            "distinct_decision_identities": self.distinct_decision_identities,
            "distinct_lineages": self.distinct_lineages,
            "distinct_selected_feature_rows": (
                self.distinct_selected_feature_rows
            ),
            "distinct_selected_option_kinds": (
                self.distinct_selected_option_kinds
            ),
            "emulator_frames": 0,
            "fit_authority_if_ready": "non-authoritative-integration-only",
            "fit_executions": 0,
            "full_support_examples": self.full_support_examples,
            "integration_fit_allowed": self.ready,
            "maximum_lineage_multiplicity": self.maximum_lineage_multiplicity,
            "minimum_contract": {
                "authentic_examples": INTEGRATION_EXPECTED_AUTHENTIC_EXAMPLES,
                "distinct_selected_feature_rows": (
                    INTEGRATION_MINIMUM_DISTINCT_SELECTED_FEATURE_ROWS
                ),
                "maximum_examples_per_lineage": (
                    INTEGRATION_MAXIMUM_EXAMPLES_PER_LINEAGE
                ),
                "selected_option_kinds": (
                    INTEGRATION_MINIMUM_SELECTED_OPTION_KINDS
                ),
                "train_lineages": INTEGRATION_MINIMUM_TRAIN_LINEAGES,
                "variable_target_heads": (
                    INTEGRATION_MINIMUM_VARIABLE_TARGET_HEADS
                ),
            },
            "model_predictions": 0,
            "outcome_aware_row_selection": False,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "reason_codes": list(self.reasons),
            "root_claims": 0,
            "schema": LIVING_DEX_CAUSAL_INTEGRATION_READINESS_SCHEMA,
            "settled_examples": self.settled_examples,
            "supported_candidate_feature_rows": (
                self.supported_candidate_feature_rows
            ),
            "teacher_queries": 0,
            "train_examples": self.train_examples,
            "transfer_claimed": False,
            "unselected_action_targets": 0,
            "variable_target_heads": self.variable_target_heads,
            "verified_success_varies": self.verified_success_varies,
        }


def audit_living_dex_causal_integration_readiness(
    examples: tuple[LivingDexAuthenticatedCausalExample, ...],
) -> LivingDexCausalIntegrationReadiness:
    """Audit every authenticated row against the frozen eight-row contract."""

    if not isinstance(examples, tuple) or any(
        not isinstance(row, LivingDexAuthenticatedCausalExample) for row in examples
    ):
        raise TypeError("integration readiness needs authenticated causal examples")

    identities = tuple(row.identity.identity_sha256 for row in examples)
    decisions = tuple(row.example.decision_sha256 for row in examples)
    lineages = Counter(row.identity.lineage_sha256 for row in examples)
    train = tuple(row for row in examples if row.example.partition == "train")
    development = tuple(
        row for row in examples if row.example.partition == "development"
    )
    settled = tuple(
        row
        for row in examples
        if row.example.outcome.status is LivingDexOutcomeStatus.SETTLED
    )
    censored = tuple(
        row
        for row in examples
        if row.example.outcome.status is LivingDexOutcomeStatus.CENSORED
    )
    selected_kinds = {
        row.example.menu.candidates[
            row.example.selected_candidate_index
        ].features.kind
        for row in settled
    }
    candidate_features = tuple(
        candidate.features
        for row in examples
        for candidate in row.example.menu.candidates
    )
    supported_candidate_features = tuple(
        features
        for features in candidate_features
        if red_setup_policy_feature_row_supported(features)
    )
    selected_vectors = tuple(row.example.selected_vector for row in settled)
    target_vectors = tuple(
        target
        for row in settled
        if (target := row.example.outcome.target_vector) is not None
    )
    variable_heads = tuple(
        name
        for index, name in enumerate(LIVING_DEX_OPTION_OUTCOME_NAMES)
        if len({target[index] for target in target_vectors}) > 1
    )
    full_support = tuple(
        row
        for row in examples
        if all(
            (probability > 0.0) is (index in row.example.menu.available_indices)
            for index, probability in enumerate(row.example.behavior_probabilities)
        )
    )

    reasons: list[str] = []
    if len(examples) != INTEGRATION_EXPECTED_AUTHENTIC_EXAMPLES:
        reasons.append("authentic_example_denominator_differs")
    if len(train) != len(examples) or development:
        reasons.append("train_only_partition_differs")
    if len(settled) != len(examples) or censored:
        reasons.append("unsettled_or_censored_example_present")
    if len(set(identities)) != len(examples):
        reasons.append("repeated_causal_identity")
    if len(set(decisions)) != len(examples):
        reasons.append("repeated_decision_identity")
    if len(lineages) < INTEGRATION_MINIMUM_TRAIN_LINEAGES:
        reasons.append("insufficient_independent_lineages")
    if lineages and max(lineages.values()) > INTEGRATION_MAXIMUM_EXAMPLES_PER_LINEAGE:
        reasons.append("lineage_multiplicity_exceeds_bound")
    if len(selected_kinds) < INTEGRATION_MINIMUM_SELECTED_OPTION_KINDS:
        reasons.append("insufficient_selected_option_kinds")
    if len(supported_candidate_features) != len(candidate_features):
        reasons.append("unsupported_red_candidate_feature_row")
    if (
        len(set(selected_vectors))
        < INTEGRATION_MINIMUM_DISTINCT_SELECTED_FEATURE_ROWS
    ):
        reasons.append("insufficient_selected_feature_contrast")
    if len(variable_heads) < INTEGRATION_MINIMUM_VARIABLE_TARGET_HEADS:
        reasons.append("insufficient_target_variation")
    if len(full_support) != len(examples):
        reasons.append("behavior_full_support_differs")

    return LivingDexCausalIntegrationReadiness(
        authentic_examples=len(examples),
        train_examples=len(train),
        development_examples=len(development),
        settled_examples=len(settled),
        censored_examples=len(censored),
        distinct_causal_identities=len(set(identities)),
        distinct_decision_identities=len(set(decisions)),
        distinct_lineages=len(lineages),
        maximum_lineage_multiplicity=max(lineages.values(), default=0),
        distinct_selected_option_kinds=len(selected_kinds),
        candidate_feature_rows=len(candidate_features),
        supported_candidate_feature_rows=len(supported_candidate_features),
        distinct_selected_feature_rows=len(set(selected_vectors)),
        variable_target_heads=len(variable_heads),
        verified_success_varies="verified_success" in variable_heads,
        full_support_examples=len(full_support),
        reasons=tuple(reasons),
    )


def require_living_dex_causal_integration_ready(
    examples: tuple[LivingDexAuthenticatedCausalExample, ...],
) -> LivingDexCausalIntegrationReadiness:
    audit = audit_living_dex_causal_integration_readiness(examples)
    if not audit.ready:
        raise LivingDexCausalIntegrationReadinessError(
            "causal integration readiness failed closed"
        )
    return audit


__all__ = [
    "INTEGRATION_EXPECTED_AUTHENTIC_EXAMPLES",
    "INTEGRATION_MAXIMUM_EXAMPLES_PER_LINEAGE",
    "INTEGRATION_MINIMUM_DISTINCT_SELECTED_FEATURE_ROWS",
    "INTEGRATION_MINIMUM_SELECTED_OPTION_KINDS",
    "INTEGRATION_MINIMUM_TRAIN_LINEAGES",
    "INTEGRATION_MINIMUM_VARIABLE_TARGET_HEADS",
    "LIVING_DEX_CAUSAL_INTEGRATION_READINESS_SCHEMA",
    "LivingDexCausalIntegrationReadiness",
    "LivingDexCausalIntegrationReadinessError",
    "audit_living_dex_causal_integration_readiness",
    "require_living_dex_causal_integration_ready",
]
