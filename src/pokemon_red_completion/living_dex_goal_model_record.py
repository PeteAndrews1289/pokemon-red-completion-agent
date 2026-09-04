"""Strict loader for the private causal living-Dex integration model record."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel

LIVING_DEX_CAUSAL_INTEGRATION_MODEL_RECORD_SCHEMA = (
    "pokemon.core.private-living-dex-causal-integration-model.v1"
)
_AUTHORITY = "non_authoritative_integration_only"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_RECORD_FIELDS = {
    "authority",
    "claim_manifest_sha256",
    "claim_record_sha256",
    "diagnostics",
    "model",
    "model_sha256",
    "readiness_result_sha256",
    "schema",
    "source",
    "train_dataset_sha256",
}
_SOURCE_FIELDS = {
    "exact_ci_attempt",
    "exact_ci_run",
    "source_bundle_sha256",
    "source_commit",
}
_DIAGNOSTIC_FIELDS = {
    "coefficient_count",
    "finite_coefficient_count",
    "normal_equation_condition_number",
}


class LivingDexGoalModelRecordError(ValueError):
    """A private causal model record failed identity or schema validation."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LivingDexGoalModelRecordError("causal model record has duplicate fields")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise LivingDexGoalModelRecordError("causal model record has a non-finite number")


@dataclass(frozen=True, slots=True)
class LivingDexGoalModelRecord:
    """Validated model plus the provenance safe to expose in a receipt."""

    model: LivingDexOptionValueModel
    file_sha256: str
    source_commit: str
    source_bundle_sha256: str
    exact_ci_run: int
    exact_ci_attempt: int

    def __post_init__(self) -> None:
        if not isinstance(self.model, LivingDexOptionValueModel):
            raise TypeError("causal model record needs a living-Dex model")
        if (
            _SHA256.fullmatch(self.file_sha256) is None
            or _GIT_COMMIT.fullmatch(self.source_commit) is None
            or _SHA256.fullmatch(self.source_bundle_sha256) is None
            or type(self.exact_ci_run) is not int  # noqa: E721
            or self.exact_ci_run <= 0
            or type(self.exact_ci_attempt) is not int  # noqa: E721
            or self.exact_ci_attempt <= 0
        ):
            raise LivingDexGoalModelRecordError("causal model provenance differs")

    def public_dict(self) -> dict[str, object]:
        return {
            "authority": _AUTHORITY,
            "exact_ci_attempt": self.exact_ci_attempt,
            "exact_ci_run": self.exact_ci_run,
            "file_sha256": self.file_sha256,
            "model_sha256": self.model.model_sha256,
            "private_path_fields": 0,
            "settled_examples": self.model.settled_examples,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "train_dataset_sha256": self.model.train_dataset_sha256,
        }


def load_living_dex_goal_model_record(
    path: Path,
    *,
    expected_model_sha256: str,
) -> LivingDexGoalModelRecord:
    """Load one exact non-authoritative integration model and fail closed."""

    if not isinstance(path, Path):
        raise TypeError("causal model record path must be a Path")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise LivingDexGoalModelRecordError("causal model record is unreadable") from error
    return load_living_dex_goal_model_record_bytes(
        payload,
        expected_model_sha256=expected_model_sha256,
    )


def load_living_dex_goal_model_record_bytes(
    payload: bytes,
    *,
    expected_model_sha256: str,
) -> LivingDexGoalModelRecord:
    """Authenticate an immutable in-memory model record without a path round trip."""

    if not isinstance(payload, bytes):
        raise TypeError("causal model record payload must be bytes")
    if (
        not isinstance(expected_model_sha256, str)
        or _SHA256.fullmatch(expected_model_sha256) is None
    ):
        raise LivingDexGoalModelRecordError("expected causal model identity differs")
    try:
        decoded = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise LivingDexGoalModelRecordError("causal model record is unreadable") from error
    if not isinstance(decoded, Mapping) or set(decoded) != _RECORD_FIELDS:
        raise LivingDexGoalModelRecordError("causal model record fields differ")
    if decoded["schema"] != LIVING_DEX_CAUSAL_INTEGRATION_MODEL_RECORD_SCHEMA:
        raise LivingDexGoalModelRecordError("causal model record schema differs")
    if decoded["authority"] != _AUTHORITY:
        raise LivingDexGoalModelRecordError("causal model authority differs")
    diagnostics = decoded["diagnostics"]
    if not isinstance(diagnostics, Mapping) or set(diagnostics) != _DIAGNOSTIC_FIELDS:
        raise LivingDexGoalModelRecordError("causal model diagnostics differ")
    coefficient_count = diagnostics["coefficient_count"]
    finite_coefficient_count = diagnostics["finite_coefficient_count"]
    condition_number = diagnostics["normal_equation_condition_number"]
    if (
        type(coefficient_count) is not int  # noqa: E721
        or coefficient_count <= 0
        or type(finite_coefficient_count) is not int  # noqa: E721
        or finite_coefficient_count != coefficient_count
        or isinstance(condition_number, bool)
        or not isinstance(condition_number, (int, float))
        or not math.isfinite(float(condition_number))
        or float(condition_number) <= 0.0
    ):
        raise LivingDexGoalModelRecordError("causal model diagnostics differ")
    for field_name in (
        "claim_manifest_sha256",
        "claim_record_sha256",
        "readiness_result_sha256",
        "train_dataset_sha256",
        "model_sha256",
    ):
        value = decoded[field_name]
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise LivingDexGoalModelRecordError(f"causal model {field_name} differs")
    model_document = decoded["model"]
    if not isinstance(model_document, Mapping):
        raise LivingDexGoalModelRecordError("causal model document differs")
    try:
        model = LivingDexOptionValueModel.from_dict(model_document)
    except (TypeError, ValueError) as error:
        raise LivingDexGoalModelRecordError("causal model document differs") from error
    if (
        model.model_sha256 != decoded["model_sha256"]
        or model.model_sha256 != expected_model_sha256
        or model.train_dataset_sha256 != decoded["train_dataset_sha256"]
    ):
        raise LivingDexGoalModelRecordError("causal model identity join differs")
    source = decoded["source"]
    if not isinstance(source, Mapping) or set(source) != _SOURCE_FIELDS:
        raise LivingDexGoalModelRecordError("causal model source fields differ")
    source_commit = source["source_commit"]
    source_bundle_sha256 = source["source_bundle_sha256"]
    exact_ci_run = source["exact_ci_run"]
    exact_ci_attempt = source["exact_ci_attempt"]
    if (
        not isinstance(source_commit, str)
        or not isinstance(source_bundle_sha256, str)
        or type(exact_ci_run) is not int  # noqa: E721
        or type(exact_ci_attempt) is not int  # noqa: E721
    ):
        raise LivingDexGoalModelRecordError("causal model source identity differs")
    return LivingDexGoalModelRecord(
        model=model,
        file_sha256=hashlib.sha256(payload).hexdigest(),
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        exact_ci_run=exact_ci_run,
        exact_ci_attempt=exact_ci_attempt,
    )


__all__ = [
    "LIVING_DEX_CAUSAL_INTEGRATION_MODEL_RECORD_SCHEMA",
    "LivingDexGoalModelRecord",
    "LivingDexGoalModelRecordError",
    "load_living_dex_goal_model_record",
    "load_living_dex_goal_model_record_bytes",
]
