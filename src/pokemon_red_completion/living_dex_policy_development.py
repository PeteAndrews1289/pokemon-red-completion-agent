"""Title-neutral commitment for one model-led development decision.

Development evaluates a frozen option-value model on a menu that was held away
from fitting.  This module turns that evaluation into an immutable, replayable
choice before any title adapter may release controller authority.  It does not
open a runtime, execute an option, observe an outcome, fit a model, or emit a
training target.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from pokemon_red_completion.living_dex_causal_journal import LivingDexCausalScenario
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOptionUtility,
    LivingDexOptionValueModel,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_POLICY_DEVELOPMENT_DECISION_SCHEMA = (
    "pokemon.core.private-living-dex-policy-development-decision.v1"
)
LIVING_DEX_POLICY_DEVELOPMENT_PUBLIC_SCHEMA = (
    "pokemon.core.living-dex-policy-development-decision.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class LivingDexPolicyDevelopmentError(ValueError):
    """A held menu or exact model cannot produce one replayable decision."""


@dataclass(frozen=True, slots=True)
class LivingDexPolicyDevelopmentDecision:
    """One complete model score vector committed before controller release."""

    causal_identity_sha256: str
    menu_sha256: str
    model_sha256: str
    utility_sha256: str
    selected_candidate_index: int
    candidate_scores: tuple[float | None, ...]
    predicted_outcomes: tuple[tuple[float, ...] | None, ...]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.causal_identity_sha256, "causal identity"),
            (self.menu_sha256, "menu"),
            (self.model_sha256, "model"),
            (self.utility_sha256, "utility"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise LivingDexPolicyDevelopmentError(
                    f"development {subject} differs"
                )
        if (
            type(self.selected_candidate_index) is not int  # noqa: E721
            or self.selected_candidate_index < 0
            or not isinstance(self.candidate_scores, tuple)
            or len(self.candidate_scores) < 2
            or not isinstance(self.predicted_outcomes, tuple)
            or len(self.predicted_outcomes) != len(self.candidate_scores)
        ):
            raise LivingDexPolicyDevelopmentError(
                "development choice dimensions differ"
            )
        available: list[int] = []
        for index, (score, outcome) in enumerate(
            zip(self.candidate_scores, self.predicted_outcomes, strict=True)
        ):
            if score is None:
                if outcome is not None:
                    raise LivingDexPolicyDevelopmentError(
                        "masked development candidate retained a prediction"
                    )
                continue
            if (
                type(score) is not float  # noqa: E721
                or not math.isfinite(score)
                or not isinstance(outcome, tuple)
                or len(outcome) != len(LIVING_DEX_OPTION_OUTCOME_NAMES)
                or any(
                    type(value) is not float  # noqa: E721
                    or not math.isfinite(value)
                    or not 0.0 <= value <= 1.0
                    for value in outcome
                )
            ):
                raise LivingDexPolicyDevelopmentError(
                    "development prediction differs"
                )
            available.append(index)
        if len(available) < 2 or self.selected_candidate_index not in available:
            raise LivingDexPolicyDevelopmentError(
                "development selected candidate is unavailable"
            )
        expected = max(
            available,
            key=lambda index: (self.candidate_scores[index], -index),
        )
        if self.selected_candidate_index != expected:
            raise LivingDexPolicyDevelopmentError(
                "development choice does not replay from scores"
            )

    @property
    def decision_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "candidate_scores": list(self.candidate_scores),
            "causal_identity_sha256": self.causal_identity_sha256,
            "menu_sha256": self.menu_sha256,
            "model_sha256": self.model_sha256,
            "predicted_outcomes": [
                None if item is None else list(item)
                for item in self.predicted_outcomes
            ],
            "schema": LIVING_DEX_POLICY_DEVELOPMENT_DECISION_SCHEMA,
            "selected_candidate_index": self.selected_candidate_index,
            "utility_sha256": self.utility_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_count": len(self.candidate_scores),
            "candidate_scores": list(self.candidate_scores),
            "decision_sha256": self.decision_sha256,
            "model_fits": 0,
            "model_predictions": 1,
            "model_sha256": self.model_sha256,
            "predicted_outcomes": [
                None
                if item is None
                else dict(zip(LIVING_DEX_OPTION_OUTCOME_NAMES, item, strict=True))
                for item in self.predicted_outcomes
            ],
            "private_binding_fields": 0,
            "private_path_fields": 0,
            "schema": LIVING_DEX_POLICY_DEVELOPMENT_PUBLIC_SCHEMA,
            "selected_candidate_index": self.selected_candidate_index,
            "teacher_queries": 0,
            "training_targets_emitted": 0,
            "utility_sha256": self.utility_sha256,
        }


def living_dex_option_utility_sha256(utility: LivingDexOptionUtility) -> str:
    """Bind all fixed planning weights without depending on a title adapter."""

    if not isinstance(utility, LivingDexOptionUtility):
        raise TypeError("development decision needs an option utility")
    utility.__post_init__()
    return canonical_sha256(
        {
            "action_cost_weight": utility.action_cost_weight,
            "completion_gain_weight": utility.completion_gain_weight,
            "dependency_unlock_weight": utility.dependency_unlock_weight,
            "frame_cost_weight": utility.frame_cost_weight,
            "irreversible_loss_weight": utility.irreversible_loss_weight,
            "party_cost_weight": utility.party_cost_weight,
            "resource_cost_weight": utility.resource_cost_weight,
            "schema": "pokemon.core.living-dex-option-utility.v1",
            "storage_cost_weight": utility.storage_cost_weight,
            "success_weight": utility.success_weight,
        }
    )


def commit_living_dex_policy_development_decision(
    scenario: LivingDexCausalScenario,
    model: LivingDexOptionValueModel,
    *,
    utility: LivingDexOptionUtility,
    expected_model_sha256: str,
) -> LivingDexPolicyDevelopmentDecision:
    """Score one held menu exactly once without touching its runtime hooks."""

    if not isinstance(scenario, LivingDexCausalScenario):
        raise TypeError("development decision needs a causal scenario")
    scenario.__post_init__()
    if scenario.identity.partition != "development":
        raise LivingDexPolicyDevelopmentError(
            "development decision received another partition"
        )
    if not isinstance(model, LivingDexOptionValueModel):
        raise TypeError("development decision needs an option-value model")
    model.__post_init__()
    if (
        not isinstance(expected_model_sha256, str)
        or _SHA256.fullmatch(expected_model_sha256) is None
        or model.model_sha256 != expected_model_sha256
    ):
        raise LivingDexPolicyDevelopmentError(
            "development model identity differs"
        )
    scores = model.scores(scenario.menu, utility)
    selected = model.select(scenario.menu, utility)
    outcomes = tuple(
        model.predict_candidate(scenario.menu.context, candidate).vector()
        if index in scenario.menu.available_indices
        else None
        for index, candidate in enumerate(scenario.menu.candidates)
    )
    return LivingDexPolicyDevelopmentDecision(
        causal_identity_sha256=scenario.identity.identity_sha256,
        menu_sha256=scenario.menu.policy_sha256,
        model_sha256=model.model_sha256,
        utility_sha256=living_dex_option_utility_sha256(utility),
        selected_candidate_index=selected,
        candidate_scores=scores,
        predicted_outcomes=outcomes,
    )


__all__ = [
    "LIVING_DEX_POLICY_DEVELOPMENT_DECISION_SCHEMA",
    "LIVING_DEX_POLICY_DEVELOPMENT_PUBLIC_SCHEMA",
    "LivingDexPolicyDevelopmentDecision",
    "LivingDexPolicyDevelopmentError",
    "commit_living_dex_policy_development_decision",
    "living_dex_option_utility_sha256",
]
