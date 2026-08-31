"""Canonical one-shot contract for one bounded Red battle model update.

The contract is deliberately smaller than a campaign framework.  It binds one
authenticated train capture and one prospectively held development capture to
the exact published source, prior, runtime, objective, and upstream catalog
identities.  It contains no paths, outcomes, predictions, or preferred actions.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import BattleFeatureBatch
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcome_adapters import BATTLE_TURN_OBJECTIVE

BATTLE_OUTCOME_EXPERIMENT_PLAN_SCHEMA = (
    "pokemon-red-battle-outcome-experiment-plan-v1"
)
BATTLE_OUTCOME_EXPERIMENT_CAPTURE_SCHEMA = (
    "pokemon-red-battle-outcome-experiment-capture-v1"
)
FROZEN_BATTLE_OUTCOME_EPOCHS = 100
FROZEN_BATTLE_OUTCOME_LEARNING_RATE = 0.01
FROZEN_BATTLE_OUTCOME_PRIOR_L2 = 0.1

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_PLAN_BYTES = 128 * 1024
_PROTECTIONS = {
    "authority_promoted": False,
    "crystal_contexts_opened": 0,
    "development_influences_fit": False,
    "development_predictions_before_outcomes": True,
    "full_game_replays": 0,
    "materializer_derivation_claimed": False,
    "red_sealed_test_cases_opened": 0,
    "teacher_choice_targets": 0,
    "teacher_queries": 0,
}


class BattleOutcomeExperimentError(ValueError):
    """Raised when a prospective battle experiment can drift or be replayed."""


def battle_outcome_controller_timing_sha256() -> str:
    """Bind the exact macro controller timing used by every candidate replay."""

    return canonical_sha256(
        {
            "schema": "pokemon.red.battle-outcome-controller-timing.v1",
            "controller_timing": asdict(
                DEFAULT_NEW_GAME_TIMING.controller_timing()
            ),
        }
    )


def battle_outcome_menu_sha256(features: BattleFeatureBatch) -> str:
    """Bind the exact title-neutral candidate menu visible before outcomes."""

    if not isinstance(features, BattleFeatureBatch):
        raise TypeError("battle outcome menu requires a BattleFeatureBatch")
    return canonical_sha256(
        {
            "candidate_vectors": features.candidate_vectors,
            "current_pp": features.current_pp,
            "feature_names": features.feature_names,
            "legal_mask": features.legal_mask,
            "schema": "pokemon.red.battle-outcome-menu.v1",
            "schema_id": features.schema_id,
            "slot_indices": features.slot_indices,
        }
    )


def battle_outcome_supported_hidden_embeddings(
    model: MaskedMLPMoveRanker,
    features: BattleFeatureBatch,
) -> tuple[tuple[float, ...], ...]:
    """Return the frozen representation only for candidates the cycle executes."""

    if not isinstance(model, MaskedMLPMoveRanker):
        raise TypeError("battle outcome hidden menu requires the nonlinear prior")
    if not isinstance(features, BattleFeatureBatch):
        raise TypeError("battle outcome hidden menu requires a BattleFeatureBatch")
    if (
        features.feature_names != model.feature_names
        or features.schema_id != model.feature_schema_id
    ):
        raise BattleOutcomeExperimentError(
            "battle menu feature schema differs from the frozen prior"
        )
    hidden = model.hidden_embeddings(features.candidate_vectors)
    return tuple(
        tuple(float(value) for value in hidden[index])
        for index, (legal, pp) in enumerate(
            zip(features.legal_mask, features.current_pp, strict=True)
        )
        if legal and pp > 0
    )


def battle_outcome_hidden_menu_sha256(
    model: MaskedMLPMoveRanker,
    features: BattleFeatureBatch,
) -> str:
    """Bind the exact supported hidden embeddings of the frozen nonlinear prior."""

    return canonical_sha256(
        {
            "embeddings": battle_outcome_supported_hidden_embeddings(model, features),
            "schema": "pokemon.red.battle-outcome-hidden-menu.v1",
        }
    )


def battle_outcome_distinct_hidden_embedding_count(
    model: MaskedMLPMoveRanker,
    features: BattleFeatureBatch,
    *,
    absolute_tolerance: float = 1e-9,
) -> int:
    """Count numerically distinguishable supported representations."""

    if (
        isinstance(absolute_tolerance, bool)
        or not isinstance(absolute_tolerance, (int, float))
        or not math.isfinite(absolute_tolerance)
        or absolute_tolerance <= 0
    ):
        raise ValueError("hidden embedding tolerance must be finite and positive")
    embeddings = battle_outcome_supported_hidden_embeddings(model, features)
    representatives: list[tuple[float, ...]] = []
    for embedding in embeddings:
        if not any(
            all(
                abs(observed - expected) <= absolute_tolerance
                for observed, expected in zip(
                    embedding,
                    representative,
                    strict=True,
                )
            )
            for representative in representatives
        ):
            representatives.append(embedding)
    return len(representatives)


@dataclass(frozen=True, slots=True)
class BattleOutcomeCaptureBinding:
    partition: ScenarioPartition
    capture_id: str
    manifest_sha256: str
    state_sha256: str
    initial_observation_sha256: str
    source_commit: str
    source_state_sha256: str
    source_slot_id: str
    source_assignment_id: str
    source_context_id: str
    source_envelope_sha256: str
    root_lineage_id: str
    root_consumption_sha256: str
    menu_sha256: str
    supported_candidate_count: int
    distinct_candidate_vector_count: int
    hidden_embedding_sha256: str
    distinct_hidden_embedding_count: int
    expected_map: int
    expected_battle_state: int

    def __post_init__(self) -> None:
        if self.partition not in {
            ScenarioPartition.TRAIN,
            ScenarioPartition.DEVELOPMENT,
        }:
            raise BattleOutcomeExperimentError("capture partition is invalid")
        for value, subject in (
            (self.capture_id, "capture identity"),
            (self.source_slot_id, "source slot"),
            (self.root_lineage_id, "root lineage"),
        ):
            _require_safe_id(value, subject)
        for value, subject in (
            (self.manifest_sha256, "capture manifest"),
            (self.state_sha256, "capture state"),
            (self.initial_observation_sha256, "initial observation"),
            (self.source_state_sha256, "source state"),
            (self.source_assignment_id, "source assignment"),
            (self.source_context_id, "source context"),
            (self.source_envelope_sha256, "source envelope"),
            (self.root_consumption_sha256, "root consumption"),
            (self.menu_sha256, "battle menu"),
            (self.hidden_embedding_sha256, "hidden embedding menu"),
        ):
            _require_sha256(value, subject)
        _require_commit(self.source_commit, "capture source")
        if self.root_lineage_id != f"red-goal-root-{self.source_assignment_id}":
            raise BattleOutcomeExperimentError(
                "capture root lineage differs from its catalog assignment"
            )
        expected_consumption = root_consumption_sha256(
            state_sha256=self.source_state_sha256,
            envelope_sha256=self.source_envelope_sha256,
        )
        if self.root_consumption_sha256 != expected_consumption:
            raise BattleOutcomeExperimentError(
                "capture root consumption differs from its upstream bytes"
            )
        if self.root_consumption_sha256 == self.state_sha256:
            raise BattleOutcomeExperimentError(
                "capture logical and physical root identities collapse"
            )
        if type(self.expected_map) is not int or not 0 <= self.expected_map <= 0xFF:  # noqa: E721
            raise BattleOutcomeExperimentError("capture expected map is invalid")
        if (
            type(self.supported_candidate_count) is not int  # noqa: E721
            or not 2 <= self.supported_candidate_count <= 4
        ):
            raise BattleOutcomeExperimentError(
                "battle experiment requires two to four supported candidates"
            )
        if (
            type(self.distinct_candidate_vector_count) is not int  # noqa: E721
            or not 2
            <= self.distinct_candidate_vector_count
            <= self.supported_candidate_count
        ):
            raise BattleOutcomeExperimentError(
                "battle experiment requires two distinct candidate vectors"
            )
        if (
            type(self.distinct_hidden_embedding_count) is not int  # noqa: E721
            or not 2
            <= self.distinct_hidden_embedding_count
            <= self.supported_candidate_count
        ):
            raise BattleOutcomeExperimentError(
                "battle experiment requires two distinct hidden embeddings"
            )
        if self.expected_battle_state != 1:
            raise BattleOutcomeExperimentError(
                "bounded battle experiment requires a wild-battle capture"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": BATTLE_OUTCOME_EXPERIMENT_CAPTURE_SCHEMA,
            "partition": self.partition.value,
            "capture_id": self.capture_id,
            "manifest_sha256": self.manifest_sha256,
            "state_sha256": self.state_sha256,
            "initial_observation_sha256": self.initial_observation_sha256,
            "source_commit": self.source_commit,
            "source_state_sha256": self.source_state_sha256,
            "source_slot_id": self.source_slot_id,
            "source_assignment_id": self.source_assignment_id,
            "source_context_id": self.source_context_id,
            "source_envelope_sha256": self.source_envelope_sha256,
            "root_lineage_id": self.root_lineage_id,
            "root_consumption_sha256": self.root_consumption_sha256,
            "menu_sha256": self.menu_sha256,
            "supported_candidate_count": self.supported_candidate_count,
            "distinct_candidate_vector_count": self.distinct_candidate_vector_count,
            "hidden_embedding_sha256": self.hidden_embedding_sha256,
            "distinct_hidden_embedding_count": self.distinct_hidden_embedding_count,
            "expected_map": self.expected_map,
            "expected_battle_state": self.expected_battle_state,
        }

    @property
    def logical_root_sha256(self) -> str:
        """Return the authenticated upstream catalog-consumption identity."""

        return self.root_consumption_sha256

    @property
    def physical_root_sha256(self) -> str:
        """Return the digest of the exact materialized battle-state bytes."""

        return self.state_sha256


@dataclass(frozen=True, slots=True)
class BattleOutcomeExperimentPlan:
    experiment_id: str
    source_commit: str
    source_bundle_sha256: str
    runner_sha256: str
    materializer_sha256: str
    registry_source_commit: str
    registry_source_bundle_sha256: str
    registry_sha256: str
    context_catalog_sha256: str
    rom_sha256: str
    runtime_identity_sha256: str
    numpy_runtime_sha256: str
    base_model_sha256: str
    controller_timing_sha256: str
    captures: tuple[BattleOutcomeCaptureBinding, BattleOutcomeCaptureBinding]
    epochs: int = FROZEN_BATTLE_OUTCOME_EPOCHS
    learning_rate: float = FROZEN_BATTLE_OUTCOME_LEARNING_RATE
    prior_l2: float = FROZEN_BATTLE_OUTCOME_PRIOR_L2
    objective_id: str = BATTLE_TURN_OBJECTIVE.objective_id
    objective_sha256: str = BATTLE_TURN_OBJECTIVE.objective_sha256

    def __post_init__(self) -> None:
        _require_safe_id(self.experiment_id, "experiment identity")
        _require_commit(self.source_commit, "experiment source")
        _require_commit(self.registry_source_commit, "registry source")
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.runner_sha256, "runner"),
            (self.materializer_sha256, "materializer"),
            (self.registry_source_bundle_sha256, "registry source bundle"),
            (self.registry_sha256, "registry"),
            (self.context_catalog_sha256, "context catalog"),
            (self.rom_sha256, "ROM"),
            (self.runtime_identity_sha256, "runtime identity"),
            (self.numpy_runtime_sha256, "NumPy runtime"),
            (self.base_model_sha256, "base model"),
            (self.controller_timing_sha256, "controller timing"),
            (self.objective_sha256, "outcome objective"),
        ):
            _require_sha256(value, subject)
        if (
            self.objective_id != BATTLE_TURN_OBJECTIVE.objective_id
            or self.objective_sha256 != BATTLE_TURN_OBJECTIVE.objective_sha256
        ):
            raise BattleOutcomeExperimentError("outcome objective differs")
        if (
            self.epochs != FROZEN_BATTLE_OUTCOME_EPOCHS
            or self.learning_rate != FROZEN_BATTLE_OUTCOME_LEARNING_RATE
            or self.prior_l2 != FROZEN_BATTLE_OUTCOME_PRIOR_L2
        ):
            raise BattleOutcomeExperimentError("fit hyperparameters differ")
        if (
            not isinstance(self.captures, tuple)
            or len(self.captures) != 2
            or any(
                not isinstance(capture, BattleOutcomeCaptureBinding)
                for capture in self.captures
            )
            or tuple(capture.partition for capture in self.captures)
            != (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT)
        ):
            raise BattleOutcomeExperimentError(
                "experiment requires one ordered train/development capture pair"
            )
        if any(capture.source_commit != self.source_commit for capture in self.captures):
            raise BattleOutcomeExperimentError(
                "capture source differs from experiment source"
            )
        for attribute, subject in (
            ("capture_id", "capture identity"),
            ("manifest_sha256", "capture manifest"),
            ("state_sha256", "capture state"),
            ("initial_observation_sha256", "initial observation"),
            ("source_state_sha256", "source state"),
            ("source_slot_id", "source slot"),
            ("source_assignment_id", "source assignment"),
            ("source_context_id", "source context"),
            ("source_envelope_sha256", "source envelope"),
            ("root_lineage_id", "root lineage"),
            ("root_consumption_sha256", "root consumption"),
        ):
            values = tuple(getattr(capture, attribute) for capture in self.captures)
            if len(set(values)) != len(values):
                raise BattleOutcomeExperimentError(
                    f"train and development repeat a {subject}"
                )

    @property
    def train(self) -> BattleOutcomeCaptureBinding:
        return self.captures[0]

    @property
    def development(self) -> BattleOutcomeCaptureBinding:
        return self.captures[1]

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def plan_consumption_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": "pokemon.red.battle-outcome-plan-consumption.v1",
                "plan_sha256": self.plan_sha256,
            }
        )

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": BATTLE_OUTCOME_EXPERIMENT_PLAN_SCHEMA,
            "status": "prospective_unexecuted",
            "experiment_id": self.experiment_id,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "runner_sha256": self.runner_sha256,
            "materializer_sha256": self.materializer_sha256,
            "registry_source_commit": self.registry_source_commit,
            "registry_source_bundle_sha256": self.registry_source_bundle_sha256,
            "registry_sha256": self.registry_sha256,
            "context_catalog_sha256": self.context_catalog_sha256,
            "rom_sha256": self.rom_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "numpy_runtime_sha256": self.numpy_runtime_sha256,
            "base_model_sha256": self.base_model_sha256,
            "objective_id": self.objective_id,
            "objective_sha256": self.objective_sha256,
            "controller_timing_sha256": self.controller_timing_sha256,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "prior_l2": self.prior_l2,
            "captures": [capture.public_dict() for capture in self.captures],
            "protections": dict(_PROTECTIONS),
            "private_path_fields": 0,
        }


def build_battle_outcome_experiment_plan_payload(
    plan: BattleOutcomeExperimentPlan,
) -> bytes:
    """Return canonical bytes only for a fully validated prospective plan."""

    if not isinstance(plan, BattleOutcomeExperimentPlan):
        raise TypeError("plan must be a BattleOutcomeExperimentPlan")
    plan.__post_init__()
    return plan.canonical_bytes()


def parse_battle_outcome_experiment_plan(
    payload: bytes,
) -> BattleOutcomeExperimentPlan:
    """Strictly reopen one canonical path-free experiment plan."""

    if not isinstance(payload, bytes):
        raise TypeError("battle outcome experiment plan must be bytes")
    if not payload or len(payload) > _MAXIMUM_PLAN_BYTES:
        raise BattleOutcomeExperimentError("experiment plan size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleOutcomeExperimentError("experiment plan is not canonical JSON") from None
    expected_fields = {
        "schema",
        "status",
        "experiment_id",
        "source_commit",
        "source_bundle_sha256",
        "runner_sha256",
        "materializer_sha256",
        "registry_source_commit",
        "registry_source_bundle_sha256",
        "registry_sha256",
        "context_catalog_sha256",
        "rom_sha256",
        "runtime_identity_sha256",
        "numpy_runtime_sha256",
        "base_model_sha256",
        "objective_id",
        "objective_sha256",
        "controller_timing_sha256",
        "epochs",
        "learning_rate",
        "prior_l2",
        "captures",
        "protections",
        "private_path_fields",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected_fields
        or value.get("schema") != BATTLE_OUTCOME_EXPERIMENT_PLAN_SCHEMA
        or value.get("status") != "prospective_unexecuted"
        or value.get("protections") != _PROTECTIONS
        or value.get("private_path_fields") != 0
    ):
        raise BattleOutcomeExperimentError("experiment plan fields differ")
    raw_captures = value.get("captures")
    if not isinstance(raw_captures, list) or len(raw_captures) != 2:
        raise BattleOutcomeExperimentError("experiment capture bindings differ")
    plan = BattleOutcomeExperimentPlan(
        experiment_id=_string(value.get("experiment_id"), "experiment identity"),
        source_commit=_string(value.get("source_commit"), "experiment source"),
        source_bundle_sha256=_string(value.get("source_bundle_sha256"), "source bundle"),
        runner_sha256=_string(value.get("runner_sha256"), "runner"),
        materializer_sha256=_string(
            value.get("materializer_sha256"), "materializer"
        ),
        registry_source_commit=_string(
            value.get("registry_source_commit"), "registry source"
        ),
        registry_source_bundle_sha256=_string(
            value.get("registry_source_bundle_sha256"),
            "registry source bundle",
        ),
        registry_sha256=_string(value.get("registry_sha256"), "registry"),
        context_catalog_sha256=_string(
            value.get("context_catalog_sha256"), "context catalog"
        ),
        rom_sha256=_string(value.get("rom_sha256"), "ROM"),
        runtime_identity_sha256=_string(
            value.get("runtime_identity_sha256"), "runtime identity"
        ),
        numpy_runtime_sha256=_string(
            value.get("numpy_runtime_sha256"), "NumPy runtime"
        ),
        base_model_sha256=_string(value.get("base_model_sha256"), "base model"),
        controller_timing_sha256=_string(
            value.get("controller_timing_sha256"), "controller timing"
        ),
        captures=tuple(_parse_capture(item) for item in raw_captures),  # type: ignore[arg-type]
        epochs=_integer(value.get("epochs"), "epochs"),
        learning_rate=_number(value.get("learning_rate"), "learning rate"),
        prior_l2=_number(value.get("prior_l2"), "prior L2"),
        objective_id=_string(value.get("objective_id"), "objective identity"),
        objective_sha256=_string(value.get("objective_sha256"), "objective"),
    )
    if plan.canonical_bytes() != payload:
        raise BattleOutcomeExperimentError("experiment plan is not canonical JSON")
    return plan


def _parse_capture(value: object) -> BattleOutcomeCaptureBinding:
    fields = {
        "schema",
        "partition",
        "capture_id",
        "manifest_sha256",
        "state_sha256",
        "initial_observation_sha256",
        "source_commit",
        "source_state_sha256",
        "source_slot_id",
        "source_assignment_id",
        "source_context_id",
        "source_envelope_sha256",
        "root_lineage_id",
        "root_consumption_sha256",
        "menu_sha256",
        "supported_candidate_count",
        "distinct_candidate_vector_count",
        "hidden_embedding_sha256",
        "distinct_hidden_embedding_count",
        "expected_map",
        "expected_battle_state",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema") != BATTLE_OUTCOME_EXPERIMENT_CAPTURE_SCHEMA
    ):
        raise BattleOutcomeExperimentError("experiment capture fields differ")
    try:
        partition = ScenarioPartition(value["partition"])
    except (KeyError, TypeError, ValueError):
        raise BattleOutcomeExperimentError("experiment capture partition differs") from None
    return BattleOutcomeCaptureBinding(
        partition=partition,
        capture_id=_string(value.get("capture_id"), "capture identity"),
        manifest_sha256=_string(value.get("manifest_sha256"), "capture manifest"),
        state_sha256=_string(value.get("state_sha256"), "capture state"),
        initial_observation_sha256=_string(
            value.get("initial_observation_sha256"), "initial observation"
        ),
        source_commit=_string(value.get("source_commit"), "capture source"),
        source_state_sha256=_string(value.get("source_state_sha256"), "source state"),
        source_slot_id=_string(value.get("source_slot_id"), "source slot"),
        source_assignment_id=_string(
            value.get("source_assignment_id"), "source assignment"
        ),
        source_context_id=_string(value.get("source_context_id"), "source context"),
        source_envelope_sha256=_string(
            value.get("source_envelope_sha256"), "source envelope"
        ),
        root_lineage_id=_string(value.get("root_lineage_id"), "root lineage"),
        root_consumption_sha256=_string(
            value.get("root_consumption_sha256"), "root consumption"
        ),
        menu_sha256=_string(value.get("menu_sha256"), "battle menu"),
        supported_candidate_count=_integer(
            value.get("supported_candidate_count"),
            "supported candidate count",
        ),
        distinct_candidate_vector_count=_integer(
            value.get("distinct_candidate_vector_count"),
            "distinct candidate vector count",
        ),
        hidden_embedding_sha256=_string(
            value.get("hidden_embedding_sha256"),
            "hidden embedding menu",
        ),
        distinct_hidden_embedding_count=_integer(
            value.get("distinct_hidden_embedding_count"),
            "distinct hidden embedding count",
        ),
        expected_map=_integer(value.get("expected_map"), "expected map"),
        expected_battle_state=_integer(
            value.get("expected_battle_state"), "expected battle state"
        ),
    )


def parse_battle_outcome_capture_binding(
    value: object,
) -> BattleOutcomeCaptureBinding:
    """Strictly parse one canonical capture binding embedded by another contract."""

    return _parse_capture(value)


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
        raise BattleOutcomeExperimentError(f"{subject} is invalid")
    return value


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleOutcomeExperimentError(f"{subject} digest is invalid")
    return value


def _require_commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleOutcomeExperimentError(f"{subject} commit is invalid")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str):
        raise BattleOutcomeExperimentError(f"{subject} must be a string")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise BattleOutcomeExperimentError(f"{subject} must be a non-negative integer")
    return value


def _number(value: object, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BattleOutcomeExperimentError(f"{subject} must be numeric")
    return float(value)


__all__ = [
    "BATTLE_OUTCOME_EXPERIMENT_CAPTURE_SCHEMA",
    "BATTLE_OUTCOME_EXPERIMENT_PLAN_SCHEMA",
    "FROZEN_BATTLE_OUTCOME_EPOCHS",
    "FROZEN_BATTLE_OUTCOME_LEARNING_RATE",
    "FROZEN_BATTLE_OUTCOME_PRIOR_L2",
    "BattleOutcomeCaptureBinding",
    "BattleOutcomeExperimentError",
    "BattleOutcomeExperimentPlan",
    "battle_outcome_controller_timing_sha256",
    "battle_outcome_distinct_hidden_embedding_count",
    "battle_outcome_hidden_menu_sha256",
    "battle_outcome_menu_sha256",
    "battle_outcome_supported_hidden_embeddings",
    "build_battle_outcome_experiment_plan_payload",
    "parse_battle_outcome_capture_binding",
    "parse_battle_outcome_experiment_plan",
]
