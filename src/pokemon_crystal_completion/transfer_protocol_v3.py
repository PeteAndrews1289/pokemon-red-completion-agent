"""Prospective, powered successor to the unopened Crystal v2 experiment.

V2 compared two converged convex fits at adaptation budget nine.  An offline
Red pilot showed that both initializations then make identical predictions,
while the zero-loss success conjunction is unnecessarily conservative.  V3
therefore makes zero-shot weight transfer the primary endpoint and treats
few-shot adaptation as a prior-preserving mandatory secondary analysis.

This module contains no cartridge path, bytes, capture, label, or prediction.
The plan remains review-gated and authorizes no private context access.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from pokemon_crystal_completion.source_contract import (
    CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT,
)
from pokemon_red_completion.evaluation_design import PairedExactDesign
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_SCHEMA_ID,
    GOAL_MANAGER_MODEL_ID,
    goal_manager_prior_adaptation_configuration,
)

CRYSTAL_TRANSFER_V3_PLAN_SCHEMA = "pokemon-core-goal-manager-transfer-plan-v3"
CRYSTAL_TRANSFER_V3_EXPERIMENT_ID = "red-to-crystal-goal-manager-v3"
CRYSTAL_TRANSFER_V3_PLAN_FILENAME = "crystal-goal-manager-transfer-v3.json"
CRYSTAL_TRANSFER_V3_ADAPTATION_CONTEXTS = 27
CRYSTAL_TRANSFER_V3_TEST_CONTEXTS = 54
CRYSTAL_TRANSFER_V3_FOLDS = 9
CRYSTAL_TRANSFER_V3_ADAPTATION_PER_FOLD = 3
CRYSTAL_TRANSFER_V3_TEST_PER_FOLD = 6
CRYSTAL_TRANSFER_V3_MINIMUM_CANDIDATE_ACCURACY = 0.50
CRYSTAL_TRANSFER_V3_MINIMUM_CANDIDATE_CORRECT = 27
CRYSTAL_TRANSFER_V3_UTILITY_COMPARATOR_ID = "highest_pressure_goal_index"
CRYSTAL_TRANSFER_V3_PRIMARY_DESIGN = PairedExactDesign(
    independent_contexts=CRYSTAL_TRANSFER_V3_TEST_CONTEXTS,
    alpha=0.05,
    smallest_useful_win_probability=0.50,
    smallest_useful_loss_probability=0.20,
    target_power=0.80,
)
CRYSTAL_TRANSFER_V3_RED_MODEL_SHA256 = (
    "af29d7e7f72e9921e638c88664b17e6fbbf6334468609ab66bda41c9f3dad66d"
)

_SOURCE_CANDIDATE = {
    "candidate_id": "red-goal-manager-74922cc-r3",
    "context_catalog_sha256": (
        "f913158ffc3fd9d9c9cfd89ee42abe819a9bc3139901df603a017182df6f3959"
    ),
    "feature_schema_id": GOAL_MANAGER_FEATURE_SCHEMA_ID,
    "fit_summary_file_sha256": (
        "cba3c9c19841c83110ff32b2be044b3ee7dbea350765df09f6ebc95081b117dc"
    ),
    "model_canonical_sha256": CRYSTAL_TRANSFER_V3_RED_MODEL_SHA256,
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


class CrystalTransferV3ProtocolError(ValueError):
    """Raised when the prospective V3 plan weakens or drifts."""


@dataclass(frozen=True, slots=True)
class CrystalTransferV3Slot:
    slot_id: str
    partition: str
    partition_ordinal: int
    goal_kind: GoalKind
    kind_ordinal: int
    fold: int
    candidate_goal_kinds: tuple[GoalKind, ...]

    @property
    def focus_candidate_index(self) -> int:
        return self.candidate_goal_kinds.index(self.goal_kind)

    def public_dict(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "partition": self.partition,
            "partition_ordinal": self.partition_ordinal,
            "goal_kind": self.goal_kind.value,
            "kind_ordinal": self.kind_ordinal,
            "fold": self.fold,
            "candidate_goal_kinds": [
                item.value for item in self.candidate_goal_kinds
            ],
            "focus_candidate_index": self.focus_candidate_index,
        }


@dataclass(frozen=True, slots=True)
class CrystalTransferV3Plan:
    plan_sha256: str
    slots: tuple[CrystalTransferV3Slot, ...]

    @property
    def adaptation_slots(self) -> tuple[CrystalTransferV3Slot, ...]:
        return tuple(item for item in self.slots if item.partition == "adaptation")

    @property
    def sealed_test_slots(self) -> tuple[CrystalTransferV3Slot, ...]:
        return tuple(item for item in self.slots if item.partition == "sealed_test")

    @property
    def authorized_for_private_context_access(self) -> bool:
        return False

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": CRYSTAL_TRANSFER_V3_PLAN_SCHEMA,
            "plan_sha256": self.plan_sha256,
            "experiment_id": CRYSTAL_TRANSFER_V3_EXPERIMENT_ID,
            "adaptation_contexts": len(self.adaptation_slots),
            "sealed_test_contexts": len(self.sealed_test_slots),
            "folds": CRYSTAL_TRANSFER_V3_FOLDS,
            "primary_endpoint": CRYSTAL_TRANSFER_V3_PRIMARY_DESIGN.public_dict(),
            "authorized_for_private_context_access": False,
            "private_path_fields": 0,
        }


def crystal_transfer_v3_slots() -> tuple[CrystalTransferV3Slot, ...]:
    """Generate balanced adaptation folds and independent sealed assignments."""

    adaptation: list[CrystalTransferV3Slot] = []
    kind_ordinals: defaultdict[GoalKind, int] = defaultdict(int)
    partition_ordinal = 0
    for fold in range(CRYSTAL_TRANSFER_V3_FOLDS):
        for offset in range(CRYSTAL_TRANSFER_V3_ADAPTATION_PER_FOLD):
            kind = _GOAL_KIND_ORDER[(fold + offset) % len(_GOAL_KIND_ORDER)]
            kind_ordinals[kind] += 1
            partition_ordinal += 1
            slot_id = f"crystal-goal-transfer-v3-adaptation-{partition_ordinal:03d}"
            adaptation.append(
                CrystalTransferV3Slot(
                    slot_id=slot_id,
                    partition="adaptation",
                    partition_ordinal=partition_ordinal,
                    goal_kind=kind,
                    kind_ordinal=kind_ordinals[kind],
                    fold=fold,
                    candidate_goal_kinds=_candidate_order(
                        slot_id,
                        focus_kind=kind,
                        focus_position=(partition_ordinal - 1) % len(_GOAL_KIND_ORDER),
                    ),
                )
            )

    sealed: list[CrystalTransferV3Slot] = []
    partition_ordinal = 0
    for kind_index, kind in enumerate(_GOAL_KIND_ORDER):
        for kind_ordinal in range(1, 7):
            partition_ordinal += 1
            fold = (kind_index + kind_ordinal - 1) % CRYSTAL_TRANSFER_V3_FOLDS
            slot_id = f"crystal-goal-transfer-v3-sealed_test-{partition_ordinal:03d}"
            sealed.append(
                CrystalTransferV3Slot(
                    slot_id=slot_id,
                    partition="sealed_test",
                    partition_ordinal=partition_ordinal,
                    goal_kind=kind,
                    kind_ordinal=kind_ordinal,
                    fold=fold,
                    candidate_goal_kinds=_candidate_order(
                        slot_id,
                        focus_kind=kind,
                        focus_position=(partition_ordinal - 1) % len(_GOAL_KIND_ORDER),
                    ),
                )
            )
    result = (*adaptation, *sealed)
    _validate_slot_schedule(result)
    return result


def crystal_transfer_v3_plan_document() -> dict[str, object]:
    slots = crystal_transfer_v3_slots()
    adaptation = tuple(item for item in slots if item.partition == "adaptation")
    sealed = tuple(item for item in slots if item.partition == "sealed_test")
    return {
        "adaptation": {
            "configuration": goal_manager_prior_adaptation_configuration(),
            "contexts": CRYSTAL_TRANSFER_V3_ADAPTATION_CONTEXTS,
            "contexts_per_fold": CRYSTAL_TRANSFER_V3_ADAPTATION_PER_FOLD,
            "folds": CRYSTAL_TRANSFER_V3_FOLDS,
            "goal_kind_exposures_per_kind": 3,
            "same_examples_order_optimizer_normalizer_and_prior_strength": True,
            "only_differing_field": "prior_center",
        },
        "authorization": {
            "external_reviews_required": ["claude", "antigravity"],
            "private_context_access": False,
            "reason": "prospective_v3_requires_external_design_review",
        },
        "catalog_gates": {
            "all_policy_contexts_unique": True,
            "candidate_order_derivation": (
                "balanced-focus-position-plus-sha256-experiment-slot-kind-v1"
            ),
            "exact_focus_position_balance_per_partition": True,
            "minimum_available_candidates_per_context": 3,
            "minimum_context_dependent_menu_reversals": 36,
            "minimum_distinct_focus_positions_per_partition": 9,
            "model_receives_candidate_position": False,
            "partition_policy_context_overlap": 0,
            "selected_candidate_positions_must_vary": True,
        },
        "claims": {
            "assigned_goal_kind_is_expected_teacher_label": True,
            "does_not_establish": [
                "end-to-end-crystal-completion",
                "autonomous-living-pokedex-completion",
                "transfer-beyond-goal-arbitration",
            ],
            "mandatory_secondary": {
                "comparison": "red_prior_vs_zero_prior_after_three_labels",
                "fold_assignment": "nine_balanced_disjoint_adaptation_folds",
                "report": "paired_wins_losses_ties_accuracy_and_per_kind",
                "promotion_endpoint": False,
            },
            "primary_endpoint": {
                **CRYSTAL_TRANSFER_V3_PRIMARY_DESIGN.public_dict(),
                "candidate": "frozen_red_weights_zero_shot",
                "control": "same_architecture_normalizer_and_masking_with_zero_weights",
                "missing_prediction_is_incorrect": True,
                "partition": "sealed_test",
            },
            "utility_gate": {
                "absolute_candidate_accuracy_floor": (
                    CRYSTAL_TRANSFER_V3_MINIMUM_CANDIDATE_ACCURACY
                ),
                "candidate_must_match_or_exceed_comparator_accuracy": True,
                "comparator_id": CRYSTAL_TRANSFER_V3_UTILITY_COMPARATOR_ID,
                "comparator_receives_same_identity_free_question": True,
                "minimum_candidate_correct": (
                    CRYSTAL_TRANSFER_V3_MINIMUM_CANDIDATE_CORRECT
                ),
                "predictions_committed_before_any_sealed_label": True,
                "zero_weight_sign_test_alone_is_not_promotion_eligible": True,
            },
        },
        "experiment_id": CRYSTAL_TRANSFER_V3_EXPERIMENT_ID,
        "prediction_order": [
            "freeze_catalog_before_any_prediction_or_label",
            (
                "commit_red_zero_weight_and_highest_pressure_predictions_for_all_"
                "sealed_contexts"
            ),
            "collect_all_adaptation_labels_without_opening_sealed_labels",
            "fit_each_red_prior_and_zero_prior_fold_from_its_three_declared_examples",
            "commit_every_fold_model_prediction_for_its_assigned_sealed_contexts",
            "open_each_sealed_context_once_and_publish_all_outcomes",
            "score_primary_and_mandatory_secondary_without_optional_stopping",
        ],
        "schema": CRYSTAL_TRANSFER_V3_PLAN_SCHEMA,
        "sealed_red_destination_test": {
            "captures": 12,
            "evaluated": 0,
            "opened": 0,
            "reused_for_transfer": False,
        },
        "slot_schedule": {
            "adaptation_contexts": len(adaptation),
            "adaptation_fold_counts": _fold_counts(adaptation),
            "adaptation_focus_position_counts": _focus_position_counts(adaptation),
            "goal_kind_order": [kind.value for kind in _GOAL_KIND_ORDER],
            "identity_prefix": "crystal-goal-transfer-v3",
            "sealed_test_contexts": len(sealed),
            "sealed_test_fold_counts": _fold_counts(sealed),
            "sealed_test_focus_position_counts": _focus_position_counts(sealed),
            "sealed_test_goal_kind_counts": _kind_counts(sealed),
            "adaptation_pairwise_order_reversals": _pairwise_order_reversals(
                adaptation
            ),
            "sealed_test_pairwise_order_reversals": _pairwise_order_reversals(sealed),
            "assignments": [item.public_dict() for item in slots],
        },
        "source_candidate": dict(_SOURCE_CANDIDATE),
        "supersedes": {
            "experiment_id": "red-to-crystal-goal-manager-v2",
            "reason": (
                "ordinary convex fine-tuning erased initialization and the zero-loss "
                "conjunction was underpowered"
            ),
            "v2_adaptation_examples_collected": 0,
            "v2_predictions_computed": 0,
            "v2_sealed_contexts_opened": 0,
            "v2_zero_shot_contexts_opened": 0,
        },
        "target_source": CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT.public_dict(),
    }


def canonical_crystal_transfer_v3_plan_bytes() -> bytes:
    return (
        json.dumps(
            crystal_transfer_v3_plan_document(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def parse_crystal_transfer_v3_plan(payload: bytes) -> CrystalTransferV3Plan:
    if not isinstance(payload, bytes):
        raise TypeError("Crystal transfer V3 plan must be bytes")
    try:
        document = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise CrystalTransferV3ProtocolError(
            "Crystal transfer V3 plan is not canonical JSON"
        ) from None
    if payload != canonical_crystal_transfer_v3_plan_bytes():
        raise CrystalTransferV3ProtocolError(
            "Crystal transfer V3 plan differs from preregistration"
        )
    if document != crystal_transfer_v3_plan_document():  # pragma: no cover - bytes imply this
        raise CrystalTransferV3ProtocolError("Crystal transfer V3 plan content differs")
    return CrystalTransferV3Plan(
        plan_sha256=hashlib.sha256(payload).hexdigest(),
        slots=crystal_transfer_v3_slots(),
    )


def load_crystal_transfer_v3_plan(repository_root: str | Path) -> CrystalTransferV3Plan:
    path = Path(repository_root) / "configs" / CRYSTAL_TRANSFER_V3_PLAN_FILENAME
    return parse_crystal_transfer_v3_plan(path.read_bytes())


def _candidate_order(
    slot_id: str,
    *,
    focus_kind: GoalKind,
    focus_position: int,
) -> tuple[GoalKind, ...]:
    if not 0 <= focus_position < len(_GOAL_KIND_ORDER):
        raise CrystalTransferV3ProtocolError("Crystal transfer focus position is invalid")
    remaining = sorted(
        (kind for kind in _GOAL_KIND_ORDER if kind is not focus_kind),
        key=lambda kind: hashlib.sha256(
            (
                f"{CRYSTAL_TRANSFER_V3_EXPERIMENT_ID}:{slot_id}:{kind.value}"
            ).encode("ascii")
        ).digest(),
    )
    remaining.insert(focus_position, focus_kind)
    return tuple(remaining)


def _validate_slot_schedule(slots: tuple[CrystalTransferV3Slot, ...]) -> None:
    if len(slots) != (
        CRYSTAL_TRANSFER_V3_ADAPTATION_CONTEXTS + CRYSTAL_TRANSFER_V3_TEST_CONTEXTS
    ):
        raise CrystalTransferV3ProtocolError("Crystal transfer V3 slot count differs")
    if len({item.slot_id for item in slots}) != len(slots):
        raise CrystalTransferV3ProtocolError("Crystal transfer V3 slot identity repeats")
    adaptation = tuple(item for item in slots if item.partition == "adaptation")
    sealed = tuple(item for item in slots if item.partition == "sealed_test")
    if Counter(item.goal_kind for item in adaptation) != Counter(
        {kind: 3 for kind in GoalKind}
    ):
        raise CrystalTransferV3ProtocolError("adaptation goal-kind balance differs")
    if Counter(item.goal_kind for item in sealed) != Counter(
        {kind: 6 for kind in GoalKind}
    ):
        raise CrystalTransferV3ProtocolError("sealed goal-kind balance differs")
    if Counter(item.fold for item in adaptation) != Counter(
        {fold: CRYSTAL_TRANSFER_V3_ADAPTATION_PER_FOLD for fold in range(9)}
    ):
        raise CrystalTransferV3ProtocolError("adaptation fold balance differs")
    if Counter(item.fold for item in sealed) != Counter(
        {fold: CRYSTAL_TRANSFER_V3_TEST_PER_FOLD for fold in range(9)}
    ):
        raise CrystalTransferV3ProtocolError("sealed fold balance differs")
    for partition in (adaptation, sealed):
        if any(
            len(item.candidate_goal_kinds) < 3
            or set(item.candidate_goal_kinds) != set(GoalKind)
            for item in partition
        ):
            raise CrystalTransferV3ProtocolError(
                "Crystal transfer V3 candidate menus are incomplete"
            )
        expected_position_count = len(partition) // len(_GOAL_KIND_ORDER)
        if Counter(item.focus_candidate_index for item in partition) != Counter(
            {
                position: expected_position_count
                for position in range(len(_GOAL_KIND_ORDER))
            }
        ):
            raise CrystalTransferV3ProtocolError(
                "Crystal transfer V3 focus positions are not exactly balanced"
            )
        if _pairwise_order_reversals(partition) != len(
            tuple(combinations(_GOAL_KIND_ORDER, 2))
        ):
            raise CrystalTransferV3ProtocolError(
                "Crystal transfer V3 candidate-order reversals are incomplete"
            )


def _fold_counts(slots: tuple[CrystalTransferV3Slot, ...]) -> dict[str, int]:
    counts = Counter(item.fold for item in slots)
    return {str(fold): counts[fold] for fold in range(CRYSTAL_TRANSFER_V3_FOLDS)}


def _kind_counts(slots: tuple[CrystalTransferV3Slot, ...]) -> dict[str, int]:
    counts = Counter(item.goal_kind for item in slots)
    return {kind.value: counts[kind] for kind in GoalKind}


def _focus_position_counts(
    slots: tuple[CrystalTransferV3Slot, ...],
) -> dict[str, int]:
    counts = Counter(item.focus_candidate_index for item in slots)
    return {str(position): counts[position] for position in range(len(_GOAL_KIND_ORDER))}


def _pairwise_order_reversals(slots: tuple[CrystalTransferV3Slot, ...]) -> int:
    if not slots:
        return 0
    return sum(
        len(
            {
                slot.candidate_goal_kinds.index(left)
                < slot.candidate_goal_kinds.index(right)
                for slot in slots
            }
        )
        == 2
        for left, right in combinations(_GOAL_KIND_ORDER, 2)
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


__all__ = [
    "CRYSTAL_TRANSFER_V3_ADAPTATION_CONTEXTS",
    "CRYSTAL_TRANSFER_V3_EXPERIMENT_ID",
    "CRYSTAL_TRANSFER_V3_MINIMUM_CANDIDATE_ACCURACY",
    "CRYSTAL_TRANSFER_V3_MINIMUM_CANDIDATE_CORRECT",
    "CRYSTAL_TRANSFER_V3_PLAN_FILENAME",
    "CRYSTAL_TRANSFER_V3_PLAN_SCHEMA",
    "CRYSTAL_TRANSFER_V3_PRIMARY_DESIGN",
    "CRYSTAL_TRANSFER_V3_TEST_CONTEXTS",
    "CRYSTAL_TRANSFER_V3_UTILITY_COMPARATOR_ID",
    "CrystalTransferV3Plan",
    "CrystalTransferV3ProtocolError",
    "CrystalTransferV3Slot",
    "canonical_crystal_transfer_v3_plan_bytes",
    "crystal_transfer_v3_plan_document",
    "crystal_transfer_v3_slots",
    "load_crystal_transfer_v3_plan",
    "parse_crystal_transfer_v3_plan",
]
