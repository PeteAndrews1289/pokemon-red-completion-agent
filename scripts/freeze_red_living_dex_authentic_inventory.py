#!/usr/bin/env python3
"""Inventory authentic Red option menus and freeze one path-free 8+4 plan.

This command is deliberately action-free.  It authenticates the already-frozen
goal-manager capture bank, restores only repeatable nonsealed and globally
unconsumed states, enumerates existing bounded semantic bindings, constructs the
complete living-Pokedex menus, and publishes one immutable private plan.  It has
no behavior issuer, model, teacher, claim writer, controller delegate, outcome
observer invocation, or full-game path.
"""

# ruff: noqa: E402 -- pin reviewed script/package origins before project imports.

from __future__ import annotations

import argparse
import json
import re
import runpy
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Never, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

_LEGACY_SUPPORT = runpy.run_path(
    str(SCRIPTS_ROOT / "freeze_red_living_dex_multifamily_pilot.py"),
    run_name="red_living_dex_authentic_inventory_legacy_support",
)

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_collection_runtime import (
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
)
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.goal_manager_trajectory import ordered_goal_manager_question
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    open_private_root,
    validate_private_record,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfile
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedLivingDexContextFacts,
    RedLivingDexOutcomeSnapshot,
    RedLivingDexScenarioBudgets,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    RedLivingDexActionFreeInventory,
    RedLivingDexActionFreeInventoryError,
    RedLivingDexInventoryObserverBinding,
    build_verified_red_living_dex_goal_scenario,
    freeze_red_living_dex_action_free_inventory,
)
from pokemon_red_completion.red_living_dex_option_materializer import (
    RedLivingDexMaterializationPlan,
    bind_red_living_dex_observer_provenance,
    red_living_dex_verified_capture_scenario_identity,
)
from pokemon_red_completion.rom import verify_rom
from pokemon_red_completion.runtime_identity import (
    build_runtime_identity,
    require_pyboy_import_origins,
)

LANE_ID = "repeatable-red-living-dex-option-value-calibration-v1"
PLAN_SCHEMA = "pokemon.red.private-living-dex-authentic-inventory-plan.v1"
RESULT_SCHEMA = "pokemon.red.living-dex-authentic-inventory-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-authentic-inventory-failure.v1"
PLAN_RECORD_ID = "red-living-dex-authentic-inventory-plan-v1"
PLAN_RECORD_KIND = "red-living-dex-authentic-inventory-plan-v1"
MAXIMUM_CONTROLLER_ACTIONS = 5_000
MAXIMUM_EMULATOR_FRAMES = 4_000_000
MATERIALIZER_UNCLAIMED_STATUS = "absent"
_MATERIALIZER_CLAIMED_STATUSES = frozenset(
    {"complete", "failed", "interrupted", "partial"}
)

_MAPPED_GOAL_KINDS = frozenset(
    {
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.DEVELOP_TEAM,
        GoalKind.EVOLVE_SPECIES,
        GoalKind.RESUPPLY,
        GoalKind.MANAGE_STORAGE,
        GoalKind.EXPLORE,
    }
)


class RedLivingDexAuthenticInventoryError(RuntimeError):
    """The bounded authentic inventory failed at one sanitized stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
        super().__init__(self.stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RedLivingDexAuthenticInventoryError("arguments")


class _ForbiddenActionPort:
    """Make an accidental provider action fail before reaching an emulator."""

    def execute(self, _action: object) -> object:
        raise RedLivingDexAuthenticInventoryError("controller_authority_forbidden")


@dataclass(frozen=True, slots=True)
class _ProjectedInventory:
    inventory: RedLivingDexActionFreeInventory
    plan: RedLivingDexMaterializationPlan
    private_rows: dict[str, dict[str, object]]
    authenticated_contexts: int
    emulator_states_read: int
    excluded_counts: dict[str, int]
    emulator_frames_advanced: int


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "source_authentication"
        source_commit, source_bundle = _authenticate_source(args)
        stage = "private_input_authentication"
        (
            rom_path,
            rom_sha256,
            rom_bytes,
            contexts,
            catalog_sha256,
            context_plan_sha256,
        ) = _authenticate_inputs(args, source_commit, source_bundle)
        stage = "action_free_inventory"
        projected = _inventory(
            args,
            rom_path=rom_path,
            rom_sha256=rom_sha256,
            contexts=contexts,
            source_bundle=source_bundle,
        )
        stage = "private_plan_encoding"
        document, private_plan_sha256 = _private_plan_document(
            source_commit=source_commit,
            source_bundle=source_bundle,
            rom_sha256=rom_sha256,
            registry_sha256=_sha(args.expected_registry_sha256, "registry"),
            catalog_sha256=catalog_sha256,
            context_plan_sha256=context_plan_sha256,
            projected=projected,
        )
        stage = "protected_input_integrity"
        _require_protected_input_integrity(
            rom_path=rom_path,
            rom_sha256=rom_sha256,
            source_bundle=source_bundle,
        )
        stage = "private_plan_publication"
        result = _publish(
            args,
            document=document,
            private_plan_sha256=private_plan_sha256,
            projected=projected,
        )
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except RedLivingDexAuthenticInventoryError as error:
        failure_stage = error.stage
    except RedLivingDexActionFreeInventoryError:
        failure_stage = stage
    except BaseException:
        failure_stage = stage
    print(
        json.dumps(
            _failure_receipt(failure_stage),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _authenticate_source(args: argparse.Namespace) -> tuple[str, str]:
    function = cast(Any, _LEGACY_SUPPORT["_authenticate_source"])
    try:
        result = function(args)
    except BaseException as error:
        raise RedLivingDexAuthenticInventoryError(
            getattr(error, "stage", "source_authentication")
        ) from None
    return cast(tuple[str, str], result)


def _authenticate_inputs(
    args: argparse.Namespace,
    source_commit: str,
    source_bundle: str,
) -> tuple[Path, str, bytes, tuple[Any, ...], str, str]:
    function = cast(Any, _LEGACY_SUPPORT["_authenticate_inputs"])
    try:
        result = function(args, source_commit, source_bundle)
    except BaseException as error:
        raise RedLivingDexAuthenticInventoryError(
            getattr(error, "stage", "private_input_authentication")
        ) from None
    return cast(tuple[Path, str, bytes, tuple[Any, ...], str, str], result)


def _inventory(
    args: argparse.Namespace,
    *,
    rom_path: Path,
    rom_sha256: str,
    contexts: tuple[Any, ...],
    source_bundle: str,
) -> _ProjectedInventory:
    runtime_identity = build_runtime_identity()
    require_pyboy_import_origins(runtime_identity)
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    scenarios = []
    private_rows: dict[str, dict[str, object]] = {}
    excluded: Counter[str] = Counter()
    states_read = 0
    total_frames = 0
    budgets = RedLivingDexScenarioBudgets(
        MAXIMUM_CONTROLLER_ACTIONS,
        MAXIMUM_EMULATOR_FRAMES,
    )

    with PyBoyAdapter(
        rom_path,
        watch=False,
        speed=None,
        expected_rom=POKEMON_RED_US_REV_0,
    ) as emulator:
        require_pyboy_import_origins(runtime_identity)
        for private in contexts:
            assignment = private.assignment
            catalog_entry = private.catalog_entry
            capture = private.capture
            profile = private.profile
            if not isinstance(capture, GoalManagerContextCapture) or not isinstance(
                profile, RedGoalContextProfile
            ):
                raise RedLivingDexAuthenticInventoryError("context_authentication")
            if assignment.partition not in {"train", "validation"}:
                excluded["sealed_or_unsupported_partition"] += 1
                continue
            if not private.root_available:
                excluded["consumed_physical_root"] += 1
                continue
            scenario_identity = red_living_dex_verified_capture_scenario_identity(capture)
            episode_id = f"redldx-{scenario_identity}"
            if not _materializer_episode_is_unclaimed(store, episode_id):
                excluded["existing_materializer_claim"] += 1
                continue

            emulator.load_state_bytes(capture.state_bytes)
            states_read += 1
            frame_before = emulator.frame_count
            if emulator.pressed_buttons:
                raise RedLivingDexAuthenticInventoryError("controller_effect_authentication")
            reader = PokemonRedStateReader(emulator)
            runtime = build_red_goal_context_runtime(
                profile=profile,
                capture=capture,
                emulator=emulator,
                reader=reader,
            )
            observation = runtime.adapter.observe()
            actions = CountingExecutor(_ForbiddenActionPort())
            bindings = runtime.enumerator(actions).enumerate(observation)
            _authenticate_historical_menu(
                assignment,
                catalog_entry,
                observation,
                bindings,
            )
            mapped_available = tuple(
                binding
                for binding in bindings.bindings
                if binding.kind in _MAPPED_GOAL_KINDS
            )
            if len(mapped_available) < 3:
                excluded["fewer_than_three_mapped_available_options"] += 1
                _require_zero_effects(emulator, actions, frame_before)
                continue
            if not observation.party.members:
                excluded["empty_party_observation"] += 1
                _require_zero_effects(emulator, actions, frame_before)
                continue

            partition = "train" if assignment.partition == "train" else "development"
            before_binding = canonical_sha256(
                {
                    "capture_id": capture.capture_id,
                    "envelope_sha256": capture.envelope_sha256,
                    "profile_sha256": profile.profile_sha256,
                    "purpose": "living-dex-before-observer",
                    "schema": "pokemon.red.private-living-dex-before-observer.v1",
                    "source_bundle_sha256": source_bundle,
                    "state_sha256": capture.state_sha256,
                }
            )
            before = _before_snapshot(
                capture,
                observation,
                bindings,
                observer_binding_sha256=before_binding,
            )
            facts = _context_facts(observation, bindings, profile)
            location_ref = _location_ref(observation)
            observer_binding = canonical_sha256(
                {
                    "capture_id": capture.capture_id,
                    "envelope_sha256": capture.envelope_sha256,
                    "profile_sha256": profile.profile_sha256,
                    "purpose": "living-dex-fresh-after-observer",
                    "schema": "pokemon.red.private-living-dex-after-observer.v1",
                    "source_bundle_sha256": source_bundle,
                    "state_sha256": capture.state_sha256,
                }
            )
            attestation = _checkpoint_attestation(
                assignment=assignment,
                catalog_entry=catalog_entry,
                capture=capture,
                profile=profile,
                physical_root_sha256=private.root_consumption_sha256,
                partition=partition,
            )

            scenario = build_verified_red_living_dex_goal_scenario(
                capture,
                profile,
                before,
                facts,
                budgets,
                bindings,
                partition=partition,
                location_ref=location_ref,
                checkpoint_attestation_sha256=canonical_sha256(attestation),
                observer_binding_sha256=observer_binding,
                observe_after=RedLivingDexInventoryObserverBinding(observer_binding),
            )
            _require_zero_effects(emulator, actions, frame_before)
            total_frames += emulator.frame_count - frame_before
            scenarios.append(scenario)
            private_rows[scenario.scenario_identity_sha256] = {
                "assignment_id": assignment.assignment_id,
                "attestation": attestation,
                "capture_id": capture.capture_id,
                "context_id": catalog_entry.context_id,
                "materialization_identity": scenario.private_identity_dict(),
                "partition": partition,
                "physical_root_sha256": private.root_consumption_sha256,
                "profile_sha256": profile.profile_sha256,
                "slot_id": assignment.slot_id,
            }

    inventory, plan = freeze_red_living_dex_action_free_inventory(tuple(scenarios))
    return _ProjectedInventory(
        inventory=inventory,
        plan=plan,
        private_rows=private_rows,
        authenticated_contexts=len(contexts),
        emulator_states_read=states_read,
        excluded_counts={key: excluded[key] for key in sorted(excluded)},
        emulator_frames_advanced=total_frames,
    )


def _authenticate_historical_menu(
    assignment: Any,
    catalog_entry: Any,
    observation: RedGoalObservation,
    bindings: GoalBindingSet,
) -> None:
    question = ordered_goal_manager_question(
        assignment_id=assignment.assignment_id,
        decision_index=0,
        situation=observation.situation,
        opportunities=bindings.opportunities,
    )
    if (
        question.ordered_policy_input_sha256 != catalog_entry.question_sha256
        or question.policy_context_sha256 != catalog_entry.policy_context_sha256
        or question.available_menu_sha256 != catalog_entry.available_menu_sha256
        or goal_binding_manifest_sha256(bindings)
        != catalog_entry.binding_manifest_sha256
        or tuple(item.kind for item in bindings.bindings)
        != catalog_entry.available_goal_kinds
    ):
        raise RedLivingDexAuthenticInventoryError("historical_context_replay")


def _materializer_episode_is_unclaimed(
    store: PrivateArtifactRoot,
    episode_id: str,
) -> bool:
    status = store.inspect_episode_state(episode_id).status
    if status == MATERIALIZER_UNCLAIMED_STATUS:
        return True
    if status in _MATERIALIZER_CLAIMED_STATUSES:
        return False
    raise RedLivingDexAuthenticInventoryError("materializer_episode_authentication")


def _before_snapshot(
    capture: GoalManagerContextCapture,
    observation: RedGoalObservation,
    bindings: GoalBindingSet,
    *,
    observer_binding_sha256: str,
) -> RedLivingDexOutcomeSnapshot:
    resources = tuple(
        sorted(
            (
                ("red.resource.capture-items", observation.capture_item_count),
                ("red.resource.recovery-items", observation.recovery_item_count),
            )
        )
    )
    snapshot = RedLivingDexOutcomeSnapshot(
        scenario_identity_sha256=(
            red_living_dex_verified_capture_scenario_identity(capture)
        ),
        scenario_repeatable=True,
        observation=observation.collection_observation,
        executable_dependency_count=sum(
            binding.kind in _MAPPED_GOAL_KINDS for binding in bindings.bindings
        ),
        usable_consumable_units=sum(units for _resource, units in resources),
        resource_pool_units=resources,
        party_health_units=sum(member.hp for member in observation.party.members),
        party_health_capacity=sum(
            member.max_hp for member in observation.party.members
        ),
        irreversible_constraints_remaining=_irreversible_constraints(observation),
        controller_actions=0,
        emulator_frames=0,
        observer_provenance_sha256="0" * 64,
    )
    return bind_red_living_dex_observer_provenance(
        snapshot,
        observer_binding_sha256=observer_binding_sha256,
    )


def _context_facts(
    observation: RedGoalObservation,
    bindings: GoalBindingSet,
    profile: RedGoalContextProfile,
) -> RedLivingDexContextFacts:
    report = observation.collection.collection
    missing = frozenset(report.missing_living)
    retained = frozenset(
        item.species_ref for item in observation.collection_observation.specimens
    )
    blocked = 0
    for species_ref in missing:
        method = RED_ACQUISITION_CATALOG.method_for(species_ref)
        if method.transforms_precursor and method.consumes_species_ref not in retained:
            blocked += 1
    config = profile.manager_config
    requirement = config.required_party_size * config.required_team_level
    current = sum(
        min(member.level, config.required_team_level)
        for member in observation.party.members[: config.required_party_size]
    )
    return RedLivingDexContextFacts(
        incomplete_dependency_frontier=len(missing),
        blocked_immediate_successors=blocked,
        access_blocked_targets=0,
        lower_bound_consumable_requirement=(
            1
            if missing
            and any(
                item.kind is GoalKind.ACQUIRE_SPECIES for item in bindings.bindings
            )
            else 0
        ),
        party_readiness_requirement=requirement,
        current_party_readiness=current,
        unresolved_dependencies=blocked,
    )


def _irreversible_constraints(observation: RedGoalObservation) -> int:
    missing = frozenset(observation.collection.collection.missing_living)
    return sum(
        not method.repeatable and method.species_ref in missing
        for method in RED_ACQUISITION_CATALOG.methods
    )


def _location_ref(observation: RedGoalObservation) -> str:
    map_id = observation.raw.map_id
    if type(map_id) is not int or not 0 <= map_id <= 0xFF:  # noqa: E721
        raise RedLivingDexAuthenticInventoryError("location_authentication")
    return f"red.start-map.{map_id}"


def _checkpoint_attestation(
    *,
    assignment: Any,
    catalog_entry: Any,
    capture: GoalManagerContextCapture,
    profile: RedGoalContextProfile,
    physical_root_sha256: str,
    partition: str,
) -> dict[str, object]:
    return {
        "assignment_id": assignment.assignment_id,
        "capture_id": capture.capture_id,
        "context_id": catalog_entry.context_id,
        "envelope_sha256": capture.envelope_sha256,
        "materializer_episode_status": MATERIALIZER_UNCLAIMED_STATUS,
        "nonsealed": True,
        "partition": partition,
        "physical_root_available": True,
        "physical_root_sha256": physical_root_sha256,
        "profile_sha256": profile.profile_sha256,
        "repeatable": True,
        "schema": "pokemon.red.private-living-dex-capture-attestation.v1",
        "state_sha256": capture.state_sha256,
    }


def _require_protected_input_integrity(
    *,
    rom_path: Path,
    rom_sha256: str,
    source_bundle: str,
) -> None:
    if verify_rom(rom_path).sha256 != rom_sha256 or rom_sha256 != (
        POKEMON_RED_US_REV_0.sha256
    ):
        raise RedLivingDexAuthenticInventoryError("protected_input_integrity")
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise RedLivingDexAuthenticInventoryError("protected_input_integrity")


def _require_zero_effects(
    emulator: PyBoyAdapter,
    actions: CountingExecutor,
    frame_before: int,
) -> None:
    if (
        actions.actions_executed != 0
        or emulator.frame_count != frame_before
        or emulator.pressed_buttons
    ):
        raise RedLivingDexAuthenticInventoryError(
            "action_free_effect_authentication"
        )


def _private_plan_document(
    *,
    source_commit: str,
    source_bundle: str,
    rom_sha256: str,
    registry_sha256: str,
    catalog_sha256: str,
    context_plan_sha256: str,
    projected: _ProjectedInventory,
) -> tuple[dict[str, object], str]:
    selected_rows = []
    for scenario in projected.plan.scenarios:
        try:
            selected_rows.append(projected.private_rows[scenario.scenario_identity_sha256])
        except KeyError:
            raise RedLivingDexAuthenticInventoryError(
                "selected_scenario_metadata_authentication"
            ) from None
    payload: dict[str, object] = {
        "behavior_draws": 0,
        "context_catalog_sha256": catalog_sha256,
        "context_plan_sha256": context_plan_sha256,
        "controller_actions": 0,
        "emulator_frames_advanced": projected.emulator_frames_advanced,
        "inventory": projected.inventory.public_dict(),
        "lane_id": LANE_ID,
        "materialization_plan": projected.plan.public_dict(),
        "model_fits": 0,
        "model_predictions": 0,
        "outcomes_observed": 0,
        "registry_sha256": registry_sha256,
        "rom_sha256": rom_sha256,
        "root_claims": 0,
        "scenarios": selected_rows,
        "schema": PLAN_SCHEMA,
        "source_bundle_sha256": source_bundle,
        "source_commit": source_commit,
        "status": "frozen_before_claim_randomization_action_outcome_or_fit",
        "teacher_queries": 0,
    }
    validate_private_record(payload)
    private_plan_sha256 = canonical_sha256(payload)
    document = {**payload, "private_plan_sha256": private_plan_sha256}
    validate_private_record(document)
    return document, private_plan_sha256


def _publish(
    args: argparse.Namespace,
    *,
    document: dict[str, object],
    private_plan_sha256: str,
    projected: _ProjectedInventory,
) -> dict[str, object]:
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    record = store.publish_sealed_record(
        PLAN_RECORD_ID,
        kind=PLAN_RECORD_KIND,
        record=document,
    )
    return {
        "authenticated_contexts": projected.authenticated_contexts,
        "behavior_draws": 0,
        "claim_boundary": (
            "action-free authentic curriculum plan only; no outcome, fit, authority, "
            "policy-quality, completion, or transfer claim"
        ),
        "controller_actions": 0,
        "emulator_frames_advanced": projected.emulator_frames_advanced,
        "emulator_states_read": projected.emulator_states_read,
        "excluded_counts": projected.excluded_counts,
        "inventory": projected.inventory.public_dict(),
        "materialization_plan": projected.plan.public_dict(),
        "model_fits": 0,
        "model_predictions": 0,
        "outcomes_observed": 0,
        "plan_manifest_sha256": record.summary.manifest_sha256,
        "private_identity_fields_published": 0,
        "private_path_fields": 0,
        "private_plan_sha256": private_plan_sha256,
        "root_claims": 0,
        "schema": RESULT_SCHEMA,
        "status": "authenticated_action_free_8_plus_4_plan_frozen",
        "teacher_queries": 0,
    }


def _failure_receipt(stage: str) -> dict[str, object]:
    safe = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
    return {
        "behavior_draws": 0,
        "controller_actions": 0,
        "emulator_frames_advanced": 0,
        "failure_stage": safe,
        "model_fits": 0,
        "model_predictions": 0,
        "outcomes_observed": 0,
        "private_identity_fields_published": 0,
        "private_path_fields": 0,
        "root_claims": 0,
        "schema": FAILURE_SCHEMA,
        "status": "failed_closed",
        "teacher_queries": 0,
    }


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RedLivingDexAuthenticInventoryError(
            f"{subject.replace(' ', '_')}_authentication"
        )
    return value


if __name__ == "__main__":
    raise SystemExit(main())
