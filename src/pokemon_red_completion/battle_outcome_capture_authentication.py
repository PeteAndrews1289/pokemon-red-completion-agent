"""Shared path-free authentication for one bounded battle learning capture."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_experiment import (
    BattleOutcomeCaptureBinding,
    BattleOutcomeExperimentError,
    battle_outcome_distinct_hidden_embedding_count,
    battle_outcome_hidden_menu_sha256,
    battle_outcome_menu_sha256,
)
from pokemon_red_completion.battle_scenario_capture import BattleScenarioCapture
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalog,
)
from pokemon_red_completion.goal_manager_protocol import GoalManagerCollectionRegistry
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.scenario_lab import ScenarioPartition

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")


class BattleOutcomeCaptureAuthenticationError(ValueError):
    """Raised when capture, catalog, feature, and prior identities do not join."""


@dataclass(frozen=True, slots=True)
class BattleScenarioSourceBinding:
    """Catalog-derived upstream identity for one battle-boundary materialization.

    The caller supplies only authenticated source-state bytes.  Partition,
    lineage, assignment, and envelope identity come from the frozen catalog
    and its historical registry; they are never accepted as materializer
    labels.
    """

    partition: ScenarioPartition
    source_state_sha256: str
    source_slot_id: str
    source_assignment_id: str
    source_context_id: str
    source_envelope_sha256: str
    root_lineage_id: str
    root_consumption_sha256: str
    catalog_sha256: str
    registry_sha256: str
    registry_source_commit: str

    def __post_init__(self) -> None:
        if self.partition not in {
            ScenarioPartition.TRAIN,
            ScenarioPartition.DEVELOPMENT,
        }:
            raise BattleOutcomeCaptureAuthenticationError("battle source partition is unsupported")
        for value, subject in (
            (self.source_state_sha256, "source state"),
            (self.source_assignment_id, "source assignment"),
            (self.source_context_id, "source context"),
            (self.source_envelope_sha256, "source envelope"),
            (self.root_consumption_sha256, "root consumption"),
            (self.catalog_sha256, "context catalog"),
            (self.registry_sha256, "goal-manager registry"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise BattleOutcomeCaptureAuthenticationError(f"battle {subject} identity differs")
        for value, subject in (
            (self.source_slot_id, "source slot"),
            (self.root_lineage_id, "root lineage"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise BattleOutcomeCaptureAuthenticationError(f"battle {subject} identity differs")
        if (
            not isinstance(self.registry_source_commit, str)
            or _GIT_COMMIT.fullmatch(self.registry_source_commit) is None
        ):
            raise BattleOutcomeCaptureAuthenticationError("battle registry source commit differs")
        if self.root_lineage_id != f"red-goal-root-{self.source_assignment_id}":
            raise BattleOutcomeCaptureAuthenticationError("battle source catalog lineage differs")
        expected_consumption = root_consumption_sha256(
            state_sha256=self.source_state_sha256,
            envelope_sha256=self.source_envelope_sha256,
        )
        if self.root_consumption_sha256 != expected_consumption:
            raise BattleOutcomeCaptureAuthenticationError("battle source upstream bytes differ")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.battle-scenario-source-binding.v1",
            "partition": self.partition.value,
            "source_state_sha256": self.source_state_sha256,
            "source_slot_id": self.source_slot_id,
            "source_assignment_id": self.source_assignment_id,
            "source_context_id": self.source_context_id,
            "source_envelope_sha256": self.source_envelope_sha256,
            "root_lineage_id": self.root_lineage_id,
            "root_consumption_sha256": self.root_consumption_sha256,
            "catalog_sha256": self.catalog_sha256,
            "registry_sha256": self.registry_sha256,
            "registry_source_commit": self.registry_source_commit,
            "caller_supplied_partition": False,
            "caller_supplied_lineage": False,
            "private_path_fields": 0,
        }


def authenticate_battle_scenario_source_binding(
    source_state_sha256: str,
    *,
    expected_partition: ScenarioPartition,
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
) -> BattleScenarioSourceBinding:
    """Derive one source binding from an exact catalog/registry join."""

    if expected_partition not in {
        ScenarioPartition.TRAIN,
        ScenarioPartition.DEVELOPMENT,
    }:
        raise BattleOutcomeCaptureAuthenticationError("battle source partition is unsupported")
    if not isinstance(source_state_sha256, str) or _SHA256.fullmatch(source_state_sha256) is None:
        raise BattleOutcomeCaptureAuthenticationError("battle source state identity differs")
    registry_source_commit = registry.execution.source_commit
    if (
        catalog.registry_sha256 != registry.registry_sha256
        or catalog.source_bundle_sha256 != registry.execution.source_bundle_sha256
        or catalog.source_commit != registry_source_commit
        or registry_source_commit is None
    ):
        raise BattleOutcomeCaptureAuthenticationError("battle source catalog and registry differ")
    matching = tuple(
        entry for entry in catalog.entries if entry.state_sha256 == source_state_sha256
    )
    if len(matching) != 1:
        raise BattleOutcomeCaptureAuthenticationError(
            "battle source has no unique upstream catalog root"
        )
    entry = matching[0]
    assignment = registry.assignment(entry.slot_id)
    expected_catalog_partition = (
        "train" if expected_partition is ScenarioPartition.TRAIN else "validation"
    )
    root_lineage_id = entry.authenticated_root_lineage_id(
        slot_id=entry.slot_id,
        capture_id=entry.capture_id,
        state_sha256=entry.state_sha256,
        envelope_sha256=entry.envelope_sha256,
    )
    if (
        assignment.partition != expected_catalog_partition
        or entry.assignment_id != assignment.assignment_id
        or root_lineage_id != assignment.root_lineage_id
    ):
        raise BattleOutcomeCaptureAuthenticationError(
            "battle source partition or lineage differs from its catalog"
        )
    return BattleScenarioSourceBinding(
        partition=expected_partition,
        source_state_sha256=entry.state_sha256,
        source_slot_id=entry.slot_id,
        source_assignment_id=entry.assignment_id,
        source_context_id=entry.context_id,
        source_envelope_sha256=entry.envelope_sha256,
        root_lineage_id=root_lineage_id,
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=entry.state_sha256,
            envelope_sha256=entry.envelope_sha256,
        ),
        catalog_sha256=catalog.catalog_sha256,
        registry_sha256=registry.registry_sha256,
        registry_source_commit=registry_source_commit,
    )


def authenticate_battle_outcome_capture_binding(
    capture: BattleScenarioCapture,
    *,
    prepared: PreparedRedBattleScenario,
    base_model: MaskedMLPMoveRanker,
    expected_partition: ScenarioPartition,
    source_commit: str,
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
) -> BattleOutcomeCaptureBinding:
    """Join one verified V2 capture to its exact catalog root and prior menu."""

    if not isinstance(base_model, MaskedMLPMoveRanker):
        raise TypeError("battle outcome binding requires the nonlinear prior")
    if expected_partition not in {
        ScenarioPartition.TRAIN,
        ScenarioPartition.DEVELOPMENT,
    }:
        raise BattleOutcomeCaptureAuthenticationError("battle capture partition is unsupported")
    manifest = capture.manifest
    if (
        manifest.partition is not expected_partition
        or manifest.source_commit != source_commit
        or manifest.source_state_sha256 is None
        or manifest.expected_battle_state != 1
    ):
        raise BattleOutcomeCaptureAuthenticationError("battle capture binding differs")
    if prepared.initial_observation_sha256 != manifest.initial_observation_sha256:
        raise BattleOutcomeCaptureAuthenticationError(
            "prepared battle observation differs from its capture"
        )
    supported_indices = tuple(
        index
        for index, (legal, pp) in enumerate(
            zip(
                prepared.features.legal_mask,
                prepared.features.current_pp,
                strict=True,
            )
        )
        if legal and pp > 0
    )
    supported_vectors = tuple(
        prepared.features.candidate_vectors[index] for index in supported_indices
    )
    try:
        hidden_digest = battle_outcome_hidden_menu_sha256(
            base_model,
            prepared.features,
        )
        distinct_hidden_count = battle_outcome_distinct_hidden_embedding_count(
            base_model,
            prepared.features,
        )
    except (TypeError, ValueError):
        raise BattleOutcomeCaptureAuthenticationError(
            "battle menu differs from the frozen prior schema"
        ) from None
    source_binding = authenticate_battle_scenario_source_binding(
        manifest.source_state_sha256,
        expected_partition=expected_partition,
        catalog=catalog,
        registry=registry,
    )
    if source_binding.root_lineage_id != manifest.root_lineage_id:
        raise BattleOutcomeCaptureAuthenticationError(
            "battle capture partition or lineage differs from its catalog"
        )
    try:
        return BattleOutcomeCaptureBinding(
            partition=expected_partition,
            capture_id=manifest.capture_id,
            manifest_sha256=capture.manifest_sha256,
            state_sha256=manifest.state_sha256,
            initial_observation_sha256=manifest.initial_observation_sha256,
            source_commit=manifest.source_commit,
            source_state_sha256=source_binding.source_state_sha256,
            source_slot_id=source_binding.source_slot_id,
            source_assignment_id=source_binding.source_assignment_id,
            source_context_id=source_binding.source_context_id,
            source_envelope_sha256=source_binding.source_envelope_sha256,
            root_lineage_id=source_binding.root_lineage_id,
            root_consumption_sha256=source_binding.root_consumption_sha256,
            menu_sha256=battle_outcome_menu_sha256(prepared.features),
            supported_candidate_count=len(supported_indices),
            distinct_candidate_vector_count=len(set(supported_vectors)),
            hidden_embedding_sha256=hidden_digest,
            distinct_hidden_embedding_count=distinct_hidden_count,
            expected_map=manifest.expected_map,
            expected_battle_state=manifest.expected_battle_state,
        )
    except BattleOutcomeExperimentError as error:
        raise BattleOutcomeCaptureAuthenticationError(str(error)) from None


__all__ = [
    "BattleScenarioSourceBinding",
    "BattleOutcomeCaptureAuthenticationError",
    "authenticate_battle_scenario_source_binding",
    "authenticate_battle_outcome_capture_binding",
]
