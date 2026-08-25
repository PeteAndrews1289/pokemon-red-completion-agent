#!/usr/bin/env python3
"""Authenticate one Red acquire-versus-evolve menu without scoring or acting."""

# ruff: noqa: E402 -- pin reviewed script/package origins before project imports.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
_PRELOADED_PROJECT_MODULES = tuple(
    sorted(
        name
        for name in sys.modules
        if name == "pokemon_red_completion" or name.startswith("pokemon_red_completion.")
    )
)
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

from freeze_rootless_execution_manifest import _current_public_bindings
from public_execution_manifest import canonical_manifest_line, read_public_manifest
from rootless_execution_manifest import (
    authenticate_rootless_execution_manifest,
    rootless_execution_invocation,
)

from pokemon_red_completion.blaine import (
    DIGLETT_SPECIES_ID,
    DIGLETTS_CAVE_TRAINING_VENUE,
)
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.encounters import ENCOUNTER_LOG_VARIABLE
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_collection_runtime import (
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    GoalManagerContextCatalogEntry,
    parse_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerAssignment,
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.goal_manager_trajectory import ordered_goal_manager_question
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    RootlessDependencyEvaluationDesignV2,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
    DependencyEvaluationFitIdentity,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    DEPENDENCY_EVALUATION_FIT_MANIFEST_KIND_V2,
    DEPENDENCY_EVALUATION_FIT_RECORD_KIND_V2,
    DEPENDENCY_EVALUATION_FIT_TERMINAL_KIND_V2,
    AuthenticatedDependencyEvaluationFitV2,
    authenticate_v2_dependency_evaluation_fit_bundle,
    dependency_fit_claim_from_manifest_document_v2,
    v2_fit_record_ids,
)
from pokemon_red_completion.observation import ItemId, MapId, PokemonRedStateReader
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot, open_private_root
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import (
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    RedSemanticVenueCaptureAdapter,
    SemanticCaptureReadiness,
    SemanticVenueAreaExecutor,
    SemanticVenueCapturePlan,
    SemanticVenueRouteBinding,
    bind_bounded_evolution_offer,
    build_red_dual_capability_scenario,
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    RedDependencySpeciesBinding,
    RedDualCapabilityScenarioSpec,
    red_dual_capability_curriculum_design,
    red_dual_capability_scenario_specs,
)
from pokemon_red_completion.red_party import DUGTRIO_SPECIES_ID
from pokemon_red_completion.rom import RomFingerprint, resolve_rom_path, verify_rom
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor
from pokemon_red_completion.training_venue import WarpSafeVenueWalker

LANE_ID = "red-dual-capability-action-free-scenario-preflight-v1"
RUNNER_RELATIVE = "scripts/run_red_dual_capability_preflight.py"
SELECTED_SLOT_ID = "red-goal-v1-032-evolve_species-train-05"
DIGLETTS_CAVE_SOURCE_ID = "wild:DiglettsCave:grass"

DESIGN_RECEIPT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/"
    "red-dual-capability-dependency-curriculum-design-qualification-v1-2026-08-21.json"
)
RUNTIME_RECEIPT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-dual-capability-curriculum-runtime-qualification-v1-2026-08-21.json"
)
DESIGN_RECEIPT_SHA256 = "aad8cf42b038a78be85f1aefa14cda292576b83818144ca85f56246cea12f2f8"
RUNTIME_RECEIPT_SHA256 = "dad315ffb90614d7d939054435e456fe80414311c6709403cb1f279213bcaede"

EVALUATION_DESIGN_PATH = PROJECT_ROOT / "configs/rootless-living-dex-dependency-evaluation-v2.json"
EVALUATION_DESIGN_DOCUMENT_SHA256 = (
    "4c614c71344ef94a894f3a7866d4b3d9d5ec6e32e98f7994be1d88ea533cd5bb"
)
EVALUATION_DESIGN_SHA256 = "1cf7423f59b5c10a7b76199c35cc3fc1d3742edd17127e371bf1e12ecb42d74b"
TRAIN_DATASET_SHA256 = "77b7d54648b5530f7e90e543e72db5319d17eee7bf681b229305fbed460816ba"
FIT_RECORD_SHA256 = "ea56c85643614202bee0e1f4a911817dc8fbb27e871e3f5ffd339083c2cb40b6"
FIT_SHA256 = "c544fa92f0fc9ab51037cb88a79bf2917e112d16f42630d08de6810aa8d4bc3c"
MODEL_SHA256 = "a42db6420d3ff999a894c8ca54fbca7714509bbe95a2020cf85c9cee195f6582"
FIT_EXECUTION_MANIFEST_SHA256 = "5a38225da79d06eec876507b5255aa68c0cb286c9f13d01534a5e8285692ff1a"
EXECUTABLE_BUNDLE_SHA256 = "c6bd856ca0bc9d807dbf17bbb968eb7ffe86c40fcac35b8bbe49d8159b964861"
FIT_MANIFEST_RECORD_SHA256 = "1696e37c44b5a10b81c194a0816b35def463baa1a61b05c80da2e8c897fbbf36"
FIT_TERMINAL_RECORD_SHA256 = "ccb77998a63b83ff47bce2575a492cefbdc42821cd93aa956a03f6c3f9fc7fa5"
FIT_CLAIM_SHA256 = "eaf6bcb37e328a331f285a39c7d68c46d379b862642042b41efc684053730747"
FIT_EXECUTION_IDENTITY_SHA256 = "9607a7238684b43def782c1d3cd401bcba8f78a322ab55093bd68e3f68a04d4d"
FIT_SOURCE_COMMIT = "15b2dbcb3cf881e97285c2611703d3c4dbac5206"
FIT_RUNNER_SHA256 = "f721c9f7ed38c19c5ed12458f9449de9f33df11d8572a567c6949bd91d7bc320"

DEPENDENCIES = (
    "claim_registry=src/pokemon_red_completion/goal_manager_composition_qualification.py",
    "context_catalog=src/pokemon_red_completion/goal_manager_context_catalog.py",
    "context_runtime=src/pokemon_red_completion/red_goal_context.py",
    "curriculum=src/pokemon_red_completion/red_living_dex_dependency_curriculum.py",
    "dual_runtime=src/pokemon_red_completion/red_dual_capability_curriculum_runtime.py",
    "field_moves=src/pokemon_red_completion/gen1_field_moves.py",
    "fit_integrity=src/pokemon_red_completion/living_dex_dependency_integrity_v2.py",
    "manifest_core=scripts/rootless_execution_manifest.py",
    "manifest_reader=scripts/public_execution_manifest.py",
    "private_store=src/pokemon_red_completion/private_artifacts.py",
    "route_runtime=src/pokemon_red_completion/gen1_route_runtime.py",
    "route_world=src/pokemon_red_completion/strategic_navigation_scenario_runtime.py",
    "surge=src/pokemon_red_completion/surge.py",
)
PRIVATE_INPUT_ROLES = (
    "claim_registry",
    "context_catalog",
    "context_envelope",
    "context_plan",
    "context_profile",
    "context_state",
    "fit_bundle_records",
    "private_artifact_root",
    "red_rom",
)
CONTEXT_PLAN_SCHEMA = "pokemon-red-private-goal-manager-context-plan-v1"
PREFLIGHT_SCHEMA = "pokemon.red.dual-capability-action-free-preflight.v1"
FAILURE_SCHEMA = "pokemon.red.dual-capability-action-free-preflight-failure.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
_MAX_STATE_BYTES = 16 * 1024 * 1024


class RedDualCapabilityPreflightError(RuntimeError):
    """A path-free failure at one named zero-action stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
        super().__init__(self.stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RedDualCapabilityPreflightError("arguments")


@dataclass(frozen=True, slots=True)
class _ContextPlanEntry:
    slot_id: str
    state: Path
    envelope: Path
    profile: Path


@dataclass(frozen=True, slots=True)
class _PublicGate:
    execution_manifest_sha256: str
    public_bindings: Mapping[str, str]
    evaluation_design: RootlessDependencyEvaluationDesignV2


@dataclass(frozen=True, slots=True)
class _Readiness:
    gate: _PublicGate
    runtime: RuntimeIdentity
    rom_path: Path
    rom: RomFingerprint
    rom_bytes: bytes
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile
    assignment: GoalManagerAssignment
    catalog_entry: GoalManagerContextCatalogEntry
    context_identity_sha256: str
    authenticated_fit: AuthenticatedDependencyEvaluationFitV2
    store: PrivateArtifactRoot


@dataclass(frozen=True, slots=True)
class _ObservedPreflight:
    result: Mapping[str, object]
    root_consumption_sha256: str
    controller_actions: int
    attempted_controller_actions: int
    emulator_frames_advanced: int


class _NoActionExecutor:
    """Fail on the first controller macro while retaining an attempt count."""

    __slots__ = ("attempted_actions",)

    def __init__(self) -> None:
        self.attempted_actions = 0

    def execute(self, action: object) -> object:
        del action
        self.attempted_actions += 1
        raise RedDualCapabilityPreflightError("action_free_capability_authentication")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--expected-execution-manifest-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--expected-profile-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "public_manifest_authentication"
        gate = _authenticate_public_gate(args)
        stage = "private_readiness_authentication"
        readiness = _prepare_readiness(args, gate)
        stage = "action_free_capability_authentication"
        observed = _observe_action_free(readiness)
        stage = "semantic_root_availability"
        result = _preflight_result(readiness, observed)
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except RedDualCapabilityPreflightError as error:
        print(
            json.dumps(
                _failure_receipt(
                    error.stage,
                    before_private=stage in {"arguments", "public_manifest_authentication"},
                ),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    except BaseException:
        print(
            json.dumps(
                _failure_receipt(stage),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1


def _authenticate_public_gate(args: argparse.Namespace) -> _PublicGate:
    _require_script_import_origins()
    _require_project_import_origins()
    _require_public_receipt(DESIGN_RECEIPT_PATH, DESIGN_RECEIPT_SHA256)
    _require_public_receipt(RUNTIME_RECEIPT_PATH, RUNTIME_RECEIPT_SHA256)
    evaluation_design = _read_evaluation_design()
    public = _current_public_bindings(
        lane_id=LANE_ID,
        runner=RUNNER_RELATIVE,
        dependencies=list(DEPENDENCIES),
    )
    if public.get("source_bundle_sha256") != working_source_bundle_sha256(PROJECT_ROOT):
        raise RedDualCapabilityPreflightError("public_source_authentication")
    semantic = _semantic_bindings(args, evaluation_design)
    invocation = rootless_execution_invocation(
        lane_id=LANE_ID,
        operation="preflight",
        semantic_bindings=semantic,
        public_bindings=public,
        private_input_roles=PRIVATE_INPUT_ROLES,
    )
    payload = read_public_manifest(args.execution_manifest, repository_root=PROJECT_ROOT)
    authenticate_rootless_execution_manifest(
        payload,
        expected_manifest_sha256=_sha(
            args.expected_execution_manifest_sha256,
            "execution manifest",
        ),
        invocation=invocation,
        current_public_bindings=public,
    )
    return _PublicGate(hashlib.sha256(payload).hexdigest(), public, evaluation_design)


def _semantic_bindings(
    args: argparse.Namespace,
    evaluation_design: RootlessDependencyEvaluationDesignV2,
) -> dict[str, str]:
    registry_source = _commit(args.registry_source_commit, "registry source")
    design = red_dual_capability_curriculum_design()
    return {
        "context_catalog_document_sha256": _sha(
            args.expected_context_catalog_sha256,
            "context catalog",
        ),
        "context_plan_document_sha256": _sha(
            args.expected_context_plan_sha256,
            "context plan",
        ),
        "curriculum_design_sha256": canonical_sha256(design.public_dict()),
        "design_qualification_receipt_sha256": DESIGN_RECEIPT_SHA256,
        "evaluation_design_document_sha256": EVALUATION_DESIGN_DOCUMENT_SHA256,
        "evaluation_design_sha256": evaluation_design.design_sha256,
        "executable_bundle_sha256": EXECUTABLE_BUNDLE_SHA256,
        "fit_claim_sha256": FIT_CLAIM_SHA256,
        "fit_execution_identity_sha256": FIT_EXECUTION_IDENTITY_SHA256,
        "fit_execution_manifest_sha256": FIT_EXECUTION_MANIFEST_SHA256,
        "fit_manifest_record_sha256": FIT_MANIFEST_RECORD_SHA256,
        "fit_record_sha256": FIT_RECORD_SHA256,
        "fit_sha256": FIT_SHA256,
        "fit_terminal_record_sha256": FIT_TERMINAL_RECORD_SHA256,
        "model_sha256": MODEL_SHA256,
        "red_rom_sha256": POKEMON_RED_US_REV_0.sha256,
        "registry_sha256": _sha(args.expected_registry_sha256, "registry"),
        "registry_source_commit_sha256": hashlib.sha256(
            registry_source.encode("ascii")
        ).hexdigest(),
        "runtime_qualification_receipt_sha256": RUNTIME_RECEIPT_SHA256,
        "source_venue_binding_sha256": canonical_sha256(
            {
                "schema": "pokemon.red.dual-capability-source-venue.v1",
                "source_id": DIGLETTS_CAVE_SOURCE_ID,
                "venue_map": int(MapId.DIGLETTS_CAVE),
            }
        ),
        "selected_context_slot_sha256": canonical_sha256(
            {"schema": "pokemon.red.dual-capability-context-slot.v1", "slot_id": SELECTED_SLOT_ID}
        ),
        "selected_profile_sha256": _sha(args.expected_profile_sha256, "profile"),
        "train_dataset_sha256": TRAIN_DATASET_SHA256,
    }


def _prepare_readiness(
    args: argparse.Namespace,
    gate: _PublicGate,
    *,
    selected_slot_id: str = SELECTED_SLOT_ID,
) -> _Readiness:
    runtime = build_runtime_identity()
    if runtime.sha256 != gate.public_bindings.get("runtime_sha256"):
        raise RedDualCapabilityPreflightError("runtime_authentication")
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    if rom.sha256 != POKEMON_RED_US_REV_0.sha256:
        raise RedDualCapabilityPreflightError("rom_authentication")
    rom_bytes = _read_external_bytes(
        rom_path,
        maximum_bytes=4 * 1024 * 1024,
        forbidden=(),
        allow_rom=True,
    )
    if hashlib.sha256(rom_bytes).hexdigest() != rom.sha256:
        raise RedDualCapabilityPreflightError("rom_authentication")

    source_commit = _commit(args.registry_source_commit, "registry source")
    registry = load_committed_goal_manager_registry_at_revision(PROJECT_ROOT, source_commit)
    if registry.registry_sha256 != _sha(args.expected_registry_sha256, "registry"):
        raise RedDualCapabilityPreflightError("registry_authentication")
    assignment = registry.assignment(selected_slot_id)
    if assignment.partition != "train" or assignment.focus_kind is not GoalKind.EVOLVE_SPECIES:
        raise RedDualCapabilityPreflightError("selected_context_authentication")

    catalog_bytes = _read_external_bytes(
        args.context_catalog,
        maximum_bytes=_MAX_DOCUMENT_BYTES,
        forbidden=(rom_path,),
    )
    if hashlib.sha256(catalog_bytes).hexdigest() != _sha(
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise RedDualCapabilityPreflightError("context_catalog_authentication")
    catalog = parse_goal_manager_context_catalog(catalog_bytes, registry)
    catalog_entry = catalog.entry(selected_slot_id)
    if catalog_entry.assignment_id != assignment.assignment_id:
        raise RedDualCapabilityPreflightError("context_catalog_authentication")

    plan_bytes = _read_external_bytes(
        args.context_plan,
        maximum_bytes=_MAX_DOCUMENT_BYTES,
        forbidden=(rom_path, args.context_catalog),
    )
    if hashlib.sha256(plan_bytes).hexdigest() != _sha(
        args.expected_context_plan_sha256,
        "context plan",
    ):
        raise RedDualCapabilityPreflightError("context_plan_authentication")
    plan_entry = _context_plan_entry(
        plan_bytes,
        registry_sha256=registry.registry_sha256,
        source_commit=registry.execution.source_commit,
        selected_slot_id=selected_slot_id,
    )
    forbidden = (rom_path, args.context_catalog, args.context_plan)
    state_bytes = _read_external_bytes(
        plan_entry.state,
        maximum_bytes=_MAX_STATE_BYTES,
        forbidden=forbidden,
    )
    envelope_bytes = _read_external_bytes(
        plan_entry.envelope,
        maximum_bytes=_MAX_DOCUMENT_BYTES,
        forbidden=(*forbidden, plan_entry.state),
    )
    profile_bytes = _read_external_bytes(
        plan_entry.profile,
        maximum_bytes=_MAX_DOCUMENT_BYTES,
        forbidden=(*forbidden, plan_entry.state, plan_entry.envelope),
    )
    capture = parse_goal_manager_context_capture(state_bytes, envelope_bytes)
    profile = parse_red_goal_context_profile(profile_bytes)
    if (
        plan_entry.slot_id != selected_slot_id
        or capture.capture_id != selected_slot_id
        or profile.profile_id != selected_slot_id
        or capture.capture_id != catalog_entry.capture_id
        or capture.state_sha256 != catalog_entry.state_sha256
        or capture.envelope_sha256 != catalog_entry.envelope_sha256
        or capture.state_sha256 != hashlib.sha256(state_bytes).hexdigest()
        or capture.envelope_sha256 != hashlib.sha256(envelope_bytes).hexdigest()
        or profile.profile_sha256 != hashlib.sha256(profile_bytes).hexdigest()
        or profile.profile_sha256 != _sha(args.expected_profile_sha256, "profile")
    ):
        raise RedDualCapabilityPreflightError("selected_context_authentication")
    context_identity = canonical_sha256(
        {
            "schema": "pokemon.red.private-dual-capability-context.v1",
            "registry_sha256": registry.registry_sha256,
            "context_catalog_sha256": catalog.catalog_sha256,
            "context_id": catalog_entry.context_id,
            "assignment_id": assignment.assignment_id,
            "root_lineage_id": assignment.root_lineage_id,
            "slot_id": assignment.slot_id,
            "partition": assignment.partition,
            "state_sha256": capture.state_sha256,
            "envelope_sha256": capture.envelope_sha256,
            "profile_sha256": profile.profile_sha256,
            "rom_sha256": rom.sha256,
        }
    )
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    fit = _authenticate_fit_bundle(store, gate.evaluation_design)
    if fit.model_sha256 != MODEL_SHA256:
        raise RedDualCapabilityPreflightError("fit_bundle_authentication")
    return _Readiness(
        gate,
        runtime,
        rom_path,
        rom,
        rom_bytes,
        capture,
        profile,
        assignment,
        catalog_entry,
        context_identity,
        fit,
        store,
    )


def _observe_action_free(readiness: _Readiness) -> _ObservedPreflight:
    if os.environ.get(ENCOUNTER_LOG_VARIABLE, "").strip():
        raise RedDualCapabilityPreflightError("zero_effect_environment")
    require_pyboy_import_origins(readiness.runtime)
    rejecting = _NoActionExecutor()
    counted = CountingExecutor(rejecting)
    route_world = StrategicScenarioRouteWorld.from_rom(readiness.rom_bytes)
    with PyBoyAdapter(
        readiness.rom_path,
        watch=False,
        speed=None,
        expected_rom=POKEMON_RED_US_REV_0,
    ) as emulator:
        require_pyboy_import_origins(readiness.runtime)
        emulator.load_state_bytes(readiness.capture.state_bytes)
        require_pyboy_import_origins(readiness.runtime)
        frame_before = emulator.frame_count
        reader = PokemonRedStateReader(emulator)
        context_runtime = build_red_goal_context_runtime(
            profile=readiness.profile,
            capture=readiness.capture,
            emulator=emulator,
            reader=reader,
        )
        observation = context_runtime.adapter.observe()
        battle_state = observation.raw.battle_state
        if type(battle_state) is not int or not 0 <= battle_state <= 0xFF:  # noqa: E721
            raise RedDualCapabilityPreflightError("capture_capability_authentication")
        bindings = context_runtime.enumerator(counted).enumerate(observation)
        historical_question = ordered_goal_manager_question(
            assignment_id=readiness.assignment.assignment_id,
            decision_index=0,
            situation=observation.situation,
            opportunities=bindings.opportunities,
        )
        if (
            historical_question.ordered_policy_input_sha256
            != readiness.catalog_entry.question_sha256
            or historical_question.policy_context_sha256
            != readiness.catalog_entry.policy_context_sha256
            or historical_question.available_menu_sha256
            != readiness.catalog_entry.available_menu_sha256
            or goal_binding_manifest_sha256(bindings)
            != readiness.catalog_entry.binding_manifest_sha256
            or tuple(item.kind for item in bindings.bindings)
            != readiness.catalog_entry.available_goal_kinds
        ):
            raise RedDualCapabilityPreflightError("historical_context_replay")

        try:
            evolution_binding = next(
                item for item in bindings.bindings if item.kind is GoalKind.EVOLVE_SPECIES
            )
        except StopIteration:
            raise RedDualCapabilityPreflightError("evolution_capability_authentication") from None
        evolution_specs = tuple(
            item for item in readiness.profile.providers if item.kind is GoalKind.EVOLVE_SPECIES
        )
        if len(evolution_specs) != 1 or evolution_binding.binding_ref != (
            "pokemon.red:evolution:diglett-to-dugtrio:"
            f"profile-{readiness.profile.profile_sha256}:"
            f"config-{evolution_specs[0].configuration_sha256}"
        ):
            raise RedDualCapabilityPreflightError("evolution_capability_authentication")
        species = RedDependencySpeciesBinding(
            red_species_ref(red_internal_species_number(DIGLETT_SPECIES_ID)),
            red_species_ref(red_internal_species_number(DUGTRIO_SPECIES_ID)),
        )
        before_ledger = dependency_specimen_ledger(observation.collection_observation)
        scenarios = tuple(
            item
            for item in red_dual_capability_scenario_specs()
            if item.before.precursor_count == before_ledger.count(species.precursor_species_ref)
            and item.before.evolved_count == before_ledger.count(species.evolved_species_ref)
        )
        if len(scenarios) != 1:
            raise RedDualCapabilityPreflightError("dependency_scenario_authentication")
        scenario = scenarios[0]

        traversal = Gen1TraversalObserver(
            reader,
            hazard_projector=Gen1TrainerSightProjector(readiness.rom_bytes, reader),
        )
        start = traversal.observe()
        route_plan = route_world.plan_to_map(start, int(MapId.DIGLETTS_CAVE))
        planner_binding = canonical_sha256(
            {
                "schema": "pokemon.red.private-dual-capability-router-binding.v1",
                "rom_sha256": readiness.rom.sha256,
                "source_bundle_sha256": readiness.gate.public_bindings["source_bundle_sha256"],
                "context_identity_sha256": readiness.context_identity_sha256,
                "goal_map": int(MapId.DIGLETTS_CAVE),
                "route_cost": route_plan.cost,
            }
        )
        route = SemanticVenueRouteBinding(route_plan, planner_binding)
        field_actions = Gen1FieldMovePort(
            counted,
            reader,
            emulator,
            cut_block_swaps={
                swap.before: swap.after for swap in route_world.rules.cut_block_swaps
            },
        )
        walker = DIGLETTS_CAVE_TRAINING_VENUE.fresh_walk_to_grass()
        if not isinstance(walker, WarpSafeVenueWalker):
            raise RedDualCapabilityPreflightError("capture_capability_authentication")
        live_capture = LiveWildEncounterExecutor(
            emulator,
            counted,
            reader,
            DEFAULT_SURGE_TIMING,
            label="semantic Diglett's Cave target capture",
        )
        area = SemanticVenueAreaExecutor(
            delegate=live_capture,
            actions=field_actions,
            reader=reader,
            emulator=emulator,
            walker=walker,
        )
        capture_plan = SemanticVenueCapturePlan(
            readiness.capture.state_sha256,
            species,
            DIGLETTS_CAVE_SOURCE_ID,
            route,
            DIGLETTS_CAVE_TRAINING_VENUE,
        )
        route_interruptions = Gen1RouteInterruptionHandler(
            field_actions,
            reader,
            maximum_flees=64,
            maximum_trainer_battles=8,
            stabilization_frames=120,
            route_name="semantic route to Diglett's Cave",
        )
        capture_adapter = RedSemanticVenueCaptureAdapter(
            capture_plan,
            field_actions,
            traversal,
            area,
            interruption_handler=route_interruptions,
            replanner=route_world.replanner(),
        )
        readiness_evidence = SemanticCaptureReadiness(
            reset_state_sha256=readiness.capture.state_sha256,
            ordinary_capture_items=_ordinary_capture_items(observation.raw.bag_items),
            immediate_capture_slots=observation.immediate_capture_slots,
            input_ready=observation.input_ready,
            battle_active=battle_state != 0,
        )
        acquire = capture_adapter.qualify(scenario, before_ledger, readiness_evidence)
        evolve = bind_bounded_evolution_offer(
            scenario,
            species,
            before_ledger,
            reset_state_sha256=readiness.capture.state_sha256,
            offer=RedGoalBindingOffer.available(evolution_binding),
        )
        bound = build_red_dual_capability_scenario(
            scenario,
            species,
            before_ledger,
            (acquire, evolve),
        )
        frame_after = emulator.frame_count
        if (
            frame_after != frame_before
            or counted.actions_executed != 0
            or rejecting.attempted_actions != 0
            or emulator.pressed_buttons
        ):
            raise RedDualCapabilityPreflightError("zero_effect_authentication")
        physical_root, scenario_identity = _semantic_identities(
            readiness,
            scenario,
            species,
        )
        result = {
            "schema": PREFLIGHT_SCHEMA,
            "status": "action_free_scenario_qualified_root_unclaimed",
            "partition": "train",
            "scenario": bound.public_dict(),
            "semantic_route": {
                **route.public_dict(),
                "route_steps": len(route_plan.steps),
                "route_cost": route_plan.cost,
            },
            "capture_resources": {
                "ordinary_capture_items_positive": readiness_evidence.ordinary_capture_items > 0,
                "immediate_capture_slots_positive": readiness_evidence.immediate_capture_slots > 0,
            },
            "authenticated_model_sha256": readiness.authenticated_fit.model_sha256,
            "semantic_scenario_identity_sha256": scenario_identity,
            "model_predictions": 0,
            "controller_actions": 0,
            "attempted_controller_actions": 0,
            "emulator_frames_advanced": 0,
            "teacher_queries": 0,
            "outcomes_observed": 0,
            "identity_claims_written": 0,
            "private_path_fields": 0,
            "private_species_fields": 0,
            "private_route_fields": 0,
        }
    require_pyboy_import_origins(readiness.runtime)
    if verify_rom(readiness.rom_path).sha256 != readiness.rom.sha256:
        raise RedDualCapabilityPreflightError("protected_input_integrity")
    return _ObservedPreflight(
        result,
        physical_root,
        counted.actions_executed,
        rejecting.attempted_actions,
        frame_after - frame_before,
    )


def _preflight_result(
    readiness: _Readiness,
    observed: _ObservedPreflight,
) -> dict[str, object]:
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        _require_fit_claim(registry)
        if not root_claim_is_available(registry, observed.root_consumption_sha256):
            raise RedDualCapabilityPreflightError("semantic_root_availability")
    if (
        observed.controller_actions != 0
        or observed.attempted_controller_actions != 0
        or observed.emulator_frames_advanced != 0
    ):
        raise RedDualCapabilityPreflightError("zero_effect_authentication")
    return {
        **dict(observed.result),
        "execution_manifest_sha256": readiness.gate.execution_manifest_sha256,
        "semantic_root_available": True,
        "semantic_root_consumed": False,
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
    }


def _require_fit_claim(registry: Path) -> None:
    expected = {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": FIT_CLAIM_SHA256,
        "execution_identity_sha256": FIT_EXECUTION_IDENTITY_SHA256,
        "source_commit": FIT_SOURCE_COMMIT,
        "runner_sha256": FIT_RUNNER_SHA256,
    }
    if read_root_claim(registry, FIT_CLAIM_SHA256) != expected:
        raise RedDualCapabilityPreflightError("fit_claim_authentication")


def _semantic_identities(
    readiness: _Readiness,
    scenario: RedDualCapabilityScenarioSpec,
    species_binding: RedDependencySpeciesBinding,
) -> tuple[str, str]:
    if not isinstance(scenario, RedDualCapabilityScenarioSpec):
        raise TypeError("semantic identity needs a dual-capability scenario")
    if not isinstance(species_binding, RedDependencySpeciesBinding):
        raise TypeError("semantic identity needs a dependency species binding")
    physical_root = root_consumption_sha256(
        state_sha256=readiness.capture.state_sha256,
        envelope_sha256=readiness.capture.envelope_sha256,
    )
    scenario_identity = canonical_sha256(
        {
            "schema": "pokemon.red.dual-capability-semantic-scenario.v1",
            "game_id": "pokemon.mainline:red:gb:us:rev0",
            "state_sha256": readiness.capture.state_sha256,
            "envelope_sha256": readiness.capture.envelope_sha256,
            "profile_sha256": readiness.profile.profile_sha256,
            "curriculum_design_sha256": canonical_sha256(
                red_dual_capability_curriculum_design().public_dict()
            ),
            "scenario_sha256": canonical_sha256(scenario.public_dict()),
            "dependency_binding_sha256": species_binding.binding_sha256,
        }
    )
    return physical_root, scenario_identity


def _authenticate_fit_bundle(
    store: PrivateArtifactRoot,
    design: RootlessDependencyEvaluationDesignV2,
) -> AuthenticatedDependencyEvaluationFitV2:
    fit_id, manifest_id, terminal_id = v2_fit_record_ids(FIT_EXECUTION_IDENTITY_SHA256)
    fit_record = store.find_sealed_record(
        fit_id,
        expected_kind=DEPENDENCY_EVALUATION_FIT_RECORD_KIND_V2,
    )
    manifest_record = store.find_sealed_record(
        manifest_id,
        expected_kind=DEPENDENCY_EVALUATION_FIT_MANIFEST_KIND_V2,
    )
    terminal_record = store.find_sealed_record(
        terminal_id,
        expected_kind=DEPENDENCY_EVALUATION_FIT_TERMINAL_KIND_V2,
    )
    if fit_record is None or manifest_record is None or terminal_record is None:
        raise RedDualCapabilityPreflightError("fit_bundle_authentication")
    identity = DependencyEvaluationFitIdentity(
        design_sha256=EVALUATION_DESIGN_SHA256,
        train_dataset_sha256=TRAIN_DATASET_SHA256,
        fit_record_sha256=FIT_RECORD_SHA256,
        fit_sha256=FIT_SHA256,
        model_sha256=MODEL_SHA256,
        fit_execution_manifest_sha256=FIT_EXECUTION_MANIFEST_SHA256,
        executable_bundle_sha256=EXECUTABLE_BUNDLE_SHA256,
    )
    pins = DependencyEvaluationBundlePins(
        identity,
        FIT_MANIFEST_RECORD_SHA256,
        FIT_TERMINAL_RECORD_SHA256,
    )
    manifest = manifest_record.read()
    claim = dependency_fit_claim_from_manifest_document_v2(manifest)
    if (
        claim.semantic_claim_sha256 != FIT_CLAIM_SHA256
        or claim.execution_identity_sha256 != FIT_EXECUTION_IDENTITY_SHA256
    ):
        raise RedDualCapabilityPreflightError("fit_bundle_authentication")
    try:
        return authenticate_v2_dependency_evaluation_fit_bundle(
            design,
            fit_claim=claim,
            pins=pins,
            fit_record_bytes=canonical_manifest_line(fit_record.read()),
            fit_manifest_record_bytes=canonical_manifest_line(manifest),
            fit_terminal_record_bytes=canonical_manifest_line(terminal_record.read()),
        )
    except (TypeError, ValueError):
        raise RedDualCapabilityPreflightError("fit_bundle_authentication") from None


def _read_evaluation_design() -> RootlessDependencyEvaluationDesignV2:
    payload = EVALUATION_DESIGN_PATH.read_bytes()
    if hashlib.sha256(payload).hexdigest() != EVALUATION_DESIGN_DOCUMENT_SHA256:
        raise RedDualCapabilityPreflightError("fit_design_authentication")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RedDualCapabilityPreflightError("fit_design_authentication") from None
    if not isinstance(value, dict):
        raise RedDualCapabilityPreflightError("fit_design_authentication")
    design = RootlessDependencyEvaluationDesignV2.from_dict(value)
    if (
        design.design_sha256 != EVALUATION_DESIGN_SHA256
        or design.train_revalidation_sha256 != TRAIN_DATASET_SHA256
    ):
        raise RedDualCapabilityPreflightError("fit_design_authentication")
    return design


def _context_plan_entry(
    payload: bytes,
    *,
    registry_sha256: str,
    source_commit: str | None,
    selected_slot_id: str = SELECTED_SLOT_ID,
) -> _ContextPlanEntry:
    document = _canonical_document(payload, subject="context plan")
    if (
        set(document) != {"entries", "registry_sha256", "schema", "source_commit"}
        or document.get("schema") != CONTEXT_PLAN_SCHEMA
        or document.get("registry_sha256") != registry_sha256
        or document.get("source_commit") != source_commit
    ):
        raise RedDualCapabilityPreflightError("context_plan_authentication")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise RedDualCapabilityPreflightError("context_plan_authentication")
    matches: list[_ContextPlanEntry] = []
    for raw in entries:
        if not isinstance(raw, dict) or set(raw) != {"envelope", "profile", "slot_id", "state"}:
            raise RedDualCapabilityPreflightError("context_plan_authentication")
        if raw.get("slot_id") == selected_slot_id:
            matches.append(
                _ContextPlanEntry(
                    selected_slot_id,
                    Path(_text(raw.get("state"), "state")),
                    Path(_text(raw.get("envelope"), "envelope")),
                    Path(_text(raw.get("profile"), "profile")),
                )
            )
    if len(matches) != 1:
        raise RedDualCapabilityPreflightError("context_plan_authentication")
    return matches[0]


def _ordinary_capture_items(raw_items: object) -> int:
    if not isinstance(raw_items, tuple):
        raise RedDualCapabilityPreflightError("capture_capability_authentication")
    inventory: dict[int, int] = {}
    for item in raw_items:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or any(type(value) is not int for value in item)  # noqa: E721
        ):
            raise RedDualCapabilityPreflightError("capture_capability_authentication")
        item_id, quantity = item
        if (
            not 0 <= item_id <= 0xFF
            or not 0 <= quantity <= 0xFF
            or item_id in inventory
        ):
            raise RedDualCapabilityPreflightError("capture_capability_authentication")
        inventory[item_id] = quantity
    return sum(
        inventory.get(int(item), 0)
        for item in (ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL)
    )


def _require_public_receipt(path: Path, expected_sha256: str) -> None:
    try:
        payload = path.read_bytes()
    except OSError:
        raise RedDualCapabilityPreflightError("public_evidence_authentication") from None
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RedDualCapabilityPreflightError("public_evidence_authentication")
    _canonical_document(payload, subject="public evidence")


def _read_external_bytes(
    path: Path,
    *,
    maximum_bytes: int,
    forbidden: tuple[Path, ...],
    allow_rom: bool = False,
) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        resolved = path.resolve(strict=True)
        project = PROJECT_ROOT.resolve(strict=True)
        forbidden_inodes = {_inode(item) for item in forbidden}
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            path.is_symlink()
            or not stat.S_ISREG(named.st_mode)
            or named.st_nlink != 1
            or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)
            or (opened.st_dev, opened.st_ino) in forbidden_inodes
            or (not allow_rom and (resolved == project or project in resolved.parents))
            or not 1 <= opened.st_size <= maximum_bytes
        ):
            raise OSError("unsafe private input")
        payload = os.read(descriptor, opened.st_size + 1)
        after = os.fstat(descriptor)
        renamed = path.lstat()
        if (
            len(payload) != opened.st_size
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            or (renamed.st_dev, renamed.st_ino, renamed.st_size, renamed.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        ):
            raise OSError("changed private input")
        return payload
    except OSError:
        raise RedDualCapabilityPreflightError("private_input_authentication") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _canonical_document(payload: bytes, *, subject: str) -> dict[str, object]:
    if not payload or len(payload) > _MAX_DOCUMENT_BYTES:
        raise RedDualCapabilityPreflightError(f"{subject.replace(' ', '_')}_authentication")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError):
        raise RedDualCapabilityPreflightError(
            f"{subject.replace(' ', '_')}_authentication"
        ) from None
    if not isinstance(value, dict) or canonical_manifest_line(value) != payload:
        raise RedDualCapabilityPreflightError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _inode(path: Path) -> tuple[int, int]:
    metadata = path.stat()
    return metadata.st_dev, metadata.st_ino


def _require_project_import_origins() -> None:
    if _PRELOADED_PROJECT_MODULES:
        raise RedDualCapabilityPreflightError("project_import_authentication")
    package_root = (SRC_ROOT / "pokemon_red_completion").resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "pokemon_red_completion" and not name.startswith("pokemon_red_completion."):
            continue
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise RedDualCapabilityPreflightError("project_import_authentication")
        path = Path(raw)
        try:
            named = path.lstat()
            resolved = path.resolve(strict=True)
        except OSError:
            raise RedDualCapabilityPreflightError("project_import_authentication") from None
        if (
            path.is_symlink()
            or not stat.S_ISREG(named.st_mode)
            or named.st_nlink != 1
            or not resolved.is_relative_to(package_root)
        ):
            raise RedDualCapabilityPreflightError("project_import_authentication")


def _require_script_import_origins() -> None:
    expected = {
        "freeze_rootless_execution_manifest": SCRIPTS_ROOT
        / "freeze_rootless_execution_manifest.py",
        "public_execution_manifest": SCRIPTS_ROOT / "public_execution_manifest.py",
        "rootless_execution_manifest": SCRIPTS_ROOT / "rootless_execution_manifest.py",
    }
    for name, expected_path in expected.items():
        module = sys.modules.get(name)
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise RedDualCapabilityPreflightError("script_import_authentication")
        imported = Path(raw)
        try:
            named = imported.lstat()
            resolved = imported.resolve(strict=True)
            expected_resolved = expected_path.resolve(strict=True)
        except OSError:
            raise RedDualCapabilityPreflightError("script_import_authentication") from None
        if (
            imported.is_symlink()
            or not stat.S_ISREG(named.st_mode)
            or named.st_nlink != 1
            or resolved != expected_resolved
        ):
            raise RedDualCapabilityPreflightError("script_import_authentication")


def _failure_receipt(
    stage: str,
    *,
    before_private: bool | None = None,
) -> dict[str, object]:
    safe = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
    if before_private is None:
        before_private = safe in {"arguments", "public_manifest_authentication"}
    return {
        "schema": FAILURE_SCHEMA,
        "status": "failed_closed",
        "failure_stage": safe,
        "protected_access_status": "verified_absent" if before_private else "not_attested",
        "effect_status": "verified_zero" if before_private else "not_attested",
        "context_substitutions": 0,
        "execution_result_emitted": False,
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "private_path_fields": 0,
        "private_identity_fields": 0,
    }


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedDualCapabilityPreflightError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise RedDualCapabilityPreflightError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedDualCapabilityPreflightError(f"{subject.replace(' ', '_')}_authentication")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
