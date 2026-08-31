"""Outcome-blind decision-pressure roster for the V2 battle curriculum.

The first claim-first battle pair proved that the execution loop works but
produced no held-choice discordance.  This module freezes the next unit of
work at the correct level: one already-retained train prefix, seven fresh
train contexts, and eight simultaneously held development contexts.

Selection is allowed to use only policy-visible features, the frozen prior's
scores and hidden representation, authenticated lineage/claim metadata, and
declared venue/level facts.  It cannot contain outcomes, preferred actions,
teacher choices, or replacement slots.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_experiment import (
    BattleOutcomeCaptureBinding,
    BattleOutcomeExperimentError,
    BattleOutcomeExperimentPlan,
    battle_outcome_hidden_menu_sha256,
    battle_outcome_menu_sha256,
    parse_battle_outcome_capture_binding,
    parse_battle_outcome_experiment_plan,
)
from pokemon_red_completion.battle_semantics import (
    POKEMON_TYPES,
    STATUS_CATEGORIES,
    BattleFeatureBatch,
)
from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAdmissionError,
    ClaimFirstAvailabilitySnapshot,
    parse_claim_first_availability_snapshot,
)
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition

BATTLE_OUTCOME_BATCH_ROSTER_SCHEMA = "pokemon-red-battle-outcome-batch-roster-v2"
BATTLE_OUTCOME_BATCH_FREEZE_SCHEMA = "pokemon-red-battle-outcome-batch-freeze-v2"
BATTLE_OUTCOME_PRESSURE_INVENTORY_SCHEMA = (
    "pokemon-red-battle-outcome-pressure-inventory-v2"
)
BATTLE_OUTCOME_PRESSURE_CANDIDATE_SCHEMA = (
    "pokemon-red-battle-outcome-pressure-candidate-v2"
)
BATTLE_OUTCOME_PRESSURE_POLICY_SCHEMA = (
    "pokemon-red-battle-outcome-pressure-policy-v2"
)
BATTLE_OUTCOME_FIXED_HEURISTIC_ID = "pokemon.core.battle.fixed-power-heuristic.v1"

FRESH_TRAIN_CONTEXTS = 7
DEVELOPMENT_CONTEXTS = 8
TOTAL_TRAIN_CONTEXTS = FRESH_TRAIN_CONTEXTS + 1
MAXIMUM_LEVEL_GAP = 12
MINIMUM_DISTINCT_VENUES = 2
MINIMUM_THREE_ACTION_CONTEXTS = 6
MINIMUM_MARGIN_STRATA = 2
MINIMUM_PARTY_CONDITIONS = 2
MAXIMUM_SINGLE_BUCKET_CONTEXTS = 6

_PRIOR_MARGIN_BOUNDARIES = (0.05, 0.20, 0.50)
_HIDDEN_RANK_TOLERANCE = 1e-9
_MINIMUM_FULL_RANK_SINGULAR_VALUE = 1e-6
_LOGDET_REGULARIZER = 1.0
_HEURISTIC_TIE_TOLERANCE = 1e-12
_MAXIMUM_INDEPENDENCE_SEARCH_NODES = 100_000

_VENUE_GROUP_PREFIXES = (
    "digletts_cave",
    "mt_moon",
    "pokemon_mansion",
    "pokemon_tower",
    "rock_tunnel",
    "safari_zone",
    "victory_road",
)

_MAXIMUM_ROSTER_BYTES = 4 * 1024 * 1024
_MAXIMUM_FREEZE_BYTES = 32 * 1024 * 1024
_MAXIMUM_PRESSURE_INVENTORY_BYTES = 16 * 1024 * 1024
_MAXIMUM_RETAINED_PREFIX_BYTES = 512 * 1024
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EXCLUSION_REASONS = {
    "claim_unavailable",
    "level_gap_exceeded",
    "not_selected_by_pressure",
    "previously_consumed",
}
_PRESSURE_POLICY = {
    "schema": BATTLE_OUTCOME_PRESSURE_POLICY_SCHEMA,
    "fresh_train_contexts": FRESH_TRAIN_CONTEXTS,
    "development_contexts": DEVELOPMENT_CONTEXTS,
    "retained_train_prefixes": 1,
    "maximum_level_gap": MAXIMUM_LEVEL_GAP,
    "minimum_distinct_venues_per_partition": MINIMUM_DISTINCT_VENUES,
    "minimum_three_action_contexts_per_partition": MINIMUM_THREE_ACTION_CONTEXTS,
    "minimum_prior_margin_strata_per_partition": MINIMUM_MARGIN_STRATA,
    "minimum_party_conditions_per_partition": MINIMUM_PARTY_CONDITIONS,
    "maximum_single_venue_margin_or_party_bucket_per_partition": (
        MAXIMUM_SINGLE_BUCKET_CONTEXTS
    ),
    "prior_margin_boundaries": list(_PRIOR_MARGIN_BOUNDARIES),
    "hidden_rank_tolerance": _HIDDEN_RANK_TOLERANCE,
    "minimum_full_rank_singular_value": _MINIMUM_FULL_RANK_SINGULAR_VALUE,
    "hidden_logdet": {
        "formula": "logdet(I + X.T@X)",
        "identity_regularizer": _LOGDET_REGULARIZER,
        "canonical_output_field": False,
    },
    "required_hidden_contrast_rank": "full_output_head_width",
    "inventory_order": ["partition_value_asc", "capture_id_asc"],
    "hard_filter_order": [
        "previously_consumed",
        "claim_unavailable",
        "level_gap_exceeded",
    ],
    "identity_dimensions": [
        "capture_id",
        "root_lineage_id",
        "logical_root_sha256",
        "physical_root_sha256",
        "source_state_sha256",
        "initial_observation_sha256",
        "title_neutral_menu_cluster_sha256",
    ],
    "claim_identity": {
        "schema": "pokemon-red-battle-outcome-root-availability-key-v2",
        "fields": ["logical_root_sha256", "physical_root_sha256"],
    },
    "venue_grouping": {
        "schema": "pokemon-red-map-area-group-v1",
        "multi_map_prefixes": list(_VENUE_GROUP_PREFIXES),
    },
    "party_condition": {
        "hp_buckets": 4,
        "level_bucket_width": 10,
        "status_categories": list(STATUS_CATEGORIES),
        "type_categories": list(POKEMON_TYPES),
        "type_cardinality": [1, 2],
    },
    "selection_order": [
        "incremental_hidden_contrast_rank_desc",
        "new_venue_desc",
        "new_prior_margin_stratum_desc",
        "new_party_condition_desc",
        "three_supported_actions_desc",
        "level_gap_asc",
        "prior_top_two_margin_asc",
        "hidden_logdet_desc",
        "capture_id_asc",
        "bounded_lexical_independent_subset_fallback",
        "deterministic_one_then_two_swap_feasibility_repair",
    ],
    "maximum_independence_fallback_nodes": _MAXIMUM_INDEPENDENCE_SEARCH_NODES,
    "repair_ranking": [
        "hidden_contrast_rank_desc",
        "minimum_full_rank_singular_value_desc",
        "hidden_logdet_desc",
        "maximum_venue_bucket_asc",
        "maximum_margin_bucket_asc",
        "maximum_party_bucket_asc",
        "total_level_gap_asc",
        "total_prior_top_two_margin_asc",
        "capture_ids_asc",
    ],
    "repair_tie_break": "lexicographically_smallest_complete_capture_id_tuple",
    "selection_failure_claim": "selector_failure_not_capacity_falsification",
    "outcome_fields": 0,
    "teacher_choice_fields": 0,
    "replacement_slots": 0,
}
_FIXED_HEURISTIC_TERMS: tuple[tuple[str, float], ...] = (
    ("move.accuracy_weighted_effective_power_fraction", 4.0),
    ("move.effective_power_fraction", 1.0),
    ("move.power_fraction", 0.25),
    ("move.accuracy", 0.05),
    ("move.pp_fraction", 0.02),
    ("move.priority", 0.02),
    ("move.effect.recharge", -0.25),
    ("move.effect.self_destruct", -4.0),
)
_FIXED_HEURISTIC: dict[str, object] = {
    "schema": "pokemon.core.battle.fixed-power-heuristic-contract.v1",
    "heuristic_id": BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
    "terms": [list(term) for term in _FIXED_HEURISTIC_TERMS],
    "tie_break": "lowest_candidate_index",
    "tie_absolute_tolerance": _HEURISTIC_TIE_TOLERANCE,
    "tie_relative_tolerance": 0.0,
    "usable_mask": "legal_and_current_pp_positive",
}


class BattleOutcomeBatchError(ValueError):
    """Raised before an outcome-blind batch can drift or overclaim capacity."""


@dataclass(frozen=True, slots=True)
class RetainedBattleOutcomePrefix:
    """Authenticated V1 train evidence and the consumed V1 development exclusion."""

    plan: BattleOutcomeExperimentPlan
    artifact_manifest_sha256: str
    train_record_sha256: str
    train_supported_candidate_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, BattleOutcomeExperimentPlan):
            raise BattleOutcomeBatchError("retained V1 plan is invalid")
        for value, subject in (
            (self.artifact_manifest_sha256, "retained artifact manifest"),
            (self.train_record_sha256, "retained train record"),
        ):
            _require_sha256(value, subject)
        if (
            not isinstance(self.train_supported_candidate_indices, tuple)
            or len(self.train_supported_candidate_indices)
            != self.train.supported_candidate_count
            or self.train_supported_candidate_indices
            != tuple(sorted(set(self.train_supported_candidate_indices)))
            or any(
                type(index) is not int or not 0 <= index <= 3  # noqa: E721
                for index in self.train_supported_candidate_indices
            )
        ):
            raise BattleOutcomeBatchError(
                "retained V1 train candidate denominator differs"
            )

    @property
    def plan_sha256(self) -> str:
        return self.plan.plan_sha256

    @property
    def original_prior_sha256(self) -> str:
        return self.plan.base_model_sha256

    @property
    def train(self) -> BattleOutcomeCaptureBinding:
        return self.plan.train

    @property
    def forbidden_development(self) -> BattleOutcomeCaptureBinding:
        return self.plan.development

    @property
    def retained_prefix_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-battle-outcome-retained-prefix-v1",
            "status": "verified_no_replay",
            "plan_sha256": self.plan_sha256,
            "plan": self.plan.public_dict(),
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
            "original_prior_sha256": self.original_prior_sha256,
            "train_record_sha256": self.train_record_sha256,
            "train_supported_candidate_indices": list(
                self.train_supported_candidate_indices
            ),
            "protections": {
                "development_reused": False,
                "prefix_reexecuted": False,
                "retained_outcomes_opened_by_projection": True,
                "teacher_queries": 0,
            },
            "private_path_fields": 0,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.public_dict())


def build_retained_battle_outcome_prefix(
    plan: BattleOutcomeExperimentPlan,
    *,
    artifact_manifest_sha256: str,
    train_collection_record: Mapping[str, object],
) -> RetainedBattleOutcomePrefix:
    """Join a fully inspected V1 artifact to its exact prospective plan."""

    if not isinstance(plan, BattleOutcomeExperimentPlan):
        raise TypeError("retained prefix requires a battle outcome plan")
    _require_sha256(artifact_manifest_sha256, "retained artifact manifest")
    supported = _validate_retained_train_collection(plan, train_collection_record)
    return RetainedBattleOutcomePrefix(
        plan=plan,
        artifact_manifest_sha256=artifact_manifest_sha256,
        train_record_sha256=canonical_sha256(train_collection_record),
        train_supported_candidate_indices=supported,
    )


def parse_retained_battle_outcome_prefix(
    payload: bytes,
) -> RetainedBattleOutcomePrefix:
    """Strictly reopen one canonical path-free V1 retained-prefix projection."""

    if not isinstance(payload, bytes):
        raise TypeError("retained battle outcome prefix must be bytes")
    if not payload or len(payload) > _MAXIMUM_RETAINED_PREFIX_BYTES:
        raise BattleOutcomeBatchError("retained prefix size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleOutcomeBatchError(
            "retained prefix is not canonical JSON"
        ) from None
    retained = _parse_retained_prefix(value)
    if retained.canonical_bytes() != payload:
        raise BattleOutcomeBatchError(
            "retained prefix is not canonical JSON"
        )
    return retained


def _validate_retained_train_collection(
    plan: BattleOutcomeExperimentPlan,
    record: Mapping[str, object],
) -> tuple[int, ...]:
    fields = {
        "record_type",
        "split",
        "collection",
        "unexecuted_counterfactual_targets",
        "unmeasured_action_targets",
    }
    if (
        not isinstance(record, Mapping)
        or set(record) != fields
        or record.get("record_type") != "battle_outcome_collection"
        or record.get("split") != ScenarioPartition.TRAIN.value
        or record.get("unexecuted_counterfactual_targets") != 0
        or record.get("unmeasured_action_targets") != 0
    ):
        raise BattleOutcomeBatchError("retained V1 train record fields differ")
    collection = record.get("collection")
    collection_fields = {
        "schema",
        "capture_id",
        "manifest_sha256",
        "root_lineage_id",
        "partition",
        "initial_state_sha256",
        "initial_observation_sha256",
        "candidate_count",
        "measured_candidate_count",
        "outcomes",
        "best_candidate_indices",
        "learner_update_eligible",
        "counterfactual_pre_attack_frames",
        "teacher_queries",
        "teacher_choice_targets",
        "full_game_replays",
        "private_path_fields",
    }
    if (
        not isinstance(collection, Mapping)
        or set(collection) != collection_fields
        or collection.get("schema")
        != "pokemon.red.battle.outcome-collection.v1"
        or collection.get("capture_id") != plan.train.capture_id
        or collection.get("manifest_sha256") != plan.train.manifest_sha256
        or collection.get("root_lineage_id") != plan.train.root_lineage_id
        or collection.get("partition") != ScenarioPartition.TRAIN.value
        or collection.get("initial_state_sha256") != plan.train.state_sha256
        or collection.get("initial_observation_sha256")
        != plan.train.initial_observation_sha256
        or collection.get("measured_candidate_count")
        != plan.train.supported_candidate_count
        or collection.get("learner_update_eligible") is not True
        or collection.get("teacher_queries") != 0
        or collection.get("teacher_choice_targets") != 0
        or collection.get("full_game_replays") != 0
        or collection.get("private_path_fields") != 0
    ):
        raise BattleOutcomeBatchError("retained V1 train collection differs")
    outcomes = collection.get("outcomes")
    best = collection.get("best_candidate_indices")
    candidate_count = collection.get("candidate_count")
    if (
        type(candidate_count) is not int  # noqa: E721
        or not plan.train.supported_candidate_count <= candidate_count <= 4
        or not isinstance(outcomes, list)
        or len(outcomes) != candidate_count
        or not isinstance(best, list)
    ):
        raise BattleOutcomeBatchError("retained V1 train denominator differs")
    pre_attack_frames = _integer(
        collection.get("counterfactual_pre_attack_frames"),
        "retained pre-attack frames",
    )
    utilities: dict[int, float] = {}
    for index, outcome in enumerate(outcomes):
        if outcome is None:
            continue
        utilities[index] = _validate_retained_turn_outcome(
            outcome,
            pre_attack_frames=pre_attack_frames,
        )
    if len(utilities) != plan.train.supported_candidate_count:
        raise BattleOutcomeBatchError("retained V1 train measurement count differs")
    best_utility = max(utilities.values())
    expected_best = tuple(
        index
        for index, utility in utilities.items()
        if math.isclose(
            utility,
            best_utility,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    )
    if (
        tuple(best) != expected_best
        or any(type(index) is not int for index in best)  # noqa: E721
    ):
        raise BattleOutcomeBatchError("retained V1 train preference differs")
    return tuple(utilities)


def _validate_retained_turn_outcome(
    value: object,
    *,
    pre_attack_frames: int,
) -> float:
    fields = {
        "schema",
        "move_executed",
        "opponent_damage_fraction",
        "player_damage_fraction",
        "opponent_fainted",
        "player_fainted",
        "battle_exited",
        "actions_executed",
        "frames_executed",
        "pre_attack_frames",
        "utility",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("schema") != "pokemon.core.battle.selected-turn-outcome.v2"
    ):
        raise BattleOutcomeBatchError("retained V1 turn outcome fields differ")
    move_executed = _boolean(value.get("move_executed"), "move executed")
    opponent_fainted = _boolean(
        value.get("opponent_fainted"),
        "opponent fainted",
    )
    player_fainted = _boolean(value.get("player_fainted"), "player fainted")
    battle_exited = _boolean(value.get("battle_exited"), "battle exited")
    del move_executed, battle_exited
    opponent_damage = _number(
        value.get("opponent_damage_fraction"),
        "opponent damage",
    )
    player_damage = _number(
        value.get("player_damage_fraction"),
        "player damage",
    )
    if not 0.0 <= opponent_damage <= 1.0 or not 0.0 <= player_damage <= 1.0:
        raise BattleOutcomeBatchError("retained V1 damage fraction differs")
    actions = _integer(value.get("actions_executed"), "retained actions")
    frames = _integer(value.get("frames_executed"), "retained frames")
    observed_pre_attack = _integer(
        value.get("pre_attack_frames"),
        "retained outcome pre-attack frames",
    )
    if (
        actions < 1
        or frames < 1
        or observed_pre_attack != pre_attack_frames
        or observed_pre_attack > frames
    ):
        raise BattleOutcomeBatchError("retained V1 execution bounds differ")
    expected_utility = (
        2.0 * float(opponent_fainted)
        - 2.0 * float(player_fainted)
        + opponent_damage
        - player_damage
    )
    utility = _number(value.get("utility"), "retained utility")
    if not math.isclose(
        utility,
        expected_utility,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise BattleOutcomeBatchError("retained V1 outcome utility differs")
    return utility


def battle_outcome_pressure_policy_sha256() -> str:
    """Return the exact deterministic roster-selection contract."""

    return canonical_sha256(_PRESSURE_POLICY)


def battle_outcome_fixed_heuristic_sha256() -> str:
    """Return the fixed non-learned development-control identity."""

    return canonical_sha256(_FIXED_HEURISTIC)


def battle_outcome_model_sha256(model: MaskedMLPMoveRanker) -> str:
    """Bind the complete model, including the output head used for margins."""

    if not isinstance(model, MaskedMLPMoveRanker):
        raise TypeError("battle outcome model digest requires the nonlinear ranker")
    return hashlib.sha256(model.to_json().encode("ascii")).hexdigest()


def battle_outcome_source_cluster_sha256(
    binding: BattleOutcomeCaptureBinding,
) -> str:
    """Derive a source cluster only from authenticated capture provenance."""

    if not isinstance(binding, BattleOutcomeCaptureBinding):
        raise TypeError("battle outcome source cluster requires a capture binding")
    return canonical_sha256(
        {
            "schema": "pokemon-red-battle-outcome-source-cluster-v2",
            "title_neutral_menu_sha256": binding.menu_sha256,
        }
    )


def battle_outcome_claim_identity_sha256(
    binding: BattleOutcomeCaptureBinding,
) -> str:
    """Bind the exact logical/physical pair checked in the claim registry."""

    if not isinstance(binding, BattleOutcomeCaptureBinding):
        raise TypeError("battle outcome claim identity requires a capture binding")
    return canonical_sha256(
        {
            "logical_root_sha256": binding.logical_root_sha256,
            "physical_root_sha256": binding.physical_root_sha256,
            "schema": "pokemon-red-battle-outcome-root-availability-key-v2",
        }
    )


def battle_outcome_fixed_heuristic_choice(features: BattleFeatureBatch) -> int:
    """Choose one usable move using only simple transferable power features."""

    if not isinstance(features, BattleFeatureBatch):
        raise TypeError("fixed battle heuristic requires a BattleFeatureBatch")
    indices = {
        name: features.feature_names.index(name)
        for name, _ in _FIXED_HEURISTIC_TERMS
    }
    scored: list[tuple[float, int]] = []
    for candidate_index, (vector, legal, pp) in enumerate(
        zip(
            features.candidate_vectors,
            features.legal_mask,
            features.current_pp,
            strict=True,
        )
    ):
        if not legal or pp <= 0:
            continue
        score = sum(
            weight * vector[indices[name]]
            for name, weight in _FIXED_HEURISTIC_TERMS
        )
        scored.append((score, candidate_index))
    if not scored:
        raise BattleOutcomeBatchError("fixed battle heuristic has no usable candidate")
    best_score = max(score for score, _ in scored)
    return min(
        index
        for score, index in scored
        if math.isclose(
            score,
            best_score,
            rel_tol=0.0,
            abs_tol=_HEURISTIC_TIE_TOLERANCE,
        )
    )


@dataclass(frozen=True, slots=True)
class BattleOutcomePressureCandidate:
    """One outcome-blind capture plus frozen-prior decision-pressure facts."""

    binding: BattleOutcomeCaptureBinding
    prior_model_sha256: str
    source_cluster_sha256: str
    player_level: int
    opponent_level: int
    player_hp_ratio: float
    opponent_hp_ratio: float
    player_status_id: str
    player_type_ids: tuple[str, ...]
    supported_candidate_indices: tuple[int, ...]
    prior_scores: tuple[float, ...]
    hidden_embeddings: tuple[tuple[float, ...], ...]
    claim_available: bool

    def __post_init__(self) -> None:
        if not isinstance(self.binding, BattleOutcomeCaptureBinding):
            raise BattleOutcomeBatchError("pressure candidate binding is invalid")
        _require_sha256(self.prior_model_sha256, "pressure prior model")
        _require_sha256(self.source_cluster_sha256, "source cluster")
        if self.source_cluster_sha256 != battle_outcome_source_cluster_sha256(
            self.binding
        ):
            raise BattleOutcomeBatchError(
                "pressure source cluster differs from authenticated provenance"
            )
        for level_value, subject in (
            (self.player_level, "player level"),
            (self.opponent_level, "opponent level"),
        ):
            if (  # noqa: E721
                type(level_value) is not int or not 1 <= level_value <= 100
            ):
                raise BattleOutcomeBatchError(f"pressure {subject} is invalid")
        if type(self.claim_available) is not bool:  # noqa: E721
            raise BattleOutcomeBatchError("pressure claim availability is invalid")
        for ratio_value, subject in (
            (self.player_hp_ratio, "player HP ratio"),
            (self.opponent_hp_ratio, "opponent HP ratio"),
        ):
            if (
                isinstance(ratio_value, bool)
                or not isinstance(ratio_value, (int, float))
                or not math.isfinite(float(ratio_value))
                or not 0.0 <= float(ratio_value) <= 1.0
            ):
                raise BattleOutcomeBatchError(f"pressure {subject} is invalid")
        if self.player_status_id not in STATUS_CATEGORIES:
            raise BattleOutcomeBatchError("pressure player status is invalid")
        if (
            not isinstance(self.player_type_ids, tuple)
            or not 1 <= len(self.player_type_ids) <= 2
            or len(set(self.player_type_ids)) != len(self.player_type_ids)
            or any(type_id not in POKEMON_TYPES for type_id in self.player_type_ids)
            or self.player_type_ids
            != tuple(type_id for type_id in POKEMON_TYPES if type_id in self.player_type_ids)
        ):
            raise BattleOutcomeBatchError("pressure player type profile is invalid")
        indices = self.supported_candidate_indices
        if (
            not isinstance(indices, tuple)
            or len(indices) != self.binding.supported_candidate_count
            or indices != tuple(sorted(set(indices)))
            or any(type(index) is not int or not 0 <= index <= 3 for index in indices)  # noqa: E721
        ):
            raise BattleOutcomeBatchError("pressure supported candidate indices differ")
        if (
            not isinstance(self.prior_scores, tuple)
            or len(self.prior_scores) != len(indices)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in self.prior_scores
            )
        ):
            raise BattleOutcomeBatchError("pressure prior scores are invalid")
        ordered_scores = sorted(
            (float(value) for value in self.prior_scores),
            reverse=True,
        )
        if not math.isfinite(ordered_scores[0] - ordered_scores[1]):
            raise BattleOutcomeBatchError("pressure prior margin is invalid")
        if (
            not isinstance(self.hidden_embeddings, tuple)
            or len(self.hidden_embeddings) != len(indices)
            or any(not isinstance(row, tuple) for row in self.hidden_embeddings)
        ):
            raise BattleOutcomeBatchError("pressure hidden embeddings are invalid")
        widths = {len(row) for row in self.hidden_embeddings}
        if (
            len(widths) != 1
            or not 2 <= next(iter(widths)) <= 128
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not -1.0 <= float(value) <= 1.0
                for row in self.hidden_embeddings
                for value in row
            )
        ):
            raise BattleOutcomeBatchError("pressure hidden embedding width differs")
        expected_hidden_sha256 = canonical_sha256(
            {
                "embeddings": self.hidden_embeddings,
                "schema": "pokemon.red.battle-outcome-hidden-menu.v1",
            }
        )
        if expected_hidden_sha256 != self.binding.hidden_embedding_sha256:
            raise BattleOutcomeBatchError(
                "pressure hidden embeddings differ from the capture binding"
            )

    @property
    def partition(self) -> ScenarioPartition:
        return self.binding.partition

    @property
    def capture_id(self) -> str:
        return self.binding.capture_id

    @property
    def venue_id(self) -> str:
        try:
            map_name = MapId(self.binding.expected_map).name.lower()
        except ValueError:
            return f"map-{self.binding.expected_map:03d}"
        return next(
            (
                prefix
                for prefix in _VENUE_GROUP_PREFIXES
                if map_name == prefix or map_name.startswith(f"{prefix}_")
            ),
            map_name,
        )

    @property
    def hidden_width(self) -> int:
        return len(self.hidden_embeddings[0])

    @property
    def level_gap(self) -> int:
        return abs(self.player_level - self.opponent_level)

    @property
    def prior_top_two_margin(self) -> float:
        ordered = sorted((float(value) for value in self.prior_scores), reverse=True)
        return ordered[0] - ordered[1]

    @property
    def prior_margin_stratum(self) -> int:
        margin = self.prior_top_two_margin
        for index, boundary in enumerate(_PRIOR_MARGIN_BOUNDARIES):
            if margin <= boundary:
                return index
        return 3

    @property
    def party_condition_id(self) -> str:
        hp_bucket = min(3, int(float(self.player_hp_ratio) * 4.0))
        level_bucket = (self.player_level - 1) // 10
        type_profile = "-".join(self.player_type_ids)
        return (
            f"hp-{hp_bucket}.status-{self.player_status_id}.level-{level_bucket}."
            f"types-{type_profile}"
        )

    @property
    def contrast_vectors(self) -> tuple[tuple[float, ...], ...]:
        anchor = self.hidden_embeddings[0]
        return tuple(
            tuple(value - base for value, base in zip(row, anchor, strict=True))
            for row in self.hidden_embeddings[1:]
        )

    @property
    def pressure_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    @property
    def claim_identity_sha256(self) -> str:
        return battle_outcome_claim_identity_sha256(self.binding)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": BATTLE_OUTCOME_PRESSURE_CANDIDATE_SCHEMA,
            "binding": self.binding.public_dict(),
            "prior_model_sha256": self.prior_model_sha256,
            "venue_id": self.venue_id,
            "source_cluster_sha256": self.source_cluster_sha256,
            "claim_identity_sha256": self.claim_identity_sha256,
            "player_level": self.player_level,
            "opponent_level": self.opponent_level,
            "player_hp_ratio": self.player_hp_ratio,
            "opponent_hp_ratio": self.opponent_hp_ratio,
            "player_status_id": self.player_status_id,
            "player_type_ids": list(self.player_type_ids),
            "party_condition_id": self.party_condition_id,
            "supported_candidate_indices": list(self.supported_candidate_indices),
            "prior_scores": list(self.prior_scores),
            "hidden_embeddings": [list(row) for row in self.hidden_embeddings],
            "claim_available": self.claim_available,
            "level_gap": self.level_gap,
            "prior_top_two_margin": self.prior_top_two_margin,
            "prior_margin_stratum": self.prior_margin_stratum,
            "outcome_fields": 0,
            "teacher_choice_fields": 0,
        }


def build_battle_outcome_pressure_candidate(
    binding: BattleOutcomeCaptureBinding,
    features: BattleFeatureBatch,
    model: MaskedMLPMoveRanker,
    *,
    expected_prior_sha256: str,
    claim_available: bool,
) -> BattleOutcomePressureCandidate:
    """Derive one pressure row without opening or predicting an outcome."""

    if not isinstance(binding, BattleOutcomeCaptureBinding):
        raise TypeError("pressure candidate requires a capture binding")
    if not isinstance(features, BattleFeatureBatch):
        raise TypeError("pressure candidate requires a BattleFeatureBatch")
    if not isinstance(model, MaskedMLPMoveRanker):
        raise TypeError("pressure candidate requires the frozen nonlinear prior")
    _require_sha256(expected_prior_sha256, "expected pressure prior")
    observed_prior_sha256 = battle_outcome_model_sha256(model)
    if observed_prior_sha256 != expected_prior_sha256:
        raise BattleOutcomeBatchError(
            "pressure model differs from the declared original prior"
        )
    if battle_outcome_menu_sha256(features) != binding.menu_sha256:
        raise BattleOutcomeBatchError("pressure features differ from the capture menu")
    if battle_outcome_hidden_menu_sha256(model, features) != binding.hidden_embedding_sha256:
        raise BattleOutcomeBatchError("pressure model differs from the capture binding")
    supported = tuple(
        index
        for index, (legal, pp) in enumerate(
            zip(features.legal_mask, features.current_pp, strict=True)
        )
        if legal and pp > 0
    )
    if len(supported) != binding.supported_candidate_count:
        raise BattleOutcomeBatchError("pressure supported candidate count differs")
    scores = model.scores(features.candidate_vectors)
    hidden = model.hidden_embeddings(features.candidate_vectors)
    player_level = _level_from_features(features, "state.player_level_fraction")
    opponent_level = _level_from_features(features, "state.opponent_level_fraction")
    return BattleOutcomePressureCandidate(
        binding=binding,
        prior_model_sha256=observed_prior_sha256,
        source_cluster_sha256=battle_outcome_source_cluster_sha256(binding),
        player_level=player_level,
        opponent_level=opponent_level,
        player_hp_ratio=_shared_feature_value(
            features,
            "state.player_hp_ratio",
        ),
        opponent_hp_ratio=_shared_feature_value(
            features,
            "state.opponent_hp_ratio",
        ),
        player_status_id=_player_status_from_features(features),
        player_type_ids=_player_types_from_features(features),
        supported_candidate_indices=supported,
        prior_scores=tuple(float(scores[index]) for index in supported),
        hidden_embeddings=tuple(
            tuple(float(value) for value in hidden[index]) for index in supported
        ),
        claim_available=claim_available,
    )


def revalidate_battle_outcome_pressure_candidate(
    candidate: BattleOutcomePressureCandidate,
    features: BattleFeatureBatch,
    model: MaskedMLPMoveRanker,
    *,
    claim_available: bool,
) -> None:
    """Reproduce every serialized pressure fact from its bound source inputs."""

    if not isinstance(candidate, BattleOutcomePressureCandidate):
        raise TypeError("pressure revalidation requires a pressure candidate")
    observed = build_battle_outcome_pressure_candidate(
        candidate.binding,
        features,
        model,
        expected_prior_sha256=candidate.prior_model_sha256,
        claim_available=claim_available,
    )
    if observed != candidate:
        raise BattleOutcomeBatchError(
            "pressure candidate differs from rederived source facts"
        )


@dataclass(frozen=True, slots=True)
class BattleOutcomePressureInventory:
    """Complete path-free pressure census observed under one claim lease."""

    retained_prefix: RetainedBattleOutcomePrefix
    claim_snapshot: ClaimFirstAvailabilitySnapshot
    prefix: BattleOutcomePressureCandidate
    screened: tuple[BattleOutcomePressureCandidate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.retained_prefix, RetainedBattleOutcomePrefix):
            raise BattleOutcomeBatchError("pressure inventory prefix is invalid")
        if not isinstance(self.claim_snapshot, ClaimFirstAvailabilitySnapshot):
            raise BattleOutcomeBatchError(
                "pressure inventory claim snapshot is invalid"
            )
        if (
            not isinstance(self.prefix, BattleOutcomePressureCandidate)
            or self.prefix.binding != self.retained_prefix.train
            or self.prefix.claim_available
            or self.prefix.supported_candidate_indices
            != self.retained_prefix.train_supported_candidate_indices
        ):
            raise BattleOutcomeBatchError(
                "pressure inventory retained row differs"
            )
        if (
            not isinstance(self.screened, tuple)
            or not self.screened
            or any(
                not isinstance(item, BattleOutcomePressureCandidate)
                for item in self.screened
            )
        ):
            raise BattleOutcomeBatchError(
                "pressure inventory screened rows differ"
            )
        rows = (self.prefix, *self.screened)
        if any(
            item.prior_model_sha256 != self.retained_prefix.original_prior_sha256
            for item in rows
        ):
            raise BattleOutcomeBatchError(
                "pressure inventory differs from the original prior"
            )
        if len({item.capture_id for item in rows}) != len(rows):
            raise BattleOutcomeBatchError(
                "pressure inventory repeats a capture identity"
            )
        expected_pairs = {
            (
                self.retained_prefix.train.logical_root_sha256,
                self.retained_prefix.train.physical_root_sha256,
            ),
            (
                self.retained_prefix.forbidden_development.logical_root_sha256,
                self.retained_prefix.forbidden_development.physical_root_sha256,
            ),
            *(
                (item.binding.logical_root_sha256, item.binding.physical_root_sha256)
                for item in self.screened
            ),
        }
        observed_pairs = {
            (item.logical_root_sha256, item.physical_root_sha256)
            for item in self.claim_snapshot.observations
        }
        if observed_pairs != expected_pairs:
            raise BattleOutcomeBatchError(
                "pressure inventory claim denominator differs"
            )
        try:
            prefix_available = self.claim_snapshot.availability_for(
                self.prefix.binding.logical_root_sha256,
                self.prefix.binding.physical_root_sha256,
            )
            development_available = self.claim_snapshot.availability_for(
                self.retained_prefix.forbidden_development.logical_root_sha256,
                self.retained_prefix.forbidden_development.physical_root_sha256,
            )
            availability_matches = all(
                item.claim_available
                == self.claim_snapshot.availability_for(
                    item.binding.logical_root_sha256,
                    item.binding.physical_root_sha256,
                )
                for item in self.screened
            )
        except ClaimFirstAdmissionError:
            raise BattleOutcomeBatchError(
                "pressure inventory claim denominator differs"
            ) from None
        if prefix_available or development_available or not availability_matches:
            raise BattleOutcomeBatchError(
                "pressure inventory claim availability differs"
            )

    @property
    def inventory_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def screened_inventory_sha256(self) -> str:
        ordered = tuple(
            sorted(
                self.screened,
                key=lambda item: (item.partition.value, item.capture_id),
            )
        )
        return canonical_sha256(
            {
                "candidates": [item.public_dict() for item in ordered],
                "schema": BATTLE_OUTCOME_PRESSURE_INVENTORY_SCHEMA,
            }
        )

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": BATTLE_OUTCOME_PRESSURE_INVENTORY_SCHEMA,
            "status": "observed_unclaimed_not_reserved",
            "original_prior_sha256": self.retained_prefix.original_prior_sha256,
            "retained_prefix_sha256": self.retained_prefix.retained_prefix_sha256,
            "retained_prefix": self.retained_prefix.public_dict(),
            "claim_snapshot_sha256": self.claim_snapshot.snapshot_sha256,
            "claim_snapshot": self.claim_snapshot.public_dict(),
            "prefix": self.prefix.public_dict(),
            "screened": [item.public_dict() for item in self.screened],
            "screened_candidate_count": len(self.screened),
            "screened_inventory_sha256": self.screened_inventory_sha256,
            "prior_score_vector_evaluations": len(self.screened) + 1,
            "hidden_representation_evaluations": len(self.screened) + 1,
            "protections": {
                "authority_promoted": False,
                "controller_actions": 0,
                "crystal_contexts_opened": 0,
                "full_game_replays": 0,
                "model_choice_predictions": 0,
                "model_fits": 0,
                "outcomes_opened": 0,
                "root_claims_created": 0,
                "sealed_red_cases_opened": 0,
                "teacher_choice_targets": 0,
                "teacher_queries": 0,
            },
            "private_path_fields": 0,
        }


def build_battle_outcome_pressure_inventory(
    *,
    retained_prefix: RetainedBattleOutcomePrefix,
    claim_snapshot: ClaimFirstAvailabilitySnapshot,
    prefix: BattleOutcomePressureCandidate,
    screened: Sequence[BattleOutcomePressureCandidate],
) -> BattleOutcomePressureInventory:
    """Join every pressure row to one atomically observed claim snapshot."""

    if isinstance(screened, (str, bytes)) or not isinstance(screened, Sequence):
        raise TypeError("pressure inventory requires a screened sequence")
    ordered = tuple(
        sorted(
            screened,
            key=lambda item: (item.partition.value, item.capture_id),
        )
    )
    return BattleOutcomePressureInventory(
        retained_prefix=retained_prefix,
        claim_snapshot=claim_snapshot,
        prefix=prefix,
        screened=ordered,
    )


def parse_battle_outcome_pressure_inventory(
    payload: bytes,
) -> BattleOutcomePressureInventory:
    """Strictly reopen one complete path-free outcome-blind pressure census."""

    if not isinstance(payload, bytes):
        raise TypeError("battle outcome pressure inventory must be bytes")
    if not payload or len(payload) > _MAXIMUM_PRESSURE_INVENTORY_BYTES:
        raise BattleOutcomeBatchError("pressure inventory size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleOutcomeBatchError(
            "pressure inventory is not canonical JSON"
        ) from None
    fields = {
        "schema",
        "status",
        "original_prior_sha256",
        "retained_prefix_sha256",
        "retained_prefix",
        "claim_snapshot_sha256",
        "claim_snapshot",
        "prefix",
        "screened",
        "screened_candidate_count",
        "screened_inventory_sha256",
        "prior_score_vector_evaluations",
        "hidden_representation_evaluations",
        "protections",
        "private_path_fields",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema") != BATTLE_OUTCOME_PRESSURE_INVENTORY_SCHEMA
        or value.get("status") != "observed_unclaimed_not_reserved"
        or value.get("private_path_fields") != 0
        or not isinstance(value.get("screened"), list)
    ):
        raise BattleOutcomeBatchError("pressure inventory fields differ")
    try:
        snapshot = parse_claim_first_availability_snapshot(
            _canonical_payload(value.get("claim_snapshot"))
        )
    except (ClaimFirstAdmissionError, TypeError, ValueError):
        raise BattleOutcomeBatchError(
            "pressure inventory claim snapshot differs"
        ) from None
    inventory = BattleOutcomePressureInventory(
        retained_prefix=_parse_retained_prefix(value.get("retained_prefix")),
        claim_snapshot=snapshot,
        prefix=_parse_pressure_candidate(value.get("prefix")),
        screened=tuple(
            _parse_pressure_candidate(item) for item in value["screened"]
        ),
    )
    if inventory.canonical_bytes() != payload:
        raise BattleOutcomeBatchError(
            "pressure inventory is not canonical JSON"
        )
    return inventory


@dataclass(frozen=True, slots=True)
class BattleOutcomeBatchRoster:
    """Canonical selected denominator before any V2 outcome is opened."""

    roster_id: str
    retained_prefix: RetainedBattleOutcomePrefix
    claim_registry_sha256: str
    screened_inventory_sha256: str
    screened_candidate_count: int
    prefix: BattleOutcomePressureCandidate
    fresh_train: tuple[BattleOutcomePressureCandidate, ...]
    development: tuple[BattleOutcomePressureCandidate, ...]
    exclusion_counts: tuple[tuple[str, int], ...]
    required_hidden_contrast_rank: int
    selection_policy_sha256: str = battle_outcome_pressure_policy_sha256()
    fixed_heuristic_sha256: str = battle_outcome_fixed_heuristic_sha256()

    def __post_init__(self) -> None:
        _require_safe_id(self.roster_id, "batch roster identity")
        if not isinstance(self.retained_prefix, RetainedBattleOutcomePrefix):
            raise BattleOutcomeBatchError("batch retained prefix is invalid")
        for value, subject in (
            (self.claim_registry_sha256, "claim registry"),
            (self.screened_inventory_sha256, "screened inventory"),
            (self.selection_policy_sha256, "selection policy"),
            (self.fixed_heuristic_sha256, "fixed heuristic"),
        ):
            _require_sha256(value, subject)
        if self.selection_policy_sha256 != battle_outcome_pressure_policy_sha256():
            raise BattleOutcomeBatchError("batch selection policy differs")
        if self.fixed_heuristic_sha256 != battle_outcome_fixed_heuristic_sha256():
            raise BattleOutcomeBatchError("batch fixed heuristic differs")
        if (
            type(self.screened_candidate_count) is not int  # noqa: E721
            or self.screened_candidate_count < FRESH_TRAIN_CONTEXTS + DEVELOPMENT_CONTEXTS
        ):
            raise BattleOutcomeBatchError("batch screened denominator is too small")
        if (
            not isinstance(self.prefix, BattleOutcomePressureCandidate)
            or self.prefix.partition is not ScenarioPartition.TRAIN
            or self.prefix.claim_available
            or self.prefix.binding != self.retained_prefix.train
            or self.prefix.supported_candidate_indices
            != self.retained_prefix.train_supported_candidate_indices
        ):
            raise BattleOutcomeBatchError(
                "batch prefix must be one retained consumed train context"
            )
        if (
            not isinstance(self.fresh_train, tuple)
            or len(self.fresh_train) != FRESH_TRAIN_CONTEXTS
            or any(
                not isinstance(item, BattleOutcomePressureCandidate)
                or item.partition is not ScenarioPartition.TRAIN
                or not item.claim_available
                for item in self.fresh_train
            )
        ):
            raise BattleOutcomeBatchError("batch fresh train roster differs")
        if (
            not isinstance(self.development, tuple)
            or len(self.development) != DEVELOPMENT_CONTEXTS
            or any(
                not isinstance(item, BattleOutcomePressureCandidate)
                or item.partition is not ScenarioPartition.DEVELOPMENT
                or not item.claim_available
                for item in self.development
            )
        ):
            raise BattleOutcomeBatchError("batch development roster differs")
        selected = (self.prefix, *self.fresh_train, *self.development)
        if any(
            item.prior_model_sha256 != self.original_prior_sha256
            for item in selected
        ):
            raise BattleOutcomeBatchError(
                "batch pressure rows differ from the original prior"
            )
        widths = {item.hidden_width for item in selected}
        if len(widths) != 1:
            raise BattleOutcomeBatchError("batch hidden widths differ")
        width = next(iter(widths))
        if self.required_hidden_contrast_rank != width:
            raise BattleOutcomeBatchError(
                "batch hidden contrast rank must cover the output-head width"
            )
        for attribute, subject in (
            ("capture_id", "capture identity"),
            ("source_cluster_sha256", "source cluster"),
        ):
            values = tuple(getattr(item, attribute) for item in selected)
            if len(values) != len(set(values)):
                raise BattleOutcomeBatchError(f"batch repeats a {subject}")
        consumed = (self.prefix.binding, *self.forbidden_consumed)
        if _captures_overlap((*self.fresh_train, *self.development), consumed):
            raise BattleOutcomeBatchError("batch reuses a consumed V1 context")
        for attribute, subject in (
            ("root_lineage_id", "root lineage"),
            ("logical_root_sha256", "logical root"),
            ("physical_root_sha256", "physical root"),
            ("source_state_sha256", "source state"),
            ("initial_observation_sha256", "initial observation"),
        ):
            values = tuple(getattr(item.binding, attribute) for item in selected)
            if len(values) != len(set(values)):
                raise BattleOutcomeBatchError(f"batch repeats a {subject}")
        train = (self.prefix, *self.fresh_train)
        self._require_partition_pressure(train, subject="train")
        self._require_partition_pressure(self.development, subject="development")
        if _hidden_contrast_rank(train) < self.required_hidden_contrast_rank:
            raise BattleOutcomeBatchError("batch train hidden contrast rank is inadequate")
        if _hidden_contrast_rank(self.development) < self.required_hidden_contrast_rank:
            raise BattleOutcomeBatchError(
                "batch development hidden contrast rank is inadequate"
            )
        for candidates, subject in (
            (train, "train"),
            (self.development, "development"),
        ):
            if (
                _minimum_full_rank_singular_value(
                    candidates,
                    width=self.required_hidden_contrast_rank,
                )
                < _MINIMUM_FULL_RANK_SINGULAR_VALUE
            ):
                raise BattleOutcomeBatchError(
                    f"batch {subject} hidden contrast clearance is inadequate"
                )
        if (
            not isinstance(self.exclusion_counts, tuple)
            or tuple(sorted(self.exclusion_counts)) != self.exclusion_counts
            or len({reason for reason, _ in self.exclusion_counts})
            != len(self.exclusion_counts)
            or any(
                reason not in _EXCLUSION_REASONS
                or type(count) is not int  # noqa: E721
                or count < 1
                for reason, count in self.exclusion_counts
            )
        ):
            raise BattleOutcomeBatchError("batch exclusion accounting differs")
        expected_screened_count = (
            FRESH_TRAIN_CONTEXTS
            + DEVELOPMENT_CONTEXTS
            + sum(count for _, count in self.exclusion_counts)
        )
        if self.screened_candidate_count != expected_screened_count:
            raise BattleOutcomeBatchError("batch screened denominator does not reconcile")

    @property
    def original_prior_sha256(self) -> str:
        return self.retained_prefix.original_prior_sha256

    @property
    def forbidden_consumed(self) -> tuple[BattleOutcomeCaptureBinding, ...]:
        return (self.retained_prefix.forbidden_development,)

    @staticmethod
    def _require_partition_pressure(
        candidates: Sequence[BattleOutcomePressureCandidate],
        *,
        subject: str,
    ) -> None:
        if any(item.level_gap > MAXIMUM_LEVEL_GAP for item in candidates):
            raise BattleOutcomeBatchError(f"batch {subject} level gap exceeds policy")
        if len({item.venue_id for item in candidates}) < MINIMUM_DISTINCT_VENUES:
            raise BattleOutcomeBatchError(f"batch {subject} venue diversity is inadequate")
        if max(Counter(item.venue_id for item in candidates).values()) > (
            MAXIMUM_SINGLE_BUCKET_CONTEXTS
        ):
            raise BattleOutcomeBatchError(f"batch {subject} venue balance is inadequate")
        if (
            sum(item.binding.supported_candidate_count >= 3 for item in candidates)
            < MINIMUM_THREE_ACTION_CONTEXTS
        ):
            raise BattleOutcomeBatchError(
                f"batch {subject} three-action coverage is inadequate"
            )
        if (
            len({item.prior_margin_stratum for item in candidates})
            < MINIMUM_MARGIN_STRATA
        ):
            raise BattleOutcomeBatchError(
                f"batch {subject} prior-margin diversity is inadequate"
            )
        if max(
            Counter(item.prior_margin_stratum for item in candidates).values()
        ) > MAXIMUM_SINGLE_BUCKET_CONTEXTS:
            raise BattleOutcomeBatchError(
                f"batch {subject} prior-margin balance is inadequate"
            )
        if (
            len({item.party_condition_id for item in candidates})
            < MINIMUM_PARTY_CONDITIONS
        ):
            raise BattleOutcomeBatchError(
                f"batch {subject} party-condition diversity is inadequate"
            )
        if max(
            Counter(item.party_condition_id for item in candidates).values()
        ) > MAXIMUM_SINGLE_BUCKET_CONTEXTS:
            raise BattleOutcomeBatchError(
                f"batch {subject} party-condition balance is inadequate"
            )

    @property
    def roster_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def train_hidden_contrast_rank(self) -> int:
        return _hidden_contrast_rank((self.prefix, *self.fresh_train))

    @property
    def development_hidden_contrast_rank(self) -> int:
        return _hidden_contrast_rank(self.development)

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        train = (self.prefix, *self.fresh_train)
        return {
            "schema": BATTLE_OUTCOME_BATCH_ROSTER_SCHEMA,
            "status": "prospective_unexecuted",
            "roster_id": self.roster_id,
            "original_prior_sha256": self.original_prior_sha256,
            "retained_prefix_sha256": (
                self.retained_prefix.retained_prefix_sha256
            ),
            "retained_prefix": self.retained_prefix.public_dict(),
            "claim_registry_sha256": self.claim_registry_sha256,
            "screened_inventory_sha256": self.screened_inventory_sha256,
            "screened_candidate_count": self.screened_candidate_count,
            "selection_policy_sha256": self.selection_policy_sha256,
            "fixed_heuristic_id": BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
            "fixed_heuristic_sha256": self.fixed_heuristic_sha256,
            "required_hidden_contrast_rank": self.required_hidden_contrast_rank,
            "prefix": self.prefix.public_dict(),
            "fresh_train": [item.public_dict() for item in self.fresh_train],
            "development": [item.public_dict() for item in self.development],
            "exclusion_counts": {
                reason: count for reason, count in self.exclusion_counts
            },
            "pressure_summary": {
                "train_contexts": len(train),
                "fresh_train_contexts": len(self.fresh_train),
                "development_contexts": len(self.development),
                "train_distinct_venues": len({item.venue_id for item in train}),
                "development_distinct_venues": len(
                    {item.venue_id for item in self.development}
                ),
                "train_three_action_contexts": sum(
                    item.binding.supported_candidate_count >= 3 for item in train
                ),
                "development_three_action_contexts": sum(
                    item.binding.supported_candidate_count >= 3
                    for item in self.development
                ),
                "train_prior_margin_strata": len(
                    {item.prior_margin_stratum for item in train}
                ),
                "development_prior_margin_strata": len(
                    {item.prior_margin_stratum for item in self.development}
                ),
                "train_party_conditions": len(
                    {item.party_condition_id for item in train}
                ),
                "development_party_conditions": len(
                    {item.party_condition_id for item in self.development}
                ),
                "train_hidden_contrast_rank": self.train_hidden_contrast_rank,
                "development_hidden_contrast_rank": (
                    self.development_hidden_contrast_rank
                ),
            },
            "protections": {
                "authority_promoted": False,
                "crystal_contexts_opened": 0,
                "development_reused": False,
                "development_outcomes_opened": 0,
                "full_game_replays": 0,
                "inferential_claim": False,
                "model_fits": 0,
                "outcomes_opened": 0,
                "preferred_action_fields": 0,
                "replacement_slots": 0,
                "retained_prefix_reexecuted": False,
                "red_sealed_test_cases_opened": 0,
                "teacher_choice_fields": 0,
            },
            "private_path_fields": 0,
        }


def select_battle_outcome_batch_roster(
    *,
    roster_id: str,
    retained_prefix: RetainedBattleOutcomePrefix,
    claim_registry_sha256: str,
    prefix: BattleOutcomePressureCandidate,
    screened: Sequence[BattleOutcomePressureCandidate],
) -> BattleOutcomeBatchRoster:
    """Select the fixed V2 denominator from outcome-blind screened candidates."""

    if not isinstance(screened, Sequence) or isinstance(screened, (str, bytes)):
        raise TypeError("screened pressure candidates must be a sequence")
    candidates = tuple(screened)
    if any(not isinstance(item, BattleOutcomePressureCandidate) for item in candidates):
        raise TypeError("screened pressure candidates contain an invalid item")
    if not isinstance(retained_prefix, RetainedBattleOutcomePrefix):
        raise TypeError("batch selection requires the verified retained prefix")
    original_prior_sha256 = retained_prefix.original_prior_sha256
    consumed = (retained_prefix.forbidden_development,)
    if prefix.binding != retained_prefix.train:
        raise BattleOutcomeBatchError("pressure prefix differs from retained V1 train")
    if prefix.prior_model_sha256 != original_prior_sha256 or any(
        item.prior_model_sha256 != original_prior_sha256 for item in candidates
    ):
        raise BattleOutcomeBatchError(
            "screened pressure rows differ from the original prior"
        )
    if any(item.hidden_width != prefix.hidden_width for item in candidates):
        raise BattleOutcomeBatchError("screened pressure hidden widths differ")
    ordered = tuple(sorted(candidates, key=lambda item: (item.partition.value, item.capture_id)))
    inventory_sha256 = canonical_sha256(
        {
            "candidates": [item.public_dict() for item in ordered],
            "schema": "pokemon-red-battle-outcome-pressure-inventory-v2",
        }
    )
    exclusions: Counter[str] = Counter()
    eligible: list[BattleOutcomePressureCandidate] = []
    already_consumed = (prefix.binding, *consumed)
    for item in ordered:
        if _candidate_overlaps_bindings(item, already_consumed):
            exclusions["previously_consumed"] += 1
            continue
        if not item.claim_available:
            exclusions["claim_unavailable"] += 1
            continue
        if item.level_gap > MAXIMUM_LEVEL_GAP:
            exclusions["level_gap_exceeded"] += 1
            continue
        eligible.append(item)
    train_pool = tuple(
        item for item in eligible if item.partition is ScenarioPartition.TRAIN
    )
    development_pool = tuple(
        item for item in eligible if item.partition is ScenarioPartition.DEVELOPMENT
    )
    fresh_train = _select_pressure_partition(
        train_pool,
        count=FRESH_TRAIN_CONTEXTS,
        initial=(prefix,),
        forbidden=consumed,
        subject="train",
    )
    development = _select_pressure_partition(
        development_pool,
        count=DEVELOPMENT_CONTEXTS,
        initial=(),
        forbidden=(prefix.binding, *consumed, *(item.binding for item in fresh_train)),
        subject="development",
    )
    selected_ids = {item.capture_id for item in (*fresh_train, *development)}
    exclusions["not_selected_by_pressure"] += sum(
        item.capture_id not in selected_ids for item in eligible
    )
    return BattleOutcomeBatchRoster(
        roster_id=roster_id,
        retained_prefix=retained_prefix,
        claim_registry_sha256=claim_registry_sha256,
        screened_inventory_sha256=inventory_sha256,
        screened_candidate_count=len(ordered),
        prefix=prefix,
        fresh_train=fresh_train,
        development=development,
        exclusion_counts=tuple(
            sorted((reason, count) for reason, count in exclusions.items() if count)
        ),
        required_hidden_contrast_rank=prefix.hidden_width,
    )


def select_battle_outcome_batch_roster_from_inventory(
    *,
    roster_id: str,
    inventory: BattleOutcomePressureInventory,
) -> BattleOutcomeBatchRoster:
    """Select only from one canonical atomic claim-snapshot inventory."""

    if not isinstance(inventory, BattleOutcomePressureInventory):
        raise TypeError("batch selection requires a pressure inventory")
    roster = select_battle_outcome_batch_roster(
        roster_id=roster_id,
        retained_prefix=inventory.retained_prefix,
        claim_registry_sha256=inventory.claim_snapshot.registry_state_sha256,
        prefix=inventory.prefix,
        screened=inventory.screened,
    )
    if roster.screened_inventory_sha256 != inventory.screened_inventory_sha256:
        raise BattleOutcomeBatchError(
            "batch roster differs from its atomic pressure inventory"
        )
    return roster


def parse_battle_outcome_batch_roster(payload: bytes) -> BattleOutcomeBatchRoster:
    """Strictly reopen one canonical outcome-blind V2 roster."""

    if not isinstance(payload, bytes):
        raise TypeError("battle outcome batch roster must be bytes")
    if not payload or len(payload) > _MAXIMUM_ROSTER_BYTES:
        raise BattleOutcomeBatchError("batch roster size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleOutcomeBatchError("batch roster is not canonical JSON") from None
    fields = {
        "schema",
        "status",
        "roster_id",
        "original_prior_sha256",
        "retained_prefix_sha256",
        "retained_prefix",
        "claim_registry_sha256",
        "screened_inventory_sha256",
        "screened_candidate_count",
        "selection_policy_sha256",
        "fixed_heuristic_id",
        "fixed_heuristic_sha256",
        "required_hidden_contrast_rank",
        "prefix",
        "fresh_train",
        "development",
        "exclusion_counts",
        "pressure_summary",
        "protections",
        "private_path_fields",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema") != BATTLE_OUTCOME_BATCH_ROSTER_SCHEMA
        or value.get("status") != "prospective_unexecuted"
        or value.get("fixed_heuristic_id") != BATTLE_OUTCOME_FIXED_HEURISTIC_ID
        or value.get("private_path_fields") != 0
    ):
        raise BattleOutcomeBatchError("batch roster fields differ")
    raw_train = value.get("fresh_train")
    raw_development = value.get("development")
    raw_exclusions = value.get("exclusion_counts")
    if (
        not isinstance(raw_train, list)
        or not isinstance(raw_development, list)
        or not isinstance(raw_exclusions, dict)
        or any(not isinstance(key, str) for key in raw_exclusions)
    ):
        raise BattleOutcomeBatchError("batch roster collections differ")
    roster = BattleOutcomeBatchRoster(
        roster_id=_string(value.get("roster_id"), "roster identity"),
        retained_prefix=_parse_retained_prefix(value.get("retained_prefix")),
        claim_registry_sha256=_string(
            value.get("claim_registry_sha256"), "claim registry"
        ),
        screened_inventory_sha256=_string(
            value.get("screened_inventory_sha256"), "screened inventory"
        ),
        screened_candidate_count=_integer(
            value.get("screened_candidate_count"), "screened candidate count"
        ),
        prefix=_parse_pressure_candidate(value.get("prefix")),
        fresh_train=tuple(_parse_pressure_candidate(item) for item in raw_train),
        development=tuple(
            _parse_pressure_candidate(item) for item in raw_development
        ),
        exclusion_counts=tuple(
            sorted(
                (
                    key,
                    _integer(raw_exclusions[key], f"{key} exclusion count"),
                )
                for key in raw_exclusions
            )
        ),
        required_hidden_contrast_rank=_integer(
            value.get("required_hidden_contrast_rank"),
            "required hidden contrast rank",
        ),
        selection_policy_sha256=_string(
            value.get("selection_policy_sha256"), "selection policy"
        ),
        fixed_heuristic_sha256=_string(
            value.get("fixed_heuristic_sha256"), "fixed heuristic"
        ),
    )
    if (
        _string(value.get("original_prior_sha256"), "original prior")
        != roster.original_prior_sha256
        or _string(value.get("retained_prefix_sha256"), "retained prefix")
        != roster.retained_prefix.retained_prefix_sha256
    ):
        raise BattleOutcomeBatchError("batch retained prefix identity differs")
    if roster.canonical_bytes() != payload:
        raise BattleOutcomeBatchError("batch roster is not canonical JSON")
    return roster


@dataclass(frozen=True, slots=True)
class BattleOutcomeBatchFreeze:
    """One durably publishable atomic inventory plus its selected roster."""

    inventory: BattleOutcomePressureInventory
    roster: BattleOutcomeBatchRoster

    def __post_init__(self) -> None:
        if not isinstance(self.inventory, BattleOutcomePressureInventory):
            raise BattleOutcomeBatchError("batch freeze inventory is invalid")
        if not isinstance(self.roster, BattleOutcomeBatchRoster):
            raise BattleOutcomeBatchError("batch freeze roster is invalid")
        expected = select_battle_outcome_batch_roster_from_inventory(
            roster_id=self.roster.roster_id,
            inventory=self.inventory,
        )
        if expected != self.roster:
            raise BattleOutcomeBatchError(
                "batch freeze roster differs from its atomic inventory"
            )

    @property
    def freeze_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": BATTLE_OUTCOME_BATCH_FREEZE_SCHEMA,
            "status": "prospective_unexecuted",
            "inventory_sha256": self.inventory.inventory_sha256,
            "roster_sha256": self.roster.roster_sha256,
            "inventory": self.inventory.public_dict(),
            "roster": self.roster.public_dict(),
            "protections": {
                "authority_promoted": False,
                "controller_actions": 0,
                "crystal_contexts_opened": 0,
                "full_game_replays": 0,
                "model_choice_predictions": 0,
                "model_fits": 0,
                "outcomes_opened": 0,
                "root_claims_created": 0,
                "sealed_red_cases_opened": 0,
                "teacher_choice_targets": 0,
                "teacher_queries": 0,
            },
            "private_path_fields": 0,
        }


def build_battle_outcome_batch_freeze(
    *,
    roster_id: str,
    inventory: BattleOutcomePressureInventory,
) -> BattleOutcomeBatchFreeze:
    """Build the single file published while the shared claim lease is held."""

    return BattleOutcomeBatchFreeze(
        inventory=inventory,
        roster=select_battle_outcome_batch_roster_from_inventory(
            roster_id=roster_id,
            inventory=inventory,
        ),
    )


def parse_battle_outcome_batch_freeze(
    payload: bytes,
) -> BattleOutcomeBatchFreeze:
    """Strictly reopen one canonical inventory-and-roster freeze."""

    if not isinstance(payload, bytes):
        raise TypeError("battle outcome batch freeze must be bytes")
    if not payload or len(payload) > _MAXIMUM_FREEZE_BYTES:
        raise BattleOutcomeBatchError("batch freeze size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleOutcomeBatchError(
            "batch freeze is not canonical JSON"
        ) from None
    fields = {
        "schema",
        "status",
        "inventory_sha256",
        "roster_sha256",
        "inventory",
        "roster",
        "protections",
        "private_path_fields",
    }
    protections = {
        "authority_promoted": False,
        "controller_actions": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "model_choice_predictions": 0,
        "model_fits": 0,
        "outcomes_opened": 0,
        "root_claims_created": 0,
        "sealed_red_cases_opened": 0,
        "teacher_choice_targets": 0,
        "teacher_queries": 0,
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema") != BATTLE_OUTCOME_BATCH_FREEZE_SCHEMA
        or value.get("status") != "prospective_unexecuted"
        or value.get("protections") != protections
        or value.get("private_path_fields") != 0
    ):
        raise BattleOutcomeBatchError("batch freeze fields differ")
    inventory = parse_battle_outcome_pressure_inventory(
        _canonical_payload(value.get("inventory"))
    )
    roster = parse_battle_outcome_batch_roster(
        _canonical_payload(value.get("roster"))
    )
    freeze = BattleOutcomeBatchFreeze(inventory=inventory, roster=roster)
    if (
        value.get("inventory_sha256") != inventory.inventory_sha256
        or value.get("roster_sha256") != roster.roster_sha256
        or freeze.canonical_bytes() != payload
    ):
        raise BattleOutcomeBatchError("batch freeze is not canonical JSON")
    return freeze


def _select_pressure_partition(
    pool: Sequence[BattleOutcomePressureCandidate],
    *,
    count: int,
    initial: Sequence[BattleOutcomePressureCandidate],
    forbidden: Sequence[BattleOutcomeCaptureBinding],
    subject: str,
) -> tuple[BattleOutcomePressureCandidate, ...]:
    if len(pool) < count:
        raise BattleOutcomeBatchError(f"batch {subject} capacity is inadequate")
    selected = list(initial)
    remaining = list(pool)
    while len(selected) < len(initial) + count:
        venues = {item.venue_id for item in selected}
        strata = {item.prior_margin_stratum for item in selected}
        party_conditions = {item.party_condition_id for item in selected}
        blocked = (*forbidden, *(item.binding for item in selected))
        feasible = [
            item
            for item in remaining
            if not _candidate_overlaps_bindings(item, blocked)
        ]
        if not feasible:
            fallback, search_complete = _find_independent_pressure_subset(
                pool=pool,
                count=count,
                initial=tuple(initial),
                forbidden=tuple(forbidden),
            )
            if fallback is None:
                if search_complete:
                    raise BattleOutcomeBatchError(
                        f"batch {subject} independent capacity is inadequate"
                    )
                raise BattleOutcomeBatchError(
                    f"batch {subject} constrained selector failed without a "
                    "capacity claim: independent-subset search limit reached"
                )
            selected = [*initial, *fallback]
            fallback_ids = {item.capture_id for item in fallback}
            remaining = [
                item for item in pool if item.capture_id not in fallback_ids
            ]
            break

        def key(
            item: BattleOutcomePressureCandidate,
            *,
            current_selected: tuple[BattleOutcomePressureCandidate, ...] = tuple(
                selected
            ),
            current_venues: frozenset[str] = frozenset(venues),
            current_strata: frozenset[int] = frozenset(strata),
            current_party_conditions: frozenset[str] = frozenset(
                party_conditions
            ),
        ) -> tuple[object, ...]:
            proposed = (*current_selected, item)
            return (
                -_hidden_contrast_rank(proposed),
                -int(item.venue_id not in current_venues),
                -int(item.prior_margin_stratum not in current_strata),
                -int(item.party_condition_id not in current_party_conditions),
                -int(item.binding.supported_candidate_count >= 3),
                item.level_gap,
                item.prior_top_two_margin,
                -_hidden_contrast_logdet(proposed),
                item.capture_id,
            )

        chosen = min(feasible, key=key)
        selected.append(chosen)
        remaining.remove(chosen)
    fresh = tuple(selected[len(initial) :])
    complete = (*initial, *fresh)
    if _partition_selection_is_qualified(
        complete,
        required_rank=complete[0].hidden_width,
    ):
        return tuple(sorted(fresh, key=lambda item: item.capture_id))
    repaired = _repair_pressure_partition_selection(
        initial=tuple(initial),
        selected=fresh,
        unselected=tuple(remaining),
        forbidden=tuple(forbidden),
    )
    if repaired is None:
        failure_reason = _partition_selection_failure_reason(
            complete,
            required_rank=complete[0].hidden_width,
        )
        raise BattleOutcomeBatchError(
            f"batch {subject} constrained selector failed without a capacity claim: "
            f"{failure_reason}"
        )
    return repaired


def _find_independent_pressure_subset(
    *,
    pool: Sequence[BattleOutcomePressureCandidate],
    count: int,
    initial: tuple[BattleOutcomePressureCandidate, ...],
    forbidden: tuple[BattleOutcomeCaptureBinding, ...],
) -> tuple[tuple[BattleOutcomePressureCandidate, ...] | None, bool]:
    """Find one independent subset, or distinguish exhaustion from search limits."""

    ordered = tuple(sorted(pool, key=lambda item: item.capture_id))
    nodes = 0
    search_limit_reached = False

    def search(
        start: int,
        chosen: tuple[BattleOutcomePressureCandidate, ...],
    ) -> tuple[BattleOutcomePressureCandidate, ...] | None:
        nonlocal nodes, search_limit_reached
        nodes += 1
        if nodes > _MAXIMUM_INDEPENDENCE_SEARCH_NODES:
            search_limit_reached = True
            return None
        if len(chosen) == count:
            return chosen
        needed = count - len(chosen)
        if len(ordered) - start < needed:
            return None
        blocked = (
            *forbidden,
            *(item.binding for item in initial),
            *(item.binding for item in chosen),
        )
        last_start = len(ordered) - needed
        for index in range(start, last_start + 1):
            item = ordered[index]
            if _candidate_overlaps_bindings(item, blocked):
                continue
            observed = search(index + 1, (*chosen, item))
            if observed is not None:
                return observed
            if search_limit_reached:
                return None
        return None

    result = search(0, ())
    return result, not search_limit_reached


def _repair_pressure_partition_selection(
    *,
    initial: tuple[BattleOutcomePressureCandidate, ...],
    selected: tuple[BattleOutcomePressureCandidate, ...],
    unselected: tuple[BattleOutcomePressureCandidate, ...],
    forbidden: tuple[BattleOutcomeCaptureBinding, ...],
) -> tuple[BattleOutcomePressureCandidate, ...] | None:
    required_rank = (*initial, *selected)[0].hidden_width
    valid: list[tuple[BattleOutcomePressureCandidate, ...]] = []
    for swap_count in (1, 2):
        if len(selected) < swap_count or len(unselected) < swap_count:
            continue
        for removed_indices in combinations(range(len(selected)), swap_count):
            retained = tuple(
                item
                for index, item in enumerate(selected)
                if index not in removed_indices
            )
            for replacements in combinations(unselected, swap_count):
                proposed = tuple(
                    sorted((*retained, *replacements), key=lambda item: item.capture_id)
                )
                complete = (*initial, *proposed)
                if not _pressure_candidates_are_independent(complete, forbidden):
                    continue
                if _partition_selection_is_qualified(
                    complete,
                    required_rank=required_rank,
                ):
                    valid.append(proposed)
        if valid:
            return min(
                valid,
                key=lambda items: _qualified_partition_key((*initial, *items)),
            )
    return None


def _pressure_candidates_are_independent(
    candidates: Sequence[BattleOutcomePressureCandidate],
    forbidden: Sequence[BattleOutcomeCaptureBinding],
) -> bool:
    selected_bindings = list(forbidden)
    for candidate in candidates:
        if _candidate_overlaps_bindings(candidate, selected_bindings):
            return False
        selected_bindings.append(candidate.binding)
    return True


def _partition_selection_is_qualified(
    candidates: Sequence[BattleOutcomePressureCandidate],
    *,
    required_rank: int,
) -> bool:
    try:
        BattleOutcomeBatchRoster._require_partition_pressure(
            candidates,
            subject="candidate",
        )
        return (
            _hidden_contrast_rank(candidates) >= required_rank
            and _minimum_full_rank_singular_value(
                candidates,
                width=required_rank,
            )
            >= _MINIMUM_FULL_RANK_SINGULAR_VALUE
        )
    except BattleOutcomeBatchError:
        return False


def _partition_selection_failure_reason(
    candidates: Sequence[BattleOutcomePressureCandidate],
    *,
    required_rank: int,
) -> str:
    try:
        BattleOutcomeBatchRoster._require_partition_pressure(
            candidates,
            subject="candidate",
        )
    except BattleOutcomeBatchError as error:
        return str(error)
    if _hidden_contrast_rank(candidates) < required_rank:
        return "hidden contrast rank is inadequate"
    if (
        _minimum_full_rank_singular_value(candidates, width=required_rank)
        < _MINIMUM_FULL_RANK_SINGULAR_VALUE
    ):
        return "hidden contrast clearance is inadequate"
    return "no one- or two-swap qualified subset was found"


def _qualified_partition_key(
    candidates: Sequence[BattleOutcomePressureCandidate],
) -> tuple[object, ...]:
    venue_counts = Counter(item.venue_id for item in candidates)
    margin_counts = Counter(item.prior_margin_stratum for item in candidates)
    party_counts = Counter(item.party_condition_id for item in candidates)
    return (
        -_hidden_contrast_rank(candidates),
        -_minimum_full_rank_singular_value(
            candidates,
            width=candidates[0].hidden_width,
        ),
        -_hidden_contrast_logdet(candidates),
        max(venue_counts.values()),
        max(margin_counts.values()),
        max(party_counts.values()),
        sum(item.level_gap for item in candidates),
        sum(item.prior_top_two_margin for item in candidates),
        tuple(item.capture_id for item in candidates),
    )


def _hidden_contrast_matrix(
    candidates: Sequence[BattleOutcomePressureCandidate],
) -> NDArray[np.float64]:
    rows = tuple(vector for item in candidates for vector in item.contrast_vectors)
    if not rows:
        raise BattleOutcomeBatchError("pressure roster has no hidden contrasts")
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2 or not np.all(np.isfinite(matrix)):
        raise BattleOutcomeBatchError("pressure hidden contrast matrix is invalid")
    return matrix


def _hidden_contrast_rank(
    candidates: Sequence[BattleOutcomePressureCandidate],
) -> int:
    try:
        return int(
            np.linalg.matrix_rank(
                _hidden_contrast_matrix(candidates),
                tol=_HIDDEN_RANK_TOLERANCE,
            )
        )
    except np.linalg.LinAlgError:
        raise BattleOutcomeBatchError(
            "pressure hidden contrast rank is not computable"
        ) from None


def _minimum_full_rank_singular_value(
    candidates: Sequence[BattleOutcomePressureCandidate],
    *,
    width: int,
) -> float:
    try:
        singular_values = np.linalg.svd(
            _hidden_contrast_matrix(candidates),
            compute_uv=False,
        )
    except np.linalg.LinAlgError:
        raise BattleOutcomeBatchError(
            "pressure hidden singular values are not computable"
        ) from None
    if len(singular_values) < width:
        return 0.0
    observed = float(singular_values[width - 1])
    if not math.isfinite(observed):
        raise BattleOutcomeBatchError("pressure hidden singular value is invalid")
    return observed


def _hidden_contrast_logdet(
    candidates: Sequence[BattleOutcomePressureCandidate],
) -> float:
    matrix = _hidden_contrast_matrix(candidates)
    gram = matrix.T @ matrix
    try:
        sign, value = np.linalg.slogdet(
            _LOGDET_REGULARIZER * np.eye(gram.shape[0], dtype=np.float64)
            + gram
        )
    except np.linalg.LinAlgError:
        raise BattleOutcomeBatchError(
            "pressure hidden contrast logdet is not computable"
        ) from None
    if sign <= 0 or not math.isfinite(float(value)):
        raise BattleOutcomeBatchError("pressure hidden contrast logdet is invalid")
    return float(value)


def _level_from_features(features: BattleFeatureBatch, name: str) -> int:
    try:
        index = features.feature_names.index(name)
    except ValueError:
        raise BattleOutcomeBatchError("pressure level feature is absent") from None
    values = {float(row[index]) for row in features.candidate_vectors}
    if len(values) != 1:
        raise BattleOutcomeBatchError("pressure level differs across candidates")
    raw = next(iter(values)) * 100.0
    rounded = round(raw)
    if not math.isclose(raw, rounded, abs_tol=1e-9) or not 1 <= rounded <= 100:
        raise BattleOutcomeBatchError("pressure level feature is invalid")
    return int(rounded)


def _shared_feature_value(features: BattleFeatureBatch, name: str) -> float:
    try:
        index = features.feature_names.index(name)
    except ValueError:
        raise BattleOutcomeBatchError(
            f"pressure shared feature {name} is absent"
        ) from None
    values = tuple(float(row[index]) for row in features.candidate_vectors)
    observed = values[0]
    if any(
        not math.isclose(value, observed, rel_tol=0.0, abs_tol=1e-12)
        for value in values[1:]
    ):
        raise BattleOutcomeBatchError(
            f"pressure shared feature {name} differs across candidates"
        )
    return observed


def _player_status_from_features(features: BattleFeatureBatch) -> str:
    status_values = tuple(
        (
            status,
            _shared_feature_value(features, f"state.player_status.{status}"),
        )
        for status in STATUS_CATEGORIES
    )
    active = tuple(
        status
        for status, value in status_values
        if math.isclose(value, 1.0, rel_tol=0.0, abs_tol=1e-12)
    )
    if len(active) != 1 or any(
        not math.isclose(
            value,
            1.0 if status == active[0] else 0.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for status, value in status_values
    ):
        raise BattleOutcomeBatchError("pressure player status encoding is invalid")
    return active[0]


def _player_types_from_features(features: BattleFeatureBatch) -> tuple[str, ...]:
    type_values = tuple(
        (
            type_id,
            _shared_feature_value(features, f"state.player_type.{type_id}"),
        )
        for type_id in POKEMON_TYPES
    )
    active = tuple(
        type_id
        for type_id, value in type_values
        if math.isclose(value, 1.0, rel_tol=0.0, abs_tol=1e-12)
    )
    if not 1 <= len(active) <= 2 or any(
        not math.isclose(
            value,
            1.0 if type_id in active else 0.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for type_id, value in type_values
    ):
        raise BattleOutcomeBatchError("pressure player type encoding is invalid")
    return active


_BINDING_IDENTITY_ATTRIBUTES = (
    "capture_id",
    "root_lineage_id",
    "logical_root_sha256",
    "physical_root_sha256",
    "source_state_sha256",
    "initial_observation_sha256",
)


def _bindings_overlap(
    first: BattleOutcomeCaptureBinding,
    second: BattleOutcomeCaptureBinding,
) -> bool:
    return any(
        getattr(first, attribute) == getattr(second, attribute)
        for attribute in _BINDING_IDENTITY_ATTRIBUTES
    ) or battle_outcome_source_cluster_sha256(
        first
    ) == battle_outcome_source_cluster_sha256(second)


def _candidate_overlaps_bindings(
    candidate: BattleOutcomePressureCandidate,
    bindings: Sequence[BattleOutcomeCaptureBinding],
) -> bool:
    return any(
        any(
            getattr(candidate.binding, attribute) == getattr(binding, attribute)
            for attribute in _BINDING_IDENTITY_ATTRIBUTES
        )
        or candidate.source_cluster_sha256
        == battle_outcome_source_cluster_sha256(binding)
        for binding in bindings
    )


def _captures_overlap(
    candidates: Sequence[BattleOutcomePressureCandidate],
    bindings: Sequence[BattleOutcomeCaptureBinding],
) -> bool:
    return any(
        _candidate_overlaps_bindings(candidate, bindings)
        for candidate in candidates
    )


def _parse_pressure_candidate(value: object) -> BattleOutcomePressureCandidate:
    fields = {
        "schema",
        "binding",
        "prior_model_sha256",
        "venue_id",
        "source_cluster_sha256",
        "claim_identity_sha256",
        "player_level",
        "opponent_level",
        "player_hp_ratio",
        "opponent_hp_ratio",
        "player_status_id",
        "player_type_ids",
        "party_condition_id",
        "supported_candidate_indices",
        "prior_scores",
        "hidden_embeddings",
        "claim_available",
        "level_gap",
        "prior_top_two_margin",
        "prior_margin_stratum",
        "outcome_fields",
        "teacher_choice_fields",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema") != BATTLE_OUTCOME_PRESSURE_CANDIDATE_SCHEMA
        or value.get("outcome_fields") != 0
        or value.get("teacher_choice_fields") != 0
    ):
        raise BattleOutcomeBatchError("pressure candidate fields differ")
    raw_indices = value.get("supported_candidate_indices")
    raw_scores = value.get("prior_scores")
    raw_embeddings = value.get("hidden_embeddings")
    raw_player_types = value.get("player_type_ids")
    if (
        not isinstance(raw_indices, list)
        or not isinstance(raw_scores, list)
        or not isinstance(raw_embeddings, list)
        or not isinstance(raw_player_types, list)
        or any(not isinstance(row, list) for row in raw_embeddings)
    ):
        raise BattleOutcomeBatchError("pressure candidate arrays differ")
    try:
        binding = parse_battle_outcome_capture_binding(value.get("binding"))
    except BattleOutcomeExperimentError:
        raise BattleOutcomeBatchError("pressure capture binding differs") from None
    candidate = BattleOutcomePressureCandidate(
        binding=binding,
        prior_model_sha256=_string(
            value.get("prior_model_sha256"), "pressure prior model"
        ),
        source_cluster_sha256=_string(
            value.get("source_cluster_sha256"), "source cluster"
        ),
        player_level=_integer(value.get("player_level"), "player level"),
        opponent_level=_integer(value.get("opponent_level"), "opponent level"),
        player_hp_ratio=_number(value.get("player_hp_ratio"), "player HP ratio"),
        opponent_hp_ratio=_number(
            value.get("opponent_hp_ratio"), "opponent HP ratio"
        ),
        player_status_id=_string(
            value.get("player_status_id"), "player status"
        ),
        player_type_ids=tuple(
            _string(item, "player type") for item in raw_player_types
        ),
        supported_candidate_indices=tuple(
            _integer(item, "supported candidate index") for item in raw_indices
        ),
        prior_scores=tuple(_number(item, "prior score") for item in raw_scores),
        hidden_embeddings=tuple(
            tuple(_number(item, "hidden embedding") for item in row)
            for row in raw_embeddings
        ),
        claim_available=_boolean(value.get("claim_available"), "claim availability"),
    )
    if (
        _string(value.get("venue_id"), "pressure venue") != candidate.venue_id
        or _string(value.get("claim_identity_sha256"), "claim identity")
        != candidate.claim_identity_sha256
        or _string(value.get("party_condition_id"), "party condition")
        != candidate.party_condition_id
        or not math.isclose(
            _number(value.get("level_gap"), "level gap"),
            candidate.level_gap,
            abs_tol=0.0,
        )
        or not math.isclose(
            _number(value.get("prior_top_two_margin"), "prior margin"),
            candidate.prior_top_two_margin,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        or _integer(value.get("prior_margin_stratum"), "prior margin stratum")
        != candidate.prior_margin_stratum
    ):
        raise BattleOutcomeBatchError("pressure candidate derived fields differ")
    return candidate


def _parse_retained_prefix(value: object) -> RetainedBattleOutcomePrefix:
    fields = {
        "schema",
        "status",
        "plan_sha256",
        "plan",
        "artifact_manifest_sha256",
        "original_prior_sha256",
        "train_record_sha256",
        "train_supported_candidate_indices",
        "protections",
        "private_path_fields",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema")
        != "pokemon-red-battle-outcome-retained-prefix-v1"
        or value.get("status") != "verified_no_replay"
        or value.get("private_path_fields") != 0
    ):
        raise BattleOutcomeBatchError("retained prefix fields differ")
    raw_indices = value.get("train_supported_candidate_indices")
    if not isinstance(raw_indices, list):
        raise BattleOutcomeBatchError("retained prefix candidate indices differ")
    retained = RetainedBattleOutcomePrefix(
        plan=_parse_retained_plan(value.get("plan")),
        artifact_manifest_sha256=_string(
            value.get("artifact_manifest_sha256"),
            "retained artifact manifest",
        ),
        train_record_sha256=_string(
            value.get("train_record_sha256"),
            "retained train record",
        ),
        train_supported_candidate_indices=tuple(
            _integer(item, "retained train candidate index")
            for item in raw_indices
        ),
    )
    if (
        _string(value.get("plan_sha256"), "retained plan")
        != retained.plan_sha256
        or _string(value.get("original_prior_sha256"), "retained original prior")
        != retained.original_prior_sha256
        or retained.public_dict() != value
    ):
        raise BattleOutcomeBatchError("retained prefix protections differ")
    return retained


def _parse_retained_plan(value: object) -> BattleOutcomeExperimentPlan:
    try:
        return parse_battle_outcome_experiment_plan(_canonical_payload(value))
    except (TypeError, ValueError):
        raise BattleOutcomeBatchError("retained V1 plan differs") from None


def _parse_consumed_capture(value: object) -> BattleOutcomeCaptureBinding:
    try:
        return parse_battle_outcome_capture_binding(value)
    except BattleOutcomeExperimentError:
        raise BattleOutcomeBatchError("consumed capture binding differs") from None


def _canonical_payload(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _require_safe_id(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise BattleOutcomeBatchError(f"{subject} is invalid")
    return value


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleOutcomeBatchError(f"{subject} digest is invalid")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str):
        raise BattleOutcomeBatchError(f"{subject} must be a string")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise BattleOutcomeBatchError(f"{subject} must be a non-negative integer")
    return value


def _number(value: object, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BattleOutcomeBatchError(f"{subject} must be finite numeric")
    try:
        observed = float(value)
    except OverflowError:
        raise BattleOutcomeBatchError(f"{subject} must be finite numeric") from None
    if not math.isfinite(observed):
        raise BattleOutcomeBatchError(f"{subject} must be finite numeric")
    return observed


def _boolean(value: object, subject: str) -> bool:
    if type(value) is not bool:  # noqa: E721
        raise BattleOutcomeBatchError(f"{subject} must be a bool")
    return value


__all__ = [
    "BATTLE_OUTCOME_BATCH_FREEZE_SCHEMA",
    "BATTLE_OUTCOME_PRESSURE_INVENTORY_SCHEMA",
    "BATTLE_OUTCOME_BATCH_ROSTER_SCHEMA",
    "BATTLE_OUTCOME_FIXED_HEURISTIC_ID",
    "BATTLE_OUTCOME_PRESSURE_CANDIDATE_SCHEMA",
    "DEVELOPMENT_CONTEXTS",
    "FRESH_TRAIN_CONTEXTS",
    "TOTAL_TRAIN_CONTEXTS",
    "BattleOutcomeBatchError",
    "BattleOutcomeBatchFreeze",
    "BattleOutcomeBatchRoster",
    "BattleOutcomePressureInventory",
    "BattleOutcomePressureCandidate",
    "RetainedBattleOutcomePrefix",
    "battle_outcome_claim_identity_sha256",
    "battle_outcome_fixed_heuristic_choice",
    "battle_outcome_fixed_heuristic_sha256",
    "battle_outcome_model_sha256",
    "battle_outcome_pressure_policy_sha256",
    "battle_outcome_source_cluster_sha256",
    "build_battle_outcome_pressure_candidate",
    "build_battle_outcome_pressure_inventory",
    "build_battle_outcome_batch_freeze",
    "build_retained_battle_outcome_prefix",
    "parse_battle_outcome_batch_freeze",
    "parse_battle_outcome_batch_roster",
    "parse_battle_outcome_pressure_inventory",
    "parse_retained_battle_outcome_prefix",
    "revalidate_battle_outcome_pressure_candidate",
    "select_battle_outcome_batch_roster",
    "select_battle_outcome_batch_roster_from_inventory",
]
