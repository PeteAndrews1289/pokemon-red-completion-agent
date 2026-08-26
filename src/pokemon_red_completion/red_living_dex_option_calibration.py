"""Coverage and censoring audit for the first Red observed-arm calibration batch.

This module does not execute gameplay or fit a model.  It aggregates path-free
selected-arm examples, verifies context uniqueness and the preregistered
family/location split, reports behavior-policy and censoring diagnostics, and
opens train-only fitting only when the active lane's minimum integration batch
is genuinely present.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from pokemon_red_completion.living_dex_option_value import (
    DEFAULT_MAX_IMPORTANCE_WEIGHT,
    LivingDexObservedArmExample,
    LivingDexOptionAvailability,
    LivingDexOptionKind,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedBoundLivingDexOption,
)
from pokemon_red_completion.red_living_dex_option_collector import (
    RedLivingDexCollectedExample,
    RedLivingDexCollectionOrigin,
)

RED_LIVING_DEX_CALIBRATION_BATCH_SCHEMA = (
    "pokemon.red.living-dex-observed-arm-calibration-batch.v1"
)

MINIMUM_SETTLED_TRAIN_EXAMPLES = 8
MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES = 4
MINIMUM_TRAIN_OPTION_KINDS = 4
MINIMUM_TRAIN_FAMILIES = 3
MINIMUM_DEVELOPMENT_FAMILIES = 4
MINIMUM_DEVELOPMENT_LOCATIONS = 4


class RedLivingDexCalibrationError(ValueError):
    """Collected Red examples cannot support the declared calibration decision."""


@dataclass(frozen=True, slots=True)
class RedLivingDexCalibrationBatch:
    """A partial or fit-ready set of repeatable Red selected-arm examples."""

    examples: tuple[RedLivingDexCollectedExample, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.examples, tuple)
            or not self.examples
            or any(
                not isinstance(example, RedLivingDexCollectedExample)
                for example in self.examples
            )
        ):
            raise RedLivingDexCalibrationError(
                "calibration batch needs collected Red examples"
            )
        partitions = tuple(example.example.partition for example in self.examples)
        if any(partition not in {"train", "development"} for partition in partitions):
            raise RedLivingDexCalibrationError(
                "calibration batch accepts only train and development examples"
            )
        decisions = tuple(example.example.decision_sha256 for example in self.examples)
        scenarios = tuple(
            example.adapted.before.scenario_identity_sha256
            for example in self.examples
        )
        if len(decisions) != len(set(decisions)):
            raise RedLivingDexCalibrationError(
                "calibration batch repeats a decision identity"
            )
        if len(scenarios) != len(set(scenarios)):
            raise RedLivingDexCalibrationError(
                "calibration batch repeats a scenario identity"
            )
        if any(
            not example.adapted.before.scenario_repeatable
            for example in self.examples
        ):
            raise RedLivingDexCalibrationError(
                "calibration batch contains a non-repeatable scenario"
            )

    @property
    def settled_train(self) -> tuple[RedLivingDexCollectedExample, ...]:
        return self._settled("train")

    @property
    def settled_development(self) -> tuple[RedLivingDexCollectedExample, ...]:
        return self._settled("development")

    @property
    def fit_ready(self) -> bool:
        train_families = self._family_hashes(self.settled_train)
        development_families = self._family_hashes(self.settled_development)
        train_locations = self._location_hashes(self.settled_train)
        development_locations = self._location_hashes(self.settled_development)
        return (
            len(self.settled_train) >= MINIMUM_SETTLED_TRAIN_EXAMPLES
            and len(self.settled_development)
            >= MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES
            and len(self._selected_kinds(self.settled_train))
            >= MINIMUM_TRAIN_OPTION_KINDS
            and len(train_families) >= MINIMUM_TRAIN_FAMILIES
            and len(development_families) >= MINIMUM_DEVELOPMENT_FAMILIES
            and len(development_locations) >= MINIMUM_DEVELOPMENT_LOCATIONS
            and not train_families & development_families
            and not train_locations & development_locations
            and all(
                _selected_option(example).authenticated_executor
                for example in (*self.settled_train, *self.settled_development)
            )
            and all(
                example.behavior.commitment.authenticated_issuance
                for example in (*self.settled_train, *self.settled_development)
            )
            and all(
                example.collection_origin
                is RedLivingDexCollectionOrigin.DURABLE_VERIFIED_CAPTURE
                for example in (*self.settled_train, *self.settled_development)
            )
        )

    def train_fit_examples(self) -> tuple[LivingDexObservedArmExample, ...]:
        """Return all train attempts, including target-free censors, after the gate."""

        if not self.fit_ready:
            raise RedLivingDexCalibrationError(
                "calibration coverage is not ready for the one train-only fit"
            )
        return tuple(
            example.example
            for example in self.examples
            if example.example.partition == "train"
        )

    def development_evaluation_examples(
        self,
    ) -> tuple[LivingDexObservedArmExample, ...]:
        """Return the held-out attempts without admitting them to fitting."""

        if not self.fit_ready:
            raise RedLivingDexCalibrationError(
                "calibration coverage is not ready for development evaluation"
            )
        return tuple(
            example.example
            for example in self.examples
            if example.example.partition == "development"
        )

    def public_dict(self) -> dict[str, object]:
        partition_counts = Counter(example.example.partition for example in self.examples)
        settled_counts = Counter(
            example.example.partition
            for example in self.examples
            if example.example.outcome.status is LivingDexOutcomeStatus.SETTLED
        )
        censored_counts = Counter(
            example.example.partition
            for example in self.examples
            if example.example.outcome.status is LivingDexOutcomeStatus.CENSORED
        )
        train_families = self._family_hashes(self.settled_train)
        development_families = self._family_hashes(self.settled_development)
        train_locations = self._location_hashes(self.settled_train)
        development_locations = self._location_hashes(self.settled_development)
        selected_probabilities = tuple(
            example.behavior.selected_probability for example in self.examples
        )
        return {
            "behavior": {
                "importance_cap_exercised_examples": sum(
                    1.0 / probability > DEFAULT_MAX_IMPORTANCE_WEIGHT
                    for probability in selected_probabilities
                ),
                "maximum_selected_probability": max(selected_probabilities),
                "minimum_selected_probability": min(selected_probabilities),
                "nonuniform_full_support_examples": len(self.examples),
            },
            "authenticated_executor_counts": {
                partition: sum(
                    _selected_option(example).authenticated_executor
                    for example in self._settled(partition)
                )
                for partition in ("development", "train")
            },
            "authenticated_randomization_counts": {
                partition: sum(
                    example.behavior.commitment.authenticated_issuance
                    for example in self._settled(partition)
                )
                for partition in ("development", "train")
            },
            "durable_materialization_counts": {
                partition: sum(
                    example.collection_origin
                    is RedLivingDexCollectionOrigin.DURABLE_VERIFIED_CAPTURE
                    for example in self._settled(partition)
                )
                for partition in ("development", "train")
            },
            "calibration_fit_ready": self.fit_ready,
            "censored_counts": _partition_document(censored_counts),
            "censoring_diagnostic": self._censoring_diagnostic(),
            "context_sampling_propensity_correction": False,
            "development_family_count": len(development_families),
            "development_location_count": len(development_locations),
            "family_overlap": len(train_families & development_families),
            "identity_fields_public": 0,
            "location_overlap": len(train_locations & development_locations),
            "menu_sampling": {
                "available_width_counts": _counter_document(
                    Counter(
                        len(example.adapted.menu.available_indices)
                        for example in self.examples
                    )
                ),
                "distinct_policy_menus": len(
                    {example.adapted.menu.policy_sha256 for example in self.examples}
                ),
                "offered_option_kind_counts": _offered_kind_counts(self.examples),
                "total_width_counts": _counter_document(
                    Counter(
                        len(example.adapted.menu.candidates)
                        for example in self.examples
                    )
                ),
            },
            "minimum_coverage": {
                "development_families": MINIMUM_DEVELOPMENT_FAMILIES,
                "development_locations": MINIMUM_DEVELOPMENT_LOCATIONS,
                "settled_development_examples": (
                    MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES
                ),
                "settled_train_examples": MINIMUM_SETTLED_TRAIN_EXAMPLES,
                "train_families": MINIMUM_TRAIN_FAMILIES,
                "train_option_kinds": MINIMUM_TRAIN_OPTION_KINDS,
            },
            "partition_attempt_counts": _partition_document(partition_counts),
            "schema": RED_LIVING_DEX_CALIBRATION_BATCH_SCHEMA,
            "selected_kind_counts": _selected_kind_counts(self.examples),
            "settled_counts": _partition_document(settled_counts),
            "train_family_count": len(train_families),
            "train_location_count": len(train_locations),
            "train_selected_option_kind_count": len(
                self._selected_kinds(self.settled_train)
            ),
            "unselected_action_targets": 0,
            "synthetic_selected_executors_admitted_to_fit": False,
            "synthetic_randomization_admitted_to_fit": False,
            "rehearsal_or_unmaterialized_examples_admitted_to_fit": False,
        }

    def private_dict(self) -> dict[str, object]:
        return {
            **self.public_dict(),
            "examples": [example.private_dict() for example in self.examples],
        }

    def _settled(self, partition: str) -> tuple[RedLivingDexCollectedExample, ...]:
        return tuple(
            example
            for example in self.examples
            if example.example.partition == partition
            and example.example.outcome.status is LivingDexOutcomeStatus.SETTLED
        )

    @staticmethod
    def _selected_kinds(
        examples: Sequence[RedLivingDexCollectedExample],
    ) -> frozenset[LivingDexOptionKind]:
        return frozenset(_selected_kind(example) for example in examples)

    @staticmethod
    def _family_hashes(
        examples: Sequence[RedLivingDexCollectedExample],
    ) -> frozenset[str]:
        return frozenset(_selected_family_sha256(example) for example in examples)

    @staticmethod
    def _location_hashes(
        examples: Sequence[RedLivingDexCollectedExample],
    ) -> frozenset[str]:
        return frozenset(_selected_location_sha256(example) for example in examples)

    def _censoring_diagnostic(self) -> dict[str, object]:
        bands: dict[str, Counter[str]] = {
            "low": Counter(),
            "medium": Counter(),
            "high": Counter(),
        }
        for example in self.examples:
            candidate = example.adapted.menu.candidates[
                example.behavior.selected_candidate_index
            ]
            risk = max(
                candidate.features.party_risk,
                candidate.features.irreversibility_risk,
                candidate.features.uncertainty,
                candidate.features.travel_effort,
                candidate.features.execution_effort,
            )
            band = "low" if risk < 1.0 / 3.0 else "medium" if risk < 2.0 / 3.0 else "high"
            bands[band]["attempts"] += 1
            if example.example.outcome.status is LivingDexOutcomeStatus.CENSORED:
                bands[band]["censored"] += 1
        return {
            band: {
                "attempts": counts["attempts"],
                "censored": counts["censored"],
                "censoring_rate": (
                    counts["censored"] / counts["attempts"]
                    if counts["attempts"]
                    else 0.0
                ),
            }
            for band, counts in bands.items()
        }


def build_red_living_dex_calibration_batch(
    examples: Sequence[RedLivingDexCollectedExample],
) -> RedLivingDexCalibrationBatch:
    if not isinstance(examples, Sequence):
        raise TypeError("examples must be a sequence")
    return RedLivingDexCalibrationBatch(tuple(examples))


def _selected_option(example: RedLivingDexCollectedExample) -> RedBoundLivingDexOption:
    return example.adapted.ordered_options[example.behavior.selected_candidate_index]


def _selected_kind(example: RedLivingDexCollectedExample) -> LivingDexOptionKind:
    return example.adapted.menu.candidates[
        example.behavior.selected_candidate_index
    ].features.kind


def _selected_family_sha256(example: RedLivingDexCollectedExample) -> str:
    option = _selected_option(example)
    return canonical_sha256(
        {
            "family_ref": option.family_ref,
            "schema": "pokemon.red.private-transformation-family-join.v1",
        }
    )


def _selected_location_sha256(example: RedLivingDexCollectedExample) -> str:
    option = _selected_option(example)
    return canonical_sha256(
        {
            "location_ref": option.location_ref,
            "schema": "pokemon.red.private-option-location-join.v1",
        }
    )


def _partition_document(counts: Counter[str]) -> dict[str, int]:
    return {partition: counts[partition] for partition in ("development", "train")}


def _counter_document(counts: Counter[int]) -> dict[str, int]:
    return {str(value): counts[value] for value in sorted(counts)}


def _selected_kind_counts(
    examples: Sequence[RedLivingDexCollectedExample],
) -> dict[str, int]:
    counts = Counter(_selected_kind(example).value for example in examples)
    return {kind.value: counts[kind.value] for kind in LivingDexOptionKind}


def _offered_kind_counts(
    examples: Sequence[RedLivingDexCollectedExample],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for example in examples:
        counts.update(
            candidate.features.kind.value
            for candidate in example.adapted.menu.candidates
            if candidate.availability is LivingDexOptionAvailability.AVAILABLE
        )
    return {kind.value: counts[kind.value] for kind in LivingDexOptionKind}


__all__ = [
    "MINIMUM_DEVELOPMENT_FAMILIES",
    "MINIMUM_DEVELOPMENT_LOCATIONS",
    "MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES",
    "MINIMUM_SETTLED_TRAIN_EXAMPLES",
    "MINIMUM_TRAIN_FAMILIES",
    "MINIMUM_TRAIN_OPTION_KINDS",
    "RED_LIVING_DEX_CALIBRATION_BATCH_SCHEMA",
    "RedLivingDexCalibrationBatch",
    "RedLivingDexCalibrationError",
    "build_red_living_dex_calibration_batch",
]
