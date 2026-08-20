"""Source-only qualification of the accepted Red Cave venue measurement.

The Cave run is already consumed.  This module cannot execute it again.  It
only verifies the immutable public receipt, proves the execution-bearing files
are byte-identical to the measured commit, and composes one additional private
venue prior beside the existing Route 11 prior.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from pokemon_red_completion.blaine import (
    DIGLETTS_CAVE_EXIT_COORDINATES,
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_BALANCED_TEAM_TRAINING_INTENT,
    MANSION_ESCORT_ENEMY_SPECIES,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_TRAINING_FLEE_TIMING,
    MANSION_VOLATILE_ENEMY_SPECIES,
    _digletts_cave_heal_and_return,
    _new_digletts_cave_walker,
    _team_training_move_guard,
    _team_training_move_slot,
)
from pokemon_red_completion.collection_protocol import (
    committed_executable_source_blob,
    committed_source_bundle_sha256,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorEvidence,
    VenuePriorMeasurementContract,
    VenuePriorObservation,
    VenuePriorOperationalContract,
    VenuePriorSourceCompatibilityAttestation,
    compose_venue_prior_evidence,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_cave_venue_measurement import (
    RED_CAVE_PROGRESS_UNITS_REQUIRED,
    RED_CAVE_ROUTE_PRIOR_OPERATIONAL_CONTRACT_SHA256,
    RED_CAVE_SUPPORT_ROOT_LINEAGE_ID,
    RED_CAVE_SUPPORT_STATE_SHA256,
    RED_CAVE_VENUE_MEASUREMENT_ID,
    RED_CAVE_VENUE_MEASUREMENT_RESULT_SCHEMA,
    RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256,
    red_cave_venue_binding_sha256,
)
from pokemon_red_completion.red_party_development_venue_priors import (
    RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
    TRAINING_ATTACK_PP_RESERVE,
    TRAINING_MOVE_IDS,
)
from pokemon_red_completion.training_venue import (
    TrainingVenue,
    WarpSafeVenueWalker,
)

RED_CAVE_VENUE_PRIOR_COMPOSITION_SCHEMA = (
    "pokemon.red.party-development-cave-venue-prior-composition.v1"
)
RED_CAVE_VENUE_PRIOR_EVIDENCE_ID = "red-cave-evolution-prior-v1"
RED_CAVE_VENUE_OPERATIONAL_CONTRACT_ID = (
    "red-cave-bounded-evolution-runtime-v1"
)
RED_CAVE_SOURCE_COMPATIBILITY_ATTESTATION_ID = (
    "red-cave-755fe53-runtime-compatibility-v1"
)
RED_CAVE_MEASUREMENT_SOURCE_COMMIT = (
    "755fe53d127c764f4213c2335cdbd5c9cb136dda"
)
RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256 = (
    "5d6ad452624f273920e642b266ba26724f6fccc8c57551acd2eead72b68d5bbe"
)
RED_CAVE_VENUE_MEASUREMENT_PUBLIC_PLAN_SHA256 = (
    "ff277a2483fce53e1e86c032ec3c8c3376e33b8d118145d6137a6a1e8ca00ff0"
)
RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256 = (
    "4119a6eb8ad7c2e5debdd83e996e17303517ae93634877e9769c8c2bdcab543f"
)

_CRITICAL_RUNTIME_PATHS = (
    "scripts/run_red_cave_venue_measurement.py",
    "src/pokemon_red_completion/actions.py",
    "src/pokemon_red_completion/battle_actions.py",
    "src/pokemon_red_completion/battle_runtime.py",
    "src/pokemon_red_completion/blaine.py",
    "src/pokemon_red_completion/bootstrap.py",
    "src/pokemon_red_completion/celadon.py",
    "src/pokemon_red_completion/emulator.py",
    "src/pokemon_red_completion/executor.py",
    "src/pokemon_red_completion/hideout.py",
    "src/pokemon_red_completion/observation.py",
    "src/pokemon_red_completion/party.py",
    "src/pokemon_red_completion/red_battle_catalog.py",
    "src/pokemon_red_completion/red_cave_venue_measurement.py",
    "src/pokemon_red_completion/red_party.py",
    "src/pokemon_red_completion/red_party_development_venue_priors.py",
    "src/pokemon_red_completion/red_team_training.py",
    "src/pokemon_red_completion/team_training.py",
    "src/pokemon_red_completion/training_candidate_rank.py",
    "src/pokemon_red_completion/training_control.py",
    "src/pokemon_red_completion/training_venue.py",
)
_COMPATIBILITY_SOURCE_ADDITIONS = frozenset(
    {
        "scripts/compose_red_cave_venue_prior.py",
        "src/pokemon_red_completion/red_cave_venue_prior.py",
    }
)
_COMPATIBILITY_WAIVER_ID = "publication-and-composition-only"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class RedCaveVenuePriorError(ValueError):
    """Raised when the accepted measurement cannot support a current prior."""


@dataclass(frozen=True, slots=True)
class RedCaveVenuePriorComposition:
    """The two-prior private registry and its path-free public projection."""

    registry: PartyDevelopmentVenuePriorRegistry
    cave_evidence: VenuePriorEvidence
    measurement_contract: VenuePriorMeasurementContract
    operational_contract: VenuePriorOperationalContract
    source_compatibility: VenuePriorSourceCompatibilityAttestation
    previous_registry_sha256: str
    public_plan_sha256: str
    public_result_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.registry, PartyDevelopmentVenuePriorRegistry):
            raise TypeError("registry must be a PartyDevelopmentVenuePriorRegistry")
        if len(self.registry.entries) != 2 or self.cave_evidence not in self.registry.entries:
            raise RedCaveVenuePriorError(
                "Cave composition must freeze one new entry beside one existing entry"
            )
        if not isinstance(self.cave_evidence, VenuePriorEvidence):
            raise TypeError("Cave evidence is invalid")
        if not isinstance(self.measurement_contract, VenuePriorMeasurementContract):
            raise TypeError("measurement contract is invalid")
        if not isinstance(self.operational_contract, VenuePriorOperationalContract):
            raise TypeError("operational contract is invalid")
        if not isinstance(
            self.source_compatibility,
            VenuePriorSourceCompatibilityAttestation,
        ):
            raise TypeError("source compatibility is invalid")
        if (
            self.cave_evidence.operational_contract_sha256
            != self.operational_contract.operational_contract_sha256
            or self.cave_evidence.source_compatibility_sha256
            != self.source_compatibility.source_compatibility_sha256
            or self.operational_contract.source_compatibility_sha256
            != self.source_compatibility.source_compatibility_sha256
        ):
            raise RedCaveVenuePriorError(
                "Cave evidence does not bind its operational compatibility"
            )
        for value, subject in (
            (self.previous_registry_sha256, "previous registry"),
            (self.public_plan_sha256, "public plan"),
            (self.public_result_sha256, "public result"),
        ):
            _require_digest(value, subject=subject)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_CAVE_VENUE_PRIOR_COMPOSITION_SCHEMA,
            "status": "source_only_prior_composed",
            "registry": self.registry.public_dict(),
            "cave_evidence": self.cave_evidence.public_dict(),
            "measurement_contract": self.measurement_contract.public_dict(),
            "operational_contract": self.operational_contract.public_dict(),
            "source_compatibility": self.source_compatibility.public_dict(),
            "source_receipt_sha256": sorted(
                (self.public_plan_sha256, self.public_result_sha256)
            ),
            "previous_registry_sha256": self.previous_registry_sha256,
            "previous_venue_prior_count": 1,
            "venue_prior_entries_added": 1,
            "resulting_venue_prior_count": 2,
            "accepted_cave_measurements": 1,
            "training_examples_created": 0,
            "composition_rom_reads": 0,
            "composition_emulator_starts": 0,
            "composition_controller_actions": 0,
            "outcomes_executed": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "sealed_test_cases_opened": 0,
            "crystal_contexts_opened": 0,
            "authority_promoted": False,
            "private_venue_identity_public": False,
            "support_identity_public": False,
            "private_path_fields": 0,
        }


def attest_red_cave_source_compatibility(
    repository_root: str | Path,
    *,
    current_commit: str,
    current_source_bundle_sha256: str,
) -> VenuePriorSourceCompatibilityAttestation:
    """Prove measured runtime files are byte-identical at the composition head."""

    root = Path(repository_root)
    if _GIT_OID.fullmatch(current_commit) is None:
        raise RedCaveVenuePriorError("current Cave compatibility commit is invalid")
    _require_digest(current_source_bundle_sha256, subject="current source bundle")
    if current_commit == RED_CAVE_MEASUREMENT_SOURCE_COMMIT:
        raise RedCaveVenuePriorError(
            "Cave compatibility needs a distinct post-measurement source commit"
        )
    observed_bundle = committed_source_bundle_sha256(
        root,
        revision=RED_CAVE_MEASUREMENT_SOURCE_COMMIT,
    )
    current_bundle = committed_source_bundle_sha256(root, revision=current_commit)
    if observed_bundle != RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256:
        raise RedCaveVenuePriorError(
            "measured Cave source bundle differs from its public receipt"
        )
    if current_bundle != current_source_bundle_sha256:
        raise RedCaveVenuePriorError(
            "current Cave source bundle differs from its published registry"
        )

    observed_rows = _committed_runtime_rows(
        root,
        revision=RED_CAVE_MEASUREMENT_SOURCE_COMMIT,
    )
    current_rows = _committed_runtime_rows(root, revision=current_commit)
    if observed_rows != current_rows:
        raise RedCaveVenuePriorError(
            "an execution-bearing Cave source file changed after measurement"
        )
    changed_source_paths = frozenset(
        path
        for path in _changed_paths_between(
            root,
            RED_CAVE_MEASUREMENT_SOURCE_COMMIT,
            current_commit,
        )
        if path.startswith(("src/", "scripts/"))
    )
    if changed_source_paths != _COMPATIBILITY_SOURCE_ADDITIONS:
        raise RedCaveVenuePriorError(
            "post-measurement executable drift exceeds publication and composition"
        )

    unchanged_sha256 = _runtime_rows_sha256(observed_rows, scope="unchanged")
    current_sha256 = _runtime_rows_sha256(current_rows, scope="current")
    waiver_sha256 = canonical_sha256(
        {
            "schema": "pokemon.red.cave-source-waiver-allowlist.v1",
            "waiver_id": _COMPATIBILITY_WAIVER_ID,
            "allowed_source_additions": sorted(_COMPATIBILITY_SOURCE_ADDITIONS),
            "critical_runtime_rows_sha256": unchanged_sha256,
            "public_result_sha256": (
                RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256
            ),
        }
    )
    return VenuePriorSourceCompatibilityAttestation(
        attestation_id=RED_CAVE_SOURCE_COMPATIBILITY_ATTESTATION_ID,
        observed_commit=RED_CAVE_MEASUREMENT_SOURCE_COMMIT,
        observed_source_bundle_sha256=observed_bundle,
        current_commit=current_commit,
        current_source_bundle_sha256=current_bundle,
        unchanged_elements_sha256=unchanged_sha256,
        current_elements_sha256=current_sha256,
        waived_elements=(_COMPATIBILITY_WAIVER_ID,),
        waiver_allowlist_sha256=waiver_sha256,
    )


def red_cave_operational_contract(
    repository_root: str | Path,
    *,
    source_compatibility: VenuePriorSourceCompatibilityAttestation,
) -> VenuePriorOperationalContract:
    """Bind the accepted counts to the exact current Cave execution layers."""

    if not isinstance(
        source_compatibility,
        VenuePriorSourceCompatibilityAttestation,
    ):
        raise TypeError("source compatibility is invalid")
    if (
        source_compatibility.attestation_id
        != RED_CAVE_SOURCE_COMPATIBILITY_ATTESTATION_ID
        or source_compatibility.observed_commit
        != RED_CAVE_MEASUREMENT_SOURCE_COMMIT
        or source_compatibility.observed_source_bundle_sha256
        != RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256
        or source_compatibility.waived_elements
        != (_COMPATIBILITY_WAIVER_ID,)
    ):
        raise RedCaveVenuePriorError(
            "Cave operational runtime differs from its source attestation"
        )
    rows = _committed_runtime_rows(
        Path(repository_root),
        revision=source_compatibility.current_commit,
    )
    if (
        _runtime_rows_sha256(rows, scope="current")
        != source_compatibility.current_elements_sha256
    ):
        raise RedCaveVenuePriorError(
            "Cave operational files differ from their current attestation"
        )
    _require_current_cave_venue(DIGLETTS_CAVE_TRAINING_VENUE)
    row_map = {str(row["path"]): str(row["sha256"]) for row in rows}

    policy_document = {
        "schema": "pokemon.red.cave-venue-policy.v1",
        "balanced_team_policy": _jsonable(
            asdict(RED_PARTY_DEVELOPMENT_OUTCOME_POLICY)
        ),
        "training_intent": _jsonable(asdict(MANSION_BALANCED_TEAM_TRAINING_INTENT)),
        "volatile_enemy_species_sha256": canonical_sha256(
            sorted(MANSION_VOLATILE_ENEMY_SPECIES)
        ),
        "escort_enemy_species_sha256": canonical_sha256(
            sorted(MANSION_ESCORT_ENEMY_SPECIES)
        ),
        "maximum_consecutive_flees": MANSION_MAX_CONSECUTIVE_FLEES,
        "training_move_table_sha256": canonical_sha256(
            {str(key): list(value) for key, value in sorted(TRAINING_MOVE_IDS.items())}
        ),
        "training_pp_reserve_sha256": canonical_sha256(
            dict(sorted(TRAINING_ATTACK_PP_RESERVE.items()))
        ),
        "source_sha256": _selected_rows_sha256(
            row_map,
            (
                "src/pokemon_red_completion/red_party_development_venue_priors.py",
                "src/pokemon_red_completion/red_team_training.py",
                "src/pokemon_red_completion/team_training.py",
            ),
            scope="policy",
        ),
    }
    encounter_document = {
        "schema": "pokemon.red.cave-venue-encounter-execution.v1",
        "private_venue_binding_sha256": red_cave_venue_binding_sha256(),
        "source_sha256": _selected_rows_sha256(
            row_map,
            (
                "src/pokemon_red_completion/blaine.py",
                "src/pokemon_red_completion/red_team_training.py",
                "src/pokemon_red_completion/training_venue.py",
            ),
            scope="encounter",
        ),
    }
    recovery_document = {
        "schema": "pokemon.red.cave-venue-recovery-execution.v1",
        "source_sha256": _selected_rows_sha256(
            row_map,
            (
                "src/pokemon_red_completion/blaine.py",
                "src/pokemon_red_completion/celadon.py",
                "src/pokemon_red_completion/executor.py",
            ),
            scope="recovery",
        ),
    }
    battle_document = {
        "schema": "pokemon.red.cave-venue-battle-timing.v1",
        "venue_battle_timing": _jsonable(
            asdict(DIGLETTS_CAVE_TRAINING_VENUE.battle_timing)
        ),
        "flee_timing": _jsonable(asdict(MANSION_TRAINING_FLEE_TIMING)),
        "level_up_move_cancel_interval": MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
        "source_sha256": _selected_rows_sha256(
            row_map,
            (
                "src/pokemon_red_completion/battle_actions.py",
                "src/pokemon_red_completion/battle_runtime.py",
                "src/pokemon_red_completion/blaine.py",
                "src/pokemon_red_completion/observation.py",
                "src/pokemon_red_completion/red_team_training.py",
            ),
            scope="battle",
        ),
    }
    accounting_document = {
        "schema": "pokemon.red.cave-venue-accounting.v1",
        "budgeted_center_phases": [
            "venue_transition",
            "required_recovery",
            "optional_recovery",
        ],
        "cleanup_counted_but_outside_recurring_cost": True,
        "source_sha256": _selected_rows_sha256(
            row_map,
            (
                "scripts/run_red_cave_venue_measurement.py",
                "src/pokemon_red_completion/red_team_training.py",
                "src/pokemon_red_completion/team_training.py",
            ),
            scope="accounting",
        ),
    }
    return VenuePriorOperationalContract(
        contract_id=RED_CAVE_VENUE_OPERATIONAL_CONTRACT_ID,
        policy_sha256=canonical_sha256(policy_document),
        encounter_execution_sha256=canonical_sha256(encounter_document),
        recovery_execution_sha256=canonical_sha256(recovery_document),
        battle_timing_sha256=canonical_sha256(battle_document),
        accounting_sha256=canonical_sha256(accounting_document),
        source_compatibility_sha256=(
            source_compatibility.source_compatibility_sha256
        ),
    )


def compose_red_cave_venue_prior(
    *,
    existing_registry: PartyDevelopmentVenuePriorRegistry,
    plan: Mapping[str, object],
    result: Mapping[str, object],
    public_plan_sha256: str,
    public_result_sha256: str,
    registry_source_commit: str,
    registry_source_bundle_sha256: str,
    source_compatibility: VenuePriorSourceCompatibilityAttestation,
    repository_root: str | Path,
) -> RedCaveVenuePriorComposition:
    """Compose one Cave entry without executing or reopening an outcome."""

    _require_public_receipts(
        plan,
        result,
        public_plan_sha256=public_plan_sha256,
        public_result_sha256=public_result_sha256,
    )
    if not isinstance(existing_registry, PartyDevelopmentVenuePriorRegistry):
        raise TypeError("existing registry is invalid")
    if (
        existing_registry.registry_sha256 != RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256
        or len(existing_registry.entries) != 1
    ):
        raise RedCaveVenuePriorError(
            "Cave composition needs the exact frozen one-prior registry"
        )
    measurement_contract = VenuePriorMeasurementContract()
    existing = existing_registry.entries[0]
    if (
        existing.measurement_contract_sha256
        != measurement_contract.measurement_contract_sha256
        or existing.operational_contract_sha256
        != RED_CAVE_ROUTE_PRIOR_OPERATIONAL_CONTRACT_SHA256
        or existing_registry.evidence_for(DIGLETTS_CAVE_TRAINING_VENUE.band)
        is not None
    ):
        raise RedCaveVenuePriorError(
            "existing venue evidence is not the qualified Route 11 predecessor"
        )
    existing_registry.require_scenario_is_independent(
        root_lineage_id=RED_CAVE_SUPPORT_ROOT_LINEAGE_ID,
        initial_state_sha256=RED_CAVE_SUPPORT_STATE_SHA256,
    )
    if (
        registry_source_commit != source_compatibility.current_commit
        or registry_source_bundle_sha256
        != source_compatibility.current_source_bundle_sha256
    ):
        raise RedCaveVenuePriorError(
            "Cave registry source differs from its compatibility attestation"
        )

    measurement = _mapping(result, "measurement")
    operational_contract = red_cave_operational_contract(
        repository_root,
        source_compatibility=source_compatibility,
    )
    observation = VenuePriorObservation(
        root_lineage_id=RED_CAVE_SUPPORT_ROOT_LINEAGE_ID,
        initial_state_sha256=RED_CAVE_SUPPORT_STATE_SHA256,
        outcome_receipt_sha256=tuple(
            sorted((public_plan_sha256, public_result_sha256))
        ),
        objective_completed=True,
        progress_units_gained=_integer(measurement, "progress_units_gained"),
        progress_units_required=_integer(
            measurement,
            "progress_units_required",
        ),
        battles_completed=_integer(measurement, "battles_completed"),
        faints=_integer(measurement, "faints"),
        venue_transition_trips=_integer(
            measurement,
            "venue_transition_trips",
        ),
        required_recovery_trips=_integer(
            measurement,
            "required_recovery_trips",
        ),
        optional_recovery_trips=_integer(
            measurement,
            "optional_recovery_trips",
        ),
        cleanup_trips=_integer(measurement, "cleanup_trips"),
        total_counted_center_routes=_integer(
            measurement,
            "total_counted_center_routes",
        ),
    )
    cave_evidence = compose_venue_prior_evidence(
        evidence_id=RED_CAVE_VENUE_PRIOR_EVIDENCE_ID,
        venue=DIGLETTS_CAVE_TRAINING_VENUE.band,
        source_commit=RED_CAVE_MEASUREMENT_SOURCE_COMMIT,
        source_bundle_sha256=RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256,
        measurement_contract=measurement_contract,
        operational_contract=operational_contract,
        source_compatibility=source_compatibility,
        observations=(observation,),
    )
    registry = PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit=registry_source_commit,
        source_bundle_sha256=registry_source_bundle_sha256,
        entries=(*existing_registry.entries, cave_evidence),
    )
    return RedCaveVenuePriorComposition(
        registry=registry,
        cave_evidence=cave_evidence,
        measurement_contract=measurement_contract,
        operational_contract=operational_contract,
        source_compatibility=source_compatibility,
        previous_registry_sha256=existing_registry.registry_sha256,
        public_plan_sha256=public_plan_sha256,
        public_result_sha256=public_result_sha256,
    )


def _require_public_receipts(
    plan: Mapping[str, object],
    result: Mapping[str, object],
    *,
    public_plan_sha256: str,
    public_result_sha256: str,
) -> None:
    if (
        public_plan_sha256 != RED_CAVE_VENUE_MEASUREMENT_PUBLIC_PLAN_SHA256
        or public_result_sha256
        != RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256
        or plan.get("schema")
        != "pokemon.red.party-development-cave-venue-measurement-plan.v2"
        or plan.get("status") != "prospective_unexecuted"
        or plan.get("measurement_id") != RED_CAVE_VENUE_MEASUREMENT_ID
        or result.get("schema") != RED_CAVE_VENUE_MEASUREMENT_RESULT_SCHEMA
        or result.get("status") != "complete_measurement_accepted"
        or result.get("measurement_id") != RED_CAVE_VENUE_MEASUREMENT_ID
        or result.get("private_path_fields") != 0
    ):
        raise RedCaveVenuePriorError(
            "Cave plan and result do not form the accepted V2 measurement"
        )
    execution = _mapping(result, "execution_identity")
    authorization = _mapping(result, "authorization")
    acceptance = _mapping(result, "acceptance")
    independence = _mapping(result, "independence")
    artifact = _mapping(result, "artifact")
    measurement = _mapping(result, "measurement")
    protected = _mapping(result, "protected_access")
    plan_acceptance = _mapping(plan, "acceptance")
    if (
        execution.get("source_commit") != RED_CAVE_MEASUREMENT_SOURCE_COMMIT
        or execution.get("source_bundle_sha256")
        != RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256
        or execution.get("public_plan_file_sha256") != public_plan_sha256
        or execution.get("exact_ci_run") != 31926299036
        or execution.get("exact_ci_conclusion") != "success"
        or authorization.get("authorized_executions") != 1
        or authorization.get("execution_count") != 1
        or authorization.get("controller_input_occurred") is not True
        or authorization.get("retry_after_controller_input") is not False
        or authorization.get("terminal_attempt_consumed") is not True
        or acceptance.get("all_declared_conditions_met") is not True
        or artifact.get("artifact_id") != "red-cave-venue-measurement-v2"
        or artifact.get("status") != "complete"
        or artifact.get("stream_records")
        != {"attempt": 1, "measurement": 1, "plan": 1}
        or independence.get("venue_binding_sha256")
        != red_cave_venue_binding_sha256()
        or independence.get("measurement_contract_sha256")
        != VenuePriorMeasurementContract().measurement_contract_sha256
        or independence.get("canonical_root_lineage_authenticated") is not True
        or independence.get("support_semantics_authenticated") is not True
        or independence.get("independent_of_existing_priors") is not True
        or independence.get("independent_of_reserved_questions") is not True
        or protected
        != {
            "candidate_menus_constructed": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
            "learner_outcomes_opened": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "sealed_red_cases_opened": 0,
            "teacher_queries": 0,
        }
    ):
        raise RedCaveVenuePriorError(
            "Cave result lacks one accepted isolated execution"
        )

    progress_gained = _integer(measurement, "progress_units_gained")
    progress_required = _integer(measurement, "progress_units_required")
    battles = _integer(measurement, "battles_completed")
    steps = _integer(measurement, "steps_taken")
    transitions = _integer(measurement, "venue_transition_trips")
    required_recovery = _integer(measurement, "required_recovery_trips")
    optional_recovery = _integer(measurement, "optional_recovery_trips")
    cleanup = _integer(measurement, "cleanup_trips")
    budgeted = _integer(measurement, "budgeted_center_calls")
    total = _integer(measurement, "total_counted_center_routes")
    attempts = _integer(measurement, "traversal_movement_attempts")
    successes = _integer(measurement, "traversal_successful_steps")
    blocked = _integer(measurement, "traversal_blocked_attempts")
    if (
        measurement.get("objective_completed") is not True
        or progress_gained != RED_CAVE_PROGRESS_UNITS_REQUIRED
        or progress_required != RED_CAVE_PROGRESS_UNITS_REQUIRED
        or _integer(measurement, "faints") != 0
        or _integer(measurement, "candidate_decisions") != 0
        or _integer(measurement, "controller_actions") <= 0
        or _integer(measurement, "frames_executed") <= 0
        or battles > _integer(plan_acceptance, "maximum_battles")
        or steps > _integer(plan_acceptance, "maximum_steps")
        or budgeted > _integer(
            plan_acceptance,
            "maximum_budgeted_center_calls",
        )
        or transitions + required_recovery + optional_recovery != budgeted
        or budgeted + cleanup != total
        or cleanup != _integer(plan_acceptance, "required_cleanup_calls")
        or optional_recovery != _integer(
            plan_acceptance,
            "optional_recovery_calls",
        )
        or attempts != successes + blocked
        or successes != steps
    ):
        raise RedCaveVenuePriorError(
            "Cave measurement does not satisfy its prospective arithmetic"
        )


def _require_current_cave_venue(venue: TrainingVenue) -> None:
    walker = venue.fresh_walk_to_grass()
    if (
        not isinstance(venue, TrainingVenue)
        or venue is not DIGLETTS_CAVE_TRAINING_VENUE
        or venue.heal_and_return is not _digletts_cave_heal_and_return
        or venue.move_slot is not _team_training_move_slot
        or venue.move_guard is not _team_training_move_guard
        or venue.walk_to_grass_factory is not _new_digletts_cave_walker
        or not isinstance(venue.walk_to_grass, WarpSafeVenueWalker)
        or not isinstance(walker, WarpSafeVenueWalker)
        or walker is venue.walk_to_grass
        or walker.expected_map_id != venue.map_id
        or walker.excluded_coordinates != DIGLETTS_CAVE_EXIT_COORDINATES
        or red_cave_venue_binding_sha256()
        != "e486eb4a7d9c0f84908d7b94df00a9af19ee84da33c163f9e56ffc701ac8a326"
    ):
        raise RedCaveVenuePriorError(
            "current Cave venue differs from the accepted operating seam"
        )


def _committed_runtime_rows(
    repository_root: Path,
    *,
    revision: str,
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "path": relative_path,
            "sha256": hashlib.sha256(
                _committed_runtime_blob(
                    repository_root,
                    revision=revision,
                    relative_path=relative_path,
                )
            ).hexdigest(),
        }
        for relative_path in _CRITICAL_RUNTIME_PATHS
    )


def _committed_runtime_blob(
    repository_root: Path,
    *,
    revision: str,
    relative_path: str,
) -> bytes:
    if relative_path.startswith("src/pokemon_red_completion/"):
        return committed_executable_source_blob(
            repository_root,
            revision=revision,
            relative_path=relative_path,
        )
    if relative_path != "scripts/run_red_cave_venue_measurement.py":
        raise RedCaveVenuePriorError("Cave critical runtime path is invalid")
    completed = subprocess.run(
        ("git", "show", f"{revision}:{relative_path}"),
        cwd=repository_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RedCaveVenuePriorError(
            "Cave measurement runner source is unavailable at the bound commit"
        )
    return completed.stdout


def _changed_paths_between(
    repository_root: Path,
    observed_commit: str,
    current_commit: str,
) -> tuple[str, ...]:
    completed = subprocess.run(
        (
            "git",
            "diff",
            "--name-only",
            "-z",
            f"{observed_commit}..{current_commit}",
        ),
        cwd=repository_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RedCaveVenuePriorError(
            "Cave source compatibility could not inspect the published delta"
        )
    try:
        paths = completed.stdout.decode("utf-8").split("\0")
    except UnicodeDecodeError as error:
        raise RedCaveVenuePriorError(
            "Cave source delta contains an invalid path"
        ) from error
    return tuple(sorted(path for path in paths if path))


def _runtime_rows_sha256(
    rows: tuple[dict[str, object], ...],
    *,
    scope: str,
) -> str:
    if len(rows) != len(_CRITICAL_RUNTIME_PATHS):
        raise RedCaveVenuePriorError("Cave runtime file set is incomplete")
    return canonical_sha256(
        {
            "schema": "pokemon.red.cave-critical-runtime-files.v1",
            "scope": scope,
            "files": list(rows),
        }
    )


def _selected_rows_sha256(
    row_map: Mapping[str, str],
    paths: tuple[str, ...],
    *,
    scope: str,
) -> str:
    try:
        rows = [{"path": path, "sha256": row_map[path]} for path in paths]
    except KeyError as error:
        raise RedCaveVenuePriorError(
            "Cave operational source group is incomplete"
        ) from error
    return canonical_sha256(
        {
            "schema": "pokemon.red.cave-operational-source-group.v1",
            "scope": scope,
            "files": rows,
        }
    )


def _jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_jsonable(item) for item in value), key=repr)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise RedCaveVenuePriorError(
        "Cave operational contract contains a non-canonical value"
    )


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise RedCaveVenuePriorError(f"published Cave evidence {key} is invalid")
    return value


def _integer(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedCaveVenuePriorError(f"published Cave evidence {key} is invalid")
    return value


def _require_digest(value: object, *, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedCaveVenuePriorError(f"Cave {subject} digest is invalid")


__all__ = [
    "RED_CAVE_MEASUREMENT_SOURCE_BUNDLE_SHA256",
    "RED_CAVE_MEASUREMENT_SOURCE_COMMIT",
    "RED_CAVE_SOURCE_COMPATIBILITY_ATTESTATION_ID",
    "RED_CAVE_VENUE_MEASUREMENT_PUBLIC_PLAN_SHA256",
    "RED_CAVE_VENUE_MEASUREMENT_PUBLIC_RESULT_SHA256",
    "RED_CAVE_VENUE_OPERATIONAL_CONTRACT_ID",
    "RED_CAVE_VENUE_PRIOR_COMPOSITION_SCHEMA",
    "RED_CAVE_VENUE_PRIOR_EVIDENCE_ID",
    "RedCaveVenuePriorComposition",
    "RedCaveVenuePriorError",
    "attest_red_cave_source_compatibility",
    "compose_red_cave_venue_prior",
    "red_cave_operational_contract",
]
