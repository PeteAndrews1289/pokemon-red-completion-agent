"""Prospective contract for one independent Red Cave venue measurement.

The party-development learner cannot use a venue's own outcome as the prior
feature for that same question.  This contract therefore reserves one open,
non-question Red root for a single-venue operating measurement.  It creates no
candidate menu, label, prediction, or learner outcome.  A later, distinct
source checkpoint may attest compatibility and compose the observation into a
second venue prior.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.blaine import DIGLETTS_CAVE_TRAINING_VENUE
from pokemon_red_completion.party_development_venue_priors import (
    VenuePriorMeasurementContract,
)
from pokemon_red_completion.provenance import canonical_sha256

RED_CAVE_VENUE_MEASUREMENT_PLAN_SCHEMA = (
    "pokemon.red.party-development-cave-venue-measurement-plan.v1"
)
RED_CAVE_VENUE_MEASUREMENT_RESULT_SCHEMA = (
    "pokemon.red.party-development-cave-venue-measurement-result.v1"
)
RED_CAVE_VENUE_MEASUREMENT_ID = "red-cave-venue-prior-measurement-v1"
RED_CAVE_VENUE_MEASUREMENT_ARTIFACT_ID = "red-cave-venue-measurement-v1"
RED_CAVE_SUPPORT_CHECKPOINT_ID = "red-goal-v1-028-evolve_species-train-01"
RED_CAVE_SUPPORT_STATE_SHA256 = (
    "4348fd2bc9b20772f9607ea6242a53ed56656843c1a68c25671bc770ce484a64"
)
RED_CAVE_SUPPORT_ENVELOPE_SHA256 = (
    "825e270d8974afabd5650b1dee618a975baeffa965124de3eff041d6dca8a4f3"
)
RED_CAVE_SUPPORT_SEMANTIC_SHA256 = (
    "319535d3e5f3af52b6a7eaa09959eb7a6455ff910ae58a1d8ba39b0933e24115"
)
RED_CAVE_SUPPORT_ASSIGNMENT_ID = (
    "b83b76f4fe14aaaadc8cb261d16456b30ebd1b9c85ef37e12e38f5bdd6553ef4"
)
RED_CAVE_SUPPORT_ROOT_LINEAGE_ID = (
    f"red-goal-root-{RED_CAVE_SUPPORT_ASSIGNMENT_ID}"
)
RED_CAVE_CONTEXT_CATALOG_FILE_SHA256 = (
    "7b1cb754bcf9884c82363bfff5e6848953f6b6c61a7796ab8a2d8b1a9be5ba83"
)
RED_CAVE_CONTEXT_CATALOG_SOURCE_COMMIT = (
    "4207981a3c7b7dfbfa47f0a7add6975068bcfc50"
)
RED_CAVE_CONTEXT_CATALOG_REGISTRY_SHA256 = (
    "b30328606fbdc383e52a49b3c9b7800ffa65f14099605aa7b99e827aa35dc1dc"
)
RED_ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
RED_CAVE_TARGET_SLOT = 3
RED_CAVE_INITIAL_TARGET_LEVEL = 22
RED_CAVE_FINAL_TARGET_LEVEL = 26
RED_CAVE_PROGRESS_UNITS_REQUIRED = 4
RED_CAVE_RESERVATION_PLAN_SHA256 = (
    "9097f73eecaf0e38949fb6e76b0cc7a3c8bafa50c353b60a87f77e5519f4e30d"
)
RED_CAVE_RESERVATION_PLAN_FILE_SHA256 = (
    "bb7f32b320499239d0582e2deebcb12759fa388eb6289b62bdb839ab083554e8"
)
RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256 = (
    "d7f45da14d203705c56cf0c1097d9f7b2e0c6f2c712a2bab8a6ffee0327f7a45"
)
RED_CAVE_VENUE_PRIOR_REGISTRY_FILE_SHA256 = (
    "102fc95256673d5b9696a152928b0edcf3d2480b6519102fadd62d19ddc2a618"
)
RED_CAVE_ROUTE_PRIOR_OPERATIONAL_CONTRACT_SHA256 = (
    "b25e5994d2830d628aefc3a119aa7cfdf7c463294e9848542b8fa35e439ae33a"
)


class RedCaveVenueMeasurementError(ValueError):
    """Raised before a Cave observation can lose its prospective meaning."""


def _private_venue_document() -> dict[str, object]:
    venue = DIGLETTS_CAVE_TRAINING_VENUE.band
    return {
        "schema": "pokemon.core.party-development-private-venue-binding.v1",
        "area_id": venue.area_id,
        "conditions": list(venue.conditions),
        "minimum_encounter_level": venue.minimum_encounter_level,
        "maximum_encounter_level": venue.maximum_encounter_level,
        "rare_maximum_encounter_level": venue.rare_maximum_encounter_level,
        "has_nearby_healer": venue.has_nearby_healer,
        "measured_samples": venue.measured_samples,
    }


def red_cave_venue_binding_sha256() -> str:
    """Return the private Cave binding without publishing its component values."""

    return canonical_sha256(_private_venue_document())


def red_cave_venue_measurement_plan_document() -> dict[str, object]:
    """Return the exact tracked plan consumed by the one-shot runner."""

    measurement_contract = VenuePriorMeasurementContract()
    return {
        "schema": RED_CAVE_VENUE_MEASUREMENT_PLAN_SCHEMA,
        "status": "prospective_unexecuted",
        "measurement_id": RED_CAVE_VENUE_MEASUREMENT_ID,
        "purpose": (
            "Measure one independently reserved Cave venue under the same bounded "
            "evolution objective used by the existing Route 11 prior, without "
            "creating or answering a learner question."
        ),
        "authenticated_root": {
            "checkpoint_id": RED_CAVE_SUPPORT_CHECKPOINT_ID,
            "assignment_id": RED_CAVE_SUPPORT_ASSIGNMENT_ID,
            "root_lineage_id": RED_CAVE_SUPPORT_ROOT_LINEAGE_ID,
            "state_sha256": RED_CAVE_SUPPORT_STATE_SHA256,
            "capture_envelope_sha256": RED_CAVE_SUPPORT_ENVELOPE_SHA256,
            "semantic_signature_sha256": RED_CAVE_SUPPORT_SEMANTIC_SHA256,
            "rom_sha256": RED_ROM_SHA256,
            "partition": "train",
            "sealed_test": False,
            "crystal": False,
        },
        "independence": {
            "historical_context_catalog_file_sha256": (
                RED_CAVE_CONTEXT_CATALOG_FILE_SHA256
            ),
            "historical_context_catalog_source_commit": (
                RED_CAVE_CONTEXT_CATALOG_SOURCE_COMMIT
            ),
            "historical_goal_manager_registry_sha256": (
                RED_CAVE_CONTEXT_CATALOG_REGISTRY_SHA256
            ),
            "reservation_plan_sha256": RED_CAVE_RESERVATION_PLAN_SHA256,
            "reservation_plan_file_sha256": (
                RED_CAVE_RESERVATION_PLAN_FILE_SHA256
            ),
            "venue_prior_registry_sha256": RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256,
            "venue_prior_registry_file_sha256": (
                RED_CAVE_VENUE_PRIOR_REGISTRY_FILE_SHA256
            ),
            "existing_venue_prior_count": 1,
            "reserved_question_count": 14,
            "support_root_is_not_a_reserved_question": True,
            "support_state_is_not_a_reserved_question": True,
            "support_root_is_not_prior_support": True,
            "support_state_is_not_prior_support": True,
        },
        "bounded_objective": {
            "initial_target_slot": RED_CAVE_TARGET_SLOT,
            "initial_target_level": RED_CAVE_INITIAL_TARGET_LEVEL,
            "final_target_level": RED_CAVE_FINAL_TARGET_LEVEL,
            "progress_units_required": RED_CAVE_PROGRESS_UNITS_REQUIRED,
            "stop_condition": "first_verified_level_triggered_evolution",
            "same_trainee_required": True,
            "target_experience_measured_exactly": True,
            "evolution_verified_from_party_memory": True,
            "overlevelled_escort_experience_is_not_target_progress": True,
        },
        "venue": {
            "venue_binding_sha256": red_cave_venue_binding_sha256(),
            "single_fixed_venue": True,
            "candidate_menu_constructed": False,
            "venue_identity_exposed_to_model": False,
            "species_identity_exposed_to_model": False,
            "party_slot_exposed_to_model": False,
        },
        "measurement_contract": {
            "measurement_contract_sha256": (
                measurement_contract.measurement_contract_sha256
            ),
            "existing_route_prior_operational_contract_sha256": (
                RED_CAVE_ROUTE_PRIOR_OPERATIONAL_CONTRACT_SHA256
            ),
            "same_measurement_contract_as_existing_prior": True,
            "source_compatibility_attested_after_measurement": True,
            "venue_prior_composed_after_measurement": True,
        },
        "execution": {
            "exact_published_source_required": True,
            "exact_commit_ci_success_required_before_execution": True,
            "private_artifact_opened_before_first_controller_input": True,
            "execute_exactly_once": True,
            "retry_after_any_controller_input": False,
            "one_fixed_venue_only": True,
            "candidate_menu_constructed": False,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "learner_outcomes_opened": 0,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
        },
        "acceptance": {
            "objective_completed": True,
            "progress_units_gained": RED_CAVE_PROGRESS_UNITS_REQUIRED,
            "faints": 0,
            "maximum_battles": 200,
            "maximum_steps": 20000,
            "maximum_budgeted_center_calls": 50,
            "required_cleanup_calls": 1,
            "optional_recovery_calls": 0,
            "candidate_decisions": 0,
            "source_state_unchanged": True,
            "source_envelope_unchanged": True,
            "rom_adjacent_artifacts_unchanged": True,
        },
        "interpretation": {
            "model_fit": False,
            "authority_promotion": False,
            "training_example_created": False,
            "next_if_complete": (
                "Publish the immutable result, attest execution-source compatibility "
                "from a distinct commit, and compose exactly one Cave venue prior."
            ),
        },
        "private_path_fields": 0,
    }


def load_red_cave_venue_measurement_plan(
    path: Path,
) -> tuple[Mapping[str, object], str]:
    """Load the plan only when its bytes encode the exact source contract."""

    payload = path.read_bytes()
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedCaveVenueMeasurementError("Cave measurement plan is invalid") from error
    if not isinstance(value, Mapping):
        raise RedCaveVenueMeasurementError("Cave measurement plan is not an object")
    if value != red_cave_venue_measurement_plan_document():
        raise RedCaveVenueMeasurementError(
            "Cave measurement plan differs from its prospective source contract"
        )
    return value, hashlib.sha256(payload).hexdigest()


__all__ = [
    "RED_CAVE_FINAL_TARGET_LEVEL",
    "RED_CAVE_CONTEXT_CATALOG_FILE_SHA256",
    "RED_CAVE_CONTEXT_CATALOG_REGISTRY_SHA256",
    "RED_CAVE_CONTEXT_CATALOG_SOURCE_COMMIT",
    "RED_CAVE_INITIAL_TARGET_LEVEL",
    "RED_CAVE_PROGRESS_UNITS_REQUIRED",
    "RED_CAVE_SUPPORT_CHECKPOINT_ID",
    "RED_CAVE_SUPPORT_ASSIGNMENT_ID",
    "RED_CAVE_SUPPORT_ENVELOPE_SHA256",
    "RED_CAVE_SUPPORT_STATE_SHA256",
    "RED_CAVE_SUPPORT_ROOT_LINEAGE_ID",
    "RED_CAVE_TARGET_SLOT",
    "RED_CAVE_VENUE_MEASUREMENT_ARTIFACT_ID",
    "RED_CAVE_VENUE_MEASUREMENT_ID",
    "RED_CAVE_VENUE_MEASUREMENT_PLAN_SCHEMA",
    "RED_CAVE_VENUE_MEASUREMENT_RESULT_SCHEMA",
    "RED_CAVE_VENUE_PRIOR_REGISTRY_FILE_SHA256",
    "RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256",
    "RED_CAVE_RESERVATION_PLAN_FILE_SHA256",
    "RED_CAVE_RESERVATION_PLAN_SHA256",
    "RED_ROM_SHA256",
    "RedCaveVenueMeasurementError",
    "load_red_cave_venue_measurement_plan",
    "red_cave_venue_binding_sha256",
    "red_cave_venue_measurement_plan_document",
]
