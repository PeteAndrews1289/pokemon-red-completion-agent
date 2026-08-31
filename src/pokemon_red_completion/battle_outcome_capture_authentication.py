"""Shared path-free authentication for one bounded battle learning capture."""

from __future__ import annotations

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
    GoalManagerContextCatalogEntry,
)
from pokemon_red_completion.goal_manager_protocol import GoalManagerCollectionRegistry
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.scenario_lab import ScenarioPartition


class BattleOutcomeCaptureAuthenticationError(ValueError):
    """Raised when capture, catalog, feature, and prior identities do not join."""


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
        raise BattleOutcomeCaptureAuthenticationError(
            "battle capture partition is unsupported"
        )
    expected_catalog_partition = (
        "train"
        if expected_partition is ScenarioPartition.TRAIN
        else "validation"
    )
    manifest = capture.manifest
    if (
        manifest.partition is not expected_partition
        or manifest.source_commit != source_commit
        or manifest.source_state_sha256 is None
        or manifest.expected_battle_state != 1
    ):
        raise BattleOutcomeCaptureAuthenticationError(
            "battle capture binding differs"
        )
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
    matching = tuple(
        entry
        for entry in catalog.entries
        if entry.state_sha256 == manifest.source_state_sha256
    )
    if len(matching) != 1:
        raise BattleOutcomeCaptureAuthenticationError(
            "battle capture has no unique upstream catalog root"
        )
    entry: GoalManagerContextCatalogEntry = matching[0]
    assignment = registry.assignment(entry.slot_id)
    root_lineage_id = entry.authenticated_root_lineage_id(
        slot_id=entry.slot_id,
        capture_id=entry.capture_id,
        state_sha256=entry.state_sha256,
        envelope_sha256=entry.envelope_sha256,
    )
    if (
        assignment.partition != expected_catalog_partition
        or entry.assignment_id != assignment.assignment_id
        or root_lineage_id != manifest.root_lineage_id
    ):
        raise BattleOutcomeCaptureAuthenticationError(
            "battle capture partition or lineage differs from its catalog"
        )
    consumption = root_consumption_sha256(
        state_sha256=entry.state_sha256,
        envelope_sha256=entry.envelope_sha256,
    )
    try:
        return BattleOutcomeCaptureBinding(
            partition=expected_partition,
            capture_id=manifest.capture_id,
            manifest_sha256=capture.manifest_sha256,
            state_sha256=manifest.state_sha256,
            initial_observation_sha256=manifest.initial_observation_sha256,
            source_commit=manifest.source_commit,
            source_state_sha256=entry.state_sha256,
            source_slot_id=entry.slot_id,
            source_assignment_id=entry.assignment_id,
            source_context_id=entry.context_id,
            source_envelope_sha256=entry.envelope_sha256,
            root_lineage_id=root_lineage_id,
            root_consumption_sha256=consumption,
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
    "BattleOutcomeCaptureAuthenticationError",
    "authenticate_battle_outcome_capture_binding",
]
