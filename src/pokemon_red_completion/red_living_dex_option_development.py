"""One authentic model-selected Red collection option with an independent outcome.

This is the narrow authority bridge between the already-qualified Red semantic
skills and the title-neutral living-Dex dependency ranker.  Preparation freezes
the complete two-candidate menu before a model is supplied.  Scoring consumes
that preparation exactly once, and execution consumes the resulting decision
exactly once.  The selected skill's return value is never used as the outcome;
a fresh collection-ledger observer is the only source accepted by the verifier.

The seam is deliberately a development primitive.  One episode proves that the
plumbing is real, not that the ranker is good, transferable, or ready for
promotion.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyCandidateFeatures,
)
from pokemon_red_completion.living_dex_dependency_ranker import DependencyRankerModel
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    BoundRedDualCapabilityScenario,
)
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    RedDualCapabilityOutcome,
)

RED_LIVING_DEX_OPTION_PREPARATION_SCHEMA = (
    "pokemon.red.private-living-dex-option-development-preparation.v1"
)
RED_LIVING_DEX_OPTION_DECISION_SCHEMA = (
    "pokemon.red.private-living-dex-option-development-decision.v1"
)
RED_LIVING_DEX_OPTION_EPISODE_SCHEMA = (
    "pokemon.red.private-living-dex-option-development-episode.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CAPABILITY_ORDER = (GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES)
_INTERRUPTION_STAGES = {
    "independent_outcome_observation",
    "selected_capability_execution",
}


class RedLivingDexOptionDevelopmentError(ValueError):
    """The one-decision development boundary was crossed or mismatched."""


@dataclass(slots=True)
class PreparedRedLivingDexOption:
    """An exact full menu frozen before any model score is requested."""

    bound: BoundRedDualCapabilityScenario
    model_sha256: str
    context_identity_sha256: str
    candidate_rows: tuple[dict[str, int | str], ...]
    preparation_sha256: str
    _decision_sha256: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.bound, BoundRedDualCapabilityScenario):
            raise TypeError("prepared option needs a bound dual-capability scenario")
        _require_sha256(self.model_sha256, "model")
        _require_sha256(self.context_identity_sha256, "context")
        expected_rows = _candidate_rows(self.bound)
        if self.candidate_rows != expected_rows:
            raise RedLivingDexOptionDevelopmentError(
                "prepared option does not contain the complete frozen menu"
            )
        expected_identity = _preparation_identity(
            self.bound,
            model_sha256=self.model_sha256,
            context_identity_sha256=self.context_identity_sha256,
            candidate_rows=self.candidate_rows,
        )
        if self.preparation_sha256 != expected_identity:
            raise RedLivingDexOptionDevelopmentError("option preparation identity differs")

    def _bind_decision(self, decision_sha256: str) -> None:
        _require_sha256(decision_sha256, "decision")
        if self._decision_sha256 is not None:
            raise RedLivingDexOptionDevelopmentError(
                "prepared option was already consumed by a model decision"
            )
        self._decision_sha256 = decision_sha256

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": RED_LIVING_DEX_OPTION_PREPARATION_SCHEMA,
            "preparation_sha256": self.preparation_sha256,
            "context_identity_sha256": self.context_identity_sha256,
            "model_sha256": self.model_sha256,
            "scenario_sha256": canonical_sha256(self.bound.scenario.public_dict()),
            "dependency_binding_sha256": self.bound.species_binding.binding_sha256,
            "before_ledger_sha256": self.bound.before_ledger.ledger_sha256,
            "candidate_rows": [dict(row) for row in self.candidate_rows],
            "candidate_count": 2,
            "model_predictions": 0,
            "teacher_queries": 0,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_LIVING_DEX_OPTION_PREPARATION_SCHEMA,
            "candidate_count": 2,
            "candidate_rows": [dict(row) for row in self.candidate_rows],
            "complete_menu_frozen_before_prediction": True,
            "independently_available_capabilities": 2,
            "same_reset_state": True,
            "model_predictions": 0,
            "teacher_queries": 0,
            "identity_fields_public": 0,
        }


@dataclass(slots=True)
class RedLivingDexOptionDecision:
    """One model preference over the already-frozen full menu."""

    preparation: PreparedRedLivingDexOption
    selected_candidate_index: int
    candidate_scores: tuple[float, float]
    selected_candidate_probability: float
    decision_sha256: str
    _executed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.preparation, PreparedRedLivingDexOption):
            raise TypeError("option decision needs a prepared menu")
        if type(self.selected_candidate_index) is not int or self.selected_candidate_index not in {
            0,
            1,
        }:  # noqa: E721
            raise RedLivingDexOptionDevelopmentError("selected candidate index differs")
        if (
            not isinstance(self.candidate_scores, tuple)
            or len(self.candidate_scores) != 2
            or any(
                type(value) is not float or not math.isfinite(value)  # noqa: E721
                for value in self.candidate_scores
            )
            or type(self.selected_candidate_probability) is not float  # noqa: E721
            or not math.isfinite(self.selected_candidate_probability)
        ):
            raise RedLivingDexOptionDevelopmentError("option decision scores differ")
        expected_index = 0 if self.candidate_scores[0] >= self.candidate_scores[1] else 1
        acquire_probability = _sigmoid(self.candidate_scores[0] - self.candidate_scores[1])
        expected_probability = (
            acquire_probability if expected_index == 0 else 1.0 - acquire_probability
        )
        if (
            self.selected_candidate_index != expected_index
            or not 0.5 <= self.selected_candidate_probability <= 1.0
            or not math.isclose(
                self.selected_candidate_probability,
                expected_probability,
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        ):
            raise RedLivingDexOptionDevelopmentError("option decision preference differs")
        expected_identity = _decision_identity(
            self.preparation,
            selected_candidate_index=self.selected_candidate_index,
            candidate_scores=self.candidate_scores,
            selected_candidate_probability=self.selected_candidate_probability,
        )
        if self.decision_sha256 != expected_identity:
            raise RedLivingDexOptionDevelopmentError("option decision identity differs")

    @property
    def selected_kind(self) -> GoalKind:
        return _CAPABILITY_ORDER[self.selected_candidate_index]

    def _consume_execution(self) -> None:
        if self._executed:
            raise RedLivingDexOptionDevelopmentError(
                "model-selected option was already executed"
            )
        if self.preparation._decision_sha256 != self.decision_sha256:
            raise RedLivingDexOptionDevelopmentError(
                "execution decision does not own the prepared menu"
            )
        self._executed = True

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": RED_LIVING_DEX_OPTION_DECISION_SCHEMA,
            "preparation_sha256": self.preparation.preparation_sha256,
            "decision_sha256": self.decision_sha256,
            "model_sha256": self.preparation.model_sha256,
            "selected_candidate_index": self.selected_candidate_index,
            "selected_goal_kind": self.selected_kind.value,
            "candidate_scores": list(self.candidate_scores),
            "selected_candidate_probability": self.selected_candidate_probability,
            "model_predictions": 1,
            "teacher_queries": 0,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_LIVING_DEX_OPTION_DECISION_SCHEMA,
            "candidate_count": 2,
            "selected_candidate_index": self.selected_candidate_index,
            "selected_goal_kind": self.selected_kind.value,
            "selected_candidate_probability": self.selected_candidate_probability,
            "score_margin": abs(self.candidate_scores[0] - self.candidate_scores[1]),
            "model_predictions": 1,
            "teacher_queries": 0,
            "identity_fields_public": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexOptionEpisode:
    """One settled or censored development terminal after the selected skill."""

    decision: RedLivingDexOptionDecision
    outcome: RedDualCapabilityOutcome
    status: Literal["settled", "interrupted"]
    interruption_stage: str | None
    episode_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RedLivingDexOptionDecision) or not isinstance(
            self.outcome, RedDualCapabilityOutcome
        ):
            raise TypeError("option episode needs one decision and verified outcome")
        if (
            not self.decision._executed
            or self.outcome.selected_kind is not self.decision.selected_kind
            or self.outcome.status != self.status
        ):
            raise RedLivingDexOptionDevelopmentError("option episode binding differs")
        if self.status == "settled":
            if self.interruption_stage is not None:
                raise RedLivingDexOptionDevelopmentError(
                    "settled option episode cannot declare an interruption"
                )
        elif self.status == "interrupted":
            if self.interruption_stage not in _INTERRUPTION_STAGES:
                raise RedLivingDexOptionDevelopmentError(
                    "interrupted option episode stage differs"
                )
        else:
            raise RedLivingDexOptionDevelopmentError("option episode status differs")
        expected_identity = _episode_identity(
            self.decision,
            self.outcome,
            interruption_stage=self.interruption_stage,
        )
        if self.episode_sha256 != expected_identity:
            raise RedLivingDexOptionDevelopmentError("option episode identity differs")

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": RED_LIVING_DEX_OPTION_EPISODE_SCHEMA,
            "episode_sha256": self.episode_sha256,
            "preparation_sha256": self.decision.preparation.preparation_sha256,
            "decision_sha256": self.decision.decision_sha256,
            "context_identity_sha256": self.decision.preparation.context_identity_sha256,
            "model_sha256": self.decision.preparation.model_sha256,
            "status": self.status,
            "interruption_stage": self.interruption_stage,
            "decision": self.decision.private_dict(),
            "outcome": self.outcome.private_dict(),
            "selected_capabilities_executed": 1,
            "model_predictions": 1,
            "teacher_queries": 0,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_LIVING_DEX_OPTION_EPISODE_SCHEMA,
            "status": self.status,
            "interruption_stage": self.interruption_stage,
            "decision": self.decision.public_dict(),
            "outcome": self.outcome.public_dict(),
            "complete_menu_frozen_before_prediction": True,
            "selected_capabilities_executed": 1,
            "independent_post_transition_observation": self.status == "settled",
            "model_predictions": 1,
            "teacher_queries": 0,
            "authority_promotions_added": 0,
            "transfer_results_added": 0,
            "private_identity_fields": 0,
        }


def prepare_red_living_dex_option(
    bound: BoundRedDualCapabilityScenario,
    *,
    model_sha256: str,
    context_identity_sha256: str,
    excluded_context_identity_sha256s: frozenset[str] = frozenset(),
    excluded_reset_state_sha256s: frozenset[str] = frozenset(),
) -> PreparedRedLivingDexOption:
    """Freeze both available candidates and reject every explicitly retired root."""

    if not isinstance(bound, BoundRedDualCapabilityScenario):
        raise TypeError("bound must be a BoundRedDualCapabilityScenario")
    _require_sha256(model_sha256, "model")
    _require_sha256(context_identity_sha256, "context")
    _require_sha256_set(excluded_context_identity_sha256s, "excluded context")
    _require_sha256_set(excluded_reset_state_sha256s, "excluded reset state")
    reset_states = frozenset(
        capability.evidence.reset_state_sha256 for capability in bound.capabilities
    )
    if context_identity_sha256 in excluded_context_identity_sha256s or not reset_states.isdisjoint(
        excluded_reset_state_sha256s
    ):
        raise RedLivingDexOptionDevelopmentError(
            "prepared option reuses an explicitly retired context or reset state"
        )
    if len(reset_states) != 1:
        raise RedLivingDexOptionDevelopmentError(
            "collection options do not share one authenticated reset state"
        )
    rows = _candidate_rows(bound)
    identity = _preparation_identity(
        bound,
        model_sha256=model_sha256,
        context_identity_sha256=context_identity_sha256,
        candidate_rows=rows,
    )
    return PreparedRedLivingDexOption(
        bound,
        model_sha256,
        context_identity_sha256,
        rows,
        identity,
    )


def score_red_living_dex_option(
    preparation: PreparedRedLivingDexOption,
    model: DependencyRankerModel,
) -> RedLivingDexOptionDecision:
    """Consume one frozen menu as exactly one full-menu model decision."""

    if not isinstance(preparation, PreparedRedLivingDexOption):
        raise TypeError("preparation must be a PreparedRedLivingDexOption")
    if not isinstance(model, DependencyRankerModel):
        raise TypeError("model must be a DependencyRankerModel")
    if model.model_sha256 != preparation.model_sha256:
        raise RedLivingDexOptionDevelopmentError("dependency model identity differs")
    if preparation._decision_sha256 is not None:
        raise RedLivingDexOptionDevelopmentError(
            "prepared option was already consumed by a model decision"
        )
    candidates = _candidate_features(preparation.bound)
    scores = tuple(float(model.score(candidate)) for candidate in candidates)
    if len(scores) != 2 or any(not math.isfinite(value) for value in scores):
        raise RedLivingDexOptionDevelopmentError("dependency model score is not finite")
    typed_scores = (scores[0], scores[1])
    selected_index = 0 if typed_scores[0] >= typed_scores[1] else 1
    acquire_probability = _sigmoid(typed_scores[0] - typed_scores[1])
    selected_probability = (
        acquire_probability if selected_index == 0 else 1.0 - acquire_probability
    )
    decision_sha256 = _decision_identity(
        preparation,
        selected_candidate_index=selected_index,
        candidate_scores=typed_scores,
        selected_candidate_probability=float(selected_probability),
    )
    decision = RedLivingDexOptionDecision(
        preparation,
        selected_index,
        typed_scores,
        float(selected_probability),
        decision_sha256,
    )
    preparation._bind_decision(decision.decision_sha256)
    return decision


def execute_red_living_dex_option(
    decision: RedLivingDexOptionDecision,
    *,
    observe_after_ledger: Callable[[], DependencySpecimenLedger],
) -> RedLivingDexOptionEpisode:
    """Execute only the selected skill and verify a fresh independent ledger.

    Ordinary execution or observation exceptions become a censored development
    terminal.  ``BaseException`` subclasses such as process interruption remain
    visible to the outer durable runner and are never silently converted.
    """

    if not isinstance(decision, RedLivingDexOptionDecision):
        raise TypeError("decision must be a RedLivingDexOptionDecision")
    if not callable(observe_after_ledger):
        raise TypeError("observe_after_ledger must be callable")
    decision._consume_execution()
    bound = decision.preparation.bound
    selected = bound.bind_selection(decision.selected_candidate_index)
    try:
        selected.execute()
    except Exception:
        return _interrupted_episode(decision, "selected_capability_execution")
    try:
        after_ledger = observe_after_ledger()
        if not isinstance(after_ledger, DependencySpecimenLedger):
            raise TypeError("independent observer did not return a specimen ledger")
        outcome = bound.verify_outcome(
            selected_kind=decision.selected_kind,
            after_ledger=after_ledger,
        )
    except Exception:
        return _interrupted_episode(decision, "independent_outcome_observation")
    identity = _episode_identity(decision, outcome, interruption_stage=None)
    return RedLivingDexOptionEpisode(decision, outcome, "settled", None, identity)


def _interrupted_episode(
    decision: RedLivingDexOptionDecision,
    stage: Literal[
        "independent_outcome_observation",
        "selected_capability_execution",
    ],
) -> RedLivingDexOptionEpisode:
    outcome = decision.preparation.bound.verify_outcome(
        selected_kind=decision.selected_kind,
        after_ledger=None,
    )
    identity = _episode_identity(decision, outcome, interruption_stage=stage)
    return RedLivingDexOptionEpisode(decision, outcome, "interrupted", stage, identity)


def _candidate_features(
    bound: BoundRedDualCapabilityScenario,
) -> tuple[DependencyCandidateFeatures, DependencyCandidateFeatures]:
    state = bound.scenario.predecision_features
    candidates = (
        DependencyCandidateFeatures(state, 1, 0, 0),
        DependencyCandidateFeatures(state, 0, 1, 1),
    )
    if tuple(candidate.policy_dict() for candidate in candidates) != bound.policy_rows():
        raise RedLivingDexOptionDevelopmentError(
            "typed model candidates differ from the bound full menu"
        )
    return candidates


def _candidate_rows(
    bound: BoundRedDualCapabilityScenario,
) -> tuple[dict[str, int | str], ...]:
    return tuple(dict(candidate.policy_dict()) for candidate in _candidate_features(bound))


def _preparation_identity(
    bound: BoundRedDualCapabilityScenario,
    *,
    model_sha256: str,
    context_identity_sha256: str,
    candidate_rows: tuple[dict[str, int | str], ...],
) -> str:
    return canonical_sha256(
        {
            "schema": RED_LIVING_DEX_OPTION_PREPARATION_SCHEMA,
            "model_sha256": model_sha256,
            "context_identity_sha256": context_identity_sha256,
            "prospective_scenario": bound.prospective.private_dict(),
            "scenario_sha256": canonical_sha256(bound.scenario.public_dict()),
            "dependency_binding_sha256": bound.species_binding.binding_sha256,
            "before_ledger_sha256": bound.before_ledger.ledger_sha256,
            "candidate_rows": [dict(row) for row in candidate_rows],
        }
    )


def _decision_identity(
    preparation: PreparedRedLivingDexOption,
    *,
    selected_candidate_index: int,
    candidate_scores: tuple[float, float],
    selected_candidate_probability: float,
) -> str:
    return canonical_sha256(
        {
            "schema": RED_LIVING_DEX_OPTION_DECISION_SCHEMA,
            "preparation_sha256": preparation.preparation_sha256,
            "model_sha256": preparation.model_sha256,
            "selected_candidate_index": selected_candidate_index,
            "selected_goal_kind": _CAPABILITY_ORDER[selected_candidate_index].value,
            "candidate_scores": list(candidate_scores),
            "selected_candidate_probability": selected_candidate_probability,
        }
    )


def _episode_identity(
    decision: RedLivingDexOptionDecision,
    outcome: RedDualCapabilityOutcome,
    *,
    interruption_stage: str | None,
) -> str:
    return canonical_sha256(
        {
            "schema": RED_LIVING_DEX_OPTION_EPISODE_SCHEMA,
            "preparation_sha256": decision.preparation.preparation_sha256,
            "decision_sha256": decision.decision_sha256,
            "outcome": outcome.private_dict(),
            "interruption_stage": interruption_stage,
        }
    )


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexOptionDevelopmentError(f"{subject} identity differs")
    return value


def _require_sha256_set(values: object, subject: str) -> None:
    if not isinstance(values, frozenset) or any(
        not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in values
    ):
        raise RedLivingDexOptionDevelopmentError(f"{subject} roster differs")


__all__ = [
    "RED_LIVING_DEX_OPTION_DECISION_SCHEMA",
    "RED_LIVING_DEX_OPTION_EPISODE_SCHEMA",
    "RED_LIVING_DEX_OPTION_PREPARATION_SCHEMA",
    "PreparedRedLivingDexOption",
    "RedLivingDexOptionDecision",
    "RedLivingDexOptionDevelopmentError",
    "RedLivingDexOptionEpisode",
    "execute_red_living_dex_option",
    "prepare_red_living_dex_option",
    "score_red_living_dex_option",
]
