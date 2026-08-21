#!/usr/bin/env python3
"""Preflight or record one read-only Red living-Dex dependency preference."""

# ruff: noqa: E402 -- pin the reviewed workspace source before project imports.

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

from pokemon_red_completion.blaine import DIGLETT_SPECIES_ID
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.encounters import ENCOUNTER_LOG_VARIABLE
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_collection_runtime import (
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
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
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import (
    EpisodeWriter,
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_collection import (
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
    RedLivingDexDependencyAdapterResult,
    adapt_red_living_dex_dependencies,
)
from pokemon_red_completion.red_living_dex_dependency_shadow import (
    PreparedRedDependencyShadow,
    RedDependencyShadowStop,
    prepare_red_dependency_shadow,
    score_red_dependency_shadow,
)
from pokemon_red_completion.red_party import DUGTRIO_SPECIES_ID
from pokemon_red_completion.rom import RomFingerprint, resolve_rom_path, verify_rom
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    build_runtime_identity,
    require_pyboy_import_origins,
)

LANE_ID = "red-living-dex-dependency-shadow-decision-v1"
RUNNER_RELATIVE = "scripts/run_red_living_dex_dependency_shadow.py"
DESIGN_PATH = PROJECT_ROOT / "configs/red-living-dex-dependency-shadow-decision-v1.json"
EVALUATION_DESIGN_PATH = PROJECT_ROOT / "configs/rootless-living-dex-dependency-evaluation-v2.json"
DESIGN_DOCUMENT_SHA256 = "5fbe527b3c1d126d376c5aae29ff10e47e9222b23cc408c4c37ad76b53e0f1dd"
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
ADAPTER_SHA256 = "2ecff694292b6f110edbc692e5c2dc326dcbaab0eb1f9a20ecd9583bdd86015f"

DEPENDENCIES = (
    "adapter=src/pokemon_red_completion/red_living_dex_dependency_adapter.py",
    "context_catalog=src/pokemon_red_completion/goal_manager_context_catalog.py",
    "context_runtime=src/pokemon_red_completion/red_goal_context.py",
    "fit_integrity=src/pokemon_red_completion/living_dex_dependency_integrity_v2.py",
    "manifest_core=scripts/rootless_execution_manifest.py",
    "manifest_reader=scripts/public_execution_manifest.py",
    "private_store=src/pokemon_red_completion/private_artifacts.py",
    "ranker=src/pokemon_red_completion/living_dex_dependency_ranker.py",
    "shadow_core=src/pokemon_red_completion/red_living_dex_dependency_shadow.py",
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
SHADOW_ARTIFACT_KIND = "red-living-dex-dependency-shadow"
SHADOW_PREREGISTRATION_SCHEMA = (
    "pokemon.red.private-living-dex-dependency-shadow-preregistration.v1"
)
SHADOW_FAILURE_SCHEMA = "pokemon.red.private-living-dex-dependency-shadow-failure.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_MAX_PUBLIC_DOCUMENT_BYTES = 4 * 1024 * 1024
_MAX_CONTEXT_DOCUMENT_BYTES = 4 * 1024 * 1024
_MAX_STATE_BYTES = 16 * 1024 * 1024


class RedLivingDexDependencyShadowRunError(RuntimeError):
    """A path-free failure at one named shadow-runner stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
        super().__init__(self.stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RedLivingDexDependencyShadowRunError("arguments")


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
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile
    assignment: GoalManagerAssignment
    catalog_entry: GoalManagerContextCatalogEntry
    context_identity_sha256: str
    authenticated_fit: AuthenticatedDependencyEvaluationFitV2
    store: PrivateArtifactRoot


@dataclass(frozen=True, slots=True)
class _ObservedShadow:
    prepared: PreparedRedDependencyShadow | RedDependencyShadowStop
    observation: RedGoalObservation
    adapter_result: RedLivingDexDependencyAdapterResult
    emulator_frames_advanced: int
    controller_actions: int


class _NoActionExecutor:
    """Make the action-free observation boundary executable only as a guard."""

    __slots__ = ("attempted_actions",)

    def __init__(self) -> None:
        self.attempted_actions = 0

    def execute(self, action: object) -> object:
        del action
        self.attempted_actions += 1
        raise RedLivingDexDependencyShadowRunError("action_free_observation")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "shadow"), required=True)
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--expected-execution-manifest-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--slot-id", required=True)
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
        stage = "action_free_red_observation"
        observed = _observe_read_only(readiness)
        stage = "one_shot_availability"
        if args.mode == "preflight":
            result = _preflight(readiness, observed)
        else:
            stage = "shadow_prediction"
            result = _execute_shadow(readiness, observed)
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
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
    design = _read_frozen_public_design()
    evaluation_design = _read_evaluation_design()
    public_bindings = _current_public_bindings(
        lane_id=LANE_ID,
        runner=RUNNER_RELATIVE,
        dependencies=list(DEPENDENCIES),
    )
    if public_bindings.get("source_bundle_sha256") != working_source_bundle_sha256(
        PROJECT_ROOT
    ) or public_bindings.get("adapter_sha256") != _file_sha256(
        PROJECT_ROOT / "src/pokemon_red_completion/red_living_dex_dependency_adapter.py"
    ):
        raise RedLivingDexDependencyShadowRunError("public_source_authentication")
    semantic = _semantic_bindings(args, evaluation_design)
    invocation = rootless_execution_invocation(
        lane_id=LANE_ID,
        operation=args.mode,
        semantic_bindings=semantic,
        public_bindings=public_bindings,
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
        current_public_bindings=public_bindings,
    )
    bindings = design.get("binding_contract")
    if not isinstance(bindings, dict) or bindings.get("model_sha256") != MODEL_SHA256:
        raise RedLivingDexDependencyShadowRunError("public_design_authentication")
    return _PublicGate(hashlib.sha256(payload).hexdigest(), public_bindings, evaluation_design)


def _semantic_bindings(
    args: argparse.Namespace,
    evaluation_design: RootlessDependencyEvaluationDesignV2,
) -> dict[str, str]:
    slot_id = _safe_id(args.slot_id, "context slot")
    source_commit = _commit(args.registry_source_commit, "registry source")
    return {
        "adapter_sha256": ADAPTER_SHA256,
        "context_catalog_document_sha256": _sha(
            args.expected_context_catalog_sha256,
            "context catalog",
        ),
        "context_plan_document_sha256": _sha(
            args.expected_context_plan_sha256,
            "context plan",
        ),
        "evaluation_design_document_sha256": EVALUATION_DESIGN_DOCUMENT_SHA256,
        "evaluation_design_sha256": evaluation_design.design_sha256,
        "executable_bundle_sha256": EXECUTABLE_BUNDLE_SHA256,
        "fit_execution_identity_sha256": FIT_EXECUTION_IDENTITY_SHA256,
        "fit_execution_manifest_sha256": FIT_EXECUTION_MANIFEST_SHA256,
        "fit_manifest_record_sha256": FIT_MANIFEST_RECORD_SHA256,
        "fit_record_sha256": FIT_RECORD_SHA256,
        "fit_sha256": FIT_SHA256,
        "fit_terminal_record_sha256": FIT_TERMINAL_RECORD_SHA256,
        "model_sha256": MODEL_SHA256,
        "red_rom_sha256": POKEMON_RED_US_REV_0.sha256,
        "registry_sha256": _sha(args.expected_registry_sha256, "registry"),
        "registry_source_commit_sha256": hashlib.sha256(source_commit.encode("ascii")).hexdigest(),
        "selected_context_slot_sha256": canonical_sha256(
            {"schema": "pokemon.red.shadow-context-slot.v1", "slot_id": slot_id}
        ),
        "selected_profile_sha256": _sha(args.expected_profile_sha256, "profile"),
        "shadow_design_document_sha256": DESIGN_DOCUMENT_SHA256,
        "train_dataset_sha256": TRAIN_DATASET_SHA256,
    }


def _prepare_readiness(args: argparse.Namespace, gate: _PublicGate) -> _Readiness:
    runtime = build_runtime_identity()
    if runtime.sha256 != gate.public_bindings.get("runtime_sha256"):
        raise RedLivingDexDependencyShadowRunError("runtime_authentication")
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    if rom.sha256 != POKEMON_RED_US_REV_0.sha256:
        raise RedLivingDexDependencyShadowRunError("rom_authentication")

    registry_source_commit = _commit(args.registry_source_commit, "registry source")
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        registry_source_commit,
    )
    if registry.registry_sha256 != _sha(args.expected_registry_sha256, "registry"):
        raise RedLivingDexDependencyShadowRunError("registry_authentication")
    assignment = registry.assignment(_safe_id(args.slot_id, "context slot"))
    if assignment.partition != "train":
        raise RedLivingDexDependencyShadowRunError("development_partition_authentication")

    catalog_bytes = _read_external_bytes(
        args.context_catalog,
        maximum_bytes=_MAX_CONTEXT_DOCUMENT_BYTES,
        forbidden=(rom_path,),
    )
    if hashlib.sha256(catalog_bytes).hexdigest() != _sha(
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise RedLivingDexDependencyShadowRunError("context_catalog_authentication")
    catalog = parse_goal_manager_context_catalog(catalog_bytes, registry)
    catalog_entry = catalog.entry(assignment.slot_id)
    if catalog_entry.assignment_id != assignment.assignment_id:
        raise RedLivingDexDependencyShadowRunError("context_catalog_authentication")

    plan_bytes = _read_external_bytes(
        args.context_plan,
        maximum_bytes=_MAX_CONTEXT_DOCUMENT_BYTES,
        forbidden=(rom_path, args.context_catalog),
    )
    if hashlib.sha256(plan_bytes).hexdigest() != _sha(
        args.expected_context_plan_sha256,
        "context plan",
    ):
        raise RedLivingDexDependencyShadowRunError("context_plan_authentication")
    plan_entry = _context_plan_entry(
        plan_bytes,
        slot_id=assignment.slot_id,
        registry_sha256=registry.registry_sha256,
        source_commit=registry.execution.source_commit,
    )
    forbidden = (rom_path, args.context_catalog, args.context_plan)
    state_bytes = _read_external_bytes(
        plan_entry.state,
        maximum_bytes=_MAX_STATE_BYTES,
        forbidden=forbidden,
    )
    envelope_bytes = _read_external_bytes(
        plan_entry.envelope,
        maximum_bytes=_MAX_CONTEXT_DOCUMENT_BYTES,
        forbidden=(*forbidden, plan_entry.state),
    )
    profile_bytes = _read_external_bytes(
        plan_entry.profile,
        maximum_bytes=_MAX_CONTEXT_DOCUMENT_BYTES,
        forbidden=(*forbidden, plan_entry.state, plan_entry.envelope),
    )
    capture = parse_goal_manager_context_capture(state_bytes, envelope_bytes)
    profile = parse_red_goal_context_profile(profile_bytes)
    if (
        capture.capture_id != assignment.slot_id
        or profile.profile_id != assignment.slot_id
        or capture.capture_id != catalog_entry.capture_id
        or capture.state_sha256 != catalog_entry.state_sha256
        or capture.envelope_sha256 != catalog_entry.envelope_sha256
        or capture.state_sha256 != hashlib.sha256(state_bytes).hexdigest()
        or capture.envelope_sha256 != hashlib.sha256(envelope_bytes).hexdigest()
        or profile.profile_sha256 != hashlib.sha256(profile_bytes).hexdigest()
        or profile.profile_sha256 != _sha(args.expected_profile_sha256, "profile")
    ):
        raise RedLivingDexDependencyShadowRunError("selected_context_authentication")
    context_identity_sha256 = canonical_sha256(
        {
            "schema": "pokemon.red.private-living-dex-dependency-shadow-context.v1",
            "registry_sha256": registry.registry_sha256,
            "context_catalog_sha256": catalog.catalog_sha256,
            "context_id": catalog_entry.context_id,
            "assignment_id": assignment.assignment_id,
            "slot_id": assignment.slot_id,
            "source_registry_partition": assignment.partition,
            "shadow_evaluation_partition": "development",
            "state_sha256": capture.state_sha256,
            "envelope_sha256": capture.envelope_sha256,
            "profile_sha256": profile.profile_sha256,
            "rom_sha256": rom.sha256,
        }
    )
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    authenticated_fit = _authenticate_fit_bundle(store, gate.evaluation_design)
    if authenticated_fit.model_sha256 != MODEL_SHA256:
        raise RedLivingDexDependencyShadowRunError("fit_bundle_authentication")
    return _Readiness(
        gate,
        runtime,
        rom_path,
        rom,
        capture,
        profile,
        assignment,
        catalog_entry,
        context_identity_sha256,
        authenticated_fit,
        store,
    )


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
        raise RedLivingDexDependencyShadowRunError("fit_bundle_authentication")
    fit_identity = DependencyEvaluationFitIdentity(
        design_sha256=EVALUATION_DESIGN_SHA256,
        train_dataset_sha256=TRAIN_DATASET_SHA256,
        fit_record_sha256=FIT_RECORD_SHA256,
        fit_sha256=FIT_SHA256,
        model_sha256=MODEL_SHA256,
        fit_execution_manifest_sha256=FIT_EXECUTION_MANIFEST_SHA256,
        executable_bundle_sha256=EXECUTABLE_BUNDLE_SHA256,
    )
    pins = DependencyEvaluationBundlePins(
        fit_identity,
        FIT_MANIFEST_RECORD_SHA256,
        FIT_TERMINAL_RECORD_SHA256,
    )
    manifest_document = manifest_record.read()
    fit_claim = dependency_fit_claim_from_manifest_document_v2(manifest_document)
    if (
        fit_claim.semantic_claim_sha256 != FIT_CLAIM_SHA256
        or fit_claim.execution_identity_sha256 != FIT_EXECUTION_IDENTITY_SHA256
    ):
        raise RedLivingDexDependencyShadowRunError("fit_bundle_authentication")
    return authenticate_v2_dependency_evaluation_fit_bundle(
        design,
        fit_claim=fit_claim,
        pins=pins,
        fit_record_bytes=canonical_manifest_line(fit_record.read()),
        fit_manifest_record_bytes=canonical_manifest_line(manifest_document),
        fit_terminal_record_bytes=canonical_manifest_line(terminal_record.read()),
    )


def _observe_read_only(readiness: _Readiness) -> _ObservedShadow:
    if os.environ.get(ENCOUNTER_LOG_VARIABLE, "").strip():
        raise RedLivingDexDependencyShadowRunError("zero_effect_environment")
    require_pyboy_import_origins(readiness.runtime)
    rejecting = _NoActionExecutor()
    actions = CountingExecutor(rejecting)
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
        runtime = build_red_goal_context_runtime(
            profile=readiness.profile,
            capture=readiness.capture,
            emulator=emulator,
            reader=reader,
        )
        observation = runtime.adapter.observe()
        bindings = runtime.enumerator(actions).enumerate(observation)
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
            or tuple(binding.kind for binding in bindings.bindings)
            != readiness.catalog_entry.available_goal_kinds
        ):
            raise RedLivingDexDependencyShadowRunError("historical_context_replay")
        frame_after = emulator.frame_count
        if (
            frame_after != frame_before
            or actions.actions_executed != 0
            or rejecting.attempted_actions != 0
            or emulator.pressed_buttons
        ):
            raise RedLivingDexDependencyShadowRunError("zero_effect_authentication")
        facts, exact_pairs = _execution_facts(readiness.profile, bindings.bindings)
        adapter_result = adapt_red_living_dex_dependencies(
            observation.collection_observation,
            execution_facts=facts,
        )
        exact_binding_ids = frozenset(
            opportunity.binding.binding_sha256
            for opportunity in adapter_result.opportunities
            if (
                opportunity.binding.precursor_species_ref,
                opportunity.binding.evolved_species_ref,
            )
            in exact_pairs
        )
        prepared = prepare_red_dependency_shadow(
            adapter_result,
            design_sha256=DESIGN_DOCUMENT_SHA256,
            model_sha256=MODEL_SHA256,
            context_identity_sha256=readiness.context_identity_sha256,
            execution_capable_binding_sha256s=exact_binding_ids,
        )
        require_pyboy_import_origins(readiness.runtime)
    require_pyboy_import_origins(readiness.runtime)
    if verify_rom(readiness.rom_path).sha256 != readiness.rom.sha256:
        raise RedLivingDexDependencyShadowRunError("protected_input_integrity")
    return _ObservedShadow(prepared, observation, adapter_result, 0, 0)


def _execution_facts(
    profile: RedGoalContextProfile,
    bindings: tuple[object, ...],
) -> tuple[RedDependencyExecutionFacts, frozenset[tuple[str, str]]]:
    by_kind = {getattr(binding, "kind", None): binding for binding in bindings}
    acquisition_refs: set[str] = set()
    exact_pairs: set[tuple[str, str]] = set()
    for provider in profile.providers:
        binding = by_kind.get(provider.kind)
        binding_ref = getattr(binding, "binding_ref", None)
        if not isinstance(binding_ref, str):
            continue
        if (
            provider.kind is GoalKind.ACQUIRE_SPECIES
            and provider.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE
        ):
            source_id = provider.parameters.get("source_id")
            if isinstance(source_id, str) and binding_ref.startswith(
                f"pokemon.red:acquisition:{source_id}:"
            ):
                acquisition_refs.update(
                    method.species_ref
                    for method in RED_ACQUISITION_CATALOG.methods_at_source(source_id)
                    if not method.transforms_precursor
                )
        if (
            provider.kind is GoalKind.EVOLVE_SPECIES
            and provider.mechanic is RedGoalMechanic.DIGLETT_EVOLUTION
            and binding_ref.startswith("pokemon.red:evolution:diglett-to-dugtrio:")
        ):
            exact_pairs.add(
                (
                    red_species_ref(red_internal_species_number(DIGLETT_SPECIES_ID)),
                    red_species_ref(red_internal_species_number(DUGTRIO_SPECIES_ID)),
                )
            )
    return (
        RedDependencyExecutionFacts(acquirable_precursor_refs=frozenset(acquisition_refs)),
        frozenset(exact_pairs),
    )


def _preflight(readiness: _Readiness, observed: _ObservedShadow) -> dict[str, object]:
    root_claim, execution_identity, episode_id = _execution_identities(
        readiness,
        observed.prepared,
    )
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        _require_fit_claim(registry)
        if (
            not root_claim_is_available(registry, root_claim)
            or readiness.store.inspect_episode_state(episode_id).status != "absent"
        ):
            raise RedLivingDexDependencyShadowRunError("one_shot_availability")
    del execution_identity
    if isinstance(observed.prepared, RedDependencyShadowStop):
        return observed.prepared.public_dict()
    return {
        "schema": "pokemon.red.living-dex-dependency-shadow-preflight.v1",
        "status": "ready_identity_unclaimed",
        "candidate_count": 2,
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames_advanced": 0,
        "teacher_queries": 0,
        "execution_identity_consumed": False,
        "identity_fields_public": 0,
    }


def _execute_shadow(
    readiness: _Readiness,
    observed: _ObservedShadow,
) -> dict[str, object]:
    prepared = observed.prepared
    root_claim, execution_identity, episode_id = _execution_identities(readiness, prepared)
    registry = open_fixed_account_claim_registry()
    writer: EpisodeWriter | None = None
    prediction_started = False
    prediction_completed = False
    decision_persisted = False
    terminal_append_started = False
    terminal_persisted = False
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        _require_fit_claim(registry)
        if (
            not root_claim_is_available(registry, root_claim)
            or readiness.store.inspect_episode_state(episode_id).status != "absent"
        ):
            raise RedLivingDexDependencyShadowRunError("one_shot_availability")
        write_root_claim(
            registry,
            root_consumption_sha256=root_claim,
            execution_identity_sha256=execution_identity,
            source_commit=_text(readiness.gate.public_bindings.get("source_commit"), "source"),
            runner_sha256=_sha(
                readiness.gate.public_bindings.get("runner_sha256"),
                "runner",
            ),
        )
        try:
            writer = readiness.store.begin_episode(episode_id)
            writer.append(
                "preregistration",
                {
                    "schema": SHADOW_PREREGISTRATION_SCHEMA,
                    "root_consumption_sha256": root_claim,
                    "execution_identity_sha256": execution_identity,
                    "execution_manifest_sha256": readiness.gate.execution_manifest_sha256,
                    **prepared.private_dict(),
                },
                durable=True,
            )
            if isinstance(prepared, RedDependencyShadowStop):
                terminal_append_started = True
                writer.append("terminal", prepared.private_terminal_dict(), durable=True)
                writer.complete()
                return prepared.public_dict()
            prediction_started = True
            decision = score_red_dependency_shadow(
                prepared,
                readiness.authenticated_fit.fit.model,
            )
            prediction_completed = True
            writer.append("decision", decision.private_terminal_dict(), durable=True)
            decision_persisted = True
            terminal_append_started = True
            writer.append(
                "terminal",
                {
                    "schema": "pokemon.red.private-living-dex-dependency-shadow-complete.v1",
                    "status": "complete",
                    "root_consumption_sha256": root_claim,
                    "execution_identity_sha256": execution_identity,
                    "semantic_identity_sha256": prepared.semantic_identity_sha256,
                    "model_predictions": 1,
                    "controller_actions": 0,
                    "emulator_frames_advanced": 0,
                    "teacher_queries": 0,
                },
                durable=True,
            )
            terminal_persisted = True
            writer.complete()
            return decision.public_dict()
        except BaseException:
            if writer is not None:
                failure_phase = (
                    "model_prediction"
                    if prediction_started and not prediction_completed
                    else "decision_persistence"
                    if prediction_started and not decision_persisted
                    else "terminal_persistence"
                    if terminal_append_started and not terminal_persisted
                    else "episode_publication"
                    if terminal_persisted
                    else "preprediction_persistence"
                )
                # A failed write to the normal terminal stream may have left its
                # bytes in an uncertain state.  Retain the failure on a distinct
                # stream in that case instead of appending behind possibly partial
                # JSONL.  The preregistration already binds the exact identity.
                failure_stream = "failure" if terminal_append_started else "terminal"
                with suppress(BaseException):
                    writer.append(
                        failure_stream,
                        {
                            "schema": SHADOW_FAILURE_SCHEMA,
                            "status": (
                                "failed_after_prediction_identity_consumed"
                                if prediction_started
                                else "failed_before_prediction_identity_consumed"
                            ),
                            "failure_phase": failure_phase,
                            "root_consumption_sha256": root_claim,
                            "execution_identity_sha256": execution_identity,
                            "semantic_identity_sha256": prepared.semantic_identity_sha256,
                            "model_prediction_attempted": prediction_started,
                            "model_prediction_completed": prediction_completed,
                            "first_failure_retained": True,
                        },
                        durable=True,
                    )
                with suppress(BaseException):
                    writer.abort(
                        "shadow_prediction_failed"
                        if prediction_started
                        else "shadow_preclaim_failed"
                    )
            raise RedLivingDexDependencyShadowRunError("shadow_prediction") from None


def _execution_identities(
    readiness: _Readiness,
    prepared: PreparedRedDependencyShadow | RedDependencyShadowStop,
) -> tuple[str, str, str]:
    root_claim = canonical_sha256(
        {
            "schema": "pokemon.red.living-dex-dependency-shadow-semantic-claim.v1",
            "semantic_identity_sha256": prepared.semantic_identity_sha256,
        }
    )
    execution_identity = canonical_sha256(
        {
            "schema": "pokemon.red.living-dex-dependency-shadow-execution.v1",
            "root_consumption_sha256": root_claim,
            "execution_manifest_sha256": readiness.gate.execution_manifest_sha256,
            "source_commit": readiness.gate.public_bindings["source_commit"],
            "source_bundle_sha256": readiness.gate.public_bindings["source_bundle_sha256"],
            "runner_sha256": readiness.gate.public_bindings["runner_sha256"],
            "runtime_sha256": readiness.runtime.sha256,
        }
    )
    return root_claim, execution_identity, f"red-shadow-{execution_identity[:32]}"


def _require_fit_claim(registry: Path) -> None:
    expected = {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": FIT_CLAIM_SHA256,
        "execution_identity_sha256": FIT_EXECUTION_IDENTITY_SHA256,
        "source_commit": FIT_SOURCE_COMMIT,
        "runner_sha256": FIT_RUNNER_SHA256,
    }
    if read_root_claim(registry, FIT_CLAIM_SHA256) != expected:
        raise RedLivingDexDependencyShadowRunError("fit_claim_authentication")


def _context_plan_entry(
    payload: bytes,
    *,
    slot_id: str,
    registry_sha256: str,
    source_commit: str | None,
) -> _ContextPlanEntry:
    document = _canonical_document(payload, subject="context plan")
    if (
        set(document) != {"entries", "registry_sha256", "schema", "source_commit"}
        or document.get("schema") != CONTEXT_PLAN_SCHEMA
        or document.get("registry_sha256") != registry_sha256
        or document.get("source_commit") != source_commit
    ):
        raise RedLivingDexDependencyShadowRunError("context_plan_authentication")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise RedLivingDexDependencyShadowRunError("context_plan_authentication")
    matches = []
    for raw in entries:
        if not isinstance(raw, dict) or set(raw) != {"envelope", "profile", "slot_id", "state"}:
            raise RedLivingDexDependencyShadowRunError("context_plan_authentication")
        if raw.get("slot_id") == slot_id:
            matches.append(
                _ContextPlanEntry(
                    slot_id,
                    Path(_text(raw.get("state"), "state")),
                    Path(_text(raw.get("envelope"), "envelope")),
                    Path(_text(raw.get("profile"), "profile")),
                )
            )
    if len(matches) != 1:
        raise RedLivingDexDependencyShadowRunError("context_plan_authentication")
    return matches[0]


def _read_frozen_public_design() -> dict[str, object]:
    payload = DESIGN_PATH.read_bytes()
    if hashlib.sha256(payload).hexdigest() != DESIGN_DOCUMENT_SHA256:
        raise RedLivingDexDependencyShadowRunError("public_design_authentication")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RedLivingDexDependencyShadowRunError("public_design_authentication") from None
    if not isinstance(value, dict) or value.get("lane_id") != LANE_ID:
        raise RedLivingDexDependencyShadowRunError("public_design_authentication")
    return value


def _read_evaluation_design() -> RootlessDependencyEvaluationDesignV2:
    payload = EVALUATION_DESIGN_PATH.read_bytes()
    if hashlib.sha256(payload).hexdigest() != EVALUATION_DESIGN_DOCUMENT_SHA256:
        raise RedLivingDexDependencyShadowRunError("fit_design_authentication")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RedLivingDexDependencyShadowRunError("fit_design_authentication") from None
    if not isinstance(value, dict):
        raise RedLivingDexDependencyShadowRunError("fit_design_authentication")
    design = RootlessDependencyEvaluationDesignV2.from_dict(value)
    if (
        design.design_sha256 != EVALUATION_DESIGN_SHA256
        or design.train_revalidation_sha256 != TRAIN_DATASET_SHA256
    ):
        raise RedLivingDexDependencyShadowRunError("fit_design_authentication")
    return design


def _read_external_bytes(
    path: Path,
    *,
    maximum_bytes: int,
    forbidden: tuple[Path, ...],
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
            or resolved == project
            or project in resolved.parents
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
        raise RedLivingDexDependencyShadowRunError("private_input_authentication") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _inode(path: Path) -> tuple[int, int]:
    metadata = path.stat()
    return metadata.st_dev, metadata.st_ino


def _canonical_document(payload: bytes, *, subject: str) -> dict[str, object]:
    if not payload or len(payload) > _MAX_PUBLIC_DOCUMENT_BYTES:
        raise RedLivingDexDependencyShadowRunError(f"{subject.replace(' ', '_')}_authentication")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError):
        raise RedLivingDexDependencyShadowRunError(
            f"{subject.replace(' ', '_')}_authentication"
        ) from None
    if not isinstance(value, dict) or canonical_manifest_line(value) != payload:
        raise RedLivingDexDependencyShadowRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _require_project_import_origins() -> None:
    if _PRELOADED_PROJECT_MODULES:
        raise RedLivingDexDependencyShadowRunError("project_import_authentication")
    package_root = (SRC_ROOT / "pokemon_red_completion").resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "pokemon_red_completion" and not name.startswith("pokemon_red_completion."):
            continue
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise RedLivingDexDependencyShadowRunError("project_import_authentication")
        path = Path(raw)
        try:
            metadata = path.lstat()
            resolved = path.resolve(strict=True)
        except OSError:
            raise RedLivingDexDependencyShadowRunError("project_import_authentication") from None
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not resolved.is_relative_to(package_root)
        ):
            raise RedLivingDexDependencyShadowRunError("project_import_authentication")


def _require_script_import_origins() -> None:
    expected = {
        "freeze_rootless_execution_manifest": (
            SCRIPTS_ROOT / "freeze_rootless_execution_manifest.py"
        ),
        "public_execution_manifest": SCRIPTS_ROOT / "public_execution_manifest.py",
        "rootless_execution_manifest": SCRIPTS_ROOT / "rootless_execution_manifest.py",
    }
    for name, path in expected.items():
        module = sys.modules.get(name)
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise RedLivingDexDependencyShadowRunError("script_import_authentication")
        imported = Path(raw)
        try:
            named = imported.lstat()
            resolved = imported.resolve(strict=True)
            expected_resolved = path.resolve(strict=True)
        except OSError:
            raise RedLivingDexDependencyShadowRunError("script_import_authentication") from None
        if (
            imported.is_symlink()
            or not stat.S_ISREG(named.st_mode)
            or named.st_nlink != 1
            or resolved != expected_resolved
        ):
            raise RedLivingDexDependencyShadowRunError("script_import_authentication")


def _failure_receipt(stage: str) -> dict[str, object]:
    safe = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
    before_private = safe in {"arguments", "public_manifest_authentication"}
    return {
        "schema": "pokemon.red.living-dex-dependency-shadow-failure.v1",
        "status": "failed_closed",
        "failure_stage": safe,
        "protected_access_status": "verified_absent" if before_private else "not_attested",
        "effect_status": "verified_zero" if before_private else "not_attested",
        "execution_result_emitted": False,
        "authority_promotions_added": 0,
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "transfer_results_added": 0,
        "private_path_fields": 0,
        "private_identity_fields": 0,
    }


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexDependencyShadowRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise RedLivingDexDependencyShadowRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _safe_id(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise RedLivingDexDependencyShadowRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexDependencyShadowRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
