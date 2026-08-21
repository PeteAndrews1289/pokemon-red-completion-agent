"""Pure one-decision shadow bridge from authentic Red state to the dependency ranker.

The module deliberately has no filesystem, emulator, controller, or private-artifact
imports.  A runner must first derive an authenticated Red collection observation and
mechanical execution facts, then call :func:`prepare_red_dependency_shadow`.  The
prepared identity fixes the complete opportunity scan and the first eligible menu
before :func:`score_red_dependency_shadow` may call the frozen ranker.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.living_dex_dependency_ranker import DependencyRankerModel
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedLivingDexDependencyAdapterResult,
    RedLivingDexDependencyOpportunity,
)

RED_LIVING_DEX_DEPENDENCY_SHADOW_PREPARATION_SCHEMA = (
    "pokemon.red.private-living-dex-dependency-shadow-preparation.v1"
)
RED_LIVING_DEX_DEPENDENCY_SHADOW_TERMINAL_SCHEMA = (
    "pokemon.red.private-living-dex-dependency-shadow-terminal.v1"
)
RED_LIVING_DEX_DEPENDENCY_SHADOW_STOP_SCHEMA = (
    "pokemon.red.private-living-dex-dependency-shadow-stop.v1"
)
RED_LIVING_DEX_DEPENDENCY_SHADOW_STATUS = "shadow_preference_recorded_zero_action"
RED_LIVING_DEX_DEPENDENCY_SHADOW_NO_ELIGIBLE_STATUS = (
    "no_eligible_opportunity_zero_prediction_zero_action"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexDependencyShadowError(ValueError):
    """The frozen shadow decision or its title-neutral boundary differs."""


class RedDependencyShadowCandidateKind(StrEnum):
    """The exact two-option order seen by the title-neutral ranker."""

    ACQUIRE_PRECURSOR = "acquire_precursor"
    TRANSFORM_PRECURSOR = "transform_precursor"


@dataclass(frozen=True, slots=True)
class PreparedRedDependencyShadow:
    """One exact context and menu frozen before any model score is requested."""

    design_sha256: str
    model_sha256: str
    context_identity_sha256: str
    opportunity_scan_sha256: str
    selected_opportunity_ordinal: int
    opportunity: RedLivingDexDependencyOpportunity
    candidate_rows: tuple[dict[str, int | str], ...]
    semantic_identity_sha256: str

    def __post_init__(self) -> None:
        for value, subject in (
            (self.design_sha256, "design"),
            (self.model_sha256, "model"),
            (self.context_identity_sha256, "context"),
            (self.opportunity_scan_sha256, "opportunity scan"),
            (self.semantic_identity_sha256, "semantic identity"),
        ):
            _require_sha256(value, subject)
        if (
            type(self.selected_opportunity_ordinal) is not int  # noqa: E721
            or self.selected_opportunity_ordinal < 0
            or not isinstance(self.opportunity, RedLivingDexDependencyOpportunity)
            or not self.opportunity.execution_qualified
            or self.candidate_rows != self.opportunity.policy_rows()
            or len(self.candidate_rows) != 2
        ):
            raise RedLivingDexDependencyShadowError("prepared shadow menu differs")
        expected = _semantic_identity(
            design_sha256=self.design_sha256,
            model_sha256=self.model_sha256,
            context_identity_sha256=self.context_identity_sha256,
            opportunity_scan_sha256=self.opportunity_scan_sha256,
            selected_opportunity_ordinal=self.selected_opportunity_ordinal,
            opportunity=self.opportunity,
            candidate_rows=self.candidate_rows,
        )
        if self.semantic_identity_sha256 != expected:
            raise RedLivingDexDependencyShadowError("shadow semantic identity differs")

    def private_dict(self) -> dict[str, object]:
        """Return the pre-score identity; this document must never be public."""

        return {
            "schema": RED_LIVING_DEX_DEPENDENCY_SHADOW_PREPARATION_SCHEMA,
            "design_sha256": self.design_sha256,
            "model_sha256": self.model_sha256,
            "context_identity_sha256": self.context_identity_sha256,
            "opportunity_scan_sha256": self.opportunity_scan_sha256,
            "selected_opportunity_ordinal": self.selected_opportunity_ordinal,
            "opportunity_binding_sha256": self.opportunity.binding.binding_sha256,
            "candidate_rows": [dict(row) for row in self.candidate_rows],
            "semantic_identity_sha256": self.semantic_identity_sha256,
            "model_predictions": 0,
        }


@dataclass(frozen=True, slots=True)
class RedDependencyShadowStop:
    """A zero-prediction stop when the frozen context has no eligible menu."""

    design_sha256: str
    model_sha256: str
    context_identity_sha256: str
    opportunity_scan_sha256: str

    def __post_init__(self) -> None:
        for value, subject in (
            (self.design_sha256, "design"),
            (self.model_sha256, "model"),
            (self.context_identity_sha256, "context"),
            (self.opportunity_scan_sha256, "opportunity scan"),
        ):
            _require_sha256(value, subject)

    def public_dict(self) -> dict[str, object]:
        """Return only the frozen aggregate fields; no identity crosses this boundary."""

        return _public_result(
            status=RED_LIVING_DEX_DEPENDENCY_SHADOW_NO_ELIGIBLE_STATUS,
            candidate_count=0,
            selected_candidate_kind=None,
            selected_candidate_probability=None,
            score_margin=None,
            model_predictions=0,
        )

    @property
    def semantic_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": RED_LIVING_DEX_DEPENDENCY_SHADOW_STOP_SCHEMA,
                "design_sha256": self.design_sha256,
                "model_sha256": self.model_sha256,
                "context_identity_sha256": self.context_identity_sha256,
                "opportunity_scan_sha256": self.opportunity_scan_sha256,
                "status": RED_LIVING_DEX_DEPENDENCY_SHADOW_NO_ELIGIBLE_STATUS,
            }
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": RED_LIVING_DEX_DEPENDENCY_SHADOW_PREPARATION_SCHEMA,
            "design_sha256": self.design_sha256,
            "model_sha256": self.model_sha256,
            "context_identity_sha256": self.context_identity_sha256,
            "opportunity_scan_sha256": self.opportunity_scan_sha256,
            "semantic_identity_sha256": self.semantic_identity_sha256,
            "model_predictions": 0,
        }

    def private_terminal_dict(self) -> dict[str, object]:
        return {
            **self.private_dict(),
            "schema": RED_LIVING_DEX_DEPENDENCY_SHADOW_STOP_SCHEMA,
            "status": RED_LIVING_DEX_DEPENDENCY_SHADOW_NO_ELIGIBLE_STATUS,
            "model_predictions": 0,
            "controller_actions": 0,
            "emulator_frames_advanced": 0,
            "teacher_queries": 0,
        }


@dataclass(frozen=True, slots=True)
class RedDependencyShadowDecision:
    """Exactly one full-menu ranker preference with no action or outcome."""

    preparation: PreparedRedDependencyShadow
    selected_candidate_kind: RedDependencyShadowCandidateKind
    selected_candidate_probability: float
    score_margin: float
    acquire_score: float
    transform_score: float

    def __post_init__(self) -> None:
        if not isinstance(self.preparation, PreparedRedDependencyShadow) or not isinstance(
            self.selected_candidate_kind, RedDependencyShadowCandidateKind
        ):
            raise RedLivingDexDependencyShadowError("shadow decision type differs")
        if any(
            type(value) is not float or not math.isfinite(value)  # noqa: E721
            for value in (
                self.selected_candidate_probability,
                self.score_margin,
                self.acquire_score,
                self.transform_score,
            )
        ):
            raise RedLivingDexDependencyShadowError("shadow score differs")
        if not 0.5 <= self.selected_candidate_probability <= 1.0 or self.score_margin < 0.0:
            raise RedLivingDexDependencyShadowError("shadow preference differs")
        expected_kind = (
            RedDependencyShadowCandidateKind.ACQUIRE_PRECURSOR
            if self.acquire_score >= self.transform_score
            else RedDependencyShadowCandidateKind.TRANSFORM_PRECURSOR
        )
        acquire_probability = _sigmoid(self.acquire_score - self.transform_score)
        expected_probability = (
            acquire_probability
            if expected_kind is RedDependencyShadowCandidateKind.ACQUIRE_PRECURSOR
            else 1.0 - acquire_probability
        )
        if (
            self.selected_candidate_kind is not expected_kind
            or self.score_margin != abs(self.acquire_score - self.transform_score)
            or not math.isclose(
                self.selected_candidate_probability,
                expected_probability,
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        ):
            raise RedLivingDexDependencyShadowError("shadow decision differs")

    def public_dict(self) -> dict[str, object]:
        """Return the exact aggregate-only public result frozen by the design."""

        return _public_result(
            status=RED_LIVING_DEX_DEPENDENCY_SHADOW_STATUS,
            candidate_count=2,
            selected_candidate_kind=self.selected_candidate_kind.value,
            selected_candidate_probability=self.selected_candidate_probability,
            score_margin=self.score_margin,
            model_predictions=1,
        )

    def private_terminal_dict(self) -> dict[str, object]:
        """Bind exact context/menu/model facts behind the private boundary."""

        return {
            **self.preparation.private_dict(),
            "schema": RED_LIVING_DEX_DEPENDENCY_SHADOW_TERMINAL_SCHEMA,
            "status": RED_LIVING_DEX_DEPENDENCY_SHADOW_STATUS,
            "selected_candidate_kind": self.selected_candidate_kind.value,
            "selected_candidate_probability": self.selected_candidate_probability,
            "score_margin": self.score_margin,
            "acquire_score": self.acquire_score,
            "transform_score": self.transform_score,
            "model_predictions": 1,
            "controller_actions": 0,
            "emulator_frames_advanced": 0,
            "teacher_queries": 0,
        }


def prepare_red_dependency_shadow(
    adapter_result: RedLivingDexDependencyAdapterResult,
    *,
    design_sha256: str,
    model_sha256: str,
    context_identity_sha256: str,
    execution_capable_binding_sha256s: frozenset[str] | None = None,
) -> PreparedRedDependencyShadow | RedDependencyShadowStop:
    """Freeze the first catalog-order eligible opportunity without scoring a model."""

    if not isinstance(adapter_result, RedLivingDexDependencyAdapterResult):
        raise TypeError("adapter_result must be a RedLivingDexDependencyAdapterResult")
    for value, subject in (
        (design_sha256, "design"),
        (model_sha256, "model"),
        (context_identity_sha256, "context"),
    ):
        _require_sha256(value, subject)
    if execution_capable_binding_sha256s is not None and (
        not isinstance(execution_capable_binding_sha256s, frozenset)
        or any(
            not isinstance(value, str) or _SHA256.fullmatch(value) is None
            for value in execution_capable_binding_sha256s
        )
    ):
        raise RedLivingDexDependencyShadowError("execution capability identity differs")
    capability_filter = (
        frozenset(
            item.binding.binding_sha256
            for item in adapter_result.opportunities
            if item.execution_qualified
        )
        if execution_capable_binding_sha256s is None
        else execution_capable_binding_sha256s
    )
    opportunity_scan_sha256 = _opportunity_scan_sha256(adapter_result, capability_filter)
    selected = next(
        (
            (ordinal, opportunity)
            for ordinal, opportunity in enumerate(adapter_result.opportunities)
            if opportunity.execution_qualified
            and opportunity.binding.binding_sha256 in capability_filter
        ),
        None,
    )
    if selected is None:
        return RedDependencyShadowStop(
            design_sha256,
            model_sha256,
            context_identity_sha256,
            opportunity_scan_sha256,
        )
    ordinal, opportunity = selected
    rows = opportunity.policy_rows()
    semantic_identity = _semantic_identity(
        design_sha256=design_sha256,
        model_sha256=model_sha256,
        context_identity_sha256=context_identity_sha256,
        opportunity_scan_sha256=opportunity_scan_sha256,
        selected_opportunity_ordinal=ordinal,
        opportunity=opportunity,
        candidate_rows=rows,
    )
    return PreparedRedDependencyShadow(
        design_sha256,
        model_sha256,
        context_identity_sha256,
        opportunity_scan_sha256,
        ordinal,
        opportunity,
        rows,
        semantic_identity,
    )


def score_red_dependency_shadow(
    preparation: PreparedRedDependencyShadow,
    model: DependencyRankerModel,
) -> RedDependencyShadowDecision:
    """Score the already-frozen two-row menu as exactly one model decision."""

    if not isinstance(preparation, PreparedRedDependencyShadow):
        raise TypeError("preparation must be a PreparedRedDependencyShadow")
    if not isinstance(model, DependencyRankerModel):
        raise TypeError("model must be a DependencyRankerModel")
    if model.model_sha256 != preparation.model_sha256:
        raise RedLivingDexDependencyShadowError("dependency model identity differs")
    acquire_score, transform_score = tuple(
        float(model.score(candidate)) for candidate in preparation.opportunity.candidates
    )
    if not math.isfinite(acquire_score) or not math.isfinite(transform_score):
        raise RedLivingDexDependencyShadowError("dependency model score is not finite")
    acquire_probability = _sigmoid(acquire_score - transform_score)
    if acquire_score >= transform_score:
        selected_kind = RedDependencyShadowCandidateKind.ACQUIRE_PRECURSOR
        selected_probability = acquire_probability
    else:
        selected_kind = RedDependencyShadowCandidateKind.TRANSFORM_PRECURSOR
        selected_probability = 1.0 - acquire_probability
    return RedDependencyShadowDecision(
        preparation=preparation,
        selected_candidate_kind=selected_kind,
        selected_candidate_probability=float(selected_probability),
        score_margin=float(abs(acquire_score - transform_score)),
        acquire_score=acquire_score,
        transform_score=transform_score,
    )


def _opportunity_scan_sha256(
    result: RedLivingDexDependencyAdapterResult,
    execution_capable_binding_sha256s: frozenset[str],
) -> str:
    rows = []
    for ordinal, opportunity in enumerate(result.opportunities):
        rows.append(
            {
                "ordinal": ordinal,
                "binding_sha256": opportunity.binding.binding_sha256,
                "status": opportunity.status.value,
                "candidate_readiness": [value.value for value in opportunity.candidate_readiness],
                "candidate_rows": [dict(row) for row in opportunity.policy_rows()],
                "exact_skill_pair_attested": (
                    opportunity.binding.binding_sha256 in execution_capable_binding_sha256s
                ),
            }
        )
    return canonical_sha256(
        {
            "schema": "pokemon.red.private-living-dex-dependency-opportunity-scan.v1",
            "rows": rows,
        }
    )


def _semantic_identity(
    *,
    design_sha256: str,
    model_sha256: str,
    context_identity_sha256: str,
    opportunity_scan_sha256: str,
    selected_opportunity_ordinal: int,
    opportunity: RedLivingDexDependencyOpportunity,
    candidate_rows: tuple[dict[str, int | str], ...],
) -> str:
    return canonical_sha256(
        {
            "schema": RED_LIVING_DEX_DEPENDENCY_SHADOW_PREPARATION_SCHEMA,
            "design_sha256": design_sha256,
            "model_sha256": model_sha256,
            "context_identity_sha256": context_identity_sha256,
            "opportunity_scan_sha256": opportunity_scan_sha256,
            "selected_opportunity_ordinal": selected_opportunity_ordinal,
            "opportunity_binding_sha256": opportunity.binding.binding_sha256,
            "candidate_rows": [dict(row) for row in candidate_rows],
        }
    )


def _public_result(
    *,
    status: str,
    candidate_count: int,
    selected_candidate_kind: str | None,
    selected_candidate_probability: float | None,
    score_margin: float | None,
    model_predictions: int,
) -> dict[str, object]:
    return {
        "status": status,
        "candidate_count": candidate_count,
        "selected_candidate_kind": selected_candidate_kind,
        "selected_candidate_probability": selected_candidate_probability,
        "score_margin": score_margin,
        "model_predictions": model_predictions,
        "controller_actions": 0,
        "emulator_frames_advanced": 0,
        "teacher_queries": 0,
        "identity_fields_public": 0,
    }


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexDependencyShadowError(f"{subject} identity differs")
    return value


__all__ = [
    "RED_LIVING_DEX_DEPENDENCY_SHADOW_NO_ELIGIBLE_STATUS",
    "RED_LIVING_DEX_DEPENDENCY_SHADOW_PREPARATION_SCHEMA",
    "RED_LIVING_DEX_DEPENDENCY_SHADOW_STATUS",
    "RED_LIVING_DEX_DEPENDENCY_SHADOW_STOP_SCHEMA",
    "RED_LIVING_DEX_DEPENDENCY_SHADOW_TERMINAL_SCHEMA",
    "PreparedRedDependencyShadow",
    "RedDependencyShadowCandidateKind",
    "RedDependencyShadowDecision",
    "RedDependencyShadowStop",
    "RedLivingDexDependencyShadowError",
    "prepare_red_dependency_shadow",
    "score_red_dependency_shadow",
]
