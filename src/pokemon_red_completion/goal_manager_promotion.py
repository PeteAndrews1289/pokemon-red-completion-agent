"""Fail-closed promotion contract for the first portable goal manager.

The fitted model and its Red development corpus are private artifacts.  This
module authenticates them through path-free digests recorded in a committed
plan, keeps the twelve destination-test captures sealed, and defines the exact
shadow/causal gates that must pass before the candidate can be called live.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalog,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GOAL_MANAGER_MODEL_ID,
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
    goal_manager_fit_configuration,
    load_goal_manager_model,
)
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_GAME_ID,
    GoalManagerCollectionRegistry,
    load_committed_goal_manager_registry_at_revision,
)

if TYPE_CHECKING:
    from pokemon_red_completion.goal_manager_promotion_runtime import (
        GoalManagerPromotionBatchResult,
    )

GOAL_MANAGER_PROMOTION_PLAN_RELATIVE_PATH = (
    "configs/red-goal-manager-promotion-v1.json"
)
GOAL_MANAGER_PROMOTION_PLAN_SCHEMA = "pokemon-red-goal-manager-promotion-plan-v1"
GOAL_MANAGER_PROMOTION_RECEIPT_SCHEMA = (
    "pokemon-red-goal-manager-promotion-evaluation-v1"
)

_MAX_PLAN_BYTES = 64 * 1024
_MAX_SUMMARY_BYTES = 4 * 1024 * 1024
_MAX_GIT_BYTES = 128 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")


class GoalManagerPromotionError(RuntimeError):
    """Raised when a candidate or promotion claim is not fully authenticated."""


@dataclass(frozen=True, slots=True)
class GoalManagerPromotionPlan:
    plan_sha256: str
    candidate_id: str
    game_id: str
    training_source_commit: str
    training_source_bundle_sha256: str
    registry_sha256: str
    teacher_execution_sha256: str
    context_catalog_sha256: str
    model_file_sha256: str
    model_canonical_sha256: str
    fit_summary_file_sha256: str
    model_id: str
    train_examples: int
    validation_examples: int
    minimum_offline_validation_accuracy: float
    minimum_each_kind_accuracy: float
    minimum_live_confidence: float
    required_shadow_contexts: int
    required_shadow_agreements: int
    required_shadow_successes: int
    required_causal_contexts: int
    required_causal_successes: int
    maximum_teacher_queries: int
    maximum_teacher_fallbacks: int
    maximum_episodes_created: int
    sealed_test_captures: int
    sealed_test_captures_opened: int
    sealed_test_captures_evaluated: int


@dataclass(frozen=True, slots=True)
class AuthenticatedGoalManagerCandidate:
    """A private model authenticated without retaining any private path."""

    plan: GoalManagerPromotionPlan
    registry: GoalManagerCollectionRegistry
    catalog: GoalManagerContextCatalog
    model: GoalManagerLinearModel
    fit_summary_sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.plan.candidate_id,
            "context_catalog_sha256": self.catalog.catalog_sha256,
            "fit_summary_file_sha256": self.fit_summary_sha256,
            "model_canonical_sha256": canonical_goal_manager_model_sha256(self.model),
            "model_file_sha256": self.plan.model_file_sha256,
            "model_id": self.model.model_id,
            "registry_sha256": self.registry.registry_sha256,
            "training_source_bundle_sha256": (
                self.registry.execution.source_bundle_sha256
            ),
            "training_source_commit": self.registry.execution.source_commit,
            "private_path_fields": 0,
        }


def parse_goal_manager_promotion_plan(payload: bytes) -> GoalManagerPromotionPlan:
    """Parse the one canonical, path-free Red promotion declaration."""

    document = _canonical_document(payload, maximum_bytes=_MAX_PLAN_BYTES, subject="plan")
    _exact_keys(
        document,
        {
            "artifacts",
            "candidate_id",
            "corpus",
            "game_id",
            "gates",
            "held_out_test",
            "schema",
            "scope",
            "training_source",
        },
        "promotion plan",
    )
    if document.get("schema") != GOAL_MANAGER_PROMOTION_PLAN_SCHEMA:
        raise GoalManagerPromotionError("goal-manager promotion plan schema differs")
    if document.get("scope") != {
        "establishes": "same-context-live-authority-integration",
        "does_not_establish": [
            "unseen-context-generalization",
            "cross-title-transfer",
            "end-to-end-game-completion",
        ],
    }:
        raise GoalManagerPromotionError("goal-manager promotion scope differs")

    artifacts = _mapping(document.get("artifacts"), "promotion artifacts")
    corpus = _mapping(document.get("corpus"), "promotion corpus")
    gates = _mapping(document.get("gates"), "promotion gates")
    held_out = _mapping(document.get("held_out_test"), "held-out test declaration")
    source = _mapping(document.get("training_source"), "promotion training source")
    _exact_keys(
        artifacts,
        {
            "context_catalog_sha256",
            "fit_summary_file_sha256",
            "model_canonical_sha256",
            "model_file_sha256",
            "model_id",
        },
        "promotion artifacts",
    )
    _exact_keys(corpus, {"train_examples", "validation_examples"}, "promotion corpus")
    _exact_keys(
        gates,
        {
            "maximum_episodes_created",
            "maximum_teacher_fallbacks",
            "maximum_teacher_queries",
            "minimum_each_kind_accuracy",
            "minimum_live_confidence",
            "minimum_offline_validation_accuracy",
            "required_causal_contexts",
            "required_causal_successes",
            "required_shadow_agreements",
            "required_shadow_contexts",
            "required_shadow_successes",
        },
        "promotion gates",
    )
    _exact_keys(
        held_out,
        {"captures", "evaluated", "opened", "status"},
        "held-out test declaration",
    )
    _exact_keys(
        source,
        {
            "registry_sha256",
            "source_bundle_sha256",
            "source_commit",
            "teacher_execution_sha256",
        },
        "promotion training source",
    )

    candidate_id = _safe_id(document.get("candidate_id"), "candidate identity")
    game_id = document.get("game_id")
    model_id = artifacts.get("model_id")
    if game_id != GOAL_MANAGER_GAME_ID or model_id != GOAL_MANAGER_MODEL_ID:
        raise GoalManagerPromotionError("goal-manager promotion identity differs")
    source_commit = source.get("source_commit")
    if not isinstance(source_commit, str) or _GIT_OID.fullmatch(source_commit) is None:
        raise GoalManagerPromotionError("goal-manager training commit is invalid")

    train_examples = _exact_integer(corpus.get("train_examples"), "train examples")
    validation_examples = _exact_integer(
        corpus.get("validation_examples"), "validation examples"
    )
    required_shadow_contexts = _exact_integer(
        gates.get("required_shadow_contexts"), "required shadow contexts"
    )
    required_shadow_agreements = _exact_integer(
        gates.get("required_shadow_agreements"), "required shadow agreements"
    )
    required_shadow_successes = _exact_integer(
        gates.get("required_shadow_successes"), "required shadow successes"
    )
    required_causal_contexts = _exact_integer(
        gates.get("required_causal_contexts"), "required causal contexts"
    )
    required_causal_successes = _exact_integer(
        gates.get("required_causal_successes"), "required causal successes"
    )
    maximum_teacher_queries = _exact_integer(
        gates.get("maximum_teacher_queries"), "maximum teacher queries"
    )
    maximum_teacher_fallbacks = _exact_integer(
        gates.get("maximum_teacher_fallbacks"), "maximum teacher fallbacks"
    )
    maximum_episodes_created = _exact_integer(
        gates.get("maximum_episodes_created"), "maximum episodes"
    )
    captures = _exact_integer(held_out.get("captures"), "sealed test captures")
    opened = _exact_integer(held_out.get("opened"), "opened sealed test captures")
    evaluated = _exact_integer(
        held_out.get("evaluated"), "evaluated sealed test captures"
    )
    if (
        train_examples != 54
        or validation_examples != 27
        or required_shadow_contexts != validation_examples
        or required_shadow_agreements != required_shadow_contexts
        or required_shadow_successes != required_shadow_contexts
        or required_causal_contexts != validation_examples
        or required_causal_successes != required_causal_contexts
        or maximum_teacher_queries != 0
        or maximum_teacher_fallbacks != 0
        or maximum_episodes_created != 0
        or captures != 12
        or opened != 0
        or evaluated != 0
        or held_out.get("status") != "sealed_unopened"
    ):
        raise GoalManagerPromotionError("goal-manager promotion counts differ")

    minimum_offline = _probability(
        gates.get("minimum_offline_validation_accuracy"),
        "minimum offline validation accuracy",
    )
    minimum_each_kind = _probability(
        gates.get("minimum_each_kind_accuracy"),
        "minimum each-kind accuracy",
    )
    minimum_confidence = _probability(
        gates.get("minimum_live_confidence"),
        "minimum live confidence",
    )
    if minimum_offline != 1.0 or minimum_each_kind != 1.0 or minimum_confidence != 0.8:
        raise GoalManagerPromotionError("goal-manager promotion thresholds differ")

    return GoalManagerPromotionPlan(
        plan_sha256=hashlib.sha256(payload).hexdigest(),
        candidate_id=candidate_id,
        game_id=GOAL_MANAGER_GAME_ID,
        training_source_commit=source_commit,
        training_source_bundle_sha256=_digest(
            source.get("source_bundle_sha256"), "training source bundle"
        ),
        registry_sha256=_digest(source.get("registry_sha256"), "registry digest"),
        teacher_execution_sha256=_digest(
            source.get("teacher_execution_sha256"), "teacher execution digest"
        ),
        context_catalog_sha256=_digest(
            artifacts.get("context_catalog_sha256"), "context catalog digest"
        ),
        model_file_sha256=_digest(
            artifacts.get("model_file_sha256"), "model file digest"
        ),
        model_canonical_sha256=_digest(
            artifacts.get("model_canonical_sha256"), "canonical model digest"
        ),
        fit_summary_file_sha256=_digest(
            artifacts.get("fit_summary_file_sha256"), "fit summary digest"
        ),
        model_id=GOAL_MANAGER_MODEL_ID,
        train_examples=train_examples,
        validation_examples=validation_examples,
        minimum_offline_validation_accuracy=minimum_offline,
        minimum_each_kind_accuracy=minimum_each_kind,
        minimum_live_confidence=minimum_confidence,
        required_shadow_contexts=required_shadow_contexts,
        required_shadow_agreements=required_shadow_agreements,
        required_shadow_successes=required_shadow_successes,
        required_causal_contexts=required_causal_contexts,
        required_causal_successes=required_causal_successes,
        maximum_teacher_queries=maximum_teacher_queries,
        maximum_teacher_fallbacks=maximum_teacher_fallbacks,
        maximum_episodes_created=maximum_episodes_created,
        sealed_test_captures=captures,
        sealed_test_captures_opened=opened,
        sealed_test_captures_evaluated=evaluated,
    )


def load_committed_goal_manager_promotion_plan(
    repository_root: str | Path,
) -> tuple[GoalManagerPromotionPlan, str]:
    """Load the promotion plan from ``HEAD`` rather than the working tree."""

    root = Path(repository_root).resolve()
    commit = _git(root, ["rev-parse", "--verify", "HEAD^{commit}"]).decode(
        "ascii"
    ).strip()
    if _GIT_OID.fullmatch(commit) is None:
        raise GoalManagerPromotionError("goal-manager evaluation commit is invalid")
    payload = _git(
        root,
        ["show", f"{commit}:{GOAL_MANAGER_PROMOTION_PLAN_RELATIVE_PATH}"],
    )
    return parse_goal_manager_promotion_plan(payload), commit


def authenticate_goal_manager_candidate(
    *,
    repository_root: str | Path,
    plan: GoalManagerPromotionPlan,
    context_catalog_path: str | Path,
    model_path: str | Path,
    fit_summary_path: str | Path,
) -> AuthenticatedGoalManagerCandidate:
    """Authenticate private artifacts and the development claim they encode."""

    registry = load_committed_goal_manager_registry_at_revision(
        repository_root,
        plan.training_source_commit,
    )
    if (
        registry.execution.source_commit != plan.training_source_commit
        or registry.execution.source_bundle_sha256
        != plan.training_source_bundle_sha256
        or registry.registry_sha256 != plan.registry_sha256
        or registry.execution.teacher_execution_sha256
        != plan.teacher_execution_sha256
    ):
        raise GoalManagerPromotionError("goal-manager training provenance differs")

    catalog_payload = _read_regular(
        Path(context_catalog_path),
        expected_sha256=plan.context_catalog_sha256,
        maximum_bytes=4 * 1024 * 1024,
        subject="context catalog",
    )
    catalog = parse_goal_manager_context_catalog(catalog_payload, registry)
    model = load_goal_manager_model(
        model_path,
        expected_sha256=plan.model_file_sha256,
    )
    if canonical_goal_manager_model_sha256(model) != plan.model_canonical_sha256:
        raise GoalManagerPromotionError("canonical goal-manager model digest differs")

    summary_payload = _read_regular(
        Path(fit_summary_path),
        expected_sha256=plan.fit_summary_file_sha256,
        maximum_bytes=_MAX_SUMMARY_BYTES,
        subject="fit summary",
    )
    summary = _canonical_document(
        summary_payload,
        maximum_bytes=_MAX_SUMMARY_BYTES,
        subject="fit summary",
    )
    _require_fit_summary(summary, plan)
    return AuthenticatedGoalManagerCandidate(
        plan=plan,
        registry=registry,
        catalog=catalog,
        model=model,
        fit_summary_sha256=hashlib.sha256(summary_payload).hexdigest(),
    )


def build_goal_manager_promotion_receipt(
    *,
    candidate: AuthenticatedGoalManagerCandidate,
    batch: GoalManagerPromotionBatchResult,
    evaluation_source_commit: str,
    evaluation_source_bundle_sha256: str,
    prior_shadow_receipt_sha256: str | None = None,
    shadow_prerequisite_passed: bool = False,
) -> dict[str, object]:
    """Build one path-free gate result from a complete live batch."""

    from pokemon_red_completion.goal_manager_promotion_runtime import (
        GoalManagerPromotionBatchResult,
    )

    if not isinstance(batch, GoalManagerPromotionBatchResult):
        raise TypeError("batch must be a GoalManagerPromotionBatchResult")
    plan = candidate.plan
    if _GIT_OID.fullmatch(evaluation_source_commit) is None:
        raise GoalManagerPromotionError("goal-manager evaluation commit is invalid")
    _digest(evaluation_source_bundle_sha256, "evaluation source bundle")
    expected_slots = tuple(
        slot.slot_id for slot in candidate.registry.slots if slot.partition == "validation"
    )
    observed_slots = tuple(item.slot_id for item in batch.results)
    expected_count = (
        plan.required_shadow_contexts
        if batch.mode == "shadow"
        else plan.required_causal_contexts
    )
    expected_successes = (
        plan.required_shadow_successes
        if batch.mode == "shadow"
        else plan.required_causal_successes
    )
    if batch.mode == "shadow":
        if prior_shadow_receipt_sha256 is not None or shadow_prerequisite_passed:
            raise GoalManagerPromotionError("shadow evaluation cannot consume shadow evidence")
    else:
        if prior_shadow_receipt_sha256 is None:
            raise GoalManagerPromotionError("causal evaluation requires shadow evidence")
        _digest(prior_shadow_receipt_sha256, "shadow receipt digest")

    authority_correct = all(
        item.model_had_execution_authority is (batch.mode == "causal")
        and item.reference_had_execution_authority is (batch.mode == "shadow")
        for item in batch.results
    )
    checks = {
        "complete_validation_slot_order": observed_slots == expected_slots,
        "context_count": batch.evaluated_contexts == expected_count,
        "model_reference_agreement": (
            batch.agreements == plan.required_shadow_agreements
            if batch.mode == "shadow"
            else batch.agreements == expected_count
        ),
        "independent_execution_success": (
            batch.successful_contexts == expected_successes
        ),
        "minimum_confidence": batch.minimum_confidence >= plan.minimum_live_confidence,
        "authority_mode": authority_correct,
        "teacher_queries_zero": plan.maximum_teacher_queries == 0,
        "teacher_fallbacks_zero": plan.maximum_teacher_fallbacks == 0,
        "episodes_created_zero": plan.maximum_episodes_created == 0,
        "shadow_prerequisite": (
            True if batch.mode == "shadow" else shadow_prerequisite_passed
        ),
        "sealed_test_untouched": (
            plan.sealed_test_captures_opened == 0
            and plan.sealed_test_captures_evaluated == 0
        ),
    }
    passed = all(checks.values())
    return {
        "schema": GOAL_MANAGER_PROMOTION_RECEIPT_SCHEMA,
        "mode": batch.mode,
        "status": "passed" if passed else "rejected",
        "promotion_plan_sha256": plan.plan_sha256,
        "evaluation_source": {
            "git_commit": evaluation_source_commit,
            "source_bundle_sha256": evaluation_source_bundle_sha256,
        },
        "candidate": candidate.public_dict(),
        "prior_shadow_receipt_sha256": prior_shadow_receipt_sha256,
        "checks": checks,
        "gates": {
            "passed": passed,
            "causal_may_start": batch.mode == "shadow" and passed,
            "promotion_eligible": batch.mode == "causal" and passed,
        },
        "authority": {
            "model_had_execution_authority": batch.mode == "causal",
            "reference_had_execution_authority": batch.mode == "shadow",
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
        },
        "audit": batch.public_dict(),
        "held_out_test": {
            "captures": plan.sealed_test_captures,
            "opened": 0,
            "evaluated": 0,
            "status": "sealed_unopened",
        },
        "scope": {
            "establishes": "same-context-live-authority-integration",
            "does_not_establish": [
                "unseen-context-generalization",
                "cross-title-transfer",
                "end-to-end-game-completion",
            ],
        },
        "counted": False,
        "episodes_created": 0,
        "private_path_fields": 0,
    }


def authenticate_goal_manager_shadow_receipt(
    payload: bytes,
    *,
    expected_sha256: str,
    candidate: AuthenticatedGoalManagerCandidate,
) -> str:
    """Require a passed shadow receipt before granting causal authority."""

    _digest(expected_sha256, "shadow receipt digest")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise GoalManagerPromotionError("goal-manager shadow receipt failed authentication")
    receipt = _canonical_document(
        payload,
        maximum_bytes=4 * 1024 * 1024,
        subject="shadow receipt",
    )
    _exact_keys(
        receipt,
        {
            "audit",
            "authority",
            "candidate",
            "checks",
            "counted",
            "episodes_created",
            "evaluation_source",
            "gates",
            "held_out_test",
            "mode",
            "prior_shadow_receipt_sha256",
            "private_path_fields",
            "promotion_plan_sha256",
            "schema",
            "scope",
            "status",
        },
        "shadow receipt",
    )
    gates = _mapping(receipt.get("gates"), "shadow gates")
    authority = _mapping(receipt.get("authority"), "shadow authority")
    audit = _mapping(receipt.get("audit"), "shadow audit")
    held_out = _mapping(receipt.get("held_out_test"), "shadow held-out declaration")
    if (
        receipt.get("schema") != GOAL_MANAGER_PROMOTION_RECEIPT_SCHEMA
        or receipt.get("mode") != "shadow"
        or receipt.get("status") != "passed"
        or receipt.get("promotion_plan_sha256") != candidate.plan.plan_sha256
        or receipt.get("candidate") != candidate.public_dict()
        or receipt.get("prior_shadow_receipt_sha256") is not None
        or receipt.get("counted") is not False
        or receipt.get("episodes_created") != 0
        or receipt.get("private_path_fields") != 0
        or gates.get("passed") is not True
        or gates.get("causal_may_start") is not True
        or gates.get("promotion_eligible") is not False
        or authority.get("model_had_execution_authority") is not False
        or authority.get("reference_had_execution_authority") is not True
        or authority.get("teacher_queries") != 0
        or authority.get("teacher_fallbacks") != 0
        or audit.get("evaluated_contexts") != candidate.plan.required_shadow_contexts
        or audit.get("agreements") != candidate.plan.required_shadow_agreements
        or audit.get("successful_contexts") != candidate.plan.required_shadow_successes
        or held_out.get("opened") != 0
        or held_out.get("evaluated") != 0
    ):
        raise GoalManagerPromotionError("goal-manager shadow receipt is not causal-ready")
    return expected_sha256


def _require_fit_summary(
    summary: Mapping[str, object],
    plan: GoalManagerPromotionPlan,
) -> None:
    _exact_keys(
        summary,
        {
            "collection",
            "feature_schema",
            "fit",
            "held_out_titles",
            "model",
            "private_path_fields",
            "schema",
            "training",
            "validation",
            "validation_gate",
        },
        "fit summary",
    )
    if (
        summary.get("schema") != "pokemon-core-goal-manager-development-fit-v1"
        or summary.get("private_path_fields") != 0
    ):
        raise GoalManagerPromotionError("goal-manager fit summary identity differs")
    collection = _mapping(summary.get("collection"), "fit collection")
    status = _mapping(collection.get("collection_status"), "collection status")
    audit = _mapping(collection.get("curriculum_audit"), "curriculum audit")
    if (
        collection.get("collection_source_commit") != plan.training_source_commit
        or collection.get("registry_sha256") != plan.registry_sha256
        or collection.get("teacher_execution_sha256")
        != plan.teacher_execution_sha256
        or collection.get("context_catalog_sha256")
        != plan.context_catalog_sha256
        or collection.get("train_examples") != plan.train_examples
        or collection.get("validation_examples") != plan.validation_examples
        or status.get("ready_for_training") is not True
        or status.get("collected_slots") != plan.train_examples + plan.validation_examples
        or status.get("successful_teacher_slots")
        != plan.train_examples + plan.validation_examples
        or audit.get("ready_for_training") is not True
        or audit.get("train_validation_context_overlap_count") != 0
        or audit.get("replicated_teacher_choice_example_count") != 0
    ):
        raise GoalManagerPromotionError("goal-manager fit collection differs")

    feature = _mapping(summary.get("feature_schema"), "feature schema")
    if (
        feature.get("candidate_scoring") != "shared_per_candidate"
        or feature.get("candidate_order_used_as_feature") is not False
        or feature.get("private_binding_identity_used_as_feature") is not False
        or feature.get("title_identity_used_as_feature") is not False
        or feature.get("feature_count") != len(GOAL_MANAGER_FEATURE_NAMES)
        or feature.get("feature_names") != list(GOAL_MANAGER_FEATURE_NAMES)
    ):
        raise GoalManagerPromotionError("goal-manager feature schema differs")
    if summary.get("fit") != goal_manager_fit_configuration():
        raise GoalManagerPromotionError("goal-manager fit configuration differs")

    model = _mapping(summary.get("model"), "fit model")
    if model != {
        "canonical_sha256": plan.model_canonical_sha256,
        "file_sha256": plan.model_file_sha256,
        "model_id": plan.model_id,
    }:
        raise GoalManagerPromotionError("goal-manager fit model identity differs")
    training = _mapping(summary.get("training"), "training metrics")
    validation = _mapping(summary.get("validation"), "validation metrics")
    if (
        training.get("examples") != plan.train_examples
        or training.get("accuracy") != 1.0
        or validation.get("examples") != plan.validation_examples
        or not _at_least(
            validation.get("accuracy"), plan.minimum_offline_validation_accuracy
        )
    ):
        raise GoalManagerPromotionError("goal-manager fit metrics differ")
    per_kind = _mapping(validation.get("selected_kind_accuracy"), "per-kind metrics")
    if set(per_kind) != {kind.value for kind in GoalKind} or any(
        not _at_least(value, plan.minimum_each_kind_accuracy)
        for value in per_kind.values()
    ):
        raise GoalManagerPromotionError("goal-manager per-kind validation differs")
    gate = _mapping(summary.get("validation_gate"), "validation gate")
    if (
        not gate
        or gate.get("passed") is not True
        or any(value is not True for value in gate.values())
    ):
        raise GoalManagerPromotionError("goal-manager validation gate did not pass")
    if summary.get("held_out_titles") != {
        "evaluated": False,
        "next_environment": "pokemon.mainline:crystal",
        "opened": False,
    }:
        raise GoalManagerPromotionError("held-out title declaration differs")


def _read_regular(
    path: Path,
    *,
    expected_sha256: str,
    maximum_bytes: int,
    subject: str,
) -> bytes:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        raise GoalManagerPromotionError(f"goal-manager {subject} is unavailable") from None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise GoalManagerPromotionError(f"goal-manager {subject} must be a regular file")
    if not payload or len(payload) > maximum_bytes:
        raise GoalManagerPromotionError(f"goal-manager {subject} size is invalid")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise GoalManagerPromotionError(f"goal-manager {subject} failed authentication")
    return payload


def _canonical_document(
    payload: bytes,
    *,
    maximum_bytes: int,
    subject: str,
) -> Mapping[str, object]:
    if not isinstance(payload, bytes) or not payload or len(payload) > maximum_bytes:
        raise GoalManagerPromotionError(f"goal-manager {subject} size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise GoalManagerPromotionError(
            f"goal-manager {subject} is not canonical ASCII JSON"
        ) from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise GoalManagerPromotionError(
            f"goal-manager {subject} is not canonical ASCII JSON"
        )
    return value


def _canonical_line(value: object) -> bytes:
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


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GoalManagerPromotionError(f"goal-manager {subject} must be an object")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], subject: str) -> None:
    if set(value) != expected:
        raise GoalManagerPromotionError(f"goal-manager {subject} fields differ")


def _safe_id(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise GoalManagerPromotionError(f"goal-manager {subject} is invalid")
    return value


def _digest(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise GoalManagerPromotionError(f"goal-manager {subject} is invalid")
    return value


def _exact_integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise GoalManagerPromotionError(f"goal-manager {subject} is invalid")
    return value


def _probability(value: object, subject: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise GoalManagerPromotionError(f"goal-manager {subject} is invalid")
    return float(value)


def _at_least(value: object, minimum: float) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= minimum
    )


def _git(root: Path, arguments: list[str]) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise GoalManagerPromotionError(
            "goal-manager committed promotion artifact is unavailable"
        ) from None
    if len(result.stdout) > _MAX_GIT_BYTES:
        raise GoalManagerPromotionError(
            "goal-manager committed promotion artifact is too large"
        )
    return result.stdout


__all__ = [
    "AuthenticatedGoalManagerCandidate",
    "GOAL_MANAGER_PROMOTION_PLAN_RELATIVE_PATH",
    "GOAL_MANAGER_PROMOTION_PLAN_SCHEMA",
    "GOAL_MANAGER_PROMOTION_RECEIPT_SCHEMA",
    "GoalManagerPromotionError",
    "GoalManagerPromotionPlan",
    "authenticate_goal_manager_candidate",
    "authenticate_goal_manager_shadow_receipt",
    "build_goal_manager_promotion_receipt",
    "load_committed_goal_manager_promotion_plan",
    "parse_goal_manager_promotion_plan",
]
