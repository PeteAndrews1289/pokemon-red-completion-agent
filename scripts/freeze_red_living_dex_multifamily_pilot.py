#!/usr/bin/env python3
"""Inventory untouched Red roots and freeze one family/root-disjoint pilot.

This command is deliberately action-free: it may restore authenticated private
states and read cartridge-derived routes, but it has no controller executor,
model scorer, teacher, outcome collector, or claim writer.  Its only mutation is
one immutable private plan record after every context and menu has passed.
"""

# ruff: noqa: E402 -- pin repository import roots before project imports.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

import run_red_dual_capability_preflight as support

from pokemon_red_completion.blaine import (
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.encounters import ENCOUNTER_LOG_VARIABLE
from pokemon_red_completion.gen1_field_moves import gen1_field_capabilities
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogEntry,
    parse_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerAssignment,
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.observation import ItemId, PokemonRedStateReader
from pokemon_red_completion.private_artifacts import (
    open_private_root,
    validate_private_record,
)
from pokemon_red_completion.provenance import (
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionKind,
    RedAcquisitionMethod,
)
from pokemon_red_completion.red_boxed_level_evolution import (
    BoxedLevelEvolutionPlan,
    ObservedSemanticBoundaryBinding,
)
from pokemon_red_completion.red_collection import (
    red_internal_species_id,
    red_species_number,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    SemanticCaptureVenue,
    SemanticVenueCapturePlan,
    SemanticVenueRouteBinding,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import parse_red_goal_context_profile
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
    RedDependencyPrivateBinding,
)
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    RedDependencySpeciesBinding,
)
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    RedMultifamilyContext,
    RedMultifamilyCurriculumPlan,
    RedMultifamilyInventory,
    freeze_two_family_curriculum,
    inventory_red_multifamily_contexts,
    map_id_for_wild_source,
    raw_exit_coordinates,
)
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID
from pokemon_red_completion.red_training_transitions import RED_TRAINING_FLY_CENTER_MAPS
from pokemon_red_completion.rom import resolve_rom_path, verify_rom
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.runtime_identity import (
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)

LANE_ID = "red-living-dex-multifamily-option-value-curriculum-v2"
PLAN_SCHEMA = "pokemon.red.private-living-dex-multifamily-pilot-plan.v2"
RESULT_SCHEMA = "pokemon.red.living-dex-multifamily-pilot-freeze-result.v2"
FAILURE_SCHEMA = "pokemon.red.living-dex-multifamily-pilot-freeze-failure.v2"
PLAN_RECORD_ID = "red-living-dex-multifamily-pilot-plan-v2"
PLAN_RECORD_KIND = "red-living-dex-multifamily-pilot-plan-v2"
PC_GOAL_YX = (4, 13)
TRAINING_GOAL_YX = (3, 3)
TRIALS_PER_CANDIDATE = 4

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class MultifamilyPilotFreezeError(RuntimeError):
    """One sanitized zero-input freeze stage failed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
        super().__init__(self.stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise MultifamilyPilotFreezeError("arguments")


@dataclass(frozen=True, slots=True)
class _AuthenticatedContext:
    assignment: GoalManagerAssignment
    catalog_entry: GoalManagerContextCatalogEntry
    capture: object
    profile: object
    context_identity_sha256: str
    root_consumption_sha256: str
    root_available: bool


@dataclass(frozen=True, slots=True)
class _FamilyMechanics:
    family_identity_sha256: str
    species_binding: RedDependencySpeciesBinding
    source_id: str
    source_map_id: int
    capture_plan: SemanticVenueCapturePlan
    evolution_plan: BoxedLevelEvolutionPlan

    def private_dict(self) -> dict[str, object]:
        pc_access = self.evolution_plan.route_to_pc
        pc_document: dict[str, object]
        if isinstance(pc_access, SemanticVenueRouteBinding):
            pc_document = {
                "pc_access_kind": "semantic_route",
                "route_to_pc_plan_sha256": pc_access.plan_sha256,
                "route_to_pc_planner_binding_sha256": (pc_access.planner_binding_sha256),
                "route_to_pc_cost": pc_access.plan.cost,
            }
        else:
            pc_document = {
                "pc_access_kind": "observed_semantic_boundary",
                "pc_boundary_binding_sha256": pc_access.binding_sha256,
                "pc_boundary_observer_binding_sha256": (pc_access.observer_binding_sha256),
                "route_to_pc_cost": 0,
            }
        return {
            "family_identity_sha256": self.family_identity_sha256,
            "precursor_species_ref": self.species_binding.precursor_species_ref,
            "evolved_species_ref": self.species_binding.evolved_species_ref,
            "source_id": self.source_id,
            "source_map_id": self.source_map_id,
            "capture_skill_binding_sha256": self.capture_plan.skill_binding_sha256,
            "capture_route_plan_sha256": self.capture_plan.route.plan_sha256,
            "capture_route_cost": self.capture_plan.route.plan.cost,
            "capture_exit_coordinates": [
                list(value)
                for value in sorted(self.capture_plan.venue.excluded_coordinates)  # type: ignore[union-attr]
            ],
            "evolution_skill_binding_sha256": self.evolution_plan.skill_binding_sha256,
            "precursor_internal_species_id": (self.evolution_plan.precursor_internal_species_id),
            "evolved_internal_species_id": self.evolution_plan.evolved_internal_species_id,
            "current_box_index": self.evolution_plan.current_box_index,
            "precursor_box_slot": self.evolution_plan.precursor_box_slot,
            "deposit_party_slot": self.evolution_plan.deposit_party_slot,
            "deposit_internal_species_id": (self.evolution_plan.deposit_internal_species_id),
            **pc_document,
            "route_to_training_plan_sha256": (self.evolution_plan.route_to_training.plan_sha256),
            "route_to_training_cost": self.evolution_plan.route_to_training.plan.cost,
            "training_binding_sha256": self.evolution_plan.training_binding_sha256,
        }


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
        rom_path, rom_sha256, rom_bytes, contexts, catalog_sha256, context_plan_sha256 = (
            _authenticate_inputs(args, source_commit, source_bundle)
        )
        stage = "action_free_inventory"
        inventory, mechanics, frames = _inventory(
            rom_path,
            rom_bytes,
            rom_sha256,
            source_bundle,
            contexts,
        )
        stage = "family_root_partition_freeze"
        plan = _freeze(inventory, mechanics)
        stage = "private_plan_encoding"
        document, frozen_plan_sha256 = _private_plan_document(
            source_commit=source_commit,
            source_bundle=source_bundle,
            rom_sha256=rom_sha256,
            registry_sha256=_sha(args.expected_registry_sha256, "registry"),
            catalog_sha256=catalog_sha256,
            context_plan_sha256=context_plan_sha256,
            inventory=inventory,
            curriculum=plan,
            mechanics=mechanics,
        )
        stage = "private_plan_publication"
        result = _publish(
            args,
            document=document,
            plan_sha256=frozen_plan_sha256,
            inventory=inventory,
            curriculum=plan,
            emulator_frames_advanced=frames,
        )
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except MultifamilyPilotFreezeError as error:
        failure_stage = error.stage
    except BaseException:
        failure_stage = stage
    print(
        json.dumps(
            {
                "schema": FAILURE_SCHEMA,
                "status": "failed_closed",
                "failure_stage": failure_stage,
                "controller_actions": 0,
                "teacher_queries": 0,
                "model_predictions": 0,
                "outcomes_observed": 0,
                "roots_claimed": 0,
                "private_paths_published": 0,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _authenticate_source(args: argparse.Namespace) -> tuple[str, str]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    expected_commit = _commit(args.expected_source_commit, "source")
    expected_bundle = _sha(args.expected_source_bundle_sha256, "source bundle")
    actual_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if source.git_commit != expected_commit or actual_bundle != expected_bundle:
        raise MultifamilyPilotFreezeError("source_authentication")
    if os.environ.get(ENCOUNTER_LOG_VARIABLE, "").strip():
        raise MultifamilyPilotFreezeError("trajectory_side_channel_environment")
    return expected_commit, expected_bundle


def _authenticate_inputs(
    args: argparse.Namespace,
    source_commit: str,
    source_bundle: str,
) -> tuple[Path, str, bytes, tuple[_AuthenticatedContext, ...], str, str]:
    del source_commit, source_bundle
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    if rom.sha256 != POKEMON_RED_US_REV_0.sha256:
        raise MultifamilyPilotFreezeError("rom_authentication")
    rom_bytes = support._read_external_bytes(
        rom_path,
        maximum_bytes=4 * 1024 * 1024,
        forbidden=(),
        allow_rom=True,
    )
    if hashlib.sha256(rom_bytes).hexdigest() != rom.sha256:
        raise MultifamilyPilotFreezeError("rom_authentication")

    registry_commit = _commit(args.registry_source_commit, "registry source")
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        registry_commit,
    )
    if registry.registry_sha256 != _sha(args.expected_registry_sha256, "registry"):
        raise MultifamilyPilotFreezeError("registry_authentication")
    catalog_bytes = support._read_external_bytes(
        args.context_catalog,
        maximum_bytes=support._MAX_DOCUMENT_BYTES,
        forbidden=(rom_path,),
    )
    if hashlib.sha256(catalog_bytes).hexdigest() != _sha(
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise MultifamilyPilotFreezeError("context_catalog_authentication")
    catalog = parse_goal_manager_context_catalog(catalog_bytes, registry)
    plan_bytes = support._read_external_bytes(
        args.context_plan,
        maximum_bytes=support._MAX_DOCUMENT_BYTES,
        forbidden=(rom_path, args.context_catalog),
    )
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    if plan_sha256 != _sha(args.expected_context_plan_sha256, "context plan"):
        raise MultifamilyPilotFreezeError("context_plan_authentication")

    claim_registry = open_fixed_account_claim_registry()
    authenticated: list[_AuthenticatedContext] = []
    with fixed_account_claim_registry_lease(claim_registry, exclusive=False):
        for assignment in (registry.assignment(slot.slot_id) for slot in registry.slots):
            if assignment.partition not in {"train", "validation"}:
                continue
            entry = catalog.entry(assignment.slot_id)
            plan_entry = support._context_plan_entry(
                plan_bytes,
                registry_sha256=registry.registry_sha256,
                source_commit=registry.execution.source_commit,
                selected_slot_id=assignment.slot_id,
            )
            forbidden = (rom_path, args.context_catalog, args.context_plan)
            state_bytes = support._read_external_bytes(
                plan_entry.state,
                maximum_bytes=support._MAX_STATE_BYTES,
                forbidden=forbidden,
            )
            envelope_bytes = support._read_external_bytes(
                plan_entry.envelope,
                maximum_bytes=support._MAX_DOCUMENT_BYTES,
                forbidden=(*forbidden, plan_entry.state),
            )
            profile_bytes = support._read_external_bytes(
                plan_entry.profile,
                maximum_bytes=support._MAX_DOCUMENT_BYTES,
                forbidden=(*forbidden, plan_entry.state, plan_entry.envelope),
            )
            capture = parse_goal_manager_context_capture(state_bytes, envelope_bytes)
            profile = parse_red_goal_context_profile(profile_bytes)
            if (
                plan_entry.slot_id != assignment.slot_id
                or capture.capture_id != assignment.slot_id
                or profile.profile_id != assignment.slot_id
                or entry.assignment_id != assignment.assignment_id
                or capture.capture_id != entry.capture_id
                or capture.state_sha256 != entry.state_sha256
                or capture.envelope_sha256 != entry.envelope_sha256
                or capture.state_sha256 != hashlib.sha256(state_bytes).hexdigest()
                or capture.envelope_sha256 != hashlib.sha256(envelope_bytes).hexdigest()
                or profile.profile_sha256 != hashlib.sha256(profile_bytes).hexdigest()
            ):
                raise MultifamilyPilotFreezeError("context_authentication")
            context_identity = canonical_sha256(
                {
                    "schema": "pokemon.red.private-multifamily-context.v1",
                    "registry_sha256": registry.registry_sha256,
                    "context_catalog_sha256": catalog.catalog_sha256,
                    "context_id": entry.context_id,
                    "assignment_id": assignment.assignment_id,
                    "root_lineage_id": assignment.root_lineage_id,
                    "slot_id": assignment.slot_id,
                    "state_sha256": capture.state_sha256,
                    "envelope_sha256": capture.envelope_sha256,
                    "profile_sha256": profile.profile_sha256,
                    "rom_sha256": rom.sha256,
                }
            )
            physical_root = root_consumption_sha256(
                state_sha256=capture.state_sha256,
                envelope_sha256=capture.envelope_sha256,
            )
            authenticated.append(
                _AuthenticatedContext(
                    assignment,
                    entry,
                    capture,
                    profile,
                    context_identity,
                    physical_root,
                    root_claim_is_available(claim_registry, physical_root),
                )
            )
    if len(authenticated) != len(registry.slots):
        raise MultifamilyPilotFreezeError("context_inventory_incomplete")
    return (
        rom_path,
        rom.sha256,
        rom_bytes,
        tuple(authenticated),
        catalog.catalog_sha256,
        plan_sha256,
    )


def _inventory(
    rom_path: Path,
    rom_bytes: bytes,
    rom_sha256: str,
    source_bundle: str,
    contexts: tuple[_AuthenticatedContext, ...],
) -> tuple[
    RedMultifamilyInventory,
    dict[tuple[str, str], _FamilyMechanics],
    int,
]:
    runtime_identity = build_runtime_identity()
    require_pyboy_import_origins(runtime_identity)
    route_world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
    projected_contexts: list[RedMultifamilyContext] = []
    mechanics: dict[tuple[str, str], _FamilyMechanics] = {}
    total_frames = 0
    with PyBoyAdapter(
        rom_path,
        watch=False,
        speed=None,
        expected_rom=POKEMON_RED_US_REV_0,
    ) as emulator:
        for private in contexts:
            capture = private.capture
            profile = private.profile
            emulator.load_state_bytes(capture.state_bytes)
            frame_before = emulator.frame_count
            reader = PokemonRedStateReader(emulator)
            runtime = build_red_goal_context_runtime(
                profile=profile,
                capture=capture,
                emulator=emulator,
                reader=reader,
            )
            observation = runtime.adapter.observe()
            traversal = Gen1TraversalObserver(
                reader,
                hazard_projector=Gen1TrainerSightProjector(rom_bytes, reader),
                capability_projector=lambda raw, e=emulator: gen1_field_capabilities(e, raw),
            )
            start = traversal.observe()
            facts, context_mechanics = _context_mechanics(
                observation.collection_observation,
                observation.raw,
                start,
                reader,
                route_world,
                reset_state_sha256=capture.state_sha256,
                context_identity_sha256=private.context_identity_sha256,
                rom_sha256=rom_sha256,
                source_bundle=source_bundle,
            )
            frames = emulator.frame_count - frame_before
            if frames != 0:
                raise MultifamilyPilotFreezeError("action_free_frame_advance")
            total_frames += frames
            partition = "train" if private.assignment.partition == "train" else "development"
            context = RedMultifamilyContext(
                private.context_identity_sha256,
                private.root_consumption_sha256,
                partition,
                observation.collection_observation,
                facts,
                private.root_available,
            )
            projected_contexts.append(context)
            for item in context_mechanics:
                key = (context.context_identity_sha256, item.family_identity_sha256)
                if key in mechanics:
                    raise MultifamilyPilotFreezeError("mechanics_identity_collision")
                mechanics[key] = item
    inventory = inventory_red_multifamily_contexts(tuple(projected_contexts))
    return inventory, mechanics, total_frames


def _context_mechanics(
    collection: object,
    raw: object,
    start: object,
    reader: PokemonRedStateReader,
    route_world: StrategicScenarioRouteWorld,
    *,
    reset_state_sha256: str,
    context_identity_sha256: str,
    rom_sha256: str,
    source_bundle: str,
) -> tuple[RedDependencyExecutionFacts, tuple[_FamilyMechanics, ...]]:
    party = tuple(getattr(raw, "party_species_ids", None) or ())
    battle_state = getattr(raw, "battle_state", None)
    map_id = getattr(raw, "map_id", None)
    box = reader.read_current_box_state()
    if (
        battle_state != 0
        or len(party) != 6
        or BLASTOISE_SPECIES_ID not in party
        or map_id not in RED_TRAINING_FLY_CENTER_MAPS
        or len(box.species_ids) >= 20
    ):
        return RedDependencyExecutionFacts(), ()
    if _ordinary_capture_items(getattr(raw, "bag_items", None)) < 1:
        return RedDependencyExecutionFacts(), ()
    if not getattr(collection, "current_box_has_room", False):
        return RedDependencyExecutionFacts(), ()

    try:
        route_to_pc_plan = route_world.plan_to_map(start, int(map_id), goal_at=PC_GOAL_YX)
        route_to_pc = _pc_access_binding(
            start,
            route_to_pc_plan,
            rom_sha256=rom_sha256,
            source_bundle=source_bundle,
            context_identity_sha256=context_identity_sha256,
        )
    except Exception:
        return RedDependencyExecutionFacts(), ()
    pc_start = replace(
        start,
        at=PC_GOAL_YX,
        ready=True,
        interruption=None,
    )
    try:
        route_to_training_plan = route_world.plan_to_map(
            pc_start,
            int(map_id),
            goal_at=TRAINING_GOAL_YX,
        )
    except Exception:
        return RedDependencyExecutionFacts(), ()
    if not route_to_training_plan.steps:
        return RedDependencyExecutionFacts(), ()
    route_to_training = SemanticVenueRouteBinding(
        route_to_training_plan,
        _planner_binding(
            "training_boundary",
            rom_sha256,
            source_bundle,
            context_identity_sha256,
            int(map_id),
            route_to_training_plan.cost,
        ),
    )
    training_binding = canonical_sha256(
        {
            "schema": "pokemon.red.private-participation-training-binding.v1",
            "mode": "precursor_participates_escort_attacks",
            "venues": [
                [venue.area_id, list(venue.band.conditions)]
                for venue in (
                    ROUTE_11_TRAINING_VENUE,
                    DIGLETTS_CAVE_TRAINING_VENUE,
                    MANSION_TRAINING_VENUE,
                )
            ],
            "route_to_training_plan_sha256": route_to_training.plan_sha256,
        }
    )

    acquirable: set[str] = set()
    trainable: set[tuple[str, str]] = set()
    bindings: list[_FamilyMechanics] = []
    specimens = tuple(getattr(collection, "specimens", ()))
    for method in RED_ACQUISITION_CATALOG.methods:
        if not _supported_level_evolution(method):
            continue
        precursor_ref = method.consumes_species_ref
        assert precursor_ref is not None
        precursor_method = RED_ACQUISITION_CATALOG.method_for(precursor_ref)
        if (
            precursor_method.kind is not RedAcquisitionKind.WILD
            or not precursor_method.repeatable
            or precursor_method.transforms_precursor
        ):
            continue
        try:
            source_map = map_id_for_wild_source(precursor_method.source_id)
            capture_route_plan = route_world.plan_to_map(start, int(source_map))
        except Exception:
            continue
        if not capture_route_plan.steps:
            continue
        boxed = tuple(
            item
            for item in specimens
            if item.species_ref == precursor_ref
            and item.location is CollectionLocation.BOX
            and item.container_index == box.box_index
        )
        if not boxed:
            continue
        precursor_internal = red_internal_species_id(red_species_number(precursor_ref))
        evolved_internal = red_internal_species_id(red_species_number(method.species_ref))
        box_slots = tuple(
            index + 1
            for index, species_id in enumerate(box.species_ids)
            if species_id == precursor_internal
        )
        if not box_slots:
            continue
        deposit_slots = tuple(
            index + 1
            for index, species_id in enumerate(party)
            if species_id not in {BLASTOISE_SPECIES_ID, precursor_internal, evolved_internal}
        )
        if not deposit_slots:
            continue
        species = RedDependencySpeciesBinding(precursor_ref, method.species_ref)
        capture_route = SemanticVenueRouteBinding(
            capture_route_plan,
            _planner_binding(
                "capture_source",
                rom_sha256,
                source_bundle,
                context_identity_sha256,
                int(source_map),
                capture_route_plan.cost,
            ),
        )
        capture_venue = SemanticCaptureVenue(
            precursor_method.source_id,
            int(source_map),
            raw_exit_coordinates(route_world.macro_graph.warp_locations.get(int(source_map), ())),
        )
        capture_plan = SemanticVenueCapturePlan(
            reset_state_sha256,
            species,
            precursor_method.source_id,
            capture_route,
            capture_venue,
        )
        evolution_plan = BoxedLevelEvolutionPlan(
            reset_state_sha256,
            species,
            precursor_internal,
            evolved_internal,
            box.box_index,
            box_slots[0],
            deposit_slots[-1],
            party[deposit_slots[-1] - 1],
            route_to_pc,
            route_to_training,
            training_binding,
        )
        # The curriculum partitions on the adapter's complete transformation
        # binding, not on the verifier's narrower two-species join.  Keeping
        # those identities distinct prevents an evolution source or method from
        # being silently folded into another family while still allowing the
        # ledger verifier to remain species-only.
        binding_id = _family_identity(method)
        acquirable.add(precursor_ref)
        trainable.add((precursor_ref, method.species_ref))
        bindings.append(
            _FamilyMechanics(
                binding_id,
                species,
                precursor_method.source_id,
                int(source_map),
                capture_plan,
                evolution_plan,
            )
        )
    return (
        RedDependencyExecutionFacts(
            acquirable_precursor_refs=frozenset(acquirable),
            trainable_evolution_pairs=frozenset(trainable),
        ),
        tuple(bindings),
    )


def _freeze(
    inventory: RedMultifamilyInventory,
    mechanics: dict[tuple[str, str], _FamilyMechanics],
) -> RedMultifamilyCurriculumPlan:
    boxed_families = {family for (_context, family), _mechanics in mechanics.items()}
    counts: Counter[tuple[str, str]] = Counter(
        (item.context.partition, item.family_identity_sha256)
        for item in inventory.available_opportunities
        if item.family_identity_sha256 in boxed_families
    )
    required = 2 * TRIALS_PER_CANDIDATE
    train_families = tuple(
        sorted(
            (
                family
                for partition, family in counts
                if partition == "train" and counts[(partition, family)] >= required
            ),
            key=lambda family: (-counts[("train", family)], family),
        )
    )
    development_families = tuple(
        sorted(
            (
                family
                for partition, family in counts
                if partition == "development" and counts[(partition, family)] >= required
            ),
            key=lambda family: (-counts[("development", family)], family),
        )
    )
    pair = next(
        (
            (train, development)
            for train in train_families
            for development in development_families
            if train != development
        ),
        None,
    )
    if pair is None:
        raise MultifamilyPilotFreezeError("two_family_inventory_insufficient")
    plan = freeze_two_family_curriculum(
        inventory,
        train_family_identity_sha256=pair[0],
        development_family_identity_sha256=pair[1],
        trials_per_candidate=TRIALS_PER_CANDIDATE,
    )
    if any(
        (
            trial.opportunity.context.context_identity_sha256,
            trial.opportunity.family_identity_sha256,
        )
        not in mechanics
        for trial in (*plan.train_trials, *plan.development_trials)
    ):
        raise MultifamilyPilotFreezeError("selected_mechanics_binding_absent")
    return plan


def _private_plan_document(
    *,
    source_commit: str,
    source_bundle: str,
    rom_sha256: str,
    registry_sha256: str,
    catalog_sha256: str,
    context_plan_sha256: str,
    inventory: RedMultifamilyInventory,
    curriculum: RedMultifamilyCurriculumPlan,
    mechanics: dict[tuple[str, str], _FamilyMechanics],
) -> tuple[dict[str, object], str]:
    """Build the complete strict-JSON private record before touching its store."""

    def trial_document(trial: object) -> dict[str, object]:
        opportunity = trial.opportunity
        context = opportunity.context
        mechanic = mechanics[(context.context_identity_sha256, opportunity.family_identity_sha256)]
        return {
            "partition": trial.partition,
            "context_identity_sha256": context.context_identity_sha256,
            "root_consumption_sha256": context.root_consumption_sha256,
            "family_identity_sha256": opportunity.family_identity_sha256,
            "candidate_index": trial.candidate_index,
            "candidate_rows": [dict(row) for row in opportunity.policy_rows()],
            "mechanics": mechanic.private_dict(),
        }

    payload: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "lane_id": LANE_ID,
        "status": "frozen_before_prediction_action_or_outcome",
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle,
        "rom_sha256": rom_sha256,
        "registry_sha256": registry_sha256,
        "context_catalog_sha256": catalog_sha256,
        "context_plan_sha256": context_plan_sha256,
        "inventory": inventory.public_dict(),
        "curriculum": curriculum.public_dict(),
        "trials": [
            trial_document(trial)
            for trial in (*curriculum.train_trials, *curriculum.development_trials)
        ],
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "outcomes_observed": 0,
        "roots_claimed": 0,
    }
    validate_private_record(payload)
    plan_sha256 = canonical_sha256(payload)
    document = {**payload, "plan_sha256": plan_sha256}
    return document, plan_sha256


def _publish(
    args: argparse.Namespace,
    *,
    document: dict[str, object],
    plan_sha256: str,
    inventory: RedMultifamilyInventory,
    curriculum: RedMultifamilyCurriculumPlan,
    emulator_frames_advanced: int,
) -> dict[str, object]:
    """Publish one pre-encoded plan and return only its path-free summary."""

    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    record = store.publish_sealed_record(
        PLAN_RECORD_ID,
        kind=PLAN_RECORD_KIND,
        record=document,
    )
    return {
        "schema": RESULT_SCHEMA,
        "status": "two_family_root_disjoint_pilot_frozen_v2",
        "lane_id": LANE_ID,
        "plan_sha256": plan_sha256,
        "plan_manifest_sha256": record.summary.manifest_sha256,
        "inventory": inventory.public_dict(),
        "curriculum": curriculum.public_dict(),
        "emulator_states_read": len(inventory.contexts),
        "emulator_frames_advanced": emulator_frames_advanced,
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "outcomes_observed": 0,
        "roots_claimed": 0,
        "private_paths_published": 0,
        "private_species_fields_published": 0,
        "private_family_fields_published": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
    }


def _supported_level_evolution(method: RedAcquisitionMethod) -> bool:
    return (
        method.kind is RedAcquisitionKind.EVOLUTION
        and method.transforms_precursor
        and method.consumes_species_ref is not None
        and method.minimum_level is not None
        and method.required_item_ref is None
        and method.repeatable
    )


def _family_identity(method: RedAcquisitionMethod) -> str:
    """Return exactly the private family key emitted by the Red adapter."""

    precursor = method.consumes_species_ref
    if precursor is None:
        raise MultifamilyPilotFreezeError("family_identity_binding")
    return RedDependencyPrivateBinding(
        precursor_species_ref=precursor,
        evolved_species_ref=method.species_ref,
        acquisition_kind=method.kind,
        source_id=method.source_id,
        required_item_ref=method.required_item_ref,
    ).binding_sha256


def _pc_access_binding(
    start: TraversalSnapshot,
    plan: RoutePlan,
    *,
    rom_sha256: str,
    source_bundle: str,
    context_identity_sha256: str,
) -> SemanticVenueRouteBinding | ObservedSemanticBoundaryBinding:
    """Bind either a real relocation or the exact already-occupied PC boundary."""

    if not isinstance(start, TraversalSnapshot) or not isinstance(plan, RoutePlan):
        raise TypeError("PC access binding needs typed traversal inputs")
    if plan.steps:
        return SemanticVenueRouteBinding(
            plan,
            _planner_binding(
                "storage_pc",
                rom_sha256,
                source_bundle,
                context_identity_sha256,
                start.map_id,
                plan.cost,
            ),
        )
    if (
        start.at != PC_GOAL_YX
        or not start.ready
        or start.interruption is not None
        or plan.macro_path.maps[0] != start.map_id
        or plan.start_at != PC_GOAL_YX
        or plan.terminal_map != start.map_id
        or plan.terminal_at != PC_GOAL_YX
        or plan.cost != 0
    ):
        raise MultifamilyPilotFreezeError("observed_pc_boundary_authentication")
    return ObservedSemanticBoundaryBinding(
        start.map_id,
        PC_GOAL_YX,
        _planner_binding(
            "observed_storage_pc",
            rom_sha256,
            source_bundle,
            context_identity_sha256,
            start.map_id,
            0,
        ),
    )


def _planner_binding(
    purpose: str,
    rom_sha256: str,
    source_bundle: str,
    context_identity_sha256: str,
    goal_map: int,
    route_cost: int,
) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.red.private-multifamily-router-binding.v1",
            "purpose": purpose,
            "rom_sha256": rom_sha256,
            "source_bundle_sha256": source_bundle,
            "context_identity_sha256": context_identity_sha256,
            "goal_map": goal_map,
            "route_cost": route_cost,
        }
    )


def _ordinary_capture_items(value: object) -> int:
    if not isinstance(value, tuple):
        return 0
    inventory: dict[int, int] = {}
    for row in value:
        if (
            not isinstance(row, tuple)
            or len(row) != 2
            or any(type(item) is not int for item in row)  # noqa: E721
        ):
            return 0
        item_id, quantity = row
        if not 0 <= item_id <= 0xFF or not 0 <= quantity <= 0xFF or item_id in inventory:
            return 0
        inventory[item_id] = quantity
    return sum(
        inventory.get(int(item), 0)
        for item in (ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL)
    )


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MultifamilyPilotFreezeError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise MultifamilyPilotFreezeError(f"{subject.replace(' ', '_')}_authentication")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
