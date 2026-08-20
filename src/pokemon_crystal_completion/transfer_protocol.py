"""Prospective Red-to-Crystal goal-manager transfer experiment.

This plan exists before any Crystal teaching label.  It separates the first
zero-shot falsification, adaptation data, and a one-opening sealed comparison;
uses balanced nested adaptation budgets; and commits every test prediction
before the teacher may act.  The protocol is intentionally stricter than an
ordinary train/test split because the same people are implementing the adapter
and evaluating whether it transfers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType

from pokemon_crystal_completion.source_contract import (
    CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_SCHEMA_ID,
    GOAL_MANAGER_MODEL_ID,
    goal_manager_adaptation_configuration,
)

CRYSTAL_TRANSFER_PLAN_SCHEMA = "pokemon-core-goal-manager-transfer-plan-v2"
CRYSTAL_TRANSFER_EXPERIMENT_ID = "red-to-crystal-goal-manager-v2"
CRYSTAL_TRANSFER_PLAN_FILENAME = "crystal-goal-manager-transfer-v2.json"
CRYSTAL_CANDIDATE_ORDER_DERIVATION = "sha256-experiment-slot-kind-v1"
CRYSTAL_BASELINE_PREDICTOR_IDS = (
    "fixed_priority",
    "highest_pressure",
    "lowest_effort",
)
CRYSTAL_ZERO_SHOT_PREDICTOR_IDS = ("red_frozen", *CRYSTAL_BASELINE_PREDICTOR_IDS)
CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS = tuple(
    f"{initialization}_budget_{budget}"
    for budget in (9, 18, 27)
    for initialization in ("red_initialized", "scratch")
)
CRYSTAL_SEALED_PREDICTOR_IDS = (
    *CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS,
    *CRYSTAL_BASELINE_PREDICTOR_IDS,
)
CRYSTAL_RED_FROZEN_MODEL_SHA256 = (
    "af29d7e7f72e9921e638c88664b17e6fbbf6334468609ab66bda41c9f3dad66d"
)
CRYSTAL_BASELINE_PREDICTOR_SHA256 = MappingProxyType(
    {
        predictor_id: hashlib.sha256(
            f"pokemon.core.goal-manager.baseline.v1:{predictor_id}".encode("ascii")
        ).hexdigest()
        for predictor_id in CRYSTAL_BASELINE_PREDICTOR_IDS
    }
)

_RED_CANDIDATE = {
    "candidate_id": "red-goal-manager-74922cc-r3",
    "context_catalog_sha256": (
        "f913158ffc3fd9d9c9cfd89ee42abe819a9bc3139901df603a017182df6f3959"
    ),
    "feature_schema_id": GOAL_MANAGER_FEATURE_SCHEMA_ID,
    "fit_summary_file_sha256": (
        "cba3c9c19841c83110ff32b2be044b3ee7dbea350765df09f6ebc95081b117dc"
    ),
    "model_canonical_sha256": CRYSTAL_RED_FROZEN_MODEL_SHA256,
    "model_file_sha256": (
        "16901b701476230d2be6c0327cc3e572f6dc5ce034f99067562916cecd3e77f4"
    ),
    "model_id": GOAL_MANAGER_MODEL_ID,
    "promotion_plan_sha256": (
        "b648d1825fb7701f38aa00f5625fe88a86040dc7b4b061b4256f6ae665b90c46"
    ),
    "training_source_commit": "74922cc9faa793bae4f9daf03627e8621297b038",
}

_GOAL_KIND_ORDER = tuple(GoalKind)
_PARTITION_COUNTS = {
    "zero_shot_probe": (18, 2),
    "adaptation": (27, 3),
    "sealed_test": (27, 3),
}
_ADAPTATION_BUDGETS = (9, 18, 27)
_FAILURE_TAXONOMY = (
    "source_identity_mismatch",
    "observation_unavailable",
    "catalog_stratum_mismatch",
    "availability_mask_error",
    "ranking_error",
    "binding_unavailable",
    "execution_failure",
    "verification_failure",
    "external_interruption",
)
_PREDICTION_ORDER = (
    "commit_zero_shot_probe_predictions_before_any_crystal_label",
    "open_zero_shot_probe_once_and_freeze_all_results",
    "collect_adaptation_partition_without_using_probe_for_model_selection",
    "freeze_red_initialized_and_scratch_candidates_at_all_three_budgets",
    "commit_every_sealed_test_prediction_before_any_test_teacher_action",
    "open_each_candidate_context_execution_identity_at_most_once",
    "score_and_publish_all_candidates_without_optional_stopping",
)


class CrystalTransferProtocolError(ValueError):
    """Raised when a transfer plan weakens or becomes ambiguous."""


@dataclass(frozen=True, slots=True)
class CrystalTransferPartition:
    name: str
    contexts: int
    contexts_per_goal_kind: int
    teacher_access: str
    teacher_labels_used_for_fitting: bool


@dataclass(frozen=True, slots=True)
class CrystalTransferSlot:
    """One prospective context identity; no capture or label exists yet."""

    slot_id: str
    partition: str
    partition_ordinal: int
    goal_kind: GoalKind
    kind_ordinal: int
    candidate_goal_kinds: tuple[GoalKind, ...]

    @property
    def focus_candidate_index(self) -> int:
        return self.candidate_goal_kinds.index(self.goal_kind)


@dataclass(frozen=True, slots=True)
class CrystalTransferPlan:
    """Parsed fixed experiment with a deterministic 72-context schedule."""

    plan_sha256: str
    experiment_id: str
    partitions: tuple[CrystalTransferPartition, ...]
    goal_kind_order: tuple[GoalKind, ...]
    adaptation_budgets: tuple[int, ...]
    prediction_order: tuple[str, ...]
    failure_taxonomy: tuple[str, ...]
    primary_budget: int
    minimum_primary_wins: int
    maximum_primary_losses: int

    @property
    def slots(self) -> tuple[CrystalTransferSlot, ...]:
        rows: list[CrystalTransferSlot] = []
        for partition in self.partitions:
            partition_ordinal = 0
            for kind_ordinal in range(1, partition.contexts_per_goal_kind + 1):
                for goal_kind in self.goal_kind_order:
                    partition_ordinal += 1
                    slot_id = (
                        f"crystal-goal-transfer-v2-{partition.name}-"
                        f"{partition_ordinal:03d}"
                    )
                    rows.append(
                        CrystalTransferSlot(
                            slot_id=slot_id,
                            partition=partition.name,
                            partition_ordinal=partition_ordinal,
                            goal_kind=goal_kind,
                            kind_ordinal=kind_ordinal,
                            candidate_goal_kinds=crystal_transfer_candidate_order(slot_id),
                        )
                    )
            if partition_ordinal != partition.contexts:
                raise CrystalTransferProtocolError("transfer partition schedule drifted")
        return tuple(rows)

    @property
    def ready_for_private_context_access(self) -> bool:
        """The plan is frozen, but the owner's exact ROM digest is not yet bound."""

        return CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT.live_identity_complete

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": CRYSTAL_TRANSFER_PLAN_SCHEMA,
            "plan_sha256": self.plan_sha256,
            "experiment_id": self.experiment_id,
            "contexts": len(self.slots),
            "partition_counts": {
                partition.name: partition.contexts for partition in self.partitions
            },
            "adaptation_budgets": list(self.adaptation_budgets),
            "primary_endpoint": {
                "budget": self.primary_budget,
                "minimum_red_initialized_wins": self.minimum_primary_wins,
                "maximum_red_initialized_losses": self.maximum_primary_losses,
                "two_sided_exact_alpha": 0.05,
            },
            "private_context_access_ready": self.ready_for_private_context_access,
            "private_path_fields": 0,
            "teacher_label_fields": 0,
        }


def parse_crystal_transfer_plan(payload: bytes) -> CrystalTransferPlan:
    """Parse only the exact canonical preregistration committed by this source."""

    document = _parse_canonical_document(payload)
    expected = crystal_transfer_plan_document()
    if document != expected:
        raise CrystalTransferProtocolError("Crystal transfer plan differs from preregistration")
    partitions_raw = document["partitions"]
    assert isinstance(partitions_raw, list)
    partitions = tuple(
        CrystalTransferPartition(
            name=str(item["name"]),
            contexts=int(item["contexts"]),
            contexts_per_goal_kind=int(item["contexts_per_goal_kind"]),
            teacher_access=str(item["teacher_access"]),
            teacher_labels_used_for_fitting=bool(item["teacher_labels_used_for_fitting"]),
        )
        for item in partitions_raw
        if isinstance(item, dict)
    )
    if len(partitions) != 3:
        raise CrystalTransferProtocolError("Crystal transfer partitions are incomplete")
    plan = CrystalTransferPlan(
        plan_sha256=hashlib.sha256(payload).hexdigest(),
        experiment_id=CRYSTAL_TRANSFER_EXPERIMENT_ID,
        partitions=partitions,
        goal_kind_order=_GOAL_KIND_ORDER,
        adaptation_budgets=_ADAPTATION_BUDGETS,
        prediction_order=_PREDICTION_ORDER,
        failure_taxonomy=_FAILURE_TAXONOMY,
        primary_budget=9,
        minimum_primary_wins=6,
        maximum_primary_losses=0,
    )
    _validate_schedule(plan)
    return plan


def crystal_transfer_plan_document() -> dict[str, object]:
    """Return the exact public plan for canonical regeneration and testing."""

    return {
        "adaptation": {
            "budgets": list(_ADAPTATION_BUDGETS),
            "configuration": goal_manager_adaptation_configuration(),
            "same_examples_order_optimizer_and_normalizer_for_both_initializations": True,
        },
        "catalog_gates": {
            "all_policy_contexts_unique": True,
            "candidate_order": {
                "derivation": CRYSTAL_CANDIDATE_ORDER_DERIVATION,
                "minimum_distinct_focus_positions_per_partition": 8,
                "model_receives_candidate_position": False,
            },
            "minimum_candidates_per_context": 2,
            "minimum_context_dependent_menus_per_partition": 3,
            "minimum_three_way_contexts": {
                "adaptation": 9,
                "sealed_test": 9,
                "zero_shot_probe": 6,
            },
            "partition_policy_context_overlap": 0,
            "selected_candidate_positions_must_vary": True,
        },
        "claims": {
            "does_not_establish": [
                "end-to-end-crystal-completion",
                "autonomous-living-pokedex-completion",
                "transfer-beyond-goal-arbitration",
            ],
            "primary_endpoint": {
                "alpha": 0.05,
                "budget": 9,
                "comparison": "red_initialized_vs_scratch",
                "maximum_discordant_losses": 0,
                "minimum_discordant_wins": 6,
                "missing_prediction_is_incorrect": True,
                "partition": "sealed_test",
                "test": "paired_two_sided_exact",
            },
            "secondary_endpoints": [
                "zero_shot_vs_fixed_baselines_descriptive",
                "budget_18_paired_descriptive",
                "budget_27_paired_descriptive",
                "accuracy_calibration_and_per_kind_results",
                "paired_causal_execution_success",
            ],
        },
        "experiment_id": CRYSTAL_TRANSFER_EXPERIMENT_ID,
        "failure_taxonomy": list(_FAILURE_TAXONOMY),
        "partitions": [
            {
                "contexts": 18,
                "contexts_per_goal_kind": 2,
                "name": "zero_shot_probe",
                "sealed_until": "zero_shot_prediction_commit",
                "teacher_access": "after_zero_shot_prediction_commit",
                "teacher_labels_used_for_fitting": False,
            },
            {
                "contexts": 27,
                "contexts_per_goal_kind": 3,
                "name": "adaptation",
                "sealed_until": "zero_shot_probe_results_frozen",
                "teacher_access": "after_zero_shot_probe_is_immutable",
                "teacher_labels_used_for_fitting": True,
            },
            {
                "contexts": 27,
                "contexts_per_goal_kind": 3,
                "name": "sealed_test",
                "sealed_until": "all_candidate_prediction_commits",
                "teacher_access": "after_all_candidate_prediction_commits",
                "teacher_labels_used_for_fitting": False,
            },
        ],
        "prediction_order": list(_PREDICTION_ORDER),
        "prediction_candidates": {
            "fixed_predictor_sha256": {
                "red_frozen": CRYSTAL_RED_FROZEN_MODEL_SHA256,
                **dict(CRYSTAL_BASELINE_PREDICTOR_SHA256),
            },
            "sealed_test": list(CRYSTAL_SEALED_PREDICTOR_IDS),
            "zero_shot_probe": list(CRYSTAL_ZERO_SHOT_PREDICTOR_IDS),
        },
        "schema": CRYSTAL_TRANSFER_PLAN_SCHEMA,
        "sealed_red_destination_test": {
            "captures": 12,
            "evaluated": 0,
            "opened": 0,
            "reused_for_transfer": False,
        },
        "slot_schedule": {
            "generation": "partition_block_then_goal-kind-order-v1",
            "goal_kind_order": [kind.value for kind in _GOAL_KIND_ORDER],
            "identity_prefix": "crystal-goal-transfer-v2",
        },
        "source_candidate": dict(_RED_CANDIDATE),
        "target_source": CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT.public_dict(),
    }


def canonical_crystal_transfer_plan_bytes() -> bytes:
    return (
        json.dumps(
            crystal_transfer_plan_document(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def crystal_transfer_candidate_order(slot_id: str) -> tuple[GoalKind, ...]:
    """Derive a stable, label-free candidate permutation for one frozen slot."""

    if (
        not isinstance(slot_id, str)
        or not slot_id.startswith("crystal-goal-transfer-v2-")
        or len(slot_id) > 96
    ):
        raise CrystalTransferProtocolError("Crystal transfer slot identity is invalid")

    def key(kind: GoalKind) -> tuple[bytes, str]:
        material = f"{CRYSTAL_TRANSFER_EXPERIMENT_ID}:{slot_id}:{kind.value}".encode("ascii")
        return hashlib.sha256(material).digest(), kind.value

    return tuple(sorted(GoalKind, key=key))


def _validate_schedule(plan: CrystalTransferPlan) -> None:
    slots = plan.slots
    if len(slots) != 72 or len({slot.slot_id for slot in slots}) != 72:
        raise CrystalTransferProtocolError("Crystal transfer slot identities are invalid")
    for partition in plan.partitions:
        rows = tuple(slot for slot in slots if slot.partition == partition.name)
        counts = {kind: sum(slot.goal_kind is kind for slot in rows) for kind in GoalKind}
        if set(counts.values()) != {partition.contexts_per_goal_kind}:
            raise CrystalTransferProtocolError("Crystal transfer goal-kind balance drifted")
        if any(
            len(slot.candidate_goal_kinds) != len(GoalKind)
            or set(slot.candidate_goal_kinds) != set(GoalKind)
            or slot.candidate_goal_kinds
            != crystal_transfer_candidate_order(slot.slot_id)
            for slot in rows
        ):
            raise CrystalTransferProtocolError("Crystal candidate order drifted")
        if len({slot.focus_candidate_index for slot in rows}) < 8:
            raise CrystalTransferProtocolError("Crystal focus candidate positions lack diversity")
    adaptation = tuple(slot for slot in slots if slot.partition == "adaptation")
    for budget in plan.adaptation_budgets:
        prefix = adaptation[:budget]
        expected_per_kind = budget // len(GoalKind)
        if budget % len(GoalKind) or any(
            sum(slot.goal_kind is kind for slot in prefix) != expected_per_kind
            for kind in GoalKind
        ):
            raise CrystalTransferProtocolError("Crystal adaptation prefix is not balanced")


def _parse_canonical_document(payload: bytes) -> dict[str, object]:
    if not isinstance(payload, bytes) or len(payload) > 256 * 1024:
        raise CrystalTransferProtocolError("Crystal transfer plan bytes are invalid")
    try:
        decoded = payload.decode("ascii")
        document = json.loads(
            decoded,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except CrystalTransferProtocolError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise CrystalTransferProtocolError("Crystal transfer plan is not valid JSON") from None
    if not isinstance(document, dict):
        raise CrystalTransferProtocolError("Crystal transfer plan must be an object")
    canonical = (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    if payload != canonical:
        raise CrystalTransferProtocolError("Crystal transfer plan must be canonical ASCII JSON")
    return document


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CrystalTransferProtocolError("Crystal transfer plan has duplicate keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    del value
    raise CrystalTransferProtocolError("Crystal transfer plan contains a non-finite number")


__all__ = [
    "CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS",
    "CRYSTAL_BASELINE_PREDICTOR_IDS",
    "CRYSTAL_BASELINE_PREDICTOR_SHA256",
    "CRYSTAL_CANDIDATE_ORDER_DERIVATION",
    "CRYSTAL_SEALED_PREDICTOR_IDS",
    "CRYSTAL_RED_FROZEN_MODEL_SHA256",
    "CRYSTAL_TRANSFER_EXPERIMENT_ID",
    "CRYSTAL_TRANSFER_PLAN_FILENAME",
    "CRYSTAL_TRANSFER_PLAN_SCHEMA",
    "CRYSTAL_ZERO_SHOT_PREDICTOR_IDS",
    "CrystalTransferPartition",
    "CrystalTransferPlan",
    "CrystalTransferProtocolError",
    "CrystalTransferSlot",
    "canonical_crystal_transfer_plan_bytes",
    "crystal_transfer_candidate_order",
    "crystal_transfer_plan_document",
    "parse_crystal_transfer_plan",
]
