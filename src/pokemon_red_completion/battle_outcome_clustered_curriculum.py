"""Versioned action-free admission contracts for clustered battle updates.

The retired V2 batch required seven fresh train contexts.  Repeated attempts to
manufacture the final two contexts through a Red-specific relocation route were
falsified.  This successor asks the scientifically relevant question instead:
whether the retained outcome plus the five authentic fresh contexts contain
enough *measured action contrasts* to justify one descriptive train-only fit.
V1 remains immutable and failed its exact three-action rule. V2 has a separate
schema and policy identity for the prospective mixed-action contrast rule.

Every usable action is still measured from the exact same starting capture.
Each capture contributes one equally weighted preference example, regardless
of how many usable actions it exposes.  The eight development captures remain
an untouched, disjoint comparison set.  This module opens no state, computes no
prediction, records no outcome, and grants no gameplay authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from pokemon_red_completion.battle_outcome_batch import (
    BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
    MAXIMUM_LEVEL_GAP,
    MAXIMUM_RETAINED_PREFIX_LEVEL_GAP,
    BattleOutcomeBatchError,
    BattleOutcomePressureCandidate,
    RetainedBattleOutcomePrefix,
    _parse_pressure_candidate,
    _parse_retained_prefix,
    battle_outcome_fixed_heuristic_sha256,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition

BATTLE_OUTCOME_CLUSTERED_CURRICULUM_SCHEMA = (
    "pokemon-red-battle-outcome-clustered-curriculum-v1"
)
BATTLE_OUTCOME_CONTRAST_CURRICULUM_SCHEMA = (
    "pokemon-red-battle-outcome-contrast-curriculum-v2"
)
BATTLE_OUTCOME_CLUSTERED_POLICY_SCHEMA = (
    "pokemon-red-battle-outcome-clustered-policy-v1"
)
BATTLE_OUTCOME_CONTRAST_POLICY_SCHEMA = (
    "pokemon-red-battle-outcome-contrast-policy-v2"
)
FRESH_TRAIN_CONTEXTS = 5
TOTAL_TRAIN_CONTEXTS = 6
DEVELOPMENT_CONTEXTS = 8
MINIMUM_DISTINCT_VENUES = 2
MINIMUM_MARGIN_STRATA = 2
MINIMUM_PARTY_CONDITIONS = 2
MINIMUM_FRESH_THREE_ACTION_CONTEXTS = 5
MINIMUM_DEVELOPMENT_THREE_ACTION_CONTEXTS = 6
MINIMUM_CONTRAST_FRESH_THREE_ACTION_CONTEXTS = 3
MINIMUM_CONTRAST_DEVELOPMENT_THREE_ACTION_CONTEXTS = 6
MINIMUM_TRAIN_CONTRAST_ROWS = 9
MINIMUM_DEVELOPMENT_CONTRAST_ROWS = 14
MAXIMUM_TARGET_HIDDEN_RANK = 14
MINIMUM_RANK_SINGULAR_VALUE = 1e-6

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAXIMUM_PAYLOAD_BYTES = 32 * 1024 * 1024
_RANK_TOLERANCE = 1e-9

_CLUSTERED_POLICY = {
    "schema": BATTLE_OUTCOME_CLUSTERED_POLICY_SCHEMA,
    "retained_train_contexts": 1,
    "fresh_train_contexts": FRESH_TRAIN_CONTEXTS,
    "development_contexts": DEVELOPMENT_CONTEXTS,
    "train_example_weighting": "one_equal_contribution_per_upstream_capture",
    "within_capture_target": "uniform_over_best_measured_usable_actions",
    "fresh_action_measurement": "every_supported_usable_action_from_exact_reset",
    "maximum_level_gap": MAXIMUM_LEVEL_GAP,
    "maximum_retained_prefix_level_gap": MAXIMUM_RETAINED_PREFIX_LEVEL_GAP,
    "minimum_distinct_venues_per_partition": MINIMUM_DISTINCT_VENUES,
    "minimum_prior_margin_strata_per_partition": MINIMUM_MARGIN_STRATA,
    "minimum_party_conditions_per_partition": MINIMUM_PARTY_CONDITIONS,
    "minimum_fresh_three_action_contexts": MINIMUM_FRESH_THREE_ACTION_CONTEXTS,
    "minimum_development_three_action_contexts": (
        MINIMUM_DEVELOPMENT_THREE_ACTION_CONTEXTS
    ),
    "hidden_contrast_rank_rule": (
        "minimum_of_14_hidden_width_and_available_contrast_rows"
    ),
    "minimum_rank_singular_value": MINIMUM_RANK_SINGULAR_VALUE,
    "fit_count": 1,
    "fit_partition": "train_only",
    "development_prediction_commitment": "before_any_development_outcome",
    "development_use": "paired_descriptive_comparison_only",
    "inferential_claim": False,
    "authority_promoted": False,
    "teacher_choice_targets": 0,
}

_CONTRAST_POLICY = {
    "schema": BATTLE_OUTCOME_CONTRAST_POLICY_SCHEMA,
    "retained_train_contexts": 1,
    "fresh_train_contexts": FRESH_TRAIN_CONTEXTS,
    "development_contexts": DEVELOPMENT_CONTEXTS,
    "independent_example_unit": "one_upstream_capture",
    "train_example_weighting": "one_equal_contribution_per_upstream_capture",
    "within_capture_target": "uniform_over_best_measured_usable_actions",
    "fresh_action_measurement": "every_supported_usable_action_from_exact_reset",
    "contrast_definition": "each_nonreference_action_hidden_minus_first_action_hidden",
    "minimum_supported_actions_per_context": 2,
    "minimum_fresh_three_action_contexts": (
        MINIMUM_CONTRAST_FRESH_THREE_ACTION_CONTEXTS
    ),
    "minimum_development_three_action_contexts": (
        MINIMUM_CONTRAST_DEVELOPMENT_THREE_ACTION_CONTEXTS
    ),
    "minimum_train_contrast_rows": MINIMUM_TRAIN_CONTRAST_ROWS,
    "minimum_development_contrast_rows": MINIMUM_DEVELOPMENT_CONTRAST_ROWS,
    "maximum_level_gap": MAXIMUM_LEVEL_GAP,
    "maximum_retained_prefix_level_gap": MAXIMUM_RETAINED_PREFIX_LEVEL_GAP,
    "minimum_distinct_venues_per_partition": MINIMUM_DISTINCT_VENUES,
    "minimum_prior_margin_strata_per_partition": MINIMUM_MARGIN_STRATA,
    "minimum_party_conditions_per_partition": MINIMUM_PARTY_CONDITIONS,
    "hidden_contrast_rank_rule": "full_row_rank_up_to_hidden_width_14",
    "minimum_rank_singular_value": MINIMUM_RANK_SINGULAR_VALUE,
    "fit_count": 1,
    "fit_partition": "train_only",
    "development_prediction_commitment": "before_any_development_outcome",
    "development_use": "paired_descriptive_comparison_only",
    "inferential_claim": False,
    "authority_promoted": False,
    "teacher_choice_targets": 0,
}


class BattleOutcomeClusteredCurriculumError(ValueError):
    """Raised when the compact curriculum lacks support or independence."""


def battle_outcome_clustered_policy_sha256(*, version: str = "v1") -> str:
    """Return the immutable clustered weighting and admission policy."""

    if version == "v1":
        return canonical_sha256(_CLUSTERED_POLICY)
    if version == "v2":
        return canonical_sha256(_CONTRAST_POLICY)
    raise ValueError("clustered policy version is unsupported")


@dataclass(frozen=True, slots=True)
class BattleOutcomeClusteredCurriculum:
    """One retained plus five fresh train contexts and eight held-out contexts."""

    curriculum_id: str
    retained_prefix: RetainedBattleOutcomePrefix
    prefix: BattleOutcomePressureCandidate
    fresh_train: tuple[BattleOutcomePressureCandidate, ...]
    development: tuple[BattleOutcomePressureCandidate, ...]
    claim_registry_sha256: str
    train_catalog_sha256: str
    development_catalog_sha256: str
    policy_sha256: str = battle_outcome_clustered_policy_sha256()
    fixed_heuristic_sha256: str = battle_outcome_fixed_heuristic_sha256()

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.curriculum_id) is None:
            raise BattleOutcomeClusteredCurriculumError(
                "clustered curriculum identity differs"
            )
        if not isinstance(self.retained_prefix, RetainedBattleOutcomePrefix):
            raise BattleOutcomeClusteredCurriculumError(
                "clustered retained prefix differs"
            )
        for value, subject in (
            (self.claim_registry_sha256, "claim registry"),
            (self.train_catalog_sha256, "train catalog"),
            (self.development_catalog_sha256, "development catalog"),
            (self.policy_sha256, "clustered policy"),
            (self.fixed_heuristic_sha256, "fixed heuristic"),
        ):
            if _SHA256.fullmatch(value) is None:
                raise BattleOutcomeClusteredCurriculumError(f"{subject} differs")
        if self.policy_sha256 not in {
            battle_outcome_clustered_policy_sha256(version="v1"),
            battle_outcome_clustered_policy_sha256(version="v2"),
        }:
            raise BattleOutcomeClusteredCurriculumError("clustered policy differs")
        if self.fixed_heuristic_sha256 != battle_outcome_fixed_heuristic_sha256():
            raise BattleOutcomeClusteredCurriculumError("fixed heuristic differs")
        if (
            not isinstance(self.prefix, BattleOutcomePressureCandidate)
            or self.prefix.partition is not ScenarioPartition.TRAIN
            or self.prefix.claim_available
            or self.prefix.binding != self.retained_prefix.train
            or self.prefix.supported_candidate_indices
            != self.retained_prefix.train_supported_candidate_indices
        ):
            raise BattleOutcomeClusteredCurriculumError(
                "clustered retained train row differs"
            )
        self._require_partition(
            self.fresh_train,
            partition=ScenarioPartition.TRAIN,
            count=FRESH_TRAIN_CONTEXTS,
            subject="fresh train",
        )
        self._require_partition(
            self.development,
            partition=ScenarioPartition.DEVELOPMENT,
            count=DEVELOPMENT_CONTEXTS,
            subject="development",
        )
        if self.policy_version == "v1" and any(
            item.binding.supported_candidate_count < 3 for item in self.fresh_train
        ):
            raise BattleOutcomeClusteredCurriculumError(
                "clustered fresh train three-action coverage is inadequate"
            )
        if self.policy_version == "v2" and any(
            item.binding.supported_candidate_count < 2
            for item in (*self.fresh_train, *self.development)
        ):
            raise BattleOutcomeClusteredCurriculumError(
                "contrast curriculum requires two actions per context"
            )
        if self.policy_version == "v2" and sum(
            item.binding.supported_candidate_count >= 3 for item in self.fresh_train
        ) < MINIMUM_CONTRAST_FRESH_THREE_ACTION_CONTEXTS:
            raise BattleOutcomeClusteredCurriculumError(
                "contrast fresh train three-action coverage is inadequate"
            )
        selected = (self.prefix, *self.fresh_train, *self.development)
        if any(
            item.prior_model_sha256 != self.retained_prefix.original_prior_sha256
            for item in selected
        ):
            raise BattleOutcomeClusteredCurriculumError(
                "clustered candidates differ from the retained prior"
            )
        if len({item.hidden_width for item in selected}) != 1:
            raise BattleOutcomeClusteredCurriculumError(
                "clustered hidden widths differ"
            )
        self._require_independence(selected)
        self._require_pressure(
            (self.prefix, *self.fresh_train),
            subject="train",
            required_three_action_contexts=(
                MINIMUM_FRESH_THREE_ACTION_CONTEXTS
                if self.policy_version == "v1"
                else 0
            ),
            minimum_contrast_rows=(
                None
                if self.policy_version == "v1"
                else MINIMUM_TRAIN_CONTRAST_ROWS
            ),
            retained_capture_id=self.prefix.capture_id,
        )
        self._require_pressure(
            self.development,
            subject="development",
            required_three_action_contexts=(
                MINIMUM_DEVELOPMENT_THREE_ACTION_CONTEXTS
                if self.policy_version == "v1"
                else MINIMUM_CONTRAST_DEVELOPMENT_THREE_ACTION_CONTEXTS
            ),
            minimum_contrast_rows=(
                None
                if self.policy_version == "v1"
                else MINIMUM_DEVELOPMENT_CONTRAST_ROWS
            ),
        )

    @staticmethod
    def _require_partition(
        candidates: object,
        *,
        partition: ScenarioPartition,
        count: int,
        subject: str,
    ) -> None:
        if (
            not isinstance(candidates, tuple)
            or len(candidates) != count
            or any(
                not isinstance(item, BattleOutcomePressureCandidate)
                or item.partition is not partition
                or not item.claim_available
                for item in candidates
            )
        ):
            raise BattleOutcomeClusteredCurriculumError(
                f"clustered {subject} denominator differs"
            )

    def _require_independence(
        self,
        selected: Sequence[BattleOutcomePressureCandidate],
    ) -> None:
        forbidden = self.retained_prefix.forbidden_development
        identity_fields = (
            "capture_id",
            "source_cluster_sha256",
        )
        for field in identity_fields:
            values = tuple(getattr(item, field) for item in selected)
            if len(values) != len(set(values)):
                raise BattleOutcomeClusteredCurriculumError(
                    f"clustered curriculum repeats {field}"
                )
        binding_fields = (
            "root_lineage_id",
            "logical_root_sha256",
            "physical_root_sha256",
            "source_state_sha256",
            "initial_observation_sha256",
        )
        for field in binding_fields:
            values = tuple(getattr(item.binding, field) for item in selected)
            if len(values) != len(set(values)):
                raise BattleOutcomeClusteredCurriculumError(
                    f"clustered curriculum repeats {field}"
                )
            forbidden_value = getattr(forbidden, field)
            if forbidden_value in values:
                raise BattleOutcomeClusteredCurriculumError(
                    "clustered curriculum reuses retained development evidence"
                )

    @staticmethod
    def _require_pressure(
        candidates: Sequence[BattleOutcomePressureCandidate],
        *,
        subject: str,
        required_three_action_contexts: int,
        minimum_contrast_rows: int | None = None,
        retained_capture_id: str | None = None,
    ) -> None:
        if any(
            item.level_gap
            > (
                MAXIMUM_RETAINED_PREFIX_LEVEL_GAP
                if item.capture_id == retained_capture_id
                else MAXIMUM_LEVEL_GAP
            )
            for item in candidates
        ):
            raise BattleOutcomeClusteredCurriculumError(
                f"clustered {subject} level gap exceeds policy"
            )
        if len({item.venue_id for item in candidates}) < MINIMUM_DISTINCT_VENUES:
            raise BattleOutcomeClusteredCurriculumError(
                f"clustered {subject} venue diversity is inadequate"
            )
        if (
            sum(item.binding.supported_candidate_count >= 3 for item in candidates)
            < required_three_action_contexts
        ):
            raise BattleOutcomeClusteredCurriculumError(
                f"clustered {subject} three-action coverage is inadequate"
            )
        contrast_rows = sum(len(item.contrast_vectors) for item in candidates)
        if minimum_contrast_rows is not None and contrast_rows < minimum_contrast_rows:
            raise BattleOutcomeClusteredCurriculumError(
                f"contrast {subject} row coverage is inadequate"
            )
        if (
            len({item.prior_margin_stratum for item in candidates})
            < MINIMUM_MARGIN_STRATA
        ):
            raise BattleOutcomeClusteredCurriculumError(
                f"clustered {subject} prior-margin diversity is inadequate"
            )
        if (
            len({item.party_condition_id for item in candidates})
            < MINIMUM_PARTY_CONDITIONS
        ):
            raise BattleOutcomeClusteredCurriculumError(
                f"clustered {subject} party-condition diversity is inadequate"
            )
        rank = _hidden_contrast_rank(candidates)
        required_rank = _required_hidden_rank(candidates)
        if rank < required_rank:
            raise BattleOutcomeClusteredCurriculumError(
                f"clustered {subject} hidden contrast rank is inadequate"
            )
        if _rank_singular_value(candidates, required_rank) < MINIMUM_RANK_SINGULAR_VALUE:
            raise BattleOutcomeClusteredCurriculumError(
                f"clustered {subject} hidden contrast clearance is inadequate"
            )

    @property
    def original_prior_sha256(self) -> str:
        return self.retained_prefix.original_prior_sha256

    @property
    def policy_version(self) -> str:
        if self.policy_sha256 == battle_outcome_clustered_policy_sha256(version="v1"):
            return "v1"
        if self.policy_sha256 == battle_outcome_clustered_policy_sha256(version="v2"):
            return "v2"
        raise BattleOutcomeClusteredCurriculumError("clustered policy differs")

    @property
    def schema(self) -> str:
        if self.policy_version == "v1":
            return BATTLE_OUTCOME_CLUSTERED_CURRICULUM_SCHEMA
        return BATTLE_OUTCOME_CONTRAST_CURRICULUM_SCHEMA

    @property
    def train(self) -> tuple[BattleOutcomePressureCandidate, ...]:
        return (self.prefix, *self.fresh_train)

    @property
    def curriculum_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        information_summary: dict[str, object] = {
            "train_contexts": len(self.train),
            "fresh_train_contexts": len(self.fresh_train),
            "development_contexts": len(self.development),
            "fresh_train_measured_action_arms": sum(
                item.binding.supported_candidate_count for item in self.fresh_train
            ),
            "development_measured_action_arms": sum(
                item.binding.supported_candidate_count for item in self.development
            ),
            "train_distinct_venues": len({item.venue_id for item in self.train}),
            "development_distinct_venues": len(
                {item.venue_id for item in self.development}
            ),
            "train_prior_margin_strata": len(
                {item.prior_margin_stratum for item in self.train}
            ),
            "development_prior_margin_strata": len(
                {item.prior_margin_stratum for item in self.development}
            ),
            "train_party_conditions": len(
                {item.party_condition_id for item in self.train}
            ),
            "development_party_conditions": len(
                {item.party_condition_id for item in self.development}
            ),
            "train_hidden_contrast_rank": _hidden_contrast_rank(self.train),
            "train_required_hidden_contrast_rank": _required_hidden_rank(self.train),
            "development_hidden_contrast_rank": _hidden_contrast_rank(self.development),
            "development_required_hidden_contrast_rank": _required_hidden_rank(
                self.development
            ),
            "train_example_weight": 1.0 / len(self.train),
            "fit_count": 1,
        }
        if self.policy_version == "v2":
            information_summary.update(
                {
                    "train_contrast_rows": sum(
                        len(item.contrast_vectors) for item in self.train
                    ),
                    "development_contrast_rows": sum(
                        len(item.contrast_vectors) for item in self.development
                    ),
                    "fresh_train_three_action_contexts": sum(
                        item.binding.supported_candidate_count >= 3
                        for item in self.fresh_train
                    ),
                    "development_three_action_contexts": sum(
                        item.binding.supported_candidate_count >= 3
                        for item in self.development
                    ),
                }
            )
        return {
            "schema": self.schema,
            "status": "qualified_action_free",
            "curriculum_id": self.curriculum_id,
            "original_prior_sha256": self.original_prior_sha256,
            "retained_prefix_sha256": self.retained_prefix.retained_prefix_sha256,
            "retained_prefix": self.retained_prefix.public_dict(),
            "claim_registry_sha256": self.claim_registry_sha256,
            "train_catalog_sha256": self.train_catalog_sha256,
            "development_catalog_sha256": self.development_catalog_sha256,
            "policy_sha256": self.policy_sha256,
            "fixed_heuristic_id": BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
            "fixed_heuristic_sha256": self.fixed_heuristic_sha256,
            "prefix": self.prefix.public_dict(),
            "fresh_train": [item.public_dict() for item in self.fresh_train],
            "development": [item.public_dict() for item in self.development],
            "information_summary": information_summary,
            "protections": {
                "authority_promoted": False,
                "controller_actions": 0,
                "crystal_contexts_opened": 0,
                "development_outcomes_opened": 0,
                "full_game_replays": 0,
                "inferential_claim": False,
                "model_fits": 0,
                "predictions_computed": 0,
                "retained_prefix_reexecuted": False,
                "root_claims_created": 0,
                "sealed_red_cases_opened": 0,
                "teacher_choice_targets": 0,
                "teacher_queries": 0,
                "train_outcomes_opened": 0,
            },
            "private_path_fields": 0,
        }


def build_battle_outcome_clustered_curriculum(
    *,
    curriculum_id: str,
    retained_prefix: RetainedBattleOutcomePrefix,
    prefix: BattleOutcomePressureCandidate,
    fresh_train: Sequence[BattleOutcomePressureCandidate],
    development: Sequence[BattleOutcomePressureCandidate],
    claim_registry_sha256: str,
    train_catalog_sha256: str,
    development_catalog_sha256: str,
    policy_version: str = "v1",
) -> BattleOutcomeClusteredCurriculum:
    """Qualify one fixed, outcome-blind roster without selecting by outcome."""

    if isinstance(fresh_train, (str, bytes)) or not isinstance(fresh_train, Sequence):
        raise TypeError("clustered fresh train candidates require a sequence")
    if isinstance(development, (str, bytes)) or not isinstance(development, Sequence):
        raise TypeError("clustered development candidates require a sequence")
    policy_sha256 = battle_outcome_clustered_policy_sha256(version=policy_version)
    return BattleOutcomeClusteredCurriculum(
        curriculum_id=curriculum_id,
        retained_prefix=retained_prefix,
        prefix=prefix,
        fresh_train=tuple(sorted(fresh_train, key=lambda item: item.capture_id)),
        development=tuple(sorted(development, key=lambda item: item.capture_id)),
        claim_registry_sha256=claim_registry_sha256,
        train_catalog_sha256=train_catalog_sha256,
        development_catalog_sha256=development_catalog_sha256,
        policy_sha256=policy_sha256,
    )


def parse_battle_outcome_clustered_curriculum(
    payload: bytes,
) -> BattleOutcomeClusteredCurriculum:
    """Strictly reopen one canonical clustered curriculum qualification."""

    if not isinstance(payload, bytes):
        raise TypeError("clustered curriculum must be bytes")
    if not payload or len(payload) > _MAXIMUM_PAYLOAD_BYTES:
        raise BattleOutcomeClusteredCurriculumError(
            "clustered curriculum size is invalid"
        )
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleOutcomeClusteredCurriculumError(
            "clustered curriculum is not canonical JSON"
        ) from None
    expected_fields = {
        "schema",
        "status",
        "curriculum_id",
        "original_prior_sha256",
        "retained_prefix_sha256",
        "retained_prefix",
        "claim_registry_sha256",
        "train_catalog_sha256",
        "development_catalog_sha256",
        "policy_sha256",
        "fixed_heuristic_id",
        "fixed_heuristic_sha256",
        "prefix",
        "fresh_train",
        "development",
        "information_summary",
        "protections",
        "private_path_fields",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected_fields
        or value.get("schema")
        not in {
            BATTLE_OUTCOME_CLUSTERED_CURRICULUM_SCHEMA,
            BATTLE_OUTCOME_CONTRAST_CURRICULUM_SCHEMA,
        }
        or value.get("status") != "qualified_action_free"
        or value.get("fixed_heuristic_id") != BATTLE_OUTCOME_FIXED_HEURISTIC_ID
        or value.get("private_path_fields") != 0
    ):
        raise BattleOutcomeClusteredCurriculumError(
            "clustered curriculum fields differ"
        )
    fresh = value.get("fresh_train")
    development = value.get("development")
    if not isinstance(fresh, list) or not isinstance(development, list):
        raise BattleOutcomeClusteredCurriculumError(
            "clustered curriculum collections differ"
        )
    try:
        curriculum = BattleOutcomeClusteredCurriculum(
            curriculum_id=_string(value.get("curriculum_id"), "curriculum identity"),
            retained_prefix=_parse_retained_prefix(value.get("retained_prefix")),
            prefix=_parse_pressure_candidate(value.get("prefix")),
            fresh_train=tuple(_parse_pressure_candidate(item) for item in fresh),
            development=tuple(
                _parse_pressure_candidate(item) for item in development
            ),
            claim_registry_sha256=_string(
                value.get("claim_registry_sha256"), "claim registry"
            ),
            train_catalog_sha256=_string(
                value.get("train_catalog_sha256"), "train catalog"
            ),
            development_catalog_sha256=_string(
                value.get("development_catalog_sha256"), "development catalog"
            ),
            policy_sha256=_string(value.get("policy_sha256"), "clustered policy"),
            fixed_heuristic_sha256=_string(
                value.get("fixed_heuristic_sha256"), "fixed heuristic"
            ),
        )
    except BattleOutcomeBatchError as error:
        raise BattleOutcomeClusteredCurriculumError(str(error)) from None
    if (
        value.get("schema") != curriculum.schema
        or value.get("original_prior_sha256") != curriculum.original_prior_sha256
        or value.get("retained_prefix_sha256")
        != curriculum.retained_prefix.retained_prefix_sha256
        or value.get("information_summary")
        != curriculum.public_dict()["information_summary"]
        or value.get("protections") != curriculum.public_dict()["protections"]
        or curriculum.canonical_bytes() != payload
    ):
        raise BattleOutcomeClusteredCurriculumError(
            "clustered curriculum is not canonical JSON"
        )
    return curriculum


def _hidden_contrast_matrix(
    candidates: Sequence[BattleOutcomePressureCandidate],
) -> np.ndarray:
    rows = tuple(vector for item in candidates for vector in item.contrast_vectors)
    if not rows:
        raise BattleOutcomeClusteredCurriculumError(
            "clustered curriculum has no hidden contrasts"
        )
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2 or not np.all(np.isfinite(matrix)):
        raise BattleOutcomeClusteredCurriculumError(
            "clustered hidden contrast matrix is invalid"
        )
    return matrix


def _required_hidden_rank(
    candidates: Sequence[BattleOutcomePressureCandidate],
) -> int:
    matrix = _hidden_contrast_matrix(candidates)
    return min(MAXIMUM_TARGET_HIDDEN_RANK, matrix.shape[0], matrix.shape[1])


def _hidden_contrast_rank(
    candidates: Sequence[BattleOutcomePressureCandidate],
) -> int:
    try:
        return int(
            np.linalg.matrix_rank(
                _hidden_contrast_matrix(candidates),
                tol=_RANK_TOLERANCE,
            )
        )
    except np.linalg.LinAlgError:
        raise BattleOutcomeClusteredCurriculumError(
            "clustered hidden contrast rank is not computable"
        ) from None


def _rank_singular_value(
    candidates: Sequence[BattleOutcomePressureCandidate],
    required_rank: int,
) -> float:
    try:
        singular_values = np.linalg.svd(
            _hidden_contrast_matrix(candidates),
            compute_uv=False,
        )
    except np.linalg.LinAlgError:
        raise BattleOutcomeClusteredCurriculumError(
            "clustered hidden singular values are not computable"
        ) from None
    if len(singular_values) < required_rank:
        return 0.0
    value = float(singular_values[required_rank - 1])
    if not math.isfinite(value):
        raise BattleOutcomeClusteredCurriculumError(
            "clustered hidden singular value is invalid"
        )
    return value


def _canonical_payload(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate object key")
        value[key] = item
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str):
        raise BattleOutcomeClusteredCurriculumError(f"{subject} differs")
    return value
