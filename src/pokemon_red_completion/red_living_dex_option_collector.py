"""Repeatable selected-arm collection for Red living-Pokédex decisions.

The collector freezes a complete menu, creates a deterministic but non-uniform
full-support behavior distribution, samples exactly one available row, executes
only its private binding, and asks an independent observer to settle the result.
No executor return value and no unselected option can become a learning target.
"""

from __future__ import annotations

import math
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionMenu,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedLivingDexAdaptedScenario,
    RedLivingDexOutcomeSnapshot,
)

RED_LIVING_DEX_BEHAVIOR_POLICY_SCHEMA = (
    "pokemon.red.living-dex-full-support-behavior-policy.v1"
)
RED_LIVING_DEX_BEHAVIOR_COMMITMENT_SCHEMA = (
    "pokemon.red.living-dex-single-draw-behavior-commitment.v1"
)
RED_LIVING_DEX_OBSERVED_ARM_COLLECTION_SCHEMA = (
    "pokemon.red.living-dex-observed-arm-collection.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexOptionCollectorError(ValueError):
    """A selected-arm collection attempt cannot be represented honestly."""


class RedLivingDexExternalInterruption(Exception):
    """Explicit scenario interruption that must remain a target-free attempt."""


class RedLivingDexBehaviorIssuance(StrEnum):
    """Whether a commitment came from the one-draw runtime issuer or a fixture."""

    SYNTHETIC_TEST = "synthetic-test"
    SYSTEM_CSPRNG = "system-csprng-single-draw-v1"


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexOptionCollectorError(f"{subject} SHA-256 is invalid")
    return value


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0 if numerator <= 0 else 1.0
    return min(1.0, max(0.0, float(numerator) / float(denominator)))


@dataclass(frozen=True, slots=True)
class RedLivingDexBehaviorCommitment:
    """One CSPRNG draw bound to a frozen scenario, partition, and policy menu.

    Authentic materializers must issue this record once, persist it before any
    controller input, and never reroll it to obtain a preferred arm.  The raw
    256-bit value is intentionally recorded so the complete behavior draw is
    replayable rather than merely asserted.
    """

    scenario_identity_sha256: str
    partition: str
    menu_sha256: str
    randomization_seed_sha256: str
    issuance_origin: RedLivingDexBehaviorIssuance = field(
        default=RedLivingDexBehaviorIssuance.SYNTHETIC_TEST,
        init=False,
    )

    def __post_init__(self) -> None:
        _require_sha256(self.scenario_identity_sha256, subject="behavior scenario")
        _require_sha256(self.menu_sha256, subject="behavior menu")
        _require_sha256(
            self.randomization_seed_sha256,
            subject="behavior randomization seed",
        )
        if self.partition not in {"train", "development"}:
            raise RedLivingDexOptionCollectorError(
                "behavior commitment partition differs"
            )
        if not isinstance(self.issuance_origin, RedLivingDexBehaviorIssuance):
            raise RedLivingDexOptionCollectorError(
                "behavior commitment issuance differs"
            )

    @property
    def authenticated_issuance(self) -> bool:
        return self.issuance_origin is RedLivingDexBehaviorIssuance.SYSTEM_CSPRNG

    @property
    def probability_seed_sha256(self) -> str:
        return canonical_sha256(
            {
                "commitment_sha256": self.commitment_sha256,
                "purpose": "available-row-rank-weights",
                "schema": RED_LIVING_DEX_BEHAVIOR_COMMITMENT_SCHEMA,
            }
        )

    @property
    def draw_seed_sha256(self) -> str:
        return canonical_sha256(
            {
                "commitment_sha256": self.commitment_sha256,
                "purpose": "single-weighted-ticket",
                "schema": RED_LIVING_DEX_BEHAVIOR_COMMITMENT_SCHEMA,
            }
        )

    @property
    def commitment_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "issuance_method": self.issuance_origin.value,
            "menu_sha256": self.menu_sha256,
            "partition": self.partition,
            "randomization_seed_sha256": self.randomization_seed_sha256,
            "scenario_bound_privately": True,
            "schema": RED_LIVING_DEX_BEHAVIOR_COMMITMENT_SCHEMA,
        }

    def private_dict(self) -> dict[str, object]:
        return {
            **self.public_dict(),
            "scenario_identity_sha256": self.scenario_identity_sha256,
        }


def issue_red_living_dex_behavior_commitment(
    adapted: RedLivingDexAdaptedScenario,
    *,
    partition: str,
) -> RedLivingDexBehaviorCommitment:
    """Issue one system-random behavior draw after the complete menu is frozen.

    This function intentionally exposes no caller-supplied entropy or desired
    candidate.  A durable materializer remains responsible for persisting the
    returned commitment once before controller authority and prohibiting reissue.
    """

    if not isinstance(adapted, RedLivingDexAdaptedScenario):
        raise TypeError("adapted must be a RedLivingDexAdaptedScenario")
    commitment = RedLivingDexBehaviorCommitment(
        adapted.before.scenario_identity_sha256,
        partition,
        adapted.menu.policy_sha256,
        secrets.token_hex(32),
    )
    object.__setattr__(
        commitment,
        "issuance_origin",
        RedLivingDexBehaviorIssuance.SYSTEM_CSPRNG,
    )
    return commitment


@dataclass(frozen=True, slots=True)
class RedLivingDexBehaviorDecision:
    """Replayable behavior probabilities and one sampled available row."""

    commitment: RedLivingDexBehaviorCommitment
    available_indices: tuple[int, ...]
    integer_weights: tuple[int, ...]
    probabilities: tuple[float, ...]
    selected_candidate_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.commitment, RedLivingDexBehaviorCommitment):
            raise TypeError("behavior decision needs a randomization commitment")
        if (
            not isinstance(self.available_indices, tuple)
            or len(self.available_indices) < 2
            or tuple(sorted(set(self.available_indices))) != self.available_indices
            or any(
                type(value) is not int or value < 0  # noqa: E721
                for value in self.available_indices
            )
            or not isinstance(self.integer_weights, tuple)
            or not self.integer_weights
            or any(type(value) is not int or value < 0 for value in self.integer_weights)  # noqa: E721
            or not isinstance(self.probabilities, tuple)
            or len(self.probabilities) != len(self.integer_weights)
            or any(
                type(value) is not float or not math.isfinite(value) or value < 0.0  # noqa: E721
                for value in self.probabilities
            )
            or type(self.selected_candidate_index) is not int  # noqa: E721
            or not 0 <= self.selected_candidate_index < len(self.integer_weights)
        ):
            raise RedLivingDexOptionCollectorError("behavior decision fields differ")
        if self.available_indices[-1] >= len(self.integer_weights):
            raise RedLivingDexOptionCollectorError("behavior availability index is invalid")
        total = sum(self.integer_weights)
        if total <= 0 or not math.isclose(
            sum(self.probabilities),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise RedLivingDexOptionCollectorError("behavior distribution differs")
        ranked = sorted(
            self.available_indices,
            key=lambda index: _behavior_rank_key(
                index,
                probability_seed_sha256=self.commitment.probability_seed_sha256,
            ),
        )
        expected_by_index = {
            index: rank + 1 for rank, index in enumerate(ranked)
        }
        expected_weights = tuple(
            expected_by_index.get(index, 0)
            for index in range(len(self.integer_weights))
        )
        if self.integer_weights != expected_weights:
            raise RedLivingDexOptionCollectorError(
                "behavior weights do not replay from the declared seed"
            )
        expected = tuple(weight / total for weight in expected_weights)
        if self.probabilities != expected:
            raise RedLivingDexOptionCollectorError(
                "behavior probabilities differ from their replay weights"
            )
        if self.integer_weights[self.selected_candidate_index] <= 0:
            raise RedLivingDexOptionCollectorError("behavior selected a masked row")
        draw_digest = canonical_sha256(
            {
                "draw_seed_sha256": self.commitment.draw_seed_sha256,
                "integer_weights": list(self.integer_weights),
                "menu_sha256": self.commitment.menu_sha256,
                "schema": RED_LIVING_DEX_BEHAVIOR_POLICY_SCHEMA,
            }
        )
        ticket = int(draw_digest, 16) % total
        cumulative = 0
        expected_selected: int | None = None
        for index, weight in enumerate(self.integer_weights):
            cumulative += weight
            if weight > 0 and ticket < cumulative:
                expected_selected = index
                break
        if self.selected_candidate_index != expected_selected:
            raise RedLivingDexOptionCollectorError(
                "behavior selection does not replay from the declared draw seed"
            )

    @property
    def selected_probability(self) -> float:
        return self.probabilities[self.selected_candidate_index]

    @property
    def behavior_configuration_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "available_indices": list(self.available_indices),
            "commitment": self.commitment.public_dict(),
            "commitment_sha256": self.commitment.commitment_sha256,
            "full_support_over_available_options": True,
            "integer_weights": list(self.integer_weights),
            "nonuniform": len({value for value in self.integer_weights if value > 0}) > 1,
            "probabilities": list(self.probabilities),
            "menu_sha256": self.commitment.menu_sha256,
            "probability_seed_sha256": self.commitment.probability_seed_sha256,
            "draw_seed_sha256": self.commitment.draw_seed_sha256,
            "schema": RED_LIVING_DEX_BEHAVIOR_POLICY_SCHEMA,
            "selected_candidate_index": self.selected_candidate_index,
            "selected_probability": self.selected_probability,
            "selection_method": "sha256-ticket-over-integer-weights-v1",
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexCollectedExample:
    """One public selected-arm example plus private-free collection diagnostics."""

    adapted: RedLivingDexAdaptedScenario
    behavior: RedLivingDexBehaviorDecision
    example: LivingDexObservedArmExample
    selected_execution_raised: bool
    independent_observer_calls: int
    after_observer_provenance_sha256: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.adapted, RedLivingDexAdaptedScenario):
            raise TypeError("collected example needs an adapted scenario")
        if not isinstance(self.behavior, RedLivingDexBehaviorDecision):
            raise TypeError("collected example needs a behavior decision")
        if not isinstance(self.example, LivingDexObservedArmExample):
            raise TypeError("collected example needs an observed-arm example")
        if (
            self.example.menu != self.adapted.menu
            or self.behavior.commitment.menu_sha256
            != self.adapted.menu.policy_sha256
            or self.behavior.commitment.scenario_identity_sha256
            != self.adapted.before.scenario_identity_sha256
            or self.behavior.commitment.partition != self.example.partition
            or self.example.selected_candidate_index
            != self.behavior.selected_candidate_index
            or self.example.behavior_probabilities != self.behavior.probabilities
            or type(self.selected_execution_raised) is not bool  # noqa: E721
            or type(self.independent_observer_calls) is not int  # noqa: E721
            or self.independent_observer_calls not in {0, 1}
        ):
            raise RedLivingDexOptionCollectorError("collected example binding differs")
        expected_decision_sha256 = _decision_sha256(
            self.adapted,
            self.behavior,
            partition=self.example.partition,
        )
        if self.example.decision_sha256 != expected_decision_sha256:
            raise RedLivingDexOptionCollectorError(
                "collected example decision identity differs"
            )
        if self.after_observer_provenance_sha256 is not None:
            _require_sha256(
                self.after_observer_provenance_sha256,
                subject="after-observer provenance",
            )
        expected_observer_calls = (
            0
            if self.example.outcome.censor_reason
            is LivingDexCensorReason.EXTERNAL_INTERRUPTION
            else 1
        )
        if self.independent_observer_calls != expected_observer_calls:
            raise RedLivingDexOptionCollectorError(
                "collected example observer accounting differs"
            )
        outcome = self.example.outcome
        if (
            outcome.status is LivingDexOutcomeStatus.SETTLED
            and self.after_observer_provenance_sha256 is None
        ) or (
            outcome.censor_reason
            in {
                LivingDexCensorReason.EXTERNAL_INTERRUPTION,
                LivingDexCensorReason.OBSERVATION_FAILED,
            }
            and self.after_observer_provenance_sha256 is not None
        ):
            raise RedLivingDexOptionCollectorError(
                "collected example observer provenance differs"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "adapter": self.adapted.public_dict(),
            "after_observation_recorded": (
                self.after_observer_provenance_sha256 is not None
            ),
            "behavior": self.behavior.public_dict(),
            "example": self.example.public_dict(),
            "identity_fields_public": 0,
            "independent_observer_calls": self.independent_observer_calls,
            "model_predictions": 0,
            "schema": RED_LIVING_DEX_OBSERVED_ARM_COLLECTION_SCHEMA,
            "selected_capabilities_executed": 1,
            "selected_execution_raised": self.selected_execution_raised,
            "teacher_queries": 0,
            "unselected_capabilities_executed": 0,
            "unselected_action_targets": 0,
        }

    def private_dict(self) -> dict[str, object]:
        selected = self.adapted.ordered_options[
            self.behavior.selected_candidate_index
        ]
        return {
            **self.public_dict(),
            "after_observer_provenance_sha256": (
                self.after_observer_provenance_sha256
            ),
            "before_observer_provenance_sha256": (
                self.adapted.before.observer_provenance_sha256
            ),
            "scenario_identity_sha256": self.adapted.before.scenario_identity_sha256,
            "selected_binding_sha256": selected.binding_sha256,
            "selected_family_sha256": canonical_sha256(
                {
                    "family_ref": selected.family_ref,
                    "schema": "pokemon.red.private-transformation-family-join.v1",
                }
            ),
            "selected_location_sha256": canonical_sha256(
                {
                    "location_ref": selected.location_ref,
                    "schema": "pokemon.red.private-option-location-join.v1",
                }
            ),
        }


def red_living_dex_behavior_decision(
    menu: LivingDexOptionMenu,
    *,
    commitment: RedLivingDexBehaviorCommitment,
) -> RedLivingDexBehaviorDecision:
    """Assign replayable rank weights and draw once without using private identity."""

    if not isinstance(menu, LivingDexOptionMenu):
        raise TypeError("menu must be a LivingDexOptionMenu")
    if not isinstance(commitment, RedLivingDexBehaviorCommitment):
        raise TypeError("commitment must be a RedLivingDexBehaviorCommitment")
    if commitment.menu_sha256 != menu.policy_sha256:
        raise RedLivingDexOptionCollectorError(
            "behavior commitment and policy menu differ"
        )
    available = menu.available_indices

    ranked = sorted(
        available,
        key=lambda index: _behavior_rank_key(
            index,
            probability_seed_sha256=commitment.probability_seed_sha256,
        ),
    )
    weight_by_index = {index: rank + 1 for rank, index in enumerate(ranked)}
    weights = tuple(weight_by_index.get(index, 0) for index in range(len(menu.candidates)))
    total = sum(weights)
    probabilities = tuple(weight / total for weight in weights)
    draw_digest = canonical_sha256(
        {
            "draw_seed_sha256": commitment.draw_seed_sha256,
            "integer_weights": list(weights),
            "menu_sha256": menu.policy_sha256,
            "schema": RED_LIVING_DEX_BEHAVIOR_POLICY_SCHEMA,
        }
    )
    ticket = int(draw_digest, 16) % total
    cumulative = 0
    selected: int | None = None
    for index, weight in enumerate(weights):
        cumulative += weight
        if weight > 0 and ticket < cumulative:
            selected = index
            break
    if selected is None:
        raise RedLivingDexOptionCollectorError("behavior draw did not select an option")
    return RedLivingDexBehaviorDecision(
        commitment,
        available,
        weights,
        probabilities,
        selected,
    )


def _behavior_rank_key(index: int, *, probability_seed_sha256: str) -> str:
    return canonical_sha256(
        {
            "candidate_index": index,
            "probability_seed_sha256": probability_seed_sha256,
            "schema": RED_LIVING_DEX_BEHAVIOR_POLICY_SCHEMA,
        }
    )


def collect_red_living_dex_observed_arm(
    adapted: RedLivingDexAdaptedScenario,
    *,
    commitment: RedLivingDexBehaviorCommitment,
    observe_after: Callable[[], RedLivingDexOutcomeSnapshot],
) -> RedLivingDexCollectedExample:
    """Sample and execute one Red option, then settle from one fresh observation.

    Ordinary executor exceptions are diagnostic only because an action may have
    changed state before raising.  The independent observer still runs once.
    Explicit external interruptions are censored immediately.  Process-level
    ``BaseException`` subclasses remain visible to the durable outer runner.
    """

    if not isinstance(adapted, RedLivingDexAdaptedScenario):
        raise TypeError("adapted must be a RedLivingDexAdaptedScenario")
    if not callable(observe_after):
        raise TypeError("observe_after must be callable")
    if not isinstance(commitment, RedLivingDexBehaviorCommitment):
        raise TypeError("commitment must be a RedLivingDexBehaviorCommitment")
    if (
        commitment.scenario_identity_sha256
        != adapted.before.scenario_identity_sha256
    ):
        raise RedLivingDexOptionCollectorError(
            "behavior commitment and scenario identity differ"
        )
    behavior = red_living_dex_behavior_decision(
        adapted.menu,
        commitment=commitment,
    )
    selected = adapted.ordered_options[behavior.selected_candidate_index]
    if selected.consumed:
        raise RedLivingDexOptionCollectorError(
            "behavior selected an already-consumed Red option binding"
        )
    selected_execution_raised = False
    observer_calls = 0
    after_observer_provenance_sha256: str | None = None
    try:
        selected.execute_once()
    except RedLivingDexExternalInterruption:
        outcome = LivingDexObservedOutcome(
            LivingDexOutcomeStatus.CENSORED,
            censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
        )
    except Exception:
        selected_execution_raised = True
        outcome, observer_calls, after_observer_provenance_sha256 = _observe_and_settle(
            adapted,
            selected_index=behavior.selected_candidate_index,
            observe_after=observe_after,
        )
    else:
        outcome, observer_calls, after_observer_provenance_sha256 = _observe_and_settle(
            adapted,
            selected_index=behavior.selected_candidate_index,
            observe_after=observe_after,
        )
    decision_sha256 = _decision_sha256(
        adapted,
        behavior,
        partition=commitment.partition,
    )
    example = LivingDexObservedArmExample(
        decision_sha256,
        commitment.partition,
        adapted.menu,
        behavior.selected_candidate_index,
        behavior.probabilities,
        outcome,
    )
    return RedLivingDexCollectedExample(
        adapted,
        behavior,
        example,
        selected_execution_raised,
        observer_calls,
        after_observer_provenance_sha256,
    )


def _observe_and_settle(
    adapted: RedLivingDexAdaptedScenario,
    *,
    selected_index: int,
    observe_after: Callable[[], RedLivingDexOutcomeSnapshot],
) -> tuple[LivingDexObservedOutcome, int, str | None]:
    try:
        after = observe_after()
    except Exception:
        return (
            LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
            ),
            1,
            None,
        )
    if not isinstance(after, RedLivingDexOutcomeSnapshot):
        return (
            LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
            ),
            1,
            None,
        )
    try:
        return (
            _settled_outcome(adapted, selected_index=selected_index, after=after),
            1,
            after.observer_provenance_sha256,
        )
    except Exception:
        return (
            LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.PROVENANCE_FAILED,
            ),
            1,
            after.observer_provenance_sha256,
        )


def _settled_outcome(
    adapted: RedLivingDexAdaptedScenario,
    *,
    selected_index: int,
    after: RedLivingDexOutcomeSnapshot,
) -> LivingDexObservedOutcome:
    before = adapted.before
    if (
        after.scenario_identity_sha256 != before.scenario_identity_sha256
        or after.scenario_repeatable != before.scenario_repeatable
        or after.controller_actions < before.controller_actions
        or after.emulator_frames < before.emulator_frames
        or after.party_health_capacity != before.party_health_capacity
    ):
        raise RedLivingDexOptionCollectorError("post-action provenance join differs")
    selected = adapted.ordered_options[selected_index]
    option_verified_success = selected.verify_success(before.ledger, after.ledger)
    if type(option_verified_success) is not bool:  # noqa: E721
        raise RedLivingDexOptionCollectorError("selected option verifier did not return bool")
    prospect = selected.prospect
    before_resource_units = before.resource_units_for(selected.resource_pool_ref)
    after_resource_units = after.resource_units_for(selected.resource_pool_ref)
    completion_delta = max(
        0,
        after.retained_living_species_count - before.retained_living_species_count,
    )
    dependency_delta = max(
        0,
        after.executable_dependency_count - before.executable_dependency_count,
    )
    lost_living_species = before.retained_living_species - after.retained_living_species
    verified_success = option_verified_success and not lost_living_species
    declared_irreversible_loss = _ratio(
        max(
            0,
            before.irreversible_constraints_remaining
            - after.irreversible_constraints_remaining,
        ),
        before.irreversible_constraints_remaining,
    )
    living_collection_loss = _ratio(
        len(lost_living_species),
        adapted.provenance.living_target_count,
    )
    return LivingDexObservedOutcome(
        status=LivingDexOutcomeStatus.SETTLED,
        verified_success=verified_success,
        completion_gain=_ratio(completion_delta, prospect.maximum_completion_units),
        dependency_unlock_gain=_ratio(
            dependency_delta,
            adapted.provenance.incomplete_dependency_frontier,
        ),
        action_cost=_ratio(
            after.controller_actions - before.controller_actions,
            adapted.provenance.maximum_controller_actions,
        ),
        frame_cost=_ratio(
            after.emulator_frames - before.emulator_frames,
            adapted.provenance.maximum_emulator_frames,
        ),
        resource_cost=_ratio(
            max(0, before_resource_units - after_resource_units),
            before_resource_units,
        ),
        party_cost=_ratio(
            max(0, before.party_health_units - after.party_health_units),
            before.party_health_capacity,
        ),
        storage_cost=_ratio(
            max(0, before.usable_storage_headroom - after.usable_storage_headroom),
            before.usable_storage_headroom,
        ),
        irreversible_loss=max(declared_irreversible_loss, living_collection_loss),
    )


def _decision_sha256(
    adapted: RedLivingDexAdaptedScenario,
    behavior: RedLivingDexBehaviorDecision,
    *,
    partition: str,
) -> str:
    selected = adapted.ordered_options[behavior.selected_candidate_index]
    return canonical_sha256(
        {
            "behavior": behavior.public_dict(),
            "menu_sha256": adapted.menu.policy_sha256,
            "normalization_provenance_sha256": (
                adapted.normalization_provenance_sha256
            ),
            "partition": partition,
            "scenario_identity_sha256": adapted.before.scenario_identity_sha256,
            "schema": RED_LIVING_DEX_OBSERVED_ARM_COLLECTION_SCHEMA,
            "selected_binding_sha256": selected.binding_sha256,
            "selected_family_sha256": canonical_sha256(
                {
                    "family_ref": selected.family_ref,
                    "schema": "pokemon.red.private-transformation-family-join.v1",
                }
            ),
            "selected_location_sha256": canonical_sha256(
                {
                    "location_ref": selected.location_ref,
                    "schema": "pokemon.red.private-option-location-join.v1",
                }
            ),
        }
    )


__all__ = [
    "RED_LIVING_DEX_BEHAVIOR_COMMITMENT_SCHEMA",
    "RED_LIVING_DEX_BEHAVIOR_POLICY_SCHEMA",
    "RED_LIVING_DEX_OBSERVED_ARM_COLLECTION_SCHEMA",
    "RedLivingDexBehaviorDecision",
    "RedLivingDexBehaviorIssuance",
    "RedLivingDexBehaviorCommitment",
    "RedLivingDexCollectedExample",
    "RedLivingDexExternalInterruption",
    "RedLivingDexOptionCollectorError",
    "collect_red_living_dex_observed_arm",
    "issue_red_living_dex_behavior_commitment",
    "red_living_dex_behavior_decision",
]
